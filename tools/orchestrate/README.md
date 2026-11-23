# tools/orchestrate

Session orchestration (design: `planning/session-orchestration.md`, spec:
`requirements/spec-session-orchestration-phase-2.md`). Temporal holds the loop. Fable splits
the job; Opus 5.5 workers run as headless Agent SDK sessions, each in its own worktree with
its own scratch database. The orchestrator runs every check itself. Workers never push or merge.

## Run (from this folder, in your own terminal, not inside the Claude app)

Before anything else, set an API key on a Console workspace that has a spend limit (D6):

```powershell
$env:ANTHROPIC_API_KEY = "<key>"
```

1. `uv run orchestrate server`: the Temporal dev server on 127.0.0.1:7244, with its UI on
   http://127.0.0.1:8244. Run it in its own terminal and leave it running.
2. `uv run orchestrate probe`: the deny-rule probe. No worker starts without a pass.
3. `uv run orchestrate host`: the worker host, in its own terminal. Killing it simulates a
   crash.
4. `uv run orchestrate start p2 --tasks phase2-tasks.json --limits '{"max_parallel": 2}'`
5. `uv run orchestrate approve p2`, then `uv run orchestrate status p2`.
6. `uv run orchestrate answer p2 TASK "text"` or `uv run orchestrate skip p2 TASK` for a
   blocked worker.
7. `uv run orchestrate stop p2` stops everything. `--hard` terminates the workflow and kills
   every recorded process id.

Worktrees, run folders (`runs/<run>/`: briefs, results, check logs, report.json) and the
Temporal database live under `%LOCALAPPDATA%\yggdras`. Set `ORCH_ROOT` to change that. The
Claude desktop app redirects `%LOCALAPPDATA%` for processes it starts, so start the host from
a normal terminal.

## Tests (free: no model calls, no database)

```powershell
$env:ORCH_TEMPORAL_BINARY = "<repo>\app\api\runtime\temporal-tools\temporal.exe"
uv run pytest -q
```
