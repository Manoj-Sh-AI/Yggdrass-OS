import secrets
from uuid import uuid4

from fastapi.testclient import TestClient

from yggdress_app.application import create_app

ROOT = "/v1/chat"


def command(client, operation, data=None, item=None, *, status=200, key=None):
    response = client.post(
        ROOT + "/commands",
        json={
            "key": key or str(uuid4()),
            "operation": operation,
            "data": data or {},
            "id": item["id"] if item else None,
            "version": item.get("version") if item else None,
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def conversation(client):
    return command(client, "conversation.create")["conversation"]


def provider(signed_in):
    client, _, settings = signed_in
    token = secrets.token_urlsafe(32)
    configured = TestClient(
        create_app(settings, receiver_tokens={"chat": token}), base_url=settings.origin
    )
    configured.cookies.update(client.cookies)
    configured.headers.update(client.headers)
    return configured, {"Authorization": "Bearer " + token}


def event(
    client, auth, request, sequence, kind="delta", text="Synthetic answer", *, status=200, key=None
):
    response = client.post(
        "/v1/receivers/chat/events",
        headers=auth,
        json={
            "event_key": key or str(uuid4()),
            "request_id": request["id"],
            "sequence": sequence,
            "kind": kind,
            "text": text,
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def test_saved_history_retries_restart_search_archive_export_delete(signed_in):
    client, _, settings = signed_in
    thread = conversation(client)
    key = str(uuid4())
    message = command(
        client, "message.send", {"content": "Synthetic gardening conversation"}, thread, key=key
    )
    assert message["request"]["state"] == "held"
    assert (
        command(
            client, "message.send", {"content": "Synthetic gardening conversation"}, thread, key=key
        )
        == message
    )
    assert len(client.get(ROOT + "/conversations/" + thread["id"]).json()["messages"]) == 1
    assert (
        client.get(ROOT + "/conversations?q=gardening").json()["conversations"][0]["id"]
        == thread["id"]
    )
    restarted = TestClient(create_app(settings), base_url=settings.origin)
    restarted.cookies.update(client.cookies)
    assert (
        restarted.get(ROOT + "/conversations/" + thread["id"]).json()["messages"][0]["content"]
        == "Synthetic gardening conversation"
    )
    current = message["conversation"]
    renamed = command(client, "conversation.rename", {"title": "Garden decisions"}, current)[
        "conversation"
    ]
    command(client, "conversation.rename", {"title": "Stale rename"}, current, status=409)
    archived = command(client, "conversation.archive", {"archived": True}, renamed)["conversation"]
    assert client.get(ROOT + "/conversations").json()["conversations"] == []
    assert (
        client.get(ROOT + "/conversations?archived=true").json()["conversations"][0]["id"]
        == thread["id"]
    )
    command(client, "message.send", {"content": "Cannot append archived"}, archived, status=409)
    restored = command(client, "conversation.archive", {"archived": False}, archived)[
        "conversation"
    ]
    exported = client.get(ROOT + "/conversations/" + thread["id"] + "/export").json()
    assert exported["messages"][0]["content"] == "Synthetic gardening conversation"
    command(client, "conversation.delete", {}, restored)
    assert client.get(ROOT + "/conversations/" + thread["id"]).status_code == 404


def test_receiver_configuration_never_replays_held_messages(signed_in):
    client, _, _ = signed_in
    thread = conversation(client)
    saved = command(
        client,
        "message.send",
        {"content": "Save without automatic delivery", "deliver": True},
        thread,
    )
    assert saved["request"]["state"] == "held"
    configured, auth = provider(signed_in)
    assert configured.get("/v1/receivers/chat/pending", headers=auth).json()["requests"] == []
    event(configured, auth, saved["request"], 0, status=409)
    queued = command(configured, "message.resend", {}, saved["message"])["request"]
    pending = configured.get("/v1/receivers/chat/pending", headers=auth).json()["requests"]
    assert len(pending) == 1 and pending[0]["id"] == queued["id"]
    context = configured.get("/v1/receivers/chat/requests/" + queued["id"], headers=auth).json()
    assert context["messages"][0]["content"] == "Save without automatic delivery"


def test_ordered_response_retry_and_terminal_state(signed_in):
    client, auth = provider(signed_in)
    thread = conversation(client)
    saved = command(
        client, "message.send", {"content": "Synthetic question", "deliver": True}, thread
    )
    request = saved["request"]
    event(client, auth, request, 1, status=409)
    key = str(uuid4())
    first = event(client, auth, request, 0, text="First ", key=key)
    assert event(client, auth, request, 0, text="First ", key=key) == first
    event(client, auth, request, 0, text="Different", key=key, status=409)
    event(client, auth, request, 1, text="second")
    event(client, auth, request, 2, kind="complete", text="")
    history = client.get(ROOT + "/conversations/" + thread["id"]).json()
    assert [message["content"] for message in history["messages"]] == [
        "Synthetic question",
        "First second",
    ]
    event(client, auth, request, 3, status=409)


def test_edit_cancel_delete_and_archive_protect_against_late_answers(signed_in):
    client, auth = provider(signed_in)
    thread = conversation(client)
    sent = command(
        client, "message.send", {"content": "Original question", "deliver": True}, thread
    )
    edited = command(client, "message.edit", {"content": "Revised question"}, sent["message"])[
        "message"
    ]
    event(client, auth, sent["request"], 0, status=409)
    command(client, "message.edit", {"content": "Stale edit"}, sent["message"], status=409)
    queued = command(client, "message.resend", {}, edited)["request"]
    command(client, "request.cancel", {}, queued)
    event(client, auth, queued, 0, status=409)
    again = command(client, "message.resend", {}, edited)["request"]
    command(client, "message.delete", {}, edited)
    event(client, auth, again, 0, status=409)
    fresh = command(
        client, "message.send", {"content": "Archived question", "deliver": True}, thread
    )
    command(client, "conversation.archive", {"archived": True}, fresh["conversation"])
    event(client, auth, fresh["request"], 0, status=409)


def test_attachment_integrity_private_access_and_conversation_boundary(signed_in):
    client, app, settings = signed_in
    first, second = conversation(client), conversation(client)
    upload = client.post(
        ROOT + "/attachments",
        params={"conversation_id": first["id"], "name": "../private.txt"},
        content=b"Synthetic file",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert upload.status_code == 200, upload.text
    file = upload.json()
    assert (
        file["name"] == "private.txt"
        and file["size"] == len(b"Synthetic file")
        and "data" not in file
    )
    command(client, "message.send", {"attachment_ids": [file["id"]]}, second, status=409)
    sent = command(client, "message.send", {"attachment_ids": [file["id"]]}, first)
    assert sent["message"]["content"] == ""
    history = client.get(ROOT + "/conversations/" + first["id"]).json()
    assert history["attachments"][0]["sha256"] == file["sha256"]
    download = client.get(ROOT + "/attachments/" + file["id"])
    assert download.content == b"Synthetic file" and download.headers[
        "content-disposition"
    ].startswith("attachment;")
    assert (
        TestClient(app, base_url=settings.origin)
        .get(ROOT + "/attachments/" + file["id"])
        .status_code
        == 401
    )
    command(client, "attachment.remove", {}, file, status=409)
    command(client, "message.delete", {}, sent["message"])
    assert client.get(ROOT + "/attachments/" + file["id"]).status_code == 404


def test_invalid_oversized_and_cross_boundary_requests_are_rejected(signed_in):
    client, app, settings = signed_in
    thread = conversation(client)
    command(client, "message.send", {"content": ""}, thread, status=422)
    oversized = client.post(
        ROOT + "/attachments",
        params={"conversation_id": thread["id"], "name": "large.bin"},
        content=b"x" * (10 * 1024 * 1024 + 1),
    )
    assert oversized.status_code == 413
    anon = TestClient(app, base_url=settings.origin)
    assert anon.get(ROOT + "/conversations").status_code == 401
    configured, auth = provider(signed_in)
    assert configured.get("/v1/receivers/chat/pending").status_code == 401
    assert client.get("/v1/receivers/chat/pending", headers=auth).status_code == 503
    assert client.get(ROOT + "/conversations?limit=101").status_code == 422
    assert client.get(ROOT + "/conversations?before=invalid").status_code == 422
    client.headers.pop("X-Yggdress-CSRF")
    command(client, "conversation.create", status=403)


def test_upload_retry_identity_cannot_duplicate_or_replace_file(signed_in):
    client, _, _ = signed_in
    thread = conversation(client)
    params = {"conversation_id": thread["id"], "name": "retry.txt", "upload_id": str(uuid4())}
    first = client.post(ROOT + "/attachments", params=params, content=b"Exact synthetic bytes")
    assert first.status_code == 200, first.text
    assert (
        client.post(ROOT + "/attachments", params=params, content=b"Exact synthetic bytes").json()
        == first.json()
    )
    assert (
        client.post(ROOT + "/attachments", params=params, content=b"Different content").status_code
        == 409
    )
