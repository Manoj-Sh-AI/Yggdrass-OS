"""Lia (D35): one behaviour. Notes as search results, native citations rendered as footnotes, the
cached prefix and skill index, load_skill and the in-turn checklist, the abstain path, the empty
guard, the free checks, effort routing, upcoming, hints, siblings, traces and plumbing."""

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


def cite(text_, index, block, end=None):
    """A text block of Lia's reply that cites search result *index*, blocks [block, end)."""
    return {
        "type": "text",
        "text": text_,
        "citations": [
            {
                "type": "search_result_location",
                "search_result_index": index,
                "start_block_index": block,
                "end_block_index": end if end is not None else block + 1,
                "source": "?",
                "title": "?",
                "cited_text": "?",
            }
        ],
    }


def at(library, slug, line):
    """The block index of *line* in a note's search result."""
    return [b.shown for b in library.blocks(slug)].index(line)


DONE_LINE = text('\n<done verdict="sufficient" checklist="none"/>')


def garden_reply(library, index=0):
    return [
        cite("You set it at three hundred euros.", index, at(library, "garden-plan", GARDEN_FACT)),
        DONE_LINE,
    ]


def abstain(reason="Nothing on ponds."):
    return [text(f"{ABSTAIN} {reason}"), text('\n<done verdict="insufficient" checklist="none"/>')]


def make(library, skills_dir, client, big=None, **cfg):
    playbooks = skills.load_library(skills_dir)
    return Lia(client, library, playbooks, LiaConfig(today="2030-11-02", **cfg), complex_client=big)


def open_(*slugs, call_id="o1"):
    return tool_use("open_notes", {"slugs": list(slugs)}, call_id)


# ---------------------------------------------------------------- notes as search results


def test_a_note_is_one_search_result_with_one_block_per_line(library):
    blocks = library.blocks("garden-plan")
    kinds = {b.kind for b in blocks}
    assert {"field", "fact", "text"} <= kinds
    assert "review: 2030-03-01" in [b.shown for b in blocks]
    assert not any(b.shown.startswith(("id:", "slug:")) for b in blocks)
    content, results, notices = library.open_notes(["garden-plan", "nope"])
    result = content[0]
    assert result["type"] == "search_result" and result["source"] == "garden-plan"
    assert result["title"] == "Garden Plan" and result["citations"] == {"enabled": True}
    assert [c["text"] for c in result["content"]] == [b.shown for b in blocks]
    assert len(content) == 1 and notices == ["nope: no such note (check the shelf map)"]
    assert [s for s, _ in results] == ["garden-plan"]


def test_history_lines_are_marked_and_render_as_history(tmp_path):
    from yggdras.processing.lia.library import note_blocks

    body = (
        "## Facts\n\n- Now it is red. (src: self, 2030-01-01)\n\n"
        "## History\n\n- It was blue. (src: self, 2029-01-01; until: 2030-01-01)\n"
    )
    blocks = note_blocks(note("paint", body=body))
    old = next(b for b in blocks if b.kind == "history")
    assert old.shown.startswith("History: It was blue.")
    assert old.footnote("paint") == "[[paint]] «It was blue» (history)"


def test_search_returns_matching_lines_grouped_by_note(library):
    content, results = library.search_notes("robotics companies")
    assert content[0]["type"] == "search_result" and content[0]["source"] == "job-search"
    assert ROBOTS in [c["text"] for c in content[0]["content"]]
    assert all(c["citations"] == {"enabled": True} for c in content)  # all or none, per request


def test_stemming_and_alias_expansion(library):
    assert search.stem("robotics") == search.stem("robots") == "robot"
    weights = search.expansions("my bank projects", library.notes)
    assert weights["bank"] == 1.0 and weights["werkstudent"] == search.EXPANDED_WEIGHT


def test_the_maps_are_the_atlas_and_shelf_map(library):
    assert set(library.maps()) == {"atlas.md", "shelf-map.md"}


# ---------------------------------------------------------------- rendering native citations


def test_render_puts_markers_after_cited_spans_and_footnotes_from_the_cited_blocks(library):
    _, results, _ = library.open_notes(["garden-plan", "german"])
    exam = at(library, "german", EXAM)
    blocks = [
        cite("You set it at three hundred euros.", 0, at(library, "garden-plan", GARDEN_FACT)),
        text(" "),
        cite("The exam isn't booked yet.", 1, exam),
        text(" Same budget again."),
        cite(" It's still three hundred.", 0, at(library, "garden-plan", GARDEN_FACT)),
        DONE_LINE,
    ]
    answer, footnotes = lia_mod.render(blocks, results)
    assert answer.startswith(
        "You set it at three hundred euros. [1] The exam isn't booked yet. [2]"
    )
    assert "three hundred. [1]" in answer and "<done" not in answer
    assert [(f["n"], f["line"]) for f in footnotes] == [
        (1, "[[garden-plan]] «The garden plan has a budget of three hundred euros»"),
        (2, "[[german]] «The A2 exam is planned for January 2031; it is not booked yet»"),
    ]  # the same line cited twice is one footnote


def test_a_field_citation_renders_as_field_value(library):
    _, results, _ = library.open_notes(["garden-plan"])
    review = at(library, "garden-plan", "review: 2030-03-01")
    answer, _ = lia_mod.render([cite("The review is due in March.", 0, review)], results)
    assert answer.endswith("[1] [[garden-plan]] review: 2030-03-01")


def test_the_done_line_is_parsed_and_removed():
    body, done = lia_mod.parse_done(
        'It holds.\n<done verdict="partly" checklist="bridge 3/4; chain 4/4"/>'
    )
    assert body == "It holds." and done == {
        "verdict": "partly",
        "checklist": "bridge 3/4; chain 4/4",
    }
    assert lia_mod.parse_done("No line.") == ("No line.", None)


# ---------------------------------------------------------------- the cached prefix and skills


def test_prefix_is_fixed_cached_in_two_breakpoints_and_holds_core_and_index(library, skills_dir):
    client = FakeClient([abstain(), abstain()])
    make(library, skills_dir, client).ask("Pond?")
    first, last = client.sent[0], client.sent[-1]
    assert first["system"] == last["system"] and first["tools"] == last["tools"]
    blocks = json.loads(first["system"])
    assert [b.get("cache_control", {}).get("ttl") for b in blocks] == ["1h", "1h"]
    cached = blocks[0]["text"]
    assert "Cite every claim." in cached  # core, always
    assert "<skill-index>" in cached and "bridge | Use it for bridge jobs." in cached
    assert "Steps for bridge." not in cached  # playbooks load on demand only


def test_a_playbook_needs_frontmatter_and_a_checklist(tmp_path):
    bad = tmp_path / "bridge.md"
    bad.write_text(
        "---\nname: bridge\ndescription: Joins.\n---\n\nNo checklist.\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="done_when"):
        skills.parse(bad)
    with pytest.raises(FileNotFoundError, match="core.md"):
        skills.load_library(tmp_path)


def test_load_skill_with_the_first_open_and_the_checklist_ticked_in_the_answer_turn(
    library, skills_dir
):
    first = [tool_use("load_skill", {"names": ["fact-lookup"]}, "s1"), open_("garden-plan")]
    reply = garden_reply(library)[:1] + [
        text('\n<done verdict="sufficient" checklist="fact-lookup 2/2"/>')
    ]
    client = FakeClient([first, reply])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert result["skills_loaded"] == ["fact-lookup"]
    assert result["skill_turns"] == [result["first_open_turn"]] == [1]  # one round trip
    assert (result["verdict"], result["checklist"]) == ("sufficient", "fact-lookup 2/2")
    assert len(client.sent) == 2  # no separate checklist step
    loaded = client.sent[1]["messages"][-1]["content"][0]["content"]
    assert "Steps for fact-lookup." in loaded and "Done when:" in loaded


def test_at_most_two_playbooks(skills_dir):
    lib = skills.load_library(skills_dir)
    text_, done = skills.loaded_text(lib, ["fact-lookup", "bridge", "status-sweep"])
    assert done == ["fact-lookup", "bridge"] and "only the first 2" in text_


# ---------------------------------------------------------------- answers


def test_a_cited_answer_has_its_footnote_and_no_retry(library, skills_dir):
    client = FakeClient([[open_("garden-plan")], garden_reply(library)])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert result["answer_full"] == (
        "You set it at three hundred euros. [1]\n\n"
        "[1] [[garden-plan]] «The garden plan has a budget of three hundred euros»"
    )
    assert (
        result["answer"]
        == "You set it at three hundred euros. [1]\n\n[1] Garden Plan (garden-plan)"
    )
    assert result["citation_check"] == {"total": 1, "failed": 0, "retried": False}
    assert result["effort"] == "simple" and result["model"] == "claude-haiku-5-5"


def test_a_search_result_index_finds_its_note_across_tool_calls(library, skills_dir):
    reply = [cite("Acme Robots is the one you named.", 1, 0), DONE_LINE]
    client = FakeClient(
        [[open_("garden-plan")], [tool_use("search_notes", {"query": "robotics"}, "s1")], reply]
    )
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert "[1] [[job-search]] «Robotics companies fit the thesis topic" in result["answer_full"]


def test_an_abstain_is_searched_by_code_first_and_sent_back_with_the_hits(library, skills_dir):
    hit_reply = [
        cite("You set it at three hundred euros.", 0, 0),
        DONE_LINE,
    ]  # the hit's own result
    client = FakeClient([abstain(), hit_reply])
    result = make(library, skills_dir, client).ask("What is the garden plan budget?")
    assert result["abstain_search"]["hits"][0][0] == "garden-plan"
    sent = client.sent[1]["messages"][-1]["content"]
    assert sent[0]["text"] == lia_mod.ABSTAIN_HITS and sent[1]["type"] == "search_result"
    assert not result["abstain"] and "[[garden-plan]]" in result["answer_full"]


def test_an_abstain_with_no_hits_stands(library, skills_dir):
    client = FakeClient([abstain()])
    result = make(library, skills_dir, client).ask("Pond?")
    assert result["abstain"] and result["abstain_search"]["hits"] == [] and len(client.sent) == 1
    assert is_abstain("Not in your brain. Nothing.")


def test_an_empty_reply_is_asked_for_once_more_then_reported(library, skills_dir):
    client = FakeClient([[open_("garden-plan")], [text("")], garden_reply(library)])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert result["asked_again"] and "three hundred" in result["answer"]
    assert lia_mod.ASK_AGAIN in str(client.sent[-1]["messages"][-1])
    client = FakeClient([[text("")], [text('<done verdict="sufficient" checklist="none"/>')]])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert result["empty_reply"] and result["answer"] == lia_mod.EMPTY_ERROR


def test_search_is_limited_to_three_rounds(library, skills_dir):
    calls = [[tool_use("search_notes", {"query": f"q{i}"}, f"s{i}")] for i in range(4)]
    client = FakeClient([*calls, abstain()])
    result = make(library, skills_dir, client).ask("Pond?")
    assert result["searches"] == 3 and "limit" in json.dumps(result["steps"][-1])


# ---------------------------------------------------------------- the free checks


def test_absence_claims_are_found_and_the_robotics_and_family_cases_caught(library):
    (robots,) = verify.check_absences("Nothing in your notes mentions robotics.", library, set())
    assert robots.hits[0][0] == "job-search"
    (family,) = verify.check_absences(
        "No note mentions Example Builders or a family business.", library, set()
    )
    assert "example-builders" in {s for s, _ in family.hits}
    assert verify.check_absences("Nothing mentions a pond.", library, set()) == []


def test_a_false_absence_is_sent_back_with_citable_hits_then_marked(library, skills_dir):
    claim = [text("Nothing in your notes mentions robotics."), DONE_LINE]
    client = FakeClient([[open_("german")], claim, claim])
    result = make(library, skills_dir, client).ask("Do my notes say anything about robots?")
    sent = client.sent[-1]["messages"][-1]["content"]
    assert "these lines mention it" in sent[0]["text"] and sent[1]["type"] == "search_result"
    assert result["answer"].endswith("[unverified absence]")


def test_claim_support_passes_and_fails(library):
    opened = {s: library.note_text(s) for s in ("german", "bank-role")}
    good = (
        "Your A2 exam is planned for January 2031, and it isn't booked yet [1].\n\n"
        f"[1] {cited('german', checks.quote_unit(EXAM))}"
    )
    assert verify.check_support(good, opened, library.notes) == []
    bad = f"Your exam and visa all fall in January 2031 [1].\n\n[1] {cited('bank-role', HOURS)}"
    (u,) = verify.check_support(bad, opened, library.notes)
    assert set(u.missing) >= {"2031", "january"}


def test_an_unsupported_sentence_is_retried_then_marked(library, skills_dir):
    bad = [cite("It all falls in January 2031.", 0, at(library, "bank-role", HOURS)), DONE_LINE]
    client = FakeClient([[open_("bank-role")], bad, bad])
    result = make(library, skills_dir, client).ask("When is the exam?")
    assert "is not supported by the line it cites" in str(client.sent[-1]["messages"][-1])
    assert "January 2031. [1] [unsupported]" in result["answer"]


def test_no_final_answer_mentions_drafts_or_checks(library, skills_dir):
    leaky = garden_reply(library)[:1] + [
        text(" I've dropped the claim about the pond after re-checking."),
        DONE_LINE,
    ]
    client = FakeClient([[open_("garden-plan")], leaky, leaky])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert verify.leaks(result["answer"]) == [] and "dropped" not in result["answer"]


def test_write_offers_are_retried(library, skills_dir):
    assert verify.write_offers("I can add the dates to the trip note.") == ["I can add"]
    offer = garden_reply(library)[:1] + [text(" I'll update the note."), DONE_LINE]
    client = FakeClient([[open_("garden-plan")], offer, garden_reply(library)])
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
    big = FakeClient([[open_("job-search")], abstain(), abstain()], model="claude-sonnet-5-5")
    result = make(library, skills_dir, small, big=big).ask(
        "What are my realistic options for a family business website?"
    )
    assert result["escalated"] and result["model"] == "claude-sonnet-5-5" and not small.sent
    beside = big.sent[1]["messages"][-1]["content"][-1]
    assert beside["type"] == "text" and "Consider these before answering" in beside["text"]
    assert "example-builders" in result["hints"]


def tool_results(client):
    """Every tool_result block in every request *client* was sent."""
    for request in client.sent:
        for message in request["messages"]:
            if isinstance(message["content"], list):
                for block in message["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        yield block


def test_a_tool_result_never_mixes_search_results_and_text(library, skills_dir):
    """The API rejects a tool result that mixes search_result and text blocks (a 400): hints,
    unknown slugs and the cap go in a text block beside the tool results, in the same message."""
    big = FakeClient(
        [[open_("job-search", "nope", "x1")], abstain(), abstain()], model="claude-sonnet-5-5"
    )
    result = make(library, skills_dir, FakeClient([]), big=big).ask(
        "What are my realistic options for a family business website?"
    )
    seen = list(tool_results(big))
    assert seen
    for block in seen:
        content = block["content"]
        if isinstance(content, list):
            kinds = {b["type"] for b in content}
            assert kinds == {"search_result"} or "search_result" not in kinds, kinds
    message = big.sent[1]["messages"][-1]["content"]
    assert message[0]["type"] == "tool_result" and message[-1]["type"] == "text"
    assert "Consider these before answering" in message[-1]["text"]
    assert "nope: no such note" in message[-1]["text"] and result["hints"]
    # Nothing opened at all: the tool result is text only.
    client = FakeClient([[open_("nope")], abstain(), abstain()])
    make(library, skills_dir, client).ask("Pond?")
    (only,) = tool_results(client)
    assert only["content"] == "nope: no such note (check the shelf map)"


def test_simple_questions_stay_on_the_default_model_without_hints(library, skills_dir):
    small = FakeClient([[open_("german")], abstain(), abstain()])
    big = FakeClient([], model="claude-sonnet-5-5")
    result = make(library, skills_dir, small, big=big).ask("When is the exam?")
    assert not result["escalated"] and not big.sent and result["hints"] == []


def test_the_sibling_sweep_returns_new_facts_as_citable_results_from_medium_up(library, skills_dir):
    found, phrases = search.siblings([checks.Citation("thesis", THESIS, True)], library)
    assert found == [("german", GERMAN)] and "no progress" in phrases
    medium_q = "Which robotics firms suit my job hunt, and what does my Deutsch exam need?"
    first = [cite("Your thesis stalled.", 0, at(library, "thesis", THESIS)), DONE_LINE]
    both = [
        cite("Your thesis stalled.", 0, at(library, "thesis", THESIS)),
        cite(" German too.", 1, 0),
        DONE_LINE,
    ]
    client = FakeClient([[open_("thesis")], first, both])
    result = make(library, skills_dir, client).ask(medium_q)
    assert result["siblings"]["lines"] == [["german", GERMAN]]
    assert "[[german]] «German made no progress in October 2030»" in result["answer_full"]


# ---------------------------------------------------------------- upcoming


def test_upcoming_is_deterministic_dated_and_fact_free(library):
    view = upcoming(library.notes, library._text, dt.date(2030, 11, 2))
    rows = view.splitlines()[2:]
    assert "2030-12-01|permit|Permit (valid from)" in rows
    for fact in (EXAM, VISA, THESIS):
        assert checks.quote_unit(fact) not in view
    assert fact_dates("A. (src: self, 2031-01-01)") == []


def test_upcoming_is_loaded_for_advice_and_timing_questions_only(library, skills_dir):
    def loaded(question):
        client = FakeClient([abstain(), abstain()], model="claude-sonnet-5-5")
        return make(library, skills_dir, client, big=client).ask(question)["upcoming_loaded"]

    assert loaded("Should I book a pond first?") and loaded("What pond is due soon?")
    assert not loaded("What pond does the thesis cover?")


# ---------------------------------------------------------------- traces, voice, context


def test_trace_is_written(library, skills_dir, tmp_path):
    client = FakeClient([[open_("garden-plan")], garden_reply(library)])
    result = make(library, skills_dir, client).ask("What is the garden budget?", qid="q/01")
    path = write_trace(result, tmp_path / "traces")
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "question", "steps", "answer", "citations", "calls", "cost_usd", "latency_ms",
        "effort", "model", "skills_loaded", "verdict", "checklist", "checks", "empty_reply",
    ):  # fmt: skip
        assert key in data
    assert path.name == "q_01.json"


def test_the_voice_check_and_chat_context(library, skills_dir):
    client = FakeClient([[open_("garden-plan")], garden_reply(library)])
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
    client = FakeClient([[open_("garden-plan")], garden_reply(library)])
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
    for name in (
        "load_skills",
        "v4_config",
        "explore_config",
        "MapOptions",
        "mark_unverified",
        "RETRY",
    ):
        assert not hasattr(lia_mod, name)
    for name in ("CHECKLIST_TOOL", "checklist_reply", "CHECKLIST_NUDGE"):
        assert not hasattr(skills, name)
    fields = set(LiaConfig.__dataclass_fields__)
    assert fields == {
        "model", "complex_model", "effort", "owner_names", "today", "horizon_days", "cite_url"
    }  # fmt: skip
    assert [t["name"] for t in lia_mod.TOOLS] == ["open_notes", "search_notes", "load_skill"]
    import yggdras.processing.lia.library as lib_mod

    for name in ("l0_matches", "_neighbours", "links_line", "search_facts"):
        assert not hasattr(lib_mod.Library, name)


# ---------------------------------------------------------------- footnote links, note server


def test_footnotes_link_to_the_note_page_and_the_full_quote_stays_in_the_trace(library, skills_dir):
    url = "http://127.0.0.1:8765/note/{slug}#cite={block}"
    client = FakeClient([[open_("garden-plan")], garden_reply(library)])
    result = make(library, skills_dir, client, cite_url=url).ask("What is the garden budget?")
    block = at(library, "garden-plan", GARDEN_FACT)
    assert result["answer"].endswith(
        f"[1] [Garden Plan](http://127.0.0.1:8765/note/garden-plan#cite={block})"
    )
    assert "«" not in result["answer"]  # no quoted fact text in the chat reply
    assert result["citations"][0]["block"] == block and "«" in result["citations"][0]["line"]


def test_every_failed_support_check_is_marked_and_the_footer_agrees(library, skills_dir):
    from yggdras.interface.mcp_server import footer

    hours = at(library, "bank-role", HOURS)
    bad = [
        cite("It all falls in January 2031.", 0, hours),
        cite("  And  it  is  all  in  March 2031.", 0, hours),  # odd spacing must still be marked
        cite(" Work is 20 h a week.", 0, hours),
        DONE_LINE,
    ]
    client = FakeClient([[open_("bank-role")], bad, bad])
    result = make(library, skills_dir, client).ask("When is the exam?")
    marks = result["answer"].count("[unsupported]")
    assert marks == result["support"]["unsupported"] == 2
    assert result["support"]["checked"] == 3
    assert footer(result).endswith("✓ 1/3")


def test_a_note_already_open_is_never_sent_again(library, skills_dir):
    client = FakeClient(
        [
            [open_("garden-plan")],
            [open_("garden-plan", "german", call_id="o2")],
            garden_reply(library),
        ]
    )
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    second = client.sent[2]["messages"][-1]["content"]
    sent = [b for b in second[0]["content"] if b["type"] == "search_result"]
    assert [b["source"] for b in sent] == ["german"]
    assert "Already open above, not sent again: garden-plan" in second[-1]["text"]
    assert result["reopens_skipped"] == 1


def test_the_runaway_guard_stops_reading_past_a_dollar_and_says_so(library, skills_dir):
    class Pricey(FakeClient):
        def send(self, **kwargs):
            reply = super().send(**kwargs)
            reply.usage.cost_usd = 0.6
            return reply

    searches = [[tool_use("search_notes", {"query": f"q{i}"}, f"s{i}")] for i in range(2)]
    client = Pricey([*searches, garden_reply(library)])
    result = make(library, skills_dir, client).ask("What is the garden budget?")
    assert result["runaway"] and len(client.sent) == 3  # two calls, then one answer, tools off
    assert lia_mod.RUNAWAY_NOTE in str(client.sent[-1]["messages"][-1])


def test_the_two_newest_user_messages_carry_cache_breakpoints():
    messages = [
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": [{"type": "text", "text": "A"}]},
        {"role": "user", "content": [{"type": "text", "text": "R1"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "B"}]},
        {"role": "user", "content": [{"type": "text", "text": "R2"}]},
    ]
    sent = with_cache_tail(messages)
    marked = [i for i, m in enumerate(sent) if isinstance(m["content"], list)
              and m["content"][-1].get("cache_control")]  # fmt: skip
    assert marked == [2, 4]
    assert "cache_control" not in messages[4]["content"][-1]  # the history itself is untouched


def test_five_minute_cache_writes_cost_less_than_one_hour_ones():
    one_hour = cost_of("claude-sonnet-5-5", 0, 1_000_000, 0, 0)
    five_min = cost_of("claude-sonnet-5-5", 0, 1_000_000, 0, 0, write_5m=1_000_000)
    assert one_hour == pytest.approx(4.0) and five_min == pytest.approx(2.5)


def test_the_note_page_highlights_the_cited_line_and_the_server_is_read_only(library):
    import urllib.error
    import urllib.request

    from yggdras.interface import note_server

    server = note_server.start(lambda: library, port=0)
    port = server.server_address[1]
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/note/garden-plan").read().decode()
        block = at(library, "garden-plan", GARDEN_FACT)
        assert f'id="b{block}"' in page and "The garden plan has a budget" in page
        assert "cite=" in page and "#select=garden-plan&amp;center=garden-plan" not in page
        assert "/graph/graph.html#select=garden-plan&center=garden-plan" in page
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/note/nope")
        assert missing.value.code == 404
        post = urllib.request.Request(f"http://127.0.0.1:{port}/note/garden-plan", data=b"x")
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(post)
        assert refused.value.code == 405
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.shutdown()
