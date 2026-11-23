"""Invented HTTP-contract fixture. No imports from or writes to the real Brain."""

import copy
import json
import re

from yggdress_app.notes_proxy import MARKDOWN, NotesError, parts

BODY = "---\nslug: sample\nname: Sample\n---\n## Summary\nInvented summary.\n## Facts\n- First (src: self, 2030-01-01)\n- Second [[linked]] (src: self, 2030-01-01)\n## Links\n"


class SyntheticBrain:
    def __init__(self):
        self.notes = {
            "sample": {
                "slug": "sample",
                "title": "Sample",
                "body": BODY,
                "version": 1,
                "area": "04-learning",
                "areas": ["04-learning", "02-work"],
                "outgoing": [{"to": "linked"}],
                "incoming": [{"from_": "backlink"}],
            }
        }
        self.calls, self.history = [], {}
        self.markdown = False
        self.fail_at = None
        self.saved = 0

    def call(self, method, path, payload=None):
        self.calls.append((method, path, copy.deepcopy(payload)))
        if path.startswith("search?"):
            from urllib.parse import parse_qs

            query = parse_qs(path.partition("?")[2]).get("q", [""])[0].lower()
            return [
                {"slug": slug}
                for slug, note in sorted(self.notes.items())
                if not query or query in (note["title"] + note["body"]).lower()
            ]
        if method == "GET":
            note = self.notes.get(path.removeprefix("note/"))
            if not note:
                raise NotesError(404, "No such note")
            return copy.deepcopy(note)
        if self.markdown:
            raise NotesError(409, MARKDOWN, "brain_markdown")
        if path.startswith("undo/"):
            identifier = path.removeprefix("undo/")
            if identifier not in self.history:
                raise NotesError(409, "Undo was already used")
            self.notes = self.history.pop(identifier)
            return {"undone": True}
        if path == "note":
            text = payload["text"]
            slug = re.search(r'^slug: ["\']?([^\n"\']+)', text, re.MULTILINE)[1]
            if slug in self.notes:
                raise NotesError(409, "Note exists")
            self.history["created"] = copy.deepcopy(self.notes)
            self.notes[slug] = {
                "slug": slug,
                "title": json.loads(re.search(r'^name: (".*")$', text, re.MULTILINE)[1])
                if re.search(r'^name: (".*")$', text, re.MULTILINE)
                else slug,
                "body": text,
                "version": 1,
                "area": "cross",
            }
            return {"undo_id": "created", "links_added": ["sample mentions linked"]}
        _, slug, operation = path.split("/")
        note = self.notes[slug]
        if note["version"] != payload["version"]:
            raise NotesError(409, "Stale version")
        if payload.get("preview"):
            return {
                "preview": True,
                "links_added": ["new-link"],
                "links_removed": ["linked"],
                "permanent": "Cannot be undone" if operation == "remove-fact" else "",
            }
        if self.fail_at == self.saved:
            raise NotesError(409, "Stale version")
        old_notes = copy.deepcopy(self.notes)
        facts, _ = parts(note["body"])
        new = payload.get("new_line", payload.get("line", ""))
        if operation == "replace-fact":
            facts[facts.index(payload["old_line"])] = new
        elif operation == "remove-fact":
            facts.remove(payload["line"])
        else:
            if "(src:" not in new:
                new += " (src: self, 2030-01-01)"
            index = (
                facts.index(payload["after_line"]) + 1 if payload.get("after_line") else len(facts)
            )
            facts.insert(index, new)
        start = note["body"].index("## Facts\n") + len("## Facts\n")
        end = note["body"].index("## Links")
        note["body"] = (
            note["body"][:start]
            + "".join("- " + line + "\n" for line in facts)
            + note["body"][end:]
        )
        if operation != "add-fact":
            note["body"] += "\n## History\n- Brain-maintained history entry\n"
        note["version"] += 1
        self.saved += 1
        identifier = str(self.saved)
        self.history[identifier] = old_notes
        result = {"links_added": ["detected-link"], "line": new}
        if operation != "remove-fact":
            result["undo_id"] = identifier
        return result
