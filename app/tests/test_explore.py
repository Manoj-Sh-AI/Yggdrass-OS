"""Lia looks wider (F1–F7): plan, coverage caps, sibling sweep, capability rule, upcoming
view, escalation and the switches."""

import datetime as dt

import pytest

from test_lia import NODE, FakeClient, cited, note, text, tool_use
from yggdras.data.maps import checks
from yggdras.data.maps.upcoming import fact_dates, upcoming
from yggdras.processing.lia import explore
from yggdras.processing.lia.lia import ABSTAIN, Lia, LiaConfig, explore_config, load_skills
from yggdras.processing.lia.library import Library

TAXONOMY = """# Taxonomy

| Folder | Holds | Not here |
|---|---|---|
| `03-work-career/` | The job search | — |
| `04-learning/` | The thesis, German | — |
| `07-home-admin/` | Residence permit and visa | — |
"""
THESIS = "The thesis made no progress in October 2030. (src: self, 2030-11-01)"
GERMAN = "German made no progress in October 2030. (src: self, 2030-11-01)"
GERMAN_OTHER = "German class is on Mondays. (src: self, 2030-11-01)"
JOBS = "Applications start in January 2031. (src: self, 2030-11-01)"
VISA = "The permit runs until 2031-01-15. (src: self, 2030-11-01; valid: 2030-12-01..)"
TODAY = dt.date(2030, 11, 2)


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "brain" / "library"
    files = {
        "00-manual/taxonomy.md": TAXONOMY,
        "00-manual/node.md": NODE,
        "04-learning/thesis.md": note(
            "thesis", area="04-learning", body=f"## Facts\n\n- {THESIS}\n"
        ),
        "04-learning/german.md": note(
            "german", area="04-learning", body=f"## Facts\n\n- {GERMAN}\n- {GERMAN_OTHER}\n"
        ),
        "03-work-career/job-search.md": note(
            "job-search", area="03-work-career", body=f"## Facts\n\n- {JOBS}\n"
        ),
        "07-home-admin/permit.md": note(
            "permit", area="07-home-admin", aliases=("visa",), body=f"## Facts\n\n- {VISA}\n"
        ),
        "03-work-career/hub-work-career.md": note(
            "hub-work-career", typ="hub", area="03-work-career", body="## Links\n\n"
        ),
    }
    for rel, body in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body, encoding="utf-8")
    return Library(root)


@pytest.fixture
def skills(tmp_path):
    folder = tmp_path / "skills"
    folder.mkdir()
    (folder / "answering.md").write_text("# Lia\n\nAnswer from notes only.\n", encoding="utf-8")
    (folder / "explore.md").write_text("# Look wide\n", encoding="utf-8")
    return folder


class RecordingClient(FakeClient):
    """A FakeClient that also records each call's tool_choice."""

    def __init__(self, replies):
        super().__init__(replies)
        self.choices = []

    def send(self, *, tool_choice=None, **kwargs):
        self.choices.append(tool_choice)
        return super().send(tool_choice=tool_choice, **kwargs)


def plan_call(effort="medium", facets=("learning",), implied=(), subs=("What is stuck?",)):
    args = {"facets": list(facets), "implied": list(implied), "sub_questions": list(subs)}
    return tool_use("plan", {**args, "effort": effort}, "p1")


def coverage_call(grade="covered", verdict="sufficient", call_id="c1"):
    grades = [{"sub_question": "What is stuck?", "grade": grade, "search_terms": ["stalled"]}]
    return tool_use("coverage", {"grades": grades, "verdict": verdict}, call_id)


def answer_with(*facts):
    marks = " ".join(f"[{i}]" for i in range(1, len(facts) + 1))
    notes = "\n".join(f"[{i}] {cited(s, f)}" for i, (s, f) in enumerate(facts, 1))
    return text(f"It stalled {marks}.\n\n{notes}")


def lia(library, skills, client, **switches):
    cfg = explore_config(LiaConfig(today="2030-11-02"), **switches)
    return Lia(client, library, load_skills(skills), cfg)


# ---------------------------------------------------------------- F1 plan


def test_the_plan_comes_first_and_is_written_to_the_trace(library, skills):
    client = RecordingClient(
        [
            [plan_call(facets=("learning",), implied=("work-career",))],
            [tool_use("open_notes", {"slugs": ["thesis"]})],
            [coverage_call()],
            [answer_with(("thesis", THESIS))],
        ]
    )
    result = lia(library, skills, client, siblings=False).ask("Is my thesis moving?")
    assert client.choices[0] == {"type": "tool", "name": "plan"}
    assert result["plan"]["implied"] == ["work-career"] and result["effort"] == "medium"
    assert result["verdict"] == "sufficient" and result["coverage"][0]["corrective_round"] is False
    plan_reply = client.sent[1]["messages"][-1]["content"][0]["content"]
    assert "03-work-career (hub: hub-work-career)" in plan_reply
    assert "04-learning" in plan_reply


def test_implied_areas_map_to_areas_and_hubs(library):
    assert explore.resolve_facets(["work-career", "07", "learning", "nonsense"], library) == [
        ("03-work-career", "hub-work-career"),
        ("07-home-admin", ""),
        ("04-learning", ""),
    ]
    # "visa" names no area, but it is an alias of a note in home-admin: a free hint.
    assert explore.atlas_hints("Does my visa allow it?", library, set()) == [
        ("07-home-admin", "visa")
    ]
    assert explore.atlas_hints("Does my visa allow it?", library, {"07-home-admin"}) == []


# ---------------------------------------------------------------- F2 coverage


@pytest.mark.parametrize("effort, rounds", [("simple", 1), ("medium", 2), ("complex", 3)])
def test_coverage_rounds_respect_the_effort_cap(effort, rounds):
    used, again = 0, True
    while again:
        _, again = explore.coverage_result(
            {"grades": [{"sub_question": "x", "grade": "not_covered"}], "verdict": "partly"},
            effort,
            used,
            enabled=True,
        )
        used += again
    assert used == rounds


def test_a_gap_starts_a_corrective_search_and_switched_off_it_only_records(library, skills):
    reply, again = explore.coverage_result(
        {"grades": [{"sub_question": "x", "grade": "partly"}], "verdict": "partly"},
        "medium",
        0,
        True,
    )
    assert again and "Search now; don't offer" in reply
    reply, again = explore.coverage_result(
        {"grades": [{"sub_question": "x", "grade": "partly"}], "verdict": "partly"},
        "medium",
        0,
        False,
    )
    assert not again and "say exactly what is missing" in reply


def test_an_answer_without_a_verdict_is_sent_back_for_one(library, skills):
    client = RecordingClient(
        [
            [plan_call()],
            [tool_use("open_notes", {"slugs": ["thesis"]})],
            [answer_with(("thesis", THESIS))],  # skipped coverage
            [coverage_call()],
            [answer_with(("thesis", THESIS))],
        ]
    )
    result = lia(library, skills, client, siblings=False).ask("Is my thesis moving?")
    assert explore.COVERAGE_NUDGE in str(client.sent[3]["messages"][-1])
    assert result["verdict"] == "sufficient"


# ---------------------------------------------------------------- F3 siblings


def test_the_sibling_sweep_returns_new_facts_only(library):
    found, phrases = explore.siblings([checks.Citation("thesis", THESIS, True)], library)
    assert found == [("german", GERMAN)]  # not the thesis fact, not German's other fact
    assert "no progress" in phrases
    # A draft quote that is no fact line gives nothing; one that only dropped a tag still counts.
    invented = checks.Citation("thesis", "The thesis made no progress at all", False, "x")
    assert explore.siblings([invented], library) == ([], [])


def test_sibling_facts_go_back_to_lia_once_and_can_be_cited(library, skills):
    client = RecordingClient(
        [
            [plan_call()],
            [tool_use("open_notes", {"slugs": ["thesis"]})],
            [coverage_call()],
            [answer_with(("thesis", THESIS))],
            [answer_with(("thesis", THESIS), ("german", GERMAN))],
        ]
    )
    result = lia(library, skills, client).ask("What am I neglecting?")
    assert result["siblings"]["lines"] == [["german", GERMAN]]
    assert result["citation_check"] == {"total": 2, "failed": 0, "retried": False}


# ---------------------------------------------------------------- F5 capability


def test_write_offers_are_found_and_retried(library, skills):
    assert explore.write_offers("Want me to look at the German side?") == []
    assert explore.write_offers("I can add the dates to the trip note.") == ["I can add"]
    footnote = "\n\n[1] [[x]] «I'll add more later»"
    assert explore.write_offers(f"It stalled [1].{footnote}") == []
    offer = text(f"It stalled [1]. I'll update the note.\n\n[1] {cited('thesis', THESIS)}")
    client = RecordingClient(
        [
            [plan_call()],
            [tool_use("open_notes", {"slugs": ["thesis"]})],
            [coverage_call()],
            [offer],
            [answer_with(("thesis", THESIS))],
        ]
    )
    result = lia(library, skills, client, siblings=False).ask("Is my thesis moving?")
    assert "read-only" in str(client.sent[-1]["messages"][-1])
    assert result["write_offers"] == [] and result["citation_check"]["retried"]


# ---------------------------------------------------------------- F6 upcoming


def test_upcoming_is_deterministic_dated_and_fact_free(library):
    view = upcoming(library.notes, library._text, TODAY)
    assert view == upcoming(library.notes, library._text, TODAY)
    assert view.splitlines()[2:] == [
        "2030-12-01|permit|Permit (valid from)",
        "2031-01|job-search|Job Search (fact)",
        "2031-01-15|permit|Permit (fact)",
    ]  # October 2030 (thesis, German) is past; the fixture's review dates are in March 2030
    for fact in (THESIS, GERMAN, JOBS, VISA):
        assert checks.quote_unit(fact) not in view
    # The recorded date in the source bracket is not an event.
    assert fact_dates("A. (src: self, 2031-01-01)") == []


def test_upcoming_is_loaded_for_complex_or_time_questions_only(library, skills):
    def run(effort, question):
        client = RecordingClient(
            [[plan_call(effort=effort)], [coverage_call()], [text(f"{ABSTAIN} x")],
             [tool_use("search_notes", {"query": "x"}, "s1")], [text(f"{ABSTAIN} x")]]
        )  # fmt: skip
        return lia(library, skills, client).ask(question)["upcoming_loaded"]

    assert run("complex", "What is my whole picture?")
    assert run("simple", "What should I do next week?")
    assert not run("simple", "What did the thesis cover?")


# ---------------------------------------------------------------- switches and F7


def test_all_switches_off_is_the_baseline(library, skills):
    cfg = LiaConfig()
    assert not cfg.exploring
    base = Lia(FakeClient([]), library, load_skills(skills, explore=False), cfg)
    assert [t["name"] for t in base.tools] == ["open_notes", "search_notes"]
    assert "Look wide" not in base.system[0]["text"]
    full = lia(library, skills, FakeClient([]))
    assert [t["name"] for t in full.tools] == ["open_notes", "search_notes", "plan", "coverage"]
    assert "Look wide" in full.system[0]["text"]
    no_plan = lia(library, skills, FakeClient([]), plan=False)
    assert "plan" not in [t["name"] for t in no_plan.tools]


def test_complex_questions_escalate_to_the_bigger_model(library, skills):
    small = RecordingClient([[plan_call(effort="complex")]])
    big = RecordingClient(
        [
            [tool_use("open_notes", {"slugs": ["thesis"]})],
            [coverage_call()],
            [answer_with(("thesis", THESIS))],
        ]
    )
    cfg = explore_config(LiaConfig(today="2030-11-02"), siblings=False)
    result = Lia(small, library, load_skills(skills), cfg, escalate_client=big).ask("All of it?")
    assert result["escalated"] and len(small.sent) == 1 and len(big.sent) == 3
