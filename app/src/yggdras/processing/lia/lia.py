"""Lia answers one question: cached manual and maps, two tools, cited answer, citation check."""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from yggdras.data.maps import checks
from yggdras.processing.lia import explore
from yggdras.processing.lia.library import Library, MapOptions
from yggdras.processing.lia.models import ModelClient

ABSTAIN = "I don't have that in your notes yet."  # v3 voice
OLD_ABSTAIN = "Not in your brain."  # v1 and v2
MAX_TURNS = 8  # model calls per question, before the citation retry
EXPLORE_TURNS = 12  # with plan and coverage rounds (F1, F2)
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
ABSTAIN_SEARCH = (
    f'Before you answer "{ABSTAIN}", run search_notes with the question\'s key terms '
    "and open the top hits. Then answer from them, or abstain if they don't support an answer."
)
RETRY = (
    "These citations failed the check: each footnote must quote a fact's text word for word "
    '(everything after "- " and before " (src:", tags included), as [n] [[slug]] «fact text», '
    "or a frontmatter field as [n] [[slug]] field: value, from a note you opened, and every "
    "marker [n] in the text needs its footnote.\n{failures}\n"
    "Write the whole answer again with corrected citations. Drop any claim you can't cite, "
    f'or reply exactly "{ABSTAIN}" with a one-line reason.'
)


@dataclass(frozen=True)
class LiaConfig:
    model: str = "claude-haiku-5-5"
    effort: str = "low"
    l0: bool = False  # E3
    neighbours: bool = False  # E8
    answer_model: str | None = None  # E6: a second model writes the answer
    maps: MapOptions = field(default_factory=MapOptions)
    owner_names: tuple[str, ...] = ()  # the voice check: Lia says "you", never these names
    # Explore (F1–F7): every switch off is the v3 baseline.
    plan: bool = False  # F1: facets, sub-questions and effort before opening anything
    coverage: bool = False  # F2: grade coverage, then search again (capped by effort)
    siblings: bool = False  # F3: free sweep for facts sharing a key phrase
    verdict: bool = False  # F4: sufficiency verdict before writing (always on when exploring)
    capability: bool = False  # F5: no offers to write (always on when exploring)
    upcoming: bool = False  # F6: the upcoming view for complex or time questions
    escalate: str | None = None  # F7: this model takes over complex questions
    today: str | None = None  # F6: "today" (ISO date); None is the real date
    horizon_days: int = 120

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def exploring(self) -> bool:
        return any((self.plan, self.coverage, self.siblings, self.verdict, self.capability))


def explore_config(base: LiaConfig, **switches) -> LiaConfig:
    """F1–F6 on (F7 off), with *switches* overriding single ones (the ablations)."""
    on = dict(plan=True, coverage=True, siblings=True, verdict=True, capability=True)
    return replace(base, **{**on, "upcoming": True, **switches})


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


EXPLORE_SKILL = "explore.md"  # loaded only when an explore switch is on


def load_skills(folder: Path, explore: bool = True) -> str:
    files = sorted(p for p in folder.glob("*.md") if explore or p.name != EXPLORE_SKILL)
    if not files:
        raise FileNotFoundError(f"no skills in {folder}")
    return "\n\n".join(p.read_text(encoding="utf-8").strip() for p in files)


def is_abstain(text: str) -> bool:
    return text.strip().startswith((ABSTAIN, OLD_ABSTAIN))


def mark_unverified(text: str, failed: list[checks.Citation]) -> str:
    for c in failed:
        if c.slug:
            patterns = [f"[[{c.slug}]] «{c.quote}»", f"[[{c.slug}]] {c.quote}"]
        elif checks.MARKER.fullmatch(c.quote):
            patterns = [c.quote]  # a footnote marker with no footnote
        else:
            patterns = [f"«{c.quote}»"]
        for pattern in patterns:
            text = text.replace(pattern, pattern + " [unverified]", 1)
    return text


class Lia:
    """One question at a time. With *answer_client* (E6), *client* routes (opens and searches)
    and *answer_client* writes the answer from the same context. With *escalate_client* (F7),
    that client takes over once the plan says the question is complex."""

    def __init__(
        self,
        client: ModelClient,
        library: Library,
        skills: str,
        config: LiaConfig,
        answer_client: ModelClient | None = None,
        escalate_client: ModelClient | None = None,
    ):
        self.client, self.library, self.config = client, library, config
        self.answer_client, self.escalate_client = answer_client, escalate_client
        self.system = system_blocks(skills, library, config.maps)
        self.tools = TOOLS + ([explore.PLAN_TOOL] if config.plan else [])
        if config.coverage or config.verdict:
            self.tools = self.tools + [explore.COVERAGE_TOOL]

    def _assistant(self, messages: list, reply) -> None:
        content = reply.content if reply.content is not None else reply.blocks
        messages.append({"role": "assistant", "content": content})

    def _upcoming(self) -> str:
        today = dt.date.fromisoformat(self.config.today) if self.config.today else dt.date.today()
        return self.library.upcoming(today, self.config.horizon_days)

    def _search_cap(self, state: dict) -> int:
        if not (self.config.plan or self.config.coverage):
            return MAX_SEARCHES
        return explore.SEARCHES[state["effort"]]

    def _tool(self, call: dict, state: dict) -> str:
        name, args = call["name"], call.get("input", {})
        if name == "open_notes":
            text, done = self.library.open_notes(
                list(args.get("slugs", [])), self.config.neighbours
            )
            state["opened"].update({s: self.library.note_text(s) for s in done})
            state["steps"].append({"tool": name, "input": args, "returned": done})
            return text
        if name == "search_notes" and state["searches"] < self._search_cap(state):
            state["searches"] += 1
            text = self.library.search_notes(str(args.get("query", "")), int(args.get("k", 10)))
            state["steps"].append({"tool": name, "input": args, "returned": text.splitlines()[:20]})
            return text
        if name == "search_notes":
            state["steps"].append({"tool": name, "input": args, "returned": "limit"})
            cap = self._search_cap(state)
            return f"Search limit reached ({cap} per question). Answer from what you have."
        if name == "plan" and self.config.plan:
            return self._plan(args, state)
        if name == "coverage" and (self.config.coverage or self.config.verdict):
            text, again = explore.coverage_result(
                args, state["effort"], state["coverage_rounds"], self.config.coverage
            )
            state["coverage_rounds"] += again
            state["coverage"].append({**args, "corrective_round": again})
            state["verdict"] = args.get("verdict")
            state["steps"].append({"tool": name, "input": args, "returned": text[:200]})
            return text
        return f"Unknown tool {name}."

    def _plan(self, args: dict, state: dict) -> str:
        state["plan"] = args
        state["effort"] = explore.normalise_effort(args.get("effort"))
        if state["effort"] == "complex" and self.escalate_client is not None:
            state["client"] = self.escalate_client
        timely = explore.TIME_WORDS.search(state["question"])
        view = None
        if self.config.upcoming and (state["effort"] == "complex" or timely):
            view = self._upcoming()
            state["upcoming_loaded"] = True
        text = explore.plan_result(args, self.library, state["question"], view)
        state["steps"].append({"tool": "plan", "input": args, "returned": text[:300]})
        return text

    def _loop(self, client: ModelClient, messages: list, state: dict, first: dict | None = None):
        """Call the client until it stops using tools (MAX_TURNS calls, or EXPLORE_TURNS). After F7
        escalates, the escalated client takes every later call."""
        reply = None
        for turn in range(EXPLORE_TURNS if self.config.exploring else MAX_TURNS):
            active = state.get("client") or client
            choice = first if turn == 0 else None
            reply = active.send(
                system=self.system, tools=self.tools, messages=messages, tool_choice=choice
            )
            state["calls"].append(reply.usage.as_dict())
            self._assistant(messages, reply)
            if reply.stop_reason != "tool_use":
                return reply
            results = [
                {"type": "tool_result", "tool_use_id": c["id"], "content": self._tool(c, state)}
                for c in reply.tool_calls
            ]
            messages.append({"role": "user", "content": results})
        # Out of turns while still calling tools: one last call, tools off.
        messages[-1]["content"].append(
            {"type": "text", "text": "Tool limit reached: answer now from what you have."}
        )
        active = state.get("client") or client
        reply = active.send(
            system=self.system, tools=self.tools, messages=messages, tool_choice={"type": "none"}
        )
        state["calls"].append(reply.usage.as_dict())
        self._assistant(messages, reply)
        return reply

    def _again(self, writer, messages: list, state: dict, prompt: str) -> str:
        messages.append({"role": "user", "content": prompt})
        reply = self._loop(writer, messages, state)
        return reply.text.strip()

    def ask(self, question: str, qid: str = "q", context: str = "") -> dict:
        """*context*: the last turns of a chat, to resolve "that" or "she"; never a source."""
        start = time.perf_counter()
        cfg = self.config
        state = {
            "steps": [],
            "calls": [],
            "opened": {},
            "searches": 0,
            "question": question,
            "effort": explore.DEFAULT_EFFORT,
            "plan": None,
            "coverage": [],
            "coverage_rounds": 0,
            "verdict": None,
        }
        content = []
        if cfg.l0:
            slugs = self.library.l0_matches(question)
            if slugs:
                text, done = self.library.open_notes(slugs, cfg.neighbours)
                state["opened"].update({s: self.library.note_text(s) for s in done})
                intro = "Opened before you start (exact name match):"
                content.append({"type": "text", "text": f"{intro}\n\n{text}"})
                state["steps"].append({"tool": "l0", "input": {"slugs": slugs}, "returned": done})
        if context.strip():
            intro = "Recent conversation, only to understand the question (not a source of facts):"
            content.append({"type": "text", "text": f"{intro}\n\n{context.strip()}"})
        if cfg.upcoming and not cfg.plan and explore.TIME_WORDS.search(question):
            content.append(
                {"type": "text", "text": f"<upcoming.md>\n{self._upcoming()}</upcoming.md>"}
            )
            state["upcoming_loaded"] = True
        content.append({"type": "text", "text": f"Question: {question}"})
        messages = [{"role": "user", "content": content}]
        first = {"type": "tool", "name": "plan"} if cfg.plan else None
        reply = self._loop(self.client, messages, state, first)
        writer = self.client
        if self.answer_client is not None:
            messages.pop()  # the router's own answer is dropped; the answer model writes it
            if messages[-1]["role"] == "assistant":
                messages.pop()
            if messages[-1]["role"] != "user":
                messages.append({"role": "user", "content": "Answer the question now."})
            reply = self._loop(self.answer_client, messages, state)
            writer = self.answer_client
        answer = reply.text.strip() if reply else ""
        if (cfg.coverage or cfg.verdict) and not state["coverage"]:
            # F4: no answer is written before a sufficiency verdict.
            answer = self._again(writer, messages, state, explore.COVERAGE_NUDGE)
        abstain_search = False
        if is_abstain(answer) and state["searches"] == 0:
            # Abstain rule: search with the question's key terms and open the top hits first.
            abstain_search = True
            answer = self._again(writer, messages, state, ABSTAIN_SEARCH)
        opened = state["opened"]
        sibling_lines, sibling_phrases = [], []
        if cfg.siblings and not is_abstain(answer):
            draft = checks.check_citations(answer, opened)
            sibling_lines, sibling_phrases = explore.siblings(draft, self.library)
            if sibling_lines:
                for slug, _ in sibling_lines:
                    opened.setdefault(slug, self.library.note_text(slug))
                lines = "\n".join(f"- [[{s}]] {f}" for s, f in sibling_lines)
                answer = self._again(
                    writer, messages, state, explore.SIBLINGS_PROMPT.format(lines=lines)
                )
        # The citation check runs on every answer, abstains included.
        cites = checks.check_citations(answer, opened)
        failed = [c for c in cites if not c.ok]
        offers = explore.write_offers(answer) if cfg.capability else []
        retried = False
        if failed or offers:
            retried = True
            parts = []
            if failed:
                lines = "\n".join(f"- [[{c.slug}]] «{c.quote}»: {c.reason}" for c in failed)
                parts.append(RETRY.format(failures=lines))
            if offers:
                parts.append(explore.CAPABILITY_RETRY)
            answer = self._again(writer, messages, state, "\n\n".join(parts))
            cites = checks.check_citations(answer, opened)
            failed = [c for c in cites if not c.ok]
            offers = explore.write_offers(answer) if cfg.capability else []
        return {
            "id": qid,
            "question": question,
            "config": cfg.as_dict(),
            "map_version": self.library.version,
            "steps": state["steps"],
            "opened": sorted(opened),
            "answer": mark_unverified(answer, failed),
            "abstain": is_abstain(answer),
            "third_person": checks.third_person(answer, cfg.owner_names),
            "citations": [asdict(c) for c in cites],
            "citation_check": {"total": len(cites), "failed": len(failed), "retried": retried},
            "searches": state["searches"],
            "abstain_search": abstain_search,
            "plan": state["plan"],
            "effort": state["effort"] if cfg.plan else None,
            "escalated": state.get("client") is not None,
            "coverage": state["coverage"],
            "verdict": state["verdict"],
            "siblings": {"phrases": sibling_phrases, "lines": [list(x) for x in sibling_lines]},
            "upcoming_loaded": state.get("upcoming_loaded", False),
            "write_offers": offers,
            "calls": state["calls"],
            "cost_usd": sum(c["cost_usd"] for c in state["calls"]),
            "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        }


def write_trace(result: dict, folder: Path) -> Path:
    """One JSON trace per question: question, steps, answer, citations, check, tokens, cost."""
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", result["id"])
    path = folder / f"{safe}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
