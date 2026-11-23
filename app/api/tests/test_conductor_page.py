"""Side chat page context (UI brief Phase E): the server re-applies every safety rule and
resolves "this" by rule. FakeModels only; invented content only."""

import time

import pytest

from yggdress_app.conductor.history import ChatHistory
from yggdress_app.conductor.log import RunLog
from yggdress_app.conductor.models import FakeModels
from yggdress_app.conductor.orchestrator import Conductor
from yggdress_app.conductor.page import describe, parse, this
from yggdress_app.conductor.state import TERMINAL
from yggdress_app.database import Database


def ref(id_, kind="doc", restricted=False, **fields):
    return {"kind": kind, "id": id_, "label": f"Invented {id_}", "origin": "ambient",
            "sensitivity": "restricted" if restricted else "normal", "fields": fields}  # fmt: skip


def test_a_restricted_item_is_reduced_to_its_id_whatever_the_client_sent():
    page = parse({"surface": "note-detail", "focus": ref("n1", restricted=True, area="health"),
                  "visible": [ref("n2", restricted=True, status="open")]})  # fmt: skip
    assert page.focus.label == "Sensitive note" and page.focus.fields == {}
    assert page.visible[0].label == "Sensitive note" and page.visible[0].fields == {}


def test_selection_text_inside_a_restricted_item_is_dropped():
    page = parse(
        {"selection": {"text": "invented private words", "refs": [ref("n1", restricted=True)]}}
    )
    assert page.selection.text == ""


def test_only_whitelisted_short_fields_and_25_items_survive():
    page = parse({"visible": [ref(f"t{i}", kind="task", starts="2026-11-28T10:00", body="x" * 500)
                              for i in range(40)]})  # fmt: skip
    assert len(page.visible) == 25
    assert page.visible[0].fields == {"starts": "2026-11-28T10:00"}


@pytest.mark.parametrize(
    "raw", [None, "nope", {"focus": {"kind": "planet", "id": "x"}}, {"visible": "x"}]
)
def test_a_malformed_context_is_ignored_not_an_error(raw):
    assert parse(raw) is None


def test_this_is_selection_then_focus_then_the_only_visible_item_else_ask():
    assert (
        this(parse({"selection": {"text": "a", "refs": [ref("s")]}, "focus": ref("f")})).id == "s"
    )
    assert this(parse({"focus": ref("f"), "visible": [ref("a"), ref("b")]})).id == "f"
    assert (
        this(parse({"focus": ref("week", kind="view"), "visible": [ref("e1", kind="event")]})).id
        == "e1"
    )
    page = parse({"focus": ref("week", kind="view"), "visible": [ref("a"), ref("b")]})
    assert this(page) is None and "ask which item he means" in describe(page)


def test_the_note_names_ids_and_labels_never_hidden_content():
    note = describe(parse({"route": "/notes", "surface": "note-detail",
                           "focus": ref("n1", restricted=True), "visible": [ref("n2")]}))  # fmt: skip
    assert "doc n1: Sensitive note (sensitive: content not shared)" in note
    assert "doc n2: Invented n2" in note and '"This" means doc n1' in note


@pytest.fixture
def conductor(setup, postgres):
    database = Database(postgres["runtime"])
    models = FakeModels({"orchestrator": ["Moved, in invented words."]})
    c = Conductor(RunLog(database), models, ChatHistory(database), owner="test")
    yield c, models
    c.shutdown()


def test_the_page_reaches_the_models_system_prompt(conductor):
    c, models = conductor
    page = parse({"route": "/calendar", "surface": "calendar-week",
                  "focus": ref("week:2026-11-23", kind="view"),
                  "visible": [ref("e1", kind="event", starts="2026-11-27T09:00")]})  # fmt: skip
    run = c.start("Move this to Friday", page=page)
    deadline = time.monotonic() + 10
    while c.log.snapshot(run.run_id)[0].status not in TERMINAL and time.monotonic() < deadline:
        time.sleep(0.05)
    systems = [
        call["system"] for call in models.calls if call["role"] in ("router", "orchestrator")
    ]
    assert systems and all("Manoj is looking at calendar-week" in s for s in systems)
    assert all('"This" means event e1' in s for s in systems)


def test_without_a_page_the_prompt_is_unchanged(conductor):
    c, models = conductor
    run = c.start("Invented question")
    deadline = time.monotonic() + 10
    while c.log.snapshot(run.run_id)[0].status not in TERMINAL and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any("looking at" in call["system"] for call in models.calls if "system" in call)
