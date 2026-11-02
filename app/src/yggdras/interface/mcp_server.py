"""Lia as a read-only MCP server (stdio), for Claude Desktop and Claude Code.

    yggdras mcp [--brain REPO] [--flat ROOT] [--model M] [--skills DIR]

Two tools, ask_lia (Lia's reply, first person, footnoted) and open_note (one note, to check a
citation), and one prompt, talk-to-lia (every message goes to Lia, shown verbatim). The
server reads the brain's current files and rebuilds Lia's maps whenever a note changes. It
never writes to the brain; every answer leaves a trace in local-data/traces/. Write tools and
the Approve buttons (D33) come later.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from yggdras import config

VERBATIM = "Show the following reply exactly as written, with no preface, summary or extra facts."
INSTRUCTIONS = (
    "Yggdras is the user's personal second brain, and Lia is its librarian. Send every question "
    "about the user's own life, work, studies, plans, people, places or decisions to ask_lia. "
    "Lia speaks to the user herself, in the first person. Show her reply exactly as written, "
    "footnotes ([1] [[slug]] «fact») and the closing line included, with no preface, summary "
    "or extra facts. Never add facts of your own, never fill a gap from general knowledge, and "
    "never present a guess as something the brain holds. Use open_note when the user wants to "
    "check a citation. These tools only read the brain."
)
ASK_DESCRIPTION = (
    "Ask Lia, the librarian of the user's second brain, a question about the user's own life, "
    "work, studies, plans, people, places or decisions. Pass the user's message as question; "
    "optionally pass the last two turns of the chat as context, so she can resolve words like "
    "'that' or 'she'. She replies to the user in the first person, with numbered footnotes "
    "([1] [[slug]] «fact text», each checked word for word against the note), or says she "
    "doesn't have it in the notes yet. Show her reply exactly as written, with no preface, "
    "summary or extra facts; never answer from your own knowledge. Read-only."
)
PROMPT_TEXT = (
    "For the rest of this conversation you are a window onto Lia, the librarian of my second "
    "brain. For every message I send, call ask_lia with my message as question and the last "
    "two turns of our conversation as context. Reply with her answer exactly as written, "
    "footnotes and closing line included, with no preface, summary or extra facts. Never "
    "answer from your own knowledge, even when you could. If I ask to check a citation, call "
    "open_note with its slug and show the note."
)
OPEN_DESCRIPTION = (
    "Open one note of the user's second brain by its slug (the part inside [[...]] in Lia's "
    "citations) and return its full text, so a citation can be checked. Read-only."
)


def default_config(model: str):
    """The tested final config (lia-v1): shelf map only, descriptions cut at 25 words."""
    from yggdras.processing.lia.lia import LiaConfig
    from yggdras.processing.lia.library import MapOptions

    return LiaConfig(
        model=model,
        maps=MapOptions(relationship=False, inverses=False, about_words=25),
        owner_names=config.owner_names(),
    )


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
    ):
        self.root, self.skills, self.flat, self.model = root, skills, flat, model
        self.client_factory = client_factory
        self.traces = traces or config.local_data() / "traces"
        self._lock = threading.Lock()
        self._lia, self._print = None, None

    def lia(self):
        from yggdras.processing.lia.lia import Lia, load_skills
        from yggdras.processing.lia.library import Library

        with self._lock:
            now = fingerprint(self.root, self.skills)
            if self._lia is None or now != self._print:
                library = Library(self.root, flat=self.flat)
                self._lia = Lia(
                    self.client_factory(self.model),
                    library,
                    load_skills(self.skills),
                    default_config(self.model),
                )
                self._print = now
            return self._lia

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
        check = result["citation_check"]
        footer = (
            f"— Lia · ${result['cost_usd']:.4f} · {result['latency_ms'] / 1000:.1f} s · "
            f"✓ {check['total'] - check['failed']}/{check['total']}"
        )
        return f"{VERBATIM}\n\n{result['answer']}\n\n{footer}"

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

    @server.prompt(
        name="talk-to-lia",
        description="Talk to Lia for the whole conversation: every message goes to her, and "
        "her replies are shown exactly as written.",
    )
    def talk_to_lia() -> str:
        return PROMPT_TEXT

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yggdras mcp", description="Lia as a read-only MCP server"
    )
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
    from yggdras.processing.lia.models import AnthropicClient

    service = LiaService(
        args.flat or brain / "library",
        skills,
        AnthropicClient,
        flat=bool(args.flat),
        model=args.model or config.lia_model(),
    )
    build_server(service).run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
