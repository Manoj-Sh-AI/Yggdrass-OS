"""Arm B v5: v4 with a reordered, enum-free answer schema. All 25 questions, 3 runs.

Changes from v4:
1. Answer schema field order is text, status, need, so the model writes its text
   before choosing a status.
2. The answer schema has no slug enum: "need" is a plain string (or null), checked in
   code against the edges sent under the same rules as v3/v4. The pick schema keeps
   its enum.
Everything else (pick, gather, NEED handling, caching, timing) is v4's code.
Writes arm-b-v5.json here.
"""

import json
import sys
from pathlib import Path

import anthropic
import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))  # run with python -I, which drops the script dir

import arm_b_v4  # noqa: E402
from arm_b_v2 import QUESTIONS, signposts  # noqa: E402
from speed_test import load_map  # noqa: E402


def answer_schema(slugs: list[str], allow_need: bool) -> dict:
    statuses = ["answer", "not_in_brain", *(["need"] if allow_need else [])]
    need = {"anyOf": [{"type": "string"}, {"type": "null"}]} if allow_need else {"type": "null"}
    return {
        "type": "object",
        "properties": {"text": {"type": "string"}, "status": {"type": "string", "enum": statuses}, "need": need},
        "required": ["text", "status", "need"],
        "additionalProperties": False,
    }


arm_b_v4.answer_schema = answer_schema  # run_one looks this up at call time


def main() -> None:
    client = anthropic.Anthropic()
    m = load_map()  # once, not counted
    slugs = sorted(n["slug"] for n in m["graph"]["nodes"])
    posts, _ = signposts(m)  # built once, not counted
    system = [
        {
            "type": "text",
            "text": f"{arm_b_v4.PICK_INSTRUCTION}\n\nNodes:\n{posts}",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    runs = []
    for run in range(1, arm_b_v4.RUNS + 1):
        rows = []
        for q in questions:
            row = arm_b_v4.run_one(client, m, system, slugs, q)
            rows.append(row)
            print(run, row["id"], row["picked"], row["status"], row["need"], row["need_status"], flush=True)
        runs.append(rows)
        (HERE / "arm-b-v5.json").write_text(json.dumps({"runs": runs}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
