"""Lia's planned operations, turned into one change to the brain's files (D36).

An operation is a small dict Lia's tools record; nothing is written here. build_change()
reads the current files every time, so a preview confirmed hours later is rebuilt (and
re-checked) against the brain as it is then.

    create_note   type, name, area, description, aliases, summary, facts[{text, valid}],
                  links[{verb, to}], sensitive, slug (optional)
    add_fact      slug, text, valid
    replace_fact  slug, old (the exact line, found from its block id), text, mode, reason
    remove_fact   slug, old, mode, reason
    link          from, verb, to
    unlink        from, verb, to
    archive_note  slug

Adding (create_note, add_fact, link) is written at once; changing or removing (the rest)
needs Manoj's confirm first (D33 as amended).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from yggdras.data.brain import notefile as nf
from yggdras.data.brain.placement import flat_folder, shelf_for
from yggdras.data.graph import structural as st
from yggdras.data.maps import checks
from yggdras.data.maps.notes import load_notes

ADDING = ("create_note", "add_fact", "link")
CHANGING = ("replace_fact", "remove_fact", "unlink", "archive_note")
MODES = ("until", "wrong")


class OpError(ValueError):
    """An operation that can't be applied as given (unknown note, line not found, …)."""


def needs_confirm(ops: list[dict]) -> bool:
    return any(op["op"] in CHANGING for op in ops)


def fact_line(text: str, today: str, valid: str = "", src: str = "manoj") -> str:
    """One fact line in node.md's form: "<text>. (src: manoj, <today>[; valid: …])"."""
    body = " ".join(text.split()).rstrip(".")
    ends = body.endswith(('."', '?"', '!"', ".'", "?'", "!'", "?", "!"))
    extra = f"; valid: {valid.strip()}" if valid and valid.strip() else ""
    return f"{body}{'' if ends else '.'} (src: {src}, {today}{extra})"


def history_tag(mode: str, today: str, reason: str = "") -> str:
    if mode == "until":
        return f"until: {today}"
    if mode == "wrong":
        return f"wrong: {reason.strip() or 'it was never true'}"
    raise OpError(f"mode must be 'until' (it changed) or 'wrong' (it was never true), not {mode!r}")


@dataclass
class Change:
    """One request's change: library paths → new text (None: taken out), the notes moved to
    the archive (library path → text), and plain summary lines."""

    title: str
    notes: dict[str, str | None] = field(default_factory=dict)
    archive: dict[str, str] = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)
    slugs: list[str] = field(default_factory=list)  # notes created or changed, for the card
    log: list[str] = field(default_factory=list)  # one entry per operation, for log.md


class Builder:
    def __init__(self, root: Path, flat: bool, today: str):
        self.root, self.flat, self.today = root, flat, today
        self.notes = load_notes(root, None if flat else st.mapped_shelves())
        self.texts: dict[str, str | None] = {}  # path → current text within this change
        self.change = Change(title="")

    # ---------------------------------------------------------------- files

    def path_of(self, slug: str) -> str:
        slug = slug.strip().strip("[]")
        if slug in self.notes:
            return self.notes[slug].path
        hits = [
            n
            for n in self.notes.values()
            if st.normalize(slug) in {st.normalize(x) for x in (n.slug, n.name, *n.aliases)}
        ]
        if len(hits) == 1:
            return hits[0].path
        raise OpError(f"no note '{slug}' (use the slug from the shelf map)")

    def slug_of(self, slug: str) -> str:
        path = self.path_of(slug)
        return next(n.slug for n in self.notes.values() if n.path == path)

    def text(self, path: str) -> str:
        if path not in self.texts:
            self.texts[path] = (self.root / path).read_text(encoding="utf-8")
        text = self.texts[path]
        if text is None:
            raise OpError(f"{path} is being archived in this same request")
        return text

    def put(self, path: str, text: str, touched: bool = True) -> None:
        if touched and text != self.texts.get(path):
            text = nf.set_field(text, "updated", self.today)
        self.texts[path] = text
        self.change.notes[path] = text

    def hub_of(self, area: str) -> str | None:
        hubs = [n for n in self.notes.values() if n.type == st.HUB and n.area == area]
        return hubs[0].path if len(hubs) == 1 else None

    # ---------------------------------------------------------------- operations

    def create_note(self, op: dict) -> None:
        name = str(op.get("name", "")).strip()
        type_ = str(op.get("type", "")).strip()
        area = str(op.get("area", "")).strip() or (st.CROSS if not self.flat else "")
        if not name or not type_:
            raise OpError("a new note needs a name and a type")
        slug = st.normalize(op.get("slug") or name)
        if slug in self.notes or any(p.endswith(f"/{slug}.md") for p in self.texts):
            raise OpError(f"a note with the slug '{slug}' already exists")
        if self.flat:
            folder = flat_folder(
                type_, [(n.type, n.path.split("/")[0]) for n in self.notes.values()]
            )
        else:
            folder = shelf_for(type_, area)
        if not folder:
            raise OpError(f"the placement rules don't settle where a {type_} in area {area} goes")
        links = []
        for item in op.get("links") or []:
            verb, to = str(item.get("verb", "")).strip(), str(item.get("to", "")).strip()
            links.append((verb, self.slug_of(to) if to in self.notes or self._known(to) else to))
        facts = [
            fact_line(f["text"], self.today, f.get("valid", "")) for f in op.get("facts") or []
        ]
        path = f"{folder}/{slug}.md"
        text = nf.new_note(
            id=str(uuid.uuid4()),
            slug=slug,
            name=name,
            type=type_,
            area=area or folder,
            description=str(op.get("description", "")).strip(),
            aliases=[str(a).strip() for a in op.get("aliases") or [] if str(a).strip()],
            created=self.today,
            summary=str(op.get("summary", "")),
            facts=facts,
            links=links,
            sensitive=bool(op.get("sensitive")),
        )
        self.texts[path] = None  # new: no text on disk
        self.put(path, text, touched=False)
        self.change.slugs.append(slug)
        self.change.lines.append(
            f"new note {name} ({path}): {len(facts)} facts, {len(links)} links"
        )
        self.change.log.append(f"create {slug}")
        hub = None if self.flat else self.hub_of(area)
        if hub:
            self.put(hub, nf.hub_listing(self.text(hub), slug, add=True))
            self.change.lines.append(f"listed in {Path(hub).stem}")

    def _known(self, slug: str) -> bool:
        try:
            self.path_of(slug)
            return True
        except OpError:
            return False

    def add_fact(self, op: dict) -> None:
        path = self.path_of(op["slug"])
        line = fact_line(str(op.get("text", "")), self.today, op.get("valid", ""))
        if not op.get("text", "").strip():
            raise OpError("add_fact needs the fact's text")
        text = self.text(path)
        if checks.quote_unit(line) in {checks.quote_unit(f) for f in nf.fact_lines(text)}:
            raise OpError("that fact is already in the note")
        self.put(path, nf.add_fact(text, line))
        slug = Path(path).stem
        self.change.slugs.append(slug)
        self.change.lines.append(f"added to {slug}: {line}")
        self.change.log.append(f"add fact to {slug}")

    def _history(self, op: dict, replacement: str | None) -> tuple[str, str, str]:
        path = self.path_of(op["slug"])
        old = str(op.get("old", "")).strip()
        tag = history_tag(str(op.get("mode", "")), self.today, str(op.get("reason", "")))
        text = self.text(path)
        moved = nf.to_history(text, old, tag, replacement)
        if moved is None:
            raise OpError(f"that fact is not (exactly once) in {Path(path).stem}'s ## Facts")
        self.put(path, moved)
        return path, old, tag

    def replace_fact(self, op: dict) -> None:
        if not str(op.get("text", "")).strip():
            raise OpError("replace_fact needs the new text")
        new = fact_line(op["text"], self.today, op.get("valid", ""))
        if checks.quote_unit(new) == checks.quote_unit(str(op.get("old", ""))):
            raise OpError(
                "the new text is the same as the old; to take a fact out, use remove_fact"
            )
        path, old, tag = self._history(op, new)
        slug = Path(path).stem
        self.change.slugs.append(slug)
        self.change.lines.append(f"{slug}: {old}  →  {new}  (old line to History, {tag})")
        self.change.log.append(f"replace fact in {slug}")

    def remove_fact(self, op: dict) -> None:
        path, old, tag = self._history(op, None)
        slug = Path(path).stem
        self.change.slugs.append(slug)
        self.change.lines.append(f"{slug}: removed {old}  (to History, {tag})")
        self.change.log.append(f"remove fact from {slug}")

    def link(self, op: dict) -> None:
        verb = str(op.get("verb", "")).strip()
        if verb not in st.VERBS or verb in st.HUB_VERBS:
            raise OpError(f"'{verb}' is not a link verb Lia may write (see the fixed list)")
        src, dst = self.path_of(op["from"]), self.slug_of(op["to"])
        if Path(src).stem == dst:
            raise OpError("a note never links to itself")
        self.put(src, nf.add_link(self.text(src), verb, dst))
        self.change.slugs.append(Path(src).stem)
        self.change.lines.append(f"link: {Path(src).stem} {verb} {dst}")
        self.change.log.append(f"link {Path(src).stem} {verb} {dst}")

    def unlink(self, op: dict) -> None:
        verb = str(op.get("verb", "")).strip() or None
        a, b = self.path_of(op["from"]), self.path_of(op["to"])
        text, gone = nf.remove_link(self.text(a), verb, Path(b).stem)
        if gone:
            self.put(a, text)
            where = Path(a).stem
        else:  # written the other way round, with the opposite verb
            back = st.OPPOSITE.get(verb) if verb else None
            text, gone = nf.remove_link(self.text(b), back, Path(a).stem)
            if not gone:
                raise OpError(f"there is no {verb or ''} link between these notes")
            self.put(b, text)
            where = Path(b).stem
        self.change.slugs.append(where)
        self.change.lines.append(
            f"unlink: {Path(a).stem} {verb or '(any verb)'} {Path(b).stem} (line in {where})"
        )
        self.change.log.append(f"unlink {Path(a).stem} {Path(b).stem}")

    def archive_note(self, op: dict) -> None:
        path = self.path_of(op["slug"])
        slug = Path(path).stem
        name = next(n.name for n in self.notes.values() if n.path == path)
        text = self.text(path)
        for other in self.notes.values():
            if other.path == path or self.texts.get(other.path, "") is None:
                continue
            before = self.text(other.path)
            after, links = nf.remove_link(before, None, slug)
            if links and other.type == st.HUB:
                after = nf.hub_listing(after, slug, add=False)  # keeps "Notes so far" right
            after, mentions = nf.unwrap_mentions(after, slug, name)
            if links or mentions:
                self.put(other.path, after)
                parts = [f"{links} link line(s) removed"] if links else []
                parts += [f"{mentions} mention(s) unlinked"] if mentions else []
                self.change.lines.append(f"{other.slug}: {', '.join(parts)}")
        self.change.archive[path] = text
        self.change.notes[path] = None
        self.texts[path] = None
        self.change.slugs.append(slug)
        self.change.lines.insert(0, f"archive {name} ({path} → archive)")
        self.change.log.append(f"archive {slug}")


def build_change(root: Path, flat: bool, ops: list[dict], today: str, title: str = "") -> Change:
    """Apply *ops* in order to the current files (in memory) and return the change."""
    if not ops:
        raise OpError("nothing to change")
    b = Builder(root, flat, today)
    for op in ops:
        kind = op.get("op")
        handler = getattr(b, kind, None) if kind in (*ADDING, *CHANGING) else None
        if handler is None:
            raise OpError(f"unknown operation {kind!r}")
        handler(op)
    b.change.slugs = list(dict.fromkeys(b.change.slugs))
    b.change.title = title or "; ".join(dict.fromkeys(b.change.log))
    return b.change
