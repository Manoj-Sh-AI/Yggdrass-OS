"""The read-only Lia connector (MCP, stdio): tools, answers, traces, rebuilds, no writes."""

import asyncio
import hashlib
import json
import os
import sys

import pytest

from test_lia import GARDEN_FACT, NODE, TAXONOMY, FakeClient, cited, note, text, tool_use
from yggdras.interface.mcp_server import LiaService, build_server


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
    skills.mkdir(parents=True)
    (skills / "answering.md").write_text("# Lia\n\nAnswer from notes only.\n", encoding="utf-8")
    return root, skills


def service_with(brain, replies, tmp_path):
    root, skills = brain
    client = FakeClient(replies)
    return LiaService(root, skills, lambda model: client, traces=tmp_path / "traces"), client


def test_two_read_only_tools_that_tell_the_chat_model_not_to_add_facts(brain, tmp_path):
    service, _ = service_with(brain, [], tmp_path)
    tools = {t.name: t for t in asyncio.run(build_server(service).list_tools())}
    assert set(tools) == {"ask_lia", "open_note"}
    assert "never add facts of your own" in tools["ask_lia"].description
    assert all(
        t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools.values()
    )


def test_ask_returns_the_cited_answer_a_cost_note_and_writes_a_trace(brain, tmp_path):
    answer = f"Three hundred euros. {cited('garden-plan', GARDEN_FACT)}"
    replies = [[tool_use("open_notes", {"slugs": ["garden-plan"]})], [text(answer)]]
    service, _ = service_with(brain, replies, tmp_path)
    out = service.ask("What is the garden budget?")
    assert out.startswith(answer)
    assert "— Lia · $" in out and "citations verified 1/1" in out
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
                return names, result.content[0].text

    names, opened = asyncio.run(session())
    assert names == ["ask_lia", "open_note"]
    assert GARDEN_FACT in opened
