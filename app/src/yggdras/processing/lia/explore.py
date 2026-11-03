"""Lia looks wider before she answers (lia-v1 explore, F1–F6): plan, coverage, siblings,
capability and timing. Free code where code can do it; each step behind a LiaConfig switch."""

from __future__ import annotations

import re
from collections import Counter

from yggdras.data.graph import structural as st
from yggdras.data.maps import checks
from yggdras.data.maps.upcoming import MONTHS, current_fact_lines

EFFORTS = ("simple", "medium", "complex")
COVERAGE_ROUNDS = {"simple": 1, "medium": 2, "complex": 3}  # F2 caps
SEARCHES = {"simple": 3, "medium": 4, "complex": 6}  # search_notes calls per question
DEFAULT_EFFORT = "medium"  # when the plan step is off
SIBLINGS_MAX = 6  # sibling fact lines handed back (F3)
PHRASE_MAX_LINES = 8  # a phrase in more fact lines than this is too common to be a key phrase

PLAN_TOOL = {
    "name": "plan",
    "description": (
        "Call this first, before opening anything. Plan wide, then narrow. facets: every life "
        "area (atlas code and name, or a folder) the question names OR implies, e.g. "
        "'interviews' implies work-career, 'visa' home-admin, 'thesis' learning; list implied "
        "areas too. sub_questions: 1 for a simple question, up to 4 for a complex one. effort: "
        "simple = one fact or one note; medium = 2 areas, or a 'what changed' question; "
        "complex = 3+ areas, or a whole-picture, advice or decision question."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "facets": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            "implied": {
                "type": "array",
                "items": {"type": "string"},
                "description": "the facets the question implies without naming them",
            },
            "sub_questions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 4,
            },
            "effort": {"type": "string", "enum": list(EFFORTS)},
        },
        "required": ["facets", "sub_questions", "effort"],
        "additionalProperties": False,
    },
}
COVERAGE_TOOL = {
    "name": "coverage",
    "description": (
        "Call this after reading, before you write the answer. Grade each sub-question: covered, "
        "partly or not_covered by the facts you have read, with new search terms (synonyms, the "
        "area's aliases, other languages) for any that are not fully covered. verdict: "
        "sufficient, partly or insufficient for the whole question; missing: what the notes "
        "don't give."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "grades": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sub_question": {"type": "string"},
                        "grade": {"type": "string", "enum": ["covered", "partly", "not_covered"]},
                        "search_terms": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["sub_question", "grade"],
                    "additionalProperties": False,
                },
            },
            "verdict": {"type": "string", "enum": ["sufficient", "partly", "insufficient"]},
            "missing": {"type": "string"},
        },
        "required": ["grades", "verdict"],
        "additionalProperties": False,
    },
}

COVERAGE_NUDGE = (
    "Before you answer, call coverage: grade each sub-question against the facts you have read, "
    "and give your verdict."
)
SIBLINGS_PROMPT = (
    "Before you finish: these fact lines, in notes you haven't cited, share a key phrase with "
    "facts you cited. Include any that bear on the question, cited like the others (their "
    "notes count as opened); leave out the rest. Then write the whole answer again.\n{lines}"
)
CAPABILITY_RETRY = (
    "You are read-only: remove every offer to add, save, update, note or create something. You "
    'may say: "Tell me and I\'ll be able to note it once writing is switched on."'
)
# Time words that make the upcoming view worth loading (F6).
TIME_WORDS = re.compile(
    r"\b(now|today|this (week|month)|next|soon|upcoming|deadline|should i|timing|"
    r"by (january|february|march|april|may|june|july|august|september|october|"
    r"november|december))\b",
    re.IGNORECASE,
)
# v4 effort rule: advice, decision and whole-picture questions are complex, and so is any
# question touching 3+ areas; one area and a short question is simple; the rest is medium.
ADVICE = re.compile(
    r"\b(should i|what should|options|recommend|advice|decide|decision|choose|worth|priorit\w*|"
    r"warn|neglect\w*|on track|realistic|what would you|whole picture|across my life|"
    r"connect\w*|fit\w* (?:around|with|together)|what has to happen|what limits|"
    r"how does .+ affect)\b",
    re.IGNORECASE,
)
SIMPLE_WORDS = 12


def question_areas(question: str, library) -> list[str]:
    """Areas the question touches: an area whose name or code it says, or whose notes' names or
    aliases share a word (four letters or more) with it."""
    words = {w.rstrip("s") for w in WORD.findall(question.lower()) if w not in STOP}
    where: dict[str, set[str]] = {}
    for n in library.notes.values():
        if n.area == st.CROSS:
            continue
        for name in (n.name, *n.aliases):
            for w in WORD.findall(name.lower()):
                if len(w) > 3 and w.rstrip("s") in words:
                    where.setdefault(w.rstrip("s"), set()).add(n.area)
    n_areas = len({n.area for n in library.notes.values()} - {st.CROSS})
    # A word found in the names of many areas ("apollo" in a demo brain) names none of them.
    distinctive = max(2, n_areas // 3)
    hits = sorted({a for areas in where.values() if len(areas) <= distinctive for a in areas})
    q = question.lower()
    for area in {n.area for n in library.notes.values()} - {st.CROSS}:
        name = area.partition("-")[2].replace("-", " ")
        if name and re.search(rf"\b{re.escape(name)}\b", q) and area not in hits:
            hits.append(area)
    return hits


def effort_of(question: str, library) -> tuple[str, str]:
    """(effort level, the reason) by the fixed v4 rule."""
    if ADVICE.search(question):
        return "complex", "advice, decision or whole-picture wording"
    areas = question_areas(question, library)
    if len(areas) >= 3:
        return "complex", f"{len(areas)} areas: {', '.join(sorted(areas))}"
    if len(areas) <= 1 and len(question.split()) <= SIMPLE_WORDS:
        return "simple", f"{len(areas)} area, {len(question.split())} words"
    return "medium", f"{len(areas)} areas"


# F5: an offer to write, while Lia is read-only.
WRITE_OFFER = re.compile(
    r"\b(I'll|I will|I can|I could|let me|shall I|want me to|should I)\s+(also\s+)?"
    r"(add|save|update|note|record|write|create|log|put|store|set up|schedule)\b",
    re.IGNORECASE,
)
STOP = frozenset(
    "a an the of to in on for and or with at by from as is was are were be been has had have "
    "his her he she it its this that these those their there than then into about after before "
    "over under via per also more most very can could would should will may might do does did "
    "i me my you your we our they them".split()
)
WORD = re.compile(r"[a-z0-9äöüß]+")


def normalise_effort(value: str | None) -> str:
    return value if value in EFFORTS else DEFAULT_EFFORT


def area_index(library) -> dict[str, tuple[str, str]]:
    """Every way a facet may name an area or folder → (area, hub slug or "")."""
    hubs = {n.area: n.slug for n in library.notes.values() if n.type == st.HUB}
    areas = sorted({n.area for n in library.notes.values()})
    index = {}
    for area in areas:
        code, _, name = area.partition("-")
        for key in {area, code, name, name.replace("-", " ")} - {""}:
            index[key.lower()] = (area, hubs.get(area, ""))
    return index


def resolve_facets(facets: list[str], library) -> list[tuple[str, str]]:
    """The facets as (area, hub); a facet that names no area is dropped."""
    index, out = area_index(library), []
    for facet in facets:
        text = facet.lower().strip()
        hit = index.get(text) or next(
            (v for k, v in index.items() if len(k) > 2 and re.search(rf"\b{re.escape(k)}\b", text)),
            None,
        )
        if hit and hit not in out:
            out.append(hit)
    return out


def atlas_hints(question: str, library, already: set[str], limit: int = 3) -> list[tuple[str, str]]:
    """Areas whose notes' names or aliases share a word with the question, not yet in the
    plan: free hints for implied facets ("visa" → the area of the note aliased "visa")."""
    words = {w.rstrip("s") for w in WORD.findall(question.lower()) if w not in STOP}
    hits = Counter()
    examples = {}
    for n in library.notes.values():
        if n.area in already or n.area == st.CROSS:
            continue
        for name in (n.name, *n.aliases):
            for w in WORD.findall(name.lower()):
                if len(w) > 3 and w.rstrip("s") in words:
                    hits[n.area] += 1
                    examples.setdefault(n.area, w)
    return [(area, examples[area]) for area, _ in hits.most_common(limit)]


def plan_result(plan: dict, library, question: str, upcoming: str | None) -> str:
    effort = normalise_effort(plan.get("effort"))
    lines = [
        f"Plan recorded. Effort {effort}: up to {COVERAGE_ROUNDS[effort]} coverage round(s), "
        f"{SEARCHES[effort]} searches."
    ]
    resolved = resolve_facets([*plan.get("facets", []), *plan.get("implied", [])], library)
    if resolved:
        lines.append(
            "Your facets: " + "; ".join(f"{a} (hub: {h})" if h else a for a, h in resolved) + "."
        )
    hints = atlas_hints(question, library, {a for a, _ in resolved})
    if hints:
        lines.append(
            "The maps also tie words in the question to: "
            + "; ".join(f"{a} ('{w}')" for a, w in hints)
            + ". Include them if they bear on it."
        )
    if upcoming:
        lines.append(f"<upcoming.md>\n{upcoming.strip()}\n</upcoming.md>")
    width = "1 to 3" if effort == "simple" else "4 to 10"
    lines.append(
        f"Now open, in ONE open_notes call, the hub of each facet and the best notes for each "
        f"sub-question ({width} notes). Start wide, then narrow."
    )
    return "\n".join(lines)


def coverage_result(call: dict, effort: str, rounds_used: int, enabled: bool) -> tuple[str, bool]:
    """The reply to a coverage call, and whether it starts a corrective round (F2)."""
    open_items = [g for g in call.get("grades", []) if g.get("grade") != "covered"]
    if enabled and open_items and rounds_used < COVERAGE_ROUNDS[effort]:
        todo = "\n".join(
            f"- {g.get('sub_question', '')} ({g.get('grade')}): "
            + (", ".join(g.get("search_terms") or []) or "new words")
            for g in open_items
        )
        return (
            "Search now; don't offer to check later. For each item below, run search_notes with "
            "rewritten terms (synonyms, the area's aliases, other languages), open the top hits "
            f"in one open_notes call, then call coverage again.\n{todo}",
            True,
        )
    verdict = call.get("verdict", "partly")
    tail = {
        "sufficient": "Write the answer now.",
        "partly": "Write the answer now, and say exactly what is missing.",
        "insufficient": "Abstain now, with your abstain line and what is missing.",
    }.get(verdict, "Write the answer now.")
    return f"Coverage recorded: {verdict}. {tail}", False


# ---------------------------------------------------------------- F3: sibling facts


def _tokens(text: str) -> list[str]:
    return WORD.findall(text.lower())


def key_phrases(fact: str, name_words: set[str]) -> set[str]:
    """Two-word phrases of a fact that could recur elsewhere: both words carry meaning (not a
    stopword, not a word of the note's own name). "no" and "not" count, so "no progress" is one."""
    words = _tokens(checks.quote_unit(fact).replace("[stated]", "").replace("[inferred]", ""))

    def keep(w: str) -> bool:
        if w in ("no", "not", "never"):
            return True
        dated = w.isdigit() or w in MONTHS  # dates recur everywhere and say nothing alike
        return not dated and w not in STOP and w not in name_words

    return {f"{a} {b}" for a, b in zip(words, words[1:], strict=False) if keep(a) and keep(b)}


TAG = re.compile(r"^\[[a-z]+\]\s*")


def _is_fact(c: checks.Citation, library) -> bool:
    """A draft quote that is a fact line of its note once tags like [stated] are ignored
    (drafts often drop them; the final check still asks for them)."""
    quote = TAG.sub("", checks.quote_unit(c.quote))
    return any(TAG.sub("", checks.quote_unit(f)) == quote for f in library.fact_lines(c.slug))


def siblings(cited: list[checks.Citation], library) -> tuple[list[tuple[str, str]], list[str]]:
    """Fact lines in notes Lia didn't cite that share a key phrase with a fact she cited.
    Returns ((slug, fact line), …) and the phrases that matched. Free: no model call."""
    good = [c for c in cited if c.slug and (c.ok or _is_fact(c, library))]
    if not good:
        return [], []
    cited_slugs = {c.slug for c in good}
    lines = {
        slug: current_fact_lines(library.note_text(slug) or "")
        for slug, n in library.notes.items()
        if slug not in cited_slugs and n.type != st.HUB
    }
    phrases = set()
    for c in good:
        n = library.notes.get(c.slug)
        name_words = set(_tokens(f"{n.name} {c.slug.replace('-', ' ')}")) if n else set()
        phrases |= key_phrases(c.quote, name_words)
    joined = {(s, f): " ".join(_tokens(f)) for s, fs in lines.items() for f in fs}
    common = {
        p
        for p in phrases
        if sum(1 for t in joined.values() if f" {p} " in f" {t} ") > PHRASE_MAX_LINES
    }
    phrases -= common
    scored = []
    for (slug, fact), text in joined.items():
        hit = sorted(p for p in phrases if f" {p} " in f" {text} ")
        if hit:
            scored.append((-len(hit), slug, fact, hit))
    scored.sort()
    top = scored[:SIBLINGS_MAX]
    return [(s, f) for _, s, f, _ in top], sorted({p for *_, h in top for p in h})


def write_offers(answer: str) -> list[str]:
    """Offers to write something (F5), in Lia's own sentences."""
    return [m.group(0) for m in WRITE_OFFER.finditer(checks.answer_body(answer))]
