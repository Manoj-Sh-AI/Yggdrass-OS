# Evals

The eval set: 20 to 30 questions with known answers, spread across direct lookup, multi-hop, page-precise, negative and temporal cases. Run it after every change to the node format, the gateway skill or any agent. A failing eval blocks the next phase.

The questions and answers are about the private brain, so `questions.yaml` lives in the brain repo (D30). This folder documents the question format and holds `fixture-brain/`: a synthetic brain with invented people, organisation and dates, used to test the format, the runner and the validator without touching real data. The runner lives in `app/` and reads a brain path at runtime. Nothing here is personal data (D4).

## Files

| Path | What |
|---|---|
| `fixture-brain/` | Synthetic brain: 10 nodes and `index.md` |
| `fixture-questions.yaml` | Its eval set (20 questions). Kept outside the brain folder so an agent answering questions cannot read the answers |
| `fixture-results/` | Dated result files written by the runner, one per recorded run |

## Question format

```yaml
questions:
  - id: d01                 # unique
    kind: direct            # direct | multi-hop | page-precise | negative | temporal
    exit: true              # one of the ten exit questions
    question: When is the project review deadline?
    expected_answer: 2030-06-30.
    required_facts: [Review deadline is 2030-06-30]   # every one must appear; empty for negatives
    expected_nodes: [index.md, areas/project.md]      # files every valid route must open
```

A set needs 20–30 questions, at least 5 negative, 3 multi-hop, 2 page-precise and 2 temporal, and exactly 10 exit questions. `expected_nodes` lists only the files *every* valid route must open: a question with two sound routes lists what they share, or a correct answer by the other route fails for the wrong reason.

## Running

From the repo root:

```bash
uv run --project app python -m yggdras.tooling.eval_runner check evals/fixture-questions.yaml
uv run --project app python -m yggdras.tooling.eval_runner show evals/fixture-questions.yaml --prompt-only
uv run --project app python -m yggdras.tooling.eval_runner record evals/fixture-questions.yaml --out evals/fixture-results --brain evals/fixture-brain
```

Ask each question in a fresh session that has only `skills/gateway/SKILL.md` and the brain path. `record` prompts for each verdict and the files opened (or reads them with `--verdicts FILE`), then writes a dated result file. The runner never grades.
