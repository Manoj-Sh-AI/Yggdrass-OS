"""Link-recovery follow-up: reconstruct run 2's two batches with Graphify's own packer, read-only.

Run 2's single chunk was truncated and split into halves (`chunk[:mid]`, `chunk[mid:]`,
`_extract_with_adaptive_retry` in graphify/llm.py). This calls Graphify's `detect` and
`_pack_chunks_by_tokens` to get the same order, then halves it the same way.

Usage (from the repo root, with the Python of the pinned Graphify tool install):
    <graphifyy tool python> -I evals/experiments/link-recovery/run2_batches.py <experiment dir>
"""

import json
import sys
from pathlib import Path

from graphify.detect import detect
from graphify.llm import _pack_chunks_by_tokens

exp = Path(sys.argv[1]).resolve()
root = exp / "brain-stripped"
docs = [Path(p) for p in detect(root)["files"]["document"]]
chunks = _pack_chunks_by_tokens(docs, token_budget=60_000)
assert len(chunks) == 1, f"expected one packed chunk, got {len(chunks)}"
mid = len(chunks[0]) // 2
halves = [chunks[0][:mid], chunks[0][mid:]]
out = {
    "note": "run 2 batches; paths relative to brain-stripped/",
    "batches": [[p.relative_to(root).as_posix() for p in h] for h in halves],
}
(exp / "run-2-batches.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print([len(b) for b in out["batches"]])
