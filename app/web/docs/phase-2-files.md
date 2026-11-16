# Phase 2 file inventory

Paths are relative to the repository root. “New” refers to this milestone; existing Phase 1/Notes work may still be untracked in the working tree.

## New

```text
requirements/spec-phase-2-planning.md
planning/phase-2-planning.md
rationale/decisions/D42-phase-2-shared-planning.md
app/api/migrations/002_planning.sql
app/api/src/yggdress_app/planning.py
app/api/src/yggdress_app/planning_models.py
app/api/tests/test_planning.py
app/web/src/lib/planning.ts
app/web/src/lib/planning-accessibility.ts
app/web/src/components/planning-provider.tsx
app/web/src/components/planning-ui.tsx
app/web/src/components/planning-daily.tsx
app/web/src/components/planning-routines.tsx
app/web/src/components/tasks.tsx
app/web/src/app/(workspace)/tasks/page.tsx
app/web/src/app/planning.css
app/web/tests/planning.test.ts
app/web/e2e/phase2.spec.ts
app/web/docs/phase-2-planning.md
app/web/docs/phase-2-files.md
```

## Modified

```text
app/api/src/yggdress_app/application.py
app/api/src/yggdress_app/database.py
app/api/tests/conftest.py
app/api/tests/postgres_fixture.py
app/api/tests/test_application.py
app/api/scripts/local_preview.py
app/api/README.md
app/web/src/lib/types.ts
app/web/src/components/application-provider.tsx
app/web/src/components/calendar.tsx
app/web/src/components/routine-execution-card.tsx
app/web/src/components/shell.tsx
app/web/src/components/today.tsx
app/web/src/components/ui.tsx
app/web/src/components/workspace-gate.tsx
app/web/src/app/api/backend/[...path]/route.ts
app/web/src/app/layout.tsx
app/web/e2e/phase1.spec.ts
app/web/playwright.config.ts
app/web/scripts/local-preview.mjs
app/web/README.md
```

No package/dependency changes, existing migration 001 changes, Brain source/test changes, Notes editor or Brain-adapter changes. No commit or deployment was performed. Ignored verification screenshots and a private temporary-preview application backup are local artifacts, not repository deliverables.
