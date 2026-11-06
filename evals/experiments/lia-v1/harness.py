"""Checking Lia (D35): one Apollo check per change, and the gate for life hard-v2.

Usage (from the code repo's app/ folder; ANTHROPIC_API_KEY in the environment or .env;
LIA_BRAIN_REPO = the brain repo, LIA_BRAIN_PIN = a clean checkout of it at PIN):
    uv run python ../evals/experiments/lia-v1/harness.py check
    uv run python ../evals/experiments/lia-v1/harness.py gate

check: Lia's one config, one run on Apollo hard-v8, stopped at $0.50. It is graded by the judge
and the key-term grader, then compared with the stored final-v2 and x-base runs and the last
check. It prints score, traps, citations, unsupported and absence flags, skill picks, cost and
latency.

gate: the v2 gate (prereg.md, "v2 changes") on life hard-v2, Apollo held-out-v8 and Apollo
hard-v8, 3 runs each, Lia against variant C. It stops until life hard-v2 is frozen.

Real-brain results and traces go to local-data/ only; Apollo ones into this folder.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CODE = HERE.parents[2]
BRAIN_REPO = Path(os.environ.get("LIA_BRAIN_REPO", "../yggdras-brain"))
BRAIN_PIN = Path(os.environ.get("LIA_BRAIN_PIN", "../yggdras-brain-pin"))
PIN = "f6fe26a"  # the brain commit the Apollo sets are read from
LOCAL = CODE / "local-data" / "lia-v1"
TODAY = "2026-11-02"  # the upcoming view's "today" in every run
WORKERS = 6
JUDGE = "claude-haiku-5-5"
CHECK_BUDGET = float(os.environ.get("LIA_CHECK_BUDGET", "0.50"))  # a run may set a lower cap
# The v2 gate's life set: Manoj writes and answers it, then it is frozen at a brain commit.
# Fill these in when it is frozen; the gate refuses to run before that.
LIFE_V2 = {"commit": None, "path": "evals/hard-v2.md", "sha256": None}
GATE_BUDGET = 3.0

from yggdras import config  # noqa: E402
from yggdras.data.maps import checks  # noqa: E402
from yggdras.processing.lia.lia import LiaConfig, default_lia  # noqa: E402
from yggdras.processing.lia.library import Library  # noqa: E402
from yggdras.processing.lia.models import AnthropicClient, Budget, BudgetStop, cost_of  # noqa: E402


# ---------------------------------------------------------------- inputs


def git(*args, repo=BRAIN_REPO) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout  # fmt: skip


def check_pin() -> None:
    head = git("rev-parse", "--short", "HEAD", repo=BRAIN_PIN).strip()
    if head != PIN or git("status", "--porcelain", repo=BRAIN_PIN).strip():
        sys.exit(f"STOP: {BRAIN_PIN} is not a clean checkout of {PIN} ({head})")


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + p.read_bytes())
    return h.hexdigest()


def apollo(name: str) -> list[dict]:
    path = BRAIN_PIN / "archive" / "demo-evals" / f"{name}.yaml"
    out = []
    for q in yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]:
        out.append({"id": q["id"], "kind": q["kind"], "question": q["question"],
                    "expected": q["expected_answer"], "keys": [str(k).lower() for k in q.get("keys", [])],
                    "gold": q.get("gold_notes") or [], "abstain": q["kind"] == "trap"})  # fmt: skip
    return out


def life_v2() -> list[dict]:
    """Life hard-v2, read from the brain repo at its frozen commit (the hard-v1 key format)."""
    if not (LIFE_V2["commit"] and LIFE_V2["sha256"]):
        sys.exit("STOP: life hard-v2 isn't frozen yet (LIFE_V2 in harness.py)")
    raw = subprocess.run(["git", "-C", str(BRAIN_REPO), "show", f"{LIFE_V2['commit']}:{LIFE_V2['path']}"],
                         capture_output=True, check=True).stdout  # fmt: skip
    if hashlib.sha256(raw).hexdigest() != LIFE_V2["sha256"]:
        sys.exit("STOP: the life hard-v2 key differs from its frozen SHA-256")
    out, current = [], None
    for line in raw.decode("utf-8").splitlines():
        m = re.match(r"^(\d+)\. (.*)$", line)
        if m:
            current = {"id": f"q{int(m.group(1)):02d}", "question": m.group(2), "kind": "life",
                       "expected": "", "gold": [], "citations": [], "keys": []}  # fmt: skip
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
    return out


SETS = {
    "apollo-hard": (lambda: apollo("hard-v8"), BRAIN_PIN / "archive" / "demo-brain", True),
    "apollo-held": (lambda: apollo("held-out-v8"), BRAIN_PIN / "archive" / "demo-brain", True),
    "life-v2": (life_v2, BRAIN_PIN / "library", False),
}


def labels() -> dict[str, list[str]]:
    """Hand labels of the playbooks that fit each Apollo hard-v8 question (written before the
    first skill-library run)."""
    return json.loads((HERE / "skill-labels.json").read_text(encoding="utf-8"))


def leak_guard() -> None:
    """No skill quotes an eval question: a four-word run with two content words, or a three-word
    "the x y" name, from any question of the Apollo sets is a leak."""
    stop = {"a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "my", "i", "is", "what",
            "which", "do", "did", "with", "at", "by", "from", "how", "when", "where", "who", "it"}  # fmt: skip
    words = lambda s: re.findall(r"[a-z0-9]+", s.lower())  # noqa: E731
    skills = BRAIN_REPO / "skills" / "lia"
    files = [skills / "core.md", *(skills / "library").glob("*.md")]
    text = " " + " ".join(words(" ".join(p.read_text(encoding="utf-8") for p in files))) + " "
    for name in ("apollo-hard", "apollo-held"):
        for q in SETS[name][0]():
            w = words(q["question"])
            runs = [w[i:i + 4] for i in range(len(w) - 3)]
            runs = [r for r in runs if sum(x not in stop for x in r) >= 2]
            runs += [w[i:i + 3] for i in range(len(w) - 2)
                     if w[i] == "the" and all(x not in stop for x in w[i + 1:i + 3])]  # fmt: skip
            for r in runs:
                if f" {' '.join(r)} " in text:
                    sys.exit(f"STOP: a skill quotes eval question {name}/{q['id']}: {' '.join(r)}")


# ---------------------------------------------------------------- running Lia


def out_dirs(set_name: str) -> tuple[Path, Path]:
    if set_name.startswith("life"):
        return LOCAL / "results", CODE / "local-data" / "traces"
    return HERE / "results", HERE / "traces"


def run_set(set_name: str, tag: str, budget: Budget, ask_factory) -> dict:
    """One run of every question in *set_name*; the first question warms the cache."""
    load, root, flat = SETS[set_name]
    questions = load()
    library = Library(root, flat=flat)
    ask = ask_factory(library, root, flat)
    rows, lock = [], threading.Lock()

    def one(q):
        res = None
        for attempt in range(3):  # each API call also retries 3 times with backoff
            try:
                res = ask(q["question"], f"{set_name}/{q['id']}")
                break
            except BudgetStop:
                raise
            except Exception as exc:  # recorded as invalid only after three failures
                if attempt == 2:
                    res = {"id": q["id"], "error": repr(exc)[:300], "cost_usd": 0.0}
                time.sleep(3 * (attempt + 1))
        res.update({"qid": q["id"], "set": set_name, "tag": tag})
        with lock:
            rows.append(res)
        return res

    one(questions[0])
    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, questions[1:]))
    rows.sort(key=lambda x: x["qid"])
    return {"tag": tag, "set": set_name, "pin": PIN, "spent": budget.spent, "rows": rows}


def lia_factory(budget: Budget):
    def factory(library, root, flat):
        lia = default_lia(library, BRAIN_REPO / "skills" / "lia",
                          lambda model: AnthropicClient(model, "low", budget),
                          LiaConfig(today=TODAY))  # fmt: skip
        return lia.ask

    return factory


def save(payload: dict, name: str) -> Path:
    results, traces = out_dirs(payload["set"])
    results.mkdir(parents=True, exist_ok=True)
    traces.mkdir(parents=True, exist_ok=True)
    path = results / f"{name}.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    if payload["set"].startswith("life"):
        for row in payload["rows"]:
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{name}__{row['qid']}")
            (traces / f"{safe}.json").write_text(json.dumps(row, indent=1, ensure_ascii=False), encoding="utf-8")
    else:
        (traces / f"{name}.jsonl").write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in payload["rows"]) + "\n", encoding="utf-8"
        )
    return path


# ---------------------------------------------------------------- grading

RUBRIC = """You grade one answer from a personal knowledge assistant against an answer key.

Grades:
- correct: the key says ABSTAIN is not the case, and the answer states every required element of the key (paraphrase is fine; extra true detail is fine).
- partly_correct: it states some but not all required elements, and nothing contradicting the key.
- wrong: it misses the key's elements, contradicts the key, or answers when the key says ABSTAIN.
- correct_abstain: the key says ABSTAIN, and the answer declines (says the brain does not hold it), optionally with a short reason.
- wrong_abstain: the key gives an answer, but the answer declines entirely.

Judge only against the key. Ignore citation formatting."""
GOOD = ("correct", "correct_abstain")


def keyterm_grade(q: dict, row: dict) -> str:
    answer = (row.get("answer") or "").lower()
    declined = row.get("abstain") or answer.lstrip().startswith(("not in your brain", "i don't have that"))
    if q["abstain"]:
        return "correct_abstain" if declined else "wrong"
    if declined:
        return "wrong_abstain"
    if not q["keys"]:
        return "unknown"
    hits = sum(1 for k in q["keys"] if k in answer)
    return "correct" if hits == len(q["keys"]) else "partly_correct" if hits else "wrong"


def judge(client: AnthropicClient, q: dict, row: dict) -> str:
    key = "ABSTAIN" if q["abstain"] else q["expected"]
    schema = {"type": "object", "additionalProperties": False, "required": ["grade"],
              "properties": {"grade": {"type": "string", "enum": ["correct", "partly_correct", "wrong",
                                                                    "correct_abstain", "wrong_abstain"]}}}  # fmt: skip
    msg = f"Question: {q['question']}\n\nKey: {key}\n\nAnswer to grade:\n{row.get('answer', '')}"
    r = client._client.messages.create(model=JUDGE, max_tokens=512, system=RUBRIC,
                                       output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
                                       messages=[{"role": "user", "content": msg}])  # fmt: skip
    u = r.usage
    client.budget.add(cost_of(JUDGE, u.input_tokens, u.cache_creation_input_tokens or 0,
                              u.cache_read_input_tokens or 0, u.output_tokens))  # fmt: skip
    return json.loads("".join(b.text for b in r.content if b.type == "text"))["grade"]


def grade(payload: dict, budget: Budget) -> dict:
    keyed = {q["id"]: q for q in SETS[payload["set"]][0]()}
    client = AnthropicClient(JUDGE, "low", budget)

    def one(row):
        q = keyed[row["qid"]]
        bad = "error" in row
        row["grade_terms"] = "wrong" if bad else keyterm_grade(q, row)
        row["grade_judge"] = "wrong" if bad else judge(client, q, row)
        return row

    with ThreadPoolExecutor(WORKERS) as pool:
        payload["rows"] = list(pool.map(one, payload["rows"]))
    return payload


def fresh_citations(payload: dict) -> tuple[int, int, int, int]:
    """Every shown citation, re-checked against the pinned notes: (shown, verified, marked
    unverified, invented). Native citations (D35) are footnotes rendered from cited blocks: one
    is verified when it is a footnote of a line of that note. Older runs quoted lines by hand
    and are re-checked word for word with today's checker."""
    _, root, flat = SETS[payload["set"]]
    library = Library(root, flat=flat)
    forms: dict[str, set[str]] = {}
    shown = verified = marked = invented = 0
    for row in payload["rows"]:
        cites = row.get("citations") or []
        if cites and isinstance(cites[0], dict) and "line" in cites[0]:
            for c in cites:
                shown += 1
                slug = c["line"][2 : c["line"].index("]]")]
                if slug not in forms:
                    forms[slug] = {b.footnote(slug) for b in library.blocks(slug)}
                verified += c["line"] in forms[slug]
                invented += c["line"] not in forms[slug]
            continue
        answer = row.get("answer") or ""
        opened = {s: library.note_text(s) for s in row.get("opened", [])}
        for c in checks.check_citations(answer.replace(" [unverified]", ""), opened):
            shown += 1
            if c.ok:
                verified += 1
            elif any(f"{c.quote}{end} [unverified]" in answer for end in ("»", '"', "")):
                marked += 1
            else:
                invented += 1
    return shown, verified, marked, invented


# ---------------------------------------------------------------- check


def summary(payload: dict, overrides: dict | None = None) -> dict:
    keyed = {q["id"]: q for q in SETS[payload["set"]][0]()}
    rows = [r for r in payload["rows"] if "error" not in r]
    overrides = overrides or {}
    judged = [overrides.get(r["qid"], r.get("grade_judge")) for r in rows]
    traps = [r for r in rows if keyed[r["qid"]]["abstain"]]
    lat = sorted(r["latency_ms"] / 1000 for r in rows)
    shown, verified, marked, invented = fresh_citations(payload)
    by_effort: dict[str, list] = {}
    by_model: dict[str, list] = {}
    for r in rows:
        by_effort.setdefault(r.get("effort") or "—", []).append(r)
        by_model.setdefault((r.get("model") or "claude-haiku-5-5").replace("claude-", ""), []).append(r)

    def pct(xs, q):
        v = sorted(x["latency_ms"] / 1000 for x in xs)
        return statistics.median(v) if q == 50 else (statistics.quantiles(v, n=10)[8] if len(v) > 1 else v[0])

    return {
        "calls": statistics.mean(len(r.get("calls", [])) for r in rows),
        "retries": sum(bool((r.get("citation_check") or {}).get("retried")) for r in rows),
        "empty": sum(bool(r.get("empty_reply")) for r in rows),
        "effort": {k: (len(v), pct(v, 50), pct(v, 90), statistics.mean(x["cost_usd"] for x in v))
                   for k, v in sorted(by_effort.items())},
        "model": {k: (len(v), statistics.mean(x["cost_usd"] for x in v)) for k, v in sorted(by_model.items())},
        "questions": len(payload["rows"]),
        "invalid": len(payload["rows"]) - len(rows),
        "judge": sum(g in GOOD for g in judged) if all(judged) else None,
        "terms": sum(keyterm_grade(keyed[r["qid"]], r) in GOOD for r in rows),
        "traps": f"{sum(keyterm_grade(keyed[r['qid']], r) == 'correct_abstain' for r in traps)}/{len(traps)}",
        "citations": f"{verified}/{shown} verified, {marked} marked, {invented} invented",
        "invented": invented,
        "unsupported": sum(len((r.get("checks") or {}).get("unsupported_left", [])) for r in rows),
        "absence": sum(len((r.get("checks") or {}).get("absence_left", [])) for r in rows),
        "cost": statistics.mean(r["cost_usd"] for r in rows),
        "p50": statistics.median(lat),
        "p90": statistics.quantiles(lat, n=10)[8] if len(lat) > 1 else lat[0],
    }


def stored(prefix: str) -> list[tuple[str, dict]]:
    """Stored Apollo hard-v8 runs named <prefix>__apollo-hard__claude-haiku-5-5__r*, with the
    Step 2 hand overrides applied to the judge grades where they exist."""
    overrides_all = json.loads((HERE / "overrides.json").read_text(encoding="utf-8"))
    out = []
    for r in (1, 2, 3):
        base = HERE / "results" / f"{prefix}__apollo-hard__claude-haiku-5-5__r{r}"
        path = next((p for p in (Path(f"{base}.graded.json"), Path(f"{base}.json")) if p.exists()), None)
        if path is None:
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        ov = {k.split("|")[3]: v for k, v in overrides_all.items()
              if k.startswith(f"{prefix}|apollo-hard|{r}|") and k.endswith("claude-haiku-5-5")}  # fmt: skip
        d["set"] = "apollo-hard"
        out.append((f"{prefix} r{r}", summary(d, ov)))
    return out


def check() -> None:
    config.load_env_file()
    check_pin()
    leak_guard()
    before = tree_hash(BRAIN_PIN)
    budget = Budget(stop_at=CHECK_BUDGET)
    stamp = time.strftime("%Y%m%d-%H%M")
    try:
        payload = run_set("apollo-hard", f"check-{stamp}", budget, lia_factory(budget))
        payload = grade(payload, budget)
    except BudgetStop as stop:
        sys.exit(f"BUDGET STOP: {stop}")
    if tree_hash(BRAIN_PIN) != before:
        sys.exit("STOP: the pinned brain changed during the check")
    previous = sorted((HERE / "results").glob("check-*.json"))
    path = save(payload, f"check-{stamp}")
    now = summary(payload)
    rows = [(f"check {stamp}", now)]
    if previous:
        last = json.loads(previous[-1].read_text(encoding="utf-8"))
        rows.append((f"last check {previous[-1].stem[6:]}", summary(last)))
    rows += stored("final-v2") + stored("x-base")
    print(f"\nApollo hard-v8, {now['questions']} questions; saved {path.name}; spent ${budget.spent:.3f}\n")
    print("| run | judge | key terms | traps | citations | unsupported | unverified absence | calls / q | retries | $ / q | p50 / p90 s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, s in rows:
        judged = "—" if s["judge"] is None else s["judge"]
        print(f"| {name} | {judged} | {s['terms']} | {s['traps']} | {s['citations']} | {s['unsupported']} | "
              f"{s['absence']} | {s['calls']:.1f} | {s['retries']} | {s['cost']:.4f} | {s['p50']:.1f} / {s['p90']:.1f} |")  # fmt: skip
    print("\n| this check, by effort | questions | p50 s | p90 s | $ / q |\n|---|---|---|---|---|")
    for level, (n, p50, p90, cost) in now["effort"].items():
        print(f"| {level} | {n} | {p50:.1f} | {p90:.1f} | {cost:.4f} |")
    print("\n| this check, by model | questions | $ / q |\n|---|---|---|")
    for model, (n, cost) in now["model"].items():
        print(f"| {model} | {n} | {cost:.4f} |")
    lab = labels()
    print("\n| q | effort | model | skills loaded | labelled | right | verdict; checklist | judge |")
    print("|---|---|---|---|---|---|---|---|")
    right = 0
    for r in payload["rows"]:
        if "error" in r:
            print(f"| {r['qid']} | invalid: {r['error'][:60]} |")
            continue
        got, ok = r.get("skills_loaded", []), lab.get(f"apollo-hard/{r['qid']}", [])
        good = bool(got) and set(got) <= set(ok)
        right += good
        print(f"| {r['qid']} | {r['effort']} | {r['model'].replace('claude-', '')} | {', '.join(got) or '—'} | "
              f"{', '.join(ok)} | {'yes' if good else 'no'} | {r.get('verdict')}; {r.get('checklist')} | {r['grade_judge']} |")  # fmt: skip
    print(f"\nskill picks right: {right}/{len(payload['rows'])}; empty replies: {now['empty']}")
    ok_traps, all_traps = now["traps"].split("/")
    simple = now["effort"].get("simple", (0, 0.0, 0.0, 0.0))
    complex_ = now["effort"].get("complex", (0, 0.0, 0.0, 0.0))
    score = now["judge"] if now["judge"] is not None else now["terms"]
    bars = [
        ("traps 4/4", ok_traps == all_traps),
        ("0 invented citations", now["invented"] == 0),
        ("judge score >= 22", score >= 22),
        ("simple p50 <= 10 s", simple[1] <= 10),
        ("simple <= $0.01 / q", simple[3] <= 0.01),
        ("complex <= $0.05 / q", complex_[3] <= 0.05),
    ]
    print("\n| bar | pass |\n|---|---|")
    for name, ok in bars:
        print(f"| {name} | {'yes' if ok else '**no**'} |")
    if not all(ok for _, ok in bars):
        print("\nFAIL: not fit to be the default.")
        sys.exit(1)
    print("\nPASS")


# ---------------------------------------------------------------- gate


def gate() -> None:
    """The v2 gate: Lia vs variant C, 3 runs each, on life hard-v2, Apollo held-out-v8 and
    hard-v8, against the five bars in prereg.md. Stops until life hard-v2 is frozen."""
    config.load_env_file()
    check_pin()
    SETS["life-v2"][0]()  # stops here until life hard-v2 is frozen
    from variant_c import VariantC

    before = tree_hash(BRAIN_PIN)
    budget = Budget(stop_at=GATE_BUDGET)
    factories = {"lia": lia_factory(budget),
                 "variant-c": lambda library, root, flat: VariantC(root, flat, "claude-haiku-5-5", budget).ask}  # fmt: skip
    results = {}
    try:
        for set_name in ("life-v2", "apollo-held", "apollo-hard"):
            for arm, factory in factories.items():
                for r in (1, 2, 3):
                    payload = grade(run_set(set_name, f"gate-{arm}-r{r}", budget, factory), budget)
                    save(payload, f"gate__{arm}__{set_name}__r{r}")
                    results.setdefault((set_name, arm), []).append(payload)
    except BudgetStop as stop:
        sys.exit(f"BUDGET STOP: {stop}")
    if tree_hash(BRAIN_PIN) != before:
        sys.exit("STOP: the pinned brain changed during the gate")
    print("| set | arm | judge score per run | traps | invented citations | p50 s | $ / q |")
    print("|---|---|---|---|---|---|---|")
    for (set_name, arm), payloads in sorted(results.items()):
        s = [summary(p) for p in payloads]
        print(f"| {set_name} | {arm} | {', '.join(str(x['judge']) for x in s)} | {', '.join(x['traps'] for x in s)} | "
              f"{sum(x['invented'] for x in s)} | {statistics.mean(x['p50'] for x in s):.1f} | "
              f"{statistics.mean(x['cost'] for x in s):.4f} |")  # fmt: skip
    print("\nApply the five bars in prereg.md (hand review of disagreements first).")


if __name__ == "__main__":
    commands = {"check": check, "gate": gate}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        sys.exit(f"usage: harness.py {' | '.join(commands)}")
    commands[sys.argv[1]]()
