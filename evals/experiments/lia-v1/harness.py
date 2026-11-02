"""lia-v1: run, grade and summarise Lia's experiments and gate (prereg.md).

Usage (from the code repo's app/ folder, ANTHROPIC_API_KEY set):
    uv run python ../evals/experiments/lia-v1/harness.py verify
    uv run python ../evals/experiments/lia-v1/harness.py run <arm> <set> <runs> [--model M]
    uv run python ../evals/experiments/lia-v1/harness.py grade
    uv run python ../evals/experiments/lia-v1/harness.py e7 [--model M]
    uv run python ../evals/experiments/lia-v1/harness.py table

Sets: apollo-hard (hard-v8, the only tuning set), apollo-held (held-out-v8), life (hard-v1).
Real-brain results and traces go to local-data/ only; Apollo ones into this folder.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CODE = HERE.parents[2]
# Both come from the environment: the brain repo, and a clean worktree of it at PIN.
BRAIN_REPO = Path(os.environ.get("LIA_BRAIN_REPO", "../yggdras-brain"))
BRAIN_PIN = Path(os.environ.get("LIA_BRAIN_PIN", "../yggdras-brain-pin"))
PIN, KEY_COMMIT = "f6fe26a", "723329b"
KEY_SHA = "252bc0813f630f4a4810c52e946850b3caa8ac45ecb113e4b96795265e985640"
SKILLS_SHA = "11bce556fe5b37c2c9141cea8f9d3dce0bf14a395f09eb9e6ac7dff8ea3dab3b"
LOCAL = CODE / "local-data" / "lia-v1"
CAP, STOP = 15.0, 12.0
WORKERS = 6
JUDGE = "claude-haiku-5-5"

from yggdras.processing.lia.lia import Lia, LiaConfig, load_skills  # noqa: E402
from yggdras.processing.lia.library import Library, MapOptions  # noqa: E402
from yggdras.processing.lia.models import AnthropicClient, Budget, BudgetStop  # noqa: E402

# Key terms for the deterministic second grader on the life set: derived from the frozen key
# and written before any run. They are personal, so they live in local-data/ (git-ignored);
# prereg.md records the file's SHA-256, and the harness stops if it changed.
LIFE_TERMS_SHA = "5c3f3b4201ba3169071874dd91689b382b1091773555986b221972ad1d4f945d"


def life_terms() -> dict[int, list[str]]:
    raw = (LOCAL / "life-terms.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != LIFE_TERMS_SHA:
        sys.exit("STOP: the life key terms changed since the prereg")
    return {int(k): v for k, v in json.loads(raw).items()}


# ---------------------------------------------------------------- pinned inputs


def git(*args, repo=BRAIN_REPO) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout  # fmt: skip


def key_text() -> str:
    text = git("show", f"{KEY_COMMIT}:evals/hard-v1.md")
    data = git("show", f"{KEY_COMMIT}:evals/hard-v1.md").encode("utf-8")
    raw = subprocess.run(["git", "-C", str(BRAIN_REPO), "show", f"{KEY_COMMIT}:evals/hard-v1.md"],
                         capture_output=True, check=True).stdout  # fmt: skip
    if hashlib.sha256(raw).hexdigest() != KEY_SHA:
        sys.exit(f"STOP: the answer key's SHA-256 differs from {KEY_SHA}")
    del data
    return text


def verify() -> None:
    key_text()
    head = git("rev-parse", "--short", "HEAD", repo=BRAIN_PIN).strip()
    if head != PIN or git("status", "--porcelain", repo=BRAIN_PIN).strip():
        sys.exit(f"STOP: the brain worktree is not a clean checkout of {PIN} ({head})")
    skills = (BRAIN_REPO / "skills" / "lia" / "answering.md").read_bytes()
    if hashlib.sha256(skills).hexdigest() != SKILLS_SHA:
        sys.exit("STOP: Lia's skills changed since the prereg")


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------- datasets and keys


def apollo(name: str) -> list[dict]:
    path = BRAIN_PIN / "archive" / "demo-evals" / f"{name}.yaml"
    out = []
    for q in yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]:
        out.append({"id": q["id"], "kind": q["kind"], "question": q["question"],
                    "expected": q["expected_answer"], "keys": [str(k).lower() for k in q.get("keys", [])],
                    "gold": q.get("gold_notes") or [], "abstain": q["kind"] == "trap"})  # fmt: skip
    return out


def life() -> list[dict]:
    text, out, current = key_text(), [], None
    for line in text.splitlines():
        m = re.match(r"^(\d+)\. (.*)$", line)
        if m:
            current = {"id": f"q{int(m.group(1)):02d}", "n": int(m.group(1)), "question": m.group(2),
                       "kind": "life", "expected": "", "gold": [], "citations": []}  # fmt: skip
            out.append(current)
            continue
        s = line.strip()
        if current and s.startswith("- Answer: "):
            current["expected"] = s[len("- Answer: "):]
        elif current and s.startswith("- Notes needed: "):
            notes = s[len("- Notes needed: "):]
            current["gold"] = [] if notes == "none" else [x.strip() for x in notes.split(",")]
        elif current and s.startswith("- [["):
            current["citations"].append(s[2:])
    for q in out:
        q["abstain"] = q["expected"].startswith("ABSTAIN")
    terms = life_terms()
    for q in out:
        q["keys"] = terms.get(q["n"], [])
    return out


SETS = {
    "apollo-hard": (lambda: apollo("hard-v8"), BRAIN_PIN / "archive" / "demo-brain", True),
    "apollo-held": (lambda: apollo("held-out-v8"), BRAIN_PIN / "archive" / "demo-brain", True),
    "life": (life, BRAIN_PIN / "library", False),
}


# ---------------------------------------------------------------- arms


def arm_config(arm: str, model: str) -> LiaConfig:
    base = LiaConfig(model=model)
    arms = {
        "default": base,
        "e1-json": replace(base, maps=MapOptions(format="json")),
        "e1-prose": replace(base, maps=MapOptions(format="prose")),
        "e2-shelf-only": replace(base, maps=MapOptions(relationship=False)),
        "e3-l0": replace(base, l0=True),
        "e4-outgoing": replace(base, maps=MapOptions(inverses=False)),
        "e5-10": replace(base, maps=MapOptions(about_words=10)),
        "e5-15": replace(base, maps=MapOptions(about_words=15)),
        "e5-25": replace(base, maps=MapOptions(about_words=25)),
        "e6-cascade": replace(base, model="claude-haiku-5-5",
                              answer_model=model if model != "claude-haiku-5-5" else "claude-sonnet-5-5"),
        "e8-neighbours": replace(base, neighbours=True),
    }  # fmt: skip
    if arm == "final":
        data = json.loads((HERE / "final-config.json").read_text(encoding="utf-8"))
        return LiaConfig(**{**data, "maps": MapOptions(**data["maps"])})
    return arms[arm]


# ---------------------------------------------------------------- budget ledger

LEDGER = LOCAL / "spend.json"
_ledger_lock = threading.Lock()


def load_budget() -> Budget:
    spent = json.loads(LEDGER.read_text())["spent"] if LEDGER.is_file() else 0.0
    return Budget(stop_at=STOP, spent=spent)


def save_budget(budget: Budget) -> None:
    with _ledger_lock:
        LOCAL.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps({"spent": round(budget.spent, 6), "calls": budget.calls}))


# ---------------------------------------------------------------- run


def out_dirs(set_name: str) -> tuple[Path, Path]:
    if set_name == "life":
        return LOCAL / "results", CODE / "local-data" / "traces"
    return HERE / "results", HERE / "traces"


def run(arm: str, set_name: str, runs: int, model: str) -> None:
    verify()
    load, root, flat = SETS[set_name]
    questions = load()
    library = Library(root, flat=flat)
    skills = load_skills(BRAIN_REPO / "skills" / "lia")
    before = tree_hash(BRAIN_PIN)
    budget = load_budget()
    results_dir, traces_dir = out_dirs(set_name)
    results_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)
    for r in range(1, runs + 1):
        out = results_dir / f"{arm}__{set_name}__{model}__r{r}.json"
        if out.is_file():
            print("skip, exists:", out.name)
            continue
        if arm == "variant-c":
            from variant_c import VariantC

            engine = VariantC(root, flat, model, budget)
            ask = engine.ask
            config = {"variant": "C", "model": model}
        else:
            cfg = arm_config(arm, model)
            client = AnthropicClient(cfg.model, cfg.effort, budget)
            answer = AnthropicClient(cfg.answer_model, cfg.effort, budget) if cfg.answer_model else None
            lia = Lia(client, library, skills, cfg, answer_client=answer)
            ask = lia.ask
            config = cfg.as_dict()
        rows, lock = [], threading.Lock()

        def one(q):
            for attempt in range(3):
                try:
                    res = ask(q["question"], f"{set_name}/{q['id']}")
                    break
                except BudgetStop:
                    raise
                except Exception as exc:  # network or API error: retry, then record it
                    if attempt == 2:
                        res = {"id": q["id"], "error": repr(exc)[:300], "cost_usd": 0.0}
                    time.sleep(3 * (attempt + 1))
            res.update({"qid": q["id"], "set": set_name, "run": r, "arm": arm})
            with lock:
                rows.append(res)
            save_budget(budget)
            return res

        try:
            one(questions[0])  # warm the cache first
            with ThreadPoolExecutor(WORKERS) as pool:
                list(pool.map(one, questions[1:]))
        except BudgetStop as stop:
            print("BUDGET STOP:", stop)
            save_budget(budget)
            sys.exit(3)
        rows.sort(key=lambda x: x["qid"])
        payload = {"arm": arm, "set": set_name, "model": model, "run": r, "config": config,
                   "pin": PIN, "spent_after": budget.spent, "rows": rows}  # fmt: skip
        out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
        if set_name == "life":
            for row in rows:
                name = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{arm}__r{r}__{row['qid']}")
                (traces_dir / f"{name}.json").write_text(json.dumps(row, indent=1, ensure_ascii=False),
                                                         encoding="utf-8")  # fmt: skip
        else:
            trace = traces_dir / f"{arm}__{set_name}__{model}__r{r}.jsonl"
            trace.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n",
                             encoding="utf-8")  # fmt: skip
        cost = sum(x.get("cost_usd", 0) for x in rows)
        print(f"{arm} {set_name} {model} r{r}: {len(rows)} q, ${cost:.3f}, total ${budget.spent:.3f}")
    if tree_hash(BRAIN_PIN) != before:
        sys.exit("STOP: the pinned brain changed during the run")


# ---------------------------------------------------------------- grading

RUBRIC = """You grade one answer from a personal knowledge assistant against an answer key.

Grades:
- correct: the key says ABSTAIN is not the case, and the answer states every required element of the key (paraphrase is fine; extra true detail is fine).
- partly_correct: it states some but not all required elements, and nothing contradicting the key.
- wrong: it misses the key's elements, contradicts the key, or answers when the key says ABSTAIN.
- correct_abstain: the key says ABSTAIN, and the answer declines (says the brain does not hold it), optionally with a short reason.
- wrong_abstain: the key gives an answer, but the answer declines entirely.

Judge only against the key. Ignore citation formatting."""


def keyterm_grade(q: dict, row: dict) -> str:
    answer = (row.get("answer") or "").lower()
    declined = row.get("abstain") or answer.lstrip().startswith(("not in your brain", "not in brain"))
    if q["abstain"]:
        return "correct_abstain" if declined else "wrong"
    if declined:
        return "wrong_abstain"
    if not q["keys"]:
        return "unknown"
    hits = sum(1 for k in q["keys"] if k in answer)
    return "correct" if hits == len(q["keys"]) else "partly_correct" if hits else "wrong"


def judge(client, q: dict, row: dict) -> str:
    import anthropic  # noqa: F401

    key = "ABSTAIN" if q["abstain"] else q["expected"]
    schema = {"type": "object", "additionalProperties": False, "required": ["grade"],
              "properties": {"grade": {"type": "string", "enum": ["correct", "partly_correct", "wrong",
                                                                    "correct_abstain", "wrong_abstain"]}}}  # fmt: skip
    msg = f"Question: {q['question']}\n\nKey: {key}\n\nAnswer to grade:\n{row.get('answer', '')}"
    r = client._client.messages.create(model=JUDGE, max_tokens=512, system=RUBRIC,
                                       output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
                                       messages=[{"role": "user", "content": msg}])  # fmt: skip
    from yggdras.processing.lia.models import cost_of

    u = r.usage
    client.budget.add(cost_of(JUDGE, u.input_tokens, u.cache_creation_input_tokens or 0,
                              u.cache_read_input_tokens or 0, u.output_tokens))  # fmt: skip
    return json.loads("".join(b.text for b in r.content if b.type == "text"))["grade"]


def grade() -> None:
    verify()
    budget = load_budget()
    client = AnthropicClient(JUDGE, "low", budget)
    for folder in (HERE / "results", LOCAL / "results"):
        for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            if path.name.endswith(".graded.json"):
                continue
            target = path.with_suffix(".graded.json")
            if target.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            keyed = {q["id"]: q for q in SETS[data["set"]][0]()}

            def one(row):
                q = keyed[row["qid"]]
                row["grade_terms"] = keyterm_grade(q, row) if "error" not in row else "wrong"
                row["grade_judge"] = judge(client, q, row) if "error" not in row else "wrong"
                row["gold"] = q["gold"]
                row["recall"] = (len(set(q["gold"]) & set(row.get("opened", []))) / len(q["gold"])
                                 if q["gold"] else None)  # fmt: skip
                return row

            with ThreadPoolExecutor(WORKERS) as pool:
                data["rows"] = list(pool.map(one, data["rows"]))
            target.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
            save_budget(budget)
            print("graded", target.name, f"total ${budget.spent:.3f}")


# ---------------------------------------------------------------- E7: routing recall at scale


def synth_brain(n: int, folder: Path, seed: int = 7) -> list[dict]:
    """A synthetic library of n notes (people and projects in eight areas) and 30 questions,
    each asking who works on a project given only its codename; gold = person + project."""
    rng = random.Random(seed + n)
    areas = ["01-health", "02-relationships", "03-work-career", "04-learning", "05-money",
             "06-purpose", "07-home-admin", "08-rest-joy"]  # fmt: skip
    syll = ["ka", "lo", "mi", "ra", "ve", "to", "su", "ne", "pa", "di", "go", "ru"]
    word = lambda k: "".join(rng.choice(syll) for _ in range(k))  # noqa: E731
    lib = folder / "library"
    (lib / "00-manual").mkdir(parents=True, exist_ok=True)
    for f in ("taxonomy.md", "node.md"):
        (lib / "00-manual" / f).write_bytes((BRAIN_PIN / "library" / "00-manual" / f).read_bytes())
    pairs, questions = n // 2, []
    for i in range(pairs):
        area = areas[i % len(areas)]
        person, project, code = f"{word(2)}-{word(2)}", f"project-{word(3)}", word(3).capitalize()
        (lib / "11-people").mkdir(exist_ok=True)
        (lib / area).mkdir(exist_ok=True)
        (lib / "11-people" / f"{person}.md").write_text(
            f"---\nid: p{i}\nslug: {person}\nname: \"{person.replace('-', ' ').title()}\"\ntype: person\n"
            f"area: {area}\ndescription: \"A person in {area[3:]}\"\naliases: []\n---\n\n# {person}\n\n"
            f"## Facts\n\n- {person} works on {project}. (src: self, 2030-01-01)\n\n## Links\n\n"
            f"- works_on [[{project}]]\n", encoding="utf-8")  # fmt: skip
        (lib / area / f"{project}.md").write_text(
            f"---\nid: j{i}\nslug: {project}\nname: \"{project.replace('-', ' ').title()}\"\ntype: project\n"
            f"area: {area}\nstatus: active\ndescription: \"A project, codename {code}\"\naliases: [\"{code}\"]\n---\n\n"
            f"# {project}\n\n## Facts\n\n- {project} has the codename {code}. (src: self, 2030-01-01)\n\n"
            "## Links\n\n", encoding="utf-8")  # fmt: skip
        questions.append({"id": f"s{i:04d}", "question": f"Who works on the project codenamed {code}?",
                          "gold": [person, project]})  # fmt: skip
    rng.shuffle(questions)
    return questions[:30]


def e7(model: str) -> None:
    verify()
    budget = load_budget()
    skills = load_skills(BRAIN_REPO / "skills" / "lia")
    out = {}
    for n in (100, 300, 1000):
        folder = LOCAL / "synth" / str(n)
        questions = synth_brain(n, folder)
        library = Library(folder / "library")
        cfg = LiaConfig(model=model)
        lia = Lia(AnthropicClient(model, "low", budget), library, skills, cfg)
        recalls = []
        for r in range(1, 4):
            def route(q):
                state = {"steps": [], "calls": [], "opened": {}, "searches": 0}
                messages = [{"role": "user", "content": [{"type": "text", "text": f"Question: {q['question']}"}]}]
                for _ in range(4):  # route only: stop at the first open_notes
                    reply = lia.client.send(system=lia.system, tools=lia_tools(), messages=messages)
                    lia._assistant(messages, reply)
                    if reply.stop_reason != "tool_use":
                        break
                    results = [{"type": "tool_result", "tool_use_id": c["id"], "content": lia._tool(c, state)}
                               for c in reply.tool_calls]  # fmt: skip
                    messages.append({"role": "user", "content": results})
                    if state["opened"]:
                        break
                save_budget(budget)
                return len(set(q["gold"]) & set(state["opened"])) / 2

            with ThreadPoolExecutor(WORKERS) as pool:
                recalls.append(statistics.mean(pool.map(route, questions)))
        out[n] = {"recall_per_run": recalls, "map_tokens_est": sum(len(t) for t in library.maps().values()) / 2.35}
        print(n, out[n], f"total ${budget.spent:.3f}")
    (HERE / "results" / f"e7__{model}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


def lia_tools():
    from yggdras.processing.lia.lia import TOOLS

    return TOOLS


# ---------------------------------------------------------------- tables


def final_grade(row: dict, overrides: dict) -> str:
    key = f"{row['arm']}|{row['set']}|{row['run']}|{row['qid']}"
    return overrides.get(key, row.get("grade_judge", "wrong"))


def table() -> None:
    overrides = {}
    for f in (HERE / "overrides.json", LOCAL / "overrides.json"):
        if f.is_file():
            overrides.update(json.loads(f.read_text(encoding="utf-8")))
    groups = {}
    for folder in (HERE / "results", LOCAL / "results"):
        for path in sorted(folder.glob("*.graded.json")) if folder.is_dir() else []:
            data = json.loads(path.read_text(encoding="utf-8"))
            groups.setdefault((data["arm"], data["set"], data["model"]), []).append(data)
    print("| arm | set | model | score per run (correct+correct abstain) | partly | citation pass | recall | $ / q | p50 s | p90 s |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for (arm, set_name, model), runs in sorted(groups.items()):
        scores, partly, lat, cost, rec, cit_ok, cit_all = [], [], [], [], [], 0, 0
        for d in sorted(runs, key=lambda d: d["run"]):
            g = [final_grade(r, overrides) for r in d["rows"]]
            scores.append(sum(x in ("correct", "correct_abstain") for x in g))
            partly.append(sum(x == "partly_correct" for x in g))
            for r in d["rows"]:
                lat.append(r.get("latency_ms", 0) / 1000)
                cost.append(r.get("cost_usd", 0))
                if r.get("recall") is not None:
                    rec.append(r["recall"])
                cc = r.get("citation_check")
                if cc:
                    cit_all += cc["total"]
                    cit_ok += cc["total"] - cc["failed"]
        n = len(runs[0]["rows"])
        q = statistics.quantiles(lat, n=10) if len(lat) > 1 else [0] * 9
        print(f"| {arm} | {set_name} | {model.replace('claude-', '')} | {', '.join(map(str, scores))} of {n} | "
              f"{', '.join(map(str, partly))} | {cit_ok}/{cit_all} | {statistics.mean(rec):.2f} | "
              f"{statistics.mean(cost):.4f} | {statistics.median(lat):.1f} | {q[8]:.1f} |")  # fmt: skip


if __name__ == "__main__":
    cmd = sys.argv[1]
    model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "claude-haiku-5-5"
    if cmd == "verify":
        verify()
        print("ok: key", KEY_SHA[:12], "pin", PIN, "skills", SKILLS_SHA[:12])
    elif cmd == "run":
        run(sys.argv[2], sys.argv[3], int(sys.argv[4]), model)
    elif cmd == "grade":
        grade()
    elif cmd == "e7":
        e7(model)
    elif cmd == "table":
        table()
