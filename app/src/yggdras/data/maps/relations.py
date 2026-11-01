"""The relationship map: one line per note with all its links, inverses written out.

Hub `lists` links are left out (the shelf map's grouping shows them). A chunk's links to its
parent and to its neighbouring chunks are written once, as a chain line.
"""

from __future__ import annotations

from yggdras.data.graph import structural as st
from yggdras.data.maps.notes import NoteMeta, area_heading, area_order

MENTIONED_IN = "mentioned_in"


def _is_chain_edge(edge: dict, notes: dict[str, NoteMeta]) -> bool:
    a, b = notes.get(edge["from_slug"]), notes.get(edge["to_slug"])
    if not a or not b or not a.parent:
        return False
    if edge["reason"] == "part_of":
        return b.slug == a.parent
    return edge["reason"] == "precedes" and b.parent == a.parent


def _chain(parent: str, notes: dict[str, NoteMeta], edges: list[dict]) -> list[str]:
    chunks = sorted(s for s, n in notes.items() if n.parent == parent)
    nxt = {
        e["from_slug"]: e["to_slug"]
        for e in edges
        if e["reason"] == "precedes" and e["from_slug"] in chunks and e["to_slug"] in chunks
    }
    starts = [c for c in chunks if c not in nxt.values()] or chunks[:1]
    order: list[str] = []
    current = starts[0] if starts else None
    while current and current not in order:
        order.append(current)
        current = nxt.get(current)
    return order + [c for c in chunks if c not in order]


def entries(graph: dict, notes: dict[str, NoteMeta]) -> tuple[dict[str, set[str]], int]:
    """Each note's link entries ("verb target"), and the number of links written."""
    lines: dict[str, set[str]] = {}
    links = 0
    for e in graph["edges"]:
        a, b, kind, reason = e["from_slug"], e["to_slug"], e["kind"], e["reason"]
        if kind == "hub" or a == b or a not in notes or b not in notes:
            continue
        if kind == "mention":
            verb, back = st.MENTION, MENTIONED_IN
        elif reason in st.OPPOSITE:
            verb, back = reason, st.OPPOSITE[reason]
        else:
            continue  # an unknown verb is an error in map.json, not a map line
        if _is_chain_edge(e, notes):
            continue
        before = (len(lines.get(a, ())), len(lines.get(b, ())))
        lines.setdefault(a, set()).add(f"{verb} {b}")
        lines.setdefault(b, set()).add(f"{back} {a}")
        if (len(lines[a]), len(lines[b])) != before:
            links += 1
    return lines, links


def relationship_map(graph: dict, notes: dict[str, NoteMeta], version: str) -> str:
    lines, links = entries(graph, notes)
    parents = sorted({n.parent for n in notes.values() if n.parent})
    out = [
        f"# relationship-map | links {links} ({2 * links} with inverses) | map_version {version}",
        "# omitted: hub lists/listed_in links. Chunk chains written once: "
        "chain <parent>: a > b > c",
    ]
    for area in sorted({n.area for n in notes.values()}, key=area_order):
        rows = []
        for slug in sorted(s for s, n in notes.items() if n.area == area):
            if slug in lines:
                rows.append(f"{slug}: " + " · ".join(sorted(lines[slug])))
            if slug in parents:
                chain = _chain(slug, notes, graph["edges"])
                short = [c[len(slug) :] if c.startswith(slug + "-") else c for c in chain]
                rows.append(f"chain {slug}: " + " > ".join(short))
        if rows:
            out += [area_heading(area), *rows]
    return "\n".join(out) + "\n"
