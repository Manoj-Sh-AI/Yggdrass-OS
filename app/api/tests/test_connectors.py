"""Phase 7: the connector catalog. A switched-on connector's tools arrive live, under their
skill's domain, and stay unreachable until a skill in that domain loads."""

import json

import pytest

from yggdress_app.connectors import Catalog, ConnectorError, parse
from yggdress_app.skill_registry import SkillRegistry
from yggdress_app.tool_gate import DELETE, WRITE, Toolbelt, ToolLocked, default_registry

MAIL = {"name": "mailbox", "title": "Mailbox", "domain": "email", "command": ["mail-mcp"],
        "env": ["MAILBOX_TOKEN"]}  # fmt: skip
TOOLS = [
    {"name": "list_messages", "description": "List inbox messages",
     "annotations": {"readOnlyHint": True}},
    {"name": "delete_message", "description": "Delete one", "annotations": {"destructiveHint": True}},
    {"name": "archive", "description": "Archive one"},
]  # fmt: skip


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("MAILBOX_TOKEN", "not-a-real-token")
    path = tmp_path / "connectors.json"
    path.write_text(json.dumps({"connectors": [MAIL]}), encoding="utf-8")
    listed = []
    registry = default_registry()
    cat = Catalog(path, registry, lambda entry: listed.append(entry.name) or TOOLS)
    return cat, registry, listed


def test_switching_on_brings_tools_live_without_a_redeploy(catalog):
    cat, registry, listed = catalog
    assert cat.view()[0]["enabled"] is False and "mailbox__list_messages" not in registry.tools
    view = cat.switch("mailbox", True)
    assert view["enabled"] is True and listed == ["mailbox"]
    tools = registry.tools
    assert tools["mailbox__list_messages"].risks == frozenset()
    assert tools["mailbox__delete_message"].risks == {WRITE, DELETE}
    assert tools["mailbox__archive"].risks == {WRITE}  # unknown means risky
    cat.switch("mailbox", False)
    assert not any(name.startswith("mailbox__") for name in registry.tools)


def test_a_connectors_tools_stay_locked_until_its_skill_loads(catalog):
    cat, registry, _ = catalog
    cat.switch("mailbox", True)
    belt = Toolbelt(registry, SkillRegistry())
    assert "mailbox__list_messages" not in {s["name"] for s in belt.schemas()}
    with pytest.raises(ToolLocked):
        belt.require("mailbox__list_messages")
    belt.load_skill("triage-inbox")  # its domains include email
    assert belt.require("mailbox__list_messages").domain == "email"


def test_no_credentials_in_the_catalog_and_missing_env_blocks_switching_on(catalog, monkeypatch):
    cat, _, _ = catalog
    with pytest.raises(ConnectorError, match="NAMES only"):
        parse({**MAIL, "env": ["MAILBOX_TOKEN=abc"]})
    monkeypatch.delenv("MAILBOX_TOKEN")
    assert cat.view()[0]["missing_env"] == ["MAILBOX_TOKEN"]
    with pytest.raises(ConnectorError, match="needs MAILBOX_TOKEN"):
        cat.switch("mailbox", True)
