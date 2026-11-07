"""Grade Arm B v6 result files: status first, then the answer text must hold every key term.

Key terms come from each question's required_facts. A negative is correct when its status
is not_in_brain. Prints every miss with its reason so it can be checked by hand, and writes
the grade into each file. Usage: python grade_v6.py arm-b-v6-A-1.json [...]
"""

import json
import sys
from pathlib import Path

NEGATIVE = {"n01", "n02", "n03", "n04", "n05", "h09", "h10"}
KEYS = {
    "d01": ["1968-12-21", "borman", "lovell", "anders"], "d02": ["beech"], "d03": ["1962-07-11"],
    "d04": ["presidential medal of freedom", "2016-11-22"], "d05": ["twelve"], "d06": ["square", "round"],
    "d07": ["descartes"], "d08": ["priority scheduling", "infer"], "d09": ["fire", "grissom", "white", "chaffee"],
    "m01": ["duke", "lovell"], "m02": ["north american aviation", "65", "28"],
    "m03": ["cortright", "langley", "fire", "oxygen tank"], "m04": ["saturn v", "von braun", "marshall"],
    "m05": ["duke", "apollo 16"], "p01": ["95", "40", "5-6"], "p02": ["600", "1100", "5-5"],
    "p03": ["5-4", "5-6", "crater"], "t01": ["fra mauro", "safe return", "1970-04-13", "abort"],
    "t02": ["backup command module pilot", "prime command module pilot", "1970-04-10"],
    "t03": ["manned spacecraft center", "1973-02-19"],
    "h01": ["grumman"], "h02": ["columbia"], "h03": ["110", "13"], "h04": ["apollo 17", "december 1972", "twelve"],
    "h05": ["lovell", "gemini 7", "gemini 12"], "h06": ["beech", "oxygen tank"], "h07": ["haise", "childhood"],
    "h08": ["apollo 4", "1967-11-09"],
}


def grade(row: dict) -> tuple[bool, str]:
    if row["id"] in NEGATIVE:
        ok = row["status"].startswith("not_in_brain")
        return ok, "" if ok else f"status {row['status']} on a negative"
    if row["status"] != "answer":
        return False, f"status {row['status']} on an answerable question"
    missing = [k for k in KEYS[row["id"]] if k not in row["answer"].lower()]
    return not missing, f"answer text lacks {missing}" if missing else ""


def main() -> None:
    for name in sys.argv[1:]:
        path = Path(name)
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data["rows"]:
            row["correct"], row["miss"] = grade(row)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        rows = data["rows"]
        old = sum(r["correct"] for r in rows if r["set"] == "old")
        new = sum(r["correct"] for r in rows if r["set"] == "new")
        print(f"== {name}: old {old}/25, new {new}/10")
        for r in rows:
            if not r["correct"]:
                print(f"  MISS {r['id']} picked={r['picked']} {r['miss']} | {r['answer'][:400]!r}")


if __name__ == "__main__":
    main()
