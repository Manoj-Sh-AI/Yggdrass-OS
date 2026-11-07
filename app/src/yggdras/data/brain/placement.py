"""Where a new note goes: the taxonomy v3 placement rules (library/00-manual/taxonomy.md).

1. Type first: person → 11-people; place → 12-places; source → 13-sources; concept or
   framework → 10-ideas; hub → its area; journal → 15-journal.
2. Otherwise (project, goal, decision, event, topic): the life area of the activity.

A flat brain (the Apollo demo) has no shelves: a new note goes to the folder that already
holds most notes of its type, else the folder holding most notes.
"""

from __future__ import annotations

from collections import Counter

from yggdras.data.graph import structural as st

BY_TYPE = {
    "person": "11-people",
    "place": "12-places",
    "source": "13-sources",
    "concept": "10-ideas",
    "framework": "10-ideas",
    "journal": "15-journal",
}
ACTIVITY_TYPES = ("project", "goal", "decision", "event", "topic")


def shelf_for(type: str, area: str) -> str | None:
    """The library shelf for a note of *type* serving *area*, or None when the rules can't
    settle it (an activity note with area `cross`, or an unknown type or area)."""
    if type in BY_TYPE:
        return BY_TYPE[type]
    if type == st.HUB or type in ACTIVITY_TYPES:
        return area if area in st.AREAS else None
    return None


def flat_folder(type: str, notes: list[tuple[str, str]]) -> str | None:
    """A flat brain's folder for *type*, from (type, folder) of its notes."""
    if not notes:
        return None
    same = Counter(folder for t, folder in notes if t == type)
    pool = same or Counter(folder for _, folder in notes)
    return sorted(pool.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
