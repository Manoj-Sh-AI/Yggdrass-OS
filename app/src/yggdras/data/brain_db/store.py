"""The brain in rows (D44): what Lia reads, and how her writes land.

Reading: a snapshot of the live notes (archived_at is null): their bodies, with the History
section rendered back from `changes` so Lia reads exactly what she read from files; the
three maps from map_cache (never a live query at question time); the manual.

Writing: one transaction per request. The planner (ops.Builder) and the checker run, as
before, on a scratch copy of the current rows (a workspace folder), so every rule stays the
same. The result is saved in one transaction:
- note bodies (History lines are never stored: they become `changes` rows);
- every derived row (areas, aliases, links, dates) re-derived from the bodies by the loader's
  own parser;
- one `changes` row per changed line, with its place, so Undo can rebuild the note exactly;
- the three maps rebuilt into map_cache.
A note whose version moved since it was read is never overwritten: the write is refused
("reload and review").
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from yggdras.data.brain import notefile as nf
from yggdras.data.brain.checker import Checker
from yggdras.data.brain.ops import Builder, Change, OpError
from yggdras.data.brain.write_path import Outcome
from yggdras.data.brain_db import loader, render
from yggdras.data.graph import structural as st
from yggdras.data.maps.notes import NoteMeta, meta_from_text

SHELF_FOLDERS = {int(s[:2]): s for s in st.SHELVES}
LOCK_KEY = 0x59474744  # pg_advisory_xact_lock: one writer at a time
TAG = re.compile(r"(?:; |\()((?:until|wrong):[^)]*)\)$")
ACTOR = "Manoj via {app}"


class Stale(RuntimeError):
    """A note changed since it was read."""


def lib_path(slug: str, shelf_no: int, parent: str | None) -> str:
    folder = SHELF_FOLDERS[shelf_no]
    return f"{folder}/{parent}/{slug}.md" if parent else f"{folder}/{slug}.md"


# ---------------------------------------------------------------- History, rendered from rows


# What Lia reads as a note's History: the section the loader kept as written (one row,
# section '## History'), then each fact Lia replaced since (old text and tag), in order.
HISTORY_SQL = (
    "SELECT c.slug, c.old_text, c.tag, c.section, c.pos FROM brain.changes c "
    "WHERE c.slug IS NOT NULL AND c.old_text IS NOT NULL AND ("
    "(c.section = '## History' AND c.actor = 'markdown-history') OR "
    "(c.section = '## Facts' AND c.kind = 'replace' AND c.tag IS NOT NULL AND "
    + render.LIVE_HISTORY
    + ")) "
    'ORDER BY c.slug COLLATE "C", c.created_at, c.id'
)


def history_item(old_text: str, tag: str | None) -> str:
    """A History line as node.md writes it: loaded ones verbatim, new ones tagged now."""
    if tag is None:
        return old_text
    return nf.tagged(old_text.removeprefix("- "), tag)


def with_history(body: str, items: list[str], block: tuple[str, int | None] | None = None) -> str:
    """The body with its ## History section put back, as the files held it: the section the
    loader kept (*block*: its text and the line it sat at, None for the end), exactly; then
    the facts replaced since, as the planner writes them."""
    if not items and not block:
        return body
    lines = body.split("\n")
    if block:
        text, at = block
        if at is None:
            at = len(lines)
        else:  # before the heading it preceded (found from where it was, if lines moved)
            at = next((i for i in range(at, len(lines)) if lines[i].startswith("## ")), len(lines))
        lines[at:at] = text.split("\n")
    if not items:
        return "\n".join(lines)
    for item in items:
        span = nf._ensure_section(lines, st.HISTORY_HEADING, ())
        nf._insert_item(lines, span, f"- {item}")
    return nf._join(lines)


# ---------------------------------------------------------------- reading


@dataclass
class Snapshot:
    """The live brain as Lia reads it, at one moment."""

    notes: dict[str, NoteMeta]
    texts: dict[str, str]  # slug -> what Lia reads (body + History from rows)
    bodies: dict[str, str]  # slug -> what is stored
    versions: dict[str, int]
    paths: dict[str, str]  # slug -> library path
    maps: dict[str, tuple[str, str]]  # map_cache: name -> (text, map_version)
    manual: dict[str, str]
    archived: dict[str, tuple[str, str]] = field(default_factory=dict)  # slug -> (path, body)


def _rows(conn, sql: str, args=()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def state(conn) -> tuple:
    """Changes whenever the brain does: the last change and the maps' versions."""
    last = _rows(conn, "SELECT coalesce(max(id), 0) FROM brain.changes")[0][0]
    maps = _rows(conn, "SELECT map_name, map_version FROM brain.map_cache ORDER BY 1")
    return (last, tuple(maps))


def snapshot(conn) -> Snapshot:
    history: dict[str, list[str]] = {}
    blocks: dict[str, tuple[str, int | None]] = {}
    for slug, old, tag, section, pos in _rows(conn, HISTORY_SQL):
        if section == st.HISTORY_HEADING:
            blocks[slug] = (old, pos)
        else:
            history.setdefault(slug, []).append(history_item(old, tag))
    notes, texts, bodies, versions, paths, archived = {}, {}, {}, {}, {}, {}
    for slug, shelf_no, parent, version, body, gone in _rows(
        conn,
        "SELECT n.slug, n.shelf_no, n.parent_slug, n.version, b.body, n.archived_at "
        "FROM brain.notes n JOIN brain.note_bodies b ON b.slug = n.slug "
        'ORDER BY n.slug COLLATE "C"',
    ):
        path = lib_path(slug, shelf_no, parent)
        if gone is not None:
            archived[slug] = (path, body)
            continue
        text = with_history(body, history.get(slug, []), blocks.get(slug))
        meta = meta_from_text(text, path)
        if meta is None:
            continue
        notes[slug], texts[slug], bodies[slug] = meta, text, body
        versions[slug], paths[slug] = version, path
    maps = {
        name: (text, version)
        for name, text, version in _rows(
            conn, "SELECT map_name, rendered_text, map_version FROM brain.map_cache ORDER BY 1"
        )
    }
    manual = dict(_rows(conn, "SELECT name, text FROM brain.manual ORDER BY 1"))
    return Snapshot(notes, texts, bodies, versions, paths, maps, manual, archived)


def materialize(snap: Snapshot, folder: Path) -> Path:
    """A workspace: the snapshot as a library on disk (stored bodies, no History), its
    manual, and its archived notes under archive/library/. Returns the library folder."""
    root = folder / st.LIBRARY
    for slug, body in snap.bodies.items():
        _write(root / snap.paths[slug], body)
    for name, text in snap.manual.items():
        _write(root / "00-manual" / name, text)
    for path, body in snap.archived.values():
        _write(folder / "archive" / st.LIBRARY / path, body)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


# ---------------------------------------------------------------- line changes


def split_history(text: str) -> tuple[str, list[str]]:
    body, items, _ = loader.split_history(text)
    return body, items


def sections(lines: list[str]) -> list[str]:
    """The section each line sits in: 'frontmatter', a '## ' heading, or 'body'."""
    start = nf._body_start(lines)
    out, current = [], "body"
    for i, line in enumerate(lines):
        if i < start:
            out.append("frontmatter")
            continue
        if line.startswith("## "):
            current = line.strip()
        out.append(current)
    return out


def line_rows(old: str | None, new: str, moved: list[str], hint: str | None) -> list[dict]:
    """The `changes` rows for one note going from *old* to *new* (bodies without History).
    *moved*: the History lines this change made (a replaced or removed fact). A removed fact
    keeps no copy (D44)."""
    if old is None:
        return [dict(kind=hint or "add", section="note", old=None, new=new, pos=0, tag=None)]
    a, b = old.split("\n"), new.split("\n")
    sec_a, sec_b = sections(a), sections(b)
    tags = {}
    for item in moved:
        m = TAG.search(item)
        if m:
            tags[item] = m.group(1)
    rows = []
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        olds, news = a[i1:i2], b[j1:j2]
        if op == "replace" and len(olds) == len(news):
            pieces = [
                ([o], [n], i1 + k, j1 + k) for k, (o, n) in enumerate(zip(olds, news, strict=True))
            ]
        elif op == "delete":
            pieces = [([o], [], i1 + k, j1) for k, o in enumerate(olds)]
        elif op == "insert":
            pieces = [([], [n], i1, j1 + k) for k, n in enumerate(news)]
        else:
            pieces = [(olds, news, i1, j1)]
        for o, n, i, j in pieces:
            section = sec_b[j] if n else sec_a[i]
            tag = None
            if len(o) == 1 and o[0].startswith("- ") and sec_a[i] == st.FACTS_HEADING:
                fact = o[0][2:].strip()
                tag = next((t for h, t in tags.items() if nf.tagged(fact, t) == h), None)
            if tag is not None:
                if n:
                    kind = "replace"
                else:  # removed: erased for good, no copy kept
                    rows.append(dict(kind="remove", section=st.FACTS_HEADING, old=None,
                                     new=None, pos=j, tag=None))  # fmt: skip
                    continue
            elif hint:
                kind = hint
            elif not o:
                kind = "add"
            elif not n and section == st.LINKS_HEADING and st.LINK_LINE.match(o[0]):
                kind = "unlink"
            else:
                kind = "replace"
            rows.append(
                dict(
                    kind=kind,
                    section=section,
                    old="\n".join(o) if o else None,
                    new="\n".join(n) if n else None,
                    pos=j,
                    tag=tag,
                )
            )
    return rows


def rebuild_before(body: str, rows: list[dict]) -> str:
    """The body as it was before *rows* (one request's line rows for one note), from the body
    as it is now. Raises Stale if the note no longer holds what the rows put there."""
    lines = body.split("\n")
    out, cursor = [], 0
    for r in sorted(rows, key=lambda r: (r["pos"], r["id"])):
        new = r["new"].split("\n") if r["new"] is not None else []
        pos = r["pos"]
        if pos < cursor or lines[pos : pos + len(new)] != new:
            raise Stale("the note changed after that change")
        out += lines[cursor:pos]
        out += r["old"].split("\n") if r["old"] is not None else []
        cursor = pos + len(new)
    return "\n".join(out + lines[cursor:])


# ---------------------------------------------------------------- restore from rows


class RowBuilder(Builder):
    """The planner, unchanged, except where files and git stood in for rows: a removed fact
    is erased (no History), a replaced one keeps its old text in `changes`, and a restore
    puts back what archiving took, read from the archive's `changes` rows (D38)."""

    store: RowStore | None = None

    def replace_fact(self, op: dict) -> None:
        super().replace_fact(op)
        line = self.change.lines[-1]
        self.change.lines[-1] = line.replace(
            "(old line to History, ", "(old text kept in history, "
        )

    def remove_fact(self, op: dict) -> None:
        super().remove_fact(op)
        line = self.change.lines[-1]
        self.change.lines[-1] = re.sub(
            r"  \(to History, [^)]*\)$", "  (erased for good: this cannot be undone)", line
        )

    def restore_note(self, op: dict) -> None:
        a = self.find_archived(str(op.get("slug") or op.get("name") or ""))
        lib, slug = a["lib"], a["slug"]
        if slug in self.notes or (self.root / lib).exists():
            raise OpError(f"'{slug}' is in the library already")
        self.texts[lib] = None
        self.put(lib, a["file"].read_text(encoding="utf-8"), touched=False)
        self.change.restored.add(lib)
        self.change.slugs.append(slug)
        self.change.lines.append(f"restored {a['name']} ({lib})")
        self.change.log.append(f"restore {slug}")
        edits = self.store.archive_edits(slug) if self.store else []
        if not edits:
            self.change.lines.append("no archive record found: links in other notes not restored")
            return
        by_slug = {n.slug: n for n in self.notes.values()}
        per_note: dict[str, list[dict]] = {}
        for row in edits:
            per_note.setdefault(row["slug"], []).append(row)
        for other, rows in sorted(per_note.items()):
            note = by_slug.get(other)
            if note is None:
                self.change.lines.append(f"{other}: no longer in the library, not restored")
                continue
            current = self.text(note.path)
            if note.type == st.HUB:
                if f"[[{slug}]]" not in current:
                    self.put(note.path, nf.hub_listing(current, slug, add=True))
                    self.change.lines.append(f"{note.slug}: listed again")
                continue
            lines, back, skipped, links_back = nf._lines(current), 0, 0, []
            for row in rows:
                was, now = row["old"], row["new"]
                if was is None or f"[[{slug}" not in was or was in lines:
                    continue
                if now is not None and lines.count(now) == 1:  # a mention made plain text
                    lines[lines.index(now)] = was
                    back += 1
                elif now is None and st.LINK_LINE.match(was):  # a link line taken out
                    links_back.append(was)
                else:
                    skipped += 1
            for line in links_back:
                span = nf._ensure_section(lines, st.LINKS_HEADING, (st.HISTORY_HEADING,))
                nf._insert_item(lines, span, line)
                back += 1
            if back:
                self.put(note.path, nf._join(lines))
                self.change.lines.append(f"{note.slug}: {back} line(s) restored")
            if skipped:
                self.change.lines.append(
                    f"{note.slug}: {skipped} line(s) changed since the archive, left as they are"
                )


# ---------------------------------------------------------------- the store


class RowStore:
    """Lia's reads and writes on the `brain` schema. *connect* opens a connection."""

    flat = False
    saved_as = "change"  # what a card calls one saved request (a git commit on files)

    def __init__(self, connect, today: str | None = None, viewer_dirs: tuple[Path, ...] = (),
                 raw_root: Path | None = None):  # fmt: skip
        self.connect = connect
        self.today = today or dt.date.today().isoformat()
        self.viewer_dirs = tuple(viewer_dirs)
        self.raw_root = raw_root
        self._ws: Path | None = None
        self._snap: Snapshot | None = None

    # -------------------------------------------------- reading

    def snapshot(self) -> Snapshot:
        with self.connect() as conn:
            return snapshot(conn)

    def state(self) -> tuple:
        with self.connect() as conn:
            return state(conn)

    # -------------------------------------------------- the workspace the planner reads

    def refresh(self) -> None:
        old = self._ws
        self._snap = self.snapshot()
        self._ws = Path(tempfile.mkdtemp(prefix="yggdras-rows-"))
        materialize(self._snap, self._ws)
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)

    @property
    def root(self) -> Path:
        if self._ws is None:
            self.refresh()
        return self._ws / st.LIBRARY

    def builder(self, root: Path, flat: bool, today: str) -> RowBuilder:
        b = RowBuilder(root, flat, today)
        b.store = self
        return b

    def versions_of(self, change: Change) -> dict[str, int]:
        """The versions of the notes *change* touches, as they were read (for a preview)."""
        if self._snap is None:
            self.refresh()
        by_path = {p: s for s, p in self._snap.paths.items()}
        paths = [*change.notes, *change.archive]
        return {by_path[p]: self._snap.versions[by_path[p]] for p in paths if p in by_path}

    def check(self, change: Change):
        return Checker(self.root, False).check(
            {**change.notes, **{p: None for p in change.archive}}, restored=change.restored
        )

    def archive_edits(self, slug: str) -> list[dict]:
        """The line rows of the latest archive of *slug* that still stands."""
        with self.connect() as conn:
            rid = _rows(
                conn,
                "SELECT c.request_id FROM brain.changes c WHERE c.slug_text = %s "
                "AND c.kind = 'archive' AND c.section = 'note' AND " + render.LIVE_HISTORY
                + " ORDER BY c.id DESC LIMIT 1",
                (slug,),
            )  # fmt: skip
            if not rid:
                return []
            rows = _rows(
                conn,
                "SELECT slug_text, old_text, new_text FROM brain.changes "
                "WHERE request_id = %s AND kind = 'archive' AND section <> 'note' ORDER BY id",
                (rid[0][0],),
            )
        return [dict(slug=s, old=o, new=n) for s, o, n in rows]

    # -------------------------------------------------- writing

    def apply(
        self, change: Change, approved_by: str, request: str = "", expect: dict | None = None
    ) -> Outcome:
        verdict = self.check(change)
        if not verdict.ok:
            return Outcome(
                "refused", "the checker refused the change", issues=verdict.hard,
                warnings=verdict.warnings,
            )  # fmt: skip
        if self._snap is None:
            self.refresh()
        snap = self._snap
        by_path = {p: s for s, p in snap.paths.items()}
        archived_by_path = {p: s for s, (p, _) in snap.archived.items()}
        expect = expect if expect is not None else self.versions_of(change)
        hint = "archive" if change.archive else "restore" if change.restored else None
        edits = Edits()
        for path, text in change.notes.items():
            if path in change.archive:
                continue  # the archived note: handled below
            if text is None:
                raise OpError(f"{path}: taking a note out is not a write Lia makes")
            body, moved = split_history(text)
            if path in change.restored:
                slug = archived_by_path.get(path) or meta_from_text(text, path).slug
                edits.unarchive[slug] = (path, body)
                edits.rows.append((slug, [dict(kind="restore", section="note", old=None,
                                                new=None, pos=None, tag=None)]))  # fmt: skip
                continue
            slug = by_path.get(path)
            if slug is None:  # a new note
                meta = meta_from_text(body, path)
                slug = meta.slug
            old = snap.bodies.get(slug)
            edits.bodies[slug] = (path, body)
            edits.rows.append((slug, line_rows(old, body, moved, hint)))
        for path in change.archive:
            slug = by_path[path]
            edits.archive[slug] = path
            edits.rows.append((slug, [dict(kind="archive", section="note", old=None, new=None,
                                           pos=None, tag=None)]))  # fmt: skip
        raw_written: list[Path] = []
        try:
            raw_written = self._write_raw(change)
            rid = self._transact(edits, expect, ACTOR.format(app=approved_by))
        except Stale as exc:
            self._remove_raw(raw_written)
            self.refresh()
            return Outcome("blocked", f"{exc}: reload and review; nothing was written")
        except OpError as exc:
            self._remove_raw(raw_written)
            return Outcome("blocked", f"{exc}; nothing was written")
        except Exception as exc:
            self._remove_raw(raw_written)
            self.refresh()
            return Outcome(
                "blocked",
                f"the database refused the change ({type(exc).__name__}); nothing was written",
            )
        out = Outcome("written", f"saved {rid[:7]}", sha=rid, warnings=verdict.warnings)
        self.refresh()
        out.viewer_error = self.render_viewers()
        return out

    def _write_raw(self, change: Change) -> list[Path]:
        """Uploads stay files (D44): written before the transaction, removed if it fails."""
        written = []
        for rel, data in change.raw.items():
            if self.raw_root is None:
                raise OpError("no folder for raw uploads is configured")
            target = (self.raw_root / rel).resolve()
            if self.raw_root.resolve() not in target.parents:
                raise OpError(f"a raw upload may not be written outside raw/: {rel}")
            if target.exists():
                raise OpError(f"{rel} exists already")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append(target)
        return written

    @staticmethod
    def _remove_raw(paths: list[Path]) -> None:
        for p in paths:
            p.unlink(missing_ok=True)

    def _transact(self, edits: Edits, expect: dict[str, int], actor: str,
                  undo_of: str | None = None) -> str:  # fmt: skip
        """Save *edits* in one transaction: version check, bodies, derived rows, `changes`,
        map_cache. Returns the request id."""
        rid = uuid.uuid4().hex[:12]
        now = dt.datetime.now(dt.UTC)
        with self.connect() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
            touched = sorted({*edits.bodies, *edits.archive, *edits.unarchive, *edits.delete})
            cur.execute(
                "SELECT slug, version FROM brain.notes WHERE slug = ANY(%s) FOR UPDATE",
                (touched,),
            )
            now_versions = dict(cur.fetchall())
            for slug, seen in sorted(expect.items()):
                if now_versions.get(slug) != seen:
                    raise Stale(f"'{slug}' changed since it was read")
            snap = snapshot(conn)
            folder = Path(tempfile.mkdtemp(prefix="yggdras-save-"))
            try:
                materialize(snap, folder)
                root = folder / st.LIBRARY
                for slug, (path, body) in {**edits.bodies, **edits.unarchive}.items():
                    old = snap.paths.get(slug)
                    if old and old != path:
                        (root / old).unlink(missing_ok=True)
                    _write(root / path, body)
                for slug in [*edits.archive, *edits.delete]:
                    (root / snap.paths[slug]).unlink(missing_ok=True)
                brain = loader.read_brain(folder)
                sync(cur, brain, edits, now)
                for slug, rows in edits.rows:
                    for r in rows:
                        cur.execute(
                            "INSERT INTO brain.changes (slug, slug_text, kind, old_text, "
                            "new_text, actor, created_at, request_id, section, pos, tag) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (slug, slug, r["kind"], r["old"], r["new"],
                             f"{undo_of}{actor}" if undo_of else actor, now, rid,
                             r["section"], r["pos"], r["tag"]),
                        )  # fmt: skip
                for slug in sorted(edits.delete):  # after its rows went in: they keep slug_text
                    cur.execute("DELETE FROM brain.notes WHERE slug = %s", (slug,))
                render.build_cache(conn, now=now, commit=False)
            finally:
                shutil.rmtree(folder, ignore_errors=True)
        return rid

    # -------------------------------------------------- undo

    def undo(self, rid: str, approved_by: str) -> Outcome:
        with self.connect() as conn:
            rows = [
                dict(id=i, slug=s, kind=k, old=o, new=n, section=sec, pos=p, actor=a)
                for i, s, k, o, n, sec, p, a in _rows(
                    conn,
                    "SELECT id, slug_text, kind, old_text, new_text, section, pos, actor "
                    "FROM brain.changes WHERE request_id LIKE %s ORDER BY id",
                    (rid + "%",),
                )
            ]
            if not rows:
                return Outcome("blocked", f"no change {rid}")
            full = _rows(conn, "SELECT request_id FROM brain.changes WHERE id = %s",
                         (rows[0]["id"],))[0][0]  # fmt: skip
            if any(r["actor"].startswith(render.UNDO_ACTOR) for r in rows):
                return Outcome("blocked", "an Undo can't itself be undone")
            done = _rows(conn, "SELECT 1 FROM brain.changes WHERE actor LIKE %s LIMIT 1",
                         (f"{render.UNDO_ACTOR}{full}%",))  # fmt: skip
            if done:
                return Outcome("blocked", f"{full[:7]} was undone already")
            if any(r["kind"] == "remove" for r in rows):
                return Outcome(
                    "blocked",
                    "that change removed a fact, which erases it for good: it can't be undone",
                )
            slugs = sorted({r["slug"] for r in rows})
            later = _rows(
                conn,
                "SELECT DISTINCT request_id FROM brain.changes WHERE id > %s "
                "AND slug_text = ANY(%s) AND request_id IS DISTINCT FROM %s",
                (max(r["id"] for r in rows), slugs, full),
            )
            if later:
                return Outcome(
                    "blocked",
                    "later changes touched the same notes; undo those first",
                    later=[r[0] or "" for r in later],
                )
            snap = snapshot(conn)
        edits, expect = Edits(), {}
        per_note: dict[str, list[dict]] = {}
        for r in rows:
            per_note.setdefault(r["slug"], []).append(r)
        try:
            for slug, note_rows in per_note.items():
                whole = [r for r in note_rows if r["section"] == "note"]
                lines = [r for r in note_rows if r["section"] != "note"]
                if slug in snap.versions:
                    expect[slug] = snap.versions[slug]
                if any(r["kind"] in ("add",) and r["section"] == "note" for r in whole):
                    edits.delete.add(slug)  # a note this change created
                elif any(r["kind"] == "archive" for r in whole):
                    path, body = snap.archived[slug]
                    edits.unarchive[slug] = (path, body)
                elif any(r["kind"] == "restore" for r in whole):
                    edits.archive[slug] = snap.paths[slug]
                if lines and slug not in edits.delete:
                    body = edits.unarchive.get(slug, (None, snap.bodies.get(slug)))[1]
                    before = rebuild_before(body, lines)
                    target = edits.unarchive if slug in edits.unarchive else edits.bodies
                    path = snap.paths.get(slug) or snap.archived[slug][0]
                    target[slug] = (path, before)
                back = [dict(kind=r["kind"], section=r["section"], old=r["new"], new=r["old"],
                             pos=None, tag=None) for r in note_rows]  # fmt: skip
                edits.rows.append((slug, back))
            undone = self._transact(edits, expect, f"{full} (Manoj via {approved_by})",
                                    undo_of=render.UNDO_ACTOR)  # fmt: skip
        except Stale as exc:
            self.refresh()
            return Outcome("blocked", f"{exc}: reload and review; nothing was undone")
        self.refresh()
        out = Outcome("written", f"undid {full[:7]}", sha=undone)
        out.viewer_error = self.render_viewers()
        return out

    # -------------------------------------------------- the viewer

    def render_viewers(self) -> str:
        """Rebuild the graph viewer in every viewer folder from the rows as they are now."""
        if not self.viewer_dirs:
            return ""
        try:
            from yggdras.data.graph import viewer

            graph = st.build_map(self.root, st.mapped_shelves())
            for folder in dict.fromkeys(self.viewer_dirs):
                viewer.render(graph, self.root, folder)
        except Exception as exc:  # noqa: BLE001
            return f"{type(exc).__name__}: {exc}"
        return ""


@dataclass
class Edits:
    """One request's effect on notes (slug-keyed)."""

    bodies: dict[str, tuple[str, str]] = field(default_factory=dict)  # live after: path, body
    archive: dict[str, str] = field(default_factory=dict)  # archived now: path
    unarchive: dict[str, tuple[str, str]] = field(default_factory=dict)  # back: path, body
    delete: set[str] = field(default_factory=set)  # taken out (Undo of a created note)
    rows: list[tuple[str, list[dict]]] = field(default_factory=list)  # changes rows per note


# ---------------------------------------------------------------- derived rows


def sync(cur, brain: loader.Brain, edits: Edits, now: dt.datetime) -> None:
    """Bring every row in line with the live notes in *brain* (read from the saved bodies).
    A note's row and body are updated only where they differ, so only changed notes get a
    new version. Archived notes keep their note, body and areas; the rest of their rows go."""
    live = {n.slug: n for n in brain.notes}
    cur.execute("SELECT slug, title, type, area_code, parent_slug, shelf_no, description, "
                "status, sensitivity, review_date, decided_date, updated_at, archived_at "
                "FROM brain.notes")  # fmt: skip
    have = {r[0]: r[1:] for r in cur.fetchall()}
    cur.execute("SELECT slug, body FROM brain.note_bodies")
    bodies = dict(cur.fetchall())
    for slug, n in sorted(live.items()):
        values = (n.title, n.type, n.areas[0], n.parent_slug, n.shelf_no, n.description,
                  n.status, n.sensitivity, n.review_date, n.decided_date, n.updated_at)  # fmt: skip
        if slug not in have:
            cur.execute(loader.NOTE_INSERT, (slug, *values))
            cur.execute("INSERT INTO brain.note_bodies (slug, body) VALUES (%s, %s)",
                        (slug, n.body))  # fmt: skip
            continue
        if tuple(have[slug][:-1]) != values or have[slug][-1] is not None:
            cur.execute(
                "UPDATE brain.notes SET title = %s, type = %s, area_code = %s, parent_slug = %s, "
                "shelf_no = %s, description = %s, status = %s, sensitivity = %s, "
                "review_date = %s, decided_date = %s, updated_at = %s, archived_at = NULL "
                "WHERE slug = %s",
                (*values, slug),
            )
        if bodies.get(slug) != n.body:
            cur.execute("UPDATE brain.note_bodies SET body = %s WHERE slug = %s", (n.body, slug))
    for slug in sorted(edits.archive):
        cur.execute("UPDATE brain.notes SET archived_at = %s WHERE slug = %s", (now, slug))
    gone = sorted(s for s, row in have.items() if s not in live and row[-1] is None)
    unexpected = [s for s in gone if s not in edits.archive and s not in edits.delete]
    if unexpected:
        raise RuntimeError(f"notes would vanish without being archived: {unexpected}")
    affected = sorted({*live, *edits.archive})
    cur.execute("DELETE FROM brain.note_areas WHERE slug = ANY(%s)", (sorted(live),))
    cur.executemany(
        "INSERT INTO brain.note_areas (slug, area_code, is_primary, ord) VALUES (%s, %s, %s, %s)",
        [(n.slug, c, i == 0, i) for n in brain.notes for i, c in enumerate(n.areas)],
    )
    cur.execute("DELETE FROM brain.aliases WHERE slug = ANY(%s)", (affected,))
    cur.executemany("INSERT INTO brain.aliases (alias, slug, ord) VALUES (%s, %s, %s)",
                    brain.aliases)  # fmt: skip
    cur.execute("DELETE FROM brain.dated_items WHERE slug = ANY(%s)", (affected,))
    cur.executemany(
        "INSERT INTO brain.dated_items (slug, date, kind, label) VALUES (%s, %s, %s, %s)",
        [(n.slug, day, kind, label) for n in brain.notes for day, kind, label in n.dated],
    )
    cur.execute(
        "DELETE FROM brain.relationships WHERE from_slug = ANY(%s) OR to_slug = ANY(%s)",
        (affected, sorted(edits.archive)),
    )
    cur.executemany(
        "INSERT INTO brain.relationships (from_slug, verb, to_slug, kind) VALUES (%s, %s, %s, %s)",
        brain.links,
    )
    cur.execute("UPDATE brain.areas SET hub_slug = NULL")
    cur.executemany(
        "UPDATE brain.areas SET hub_slug = %s WHERE area_code = %s",
        [(slug, code) for code, slug in sorted(brain.hubs.items())],
    )


def write_note(store: RowStore, slug: str, text: str, version: int, approved_by: str) -> Outcome:
    """The app's write (D44 §6): a whole note's new text, carrying the version token it was
    read with. Checked like any write; a stale version is refused, never overwritten."""
    store.refresh()
    path = store._snap.paths.get(slug)
    if path is None:
        return Outcome("blocked", f"no live note '{slug}'")
    old_facts = nf.fact_lines(store._snap.bodies[slug])
    gone = [f for f in old_facts if f not in nf.fact_lines(text)]
    if gone:  # an edited or dropped fact: its old text goes to history, as Lia's replace does
        lines = nf._lines(text)
        for fact in gone:
            span = nf._ensure_section(lines, st.HISTORY_HEADING, ())
            nf._insert_item(lines, span, f"- {nf.tagged(fact, f'until: {store.today}')}")
        text = nf._join(lines)
    change = Change(title=f"edit {slug}", notes={path: text}, slugs=[slug],
                    lines=[f"{slug}: edited"], log=[f"edit {slug}"])  # fmt: skip
    return store.apply(change, approved_by, f"edit {slug}", expect={slug: version})
