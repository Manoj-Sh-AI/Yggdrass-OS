# Scoping: Phase 1a — brain files, links, gateway skill

Answer in your own words. Go deep where a wrong guess is expensive (stored data, several reasonable designs, edge cases). Stay shallow on anything cheap to change later.

**This file is public.** Answer in generic terms ("seed domain A", "a person node"). Anything naming a real domain, person or deadline goes in `yggdras-brain/private/scoping-phase-1a-notes.md`.

Source: `planning/locked-plan-v1.md`, sections "Phase 1a", "Node schema", "Merge, dedup and the eval set", "Build order for phase 1a".

## Decided before scoping

| Choice | Decision | Where |
|---|---|---|
| Node types | `person`, `area`, `topic`, `source`, `chunk` | D29 |
| Seed domains | Two domains for the first 10 nodes, named in the brain repo's private notes | 2026-10-24 |
| Eval set location | `questions.yaml` lives in the brain repo. Public `evals/` holds only the runner and format, and reads the brain path at runtime | D30 |
| Public vs private | This file stays generic; specifics go in the brain repo | 2026-10-24 |

## 1. What kind of software is this?

Phase 1a is not really software. It is a content and format exercise: a set of
markdown files, an index over them, and one instruction file that tells an agent
how to navigate them. There is no runtime, no service, no database and no
dependency to install.

The only executable artifact is the eval runner in the public `evals/` folder,
which is a thin script that reads a question file and a brain path. It is
tooling for this phase, not part of the system being built.

## 2. Which tasks does it take on?

**In (breadth):**

- Write the node schema down as a template and an ADR before any node exists.
- Hand-build 10 nodes across two seed domains, covering all five node types.
- Maintain `index.md` by hand: one line per node, written as a search snippet.
- Write the gateway skill and test it against an agent with no other context.
- Expand to roughly 50 nodes, adding aliases on every name variant encountered.
- Write 20–30 eval questions with known answers, at least five of them negative.
- Run the eval, fix the format, the index or the gateway skill, and repeat until every question passes.
- Freeze the node format and record the freeze date in the decision register.

**Out (for now):**

- Graphiti, the graph database and Docker (all phase 1b).
- The connector, its tool surface and its validation rules (phase 2).
- Any automated writing of nodes: ingest, extraction, the conversation filter.
- Agents, the orchestrator, the app, the calendar, notifications, the graph view.

## 3. What is the expected result? (acceptance criteria)

**How an answer is judged correct.** Each question in `questions.yaml` records
three things: the expected answer in prose, the specific facts the answer must
contain, and the nodes that must be opened to reach it. A pass requires all
three — the required facts present, no facts invented, and the right nodes
actually opened. An answer that happens to be right while opening the wrong
files is a fail, because it means retrieval is not working and the next phase
would be built on luck.

**Negative questions** test refusal, not retrieval. Their expected node list is
`index.md` plus whatever was reasonably searched; the search path is not
specified. A negative passes when the response is an explicit "I don't have
that" and no node was used as the basis for an answer. Opening an unrelated
node and answering from it is a fail.

**Who judges.** Manoj, by hand, for all of phase 1a. Automated grading is
deferred until the connector exists, because a grader written now would be
tuned against a format that is still changing.

**The runner shows and records; it does not grade.** For each question it
prints the question, the expected answer, the required facts and the expected
node list. Manoj runs the question in a fresh session, then records what
happened. The runner writes a dated result file with per-question pass/fail and
the files actually opened. That file is the proof the gate was met, and the
baseline to compare against after the next format change. Anything cleverer is
phase 2 work.

**Composition of the set.** 20–30 questions, containing at least five negative,
three multi-hop, two page-precise (correct page range from a source chunk) and
two temporal (current value and what it superseded). The ten exit questions
are a subset of this set, not a separate gate. No question should need more
than about five files opened.

Phase 1a is done when all of the following hold:

- Every question in the set passes, as defined above, in one recorded run.
- Every node satisfies the schema: all required frontmatter fields present,
  every fact line tagged and sourced, under the size limit.
- `index.md` has exactly one entry per node, with no orphans in either direction.
- The format is frozen and the date recorded.

## 4. Which processes run inside it?

1. Create a node.
2. Update a node, including superseding an existing fact.
3. Keep `index.md` current.
4. Resolve an entity before creating anything (dedup).
5. Navigate the brain via the gateway skill.
6. Run the eval set and act on failures.
7. Freeze the format.

## 5. How is each carried out, step by step?

**Create a node.** Run resolution first (process 4). Generate a UUID, pick a
slug, fill all required frontmatter. Write facts one per line, each tagged and
sourced. Add links with a reason attached. Add an index entry in the same
sitting — an index updated later is an index that drifts.

**Update a node.** Add new facts as new lines. Supersede rather than overwrite
(see 6). Touch `updated`. If the node passes the size limit, split it.

**Keep the index current.** Every create or rename updates `index.md`
immediately. Descriptions are rewritten whenever a node's subject shifts, since
a stale description causes the wrong file to be opened.

**Resolve an entity.** Exact slug, then alias, then fuzzy name match. A fuzzy
match returns candidates to choose from and never merges on its own.

**Navigate.** Read `index.md`, pick the category, then the subject, then the
chunk, then plain text search inside that file for the exact passage.

**Run the eval.** The runner prints each question with its expected answer,
required facts and expected nodes. Ask the question in a fresh session where the
agent starts from the index and the gateway skill and opens only the files it
chooses. Record pass or fail and the files opened; the runner writes the dated
result file.

**Freeze the format.** When every question passes, record the freeze date in the
register. The eval set freezes with the format. Changes to the format after that
point are register amendments, not edits; questions do not change.

## 6. When do exceptions apply, and what happens then?

| Case | Rule |
|---|---|
| Node over the size limit | Warn, never block. Split into two nodes and link them — a node that long is doing two jobs. |
| Same subject under two names | Resolution chain, and never a silent merge. Merging forward: the older `id` survives, facts move across, the newer slug becomes an alias, a tombstone keeps old links resolving. |
| Link to a node that doesn't exist | Not an error. Recorded as dangling and reviewed in batches — it is a signal that something is worth creating. |
| Fact with no external source | Every fact has a source. Where no external source exists, the author and the date written are the source, and the fact is `[stated]`. No `src: unknown`. A fact with no traceable origin that the author won't stand behind stays out of the brain. |
| Fact superseded by a newer one | Rewrite in place keeping the history: the new value, the old value, and the date it changed. Never a silent replacement. |
| Question the brain can't answer | The correct behaviour is to say so. An invented answer is a phase 1a failure, not a minor flaw. |
| Eval failure | Fix the format, the index or the gateway skill. Never tune the question to the system. A truly malformed question is a bug in the eval set, fixed before the set freezes with the format. After the freeze, questions do not change. |
Ready to build? Only if 3 and 6 are answered.
