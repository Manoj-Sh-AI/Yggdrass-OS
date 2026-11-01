"""Viewer: draw the brain's map as an interactive page, offline.

Our own page on the vendored vis-network (D32 as amended 2026-10-31: Graphify renders
nothing in Yggdras). The data is our structural map plus each note's summary, facts and
link lines; nothing else is read and nothing is sent anywhere. Notes marked
`sensitivity: high` keep their name, type and area visible, and hide description,
aliases, summary, facts and link lines behind a "show" click.

Usage:
    python -m yggdras.data.graph.viewer BRAIN_REPO
    python -m yggdras.data.graph.viewer BRAIN_ROOT --flat --out-dir DIR

The first form writes graph.html to library/00-manual/generated/ (gitignored in the brain
repo); the second draws a flat brain such as the archived Apollo demo.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

import yaml

from yggdras.data.graph import structural

VIS_NETWORK = Path(__file__).with_name("vendor") / "vis-network-9.1.6.min.js"
# The integrity hash Graphify 0.9.95 pinned for vis-network 9.1.6 on unpkg.
VIS_NETWORK_SHA384 = "Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"
LOCAL_SCRIPT = "vis-network.min.js"
VENDOR = Path(__file__).with_name("vendor")
# Fonts for the labels (Inter, SIL OFL 1.1), copied next to the page: name -> sha384.
FONTS = {
    "inter-latin-400-normal.woff2": (
        "fh/R5bWIGwMIs5kzn3aCWuUjbYvaxfc2SGWUTGTtkedhrySWrY8datYfSK2QcZHL"
    ),
    "inter-latin-600-normal.woff2": (
        "lI+hrOImxNsIljMZ+LxBmjTPRJCqvHKeOmTiKCfLU1X6p6NCfvF38SRH8pIuu2XO"
    ),
}
TEMPLATE = Path(__file__).with_name("viewer_template.html")
DATA_TOKEN = "/*__YGGDRAS_DATA__*/null"
SUMMARY_HEADING = "## Summary"


class ViewerError(RuntimeError):
    pass


def shelf_of(path: str) -> str:
    return path.split("/", 1)[0]


def plain(verb: str) -> str:
    """A link verb in plain words: "replaced_by" -> "replaced by"."""
    return verb.replace("_", " ")


def note_parts(path: Path) -> dict:
    """Frontmatter fields and body sections the page shows, from one note file."""
    text = path.read_text(encoding="utf-8")
    parts = structural._split(text)
    if parts is None:
        return {"fm": {}, "lines": text.splitlines(), "summary": "", "facts": []}
    fm_text, body, first = parts
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}
    summary = " ".join(
        line.strip() for _, line in structural.section(body, first, SUMMARY_HEADING) if line.strip()
    )
    facts = [
        line[2:].strip()
        for _, line in structural.section(body, first, structural.FACTS_HEADING)
        if line.startswith("- ")
    ]
    return {"fm": fm, "lines": text.splitlines(), "summary": summary, "facts": facts}


def build_view(graph: dict, root: Path, out_dir: Path) -> dict:
    """Everything the page needs: nodes with their text, and edges with their lines."""
    parts = {n["slug"]: note_parts(root / n["path"]) for n in graph["nodes"]}
    degree = {n["slug"]: 0 for n in graph["nodes"]}
    for e in graph["edges"]:
        degree[e["from_slug"]] += 1
        degree[e["to_slug"]] += 1
    nodes = []
    for n in graph["nodes"]:
        p = parts[n["slug"]]
        fm = p["fm"]
        rel = os.path.relpath(root / n["path"], out_dir).replace(os.sep, "/")
        nodes.append(
            {
                "id": n["id"],
                "slug": n["slug"],
                "name": n["name"],
                "type": n["type"],
                "area": str(fm.get("area") or ""),
                "shelf": shelf_of(n["path"]),
                "path": n["path"],
                "href": rel,
                "description": str(fm.get("description") or ""),
                "aliases": n["aliases"],
                "summary": p["summary"],
                "facts": p["facts"],
                "sensitive": str(fm.get("sensitivity") or "") == "high",
                "degree": degree[n["slug"]],
            }
        )
    by_slug = {n["slug"]: n for n in graph["nodes"]}
    edges = []
    for i, e in enumerate(graph["edges"]):
        lines = parts[e["from_slug"]]["lines"]
        line = lines[e["line"] - 1].strip() if 0 < e["line"] <= len(lines) else ""
        if e["kind"] == "mention":
            back = structural.MENTIONED_IN
        else:
            back = structural.OPPOSITE.get(e["reason"], "")
        edges.append(
            {
                "id": i,
                "from": e["from"],
                "to": e["to"],
                "kind": e["kind"],
                "verb": e["reason"],
                "label": plain(e["reason"]),
                "back": plain(back),
                "line": line,
                "fromName": by_slug[e["from_slug"]]["name"],
                "toName": by_slug[e["to_slug"]]["name"],
            }
        )
    return {"schema": graph["schema"], "nodes": nodes, "edges": edges}


def checked(path: Path, sha384: str) -> bytes:
    """A vendored file's bytes, refused unless its hash matches the pin."""
    blob = path.read_bytes()
    digest = base64.b64encode(hashlib.sha384(blob).digest()).decode()
    if digest != sha384:
        raise ViewerError(f"{path.name}: sha384 {digest} does not match the pinned hash")
    return blob


def vis_network_bytes() -> bytes:
    return checked(VIS_NETWORK, VIS_NETWORK_SHA384)


def page(view: dict) -> str:
    """The template with the data embedded; every `<` escaped so no value can end the script."""
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(DATA_TOKEN) != 1:
        raise ViewerError("viewer template must hold the data token exactly once")
    data = json.dumps(view, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")
    return template.replace(DATA_TOKEN, data)


def render(graph: dict, root: Path, out_dir: Path) -> Path:
    """Write graph.html, and the vis-network and font copies next to it."""
    script = vis_network_bytes()
    fonts = {name: checked(VENDOR / name, sha) for name, sha in FONTS.items()}
    out_dir.mkdir(parents=True, exist_ok=True)
    html = out_dir / "graph.html"
    html.write_text(page(build_view(graph, root, out_dir)), encoding="utf-8", newline="\n")
    (out_dir / LOCAL_SCRIPT).write_bytes(script)
    for name, blob in fonts.items():
        (out_dir / name).write_bytes(blob)
    return html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="viewer", description=__doc__.splitlines()[0])
    parser.add_argument("brain", type=Path, help="the brain repo, or a flat brain with --flat")
    parser.add_argument("--flat", action="store_true", help="read every node under BRAIN")
    parser.add_argument("--out-dir", type=Path, help="output folder, --flat only")
    args = parser.parse_args(argv)
    if args.flat != bool(args.out_dir):
        print("--flat and --out-dir go together", file=sys.stderr)
        return 2
    root = args.brain if args.flat else args.brain / structural.LIBRARY
    if not root.is_dir():
        print(f"not a folder: {root}", file=sys.stderr)
        return 2
    shelves = None if args.flat else structural.mapped_shelves()
    out_dir = args.out_dir or structural.generated_dir(args.brain)
    try:
        html = render(structural.build_map(root, shelves), root, out_dir)
    except ViewerError as exc:
        print(f"viewer: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
