# Mobile follows the open-air look

Date: 2026-11-18. Owner choice: "JS-only match".

The Android app had its own flat green theme. Web and desktop use the open-air
material (`web/src/app/open-air.css`): a seasonal nature photo behind smoked-glass
panels, cream primary buttons, light headings. The phone now uses the same tokens
(`app/mobile/src/ui.tsx`) and the same 24 scene photos.

Choices:

- **Bundled 960px scenes** (~2.3 MB) in `app/mobile/assets/scenes`, copied from
  `web/public/scenes`. The 480px set looked soft on a phone; 1920px adds ~10 MB for
  no visible gain. The backdrop then works offline and before sign-in.
- **Clock-only scene choice** (season from month, phase 06:00/09:00/18:00, sky
  always clear), mirroring the web's fallback. The phone has no weather feed or
  place preference yet, so it assumes the northern hemisphere.
- **No native additions**: no blur, no Inter font, no icon set. Each needs a new
  native module. The glass fill is 84% opaque, so blur would barely show; the
  system font and text tabs are the accepted gap.

Tradeoff: the app grows by ~2.3 MB, and the two sets of scene files must be kept in
step by hand if the web scenes change.
