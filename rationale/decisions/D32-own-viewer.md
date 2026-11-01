# D32 amendment: our own brain-map viewer

Date: 2026-10-31
Status: accepted (Manoj, 2026-10-31)

Register row: D32 in `planning/locked-plan-v1.md`. Related: D5 (our own structural map), D6 (derived, rebuildable), D13 (nothing cloud-queryable).

## Context

Since the 2026-10-31 morning amendment, Graphify's only job was drawing the brain map: we converted our map to Graphify's `graph.json`, ran `graphify export html`, then pointed its vis-network script at a local copy. With the first 80 real notes, the page was hard to read: hubs made a hairball, labels were tiny or overlapping, edges said "advances [EXTRACTED]", area colours repeated, and hovering showed nothing. Manoj asked for hover focus, a detail panel, plain-word links, readable labels, hub and type/verb filters, shapes per type, unique area colours, spring dragging with pinning, light/dark themes, and speed at thousands of notes.

## Options compared

**(a) A customisation layer injected after Graphify renders, without editing Graphify.** Graphify 0.9.95's page defines `nodesDS`, `edgesDS` and `network` as top-level constants and has fixed element IDs (`#search`, `#info-panel`, `#legend`). A later script could reach them.

- It saves little: Graphify's node data holds only a label, community and source file, so our description, aliases, summary, facts and types would be embedded anyway, and the panel, search, legend, hover and filters rewritten.
- It fights Graphify's own handlers: its click panel, tooltips, community legend and `[EXTRACTED]` titles all have to be switched off or overwritten.
- It is fragile on upgrades: it depends on three variable names, about six element IDs, the exact script tag and Graphify's data fields. A rename in any upgrade gives a blank or half-styled page with no error. D32 pins the version, so this bites only on a deliberate upgrade, but each upgrade needs a re-test.

**(b) Our own page on the same vis-network library, from `map.json` and the notes.** Full control, testable, no dependency on another tool's internals. Costs a template of about 600–900 lines.

## Decision

(b). Graphify renders nothing in Yggdras. It stays installed at the pinned version, unused by the product, and Experiment G (a one-time benchmark, optional) stays in the librarian plan.

## Consequences

- `yggdras.data.graph.viewer` builds the page from the structural map plus each note's frontmatter, summary, facts and link lines; `viewer_template.html` holds the page. The vendored vis-network keeps its pinned hash check.
- Notes with `sensitivity: high` show name, type and area; description, aliases, summary, facts and link lines stay behind a "Show" click. The data is still in the local, gitignored file.
- A Graphify upgrade no longer needs any viewer re-test.

## Amendment 2026-11-01: layouts, and porting the circle packing

The page offers three layouts (sidebar "Layout", or `#layout=force|radial|circlepack`): the force layout (default), radial sectors and circlepack. The idea comes from LightRAG's web UI, which offers Circular, Circlepack, Random, Noverlaps, Force Directed and Force Atlas on sigma.js and graphology. Circular is its default; the first three are graphology-layout functions computed at once, and the force ones run in a web worker.

**Ported, not vendored.** Circlepack uses d3-hierarchy's `packSiblings` and `packEnclose` (ISC), the same algorithm graphology-layout's `circlepack` (MIT) uses, ported into the template as about 120 lines. Vendoring graphology-layout would need graphology itself, `graphology-utils` and `pandemonium`, plus a bundling step. The viewer has no build step today and doesn't use a graphology graph. The result is the same circles; the port is covered by tests (every note inside its own circle and the outer one).

Radial sectors is our own: sectors sized by note count with a 7% floor, ordered so the most-linked groups are neighbours, the area hub at 55% of the radius, more-linked notes inward, and a short relax that keeps link springs but holds each note in its sector and the disc.
