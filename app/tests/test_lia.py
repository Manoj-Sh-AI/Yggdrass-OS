"""Lia's read side: tools, cache order, citation check and retry, abstain, switches, traces."""

import hashlib
import json

import pytest

from yggdras.processing.lia.lia import (
    ABSTAIN,
    TOOLS,
    Lia,
    LiaConfig,
    is_abstain,
    load_skills,
    write_trace,
)
from yggdras.processing.lia.library import Library, MapOptions
from yggdras.processing.lia.models import Budget, BudgetStop, Reply, Usage, cost_of

TAXONOMY = """# Taxonomy

| Folder | Holds | Not here |
|---|---|---|
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
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return Library(root)


@pytest.fixture
def skills(tmp_path):
    folder = tmp_path / "skills"
    folder.mkdir()
    (folder / "answering.md").write_text("# Lia\n\nAnswer from notes only.\n", encoding="utf-8")
    return load_skills(folder)


def tool_use(name, args, call_id="t1"):
    return {"type": "tool_use", "id": call_id, "name": name, "input": args}


def text(value):
    return {"type": "text", "text": value}


class FakeClient:
    """Plays scripted replies and records what it was sent."""

    model = "claude-haiku-5-5"

    def __init__(self, replies):
        self.replies, self.sent = list(replies), []

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


# ---------------------------------------------------------------- tools


def test_open_notes_returns_full_text_and_reports_unknown_slugs(library):
    out, opened = library.open_notes(["garden-plan", "nope"])
    assert opened == ["garden-plan"]
    assert GARDEN_FACT in out and "nope: no such note" in out
    assert "neighbours" not in out


def test_open_notes_caps_at_ten(library):
    out, opened = library.open_notes([f"x{i}" for i in range(12)])
    assert "only the first 10 slugs" in out


def test_neighbour_descriptions_behind_the_switch_and_no_facts(library):
    out, _ = library.open_notes(["garden-plan"], neighbours=True)
    block = out.split("--- neighbours of garden-plan")[1]
    assert "advances home-goals | goal | About home-goals" in block
    assert "quiet garden corner" not in block  # descriptions only, never facts


def test_search_ranks_and_snippets(library):
    out = library.search_notes("budget euros", k=5).splitlines()
    assert out[0].startswith("garden-plan |") and "three hundred euros" in out[0]
    assert library.search_notes("zebra") == "No matches."


def test_l0_matches_unique_names_and_skips_the_stoplist(library):
    assert library.l0_matches("How big is the allotment plan?") == ["garden-plan"]
    assert library.l0_matches("What about home?") == []  # "home" is on the stoplist


def test_map_variants(library):
    default = library.maps()
    assert set(default) == {"atlas.md", "shelf-map.md", "relationship-map.md"}
    assert "advanced_by garden-plan" in default["relationship-map.md"]
    assert "relationship-map.md" not in library.maps(MapOptions(relationship=False))
    outgoing = library.maps(MapOptions(inverses=False))["relationship-map.md"]
    assert "advances home-goals" in outgoing and "advanced_by" not in outgoing
    assert json.loads(library.maps(MapOptions(format="json"))["shelf-map.json"])[0]["slug"]
    assert " has type " in library.maps(MapOptions(format="prose"))["shelf-map.md"]
    short = library.maps(MapOptions(about_words=1))["shelf-map.md"]
    assert "|About|" in short and "|About garden-plan|" not in short


# ---------------------------------------------------------------- the loop


def test_prompt_prefix_is_fixed_and_cached_in_two_breakpoints(library, skills):
    answer = text(f"Three hundred euros. {cited('garden-plan', GARDEN_FACT)}")
    client = FakeClient(
        [
            [tool_use("open_notes", {"slugs": ["garden-plan"]})],
            [answer],
            [tool_use("open_notes", {"slugs": ["garden-plan"]})],
            [answer],
        ]
    )
    lia = Lia(client, library, skills, LiaConfig())
    lia.ask("Budget?", "a")
    lia.ask("Budget again?", "b")
    assert len({c["system"] for c in client.sent}) == 1  # identical prefix on every call
    assert len({c["tools"] for c in client.sent}) == 1
    system = json.loads(client.sent[0]["system"])
    assert [b["cache_control"] for b in system] == [{"type": "ephemeral", "ttl": "1h"}] * 2
    assert system[0]["text"].startswith("# Lia") and "# Taxonomy" in system[0]["text"]
    assert system[1]["text"].index("<atlas.md>") < system[1]["text"].index("<shelf-map.md>")
    assert system[1]["text"].index("<shelf-map.md>") < system[1]["text"].index(
        "<relationship-map.md>"
    )
    assert [t["name"] for t in TOOLS] == ["open_notes", "search_notes"]


def test_citations_pass(library, skills):
    client = FakeClient(
        [
            [tool_use("open_notes", {"slugs": ["garden-plan"]})],
            [text(f"Three hundred. {cited('garden-plan', GARDEN_FACT)}")],
        ]
    )
    result = Lia(client, library, skills, LiaConfig()).ask("Budget?")
    assert result["citation_check"] == {"total": 1, "failed": 0, "retried": False}
    assert result["opened"] == ["garden-plan"] and len(client.sent) == 2


def test_failed_citation_is_retried_once_then_fixed(library, skills):
    client = FakeClient(
        [
            [tool_use("open_notes", {"slugs": ["garden-plan"]})],
            [text(f"About 300. {cited('garden-plan', 'The budget is 300.')}")],
            [text(f"Three hundred. {cited('garden-plan', GARDEN_FACT)}")],
        ]
    )
    result = Lia(client, library, skills, LiaConfig()).ask("Budget?")
    assert result["citation_check"] == {"total": 1, "failed": 0, "retried": True}
    assert "failed the check" in json.dumps(client.sent[-1]["messages"][-1])
    assert "[unverified]" not in result["answer"]


def test_still_failing_citation_is_marked_unverified(library, skills):
    bad = text(f"About 300. {cited('garden-plan', 'The budget is 300.')}")
    client = FakeClient([[tool_use("open_notes", {"slugs": ["garden-plan"]})], [bad], [bad]])
    result = Lia(client, library, skills, LiaConfig()).ask("Budget?")
    assert result["citation_check"]["failed"] == 1
    assert "«The budget is 300.» [unverified]" in result["answer"]


def test_citing_an_unopened_note_fails(library, skills):
    claim = text(f"Corner. {cited('home-goals', CORNER)}")
    client = FakeClient([[claim], [claim]])
    result = Lia(client, library, skills, LiaConfig()).ask("Corner?")
    assert result["citations"][0]["reason"] == "note was not opened for this question"


def test_abstain_format(library, skills):
    client = FakeClient([[text(f"{ABSTAIN} No note mentions a pond.")], *SEARCHED_ABSTAIN])
    result = Lia(client, library, skills, LiaConfig()).ask("Pond?")
    assert result["abstain"] and result["citations"] == []
    assert result["abstain_search"] and result["searches"] == 1


def test_search_is_limited_to_three_rounds(library, skills):
    calls = [[tool_use("search_notes", {"query": f"q{i}"}, f"s{i}")] for i in range(5)]
    client = FakeClient([*calls, [text(f"{ABSTAIN} Nothing found.")]])
    result = Lia(client, library, skills, LiaConfig()).ask("Anything?")
    assert result["searches"] == 3
    assert sum(1 for s in result["steps"] if s["returned"] == "limit") == 2


def test_l0_switch_opens_before_the_first_call(library, skills):
    answer = [text(f"Three hundred. {cited('garden-plan', GARDEN_FACT)}")]
    off = FakeClient([answer, answer])
    Lia(off, library, skills, LiaConfig()).ask("How big is the allotment plan?")
    assert "Opened before you start" not in json.dumps(off.sent[0]["messages"])
    on = FakeClient([answer])
    result = Lia(on, library, skills, LiaConfig(l0=True)).ask("How big is the allotment plan?")
    assert "Opened before you start" in json.dumps(on.sent[0]["messages"])
    assert result["steps"][0]["tool"] == "l0" and result["citation_check"]["failed"] == 0


def test_neighbour_switch_reaches_open_notes(library, skills):
    client = FakeClient(
        [
            [tool_use("open_notes", {"slugs": ["garden-plan"]})],
            [text(f"{ABSTAIN} x")],
            *SEARCHED_ABSTAIN,
        ]
    )
    Lia(client, library, skills, LiaConfig(neighbours=True)).ask("Q?")
    assert "neighbours of garden-plan" in json.dumps(client.sent[1]["messages"])


def test_trace_is_written(library, skills, tmp_path):
    client = FakeClient([[text(f"{ABSTAIN} Not recorded.")], *SEARCHED_ABSTAIN])
    result = Lia(client, library, skills, LiaConfig()).ask("Pond?", "life/q09 run1")
    path = write_trace(result, tmp_path / "traces")
    trace = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "life_q09_run1.json"
    assert {
        "question",
        "steps",
        "answer",
        "citations",
        "citation_check",
        "calls",
        "cost_usd",
        "latency_ms",
        "map_version",
        "abstain_search",
    } <= set(trace)


def test_budget_stops_at_the_line():
    budget = Budget(stop_at=0.01)
    budget.add(0.006)
    budget.check()
    budget.add(0.005)
    with pytest.raises(BudgetStop):
        budget.check()


def test_cost_uses_the_cache_rates():
    # 1M uncached in + 1M cache writes (1h, 2x) + 1M cache reads (0.05x) + 1M out, Sonnet 5.5
    assert cost_of("claude-sonnet-5-5", 10**6, 10**6, 10**6, 10**6) == pytest.approx(
        2 + 4 + 0.1 + 10
    )


def test_nothing_is_written_to_the_brain(library, skills):
    def tree():
        return {
            p: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in library.root.rglob("*")
            if p.is_file()
        }

    before = tree()
    client = FakeClient(
        [
            [tool_use("open_notes", {"slugs": ["garden-plan", "home-goals"]})],
            [tool_use("search_notes", {"query": "garden"}, "t2")],
            [text(f"Three hundred. {cited('garden-plan', GARDEN_FACT)}")],
        ]
    )
    Lia(client, library, skills, LiaConfig(l0=True, neighbours=True)).ask("Allotment plan?")
    assert tree() == before


def test_cascade_router_opens_and_the_answer_model_writes(library, skills):
    router = FakeClient(
        [[tool_use("open_notes", {"slugs": ["garden-plan"]})], [text("router's own answer")]]
    )
    writer = FakeClient([[text(f"Three hundred. {cited('garden-plan', GARDEN_FACT)}")]])
    config = LiaConfig(answer_model="claude-sonnet-5-5")
    result = Lia(router, library, skills, config, answer_client=writer).ask("Budget?")
    assert "router's own answer" not in result["answer"]
    assert result["citation_check"]["failed"] == 0 and len(result["calls"]) == 3
    last = writer.sent[0]["messages"][-1]
    assert last["role"] == "user" and last["content"][0]["type"] == "tool_result"


def test_flat_brain_keeps_free_verbs_with_their_other_direction(tmp_path):
    root = tmp_path / "demo"
    (root / "people").mkdir(parents=True)
    (root / "areas").mkdir()
    (root / "people" / "ann.md").write_text(
        "---\nid: a\nslug: ann\nname: Ann\ntype: person\ndescription: A pilot\naliases: []\n---\n\n"
        "## Facts\n\n- [stated] Flew one mission (src: x, 2030-01-01)\n\n"
        "## Links\n\n- flew [[m1]]\n",
        encoding="utf-8",
    )
    (root / "areas" / "m1.md").write_text(
        "---\nid: m\nslug: m1\nname: M1\ntype: event\ndescription: A mission\naliases: []\n---\n\n"
        "## Facts\n\n- [stated] Launched (src: x, 2030-01-01)\n",
        encoding="utf-8",
    )
    lib = Library(root, flat=True)
    maps = lib.maps()
    assert "ann: flew m1" in maps["relationship-map.md"]
    assert "m1: ←flew ann" in maps["relationship-map.md"]
    assert "## people" in maps["shelf-map.md"] and "people|1" in maps["atlas.md"]


def test_abstain_without_a_search_is_sent_back_to_search_first(library, skills):
    client = FakeClient(
        [
            [text(f"{ABSTAIN} No budget recorded.")],
            [tool_use("search_notes", {"query": "garden budget"}, "s1")],
            [tool_use("open_notes", {"slugs": ["garden-plan"]}, "o1")],
            [text(f"Three hundred. {cited('garden-plan', GARDEN_FACT)}")],
        ]
    )
    result = Lia(client, library, skills, LiaConfig()).ask("Garden budget?")
    assert result["abstain_search"] and not result["abstain"]
    assert "run search_notes" in json.dumps(client.sent[1]["messages"][-1])
    assert [s["tool"] for s in result["steps"]] == ["search_notes", "open_notes"]


def test_abstain_after_a_search_is_not_sent_back(library, skills):
    client = FakeClient(
        [[tool_use("search_notes", {"query": "pond"}, "s1")], [text(f"{ABSTAIN} No pond.")]]
    )
    result = Lia(client, library, skills, LiaConfig()).ask("Pond?")
    assert result["abstain"] and not result["abstain_search"] and len(client.sent) == 2


def test_citations_in_an_abstain_answer_are_checked(library, skills):
    bad = text(f"{ABSTAIN} Only this: {cited('garden-plan', 'A budget was set.')}")
    client = FakeClient(
        [
            [tool_use("search_notes", {"query": "b"}, "s1")],
            [tool_use("open_notes", {"slugs": ["garden-plan"]}, "o1")],
            [bad],
            [bad],
        ]
    )
    result = Lia(client, library, skills, LiaConfig()).ask("Pond?")
    assert result["abstain"]
    assert result["citation_check"] == {"total": 1, "failed": 1, "retried": True}
    assert "«A budget was set.» [unverified]" in result["answer"]


def test_a_quote_without_a_slug_is_retried_then_marked(library, skills):
    bare = text(f"Three hundred: «{GARDEN_FACT}»")
    client = FakeClient([[tool_use("open_notes", {"slugs": ["garden-plan"]})], [bare], [bare]])
    result = Lia(client, library, skills, LiaConfig()).ask("Budget?")
    assert result["citation_check"] == {"total": 1, "failed": 1, "retried": True}
    assert f"«{GARDEN_FACT}» [unverified]" in result["answer"]


# ---------------------------------------------------------------- v3 voice


def test_abstain_wording_is_lias_own_and_the_old_one_still_counts(library, skills):
    assert ABSTAIN == "I don't have that in your notes yet."
    reply = f"{ABSTAIN} None of your notes mention a pond."
    client = FakeClient([[text(reply)], *SEARCHED_ABSTAIN[:1], [text(reply)]])
    result = Lia(client, library, skills, LiaConfig()).ask("Pond?")
    assert result["abstain"] and result["answer"] == reply
    assert is_abstain("Not in your brain. Nothing.")


def test_footnoted_answer_is_verified_and_the_voice_is_checked(library, skills):
    answer = f"You set it at three hundred euros [1].\n\n[1] {cited('garden-plan', GARDEN_FACT)}"
    replies = [[tool_use("open_notes", {"slugs": ["garden-plan"]})], [text(answer)]]
    cfg = LiaConfig(owner_names=("Manoj",))
    result = Lia(FakeClient(replies), library, skills, cfg).ask("Budget?")
    assert result["citation_check"] == {"total": 1, "failed": 0, "retried": False}
    assert result["third_person"] == []


def test_chat_context_is_shown_to_lia_but_not_as_the_question(library, skills):
    client = FakeClient([[text(f"{ABSTAIN} x")], *SEARCHED_ABSTAIN])
    Lia(client, library, skills, LiaConfig()).ask("And hers?", context="me: Who is Ada?")
    first = client.sent[0]["messages"][0]["content"]
    assert "me: Who is Ada?" in first[0]["text"] and first[-1]["text"] == "Question: And hers?"
