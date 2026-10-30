# Hard set v8: whole brain vs the pipeline (pre-registration)

Written 2026-10-30, before any run. Prompts, questions, grading and code are frozen from here; any change after results would be logged under Deviations. Local only, no commits, `demo-brain/` and `brain/` untouched.

**Questions.** Both files are in the brain repo, approved by Manoj; v22 is reworded per his note before any run.
- `demo-evals/hard-v8.yaml`: 24 questions, 4 each of bridge, chain, unlinked, trap, reworded and whole picture.
- `demo-evals/held-out-v8.yaml`: 10 questions, mixed types.

**Arms.** Same code paths as `evals/baseline.md`. Model `claude-haiku-5-5`, thinking off, effort low.
- **Whole brain:** every note's fact lines and link lines as `search_result` blocks, with the cache marker on the last block. One cited answer call per question; this is Experiment 2's arm B.
- **Pipeline:** variant C, `retrieve.py`. Pick (cached signpost block), then gather the picked notes and their neighbours, then one cited answer.

**Runs.**
- 3 per arm per file, one question at a time.
- Run order per file: whole-1, pipeline-1, whole-2, pipeline-2, whole-3, pipeline-3. Each arm's first question therefore meets a cold cache unless the prefix is still warm from an earlier call (5-minute TTL).
- **Cold vs warm per question:** a question is cold when its cached call wrote to the cache (`cache_creation_input_tokens > 0`), warm otherwise. Measured from the API's usage figures.

**Grading.**
- **Decline:** a reply starting with "NOT IN BRAIN".
- **Trap:** correct only if it declines.
- **Other questions:** correct when the reply does not decline and contains every key term. Each flagged answer is then read by hand, and paraphrases are credited and noted.
- **v24 and y08** (long lists) are graded correct / partial / wrong:
  - **correct:** every key term (after hand review)
  - **partial:** at least one key but not all
  - **wrong:** none of them, or declined
  - Partials count as not correct in the score and are reported separately.

**Reported per arm and file:**
- score per run
- $ per correct
- billed-equivalent tokens per question, median (highest)
- median seconds end to end
- warm vs cold: the count of each, and median $ and seconds for each
- partials on v24 and y08
- every question that every option misses

**Cap.** $3 total. The runner stops if the spend passes it.

## Deviations

None yet.
