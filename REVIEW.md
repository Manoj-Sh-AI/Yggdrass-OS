# Review guidance (read from the base branch only)

Review for correctness, not style. Report only real defects, ranked, with file:line, a
concrete failure scenario and a fix. Always check:
- Hard rules (AGENTS.md): brain only over its HTTP API; sensitive notes never in context;
  no secrets in code, logs or commits; nothing outward without approval.
- Migrations: new numbered file, expand-contract, no edits to committed migrations.
- Tests changed together with code; no new skip/xfail/.only; no weakened assertions.
- Tier 3 paths (merge by hand only): app/api/migrations/, the brain client
  (notes_proxy.py, brain.py), auth and sessions (application.py session, security.py),
  Temporal workflows (temporal_agent_*.py), .github/, .claude/, railway.json.
