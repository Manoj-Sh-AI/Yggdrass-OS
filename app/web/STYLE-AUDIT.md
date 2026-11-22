# Style audit (Phase A1), 2026-11-21, branch ui-rebuild

Scope: `app/web/src` (.css, .tsx, .ts). Regenerate: see the grep patterns below.

| Pattern | Matches | Files |
|---|---:|---:|
| `bg-[#` | 0 | 0 |
| `p-[ / m-[ / gap-[` | 0 | 0 |
| `rounded-[` | 0 | 0 |
| `text-[` | 0 | 0 |
| `shadow-[` | 0 | 0 |
| `raw hex (all)` | 1086 | 22 |
| `rgb()/rgba()/hsl()` | 56 | 14 |
| `inline style={{}}` | 23 | 12 |
| `inline style with colour` | 9 | 6 |
| `-gray-N` | 0 | 0 |
| `-blue-N` | 0 | 0 |
| `-zinc-N` | 0 | 0 |
| `bg-blue` | 0 | 0 |
| `border-radius: Npx` | 180 | 14 |
| `box-shadow:` | 102 | 13 |
| `font-size: Npx` | 577 | 13 |
| `backdrop-filter` | 58 | 7 |

## Raw hex by file

| File | Hex | border-radius px | font-size px | box-shadow |
|---|---:|---:|---:|---:|
| `src/app/calendar-workspace.css` | 73 | 10 | 31 | 14 |
| `src/app/calls.css` | 18 | 1 | 4 | 4 |
| `src/app/catalog.css` | 21 | 9 | 16 | 2 |
| `src/app/chat.css` | 26 | 15 | 38 | 3 |
| `src/app/globals.css` | 341 | 53 | 280 | 25 |
| `src/app/graph.css` | 27 | 3 | 23 | 2 |
| `src/app/interface-feel.css` | 2 | 1 | 0 | 0 |
| `src/app/kanban.css` | 41 | 13 | 31 | 4 |
| `src/app/nature-glass.css` | 159 | 21 | 1 | 20 |
| `src/app/notes.css` | 76 | 12 | 47 | 3 |
| `src/app/open-air.css` | 124 | 9 | 16 | 20 |
| `src/app/planning.css` | 108 | 18 | 62 | 2 |
| `src/app/signal-workspace.css` | 5 | 3 | 22 | 2 |
| `src/app/yggdras.css` | 33 | 12 | 0 | 1 |
| `src/components/area.tsx` | 4 | 0 | 0 | 0 |
| `src/components/dashboard.tsx` | 4 | 0 | 0 | 0 |
| `src/components/planning-daily.tsx` | 2 | 0 | 0 | 0 |
| `src/components/planning-ui.tsx` | 2 | 0 | 0 | 0 |
| `src/components/routine-execution-card.tsx` | 4 | 0 | 0 | 0 |
| `src/components/today.tsx` | 4 | 0 | 0 | 0 |
| `src/lib/data.ts` | 8 | 0 | 0 | 0 |
| `src/lib/kanban.ts` | 4 | 0 | 0 | 0 |

## Distinct values in use

- distinct hex colours: 908
- distinct border-radius values: 42
- distinct font-size values: 53
- inline style={{}} sites: src/components/area.tsx src/components/calendar.tsx src/components/catalogs.tsx src/components/dashboard.tsx src/components/notes.tsx src/components/notes-brain-provider.tsx src/components/scenery.tsx src/components/settings.tsx src/components/task-board.tsx src/components/today.tsx src/components/ui.tsx src/components/work-graph.tsx 
