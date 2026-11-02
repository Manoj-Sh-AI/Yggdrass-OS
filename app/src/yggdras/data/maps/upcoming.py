"""The upcoming view (F6): every dated item in the next N days, one row each, no fact text.

`date | slug | label`, where the label is the note's title and the kind of date (fact, review,
valid from). A row only says *where* to look; Lia opens the note to cite (D34). Deterministic
for a given brain and "today".
"""

from __future__ import annotations

import datetime as dt
import re

from yggdras.data.graph import structural as st
from yggdras.data.maps.notes import NoteMeta, clean

HORIZON_DAYS = 120
MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            "january januar",
            "february februar",
            "march märz maerz",
            "april",
            "may mai",
            "june juni",
            "july juli",
            "august",
            "september",
            "october oktober",
            "november",
            "december dezember",
        ]
    )
    for m in names.split()
}
ISO = re.compile(r"\b(20\d\d)-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?\b")
# "1 November 2026", "March 2027", "late December 2026", "January–March 2027" (the first
# month counts).
WORDS = re.compile(
    r"(?:\b([0-3]?\d)\.?\s+)?\b("
    + "|".join(MONTHS)
    + r")(?:\s*[–-]\s*(?:"
    + "|".join(MONTHS)
    + r"))?\s+(20\d\d)\b",
    re.IGNORECASE,
)
SOURCE = re.compile(r"\(src:(?P<src>[^)]*)\)\s*$")
VALID_FROM = re.compile(r"valid:\s*(20\d\d-\d\d(?:-\d\d)?)\.\.")


def current_fact_lines(text: str) -> list[str]:
    """The `## Facts` lines of a note (History left out), without the leading '- '."""
    parts = st._split(text)
    if parts is None:
        return []
    return [
        line[2:].strip()
        for heading, _, line in st.sections(parts[1], parts[2])
        if heading == st.FACTS_HEADING and line.startswith("- ")
    ]


def _date(year: str, month: str | int, day: str | None) -> tuple[dt.date, str]:
    """A date and how it is shown: YYYY-MM-DD, or YYYY-MM for a month (its first day)."""
    m = int(month)
    if day:
        return dt.date(int(year), m, int(day)), f"{year}-{m:02d}-{day}"
    return dt.date(int(year), m, 1), f"{year}-{m:02d}"


def fact_dates(line: str) -> list[tuple[dt.date, str, str]]:
    """Dates a fact line is about: (date, shown, kind). The recorded date in the source
    bracket is not one, but its `valid:` start is."""
    found = []
    m = SOURCE.search(line)
    body = line[: m.start()] if m else line
    for y, mo, d in ISO.findall(body):
        found.append((*_date(y, mo, d or None), "fact"))
    for day, month, year in WORDS.findall(body):
        day = f"{int(day):02d}" if day and 1 <= int(day) <= 28 else None
        found.append((*_date(year, MONTHS[month.lower()], day), "fact"))
    if m:
        for value in VALID_FROM.findall(m.group("src")):
            y, mo, *d = value.split("-")
            found.append((*_date(y, mo, d[0] if d else None), "valid from"))
    return found


def rows(
    notes: dict[str, NoteMeta],
    texts: dict[str, str],
    today: dt.date,
    days: int = HORIZON_DAYS,
) -> list[tuple[str, str, str]]:
    """(shown date, slug, label) for every dated item from *today* to *today* + *days*.
    A month counts when any day of it falls in the window."""
    end = today + dt.timedelta(days=days)
    out = set()
    for slug, n in notes.items():
        if n.type == st.HUB:
            continue
        title = clean(n.name)
        items = [d for line in current_fact_lines(texts.get(slug, "")) for d in fact_dates(line)]
        if n.review:
            m = ISO.search(n.review)
            if m:
                items.append((*_date(m.group(1), m.group(2), m.group(3)), "review"))
        for date, shown, kind in items:
            last = date if len(shown) == 10 else _month_end(date)
            if last >= today and date <= end:
                out.add((shown, slug, f"{title} ({kind})"))
    return sorted(out)


def _month_end(date: dt.date) -> dt.date:
    nxt = date.replace(day=28) + dt.timedelta(days=4)
    return nxt - dt.timedelta(days=nxt.day)


def upcoming(
    notes: dict[str, NoteMeta],
    texts: dict[str, str],
    today: dt.date,
    days: int = HORIZON_DAYS,
) -> str:
    found = rows(notes, texts, today, days)
    head = [
        f"# upcoming | from {today.isoformat()} | next {days} days | items {len(found)}",
        "date|slug|label",
    ]
    return "\n".join(head + ["|".join(r) for r in found]) + "\n"
