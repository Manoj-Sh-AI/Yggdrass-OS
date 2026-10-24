"""Eval runner: shows questions and records verdicts. It never grades.

Usage:
    python -m yggdras.tooling.eval_runner check QUESTIONS
    python -m yggdras.tooling.eval_runner show QUESTIONS [--id ID] [--prompt-only]
    python -m yggdras.tooling.eval_runner record QUESTIONS --out DIR
        [--verdicts FILE] [--brain PATH]

Verdicts come from a person, either typed in at the prompt or read from a YAML
file mapping question id to {pass, files_opened, notes}.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

KINDS = ("direct", "multi-hop", "page-precise", "negative", "temporal")
MINIMUMS = {"negative": 5, "multi-hop": 3, "page-precise": 2, "temporal": 2}
SET_SIZE = (20, 30)
EXIT_COUNT = 10


@dataclass
class Question:
    id: str
    kind: str
    question: str
    expected_answer: str
    required_facts: list[str] = field(default_factory=list)
    expected_nodes: list[str] = field(default_factory=list)
    exit: bool = False


@dataclass
class Verdict:
    passed: bool
    files_opened: list[str]
    notes: str = ""


def load_questions(path: Path) -> list[Question]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("questions")
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a top-level 'questions' list")
    questions = []
    for i, item in enumerate(raw):
        missing = [k for k in ("id", "kind", "question", "expected_answer") if not item.get(k)]
        if missing:
            raise ValueError(f"{path}: question {i} is missing {', '.join(missing)}")
        questions.append(
            Question(
                id=str(item["id"]),
                kind=item["kind"],
                question=item["question"],
                expected_answer=item["expected_answer"],
                required_facts=list(item.get("required_facts") or []),
                expected_nodes=list(item.get("expected_nodes") or []),
                exit=bool(item.get("exit", False)),
            )
        )
    return questions


def composition_problems(questions: list[Question]) -> list[str]:
    """Check the set against the phase 1a composition rules."""
    problems = []
    lo, hi = SET_SIZE
    if not lo <= len(questions) <= hi:
        problems.append(f"set has {len(questions)} questions, needs {lo}-{hi}")
    ids = [q.id for q in questions]
    problems += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for q in questions:
        if q.kind not in KINDS:
            problems.append(f"{q.id}: unknown kind '{q.kind}'")
        if q.kind != "negative" and not q.required_facts:
            problems.append(f"{q.id}: no required facts")
        if q.kind != "negative" and not [n for n in q.expected_nodes if n != "index.md"]:
            problems.append(f"{q.id}: no expected node beyond index.md")
    for kind, minimum in MINIMUMS.items():
        count = sum(q.kind == kind for q in questions)
        if count < minimum:
            problems.append(f"{count} {kind} questions, needs at least {minimum}")
    exits = sum(q.exit for q in questions)
    if exits != EXIT_COUNT:
        problems.append(f"{exits} exit questions, needs exactly {EXIT_COUNT}")
    return problems


def render(q: Question, prompt_only: bool = False) -> str:
    if prompt_only:
        return q.question
    lines = [
        f"[{q.id}] {q.kind}{' (exit)' if q.exit else ''}",
        f"  Q: {q.question}",
        f"  Expected: {q.expected_answer}",
        "  Required facts: " + ("; ".join(q.required_facts) or "none (negative)"),
        "  Expected nodes: " + (", ".join(q.expected_nodes) or "index.md"),
    ]
    return "\n".join(lines)


def load_verdicts(path: Path) -> dict[str, Verdict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    verdicts = {}
    for qid, v in data.items():
        if not isinstance(v, dict) or not isinstance(v.get("pass"), bool):
            raise ValueError(f"{path}: verdict for {qid} needs a boolean 'pass'")
        verdicts[str(qid)] = Verdict(
            passed=v["pass"],
            files_opened=list(v.get("files_opened") or []),
            notes=str(v.get("notes") or ""),
        )
    return verdicts


def prompt_verdicts(questions: list[Question], ask=input, say=print) -> dict[str, Verdict]:
    verdicts = {}
    for q in questions:
        say(render(q))
        answer = ""
        while answer not in ("y", "n"):
            answer = ask("  Pass? [y/n] ").strip().lower()
        files = ask("  Files opened (comma-separated): ")
        notes = ask("  Notes: ")
        verdicts[q.id] = Verdict(
            passed=answer == "y",
            files_opened=[f.strip() for f in files.split(",") if f.strip()],
            notes=notes.strip(),
        )
    return verdicts


def build_result(
    questions: list[Question],
    verdicts: dict[str, Verdict],
    questions_path: Path,
    brain: str | None,
    today: dt.date,
) -> dict:
    missing = [q.id for q in questions if q.id not in verdicts]
    unknown = sorted(set(verdicts) - {q.id for q in questions})
    if missing or unknown:
        raise ValueError(f"verdicts missing for {missing}, unknown ids {unknown}")
    entries = [
        {
            "id": q.id,
            "kind": q.kind,
            "exit": q.exit,
            "pass": verdicts[q.id].passed,
            "files_opened": verdicts[q.id].files_opened,
            "notes": verdicts[q.id].notes,
        }
        for q in questions
    ]
    passed = sum(e["pass"] for e in entries)
    return {
        "date": today.isoformat(),
        "questions_file": questions_path.as_posix(),
        "brain": brain,
        "summary": {"total": len(entries), "passed": passed, "failed": len(entries) - passed},
        "gate_met": passed == len(entries),
        "results": entries,
    }


def write_result(result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 1
    while (path := out_dir / f"{result['date']}-run-{n}.yaml").exists():
        n += 1
    path.write_text(yaml.safe_dump(result, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval_runner", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "show", "record"):
        p = sub.add_parser(name)
        p.add_argument("questions", type=Path)
        if name == "show":
            p.add_argument("--id")
            p.add_argument("--prompt-only", action="store_true")
        if name == "record":
            p.add_argument("--out", type=Path, required=True)
            p.add_argument("--verdicts", type=Path)
            p.add_argument("--brain")
    args = parser.parse_args(argv)

    questions = load_questions(args.questions)
    if args.command == "check":
        problems = composition_problems(questions)
        for problem in problems:
            print(problem)
        print("composition ok" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if args.command == "show":
        chosen = [q for q in questions if args.id in (None, q.id)]
        if not chosen:
            print(f"no question with id {args.id}", file=sys.stderr)
            return 1
        print("\n\n".join(render(q, args.prompt_only) for q in chosen))
        return 0

    verdicts = load_verdicts(args.verdicts) if args.verdicts else prompt_verdicts(questions)
    result = build_result(questions, verdicts, args.questions, args.brain, dt.date.today())
    path = write_result(result, args.out)
    s = result["summary"]
    print(f"{s['passed']}/{s['total']} passed; gate {'met' if result['gate_met'] else 'NOT met'}")
    print(f"wrote {path}")
    return 0 if result["gate_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
