# Connected data: a proposal to make the tables one brain

Status: **PROPOSAL, 2026-11-23. Nothing here is built.** Every table and column below is a
draft for Manoj to accept, change or reject (AGENTS.md: never invent requirements; ask before
touching stored data). Where a choice could go either way it is listed under *Decisions*.

Facts come from the 95 production tables as of migration 040 (`app`: 83, `brain`: 12),
read from the migrations on `main`, not from a live query.

## The test every change below has to pass

`intent/big-picture.md` is the bar, not "more links":

- **It serves the one line** (turn what Manoj knows into possibilities he can act on,
  reliably, cheaply, privately) or it is cut.
- **It respects the ladder.** Discovery (rung 6) does not start until answering passes a
  hard eval. So this proposal *prepares* discovery's tables and ships the rungs below it.
- **Obvious is free, significant is paid.** Links code can derive are written by code;
  a model is only asked about the short list that clears a threshold.
- **Nothing enters the brain without approval.** Every machine-made link is a proposal
  until Manoj approves it.
- **Private by default.** The app still reaches the brain only through the Brain API; no
  foreign key crosses from `app` into `brain`.

"100% signal" is not promised, because no system can measure itself perfect. What is promised: every link is typed,
sourced and approved-or-not, every consumer gets only what it may see, and signal is
*measured* (approval rate of suggestions, answer accuracy) instead of assumed.

## What is wrong today (the critique)

| # | Gap | Evidence | Cost |
|---|---|---|---|
| G1 | **Four copies of one link.** `task_note_links`, `event_note_links`, `availability_note_links`, `date_item_note_links` have the same shape (thing, note, `kind` in source/context/result). | migration 003 and later | Every new kind of thing (a call, a journal entry, a project) needs another table, another grant and more code. Agents cannot ask "what is linked to this?" in one query. |
| G2 | **Links have no meaning.** The app's links know only `source`/`context`/`result`; the brain's `relationships` use real verbs (`brain.verbs`). | `kind` CHECK vs `brain.verbs` | "This task *blocks* that goal" or "this event *is evidence for* that note" cannot be said. The fixed verb list the ladder calls for exists only inside the brain. |
| G3 | **No record of who made a link, or why.** Rows carry `created_at`, not *by whom* (Manoj, Lia, a rule, a connector) or *from what*. | all link tables | You can't tell a link you wrote from one an agent guessed, so you can't measure or roll back agent mistakes. Principle 2 (facts with their source) stops at the brain's edge. |
| G4 | **Sensitivity stops at the bridge.** `brain.notes.sensitivity` exists; `app.note_refs` does not carry it. | 0001 brain schema vs 003 | Every app-side reader (chat catalog, conductor, side chat, phone) must re-check on its own. One forgotten check leaks a sensitive title. |
| G5 | **No shared change stream.** Changes live in `workspace_changes` (the UI feed), `notifications`, `scheduled_jobs`, `conductor_events`, `agent_*` and `brain.changes`, each with its own shape. | six tables | Agents and MCP tools poll or miss things. There is no single, ordered "what happened" for an agent to subscribe to, so they get noise instead of signal. |
| G6 | **Judgements are scattered.** `yggdras_feedback`, `workflow_reviews`, `call_reviews`, `daily_reviews`, `item_outcomes`. | five tables | Your approvals and rejections are the best training signal the system has, and they can't be counted together. "Measure, don't guess" has nothing to read. |
| G7 | **Two chat engines, two run logs.** `chat_requests` + `agent_runs` (old pipeline, phone) and `conductor_runs`/`events` (new chat). | 009/010 vs 040 | Two places to look for what an agent did; two approval systems. |
| G8 | **Nowhere for a suggested connection.** No table holds "a link the brain found that you have not approved". | none exists | Discovery has nowhere to put its output, and a rejection is not remembered, so the same bad idea can come back. |
| G9 | **Agents and MCP read raw tables.** Sensitivity and permission rules sit in Python, per caller. | `catalog.py`, `notes_proxy.py`, MCP server | Each new agent or MCP tool must re-implement the rules correctly. |

What is **not** wrong, and should stay: one time model per kind of thing (merging
calendar events, blocks and availability into one table would be over-normalising), the
brain's own graph (`notes` - `relationships` - `verbs`), and the API boundary between
`app` and `brain`.

## The proposed structure

```
                 BRAIN (unchanged: notes, relationships, verbs, ...)
                                   ▲ Brain API only
   ┌───────────────────────────────┴───────────────────────────────┐
   │ app.note_refs  + sensitivity (G4)                             │
   └───────────────────────────────▲───────────────────────────────┘
                                   │ (kind='note', id=note_ref)
   ┌───────────────────────────────┴───────────────────────────────┐
   │ app.links: ONE typed edge table for every pair (G1, G2, G3)   │
   │   from (kind,id) ─ verb ─► to (kind,id)                       │
   │   origin: manual | rule | agent | connector · status          │
   └─────▲──────────────▲───────────────▲──────────────▲───────────┘
         │              │               │              │
     tasks, events,  journal, calls, chat     candidate links (G8)
     availability,   routines, projects       ─ approve ─► links
     date items      (any table, no new       ─ reject ──► remembered
                      link table needed)
   ┌───────────────────────────────────────────────────────────────┐
   │ app.events: one ordered change stream (G5); every write adds a │
   │ typed row; agents, MCP, discovery and sync read by cursor      │
   ├───────────────────────────────────────────────────────────────┤
   │ app.judgements: every approve/reject/rating in one place (G6)  │
   ├───────────────────────────────────────────────────────────────┤
   │ api.* views: the only thing agents and MCP read (G9);          │
   │ sensitivity applied once, inside the view                      │
   └───────────────────────────────────────────────────────────────┘
```

### 1. `app.links`: one typed, sourced edge table (G1, G2, G3)

```sql
CREATE TABLE app.links (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_kind   text NOT NULL,   -- 'task','event','availability','date_item','note','journal','call','project','goal',...
  from_id     uuid NOT NULL,
  verb        text NOT NULL REFERENCES app.link_verbs(verb),
  to_kind     text NOT NULL,
  to_id       uuid NOT NULL,
  origin      text NOT NULL CHECK (origin IN ('manual','rule','agent','connector')),
  origin_ref  text,             -- which rule / agent run / connector made it
  status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  retired_at  timestamptz,
  UNIQUE (from_kind, from_id, verb, to_kind, to_id)
);
CREATE INDEX links_from ON app.links (from_kind, from_id) WHERE status = 'active';
CREATE INDEX links_to   ON app.links (to_kind, to_id)     WHERE status = 'active';

CREATE TABLE app.link_verbs (      -- the fixed list the ladder asks for (rung 3)
  verb     text PRIMARY KEY,       -- 'about','source_of','result_of','blocks','part_of',
  inverse  text NOT NULL,          -- 'evidence_for','scheduled_for','follows_up',...
  meaning  text NOT NULL
);
```

- "Everything linked to this" becomes one indexed query in both directions, for any
  kind of thing, which is what agents and MCP tools need.
- Notes stay behind the bridge: a note end is `('note', note_refs.id)`, never a brain id.
- Integrity: polymorphic ends cannot have plain foreign keys. A trigger checks that the
  row exists for known kinds; the four old tables keep their foreign keys until contract.
- **Expand-contract.** Release 1 adds `links` and backfills from the four link tables
  (`kind` maps to verbs: source→`source_of`, context→`about`, result→`result_of`), and
  code writes to both. Release 2, after production has run release 1, reads from `links`
  only. Release 3 drops the four old tables.

### 2. Sensitivity on the bridge (G4)

`ALTER TABLE app.note_refs ADD COLUMN sensitivity text` (nullable: expand), filled from
the Brain API whenever a ref is verified. Every view in section 6 hides a restricted
note's title. The brain stays the authority; this is a cached copy re-checked on every
verify, like `observed_title` already is.

### 3. `app.events`: one change stream (G5)

```sql
CREATE TABLE app.events (
  seq        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  at         timestamptz NOT NULL DEFAULT now(),
  kind       text NOT NULL,      -- 'task.created','link.approved','note.saved','run.finished',...
  subject_kind text NOT NULL, subject_id uuid,
  actor      text NOT NULL,      -- 'manoj','lia','conductor','rule:<name>','connector:<name>'
  detail     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- ids and small fields only, never note text
  sensitivity text
);
CREATE TABLE app.event_cursors (consumer text PRIMARY KEY, last_seq bigint NOT NULL);
```

Each write path adds one row in the same transaction (an outbox). Consumers (agents, the
MCP server, discovery, phone sync) keep their own cursor and read forward. It is the
pattern `conductor_events` and `workspace_changes` already use, done once for the whole
app. Expand: those two keep working; `workspace_changes` can become a view later.

### 4. `app.judgements`: every verdict in one place (G6)

```sql
CREATE TABLE app.judgements (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_kind text NOT NULL, subject_id uuid NOT NULL,   -- a link, a suggestion, an answer, a run, a call
  verdict    text NOT NULL CHECK (verdict IN ('approved','rejected','useful','wrong','neutral')),
  by         text NOT NULL,      -- 'manoj', or an evaluator's name for automatic checks
  reason     text,
  at         timestamptz NOT NULL DEFAULT now()
);
```

Backfilled from the five feedback tables (expand), which keep working. This is the
dataset for the hard eval and for discovery's threshold: precision equals approved
divided by shown.

### 5. `app.candidate_links`: where discovery will put its output (G8). Gated.

```sql
CREATE TABLE app.candidate_links (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_kind text NOT NULL, from_id uuid NOT NULL,
  verb      text NOT NULL REFERENCES app.link_verbs(verb),
  to_kind   text NOT NULL, to_id uuid NOT NULL,
  distance   real,   -- cheap, from the graph: how far apart the two areas are
  possibility real,  -- cheap, from the graph: how many new links it would open
  action     real,   -- paid, model-judged, only for the short list
  score      real,
  evidence   jsonb NOT NULL DEFAULT '{}'::jsonb,   -- ids of the notes/facts behind it
  status     text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','rejected','expired')),
  proposed_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (from_kind, from_id, verb, to_kind, to_id)
);
```

Approve creates a row in `app.links` (origin `agent`) and a `judgement`; reject keeps the row
as `rejected`, so the same pair is never suggested again. This is literature-based
discovery with memory. **Built only after answering passes the hard eval** (the ladder rule).

### 6. `api.*` views: the one surface for agents and MCP (G9)

A read-only schema of views, for example `api.entity_links` (links joined to titles, with
restricted titles replaced) and `api.recent_events`, granted to a dedicated
`yggdras_agents` role. Agents and the MCP server read only these. Sensitivity and
permissions live once, in SQL, and are tested once.

### 7. One run log (G7)

Move the phone and the old panel onto the conductor, then retire `chat_requests` and the
`agent_*` tables, about 9 tables. Expand-contract over two releases. This is the largest
change, so it comes last.

## Order of work (each step proven before the next)

| Step | What | Rung it serves | Risk | Size | Status |
|---|---|---|---|---|---|
| 1 | `link_verbs`, `links` (expand + backfill + dual write) | 3: links | low, additive | M | [x] built 2026-11-23: migration 042, tests, rehearsal 48 = 48 |
| 2 | `note_refs.sensitivity` + `api.*` views + agents role | 5: answering, safely | low | S | [x] built 2026-11-23: migration 043, views, backfill 3 restricted / 8 normal / 1 unknown in rehearsal; separate agents DB role not created (see PR) |
| 3 | `events` outbox + cursors | 5, and 6 later | low | M | [ ] |
| 4 | `judgements` (expand + backfill) | 5: the hard eval | low | S | [ ] |
| 5 | retire the four link tables (contract) | n/a | medium, destructive | S | [ ] |
| 6 | one run log (phone onto the conductor) | 5 | medium | L | [ ] |
| 7 | `candidate_links` + significance scoring | **6: discovery, gated on the hard eval** | n/a | L | [ ] |
| 8 | frameworks / situations | 7-8 | n/a | n/a | [ ] |

Each migration ships through `migrate_hosted plan` then `apply` **before** its PR merges
(production never migrates by itself). Destructive steps (5, end of 6) need the label
`destructive-migration-approved`.

## How it pays off, per consumer

- **Lia and the conductor:** "what is around this task?" is one query over `api.entity_links`;
  sensitive notes are filtered before the model sees anything.
- **MCP tools:** read the views and the event stream, so there are no rules to re-implement and no
  raw-table access.
- **Discovery (later):** reads `links` and `events`, writes `candidate_links`, learns from
  `judgements`. Obvious links are free (rules); only the short list costs a model call.
- **You:** every link says who made it and why; one place shows what agents proposed and
  what you decided; one number (approval rate) says whether suggestions are worth it.

## Decisions for Manoj

1. **The verb list.** Accept the starter list above, or set it yourself. The ladder already
   says 15 to 20 verbs with their inverses.
2. **Polymorphic links.** One `links` table with a trigger for integrity (proposed), or keep
   one table per pair and add only verbs and origin. The second option has stricter foreign keys but repeats G1.
3. **Whether to retire the old chat path** (step 6) now, or keep two engines until the
   phone is rebuilt.
4. **Whether `candidate_links` is created now (empty) or only when discovery starts.** The
   ladder rule says discovery waits; an empty table is harmless but is still a schema change.
5. **Where to start.** Steps 1 to 4 are additive and low-risk. Recommended: step 1 then 2.
