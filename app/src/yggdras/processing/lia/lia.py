"""Lia answers one question from the brain's notes, with cited facts, in her own voice.

One fixed behaviour (D35), no switches:
- the cached prompt: the core skill and the skill index, the taxonomy and node template, then
  her maps (atlas, shelf map);
- the effort rule picks the model: Haiku for simple and medium questions, Sonnet for complex;
- tools: open_notes, search_notes (fact-level), load_skill (at most two playbooks) and
  checklist (each loaded playbook's "done when" list, before the answer);
- complex questions get unopened-candidate hints with the first open_notes; advice and timing
  questions get the upcoming view;
- free checks after the draft: the sibling sweep (medium and complex), then citations, claim
  support, absence claims, write offers and draft talk, all in one retry; whatever still
  fails is marked.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from yggdras.data.maps import checks
from yggdras.processing.lia import effort as effort_mod
from yggdras.processing.lia import search, verify
from yggdras.processing.lia import skills as skill_mod
from yggdras.processing.lia.library import Library
from yggdras.processing.lia.models import ModelClient

ABSTAIN = "I don't have that in your notes yet."
OLD_ABSTAIN = "Not in your brain."  # v1 and v2; still recognised
MAX_TURNS = 10  # model calls per question, before the checks
MAX_SEARCHES = 3  # "look wider with new words", at most three rounds
CACHE = {"type": "ephemeral", "ttl": "1h"}
DEFAULT_MODEL = "claude-haiku-5-5"
COMPLEX_MODEL = "claude-sonnet-5-5"

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
            "Keyword search over every fact line, title, alias and description, with word forms "
            "and the brain's aliases matched. One ranked list: slug | score | fact line. Use it "
            "when the maps and the opened notes don't give enough evidence, and before you say "
            "something isn't in the notes; try new words each time. At most 3 per question."
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
    skill_mod.LOAD_SKILL_TOOL,
    skill_mod.CHECKLIST_TOOL,
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
    "Drop any claim you can't cite, "
    f'or reply exactly "{ABSTAIN}" with a one-line reason.'
)
FRESH = (
    "Write the whole answer again, from scratch, as if for the first time. Never mention "
    "drafts, retries, checks or corrections in it."
)


@dataclass(frozen=True)
class LiaConfig:
    model: str = DEFAULT_MODEL  # simple and medium questions
    complex_model: str = COMPLEX_MODEL  # complex questions (the effort rule)
    effort: str = "low"
    owner_names: tuple[str, ...] = ()  # the voice check: Lia says "you", never these names
    today: str | None = None  # the upcoming view's "today" (ISO date); None is the real date
    horizon_days: int = 120

    def as_dict(self) -> dict:
        return asdict(self)


def system_blocks(skills: str, library: Library) -> list[dict]:
    """[core skill + skill index + taxonomy + node template] (breakpoint 1), then the maps
    (breakpoint 2). Fixed order and fixed bytes, so the prefix is identical on every call."""
    maps = library.maps()
    return [
        {
            "type": "text",
            "text": f"{skills.strip()}\n\n{library.manual().strip()}",
            "cache_control": CACHE,
        },
        {
            "type": "text",
            "text": "\n\n".join(f"<{k}>\n{maps[k].strip()}\n</{k}>" for k in maps),
            "cache_control": CACHE,
        },
    ]


def with_cache_tail(messages: list) -> list:
    """A copy of *messages* whose newest user block carries a 5-minute cache breakpoint, so each
    call reads the conversation so far from the cache (the system blocks keep their 1-hour ones)."""
    if not messages or messages[-1]["role"] != "user":
        return messages
    last = dict(messages[-1])
    content = last["content"]
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
    if not blocks:
        return messages
    blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
    last["content"] = blocks
    return [*messages[:-1], last]


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
    """One question at a time. *client* answers simple and medium questions; *complex_client*,
    when given, takes complex ones from the first call. *playbooks* is the skill library
    (skills.load_library): its core skill and index go into the cached prompt."""

    def __init__(
        self,
        client: ModelClient,
        library: Library,
        playbooks: dict[str, skill_mod.Skill],
        config: LiaConfig,
        complex_client: ModelClient | None = None,
    ):
        self.client, self.library, self.config = client, library, config
        self.complex_client = complex_client
        self.playbooks = playbooks
        self.system = system_blocks(skill_mod.system_text(playbooks), library)
        self.tools = TOOLS

    def _assistant(self, messages: list, reply) -> None:
        content = reply.content if reply.content is not None else reply.blocks
        messages.append({"role": "assistant", "content": content})

    def _upcoming(self) -> str:
        today = dt.date.fromisoformat(self.config.today) if self.config.today else dt.date.today()
        return self.library.upcoming(today, self.config.horizon_days)

    def _tool(self, call: dict, state: dict) -> str:
        name, args = call["name"], call.get("input", {})
        step = {"tool": name, "input": args, "turn": state["turn"]}
        if name == "open_notes":
            text, done = self.library.open_notes(list(args.get("slugs", [])))
            state["opened"].update({s: self.library.note_text(s) for s in done})
            state["steps"].append({**step, "returned": done})
            if state["effort"] == "complex" and not state["hints_given"]:
                text += self._hints(state)
            return text
        if name == "search_notes":
            if state["searches"] >= MAX_SEARCHES:
                state["steps"].append({**step, "returned": "limit"})
                return (
                    f"Search limit reached ({MAX_SEARCHES} per question). "
                    "Answer from what you have."
                )
            state["searches"] += 1
            text = self.library.search_notes(str(args.get("query", "")), int(args.get("k", 10)))
            state["steps"].append({**step, "returned": text.splitlines()[:20]})
            return text
        if name == "load_skill":
            room = skill_mod.MAX_LOAD - len(state["skills_loaded"])
            names = [n for n in args.get("names", []) if n not in state["skills_loaded"]][:room]
            if not names:
                return f"At most {skill_mod.MAX_LOAD} skills per question; none more were loaded."
            text, done = skill_mod.loaded_text(self.playbooks, names)
            state["skills_loaded"].extend(done)
            state["steps"].append({**step, "returned": done})
            return text
        if name == "checklist":
            items = list(args.get("items", []))
            text, complete = skill_mod.checklist_reply(
                items, state["skills_loaded"], self.playbooks, len(state["checklists"])
            )
            state["checklists"].append(items)
            state["checklist_complete"] = complete
            state["steps"].append({**step, "returned": text[:200]})
            return text
        return f"Unknown tool {name}."

    def _hints(self, state: dict) -> str:
        """Complex questions, once: shelf rows not opened yet that share a key term with the
        question (alias-expanded)."""
        state["hints_given"] = True
        words = list(search.expansions(state["question"], self.library.notes))
        rows = self.library.candidates(words, set(state["opened"]))
        state["hints"] = [n.slug for n in rows]
        if not rows:
            return ""
        lines = "\n".join(f"{n.slug} | {n.type} | {n.name} | {n.description}" for n in rows)
        return f"\n\nConsider these before answering (notes you haven't opened):\n{lines}"

    def _loop(self, messages: list, state: dict):
        """Call the model until it stops using tools (at most MAX_TURNS calls)."""
        client = state["client"]
        reply = None
        for _ in range(MAX_TURNS):
            state["turn"] += 1
            reply = client.send(
                system=self.system, tools=self.tools, messages=with_cache_tail(messages)
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
        reply = client.send(
            system=self.system, tools=self.tools, messages=messages, tool_choice={"type": "none"}
        )
        state["calls"].append(reply.usage.as_dict())
        self._assistant(messages, reply)
        return reply

    def _again(self, messages: list, state: dict, prompt: str) -> str:
        messages.append({"role": "user", "content": prompt})
        return self._loop(messages, state).text.strip()

    def _checks(self, answer: str, cites: list, opened: dict) -> tuple[list, list, list, list]:
        cited = {(c.slug, checks.quote_unit(c.quote)) for c in cites if c.ok}
        return (
            verify.write_offers(answer),
            verify.check_absences(answer, self.library, cited),
            verify.check_support(answer, opened, self.library.notes),
            verify.leaks(answer),
        )

    def ask(self, question: str, qid: str = "q", context: str = "") -> dict:
        """*context*: the last turns of a chat, to resolve "that" or "she"; never a source."""
        start = time.perf_counter()
        level, reason = effort_mod.effort_of(question, self.library)
        complex_q = level == "complex" and self.complex_client is not None
        state = {
            "steps": [],
            "calls": [],
            "opened": {},
            "searches": 0,
            "question": question,
            "effort": level,
            "turn": 0,
            "client": self.complex_client if complex_q else self.client,
            "hints_given": False,
            "hints": [],
            "skills_loaded": [],
            "checklists": [],
            "checklist_complete": None,
        }
        content = []
        if context.strip():
            intro = "Recent conversation, only to understand the question (not a source of facts):"
            content.append({"type": "text", "text": f"{intro}\n\n{context.strip()}"})
        upcoming = effort_mod.wants_upcoming(question)
        if upcoming:
            content.append(
                {"type": "text", "text": f"<upcoming.md>\n{self._upcoming()}</upcoming.md>"}
            )
        content.append({"type": "text", "text": f"Question: {question}"})
        messages = [{"role": "user", "content": content}]
        reply = self._loop(messages, state)
        answer = reply.text.strip() if reply else ""
        if state["skills_loaded"] and not state["checklists"]:
            # The loaded playbooks' "done when" lists come before the answer.
            answer = self._again(messages, state, skill_mod.CHECKLIST_NUDGE)
        abstain_search = False
        if is_abstain(answer) and state["searches"] == 0:
            # Search with the question's key terms and open the top hits before abstaining.
            abstain_search = True
            answer = self._again(messages, state, ABSTAIN_SEARCH)
        opened = state["opened"]
        sibling_lines, sibling_phrases = [], []
        if level != "simple" and not is_abstain(answer):
            draft = checks.check_citations(answer, opened)
            sibling_lines, sibling_phrases = search.siblings(draft, self.library)
            if sibling_lines:
                for slug, _ in sibling_lines:
                    opened.setdefault(slug, self.library.note_text(slug))
                lines = "\n".join(f"- [[{s}]] {f}" for s, f in sibling_lines)
                answer = self._again(messages, state, search.SIBLINGS_PROMPT.format(lines=lines))
        # Every free check runs on every answer, abstains included, and shares one retry.
        cites = checks.check_citations(answer, opened)
        failed = [c for c in cites if not c.ok]
        offers, absent, unsupported, leaked = self._checks(answer, cites, opened)
        first_check = {
            "absence_fired": len(verify.absence_claims(answer)),
            "absence_found": len(absent),
            "unsupported": [u.sentence for u in unsupported],
            "leaks": leaked,
            "write_offers": offers,
        }
        retried = bool(failed or offers or absent or unsupported or leaked)
        if retried:
            parts = []
            if failed:
                lines = "\n".join(f"- [[{c.slug}]] «{c.quote}»: {c.reason}" for c in failed)
                parts.append(RETRY.format(failures=lines))
            if offers:
                parts.append(verify.CAPABILITY_RETRY)
            for a in absent:
                hits = "\n".join(f"- [[{s}]] {f}" for s, f in a.hits)
                parts.append(
                    f'You wrote "{a.sentence}", but these lines mention it. Use them if they '
                    f"answer it, and keep the sentence only if they don't:\n{hits}"
                )
            for u in unsupported:
                parts.append(
                    f'"{u.sentence}" is not supported by the line it cites (missing: '
                    f"{', '.join(u.missing)}). Cite the line that states it, or drop the claim."
                )
            parts.append(FRESH)
            answer = self._again(messages, state, "\n\n".join(parts))
            cites = checks.check_citations(answer, opened)
            failed = [c for c in cites if not c.ok]
            offers, absent, unsupported, leaked = self._checks(answer, cites, opened)
        answer = verify.strip_leaks(answer)
        for a in absent:
            answer = verify.mark(answer, a.sentence, "[unverified absence]")
        for u in unsupported:
            answer = verify.mark(answer, u.sentence, "[unsupported]")
        return {
            "id": qid,
            "question": question,
            "config": self.config.as_dict(),
            "map_version": self.library.version,
            "steps": state["steps"],
            "opened": sorted(opened),
            "answer": mark_unverified(answer, failed),
            "abstain": is_abstain(answer),
            "third_person": checks.third_person(answer, self.config.owner_names),
            "citations": [asdict(c) for c in cites],
            "citation_check": {"total": len(cites), "failed": len(failed), "retried": retried},
            "searches": state["searches"],
            "abstain_search": abstain_search,
            "effort": level,
            "effort_reason": reason,
            "model": state["client"].model,
            "escalated": complex_q,
            "upcoming_loaded": upcoming,
            "hints": state["hints"],
            "siblings": {"phrases": sibling_phrases, "lines": [list(x) for x in sibling_lines]},
            "skills_loaded": state["skills_loaded"],
            "skill_turns": sorted({s["turn"] for s in state["steps"] if s["tool"] == "load_skill"}),
            "first_open_turn": next(
                (s["turn"] for s in state["steps"] if s["tool"] == "open_notes"), None
            ),
            "checklists": state["checklists"],
            "checklist_complete": state["checklist_complete"],
            "write_offers": offers,
            "checks": {
                "first": first_check,
                "absence_left": [a.sentence for a in absent],
                "unsupported_left": [u.sentence for u in unsupported],
            },
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


def default_lia(
    library: Library, skills_dir: Path, client_factory, config: LiaConfig | None = None
) -> Lia:
    """Lia as the connector, the CLI and the eval harness all build her: the skill library
    from *skills_dir* (core.md + library/), *client_factory(model)* for each model."""
    config = config or LiaConfig()
    playbooks = skill_mod.load_library(skills_dir)
    return Lia(
        client_factory(config.model),
        library,
        playbooks,
        config,
        complex_client=client_factory(config.complex_model),
    )
