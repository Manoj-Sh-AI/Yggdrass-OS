"""Invented data only: durable reviews, Lia proposal/approval and public-source fixtures."""

import json
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from yggdress_app import daily_content as content
from yggdress_app import daily_filing as filing
from yggdress_app import daily_inputs as inputs

DAY = date(2031, 6, 3)
ZONE = "Europe/Berlin"


class Librarian:
    def __init__(self):
        self.proposals = 0
        self.writes = []
        self.quotes = True
        self.fail_write = False

    def propose_daily(self, entries, corrections):
        self.proposals += 1
        row = entries[0]
        return {
            "proposal": {
                "actions": [
                    {
                        "target": "studio",
                        "fact": row["text"],
                        "evidence": [
                            {
                                "entry_id": row["id"],
                                "quote": row["text"] if self.quotes else "invented quote",
                            }
                        ],
                    }
                ]
            }
        }

    def file_daily_fact(self, target, fact, identifier):
        self.writes.append((target, fact, identifier))
        if self.fail_write:
            raise TimeoutError
        return {
            "done": True,
            "receipt": {"sha": "private-fixture-sha", "token": "private-fixture-receipt"},
        }

    def undo_daily_fact(self, receipt):
        assert receipt["token"] == "private-fixture-receipt"
        return {"done": True}


def test_cited_filing_is_single_use_reversible_and_private(signed_in):
    _, app, _ = signed_in
    database = app.state.database
    lia = Librarian()
    assert filing.consolidate(database, None, DAY)["actions"] == []
    assert filing.consolidate(database, None, DAY - timedelta(days=1))["actions"] == []
    with database.connect() as db:
        first = content.append_journal(
            db, DAY, content.JournalInput(key=uuid4(), text="The invented studio moved.")
        )
    offer = filing.consolidate(database, lia, DAY)["actions"][0]
    assert str(first["id"]) == offer["evidence"][0]["entry_id"]
    assert not lia.writes
    assert filing.consolidate(database, lia, DAY)["actions"] == [offer]
    assert lia.proposals == 1
    identifier = offer["id"]
    moved = filing.decide(database, lia, identifier, "move", "ceramics")
    assert moved["state"] == "proposed" and moved["target"] == "ceramics"
    saved = filing.decide(database, lia, identifier, "accept")
    assert saved["can_undo"] and saved["state"] == "applied" and "undo_ref" not in saved
    assert filing.decide(database, lia, identifier, "accept") == saved
    assert len(lia.writes) == 1
    assert filing.decide(database, lia, identifier, "undo")["state"] == "reverted"
    with database.connect() as db:
        morning = content.preview(db, "morning", DAY + timedelta(days=1), ZONE)
        assert "private-fixture" not in morning["context"]
        assert "The invented studio moved." not in morning["text"]


def test_superseding_entries_cancel_approval_and_new_proposals_use_only_corrections(signed_in):
    _, app, _ = signed_in
    database = app.state.database
    lia = Librarian()
    key = uuid4()
    with database.connect() as db:
        content.append_journal(db, DAY, content.JournalInput(key=key, text="The studio is blue."))
    offer = filing.consolidate(database, lia, DAY)["actions"][0]
    with database.connect() as db:
        new = content.append_journal(
            db,
            DAY + timedelta(days=2),
            content.JournalInput(key=uuid4(), text="The studio is green.", supersedes_id=key),
        )
    with pytest.raises(HTTPException, match="corrected"):
        filing.decide(database, lia, offer["id"], "accept")
    assert new["local_date"] == DAY and not lia.writes
    lia.quotes = False
    with pytest.raises(HTTPException, match="proposals could not"):
        filing.consolidate(database, lia, DAY)
    lia.quotes = True
    result = filing.consolidate(database, lia, DAY)
    new_offer = next(a for a in result["actions"] if a["id"] != offer["id"])
    assert new_offer["fact"] == "The studio is green."
    lia.fail_write = True
    with pytest.raises(HTTPException, match="receipt"):
        filing.decide(database, lia, new_offer["id"], "accept")
    with pytest.raises(HTTPException, match="current filing state"):
        filing.decide(database, lia, new_offer["id"], "accept")
    assert len(lia.writes) == 1


def test_evening_carries_exact_step_and_only_confirmed_lesson(signed_in):
    _, app, _ = signed_in
    database = app.state.database
    task = uuid4()
    tomorrow = DAY + timedelta(days=1)
    with database.connect() as db:
        db.execute(
            "INSERT INTO app.tasks(id,title,objective,area,due_date) VALUES(%s,'Draft','Finish draft','work',%s)",
            (task, tomorrow),
        )
        body = content.ReviewInput(
            key=uuid4(),
            outcome="partial",
            worked="An invented private journal line.",
            next_steps=[{"task_id": task, "step": "Open the blue draft", "slot": "09:30"}],
            lessons=["If writing, open the blue draft."],
            tomorrow="Check draft",
            energy=3,
        )
        result = content.submit_review(db, DAY, ZONE, body)
        morning = content.preview(db, "morning", tomorrow, ZONE)
        assert "Check draft" in morning["text"] and not morning["details"]["lessons"]
        assert "private journal" not in morning["context"]
        lesson = result["lessons"][0]
        content.decide_lesson(db, lesson["id"], "confirm")
        db.execute(
            "UPDATE app.daily_lessons SET review_due=%s WHERE id=%s", (tomorrow, lesson["id"])
        )
        assert content.preview(db, "morning", tomorrow, ZONE)["details"]["lessons"][0]["id"] == str(
            lesson["id"]
        )
        scheduled = datetime.combine(tomorrow, datetime.min.time(), tzinfo=UTC)
        value = content.preview(db, "pre_task", tomorrow, ZONE, task, scheduled)
        content.persist_brief(db, value)
        assert (
            "Open the blue draft"
            in content.get_brief(db, "pre_task", tomorrow, task, scheduled)["text"]
        )


def test_weather_and_approved_feeds_are_bounded_and_cache_uses_consent(signed_in):
    _, app, _ = signed_in
    database = app.state.database
    now = datetime(2031, 6, 3, 7, tzinfo=UTC)
    news_url = "https://huggingface.co/blog/fixture"
    hits = []

    def get(url):
        hits.append(url)
        if "dwd-icon" in url:
            return json.dumps(
                {
                    "hourly": {
                        "time": ["2031-06-03T09:00"],
                        "precipitation_probability": [50],
                        "precipitation": [0.2],
                        "weather_code": [3],
                    }
                }
            ).encode()
        if url == inputs.SOURCES["huggingface"]["url"]:
            return (
                f"<rss><channel><item><title>Fixture model</title><link>{news_url}</link>"
                "<pubDate>Tue, 03 Jun 2031 06:00:00 GMT</pubDate></item>"
                "<item><title>Invalid article</title><link>https://example.invalid/no</link>"
                "<pubDate>Tue, 03 Jun 2031 06:00:00 GMT</pubDate></item></channel></rss>"
            ).encode()
        assert url == news_url
        return b"<h1>Fixture model</h1><p>This model demonstrates fixture inference in an invented local test.</p>"

    assert inputs.refresh(database, DAY, ZONE, get=get, now=now) == {} and not hits
    with database.connect() as db:
        db.execute(
            "UPDATE app.daily_routine_settings SET enabled=true,approved_feeds='{huggingface}',"
            "latitude=52,longitude=10"
        )
    result = inputs.refresh(database, DAY, ZONE, get=get, now=now)
    assert len(hits) == 3 and "Bring an umbrella" in result["weather"]["text"]
    assert result["news"][0]["url"] == news_url and result["news"][0]["tag"] == "primary-verified"
    assert inputs.refresh(database, DAY, ZONE, get=get, now=now) == result and len(hits) == 3
    with database.connect() as db:
        db.execute("UPDATE app.daily_routine_settings SET approved_feeds='{}'")
        assert not content.preview(db, "morning", DAY, ZONE)["details"]["news"]
