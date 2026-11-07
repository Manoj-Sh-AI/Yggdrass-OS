"""Free checks that make Lia stop and ask instead of writing (D36).

- A likely duplicate note: an exact match of the normalised name or an alias against an
  existing note's slug, name or aliases always asks; so does a word overlap of 0.6 or more
  between names (Jaccard over their words).
- A conflicting fact: a new fact whose words match an existing fact's (overlap 0.6 or more,
  dates and figures left out) but whose dates or figures differ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from yggdras.data.graph import structural as st
from yggdras.data.maps import checks

OVERLAP = 0.6
# Whole figures only: "2031" or "14.01.2031", never the 2 in "A2".
NUMBER = re.compile(r"\b\d+(?:[.,:/-]\d+)*\b")
STOP = frozenset(
    "a an and the of to in on at for by with from is are was were be been my me i you your "
    "his her their its it this that as or not no".split()
)


MONTHS = frozenset(
    "january february march april may june july august september october november december "
    "jan feb mar apr jun jul aug sep sept oct nov dec januar februar marz mai juni juli "
    "oktober dezember".split()
)


def words(text: str) -> set[str]:
    """Content words: no stop words, no figures, no month names (those are dates)."""
    found = {w for w in st.normalize(NUMBER.sub(" ", text)).split("-") if len(w) > 1}
    return found - STOP - MONTHS


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


@dataclass(frozen=True)
class Duplicate:
    slug: str
    name: str
    why: str


def likely_duplicates(
    notes: dict, name: str, aliases: list[str] = (), skip: set[str] = frozenset()
) -> list[Duplicate]:
    """Existing notes (*notes*: slug → NoteMeta) a new note named *name* may duplicate."""
    mine = {st.normalize(x) for x in (name, *aliases) if x.strip()}
    out = []
    for slug, n in notes.items():
        if slug in skip:
            continue
        theirs = {st.normalize(x) for x in (slug, n.name, *n.aliases) if x.strip()}
        same = mine & theirs
        if same:
            out.append(Duplicate(slug, n.name, f"same name or alias ({sorted(same)[0]})"))
            continue
        score = jaccard(words(name), words(n.name))
        if score >= OVERLAP:
            out.append(Duplicate(slug, n.name, f"similar name ({score:.0%} word overlap)"))
    return out


def numbers(text: str) -> set[str]:
    """A fact's dates and figures: its numbers and month names."""
    unit = checks.quote_unit(text)
    months = {w for w in st.normalize(unit).split("-") if w in MONTHS}
    return set(NUMBER.findall(unit)) | months


def conflicting_facts(existing: list[str], new: str) -> list[str]:
    """Existing fact lines that say the same thing as *new* with other dates or figures."""
    unit, figures = checks.quote_unit(new), numbers(new)
    if not figures:
        return []
    out = []
    for line in existing:
        theirs = numbers(line)
        if not theirs or theirs == figures:
            continue
        if jaccard(words(unit), words(checks.quote_unit(line))) >= OVERLAP:
            out.append(line)
    return out
