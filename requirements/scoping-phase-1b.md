# Scoping: Phase 1b — Graphify map and link discovery

Answer in your own words. Go deep where a wrong guess is expensive (stored data, several reasonable designs, edge cases). Stay shallow on anything cheap to change later.

**This file is public.** Keep answers generic; anything personal goes in `yggdras-brain/private/`.

Source: `planning/locked-plan-v1.md`, "Revision 2026-10-25" and "Phase 1b", and register rows D5–D9.

## Already decided by the plan

| Choice | Decision | Where |
|---|---|---|
| Graph layer | Graphify code inside the Yggdras repo; no database | D5 |
| Storage | Derived `graph.json` plus a report in the gitignored `.graphify/` folder of the brain repo, rebuilt from the markdown at any time | D5, D6 |
| Direction | One-way, files to map; the map can always be dropped and rebuilt | D6 |
| Structural pass | Built from written `[[links]]` and frontmatter: no model, free, identical every run, rerun on every file change | D7, D8 |
| Discovery pass | A paid model proposes new links tagged inferred with a one-line reason; run manually; proposals accepted or rejected through the connector, and accepted ones become real links in the markdown | D7, D8 |
| Corpus | The Apollo demo brain (`yggdras-brain/demo-brain/`) | Revision 2026-10-25 |
| Exit test | A structural rebuild reproduces the map exactly; discovery recovers deleted links clearly above its own run-to-run noise; the eval scores no worse with the map than without it | Phase 1b |

## Open questions (in order)

1. **Verify Graphify first (step one of Phase 1b).** Before any design work, confirm against the actual project and its source:
   - that its open-source core is Apache 2.0, and what the licence-notice obligations are (keeping the notice, marking changed files);
   - how its structural and discovery passes actually work, and whether they match what the plan assumes;
   - what it exports (the format of `graph.json` and the report), and whether that fits a derived, rebuildable map.

   Anything that doesn't match the plan's assumptions is a finding to bring back, not a detail to work around.

<!-- Further open questions are added once question 1 is answered. -->

## 1. What kind of software is this?

<!-- Manoj. -->

## 2. Which tasks does it take on?

**In (breadth):**

<!-- Manoj. -->

**Out (for now):**

<!-- Manoj. -->

## 3. What is the expected result? (acceptance criteria)

<!-- Manoj. Context: the exit test in "Already decided" above. -->

## 4. Which processes run inside it?

<!-- Manoj. -->

## 5. How is each carried out, step by step?

<!-- Manoj. -->

## 6. When do exceptions apply, and what happens then?

<!-- Manoj. -->

---
Ready to build? Only if 3 and 6 are answered and open question 1 is resolved.
