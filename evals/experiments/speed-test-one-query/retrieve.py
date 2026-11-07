"""Default retrieval for the Apollo speed test: model pick, structural gather, cited answer.

This is variant C from the v6 comparison (see README.md), made the default and always on.

1. Pick: one Haiku call returns 1-2 node slugs as JSON. The slug list sits in a cached
   system block (slug, name, aliases, description per node; first fact line when a note
   has no description). An empty pick is retried once.
2. Gather (no model): for each picked node, its fact lines and edge lines, plus the fact
   lines of every neighbour. Built from the structural map, rebuilt from the markdown.
3. Answer: one Haiku call. Each gathered node is a search_result block (source = slug,
   title = node name, one text block per line) with citations on. A reply that starts
   with "NOT IN BRAIN" is a decline. There is no extra hop.

The "(src: ...)" tail of a fact line stays in the cited source; it is stripped from the
answer text shown to the user.

Usage (from the repo root):
    uv run --project app --with anthropic python \
        evals/experiments/speed-test-one-query/retrieve.py \
        ask <demo-brain> "Who replaced Ken Mattingly on Apollo 13, and why?"
    uv run --project app --with anthropic python \
        evals/experiments/speed-test-one-query/retrieve.py \
        eval <demo-brain> <out.json> <questions.yaml> [<questions.yaml> ...]
Needs ANTHROPIC_API_KEY. Reads the brain only; writes only the eval output file.
"""

import json
import re
import sys
import time
from pathlib import Path

import yaml
from yggdras.data.graph.structural import build_map

MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50  # $ per MTok, prompts under 100K tokens
CACHE_WRITE, CACHE_READ = 1.25, 0.10  # x input price, 5-minute TTL
PICK_INSTRUCTION = (
    "Pick the 1 or 2 nodes the question is about, as slugs from the list. "
    "Always give at least one: if unsure, give your best guess."
)
ANSWER_INSTRUCTION = (
    "Answer the question from these search results only, citing them. "
    'If the answer is not present, start your reply with exactly "NOT IN BRAIN".'
)
DECLINE = "NOT IN BRAIN"
SRC_TAIL = re.compile(r"\s*\(src:[^)]*\)")


def ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


# --- brain access (no model) -------------------------------------------------------


def note_text(brain: Path, node: dict) -> str:
    return (brain / node["path"]).read_text(encoding="utf-8")


def fact_lines(text: str) -> list[str]:
    """The '- [tag] ...' lines of a note's ## Facts section."""
    if "## Facts" not in text:
        return []
    section = text.split("## Facts", 1)[1].split("\n## ", 1)[0]
    return [line for line in section.splitlines() if line.startswith("- [")]


def description(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    front = yaml.safe_load(text.split("---", 2)[1]) or {}
    return front.get("description")


def signposts(brain: Path, graph: dict) -> tuple[str, int]:
    """One line per node; returns the list and how many needed the first-fact fallback."""
    rows, fallback = [], 0
    for n in graph["nodes"]:
        text = note_text(brain, n)
        desc = description(text)
        if not desc:
            fallback += 1
            facts = fact_lines(text)
            desc = facts[0][2:] if facts else ""
        aliases = ", ".join(a for a in n.get("aliases", []) if a != n["name"])
        rows.append(
            f"{n['slug']} | {n['name']}" + (f" | aka {aliases}" if aliases else "") + f" | {desc}"
        )
    return "\n".join(rows), fallback


def edges_of(graph: dict, node: dict) -> list[dict]:
    """The node's edges in both directions, as readable lines plus the neighbour slug."""
    by_id = {n["id"]: n for n in graph["nodes"]}
    out = []
    for e in graph["edges"]:
        if e["from"] == node["id"]:
            other = by_id[e["to"]]
            line = f"{node['name']} {e['reason']} {other['name']} ({other['slug']})"
        elif e["to"] == node["id"]:
            other = by_id[e["from"]]
            line = f"{other['name']} ({other['slug']}) {e['reason']} {node['name']}"
        else:
            continue
        out.append({"neighbour": other["slug"], "line": line})
    return out


def search_results(brain: Path, graph: dict, picked: list[str]) -> list[dict]:
    """One search_result block per gathered node, picked nodes first."""
    by_slug = {n["slug"]: n for n in graph["nodes"]}
    blocks, seen = [], set()
    for slug in picked:
        edges = edges_of(graph, by_slug[slug])
        for s in [slug, *dict.fromkeys(e["neighbour"] for e in edges)]:
            if s in seen:
                continue
            seen.add(s)
            lines = fact_lines(note_text(brain, by_slug[s]))
            if s == slug:
                lines += [f"Link: {e['line']}" for e in edges]
            if lines:
                blocks.append(
                    {
                        "type": "search_result",
                        "source": s,
                        "title": by_slug[s]["name"],
                        "content": [{"type": "text", "text": line} for line in lines],
                        "citations": {"enabled": True},
                    }
                )
    return blocks


def display_text(answer: str) -> str:
    """The answer as shown to the user: fact-line "(src: ...)" tails removed."""
    return SRC_TAIL.sub("", answer)


def status_of(answer: str) -> str:
    return "not_in_brain" if answer.lstrip().startswith(DECLINE) else "answer"


# --- model calls ---------------------------------------------------------------------


def usage_row(usage, start: float) -> dict:
    written = usage.cache_creation_input_tokens or 0
    read = usage.cache_read_input_tokens or 0
    billed_in = usage.input_tokens + CACHE_WRITE * written + CACHE_READ * read
    return {
        "full_ms": ms(start),
        "uncached_in": usage.input_tokens,
        "cache_write": written,
        "cache_read": read,
        "total_in": usage.input_tokens + written + read,
        "billed_equiv_in": billed_in,
        "output_tokens": usage.output_tokens,
        "cost_usd": (billed_in * PRICE_IN + usage.output_tokens * PRICE_OUT) / 1e6,
    }


def pick(client, system: list, slugs: list[str], question: str) -> tuple[list[str], dict]:
    schema = {
        "type": "object",
        "properties": {"notes": {"type": "array", "items": {"type": "string", "enum": slugs}}},
        "required": ["notes"],
        "additionalProperties": False,
    }
    start = time.perf_counter()
    for _ in range(2):  # one retry on an empty list
        with client.messages.stream(
            model=MODEL,
            max_tokens=256,
            thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": f"Question: {question}"}],
        ) as s:
            final = s.get_final_message()
        text = "".join(b.text for b in final.content if b.type == "text")
        picked = [x for x in dict.fromkeys(json.loads(text)["notes"]) if x in slugs][:2]
        if picked:
            break
    return picked, usage_row(final.usage, start)


def answer(client, question: str, blocks: list[dict]) -> dict:
    start = time.perf_counter()
    first = None
    content = [*blocks, {"type": "text", "text": f"{ANSWER_INSTRUCTION}\n\nQuestion: {question}"}]
    with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "disabled"},
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": content}],
    ) as s:
        for text in s.text_stream:
            if first is None and text:
                first = time.perf_counter() - start
        final = s.get_final_message()
    raw = "".join(b.text for b in final.content if b.type == "text")
    cites = [
        {"source": c.source, "cited_text": c.cited_text}
        for b in final.content
        if b.type == "text" and b.citations
        for c in b.citations
    ]
    return {
        **usage_row(final.usage, start),
        "first_token_ms": round(first * 1000, 3) if first is not None else None,
        "raw_answer": raw,
        "citations": cites,
        "cited_blocks": [
            {"text": b.text, "cited": bool(b.citations)} for b in final.content if b.type == "text"
        ],
    }


class Retriever:
    def __init__(self, brain: Path):
        import anthropic

        self.client = anthropic.Anthropic()
        self.brain = brain
        self.graph = build_map(brain)
        self.slugs = sorted(n["slug"] for n in self.graph["nodes"])
        posts, self.description_fallback = signposts(brain, self.graph)
        self.system = [
            {
                "type": "text",
                "text": f"{PICK_INSTRUCTION}\n\nNodes:\n{posts}",
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def ask(self, question: str) -> dict:
        start = time.perf_counter()
        picked, pick_usage = pick(self.client, self.system, self.slugs, question)
        blocks = search_results(self.brain, self.graph, picked)
        ans = answer(self.client, question, blocks)
        calls = [pick_usage, ans]
        return {
            "question": question,
            "picked": picked,
            "status": status_of(ans["raw_answer"]),
            "answer": display_text(ans["raw_answer"]),
            "raw_answer": ans["raw_answer"],
            "citations": ans["citations"],
            "cited_blocks": ans["cited_blocks"],
            "lines_sent": sum(len(b["content"]) for b in blocks),
            "pick_ms": pick_usage["full_ms"],
            "first_token_ms": round(pick_usage["full_ms"] + ans["first_token_ms"], 3),
            "end_to_end_ms": ms(start),
            "total_in": sum(c["total_in"] for c in calls),
            "cached_in": sum(c["cache_read"] for c in calls),
            "billed_equiv_in": round(sum(c["billed_equiv_in"] for c in calls), 1),
            "output_tokens": sum(c["output_tokens"] for c in calls),
            "cost_usd": sum(c["cost_usd"] for c in calls),
        }


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "ask":
        result = Retriever(Path(argv[1])).ask(argv[2])
        print(result["answer"])
        print(
            "\nSources:",
            ", ".join(dict.fromkeys(c["source"] for c in result["citations"])) or "none",
        )
        return 0
    if len(argv) >= 4 and argv[0] == "eval":
        retriever, out = Retriever(Path(argv[1])), Path(argv[2])
        rows = []
        for qfile in argv[3:]:
            for q in yaml.safe_load(Path(qfile).read_text(encoding="utf-8"))["questions"]:
                row = {"id": q["id"], "set": Path(qfile).stem, **retriever.ask(q["question"])}
                rows.append(row)
                print(row["id"], row["picked"], row["status"], flush=True)
                out.write_text(
                    json.dumps({"variant": "C", "rows": rows}, indent=2), encoding="utf-8"
                )
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
