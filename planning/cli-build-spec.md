# CLI build spec (Phase C): the contract both runs build to

Approved list: planning/cli-inventory.md, cut by Manoj on 2026-11-24 (decisions 1–5).
The base for this spec (the dispatcher, the contract module, app forwarding and the MCP tool)
is already on the base branch. **Build only the commands below. Change no existing behaviour.**

## Commands

`yggdras <group> <verb> …`. Brain groups run in the `yggdras` package; app groups run in
`yggdress_app` (`python -m yggdress_app.commands`), and `yggdras` forwards them with the same argv.

| group | verbs | where |
|---|---|---|
| `brain` (read) | `tree`, `note <slug>`, `version <slug>`, `search <q>` | `app/src/yggdras/interface/commands/brain_read.py` |
| `brain` (write) | `add-note --file F`, `add-fact <slug> <line> --version V [--section S] [--after-line L]`, `replace-fact <slug> --old L --new L --version V [--preview]`, `remove-fact <slug> <line> --version V [--preview]`, `link <slug> <verb> <target> --version V [--preview]`, `unlink <slug> <verb> <target> --version V [--preview]`, `undo <undo_id>` | `…/commands/brain_write.py` |
| `notes` | `find <q>`, `refs [--id ID]`, `linked (--note ID \| --thing KIND:ID)` | `app/api/src/yggdress_app/commands/notes.py` |
| `links` | `list --kind K --id ID [--verb V]` | `…/commands/notes.py` |
| `changes` | `read <consumer> [--limit N]` | `…/commands/changes.py` |
| `task` | `create`, `update <id> --version V`, `execute <id> --version V`, `link-note <task> <note_ref>`, `unlink-note <task> <note_ref>` | `…/commands/planning.py` |
| `goal`, `project` | `create`, `update <id> --version V` | `…/commands/planning.py` |
| `block` | `create`, `update <id> --version V`, `remove <id> --version V`, `split <id> --version V …` | `…/commands/planning.py` |
| `event` | `create`, `update <id> --version V`, `remove <id> --version V`, `link-note`, `unlink-note`, `link-task`, `unlink-task` | `…/commands/planning.py` |
| `date-item`, `availability` | `create`, `update <id> --version V`, `remove <id> --version V` | `…/commands/planning.py` |

Write fields are passed as `--set name=value` (repeatable) or `--data JSON`, and are given
unchanged to the existing command models (`planning_models.Command`, `temporal.TimeCommand`,
the connections command). `--key UUID` is optional; when it is left out the CLI makes one and
prints it, so a retry with the same key is safe.

## Output (the token saving)

- **Success:** one line per result, fields separated by tabs, no header and no prose. With
  `--json`, one JSON document on stdout. A write prints `ok\t<id or slug>\t<new version>[\t<undo_id>]`.
- **Errors:** one line on stderr, `error\t<kind>\t<message>`. With `--json`, it is
  `{"error": kind, "message": …}` on stderr instead.
- **Exit codes** (`commands.contract.Exit`):

| exit | kind | meaning |
|---|---|---|
| 0 | — | ok |
| 1 | `failed` | anything unexpected |
| 2 | `usage` | bad arguments (argparse) |
| 3 | `not_found` | no such note, id or link |
| 4 | `not_allowed` | the target is restricted, or the action is not permitted |
| 5 | `stale` | the version is old: someone else changed it, so reload |
| 6 | `invalid` | the value is refused by the existing validation (422) |

Raise `contract.CliError(kind, message)`. The runner prints it and exits with its code. Map
the existing errors (`ApiError.status`, `HTTPException.status_code`): 404 → `not_found`,
409 because of the version → `stale`, any other 409 → `invalid`, 422 or 400 → `invalid`,
403 → `not_allowed`.

## Safety rules (tested)

- **Reads use only the `api.*` views.**
  - Brain reads use `api.brain_notes`, `api.brain_note_bodies`, `api.brain_note_areas`,
    `api.brain_links`, `api.brain_search` and `api.brain_note_access()` (brain migration
    0005). Never `brain.*` tables, `brain_db.api`, or the brain HTTP API.
  - App reads use `api.note_refs`, `api.note_search`, `api.note_links` and `api.links`.
  - Exception: `changes read` wraps `events.read`. It returns exactly the `api.events`
    columns, ids only. The view has no `tx` column, and the cursor needs it.
- **A restricted target exits 4**, for example `brain note ada-lin` or `brain add-fact ada-lin …`;
  `api.brain_note_access()` gives the verdict. **A missing target exits 3.**
- **Every write that changes something that already exists needs `--version`.** A stale
  version exits 5 and writes nothing. Brain writes pass it to `BrainWrites`. App writes pass
  it to the command model.
- **Writes call the existing functions**: `BrainWrites.*` with a `RowStore`, and
  `planning.command_result` / `temporal.temporal_result` / the connections command handler,
  with the same lock, receipt and command id as their router. If a router's body has to be
  shared, move it into a function that the router and the CLI both call, with **no change in
  behaviour**. The router's existing tests must still pass unchanged.
- **MCP:** `yggdras_command` (already on the base) calls `commands.run`, so there is one
  implementation. It only reads: the model's only write path stays `tell_lia` plus your
  confirm in the app (D33, D36). The read verbs are listed in `mcp_server.MCP_READS`; a write
  exits 4.
- **Configuration:** the brain uses `BRAIN_DATABASE_URL`; the app uses `YGGDRESS_DATABASE_URL`.
  Neither is ever printed.

## Tests (one file per area; throwaway clusters only)

Every command needs:
- a success case;
- a not-found case;
- a permission case, where a restricted note is involved. A command that can never touch a
  note is covered by the leak test instead;
- for every writer, a stale-write case: an old `--version` exits 5, and the data is unchanged.

One **leak test** per area runs every read command of that area against fixtures that hold a
restricted note. It asserts the restricted slug, title and body never appear in stdout or
stderr. Brain fixtures: `app/tests/brain_pg.py` (where `ada-lin` is high). App fixtures:
`app/api/tests/postgres_fixture.py`. Also give the app side a note_ref with sensitivity
`restricted`.

Every command has `--help` (argparse). A test checks that `--help` exits 0 for each verb.
