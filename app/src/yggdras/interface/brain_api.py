"""The brain's HTTP API for the app, served by the note server on 127.0.0.1 (D44 §6).

Every /api/ route, read or write, needs HTTP Basic Auth with BRAIN_API_USER and
BRAIN_API_PASSWORD, read once at start. Without both, the API does not start (the note
pages and the graph still do, so Lia's footnotes keep working). The password is never logged.

    GET  /api/tree                          the note tree
    GET  /api/note/<slug>                   a note with its links, incoming links and mentions
    GET  /api/version/<slug>                its version token
    POST /api/note                          add a note            {text}
    POST /api/note/<slug>/add-fact          add a fact            {line, section?, after_line?}
    POST /api/note/<slug>/replace-fact      replace a fact        {old_line, new_line, preview}
    POST /api/note/<slug>/remove-fact       remove a fact         {line, preview}
    POST /api/note/<slug>/link              add a link            {target_slug, verb, preview}
    POST /api/note/<slug>/unlink            remove a link         {target_slug, verb, preview}
    POST /api/undo/<undo_id>                undo an add, a replace or a link, once

Any write body may carry "version" (from a read): a stale one is refused.
"""

from __future__ import annotations

import base64
import hmac
import os
import re
from collections.abc import Callable

from yggdras.data.brain_db.writes import ApiError, BrainWrites

USER_VAR, PASSWORD_VAR = "BRAIN_API_USER", "BRAIN_API_PASSWORD"
WRITE = re.compile(r"^note/(?P<slug>[^/]+)/(?P<op>replace-fact|remove-fact|add-fact|link|unlink)$")


class ApiConfigError(RuntimeError):
    pass


def credentials() -> tuple[str, str]:
    """The API's user and password from the environment; neither is ever printed."""
    user = os.environ.get(USER_VAR, "").strip()
    password = os.environ.get(PASSWORD_VAR, "").strip()
    missing = [name for name, value in ((USER_VAR, user), (PASSWORD_VAR, password)) if not value]
    if missing:
        raise ApiConfigError(
            f"{' and '.join(missing)} not set (see .env.example): the brain API is not started"
        )
    return user, password


class BrainApi:
    def __init__(self, user: str, password: str, read: Callable, writes: BrainWrites):
        self._expected = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.read, self.writes = read, writes

    def authorized(self, header: str | None) -> bool:
        if not header or not header.startswith("Basic "):
            return False
        return hmac.compare_digest(header[len("Basic ") :].strip(), self._expected)

    def get(self, route: str) -> tuple[int, object]:
        name, _, slug = route.partition("/")
        calls = {"tree": ("note_tree",), "note": ("note_with_relationships", slug),
                 "version": ("version", slug)}  # fmt: skip
        if name not in calls or (name != "tree" and not slug):
            return 404, {"error": "not found"}
        data = self.read(*calls[name])
        if data is None:
            return 404, {"error": "no such note"}
        return 200, {"version": data} if name == "version" else data

    def post(self, route: str, body: dict) -> tuple[int, object]:
        try:
            if route == "note":
                return 200, self.writes.add_note(body)
            if route.startswith("undo/"):
                return 200, self.writes.undo(route[len("undo/") :])
            m = WRITE.match(route)
            if not m:
                return 404, {"error": "not found"}
            handler = getattr(self.writes, m["op"].replace("-", "_"))
            return 200, handler(m["slug"], body)
        except ApiError as exc:
            return exc.status, {"error": exc.message, **exc.extra}
