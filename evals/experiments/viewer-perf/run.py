"""Viewer performance check: a synthetic library of N notes and about 2N links.

Builds invented notes (no personal data) in a temp folder, renders the viewer, opens it in
headless Edge with the network blocked, and reports the page's own layout time
(`data-ready-ms`) and the wall-clock time of the whole browser run.

Usage (from app/): uv run python ../evals/experiments/viewer-perf/run.py 3000 [--shot out.png]
"""

import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from yggdras.data.graph import structural, viewer

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
TYPES = ["project", "goal", "decision", "event", "topic", "person", "place", "source", "concept"]
FOLDER = {
    "person": "11-people",
    "place": "12-places",
    "source": "13-sources",
    "concept": "10-ideas",
}
VERBS = ["part_of", "depends_on", "advances", "uses", "about", "related_to", "informed_by"]


def build(root: Path, n: int, seed: int = 7) -> None:
    rnd = random.Random(seed)
    slugs = [f"note-{i:05d}" for i in range(n)]
    for i, slug in enumerate(slugs):
        typ = TYPES[i % len(TYPES)]
        area = structural.AREAS[rnd.randrange(len(structural.AREAS))]
        folder = FOLDER.get(typ, area)
        targets = rnd.sample(slugs, 2)
        mention = rnd.choice(slugs)
        text = (
            f"---\nid: id-{slug}\nslug: {slug}\nname: Note {i}\ntype: {typ}\narea: {area}\n"
            f"description: Invented note {i}\naliases: []\n---\n\n# Note {i}\n\n"
            f"## Summary\n\nInvented.\n\n## Facts\n\n- Note {i} mentions [[{mention}]]. "
            f"(src: self, 2030-01-01)\n\n## Links\n\n"
            + "".join(f"- {rnd.choice(VERBS)} [[{t}]]\n" for t in targets)
        )
        path = root / folder / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def main() -> None:
    n = int(sys.argv[1])
    shot = sys.argv[sys.argv.index("--shot") + 1] if "--shot" in sys.argv else None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "library"
        build(root, n)
        graph = structural.build_map(root, structural.mapped_shelves())
        html = viewer.render(graph, root, Path(tmp) / "out")
        with tempfile.TemporaryDirectory() as profile:
            args = [EDGE, "--headless=new", "--disable-gpu", "--window-size=1600,1000",
                    "--virtual-time-budget=60000", "--host-resolver-rules=MAP * ~NOTFOUND",
                    f"--user-data-dir={profile}"]  # fmt: skip
            start = time.perf_counter()
            dom = subprocess.run(args + ["--dump-dom", html.as_uri()], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace").stdout  # fmt: skip
            wall = time.perf_counter() - start
            if shot:
                subprocess.run(args + [f"--screenshot={Path(shot).resolve()}", html.as_uri()],
                               capture_output=True)  # fmt: skip
        body = re.search(r"<body[^>]*>", dom).group(0)
        ready = re.search(r'data-ready-ms="(\d+)"', body)
        layout = f"{int(ready.group(1)) / 1000} s" if ready else "?"
        print(
            f"notes {len(graph['nodes'])}, links {len(graph['edges'])}, "
            f"page size {html.stat().st_size / 1e6:.1f} MB, "
            f"ready {'yes' if ready else 'NO'}, layout {layout} "
            f"(page clock), browser run {wall:.1f} s wall, error: {'data-error' in body}"
        )


if __name__ == "__main__":
    main()
