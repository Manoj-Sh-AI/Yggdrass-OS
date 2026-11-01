"""Link-recovery follow-up, arm B: copy the stripped corpus and add a roster file.

Graphify itself is not touched. The roster lists every node's name, slug and aliases.

Usage (from the repo root):
    uv run --project app python evals/experiments/link-recovery/arm_b_corpus.py <experiment dir>
"""

import shutil
import sys
from pathlib import Path

from yggdras.data.graph.structural import build_map

exp = Path(sys.argv[1])
src, dst = exp / "brain-stripped", exp / "arm-b-corpus"
if dst.exists():
    sys.exit(f"{dst} already exists; delete it deliberately to rebuild")
shutil.copytree(src, dst)
lines = ["# Roster", "", "Every note in this corpus, with the other names it goes by.", ""]
for n in sorted(build_map(src)["nodes"], key=lambda n: n["slug"]):
    also = ", ".join(a for a in n["aliases"] if a != n["name"])
    lines.append(f"- {n['name']} (note: {n['slug']}" + (f"; also called: {also})" if also else ")"))
(dst / "_roster.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
shutil.copy(dst / "_roster.md", exp / "arm-b-roster.md")
print(f"copied {src} to {dst} with a {len(lines) - 4}-entry roster")
