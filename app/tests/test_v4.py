"""Lia v4: fact-level search, alias expansion, stemming, hints, absence and support checks,
draft leakage, the effort rule and model routing, retries and the rolling cache. Synthetic notes
that mirror the failures seen on the real brain (no personal data)."""

import pytest

from test_explore import RecordingClient
from test_lia import NODE, cited, note, text, tool_use
from yggdras.processing.lia import explore, search, verify
from yggdras.processing.lia.lia import (
    ABSTAIN,
    Lia,
    LiaConfig,
    load_skills,
    v4_config,
    with_cache_tail,
)
from yggdras.processing.lia.library import Library
from yggdras.processing.lia.models import Budget, BudgetStop, with_retries

TAXONOMY = """# Taxonomy

| Folder | Holds | Not here |
|---|---|---|
| `03-work-career/` | The job search | — |
| `04-learning/` | The thesis, German | — |
| `07-home-admin/` | Residence permit and visa | — |
"""
ROBOTS = (
    "Robotics companies fit the thesis topic; Acme Robots is the one named so far. "
    "(src: self, 2030-11-01)"
)
FAMILY = "Example Builders is the family business, in Springfield. (src: self, 2030-11-01)"
SITE = "The Example Builders website runs on a small web stack. (src: self, 2030-11-01)"
HOURS = "Work is 20 h a week at the bank. (src: self, 2030-11-01)"
EXAM = "The A2 exam is planned for January 2031; it is not booked yet. (src: self, 2030-11-01)"
FREELANCE = "A freelance idea: websites for local businesses. (src: self, 2030-11-01)"


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "brain" / "library"
    files = {
        "00-manual/taxonomy.md": TAXONOMY,
        "00-manual/node.md": NODE,
        "03-work-career/job-search.md": note(
            "job-search",
            area="03-work-career",
            aliases=("job hunt",),
            body=f"## Facts\n\n- {ROBOTS}\n",
        ),
        "03-work-career/bank-role.md": note(
            "bank-role",
            area="03-work-career",
            aliases=("bank job", "Werkstudent"),
            description="Working-student job at Example Bank",
            body=f"## Facts\n\n- {HOURS}\n",
        ),
        "03-work-career/freelance-ideas.md": note(
            "freelance-ideas", area="03-work-career", body=f"## Facts\n\n- {FREELANCE}\n"
        ),
        "03-work-career/example-builders.md": note(
            "example-builders",
            typ="place",
            area="03-work-career",
            description="The family business, a construction company",
            body=f"## Facts\n\n- {FAMILY}\n",
        ),
        "03-work-career/example-builders-website.md": note(
            "example-builders-website",
            area="03-work-career",
            description="Website and digital systems for the family business",
            body=f"## Facts\n\n- {SITE}\n",
        ),
        "04-learning/german.md": note(
            "german", area="04-learning", aliases=("Deutsch",), body=f"## Facts\n\n- {EXAM}\n"
        ),
        "07-home-admin/permit.md": note(
            "permit",
            area="07-home-admin",
            aliases=("visa",),
            body="## Facts\n\n- A permit. (src: self, 2030-11-01)\n",
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
    return folder


def v4(library, skills, client, **switches):
    cfg = v4_config(LiaConfig(today="2030-11-02"), siblings=False, **switches)
    return Lia(client, library, load_skills(skills), cfg)


# ---------------------------------------------------------------- 1a–1c search


def test_the_fact_index_returns_fact_lines_with_their_slugs(library):
    out = library.search_facts("robotics companies")
    first = out.splitlines()[0]
    assert first.startswith("job-search | ") and "Acme Robots is the one named so far" in first
    assert "(src:" not in first


def test_stemming_matches_word_forms():
    assert search.stem("robotics") == search.stem("robots") == search.stem("robot") == "robot"
    assert search.stem("jobs") == "job" and search.stem("studies") == "study"


def test_query_expansion_adds_the_aliases_of_the_notes_a_term_names(library):
    weights = search.expansions("my bank projects", library.notes)
    assert weights["bank"] == 1.0
    assert weights["werkstudent"] == search.EXPANDED_WEIGHT  # an alias of the bank-role note
    german = search.expansions("Deutsch practice", library.notes)
    assert german.get("german") == search.EXPANDED_WEIGHT  # the German/English pairs


def test_hints_come_on_complex_questions_only_and_name_unopened_notes(library, skills):
    question = "What are my realistic options for freelance work with websites for a business?"
    assert explore.effort_of(question, library)[0] == "complex"
    searched_abstain = [
        [text(f"{ABSTAIN} x")],
        [tool_use("search_notes", {"query": "x"}, "s1")],
        [text(f"{ABSTAIN} x")],
    ]
    client = RecordingClient(
        [[tool_use("open_notes", {"slugs": ["freelance-ideas"]})], *searched_abstain]
    )
    result = v4(library, skills, client, absence=False).ask(question)
    hint = client.sent[1]["messages"][-1]["content"][0]["content"]
    assert "Consider these before answering" in hint
    assert "example-builders" in result["hints"] and "freelance-ideas" not in result["hints"]
    simple = RecordingClient([[tool_use("open_notes", {"slugs": ["german"]})], *searched_abstain])
    v4(library, skills, simple, absence=False).ask("When is the exam?")
    assert "Consider these" not in str(simple.sent[1]["messages"][-1])


def test_typed_links_ride_along_on_complex_questions_in_arm_c(library):
    text_, _ = library.open_notes(["german"], links=True)
    assert "--- links of german:" in text_


# ---------------------------------------------------------------- 2a absence


def test_absence_claims_are_found_with_their_topic():
    claims = verify.absence_claims("Nothing in your notes mentions robotics.\n\n[1] [[x]] «y»")
    assert claims == [("Nothing in your notes mentions robotics.", ["robot"])]
    assert verify.absence_claims("You chose AWS [1].") == []


def test_the_robotics_and_family_business_cases_are_caught(library):
    (robots,) = verify.check_absences("Nothing in your notes mentions robotics.", library, set())
    assert robots.hits[0][0] == "job-search"
    (family,) = verify.check_absences(
        "No note mentions Example Builders or a family business.", library, set()
    )
    assert {s for s, _ in family.hits} >= {"example-builders"}
    # A claim the notes don't contradict passes.
    assert verify.check_absences("Nothing mentions a pond.", library, set()) == []


def test_a_false_absence_is_sent_back_then_marked(library, skills):
    claim = text("Nothing in your notes mentions robotics.")
    client = RecordingClient([[tool_use("open_notes", {"slugs": ["german"]})], [claim], [claim]])
    result = v4(library, skills, client).ask("Do my notes say anything about robots?")
    assert "these lines mention it" in str(client.sent[-1]["messages"][-1])
    assert result["answer"].endswith("[unverified absence]")
    assert result["checks"]["first"]["absence_found"] == 1


def test_a_fixed_absence_is_not_marked(library, skills):
    fixed = text(
        f"Acme Robots is the robotics company you named [1].\n\n[1] {cited('job-search', ROBOTS)}"
    )
    client = RecordingClient(
        [
            [tool_use("open_notes", {"slugs": ["job-search"]})],
            [text("Nothing in your notes mentions robotics.")],
            [fixed],
        ]
    )
    result = v4(library, skills, client).ask("Do my notes say anything about robots?")
    assert "[unverified absence]" not in result["answer"]
    assert result["checks"]["absence_left"] == []


# ---------------------------------------------------------------- 2b support


def test_claim_support_passes_and_fails(library):
    opened = {s: library.note_text(s) for s in ("german", "bank-role")}
    good = (
        "Your A2 exam is planned for January 2031, and it isn't booked yet [1].\n\n"
        f"[1] {cited('german', EXAM)}"
    )
    assert verify.check_support(good, opened, library.notes) == []
    # The January/work-hours case: a work-hours line cited for a January claim.
    bad = (
        "Your exam, visa and job search all fall in January 2031 [1].\n\n"
        f"[1] {cited('bank-role', HOURS)}"
    )
    (u,) = verify.check_support(bad, opened, library.notes)
    assert set(u.missing) >= {"2031", "january"}
    # A name may come from the cited note's own name or aliases.
    alias = f"Your Werkstudent job is 20 h a week [1].\n\n[1] {cited('bank-role', HOURS)}"
    assert verify.check_support(alias, opened, library.notes) == []
    # A negation needs a negation in the cited line.
    neg = f"Work is not 20 h a week [1].\n\n[1] {cited('bank-role', HOURS)}"
    assert verify.check_support(neg, opened, library.notes)[0].missing == ["<negation>"]


def test_an_unsupported_sentence_is_retried_then_marked(library, skills):
    bad = text(f"It all falls in January 2031 [1].\n\n[1] {cited('bank-role', HOURS)}")
    client = RecordingClient([[tool_use("open_notes", {"slugs": ["bank-role"]})], [bad], [bad]])
    result = v4(library, skills, client).ask("When is the exam?")
    assert "is not supported by the line it cites" in str(client.sent[-1]["messages"][-1])
    assert "January 2031 [1]. [unsupported]" in result["answer"]


# ---------------------------------------------------------------- 2c leakage


def test_no_final_answer_mentions_drafts_or_checks(library, skills):
    leaky = text(
        "Your exam is in January 2031 [1]. "
        "I've dropped the claim about the visa after re-checking."
        f"\n\n[1] {cited('german', EXAM)}"
    )
    client = RecordingClient([[tool_use("open_notes", {"slugs": ["german"]})], [leaky], [leaky]])
    result = v4(library, skills, client).ask("When is the exam?")
    assert verify.leaks(result["answer"]) == []
    assert "dropped" not in result["answer"] and "January 2031 [1]." in result["answer"]
    assert "Never mention drafts" in str(client.sent[-1]["messages"][-1])


# ---------------------------------------------------------------- effort rule and routing


@pytest.mark.parametrize(
    "question, level",
    [
        ("When is the exam?", "simple"),
        ("Should I book the exam or the visa first?", "complex"),
        ("How does my job hunt connect to German and my visa?", "complex"),
        ("Which robotics firms suit my job hunt, and what does my Deutsch exam need?", "medium"),
    ],
)
def test_the_effort_rule(library, question, level):
    assert explore.effort_of(question, library)[0] == level


def test_complex_questions_go_to_the_complex_model_and_simple_ones_stay(library, skills):
    small = RecordingClient(
        [[text(f"{ABSTAIN} x")], [tool_use("search_notes", {"query": "x"})], [text(f"{ABSTAIN} x")]]
    )
    big = RecordingClient([])
    cfg = v4_config(LiaConfig(today="2030-11-02"), escalate="claude-sonnet-5-5")
    lia = Lia(small, library, load_skills(skills), cfg, escalate_client=big)
    assert not lia.ask("When is the exam?")["escalated"] and not big.sent
    big.replies = [
        [text(f"{ABSTAIN} x")],
        [tool_use("search_notes", {"query": "x"})],
        [text(f"{ABSTAIN} x")],
    ]
    small.sent.clear()
    result = lia.ask("Should I book the exam or the visa first?")
    assert result["escalated"] and big.sent and not small.sent


# ---------------------------------------------------------------- plumbing


def test_the_rolling_cache_marks_only_the_newest_user_block():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "Q"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "A"}]},
        {"role": "user", "content": "Again"},
    ]
    sent = with_cache_tail(messages)
    assert sent[-1]["content"] == [
        {"type": "text", "text": "Again", "cache_control": {"type": "ephemeral"}}
    ]
    assert "cache_control" not in sent[0]["content"][0] and messages[-1]["content"] == "Again"


def test_retry_with_backoff_tries_three_times_then_raises():
    class Flaky(Exception):
        pass

    calls, waits = [], []

    def call():
        calls.append(1)
        if len(calls) < 3:
            raise Flaky()
        return "ok"

    assert with_retries(call, (Flaky,), sleep=waits.append) == "ok"
    assert len(calls) == 3 and waits == [2.0, 6.0]
    calls.clear()
    with pytest.raises(Flaky):
        with_retries(
            lambda: (calls.append(1), (_ for _ in ()).throw(Flaky()))[1],
            (Flaky,),
            sleep=lambda s: None,
        )
    assert len(calls) == 3
    with pytest.raises(ValueError):  # not transient: no retry
        with_retries(lambda: (_ for _ in ()).throw(ValueError()), (Flaky,), sleep=lambda s: None)


def test_the_budget_stops_at_its_line():
    budget = Budget(stop_at=10.0)
    budget.add(9.99)
    budget.check()
    budget.add(0.02)
    with pytest.raises(BudgetStop):
        budget.check()
