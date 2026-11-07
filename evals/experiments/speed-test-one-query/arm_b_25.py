"""Arm B (one call, Haiku 5.5, thinking off, streamed) on all 25 Apollo questions.

Questions run one at a time, so timings are not affected by concurrency. A question
whose noun the Stage 1a lookup can't find is recorded and skipped; nothing else is
read. Grading is done by hand afterwards against demo-evals/questions.yaml.
Nothing in the brain is written. Writes arm-b-25.json here.
"""

import json
import sys
from pathlib import Path

import anthropic
import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))  # run with python -I, which drops the script dir

from speed_test import BRAIN_REPO, load_map  # noqa: E402
from speed_test_v2 import find_noun  # noqa: E402
from speed_test_v3 import arm_b  # noqa: E402

QUESTIONS = BRAIN_REPO / "demo-evals" / "questions.yaml"


def main() -> None:
    client = anthropic.Anthropic()
    m = load_map()  # once, not counted
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    rows = []
    for q in questions:
        row = {"id": q["id"], "question": q["question"], "expected": q["expected_answer"]}
        noun = find_noun(m, q["question"])
        if noun is None:
            row["skipped"] = "no noun found by Stage 1a lookup"
        else:
            r = arm_b(client, m, q["question"], noun)
            row.update(
                noun=r["noun"],
                lines_sent=r["line_count"],
                input_tokens=r["total"]["input_tokens"],
                output_tokens=r["total"]["output_tokens"],
                cost_usd=r["total"]["cost_usd"],
                first_word_ms=r["first_word_from_start_ms"],
                end_to_end_ms=r["total"]["end_to_end_ms"],
                answer=r["answer"]["text"],
            )
        rows.append(row)
        print(row["id"], row.get("noun", "SKIPPED"), row.get("input_tokens"), flush=True)
    (HERE / "arm-b-25.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
