"""Lia as an MCP server (stdio), for Claude Desktop and Claude Code.

    yggdras mcp [--brain REPO] [--flat ROOT] [--model M] [--skills DIR]

Model-visible tools: ask_lia (Lia's reply, first person, footnoted), open_note (one note, to
check a citation) and tell_lia (Manoj's change request; Lia does all writing, D36). One
prompt, talk-to-lia (every message goes to Lia, shown verbatim).

Changes that alter or remove content wait as a preview for Manoj's confirm (D33 as amended):
- Claude Code: a form inside tell_lia (elicitation), answered by Manoj, never by the model;
- Claude Desktop: the card's buttons (MCP Apps), which call confirm_change, cancel_change
  and undo_change. Those three are app-only, and each needs the card's token, which travels in
  the result's _meta (never shown to the model);
- anywhere: `yggdras confirm <id>` in a terminal.

The server rebuilds Lia's maps whenever a note changes; every request leaves a trace in
local-data/traces/.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent
from pydantic import BaseModel, Field

from yggdras import config

VERBATIM = (
    "Reply to the user with exactly the text inside <lia_reply>…</lia_reply>, unchanged: no "
    "preface, no summary, no retelling of Lia in the third person, nothing added."
)
INSTRUCTIONS = (
    "Yggdras is the user's personal second brain, and Lia is its librarian. Send every question "
    "about the user's own life, work, studies, plans, people, places or decisions to ask_lia. "
    "Lia speaks to the user herself, in the first person. Each ask_lia result holds her reply "
    "in a <lia_reply> block: reply with exactly the text inside it, footnotes ([1] [[slug]] "
    "«fact») and the closing line included. No preface, no summary, and never retell her in the "
    'third person ("Her strongest story…"). Never add facts of your own, never fill a gap '
    "from general knowledge, and "
    "never present a guess as something the brain holds. Use open_note when the user wants to "
    "check a citation. When the user asks to add, change, link or remove something in their "
    "notes, pass their request to tell_lia in their own words; when they upload a markdown "
    "file and ask to add it, give it to ingest_file (its path if it is on this computer, else "
    "its content); never edit notes yourself. You "
    "can't confirm, cancel or undo changes: only the user can, with the card's buttons, a form "
    "or the yggdras command. To bring back an archived note, use restore_note."
)
TELL_DESCRIPTION = (
    "Pass the user's request to change their second brain to Lia, in their own words: add a "
    "fact, create a note, link or unlink notes, update or correct a fact, remove a fact, "
    "archive a note. Optionally pass the last two turns of the chat as context. Lia plans and "
    "checks the change. Adding is written at once (with Undo); changing or removing shows a "
    "preview the user confirms themselves. The result holds Lia's card in a <lia_reply> "
    "block: show it exactly as written. You can't confirm or undo anything."
)
RESTORE_DESCRIPTION = (
    'Bring back a note the user archived ("deleted") in their second brain, by its slug, name '
    "or alias, when they ask to restore it. Free and exact: the note returns to its shelf, and "
    "the links, mentions and hub listing archiving removed from other notes come back. Written "
    "at once with Undo; the result holds Lia's card in a <lia_reply> block: show it exactly."
)
INGEST_DESCRIPTION = (
    "Give Lia a markdown file the user uploaded and asked to add to their second brain. In "
    "Claude Code, or whenever the file is on this computer, pass its `path` (up to 5 MB; the "
    "text never goes through you). Otherwise pass `filename` and the file's full `content` "
    "exactly as uploaded (up to 100 KB). Pass the user's words as `instruction`. Markdown "
    "(.md) only for now. Lia keeps the file verbatim, files its facts into notes, links them "
    "and returns her card in a <lia_reply> block: show it exactly as written. Adding is "
    "written at once with Undo; a change to existing notes waits for the user's own confirm."
)
UI_URI = "ui://yggdras/change-card.html"
UI_MIME = "text/html;profile=mcp-app"
APP_ONLY = {"ui": {"visibility": ["app"]}}
TOKEN_KEY = "yggdras/token"
ASK_DESCRIPTION = (
    "Ask Lia, the librarian of the user's second brain, a question about the user's own life, "
    "work, studies, plans, people, places or decisions. Pass the user's message as question; "
    "optionally pass the last two turns of the chat as context, so she can resolve words like "
    "'that' or 'she'. She replies to the user in the first person, with numbered footnotes "
    "([1] [[slug]] «fact text», each checked word for word against the note), or says she "
    "doesn't have it in the notes yet. The result holds her reply in a <lia_reply> block: "
    "reply with exactly the text inside, unchanged, never retold in the third person; never "
    "answer from your own knowledge. Read-only."
)
PROMPT_TEXT = (
    "For the rest of this conversation you are a window onto Lia, the librarian of my second "
    "brain. For every message I send, call ask_lia with my message as question and the last "
    "two turns of our conversation as context; when I ask to add, change, link or remove "
    "something in my notes, call tell_lia with my request instead. Reply with exactly the text "
    "inside the <lia_reply> block, footnotes and closing line included: no preface, no "
    "summary, never retelling her in the third person. Never "
    "answer from your own knowledge, even when you could. If I ask to check a citation, call "
    "open_note with its slug and show the note. Never edit my notes yourself."
)
OPEN_DESCRIPTION = (
    "Open one note of the user's second brain by its slug (the part inside [[...]] in Lia's "
    "citations) and return its full text, so a citation can be checked. Read-only."
)


def default_config(model: str, cite_url: str | None = None):
    """Lia's one config (D35): *model* for simple and medium questions, Sonnet for complex;
    footnotes link to the note server when *cite_url* is set."""
    from yggdras.processing.lia.lia import LiaConfig

    return LiaConfig(model=model, owner_names=config.owner_names(), cite_url=cite_url)


def footer(result: dict) -> str:
    """The closing line: cost, time, and claims that passed the support check out of those
    checked. Every failed one carries an inline [unsupported], so the two always agree."""
    support = result.get("support") or {}
    checked = support.get("checked", 0)
    good = checked - support.get("unsupported", 0)
    return (
        f"— Lia · ${result['cost_usd']:.4f} · {result['latency_ms'] / 1000:.1f} s · "
        f"✓ {good}/{checked}"
    )


class Confirm(BaseModel):
    """Claude Code's confirm form (elicitation): Manoj answers it, never the model."""

    write: bool = Field(description="Write these changes to your notes?")


def card_footer(card) -> str:
    return f"— Lia · ${card.cost_usd:.4f}" if card.cost_usd else "— Lia"


def fingerprint(root: Path, skills: Path) -> tuple:
    """Changes whenever a note, the manual or a skill changes (path, size, modified time)."""
    files = [p for folder in (root, skills) for p in folder.rglob("*.md")]
    return tuple(sorted((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in files))


class LiaService:
    """Holds one Lia and rebuilds her (maps included) when the brain's files change."""

    def __init__(
        self,
        root: Path,
        skills: Path,
        client_factory: Callable,
        *,
        flat: bool = False,
        model: str = "claude-haiku-5-5",
        traces: Path | None = None,
        cite_url: str | None = None,
    ):
        self.root, self.skills, self.flat, self.model = root, skills, flat, model
        self.config = default_config(model, cite_url)
        self.client_factory = client_factory
        self.traces = traces or config.local_data() / "traces"
        self._lock = threading.Lock()
        self._lia, self._print = None, None
        self._write, self._ingest, self.note_url = None, None, None

    def lia(self):
        from yggdras.processing.lia.lia import default_lia
        from yggdras.processing.lia.library import Library

        with self._lock:
            now = fingerprint(self.root, self.skills)
            if self._lia is None or now != self._print:
                library = Library(self.root, flat=self.flat)
                self._lia = default_lia(library, self.skills, self.client_factory, self.config)
                self._write = self._ingest = None  # rebuilt on the next request, new maps
                self._print = now
            return self._lia

    def writer(self):
        """Lia's writing side on the current maps (None if the brain isn't a git repo)."""
        from yggdras.interface import writing

        lia = self.lia()
        with self._lock:
            if self._write is None:
                self._write = writing.write_side(
                    lia.library, self.root, self.flat, self.client_factory, self.note_url
                )
            return self._write

    def restore(self, note: str, app: str):
        from yggdras.processing.lia.write import Card

        side = self.writer()
        if side is None:
            return Card("refused", "Writing is off: this brain is not in a git repository.")
        return side.restore(note, app)

    def ingester(self):
        """Lia's upload filing on the current maps (None if the brain isn't a git repo)."""
        from yggdras.interface import writing

        lia = self.lia()
        with self._lock:
            if self._ingest is None:
                self._ingest = writing.write_side(
                    lia.library, self.root, self.flat, self.client_factory, self.note_url,
                    kind="ingest",
                )  # fmt: skip
            return self._ingest

    def ingest(self, filename: str, content: str, path: str, instruction: str, app: str):
        from yggdras.interface import writing
        from yggdras.processing.lia.write import Card

        try:
            name, data = writing.read_upload(filename, content, path)
        except writing.UploadError as exc:
            return Card("refused", str(exc))
        side = self.ingester()
        if side is None:
            return Card("refused", "Writing is off: this brain is not in a git repository.")
        card = side.ingest(name, data, instruction, app)
        card.trace["source"] = "mcp"
        writing.trace(card, self.traces)
        return card

    def tell(self, request: str, context: str = "", app: str = "chat"):
        from yggdras.interface import writing
        from yggdras.processing.lia.write import Card

        side = self.writer()
        if side is None:
            return Card("refused", "Writing is off: this brain is not in a git repository.")
        card = side.tell(request, context, app)
        card.trace["source"] = "mcp"
        writing.trace(card, self.traces)
        return card

    def ask(self, question: str, context: str = "") -> str:
        from yggdras.processing.lia.lia import write_trace

        lia = self.lia()
        result = lia.ask(
            question,
            qid=f"mcp-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**6}",
            context=context,
        )
        result["source"] = "mcp"
        result["context"] = context
        write_trace(result, self.traces)
        return f"{VERBATIM}\n<lia_reply>\n{result['answer']}\n\n{footer(result)}\n</lia_reply>"

    def open_note(self, slug: str) -> str:
        library = self.lia().library
        text = library.note_text(slug.strip().strip("[]"))
        if text is None:
            return f"No note with the slug '{slug}'."
        return text


def build_server(service: LiaService):
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer(name="yggdras", instructions=INSTRUCTIONS)
    read_only = ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    )

    @server.tool(name="ask_lia", description=ASK_DESCRIPTION, annotations=read_only)
    def ask_lia(question: str, context: str = "") -> str:
        return service.ask(question, context)

    @server.tool(name="open_note", description=OPEN_DESCRIPTION, annotations=read_only)
    def open_note(slug: str) -> str:
        return service.open_note(slug)

    def result(card) -> CallToolResult:
        text = f"{VERBATIM}\n<lia_reply>\n{card.text}\n\n{card_footer(card)}\n</lia_reply>"
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            structured_content={
                "kind": card.kind,
                "text": card.text,
                "pending_id": card.pending_id,
                "sha": card.sha,
            },
            _meta={TOKEN_KEY: card.token} if card.token else None,
        )

    def app_name(ctx) -> str:
        try:
            return ctx.session.client_params.client_info.name or "chat"
        except Exception:
            return "chat"

    write_hints = ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
    )

    @server.tool(
        name="tell_lia",
        description=TELL_DESCRIPTION,
        annotations=write_hints,
        meta={"ui": {"resourceUri": UI_URI}},
    )
    async def tell_lia(request: str, context: str = "", ctx: Context = None) -> CallToolResult:
        import anyio

        app = app_name(ctx)
        card = await anyio.to_thread.run_sync(lambda: service.tell(request, context, app))
        return result(await confirm_by_form(card, ctx, app))

    async def confirm_by_form(card, ctx, app: str):
        """Claude Code: a preview is confirmed in a form Manoj answers; the model never sees a
        confirm tool. Other clients get the card (buttons) or the CLI line."""
        import anyio

        caps = ctx.client_capabilities if ctx is not None else None
        if card.kind != "preview" or caps is None or caps.elicitation is None:
            return card
        answer = await ctx.elicit(f"{card.text}\n\nWrite these changes?", schema=Confirm)
        side = service.writer()
        if answer.action == "accept" and answer.data is not None and answer.data.write:
            pid, token = card.pending_id, card.token
            return await anyio.to_thread.run_sync(lambda: side.confirm(pid, token, f"{app} (form)"))
        return side.cancel(card.pending_id, card.token)

    @server.tool(
        name="restore_note",
        description=RESTORE_DESCRIPTION,
        annotations=write_hints,
        meta={"ui": {"resourceUri": UI_URI}},
    )
    async def restore_note(note: str, ctx: Context = None) -> CallToolResult:
        import anyio

        app = app_name(ctx)
        return result(await anyio.to_thread.run_sync(lambda: service.restore(note, app)))

    @server.tool(
        name="ingest_file",
        description=INGEST_DESCRIPTION,
        annotations=write_hints,
        meta={"ui": {"resourceUri": UI_URI}},
    )
    async def ingest_file(
        filename: str = "",
        content: str = "",
        path: str = "",
        instruction: str = "",
        ctx: Context = None,
    ) -> CallToolResult:
        import anyio

        app = app_name(ctx)
        card = await anyio.to_thread.run_sync(
            lambda: service.ingest(filename, content, path, instruction, app)
        )
        return result(await confirm_by_form(card, ctx, app))

    def off():
        from yggdras.processing.lia.write import Card

        return result(Card("refused", "Writing is off: this brain is not in a git repository."))

    @server.tool(
        name="confirm_change", description="App only: the card's Confirm button.", meta=APP_ONLY
    )
    async def confirm_change(pending_id: str, token: str, ctx: Context = None) -> CallToolResult:
        import anyio

        side, app = service.writer(), f"{app_name(ctx)} (button)"
        if side is None:
            return off()
        return result(await anyio.to_thread.run_sync(lambda: side.confirm(pending_id, token, app)))

    @server.tool(
        name="cancel_change", description="App only: the card's Cancel button.", meta=APP_ONLY
    )
    def cancel_change(pending_id: str, token: str) -> CallToolResult:
        side = service.writer()
        return off() if side is None else result(side.cancel(pending_id, token))

    @server.tool(name="undo_change", description="App only: the card's Undo button.", meta=APP_ONLY)
    async def undo_change(sha: str, token: str, ctx: Context = None) -> CallToolResult:
        import anyio

        side, app = service.writer(), f"{app_name(ctx)} (button)"
        if side is None:
            return off()
        return result(await anyio.to_thread.run_sync(lambda: side.undo(sha, token, app)))

    @server.resource(
        UI_URI,
        name="change-card",
        mime_type=UI_MIME,
        description="Lia's change card: Confirm, Cancel and Undo buttons.",
    )
    def change_card() -> str:
        return Path(__file__).with_name("change_card.html").read_text(encoding="utf-8")

    @server.prompt(
        name="talk-to-lia",
        description="Talk to Lia for the whole conversation: every message goes to her, and "
        "her replies are shown exactly as written.",
    )
    def talk_to_lia() -> str:
        return PROMPT_TEXT

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yggdras mcp", description="Lia as an MCP server")
    parser.add_argument("--brain", type=Path, help="brain repo (default: YGGDRAS_BRAIN)")
    parser.add_argument("--flat", type=Path, help="a flat demo brain root instead of a library")
    parser.add_argument("--model", help="Lia's model (default: YGGDRAS_LIA_MODEL)")
    parser.add_argument("--skills", type=Path, help="skills folder (default: <brain>/skills/lia)")
    args = parser.parse_args(argv)
    config.load_env_file()
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)  # no per-request lines on stderr
    brain = args.brain or config.brain_repo()
    if not (args.flat or brain):
        print("no brain: pass --brain or set YGGDRAS_BRAIN", file=sys.stderr)
        return 2
    skills = args.skills or (brain / "skills" / "lia" if brain else None)
    if not skills:
        print("no skills folder: pass --skills", file=sys.stderr)
        return 2
    from yggdras.interface import note_server
    from yggdras.processing.lia.models import AnthropicClient

    root = args.flat or brain / "library"
    port = config.notes_port()
    viewer = None if args.flat else note_server.build_viewer(root, config.local_data() / "viewer")
    service = LiaService(root, skills, AnthropicClient, flat=bool(args.flat),
                         model=args.model or config.lia_model())  # fmt: skip
    served = note_server.start(
        lambda: service.lia().library, port, viewer.parent if viewer else None
    )
    if served is not None:  # footnotes link to the note pages; if the port is taken, plain text
        service.config = default_config(
            service.model, f"http://{note_server.HOST}:{port}/note/{{slug}}#cite={{block}}"
        )
        service.note_url = f"http://{note_server.HOST}:{port}/note/{{slug}}"
    build_server(service).run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
