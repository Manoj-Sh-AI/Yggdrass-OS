"""Parity gate (D44 §7, prereg.md): life hard-v1 + explore x04/x09, markdown vs rows.

Usage (from the code repo root, with LIA_BRAIN_REPO pointing at the brain repo):
    uv run --project app python evals/experiments/rows-parity/parity.py [--check-only]

The brain copy, results and traces go to local-data/ (git-ignored): they are personal.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "lia-v1"))
sys.path.insert(0, str(CODE / "app" / "tests"))

import harness as H  # noqa: E402

from yggdras.data.brain_db import loader, migrate  # noqa: E402
from yggdras.data.brain_db.store import snapshot  # noqa: E402
from yggdras.data.graph import structural as st  # noqa: E402
from yggdras.processing.lia.library import Library, RowLibrary  # noqa: E402
from yggdras.processing.lia.models import Budget, BudgetStop  # noqa: E402

KEY_COMMIT = "723329b"
KEY_SHA = "252bc0813f630f4a4810c52e946850b3caa8ac45ecb113e4b96795265e985640"
TERMS_SHA = "5c3f3b4201ba3169071874dd91689b382b1091773555986b221972ad1d4f945d"
RUBRIC_SHA = "b5c31bf208e001fe45d7be62efae84efd2132bc8f1c071071f7c7384df3242cd"
EXPLORE = ("x04", "x09")
WATCH = ("q02", "x04", "x09")  # robotics; RK Constructions
OUT = CODE / "local-data" / "rows-parity"
COPY = OUT / "brain"
STOP_AT = 12.0


def _sha(raw: bytes, want: str, what: str) -> None:
    if hashlib.sha256(raw).hexdigest() != want:
        sys.exit(f"STOP: {what} changed since the prereg")


def questions() -> list[dict]:
    raw = subprocess.run(["git", "-C", str(H.BRAIN_REPO), "show", f"{KEY_COMMIT}:evals/hard-v1.md"],
                         capture_output=True, check=True).stdout  # fmt: skip
    _sha(raw, KEY_SHA, "the hard-v1 key")
    terms_raw = (H.LOCAL / "life-terms.json").read_bytes()
    _sha(terms_raw, TERMS_SHA, "the life key terms")
    terms = {int(k): v for k, v in json.loads(terms_raw).items()}
    out, current = [], None
    for line in raw.decode("utf-8").splitlines():
        m = re.match(r"^(\d+)\. (.*)$", line)
        if m:
            n = int(m.group(1))
            current = {"id": f"q{n:02d}", "question": m.group(2), "kind": "life", "expected": "",
                       "gold": [], "citations": [], "keys": terms.get(n, [])}  # fmt: skip
            out.append(current)
            continue
        s = line.strip()
        if current and s.startswith("- Answer: "):
            current["expected"] = s[len("- Answer: ") :]
    for q in out:
        q["abstain"] = q["expected"].startswith("ABSTAIN")
    rubric_raw = (H.LOCAL / "explore-rubric.json").read_bytes()
    _sha(rubric_raw, RUBRIC_SHA, "the explore rubric")
    for q in json.loads(rubric_raw):
        if q["id"] in EXPLORE:
            out.append({"id": q["id"], "kind": "explore", "question": q["question"],
                        "expected": q["required"], "keys": q["keys"], "abstain": False})  # fmt: skip
    return out


def frozen_copy() -> Path:
    if COPY.exists():
        shutil.rmtree(COPY)
    shutil.copytree(H.BRAIN_REPO / "library", COPY / "library",
                    ignore=shutil.ignore_patterns("generated"))  # fmt: skip
    return COPY / "library"


def view_check(files: Library, rows: RowLibrary) -> dict:
    strip = lambda t: re.sub(r"map_version \w+", "map_version V", t)  # noqa: E731
    names = [n.name for n in files.notes.values()]
    return {
        "notes": len(files.notes),
        "same notes": rows.notes.keys() == files.notes.keys(),
        "texts differ": [s for s in files.notes if rows.note_text(s) != files.note_text(s)],
        "citable lines differ": [s for s in files.notes if rows.blocks(s) != files.blocks(s)],
        "searches differ": sum(rows.search_notes(q) != files.search_notes(q) for q in names),
        "manual same": rows.manual() == files.manual(),
        "maps differ": [k for k in files.maps() if strip(rows.maps()[k]) != strip(files.maps()[k])],
    }


def main(argv: list[str]) -> int:
    from brain_pg import Cluster, pg_bin

    from yggdras import config

    config.load_env_file()
    qs = questions()
    root = frozen_copy()
    os.environ["YGGDRAS_BRAIN"] = str(H.BRAIN_REPO)  # the loader refuses the real brain path
    tmp = Path(tempfile.mkdtemp(prefix="yggdras-parity-"))
    cluster = Cluster(pg_bin(), tmp / "data")
    url = cluster.start()
    try:
        import psycopg

        with psycopg.connect(url) as conn:
            migrate.up(conn)
            report = loader.load(conn, COPY)
            row_library = RowLibrary(snapshot(conn))
        files = Library(root)
        check = view_check(files, row_library)
        (OUT / "load-report.txt").write_text(report, encoding="utf-8")
        print(json.dumps(check, indent=1))
        if "--check-only" in argv:
            return 0
        H.SETS["life-md"] = (lambda: qs, root, False)
        H.SETS["life-rows"] = (lambda: qs, root, False)
        budget = Budget(stop_at=STOP_AT)
        runs = {}
        real_library = H.Library
        for r in (1, 2):
            for path in ("md", "rows"):
                name = f"parity__life-{path}__r{r}"
                H.Library = (lambda *_a, **_k: row_library) if path == "rows" else real_library
                try:
                    payload = H.run_set(f"life-{path}", name, budget, H.lia_factory(budget))
                finally:
                    H.Library = real_library
                payload = H.grade(payload, budget)
                H.save(payload, name)
                runs[(path, r)] = payload
                print(f"{name}: spent ${budget.spent:.2f}", flush=True)
        table = summarize(runs)
        (OUT / "parity.md").write_text(table, encoding="utf-8")
        print(table)
    except BudgetStop as exc:
        print(f"STOPPED: {exc}")
        return 3
    finally:
        cluster.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


def summarize(runs: dict) -> str:
    keyed = {q["id"]: q for q in H.SETS["life-md"][0]()}
    lines = ["| path | run | judge | key terms | traps | citations | unverified absence (q02, x04, x09) | $ / q | p50 / p90 s | $ / q by effort |",
             "|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    stats = {}
    for (path, r), payload in sorted(runs.items()):
        s = H.summary(payload)
        watch = {row["qid"]: len((row.get("checks") or {}).get("absence_left", []))
                 for row in payload["rows"] if row["qid"] in WATCH}  # fmt: skip
        effort = "; ".join(f"{k} {n}× ${c:.4f}" for k, (n, _, _, c) in s["effort"].items())
        lines.append(f"| {path} | {r} | {s['judge']}/{len(keyed)} | {s['terms']} | {s['traps']} | "
                     f"{s['citations']} | {watch} | {s['cost']:.4f} | {s['p50']:.1f} / {s['p90']:.1f} | "
                     f"{effort} |")  # fmt: skip
        stats[(path, r)] = (s, watch)
    lines += ["", "## Bars", ""]
    md = [stats[("md", r)][0] for r in (1, 2)]
    rw = [stats[("rows", r)][0] for r in (1, 2)]

    def spread(key):
        return abs(md[0][key] - md[1][key])

    def mean(xs, key):
        return statistics.mean(x[key] for x in xs)

    bars = {
        "accuracy": mean(rw, "judge") >= mean(md, "judge") - spread("judge"),
        "traps": all(s["traps"].split("/")[0] == s["traps"].split("/")[1] for s in md + rw),
        "invented citations": all(s["invented"] == 0 for s in md + rw),
        "absences on q02/x04/x09": all(not any(w.values()) for _, w in stats.values()),
    }
    for key in ("cost", "p50", "p90"):
        bound = max(spread(key), 0.2 * mean(md, key))
        bars[key] = abs(mean(rw, key) - mean(md, key)) <= bound
    lines += [f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in bars.items()]
    lines += ["", f"Switch the default to rows: {'all bars pass' if all(bars.values()) else 'NO'}"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
