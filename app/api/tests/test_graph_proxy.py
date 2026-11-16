import io
import json
from urllib.error import HTTPError, URLError

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from yggdress_app import graph_proxy
from yggdress_app.graph_proxy import ASSETS, BrainGraphHTTP, existing_graph, graph_router
from yggdress_app.notes_proxy import BrainNotesHTTP, NotesError, NotesProxy

PAGE = b'<html><script>const DATA = {"nodes":[{"id":"invented"}],"edges":[]};</script></html>'


class Opener:
    def __init__(self, raw=PAGE, error=None):
        self.raw, self.error, self.requests = raw, error, []

    def open(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return io.BytesIO(self.raw)


def test_graph_transport_keeps_auth_server_side_and_refuses_unknown_paths(monkeypatch):
    opener = Opener()
    monkeypatch.setattr(graph_proxy, "build_opener", lambda *_: opener)
    graph = BrainGraphHTTP(BrainNotesHTTP("http://localhost:8100", "invented", "test-only"))
    assert graph.status() == {"nodes": 1, "links": 0, "source": "brain-viewer"}
    assert opener.requests[0].full_url == "http://localhost:8100/graph/graph.html"
    assert opener.requests[0].get_header("Authorization").startswith("Basic ")
    for path in ("../.env", "note/secret", "graph.html?x=1", "https://example.test/file"):
        with pytest.raises(NotesError) as error:
            graph.asset(path)
        assert error.value.status == 404
    assert len(opener.requests) == 1


@pytest.mark.parametrize("raw", [b"not html", b"const DATA = null;", b"const DATA = {};"])
def test_invalid_graph_is_reported_without_demo_fallback(monkeypatch, raw):
    monkeypatch.setattr(graph_proxy, "build_opener", lambda *_: Opener(raw))
    graph = BrainGraphHTTP(BrainNotesHTTP("http://localhost:8100", "test", "test"))
    with pytest.raises(NotesError) as error:
        graph.status()
    assert error.value.code == "graph_format"


@pytest.mark.parametrize(
    "failure",
    [
        URLError("offline"),
        HTTPError("http://localhost", 302, "redirect", {}, None),
    ],
)
def test_unavailable_graph_and_redirect_are_safe_errors(monkeypatch, failure):
    monkeypatch.setattr(graph_proxy, "build_opener", lambda *_: Opener(error=failure))
    graph = BrainGraphHTTP(BrainNotesHTTP("http://localhost:8100", "test", "test"))
    with pytest.raises(NotesError) as error:
        graph.asset("graph.html")
    assert error.value.status == 503 and error.value.code == "graph_unavailable"


def test_private_asset_limit_and_fixture_fail_closed(monkeypatch):
    monkeypatch.setattr(graph_proxy, "build_opener", lambda *_: Opener(b"x" * 5_000_001))
    graph = BrainGraphHTTP(BrainNotesHTTP("http://localhost:8100", "test", "test"))
    with pytest.raises(NotesError) as error:
        graph.asset("three.js")
    assert error.value.status == 502

    class Synthetic:
        pass

    with pytest.raises(NotesError) as error:
        existing_graph(NotesProxy(Synthetic())).status()
    assert error.value.status == 503


def test_every_graph_route_requires_application_session():
    calls = []

    class Graph:
        def status(self):
            calls.append("status")
            return {"nodes": 1, "links": 0}

        def asset(self, name):
            calls.append(name)
            return PAGE

    def session(request: Request):
        if request.headers.get("x-test-session") != "invented":
            raise HTTPException(401, "Sign in")

    app = FastAPI()

    @app.exception_handler(NotesError)
    async def failure(_, error):
        return JSONResponse({"detail": error.message}, status_code=error.status)

    app.include_router(graph_router(Graph(), session))
    client = TestClient(app)
    for path in ["status", *("assets/" + asset for asset in ASSETS)]:
        assert client.get("/v1/graph/" + path).status_code == 401
    assert not calls
    client.headers["x-test-session"] = "invented"
    assert client.get("/v1/graph/status").json()["nodes"] == 1
    response = client.get("/v1/graph/assets/graph.html")
    assert response.content == PAGE and "text/html" in response.headers["content-type"]
    assert client.get("/v1/graph/assets/private.sql").status_code == 404
    assert "invented" not in json.dumps(calls)
