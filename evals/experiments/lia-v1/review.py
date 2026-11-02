"""List the answers due for hand review (every grader disagreement plus 20% of agreements,
seed 7), and record the reviewer's final grades.

    uv run python ../evals/experiments/lia-v1/review.py list [--set apollo|life]
    uv run python ../evals/experiments/lia-v1/review.py set <key> <grade> [<key> <grade> ...]
    uv run python ../evals/experiments/lia-v1/review.py confirm   # judge grade stands for the rest listed

Apollo overrides go to this folder; life overrides stay in local-data/.
"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as h  # noqa: E402


def files():
    for folder in (HERE / "results", h.LOCAL / "results"):
        if folder.is_dir():
            yield from sorted(folder.glob("*.graded.json"))


def overrides_path(set_name: str) -> Path:
    return (h.LOCAL if set_name == "life" else HERE) / "overrides.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def due() -> list[tuple[str, dict, dict]]:
    out = []
    for path in files():
        data = json.loads(path.read_text(encoding="utf-8"))
        rng = random.Random(f"7|{path.name}")
        keyed = {q["id"]: q for q in h.SETS[data["set"]][0]()}
        for row in data["rows"]:
            key = f"{data['arm']}|{data['set']}|{data['run']}|{row['qid']}|{data['model']}"
            agree = row.get("grade_judge") == row.get("grade_terms")
            if not agree or rng.random() < 0.2:
                out.append((key, row, keyed[row["qid"]]))
    return out


def main():
    cmd = sys.argv[1]
    if cmd == "list":
        only = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else None
        for key, row, q in due():
            set_name = key.split("|")[1]
            if only and not set_name.startswith(only):
                continue
            if key in load(overrides_path(set_name)):
                continue
            ans = " ".join((row.get("answer") or "").split())
            print(f"## {key}  judge={row.get('grade_judge')} terms={row.get('grade_terms')}")
            print(f"Q: {q['question']}\nKEY: {'ABSTAIN' if q['abstain'] else q['expected']}\nA: {ans}\n")
    elif cmd == "set":
        args = sys.argv[2:]
        for key, grade in zip(args[::2], args[1::2], strict=True):
            path = overrides_path(key.split("|")[1])
            data = load(path)
            data[key] = grade
            path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    elif cmd == "confirm":
        for key, row, _ in due():
            path = overrides_path(key.split("|")[1])
            data = load(path)
            if key not in data:
                data[key] = row.get("grade_judge")
                path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
