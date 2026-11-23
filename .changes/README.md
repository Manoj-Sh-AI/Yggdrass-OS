# Changes, one file per change

Two agents on two branches never edit the same changelog line, so there is no
`CHANGELOG.md` to collide on (planning/agentic-engineering.md item 55). Each change adds
`.changes/unreleased/<YYYYMMDD>-<slug>.md`:

    ---
    kind: added | changed | fixed | removed | security
    area: api | web | mobile | desktop | tooling
    ---
    One or two plain sentences a user would understand.

At release the files are concatenated into the release notes and moved to
`.changes/<version>/`. The name is date + slug, never a number.
