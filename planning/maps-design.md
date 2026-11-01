# Maps design

> Status: **plan for approval, nothing built.** Drafted by Claude on 2026-11-01. Inputs:
> - the research report "Lia's two maps: research and template" (Manoj, 2026-11-01; called "the report" below);
> - `planning/maps-proposal.md` (draft PR #25);
> - `planning/lia-and-connector.md` (PR #28);
> - the brain's `taxonomy.md`, `node.md` and current `generated/` maps.
>
> **Provisional decisions (Manoj, 2026-11-01):** maps route and notes answer; three files; hub links out and chunk chains compressed; L0 and neighbour stubs behind switches, default off; the report's draft pass bars. Every change below that touches those decisions is marked **Changed** or **Decide**.

## 1. Review of the report

### 1.1 Measured on the real brain

The three files were generated from the real brain (80 notes, brain commit 9cb3bcb) exactly as the report's section 5 describes, in a scratch folder. Nothing was committed and the brain was not changed. Tokens were counted with Anthropic's `count_tokens` endpoint; Opus 5.5, Sonnet 5.5 and Haiku 5.5 gave identical counts.

| File | Tokens (real) | Report's estimate |
|---|---|---|
| `atlas.md` | 559 | — |
| `shelf-map.md` | 7,620 | ~3,000 |
| `relationship-map.md` (typed links only, as specified) | 1,674 | ~2–3,000 |
| **All three** | **9,857** | **~5–6,000** |
| Variant: descriptions cut to 15 words | 9,038 (shelf map 6,801) | — |
| Variant: plain `[[mentions]]` kept in the relationship map | 11,320 (relationship map 3,137) | — |
| For comparison: today's `relationship-map.md` | 9,653 | — |
| For comparison: `taxonomy.md` + `node.md` (breakpoint 1) | 3,033 + 5,666 | — |

What the measurements show:
- **The shelf map costs about 95 tokens a row, not 30–40.** Titles, aliases (up to six per note) and descriptions averaging 19 words drive it. Cutting descriptions to 15 words saves only about 10%.
- **The maps cost about 120 tokens per note in total,** so the report's 25k-token trigger is reached at roughly 200 notes, not about 300.
- **Still cheap:** 9.9k cached tokens cost about $0.002 per question on Opus 5.5 (cache read at 0.05×). A rewrite after a commit (a 1-hour write at 2×) costs about $0.08.

### 1.2 Claims checked against their sources

| Claim (report section) | Verdict | Note |
|---|---|---|
| Claude Code loads the first 200 lines / 25 KB of `MEMORY.md` (2.1) | **Correct** | [Claude Code memory docs](https://code.claude.com/docs/en/memory) |
| RAG-MCP: 13.6% vs 43.1%, about half the tokens; reliable below ~30 options, failing past ~100 (2.1) | **Correct, slightly rounded** | Table 1: 13.62% vs 43.13%. Prompt tokens 2,134 → 1,084, a 49% cut (the paper says "over 50%"). The 30/100 thresholds are read off a heat map, not measured numbers ([paper](https://arxiv.org/html/2505.03275v1)) |
| Talk like a Graph: encoding changes accuracy 5% to over 60%; incident encoding best on most tasks (2.2) | **Correct** | [Google blog](https://research.google/blog/talk-like-a-graph-encoding-graphs-for-large-language-models/) |
| Triples beat prose: 73% vs 55% for ChatGPT on DocRED 1-hop (2.2) | **Correct, but off-target** | 73.38 vs 55.25 ([paper](https://arxiv.org/html/2402.11541v4)). It is evidence about *fact* formats, and the maps hold no facts. It supports our fact lines in notes, not the map format |
| TOON 63.1%, CSV 62.2%, JSON 60.3% on uniform tables, within error (2.2) | **Correct** | Flat track, ±4.5 points. Also: CSV is about 6% *smaller* than TOON on flat data, and pipe rows are CSV-like ([benchmarks](https://toonformat.dev/guide/benchmarks)) |
| Meaningful names instead of UUIDs improve retrieval precision (2.3) | **Correct** | Anthropic, "Writing effective tools for agents" |
| "Every row starts with the note's slug (its filename, which is also its name)" (2.3) | **Wrong in detail** | Slug and name differ in our format (`masters-thesis` vs "Master's thesis"). The shelf map carries both, which is right |
| Lost-in-the-middle strongest up to ~50% of the window; recency holds (2.4) | **Correct** | [paper](https://arxiv.org/html/2508.07479v1) |
| LongMemEval: ChatGPT ~92% → ~58%; time-aware filtering +7–11%; structured reading up to +10 points (2.5) | **Plausible, not fully verified** | The abstract confirms a ~30% drop for commercial assistants. The PDF couldn't be read, so the exact figures are unchecked ([abstract](https://arxiv.org/abs/2410.10813)) |
| Zep +18.5% accuracy, 90% lower latency (2.5) | **Correct as quoted** | The vendor's own numbers, as the report says |
| A-MEM ~14× fewer tokens than MemGPT, temporal F1 more than doubled, weaker single-hop (2.5) | **Correct** | 1,216 vs 16,987 tokens; temporal F1 39.4 vs 17.3; single-hop 48.4 vs 60.2 |
| GraphRAG wins 72% on comprehensiveness "while using 97% fewer tokens" (2.6) | **Overstated** | Two different comparisons joined into one: the 72% is root-level summaries vs vector RAG; the 97% is root-level summaries vs source-text summarisation ([paper](https://arxiv.org/html/2404.16130v2)) |
| HippoRAG 2: structured methods worse than plain retrieval on simple facts (2.6) | **Correct** | — |
| Caching: up to 4 breakpoints; 1-hour writes 2×, 5-minute writes 1.25×; reads 0.05× on Opus 5.5 and Sonnet 5.5; minimum 512 tokens; same latency for both TTLs; hits don't count against rate limits (2.8) | **Correct** | [Prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). This corrects PR #28's cost table, which used 0.1× for Sonnet 5.5 (cache reads are $0.10/MTok, not $0.20) |
| FrugalGPT up to 98% cheaper at GPT-4 quality; Aider's repo map uses PageRank with a ~1k-token default budget (2.8) | **Correct** | — |

### 1.3 Problems in the template itself

1. **The header breaks determinism and caching.**
   - `generated 2026-11-01T20:00` changes on every rebuild. So unchanged notes would give different bytes (failing the determinism rule from `maps-proposal.md`), and the 1-hour cache would be rewritten for nothing.
   - `commit 4ac425e` can't name the commit the maps are saved in, because the maps are written before that commit exists.
   - **Changed:** the header carries only counts and `map_version`, a hash of the inputs.
2. **The description rules don't match today's notes.**
   - `node.md` says a description should cover "what it can answer", and for a concept, framework or decision should be "written as a full claim". The report wants at most 15 words and no facts or figures.
   - On the real brain: 55 of 80 descriptions are over 15 words; 42 of 80 contain digits (dates, sizes, amounts); and the 23 sensitive notes' descriptions name exactly what is sensitive.
   - Adopting the rules means rewriting most descriptions (a brain change through the approval path) and amending `node.md` (D31). See section 3.
3. **Chunk descriptions can't follow both rules.** `node.md` asks for "Chapter 3 (pp. 41–58) of <Book>: …", and the report forbids figures. **Changed:** page labels move out of the description into a `P:` flag, taken from the existing `pages` field.
4. **Plain `[[mentions]]` are dropped.** Section 5.3 keeps typed links only, which loses 52 of the 97 non-hub links: which people, places and projects a note mentions. **Decide:** keep them (+1.5k tokens). The proposal is to keep them, accuracy first, and let E2 test dropping them.
5. **`also` is missing.** A note filed under 04 with `also: [03-work-career]` doesn't appear under 03, so routing by area misses it. **Changed:** an `A:03` flag (from `maps-proposal.md`).
6. **The "review due" flag can't say "due"** without today's date, which would break determinism. **Changed:** the flag is "R:<date> = review date". Overdue is judged only in `lint.md`, as `maps-proposal.md` already ruled.
7. **The pipe format needs a guard.** A `|` inside a title, alias or description breaks the row. The checker forbids `|` and line breaks in those fields; the generator never escapes.
8. **The example relationship lines use verbs outside the fixed list** (`built_with`, `supervised_by`). The generator emits only the 22 verbs and their inverses, plus `mentions` / `mentioned_in` if kept.
9. **The atlas mostly repeats `taxonomy.md`,** which is already cached at breakpoint 1. It is small (559 tokens) and adds hub slugs and counts, so keeping it costs little. Merging it into the shelf map's area headings would save a file. Not proposed, since Manoj chose three files; just noted.
10. **L0's exact alias match will fire on generic aliases.** Real aliases include everyday words ("work", "visa", "thesis", "health"). E3 must test L0 with a minimum-specificity rule: no single common word, and at least two words or one rare token.
11. **No free code can judge whether a sensitive note's description "reveals" too much.** The checker can enforce the shape (short, no digits). Whether the wording is safe has to be a human review list.

## 2. One design: the report plus `maps-proposal.md`

| Part | From the report | From `maps-proposal.md` | Decision |
|---|---|---|---|
| Always-loaded files | atlas, shelf map, relationship map | shelf map, atlas, alias index | **Three files** (Manoj) |
| Alias index | — | A separate file | **Not a file.** Aliases are in the shelf rows; code builds an in-memory alias table for L0 and the duplicate checker |
| `active.md`, `timeline.md` | L7, later | Proposed now | **Later.** Built only when an experiment shows the "what's due / what happened when" questions need them |
| `lint.md` | — | Problems, overdue reviews with `--today` | **Kept, never loaded into Lia's prompt.** It is for Manoj and the checker, and it also holds the sensitive-description review list |
| Shelf columns | slug, type, title, about, aliases, status, updated, flags | adds `also`, `review`, fact count | Report columns; `also` and `review` become flags; fact count dropped (tokens, little routing value) |
| Atlas scope | From `taxonomy.md` | From hub descriptions | **`taxonomy.md`** (one source, already human-maintained) |
| Determinism | Not stated | Byte-identical for unchanged notes; overdue only in lint | **Adopted** (section 3.4) |
| Size limits | ~300 notes / 25k tokens | ~25 KB or 300 notes per folder | **Measured tokens decide** (section 6): warn at 20k, split at 25k |

## 3. Final template

### 3.1 General rules

- **Generated by code only;** never edited by hand or by Lia. Rebuilt on every commit and every Undo (D8 as amended in PR #28).
- **Header:** one line with the file name, counts and `map_version`. No timestamp and no commit id.
- **Deterministic:** rows sorted by area code then slug; UTF-8; LF line endings; a fixed column order.
- **Format:** pipe rows, the header row once; no JSON, no prose.
- **No facts:** a description says what the note is about, never a figure or date the note holds.
- **Sensitive notes** appear like any other, flagged `S`.

### 3.2 `00-manual/generated/atlas.md`

```text
# atlas | areas 8 | notes 80 | map_version 3f9a1c27b0d4
code|area|hub|notes|belongs here|not here|key aliases
04|learning|hub-learning|28|The thesis, German, courses, skills, side projects|Ideas themselves (10); job applications (03)|learning, studies
registries|ideas 10 (9) · people 11 (3) · places 12 (8) · sources 13 (15) · journal 15 (0) · cross-area 4
```

`belongs here` and `not here` are copied from `taxonomy.md`'s area table. `key aliases` are the hub's aliases.

### 3.3 `00-manual/generated/shelf-map.md`

```text
# shelf-map | notes 80 | map_version 3f9a1c27b0d4
# flags: S=sensitive  H=has superseded facts  R:<date>=review date  A:<code>=also in area  C:<parent>=chunk of  P:<pages>=pages
slug|type|title|about|aliases|status|updated|flags
## 08 rest-joy
community-garden-plan|project|Community garden plan|Plan for a shared garden plot with neighbours|garden plan|active|2030-05-02|R:2030-06-01 A:02
garden-book-ch-03|source|Garden book: soil|Chapter on soil preparation and compost in the garden book||—|2030-04-10|C:garden-book P:41 to 58
```

(The example rows are invented, as in the brain template.)

- `about` is the note's `description` as written. The checker enforces its length and content (section 4); the generator never cuts it, so the note and the map always agree.
- `updated` is the note's `updated` field.
- A note appears exactly once, under its `area` (`cross` notes under `## cross`).

### 3.4 `00-manual/generated/relationship-map.md`

```text
# relationship-map | links 97 (194 with inverses) | map_version 3f9a1c27b0d4
# omitted: hub lists/listed_in links. Chunk chains written once: chain <parent>: a > b > c
## 08 rest-joy
community-garden-plan: advances healthy-routine-goal · mentions ana · located_in hamburg-allotments
chain garden-book: -ch-01 > -ch-02 > -ch-03
```

- **The incident layout:** one line per note with all of its links, inverses written out by code, sorted by verb then target.
- **Chunk `part_of` and `precedes` links** are folded into the `chain` line.
- **`mentions` / `mentioned_in`** are kept, pending E2 (**Decide**, 1.3 #4).

### 3.5 `open_notes` return format

```text
=== community-garden-plan (08-rest-joy/community-garden-plan.md) | updated 2030-05-02 | flags R:2030-06-01
<full note text>
--- neighbours (1 hop, descriptions only)           ← only when the L3 switch is on (default off)
advances healthy-routine-goal | goal | Keep a weekly outdoor routine
```

- Several slugs per call, opened in parallel.
- Neighbours exclude hub links, never include facts, and are listed once per call even if two opened notes share them.

### 3.6 Cache layout (fixed order, 1-hour TTL, two breakpoints)

```text
[tools: open_notes, search_notes]
[system: Lia skills (brain repo, D23) + taxonomy.md + node.md]   ── breakpoint 1 (1h): changes rarely
[system: atlas → shelf-map → relationship-map]                    ── breakpoint 2 (1h): changes on each commit
[messages: L0 pre-opened notes (switch, default off), then the question]   — never cached
```

Today this is about 8.7k + 9.9k ≈ 18.6k cached tokens (20k with mentions kept), plus Lia's skills.

## 4. Checker rules this needs

These are added to the write path from PR #28 (D22). **Hard rules block a write; warnings are listed on the summary card and in `lint.md`.**

| Rule | Hard or warning | Why |
|---|---|---|
| `description` present, one line, no `|` | Hard | The pipe format |
| No `|` or line breaks in `name` or aliases | Hard | The pipe format |
| No digits in `description`, except digits that are also in the note's `name` or an alias (for example, "Job search 2027") | Hard | Maps route, notes answer |
| Chunk page ranges only in `pages`, not in the description | Hard | Same; shown as the `P:` flag |
| Description length ≤ 15 words | **Decide:** hard now, or a warning until E5 (which tests 10 / 15 / 25 words). The proposal is a warning until E5: a hard rule now would flag 55 of 80 notes, and block any edit to them until they are rewritten | Tokens and routing |
| Sensitive notes: description ≤ 8 words and no digits; every sensitive note's description is listed in `lint.md` for Manoj to read after any change | Hard for the shape; human review for the meaning | Free code can't judge "reveals" |
| Unique slugs; aliases unique across the brain | Hard (already in the structural pass) | Routing by name |
| Only the 22 verbs (and `mentions`) appear in maps | Hard (already) | — |

**Migration:** the rules can't go live until the existing descriptions comply. That means one approved batch of description rewrites through Lia's write path, or by hand. It is a brain change, so it needs Manoj's approval, and it comes with a `node.md` amendment (D31, "description" rule) before the generator ships.

## 5. The generator

- **Where:** `app/src/yggdras/data/maps/` (data layer): `atlas.py`, `shelf.py`, `relations.py` and a shared `version.py`. It is called by the structural pass in library mode, so one command rebuilds everything.
- **Inputs:** the parsed notes and the `build_map` edges, which already exist, plus the area table from `taxonomy.md`.
- **`map_version`:** the first 12 hex digits of a SHA-256 over:
  - the generator's own version string;
  - each mapped note's path and bytes, in sorted order;
  - `taxonomy.md`'s bytes.

  The same input always gives the same version. Lia's answers record it, so an answer can be traced to the maps it saw (and L6's answer cache keys on it).
- **When:** after every Lia commit and every Undo, inside the same commit (D8 as amended). Also from the CLI: `yggdras maps build`.
- **Budget warning:** the generator counts tokens with a local estimate: characters ÷ 2.35, calibrated against today's `count_tokens` result of 9,857 tokens for 23,189 characters. Slugs and pipes make map text denser than prose. The estimate is recalibrated with `count_tokens` at each monthly log. It warns in `lint.md` above 20k tokens.
- **Map-size log:** `yggdras maps stats --log` appends one dated line (notes, tokens per file, total) to `00-manual/map-size-log.md`. It runs on the first commit of each month, or by hand. It is the one map file that isn't deterministic, so it is excluded from the determinism test. **Decide:** keep the log in the brain (proposed) or in `local-data/`.

## 6. Citation check

- **Format:** Lia cites each claim as `[[slug]] "exact fact line text"`.
- **The check (free code):**
  - the slug was among the notes opened for this question;
  - the quoted text appears word for word in that note's Facts or History, after whitespace is normalised.
- **On a failure:** the answer goes back to Lia once, with the failing citation named. If it fails again, the claim is marked "unverified" in the reply. The check never silently drops a claim.
- **Logging:** each answer's check result is logged with `map_version`, for the experiments.

## 7. Scaling triggers

Measured today: about 120 map tokens per note.

| Stage | Trigger | Change |
|---|---|---|
| Now (≤ ~160 notes) | Total maps under 20k tokens | Three whole files |
| Warning | Total maps over 20k (about 165 notes at today's rate) | `lint.md` warns; plan the split |
| Split | Total maps over 25k (about 200 notes), or E7 shows routing recall dropping | Atlas plus per-area shelf and relationship files, several opened at once; BM25 over map rows and aliases |
| Search | Atlas over ~150 lines, or routing recall dropping again | Per-area maps plus hybrid search (BM25 + local embeddings), and a neighbour tool weighted by verb |

The monthly size log (section 5) tracks this; thresholds use measured tokens, not note counts.

## 8. Experiments

**Pass bars** are the report's section-7 drafts, as Manoj chose, and he may tighten them:
- accuracy matches or beats variant C;
- 100% citation-check pass on returned answers;
- p50 latency ≤ 8 s for questions that need no search;
- cost within 2× of the plan's estimate.

Any arm that doesn't beat the simpler one on accuracy is dropped.

| # | Question | Needs |
|---|---|---|
| E1 | Format: pipe rows vs JSON vs prose | Generator with three output modes |
| E2 | Relationship map worth its tokens? Also with vs without `mentions` | Shelf-only mode; mentions switch |
| E3 | L0 pre-pass | L0 with the specificity rule (1.3 #10); switch |
| E4 | Inverses written out vs outgoing only | Generator mode |
| E5 | Description length 10 / 15 / 25 words | Three description sets, which are brain changes. Run on copies of the brain, never the real one |
| E6 | Same model for routing and answering vs a small-routes / large-answers cascade | Model client per role (D27) |
| E7 | When does one flat shelf map break? | Synthetic brains of 100 / 300 / 1,000 notes, and routing recall |
| E8 | Neighbour stubs in `open_notes` | Switch |

**Blocked:** every experiment depends on the life hard-eval answer key (`evals/hard-v1.md` in the brain repo). Its 20 questions were frozen on 2026-10-30, but their Answer and Notes fields are empty. E1, E4 and E7 can run on the Apollo hard set first. Apollo is a flat brain, so its folders stand in for areas.

**Writing the answer key** (proposed):
1. Pin the brain commit the key is written against, and record its hash in the file.
2. For each question, Manoj answers in his own words (by text or voice, one sitting or several). Claude only structures:
   - the answer;
   - the notes needed (slugs);
   - the exact fact lines that support it;
   - "abstain" where the brain doesn't hold the answer. Abstention is scored too.
3. Claude never proposes an answer. Where a note is missing, that is recorded as "abstain" or a brain gap, not filled in.
4. Manoj reads the finished key and approves it. It is committed in the brain repo with its SHA-256 in the commit message, before any run.
5. After that it is never edited. A wrong answer is fixed in `hard-v2.md`, and results always name the version. The key stays outside `library/` and outside Lia's reach (D30).

## 9. Tests (for the generator build)

| Test | Bar |
|---|---|
| Determinism | Two builds of the same brain give byte-identical files; a whitespace-only change outside the notes changes nothing |
| `map_version` | Changes when any mapped note or `taxonomy.md` changes; stays the same otherwise |
| No facts in maps | No fact line from any note appears in any map file; no digits in `about` except name or alias digits |
| Every note once | The shelf map has exactly one row per mapped note; none from `00-manual` or `14-inbox` |
| Every link with its inverse | Every non-hub edge from `build_map` appears in both endpoint lines (or in a `chain` line); no hub links |
| Sensitive flag | Every `sensitivity: high` note has `S`; no other note has it |
| Pipe safety | A fixture with `|` in a description is rejected by the checker before the generator runs |
| Token budget | A synthetic 220-note brain triggers the 20k warning in `lint.md` |
| Citation check | A fabricated quote, a quote from an unopened note, and a quote with only whitespace changes give fail, fail, pass |

All of these run on Apollo and synthetic fixtures only (D23).

## 10. Register changes needed

- **D31 (node format):** amend the `description` rule (≤ 15 words or per E5; no figures; sensitive shape; page ranges in `pages` only). This also needs a brain change: one approved batch of rewrites.
- **D6 (derived, one-way):** no change. The maps are derived and droppable. Confirm the size log is the one non-deterministic generated file.
- **D8:** already amended in PR #28 (rebuild on every commit and Undo). No further change.
- **New D34, "Maps route, notes answer":** the maps hold no facts; answers cite fact lines in opened notes, checked word for word by code. **Decide:** a register row, or leave it to this plan.

## 11. Disagreements with the report (summary)

1. **Size:** 9.9k tokens today, not 5–6k, and the split comes at about 200 notes, not about 300.
2. **Header:** no timestamp or commit id.
3. **Description rules:** ≤ 15 words as a warning until E5, not a hard rule now; it would flag 55 of 80 notes. "No figures" and the sensitive shape should be hard rules, after one approved rewrite batch.
4. **Mentions:** keep them in the relationship map unless E2 says otherwise.
5. **Chunk pages** go to a `P:` flag; **`also`** becomes an `A:` flag; **"review due"** becomes "review date".
6. **L0** needs a specificity rule for generic aliases.
7. **Sensitive descriptions** need a human review list; code can't judge meaning.
8. **The triples study and the GraphRAG pairing** don't support what the report uses them for.
