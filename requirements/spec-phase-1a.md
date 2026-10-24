# Spec: Phase 1a — brain files, links, gateway skill

Status: approved (rulings 2026-10-24)
Scoping: [`scoping-phase-1a.md`](scoping-phase-1a.md)
Plan: `planning/locked-plan-v1.md`, "Phase 1a" and "Build order for phase 1a"
Format: [`rationale/decisions/D02-node-identity.md`](../rationale/decisions/D02-node-identity.md), [`templates/node.md`](../templates/node.md)

## Summary

Build the brain by hand: about 50 markdown nodes in the private brain repo, an `index.md` over them, and a gateway skill that tells an agent how to navigate them. Then prove retrieval works with an eval set of 20–30 questions, graded by Manoj, and freeze the format. Nothing automated writes to the brain in this phase. Every later phase is built on this format, so its weaknesses must surface now, while changing it is cheap.

## Inputs and outputs

| Input | Source | Format |
|---|---|---|
| Facts about seed domains | Manoj: written by hand for nodes 1–10, dictated to the agent from node 11 | Fact lines per D02 |
| Node format | `D02-node-identity.md`, `templates/node.md` | Markdown + YAML frontmatter |
| Eval questions | Manoj, written after the nodes exist | `yggdras-brain/evals/questions.yaml` (D30) |

| Output | Destination | Format |
|---|---|---|
| Nodes | `yggdras-brain/{people,areas,topics,sources}/` | One `.md` per subject |
| Index | `yggdras-brain/index.md` | One line per node: slug, aliases, uuid, type, description |
| Gateway skill | `skills/gateway/` (public, no personal data, D23) | Markdown instructions |
| Eval runner | `app/`, tests in `app/tests/` | Python script |
| Node validator | `app/`, as `validation/`, tests in `app/tests/` | Python package, built after the first 10 nodes |
| Eval result file | `yggdras-brain/evals/results/` | Dated file, per-question pass/fail and files opened |
| Freeze date | Decision register | Register amendment |

## Behavior

1. Accept D02 and the template (build order step 2).
2. Write 10 nodes by hand across the two seed domains, at least 3–4 from the second domain, covering all five node types. Add each to `index.md` in the same sitting (step 3–4). Check criteria 1–9 on these by hand.
3. Build the node validator (`validation/` in `app/`) from what the first 10 nodes taught, with tests. From here on it checks criteria 1–9.
4. Write the gateway skill. Try it on a fresh agent with three questions (step 5). This is exploratory: record what went wrong and fix the skill or format. It is not a pass/fail gate.
5. Grow to about 50 nodes, adding aliases on every name variant seen (step 6). From node 11 on, the agent drafts nodes from what Manoj tells it, and Manoj checks each one before it is committed. Manoj stays the source of every `[stated]` fact. Writing by hand first exists to debug the format, not as a rule to keep for its own sake.
6. Write the eval set to the composition rules (step 7).
7. Run the eval with the runner. Fix the format, the index or the gateway skill until every question passes in one recorded run (step 8).
8. Freeze the format and the eval set; record the date in the register (step 9).

## Acceptance criteria

**Nodes and index**

1. Given any node, when its frontmatter is read, then `id`, `slug`, `name`, `type`, `description`, `created` and `updated` are present and non-empty, `type` is one of the D29 values, and `id` is a UUID v4 that is not the template placeholder `00000000-0000-4000-8000-000000000000`. The validator rejects that string by name.
2. Given any two nodes, when their `slug` and `id` are compared, then neither is shared; and when their aliases are normalized (lowercase, spaces and underscores to hyphens, punctuation dropped), no normalized alias appears on two nodes.
3. Given any node, when its filename is read, then it equals `<slug>.md`, and the node sits in the folder matching its type.
4. Given any fact line, when it is parsed, then it carries exactly one of `[stated]`, `[observed]`, `[derived]` and a `(src: <source>, <YYYY-MM-DD>)` suffix. The source is always the final parenthetical group; earlier brackets belong to the fact. `src: unknown` does not occur.
5. Given a fact that changed value, when its line is read, then it shows the new value, the old value and the change date.
6. Given any link line, when it is parsed, then it has relation text and one `[[slug]]`.
6a. Given any node body, when it is read, then it has a `## Facts` section followed by a `## Links` section, and `## Facts` holds at least one fact line. A node with no facts is invalid.
7. Given `index.md` and the node folders, when compared, then every node has exactly one index entry, every entry points at an existing node, and each entry lists the same aliases as its node.
7a. Given a link `[[x]]` where `x` equals the normalized form of one of a node's aliases, when it is resolved through `index.md`, then it reaches that node. Given a name typed as written (for example `Bank Work`), when it is normalized, then it matches the same node.
8. Given a chunk node, when its frontmatter is read, then `pages` is present.
9. Given any node, when its lines are counted, then it is at most about 50 lines, or it has been split.

**Gateway skill**

10. Given the gateway skill, when it is tried on a fresh agent with three questions (step 5), then the findings are recorded and acted on. Exploratory, not pass/fail; the eval set is the gate.

**Validator**

10a. Given the node validator and a brain path, when it runs, then it reports every violation of criteria 1–9, and its tests cover a valid node, a missing field, an empty facts section, a bad fact line, a fact that itself ends in brackets, the template placeholder `id`, a duplicate slug, two aliases on different nodes that collide only after normalization, and an index mismatch.

**Eval set**

11. Given `questions.yaml`, when it is counted, then it holds 20–30 questions, including at least 5 negative, 3 multi-hop, 2 page-precise and 2 temporal. The 10 exit questions are a subset of the set.
12. Given each question, when it is read, then it records the expected answer, the required facts and the expected node list.
13. Given the runner and a question file, when it runs, then it prints each question with its expected answer, required facts and expected nodes, records Manoj's verdict and the files opened, and writes a dated result file. It does not grade.
14. Given a non-negative question, when it passes, then all required facts are present, no facts are invented, and the expected nodes were opened.
15. Given a negative question, when it passes, then the answer is an explicit "I don't have that", and no node was used as the basis for an answer.

**Gate**

16. Given one recorded run, when the result file is read, then every question passed, and the validator reports no violations of criteria 1–9. Only then is the format frozen and the date recorded.

## Edge cases

| Case | Expected behavior |
|---|---|
| Node over the size limit | Warned, not blocked; split into two linked nodes before the gate |
| Same subject under two names | Resolution chain (slug, alias, fuzzy match with a human choice); never a silent merge. Merge forward: older `id` survives, facts move across, newer slug becomes an alias listed in `index.md`, so existing links still resolve |
| Link to a missing node | Allowed; listed as dangling and reviewed in batches |
| Fact with no external source | Author and date are the source, tagged `[stated]` |
| Superseded fact | Rewritten in place with old value and change date |
| Question the brain can't answer | Explicit "I don't have that" |
| Eval failure | Fix format, index or gateway skill, never the question. A malformed question is fixed before the freeze; after it, questions don't change |
| Empty node (frontmatter, no facts) | Invalid. A dangling link stays dangling until there is a fact to write |

## Tradeoffs (name them)

- **Reliability over speed.** Hand-written nodes and hand grading are slow, but they surface format weaknesses an automated pipeline would hide.
- **Consistency over simplicity.** Strict fact and link syntax costs effort while writing, and pays off for every machine reader in later phases.
- **Privacy over CI coverage.** The real eval set lives in the private brain repo (D30), so CI can't run it.

## Out of scope

Graphiti, Docker and the graph database (1b). The connector, its tools and its validation (2). Any automated node writing: ingest, extraction, the filter (3–4). Agents, the orchestrator, the app, notifications and the graph view.

## Resolved questions (rulings 2026-10-24)

1. **Automated checks.** Criteria 1–9 are checked by hand for the first 10 nodes, then by a validator built as `validation/` in `app/` (criterion 10a). This satisfies constitution #9 once the format has been tried by hand.
2. **Runner location.** `app/`, with tests in `app/tests/`. The plan's layout line is corrected.
3. **Template location.** Only `templates/node.md` in the public repo.
4. **Empty nodes.** Invalid (criterion 6a).
5. **Body headings.** `## Facts` and `## Links` are required, in that order (criterion 6a).
6. **Self-source label.** `src: self`.
7. **Tombstones.** Removed from the plan entirely. Resolution is slug or alias → index → uuid → path, and `index.md` carries each node's aliases, so the alias does the tombstone's job (criterion 7a).
8. **Gateway test.** Exploratory, not pass/fail (criterion 10).
