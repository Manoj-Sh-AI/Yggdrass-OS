# Scoping: Phase 1b — Graphify map and link discovery

Answer in your own words. Go deep where a wrong guess is expensive (stored data, several reasonable designs, edge cases). Stay shallow on anything cheap to change later.

**This file is public.** Keep answers generic; anything personal goes in `yggdras-brain/private/`.

Source: `planning/locked-plan-v1.md`, "Revision 2026-10-25" and "Phase 1b", and register rows D5–D9.

## Already decided by the plan

| Choice | Decision | Where |
|---|---|---|
| Graph layer | Graphify code inside the Yggdras repo; no database | D5 |
| Storage | Derived `graph.json` plus a report in the gitignored `.graphify/` folder of the brain repo, rebuilt from the markdown at any time | D5, D6 |
| Direction | One-way, files to map; the map can always be dropped and rebuilt | D6 |
| Structural pass | Built from written `[[links]]` and frontmatter: no model, free, identical every run, rerun on every file change | D7, D8 |
| Discovery pass | A paid model proposes new links tagged inferred with a one-line reason; run manually; proposals accepted or rejected through the connector, and accepted ones become real links in the markdown | D7, D8 |
| Corpus | The Apollo demo brain (`yggdras-brain/demo-brain/`) | Revision 2026-10-25 |
| Exit test | A structural rebuild reproduces the map exactly; discovery recovers deleted links clearly above its own run-to-run noise; the eval scores no worse with the map than without it | Phase 1b |

## Open questions (in order)

1. **Verify Graphify first (step one of Phase 1b).** Before any design work, confirm against the actual project and its source:
   - that its open-source core is Apache 2.0, and what the licence-notice obligations are (keeping the notice, marking changed files);
   - how its structural and discovery passes actually work, and whether they match what the plan assumes;
   - what it exports (the format of `graph.json` and the report), and whether that fits a derived, rebuildable map.

   Anything that doesn't match the plan's assumptions is a finding to bring back, not a detail to work around.

### Findings for question 1 (read-only, 2026-10-25; nothing installed or vendored)

Canonical project: [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) (`safishamsi/graphify` redirects there). Latest release v0.9.95 (2026-10-23). Very active, so any version used must be pinned. The PyPI package is `graphifyy` (double y).

**1. Licence: the core is Apache 2.0, and there is a separate hosted/enterprise product.**
- **Core:** GitHub reports Apache-2.0 for the repo. [LICENSE](https://github.com/Graphify-Labs/graphify/blob/HEAD/LICENSE) is the Apache 2.0 text. [NOTICE](https://github.com/Graphify-Labs/graphify/blob/HEAD/NOTICE) reads "Copyright 2026 Safi Shamsi and the Graphify contributors" and says portions contributed under MIT before the relicensing remain under those terms, with the text kept in [LICENSE-MIT](https://github.com/Graphify-Labs/graphify/blob/HEAD/LICENSE-MIT).
- **Obligations if a public repo vendors part of it** (Apache 2.0 section 4; not legal advice):
  - ship a copy of the Apache licence;
  - keep the copyright, patent, trademark and attribution notices from the vendored files;
  - include the attribution notices from Graphify's `NOTICE` in a `NOTICE` file shipped with Yggdras;
  - mark every changed file with a prominent notice saying it was changed;
  - also keep `LICENSE-MIT`, because the NOTICE says earlier portions remain MIT.
- **No enterprise code in the repository.** A search of the file tree found no enterprise or commercial directory, and the README names no license other than Apache 2.0.
- **Enterprise is a separate product**, per [graphify.com/llms-full.txt](https://graphify.com/llms-full.txt):
  - Enterprise is self-hosted, early access, per seat, with custom pricing: legacy migration, SAML SSO, self-hosting, a GitHub App verification gate, Jira links.
  - A hosted app at app.graphify.com has Free, Pro and Teams plans.
  - The "free for open source" programme is for the hosted product, for non-commercial MIT/Apache projects. Yggdras has no licence, so it wouldn't qualify, but none of that is needed if only the CLI core is used.
  - The vendor doc is inconsistent on whether `verify-edit` ships in the open-source package, so treat it as not available.

**2. The two passes: no, not as the plan assumes.** This changes D7 and D8.
- **The free, model-free pass is built for code.** Graphify's README says code is "parsed with tree-sitter AST: deterministic, no LLM", while "docs, PDFs, images" go to a model ([README](https://github.com/Graphify-Labs/graphify/blob/HEAD/README.md), Privacy section; [how-it-works](https://github.com/Graphify-Labs/graphify/blob/HEAD/docs/how-it-works.md), "The three passes").
- **Markdown counts as a document, so it gets the paid pass.** `.md` is classed as `DOCUMENT`, not code ([detect.py](https://github.com/Graphify-Labs/graphify/blob/HEAD/graphify/detect.py), `DOC_EXTENSIONS`). Pass 3, the model, "runs in parallel over markdown". In the incremental update, any changed doc file switches on semantic extraction ([update reference](https://github.com/Graphify-Labs/graphify/blob/HEAD/graphify/skills/codex/references/update.md)).
- **The model-free modes skip markdown.** `graphify update` re-extracts "code files" only, and `--code-only` skips doc files, markdown included.
- **A deterministic markdown extractor does exist in the source, but can't be run on its own.** [extractors/markdown.py](https://github.com/Graphify-Labs/graphify/blob/HEAD/graphify/extractors/markdown.py) is registered for `.md` in the AST extractor map. It parses YAML frontmatter, headings and `[[wikilinks]]`, resolving them by filename across the folder. It emits `file --references--> file` and `heading --contains--> heading` edges tagged `EXTRACTED`. But no documented CLI mode runs it without the model. Using it model-free would mean calling it directly as a library, which means vendoring or wrapping, and that's unverified.
- **Plain answer:** the "free structural pass over the markdown on every file change" is not something Graphify provides out of the box. Every documented path that reads our notes also calls a model. D7 and D8 as written assume otherwise.

**3. Outputs and update mode.**
- **Writes** `graphify-out/` next to the input (or `<DIR>/graphify-out/` with `--out DIR`): `graph.json` (NetworkX node-link format, with `schema_version` and `graphify_version`), `graph.html` and `GRAPH_REPORT.md`, plus `cache/`.
- **Update mode is incremental:** an SHA256 content cache in `graphify-out/cache/` plus a manifest, so unchanged files are skipped. `--force` does a full re-scan. `graphify watch` and git hooks can trigger rebuilds. But a changed `.md` file still triggers the model pass, so "run it on every file change" means a paid call per changed note.
- **Edges are tagged** `EXTRACTED`, `INFERRED` or `AMBIGUOUS`, which maps well onto the plan's "proposals tagged inferred".

**4. Exports.**
- **Confirmed as `/graphify` skill flags:** `--graphml`, `--svg` and `--neo4j` (Cypher file; `--neo4j-push` pushes), plus `--falkordb`, `--wiki` and `--mcp` ([exports reference](https://github.com/Graphify-Labs/graphify/blob/HEAD/graphify/skills/claude/references/exports.md)).
- **`--obsidian` is not a skill flag.** Obsidian export exists as the CLI subcommand `graphify export obsidian` (notes plus canvas). The other exports also exist as `graphify export html|svg|graphml|neo4j|falkordb|wiki`.
- **The HTML view is not fully self-contained.** The graph data is inlined, but the vis-network library loads from unpkg ([exporters/html.py](https://github.com/Graphify-Labs/graphify/blob/HEAD/graphify/exporters/html.py), with a subresource-integrity hash). It needs internet access to render.

**5. Other findings that contradict or affect the revised Phase 1b**
- **Link reasons are lost.** Every `[[wikilink]]` becomes a bare `references` edge, so the reason text on each link (the plan's "labelled relationship") doesn't survive. Our `aliases` aren't used either, since resolution is by filename only.
- **The output folder doesn't match.** The plan says `.graphify/`, but Graphify writes `graphify-out/`. Configurable through `--out`, but it needs a decision and a `.gitignore` entry.
- **Privacy: query logging is on by default.** Every query, path and explain call logs the question text to `~/.cache/graphify-queries.log`. That's brain content leaving the brain repo. Set `GRAPHIFY_QUERY_LOG_DISABLE=1`. One secondary source claimed logging is off by default since v0.9.28; the current README says otherwise.
- **Privacy: model choice is automatic.** Without `--backend`, Graphify picks the first key it finds (Gemini, then Kimi, then Claude…). Kimi routes to servers in China. Pin `--backend claude`, or `GRAPHIFY_BACKEND`, explicitly.

2. **How to get a model-free map, given finding 2. Ruled (Manoj, 2026-10-25): our own structural pass, with Graphify installed whole.**
   - **Our structural pass.** It reads every markdown file in the brain, takes the frontmatter and every hand-written `[[link]]`, and writes `graph.json`: no model, free, identical every run, re-run on every file change. It keeps what Graphify drops: each link's reason text and the frontmatter aliases (D31). It's ours, in the repo, not a fork of Graphify.
   - **Graphify installed whole.** Nothing is stripped, forked, patched or narrowed. The code pass, document extraction, the HTML view and report, every export, update mode and git hooks, question answering and MCP mode all stay reachable. Only discovery is used now.
   - **Two privacy settings, configuration only:** the provider is pinned to Anthropic and never auto-detected (no Kimi, no China routing), and question logging to the home folder is off. Nothing else is disabled.
   - **Outputs stay separate.** Our `graph.json` is the map and the source for the graph view. Graphify's output under `.graphify/` is a proposal feed only. Proposals are tagged inferred, carry a reason, and go through accept or reject in the connector; nothing reaches the brain unreviewed.
   - **Exact version pinned** (v0.9.95 or newer at adoption); upgrades are deliberate.
   - **Register:** D5, D7 and D8 amended, and D32 added (Graphify adopted whole, future uses anticipated, so the unused parts must not be cleaned up).
   - **Folder (Manoj, 2026-10-25):** our structural output lives in `.map/` in the brain repo, beside `.graphify/`. Both are gitignored (D6).
   - **Next step, held until Manoj has seen the amended register:** build the structural pass, run it over the Apollo demo brain, and compare its edges against the hand-written links.

## Link-recovery experiment (2026-10-25)

Full method and data: `evals/experiments/link-recovery/README.md`, pre-registered and committed before any run. 20 of the Apollo brain's 81 linked pairs were deleted from a copy (fixed seed, stratified, both leaves included), and Graphify discovery was run twice on the identical copy.

| | Run 1 | Run 2 |
|---|---|---|
| **Recovered (of 20)** | **9** | **7** (6 in both runs; 4 flip between runs; 10 never) |
| Plausible (never in the brain) | 0 | 1: `john-young` cites `apollo-13-measles-article`, a real source link |
| Wrong | 0 | 0 |
| Pairs proposed (overlap between runs) | 68 | 69 (65 shared, overlap 0.90) |
| Raw output | 43 nodes, 71 edges | 72 nodes, 91 edges |
| Time / cost | 182 s / ~$0.30 | 265 s / ~$0.35 |

- **Reasons:** none. Proposals carry only generic labels (`references`, `conceptually_related_to`, `cites`) and a confidence tag, with no per-link reason for review.
- **What "discovery" did:** it recovered connections already stated in fact lines, and re-found 59–61 of the 61 links still written. It proposed almost nothing new: 0 and 1 new pairs.
- **Misses:** 10 of the 20 deleted pairs were never recovered, including one stated plainly in the text (`apollo-13`–`ken-mattingly`) and the one hub–hub pair.

The register and plan are unchanged, pending Manoj's ruling on the kill criterion.

### Follow-up: three arms on the same copy (2026-10-25)

Pre-registered and committed before any arm ran. Same copy, answer key and 20 pairs; each arm ran twice. Details: `evals/experiments/link-recovery/README.md`.

| Arm | Recovered of 20 (run 1 / 2) | Noise (pair overlap, flips) | Plausible / wrong per run | Reasons | Cost per run | Time per run |
|---|---|---|---|---|---|---|
| Original Graphify | 9 / 7 | 0.90, 4 flips | 0/0, 1/0 | No | ~$0.30–0.35 | 182–265 s |
| **A, free baseline** (name scan of fact lines, no model) | **11 / 11** | **1.00, 0 flips** | **28 / 6** | **Yes** | **$0** | **~1 s** |
| B, Graphify + roster, forced one batch | 9 / 6 | 0.93, 3 flips | 2/0, 0/0 | No | ~$0.28–0.29 | 183–229 s |
| C, cross-batch pass alone | 5 / 5 | 0.90, 0 flips | 13/0, 15/0 | Yes | ~$0.08–0.09 | 22–25 s |
| Original run 2 + C | 12 / 12 | 0.98, 0 flips | 14/0, 16/0 | C's only | ~$0.44 | ~290 s |

- **Issues at the pinned 0.9.95:**
  - #65 still applies; it was closed with guidance only, and there is still no cross-batch pass.
  - #3947 and #4547 are open.
  - #3094 is fixed.
- **Arm B was reachable without editing Graphify:** a roster file in a copy of the corpus, plus Graphify's public `GRAPHIFY_MAX_OUTPUT_TOKENS` setting so the batch never split. There is no prompt or instruction option.
- **Straight call: A matches or beats both B and C.**
  - A beats B outright, and beats C alone (11 vs 5).
  - Graphify plus C edges A by one pair (12 vs 11), at about $0.44 and 290 s a run against zero.
  - A is identical run to run and gives every proposal its sentence.
  - A's 6 wrong proposals are all spurious name matches ("Cape Kennedy", and "Apollo 11's" read as "Apollo"), each obvious from its reason line.
- **Coverage:** across all arms, 15 of 20 pairs were recovered at least once. Model arms alone found 4, A alone found 2, and 5 were found by nothing. For those 5, neither note's fact text names the other.

Register and plan unchanged. Ruling is Manoj's.

## Apollo 25-question eval: with and without the map (2026-10-25)

**Setup.**
- **Same for both conditions:** 25 questions (`demo-evals/questions.yaml`) over `demo-brain/`, phase 1a method: one fresh agent per question that follows `skills/gateway/SKILL.md` and reads one file at a time.
- **Model pinned:** `claude-opus-5-5`, confirmed in every transcript.
- **Without the map:** the phase 1a prompt, unchanged.
- **With the map:** the same prompt, plus permission to read `.map/graph.json` (checked current against `demo-brain`) to find the starting note and follow links, with `index.md` optional.
- **One run per condition.** Batching was matched (20 agents at once, then 5), because time depends on how many run together.
- **How each column was measured:**
  - Tokens are all tokens processed, including cache reads.
  - Cost uses Opus 5.5 rates of $4/MTok input, $20/MTok output and $0.20/MTok cache reads, and assumes $5/MTok for cache writes.
  - Time is first to last transcript entry.
  - "Notes read" excludes the skill file, `index.md` and the map.

| Q | Correct (no map / map) | Notes read | Tokens (k) | Time (s) | Cost ($) |
|---|---|---|---|---|---|
| d01 | ✓ / ✓ | 1 / 1 | 159 / 203 | 46 / 43 | 0.24 / 0.24 |
| d02 | ✓ / ✓ | 1 / 2 ⚑ | 159 / 352 | 47 / 62 | 0.24 / 0.31 |
| d03 | ✓ / ✓ | 1 / 1 | 159 / 281 | 49 / 55 | 0.24 / 0.29 |
| d04 | ✓ / ✓ | 1 / 1 | 159 / 203 | 51 / 47 | 0.24 / 0.24 |
| d05 | ✓ / ✓ | 1 / 1 | 159 / 281 | 47 / 52 | 0.24 / 0.29 |
| d06 | ✓ / ✓ | 1 / 1 | 159 / 281 | 49 / 54 | 0.25 / 0.29 |
| d07 | ✓ / ✓ | 1 / 1 | 159 / 165 | 51 / 42 | 0.24 / 0.23 |
| d08 | ✓ / ✓ | 4 / 4 | 249 / 355 | 59 / 69 | 0.28 / 0.33 |
| d09 | ✓ / ✓ | 1 / 1 | 159 / 203 | 48 / 47 | 0.25 / 0.24 |
| m01 | ✓ / ✓ | 3 / 4 ⚑ | 247 / 365 | 56 / 64 | 0.27 / 0.29 |
| m02 | ✓ / ✓ | 2 / 3 ⚑ | 160 / 335 | 48 / 63 | 0.25 / 0.28 |
| m03 | ✓ / ✓ | 3 / 2 | 203 / 272 | 54 / 59 | 0.27 / 0.27 |
| m04 | ✓ / ✓ | 3 / 3 | 160 / 282 | 48 / 55 | 0.25 / 0.30 |
| m05 | ✓ / ✓ | 1 / 1 | 159 / 204 | 47 / 41 | 0.25 / 0.24 |
| p01 | ✓ / ✓ | 1 / 1 | 159 / 204 | 47 / 40 | 0.25 / 0.24 |
| p02 | ✓ / ✓ | 1 / 1 | 159 / 204 | 46 / 45 | 0.25 / 0.24 |
| p03 | ✓ / ✓ | 1 / 1 | 159 / 204 | 47 / 40 | 0.25 / 0.24 |
| t01 | ✓ / ✓ | 1 / 1 | 159 / 204 | 51 / 40 | 0.25 / 0.24 |
| t02 | ✓ / ✓ | 1 / 1 | 159 / 203 | 46 / 42 | 0.24 / 0.24 |
| t03 | ✓ / ✓ | 1 / 1 | 159 / 203 | 46 / 44 | 0.24 / 0.24 |
| n01 | ✓ / ✓ | 1 / 2 ⚑ | 159 / 282 | 22 / 28 | 0.13 / 0.30 |
| n02 | ✓ / ✓ | 0 / 0 | 116 / 171 | 18 / 20 | 0.11 / 0.27 |
| n03 | ✓ / ✓ | 2 / 5 ⚑ | 202 / 269 | 24 / 28 | 0.14 / 0.27 |
| n04 | ✓ / ✓ | 2 / 2 | 202 / 269 | 25 / 25 | 0.14 / 0.26 |
| n05 | ✓ / ✓ | 3 / 3 | 247 / 388 | 31 / 27 | 0.16 / 0.33 |
| **Total** | **25 / 25 both** | **38 / 44** | **4,328 / 6,382 (+47%)** | **1,101 / 1,133 (+3%)** | **5.68 / 6.71 (+18%)** |

- **Answers:** no question got a different answer between the two conditions. Both flagged d08 as an agent's inference, and both said "I don't have that" on all five negatives.
- **⚑ The map run read notes the question didn't need:**
  - d02: `oxygen-tank-2`.
  - m01: `rubella-crew-swap`.
  - m02: `beech-aircraft`.
  - n01: `nasa`.
  - n03: `command-service-module`, plus re-reading `apollo-11` and `command-service-module`.
- **The one saving:** on m03 the map run skipped `oxygen-tank-2`, which the run without the map had read for background.
- **Why the map costs more:**
  - `graph.json` is 55 KB, about seven times `index.md`, and has no descriptions.
  - It was read 35 times in 25 runs; 10 runs had to read it in two parts.
  - Following links led to extra neighbours rather than fewer reads.
- **Cost caveat:**
  - Billed cost depends on what was already cached. The 5 negatives without the map ran on a warm cache, which made them about half price.
  - Priced as if nothing were cached, the totals are $17.52 without the map and $25.77 with it (+47%), the same ratio as tokens.

Register and plan unchanged.

## Known gaps

- **Alias resolution has no real-corpus coverage yet (2026-10-25).** Structural-pass criterion 4 is covered by unit tests only (`[[Mattingly]]` resolving to `ken-mattingly`). All 143 Apollo links resolved by slug, because none in that corpus are written as an alias. The Apollo brain is deliberately **not** edited to add alias links, since that would write the test's answer into the corpus. Real coverage comes when Manoj's own brain is in, since he writes links by alias.

<!-- Further open questions are added as they come up. -->

## 1. What kind of software is this?

<!-- Manoj. -->

## 2. Which tasks does it take on?

**In (breadth):**

<!-- Manoj. -->

**Out (for now):**

<!-- Manoj. -->

## 3. What is the expected result? (acceptance criteria)

<!-- Manoj. Context: the exit test in "Already decided" above. -->

## 4. Which processes run inside it?

<!-- Manoj. -->

## 5. How is each carried out, step by step?

<!-- Manoj. -->

## 6. When do exceptions apply, and what happens then?

<!-- Manoj. -->

---
Ready to build? Only if 3 and 6 are answered and open question 1 is resolved.
