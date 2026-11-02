"""The atlas: one row per life area, generated from taxonomy.md (the one source)."""

from __future__ import annotations

import re

from yggdras.data.graph import structural as st
from yggdras.data.maps.notes import NoteMeta, clean

COLUMNS = "code|area|hub|notes|belongs here|not here|key aliases"
# A row of taxonomy.md's life-area table: | `01-health/` | Holds | Not here |
AREA_ROW = re.compile(r"^\| `(0[1-8]-[a-z-]+)/` \| (.*?) \| (.*?) \|\s*$")
REGISTRIES = {
    "10-ideas": "ideas",
    "11-people": "people",
    "12-places": "places",
    "13-sources": "sources",
    "15-journal": "journal",
}


def area_scopes(taxonomy: str) -> dict[str, tuple[str, str]]:
    scopes = {}
    for line in taxonomy.splitlines():
        m = AREA_ROW.match(line)
        if m:
            scopes[m.group(1)] = (m.group(2).replace("`", ""), m.group(3).replace("`", ""))
    return scopes


def atlas(notes: dict[str, NoteMeta], taxonomy: str, version: str) -> str:
    scopes = area_scopes(taxonomy)
    hubs = {n.area: n for n in notes.values() if n.type == st.HUB and n.path.startswith(n.area)}
    rows = [
        f"# atlas | areas {len(st.AREAS)} | notes {len(notes)} | map_version {version}",
        COLUMNS,
    ]
    for area in st.AREAS:
        hub = hubs.get(area)
        holds, not_here = scopes.get(area, ("", ""))
        code, _, name = area.partition("-")
        count = sum(1 for n in notes.values() if n.area == area)
        hub_aliases = ", ".join(clean(a) for a in hub.aliases) if hub else ""
        rows.append(
            "|".join(
                [
                    code,
                    name,
                    hub.slug if hub else "",
                    str(count),
                    clean(holds),
                    clean(not_here),
                    hub_aliases,
                ]
            )
        )
    shelves = {}
    for n in notes.values():
        shelf = n.path.split("/")[0]
        shelves[shelf] = shelves.get(shelf, 0) + 1
    cross = sum(1 for n in notes.values() if n.area == st.CROSS)
    parts = [f"{name} {shelf[:2]} ({shelves.get(shelf, 0)})" for shelf, name in REGISTRIES.items()]
    rows.append("registries|" + " · ".join([*parts, f"cross-area ({cross})"]))
    return "\n".join(rows) + "\n"
