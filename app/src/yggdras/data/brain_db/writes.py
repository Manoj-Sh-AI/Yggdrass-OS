"""The app's writes to the brain (D44 §6, Manoj's endpoint spec of 2026-11-12).

Every write is a text edit to one note, checked by the note checker and saved by the row
store in one transaction, exactly as Lia's writes are: the text is the truth, and its link
rows are re-derived from it (link detection is that derivation: regex only, no model).

- Adding (a note, a fact, a link) is written at once and returns an undo_id.
- Replace previews first (preview=true writes nothing), then writes; it returns an undo_id.
- Remove and unlink preview first, then erase for good: no copy, no Undo.
- A link is one row, one direction (D31). The preview shows how the reverse reads; it is
  never written.
- Until the brain is switched to rows (YGGDRAS_BRAIN_SOURCE=rows) every write is refused:
  the markdown is still the truth, and a reload would erase what was written here.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable

from yggdras.data.brain import notefile as nf
from yggdras.data.brain.ops import Change, fact_line
from yggdras.data.brain.placement import shelf_for
from yggdras.data.brain_db.store import RowStore
from yggdras.data.graph import structural as st
from yggdras.data.maps.notes import meta_from_text

UNDOABLE = ("add-note", "add-fact", "replace-fact", "link")
PERMANENT = "{op} is permanent: it erased {what} for good, so it can't be undone"
ON_MARKDOWN = (
    "the brain is still on markdown: writes through the API go live after the switch to rows"
)


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


def targets(line: str) -> set[str]:
    """The notes a line names: every [[slug]] in it (a link line's target, or a mention)."""
    return {t.strip() for t in st.WIKILINK.findall(line)}


def _item(line: str) -> str:
    return line.strip().removeprefix("- ").strip()


class BrainWrites:
    def __init__(self, store: RowStore, live: Callable[[], bool], today: Callable[[], str]):
        self.store, self.live, self.today = store, live, today

    # -------------------------------------------------- helpers

    def _open(self) -> None:
        if not self.live():
            raise ApiError(409, ON_MARKDOWN)
        self.store.today = self.today()
        self.store.refresh()

    def _note(self, slug: str, body: dict) -> tuple[str, str]:
        snap = self.store._snap
        if slug not in snap.paths:
            raise ApiError(404, f"no live note '{slug}'")
        seen = body.get("version")
        if seen is not None and seen != snap.versions[slug]:
            raise ApiError(409, f"'{slug}' changed since it was read: reload and review",
                           version=snap.versions[slug])  # fmt: skip
        return snap.paths[slug], snap.bodies[slug]

    def _links(self, slug: str) -> set[tuple[str, str, str]]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT verb, to_slug, kind FROM brain.relationships WHERE from_slug = %s",
                (slug,),
            ).fetchall()
        return set(rows)

    def _save(self, op: str, slug: str, path: str, text: str, title: str,
              expect: dict | None) -> dict:  # fmt: skip
        before = self._links(slug) if slug in self.store._snap.paths else set()
        change = Change(title=title, notes={path: text}, slugs=[slug], lines=[title], log=[title])
        out = self.store.apply(change, "api", title, expect=expect)
        if out.status == "refused":
            raise ApiError(422, "the note checker refused it; nothing was written",
                           issues=[str(i) for i in out.issues])  # fmt: skip
        if out.status != "written":
            raise ApiError(409, out.message)
        after = self._links(slug)
        undo_id = str(uuid.uuid4())
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO brain.undo (undo_id, operation, payload) VALUES (%s, %s, %s)",
                (undo_id, op, json.dumps({"request_id": out.sha, "slug": slug})),
            )
        added = sorted(f"{slug} {v} {t}" + (" (mention)" if k == "mention" else "")
                       for v, t, k in after - before)  # fmt: skip
        return {"undo_id": undo_id, "change_id": out.sha, "links_added": added}

    # -------------------------------------------------- adding: written at once, with Undo

    def add_note(self, body: dict) -> dict:
        self._open()
        text = str(body.get("text") or "")
        meta = meta_from_text(text, "new.md")
        if meta is None:
            raise ApiError(422, "the text needs frontmatter with a slug (the note format)")
        if meta.slug in self.store._snap.paths or meta.slug in self.store._snap.archived:
            raise ApiError(409, f"a note '{meta.slug}' exists already")
        shelf = shelf_for(meta.type, meta.area)
        if shelf is None:
            raise ApiError(422, f"no shelf for a {meta.type!r} note in area {meta.area!r}")
        text = text if text.endswith("\n") else text + "\n"
        path = f"{shelf}/{meta.slug}.md"
        out = self._save("add-note", meta.slug, path, text, f"add note {meta.slug}", expect={})
        return {**out, "warnings": []}

    def add_fact(self, slug: str, body: dict) -> dict:
        self._open()
        path, text = self._note(slug, body)
        fact = _item(str(body.get("line") or ""))
        if not fact:
            raise ApiError(422, "line is empty")
        if "(src:" not in fact:
            fact = fact_line(fact, self.today(), "", "manoj")
        section = str(body.get("section") or "Facts").strip().removeprefix("## ").strip()
        heading = f"## {section}"
        lines = nf._lines(text)
        after = body.get("after_line")
        if after:
            span = nf._section_span(lines, heading)
            want = f"- {_item(str(after))}"
            hit = [i for i in range(*span) if lines[i].strip() == want] if span else []
            if len(hit) != 1:
                raise ApiError(422, f"after_line is not (exactly once) in {heading}")
            lines.insert(hit[0] + 1, f"- {fact}")
        else:
            before = (st.LINKS_HEADING, st.HISTORY_HEADING) if heading == st.FACTS_HEADING else ()
            nf._insert_item(lines, nf._ensure_section(lines, heading, before), f"- {fact}")
        out = self._save("add-fact", slug, path, nf._join(lines), f"add fact to {slug}",
                         expect=self._expect(slug, body))  # fmt: skip
        return {**out, "line": fact, "warnings": []}

    def link(self, slug: str, body: dict) -> dict:
        self._open()
        path, text = self._note(slug, body)
        target, verb = (
            str(body.get("target_slug") or "").strip(),
            str(body.get("verb") or "").strip(),
        )
        if verb not in st.VERBS or verb in st.HUB_VERBS:
            raise ApiError(422, f"'{verb}' is not a link verb (see the fixed list)")
        if target not in self.store._snap.paths:
            raise ApiError(404, f"no live note '{target}'")
        if target == slug:
            raise ApiError(422, "a note never links to itself")
        if (verb, target) in nf.link_lines(text):
            raise ApiError(409, f"{slug} {verb} {target} exists already")
        reverse = f"{target} {st.OPPOSITE[verb]} {slug}"
        if body.get("preview", True):
            return {"preview": True, "add": f"{slug} {verb} {target}", "reverse_reads_as": reverse,
                    "note": "one row, one direction (D31): the reverse is how the link reads "
                            "from the other note, never a second row; nothing written"}  # fmt: skip
        title, expect = f"link {slug} {verb} {target}", self._expect(slug, body)
        out = self._save("link", slug, path, nf.add_link(text, verb, target), title, expect)
        extra = {"back_link": "not written (D31): the reverse is a query"} \
            if "back_link" in body else {}  # fmt: skip
        return {**out, "reverse_reads_as": reverse, **extra}

    # -------------------------------------------------- changing: preview, then Confirm

    def replace_fact(self, slug: str, body: dict) -> dict:
        self._open()
        path, text = self._note(slug, body)
        old, new = _item(str(body.get("old_line") or "")), _item(str(body.get("new_line") or ""))
        if not old or not new:
            raise ApiError(422, "old_line and new_line are both needed")
        changed = nf.to_history(text, old, f"until: {self.today()}", replacement=new)
        if changed is None:
            raise ApiError(404, "old_line is not (exactly once) in the note's Facts")
        gained, lost = sorted(targets(new) - targets(old)), sorted(targets(old) - targets(new))
        unknown = [t for t in gained if t not in self.store._snap.paths]
        view = {"old_line": old, "new_line": new, "links_added": gained, "links_removed": lost,
                "unknown_targets": unknown}  # fmt: skip
        if body.get("preview", True):
            return {"preview": True, **view, "note": "nothing written; the old line goes to "
                    "history on Confirm, and a link it held goes with it"}  # fmt: skip
        out = self._save("replace-fact", slug, path, changed, f"replace fact in {slug}",
                         expect=self._expect(slug, body))  # fmt: skip
        warn = [
            f"{slug} no longer names [[{t}]]; its link row went with the old line" for t in lost
        ]
        return {**view, **out, "warnings": warn}  # links_added: the rows detection added

    def remove_fact(self, slug: str, body: dict) -> dict:
        self._open()
        path, text = self._note(slug, body)
        line = _item(str(body.get("line") or ""))
        changed = nf.to_history(text, line, f"until: {self.today()}") if line else None
        if changed is None:
            raise ApiError(404, "line is not (exactly once) in the note's Facts")
        if body.get("preview", True):
            return {"preview": True, "remove": line,
                    "permanent": "This erases the line for good: no copy is kept, and it "
                                 "cannot be undone."}  # fmt: skip
        out = self._save("remove-fact", slug, path, changed, f"remove fact from {slug}",
                         expect=self._expect(slug, body))  # fmt: skip
        return {"done": True, "change_id": out["undo_id"], "undo": None,
                "message": "Removed for good; it cannot be undone."}  # fmt: skip

    def unlink(self, slug: str, body: dict) -> dict:
        self._open()
        path, text = self._note(slug, body)
        target, verb = (
            str(body.get("target_slug") or "").strip(),
            str(body.get("verb") or "").strip(),
        )
        if (verb, target) not in nf.link_lines(text):
            raise ApiError(404, f"no link {slug} {verb} {target} in the note")
        if body.get("preview", True):
            return {"preview": True, "remove": f"{slug} {verb} {target}",
                    "permanent": "This removes the link for good: no copy is kept, and it "
                                 "cannot be undone."}  # fmt: skip
        changed, _ = nf.remove_link(text, verb, target)
        out = self._save("unlink", slug, path, changed, f"unlink {slug} {verb} {target}",
                         expect=self._expect(slug, body))  # fmt: skip
        return {"done": True, "change_id": out["undo_id"], "undo": None,
                "message": "Unlinked for good; it cannot be undone."}  # fmt: skip

    def _expect(self, slug: str, body: dict) -> dict:
        """The version the write is checked against: the caller's, else the one just read."""
        seen = body.get("version")
        return {slug: seen if seen is not None else self.store._snap.versions[slug]}

    # -------------------------------------------------- undo

    def undo(self, undo_id: str) -> dict:
        self._open()
        try:
            uuid.UUID(undo_id)
        except ValueError:
            raise ApiError(404, f"no undo {undo_id}") from None
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT operation, payload, used FROM brain.undo WHERE undo_id = %s FOR UPDATE",
                (undo_id,),
            ).fetchone()
            if row is None:
                raise ApiError(404, f"no undo {undo_id}")
            op, payload, used = row
            if op not in UNDOABLE:
                what = "a fact" if op == "remove-fact" else "a link"
                raise ApiError(400, PERMANENT.format(op=op, what=what))
            if used:
                raise ApiError(409, f"undo {undo_id} was used already")
            out = self.store.undo(payload["request_id"], "api")
            if out.status != "written":
                raise ApiError(409, out.message)
            conn.execute("UPDATE brain.undo SET used = true WHERE undo_id = %s", (undo_id,))
        return {"undone": True, "operation": op, "change_id": out.sha}
