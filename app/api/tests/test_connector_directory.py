"""The connector directory: signing in to an app (an invented OAuth server), its tools under
the skill gate, the encrypted vault, and a real MCP round trip against a local server."""

import json
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from yggdress_app.connector_auth import Auth, AuthError, Vault
from yggdress_app.connector_directory import APPS, BY_ID, App
from yggdress_app.connectors import Catalog, mcp_lister
from yggdress_app.orchestration_host import Host
from yggdress_app.skill_registry import SkillRegistry
from yggdress_app.tool_gate import WRITE, ToolLocked, default_registry

NOTES = App("notes-app", "Notes App", "Notes & docs", "Invented.", "email",
            "https://mcp.example.test/mcp")  # fmt: skip
SETUP = App("setup-app", "Setup App", "Code", "Invented.", "code",
            "https://mcp.example.test/mcp", "client", ("read",),
            ("SETUP_APP_CLIENT_ID", "SETUP_APP_CLIENT_SECRET"), setup="Make an app.")  # fmt: skip
TOOLS = [
    {"name": "search", "description": "Search pages", "annotations": {"readOnlyHint": True}},
    {"name": "update_page", "description": "Change a page", "annotations": {}},
]


class FakeOAuth:
    """An invented authorization server and protected resource. Records every request."""

    def __init__(self):
        self.requests, self.issued, self.revoked = [], 0, []
        self.dcr = True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url == "https://mcp.example.test/.well-known/oauth-protected-resource/mcp":
            return httpx.Response(200, json={"resource": "https://mcp.example.test/mcp",
                                             "authorization_servers": ["https://auth.example.test"]})  # fmt: skip
        if url == "https://auth.example.test/.well-known/oauth-authorization-server":
            meta = {"authorization_endpoint": "https://auth.example.test/authorize",
                    "token_endpoint": "https://auth.example.test/token",
                    "revocation_endpoint": "https://auth.example.test/revoke",
                    "code_challenge_methods_supported": ["S256"]}  # fmt: skip
            if self.dcr:
                meta["registration_endpoint"] = "https://auth.example.test/register"
            return httpx.Response(200, json=meta)
        if url == "https://auth.example.test/register":
            body = json.loads(request.content)
            assert body["token_endpoint_auth_method"] == "none"
            return httpx.Response(201, json={"client_id": "invented-client"})
        if url == "https://auth.example.test/token":
            form = parse_qs(request.content.decode())
            self.issued += 1
            if form["grant_type"] == ["authorization_code"]:
                assert form["code"] == ["invented-code"] and form["code_verifier"]
            return httpx.Response(200, json={"access_token": f"invented-access-{self.issued}",
                                             "refresh_token": "invented-refresh",
                                             "expires_in": 3600})  # fmt: skip
        if url == "https://auth.example.test/revoke":
            self.revoked.append(parse_qs(request.content.decode())["token"][0])
            return httpx.Response(200)
        return httpx.Response(404)


@pytest.fixture
def oauth():
    return FakeOAuth()


@pytest.fixture
def auth(tmp_path, oauth):
    return Auth(Vault(tmp_path / "vault"), http=httpx.Client(transport=httpx.MockTransport(oauth)),
                environ={})  # fmt: skip


def sign_in(auth, app=NOTES, redirect="http://127.0.0.1:3000/api/backend/connectors/callback"):
    url = auth.start(app, redirect)
    query = parse_qs(urlsplit(url).query)
    return url, query


def test_the_directory_offers_at_least_twenty_real_apps_without_secrets():
    usable = [a for a in APPS if a.auth != "unavailable"]
    assert len(usable) >= 20 and len(BY_ID) == len(APPS)
    for app in usable:
        assert app.url.startswith("https://"), app.id
        assert app.id.replace("-", "").isalnum() and app.domain
        if app.auth == "client":
            assert len(app.client_env) == 2 and all("=" not in n for n in app.client_env)
            assert app.setup
    assert {"gmail", "google-calendar", "notion", "slack", "github"} <= set(BY_ID)


def test_sign_in_registers_uses_pkce_and_stores_tokens_encrypted(auth, oauth, tmp_path):
    url, query = sign_in(auth)
    assert url.startswith("https://auth.example.test/authorize?")
    assert query["client_id"] == ["invented-client"]
    assert query["code_challenge_method"] == ["S256"] and query["state"][0]
    assert query["resource"] == ["https://mcp.example.test/mcp"]
    app = auth.finish(query["state"][0], "invented-code", {NOTES.id: NOTES}.get)
    assert app is NOTES and auth.access(NOTES) == "invented-access-1"
    raw = (tmp_path / "vault" / "vault.bin").read_bytes()
    assert b"invented-access" not in raw and b"invented-refresh" not in raw


def test_a_sign_in_state_works_once_and_expires(auth, monkeypatch):
    _, query = sign_in(auth)
    state = query["state"][0]
    auth.finish(state, "invented-code", {NOTES.id: NOTES}.get)
    with pytest.raises(AuthError, match="expired or was already used"):
        auth.finish(state, "invented-code", {NOTES.id: NOTES}.get)
    _, query = sign_in(auth)
    later = time.time() + 601
    monkeypatch.setattr("yggdress_app.connector_auth.time.time", lambda: later)
    with pytest.raises(AuthError, match="expired"):
        auth.finish(query["state"][0], "invented-code", {NOTES.id: NOTES}.get)
    with pytest.raises(AuthError):
        auth.finish("made-up-state", "invented-code", {NOTES.id: NOTES}.get)


def test_an_expired_token_refreshes_and_disconnect_revokes(auth, oauth):
    _, query = sign_in(auth)
    auth.finish(query["state"][0], "invented-code", {NOTES.id: NOTES}.get)
    record = auth.vault.get(NOTES.id)
    auth.vault.update(NOTES.id, tokens={**record["tokens"], "expires": 0})
    assert auth.access(NOTES) == "invented-access-2"
    auth.disconnect(NOTES)
    assert oauth.revoked == ["invented-refresh"]
    assert "tokens" not in auth.vault.get(NOTES.id) and auth.vault.get(NOTES.id)["client"]
    with pytest.raises(AuthError, match="not connected"):
        auth.access(NOTES)


def test_an_app_needing_its_own_oauth_app_waits_for_env_names(auth, oauth):
    assert auth.missing_env(SETUP) == ["SETUP_APP_CLIENT_ID", "SETUP_APP_CLIENT_SECRET"]
    with pytest.raises(AuthError, match="needs SETUP_APP_CLIENT_ID"):
        auth.start(SETUP, "http://127.0.0.1:3000/cb")
    auth.environ = {"SETUP_APP_CLIENT_ID": "invented-id", "SETUP_APP_CLIENT_SECRET": "invented"}
    oauth.dcr = False
    _, query = sign_in(auth, SETUP)
    assert query["client_id"] == ["invented-id"] and query["scope"] == ["read"]
    auth.finish(query["state"][0], "invented-code", {SETUP.id: SETUP}.get)
    token_form = parse_qs(oauth.requests[-1].content.decode())
    assert token_form["client_secret"] == ["invented"]


@pytest.fixture
def catalog(tmp_path, auth):
    calls = []
    cat = Catalog(tmp_path / "none.json", default_registry(), mcp_lister, apps=(NOTES, SETUP),
                  auth=auth, mcp_list=lambda url, token: TOOLS,
                  mcp_call=lambda url, token, name, args: calls.append((name, args, token))
                  or {"error": False, "text": "Invented result", "truncated": False})  # fmt: skip
    return cat, calls


def test_connecting_brings_the_apps_tools_under_the_skill_gate(catalog):
    cat, calls = catalog
    views = {v["name"]: v for v in cat.view()}
    assert views["notes-app"]["status"] == "available"
    assert views["setup-app"]["status"] == "needs_setup"
    _, query = sign_in(cat.auth)
    view = cat.connected(query["state"][0], "invented-code")
    assert view["status"] == "connected" and view["enabled"] and view["tool_count"] == 2
    tools = cat.registry.tools
    assert tools["notes-app__search"].risks == frozenset()
    assert tools["notes-app__update_page"].risks == {WRITE}
    host = Host(SkillRegistry(), cat.registry, handlers=cat.handlers())
    with pytest.raises(ToolLocked):  # locked until a skill in its domain loads
        host.call("yggdras", {"name": "notes-app__search", "input": {"q": "x"}})
    host.load("triage-inbox")  # domain: email
    assert host.call("yggdras", {"name": "notes-app__search", "input": {"q": "x"}})["text"]
    assert calls == [("search", {"q": "x"}, "invented-access-1")]
    with pytest.raises(ToolLocked, match="approval"):  # writes only after a card
        host.call("yggdras", {"name": "notes-app__update_page", "input": {}})
    cat.switch("notes-app", False)
    assert not any(n.startswith("notes-app__") for n in cat.registry.tools)
    cat.switch("notes-app", True)
    cat.disconnect("notes-app")
    assert {v["name"]: v for v in cat.view()}["notes-app"]["status"] == "available"
    assert not any(n.startswith("notes-app__") for n in cat.registry.tools)


def test_no_token_ever_reaches_the_view(catalog):
    cat, _ = catalog
    _, query = sign_in(cat.auth)
    cat.connected(query["state"][0], "invented-code")
    assert "invented-access" not in json.dumps(cat.view())


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_real_mcp_round_trip_lists_annotations_and_calls_a_tool():
    import uvicorn
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    from yggdress_app import connector_mcp

    server = FastMCP("invented", stateless_http=True)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def echo(text: str) -> str:
        """Say it back."""
        return f"echo: {text}"

    port = _free_port()
    config = uvicorn.Config(server.streamable_http_app(), host="127.0.0.1", port=port,
                            log_level="error")  # fmt: skip
    running = uvicorn.Server(config)
    thread = threading.Thread(target=running.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if running.started:
                break
            time.sleep(0.05)
        url = f"http://127.0.0.1:{port}/mcp"
        tools = connector_mcp.list_tools(url, "invented-token")
        assert tools[0]["name"] == "echo" and tools[0]["annotations"]["readOnlyHint"] is True
        out = connector_mcp.call_tool(url, "invented-token", "echo", {"text": "hi"})
        assert out == {"error": False, "text": "echo: hi", "truncated": False}
    finally:
        running.should_exit = True
        thread.join(timeout=5)
