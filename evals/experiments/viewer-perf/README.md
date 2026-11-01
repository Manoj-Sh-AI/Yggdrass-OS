# Viewer: performance check and screenshots (2026-10-31)

The brain-map viewer (`yggdras.data.graph.viewer`) is our own page on the vendored vis-network 9.1.6. These are its checks. Screenshots use the public-domain Apollo demo brain and a synthetic brain only, never the real one.

## Performance

`run.py` builds an invented library of N notes, each with two typed links and one mention, renders the viewer, and opens it in headless Edge with the network blocked. Run from `app/`:

```bash
uv run python ../evals/experiments/viewer-perf/run.py 3000
```

| Notes | Links | Page size | Layout time (page clock) | Browser run (wall) | Errors |
|---|---|---|---|---|---|
| 80 (real brain) | 171 | — | 0.5 s | — | none |
| 300 | 900 | 0.4 MB | 0.6 s | 6.3 s | none |
| 1,000 | 3,000 | 1.1 MB | 2.7 s | 15.4 s | none |
| 3,000 | 9,000 | 3.4 MB | 10.0–10.6 s | 13.0–13.9 s | none |

Timings vary with machine load. In one sitting (2026-10-31, after the restyle), the previous page took 11.6–14.0 s for 3,000 notes and the restyled page 10.0–10.6 s. An earlier, quieter run of the previous page measured 5.9–7.3 s.

- **Layout time** is the page's own measure, from script start to the end of layout. Headless Edge ran with a virtual time budget, so treat it as indicative.
- **Wall time** includes starting the browser.
- **Above 1,000 notes** the page skips vis-network's improved initial layout, caps layout at 120 iterations, turns off the overlap pass, draws straight rather than curved links, and hides edges while dragging or zooming.
- **Theme and style** are settled before the graph is created, so no link update restarts the layout.
- **First measurement:** the 3,000-note run took 10.9 s of layout before this tuning.
- **Not measured:** hover, drag and zoom smoothness. Headless runs can't measure them. The hover fade costs O(neighbours) per frame, and labels are culled to the viewport, with at most 450 drawn.

## Screenshots

Four graph styles, switchable in the sidebar (Style) or with `#style=classic|graphite|muted|clouds` in the address. **Classic is the default.**

- **Classic:** the look of the first demo viewer: near-black background, flat solid circles sized by links, 1px straight grey links, no labels at rest, a legend card top-left. Colour by type group (hubs orange, people blue, knowledge green, sources purple, chunks pink, doings teal, places muted yellow) or by life area (`#colour=area`).
- **Graphite:** brand colours (graphite, ivory), grey circles, one warm accent for focus, area colours only on hover, selection or area filter.
- **Muted areas:** circles in area colours, all at the same low saturation and lightness.
- **Area clouds:** Graphite plus a soft tinted region per area, labelled, with same-area notes gently pulled together.

| | Light | Dark |
|---|---|---|
| The first demo viewer (reference for Classic) | | `screenshots/apollo-old-demo-dark.png` |
| Classic | | `screenshots/apollo-classic-dark.png`, focused: `screenshots/apollo-classic-focus-dark.png` |
| Before (Graphify page; it ignores the system theme) | `screenshots/apollo-before-light.png` | `screenshots/apollo-before-dark.png` |
| Graphite | `screenshots/apollo-graphite-light.png` | `screenshots/apollo-graphite-dark.png` |
| Muted areas | `screenshots/apollo-muted-light.png` | `screenshots/apollo-muted-dark.png` |
| Area clouds | `screenshots/apollo-clouds-light.png` | `screenshots/apollo-clouds-dark.png` |
| 3,000 synthetic notes (Graphite) | | `screenshots/perf-3000.png` |

The Apollo brain uses the old D02 folders, so its "areas" are its folders (areas, people, sources, topics).

### Layouts

Three layouts, in the sidebar (Layout) or `#layout=force|radial|circlepack`; the choice is remembered and notes glide between layouts. "Show ring and area names" (`#ring=1`, off by default) draws a faint outline and names.

- **Force:** the force layout, as before (default).
- **Radial sectors:** Cross-area notes (the owner, the Ideas hub) in the middle; each colour group gets a slice of the disc sized by its note count (7% floor), with the most-linked groups side by side; each group's hub at 55% of the radius, more-linked notes inward.
- **Circlepack:** each colour group packed as its own circle, all inside one outer circle, Cross-area notes packed first so they sit near the middle.

| Layout | Dark, ring on |
|---|---|
| Force | `screenshots/apollo-layout-force-dark.png` |
| Radial sectors | `screenshots/apollo-layout-radial-dark.png` |
| Circlepack | `screenshots/apollo-layout-circlepack-dark.png` |

Tests check every note stays inside the disc and its own sector (radial, 10% allowed outside) or its own circle (circlepack).
