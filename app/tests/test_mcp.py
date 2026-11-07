"""The Lia connector (MCP, stdio): tools, answers, traces, rebuilds; writes only through
tell_lia, and confirm, cancel and undo only from the app (D33 as amended, D36)."""

import asyncio
import hashlib
import json
import os
import sys

import pytest

from test_lia import (
    CORE,
    DONE_LINE,
    GARDEN_FACT,
    NODE,
    TAXONOMY,
    FakeClient,
    cite,
    cited,
    note,
    playbook,
    text,
    tool_use,
)
from yggdras.interface.mcp_server import VERBATIM, LiaService, build_server


@pytest.fixture
def brain(tmp_path):
    root = tmp_path / "brain" / "library"
    files = {
        "00-manual/taxonomy.md": TAXONOMY,
        "00-manual/node.md": NODE,
        "08-rest-joy/garden-plan.md": note("garden-plan", body=f"## Facts\n\n- {GARDEN_FACT}\n"),
    }
    for rel, body in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body, encoding="utf-8")
    skills = tmp_path / "brain" / "skills" / "lia"
    (skills / "library").mkdir(parents=True)
    (skills / "core.md").write_text(CORE, encoding="utf-8")
    (skills / "library" / "fact-lookup.md").write_text(playbook("fact-lookup"), encoding="utf-8")
    return root, skills


def service_with(brain, replies, tmp_path):
    root, skills = brain
    client = FakeClient(replies)
    return LiaService(root, skills, lambda model: client, traces=tmp_path / "traces"), client


MODEL_TOOLS = {"ask_lia", "open_note", "tell_lia"}
APP_TOOLS = {"confirm_change", "cancel_change", "undo_change"}


def test_the_model_reads_and_asks_lia_to_write_but_only_the_app_confirms(brain, tmp_path):
    service, _ = service_with(brain, [], tmp_path)
    tools = {t.name: t for t in asyncio.run(build_server(service).list_tools())}
    assert set(tools) == MODEL_TOOLS | APP_TOOLS
    assert "<lia_reply>" in tools["ask_lia"].description
    assert "third person" in tools["ask_lia"].description
    assert "never answer from your own knowledge" in tools["ask_lia"].description
    for name in ("ask_lia", "open_note"):
        assert tools[name].annotations.read_only_hint
    assert not tools["tell_lia"].annotations.read_only_hint
    assert "can't confirm or undo" in tools["tell_lia"].description
    assert tools["tell_lia"].meta["ui"]["resourceUri"] == "ui://yggdras/change-card.html"
    for name in APP_TOOLS:  # hidden from the model by MCP Apps hosts, and token-guarded
        assert tools[name].meta == {"ui": {"visibility": ["app"]}}
        assert "token" in tools[name].input_schema["required"]


def test_ask_returns_the_cited_answer_a_cost_note_and_writes_a_trace(brain, tmp_path):
    from yggdras.processing.lia.library import Library

    root, _ = brain
    block = [b.shown for b in Library(root).blocks("garden-plan")].index(GARDEN_FACT)
    reply = [cite("Three hundred euros.", 0, block), DONE_LINE]
    replies = [[tool_use("open_notes", {"slugs": ["garden-plan"]})], reply]
    service, _ = service_with(brain, replies, tmp_path)
    out = service.ask("What is the garden budget?")
    answer = "Three hundred euros. [1]\n\n[1] Garden Plan (garden-plan)"
    assert out.startswith(f"{VERBATIM}\n<lia_reply>\n{answer}\n\n— Lia · $")
    assert out.endswith(" s · ✓ 1/1\n</lia_reply>")
    (trace,) = (tmp_path / "traces").glob("mcp-*.json")
    data = json.loads(trace.read_text(encoding="utf-8"))
    assert data["question"] == "What is the garden budget?" and data["source"] == "mcp"


def test_open_note_returns_the_full_note(brain, tmp_path):
    service, _ = service_with(brain, [], tmp_path)
    assert GARDEN_FACT in service.open_note("garden-plan")
    assert GARDEN_FACT in service.open_note("[[garden-plan]]")
    assert service.open_note("pond") == "No note with the slug 'pond'."


def test_lia_is_rebuilt_when_the_brain_changes(brain, tmp_path):
    root, _ = brain
    service, _ = service_with(brain, [], tmp_path)
    first = service.lia()
    assert service.lia() is first  # nothing changed: same Lia, same cached maps
    (root / "08-rest-joy" / "pond.md").write_text(note("pond"), encoding="utf-8")
    assert service.lia() is not first
    assert "pond" in service.open_note("pond")


def test_the_connector_never_writes_to_the_brain(brain, tmp_path):
    root, _ = brain

    def tree():
        return {
            p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()
        }

    before = tree()
    replies = [
        [tool_use("open_notes", {"slugs": ["garden-plan"]})],
        [text(f"Three hundred. {cited('garden-plan', GARDEN_FACT)}")],
    ]
    service, _ = service_with(brain, replies, tmp_path)
    service.ask("Budget?")
    service.open_note("garden-plan")
    assert tree() == before


def test_the_server_speaks_mcp_over_stdio(brain, tmp_path):
    """A real stdio round trip: start `yggdras mcp`, list the tools, open a note (no API call)."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root, skills = brain
    env = {
        **os.environ,
        "ANTHROPIC_API_KEY": "test-not-used",
        "YGGDRAS_ENV_FILE": str(tmp_path / "none.env"),
        "YGGDRAS_LOCAL_DATA": str(tmp_path),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "yggdras.interface.cli",
            "mcp",
            "--brain",
            str(root.parent),
            "--skills",
            str(skills),
        ],
        env=env,
    )

    async def session():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                names = sorted(t.name for t in (await s.list_tools()).tools)
                result = await s.call_tool("open_note", {"slug": "garden-plan"})
                guessed = await s.call_tool("confirm_change", {"pending_id": "c-x", "token": "x"})
                uris = [str(r.uri) for r in (await s.list_resources()).resources]
                card = await s.read_resource("ui://yggdras/change-card.html")
                return names, result.content[0].text, guessed.content[0].text, uris, card

    names, opened, guessed, uris, card = asyncio.run(session())
    assert names == sorted(MODEL_TOOLS | APP_TOOLS)
    assert GARDEN_FACT in opened
    assert "Writing is off" in guessed  # this fixture isn't a git repo: nothing can be written
    assert uris == ["ui://yggdras/change-card.html"]
    assert card.contents[0].mime_type == "text/html;profile=mcp-app"
    assert "confirm_change" in card.contents[0].text


def test_the_result_starts_with_the_verbatim_line_and_wraps_her_reply(brain, tmp_path):
    assert VERBATIM.startswith("Reply to the user with exactly the text inside <lia_reply>")
    assert "third person" in VERBATIM
    replies = [[text("I don't have that in your notes yet. Nothing on ponds.")]]
    replies += [[tool_use("search_notes", {"query": "pond"})], [text("I don't have that yet.")]]
    service, _ = service_with(brain, replies, tmp_path)
    out = service.ask("Pond?")
    first, rest = out.split("\n", 1)
    assert first == VERBATIM
    assert rest.startswith("<lia_reply>\n") and rest.endswith("\n</lia_reply>")


def test_the_connector_runs_the_one_config():
    from yggdras.interface.mcp_server import default_config

    cfg = default_config("claude-haiku-5-5")
    assert (cfg.model, cfg.complex_model) == ("claude-haiku-5-5", "claude-sonnet-5-5")


def test_the_talk_to_lia_prompt_sets_the_rule_for_the_conversation(brain, tmp_path):
    service, _ = service_with(brain, [], tmp_path)
    server = build_server(service)
    (prompt,) = asyncio.run(server.list_prompts())
    assert prompt.name == "talk-to-lia"
    result = asyncio.run(server.get_prompt("talk-to-lia"))
    body = result.messages[0].content.text
    assert "call ask_lia" in body and "<lia_reply>" in body
    assert "Never answer from your own knowledge" in body


# ---------------------------------------------------------------- the writing side


def write_service(repo, tmp_path, replies):
    """A LiaService over a git-backed library brain (test_brain_write's fixture)."""
    skills = tmp_path / "skills"
    (skills / "library").mkdir(parents=True)
    (skills / "core.md").write_text(CORE, encoding="utf-8")
    (skills / "library" / "fact-lookup.md").write_text(playbook("fact-lookup"), encoding="utf-8")
    client = FakeClient(replies)
    service = LiaService(repo / "library", skills, lambda model: client, traces=tmp_path / "tr")
    return service


class FakeCtx:
    """A client that supports elicitation (Claude Code): Manoj answers the form."""

    def __init__(self, write: bool | None):
        from types import SimpleNamespace

        self.client_capabilities = SimpleNamespace(elicitation=object())
        self.session = SimpleNamespace(
            client_params=SimpleNamespace(client_info=SimpleNamespace(name="claude-code"))
        )
        self.write, self.asked = write, []

    async def elicit(self, message, schema):
        from types import SimpleNamespace

        self.asked.append(message)
        if self.write is None:
            return SimpleNamespace(action="cancel", data=None)
        return SimpleNamespace(action="accept", data=schema(write=self.write))


def call(server, name, args, ctx):
    tool = server._tool_manager.get_tool(name)
    return asyncio.run(tool.fn(**args, ctx=ctx))


def _git_brain(tmp_path):
    from test_brain_write import make_brain

    return make_brain(tmp_path)


def _thesis_block(repo):
    from test_brain_write import THESIS_FACT
    from yggdras.processing.lia.library import Library

    return [b.shown for b in Library(repo / "library").blocks("masters-thesis")].index(THESIS_FACT)


@pytest.mark.parametrize("write", [True, False, None])
def test_claude_code_confirms_with_a_form_inside_tell_lia(tmp_path, monkeypatch, write):
    import subprocess

    monkeypatch.setenv("YGGDRAS_LOCAL_DATA", str(tmp_path / "local"))
    repo = _git_brain(tmp_path)
    replies = [
        [
            tool_use(
                "remove_fact",
                {"slug": "masters-thesis", "block_id": _thesis_block(repo), "mode": "until"},
            )
        ],
        [text("Here is the change.")],
    ]
    service = write_service(repo, tmp_path, replies)
    ctx = FakeCtx(write)
    out = call(build_server(service), "tell_lia", {"request": "Remove my thesis due date."}, ctx)
    assert ctx.asked and "Write these changes?" in ctx.asked[0]
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s"], capture_output=True, text=True
    ).stdout.splitlines()
    if write:
        assert out.structured_content["kind"] == "summary"
        assert log[0] == "lia: remove fact from masters-thesis"
        assert (
            "claude-code (form)"
            in subprocess.run(
                ["git", "-C", str(repo), "log", "-1", "--format=%B"], capture_output=True, text=True
            ).stdout
        )
    else:
        assert out.structured_content["kind"] == "message" and log == ["base"]


def test_the_token_travels_only_in_meta_never_in_the_models_text(tmp_path, monkeypatch):
    monkeypatch.setenv("YGGDRAS_LOCAL_DATA", str(tmp_path / "local"))
    repo = _git_brain(tmp_path)
    replies = [
        [
            tool_use(
                "remove_fact",
                {"slug": "masters-thesis", "block_id": _thesis_block(repo), "mode": "until"},
            )
        ],
        [text("Here is the change.")],
    ]
    service = write_service(repo, tmp_path, replies)
    server = build_server(service)
    out = call(server, "tell_lia", {"request": "Remove my thesis due date."}, None)  # no form
    token = out.meta["yggdras/token"]
    pid = out.structured_content["pending_id"]
    assert token and token not in out.content[0].text and token not in str(out.structured_content)
    guess = call(server, "confirm_change", {"pending_id": pid, "token": "guess"}, None)
    assert guess.structured_content["kind"] == "refused"
    done = call(server, "confirm_change", {"pending_id": pid, "token": token}, None)
    assert done.structured_content["kind"] == "summary"


def test_writing_needs_the_brains_own_repo_never_one_further_up(tmp_path):
    import subprocess

    from yggdras.interface.writing import repo_of

    outer = tmp_path / "home"
    (outer / "notes" / "brain" / "library").mkdir(parents=True)
    subprocess.run(["git", "-C", str(outer), "init", "-q"], check=True)
    library = outer / "notes" / "brain" / "library"
    assert repo_of(library) is None  # a home folder in git never receives Lia's commits
    subprocess.run(["git", "-C", str(library.parent), "init", "-q"], check=True)
    assert repo_of(library) == library.parent.resolve()
