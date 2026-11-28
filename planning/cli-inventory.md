# CLI inventory (Phase B)

Status: **for Manoj to cut. No CLI code exists.** Read on 2026-11-24 from the top of the
step 1–4 stack (`claude/20261123-links-step4`, PR #56): `app/src/yggdras/interface/cli.py`
(Lia), `brain_api.py`, `data/brain_db/{api,writes}.py`, the MCP server, and the app routers
in `app/api/src/yggdress_app/`. Names are proposals.

**Status key**
- **EXISTS**: already a Lia CLI command, an MCP tool, a module command or a brain HTTP route.
- **WRAPS**: the behaviour is already in code but has no command.
- **NEW**: needs behaviour that does not exist. These are listed separately in §8 and none
  will be built.

**R/W**: R = read, W = write, R$ = read that makes a paid model call.
**Sens.**: whether the command can return text from a `sensitivity: high` note (brain), or a
note title, slug or body that the app marks `restricted` or `unknown`.

## 0. Four facts that decide how the CLI must be built

1. **The `api.*` views cover the app side only.** Migration 043 adds `api.note_refs`,
   `api.links`, `api.note_links` and `api.note_search`: slug, title and sensitivity, masked.
   Nothing in `api.*` holds brain content (note body, tree, full-text search) or tasks and
   calendar. The rule "every read goes through `api.*`" can therefore be met today only by the
   commands marked *via api.*\*. Every other read needs a view from §8.
2. **The brain HTTP API does not filter sensitivity.** `GET /api/note`, `/api/tree` and
   `/api/search` return `sensitivity: high` notes in full, because the brain API serves your
   own app. An agent-facing CLI that wraps them as they are would leak.
3. **Two existing app reads use the raw table.** `connections.py` (`/notes/{slug}`,
   `/tasks/{id}`, `/events/{id}`) and `work_graph.py` read `app.note_refs.observed_title`
   directly. A command must read the masked `api.*` view instead of wrapping these endpoints.
4. **Version checks: optional on the brain, present on the app.** Brain writes refuse a stale
   `version` only when one is sent. The CLI would always read the version first and send it, so
   no new behaviour is needed. App writes (`planning`, `time`, `connections` commands) already
   carry `version` and an idempotency `key`.

## 1. Brain read

| command | status | does | args | returns | wraps | R/W | sens. |
|---|---|---|---|---|---|---|---|
| `brain tree` | EXISTS | areas with their notes | — | area, slug, title, type, version per line | `GET /api/tree` → `brain_db.api.note_tree` | R | yes |
| `brain note` | EXISTS | one note, with links in and out and mentions | `<slug>` | the note's fields and body; `--json` | `GET /api/note/<slug>` → `brain_db.api.note_with_relationships` | R | yes |
| `brain version` | EXISTS | the note's version token | `<slug>` | an integer | `GET /api/version/<slug>` → `brain_db.api.version` | R | no |
| `brain search` | EXISTS | full-text search; an empty query lists every note | `<q>` | slug, title, rank per line | `GET /api/search` → `brain_db.api.search` | R | yes |
| `brain ask` | EXISTS | Lia answers from the notes, with citations | `"<question>" [--model]` | the answer, citations and cost | `yggdras ask` / MCP `ask_lia` | R$ | yes |
| `brain open` | EXISTS | a note rendered for reading | `<slug>` | text | MCP `open_note` → `LiaService.open_note` | R | yes |

## 2. Brain write (each takes `--version`; the CLI fetches it if left out, so it is always sent)

| command | status | does | args | returns | wraps | R/W | sens. |
|---|---|---|---|---|---|---|---|
| `brain add-note` | EXISTS | creates a note from note-format text | `--file F` | slug, version, undo id | `POST /api/note` → `BrainWrites.add_note` | W | yes |
| `brain add-fact` | EXISTS | appends a fact line | `<slug> "<line>" [--section] [--after-line]` | version, undo id | `POST …/add-fact` | W | yes |
| `brain replace-fact` | EXISTS | swaps one fact; `--preview` shows the change and writes nothing | `<slug> --old L --new L [--preview]` | version, undo id or diff | `POST …/replace-fact` | W | yes |
| `brain remove-fact` | EXISTS | removes one fact | `<slug> "<line>" [--preview]` | version, undo id | `POST …/remove-fact` | W | yes |
| `brain link` | EXISTS | adds a typed link | `<slug> <verb> <target> [--preview]` | version, undo id | `POST …/link` | W | no |
| `brain unlink` | EXISTS | removes a link | `<slug> <verb> <target> [--preview]` | version | `POST …/unlink` | W | no |
| `brain undo` | EXISTS | undoes one add, replace or link, once | `<undo_id>` | ok, version | `POST /api/undo/<id>` | W | no |
| `lia tell` | EXISTS | a change request in plain words: adds are written at once, changes become a preview | `"<request>"` | card text, preview id | `yggdras tell` | W$ | yes |
| `lia ingest` | EXISTS | files a markdown file (up to 5 MB) | `<file> [--instruction]` | card | `yggdras ingest` | W$ | yes |
| `lia pending` | EXISTS | previews waiting for confirm | — | id, time, request per line | `yggdras pending` | R | yes |
| `lia confirm` / `lia cancel` | EXISTS | writes or drops a preview | `<preview id>` | card | `yggdras confirm/cancel` | W | yes |
| `lia undo` | EXISTS | undoes one of Lia's commits | `<sha>` | card | `yggdras undo` | W | no |
| `lia restore` | EXISTS | brings back an archived note | `<slug or name>` | card | `yggdras restore` | W | yes |

## 3. Tasks (app DB; commands carry `key` and `version`)

| command | status | does | args | returns | wraps | R/W | sens. |
|---|---|---|---|---|---|---|---|
| `tasks list` | WRAPS | tasks, goals, projects, blocks and events in a date range | `--start D --end D [--tz]` | one line per item; `--json` | `GET /v1/application/planning` → `snapshot` | R | no (raw tables, no `api.*` view, §8 N2) |
| `task show` | WRAPS | one task with its links | `<id>` | the task's fields and linked items | `api.links` + task row (*not* the connections endpoint, fact 3) | R | masked via api.* |
| `task create` / `task update` / `task execute` | WRAPS | changes a task | `--title … [--version]` | id, version | `POST planning/commands` (`task.*`) | W | no |
| `goal create/update`, `project create/update` | WRAPS | same, for goals and projects | the same shape | id, version | `planning/commands` (`goal.*`, `project.*`) | W | no |
| `task link-note` / `task unlink-note` | WRAPS | links a task to a note | `<task> <note_ref>` | link id | `connections/commands` | W | no |

## 4. Calendar

| command | status | does | args | returns | wraps | R/W | sens. |
|---|---|---|---|---|---|---|---|
| `cal list` | WRAPS | the same snapshot, calendar only | `--start --end [--tz]` | one line per item | `planning` `snapshot` | R | no (§8 N2) |
| `block create/update/remove/split` | WRAPS | time blocks | `…[--version]` | id, version | `planning/commands` (`block.*`) | W | no |
| `event create/update/remove` | WRAPS | calendar events | `…[--version]` | id, version | `planning/commands` (`event.*`) | W | no |
| `date-item create/update/remove` | WRAPS | all-day ranges | `--title --start --end [--version]` | id, version | `POST /v1/application/time/commands` | W | no |
| `availability create/update/remove` | WRAPS | availability windows | the same shape | id, version | `time/commands` | W | no |
| `event link-note/unlink-note/link-task/unlink-task` | WRAPS | links | `<event> <target>` | link id | `connections/commands` | W | no |
| `cal context` | WRAPS | what is around one calendar item | `<kind> <id>` | the linked items | `api.links` (*not* `/calendar-context`, which reads raw tables) | R | masked via api.* |

## 5. Notes (app side: references, links, the app's preview flow)

| command | status | does | args | returns | wraps | R/W | sens. |
|---|---|---|---|---|---|---|---|
| `notes find` | WRAPS | searches note references, normal notes only | `<q>` | id, slug, title per line | `api.note_search` | R | masked via api.* |
| `notes refs` | WRAPS | the note references, masked | `[--id]` | id, slug or none, title, sensitivity | `api.note_refs` | R | masked via api.* |
| `notes linked` | WRAPS | everything linked to a note, or the notes linked to a thing | `--note ID` or `--thing KIND:ID` | link, kind, id, verb, label | `api.note_links`, `api.links` | R | masked via api.* |
| `links list` | WRAPS | active links in both directions | `--kind K --id I [--verb]` | link, from, verb, to, origin, approved | `api.links` | R | masked via api.* |
| `notes preview/confirm/cancel/create/undo` | WRAPS | the app's guarded edit flow (fetch token = version) | `<slug> …` | token, result | `/v1/notes/*` (`NotesProxy`) | W | yes |
| `notes to-work` | WRAPS | creates a task or event from a note | `<slug> --kind task|event …` | id | `POST connections/from-note` | W | no |
| `graph roots` / `graph show` | WRAPS | the work graph | `[--q]` / `<kind:id>` | nodes and edges | `work_graph` (reads raw `note_refs`: use the masked `api.*` view, or cut) | R | yes, as it is today |

## 6. Agents and runs

| command | status | does | args | returns | wraps | R/W | sens. |
|---|---|---|---|---|---|---|---|
| `agents status` | WRAPS | whether the agent runtime is up | — | state | `GET /v1/application/agents/status` | R | no |
| `agents reviews` / `agents resolve` | WRAPS | lists and answers pending proposals | `[--limit]` / `<id> approve|reject` | id, summary / ok | `agents/reviews`, `reviews/resolve` | R/W | yes (proposal text) |
| `runs list` / `runs show` / `runs cancel` | WRAPS | executions | `[--limit --before]` / `<id>` / `<id> --version` | id, state, time | `agents/executions*` | R/W | yes (answers) |
| `assistant send` / `resume` / `thread` | WRAPS | the conductor chat | `"<msg>"` / `<id>` | events, final answer | `POST /v1/assistant`, `…/threads/{id}` | W$ | yes |
| `assistant policy` | WRAPS | reads or sets the approval policy | `[--set …]` | the policy | `GET/PUT /v1/assistant/policy` | R/W | no |
| `events read` | WRAPS | the next change events for one named consumer; moves its cursor | `<consumer> [--limit]` | seq, kind, subject, actor per line | `events.read` (`app.events`) | R (advances the cursor) | no (ids only) |
| `orchestrate *` | EXISTS | session orchestration | see `orchestrate --help` | status lines | `tools/orchestrate` (PR #58) | R/W$ | no |

## 7. Admin (for Manoj only; never in a worker's slice)

| command | status | does | args | returns | wraps | R/W | sens. |
|---|---|---|---|---|---|---|---|
| `app password` / `app migrate` / `app serve` | EXISTS | password hash, migrations, serve | as today | message | `yggdress_app.cli` | W | secrets |
| `migrate-hosted plan/apply/counts` | EXISTS | the hosted database | as today | the plan or the counts | `yggdress_app.migrate_hosted` | W, **production** | yes |
| `cloud-move check/dry-run/cutover/rollback` | EXISTS | the cloud move | as today | report | `yggdress_app.cloud_move` | W, **production** | yes |
| `backup` | EXISTS | backs up the database and the markdown | as today | paths | `yggdress_app.backup:main` | R | yes |
| `scratch-db up/down/url` | EXISTS | throwaway PostgreSQL | `[name]` | URL | `tools/scratch_db.py` | W (scratch) | no |
| `mcp` | EXISTS | the yggdras MCP server | as today | stdio | `yggdras mcp` | — | — |

Not inventoried (outside the seven groups): daily routines, calls and voice, connectors,
mobile updates, routine delivery.

## 8. NEW: behaviour that does not exist (none will be built)

| # | what | why the rules need it |
|---|---|---|
| N1 | `api.*` views over brain content (tree, note, search) that drop or mask `sensitivity: high` | "every read goes through `api.*`" for brain reads (facts 1 and 2). Needs a migration on the brain side, and `brain` is outside the app's schema boundary |
| N2 | `api.tasks`, `api.calendar` views | the same rule for task and calendar reads; today they read raw tables |
| N3 | a judgements reader (`judgements list`) | `app.judgements` exists (step 4) and nothing reads it |
| N4 | the dedicated `yggdras_agents` database role, granted only `api.*` | the real enforcement of "no command may bypass the views". Step 2 left it out (PR #54) |
| N5 | a way for the CLI to authenticate to the app's HTTP API without the owner's browser session | `/v1/application/*` needs `Depends(session)`. Either the CLI calls the same functions in-process with a scratch or local DB URL, or a token kind is added |

## Decisions for Manoj

1. **Cut the list.** Recommended for Phase C: §1, §2, §5's `via api.*` rows, `events read`,
   and the §3/§4 writes. Leave out §7 and the paid `lia tell`/`ingest`/`assistant send`.
2. **Brain reads (facts 1 and 2):** either approve N1 first, or let the CLI's brain reads
   filter `sensitivity: high` itself. The second option puts the rule in the CLI instead of in
   SQL, which is the thing G9 warns about.
3. **How the CLI reaches the app (N5):** in-process with a database URL (no HTTP, no
   session), or over HTTP with a new token kind.
4. **The name:** extend the existing `yggdras` command (`yggdras brain note …`) or start a new
   one.
