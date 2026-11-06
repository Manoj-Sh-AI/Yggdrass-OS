"""Lia answers one question from the brain's notes, with cited facts, in her own voice.

One fixed behaviour (D35), no switches:
- the cached prompt: the core skill and the skill index, the taxonomy and node template, then
  her maps (atlas, shelf map);
- the effort rule picks the model: Haiku for simple and medium questions, Sonnet for complex;
- tools: open_notes and search_notes return notes as search_result blocks with native
  citations, so Lia cites lines by pointer and code renders the footnotes from the cited
  blocks; load_skill loads at most two playbooks;
- she ends her reply with a hidden <done verdict=… checklist=…/> line: her sufficiency verdict
  and each loaded playbook's "done when" list, recorded in the trace, never shown;
- complex questions get unopened-candidate hints with the first open_notes; advice and timing
  questions get the upcoming view;
- free checks after the draft: the sibling sweep (medium and complex); before any abstain, a
  fact-level search of the question; then claim support, absence claims, write offers and
  draft talk, all in one retry; whatever still fails is marked. An empty reply is asked for
  once more, then reported as an error, never shown as an empty answer.
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
from yggdras.processing.lia.library import Block, Library, search_result
from yggdras.processing.lia.models import ModelClient

ABSTAIN = "I don't have that in your notes yet."
OLD_ABSTAIN = "Not in your brain."  # v1 and v2; still recognised
EMPTY_ERROR = "Lia couldn't put an answer together this time. Please ask again."
MAX_TURNS = 10  # model calls per question, before the checks
MAX_SEARCHES = 3  # "look wider with new words", at most three rounds
CACHE = {"type": "ephemeral", "ttl": "1h"}
RUNAWAY_USD = 1.0  # not a cap: past this, one question stops reading and answers with what it has
DEFAULT_MODEL = "claude-haiku-5-5"
COMPLEX_MODEL = "claude-sonnet-5-5"
# The hidden last line of every reply: the sufficiency verdict and the playbook checklist.
DONE = re.compile(r"<done\b([^>]*)/?>(?:\s*</done>)?", re.IGNORECASE)
ATTR = re.compile(r'(\w+)="([^"]*)"')

TOOLS = [
    {
        "name": "open_notes",
        "description": (
            "Open notes by slug, up to 10 in one call. Each note comes back as a search result, "
            "one line per block: frontmatter fields, Facts, History (marked), other sections. "
            "Open every note that may hold the answer at once, never one by one."
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
            "and the brain's aliases matched. Returns the matching lines as search results, by "
            "note. Use it when the maps and the opened notes don't give enough evidence; try "
            "new words each time. At most 3 per question."
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
]
FRESH = (
    "Write the whole answer again, from scratch, as if for the first time, and end it with your "
    "<done …/> line. Never mention drafts, retries, checks or corrections in it."
)
ASK_AGAIN = "Write your answer to the question now, and end it with your <done …/> line."
ABSTAIN_HITS = (
    "Before you say it isn't in the notes: these lines came up for the question. Use them if "
    "they answer it; if they don't, keep your answer. Then write the whole answer again."
)
RUNAWAY_NOTE = (
    "This question has used a lot of reading already. Answer now from what you have, and say "
    "plainly in one line that you stopped looking early."
)
ABSENCE_HITS = (
    'You wrote "{sentence}", but these lines mention it. Use them if they answer it, and keep '
    "the sentence only if they don't."
)


@dataclass(frozen=True)
class LiaConfig:
    model: str = DEFAULT_MODEL  # simple and medium questions
    complex_model: str = COMPLEX_MODEL  # complex questions (the effort rule)
    effort: str = "low"
    owner_names: tuple[str, ...] = ()  # the voice check: Lia says "you", never these names
    today: str | None = None  # the upcoming view's "today" (ISO date); None is the real date
    horizon_days: int = 120
    # Footnote links to the local note server, e.g. "http://127.0.0.1:8765/note/{slug}#cite={block}".
    # None: plain footnotes, "[1] Master's thesis (masters-thesis)".
    cite_url: str | None = None

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
    """A copy of *messages* whose two newest user messages end in a 5-minute cache breakpoint.
    The older one sits exactly where the previous call wrote the cache, so each round reads
    everything before it (notes included) at the cache-read price, however many blocks the
    replies in between hold; the newer one writes this round for the next. With the system's
    two breakpoints that is the API's limit of four."""
    users = [i for i, m in enumerate(messages) if m["role"] == "user"][-2:]
    if not users or users[-1] != len(messages) - 1:
        return messages
    out = list(messages)
    for i in users:
        message = dict(out[i])
        content = message["content"]
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
        if not blocks:
            continue
        blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
        message["content"] = blocks
        out[i] = message
    return out


def is_abstain(text: str) -> bool:
    return text.strip().startswith((ABSTAIN, OLD_ABSTAIN))


def parse_done(text: str) -> tuple[str, dict | None]:
    """The reply without its <done …/> line, and that line's attributes (or None)."""
    found = None
    for m in DONE.finditer(text):
        found = dict(ATTR.findall(m.group(1)))
    return DONE.sub("", text).strip(), found


def render(blocks: list[dict], results: list[tuple[str, list[Block]]]) -> tuple[str, list[dict]]:
    """Lia's reply as text with numbered markers after each cited span, then one footnote per
    cited line: "[1] [[slug]] «fact line»" (or "field: value"). *results* are the search results
    of the conversation in request order, so a citation's search_result_index finds its note."""
    body, notes = [], {}
    for b in blocks:
        if b.get("type") != "text":
            continue
        text, marks = b.get("text", ""), []
        for c in b.get("citations") or []:
            if c.get("type") != "search_result_location":
                continue
            i = c.get("search_result_index", -1)
            if 0 <= i < len(results):
                slug, lines = results[i]
                cited = lines[c["start_block_index"] : c["end_block_index"]]
            else:  # not ours: show what the API says was cited
                slug, cited = c.get("source", "?"), [Block("text", c.get("cited_text", ""))]
            for line in cited:
                key = line.footnote(slug)
                if key not in notes:
                    notes[key] = (len(notes) + 1, slug, line)
                n = notes[key][0]
                if n not in marks:
                    marks.append(n)
        if marks:
            stripped = text.rstrip()
            text = stripped + "".join(f" [{n}]" for n in marks) + text[len(stripped) :]
        body.append(text)
    answer, _ = parse_done("".join(body))
    footnotes = [
        {"n": n, "line": key, "slug": slug, "shown": line.shown}
        for key, (n, slug, line) in notes.items()
    ]
    if footnotes and answer:
        answer += "\n\n" + "\n".join(f"[{f['n']}] {f['line']}" for f in footnotes)
    return answer, footnotes


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

    def _register(self, state: dict, results: list[tuple[str, list[Block]]]) -> None:
        state["results"].extend(results)
        for slug, _ in results:
            state["opened"].setdefault(slug, self.library.note_text(slug))

    def _tool(self, call: dict, state: dict):
        name, args = call["name"], call.get("input", {})
        step = {"tool": name, "input": args, "turn": state["turn"]}
        if name == "open_notes":
            asked = list(args.get("slugs", []))
            again = [s for s in asked if s in state["opened"]]
            content, results, notices = self.library.open_notes(
                [s for s in asked if s not in state["opened"]]
            )
            if again:  # never re-open: the note is already in this conversation
                state["reopens_skipped"] += len(again)
                notices.append("Already open above, not sent again: " + ", ".join(again))
            self._register(state, results)
            state["steps"].append({**step, "returned": [s for s, _ in results]})
            if state["effort"] == "complex" and not state["hints_given"]:
                hint = self._hints(state)
                if hint:
                    notices.append(hint)
            if not content:  # nothing opened: the notices are the whole (text) result
                return "\n\n".join(notices) or "No notes opened."
            state["notices"].extend(notices)  # sent beside the tool results, never inside
            return content
        if name == "search_notes":
            if state["searches"] >= MAX_SEARCHES:
                state["steps"].append({**step, "returned": "limit"})
                return (
                    f"Search limit reached ({MAX_SEARCHES} per question). "
                    "Answer from what you have."
                )
            state["searches"] += 1
            query, k = str(args.get("query", "")), int(args.get("k", 10))
            content, results = self.library.search_notes(query, k)
            self._register(state, results)
            state["steps"].append({**step, "returned": [s for s, _ in results]})
            return content
        if name == "load_skill":
            room = skill_mod.MAX_LOAD - len(state["skills_loaded"])
            names = [n for n in args.get("names", []) if n not in state["skills_loaded"]][:room]
            if not names:
                return f"At most {skill_mod.MAX_LOAD} skills per question; none more were loaded."
            text, done = skill_mod.loaded_text(self.playbooks, names)
            state["skills_loaded"].extend(done)
            state["steps"].append({**step, "returned": done})
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
        return f"Consider these before answering (notes you haven't opened):\n{lines}"

    def _loop(self, messages: list, state: dict):
        """Call the model until it stops using tools (at most MAX_TURNS calls)."""
        client = state["client"]
        reply = None
        for _ in range(MAX_TURNS):
            if sum(c["cost_usd"] for c in state["calls"]) >= RUNAWAY_USD:
                state["runaway"] = True
                break
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
            if state["notices"]:
                results.append({"type": "text", "text": "\n\n".join(state["notices"])})
                state["notices"] = []
            messages.append({"role": "user", "content": results})
        # Out of turns (or past the runaway line) while still reading: one last call, tools off.
        note = (
            RUNAWAY_NOTE
            if state["runaway"]
            else "Tool limit reached: answer now from what you have."
        )
        if isinstance(messages[-1]["content"], str):
            messages[-1]["content"] = [{"type": "text", "text": messages[-1]["content"]}]
        messages[-1]["content"].append({"type": "text", "text": note})
        reply = client.send(
            system=self.system, tools=self.tools, messages=messages, tool_choice={"type": "none"}
        )
        state["calls"].append(reply.usage.as_dict())
        self._assistant(messages, reply)
        return reply

    def _answer(self, reply, state: dict) -> str:
        """Render a reply and keep its <done …/> line in the trace."""
        raw = "".join(b.get("text", "") for b in reply.blocks if b.get("type") == "text")
        _, done = parse_done(raw)
        if done is not None:
            state["done"] = done
        answer, footnotes = render(reply.blocks, state["results"])
        state["footnotes"] = footnotes
        return answer

    def _again(self, messages: list, state: dict, content) -> str:
        messages.append({"role": "user", "content": content})
        return self._answer(self._loop(messages, state), state)

    def _locate(self, footnotes: list[dict]) -> list[dict]:
        """Each footnote with its note's title and the cited line's index in the whole note (the
        anchor the note page highlights)."""
        out = []
        for f in footnotes:
            slug = f["slug"]
            blocks = self.library.blocks(slug)
            unit = checks.quote_unit(f["shown"].removeprefix("History: "))
            block = next(
                (i for i, b in enumerate(blocks) if b.shown == f["shown"]),
                next(
                    (i for i, b in enumerate(blocks)
                     if checks.quote_unit(b.shown.removeprefix("History: ")) == unit),
                    None,
                ),
            )  # fmt: skip
            note = self.library.notes.get(slug)
            out.append({**f, "block": block, "title": note.name if note else slug})
        return out

    def _with_lines(self, state: dict, text: str, lines: list[tuple[str, str]]) -> list[dict]:
        """A user message: *text*, then the notes' *lines* as citable search results."""
        grouped: dict[str, list[Block]] = {}
        for slug, line in lines:
            kind = "history" if line.startswith("History: ") else "fact"
            grouped.setdefault(slug, []).append(Block(kind, line))
        results = list(grouped.items())
        self._register(state, results)
        return [{"type": "text", "text": text}] + [
            search_result(s, self.library.notes[s].name if s in self.library.notes else s, b)
            for s, b in results
        ]

    def _cited(self, state: dict) -> set[tuple[str, str]]:
        """(slug, quote unit) of every fact line the current answer cites."""
        out = set()
        for f in state["footnotes"]:
            m = re.match(r"\[\[([^\]]+)\]\] «(.*)»", f["line"])
            if m:
                out.add((m.group(1), checks.quote_unit(m.group(2))))
        return out

    def _checks(self, answer: str, state: dict) -> tuple[list, list, list, list]:
        cited = self._cited(state)
        return (
            verify.write_offers(answer),
            verify.check_absences(answer, self.library, cited),
            verify.check_support(answer, state["opened"], self.library.notes),
            verify.leaks(answer),
        )

    def _abstain_hits(self, question: str, state: dict) -> list[tuple[str, str]]:
        """Before any abstain: the fact-level search of the question, minus lines already given."""
        given = {(s, b.shown) for s, bs in state["results"] for b in bs}
        hits = []
        for unit in self.library.fact_index.hits(question, k=5):
            line = unit.text if unit.kind == "fact" else f"History: {unit.text}"
            if (unit.slug, line) not in given:
                hits.append((unit.slug, line))
        return hits

    def ask(self, question: str, qid: str = "q", context: str = "") -> dict:
        """*context*: the last turns of a chat, to resolve "that" or "she"; never a source."""
        start = time.perf_counter()
        level, reason = effort_mod.effort_of(question, self.library)
        complex_q = level == "complex" and self.complex_client is not None
        state = {
            "steps": [],
            "calls": [],
            "opened": {},
            "results": [],
            "footnotes": [],
            "searches": 0,
            "question": question,
            "effort": level,
            "turn": 0,
            "client": self.complex_client if complex_q else self.client,
            "hints_given": False,
            "hints": [],
            "notices": [],
            "reopens_skipped": 0,
            "runaway": False,
            "skills_loaded": [],
            "done": None,
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
        answer = self._answer(self._loop(messages, state), state)
        asked_again = False
        if not answer:
            # Empty-reply guard: one more ask, then an error, never an empty answer.
            asked_again = True
            answer = self._again(messages, state, ASK_AGAIN)
        abstain_hits = []
        if answer and is_abstain(answer) and not state["runaway"]:
            # The engineered abstain path: free code searches the question first.
            abstain_hits = self._abstain_hits(question, state)
            if abstain_hits:
                answer = self._again(
                    messages, state, self._with_lines(state, ABSTAIN_HITS, abstain_hits)
                )
        sibling_lines, sibling_phrases = [], []
        if answer and level != "simple" and not is_abstain(answer) and not state["runaway"]:
            draft = [checks.Citation(s, q, True) for s, q in self._cited(state)]
            sibling_lines, sibling_phrases = search.siblings(draft, self.library)
            if sibling_lines:
                answer = self._again(
                    messages,
                    state,
                    self._with_lines(state, search.SIBLINGS_PROMPT.format(lines=""), sibling_lines),
                )
        offers, absent, unsupported, leaked = self._checks(answer, state)
        first_check = {
            "absence_fired": len(verify.absence_claims(answer)),
            "absence_found": len(absent),
            "unsupported": [u.sentence for u in unsupported],
            "leaks": leaked,
            "write_offers": offers,
        }
        retried = bool(
            answer and not state["runaway"] and (offers or absent or unsupported or leaked)
        )
        if retried:
            parts: list[dict] = []
            lines: list[tuple[str, str]] = []
            text = []
            if offers:
                text.append(verify.CAPABILITY_RETRY)
            for a in absent:
                text.append(ABSENCE_HITS.format(sentence=a.sentence))
                lines += a.hits
            for u in unsupported:
                text.append(
                    f'"{u.sentence}" is not supported by the line it cites (missing: '
                    f"{', '.join(u.missing)}). Cite the line that states it, or drop the claim."
                )
            text.append(FRESH)
            parts = (
                self._with_lines(state, "\n\n".join(text), lines) if lines else "\n\n".join(text)
            )
            answer = self._again(messages, state, parts)
            offers, absent, unsupported, leaked = self._checks(answer, state)
        empty = not answer
        if empty:
            answer = EMPTY_ERROR
        else:
            # Marks go on before draft talk is stripped, so every flagged sentence still matches.
            for a in absent:
                answer = verify.mark(answer, a.sentence, "[unverified absence]")
            for u in unsupported:
                answer = verify.mark(answer, u.sentence, "[unsupported]")
            answer = verify.strip_leaks(answer)
        footnotes = self._locate(state["footnotes"])
        checked = verify.supported_sentences(answer)
        done = state["done"] or {}
        return {
            "id": qid,
            "question": question,
            "config": self.config.as_dict(),
            "map_version": self.library.version,
            "steps": state["steps"],
            "opened": sorted(state["opened"]),
            "answer": display(answer, footnotes, self.config.cite_url) if not empty else answer,
            "answer_full": answer,
            "empty_reply": empty,
            "support": {"checked": checked, "unsupported": len(unsupported)},
            "runaway": state["runaway"],
            "reopens_skipped": state["reopens_skipped"],
            "abstain": is_abstain(answer),
            "third_person": checks.third_person(answer, self.config.owner_names),
            "citations": footnotes,
            "citation_check": {"total": len(state["footnotes"]), "failed": 0, "retried": retried},
            "searches": state["searches"],
            "asked_again": asked_again,
            "abstain_search": {"hits": [list(h) for h in abstain_hits]},
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
            "verdict": done.get("verdict"),
            "checklist": done.get("checklist"),
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


def display(answer: str, footnotes: list[dict], cite_url: str | None) -> str:
    """The answer as Manoj sees it: Lia's sentences with their [n] marks, then one short footnote
    per mark, a link to the note page when *cite_url* is set, else the title and slug. The full
    quotes stay in the trace (answer_full, citations)."""
    body = checks.answer_body(answer).rstrip()
    if not footnotes:
        return body
    lines = []
    for f in footnotes:
        if cite_url:
            url = cite_url.format(slug=f["slug"], block="" if f["block"] is None else f["block"])
            lines.append(f"[{f['n']}] [{f['title']}]({url})")
        else:
            lines.append(f"[{f['n']}] {f['title']} ({f['slug']})")
    return body + "\n\n" + "\n".join(lines)


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
