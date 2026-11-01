"""The shelf map: one row per note, grouped by area, with flags."""

from __future__ import annotations

from yggdras.data.maps.notes import NoteMeta, area_heading, area_order, clean

FLAGS = (
    "# flags: S=sensitive  H=has superseded facts  R:<date>=review date  "
    "A:<code>=also in area  C:<parent>=chunk of  P:<pages>=pages"
)
COLUMNS = "slug|type|title|about|aliases|status|updated|flags"


def flags(note: NoteMeta) -> str:
    out = []
    if note.sensitive:
        out.append("S")
    if note.has_history:
        out.append("H")
    if note.review:
        out.append(f"R:{note.review}")
    if note.also:
        out.append("A:" + ",".join(a.partition("-")[0] for a in note.also))
    if note.parent:
        out.append(f"C:{note.parent}")
    if note.pages:
        out.append(f"P:{clean(note.pages)}")
    return " ".join(out)


def row(note: NoteMeta) -> str:
    return "|".join(
        [
            note.slug,
            note.type,
            clean(note.name),
            clean(note.description),
            ", ".join(clean(a) for a in note.aliases),
            clean(note.status) or "—",
            note.updated,
            flags(note),
        ]
    )


def shelf_map(notes: dict[str, NoteMeta], version: str) -> str:
    lines = [f"# shelf-map | notes {len(notes)} | map_version {version}", FLAGS, COLUMNS]
    for area in sorted({n.area for n in notes.values()}, key=area_order):
        lines.append(area_heading(area))
        lines += [row(notes[s]) for s in sorted(s for s, n in notes.items() if n.area == area)]
    return "\n".join(lines) + "\n"
