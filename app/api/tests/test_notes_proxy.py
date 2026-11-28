import base64
import copy
import json
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from urllib.error import URLError

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from notes_fixture import BODY, SyntheticBrain

from yggdress_app import notes_proxy
from yggdress_app.notes_proxy import (
    MARKDOWN,
    STALE,
    BrainNotesHTTP,
    NotesError,
    NotesProxy,
    note_view,
    notes_router,
)


@pytest.fixture
def subject():
    fake = SyntheticBrain()
    return NotesProxy(fake), fake


def review(proxy, text, owner="session"):
    fetched = proxy.get(owner, "sample")
    return proxy.preview(owner, "sample", fetched["note"]["fetchToken"], text)


def test_search_empty_query_full_body_and_area_tags(subject):
    proxy, fake = subject
    result = proxy.search("one", "")
    assert fake.calls[0] == ("GET", "search?q=", None)
    note = result["notes"][0]
    assert note["title"] == "Sample"
    assert note["description"] == "First (src: self, 2030-01-01)"
    assert note["tags"] == ["04-learning", "02-work"]
    assert note["links"] == ["linked"] and note["backlinks"] == ["backlink"]
    assert note["bodyPrefix"] + note["content"] == BODY
    assert "fetchToken" not in note
    proxy.search("one", "a & b")
    assert "search?q=a+%26+b" in [call[1] for call in fake.calls]


def test_title_fallback_and_missing_version(subject):
    _, fake = subject
    raw = fake.notes["sample"].copy()
    raw["title"] = ""
    assert note_view(raw)["title"] == "sample"
    del raw["version"]
    with pytest.raises(NotesError) as caught:
        note_view(raw)
    assert caught.value.status == 502


def test_search_detail_reads_are_bounded_parallel_and_preserve_order():
    fake = SyntheticBrain()
    original = fake.notes["sample"]
    fake.notes = {
        f"note-{i:02d}": {**copy.deepcopy(original), "slug": f"note-{i:02d}"} for i in range(20)
    }
    call = fake.call
    active = peak = 0
    lock = Lock()

    def delayed(method, path, body=None):
        nonlocal active, peak
        if not path.startswith("note/"):
            return call(method, path, body)
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.01)
            return call(method, path, body)
        finally:
            with lock:
                active -= 1

    fake.call = delayed
    notes = NotesProxy(fake).search("one", "")["notes"]
    assert [n["slug"] for n in notes] == sorted(fake.notes)
    assert 1 < peak <= 8


def test_reordering_facts_is_refused_without_permanent_line_operations(subject):
    proxy, fake = subject
    first = "First (src: self, 2030-01-01)"
    second = "Second [[linked]] (src: self, 2030-01-01)"
    with pytest.raises(NotesError) as error:
        review(proxy, BODY.replace(first, "TEMP").replace(second, first).replace("TEMP", second))
    assert error.value.status == 422
    assert not [c for c in fake.calls if c[0] == "POST"]


def test_combined_preview_no_writes_and_confirm_version_chaining(subject):
    proxy, fake = subject
    changed = BODY.replace("First", "Changed first").replace(
        "Second [[linked]]", "Changed second [[new-link]]"
    )
    preview = review(proxy, changed)
    assert len(preview["changes"]) == 2
    assert fake.saved == 0
    assert all(p["version"] == 1 and p["preview"] for m, _, p in fake.calls if m == "POST")
    assert preview["changes"][0]["links_removed"] == ["linked"]
    result = proxy.confirm("session", preview["token"])
    writes = [p for m, _, p in fake.calls if m == "POST" and not p["preview"]]
    assert [p["version"] for p in writes] == [1, 2]
    assert result["note"]["version"] == "3" and result["canUndo"]
    assert "Changed second" in result["note"]["content"]
    assert proxy.confirm("session", preview["token"]) == result
    assert fake.saved == 2


def test_additions_staged_until_confirm_and_server_provenance_anchors(subject):
    proxy, fake = subject
    changed = BODY.replace("## Links", "- Added [[x]]\n- Another addition\n## Links")
    preview = review(proxy, changed)
    assert not [c for c in fake.calls if c[0] == "POST"]
    assert preview["changes"][0]["links_added"] == ["x"]
    result = proxy.confirm("session", preview["token"])
    assert result["completed"] == 2
    assert "Added [[x]] (src:" in result["note"]["content"]
    calls = [p for m, path, p in fake.calls if m == "POST" and path.endswith("add-fact")]
    assert calls[1]["after_line"] == "Added [[x]] (src: self, 2030-01-01)"


def test_remove_permanent_preview_and_cancel(subject):
    proxy, fake = subject
    changed = BODY.replace("- First (src: self, 2030-01-01)\n", "")
    preview = review(proxy, changed)
    assert preview["changes"][0]["kind"] == "remove-fact"
    assert preview["changes"][0]["permanent"]
    proxy.cancel("session", preview["token"])
    with pytest.raises(NotesError):
        proxy.confirm("session", preview["token"])
    assert fake.saved == 0


def test_preview_tokens_are_owned_expire_and_cannot_be_forged(subject):
    proxy, fake = subject
    clock = [1]
    proxy.clock = lambda: clock[0]
    preview = review(proxy, BODY.replace("First", "Changed"))
    with pytest.raises(NotesError):
        proxy.confirm("other-session", preview["token"])
    clock[0] += 601
    with pytest.raises(NotesError):
        proxy.confirm("session", preview["token"])
    assert fake.saved == 0


def test_stale_before_confirm_and_mid_sequence_stop(subject):
    proxy, fake = subject
    preview = review(proxy, BODY.replace("First", "Changed"))
    fake.notes["sample"]["version"] += 1
    with pytest.raises(NotesError) as error:
        proxy.confirm("session", preview["token"])
    assert error.value.message == STALE and fake.saved == 0
    preview = review(proxy, BODY.replace("First", "Changed").replace("Second", "Changed second"))
    fake.fail_at = 1
    with pytest.raises(NotesError) as error:
        proxy.confirm("session", preview["token"])
    assert error.value.extra == {"completed": 1, "canUndo": True}
    assert fake.saved == 1


def test_markdown_409_preserves_input_and_all_real_data(subject):
    proxy, fake = subject
    fetched = proxy.get("one", "sample")["note"]
    fake.markdown = True
    with pytest.raises(NotesError) as error:
        proxy.preview("one", "sample", fetched["fetchToken"], BODY.replace("First", "Changed"))
    assert error.value.code == "brain_markdown" and error.value.message == MARKDOWN
    assert fake.notes["sample"]["body"] == BODY


def test_duplicate_fact_and_nonfact_edits_rejected_before_calls(subject):
    proxy, fake = subject
    for body in (
        BODY.replace("Invented summary", "Edited summary"),
        BODY.replace("## Facts", "## New section"),
    ):
        with pytest.raises(NotesError) as error:
            review(proxy, body)
        assert error.value.status == 422
    duplicate = "First (src: self, 2030-01-01)"
    fake.notes["sample"]["body"] = BODY.replace("## Links", "- " + duplicate + "\n## Links")
    with pytest.raises(NotesError) as error:
        review(proxy, fake.notes["sample"]["body"].replace(duplicate, "Changed", 1))
    assert error.value.status == 422
    assert not [c for c in fake.calls if c[0] == "POST"]


def test_create_and_undo_session_latest_id_only(subject):
    proxy, fake = subject
    result = proxy.create("one", BODY.replace("slug: sample", "slug: created"), "created")
    assert result["links_added"] == ["sample mentions linked"]
    assert proxy.state("one")["undo"] == "created"
    proxy.create("one", BODY.replace("slug: sample", "slug: created"), "created")
    assert len([c for c in fake.calls if c[:2] == ("POST", "note")]) == 1
    with pytest.raises(NotesError):
        proxy.undo("other")
    assert proxy.undo("one")["message"] == "undone"
    assert "created" not in fake.notes
    with pytest.raises(NotesError):
        proxy.undo("one")


def test_application_notes_routes_keep_existing_auth_and_csrf(signed_in):
    client, app, settings = signed_in
    app.state.notes_proxy.http = SyntheticBrain()
    assert client.get("/v1/notes/search?q=").status_code == 200
    csrf = client.headers.pop("X-Yggdress-CSRF")
    response = client.post("/v1/notes/create", json={"slug": "created", "text": BODY})
    assert response.status_code == 403
    client.headers["X-Yggdress-CSRF"] = csrf
    client.headers["Origin"] = "http://untrusted.invalid"
    assert client.post("/v1/notes/undo").status_code == 403
    client.headers["Origin"] = settings.origin
    assert client.get("/v1/notes/search").status_code == 200


@contextmanager
def http_fixture(status=200, data=None, redirect=False):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, self.headers.get("Authorization")))
            self.send_response(status)
            if redirect:
                self.send_header("Location", "/api/elsewhere")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            BrainNotesHTTP(
                f"http://127.0.0.1:{server.server_port}", "synthetic-user", "synthetic-password"
            ),
            calls,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_http_attaches_basic_auth_every_request_and_rejects_redirects():
    with http_fixture(data=[]) as (http, calls):
        assert http.call("GET", "search?q=") == []
        assert http.call("GET", "note/sample") == []
        expected = "Basic " + base64.b64encode(b"synthetic-user:synthetic-password").decode()
        assert all(header == expected for _, header in calls)
    with http_fixture(302, redirect=True) as (http, calls):
        with pytest.raises(NotesError):
            http.call("GET", "search?q=")
        assert len(calls) == 1


@pytest.mark.parametrize(
    ("status", "data", "expected", "code"),
    [
        (401, {}, 502, "brain_authentication"),
        (409, {"error": "brain is still on markdown"}, 409, "brain_markdown"),
        (400, {"error": "cannot undo"}, 400, "brain_upstream"),
    ],
)
def test_http_error_mapping(status, data, expected, code):
    with http_fixture(status, data) as (http, _):
        with pytest.raises(NotesError) as error:
            http.call("GET", "note/sample")
        assert error.value.status == expected and error.value.code == code


def test_missing_credentials_fail_closed_and_nonlocal_plain_http_rejected():
    with pytest.raises(NotesError) as error:
        BrainNotesHTTP("http://localhost:8100", "", "").call("GET", "search?q=")
    assert error.value.status == 503
    with pytest.raises(ValueError):
        BrainNotesHTTP("http://example.test", "user", "password")


def test_notes_router_requires_application_session_and_keeps_tokens_private(subject):
    proxy, _ = subject
    api = FastAPI()

    def authenticated():
        raise HTTPException(401, "Sign in")

    api.include_router(notes_router(proxy, authenticated))

    @api.exception_handler(NotesError)
    async def notes_error(_request, error):
        return JSONResponse({"detail": error.message, "code": error.code}, status_code=error.status)

    client = TestClient(api)
    assert client.get("/v1/notes/search").status_code == 401
    api.dependency_overrides[authenticated] = lambda: {"csrf": "one"}
    assert client.get("/v1/notes/search").status_code == 200
    note = client.get("/v1/notes/items/sample").json()["note"]
    response = client.post(
        "/v1/notes/items/sample/preview",
        json={"fetchToken": note["fetchToken"], "body": BODY.replace("First", "Changed")},
    )
    token = response.json()["token"]
    api.dependency_overrides[authenticated] = lambda: {"csrf": "two"}
    assert client.post(f"/v1/notes/previews/{token}/confirm").status_code == 409


def test_delete_previews_then_removes_and_forgets_the_session_undo(subject):
    """Manoj, 2026-11-28: deleting a note is permanent; the preview writes nothing."""
    proxy, fake = subject
    proxy.create("one", BODY.replace("slug: sample", "slug: created"), "created")
    assert proxy.state("one")["undo"] == "created"
    view = proxy.delete_preview("one", "created")
    assert view["preview"] and "created" in fake.notes
    out = proxy.delete("one", "created", 1)
    assert out["deleted"] == "created" and "created" not in fake.notes
    assert out["canUndo"] is False and proxy.state("one")["undo"] is None
    assert fake.calls[-1] == ("POST", "note/created/delete", {"preview": False, "version": 1})


def test_writes_wait_longer_than_reads(monkeypatch):
    """A write re-renders the graph before the Brain replies; 6 s cut saved notes off."""
    seen = []

    class Opener:
        def open(self, request, timeout):
            seen.append((request.get_method(), timeout))
            raise URLError("stop")

    monkeypatch.setattr(notes_proxy, "build_opener", lambda *_: Opener())
    http = BrainNotesHTTP("http://localhost:8100", "user", "password")
    for method in ("GET", "POST"):
        with pytest.raises(NotesError):
            http.call(method, "note/sample", None if method == "GET" else {})
    assert seen == [("GET", notes_proxy.READ_TIMEOUT), ("POST", notes_proxy.WRITE_TIMEOUT)]
    assert notes_proxy.WRITE_TIMEOUT < 60  # the web route gives notes 60 s
