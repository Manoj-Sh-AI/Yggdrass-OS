"""Synthetic boundary simulator only. No Brain SQL, files, or real Lia implementation."""

import secrets
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import RLock

from fastapi import HTTPException

# Public existing taxonomy, copied as fixture labels only from structural.py's SHELVES.
SHELVES = (
    "00-manual",
    "01-health",
    "02-relationships",
    "03-work-career",
    "04-learning",
    "05-money",
    "06-purpose",
    "07-home-admin",
    "08-rest-joy",
    "10-ideas",
    "11-people",
    "12-places",
    "13-sources",
    "14-inbox",
    "15-journal",
)


class MockBrain:
    mode = "mock"
    integration_blocked = True

    def __init__(self):
        self.lock = RLock()
        self.previews = {}
        now = datetime.now(UTC).isoformat()
        samples = [
            (
                "credit-report",
                "Credit Risk Dashboard",
                "03-work-career",
                "A synthetic reporting exercise.",
                [],
            ),
            (
                "german-a2",
                "German A2.1",
                "04-learning",
                "Practice a few useful phrases.",
                ["weekly-review"],
            ),
            (
                "thesis",
                "Master’s Thesis",
                "04-learning",
                "A fictional research outline.",
                ["second-brain"],
            ),
            (
                "second-brain",
                "Second Brain",
                "10-ideas",
                "A synthetic connected-workspace idea.",
                ["thesis", "weekly-review"],
            ),
            ("strength", "A stronger everyday", "01-health", "A fictional movement routine.", []),
            (
                "career-next",
                "The next chapter",
                "03-work-career",
                "A sample portfolio checklist.",
                [],
            ),
            (
                "weekly-review",
                "The weekly reset",
                "15-journal",
                "A fictional weekly reflection.",
                [],
            ),
            (
                "coffee",
                "Conversations worth having",
                "02-relationships",
                "A synthetic conversation prompt.",
                [],
            ),
        ]
        self.notes = {
            i: {
                "id": i,
                "slug": i,
                "title": title,
                "shelfId": shelf,
                "area": shelf if shelf[0:2] in [f"{n:02}" for n in range(1, 9)] else "cross",
                "also": [],
                "description": body,
                "content": body,
                "tags": ["synthetic"],
                "links": links,
                "updated": now,
                "version": secrets.token_urlsafe(18),
                "source": "mock",
            }
            for i, title, shelf, body, links in samples
        }

    def envelope(self, **values):
        return {"mode": "mock", "integrationBlocked": True, **values}

    def tree(self):
        with self.lock:
            return self.envelope(
                shelves=[
                    {
                        "id": s,
                        "name": s,
                        "isArea": "01" <= s[:2] <= "08",
                        "noteIds": [n["id"] for n in self.notes.values() if n["shelfId"] == s],
                    }
                    for s in SHELVES
                ]
            )

    def list_notes(self):
        with self.lock:
            return self.envelope(notes=[self._detail(i) for i in self.notes])

    def _detail(self, note_id):
        note = self.notes.get(note_id)
        if not note:
            raise HTTPException(404, "Note unavailable from the Brain adapter.")
        return deepcopy(
            {**note, "backlinks": [n["id"] for n in self.notes.values() if note_id in n["links"]]}
        )

    def get(self, note_id):
        with self.lock:
            return self.envelope(note=self._detail(note_id))

    def _version(self, note_id, version):
        note = self._detail(note_id)
        if note["version"] != version:
            raise HTTPException(
                409, "This note changed elsewhere. Reload the latest note before trying again."
            )
        return note

    def create(self, values):
        with self.lock:
            note_id = secrets.token_urlsafe(12)
            shelf = values["shelfId"]
            if shelf not in SHELVES:
                raise HTTPException(422, "Choose a shelf supplied by the Brain adapter.")
            self.notes[note_id] = {
                "id": note_id,
                "slug": note_id,
                **values,
                "area": shelf if "01" <= shelf[:2] <= "08" else "cross",
                "also": [],
                "links": [],
                "updated": datetime.now(UTC).isoformat(),
                "version": secrets.token_urlsafe(18),
                "source": "mock",
            }
            return self.get(note_id)

    def replace(self, note_id, version, values):
        with self.lock:
            self._version(note_id, version)
            # No application history, semantic linking, or conflict-version logic.
            # A new opaque fixture token simulates the still-missing service contract.
            self.notes[note_id] = {
                **self.notes[note_id],
                **values,
                "version": secrets.token_urlsafe(18),
                "updated": datetime.now(UTC).isoformat(),
            }
            self.previews = {k: v for k, v in self.previews.items() if v["noteId"] != note_id}
            return self.get(note_id)

    def preview_delete(self, note_id, version):
        with self.lock:
            note = self._version(note_id, version)
            token = secrets.token_urlsafe(24)
            self.previews[token] = {
                "noteId": note_id,
                "version": version,
                "expires": datetime.now(UTC) + timedelta(minutes=5),
            }
            return self.envelope(
                preview={
                    "token": token,
                    "noteId": note_id,
                    "version": version,
                    "title": note["title"],
                    "content": note["content"],
                }
            )

    def confirm_delete(self, note_id, version, token, confirmed):
        with self.lock:
            self._version(note_id, version)
            preview = self.previews.get(token)
            if (
                not confirmed
                or not preview
                or preview["noteId"] != note_id
                or preview["version"] != version
                or preview["expires"] < datetime.now(UTC)
            ):
                raise HTTPException(
                    409, "Request a fresh delete preview and explicitly confirm it."
                )
            del self.notes[note_id]
            self.previews = {k: v for k, v in self.previews.items() if v["noteId"] != note_id}
            return self.envelope(deleted=True)


class UnavailableBrain:
    def __getattr__(self, _):
        raise HTTPException(
            503, "Lia is unavailable. Application tasks and routines remain available."
        )
