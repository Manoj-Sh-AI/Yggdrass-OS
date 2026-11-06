"""How hard a question is, by a fixed rule (free code), and whether it needs the upcoming view.

- complex: advice, decision or whole-picture wording, or a question touching 3+ areas;
- simple: 0–1 areas and at most 12 words;
- medium: the rest.

Complex questions go to the complex model (Sonnet); the rest stay on the default (Haiku).
"""

from __future__ import annotations

import re

from yggdras.data.graph import structural as st

EFFORTS = ("simple", "medium", "complex")
SIMPLE_WORDS = 12
ADVICE = re.compile(
    r"\b(should i|what should|options|recommend|advice|decide|decision|choose|worth|priorit\w*|"
    r"warn|neglect\w*|on track|realistic|what would you|whole picture|across my life|"
    r"connect\w*|fit\w* (?:around|with|together)|what has to happen|what limits|"
    r"how does .+ affect)\b",
    re.IGNORECASE,
)
# Time words: with ADVICE, these load the upcoming view.
TIME_WORDS = re.compile(
    r"\b(now|today|this (week|month)|next|soon|upcoming|deadline|timing|"
    r"by (january|february|march|april|may|june|july|august|september|october|"
    r"november|december))\b",
    re.IGNORECASE,
)
STOP = frozenset(
    "a an the of to in on for and or with at by from as is was are were be been has had have "
    "his her he she it its this that these those their there than then into about after before "
    "over under via per also more most very can could would should will may might do does did "
    "i me my you your we our they them".split()
)
WORD = re.compile(r"[a-z0-9äöüß]+")


def question_areas(question: str, library) -> list[str]:
    """Areas the question touches: one whose name it says, or whose notes' names or aliases share
    a word (four letters or more) with it. A word found in the names of more than a third of
    the areas ("apollo" in a demo brain) names none of them."""
    words = {w.rstrip("s") for w in WORD.findall(question.lower()) if w not in STOP}
    where: dict[str, set[str]] = {}
    for n in library.notes.values():
        if n.area == st.CROSS:
            continue
        for name in (n.name, *n.aliases):
            for w in WORD.findall(name.lower()):
                if len(w) > 3 and w.rstrip("s") in words:
                    where.setdefault(w.rstrip("s"), set()).add(n.area)
    areas = {n.area for n in library.notes.values()} - {st.CROSS}
    distinctive = max(2, len(areas) // 3)
    hits = sorted({a for found in where.values() if len(found) <= distinctive for a in found})
    q = question.lower()
    for area in sorted(areas):
        name = area.partition("-")[2].replace("-", " ")
        if name and re.search(rf"\b{re.escape(name)}\b", q) and area not in hits:
            hits.append(area)
    return hits


def effort_of(question: str, library) -> tuple[str, str]:
    """(effort level, the reason)."""
    if ADVICE.search(question):
        return "complex", "advice, decision or whole-picture wording"
    areas = question_areas(question, library)
    if len(areas) >= 3:
        return "complex", f"{len(areas)} areas: {', '.join(sorted(areas))}"
    if len(areas) <= 1 and len(question.split()) <= SIMPLE_WORDS:
        return "simple", f"{len(areas)} area, {len(question.split())} words"
    return "medium", f"{len(areas)} areas"


def wants_upcoming(question: str) -> bool:
    """Advice, decision and timing questions get the upcoming view."""
    return bool(ADVICE.search(question) or TIME_WORDS.search(question))
