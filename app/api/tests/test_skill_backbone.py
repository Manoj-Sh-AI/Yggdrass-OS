"""Phase 1: skills (know-how), gated tools (hands) and sub-agents (the team). No database,
no paid model: a scripted model and an in-memory effect host."""

from pathlib import Path

import pytest

from yggdress_app import skill_registry
from yggdress_app.agent_effects import drive
from yggdress_app.agent_models import ModelReply
from yggdress_app.skill_registry import SkillRegistry, read_frontmatter
from yggdress_app.subagents import SubAgentSpec, run
from yggdress_app.tool_gate import Tool, Toolbelt, ToolLocked, ToolRegistry, default_registry

SEEDED = ("plan-week", "file-to-brain", "send-email", "triage-inbox", "daily-review")


def skill(folder: Path, name: str, domains: str, body: bytes) -> None:
    (folder / name).mkdir(parents=True)
    head = f"---\nname: {name}\ndescription: Use for {name}.\ndomains: {domains}\n---\n".encode()
    (folder / name / "SKILL.md").write_bytes(head + body)


def test_startup_reads_only_name_and_description(tmp_path):
    # A body that is not even valid UTF-8: reading it at startup would fail.
    skill(tmp_path, "secret-body", "[email]", b"\xff\xfe never read at startup \xff")
    reg = SkillRegistry(tmp_path)
    assert reg.cards["secret-body"].description == "Use for secret-body."
    assert "never read" not in reg.index() and reg.loads == {}


def test_a_body_loads_exactly_once_when_matched(tmp_path, monkeypatch):
    skill(tmp_path, "plan", "[tasks]", b"Step one. Step two.\n")
    reg = SkillRegistry(tmp_path)
    reads = []
    real = Path.read_text
    monkeypatch.setattr(
        Path, "read_text", lambda self, *a, **k: reads.append(self) or real(self, *a, **k)
    )
    assert reg.load("plan") == {"name": "plan", "instructions": "Step one. Step two.",
                                "unlocks": ["tasks"]}  # fmt: skip
    reg.load("plan")
    reg.body("plan")
    assert reg.loads == {"plan": 1} and len(reads) == 1


def test_the_seeded_skills_are_real_and_well_formed():
    reg = SkillRegistry()
    for name in SEEDED:
        card = reg.cards[name]
        assert card.domains and len(read_frontmatter(card.path)) >= 3
        assert len(reg.body(name)) > 400  # real instructions, not a stub
    assert reg.domains("send-email") == ("email",)
    assert set(reg.domains("plan-week")) == {"tasks", "calendar"}


def test_an_ungated_tool_is_unreachable():
    belt = Toolbelt(default_registry(), SkillRegistry())
    names = {s["name"] for s in belt.schemas()}
    assert names == {"load_skill"}  # nothing visible before a skill loads
    with pytest.raises(ToolLocked, match="load a skill in the email domain"):
        belt.require("send_email")
    belt.load_skill("send-email")
    assert belt.require("send_email").domain == "email"
    with pytest.raises(ToolLocked):  # the email skill unlocks email tools and nothing else
        belt.require("propose_task_change")
    assert {s["name"] for s in belt.schemas()} == {"load_skill", "draft_email", "send_email"}


class Script:
    """A scripted model: returns the replies in order and keeps what it was sent."""

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def complete(self, system, messages, tools):
        self.seen.append({"system": system, "messages": [m for m in messages], "tools": tools})
        return self.replies.pop(0)


class Host:
    """The effect host the driver calls for tools: records what actually ran."""

    def __init__(self):
        self.ran = []

    def call(self, agent, data):
        self.ran.append(data["name"])
        return {"proposal": {"tool": data["name"], "input": data["input"]}}


def tool_use(name, values, ident="t1"):
    return ModelReply([{"type": "tool_use", "id": ident, "name": name, "input": values}])


def text(value):
    return ModelReply([{"type": "text", "text": value}])


def test_a_locked_tool_called_by_name_never_runs(monkeypatch):
    monkeypatch.setattr(skill_registry, "_REGISTRY", SkillRegistry())
    model, host = Script([tool_use("send_email", {"to": "a", "subject": "b", "body": "c"}),
                          text("I could not send it.")]), Host()  # fmt: skip
    belt = Toolbelt(default_registry(), skill_registry.registry())
    result = drive(run(SubAgentSpec("Email Sam.", (), "claude-haiku-5-5"), belt), model, host)
    assert host.ran == [] and result.tools == []  # the effect was never produced
    refusal = model.seen[1]["messages"][-1]["content"][0]["content"]
    assert "locked" in refusal


def test_a_subagent_returns_only_its_result(monkeypatch):
    monkeypatch.setattr(skill_registry, "_REGISTRY", SkillRegistry())
    secret_parent_context = "PARENT-ONLY: Manoj's private conversation"
    model = Script([
        tool_use("draft_email", {"to": "sam@example.com", "subject": "Hi", "body": "Hello Sam"}),
        text("Drafted the email to Sam."),
    ])  # fmt: skip
    host = Host()
    belt = Toolbelt(default_registry(), skill_registry.registry())
    spec = SubAgentSpec("Draft a short hello to Sam.", ("send-email",), "claude-haiku-5-5")
    result = drive(run(spec, belt), model, host)
    assert result.answer == "Drafted the email to Sam."
    assert result.proposals == [{"tool": "draft_email", "input": {
        "to": "sam@example.com", "subject": "Hi", "body": "Hello Sam"}}]  # fmt: skip
    assert result.skills == ["send-email"] and result.tools == ["draft_email"]
    # clean context in: the helper saw its task, never the parent's conversation
    assert model.seen[0]["messages"] == [{"role": "user", "content": spec.task}]
    assert all(secret_parent_context not in str(call) for call in model.seen)
    # nothing leaks out: the result carries no transcript, tool output or instructions
    assert set(vars(result)) == {"answer", "proposals", "skills", "tools"}
    assert "Approval:" not in str(vars(result))  # the skill body stayed inside


def test_a_registry_rejects_unknown_risks_and_duplicate_tools():
    reg = ToolRegistry()
    reg.register(Tool("x", "d", "x", {"type": "object"}))
    with pytest.raises(ValueError):
        reg.register(Tool("x", "d", "x", {"type": "object"}))
    with pytest.raises(ValueError):
        reg.register(Tool("y", "d", "y", {"type": "object"}, frozenset({"explodes"})))
