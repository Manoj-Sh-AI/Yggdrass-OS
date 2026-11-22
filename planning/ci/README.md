# CI drafts (owner installs)

Agent sessions cannot edit `.github/**` (the protect-paths gate, item 13, blocked this
on 2026-11-22: that is the boundary working). These drafts are reviewed and YAML-valid;
install them yourself:

    cp planning/ci/workflows/*.yml .github/workflows/ && git rm .github/workflows/ci.yml

- `pr.yml`: changes filter, per-stack jobs (adds the app/api suite on a Postgres service;
  the old ci.yml only ran `app/`), `ci-gate` aggregator, per-PR cancelling concurrency.
- `ci-integrity.yml`: label-gated CI/test-config changes (`ci-change-approved`), blocks
  `|| true`/`continue-on-error`, new skip/xfail/.only, net test deletion > 50 lines;
  warns on code-without-tests and tests-only; lockfile discipline; diff-only gitleaks.
- `main.yml`: non-cancellable run on push to main + a 30-minute deploy watchdog (set the
  repository variable `PRODUCTION_HEALTH_URL`, e.g. https://<backend>/health).

Server-side, done by the agent via the GitHub API (2026-11-22):
- Ruleset 27852848 on `main`: PR required, squash only, linear history, strict `ci-gate`,
  no force-push/deletion, bypass = repository admin. Until `pr.yml` is installed nothing
  can merge to main (no `ci-gate` result exists yet).
- Push (file-path) ruleset: refused by GitHub ("only org-owned repos can have push
  rules"; public user repos cannot). Compensating controls: the local protect-paths
  hook and the ci-integrity label rule.

Owner-only (no API from here): Railway "Wait for CI" and healthcheck path `/health`
(railway.json is a protected path), production branch (today `codex/android-completion`,
not `main`), rollback rehearsal, backup restore, Console spend limit.
