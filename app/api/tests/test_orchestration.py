"""Phase 2: intake → router → planner → dispatch → checker → memory, with scripted models
(no paid call, no database)."""

import pytest

from yggdress_app.agent_effects import Effect, drive
from yggdress_app.agent_models import ModelReply
from yggdress_app.agent_orchestrator import Yggdras
from yggdress_app.orchestration import (
    PLANNER_MODEL,
    ROUTER_MODEL,
    Checker,
    cost,
    intake,
)
from yggdress_app.orchestration_host import Host
from yggdress_app.skill_registry import SkillRegistry
from yggdress_app.tool_gate import SEND, SENSITIVE, Toolbelt, ToolLocked, default_registry


def use(name, values, ident="u1", tokens=(100, 10)):
    return ModelReply([{"type": "tool_use", "id": ident, "name": name, "input": values}], *tokens)


def say(text, tokens=(100, 10)):
    return ModelReply([{"type": "text", "text": text}], *tokens)


class Scripted:
    """Replies scripted per agent; records (agent, model, tool names) of every call."""

    def __init__(self, scripts):
        self.scripts, self.seen = {k: list(v) for k, v in scripts.items()}, []

    def for_agent(self, agent):
        return Bound(self, agent, "default")


class Bound:
    def __init__(self, root, agent, model):
        self.root, self.agent, self.model = root, agent, model

    def for_agent(self, agent):
        return Bound(self.root, agent, "default")

    def with_model(self, model):
        return Bound(self.root, self.agent, model)

    def complete(self, system, messages, tools):
        self.root.seen.append((self.agent, self.model, sorted(t["name"] for t in tools)))
        script = self.root.scripts.get(self.agent)
        if not script and self.agent == "notice":  # nothing worth filing, unless scripted
            return say("none")
        return script.pop(0)


class Lia:
    def __init__(self):
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return "Manoj's German lesson is on Thursday at 18:00."


def setup(scripts, handlers=None, sensitive=()):
    skills, tools = SkillRegistry(), default_registry()
    host = Host(skills, tools, handlers=handlers or {})
    model, lia = Scripted(scripts), Lia()
    ygg = Yggdras(model, host, lia)
    checker = Checker(set(sensitive))

    def go(text, source="chat"):
        request = intake(source, {"chat": {"content": text}, "voice": {"transcript": text},
                                  "notification": {"reply": text, "notification_id": "n1"}}[source])  # fmt: skip
        steps = ygg.handle(request, skills=skills, belt_for=lambda: Toolbelt(tools, skills),
                           checker=checker)  # fmt: skip
        return drive(steps, model, host, lia)

    return go, model, host, lia


def test_intake_normalises_every_entry_point_to_one_shape():
    a = intake("chat", {"content": "Plan my week", "session": "s1"})
    b = intake("voice", {"transcript": "Plan my week"})
    c = intake("notification", {"reply": "Plan my week", "notification_id": "n7"})
    d = intake("mobile", {"text": "Plan my week"})
    e = intake("connector", {"summary": "Plan my week"})
    assert {x.text for x in (a, b, c, d, e)} == {"Plan my week"}
    assert c.reply_to == "n7" and type(a) is type(e)
    with pytest.raises(ValueError):
        intake("fax", {"text": "x"})


def test_a_quick_answer_returns_directly_on_the_cheap_model():
    go, model, host, lia = setup({"router": [use("route", {"kind": "quick"})],
                                  "yggdras": [say("Berlin is in UTC+1 in winter.")]})  # fmt: skip
    out = go("What timezone is Berlin in?")
    assert out.route == "quick" and out.answer.startswith("Berlin")
    assert [s[:2] for s in model.seen] == [
        ("router", ROUTER_MODEL), ("yggdras", ROUTER_MODEL), ("notice", ROUTER_MODEL)]  # fmt: skip
    assert model.seen[1][2] == []  # no tools for a quick answer
    assert host.runs[0]["route"] == "quick" and not lia.asked


def test_a_single_action_takes_one_tool_then_goes_to_the_checker():
    found = []
    handlers = {"search_brain": lambda v: found.append(v) or {"hits": ["german-learning"]}}
    go, model, host, _ = setup({
        "router": [use("route", {"kind": "single"})],
        "yggdras": [use("load_skill", {"name": "file-to-brain"}),
                    use("search_brain", {"query": "German"}, "u2"),
                    say("Your German notes are in german-learning.")]}, handlers)  # fmt: skip
    out = go("Where are my German notes?")
    assert out.route == "single" and host.ran == ["search_brain"] and found == [{"query": "German"}]
    assert out.cards == [] and out.steps[0]["tools"] == ["search_brain"]
    # tools appeared only after the skill unlocked them
    assert model.seen[1][2] == ["load_skill"] and "search_brain" in model.seen[2][2]


def test_a_risky_action_cannot_execute_without_approval():
    sent = []
    go, _model, host, _ = setup({
        "router": [use("route", {"kind": "single"})],
        "yggdras": [use("load_skill", {"name": "send-email"}),
                    use("send_email", {"to": "sam@example.com", "subject": "Hi", "body": "Hello"}, "u2"),
                    say("The email to Sam waits on a card for you.")]},
        {"send_email": lambda v: sent.append(v)})  # fmt: skip
    out = go("Email Sam hello")
    assert sent == [] and host.ran == []  # never executed
    assert len(out.cards) == 1 and out.cards[0]["tool"] == "send_email"
    assert SEND in out.cards[0]["reasons"] and host.runs[0]["checker_stopped"] is True
    # and the host refuses it even if something tried to run it directly
    host.unlocked.add("email")
    with pytest.raises(ToolLocked, match="needs Manoj's approval"):
        host.call("yggdras", {"name": "send_email", "input": {}})


def test_touching_a_sensitive_note_is_risky_even_for_a_read():
    checker = Checker({"health-record"})
    tool = default_registry().tools["search_brain"]
    assert checker.check(tool, {"query": "show health-record"}).reasons == (SENSITIVE,)
    assert not checker.check(tool, {"query": "German"}).approve


def test_the_host_refuses_a_forged_tool_effect_for_a_locked_domain():
    host = Host(SkillRegistry(), default_registry(), handlers={"read_tasks": lambda v: []})
    with pytest.raises(ToolLocked, match="not unlocked"):
        host.call("yggdras", {"name": "read_tasks", "input": {"query": "x"}})
    host.load("daily-review")
    assert host.call("yggdras", {"name": "read_tasks", "input": {"query": "x"}}) == []


def test_a_multi_step_job_is_planned_per_step_and_dispatched_and_recorded():
    plan = {"framework": "gather → propose", "steps": [
        {"task": "When is German this week?", "agent": "lia", "model": ROUTER_MODEL},
        {"task": "Draft and send Sam the German time.", "agent": "helper",
         "skills": ["send-email"], "model": PLANNER_MODEL, "framework": "draft → send"}]}  # fmt: skip
    go, model, host, lia = setup({
        "router": [use("route", {"kind": "multi"})],
        "planner": [use("plan", plan)],
        "helper": [use("send_email", {"to": "sam@example.com", "subject": "German",
                                      "body": "Thursday 18:00"}),
                   say("The email is drafted and waits for approval.")],
        "yggdras": [say("German is Thursday at 18:00; the email to Sam waits on a card.")]})  # fmt: skip
    out = go("Tell Sam when my German lesson is", source="voice")
    assert out.route == "multi" and out.plan["framework"] == "gather → propose"
    assert lia.asked == ["When is German this week?"]
    assert [s["agent"] for s in out.steps] == ["lia", "helper"]
    assert [s["model"] for s in out.steps] == [ROUTER_MODEL, PLANNER_MODEL]  # model per step
    helper_calls = [s for s in model.seen if s[0] == "helper"]
    assert helper_calls[0][1] == PLANNER_MODEL and "send_email" in helper_calls[0][2]
    assert "propose_task_change" not in helper_calls[0][2]  # only its own skill's tools
    assert len(out.cards) == 1 and out.cards[0]["agent"] == "helper"
    run = host.runs[0]
    assert run["route"] == "multi" and run["request"]["source"] == "voice"
    assert run["cards"] == 1 and {u["agent"] for u in run["usage"]} == {
        "router",
        "planner",
        "yggdras",
        "notice",
    }
    assert all(u["cost"] >= 0 for u in run["usage"])


def test_the_router_falls_back_to_the_planner_when_unclear():
    go, _model, _host, _ = setup({
        "router": [say("hmm")],
        "planner": [use("plan", {"framework": "ask", "steps": [
            {"task": "What is on today?", "agent": "lia", "model": ROUTER_MODEL}]})],
        "yggdras": [say("Today: German at 18:00.")]})  # fmt: skip
    assert go("today?").route == "multi"


def test_router_cost_per_call():
    # a routing call: about 600 tokens in, 40 out, on Haiku 5.5
    assert cost(ROUTER_MODEL, 600, 40) == pytest.approx(0.00008)


def test_effects_have_the_kinds_the_temporal_activity_serves():
    assert Effect("record", "yggdras", {}).kind == "record"


def test_yggdras_offers_a_fact_worth_filing_without_writing_it():
    handlers = {"search_brain": lambda v: {"hits": ["techciti-internship"]}}
    facts = {"facts": [{"fact": "Manoj's internship mentor is Priya.", "about": "internship"}]}
    go, _model, host, _ = setup({
        "router": [use("route", {"kind": "quick"})],
        "yggdras": [say("Nice, a good mentor helps.")],
        "notice": [use("offer_facts", facts)]}, handlers)  # fmt: skip
    out = go("My internship mentor is Priya, by the way.")
    assert host.ran == ["search_brain"]  # the brain was only searched
    assert [c["tool"] for c in out.cards] == ["offer_brain_fact"]
    assert out.cards[0]["input"] == {"slug": "techciti-internship",
                                     "fact": "Manoj's internship mentor is Priya."}  # fmt: skip
    assert out.cards[0]["offer"] is True and out.cards[0]["reasons"] == []
