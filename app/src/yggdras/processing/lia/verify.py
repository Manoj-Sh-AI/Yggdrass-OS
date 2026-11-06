"""Verification, free code: absence claims, claim support, draft leakage, write offers.

All lexical and deterministic. They run on Lia's own sentences (footnote lines left out), feed
the one retry, and mark what still fails: `[unverified absence]`, `[unsupported]`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from yggdras.data.maps import checks
from yggdras.data.maps.upcoming import MONTHS
from yggdras.processing.lia.search import stem, terms

SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+(?:\s*\[\d+\])*|$)")
# 2a: sentences that say a topic is not in the notes.
ABSENCE = re.compile(
    r"\b(nothing (?:in your notes |else )?(?:mentions?|says?|records?|covers?)|no note(?:s)?\b|"
    r"none of (?:your|the) notes|(?:your |the )?notes? (?:don't|do not|doesn't|does not|never) "
    r"(?:say|mention|record|cover|name|give|show|list)|isn't in your notes|not in your notes|"
    r"(?:is|are)n't recorded|not recorded|no record of|found nothing|(?:didn't|did not) find|"
    r"(?:there's|there is) no (?:note|record|mention)|I don't have (?:that|it|anything))",
    re.IGNORECASE,
)
ABSENCE_WORDS = frozenset(
    "nothing note notes mention mentions record records recorded say says cover covers name "
    "names give show list found find don't doesn't isn't aren't didn't never none there "
    "anything else yet have".split()
)
# 2c: words about drafts, retries or checks that must never reach the final answer.
LEAK = re.compile(
    r"(earlier draft|previous (?:answer|draft|version)|my (?:first|last) answer|"
    r"I(?:'ve| have)? (?:dropped|removed|corrected|fixed|rewritten|revised)|after re-?checking|"
    r"re-?checked|corrected citations?|answer again|revised answer|on second look|"
    r"(?:the|a) (?:citation |support )?check (?:failed|flagged|found)|as (?:noted|flagged) above)",
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(not|no|never|none|nothing|n't|without|yet to)\b|n't\b", re.IGNORECASE)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
CAPITAL = re.compile(r"\b[A-ZÄÖÜ][A-Za-z0-9äöüß&.-]*[A-Za-z0-9]\b|\b[A-Z]\d\b")
PLAIN_CAPS = frozenset(
    "I You Your Yours It Its The This That These Those A An And But Or So If When Then There "
    "Here Want Do Does Did Is Are Was Were My Me We Our They Their He His She Her Also Both "
    "Nothing None No Not Only Still Yet Next First Second Third One Two Three".split()
)


def sentences(body: str) -> list[str]:
    return [s.strip() for s in SENTENCE.findall(body) if s.strip()]


# ---------------------------------------------------------------- 2a absence claims


@dataclass
class Absence:
    sentence: str
    topic: list[str]  # stemmed topic words
    hits: list[tuple[str, str]]  # (slug, fact text) lines that mention the topic


def absence_claims(answer: str) -> list[tuple[str, list[str]]]:
    """(sentence, topic words) for each sentence of Lia's own that claims something is absent."""
    out = []
    for s in sentences(checks.answer_body(answer)):
        if not ABSENCE.search(s):
            continue
        topic = [
            t
            for t in terms(ABSENCE.sub(" ", re.sub(r"\[\d+\]", " ", s)))
            if t not in {stem(w) for w in ABSENCE_WORDS} and not t.isdigit()
        ]
        if topic:
            out.append((s, list(dict.fromkeys(topic))))
    return out


def check_absences(answer: str, library, cited: set[tuple[str, str]]) -> list[Absence]:
    """Absence claims the notes contradict: a fact line not yet cited that holds at least half
    of the topic's words (at least one) is a hit. Claims without hits are fine."""
    found = []
    for sentence, topic in absence_claims(answer):
        need = max(1, (len(topic) + 1) // 2)
        hits = []
        for unit in library.fact_index.hits(" ".join(topic), k=10):
            text = unit.text.split(" (src:")[0]
            if (unit.slug, checks.quote_unit(text)) in cited:
                continue
            words = set(terms(f"{unit.slug.replace('-', ' ')} {text}"))
            if sum(t in words for t in topic) >= need:
                hits.append((unit.slug, text))
        if hits:
            found.append(Absence(sentence, topic, hits[:5]))
    return found


# ---------------------------------------------------------------- 2b claim support


@dataclass
class Unsupported:
    sentence: str
    missing: list[str]  # key facts of the sentence the cited lines don't hold


def key_facts(sentence: str) -> list[str]:
    """Names, numbers, dates and a negation: what a cited line must hold for the sentence."""
    text = re.sub(r"\[\d+\]", " ", sentence)
    keys = NUMBER.findall(text)
    keys += [m.lower() for m in re.findall(r"[A-Za-zäöü]+", text) if m.lower() in MONTHS]
    start = len(text) - len(text.lstrip(' "“'))
    for m in CAPITAL.finditer(text):
        word = m.group(0).strip(".")
        if word in PLAIN_CAPS or word.lower() in MONTHS:
            continue
        # The first word is capitalised by grammar ("Another", "Graduation"); only an
        # all-caps first word (HCOB, AWS) counts as a name.
        if m.start() == start and not word.isupper():
            continue
        keys.append(word)
    if NEGATION.search(text):
        keys.append("<negation>")
    return list(dict.fromkeys(keys))


ISO_DATE = re.compile(r"\b(20\d\d)-(0[1-9]|1[0-2])(?:-(\d\d))?\b")
MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
]  # fmt: skip


def _spelled(lines: str) -> str:
    """ISO dates in *lines* written out too ("2026-11-07" → "7 november 2026"), so a sentence
    that spells a date matches the line that writes it as digits."""
    out = []
    for y, mo, d in ISO_DATE.findall(lines):
        out.append(
            f"{int(d)} {MONTH_NAMES[int(mo) - 1]} {y}" if d else f"{MONTH_NAMES[int(mo) - 1]} {y}"
        )
    return f"{lines} {' '.join(out)}"


def _holds(key: str, lines: str, names: str) -> bool:
    if key == "<negation>":
        return bool(NEGATION.search(lines))
    low, hay = key.lower(), f"{_spelled(lines)} {names}".lower()
    if low in hay:
        return True
    if NUMBER.fullmatch(key):
        return key.replace(",", "") in hay.replace(",", "")
    return stem(low) in {stem(w) for w in re.findall(r"[a-z0-9äöüß]+", hay)}


def check_support(answer: str, opened: dict[str, str], notes: dict) -> list[Unsupported]:
    """Each of Lia's sentences with footnote markers must hold its key facts in the lines it
    cites (or in the cited notes' names and aliases, for names). Lexical, so it errs strict."""
    body = checks.answer_body(answer)
    lines = {}
    for line in answer.splitlines():
        m = re.match(r"^\s*\[(\d+)\]\s*(.*)$", line)
        if m and "[[" in m.group(2):
            lines[m.group(1)] = m.group(2)
    out = []
    for s in sentences(body):
        marks = re.findall(r"\[(\d+)\]", s)
        if not marks or ABSENCE.search(s):
            continue
        cited = " ".join(lines.get(n, "") for n in marks)
        slugs = re.findall(r"\[\[([^\]|]+)\]\]", cited)
        names = " ".join(
            f"{notes[x].name} {' '.join(notes[x].aliases)} {x.replace('-', ' ')}"
            for x in slugs
            if x in notes
        )
        quoted = (
            " ".join(re.findall(r"«([^»]+)»", cited)) + " " + re.sub(r"\[\[[^\]]+\]\]", " ", cited)
        )
        missing = [k for k in key_facts(s) if not _holds(k, quoted, names)]
        if missing:
            out.append(Unsupported(s, missing))
    return out


# ---------------------------------------------------------------- 2c leakage


def leaks(answer: str) -> list[str]:
    return [s for s in sentences(checks.answer_body(answer)) if LEAK.search(s)]


def strip_leaks(answer: str) -> str:
    """Drop every sentence of Lia's own that talks about drafts, retries or checks."""
    out = answer
    for s in leaks(answer):
        out = out.replace(s, "", 1)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", out)).strip()


def mark(answer: str, sentence: str, tag: str) -> str:
    return answer.replace(sentence, f"{sentence} {tag}", 1)


# ---------------------------------------------------------------- capability: read-only

WRITE_OFFER = re.compile(
    r"\b(I'll|I will|I can|I could|let me|shall I|want me to|should I)\s+(also\s+)?"
    r"(add|save|update|note|record|write|create|log|put|store|set up|schedule)\b",
    re.IGNORECASE,
)
CAPABILITY_RETRY = (
    "You are read-only: remove every offer to add, save, update, note or create something. You "
    'may say: "Tell me and I\'ll be able to note it once writing is switched on."'
)


def write_offers(answer: str) -> list[str]:
    """Offers to write something, in Lia's own sentences."""
    return [m.group(0) for m in WRITE_OFFER.finditer(checks.answer_body(answer))]
