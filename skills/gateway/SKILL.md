# Gateway skill: navigating the brain

You answer questions from a brain: a folder of markdown nodes with an `index.md` at its root. You are told the brain's root path. Everything you say must come from nodes you opened. Follow these steps in order.

## 1. Read `index.md` first, and only it

Open `<brain>/index.md` before any other file. It has one row per node: `slug`, `type`, `aliases`, `id`, `description`. Do not list, glob or search the brain's folders: the index is the map.

## 2. Pick candidates from the index

Choose the rows whose description or aliases fit the question. Match names loosely: lowercase, ignore accents, treat spaces, underscores and hyphens alike (`Inés Navarro`, `ines navarro` and `ines-navarro` are the same name).

If no row plausibly fits, stop and go to step 6. Do not open a node just to see what is in it.

## 3. Open nodes by path

The path follows from the row:

| type | path |
|---|---|
| `person` | `people/<slug>.md` |
| `area` | `areas/<slug>.md` |
| `topic` | `topics/<slug>.md` |
| `source` | `sources/<slug>.md` |
| `chunk` | `sources/<source-slug>/<slug>.md`; the slug is `<source-slug>-ch-<nn>` |

Open the best candidate first. Open more only when the question needs it. Aim for five files or fewer, `index.md` included.

## 4. Follow links for multi-step questions

A node's `## Links` lines name related nodes as `[[slug]]`, with the relation in words. When the answer needs a second subject ("who employs the supervisor of X"), follow the link: find its row in `index.md`, then open it by path. A link to a slug with no index row means the brain has nothing on it.

## 5. Page questions go through the chunk

For a question about a section, chapter or page of a source, open the chunk, not just the source. The chunk's `pages` field gives its page range, and its facts cite pages as `(src: <source> p.<n>, <date>)`. Quote both in the answer.

Within an opened file you may search for the exact passage. Never search across files.

## 6. Answer only from what you opened

Each fact line reads `- [tag] <fact> (src: <source>, <date>)`. The **last** bracketed group is always the source.

- Answer from fact lines only. Never add knowledge of your own, and never infer beyond what a fact says.
- `[stated]` and `[observed]` facts you may give as facts. A `[derived]` fact is an agent's inference: say so ("an agent concluded that…").
- A changed fact reads `<new> (was <old>, changed <date>[ by <change source>])`. When asked about history, give the current value, the old value, the change date and, if named, what changed it. The final bracketed group is still the original source, such as a page; cite it for the fact.
- If the opened nodes do not contain the answer, say **"I don't have that"**, and say what you checked. Do not stretch a related fact into an answer. Do not answer partly from general knowledge. A confident wrong answer is the worst outcome.

## 7. Report what you opened

End every answer with the files you opened, in order, as paths relative to the brain root.
