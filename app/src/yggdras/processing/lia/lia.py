"""Lia answers one question: cached manual and maps, two tools, cited answer, citation check."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from yggdras.data.maps import checks
from yggdras.processing.lia.library import Library, MapOptions
from yggdras.processing.lia.models import ModelClient

ABSTAIN = "Not in your brain."
MAX_TURNS = 8  # model calls per question, before the citation retry
MAX_SEARCHES = 3  # "look wider with new words", at most three rounds
CACHE = {"type": "ephemeral", "ttl": "1h"}

TOOLS = [
    {
        "name": "open_notes",
        "description": (
            "Open notes by slug, up to 10 in one call, and get each note's full text. Open every "
            "note that may hold the answer at once, never one by one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "slugs": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            },
            "required": ["slugs"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_notes",
        "description": (
            "Keyword search over every note's text, title, aliases and description. One ranked "
            "list: slug | score | snippet. Use it only when the maps and the opened notes don't "
            "give enough evidence; try new words each time. At most 3 searches per question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]
RETRY = (
    "These citations failed the check: each quoted line must be copied word for word from a "
    "fact line (or frontmatter field) of a note you opened.\n{failures}\n"
    "Write the whole answer again with corrected citations. Drop any claim you can't cite, "
    f'or reply exactly "{ABSTAIN}" with a one-line reason.'
)


@dataclass(frozen=True)
class LiaConfig:
    model: str = "claude-haiku-5-5"
    effort: str = "low"
    l0: bool = False  # E3
    neighbours: bool = False  # E8
    maps: MapOptions = field(default_factory=MapOptions)

    def as_dict(self) -> dict:
        return asdict(self)


def system_blocks(skills: str, library: Library, options: MapOptions) -> list[dict]:
    """[skills + taxonomy + node template] (breakpoint 1), then the maps (breakpoint 2).
    Fixed order and fixed bytes, so the prefix is identical on every call."""
    maps = library.maps(options)
    order = [
        k
        for k in (
            "atlas.md",
            "shelf-map.md",
            "relationship-map.md",
            "atlas.json",
            "shelf-map.json",
            "relationship-map.json",
        )
        if k in maps
    ]
    return [
        {
            "type": "text",
            "text": f"{skills.strip()}\n\n{library.manual().strip()}",
            "cache_control": CACHE,
        },
        {
            "type": "text",
            "text": "\n\n".join(f"<{k}>\n{maps[k].strip()}\n</{k}>" for k in order),
            "cache_control": CACHE,
        },
    ]


def load_skills(folder: Path) -> str:
    files = sorted(folder.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"no skills in {folder}")
    return "\n\n".join(p.read_text(encoding="utf-8").strip() for p in files)


def is_abstain(text: str) -> bool:
    return text.strip().startswith(ABSTAIN)


def mark_unverified(text: str, failed: list[checks.Citation]) -> str:
    for c in failed:
        for pattern in (f'[[{c.slug}]] "{c.quote}"', f"[[{c.slug}]] {c.quote}"):
            text = text.replace(pattern, pattern + " [unverified]", 1)
    return text


class Lia:
    def __init__(self, client: ModelClient, library: Library, skills: str, config: LiaConfig):
        self.client, self.library, self.config = client, library, config
        self.system = system_blocks(skills, library, config.maps)

    def ask(self, question: str, qid: str = "q") -> dict:
        start = time.perf_counter()
        steps, calls, opened = [], [], {}
        content = []
        if self.config.l0:
            slugs = self.library.l0_matches(question)
            if slugs:
                text, done = self.library.open_notes(slugs, self.config.neighbours)
                opened.update({s: self.library.note_text(s) for s in done})
                content.append(
                    {
                        "type": "text",
                        "text": f"Opened before you start (exact name match):\n\n{text}",
                    }
                )
                steps.append({"tool": "l0", "input": {"slugs": slugs}, "returned": done})
        content.append({"type": "text", "text": f"Question: {question}"})
        messages = [{"role": "user", "content": content}]
        searches, reply = 0, None
        for _ in range(MAX_TURNS):
            reply = self.client.send(system=self.system, tools=TOOLS, messages=messages)
            calls.append(reply.usage.as_dict())
            messages.append(
                {
                    "role": "assistant",
                    "content": reply.content if reply.content is not None else reply.blocks,
                }
            )
            if reply.stop_reason != "tool_use":
                break
            results = []
            for call in reply.tool_calls:
                name, args = call["name"], call.get("input", {})
                if name == "open_notes":
                    text, done = self.library.open_notes(
                        list(args.get("slugs", [])), self.config.neighbours
                    )
                    opened.update({s: self.library.note_text(s) for s in done})
                    steps.append({"tool": name, "input": args, "returned": done})
                elif name == "search_notes" and searches < MAX_SEARCHES:
                    searches += 1
                    text = self.library.search_notes(
                        str(args.get("query", "")), int(args.get("k", 10))
                    )
                    steps.append({"tool": name, "input": args, "returned": text.splitlines()[:20]})
                elif name == "search_notes":
                    text = "Search limit reached (3 per question). Answer from what you have."
                    steps.append({"tool": name, "input": args, "returned": "limit"})
                else:
                    text = f"Unknown tool {name}."
                results.append({"type": "tool_result", "tool_use_id": call["id"], "content": text})
            messages.append({"role": "user", "content": results})
        if reply is not None and reply.stop_reason == "tool_use":
            # Out of turns while still calling tools: one last call, tools off.
            messages[-1]["content"].append(
                {"type": "text", "text": "Tool limit reached: answer now from what you have."}
            )
            reply = self.client.send(
                system=self.system, tools=TOOLS, messages=messages, tool_choice={"type": "none"}
            )
            calls.append(reply.usage.as_dict())
            messages.append(
                {
                    "role": "assistant",
                    "content": reply.content if reply.content is not None else reply.blocks,
                }
            )
        answer = reply.text.strip() if reply else ""
        cites = [] if is_abstain(answer) else checks.check_citations(answer, opened)
        failed = [c for c in cites if not c.ok]
        retried = False
        if failed:
            retried = True
            lines = "\n".join(f'- [[{c.slug}]] "{c.quote}": {c.reason}' for c in failed)
            messages.append({"role": "user", "content": RETRY.format(failures=lines)})
            reply = self.client.send(system=self.system, tools=TOOLS, messages=messages)
            calls.append(reply.usage.as_dict())
            answer = reply.text.strip()
            cites = [] if is_abstain(answer) else checks.check_citations(answer, opened)
            failed = [c for c in cites if not c.ok]
        shown = mark_unverified(answer, failed)
        return {
            "id": qid,
            "question": question,
            "config": self.config.as_dict(),
            "map_version": self.library.version,
            "steps": steps,
            "opened": sorted(opened),
            "answer": shown,
            "abstain": is_abstain(answer),
            "citations": [asdict(c) for c in cites],
            "citation_check": {"total": len(cites), "failed": len(failed), "retried": retried},
            "searches": searches,
            "calls": calls,
            "cost_usd": sum(c["cost_usd"] for c in calls),
            "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        }


def write_trace(result: dict, folder: Path) -> Path:
    """One JSON trace per question: question, steps, answer, citations, check, tokens, cost."""
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", result["id"])
    path = folder / f"{safe}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
