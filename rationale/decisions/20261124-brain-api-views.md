# Brain api.* views (N1): the sensitivity rule for brain reads lives in SQL

Date: 2026-11-24
Status: accepted (Manoj approved N1, 2026-11-24)

## Context

The CLI's brain reads must go through `api.*` views (planning/cli-inventory.md, fact 1). The
brain HTTP API returns `sensitivity: high` notes unfiltered (fact 2), and Manoj ruled out
filtering in Python.

## Decision

Brain migration 0005 adds `api.brain_areas`, `api.brain_notes` (the tree and the version
token), `api.brain_note_bodies`, `api.brain_note_areas`, `api.brain_links` and
`api.brain_search`, and the function `api.brain_note_access(slug)`.

- **The rule** is the same one `migrate_hosted.backfill_sensitivity` uses: `high` (any
  case) is restricted, everything else is normal. Archived notes never show.
- **The tree** shows a restricted note as a masked row: no slug, title, type, version or
  parent, only its area. Every other view leaves it out completely.
- **Text that names it** is masked: inside a normal note's body, `[[slug]]`, `[[slug|label]]`
  and `[[slug#part]]` become `[[sensitive-note]]`, and search runs over the masked text.
- **A child never names a restricted parent.**
- **Not allowed versus not found:** `api.brain_note_access(slug)` returns `normal`,
  `restricted` or NULL, for one exact slug only.

## Alternatives considered

- Leave restricted notes out of the tree too. That is simpler, but shelf counts would be
  wrong, and the step 2 pattern masks rather than drops in `api.note_refs`.
- Keep a separate visibility rule that is stricter than "high", so unknown values are hidden
  too. It is safer, but it disagrees with the app-side backfill, and a note would be visible
  on one side and hidden on the other.

## Tradeoffs

- **Masking is only as good as the link syntax.** A restricted person's name written as a
  plain word in another note is not found. This is a known limit, tested and documented.
- **Cost:** `masked_body` loops over the restricted notes for each body it returns. That is
  fine for a personal brain, and is worth measuring if the brain grows large.
- **Existence:** `brain_note_access` reveals that an exact slug exists. It reveals nothing
  else.

## Consequences

The brain read commands can read only these views. The agents-only database role (N4) is
still what would make that impossible to bypass. Until then it is a rule in the code, tested
by `app/tests/test_brain_api_views.py`.
