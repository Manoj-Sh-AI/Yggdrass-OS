"""The deterministic checker (D22, D36): free code, run on every change before it is written.

A change is {path relative to the brain root: new text, or None to take the file out}. The
checker applies it to a temporary copy and judges what the change adds or alters, so a brain
with older problems (the Apollo demo's free-text verbs) can still be written to:

1. path: under a shelf of the library (or the flat brain's folders); never the manual,
   the inbox, evals, archive, private, skills or generated files;
2. frontmatter: required fields, a known type and area, slug equals the filename;
3. placement: a new note sits where the taxonomy's rules put it (library only);
4. sections: Summary, Facts, Links and History in that order; a new note has them;
5. fact lines: each new one carries "(src: <source>, <YYYY-MM-DD>)";
6. links: each new one uses a verb from the fixed list, never a self-link, `lists` only on a
   hub, never a second copy of a link that exists either way round;
7. history: a fact that leaves ## Facts is in ## History, never deleted;
8. sensitivity: `sensitivity: high` is never removed;
9. description: A23's rules for new or changed descriptions;
10. the whole library: the structural pass finds no new error, dangling link or unknown verb.

Lint warnings never stop a write: a long note, a new note with no typed link, "Not recorded
yet." sections.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

from yggdras import config
from yggdras.data.brain import notefile as nf
from yggdras.data.brain.placement import shelf_for
from yggdras.data.graph import structural as st
from yggdras.data.maps import checks
from yggdras.data.maps.notes import load_notes

SOURCED = re.compile(r"\(src: [^()]*?\d{4}-\d{2}-\d{2}")
NEVER = ("00-manual", "14-inbox", "evals", "archive", "private", "skills", "generated")
LONG_NOTE = 80  # lines: "longer than about a page"
REQUIRED = ("id", "slug", "name", "type", "description")
ORDER = ("## Summary", st.FACTS_HEADING, st.LINKS_HEADING, st.HISTORY_HEADING)


@dataclass(frozen=True)
class Issue:
    rule: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message} ({self.rule})"


@dataclass
class Verdict:
    hard: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.hard


def _frontmatter(text: str) -> dict | None:
    parts = st._split(text)
    if parts is None:
        return None
    try:
        fm = yaml.safe_load(parts[0]) or {}
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def _headings(text: str) -> list[str]:
    parts = st._split(text)
    body = parts[1] if parts else text.splitlines()
    return [ln.strip() for ln in body if ln.startswith("## ")]


def _sensitive(text: str | None) -> bool:
    fm = _frontmatter(text) if text else None
    return bool(fm) and str(fm.get("sensitivity", "")).strip().lower() == "high"


def _key(line: str) -> str:
    """A fact line's identity: its quote unit with [[links]] unwrapped and normalised, so a
    mention turned into plain text (its note was archived) is still the same fact."""
    return st.normalize(st.WIKILINK.sub(lambda m: m.group(1), checks.quote_unit(line)))


def _units(lines: list[str]) -> set[str]:
    return {_key(ln) for ln in lines}


class Checker:
    """Checks changes to the brain at *root* (a library, or a flat brain with *flat*)."""

    def __init__(self, root: Path, flat: bool = False):
        self.root, self.flat = root, flat
        self.shelves = None if flat else st.mapped_shelves()

    # ---------------------------------------------------------------- the copy

    def _copy(self, changes: dict[str, str | None], into: Path) -> Path:
        copy = into / "brain"
        shutil.copytree(self.root, copy, ignore=shutil.ignore_patterns("generated", ".git"))
        for rel, text in changes.items():
            target = copy / rel
            if text is None:
                if target.exists():
                    target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        return copy

    def _graph(self, root: Path) -> dict:
        return st.build_map(root, self.shelves)

    # ---------------------------------------------------------------- the rules

    def _path_issues(self, rel: str) -> list[Issue]:
        p = PurePosixPath(rel)
        bad = []
        if p.suffix != ".md" or ".." in p.parts or p.is_absolute():
            bad.append("not a note path")
        elif any(part in NEVER for part in p.parts):
            bad.append(f"writes are never allowed under {p.parts[0]}/")
        elif not self.flat:
            if p.parts[0] not in st.mapped_shelves() or len(p.parts) not in (2, 3):
                bad.append("not under a library shelf")
            elif len(p.parts) == 3 and p.parts[0] != "13-sources":
                bad.append("sub-folders exist only for a source's chunks (13-sources)")
        elif p.name == "index.md" or len(p.parts) < 2:
            bad.append("not inside one of the brain's folders")
        return [Issue("path", rel, m) for m in bad]

    def _note_issues(self, rel: str, before: str | None, after: str) -> list[Issue]:
        out: list[Issue] = []
        say = lambda rule, msg: out.append(Issue(rule, rel, msg))  # noqa: E731
        fm = _frontmatter(after)
        if fm is None:
            return [Issue("frontmatter", rel, "no readable frontmatter block")]
        new = before is None
        missing = [k for k in REQUIRED if not str(fm.get(k) or "").strip()]
        if not self.flat and not str(fm.get("area") or "").strip():
            missing.append("area")
        old_fm = (_frontmatter(before) or {}) if before else {}
        if missing and (new or any(old_fm.get(k) for k in missing)):
            say("frontmatter", f"missing field(s): {', '.join(missing)}")
        slug, type_ = str(fm.get("slug", "")), str(fm.get("type", ""))
        if slug and slug != PurePosixPath(rel).stem:
            say("frontmatter", f"slug '{slug}' does not match the file name")
        if new and slug and st.normalize(slug) != slug:
            say("frontmatter", f"slug '{slug}' is not kebab-case")
        if new and type_ and type_ not in (*st.CONTENT_TYPES, st.HUB, st.JOURNAL):
            say("frontmatter", f"unknown type '{type_}'")
        area = str(fm.get("area") or "")
        if new and not self.flat and area and area not in (*st.AREAS, st.CROSS):
            say("frontmatter", f"unknown area '{area}'")
        if new and not self.flat and type_ and area:
            shelf, folder = shelf_for(type_, area), PurePosixPath(rel).parts[0]
            if shelf is None:
                say("placement", f"the placement rules don't settle a {type_} in area {area}")
            elif shelf != folder:
                say("placement", f"a {type_} in area {area} belongs in {shelf}/, not {folder}/")
        heads = _headings(after)
        seen = [h for h in heads if h in ORDER]
        if seen != sorted(seen, key=ORDER.index) or len(seen) != len(set(seen)):
            say("sections", "Summary, Facts, Links and History must appear once, in that order")
        if new:
            need = ["## Summary", st.LINKS_HEADING] + (
                [] if type_ == st.HUB else [st.FACTS_HEADING]
            )
            gaps = [h for h in need if h not in heads]
            if gaps:
                say("sections", f"a new note needs {', '.join(gaps)}")
        old_lines = set()
        if before:
            old_lines = _units(nf.fact_lines(before) + nf.history_lines(before))
        for line in nf.fact_lines(after) + nf.history_lines(after):
            if _key(line) not in old_lines and not SOURCED.search(line):
                say("facts", f"fact line without (src: <source>, <date>): {line[:60]}")
        if type_ == st.HUB and nf.fact_lines(after):
            say("facts", "a hub holds no facts of its own")
        old_links = set(nf.link_lines(before)) if before else set()
        for verb, target in nf.link_lines(after):
            if (verb, target) in old_links:
                continue
            if verb not in st.VERBS:
                say("links", f"'{verb}' is not a verb from the fixed list")
            if verb == "lists" and type_ != st.HUB:
                say("links", "only a hub lists notes")
            if st.normalize(target) == st.normalize(slug):
                say("links", "a note never links to itself")
        if before is not None:
            kept = _units(nf.fact_lines(after) + nf.history_lines(after))
            gone = [f for f in nf.fact_lines(before) if _key(f) not in kept]
            for f in gone:
                say("history", f"a fact left ## Facts without going to ## History: {f[:60]}")
            if _sensitive(before) and not _sensitive(after):
                say("sensitivity", "sensitivity: high was removed")
        return out

    def _duplicate_links(self, graph: dict, before_graph: dict) -> list[Issue]:
        """A link written twice, either way round (each link is written once, in one note)."""
        old = {(e["from_slug"], e["to_slug"], e["reason"]) for e in before_graph["edges"]}
        out = []
        for e in graph["edges"]:
            if e["kind"] == "mention" or (e["from_slug"], e["to_slug"], e["reason"]) in old:
                continue
            back = st.OPPOSITE.get(e["reason"])
            twin = any(
                f["kind"] != "mention"
                and f is not e
                and (
                    (f["from_slug"], f["to_slug"], f["reason"])
                    == (e["from_slug"], e["to_slug"], e["reason"])
                    or (f["from_slug"], f["to_slug"], f["reason"])
                    == (e["to_slug"], e["from_slug"], back)
                )
                for f in graph["edges"]
            )
            if twin:
                out.append(
                    Issue(
                        "links",
                        e["from_slug"],
                        f"{e['reason']} [[{e['to_slug']}]] is already written (either way round)",
                    )
                )
        return out

    def _library_issues(self, before: dict, after: dict) -> list[Issue]:
        out = []
        old = {(e["path"], e["problem"]) for e in before["errors"]}
        out += [
            Issue("library", e["path"], e["problem"])
            for e in after["errors"]
            if (e["path"], e["problem"]) not in old
        ]
        key = lambda d: (d["from_slug"], d["written_as"], d["reason"])  # noqa: E731
        old_d = {key(d) for d in before["dangling"]}
        out += [
            Issue("library", d["from_slug"], f"[[{d['written_as']}]] points to no note")
            for d in after["dangling"]
            if key(d) not in old_d
        ]
        old_v = {(u["path"], u["verb"]) for u in before["unknown_verbs"]}
        out += [
            Issue("links", u["path"], f"'{u['verb']}' is not a verb from the fixed list")
            for u in after["unknown_verbs"]
            if (u["path"], u["verb"]) not in old_v
        ]
        return out

    def _descriptions(self, copy: Path, touched: dict[str, tuple[str | None, str]]) -> list[Issue]:
        hard = config.hard_description_rules()
        notes = {n.path: n for n in load_notes(copy, self.shelves).values()}
        out = []
        for rel, (before, _after) in touched.items():
            note = notes.get(rel)
            if note is None:
                continue
            old = _frontmatter(before) if before else None
            if old is not None and str(old.get("description", "")) == note.description:
                continue
            out += [
                Issue("description", rel, p.message)
                for p in checks.description_problems(note, hard)
                if p.severity == "hard"
            ]
        return out

    def _lint(self, touched: dict[str, tuple[str | None, str]]) -> list[Issue]:
        out = []
        for rel, (before, after) in touched.items():
            if before is not None:
                continue
            if after.count("\n") > LONG_NOTE:
                out.append(Issue("lint", rel, "longer than about a page"))
            typed = [v for v, _ in nf.link_lines(after) if v not in st.HUB_VERBS]
            if not typed:
                out.append(Issue("lint", rel, "a new note with no typed link"))
            if nf.NOT_RECORDED in after:
                out.append(Issue("lint", rel, 'has "Not recorded yet." sections'))
        return out

    # ---------------------------------------------------------------- the check

    def check(self, changes: dict[str, str | None]) -> Verdict:
        verdict = Verdict()
        touched: dict[str, tuple[str | None, str]] = {}
        for rel, text in changes.items():
            path = self.root / rel
            before = path.read_text(encoding="utf-8") if path.is_file() else None
            if text is None:
                if before is None:
                    verdict.hard.append(Issue("path", rel, "no such note to take out"))
                continue
            path_issues = self._path_issues(rel)
            verdict.hard += path_issues
            if not path_issues:
                touched[rel] = (before, text)
                verdict.hard += self._note_issues(rel, before, text)
        if verdict.hard:
            return verdict
        with tempfile.TemporaryDirectory() as tmp:
            copy = self._copy(changes, Path(tmp))
            before_graph, after_graph = self._graph(self.root), self._graph(copy)
            verdict.hard += self._library_issues(before_graph, after_graph)
            verdict.hard += self._duplicate_links(after_graph, before_graph)
            verdict.hard += self._descriptions(copy, touched)
        verdict.warnings += self._lint(touched)
        return verdict
