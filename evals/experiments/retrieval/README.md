# Retrieval follow-up — Apollo demo, 25 October 2026

Neither alternative beat the plain-index baseline at equal answer quality in this run. Wiki-first kept answer content correct but added cost and reads; query-first lost four answerable questions. Query-first's small token saving came with lower accuracy and higher observed cost and time.

**Protocol caveat:** this is not a clean replication of strict one-file-at-a-time execution. Some agents requested two Read calls in a single message despite the unchanged instruction. These are retained and flagged, not silently rerun. Content correctness is separate from grounding and instruction compliance. No condition is being declared to have passed the full project release gate.

## Measured comparison

All scores below were reviewed against the existing answer key. Rates are the same recorded Opus 5.5 rates used previously: $4/M input, $20/M output, $0.20/M cache reads, $5/M cache writes. Cost is answering agents only in the first table.

| Condition | Correct content | Required-source check | Brain notes read | Tool calls | Tokens processed | Sum of question times | Observed cost | No-cache cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| R1: Plain index | 25/25 | 25/25 | 37 | 87 | 1,680,280 | 239.9 s | $1.339 | $6.904 |
| R2: Wiki first | 25/25 | 24/25 | 45 | 135 | 2,422,720 | 376.6 s | $1.870 | $9.993 |
| R3: Query, budget 2000 | 21/25 | 21/25 | 38 | 88 | 1,658,662 | 367.1 s | $1.495 | $6.873 |

Notes exclude the skill, brain index, graph, and wiki. Wiki-first additionally read 49 wiki files, including index reads. Tool calls count all actual Read/Bash requests. Tokens include all cache reads; usage comes from finalized child transcripts, deduplicated by message ID. Streaming event usage is provisional and was not used for the totals.

| Alternative versus R1 | Tokens | Observed answering cost | No-cache answering cost | Sum of question times |
|---|---:|---:|---:|---:|
| R2 | +44.2% | +39.6% | +44.8% | +57.0% |
| R3 | -1.3% | +11.7% | -0.4% | +53.0% |

### Changed answers and grounding

- R3 d02: could not verify Beech Aircraft as the tank builder. The query chose an `import` context and omitted the builder note, even though an opened note's link named it. The agent correctly refused to treat that link as a fact.
- R3 d09: could not answer the Apollo 1 fire question because it received only Apollo 11 alarm/report nodes for Launch Complex 34 and 1967-01-27. It opened no unrelated notes.
- R3 m04: could not identify Wernher von Braun or Marshall Space Flight Center because neither supporting note was returned.
- R3 m05: returned `No matching nodes found` (exit 4) for the capsule-communicator question, so it could not establish Charlie Duke/Apollo 16. This is a retrieval outcome, not an infrastructure failure to retry.
- R2 m01: Jim Lovell was the correct answer, but the agent explicitly relied on a link and index description and did not open his fact note. Thus 25/25 content does **not** mean 25/25 grounded retrieval.
- R2 m03: the core answer was supported; an extra explanation about thermostatic switches came from frontmatter description rather than fact lines.
- All three flagged d08 as an agent's inference, and all three refused all five negative questions. Other required answers retained their meaning; wording and extra context varied.

Full answers and expected facts: [answers.md](answers.md). Exact per-question metrics and audits: [comparison.json](comparison.json).

## Step 0: installed code

The installed pin is **graphifyy 0.9.95**. Its source already contains budgeted BFS and the requested retrieval paths, so the premise that these necessarily require a later version does not hold for this installation. No upgrade was needed or attempted; no newer pin or migration cost is proposed.

| Capability | Installed result |
|---|---|
| Budgeted BFS | Present in `serve.py`: `_bfs`, `_subgraph_to_text`, `_query_graph_text` |
| `query --budget`, `query --dfs`, `path`, `explain` | CLI branches present |
| Wiki | `graphify export wiki`; `--wiki` is a Graphify skill flag rather than a standalone CLI switch |
| Serve / MCP | `python -m graphify.serve <graph>` and `graphify-mcp`; `--mcp` is a skill flag. No literal `graphify serve` CLI branch |
| MCP tools | `query_graph`, `get_node`, `get_neighbors`, `shortest_path` present |
| Report-first text | Main navigation guidance is query-first. A leftover Kilo plugin reminder still says to read the report before searching (`install.py:1562`); not every installer surface is fixed |

Source locations, hashes, and relevant installer lines are saved in [input-audit.json](input-audit.json). Graphify was not edited.

## Reused graph and wiki sizes

The already rebuilt graph matches all 43 current markdown files against its manifest: no additions, changes, or missing files. It has 78 nodes and 112 edges. It was reused without another paid rebuild or wiki regeneration. The existing build log estimates its earlier extraction at $0.4000; that is not a new charge from this resumption.

| Artifact | Bytes |
|---|---:|
| Brain index | 8,352 |
| Wiki index | 1,689 |
| Entire wiki, 21 files | 18,950 |
| Graphify graph.json | 57,861 |
| Yggdras structural graph.json | 55,823 |

The wiki index is small, but it often requires an article and then a fallback to the brain index; a smaller first file did not produce a cheaper complete route.

## Budget behavior, without workarounds

All 25 unchanged questions were probed at budget 2000; five were also probed at 500. None of the 2000-budget probes truncated node lines. Instead, **16/25 exceeded the requested budget**: once all nodes fit, this installation retains every edge as well. Four of the five 500-budget probes cut nodes, with an explicit warning.

| Example | Result | Evidence |
|---|---|---|
| d01, 2000 | 41 nodes; 8,530 output characters including header/warning. Body reports about 2,665 tokens and retains all nodes/edges | [raw output](query-probes/d01-2000.txt) |
| d02, 2000 | Five seed nodes under an `import` heuristic; no builder note | [raw output](query-probes/d02-2000.txt) |
| d09, 2000 | Apollo 11 alarms/report subgraph for an Apollo 1 question | [raw output](query-probes/d09-2000.txt) |
| m04, 2000 | Returned paths omit the needed Saturn V/developer notes | [raw output](query-probes/m04-2000.txt) |
| m05, 2000 | No matching nodes | [raw output](query-probes/m05-2000.txt) |
| d01, 500 | 15/41 nodes shown, 26 cut; unrelated Apollo 1/13 and crew-swap seeds consume space | [raw output](query-probes/d01-500.txt) |
| p01, 500 | 13/51 nodes shown, 38 cut; the required report-chunk seed is retained, alongside Apollo 13/board and other seeds | [raw output](query-probes/p01-500.txt) |

The reported 2k truncation was not reproduced on these inputs. Oversized responses, code-oriented context selection, irrelevant seeds, and missing required notes were observed. No seeds, filters, larger budgets, revised questions, extra queries, or fallback reads were used to rescue R3. The 500-budget runs are navigation probes only, not additional scored answering-agent conditions.

## Comparability, timing, and costs

The original desktop runner was not authenticated in this process. A bundled Claude Code 2.1.308 runner was located and used with the project's configured Anthropic key. Its starting context differs from the old desktop session, so R1 was rerun rather than mixing old absolute token/cost figures into this comparison. Every scored question used a fresh Explore child, verified as `claude-opus-5-5`, with the same gateway skill. R1 and R2 launch prompts match the recovered originals exactly; the final five R2 prompts substitute only their question into the recovered template. R3 uses one unchanged-question query followed only by note paths it returns.

Each condition uses the same first 20 questions, followed by the same five negatives. A process barrier enforces that batch two starts after batch one finishes. The dispatcher streams child launches: the measured first-batch peak was six active children for each condition, not 20 simultaneously. Final-batch peaks were 3/4/5. Thus batching matches, but latency still includes different launch overlap and cannot be read as a tightly controlled algorithm benchmark. Per-batch spans and peaks are in the summaries.

The one-file-at-a-time instruction was not perfectly obeyed: R1 m03, R2 m03, and R3 m01/n04 requested pairs of Read calls in the same model message. R3 m01 did so twice. These observations are saved in the audit and weaken strict protocol claims; the alternatives still did not achieve a better equal-quality result.

| Condition | End-to-end wall time, including dispatch | Answering + dispatch cost | No-cache answering + dispatch cost |
|---|---:|---:|---:|
| R1 | 114.3 s | $1.743 | $7.675 |
| R2 | 149.8 s | $2.426 | $10.925 |
| R3 | 160.1 s | $2.127 | $7.886 |

The three completed comparison conditions cost $6.296 including dispatch, of which $4.705 was answering agents. These are observed API/list-rate costs, not an account-invoice reconciliation. Cache-neutral cost reprices every processed input token, including cache reads/writes, at $4/M.

Excluded setup attempts are preserved: a tiny model check, Read/query tool checks, a 20-native-process batch with ten startup exits, a minimal-mode dispatcher with no Agent tool, and a dispatcher-only run that overlapped the second batch by a few seconds. No failed/overlapped attempt was spliced into the scored comparison. Their reported costs total about $2.636; some timed-out connection checks returned no usage, so their billing is unknown. The retained comparison uses one measured run per condition; there are no repeated-run confidence estimates.

## Files and state

- [Final condition data](matched-subagents-3/) contains exact jobs, dispatcher traces, finalized per-question child transcripts, usage, answers, and batch summaries.
- [Recovered old baseline](baseline-recovered.json) preserves the original 25 no-map and 25 whole-map transcripts' aggregates for reference; it is not the control for this new runner.
- [Recovered original prompts](prompts-recovered.json) preserve the R1 prompts and the failed R2 launch prompts/template.
- [Query probes](query-probes.json) retain measured sizes, paths, truncation, timings, and links to raw outputs.
- Brain facts, gateway skill, installed Graphify, decision register, plan, and existing scoping edit were not changed. No commits, PRs, merges, upgrades, or new graph builds were made.
