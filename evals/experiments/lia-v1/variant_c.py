"""Variant C (the current pipeline), ported to run beside Lia with the same model.

Source: evals/experiments/speed-test-one-query/retrieve.py on branch
retrieval-baseline-citations (PR #18). Same three steps: one pick call returns 1-2 slugs
from a cached signpost list; free code gathers each picked note's fact and link lines plus its
neighbours' fact lines; one cited answer call over search_result blocks.

Port changes (prereg.md, "Deviations"): the model is a parameter; thinking is left at the
model default (Opus 5.5 and Sonnet 5.5 refuse "disabled"), effort low as before; fact lines
are read in both formats (the demo's "- [tag] ..." and the library's "- ..."); the graph is
built in library mode for a library brain; costs use the 5.5 cache rates. Nothing else.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import yaml

from yggdras.data.graph import structural as st
from yggdras.processing.lia.models import PRICES

PICK_INSTRUCTION = (
    "Pick the 1 or 2 nodes the question is about, as slugs from the list. "
    "Always give at least one: if unsure, give your best guess."
)
ANSWER_INSTRUCTION = (
    "Answer the question from these search results only, citing them. "
    'If the answer is not present, start your reply with exactly "NOT IN BRAIN".'
)
DECLINE = "NOT IN BRAIN"


def _cost(model, usage) -> float:
    p_in, p_out, read_x, _ = PRICES[model]
    write = usage.cache_creation_input_tokens or 0
    read = usage.cache_read_input_tokens or 0
    return (usage.input_tokens * p_in + write * p_in * 1.25 + read * p_in * read_x
            + usage.output_tokens * p_out) / 1e6  # fmt: skip


def fact_lines(text: str) -> list[str]:
    if "## Facts" not in text:
        return []
    section = text.split("## Facts", 1)[1].split("\n## ", 1)[0]
    return [line for line in section.splitlines() if line.startswith("- ")]


class VariantC:
    def __init__(self, root: Path, flat: bool, model: str, budget=None):
        import anthropic

        self.client = anthropic.Anthropic()
        self.root, self.model, self.budget = root, model, budget
        self.graph = st.build_map(root, None if flat else st.mapped_shelves())
        self.by_slug = {n["slug"]: n for n in self.graph["nodes"]}
        self.slugs = sorted(self.by_slug)
        rows = []
        for n in self.graph["nodes"]:
            text = self._text(n["slug"])
            front = (yaml.safe_load(st._split(text)[0]) or {}) if text.startswith("---") else {}
            desc = front.get("description") or (fact_lines(text)[0][2:] if fact_lines(text) else "")
            aliases = ", ".join(a for a in n.get("aliases", []) if a != n["name"])
            rows.append(f"{n['slug']} | {n['name']}" + (f" | aka {aliases}" if aliases else "")
                        + f" | {desc}")  # fmt: skip
        self.system = [{"type": "text", "text": f"{PICK_INSTRUCTION}\n\nNodes:\n" + "\n".join(rows),
                        "cache_control": {"type": "ephemeral"}}]  # fmt: skip

    def _text(self, slug: str) -> str:
        return (self.root / self.by_slug[slug]["path"]).read_text(encoding="utf-8")

    def _edges(self, slug: str) -> list[dict]:
        node, out = self.by_slug[slug], []
        by_id = {n["id"]: n for n in self.graph["nodes"]}
        for e in self.graph["edges"]:
            if e["from"] == node["id"]:
                other = by_id[e["to"]]
                out.append({"n": other["slug"], "line": f"{node['name']} {e['reason']} {other['name']} ({other['slug']})"})
            elif e["to"] == node["id"]:
                other = by_id[e["from"]]
                out.append({"n": other["slug"], "line": f"{other['name']} ({other['slug']}) {e['reason']} {node['name']}"})
        return out

    def _call(self, **kw):
        if self.budget:
            self.budget.check()
        start = time.perf_counter()
        r = self.client.messages.create(model=self.model, output_config={"effort": "low", **kw.pop("fmt", {})}, **kw)
        cost = _cost(self.model, r.usage)
        if self.budget:
            self.budget.add(cost)
        return r, cost, (time.perf_counter() - start) * 1000

    def ask(self, question: str, qid: str = "q") -> dict:
        start = time.perf_counter()
        schema = {"type": "object", "additionalProperties": False, "required": ["notes"],
                  "properties": {"notes": {"type": "array", "items": {"type": "string", "enum": self.slugs}}}}  # fmt: skip
        cost, picked = 0.0, []
        for _ in range(2):
            r, c, _ = self._call(max_tokens=1024, system=self.system,
                                 fmt={"format": {"type": "json_schema", "schema": schema}},
                                 messages=[{"role": "user", "content": f"Question: {question}"}])  # fmt: skip
            cost += c
            text = "".join(b.text for b in r.content if b.type == "text")
            picked = [x for x in dict.fromkeys(json.loads(text)["notes"]) if x in self.by_slug][:2]
            if picked:
                break
        blocks, seen = [], set()
        for slug in picked:
            edges = self._edges(slug)
            for s in [slug, *dict.fromkeys(e["n"] for e in edges)]:
                if s in seen:
                    continue
                seen.add(s)
                lines = fact_lines(self._text(s)) + ([f"Link: {e['line']}" for e in edges] if s == slug else [])
                if lines:
                    blocks.append({"type": "search_result", "source": s, "title": self.by_slug[s]["name"],
                                   "content": [{"type": "text", "text": x} for x in lines],
                                   "citations": {"enabled": True}})  # fmt: skip
        content = [*blocks, {"type": "text", "text": f"{ANSWER_INSTRUCTION}\n\nQuestion: {question}"}]
        r, c, _ = self._call(max_tokens=2048, messages=[{"role": "user", "content": content}])
        cost += c
        raw = "".join(b.text for b in r.content if b.type == "text")
        return {"id": qid, "question": question, "answer": raw, "abstain": raw.lstrip().startswith(DECLINE),
                "opened": sorted(seen), "picked": picked, "citations": [], "citation_check": None,
                "searches": 0, "cost_usd": cost, "latency_ms": round((time.perf_counter() - start) * 1000, 1)}  # fmt: skip
