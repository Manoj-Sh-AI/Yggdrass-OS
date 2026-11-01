# Speed test: one-call retrieval over the Apollo demo brain

How fast and cheap can a question be answered from the brain without an agent? Each question takes two Haiku 5.5 calls (thinking off) and one model-free step in between:

1. **Pick:** the model picks 1–2 nodes from a cached list of every node (slug, name, aliases, description), as JSON.
2. **Gather (no model):** the picked nodes' fact lines and links, plus the fact lines of every neighbour, from the structural map.
3. **Answer:** one call answers from those lines only, or declines.

The default is `retrieve.py`, variant C below. It sends each gathered node as a `search_result` block with citations on, and strips the `(src: ...)` tail of fact lines from the answer shown to the user. The tail stays in the cited source. `variant_a.py` is kept for reference only.

## Final comparison (v6, 2026-10-26)

35 questions: the 25 in `demo-evals/questions.yaml` and 10 held out in `demo-evals/held-out-v6.yaml` (brain repo), written before any v6 run. Questions run one at a time. Cost uses $0.10/MTok input, $0.50/MTok output, cache writes at 1.25× and reads at 0.1×. Billed tokens count cache reads at 0.1×. A negative is correct only when the reply declines.

| Variant | Answer step | Accuracy (old 25 / new 10) | Cost per correct answer | Billed tokens in, median / highest | End to end, median / slowest |
|---|---|---|---|---|---|
| A | Structured JSON (text, status), pick cached | 24 / 10 (1 run) | **$0.00045** | 2,841 / 5,888 | 4.05 s / 9.65 s |
| B | A with caching off | 25 / 9 (1 run) | $0.00077 | 6,043 / 9,078 | 3.43 s / 6.73 s |
| C | `search_result` blocks, citations on, pick cached | 25 / 10 in each of 3 runs | $0.00062 | 3,893 / 8,330 | 3.18 s / 8.74 s |
| C, `retrieve.py` check run | as C, refactored code | 23 / 10 (1 run) | $0.00067 | 3,778 / 8,330 | 3.15 s / 5.15 s |

- **A is the cheapest per correct answer; C is the most accurate and cites its sources.** C is the default because citations make each answer checkable against the notes.
- **C's citations cover 53–56% of answer sentences.** The uncited ones are mostly a one-line headline answer before a cited sentence that says the same thing.
- **C still misses sometimes.** The check run after refactoring scored 33 / 35:
  - m02 dropped the 28-volt switch rating.
  - p01 opened with "NOT IN BRAIN" and then gave the right figures.
- **There is no extra hop.** A `NEED: <slug>` step was tried in v2–v5 and never fired. The gather already sends the lines of every neighbour named in the links it sends, so no slug can qualify. It is removed.
- **Grading is by hand.** A key-term check runs first, then every flagged answer is read. Answers that paraphrase a key fact ("13 April 1970") are credited; each such call is noted in the result file.

## Files

| Path | What |
|---|---|
| `retrieve.py` | Default retrieval (variant C). `ask` answers one question; `eval` runs question files |
| `variant_a.py` | Variant A for reference (`--no-cache` gives B) |
| `test_retrieve.py` | Model-free tests on the fixture brain |
| `results/v6-*.json` | The v6 runs behind the table (graded) |
| `results/retrieve-check.json` | `retrieve.py` check run (graded) |

## Running

From the repo root, with `ANTHROPIC_API_KEY` set:

```bash
uv run --project app pytest evals/experiments/speed-test-one-query/test_retrieve.py
uv run --project app --with anthropic python evals/experiments/speed-test-one-query/retrieve.py ask <path to yggdras-brain/demo-brain> "Who replaced Ken Mattingly on Apollo 13, and why?"
```
