"""Fill the `brain` schema from a markdown brain, then render the maps into map_cache.

Usage:
    python -m yggdras.data.brain_db.loader BRAIN_COPY [--real]

Runs against a COPY of the brain: a path that is the configured brain (YGGDRAS_BRAIN) is
refused unless --real is given. Re-runnable: it wipes the brain tables and loads them again
in one transaction (brain.changes is history and is never wiped; its rows are re-attached to
notes by slug_text). Invents nothing: a field absent from the markdown is left null and
reported, and anything that does not fit the schema is listed, never forced in. A note is
never dropped for its area: an area value that fits no area stops the whole load.

Two passes, because areas and notes refer to each other: areas go in with hub_slug null,
then notes, then each area's hub_slug is filled. Chunk parents (notes.parent_slug) and the
one-primary-area rule are checked at commit, so their order does not matter.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from yggdras import config
from yggdras.data.brain_db import migrate, render
from yggdras.data.brain_db.db import DatabaseError, connect
from yggdras.data.graph import structural as st
from yggdras.data.maps import upcoming
from yggdras.data.maps.atlas import area_scopes
from yggdras.data.maps.notes import SOURCE_SHELVES, TAXONOMY, load_notes
from yggdras.data.maps.relations import MENTIONED_IN

NODE_RULES = Path("00-manual") / "node.md"
VERB_ROW = re.compile(r"^\|\s*\d+\s*\|\s*`([a-z_]+)`\s*\|\s*`([a-z_]+)`[^|]*\|(.*)\|\s*$")
# [[mentions]] are stored with a verb the code defines (the maps print them as such).
MENTION_VERB = (st.MENTION, MENTIONED_IN, "a [[link]] written outside ## Links (code)")
# Every value `area` and `also` may take, and its area code. `cross` is area 09.
AREA_CODES = {**{a: a[:2] for a in st.AREAS}, st.CROSS: render.CROSS_CODE}
# Frontmatter dates that become dated items, and their kind.
DATED = {"date": "event", "start": "start", "end": "end", "review": "review", "decided": "decided"}
# Dates inside fact lines, as today's upcoming code finds them, and their kind here.
FACT_KINDS = {"fact": "event", "valid from": "start"}
COLUMNS = (
    "slug", "name", "type", "area", "also", "description", "status", "sensitivity", "review",
    "decided", "updated", "aliases",
)  # fmt: skip
OPTIONAL_COLUMNS = {
    "description": "description",
    "status": "status",
    "sensitivity": "sensitivity",
    "review": "review_date",
    "decided": "decided_date",
    "updated": "updated_at",
}
NOTE_INSERT = (
    "INSERT INTO brain.notes (slug, title, type, area_code, parent_slug, shelf_no, description, "
    "status, sensitivity, review_date, decided_date, updated_at, archived_at, version) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, 1)"
)
ROWS = ("notes", "facts", "links", "mentions", "aliases", "dated items", "areas", "verbs")


class Refused(RuntimeError):
    pass


@dataclass
class Note:
    slug: str
    title: str
    type: str
    areas: list[str]  # area codes, the primary first, then the secondary ones as written
    parent_folder: str  # a chunk's folder under 13-sources/, else ""
    shelf_no: int
    folder: str
    description: str | None
    status: str | None
    sensitivity: str | None
    review_date: dt.date | None
    decided_date: dt.date | None
    updated_at: dt.datetime | None
    body: str
    aliases: list[str]
    dated: list[tuple[dt.date, str, str]]  # (date, kind, label)
    parent_slug: str | None = None


@dataclass
class Brain:
    """What the markdown holds, ready for the tables, and what would not fit."""

    areas: list[tuple] = field(default_factory=list)  # (code, name, holds, not_here, sort)
    hubs: dict[str, str] = field(default_factory=dict)  # area code -> hub slug
    verbs: list[tuple[str, str, str | None]] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    aliases: list[tuple[str, str, int]] = field(default_factory=list)  # (alias, slug, ord)
    links: list[tuple[str, str, str, str]] = field(default_factory=list)
    markdown: dict[str, int] = field(default_factory=dict)  # counts as the files hold them
    unplaced: list[str] = field(default_factory=list)
    left_null: dict[str, list[str]] = field(default_factory=dict)  # field -> slugs
    body_only: dict[str, int] = field(default_factory=dict)  # frontmatter key -> notes
    notes_info: list[str] = field(default_factory=list)
    upcoming: set[tuple[str, dt.date, str]] = field(default_factory=set)  # what upcoming finds

    def count(self, name: str, n: int = 1) -> None:
        self.markdown[name] = self.markdown.get(name, 0) + n


# ---------------------------------------------------------------- the copy guard


def check_copy(repo: Path, real: bool) -> None:
    """Refuse the configured (real) brain unless *real*; refuse when it can't be told."""
    if real:
        return
    config.load_env_file()
    configured = config.brain_repo()
    if configured is None:
        raise Refused(
            "YGGDRAS_BRAIN is not set, so a copy can't be told from the real brain; "
            "set it before loading a copy"
        )
    if repo.resolve() == configured.resolve():
        raise Refused(
            "this is the configured brain (YGGDRAS_BRAIN), not a copy; load a copy, or pass --real"
        )


# ---------------------------------------------------------------- reading the markdown


def _date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def fact_lines(body: str) -> int:
    parts = st._split(body)
    if parts is None:
        return 0
    return sum(
        1
        for heading, _, line in st.sections(parts[1], parts[2])
        if heading == st.FACTS_HEADING and line.startswith("- ")
    )


def read_verbs(root: Path, out: Brain) -> None:
    rules = root / NODE_RULES
    if not rules.is_file():
        out.unplaced.append(f"verbs: {NODE_RULES.as_posix()} not found; no verbs loaded")
        return
    inside = False
    for line in rules.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Link verbs"
            continue
        m = VERB_ROW.match(line) if inside else None
        if m:
            meaning = " ".join(m.group(3).split()) or None
            out.verbs.append((m.group(1), m.group(2), meaning))
    out.markdown["verbs"] = len(out.verbs)
    missing = sorted(set(st.VERBS) - {v for v, _, _ in out.verbs})
    if missing:
        out.notes_info.append(f"verbs the code knows but node.md does not list: {missing}")
    if st.MENTION not in {v for v, _, _ in out.verbs}:
        out.verbs.append(MENTION_VERB)
        out.notes_info.append(
            f"verb '{st.MENTION}' (inverse '{MENTIONED_IN}') added by the loader for [[mentions]]"
        )


def read_areas(root: Path, out: Brain) -> None:
    taxonomy = root / TAXONOMY
    scopes = area_scopes(taxonomy.read_text(encoding="utf-8")) if taxonomy.is_file() else {}
    out.markdown["areas"] = sum(1 for a in st.AREAS if a in scopes)
    for area in st.AREAS:
        code, _, name = area.partition("-")
        holds, not_here = scopes.get(area, (None, None))
        if area not in scopes:
            out.left_null.setdefault("areas.belongs_here, areas.not_here", []).append(code)
        out.areas.append((code, name, holds, not_here, int(code)))
    out.areas.append((render.CROSS_CODE, render.CROSS_NAME, None, None, int(render.CROSS_CODE)))
    out.left_null.setdefault("areas.belongs_here, areas.not_here", []).append(render.CROSS_CODE)
    out.left_null["areas.node_range"] = [a[0] for a in out.areas]
    out.notes_info.append(
        f"area {render.CROSS_CODE}-{render.CROSS_NAME} added by the loader for `area: cross` "
        "(taxonomy.md lists 01–08)"
    )


def note_areas(slug: str, fm: dict, out: Brain, bad: list[str]) -> list[str]:
    """The note's area codes, primary first. A missing area is `cross`, as the maps read it.
    A value that fits no area goes to *bad*: the load stops."""
    area = _text(fm.get("area"))
    if area is None:
        out.notes_info.append(f"{slug}: no area; loaded as cross, as today's maps read it")
        area = st.CROSS
    codes = []
    for value in [area, *st._as_list(fm.get("also"))]:
        code = AREA_CODES.get(value)
        if code is None:
            bad.append(f"{slug}: area '{value}' fits no area")
        elif code in codes:
            out.notes_info.append(f"{slug}: area '{value}' written twice, stored once")
        else:
            codes.append(code)
    return codes


def dated_items(slug: str, title: str, type_: str, fm: dict, body: str, out: Brain) -> list:
    """Frontmatter dates, and the dates inside fact lines exactly as the upcoming view reads
    them (hubs left out, History left out). Each (date, kind, label) once."""
    found: set[tuple[dt.date, str, str]] = set()
    for key, kind in DATED.items():
        value = fm.get(key)
        if value is None:
            continue
        out.count("dated items (frontmatter)")
        if key == "review":  # as upcoming reads it: the first ISO date in the text
            m = upcoming.ISO.search(str(value))
            day = upcoming._date(m.group(1), m.group(2), m.group(3))[0] if m else None
        else:
            day = _date(value)
        if day is None:
            if key not in OPTIONAL_COLUMNS:  # review/decided are reported with the column
                out.unplaced.append(f"{slug}: {key} '{value}' is not a date; not loaded")
            continue
        found.add((day, kind, f"{title} ({kind})"))
    if type_ != st.HUB:
        for line in upcoming.current_fact_lines(body):
            for day, _, kind in upcoming.fact_dates(line):
                out.count("dated items (fact lines)")
                found.add((day, FACT_KINDS[kind], f"{title} ({FACT_KINDS[kind]})"))
    return sorted(found)


def read_notes(root: Path, out: Brain) -> None:
    seen: dict[str, str] = {}
    bad: list[str] = []
    for path in st.node_files(root, st.mapped_shelves()):
        rel = path.relative_to(root).as_posix()
        body = path.read_bytes().decode("utf-8")
        parts = st._split(body)
        if parts is None:
            out.unplaced.append(f"{rel}: no frontmatter")
            continue
        try:
            fm = yaml.safe_load(parts[0]) or {}
        except yaml.YAMLError:
            out.unplaced.append(f"{rel}: frontmatter does not parse")
            continue
        out.count("notes")
        out.count("facts", fact_lines(body))
        out.count("aliases", len(st._as_list(fm.get("aliases"))))
        slug = _text(fm.get("slug"))
        if not slug:
            out.unplaced.append(f"{rel}: no slug")
            continue
        if slug in seen:
            out.unplaced.append(f"{rel}: duplicate slug '{slug}' (also {seen[slug]})")
            continue
        seen[slug] = rel
        missing = [k for k in ("name", "type") if not _text(fm.get(k))]
        if missing:
            out.unplaced.append(f"{slug}: no {', '.join(missing)} (a required column)")
            continue
        title, type_ = _text(fm["name"]), _text(fm["type"])
        codes = note_areas(slug, fm, out, bad)
        values = {}
        for key, column in OPTIONAL_COLUMNS.items():
            raw = fm.get(key)
            if raw is None or _text(raw) is None:
                out.left_null.setdefault(f"notes.{column}", []).append(slug)
                values[key] = None
            elif key in ("review", "decided", "updated"):
                day = _date(raw)
                if day is None:
                    out.unplaced.append(
                        f"{slug}: {key} '{raw}' is not a date; column left null"
                        + ("" if key == "updated" else ", no dated item")
                    )
                values[key] = day
            else:
                values[key] = _text(raw)
        for key in fm:
            if key not in COLUMNS and key not in DATED:
                out.body_only[key] = out.body_only.get(key, 0) + 1
        folder = rel.split("/")[0]
        bits = rel.split("/")
        updated = values["updated"]
        out.notes.append(
            Note(
                slug=slug,
                title=title,
                type=type_,
                areas=codes,
                parent_folder=bits[1] if len(bits) == 3 and bits[0] in SOURCE_SHELVES else "",
                shelf_no=int(folder[:2]),
                folder=folder,
                description=values["description"],
                status=values["status"],
                sensitivity=values["sensitivity"],
                review_date=values["review"],
                decided_date=values["decided"],
                updated_at=dt.datetime.combine(updated, dt.time(), dt.UTC) if updated else None,
                body=body,
                aliases=st._as_list(fm.get("aliases")),
                dated=dated_items(slug, title, type_, fm, body, out),
            )
        )
    if bad:
        raise Refused(
            "these notes have an area that fits no area; nothing was loaded:\n  - "
            + "\n  - ".join(bad)
        )
    out.notes.sort(key=lambda n: n.slug)
    out.markdown["dated items"] = sum(len(n.dated) for n in out.notes)


def read_parents(out: Brain) -> None:
    """A chunk's parent is the note its folder is named after (13-sources/<parent>/...)."""
    loaded = {n.slug for n in out.notes}
    for n in out.notes:
        if not n.parent_folder:
            continue
        if n.parent_folder in loaded and n.parent_folder != n.slug:
            n.parent_slug = n.parent_folder
        else:
            out.unplaced.append(
                f"{n.slug}: a chunk in folder '{n.parent_folder}', which is no note; "
                "parent_slug left null"
            )


def read_hubs(out: Brain) -> None:
    by_area: dict[str, list[str]] = {}
    for n in out.notes:
        if n.type == st.HUB and n.folder[:2] == n.areas[0]:
            by_area.setdefault(n.areas[0], []).append(n.slug)
    for code, *_ in out.areas:
        hubs = sorted(by_area.get(code, []))
        if hubs:
            out.hubs[code] = hubs[0]
        else:
            out.left_null.setdefault("areas.hub_slug", []).append(code)
        if len(hubs) > 1:
            out.unplaced.append(f"area {code}: several hubs {hubs}; kept {hubs[0]}")


def read_aliases(out: Brain) -> None:
    owner: dict[str, str] = {}
    for n in out.notes:
        for alias in n.aliases:
            if alias in owner:
                if owner[alias] != n.slug:
                    out.unplaced.append(
                        f"alias '{alias}' of {n.slug}: already an alias of {owner[alias]}"
                    )
                else:
                    out.notes_info.append(f"alias '{alias}' written twice in {n.slug}")
                continue
            owner[alias] = n.slug
            out.aliases.append((alias, n.slug, len([a for a in out.aliases if a[1] == n.slug])))


def read_links(root: Path, out: Brain) -> None:
    """Link, hub and mention lines, resolved as the map builds them. A link written with an
    inverse verb ("has_part") is stored once, the other way round, with its verb ("part_of")."""
    graph = st.build_map(root, st.mapped_shelves())
    loaded = {n.slug for n in out.notes}
    verbs = {v for v, _, _ in out.verbs}
    inverse_of = {inv: v for v, inv, _ in out.verbs if inv not in verbs}
    rows: dict[tuple[str, str, str], str] = {}
    for e in graph["edges"]:
        a, b, kind, verb = e["from_slug"], e["to_slug"], e["kind"], e["reason"]
        out.count("mentions" if kind == "mention" else "links")
        where = f"{a} → {verb} [[{e['written_as']}]]"
        if kind != "mention" and verb not in verbs and verb in inverse_of:
            a, b, verb = b, a, inverse_of[verb]
            out.notes_info.append(
                f"{where}: written with an inverse verb, stored as {a} {verb} {b}"
            )
        if verb not in verbs:
            out.unplaced.append(f"link {where}: verb not in the verb list")
        elif a == b:
            out.unplaced.append(f"{kind} {where}: a note linking to itself")
        elif a not in loaded or b not in loaded:
            gone = a if a not in loaded else b
            out.unplaced.append(f"{kind} {where}: {gone} is not in the database")
        elif (a, verb, b) in rows:
            what = "mentioned" if kind == "mention" else "written"
            out.notes_info.append(f"{kind} {where}: {what} more than once, stored once")
        else:
            rows[(a, verb, b)] = kind
    for d in graph["dangling"]:
        out.count("mentions" if d["kind"] == "mention" else "links")
        out.unplaced.append(
            f"{d['kind']} {d['from_slug']} → {d['reason']} [[{d['written_as']}]]: no such note"
        )
    out.links = sorted((a, v, b, k) for (a, v, b), k in rows.items())
    for problem in graph["errors"]:
        if "ambiguous" in problem["problem"]:
            out.unplaced.append(f"{problem['path']}: {problem['problem']}")


def read_upcoming(root: Path, out: Brain) -> None:
    """Every dated item today's upcoming code finds (all dates, not just the next 120 days),
    as (slug, date, kind here): the check that fact-line dates all reach dated_items."""
    notes = load_notes(root, st.mapped_shelves())
    texts = {s: (root / n.path).read_text(encoding="utf-8") for s, n in notes.items()}
    kinds = {**FACT_KINDS, "review": "review"}
    for shown, slug, label in upcoming.rows(notes, texts, dt.date(1, 1, 1), days=3_000_000):
        kind = label.rsplit("(", 1)[1].rstrip(")")
        day = dt.date.fromisoformat(shown if len(shown) == 10 else f"{shown}-01")
        out.upcoming.add((slug, day, kinds[kind]))


def read_brain(repo: Path) -> Brain:
    """Everything the loader will write, read from the markdown. Writes nothing."""
    root = repo / st.LIBRARY
    if not root.is_dir():
        raise Refused(f"no {st.LIBRARY}/ folder in {repo}")
    out = Brain()
    read_verbs(root, out)
    read_areas(root, out)
    read_notes(root, out)
    read_parents(out)
    read_hubs(out)
    read_aliases(out)
    read_links(root, out)
    read_upcoming(root, out)
    archived = repo / "archive"
    if archived.is_dir():
        count = sum(1 for _ in archived.rglob("*.md"))
        if count:
            out.notes_info.append(
                f"{count} archived note file(s) under archive/ not loaded "
                "(their archive date lives in git, not in the markdown)"
            )
    return out


# ---------------------------------------------------------------- writing the tables


WIPE = (
    "DELETE FROM brain.relationships",
    "DELETE FROM brain.aliases",
    "DELETE FROM brain.dated_items",
    "DELETE FROM brain.note_bodies",
    "DELETE FROM brain.note_areas",
    "UPDATE brain.areas SET hub_slug = NULL",
    "DELETE FROM brain.notes",  # brain.changes keeps its rows: slug becomes null
    "DELETE FROM brain.areas",
    "DELETE FROM brain.verbs",
    "ALTER TABLE brain.dated_items ALTER COLUMN id RESTART WITH 1",
)


def write(conn, brain: Brain) -> None:
    """Wipe and reload the brain tables in one transaction; then render map_cache."""
    with conn.transaction(), conn.cursor() as cur:
        for sql in WIPE:
            cur.execute(sql)
        cur.executemany("INSERT INTO brain.verbs (verb, inverse, meaning) VALUES (%s, %s, %s)",
                        brain.verbs)  # fmt: skip
        # Pass 1: areas without hubs, then the notes that refer to them.
        cur.executemany(
            "INSERT INTO brain.areas (area_code, name, node_range, hub_slug, belongs_here, "
            "not_here, sort_order) VALUES (%s, %s, NULL, NULL, %s, %s, %s)",
            brain.areas,
        )
        cur.executemany(
            NOTE_INSERT,
            [
                (n.slug, n.title, n.type, n.areas[0], n.parent_slug, n.shelf_no, n.description,
                 n.status, n.sensitivity, n.review_date, n.decided_date, n.updated_at)
                for n in brain.notes
            ],
        )  # fmt: skip
        cur.executemany(
            "INSERT INTO brain.note_areas (slug, area_code, is_primary, ord) "
            "VALUES (%s, %s, %s, %s)",
            [(n.slug, code, i == 0, i) for n in brain.notes for i, code in enumerate(n.areas)],
        )
        cur.executemany(
            "INSERT INTO brain.note_bodies (slug, body) VALUES (%s, %s)",
            [(n.slug, n.body) for n in brain.notes],
        )
        cur.executemany(
            "INSERT INTO brain.aliases (alias, slug, ord) VALUES (%s, %s, %s)", brain.aliases
        )
        cur.executemany(
            "INSERT INTO brain.dated_items (slug, date, kind, label) VALUES (%s, %s, %s, %s)",
            [(n.slug, day, kind, label) for n in brain.notes for day, kind, label in n.dated],
        )
        cur.executemany(
            "INSERT INTO brain.relationships (from_slug, verb, to_slug, kind) "
            "VALUES (%s, %s, %s, %s)",
            brain.links,
        )
        # Pass 2: each area's hub.
        cur.executemany(
            "UPDATE brain.areas SET hub_slug = %s WHERE area_code = %s",
            [(slug, code) for code, slug in sorted(brain.hubs.items())],
        )
        # History survives a reload: re-attach it to the notes it names.
        cur.execute(
            "UPDATE brain.changes c SET slug = c.slug_text FROM brain.notes n "
            "WHERE c.slug IS NULL AND n.slug = c.slug_text"
        )
    conn.commit()
    render.build_cache(conn)


def _rows(conn, sql: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    conn.commit()
    return rows


def database_counts(conn) -> dict[str, int]:
    def one(sql: str) -> int:
        return _rows(conn, sql)[0][0]

    bodies = _rows(conn, 'SELECT body FROM brain.note_bodies ORDER BY slug COLLATE "C"')
    return {
        "notes": one("SELECT count(*) FROM brain.notes"),
        "facts": sum(fact_lines(body) for (body,) in bodies),
        "links": one("SELECT count(*) FROM brain.relationships WHERE kind <> 'mention'"),
        "mentions": one("SELECT count(*) FROM brain.relationships WHERE kind = 'mention'"),
        "aliases": one("SELECT count(*) FROM brain.aliases"),
        "dated items": one("SELECT count(*) FROM brain.dated_items"),
        "areas": one("SELECT count(*) FROM brain.areas"),
        "verbs": one("SELECT count(*) FROM brain.verbs"),
    }


def upcoming_check(conn, brain: Brain) -> str:
    stored = set(_rows(conn, "SELECT slug, date, kind FROM brain.dated_items"))
    missing = sorted(brain.upcoming - stored)
    line = (
        f"dated items check: today's upcoming code finds {len(brain.upcoming)} "
        f"(fact lines and reviews, all dates); {len(brain.upcoming) - len(missing)} of them "
        "are in dated_items"
    )
    return line + "".join(f"\n  - missing: {s} {d} {k}" for s, d, k in missing)


def report(brain: Brain, db: dict[str, int], check: str) -> str:
    out = ["brain load: count report", f"{'':14}{'markdown':>10}{'database':>10}"]
    for name in ROWS:
        out.append(f"{name:14}{brain.markdown.get(name, 0):>10}{db.get(name, 0):>10}")
    out.append(
        f"  (dated items in the markdown: {brain.markdown.get('dated items (frontmatter)', 0)} "
        f"frontmatter dates, {brain.markdown.get('dated items (fact lines)', 0)} fact-line "
        "dates; the same date, kind and note once)"
    )
    out += ["", check]
    out += ["", f"couldn't place ({len(brain.unplaced)}):"]
    out += [f"  - {line}" for line in brain.unplaced] or ["  - nothing"]
    out += ["", "left null (absent from the markdown):"]
    for name, unsorted in sorted(brain.left_null.items()):
        slugs = sorted(unsorted)
        shown = ", ".join(slugs[:8]) + (f", … ({len(slugs)} in all)" if len(slugs) > 8 else "")
        out.append(f"  - {name}: {shown}")
    if brain.body_only:
        out += ["", "frontmatter with no column (kept in note_bodies only):"]
        out += [f"  - {k}: {n} note(s)" for k, n in sorted(brain.body_only.items())]
    if brain.notes_info:
        out += ["", "notes:"]
        out += [f"  - {line}" for line in brain.notes_info]
    return "\n".join(out) + "\n"


def load(conn, repo: Path) -> str:
    """Read *repo*, reload the tables, render the maps; return the count report."""
    latest = max((m.version for m in migrate.migrations()), default=0)
    if migrate.current(conn) != latest:
        raise Refused("the brain schema is not at the latest migration; run migrate up first")
    brain = read_brain(repo)
    write(conn, brain)
    return report(brain, database_counts(conn), upcoming_check(conn, brain))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m yggdras.data.brain_db.loader")
    parser.add_argument("brain", type=Path, help="a COPY of the brain repo")
    parser.add_argument("--real", action="store_true", help="allow the configured brain itself")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # the report has arrows; Windows consoles are cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        check_copy(args.brain, args.real)
        conn = connect()
        with conn:
            print(load(conn, args.brain), end="")
    except (Refused, DatabaseError) as exc:
        print(f"not loaded: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
