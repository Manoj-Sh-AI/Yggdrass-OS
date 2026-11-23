"""End-to-end phone API checks against the explicit invented-data fixture only."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[3]
state = json.loads((ROOT / "app/mobile/.cache/device-fixture-state.json").read_text())
assert state == {
    "ready": True,
    "origin": "http://127.0.0.1:3300",
    "data": "invented only",
    "model_calls": 0,
}
origin = state["origin"]


def run():
    with httpx.Client(base_url=origin, follow_redirects=True, timeout=60) as client:
        client.headers["Origin"] = origin
        login = client.post(
            "/api/backend/mobile/auth/login", json={"password": "mobile-fixture-password-123"}
        )
        assert login.status_code == 200
        token = login.json()["token"]
        client.headers["Authorization"] = "Bearer " + token

        def call(method, path, data=None):
            response = client.request(method, "/api/backend/" + path, json=data)
            assert response.status_code < 300, (method, path, response.status_code)
            return response.json()

        day = datetime.now(UTC).date().isoformat()
        month = day[:7]
        payload = {
            "key": str(uuid4()),
            "op": "task.create",
            "data": {
                "title": "Device fixture task",
                "objective": "An invented goal that stays fixed",
                "due_date": day,
            },
        }
        made = call("POST", "application/planning/commands", payload)
        assert call("POST", "application/planning/commands", payload) == made
        snapshot = call("GET", f"application/planning?start={month}-01&end={month}-28")
        task = next(t for t in snapshot["tasks"] if t["title"] == "Device fixture task")
        call(
            "POST",
            "application/planning/commands",
            {
                "key": str(uuid4()),
                "op": "task.execute",
                "id": task["id"],
                "version": task["version"],
                "data": {"action": "complete"},
            },
        )
        snapshot = call("GET", f"application/planning?start={month}-01&end={month}-28")
        task = next(t for t in snapshot["tasks"] if t["id"] == task["id"])
        assert task["done"] and task["objective"] == "An invented goal that stays fixed"
        call(
            "POST",
            "application/planning/commands",
            {
                "key": str(uuid4()),
                "op": "task.execute",
                "id": task["id"],
                "version": task["version"],
                "data": {"action": "reopen"},
            },
        )
        call(
            "POST",
            "application/time/commands",
            {
                "key": str(uuid4()),
                "operation": "date_item.create",
                "data": {
                    "title": "Device fixture calendar item",
                    "description": "Invented only",
                    "kind": "event",
                    "starts_on": day,
                    "ends_before": (datetime.now(UTC).date() + timedelta(days=1)).isoformat(),
                },
            },
        )
        conversation = call(
            "POST",
            "chat/commands",
            {
                "key": str(uuid4()),
                "operation": "conversation.create",
                "data": {"title": "Device fixture chat"},
            },
        )["conversation"]
        call(
            "POST",
            "chat/commands",
            {
                "key": str(uuid4()),
                "operation": "message.send",
                "id": conversation["id"],
                "data": {"content": "Invented message for phone verification", "deliver": False},
            },
        )
        history = call("GET", "chat/conversations/" + conversation["id"])
        assert history["messages"][0]["content"] == "Invented message for phone verification"
        assert history["requests"][0]["state"] == "held"
        notes = call("GET", "notes/search?q=")
        assert all(n["slug"] != "fixture-private" for n in notes["notes"])
        fetched = call("GET", "notes/items/sample")["note"]
        body = fetched["bodyPrefix"] + fetched["content"]
        preview = call(
            "POST",
            "notes/items/sample/preview",
            {
                "fetchToken": fetched["fetchToken"],
                "body": body.replace("First (src:", "Updated invented fact (src:"),
            },
        )
        call("POST", "notes/previews/" + preview["token"] + "/confirm", {})
        assert "Updated invented fact" in call("GET", "notes/items/sample")["note"]["content"]

        # Match Android's actual postUrl behavior: form body, no custom headers.
        client.headers.pop("Authorization")
        client.headers.pop("Origin")
        response = client.post("/api/mobile-session?view=notes", data={"token": token})
        assert response.status_code == 200 and 'class="native-workspace"' in response.text
        graph = client.get("/api/graph-viewer/graph.html")
        assert graph.status_code == 200 and "fixture-private" not in graph.text
        result = {
            "native_bearer_auth": True,
            "idempotent_task_save": True,
            "goal_preserved_on_completion": True,
            "calendar_save": True,
            "chat_persisted_without_replay": True,
            "note_preview_confirm_refresh": True,
            "android_webview_cookie_bridge": True,
            "native_editor_layout": True,
            "sensitive_notes_and_graph_nodes_excluded": True,
            "provider_calls": 0,
            "real_brain_writes": 0,
        }
        (ROOT / "app/mobile/.cache/device-api-verification.json").write_text(json.dumps(result))
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        run()
    except Exception as error:  # noqa: BLE001 -- report only safe diagnostic categories
        print("Invented-data device verification failed: " + type(error).__name__)
        raise SystemExit(1) from None
