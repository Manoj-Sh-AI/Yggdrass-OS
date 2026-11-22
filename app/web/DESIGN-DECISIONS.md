# Design decisions (Yggdras UI rebuild)

Why each visual choice was made. Every value is tagged:
- **[cited]**: from a primary source named in the rebuild brief.
- **[proposal]**: no source; a starting point to tune.
- **[measured]**: measured in this repo; method stated.
- **[derived]**: computed from cited values; derivation stated.
- **[owner]**: decided by Manoj.

Values are never copied from Google, Notion, Obsidian or Bear assets (logos, wordmarks,
named palettes, icon sets). Layout conventions only.

The token file is `src/styles/tokens.css`; the primitives are `src/components/primitives`.

## Phase A: token layer (2026-11-21)

### Why a closed set
The audit (`STYLE-AUDIT.md`) found **908 distinct hex colours, 42 border-radius values
and 53 font sizes** across 15 hand-written CSS files: each screen invented its own.
The token layer resets Tailwind's palette, radii, shadows, type and weights
(`--color-*: initial` etc.), so `bg-blue-500` and `border-zinc-800` no longer compile
at all. The lint (`scripts/lint-tokens.mjs`) catches what the compiler can't:
raw hex and arbitrary values.

### Surfaces [cited, Anthropic MCP Apps tokens; names ours]
| Token | Value | Use |
|---|---|---|
| `--surface-0` | #141413 | app canvas [cited] |
| `--surface-1` | #262624 | panel / card [cited] |
| `--surface-2` | #30302E | raised, hover, active [cited] |
| `--surface-3` | #3A3A37 | overlay, popover, menu [proposal: continues the ladder] |
| `--surface-sunken` | surface-0 85% + black | wells [proposal] |

Anthropic's own names are inverted (background-primary is the lightest in dark mode); we
use an explicit 0-3 ladder. shadcn's names alias onto it: `background` → 0, `card` → 1,
`popover` → 3; `accent`, `secondary` and `muted` → surface-2, so no accent-tinted surface
exists anywhere.

### Ink, hairlines, ring, semantic [cited]
One ink at fixed alphas, never an opaque grey: text #FAF9F5 / #C2C0B6 / #9C9A92, disabled
= ink at 50%, hairlines #DEDCD1 at 15 / 30 / 40%, border width 0.5px, ring = ink at 70%.
Semantic surface/text pairs: info #253E5F / #80AADD, danger #602A28 / #EE8884, success
#1B4614 / #7AB948, warning #483A0F / #D1A041; semantic rings at 50%.

### Primary [owner, 2026-11-21]
`--primary` = ink #FAF9F5 with surface-0 text on it. Chosen over the logo navy #031C4A
(1.11:1 against the canvas, so a navy button nearly disappears) and info blue #80AADD
(would make "primary" and "info" the same hue). No new hue enters the palette.

### Measured contrast [measured, WCAG 2.x relative luminance]
| On | text-1 | text-2 | text-3 | disabled | hairline 15% |
|---|---:|---:|---:|---:|---:|
| surface-0 | 17.50 | 10.10 | 6.54 | 5.09 | 1.44 |
| surface-1 | 14.39 | 8.31 | 5.38 | 4.71 | 1.49 |
| surface-2 | 12.55 | 7.25 | 4.69 | 4.38 | 1.48 |
| surface-3 | 10.83 | 6.25 | **4.05** | 4.02 | 1.46 |

- **text-3 on surface-3 fails 4.5:1 (4.05).** Open question for Manoj. Until answered,
  text-3 is not used for readable text inside popovers or menus.
- Semantic text on its own surface: info 4.51, danger 4.57, success 4.58, warning 4.67
  (all pass, narrowly). Semantic text on the canvas: 7.45-7.78.
- Primary: surface-0 text on ink 17.50; ink fill against surface-2 12.55.
- Hairlines are decorative separators (1.4-1.5:1). Inputs use the 30% hairline.

### Radius, shadow, type, weight [cited]
Radii 4 / 6 / 8 / 10 / 12 / full. Shadows: exactly four, Tailwind's xs/sm/md/lg values.
**Decision:** the brief's "hairline" shadow is named `shadow-xs` (same value) so shadcn's
`shadow-xs` resolves untouched; there are still exactly four. Text 12 / 14 / 16 / 20,
headings add 24 / 28 / 36; line heights 1.4 (xs-base), 1.25 (lg, xl), 1.1 (2xl), 1 (3xl);
weights 400 / 500 / 600 / 700. Spacing inherits Tailwind v4's 0.25rem multiplier.
`--radius` (shadcn's base) is set to 10px = radius-lg, not a new value.

### Motion [cited Atlassian]
Durations 0 / 50 / 100 / 150 / 200 / 250 / 400 / 600ms in plain `:root` (no Tailwind
namespace exists); `--ease-practical: cubic-bezier(0.4, 1, 0.6, 1)`, also exposed as
`ease-practical`.

### The scrim [measured]
`scripts/measure-scrim.mjs`: for each of the 24 scene photos (1920px), find the
**lightest 48×48 px region** (about two lines of body text; mean linear luminance, every
4px), then raise a black scrim until each text token clears 4.5:1 against that region.

| Text on bare canvas | Night scenes need | All 24 scenes need |
|---|---:|---:|
| text-1 | 0.41 | 0.51 |
| text-2 | 0.60 | 0.66 |
| text-3 | 0.74 | 0.78 |

The lightest night region is the moon's reflection on the lake
(autumn-night-clear, x1244 y800, mean sRGB 189,195,200). The lightest region overall is
a sunrise sky (spring-sunrise-clear, x1160 y300).

**Landed on `--scrim: rgba(0,0,0,0.66)`**, not the brief's 0.5 (0.5 fails text-1 on six
day scenes and text-2 everywhere). 0.66 lets text-1 and text-2 sit directly on the canvas
on every scene, including day scenes the app shows automatically. **Rule:** text-3
never sits on the bare canvas, only on panels (5.16:1 on a 92% panel over the worst
scrimmed region). Night-only would be 0.60; text-1-only would be 0.51.

Method caveat: a uniform scrim against the single lightest region is a strict bound.
`background-size: cover` crops differently per viewport, but the lightest region is
inside the image, so the bound holds.

### Glass [cited unless marked]
`--panel-bg` surface-1 at 92% [derived]; `--panel-blur` 16px, `--panel-saturate` 180%
[cited]; `--panel-highlight` inset 1px white 8% [proposal]. Blur only inside
`@supports (backdrop-filter …)` AND `prefers-reduced-transparency: no-preference`; the
92% solid fallback carries the contrast. `-webkit-backdrop-filter` is hardcoded to
16px / 180% (custom properties do not resolve there); a test keeps the two in step.
Budget: at most 3-4 glass layers per viewport; never animate blur.

### Primitives
shadcn (new-york, v4.23.0) Button, Card, Input, Sheet, Dialog, Separator and Badge were
copied in with a hand-written `components.json` (no `shadcn init`, which would rewrite
the CSS with its own colours), then retokenised:
- Removed every `dark:` variant (the app is dark-only).
- `bg-black/50` overlays → `bg-scrim` (the measured scrim).
- `text-white` on destructive → surface-0 text (7.45:1).
- `ring-[3px]` → `ring-2`.
- Card loses its border and shadow (hierarchy by surface, not border).
- Dialog = surface-3 + shadow-lg + 0.5px edge (B1 popover rule).
- Sheet = surface-1 with a 0.5px edge.
- Borders use the `border-hairline` utilities (0.5px).
- `Surface`/`Panel` is new: levels 0-3 + sunken, `glass` (panels only) and `scrim`
  (canvas only). Elevation and glass live only here.
- Motion classes from shadcn (`animate-in`, `duration-300`…) are inert for now
  (tw-animate-css not installed). Sheet motion is specified in Phase E and will use
  the duration tokens.
- shadcn now ships its class helper as the `cn` package (`shadcn-ui/cn`), not a local
  `lib/utils.ts`.

### Legacy variables renamed
`--border`, `--accent` and `--radius` already existed in the legacy CSS and would have
overridden shadcn's names (the legacy `:root` comes later in the cascade). They are
renamed `--legacy-border` / `--legacy-accent` / `--legacy-radius` (81 uses, mechanical,
no visual change).

### Visible change to existing pages
The base layer paints `body` with `--surface-0` (#141413). Legacy CSS never set a body
background (only `html` = #09121c), so wherever no photo or panel covers the body,
the canvas changes from blue-black to warm near-black. That is the point of "every page
inherits the canvas", but it is visible before any page is rebuilt.

### Lint
`npm run lint:tokens` (and `prebuild`): raw hex, rgb()/hsl()/oklch(), arbitrary design
values (`bg-[#…]`, `p-[13px]`, `rounded-[7px]`, `text-[…]`, `shadow-[…]`, `duration-[…]`…;
`[var(--…)]` allowed), palette classes, and colours in inline styles. Ratchet: the
legacy counts in `scripts/lint-tokens-baseline.json` (1,145 values in 24 files) may only
fall. New violations warn locally and fail when `CI=1`.

## Phase B: chat (2026-11-22)

Built on the conductor (rationale/decisions/chat-conductor.md): one orchestrator per
conversation, streamed over assistant-ui's Assistant Transport.

### Surfaces (B1) [cited brief]
Conversation list `surface-1`, separated by colour alone (no border). Transcript is
transparent content on the canvas. Composer `surface-2` + `--panel-highlight` + a 0.5px
top edge. Popovers `surface-3` + `shadow-lg` + 0.5px (new `Popover` primitive). Plan card
`surface-1`, tool cards `surface-2`, code/JSON wells `surface-sunken`.

### Deleted (B2)
"Response connection configured" / "Messages saved here…" status line, every per-message
state line, the old empty-state copy, and the two full-width Agent/Model selects (the old
page component `components/chat.tsx` is no longer routed; kept for one-line rollback).

### Model choice (B2) [proposal]
A small text button in the composer's bottom-left opens a popover: Sonnet 5.5 (default,
owner decision), Opus 5.5, Fable 5.2, Haiku 5.5, each with a cost note. Remembered per
browser (localStorage). Haiku stays the router/verifier.

### Composer (B3-B6)
- One composer, one DOM position; the container is `grid-rows-[1fr_auto]` [cited pattern].
  A new conversation receiving its id mid-answer does not remount it.
- No product publishes composer pixels [said plainly]. Chosen [proposal]: `rows={1}`
  [cited], max-height `40vh`, input `text-base` (16px, avoids iOS zoom), padding
  `px-2 py-1.5`. assistant-ui's input is react-textarea-autosize (JS-measured height),
  so `field-sizing: content` is not needed and Firefox needs no fallback.
- Shrink hysteresis [cited, exact]: grow freely; shrink only when the value is empty
  (held as a minimum row count, `composer/logic.ts`).
- Bottom-anchored growth: the composer is the grid's bottom row, so its top edge rises;
  a ResizeObserver adds the growth to the transcript's scrollTop in the same frame.
- Send button, six states (`sendState`): idle = low-contrast glyph on surface-3 (never a
  grey "disabled" fill); ready = primary (ink) fill; blocked = inert + a line of copy
  (today: "You're offline. Your draft is kept."); sending/generating = Stop in the same
  slot (also cancels the run on the server); error = Retry + the error inline.
- "+" menu, not a bare paperclip [cited]; inline dismissible previews; the whole composer
  is a drop target (`AttachmentDropzone`, `data-dragging`). Images (PNG/JPEG/WebP/GIF,
  ≤5 MB, ≤4) go to the model; text files become text. PDFs are refused with a visible
  note: they need their own upload path [cited], not built yet.
- Keyboard: `submitMode` "enter" on fine pointers, "none" on coarse (Enter = newline,
  Send submits) [cited]; `cancelOnEscape` on. Shift+Enter hint on the first-run empty
  composer or first wrap, then remembered [proposal].

### Empty state (B7)
One line ("What should we work on?"), three starter pills that are real jobs here
(calendar week, plan Saturday around tasks, what notes say about goals), the composer.
Placeholder is a mode signal: "Ask Yggdras, or give it a job".

### Streaming (B8)
Streamdown **2.8.0** (not 1.5.0) with `@streamdown/code` 2.0.1, `math` 1.0.4, `mermaid`
1.0.4; `isAnimating` while streaming. Streamdown 2.8 ships a `caret` prop, so the caret is
the library's ("block"), not a hand-made pseudo-element (the brief's "no library exposes
it" is out of date). `@source` for its classes is in tokens.css [cited].

### Tool cards and the seven states (B9)
Badges exactly: Pending, Running, Awaiting Approval, Responded, Completed, Error, Denied.
**Contradiction in the brief, resolved:** its table marks output-available as
auto-opening, but its rule says "successes collapse, errors and approvals expand". The
rule wins: only `approval-requested` and `output-error` open by themselves.
Reasoning opens only when last message ∧ thread running ∧ last part is reasoning; the
app owns the "Thought for Ns" timer.

### Plan and the failed step (B10) [own design, undocumented anywhere]
One progress surface per turn: the Plan card when there is a plan (tool cards nest under
their step), otherwise the tool list. A step keeps the 3-value status; `verdict: failed`
shows a danger glyph and the reason; while another attempt comes it reads
"Retrying (n/3): reason"; after the last, "Gave up after 3 attempts: …"; a dependent
reads "Skipped: it needs step X, which failed." A step that already made a change is
never retried ("Not retried: this step already made a change"). Step titles follow
action + item + limits [cited].

### Approvals
Intent preview built from the real fields (operation, target id, data), with the
model's explanation labelled as its note; "This cannot be undone" on irreversible calls.

### Not done in Phase B (flagged)
- shadcn's AI Elements compositions were not copied in. They are written against AI-SDK
  message types; the parts here are built on our token primitives with the same
  anatomy instead (Plan/Task/Tool/Reasoning/Confirmation), Streamdown providing code
  blocks. Copying them later is mechanical if wanted.
- Sources/citations part: the conductor does not emit sources yet.
- The phone keeps the old chat path.
