"""Checks that keep the maps honest: description rules (A23), no facts in maps, citations (D34)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from yggdras.data.graph import structural as st
from yggdras.data.maps.notes import NoteMeta, clean

MAX_WORDS = 15  # a warning until experiment E5 sets the limit (A23)
MAX_WORDS_SENSITIVE = 8
CLAIM_TYPES = ("concept", "framework", "decision")
DIGITS = re.compile(r"\d+")
# A fact line's own text, before its source bracket.
SOURCE = re.compile(r"\s*\(src:.*$")
MIN_FACT_WORDS = 5  # shorter fact texts ("Manoj is Indian.") are too common to flag


@dataclass(frozen=True)
class Problem:
    severity: str  # "hard" or "warning"
    slug: str
    message: str


def _bad_chars(text: str) -> bool:
    return "|" in text or "\n" in text or "\r" in text


def description_problems(note: NoteMeta, hard: bool) -> list[Problem]:
    """A23's rules for one note. With *hard* off, the content rules are only warnings."""
    level = "hard" if hard else "warning"
    out = []
    say = lambda severity, message: out.append(Problem(severity, note.slug, message))  # noqa: E731
    if not note.description.strip():
        say("hard", "missing description")
    if any(_bad_chars(t) for t in (note.description, note.name, *note.aliases)):
        say("hard", "'|' or a line break in the description, title or an alias")
    words = len(clean(note.description).split())
    allowed = set(DIGITS.findall(" ".join([note.name, *note.aliases])))
    figures = [d for d in DIGITS.findall(note.description) if d not in allowed]
    if note.sensitive:
        if words > MAX_WORDS_SENSITIVE or DIGITS.search(note.description):
            say(level, f"sensitive description must be ≤ {MAX_WORDS_SENSITIVE} words, no digits")
    elif figures:
        say(level, f"dates or figures in the description: {', '.join(figures)}")
    if words > MAX_WORDS:
        say("warning", f"description has {words} words (limit {MAX_WORDS}, until E5)")
    if note.type in CLAIM_TYPES and not note.summary:
        say("warning", f"a {note.type} keeps its claim or definition in ## Summary, which is empty")
    return out


def fact_text(line: str) -> str:
    return clean(SOURCE.sub("", line)).rstrip(".")


def facts_in_maps(maps: dict[str, str], notes: dict[str, NoteMeta], hard: bool) -> list[Problem]:
    """A fact line's text that turns up in a map: maps route, notes answer (D34).

    Facts reach a map only through a description, so this follows the description switch.
    """
    joined = "\n".join(clean(text) for text in maps.values())
    out = []
    for note in notes.values():
        for line in note.facts:
            text = fact_text(line)
            if len(text.split()) >= MIN_FACT_WORDS and text in joined:
                level = "hard" if hard else "warning"
                out.append(Problem(level, note.slug, f"fact in a map: {text[:60]}"))
    return out


# ---------------------------------------------------------------- citation check (D34)
CITATION = re.compile(r"\[\[([^\]|]+)\]\]\s*\"([^\"]+)\"")


@dataclass(frozen=True)
class Citation:
    slug: str
    quote: str
    ok: bool
    reason: str = ""


def note_fact_lines(text: str) -> list[str]:
    """The Facts and History lines of a note's text, without the leading '- '."""
    parts = st._split(text)
    if parts is None:
        return []
    return [
        line[2:].strip()
        for heading, _, line in st.sections(parts[1], parts[2])
        if heading in (st.FACTS_HEADING, st.HISTORY_HEADING) and line.startswith("- ")
    ]


def _same(quote: str, line: str) -> bool:
    q = clean(quote).removeprefix("- ").rstrip(".")
    return q in (clean(line).rstrip("."), fact_text(line))


def check_citations(answer: str, opened: dict[str, str]) -> list[Citation]:
    """Every `[[slug]] "fact line"` in *answer*, checked word for word against *opened* notes.

    *opened* maps the slug of each note Lia opened for this question to its full text.
    """
    out = []
    for slug, quote in CITATION.findall(answer):
        slug = slug.strip()
        if slug not in opened:
            out.append(Citation(slug, quote, False, "note was not opened for this question"))
        elif any(_same(quote, line) for line in note_fact_lines(opened[slug])):
            out.append(Citation(slug, quote, True))
        else:
            out.append(Citation(slug, quote, False, "not a fact line of that note, word for word"))
    return out
