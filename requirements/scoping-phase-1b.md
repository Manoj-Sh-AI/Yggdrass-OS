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
