"""Invented records only: device sessions, existing CRUD and sensitive-note exclusion."""

import json

import pytest
from fastapi.testclient import TestClient

from yggdress_app.application import create_app
from yggdress_app.mobile_policy import mobile_graph
from yggdress_app.notes_proxy import NotesProxy


class HTTP:
    configured = True

    def call(self, method, path, body=None):
        if path.startswith("search?"):
            return [{"slug": "public-example"}, {"slug": "private-example"}]
        slug = path.partition("/")[2]
        if method == "GET" and slug in ("public-example", "private-example"):
            private = slug == "private-example"
            return {
                "slug": slug,
                "title": "Private invented note" if private else "Public invented note",
                "body": "---\nslug: "
                + slug
                + "\nsensitivity: "
                + ("high" if private else "normal")
                + "\n---\n# Example\n\n## Facts\n- "
                + ("INVENTED_PRIVATE_TEXT" if private else "A public invented point")
                + "\n",
                "version": 1,
                "outgoing": [{"to": "private-example"}],
                "incoming": [],
            }
        raise AssertionError("No write is expected in these note-policy tests.")


class Graph:
    def status(self):
        return {"nodes": 2, "links": 1, "source": "brain-viewer"}

    def asset(self, name):
        if name != "graph.html":
            return b"// invented vendor fixture"
        return (
            "<script>const DATA = "
            + json.dumps(
                {
                    "nodes": [
                        {
                            "id": 1,
                            "slug": "public-example",
                            "sensitive": False,
                            "name": "Public",
                            "degree": 1,
                        },
                        {
                            "id": 2,
                            "slug": "private-example",
                            "sensitive": True,
                            "facts": ["INVENTED_PRIVATE_TEXT"],
                        },
                    ],
                    "edges": [{"id": 1, "from": 1, "to": 2, "line": "private relationship"}],
                }
            )
            + ";\n</script>"
        ).encode()


@pytest.fixture
def mobile(setup):
    _, _, password, settings = setup
    app = create_app(settings, notes=NotesProxy(HTTP()), graph=Graph())
    client = TestClient(app, base_url=settings.origin)
    login = client.post(
        "/v1/mobile/auth/login",
        json={"password": password},
        headers={"Origin": settings.origin, "X-Yggdress-Login": "1"},
    )
    assert login.status_code == 200 and not login.headers.get("set-cookie")
    token = login.json()["token"]
    client.headers.update({"Authorization": "Bearer " + token})
    return client, app, settings


def test_mobile_session_can_read_and_write_existing_application_records(mobile):
    client, _, _ = mobile
    made = client.post(
        "/v1/application/planning/commands",
        json={
            "key": "eac9c984-7a44-41f0-ad54-ff7d8376012c",
            "op": "task.create",
            "data": {
                "title": "Invented mobile task",
                "objective": "Keep this fixed",
                "due_date": "2030-04-10",
            },
        },
    )
    assert made.status_code == 200
    tasks = client.get("/v1/application/planning?start=2030-04-01&end=2030-04-30").json()["tasks"]
    task = next(t for t in tasks if t["title"] == "Invented mobile task")
    done = client.post(
        "/v1/application/planning/commands",
        json={
            "key": "0acb051a-f5a1-4c2d-acad-83c728d2541f",
            "op": "task.execute",
            "id": task["id"],
            "version": task["version"],
            "data": {"action": "complete"},
        },
    )
    assert done.status_code == 200
    reread = client.get("/v1/application/planning?start=2030-04-01&end=2030-04-30").json()
    assert reread["tasks"][0]["done"] and reread["tasks"][0]["objective"] == "Keep this fixed"


def test_native_bearer_session_is_revoked_on_logout(mobile):
    client, _, _ = mobile
    assert client.get("/v1/auth/session").status_code == 200
    assert client.post("/v1/auth/logout").status_code == 200
    assert client.get("/v1/auth/session").status_code == 401


def test_web_session_cannot_be_repurposed_as_a_mobile_bearer(setup):
    client, _, password, settings = setup
    login = client.post(
        "/v1/auth/login",
        json={"password": password},
        headers={"Origin": settings.origin, "X-Yggdress-Login": "1"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = "Bearer " + client.cookies["yggdress_session"]
    assert client.get("/v1/auth/session").status_code == 401


def test_mobile_notes_exclude_sensitive_content_and_links(mobile):
    client, _, _ = mobile
    response = client.get("/v1/notes/search?q=")
    assert response.status_code == 200
    assert "private-example" not in response.text and "INVENTED_PRIVATE_TEXT" not in response.text
    assert len(response.json()["notes"]) == 1
    response = client.get("/v1/notes/items/private-example")
    assert response.status_code == 403 and "INVENTED_PRIVATE_TEXT" not in response.text
    assert (
        client.post(
            "/v1/notes/items/private-example/preview",
            json={"fetchToken": "invented", "body": "## Facts\n- New"},
        ).status_code
        == 403
    )


def test_mobile_graph_excludes_sensitive_nodes_and_incident_edges(mobile):
    client, _, _ = mobile
    response = client.get("/v1/graph/assets/graph.html")
    assert response.status_code == 200
    assert "private-example" not in response.text and "INVENTED_PRIVATE_TEXT" not in response.text
    assert '"edges": []' in response.text and '"degree": 0' in response.text
    assert client.get("/v1/graph/status").json()["nodes"] == 1


def test_webview_cookie_keeps_mobile_restrictions(mobile):
    client, _, _ = mobile
    assert client.post("/v1/mobile/webview-session").status_code == 200
    del client.headers["Authorization"]
    assert client.get("/v1/notes/items/private-example").status_code == 403
    assert client.get("/v1/brain/notes").status_code == 403
    assert client.get("/v1/yggdras/cards").status_code == 403
    assert client.post("/v1/application/planning/commands", json={}).status_code == 403


def test_unknown_graph_sensitivity_is_not_exported():
    blob = b'const DATA = {"nodes":[{"id":1,"facts":["UNKNOWN"]}],"edges":[]};'
    assert b"UNKNOWN" not in mobile_graph(blob)


def test_owner_approved_mobile_catalogue_and_graph_match_desktop(setup):
    from dataclasses import replace

    _, _, password, settings = setup
    settings = replace(settings, mobile_sensitive_access=True)
    app = create_app(settings, notes=NotesProxy(HTTP()), graph=Graph())
    phone = TestClient(app, base_url=settings.origin)
    login = phone.post(
        "/v1/mobile/auth/login",
        json={"password": password},
        headers={"Origin": settings.origin, "X-Yggdress-Login": "1"},
    )
    phone.headers["Authorization"] = "Bearer " + login.json()["token"]
    desktop = TestClient(app, base_url=settings.origin)
    assert (
        desktop.post(
            "/v1/auth/login",
            json={"password": password},
            headers={"Origin": settings.origin, "X-Yggdress-Login": "1"},
        ).status_code
        == 200
    )
    phone_notes = phone.get("/v1/notes/search?q=")
    assert phone_notes.json() == desktop.get("/v1/notes/search?q=").json()
    assert len(phone_notes.json()["notes"]) == 2
    private = phone.get("/v1/notes/items/private-example")
    assert private.status_code == 200 and private.json()["note"]["sensitive"] is True
    assert private.json()["note"]["description"] == "Sensitive note"
    assert phone.get("/v1/graph/status").json() == desktop.get("/v1/graph/status").json()
    assert (
        phone.get("/v1/graph/assets/graph.html").content
        == desktop.get("/v1/graph/assets/graph.html").content
    )
    # Access to the owner's catalogue does not elevate the mobile token itself.
    assert phone.get("/v1/brain/notes").status_code == 403
    assert phone.post("/v1/mobile/webview-session").status_code == 200
    del phone.headers["Authorization"]
    assert phone.get("/v1/notes/items/private-example").status_code == 200
    assert phone.get("/v1/yggdras/cards").status_code == 403
    assert phone.post("/v1/application/planning/commands", json={}).status_code == 403


def test_phone_cannot_grant_itself_sensitive_access(mobile):
    client, _, _ = mobile
    client.headers["X-Yggdress-Mobile-Sensitive-Access"] = "1"
    assert client.get("/v1/notes/items/private-example").status_code == 403


def test_phone_reads_the_catalogs_but_cannot_switch_or_approve(mobile):
    client, _, _ = mobile
    # Reads pass the mobile gate (this app has no Yggdras service, so they 404 past it).
    for path in ("/v1/yggdras/connectors", "/v1/yggdras/skills", "/v1/yggdras/skills/send-email"):
        assert client.get(path).status_code != 403, path
    assert client.post("/v1/yggdras/connectors/mail", json={"enabled": True}).status_code == 403
    assert client.get("/v1/yggdras/cards").status_code == 403
    assert client.get("/v1/brain/notes").status_code == 403


def test_a_phone_sign_in_lasts_30_days_and_renews_with_use(mobile, postgres):
    """The phone keeps ringing day to day without signing in again (Manoj, 2026-11-20)."""
    from datetime import UTC, datetime, timedelta

    from yggdress_app.database import Database

    client, _, _ = mobile
    with Database(postgres["admin"]).connect() as db:
        expires = db.execute("SELECT max(expires_at) AS e FROM app.sessions").fetchone()["e"]
        assert expires - datetime.now(UTC) > timedelta(days=29)
        # 20 days later (simulated): the next request renews it to 30 days again.
        db.execute("UPDATE app.sessions SET expires_at=now()+interval '10 days'")
    assert client.get("/v1/auth/session").status_code == 200
    with Database(postgres["admin"]).connect() as db:
        expires = db.execute("SELECT max(expires_at) AS e FROM app.sessions").fetchone()["e"]
    assert expires - datetime.now(UTC) > timedelta(days=29)
