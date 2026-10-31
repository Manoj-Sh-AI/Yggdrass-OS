# Viewer: performance check and screenshots (2026-10-31)

The brain-map viewer (`yggdras.data.graph.viewer`) is our own page on the vendored vis-network 9.1.6. These are its checks. Screenshots use the public-domain Apollo demo brain and a synthetic brain only, never the real one.

## Performance

`run.py` builds an invented library of N notes, each with two typed links and one mention, renders the viewer, and opens it in headless Edge with the network blocked. Run from `app/`:

```bash
uv run python ../evals/experiments/viewer-perf/run.py 3000
```

| Notes | Links | Page size | Layout time (page clock) | Browser run (wall) | Errors |
|---|---|---|---|---|---|
| 80 (real brain) | 171 | — | 0.7 s | — | none |
| 300 | 900 | 0.4 MB | 0.7 s | 6.9 s | none |
| 1,000 | 3,000 | 1.1 MB | 1.8 s | 10.3 s | none |
| 3,000 | 9,000 | 3.4 MB | 5.9–7.3 s | 9.3 s | none |

- **Layout time** is the page's own measure, from script start to the end of layout. Headless Edge ran with a virtual time budget, so treat it as indicative.
- **Wall time** includes starting the browser.
- **Above 1,000 notes** the page skips vis-network's improved initial layout, caps layout at 120 iterations, turns off the overlap pass, and hides edges while dragging or zooming.
- **First measurement:** the 3,000-note run took 10.9 s of layout before this tuning.
- **Not measured:** hover, drag and zoom smoothness. Headless runs can't measure them. The hover fade costs O(neighbours) per frame, and labels are culled to the viewport, with at most 450 drawn.

## Screenshots

| | Light | Dark |
|---|---|---|
| Before (Graphify page; it ignores the system theme) | `screenshots/apollo-before-light.png` | `screenshots/apollo-before-dark.png` |
| After (our page) | `screenshots/apollo-after-light.png` | `screenshots/apollo-after-dark.png` |
| After, a note selected, link labels on | | `screenshots/apollo-after-select-dark.png` |
| 3,000 synthetic notes | | `screenshots/perf-3000.png` |

The Apollo brain uses the old D02 types and folders, so its colours follow its folders and every note is drawn as a circle or the default shape. The real brain uses one colour per area and one shape per type.
