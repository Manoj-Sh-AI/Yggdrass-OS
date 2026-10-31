"""Viewer: draw our structural map with Graphify's HTML view, offline.

Graphify is a viewer only (D32 as amended 2026-10-31): no extraction, no query, no model
pass, no Graphify-built links. Every node, link and verb comes from our own map; Graphify
only renders it. Its HTML loads vis-network from the internet, so after rendering the
script tag is pointed at a local, hash-checked copy and the page works offline.

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
import re
import shutil
import subprocess
import sys
from pathlib import Path

from yggdras.data.graph import structural

GRAPHIFY_VERSION = "0.9.95"
VIS_NETWORK = Path(__file__).with_name("vendor") / "vis-network-9.1.6.min.js"
# The integrity hash Graphify 0.9.95 pins for vis-network 9.1.6 on unpkg.
VIS_NETWORK_SHA384 = "Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"
LOCAL_SCRIPT = "vis-network.min.js"
CDN_SCRIPT = re.compile(
    r'<script src="https://unpkg\.com/vis-network@9\.1\.6/standalone/umd/vis-network\.min\.js"'
    r'\s+integrity="sha384-[^"]+"\s+crossorigin="anonymous"></script>'
)
# Graphify settings for every call: no model backend, no query log in the home folder.
GRAPHIFY_ENV = {"GRAPHIFY_BACKEND": "none", "GRAPHIFY_QUERY_LOG_DISABLE": "1"}


class ViewerError(RuntimeError):
    pass


def shelf_of(path: str) -> str:
    return path.split("/", 1)[0]


def to_graphify(graph: dict) -> tuple[dict, dict[str, str]]:
    """Our map as Graphify's node-link graph.json, plus its community labels.

    Communities are shelves (each note's top-level folder), so the view colours by shelf.
    """
    shelves = sorted({shelf_of(n["path"]) for n in graph["nodes"]})
    community = {s: i for i, s in enumerate(shelves)}
    data = {
        "directed": False,  # Graphify's own convention; direction travels in _src/_tgt
        "multigraph": True,  # keep two different links between the same pair
        "graph": {},
        "nodes": [
            {
                "id": n["id"],
                "label": n["name"],
                "source_file": n["path"],
                "file_type": "document",
                "community": community[shelf_of(n["path"])],
            }
            for n in graph["nodes"]
        ],
        "links": [
            {
                "source": e["from"],
                "target": e["to"],
                "_src": e["from"],
                "_tgt": e["to"],
                "relation": e["reason"],
                "confidence": "EXTRACTED",
            }
            for e in graph["edges"]
        ],
    }
    return data, {str(i): s for s, i in community.items()}


def vis_network_bytes() -> bytes:
    """The local vis-network copy, refused unless its hash matches Graphify's pin."""
    blob = VIS_NETWORK.read_bytes()
    digest = base64.b64encode(hashlib.sha384(blob).digest()).decode()
    if digest != VIS_NETWORK_SHA384:
        raise ViewerError(f"{VIS_NETWORK.name}: sha384 {digest} does not match the pinned hash")
    return blob


def localize(html: str) -> str:
    """Point the page's one vis-network script tag at the local copy."""
    new, count = CDN_SCRIPT.subn(f'<script src="{LOCAL_SCRIPT}"></script>', html)
    if count != 1:
        raise ViewerError(f"expected one vis-network script tag in graph.html, found {count}")
    if re.search(r"<script[^>]+src=\"https?://", new):
        raise ViewerError("graph.html still loads a script from the internet")
    return new


def graphify_version(exe: str) -> str:
    out = subprocess.run(
        [exe, "--version"], capture_output=True, text=True, check=True, env=_env()
    ).stdout
    return out.split()[-1] if out.split() else ""


def _env() -> dict[str, str]:
    return {**os.environ, **GRAPHIFY_ENV}


def render(graph: dict, out_dir: Path, exe: str = "graphify") -> Path:
    """Write graph.json, render graph.html with Graphify, and make it work offline."""
    version = graphify_version(exe)
    if version != GRAPHIFY_VERSION:
        raise ViewerError(f"Graphify {GRAPHIFY_VERSION} is pinned (D32); found {version!r}")
    script = vis_network_bytes()
    data, labels = to_graphify(graph)
    out_dir.mkdir(parents=True, exist_ok=True)
    graph_json = out_dir / "graph.json"
    graph_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / ".graphify_labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
    subprocess.run(
        [exe, "export", "html", "--graph", str(graph_json)],
        check=True,
        capture_output=True,
        env=_env(),
    )
    html = out_dir / "graph.html"
    html.write_text(localize(html.read_text(encoding="utf-8")), encoding="utf-8")
    (out_dir / LOCAL_SCRIPT).write_bytes(script)
    return html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="viewer", description=__doc__.splitlines()[0])
    parser.add_argument("brain", type=Path, help="the brain repo, or a flat brain with --flat")
    parser.add_argument("--flat", action="store_true", help="read every node under BRAIN")
    parser.add_argument("--out-dir", type=Path, help="output folder, --flat only")
    parser.add_argument("--graphify", default=shutil.which("graphify") or "graphify")
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
        html = render(structural.build_map(root, shelves), out_dir, args.graphify)
    except (ViewerError, subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"viewer: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
