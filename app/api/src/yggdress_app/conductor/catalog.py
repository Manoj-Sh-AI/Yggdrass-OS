"""The conductor's real tools: Manoj's notes (through the authenticated brain HTTP API,
never the database), tasks and calendar (through the application's own validated
read/command code). Sensitive notes never leave as text: a restricted note is an id
and a placeholder label only (hard rule)."""

from __future__ import annotations

import uuid
from typing import Any

from ..agent_tools import ApplicationTools, Proposal, ReadQuery, allowed
from ..mobile_policy import sensitive
from .tools import StaticToolbox, ToolSpec

EXCERPT_CHARS = 1500
NOTES_OWNER = "conductor"


def restricted_view(note: dict[str, Any]) -> dict[str, Any]:
    slug = note.get("slug") or note.get("id") or ""
    if sensitive(note):
        return {"slug": slug, "title": "Restricted note", "sensitivity": "restricted"}
    # `content` is the body without frontmatter (note_view); never the raw file.
    body = note.get("content") or note.get("body") or ""
    return {"slug": slug, "title": note.get("title") or slug, "excerpt": body[:EXCERPT_CHARS]}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}  # fmt: skip


READ_PROPERTIES = {
    "query": {"type": "string", "description": "words in the title; empty for all"},
    "start": {"type": "string", "description": "YYYY-MM-DD, optional"},
    "end": {"type": "string", "description": "YYYY-MM-DD, optional"},
    "limit": {"type": "integer", "minimum": 1, "maximum": 40},
}
CHANGE_PROPERTIES = {
    "operation": {"type": "string", "description": "e.g. task.create, event.update, event.remove"},
    "id": {"type": "string", "description": "existing item id (omit to create)"},
    "version": {"type": "integer", "description": "existing item's exact version"},
    "data": {"type": "object", "description": "fields to set"},
    "explanation": {"type": "string", "description": "one sentence: why this change"},
}


def change_stakes(arguments: dict[str, Any]) -> tuple[str, bool]:
    """Removing or cancelling is high impact and cannot be undone here; creating or
    updating is low impact but has no undo either (version-checked and logged)."""
    operation = str(arguments.get("operation", ""))
    if operation.endswith((".remove", ".cancel")):
        return "high", False
    return "low", False


def build_toolbox(database, notes=None) -> StaticToolbox:
    application = ApplicationTools(database)
    tools: list[ToolSpec] = [
        ToolSpec(
            "read_tasks",
            "Read Manoj's tasks, optionally filtered by title words and a date range.",
            _schema(READ_PROPERTIES, []),
            run=lambda a: application.read("tasks", ReadQuery.model_validate(a).model_dump()),
        ),
        ToolSpec(
            "read_calendar",
            "Read Manoj's calendar events and availability in a date range.",
            _schema({**READ_PROPERTIES, "free_minutes": {"type": "integer"}}, []),
            run=lambda a: application.read("calendar", ReadQuery.model_validate(a).model_dump()),
        ),
    ]
    for agent, tool_name in (("tasks", "change_task"), ("calendar", "change_calendar")):
        tools.append(
            ToolSpec(
                tool_name,
                f"Propose a change to Manoj's {agent}. It runs only after the safety checks "
                "(and Manoj's approval where required).",
                _schema(CHANGE_PROPERTIES, ["operation", "explanation"]),
                impact="low",
                reversible=False,
                classify=change_stakes,
                run=lambda a, agent=agent: _change(database, application, agent, a),
            )
        )
    if notes is not None:
        tools.append(
            ToolSpec(
                "search_notes",
                "Search Manoj's notes (his second brain). Returns titles and short excerpts; "
                "restricted notes appear without content.",
                _schema({"query": {"type": "string"}}, ["query"]),
                reads_notes=True,
                run=lambda a: [
                    restricted_view(n)
                    for n in notes.search(NOTES_OWNER, str(a.get("query", ""))[:200])["notes"]
                ],
            )
        )
    return StaticToolbox(tools)


def _change(database, application: ApplicationTools, agent: str, arguments: dict[str, Any]):
    proposal = Proposal.model_validate(arguments)
    if not allowed(agent, proposal):
        raise ValueError(f"{proposal.operation} is not a {agent} change.")
    with database.connect() as db:
        return application.execute(proposal, uuid.uuid4(), db)
