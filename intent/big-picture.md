# The Big Picture

The motivation behind Yggdras. Read this first, every time. When a decision trades one thing against another, favour the principles here. When the principles don't settle it, ask Manoj. This file is the why; the specs and the code are the how. Don't lose sight of the why.

## Why Yggdras exists

Yggdras is not a note app. It is a second brain whose job is to help Manoj make better decisions and handle whatever life throws at him — by connecting things he already knows into possibilities he hasn't seen yet.

The emblem of the whole project is a small true story. A friend wanted to get fit and mentioned swimming. Manoj offered to send a list of nearby pools. Then something connected: if there are pools, and my friend swims, maybe he can teach me — for free. He asked. The friend said yes. A new skill, at no cost, purely because his mind linked three things he already knew.

That jump — from what you know to what you could do — is the entire point. Yggdras should make those jumps on purpose, all the time.

The bet behind it: connected knowledge compounds. A brain that keeps finding links between what it already holds gives its owner an advantage that grows over a lifetime. That is the leverage we are building.

## The one line

**Yggdras turns what Manoj knows into possibilities he can act on — reliably, cheaply, and privately.**

Every rung of the system serves that sentence. If a feature doesn't, it's a distraction.

## The ladder: from the smallest node to managing situations

Yggdras is built as a climb. Each rung rests on the one below. Never build a higher rung on an unproven lower one.

1. **A fact** — one true statement on one line, with its source. The atom. (e.g. "Jack Swigert replaced Ken Mattingly on 1970-04-10.")
2. **A node** — one markdown file about one thing: a person, an area, a topic, a source. Frontmatter (name, aliases, one-line description, type), fact lines, and links.
3. **A link** — a connection between two nodes, with a reason ("replaced by", "flew on"). Links are the knowledge. The hand-written ones are the real graph.
4. **The map** — the whole graph of nodes and links, built by free deterministic code from the links in the files. Cheap, exact, rebuildable in seconds.
5. **Answering** — ask the brain a question, get a true answer with its sources. This rung is built and proven (meaning-based pick → gather facts + neighbours → one cited answer). It is the foundation everything else stands on, so it has to be as close to never-wrong as we can measure.
6. **Discovery** — the brain finds connections Manoj hasn't written yet, and surfaces the significant ones as a question: "your hardware note and your neural-network note both point at your thesis — interesting?" The obvious links form silently underneath; only the significant, non-obvious ones come up for approval. Not built yet. This is the next leap.
7. **Frameworks** — reusable patterns for kinds of situations, ingested once and fetched when a matching situation arises. Case-based reasoning: store the shape of a problem and its options, recall it when life repeats the shape. Not built yet.
8. **Managing situations** — the summit. From a little context (the time, and what Manoj is doing) the brain proactively offers the right possibility at the right moment: "leaving the office at 6pm — want to stop at the supermarket? the nearest is 400 m away." Not built yet; designed as a parallel experiment once discovery begins.

The climb is the roadmap. Answering is solid. Everything above it is the work ahead.

## What makes a connection "significant"

Below a threshold, connections are obvious — small, necessary, expected. These are linked automatically and silently, by free code, never by a paid model.

Above the threshold, a connection is significant: non-obvious, and worth Manoj's attention. Significance blends three signals:

- **Distance** — the two notes live in different areas of life that don't usually meet (studies ↔ work ↔ a hobby).
- **Possibility** — the connection could open many new links or options later.
- **Action** — it implies something Manoj could actually do, like the swimming lesson.

Compute the cheap signals (distance, possibility) from the graph first, as a filter. Let the model judge action only on the short list that survives. The obvious ones link silently; the few that clear the bar arrive as a question Manoj approves or waves away. A wrong suggestion costs one word to reject — so here, unlike in answering, a fuzzy guess is acceptable.

This idea has a lineage: literature-based discovery (Don Swanson's work in the 1980s, which surfaced the fish-oil / Raynaud's link by joining two bodies of knowledge nobody had connected). We are building a personal version of it.

## The principles that protect the vision

These are non-negotiable. They are how the climb stays honest.

1. **Markdown is the source of truth.** Graphs, indexes, embeddings — all derived, all droppable, all rebuildable from the files. Never let a derived store become the thing you can't lose.
2. **Factual consistency comes first.** The answering rung must be as near never-wrong as we can measure — proven on a hard, held-out eval, not an easy one. Six-nines reliability is the aim; it must be earned with an eval big and mean enough to detect it, never merely claimed.
3. **Obvious is free; significant is paid.** Never spend a model call on what deterministic code can do. The model only ever looks at the few things that matter.
4. **Nothing enters the brain without approval.** New facts, new links, new frameworks — Manoj approves. The brain proposes; the human disposes.
5. **Private by default.** No cloud-queryable store of the brain. No personal data in the public code repo. Local first.
6. **Measure, don't guess.** Pre-register evals before running them. Never rewrite a question or tune a system after seeing it fail. A cheaper, simpler baseline must always be beaten before a fancier one is adopted.
7. **One tool, one job.** A tool earns its place only by beating a free baseline at a real job. (We proved Graphify is a locator and a code-mapper — not an answerer, and not a typed-link maker — so it does not sit in the answer path.)

## Where we are, so no one confuses the dream with the done

- **Built and proven:** the node format (frozen), the free map, and the answering pipeline (35/35 on the current eval — but that eval is easy, so this is a ceiling, not a guarantee).
- **In progress:** experiments comparing our pipeline against harder questions, link-proposal methods, and Graphify's real roles.
- **Not built:** discovery, frameworks, the proactive layer, embeddings.

The sequence from here:

1. Finish the running experiments (the hard-question test is the key one).
2. Build a hard eval that defines "rock-solid" — the gate.
3. Build a small local embedding index — the shared floor for both better answering and discovery.
4. Build the discovery engine on top, with the proactive loop as a parallel experiment.

**Discovery does not begin until answering passes a genuinely hard eval. That is the rule.**

## What Yggdras is not

- Not a chatbot that answers from the model's own memory — it answers only from Manoj's notes, with sources.
- Not a cloud service.
- Not a general RAG-for-everything — it is a hand-tended brain where human-written links are the backbone.
- Not dependent on any one framework. Tools are swappable; the markdown is forever.
- Not a system that acts without approval.
- Not optimised for a flashy demo over quiet, provable consistency.

## The why, once more

Every hour spent here is spent so that one day, in an ordinary moment, Yggdras makes a connection Manoj wouldn't have made alone — and a possibility opens that wouldn't have otherwise. Build toward that. Don't lose sight of it.

For the binding technical decisions behind these principles, see the decision register (D1 markdown as source of truth, D6 one-way derived graph, D13 no cloud-queryable store, D23 no personal data in the public repo, D30 evals out of the answering agent's reach, D31 frozen node format, D32 Graphify's pinned role). This file is the motivation; the register is the law.
