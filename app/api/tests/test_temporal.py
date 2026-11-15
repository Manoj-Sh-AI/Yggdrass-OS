from uuid import uuid4

from notes_fixture import SyntheticBrain

from yggdress_app.database import Database


def time_command(client, operation, data, item=None, key=None, status=200):
    response = client.post(
        "/v1/application/time/commands",
        json={
            "key": key or str(uuid4()),
            "operation": operation,
            "data": data,
            "id": item["id"] if item else None,
            "version": item["version"] if item else None,
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def snapshot(client):
    response = client.get(
        "/v1/application/planning?start=2026-03-28&end=2026-04-02&timezone=Europe%2FBerlin"
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_date_ranges_preserve_precision_and_do_not_consume_focus_or_timed_capacity(signed_in):
    client, _, _ = signed_in
    created = time_command(
        client,
        "date_item.create",
        {"title": "Synthetic date range", "starts_on": "2026-03-28", "ends_before": "2026-04-01"},
    )
    data = snapshot(client)
    item = data["date_items"][0]
    assert (
        item["id"] == created["id"]
        and str(item["starts_on"]) == "2026-03-28"
        and str(item["ends_before"]) == "2026-04-01"
    )
    assert (
        "starts_at" not in item
        and data["events"] == []
        and data["blocks"] == []
        and data["sessions"] == []
    )
    assert all(day["event_minutes"] == day["actual_minutes"] == 0 for day in data["summaries"])


def test_availability_is_not_an_appointment_and_validates_clock_changes(signed_in):
    client, _, _ = signed_in
    invalid = {
        "title": "Synthetic available time",
        "start": "2026-03-29T02:30",
        "end": "2026-03-29T04:00",
        "timezone": "Europe/Berlin",
    }
    time_command(client, "availability.create", invalid, status=422)
    created = time_command(client, "availability.create", {**invalid, "start": "2026-03-29T03:00"})
    data = snapshot(client)
    assert data["availability"][0]["id"] == created["id"] and data["events"] == []
    assert all(day["event_minutes"] == 0 for day in data["summaries"])


def test_date_source_links_replay_cancel_and_unlink_keep_history(signed_in):
    client, app, settings = signed_in
    fixture = SyntheticBrain()
    app.state.notes_proxy.http = fixture
    command = {
        "key": str(uuid4()),
        "operation": "date_item.create",
        "note_slug": "sample",
        "note_revision": "1",
        "date_item": {
            "title": "Synthetic source date",
            "kind": "review",
            "starts_on": "2026-03-30",
            "ends_before": "2026-03-31",
        },
    }
    response = client.post("/v1/application/connections/from-note", json=command)
    assert response.status_code == 200, response.text
    created = response.json()
    assert client.post("/v1/application/connections/from-note", json=command).json() == created
    note = client.get("/v1/application/connections/notes/sample").json()
    assert (
        note["date_items"][0]["relation"] == "source"
        and note["date_items"][0]["source_revision"] == "1"
    )
    reverse = client.get(
        "/v1/application/connections/calendar-context/date_item/" + created["id"]
    ).json()
    assert reverse["notes"][0]["external_id"] == "sample"
    cancelled = time_command(client, "date_item.remove", {}, created)
    assert snapshot(client)["date_items"] == []
    assert client.get("/v1/application/connections/notes/sample").json()["date_items"][0][
        "cancelled"
    ]
    unlinked = client.post(
        "/v1/application/connections/commands",
        json={
            "key": str(uuid4()),
            "operation": "date_item.unlink_note",
            "entity_id": created["id"],
            "version": cancelled["version"],
            "note_slug": "sample",
            "relation": "source",
        },
    )
    assert unlinked.status_code == 200
    assert all(method == "GET" for method, _, _ in fixture.calls)
    with Database(settings.database_url).connect() as db:
        assert db.execute(
            "SELECT cancelled FROM app.calendar_date_items WHERE id=%s", (created["id"],)
        ).fetchone()["cancelled"]
        deleted = db.execute(
            "SELECT detail FROM app.workspace_changes WHERE entity_type='date_item_note_links' AND operation='DELETE'"
        ).fetchone()
        assert deleted["detail"]["before_refs"]["date_item_id"] == created["id"]


def test_coarse_dates_and_datetime_coercion_are_not_invented_date_ranges(signed_in):
    client, _, _ = signed_in
    base = {
        "title": "Synthetic precise date",
        "starts_on": "2026-03-30",
        "ends_before": "2026-03-31",
    }
    for change in (
        {"starts_on": "2026-03"},
        {"starts_on": "2026-03-30T00:00:00Z"},
        {"ends_before": "2026-03-30"},
        {"kind": "deadline"},
    ):
        time_command(client, "date_item.create", {**base, **change}, status=422)
    assert snapshot(client)["date_items"] == []


def test_temporal_retry_and_stale_version_do_not_overwrite(signed_in):
    client, _, _ = signed_in
    body = {
        "title": "Synthetic availability date",
        "kind": "availability",
        "starts_on": "2026-03-30",
        "ends_before": "2026-03-31",
    }
    key = str(uuid4())
    original = time_command(client, "date_item.create", body, key=key)
    assert time_command(client, "date_item.create", body, key=key) == original
    changed = time_command(
        client, "date_item.update", {**body, "ends_before": "2026-04-01"}, original
    )
    time_command(client, "date_item.remove", {}, original, status=409)
    assert snapshot(client)["date_items"][0]["version"] == changed["version"]
    client.headers.pop("X-Yggdress-CSRF")
    time_command(client, "date_item.create", body, status=403)
