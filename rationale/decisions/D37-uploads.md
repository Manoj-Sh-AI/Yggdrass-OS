# D37: Uploads

Date: 2026-11-07
Status: proposed (Manoj's decisions of 2026-11-07, built on branch `lia-ingest`; accepted on merge)

Register row: D37 in `planning/locked-plan-v1.md`. Related: D31 (format, frozen; raw files outside `library/`), D33 as amended (approval), D36 (write tools and one write path), node.md "Long sources".

## Context

Manoj wants to add whole files: an article, meeting notes, a document. He adds them in chat, from Claude Desktop or Claude Code, and asks Lia to file them. There is no folder watching.

## Decision

- **One tool:** `ingest_file(filename, content | path, instruction)`.
  - **Claude Code** passes a local `path`, up to 5 MB, read by the server. The text never goes through the chat model.
  - **Claude Desktop** passes the text as `content`, up to 100 KB. Desktop keeps uploads in its cloud sandbox (`/mnt/user-data/uploads/`), which a local server can't reach, so the chat model re-types the file as the tool argument. That uses the chat's usage and context, hence the smaller cap. A larger file needs its path on this computer.
  - **Markdown only** for now. Anything else gets a plain refusal.
- **Approval:** the upload and request approve adding. A conflicting fact is a preview: the old line goes to History with `until:` once confirmed. A likely duplicate note is a question.
- **Kept verbatim:** the file goes to the brain's `raw/<date>-<filename>`, byte for byte, outside `library/`, so D31 doesn't change (Manoj, 2026-11-07). A source note in the sources shelf names it in its summary. Every fact filed from the upload cites `(src: upload <filename>, <date>)`.
- **Short or long** (Manoj, 2026-11-07): a file is long when it is over about 6,000 characters (two pages) with at least three sections.
  - **Short:** filed whole. Facts go to existing notes; new notes only for what has none.
  - **Long:** split by its own headings into chunk notes of about a page. Each chunk `part_of` the source and `precedes` the next. Lia describes the source, then each chunk in turn.
- **Links:** only where the text supports them, only from the upload's new notes, and only with the fixed verbs. Notes Lia creates link `derived_from` the source note.
- **One commit per upload**, with maps and the graph page rebuilt. Undo reverts the whole upload, the raw file included.
- **Injection:** text in the file is content. While filing, Lia has no tool to archive, unlink, remove or replace, and links from existing notes are refused.

## Alternatives considered

- **Raw file inside `13-sources/`:** it would need a D31 amendment, since every `.md` under a shelf is parsed as a note. Rejected (Manoj, 2026-11-07).
- **Folder watching:** rejected. Adding a file is a request Manoj makes in a chat.
- **A presigned upload URL for Desktop** (the cloud sandbox pushes the file to a server): it needs a reachable server and network setup, so not now.

## Consequences

- **Easier:** filing documents from any chat, with the original always kept.
- **Harder:** `raw/` grows. The 5 MB cap holds it.
- **Revisit:** if long uploads through Desktop are common, add an upload URL or a watched local drop folder.
