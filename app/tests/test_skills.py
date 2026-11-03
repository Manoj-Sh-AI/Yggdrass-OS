"""Arm D, the skill library: the index is cached, playbooks load on demand (at most two, with the
first open_notes), and the 'done when' checklist is reported before the answer."""

import pytest

from test_explore import RecordingClient
from test_lia import GARDEN_FACT, cited, text, tool_use
from test_lia import library as library  # noqa: F401  (the fixture)
from yggdras.processing.lia import skills
from yggdras.processing.lia.lia import Lia, LiaConfig

CORE = "---\nname: core\ndescription: Always loaded.\n---\n\n# Core\n\nCite every claim.\n"


def playbook(name, items=("I did the first thing.", "I did the second thing.")):
    done = "\n".join(f"  - {i}" for i in items)
    return (
        f"---\nname: {name}\ndescription: Use it for {name} jobs.\ndone_when:\n{done}\n---\n\n"
        f"# {name}\n\nSteps for {name}.\n"
    )


@pytest.fixture
def playbooks(tmp_path):
    folder = tmp_path / "library"
    folder.mkdir()
    (folder / "core.md").write_text(CORE, encoding="utf-8")
    for name in ("fact-lookup", "bridge", "status-sweep"):
        (folder / f"{name}.md").write_text(playbook(name), encoding="utf-8")
    return skills.load_library(folder)


def lia_d(library, playbooks, client):  # noqa: F811
    cfg = LiaConfig(skill_library=True)
    return Lia(client, library, skills.system_text(playbooks), cfg, playbooks=playbooks)


def report(names, done=True):
    items = [{"skill": n, "item": f"item {i}", "done": done} for n in names for i in range(2)]
    return tool_use("checklist", {"items": items}, "k1")


ANSWER = f"Three hundred euros [1].\n\n[1] {cited('garden-plan', GARDEN_FACT)}"


def test_a_playbook_needs_frontmatter_and_a_checklist(tmp_path):
    bad = tmp_path / "bridge.md"
    bad.write_text(
        "---\nname: bridge\ndescription: Joins.\n---\n\nNo checklist.\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="done_when"):
        skills.parse(bad)
    wrong = tmp_path / "chain.md"
    wrong.write_text(playbook("not-chain"), encoding="utf-8")
    with pytest.raises(ValueError, match="name"):
        skills.parse(wrong)


def test_the_index_and_core_are_cached_and_playbooks_are_not(library, playbooks):  # noqa: F811
    lia = lia_d(library, playbooks, RecordingClient([]))
    cached = lia.system[0]["text"]
    assert "Cite every claim." in cached and "<skill-index>" in cached
    assert "bridge | Use it for bridge jobs." in cached
    assert "Steps for bridge." not in cached  # loaded on demand only
    assert {"load_skill", "checklist"} <= {t["name"] for t in lia.tools}
    assert "Steps for bridge." in skills.full_text(playbooks)  # the one-prompt baseline


def test_skills_load_with_the_first_open_and_the_checklist_comes_before_the_answer(
    library,  # noqa: F811
    playbooks,
):
    first = [
        tool_use("load_skill", {"names": ["fact-lookup"]}, "s1"),
        tool_use("open_notes", {"slugs": ["garden-plan"]}, "o1"),
    ]
    client = RecordingClient([first, [report(["fact-lookup"])], [text(ANSWER)]])
    result = lia_d(library, playbooks, client).ask("What is the garden budget?")
    assert result["skills_loaded"] == ["fact-lookup"]
    assert result["skill_turns"] == [result["first_open_turn"]] == [1]  # one round trip
    assert result["checklist_complete"] is True and len(result["checklists"]) == 1
    loaded = client.sent[1]["messages"][-1]["content"][0]["content"]
    assert "Steps for fact-lookup." in loaded and "Done when:" in loaded


def test_at_most_two_playbooks(library, playbooks):  # noqa: F811
    text_, done = skills.loaded_text(playbooks, ["fact-lookup", "bridge", "status-sweep"])
    assert done == ["fact-lookup", "bridge"] and "only the first 2" in text_
    first = [tool_use("load_skill", {"names": ["fact-lookup", "bridge"]}, "s1")]
    more = [tool_use("load_skill", {"names": ["status-sweep"]}, "s2")]
    abstain = [text("I don't have that in your notes yet. x")]
    search = [tool_use("search_notes", {"query": "x"}, "q1")]
    client = RecordingClient(
        [first, more, [report(["fact-lookup", "bridge"])], abstain, search, abstain]
    )
    result = lia_d(library, playbooks, client).ask("Pond?")
    assert result["skills_loaded"] == ["fact-lookup", "bridge"]


def test_an_answer_without_the_checklist_is_sent_back_and_undone_items_get_a_round(
    library,  # noqa: F811
    playbooks,
):
    client = RecordingClient(
        [
            [
                tool_use("load_skill", {"names": ["bridge"]}, "s1"),
                tool_use("open_notes", {"slugs": ["garden-plan"]}, "o1"),
            ],
            [text(ANSWER)],  # skipped the checklist
            [report(["bridge"], done=False)],
            [report(["bridge"])],
            [text(ANSWER)],
        ]
    )
    result = lia_d(library, playbooks, client).ask("Budget?")
    assert skills.CHECKLIST_NUDGE in str(client.sent[2]["messages"][-1])
    assert "Finish these first" in str(client.sent[3]["messages"][-1])
    assert result["checklist_complete"] is True and len(result["checklists"]) == 2


def test_a_reworded_item_still_counts_and_a_missing_one_does_not(playbooks):
    items = [{"skill": "bridge", "item": "reworded", "done": True}]
    reply, complete = skills.checklist_reply(items, ["bridge"], playbooks, 0)
    assert not complete and "(not reported)" in reply
    items.append({"skill": "bridge", "item": "also reworded", "done": True})
    assert skills.checklist_reply(items, ["bridge"], playbooks, 0)[1]


def test_the_connector_arm_d():
    from yggdras.interface.mcp_server import default_config

    cfg = default_config("claude-haiku-5-5", "D")
    assert cfg.skill_library and cfg.escalate == "claude-sonnet-5-5" and cfg.fact_search
