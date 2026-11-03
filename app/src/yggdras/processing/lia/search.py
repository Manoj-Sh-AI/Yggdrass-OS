"""Better search, free code (v4 1a–1c): a fact-level index, query expansion from the brain's own
aliases, light stemming, and unopened-candidate hints. No embeddings; nothing is written."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from yggdras.data.graph import structural as st
from yggdras.data.maps.notes import NoteMeta, clean

WORD = re.compile(r"[a-z0-9äöüß]+")
STOP = frozenset(
    "a an the of to in on for and or with at by from as is was are were be been has had have "
    "his her he she it its this that these those their there than then into about after before "
    "over under via per also more most very can could would should will may might do does did "
    "i me my mine you your we our they them what which who whom how why when where any some "
    "all one now right just still get got there here not no".split()
)
# German/English pairs of the kind the brain's aliases already use (generic words only).
PAIRS = {
    "studium": "studies",
    "jobsuche": "job search",
    "arbeit": "work",
    "karriere": "career",
    "gesundheit": "health",
    "finanzen": "money",
    "deutsch": "german",
    "masterarbeit": "thesis",
    "aufenthaltstitel": "residence permit",
    "aufenthaltserlaubnis": "residence permit",
    "wohnung": "flat",
    "steuern": "taxes",
    "bewerbung": "application",
    "vorstellungsgespräch": "interview",
    "werkstudent": "working student",
    "familie": "family",
    "reise": "trip",
}
PAIRS |= {v: k for k, v in list(PAIRS.items())}
EXPANDED_WEIGHT = 0.5  # an alias-expanded term counts half a term the question used
SUFFIXES = ("ations", "ation", "ics", "ies", "ing", "ers", "er", "es", "ed", "s")


def stem(word: str) -> str:
    """Light stemming: robotics/robots → robot, jobs → job, studies → study."""
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            base = word[: -len(suffix)]
            return base + "y" if suffix == "ies" else base
    return word


def terms(text: str) -> list[str]:
    """Stemmed content words of *text*."""
    return [stem(w) for w in WORD.findall(text.lower()) if w not in STOP and len(w) > 1]


@dataclass(frozen=True)
class Unit:
    slug: str
    kind: str  # fact | history | about
    text: str


def fact_units(notes: dict[str, NoteMeta], texts: dict[str, str]) -> list[Unit]:
    """Every Facts and History line as its own unit, plus one "about" unit per note (title,
    aliases, description), each keeping its note's slug (1a)."""
    units = []
    for slug, n in notes.items():
        about = " · ".join(x for x in (n.name, ", ".join(n.aliases), n.description) if x)
        units.append(Unit(slug, "about", clean(about)))
        parts = st._split(texts.get(slug, ""))
        if parts is None:
            continue
        for heading, _, line in st.sections(parts[1], parts[2]):
            if heading in (st.FACTS_HEADING, st.HISTORY_HEADING) and line.startswith("- "):
                kind = "fact" if heading == st.FACTS_HEADING else "history"
                units.append(Unit(slug, kind, line[2:].strip()))
    return units


def expansions(query: str, notes: dict[str, NoteMeta]) -> dict[str, float]:
    """The query's stemmed terms (weight 1), plus the names and aliases of every note one of
    them names (1b): a term that is a whole alias, or a word of a one- or two-word alias, adds
    that note's other names at half weight. German/English pairs work the same way."""
    words = terms(query)
    weights = dict.fromkeys(words, 1.0)
    found = set(words)
    for w in WORD.findall(query.lower()):
        if w in PAIRS:
            for t in terms(PAIRS[w]):
                weights.setdefault(t, EXPANDED_WEIGHT)
    for n in notes.values():
        if n.type == st.HUB:
            continue
        names = [n.name, *n.aliases]
        hit = False
        for name in names:
            parts = terms(name)
            if not parts:
                continue
            if all(p in found for p in parts) or (len(parts) <= 2 and set(parts) & found):
                hit = True
                break
        if hit:
            for name in names:
                for t in terms(name):
                    weights.setdefault(t, EXPANDED_WEIGHT)
    return weights


class FactIndex:
    """BM25 over fact units, stemmed, with alias expansion."""

    def __init__(self, notes: dict[str, NoteMeta], texts: dict[str, str]):
        self.notes = notes
        self.units = fact_units(notes, texts)
        self.counts = [Counter(terms(f"{u.slug.replace('-', ' ')} {u.text}")) for u in self.units]
        self.df = Counter(t for c in self.counts for t in c)
        self.avg = sum(sum(c.values()) for c in self.counts) / max(len(self.counts), 1)

    def scores(self, weights: dict[str, float]) -> list[tuple[float, int]]:
        n = len(self.units)
        out = []
        for i, counts in enumerate(self.counts):
            length = sum(counts.values())
            score = 0.0
            for t, w in weights.items():
                tf = counts.get(t, 0)
                if not tf:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                score += w * idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / self.avg))
            if score > 0:
                out.append((score, i))
        return sorted(out, key=lambda x: (-x[0], self.units[x[1]].slug))

    def search(self, query: str, k: int = 10, expand: bool = True) -> str:
        weights = expansions(query, self.notes) if expand else dict.fromkeys(terms(query), 1.0)
        ranked = self.scores(weights)[:k]
        if not ranked:
            return "No matches."
        rows = []
        for score, i in ranked:
            u = self.units[i]
            text = u.text.split(" (src:")[0] if u.kind != "about" else u.text
            label = {"fact": "", "history": "history: ", "about": "about: "}[u.kind]
            rows.append(f"{u.slug} | {round(score, 2)} | {label}{text}")
        return "\n".join(rows)

    def hits(self, query: str, k: int = 10) -> list[Unit]:
        """The top fact and history units for *query* (no "about" rows): for the checks."""
        ranked = self.scores(expansions(query, self.notes))
        return [self.units[i] for _, i in ranked if self.units[i].kind != "about"][:k]


def candidates(
    notes: dict[str, NoteMeta],
    words: list[str],
    exclude: set[str],
    k: int = 8,
) -> list[NoteMeta]:
    """Shelf rows not opened yet whose title, aliases or description share a key term with
    *words* (1c). Rarer shared terms count more; hubs are left out."""
    wanted = set(words)
    rows = {
        s: set(terms(f"{n.name} {' '.join(n.aliases)} {n.description} {s.replace('-', ' ')}"))
        for s, n in notes.items()
        if n.type != st.HUB and s not in exclude
    }
    df = Counter(t for ts in rows.values() for t in ts)
    total = max(len(rows), 1)
    scored = []
    for slug, ts in rows.items():
        shared = ts & wanted
        if shared:
            score = sum(math.log(1 + total / df[t]) for t in shared)
            scored.append((-score, slug))
    return [notes[s] for _, s in sorted(scored)[:k]]
