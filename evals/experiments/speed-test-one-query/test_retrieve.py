"""Model-free checks for retrieve.py, on the synthetic fixture brain.

Run from the repo root:
    uv run --project app pytest evals/experiments/speed-test-one-query/test_retrieve.py
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from retrieve import (  # noqa: E402
    display_text,
    edges_of,
    fact_lines,
    search_results,
    signposts,
    status_of,
)
from yggdras.data.graph.structural import build_map  # noqa: E402

FIXTURE = HERE.parents[1] / "fixture-brain"


def test_display_text_strips_src_tails_only():
    raw = "Launched 1968-12-21 with Frank Borman (src: NASA history, 2026-10-24). Crew of three."
    assert display_text(raw) == "Launched 1968-12-21 with Frank Borman. Crew of three."
    assert display_text("No tail here (see p.5-6).") == "No tail here (see p.5-6)."


def test_status_of_reads_the_decline_prefix():
    assert status_of("NOT IN BRAIN: no cost figure") == "not_in_brain"
    assert status_of("  NOT IN BRAIN") == "not_in_brain"
    assert status_of("The answer is X. It is NOT IN BRAIN elsewhere.") == "answer"


def test_fact_lines_take_only_the_facts_section():
    text = (
        "---\nslug: a\n---\n\n## Facts\n\n- [stated] One (src: x, 2026-01-01)\nnote\n\n"
        "## Links\n\n- [[b]]\n"
    )
    assert fact_lines(text) == ["- [stated] One (src: x, 2026-01-01)"]
    assert fact_lines("no facts here") == []


def test_signposts_cover_every_node():
    graph = build_map(FIXTURE)
    posts, fallback = signposts(FIXTURE, graph)
    assert len(posts.splitlines()) == len(graph["nodes"])
    assert fallback == 0


def test_search_results_keep_src_tails_and_put_picked_node_first():
    graph = build_map(FIXTURE)
    node = next(n for n in graph["nodes"] if edges_of(graph, n))
    blocks = search_results(FIXTURE, graph, [node["slug"]])
    assert blocks[0]["source"] == node["slug"]
    assert blocks[0]["citations"] == {"enabled": True}
    neighbours = {e["neighbour"] for e in edges_of(graph, node)}
    assert {b["source"] for b in blocks[1:]} <= neighbours
    texts = [c["text"] for b in blocks for c in b["content"]]
    assert any("(src:" in t for t in texts)
    assert any(c["text"].startswith("Link: ") for c in blocks[0]["content"])
    assert not any(c["text"].startswith("Link: ") for b in blocks[1:] for c in b["content"])
