"""Notes-only HTTP plumbing. No Brain imports, SQL, source switching or file writes."""

import base64
import difflib
import json
import os
import re
import secrets
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

MARKDOWN = "Writes are not live yet — the brain is still on markdown."
STALE = "another change was saved while you were editing — please refresh."


class NotesError(Exception):
    def __init__(self, status, message, code="notes_error", **extra):
        self.status, self.message, self.code, self.extra = status, message, code, extra


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None  # Never forward a Basic credential to a redirected destination.


class BrainNotesHTTP:
    def __init__(self, url, user, password):
        parsed = urlsplit(url)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/")
        ):
            raise ValueError(
                "BRAIN_SERVER_URL must be a server origin without credentials or a path."
            )
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")
        ):
            raise ValueError("Brain HTTP is allowed only on loopback; other origins require HTTPS.")
        self.root = url.rstrip("/")
        self._auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.configured = bool(user and password)

    @classmethod
    def environment(cls):
        return cls(
            os.environ.get("BRAIN_SERVER_URL", "http://localhost:8100"),
            os.environ.get("BRAIN_API_USER", ""),
            os.environ.get("BRAIN_API_PASSWORD", ""),
        )

    def call(self, method, path, body=None):
        if not self.configured:
            raise NotesError(
                503,
                "Configure BRAIN_API_USER and BRAIN_API_PASSWORD in the application backend environment.",
                "brain_configuration",
            )
        request = Request(
            self.root + "/api/" + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": self._auth,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=6) as response:
                raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise NotesError(502, "The Brain response exceeds the Notes response limit.")
                return json.loads(raw)
        except HTTPError as error:
            if error.code in (401, 403):
                raise NotesError(
                    502,
                    "Brain API authentication failed. Check the backend credentials.",
                    "brain_authentication",
                ) from None
            try:
                data = json.loads(error.read(10000))
                message = data.get("error") or data.get("detail") or "Brain API request failed."
                if error.code == 422 and isinstance(data.get("issues"), list):
                    message += " " + "; ".join(str(issue) for issue in data["issues"][:10])
            except (ValueError, AttributeError):
                message = "Brain API request failed."
            if error.code == 409 and "still on markdown" in str(message).lower():
                raise NotesError(409, MARKDOWN, "brain_markdown") from None
            if error.code == 404 and path.startswith("search"):
                message = "The running Brain API has no GET /api/search route. Start the version that provides it."
            status = error.code if error.code in (400, 404, 409, 413, 422) else 502
            raise NotesError(
                status, str(message), "brain_stale" if error.code == 409 else "brain_upstream"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise NotesError(
                503,
                "The Brain server is unavailable. Your edits have been preserved.",
                "brain_unavailable",
            ) from None
        except (ValueError, UnicodeError):
            raise NotesError(502, "The Brain API returned an unreadable response.") from None


def slug_path(slug):
    if (
        not slug
        or len(slug) > 200
        or any(c in slug for c in "/\\?#\x00\r\n")
        or slug in (".", "..")
    ):
        raise NotesError(422, "Invalid note slug.")
    return "note/" + quote(slug, safe="")


def canonical(line):
    # BlockNote may escape literal wiki brackets in its CommonMark projection.
    value = line.strip().replace("\\[", "[").replace("\\]", "]")
    return re.sub(r"^[-*+]\s+", "", value)


def parts(body, ignore_history=False):
    facts, other, section = [], [], ""
    for line in body.replace("\r\n", "\n").splitlines():
        if re.match(r"^#{1,6}\s", line):
            section = line.lstrip("#").strip().lower()
        if not line.strip():
            continue
        if ignore_history and section == "history":
            continue
        if section == "facts" and not line.startswith("#"):
            facts.append(canonical(line))
        else:
            other.append(canonical(line))
    return facts, other


def targets(line):
    return sorted(set(re.findall(r"\[\[([^\]|\n]+)(?:\|[^\]\n]*)?\]\]", line)))


def note_view(data, requested=None):
    if not isinstance(data, dict) or not isinstance(data.get("body", data.get("text")), str):
        raise NotesError(502, "The Brain note response must include its full body.")
    body = data.get("body", data.get("text"))
    slug = str(data.get("slug") or requested or "")
    slug_path(slug)
    version = data.get("version")
    if type(version) not in (str, int):
        raise NotesError(502, "The Brain note response is missing its version token.")
    facts, _ = parts(body)
    prefix = ""
    display = body
    if body.startswith(("---\n", "---\r\n")):
        match = re.match(r"\A---\r?\n.*?\r?\n---(?:\r?\n|$)", body, re.DOTALL)
        if match:
            prefix, display = body[: match.end()], body[match.end() :]
    heading = re.match(r"\A\s*# [^\n]*\n", display)
    if heading:
        prefix += display[: heading.end()]
        display = display[heading.end() :]
    areas = data.get("areas") or data.get("also") or []
    if not isinstance(areas, list):
        areas = []
    area = str(data.get("area") or "cross")
    outgoing = data.get("outgoing") or []
    incoming = data.get("incoming") or []
    return {
        "id": slug,
        "slug": slug,
        "title": str(data.get("title") or data.get("name") or slug),
        "description": facts[0] if facts else str(data.get("description") or ""),
        "content": display,
        "rawBody": body,
        "bodyPrefix": prefix,
        "area": area,
        "also": [str(a) for a in areas if str(a) != area],
        "tags": list(dict.fromkeys([area, *map(str, areas)])),
        "shelfId": str(data.get("shelf") or area),
        "links": [str(x.get("to")) for x in outgoing if isinstance(x, dict) and x.get("to")],
        "backlinks": [
            str(x.get("from_")) for x in incoming if isinstance(x, dict) and x.get("from_")
        ],
        "updated": str(data.get("updated") or ""),
        "source": "lia",
        "version": str(version),
    }


class NotesProxy:
    """Bounded process memory; a restart expires drafts/previews without touching notes."""

    def __init__(self, http=None, clock=time.monotonic):
        self.http = http or BrainNotesHTTP.environment()
        self.clock, self.lock, self.owners = clock, RLock(), {}

    def state(self, owner):
        now = self.clock()
        self.owners = {
            key: value for key, value in self.owners.items() if now - value["seen"] < 8 * 3600
        }
        if owner not in self.owners and len(self.owners) >= 128:
            raise NotesError(503, "Too many active Notes sessions. Try again later.")
        state = self.owners.setdefault(
            owner, {"seen": now, "fetched": {}, "previews": {}, "created": {}, "undo": None}
        )
        state["seen"] = now
        state["fetched"] = {k: v for k, v in state["fetched"].items() if now - v["at"] < 1800}
        state["previews"] = {k: v for k, v in state["previews"].items() if now - v["at"] < 600}
        return state

    def get(self, owner, slug):
        with self.lock:
            raw = self.http.call("GET", slug_path(slug))
            note = note_view(raw, slug)
            state = self.state(owner)
            token = secrets.token_urlsafe(24)
            if len(state["fetched"]) >= 64:
                state["fetched"].pop(next(iter(state["fetched"])))
            state["fetched"][token] = {"slug": slug, "raw": raw, "note": note, "at": self.clock()}
            return {"note": {**note, "fetchToken": token}, "canUndo": bool(state["undo"])}

    def search(self, owner, query):
        with self.lock:
            data = self.http.call("GET", "search?" + urlencode({"q": query}))
            entries = (
                data
                if isinstance(data, list)
                else data.get("notes", data.get("results"))
                if isinstance(data, dict)
                else None
            )
            if not isinstance(entries, list):
                raise NotesError(502, "The Brain search response must contain a list of notes.")

            def read(entry):
                slug = (
                    entry.get("slug")
                    if isinstance(entry, dict)
                    else entry
                    if isinstance(entry, str)
                    else None
                )
                if not slug:
                    raise NotesError(502, "A Brain search result is missing its slug.")
                raw = (
                    entry
                    if isinstance(entry, dict)
                    and isinstance(entry.get("body", entry.get("text")), str)
                    and entry.get("version") is not None
                    else self.http.call("GET", slug_path(slug))
                )
                return note_view(raw, slug)

            # Search returns catalogue rows, so previews need detail reads. Bound the
            # fan-out, preserve upstream order, and cancel queued work on failure.
            pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="notes-read")
            try:
                notes = list(pool.map(read, entries))
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
            return {"notes": notes, "canUndo": bool(self.state(owner)["undo"]), "mode": "lia"}

    def preview(self, owner, slug, fetch_token, body):
        with self.lock:
            state = self.state(owner)
            fetched = state["fetched"].get(fetch_token)
            if not fetched or fetched["slug"] != slug:
                raise NotesError(
                    409,
                    "The fetched note snapshot expired. Refresh before reviewing changes.",
                    "brain_stale",
                )
            old, old_other = parts(fetched["note"]["rawBody"])
            new, new_other = parts(body)
            if old_other != new_other:
                raise NotesError(
                    422,
                    "The Brain fact API cannot edit metadata, headings, summaries or link sections. Keep those unchanged; your draft is preserved.",
                    "unsupported_edit",
                )
            counts = Counter(old)
            operations = []
            for tag, a, b, c, d in difflib.SequenceMatcher(
                a=old, b=new, autojunk=False
            ).get_opcodes():
                if tag == "equal":
                    continue
                before, after = old[a:b], new[c:d]
                paired = min(len(before), len(after)) if tag == "replace" else 0
                for index in range(paired):
                    operations.append(
                        {"kind": "replace-fact", "old": before[index], "new": after[index]}
                    )
                for value in before[paired:]:
                    operations.append({"kind": "remove-fact", "old": value, "new": ""})
                for index, value in enumerate(after[paired:], start=c + paired):
                    operations.append(
                        {
                            "kind": "add-fact",
                            "old": "",
                            "new": value,
                            "after": new[index - 1] if index else None,
                        }
                    )
            if len(operations) > 100:
                raise NotesError(422, "Review at most 100 line changes at a time.")
            removed = {op["old"] for op in operations if op["old"]}
            added = {op["new"] for op in operations if op["new"]}
            if removed & added:
                raise NotesError(
                    422,
                    "Moving existing fact lines is not supported by this API. Keep their order unchanged; your draft is preserved.",
                )
            for op in operations:
                if op["old"] and counts[op["old"]] != 1:
                    raise NotesError(
                        422,
                        "A changed fact occurs more than once; the API cannot identify it unambiguously.",
                    )
                version = fetched["raw"]["version"]
                if op["kind"] == "add-fact":
                    view = {
                        "links_added": targets(op["new"]),
                        "links_removed": [],
                        "note": "This addition is staged locally; add-fact is called only after Confirm.",
                    }
                    if old and not op.get("after"):
                        view["note"] += (
                            " The API has no insert-before operation, so this line will be appended to Facts."
                        )
                else:
                    payload = {"version": version, "preview": True}
                    payload.update(
                        {"old_line": op["old"], "new_line": op["new"]}
                        if op["kind"] == "replace-fact"
                        else {"line": op["old"]}
                    )
                    view = self.http.call("POST", slug_path(slug) + "/" + op["kind"], payload)
                    if not isinstance(view, dict) or view.get("preview") is not True:
                        raise NotesError(
                            502, "The Brain did not return a safe preview. Nothing was confirmed."
                        )
                op["preview"] = view
            token = secrets.token_urlsafe(24)
            if len(state["previews"]) >= 32:
                state["previews"].pop(next(iter(state["previews"])))
            state["previews"][token] = {
                "slug": slug,
                "raw": fetched["raw"],
                "ops": operations,
                "at": self.clock(),
                "state": "pending",
                "result": None,
            }
            return {
                "token": token,
                "slug": slug,
                "changes": [
                    {
                        "kind": op["kind"],
                        "old": op["old"],
                        "new": op["new"],
                        "links_added": op["preview"].get("links_added", []),
                        "links_removed": op["preview"].get(
                            "links_removed",
                            targets(op["old"]) if op["kind"] == "remove-fact" else [],
                        ),
                        "permanent": op["preview"].get("permanent", ""),
                        "note": op["preview"].get("note", ""),
                    }
                    for op in operations
                ],
            }

    def cancel(self, owner, token):
        with self.lock:
            preview = self.state(owner)["previews"].get(token)
            if not preview or preview["state"] != "pending":
                raise NotesError(409, "This preview expired or was already used.")
            preview["state"] = "cancelled"
            return {"cancelled": True}

    def confirm(self, owner, token):
        with self.lock:
            state = self.state(owner)
            preview = state["previews"].get(token)
            if not preview:
                raise NotesError(409, "This preview expired. Refresh and review again.")
            if preview["state"] == "applied":
                return preview["result"]
            if preview["state"] != "pending":
                raise NotesError(
                    409, "This preview was cancelled or interrupted. Refresh before retrying."
                )
            preview["state"] = "running"
            completed = 0
            links, anchors = [], {}
            try:
                raw = self.http.call("GET", slug_path(preview["slug"]))
                if raw.get("version") != preview["raw"]["version"] or parts(raw["body"]) != parts(
                    preview["raw"]["body"]
                ):
                    raise NotesError(409, STALE, "brain_stale", completed=0)
                for op in preview["ops"]:
                    payload = {"preview": False, "version": raw["version"]}
                    if op["kind"] == "replace-fact":
                        payload.update(old_line=op["old"], new_line=op["new"])
                    elif op["kind"] == "remove-fact":
                        payload["line"] = op["old"]
                    else:
                        payload["line"], payload["section"] = op["new"], "Facts"
                        if op.get("after"):
                            payload["after_line"] = anchors.get(op["after"], op["after"])
                    before, other = parts(raw["body"], ignore_history=True)
                    out = self.http.call(
                        "POST", slug_path(preview["slug"]) + "/" + op["kind"], payload
                    )
                    completed += 1
                    if out.get("undo_id"):
                        state["undo"] = out["undo_id"]
                        state["undo_slug"] = preview["slug"]
                    links.extend(out.get("links_added", []))
                    actual_new = canonical(out.get("line", op["new"]))
                    if op["kind"] == "replace-fact":
                        before[before.index(op["old"])] = actual_new
                    elif op["kind"] == "remove-fact":
                        before.remove(op["old"])
                    else:
                        after_line = payload.get("after_line")
                        index = before.index(after_line) + 1 if after_line else len(before)
                        before.insert(index, actual_new)
                        anchors[op["new"]] = actual_new
                    raw = self.http.call("GET", slug_path(preview["slug"]))
                    # The authoritative fact API also maintains its own History section.
                    # Do not recreate that algorithm or mistake its output for a conflict.
                    if parts(raw["body"], ignore_history=True) != (before, other):
                        raise NotesError(409, STALE, "brain_stale")
                result = {
                    **self.get(owner, preview["slug"]),
                    "links_added": links,
                    "completed": completed,
                }
                preview["state"], preview["result"] = "applied", result
                return result
            except NotesError as error:
                preview["state"] = "failed"
                if error.status == 409 and error.code != "brain_markdown":
                    error.message = STALE
                    error.code = "brain_stale"
                error.extra.update(completed=completed, canUndo=bool(state["undo"]))
                raise

    def create(self, owner, text, slug):
        with self.lock:
            slug_path(slug)
            state = self.state(owner)
            previous = state["created"].get(slug)
            if previous and previous["text"] != text:
                raise NotesError(
                    409,
                    "This note was already created. Refresh before editing it.",
                    "brain_stale",
                    canUndo=bool(state["undo"]),
                )
            out = previous["out"] if previous else self.http.call("POST", "note", {"text": text})
            if not previous and len(state["created"]) >= 32:
                state["created"].pop(next(iter(state["created"])))
            state["created"][slug] = {"text": text, "out": out}
            if out.get("undo_id"):
                state["undo"] = out["undo_id"]
                state["undo_slug"] = slug
            try:
                return {**self.get(owner, slug), "links_added": out.get("links_added", [])}
            except NotesError as error:
                error.extra.update(completed=1, canUndo=bool(state["undo"]))
                raise

    def undo(self, owner):
        with self.lock:
            state = self.state(owner)
            identifier = state["undo"]
            if not identifier:
                raise NotesError(400, "There is nothing to undo in this session.")
            out = self.http.call("POST", "undo/" + quote(str(identifier), safe=""), {})
            state["undo"] = None
            state["previews"].clear()
            state["fetched"].clear()
            state["created"].clear()
            return {"message": "undone", "canUndo": False, "result": out}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreviewInput(Strict):
    fetchToken: str = Field(min_length=1, max_length=200)
    body: str = Field(max_length=100000)


class CreateInput(Strict):
    text: str = Field(min_length=1, max_length=100000)
    slug: str = Field(min_length=1, max_length=200)


def notes_router(proxy, session, on_saved=None, observer=None):
    router = APIRouter(prefix="/v1/notes")
    authenticated = Depends(session)

    def observed(result, intent=None):
        if (on_saved or observer) and result.get("note"):
            try:
                if observer:
                    observer.note_saved(result["note"], intent)
                else:
                    on_saved(result["note"])
            except Exception:  # noqa: BLE001 -- save remains successful if dispatch is unavailable
                # A completed Brain save must never be reported as a failed save
                # just because its independent application handoff failed.
                result["reviewWarning"] = (
                    "Your note is saved, but its background review could not be queued. Save again to retry."
                )
                if observer and intent:
                    observer.retry_intents.add(intent)
        return result

    def failed(intent, error):
        if observer and intent:
            observer.retry_intents.add(intent)
            observer.write_failed(
                intent, error.status in (400, 404, 409, 422) and not error.extra.get("completed")
            )

    @router.get("/search")
    def search(q: str = "", auth=authenticated):
        if len(q) > 500:
            raise NotesError(422, "Use a shorter search query.")
        return proxy.search(auth["csrf"], q)

    @router.get("/items/{slug}")
    def get(slug: str, auth=authenticated):
        return proxy.get(auth["csrf"], slug)

    @router.post("/items/{slug}/preview")
    def preview(slug: str, body: PreviewInput, auth=authenticated):
        return proxy.preview(auth["csrf"], slug, body.fetchToken, body.body)

    @router.post("/previews/{token}/confirm")
    def confirm(token: str, auth=authenticated):
        snapshot = proxy.state(auth["csrf"])["previews"].get(token)
        intent = (
            observer.prepare_write(snapshot["slug"], snapshot["raw"]["version"], "save")
            if observer and snapshot and snapshot["state"] == "pending"
            else None
        )
        try:
            return observed(proxy.confirm(auth["csrf"], token), intent)
        except NotesError as error:
            failed(intent, error)
            if (on_saved or observer) and error.extra.get("completed", 0):
                preview = proxy.state(auth["csrf"])["previews"].get(token)
                if preview:
                    try:
                        observed(proxy.get(auth["csrf"], preview["slug"]), intent)
                    except NotesError:
                        pass
            raise

    @router.post("/previews/{token}/cancel")
    def cancel(token: str, auth=authenticated):
        return proxy.cancel(auth["csrf"], token)

    @router.post("/create")
    def create(body: CreateInput, auth=authenticated):
        intent = observer.prepare_write(body.slug, None, "create") if observer else None
        try:
            return observed(proxy.create(auth["csrf"], body.text, body.slug), intent)
        except NotesError as error:
            failed(intent, error)
            raise

    @router.post("/undo")
    def undo(auth=authenticated):
        slug = proxy.state(auth["csrf"]).get("undo_slug")
        before = proxy.get(auth["csrf"], slug)["note"]["version"] if observer and slug else None
        intent = observer.prepare_write(slug, before, "undo") if observer and slug else None
        try:
            result = proxy.undo(auth["csrf"])
        except NotesError as error:
            failed(intent, error)
            raise
        if (on_saved or observer) and slug:
            try:
                observed_note = observed(proxy.get(auth["csrf"], slug), intent)
                if observed_note.get("reviewWarning"):
                    result["reviewWarning"] = observed_note["reviewWarning"]
            except NotesError:
                result["reviewWarning"] = (
                    "Undo succeeded. The source note is no longer readable; linked work is preserved."
                )
        return result

    return router
