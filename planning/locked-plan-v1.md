# Yggdras — Locked Prototype Plan (v1)

Oct 24, 2026 · Manoj

> Public copy. Personal examples are replaced with generic ones; the original lives in the private brain repo. Amended 2026-10-24: D13 reworded, D26–D30 added, decision-record naming and layout notes added to match this repo, provenance rule made explicit, build order steps 6 and 8 tightened, merge-forward simplified (aliases resolve old slugs), runner moved to `app/`. Example facts and dates are invented.

## Scope and principles

This plan builds the brain before anything that depends on it, and treats every later phase as blocked until the one beneath it is trusted.

Four rules govern the whole build:

- **Markdown files are the source of truth.** Every other store is a derived index that can be rebuilt from the files by rerunning an ingest. The moment a derived store holds something the files do not, there are two brains and no way to tell which one is lying.
- **Nothing is built on an unproven layer.** Each phase has an exit test. Failing it means fixing the layer, not starting the next one.
- **One agent before any orchestration.** Coordination is extracted from observed repetition, never designed in advance for workers that do not exist.
- **Daily use beats planning.** The connector lands early so the brain is exercised with real questions while its format can still change cheaply.
- **Every decision is written down with a revisit trigger.** Flexibility comes from decisions being explicit and reversible on a stated condition, not from leaving them vague. The decision register is the authority: when something changes, the row changes and the reason is recorded there.

## Phase 1a — Brain files, links, gateway skill

Build 50 to 100 real nodes by hand, from things actually in use: current projects, work, ongoing learning, and the people attached to them. The node format is designed here, deliberately, for machine extraction later.

**The node.** One markdown file per subject, one subject per file, under about 50 lines. Three parts:

1. A header carrying name, a one-line description written like a search snippet, a type (`person`, `area`, `topic`, `source`, `chunk`, per D29), and a last-updated date.
2. A body of short fact lines, one fact per line, each carrying its source and date.
3. Links to other nodes in wiki form, each with a short reason attached, so the link reads as a labeled relationship rather than a bare pointer.

**Folders.** Subjects split by kind: people, areas, topics, sources. A node lives in exactly one folder.

**The gateway skill.** A markdown instruction file, kept outside the brain, that tells an agent how to navigate: read the index first, pick the category, then the subject, then the chunk, and only then search within that chunk for the exact passage. The graph stops at chapter or section level; the last step down to paragraph, line or word is plain text search inside a small file.

**The index.** One file listing every node with its one-line description. This is what the agent reads before deciding which files to open, and vague descriptions here are the single most common cause of wrong retrieval.

**Exit test.** Ten real questions answered correctly by an agent reading only the index, the gateway skill, and the files it chooses from them.

## Phase 1b — Graphiti layer

Point Graphiti at the corpus built in 1a, once the node format has stopped moving. Graphiti reads text with an LLM, extracts entities and relations, and stores them with timestamps, so its real value here is temporal: it tracks when a fact became true and when it stopped being true, which suits shifting deadlines and statuses.

**Amended 2026-10-24: the value case is link discovery.** A three-node spike disproved the temporal case as assumed. Graphiti's invalidation never fired when a fact and its history arrived in one episode, and superseded values came out inconsistently through model extraction. Separately, the model read recording dates as start dates, and page citations never reached the graph. So 1b's value case is discovering connections not written by hand. Temporal handling is measured and reported, but not gated. History and page precision stay in the files. This is a much thinner case than the one that justified D5–D8, so the link-recovery kill criterion carries it: if recovery can't be told apart from the noise floor, the graph layer is dropped by register amendment. Details are in `requirements/scoping-phase-1b.md`.

**Database.** FalkorDB, running locally in Docker. It is Redis-based, light, and ships bundled with Graphiti's MCP server in a single container, which matters because phase 2 goes that way anyway. Two alternatives stay open: [Kuzu](https://mintlify.com/getzep/graphiti/guides/graph-drivers) is embedded with no server at all, a file on disk, for a truly zero-infrastructure setup; [Neo4j Community](https://help.getzep.com/graphiti/configuration/graph-db-configuration) is heavier but ships a browser for inspecting the graph visually while learning. Graphiti supports all three plus Amazon Neptune through a unified driver interface.

**Ingest direction is one-way.** Files to graph, never the reverse. The graph must be droppable and rebuildable from the files at any moment.

**The free eval.** The links written by hand in 1a are ground truth. Compare them against what Graphiti extracts: where it agrees, the extraction is trustworthy; where it invents connections, its failure modes are now known before anything depends on them.

**Exit test.** A full rebuild from files reproduces the graph, and extracted relations agree with hand-written links often enough to trust the ones it found independently.

## Phase 2 — The connector

An MCP server exposing the brain, running locally, added to Claude Code once. From here on the brain is used daily in plain language, and a week of real use teaches more about what it needs than a month of further planning.

**Tools it exposes:** search the brain, read a node, add a node, link two nodes, and one overview call that returns a compact digest — today's items, what changed since last time, the few nodes most recently touched. The digest is assembled by the connector and kept short, rather than dumping the brain into the context.

**It is also where rules get enforced.** The connector refuses a malformed write: a node with no description, a link to a node that does not exist, a fact with no source. Validation lives here rather than in every agent that writes.

**Exit test.** A week of daily use through Claude Code with no manual file editing required.

## Phase 3 — First agent

One agent doing one real job end to end, with its own skill file. The strongest candidate is the conversation filter, because it runs constantly and its failures are immediately visible.

**The filter, as designed:** a session transcript is written to an inbox folder; a filtering pass extracts decisions, new facts, tasks and changed dates, merges them into the right nodes, and deletes the transcript. Explicit instructions to save are the primary signal. A nightly pass scans for decisions and date changes that were not flagged and lists them as suggestions for approval, so nothing important slips through and nothing is saved without a say-so.

**Keep the transcript for a day or two** before deletion, in case the filter misses something.

**Exit test.** A week of sessions filtered, with the suggestion list short enough to review in a minute and no wrong merges.

## Phase 4 — Second agent, then the orchestrator

Build a second agent with a different shape of job — a research or ingest agent that reads a source and produces chunked nodes is the natural pick, since it exercises the book-chunking path.

**For the chunking agent:** extracting text and page numbers is done by a script, while the agent handles the judgment — where topics change, and what the summaries say. This is cheaper and avoids the agent quietly dropping or rewording lines. Each chunk carries its page range, because PDFs lose that on conversion and without it the system cannot answer questions that name a page.

**Then extract the orchestrator from what repeats** across the two agents. It coordinates rather than doing specialized work: it breaks a request into tasks, hands each to the right agent, tracks which finished or failed, and combines results.

Two rules it holds from the start:

- A cap on how many workers run at once, so a bad loop cannot flood the machine or the bill.
- Workers never write to central memory directly. They hand results to the orchestrator, which confirms them first — this is what "finalized" means.

**Exit test.** A request needing both agents completes without manual intervention, and a deliberately failing worker is handled rather than hanging the run.

## Phase 5 — Features

Calendar, task manager and the notification layer, added one at a time, each as its own tool on the existing connector rather than as a change to it.

**Shared source of truth.** The app and the connector read and write the same underlying data, so a change made through Claude appears in the interface and a change made by hand is visible to the agents. Structured app data — tasks, events, schedule state — lives in a local SQLite file, since a single-user desktop app needs no network hop and works offline. Three writers touch the brain here, so their scopes are kept disjoint: the app writes only task and schedule fields, Claude writes facts and links, and manual edits can touch anything. Git history is the backstop when they collide.

**Notifications** are the designed payoff: six or seven a day, each pointing at one task with a brief, so attention lands somewhere specific instead of on a list. They reach the phone through a Telegram bot, which also opens a path back: a message to the bot becomes a capture straight into the inbox, which covers the capture requirement from a phone.

**Start with one capability** driven by task nodes already in the brain, and only then widen.

**The collision loop**, end to end: the app detects two tasks clashing, picks a new slot, and writes a proposal to the outbox. Telegram asks whether to accept. The answer is recorded in the outbox, and the app applies it to SQLite and the relevant brain node when it next runs. Nothing in this loop requires the machine to be awake at the moment of asking.

**Exit test.** Moving a task's date in conversation updates the calendar, the brain node and the notification schedule together, with no manual reconciliation.

## Phase 6 — Visualization and packaging

The 3D graph view is built last, once the schema has stopped moving. Built early it would be weeks of work tightly coupled to a data model still in flux, and rebuilt every time a node format changed.

**Until then**, any off-the-shelf graph viewer pointed at the files is enough to inspect structure — the goal in the early phases is to see the shape, not to own the renderer.

**The real view** is force-directed, dense, with colored communities, built on a WebGL force-graph library. Worth checking what the best open-source option is at the time rather than committing now. Being a desktop app changes nothing here, since the shell renders a system webview and the view is web technology inside it.

**The shell is Tauri** — a Rust core over the system webview — which keeps bundles small and memory low for a tool that runs all day on one machine.

**Packaging** means the connector becomes a single installable doorway to everything: brain, calendar, agents, features. One doorway is easier to secure and easier to extend, since each new feature is another tool on the same server.

## Cross-cutting, from day one

These start in phase 1a and run through every later phase. The eval set is the highest-leverage item here and the one most often skipped, which is why most systems like this quietly rot.

- **Git on the brain folder.** Free versioning, diffs and rollback. When an agent mangles the brain, the answer is a revert rather than regret.
- **An eval set.** 20 to 30 questions with known answers, run after every change to the format, the gateway skill or any agent. Without it, degradation is invisible until it is severe.
- **Provenance on every fact.** Source and date on each line, so what was stated can always be separated from what an agent inferred.
- **Merge and dedup rules.** The genuinely hard problem: the same entity arriving under three names. Decide early how a new fact updates an existing node instead of spawning a twin, and keep an alias list on each node so later mentions match.
- **A capture path measured in seconds.** Friction at capture kills the system regardless of how good retrieval is. One command or one shortcut, straight into an inbox, sorted later.
- **Skills live outside the brain.** The brain holds knowledge; skills are operating instructions, versioned with the code. This matters because the repo is public, and because skills must be shareable without carrying personal data if this ever becomes a product.

## Stack

Everything runs locally except two things: the model Graphiti calls on every ingest, and the notification outbox. Nothing else needs to be reachable, and the brain never leaves the machine.

| Layer | Choice | Where | Needs uptime | Phase |
| --- | --- | --- | --- | --- |
| Brain storage | Markdown files + git, private repo | Local | No | 1a |
| Graph index | FalkorDB via Docker | Local | Only during ingest and query | 1b |
| Extraction | Graphiti + paid API model | Local process, cloud model | No | 1b |
| Interface | MCP server in Python, Claude as client | Local | No | 2 |
| Agents + orchestrator | Python processes | Local | No | 3–4 |
| App data | SQLite | Local | No | 5 |
| Notification outbox | Supabase table + scheduled job | Cloud | Yes — the only one | 5 |
| Notifications + phone capture | Telegram bot | Cloud | Yes | 5 |
| Desktop shell | Tauri, Rust core + web frontend | Local | No | 6 |
| Graph view | WebGL force-graph, inside the shell | Local | No | 6 |
| Mobile web client | Shared components over Supabase | Cloud | Deferred | Later |

Hosting stays local for the prototype, with one exception. Only the notification outbox needs uptime, because a desktop app cannot fire a push at 9am with the laptop shut. The desktop app computes the schedule while it is running and pushes the next few days of pending notifications to Supabase; the scheduled job sends them through the Telegram bot whether or not the machine is awake. Accept-or-reject answers and anything captured from the phone land back in that same table, and the app reconciles them into the brain on next wake. The outbox never holds brain content, only the four columns in D15.

## Decision register

Every architectural decision, with what would make us reverse it. A decision is flexible because it is written down with a revisit trigger, not because it was left vague. Status is **locked** unless marked otherwise.

| # | Decision | Choice | Why | Revisit when |
| --- | --- | --- | --- | --- |
| D1 | Source of truth | Markdown files | Greppable, diffable, editable by hand, readable by any agent with no service running | Never — this one is structural |
| D2 | Node identity | UUID in frontmatter, filename is a label | Rename anything without breaking links | Links prove stable enough that readable IDs are worth more |
| D3 | Brain repo | Private from first commit, separate from code | Publishing cannot be undone; git history would carry personal life | Never |
| D4 | Code repo | Public | Nothing personal in it once D3 holds | Commercial version starts — then a private fork |
| D5 | Graph index | FalkorDB in Docker, local | Bundled with Graphiti's MCP server, light, Redis-based | Graph outgrows one machine, or Kuzu's embedded mode removes the Docker dependency |
| D6 | Graph is derived | Rebuildable from files, one-way ingest | Prevents two brains disagreeing | Never |
| D7 | Extraction | Graphiti with a paid API model | Best quality on bulk material; conversational capture stays free via Claude | Monthly cost exceeds its value, then local Ollama for bulk |
| D8 | Ingest trigger | Scheduled nightly, catch-up on wake | Batched and cheap; a stale graph costs nothing since files lead | Same-day accuracy matters, then add a manual command |
| D9 | Connector + agents language | Python | Graphiti is Python, so ingest is fixed; one language avoids a process boundary mid-pipeline | A component is provably bottlenecked by Python |
| D10 | App shell | Tauri | Rust core over system webview, small bundles, low memory for an all-day tool | Mobile native becomes a requirement |
| D11 | UI structure | Web frontend behind a data-access interface | Same components run on local files or Supabase, so the web client is not a rewrite | Never — this is cheap now and expensive later |
| D12 | App data | SQLite, local | Single-user desktop app, offline, no network hop | Multiple devices need to write the same tasks |
| D13 | Brain in the cloud | Never a cloud-queryable store; private or encrypted backup to a remote the owner controls is permitted | Privacy, and a live online store would break D1. A backup is not a store: losing the brain to a dead disk is the likelier harm | Never |
| D14 | Always-on component | Supabase outbox + scheduled job | Only the notification queue needs uptime; four columns, free tier | Outbox grows features, then a VPS |
| D15 | Outbox contents | Task ID, time, short title, status | Enough for a useful notification, little enough to accept it leaving the machine | Never widen without a reason written here |
| D16 | Notification channel | Telegram bot | Two-way: delivers pushes and accepts captures from the phone | Telegram proves too limited, then the web client |
| D17 | Bot security | Hardcoded chat ID allowlist | A bot token is public-facing; without this anyone who finds it can command the system | Never |
| D18 | Mobile editing | Telegram now, web app later | Avoids hosting and auth until the need is proven | A daily task cannot be done from chat |
| D19 | Missed notifications | Fire on time, reconcile on wake | Queue was pushed in advance, so uptime of the laptop is irrelevant | Reconciliation proves noisy |
| D20 | Brain write access | Claude, user, and app | App must propose reschedules; user must be able to fix a node in a text editor | Conflicts become frequent — then narrow by field, per D21 |
| D21 | Write partitioning | App writes only task and schedule fields; Claude writes facts and links; user writes anything | Three writers with disjoint scopes collide rarely | A collision happens that git history cannot resolve |
| D22 | Validation | Enforced in the connector, not in agents | One place to change the rules | A writer appears that bypasses the connector |
| D23 | Skills location | Outside the brain, versioned with code | Brain holds knowledge, skills hold operating instructions; D4 requires they carry no personal data | Never |
| D24 | Orchestration | Extracted after two agents exist | Coordination designed for hypothetical workers gets rewritten | Never — this is a sequencing rule |
| D25 | 3D view | Last phase, WebGL force-graph inside the shell | Schema must stop moving first; Tauri renders web tech so nothing is lost by waiting | Schema is stable before phase 6 arrives |
| D26 | Brain repo location | Never inside a sync folder (OneDrive, Dropbox, iCloud) | Sync engines and git interact badly: file locks, partial syncs and corrupted `.git` objects | Never |
| D27 | LLM access | Model client behind an interface from day one, as D11 does for data | Honours constitution #7 (model-agnostic core) while provider switching stays out of scope; cheap now, expensive to retrofit | Never |
| D28 | Code layout | **Open.** Layered (`app/src/yggdras/{interface,processing,data}`) now; layered vs service-oriented (`services/`) decided when there is code to arrange | Phase 1a produces almost no code, so restructuring empty folders gains nothing | Start of phase 2 |
| D29 | Node type enum | `person`, `area`, `topic`, `source`, `chunk`. No `project` type: a project is an area. Concepts are topics, books are sources | Matches the folder structure, so there is one fewer mapping to maintain | A sixth type is genuinely needed — then amend this row, never decide it while writing a node |
| D30 | Eval set location | `questions.yaml` in the brain repo's `evals/`, beside the `brain/` node root, never under it; the runner lives in `app/` and reads the brain path at runtime; the public `evals/` documents the question format and holds a synthetic fixture brain (`evals/fixture-brain/`, invented content only) for testing the format and runner | Questions and answers about the brain are personal data, which D4 keeps out of the public repo; constitution #5 has data flow in at runtime | Trigger fired 2026-10-24: the fixture brain was added. Revisit if the fixture stops matching the real brain's shape |
| D31 | Node format frozen | **Frozen 2026-10-24.** D02 as amended (f02 `by <source>` history; chunk `pages` as `"<first> to <last>"`) is the frozen format. Further changes are register amendments | The 25-question gate passed 25/25 in one recorded run (`yggdras-brain/demo-evals/results/2026-10-24-run-1.yaml`) on a 42-node demo brain (now `yggdras-brain/demo-brain/`) built from public-domain Apollo sources, graded by Claude at Manoj's direction. The real brain's own facts and questions are still to come | The real brain's first graded run fails a question for format reasons |

**Decision records.** A record for a register row lives in `rationale/decisions/` as `Dnn-<slug>.md` (`D02-node-identity.md` is D2), so the mapping is visible in the filename. Records that predate the register keep their own `NNNN-` sequence (`0001-project-setup.md`). Nothing is renumbered.

## Repository layout

The tree below is the eventual target, not a register decision. Until D28 is settled the code repo keeps its current layout (`app/`, `rationale/decisions/` for ADRs, this plan at `planning/locked-plan-v1.md`) and adds only `skills/`, `evals/` and `templates/` for phase 1a. Phase 1a code (the eval runner and the node validator) lives in `app/`.

Two repos, per D3 and D4. The code repo is public and contains nothing personal; the brain repo is private from its first commit and is never a submodule of the public one, because a submodule pointer in public history still names it.

**`yggdras/` — public**

```
apps/
  desktop/            Tauri shell: Rust core + web frontend entry
packages/
  ui/                 shared components, used by desktop now and web later
  data-access/        the interface of D11: one API, two implementations
    local.ts            reads SQLite + local files
    remote.ts           reads Supabase (unused until the web client)
services/
  connector/          Python MCP server — the only validated write path
    tools/              one module per tool
    validation/         schema checks, link integrity, frontmatter rules
  agents/
    filter/             conversation filter (phase 3)
    ingest/             source chunking agent (phase 4)
    orchestrator/       extracted in phase 4, not before
  graph/              Graphiti pipeline, nightly ingest, rebuild command
  outbox/             Supabase client, scheduled job, Telegram bot
skills/
  gateway/            how to navigate the brain
  filter/             per-agent skills, loaded by their agent only
  ingest/
evals/                question format only; questions.yaml lives in the brain repo (D30), the runner in app/
docker/
  falkordb.yml
docs/
  plan.md             this document
  adr/                one file per decision, numbered to match the register
```

**`yggdras-brain/` — private**

```
brain/                the node root: an answering agent is given this folder and nothing above it
  index.md              every node: slug, aliases, uuid, one-line description, type
  people/
  areas/
  topics/
  sources/              chunked books and documents
    <source-slug>.md      the source node: title, author, page count, ingest date
    <source-slug>/        its chunks, one per file
      <source-slug>-ch-01.md  page range in frontmatter; filename = slug
evals/                questions.yaml and results/, beside brain/ so no answer is in an agent's reach (D30)
inbox/                raw captures awaiting filtering, deleted after 48h
private/              notes that are not nodes
.graphiti/            derived index, gitignored, rebuildable
```

Path scoping is the control, not the folder name: an agent with a shell can walk up a directory. What makes the split safe is the combination of a scoped root, the owner grading, and the runner never reading the brain. The split removes the trivial failure mode where answers sit in the directory the agent was told to read.

The `.graphiti/` directory is gitignored deliberately: D6 says the graph is derived, so committing it would create a second source of truth with its own merge conflicts.

## Node schema

The format the whole system depends on. It is designed so a model can parse it without ambiguity and a human can edit it in any text editor.

| Field | Type | Required | Purpose |
| --- | --- | --- | --- |
| `id` | UUID v4 | Yes | Stable identity per D2. Never changes, never reused |
| `slug` | kebab-case | Yes | What links point at. Changeable; the old value moves to `aliases` |
| `name` | string | Yes | Human title as you would say it aloud |
| `type` | enum | Yes | `person`, `area`, `topic`, `source`, `chunk` |
| `description` | one line | Yes | Written as a search snippet — this is what the index shows and what decides whether a file gets opened |
| `created` | ISO date | Yes | Set once |
| `updated` | ISO date | Yes | Touched on every write |
| `aliases` | list | No | Former slugs and other names the subject goes by, so later mentions match one file |
| `pages` | range | Chunks only | Page span in the original, captured at ingest because PDFs lose it; written `"<first> to <last>"` using the printed page labels (`"11 to 16"`, `"5-4 to 5-6"`); a single page is just its label |

**Body format.** Facts are one per line, each tagged with how it is known and where it came from:

```markdown
- [stated] Project deadline moved to 2030-06-30 (src: review meeting, 2030-01-15)
- [derived] Data quality is the binding constraint (src: agent, 2030-01-20)
```

Three tags only. `stated` means you said it, `observed` means it came from a connected source such as the calendar, `derived` means an agent concluded it. The distinction exists so a wrong inference can be found and removed without touching anything you actually said.

**Every fact has a source.** Where no external source exists, the author and the date written are the source, written `(src: self, <date>)`, and the fact is `[stated]`. There is no `src: unknown`: it would blur stated and derived while looking compliant. A fact with no traceable origin that the author also will not stand behind does not belong in the brain.

**Links** are written as `[[slug]]` with a reason attached, which is what turns a pointer into a relationship:

```markdown
- applies [[method-name]] to [[problem-name]]
- reviewed by [[person-name]]
```

Resolution goes slug or alias → index → uuid → path, and `index.md` carries each node's aliases alongside its description. That is what lets a merged or renamed slug keep resolving: the alias does the job a tombstone would. Aliases are stored as written; resolution normalizes both sides before comparing (lowercase, accents stripped, spaces and underscores to hyphens, punctuation dropped; see D02), so `bank work` resolves `[[bank-work]]` and also matches a name typed in passing. A link to a slug that does not exist is not an error; it is a flag that something is worth creating, and the connector reports these rather than rejecting the write.

**Size limit is about 50 lines.** Past that, the node is doing two jobs and should be split, because retrieval precision falls off with file size.

## Connector tool surface

The complete set, defined in phase 2 and extended later. Every write goes through here so validation runs exactly once, per D22.

| Tool | Input | Returns | Writes | Phase |
| --- | --- | --- | --- | --- |
| `overview` | none | Compact digest: today's items, changes since last call, recently touched nodes | No | 2 |
| `search` | query, optional type filter | Matching slugs with descriptions, ranked | No | 2 |
| `read_node` | slug or uuid | Full file contents | No | 2 |
| `read_chunk` | source slug, page or section | One chunk plus its page range | No | 2 |
| `create_node` | type, name, description, facts | New uuid and slug | Yes | 2 |
| `update_node` | slug, facts to add or replace | Updated node | Yes | 2 |
| `link` | from slug, to slug, relation text | Confirmation, plus a warning if the target does not exist | Yes | 2 |
| `resolve` | a name or phrase | Candidate nodes it might refer to, for dedup | No | 2 |
| `list_dangling` | none | Links pointing at nodes that do not exist yet | No | 2 |
| `ingest_source` | file path, title | Chunked nodes under `sources/` | Yes | 4 |
| `schedule` | task slug, time | Updated schedule, collisions flagged | Yes | 5 |
| `push_outbox` | pending notifications | Rows written to Supabase | Yes | 5 |
| `pull_decisions` | none | Accept/reject answers and phone captures awaiting reconciliation | No | 5 |

**Validation rules the connector enforces:** every node has a non-empty description; no two nodes share a slug; every fact line carries a tag and a source; `updated` is touched on write; a node over the size limit returns a warning rather than a rejection; and a write that would create a second node for an existing subject triggers `resolve` first.

**The overview call is deliberately narrow.** It assembles its digest server-side and returns a summary, never a dump of nodes, because the whole retrieval design exists to keep the context small.

## Data models

Two structured stores, both small. Neither holds brain content.

**SQLite, local (phase 5).** The app's working data, derived from task nodes in the brain and reconciled back to them.

```sql
task        id, node_uuid, title, duration_min, due_date, status, priority
slot        id, task_id, starts_at, ends_at, source        -- source: planned | manual | accepted
event       id, node_uuid, title, starts_at, ends_at, origin
notification id, task_id, fire_at, channel, state          -- state: pending | pushed | sent | answered
reconcile   id, kind, payload_json, created_at, applied_at -- inbound from the outbox
```

**Supabase, cloud (phase 5).** The outbox of D14 and D15 — the only table that needs uptime, and the only one that leaves the machine.

```sql
outbox      id, task_ref, fire_at, short_title, kind, state, answer, answered_at
            -- kind: reminder | reschedule_proposal | capture
            -- state: pending | sent | answered | expired
```

`task_ref` is an opaque identifier, not the node UUID, so the cloud row cannot be joined back to your brain by anyone holding the table. `short_title` is the only free text, and it is whatever you wrote as the task title.

**Flow in both directions:**

1. The app computes the next few days of notifications and writes them to `outbox` with `state = pending`.
2. The scheduled job fires each one at `fire_at` through the Telegram bot and sets `state = sent`.
3. Your reply, or a capture you type to the bot, lands in `answer` with `state = answered`.
4. On next wake the app calls `pull_decisions`, writes each into `reconcile`, applies it to SQLite and the relevant brain node, and stamps `applied_at`.

The queue is pushed in advance, which is why D19 works: the laptop being off at `fire_at` is irrelevant, and reconciliation simply happens later.

## Merge, dedup and the eval set

The two cross-cutting items that decide whether the brain stays trustworthy as it grows.

### Entity resolution

The same subject arriving under three names is the hardest recurring problem in a system like this. The rule chain, applied in order before any node is created:

1. **Exact slug match** → update that node.
2. **Alias match** → update the node holding that alias.
3. **Fuzzy name match above threshold** → return candidates and ask rather than guessing. Silent merges are worse than duplicates, because a duplicate is visible and a bad merge is not.
4. **No match** → create, and add any name variant seen in passing to `aliases` immediately.

When two nodes turn out to be the same subject, merge forward: the older `id` survives, the newer node's facts move across, and the newer slug becomes an alias of the surviving node.

**History is kept, not overwritten.** A superseded fact becomes `Project deadline is 2030-06-30 (was 2030-03-31, changed 2030-01-15 by review meeting) (src: kickoff plan, 2030-01-05)` rather than a silent replacement. The final group keeps the original citation, and `by <source>` inside the history names where the change came from, so neither is lost (D02, amended 2026-10-24), because knowing when something changed is often the thing you actually need.

### Eval set

20 to 30 questions with known answers, in the brain repo's `evals/questions.yaml` (D30), run after every change to the node format, the gateway skill, or any agent. Spread across five kinds:

| Kind | Example shape | What it catches |
| --- | --- | --- |
| Direct lookup | "When is the project deadline?" | Retrieval basics, index quality |
| Multi-hop | "Why does the weekly review matter?" | Whether links are being traversed at all |
| Page-precise | "What does chapter 4 of \<source> say about X?" | Chunking and page-range integrity |
| Negative | "What did I decide about \<thing never discussed>?" | Whether it invents an answer instead of saying it has nothing |
| Temporal | "What was the deadline before it moved?" | Whether superseded facts survived |

The negative cases matter most and are the ones usually left out. A system that answers confidently when the brain holds nothing is worse than one that retrieves poorly, because the failure is invisible.

**Run it as a gate, not a report.** A failing eval blocks the next phase, which is what makes the exit tests in each phase meaningful.

## Risks

What is most likely to go wrong, and what the plan already does about it.

| Risk | Why it bites | Mitigation in this plan |
| --- | --- | --- |
| Brain history reaches a public remote | Cannot be undone; forks and caches persist | D3: private repo from first commit, never a submodule |
| Capture friction kills the habit | A brain nobody writes to is dead regardless of retrieval quality | Telegram capture from the phone, inbox folder, no required structure at capture time |
| Silent quality decay | Retrieval degrades invisibly as the corpus grows | Eval set run as a gate on every change, negative cases included |
| Duplicate entities multiply | Three nodes for one person, answers split across them | Resolution chain, aliases filled on first sight, `resolve` before every create |
| Extraction invents relationships | Derived facts pollute stated ones | `derived` tag on every inferred line, so they can be found and dropped wholesale |
| Phase creep | Features arrive before the layer beneath is trusted | Exit test per phase, explicit out-of-scope list |
| Schema churn forces re-ingest | Graph rebuilt repeatedly during 1b | Node format frozen at the end of 1a; graph is rebuildable by design (D6) |
| Extraction cost surprises | Paid API on every ingest, bulk sources are large | Nightly batching (D8), revisit trigger on D7 names cost explicitly |
| Three writers collide | App, Claude and manual edits touch the same node | Disjoint field scopes (D21), git history as backstop |
| Bot token leaks | Anyone who finds it can command the system | Chat ID allowlist (D17), token in environment variables, never the public repo |
| Orchestrator built too early | Designed for workers that do not exist, then rewritten | D24: extracted after two agents, never before |
| 3D view blocks progress | Weeks of work coupled to a moving schema | Phase 6, off-the-shelf viewer until then |

## Build order for phase 1a

The concrete first sitting, in order. Nothing here needs Docker, a database, or a running service.

1. Create both repos. Confirm the brain repo is private before the first commit touches it.
2. Write the node schema down as `rationale/decisions/D02-node-identity.md` and a template file, before writing any node.
3. Build 10 nodes by hand across two domains you know best. Do not automate yet — the format's weaknesses only show up while writing by hand.
4. Write `index.md` and keep it current manually. The descriptions are the product here; treat each as a search snippet you would want to see.
5. Write the gateway skill. Test it by handing it to an agent with no other context and asking three questions.
6. Build out to 50 nodes, adding aliases on every name variant you encounter. Aim for breadth and sharp index descriptions and links, not fact density; let facts accumulate as the brain is used (node-strength experiment, 2026-10-24: no large effect from depth, n=1 per question). From node 11 the agent drafts nodes from what you tell it, and you check each one: writing by hand first exists to debug the format, not as a discipline to keep for its own sake.
7. Write the eval set against what now exists, including at least five negative cases.
8. Run the eval. Fix the format, the index or the gateway skill, not the questions. A malformed question is a bug in the eval set, fixed before the set is frozen alongside the format. After the freeze, questions do not change.
9. Freeze the node format. Record the freeze date in the register, since D-numbers now depend on it. Done 2026-10-24 (D31).

**Open before step 2:** which domains seed the first 50 nodes. It is quick to settle and cheaper to decide now than to migrate later. The `type` enum is settled by D29.

## Out of scope for the prototype

Named here so the plan stays locked and these do not creep back in mid-build. Each is a real goal, deferred rather than dropped.

- Model-agnostic switching between providers
- Health monitoring and the emotion dashboard
- The language-learning page with its tree structures
- Voice models and the common agent across pages
- The life timeline page with deadline milestones
- The mobile web client — deferred until Telegram proves too limited (D18), but the UI is built so it is not a rewrite (D11)
- Cloud hosting beyond the notification outbox, continuous deployment, versioned releases
- Any sync that would put brain content online (D13)
- Sub-brains beyond the two agents of phase 4
- Any product packaging, licensing or paid-tier work

**The one thing to protect** while building: the markdown files remain the source of truth. Every deferred feature above is additive on top of that, and none of them should ever hold state the files do not.
