"""Lia (D35): one behaviour. Tools, the cached prefix and its skill index, load_skill and the
checklist, citations and the free checks, effort routing, upcoming, hints, siblings, traces,
the budget, retries, and nothing written to the brain. Synthetic notes only."""

import datetime as dt
import hashlib
import json

import pytest

from yggdras.data.maps import checks
from yggdras.data.maps.upcoming import fact_dates, upcoming
from yggdras.processing.lia import effort, search, skills, verify
from yggdras.processing.lia import lia as lia_mod
from yggdras.processing.lia.lia import (
    ABSTAIN,
    Lia,
    LiaConfig,
    default_lia,
    is_abstain,
    with_cache_tail,
    write_trace,
)
from yggdras.processing.lia.library import Library
from yggdras.processing.lia.models import Budget, BudgetStop, Reply, Usage, cost_of, with_retries

TAXONOMY = """# Taxonomy

| Folder | Holds | Not here |
|---|---|---|
| `03-work-career/` | The job search | — |
| `04-learning/` | The thesis, German | — |
| `07-home-admin/` | Residence permit and visa | — |
| `08-rest-joy/` | Hobbies | — |
| `06-purpose/` | Values | — |
"""
NODE = "# Node template\n\nFacts are one per line.\n"


def note(slug, *, typ="project", area="08-rest-joy", description=None, aliases=(), body=""):
    alias_list = ", ".join(f'"{a}"' for a in aliases)
    return (
        f"---\nid: id-{slug}\nslug: {slug}\nname: {slug.replace('-', ' ').title()}\n"
        f'type: {typ}\narea: {area}\ndescription: "{description or "About " + slug}"\n'
        f"aliases: [{alias_list}]\nupdated: 2030-01-02\nreview: 2030-03-01\n---\n\n"
        f"# {slug}\n\n{body}"
    )


CORNER = "Home goals include a quiet garden corner. (src: self, 2030-01-01)"
GARDEN_FACT = "The garden plan has a budget of three hundred euros. (src: self, 2030-01-01)"
ROBOTS = (
    "Robotics companies fit the thesis topic; Acme Robots is the one named so far. "
    "(src: self, 2030-11-01)"
)
FAMILY = "Example Builders is the family business, in Springfield. (src: self, 2030-11-01)"
HOURS = "Work is 20 h a week at the bank. (src: self, 2030-11-01)"
EXAM = "The A2 exam is planned for January 2031; it is not booked yet. (src: self, 2030-11-01)"
THESIS = "The thesis made no progress in October 2030. (src: self, 2030-11-01)"
GERMAN = "German made no progress in October 2030. (src: self, 2030-11-01)"
VISA = "The permit runs until 2031-01-15. (src: self, 2030-11-01; valid: 2030-12-01..)"


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "brain" / "library"
    files = {
        "00-manual/taxonomy.md": TAXONOMY,
        "00-manual/node.md": NODE,
        "08-rest-joy/garden-plan.md": note(
            "garden-plan",
            aliases=("allotment plan",),
            body=f"## Facts\n\n- {GARDEN_FACT}\n\n## Links\n\n- advances [[home-goals]]\n",
        ),
        "06-purpose/home-goals.md": note(
            "home-goals",
            typ="goal",
            area="06-purpose",
            aliases=("home",),
            body=f"## Facts\n\n- {CORNER}\n",
        ),
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
        "03-work-career/example-builders.md": note(
            "example-builders",
            typ="place",
            area="03-work-career",
            description="The family business, a construction company",
            body=f"## Facts\n\n- {FAMILY}\n",
        ),
        "04-learning/german.md": note(
            "german",
            area="04-learning",
            aliases=("Deutsch",),
            body=f"## Facts\n\n- {EXAM}\n- {GERMAN}\n",
        ),
        "04-learning/thesis.md": note(
            "thesis", area="04-learning", body=f"## Facts\n\n- {THESIS}\n"
        ),
        "07-home-admin/permit.md": note(
            "permit", area="07-home-admin", aliases=("visa",), body=f"## Facts\n\n- {VISA}\n"
        ),
    }
    for rel, body in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body, encoding="utf-8")
    return Library(root)


CORE = "---\nname: core\ndescription: Always loaded.\n---\n\n# Core\n\nCite every claim.\n"


def playbook(name, items=("I did the first thing.", "I did the second thing.")):
    done = "\n".join(f"  - {i}" for i in items)
    return (
        f"---\nname: {name}\ndescription: Use it for {name} jobs.\ndone_when:\n{done}\n---\n\n"
        f"# {name}\n\nSteps for {name}.\n"
    )


@pytest.fixture
def skills_dir(tmp_path):
    folder = tmp_path / "skills" / "lia"
    (folder / "library").mkdir(parents=True)
    (folder / "core.md").write_text(CORE, encoding="utf-8")
    for name in ("fact-lookup", "bridge", "status-sweep"):
        (folder / "library" / f"{name}.md").write_text(playbook(name), encoding="utf-8")
    return folder


def tool_use(name, args, call_id="t1"):
    return {"type": "tool_use", "id": call_id, "name": name, "input": args}


def text(value):
    return {"type": "text", "text": value}


class FakeClient:
    """Plays scripted replies and records what it was sent."""

    def __init__(self, replies, model="claude-haiku-5-5"):
        self.replies, self.sent, self.model = list(replies), [], model

    def send(self, *, system, tools, messages, max_tokens=4096, tool_choice=None):
        self.sent.append(
            {
                "system": json.dumps(system),
                "tools": json.dumps(tools),
                "messages": json.loads(json.dumps(messages, default=str)),
            }
        )
        blocks = self.replies.pop(0)
        stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
        return Reply(blocks, stop, Usage(self.model, 100, 0, 1000, 50, 0.001, 5.0))


# What the fake model says after the abstain rule sends it back: one search, then abstain.
SEARCHED_ABSTAIN = [
    [{"type": "tool_use", "id": "sx", "name": "search_notes", "input": {"query": "pond"}}],
    [{"type": "text", "text": "Not in your brain. No note mentions it."}],
]


def cited(slug, line):
    return f"[[{slug}]] «{line}»"


def footnoted(*facts, claim="It holds"):
    marks = " ".join(f"[{i}]" for i in range(1, len(facts) + 1))
    notes = "\n".join(f"[{i}] {cited(s, f)}" for i, (s, f) in enumerate(facts, 1))
    return text(f"{claim} {marks}.\n\n{notes}")


GARDEN = footnoted(("garden-plan", GARDEN_FACT), claim="You set it at three hundred euros")


def make(library, skills_dir, client, big=None, **cfg):
    playbooks = skills.load_library(skills_dir)
    return Lia(client, library, playbooks, LiaConfig(today="2030-11-02", **cfg), complex_client=big)


# ---------------------------------------------------------------- tools


def test_open_notes_returns_full_text_and_reports_unknown_slugs(library):
    out, opened = library.open_notes(["garden-plan", "nope"])
    assert opened == ["garden-plan"]
    assert GARDEN_FACT in out and "nope: no such note" in out


def test_open_notes_caps_at_ten(library):
    out, opened = library.open_notes(["garden-plan"] + [f"x{i}" for i in range(12)])
    assert "only the first 10" in out


def test_search_returns_fact_lines_with_their_slugs(library):
    first = library.search_notes("robotics companies").splitlines()[0]
    assert first.startswith("job-search | ") and "Acme Robots is the one named so far" in first
    assert "(src:" not in first


def test_stemming_and_alias_expansion():
    assert search.stem("robotics") == search.stem("robots") == "robot"
    assert search.stem("jobs") == "job" and search.stem("studies") == "study"


def test_query_expansion_adds_the_aliases_of_the_notes_a_term_names(library):
    weights = search.expansions("my bank projects", library.notes)
    assert weights["bank"] == 1.0 and weights["werkstudent"] == search.EXPANDED_WEIGHT
    assert (
        search.expansions("Deutsch practice", library.notes).get("german") == search.EXPANDED_WEIGHT
    )


def test_the_maps_are_the_atlas_and_shelf_map_with_short_descriptions(library):
    maps = library.maps()
    assert set(maps) == {"atlas.md", "shelf-map.md"}
    assert "garden-plan|" in maps["shelf-map.md"]


# ---------------------------------------------------------------- the cached prefix and skills


def test_prefix_is_fixed_cached_in_two_breakpoints_and_holds_core_and_index(library, skills_dir):
    client = FakeClient([[text(f"{ABSTAIN} x")], *SEARCHED_ABSTAIN, [text(f"{ABSTAIN} x")]])
    lia = make(library, skills_dir, client)
    lia.ask("Pond?")
    first, last = client.sent[0], client.sent[-1]
    assert first["system"] == last["system"] and first["tools"] == last["tools"]
    blocks = json.loads(first["system"])
    assert [b.get("cache_control", {}).get("ttl") for b in blocks] == ["1h", "1h"]
    cached = blocks[0]["text"]
    assert "Cite every claim." in cached  # core, always
    assert "<skill-index>" in cached and "bridge | Use it for bridge jobs." in cached
    assert "Steps for bridge." not in cached  # playbooks load on demand only
    assert "<atlas.md>" in blocks[1]["text"] and "<shelf-map.md>" in blocks[1]["text"]


def test_a_playbook_needs_frontmatter_and_a_checklist(tmp_path):
    bad = tmp_path / "bridge.md"
    bad.write_text(
        "---\nname: bridge\ndescription: Joins.\n---\n\nNo checklist.\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="done_when"):
        skills.parse(bad)
    with pytest.raises(FileNotFoundError, match="core.md"):
        skills.load_library(tmp_path)


def test_load_skill_with_the_first_open_and_the_checklist_in_the_trace(library, skills_dir):
    first = [
        tool_use("load_skill", {"names": ["fact-lookup"]}, "s1"),
        tool_use("open_notes", {"slugs": ["garden-plan"]}, "o1"),
    ]
    report = tool_use(
        "checklist",
        {"items": [{"skill": "fact-lookup", "item": f"i{i}", "done": True} for i in range(2)]},
        "k1",
    )
    client = FakeClient([first, [report], [GARDEN]])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert result["skills_loaded"] == ["fact-lookup"]
    assert result["skill_turns"] == [result["first_open_turn"]] == [1]  # one round trip
    assert result["checklist_complete"] is True and len(result["checklists"]) == 1
    loaded = client.sent[1]["messages"][-1]["content"][0]["content"]
    assert "Steps for fact-lookup." in loaded and "Done when:" in loaded


def test_at_most_two_playbooks(library, skills_dir):
    lib = skills.load_library(skills_dir)
    text_, done = skills.loaded_text(lib, ["fact-lookup", "bridge", "status-sweep"])
    assert done == ["fact-lookup", "bridge"] and "only the first 2" in text_


def test_an_answer_without_the_checklist_is_sent_back(library, skills_dir):
    client = FakeClient(
        [
            [
                tool_use("load_skill", {"names": ["bridge"]}, "s1"),
                tool_use("open_notes", {"slugs": ["garden-plan"]}, "o1"),
            ],
            [GARDEN],  # skipped the checklist
            [
                tool_use(
                    "checklist", {"items": [{"skill": "bridge", "item": "x", "done": False}]}, "k1"
                )
            ],
            [
                tool_use(
                    "checklist",
                    {
                        "items": [
                            {"skill": "bridge", "item": f"i{i}", "done": True} for i in range(2)
                        ]
                    },
                    "k2",
                )
            ],
            [GARDEN],
        ]
    )
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert skills.CHECKLIST_NUDGE in str(client.sent[2]["messages"][-1])
    assert "Finish these first" in str(client.sent[3]["messages"][-1])
    assert result["checklist_complete"] is True


# ---------------------------------------------------------------- citations and abstaining


def test_footnoted_citations_pass(library, skills_dir):
    client = FakeClient([[tool_use("open_notes", {"slugs": ["garden-plan"]})], [GARDEN]])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert result["citation_check"] == {"total": 1, "failed": 0, "retried": False}
    assert result["effort"] == "simple" and result["model"] == "claude-haiku-5-5"


def test_a_failing_citation_is_retried_then_marked_unverified(library, skills_dir):
    bad = footnoted(("garden-plan", "The garden plan has a budget of four hundred euros."))
    client = FakeClient([[tool_use("open_notes", {"slugs": ["garden-plan"]})], [bad], [bad]])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert result["citation_check"] == {"total": 1, "failed": 1, "retried": True}
    assert "[unverified]" in result["answer"]
    assert lia_mod.FRESH in str(client.sent[-1]["messages"][-1])


def test_citing_an_unopened_note_fails(library, skills_dir):
    client = FakeClient([[GARDEN], [GARDEN]])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert result["citations"][0]["reason"] == "note was not opened for this question"


def test_abstain_is_sent_to_search_first_and_the_old_line_still_counts(library, skills_dir):
    client = FakeClient(
        [[text(f"{ABSTAIN} None of your notes mention a pond.")], *SEARCHED_ABSTAIN]
    )
    result = make(library, skills_dir, client).ask("Pond?")
    assert result["abstain"] and result["abstain_search"] and result["searches"] == 1
    assert is_abstain("Not in your brain. Nothing.")


def test_search_is_limited_to_three_rounds(library, skills_dir):
    calls = [[tool_use("search_notes", {"query": f"q{i}"}, f"s{i}")] for i in range(4)]
    client = FakeClient([*calls, [text(f"{ABSTAIN} Nothing found.")]])
    result = make(library, skills_dir, client).ask("Pond?")
    assert result["searches"] == 3 and "limit" in json.dumps(result["steps"][-1])


# ---------------------------------------------------------------- the free checks


def test_absence_claims_are_found_and_the_robotics_and_family_cases_caught(library):
    assert verify.absence_claims("Nothing in your notes mentions robotics.") == [
        ("Nothing in your notes mentions robotics.", ["robot"])
    ]
    (robots,) = verify.check_absences("Nothing in your notes mentions robotics.", library, set())
    assert robots.hits[0][0] == "job-search"
    (family,) = verify.check_absences(
        "No note mentions Example Builders or a family business.", library, set()
    )
    assert "example-builders" in {s for s, _ in family.hits}
    assert verify.check_absences("Nothing mentions a pond.", library, set()) == []


def test_a_false_absence_is_sent_back_then_marked(library, skills_dir):
    claim = text("Nothing in your notes mentions robotics.")
    client = FakeClient([[tool_use("open_notes", {"slugs": ["german"]})], [claim], [claim]])
    result = make(library, skills_dir, client).ask("Do my notes say anything about robots?")
    assert "these lines mention it" in str(client.sent[-1]["messages"][-1])
    assert result["answer"].endswith("[unverified absence]")


def test_claim_support_passes_and_fails(library):
    opened = {s: library.note_text(s) for s in ("german", "bank-role")}
    good = (
        "Your A2 exam is planned for January 2031, and it isn't booked yet [1].\n\n"
        f"[1] {cited('german', EXAM)}"
    )
    assert verify.check_support(good, opened, library.notes) == []
    bad = f"Your exam and visa all fall in January 2031 [1].\n\n[1] {cited('bank-role', HOURS)}"
    (u,) = verify.check_support(bad, opened, library.notes)
    assert set(u.missing) >= {"2031", "january"}
    alias = f"Your Werkstudent job is 20 h a week [1].\n\n[1] {cited('bank-role', HOURS)}"
    assert verify.check_support(alias, opened, library.notes) == []


def test_an_unsupported_sentence_is_retried_then_marked(library, skills_dir):
    bad = text(f"It all falls in January 2031 [1].\n\n[1] {cited('bank-role', HOURS)}")
    client = FakeClient([[tool_use("open_notes", {"slugs": ["bank-role"]})], [bad], [bad]])
    result = make(library, skills_dir, client).ask("When is the exam?")
    assert "January 2031 [1]. [unsupported]" in result["answer"]


def test_no_final_answer_mentions_drafts_or_checks(library, skills_dir):
    leaky = text(
        "You set it at three hundred euros [1]. I've dropped the claim about the pond after "
        f"re-checking.\n\n[1] {cited('garden-plan', GARDEN_FACT)}"
    )
    client = FakeClient([[tool_use("open_notes", {"slugs": ["garden-plan"]})], [leaky], [leaky]])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert verify.leaks(result["answer"]) == [] and "dropped" not in result["answer"]


def test_write_offers_are_retried(library, skills_dir):
    assert verify.write_offers("Want me to look at the German side?") == []
    assert verify.write_offers("I can add the dates to the trip note.") == ["I can add"]
    offer = text(
        "You set it at three hundred euros [1]. I'll update the note.\n\n"
        f"[1] {cited('garden-plan', GARDEN_FACT)}"
    )
    client = FakeClient([[tool_use("open_notes", {"slugs": ["garden-plan"]})], [offer], [GARDEN]])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert "read-only" in str(client.sent[-1]["messages"][-1]) and result["write_offers"] == []


# ---------------------------------------------------------------- effort, routing, hints, siblings


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
    assert effort.effort_of(question, library)[0] == level


def test_complex_questions_go_to_the_complex_model_and_get_hints(library, skills_dir):
    small = FakeClient([])
    big = FakeClient(
        [
            [tool_use("open_notes", {"slugs": ["job-search"]})],
            [text(f"{ABSTAIN} x")],
            *SEARCHED_ABSTAIN,
        ],
        model="claude-sonnet-5-5",
    )
    result = make(library, skills_dir, small, big=big).ask(
        "What are my realistic options for a family business website?"
    )
    assert result["escalated"] and result["model"] == "claude-sonnet-5-5" and not small.sent
    hint = big.sent[1]["messages"][-1]["content"][0]["content"]
    assert "Consider these before answering" in hint and "example-builders" in result["hints"]


def test_simple_questions_stay_on_the_default_model_without_hints(library, skills_dir):
    small = FakeClient(
        [[tool_use("open_notes", {"slugs": ["german"]})], [text(f"{ABSTAIN} x")], *SEARCHED_ABSTAIN]
    )
    big = FakeClient([], model="claude-sonnet-5-5")
    result = make(library, skills_dir, small, big=big).ask("When is the exam?")
    assert not result["escalated"] and not big.sent and result["hints"] == []


def test_the_sibling_sweep_returns_new_facts_only_and_runs_from_medium(library, skills_dir):
    found, phrases = search.siblings([checks.Citation("thesis", THESIS, True)], library)
    assert found == [("german", GERMAN)] and "no progress" in phrases
    medium_q = "Which robotics firms suit my job hunt, and what does my Deutsch exam need?"
    first = footnoted(("thesis", THESIS), claim="Your thesis stalled")
    both = footnoted(("thesis", THESIS), ("german", GERMAN), claim="Your thesis and German stalled")
    client = FakeClient([[tool_use("open_notes", {"slugs": ["thesis"]})], [first], [both]])
    result = make(library, skills_dir, client).ask(medium_q)
    assert result["siblings"]["lines"] == [["german", GERMAN]]
    assert result["citation_check"]["failed"] == 0


# ---------------------------------------------------------------- upcoming


def test_upcoming_is_deterministic_dated_and_fact_free(library):
    view = upcoming(library.notes, library._text, dt.date(2030, 11, 2))
    rows = view.splitlines()[2:]
    assert (
        "2030-12-01|permit|Permit (valid from)" in rows
        and "2031-01-15|permit|Permit (fact)" in rows
    )
    assert not any("thesis" in r for r in rows)  # October 2030 is past
    for fact in (EXAM, VISA, THESIS):
        assert checks.quote_unit(fact) not in view
    assert fact_dates("A. (src: self, 2031-01-01)") == []


def test_upcoming_is_loaded_for_advice_and_timing_questions_only(library, skills_dir):
    def loaded(question):
        client = FakeClient([[text(f"{ABSTAIN} x")], *SEARCHED_ABSTAIN], model="claude-sonnet-5-5")
        return make(library, skills_dir, client, big=client).ask(question)["upcoming_loaded"]

    assert loaded("Should I book the exam first?") and loaded("What is due soon?")
    assert not loaded("What does the thesis cover?")


# ---------------------------------------------------------------- traces, voice, context


def test_trace_is_written(library, skills_dir, tmp_path):
    client = FakeClient([[tool_use("open_notes", {"slugs": ["garden-plan"]})], [GARDEN]])
    result = make(library, skills_dir, client).ask("What is the garden budget?", qid="q/01")
    path = write_trace(result, tmp_path / "traces")
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "question",
        "steps",
        "answer",
        "citations",
        "citation_check",
        "calls",
        "cost_usd",
        "latency_ms",
        "effort",
        "model",
        "skills_loaded",
        "checklists",
        "checks",
    ):
        assert key in data
    assert path.name == "q_01.json"


def test_the_voice_check_and_chat_context(library, skills_dir):
    client = FakeClient([[tool_use("open_notes", {"slugs": ["garden-plan"]})], [GARDEN]])
    result = make(library, skills_dir, client, owner_names=("Manoj",)).ask(
        "And the budget?", context="me: Tell me about the garden plan."
    )
    assert result["third_person"] == []
    first = client.sent[0]["messages"][0]["content"]
    assert "me: Tell me about the garden plan." in first[0]["text"]
    assert first[-1]["text"] == "Question: And the budget?"


def test_nothing_is_written_to_the_brain(library, skills_dir):
    root = library.root

    def tree():
        return {
            p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()
        }

    before = tree()
    client = FakeClient([[tool_use("open_notes", {"slugs": ["garden-plan"]})], [GARDEN]])
    make(library, skills_dir, client).ask("What is the garden budget?")
    assert tree() == before


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
    assert messages[-1]["content"] == "Again"


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
    assert waits == [2.0, 6.0]
    with pytest.raises(ValueError):  # not transient: no retry
        with_retries(lambda: (_ for _ in ()).throw(ValueError()), (Flaky,), sleep=lambda s: None)


def test_budget_stops_at_the_line_and_cost_uses_cache_rates():
    budget = Budget(stop_at=1.0)
    budget.add(0.99)
    budget.check()
    budget.add(0.02)
    with pytest.raises(BudgetStop):
        budget.check()
    assert cost_of("claude-haiku-5-5", 0, 0, 1_000_000, 0) == pytest.approx(0.01)


def test_default_lia_builds_both_models_from_the_skill_library(library, skills_dir):
    made = []

    def factory(model):
        made.append(model)
        return FakeClient([], model=model)

    lia = default_lia(library, skills_dir, factory)
    assert made == ["claude-haiku-5-5", "claude-sonnet-5-5"] and "core" in lia.playbooks


def test_no_removed_code_paths_are_left():
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("yggdras.processing.lia.explore")
    for name in ("load_skills", "v4_config", "explore_config", "MapOptions"):
        assert not hasattr(lia_mod, name)
    fields = set(LiaConfig.__dataclass_fields__)
    assert fields == {"model", "complex_model", "effort", "owner_names", "today", "horizon_days"}
    assert [t["name"] for t in lia_mod.TOOLS] == [
        "open_notes",
        "search_notes",
        "load_skill",
        "checklist",
    ]
    import yggdras.processing.lia.library as lib_mod

    for name in ("l0_matches", "_neighbours", "links_line", "search_facts"):
        assert not hasattr(lib_mod.Library, name)
