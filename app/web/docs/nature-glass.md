# Nature glass presentation

The visual direction is alpine mist, fir, sage and clear water. Existing landscapes remain time/weather/season aware; they are more visible between surfaces. The interface remains dark, with stronger reading layers for notes and dense planning content. No memory-engine, data connection, schema or application workflow was replaced.

`src/app/nature-glass.css` is the shared final presentation layer. It defines fills, highlights, shadows, focus colour, readable foregrounds and control surfaces. Existing page layouts and semantic area colours are preserved. The generic graph adapter receives the same palette and accessibility preferences; its original data and renderer remain unchanged.

| Material | Choice |
| --- | --- |
| Default glass | Fir fill at 86%, modest highlight and soft rim |
| Blur | 14px maximum on primary glass, 8px on mobile; no nested panel blur |
| Reading surface | Strong evergreen fill for the notebook |
| Primary action | Pale sage/mint with dark text |
| Focus | Distinct light-green outline, independent of colour-only status |
| Reduced transparency | Solid surfaces, zero blur, saved in existing browser preferences |

System reduced transparency is respected where supported. The manual Settings control also works when that media query is unavailable. Reduced motion and forced colours have dedicated fallbacks; the graph receives manual accessibility changes through its existing frame bridge. There is no new decorative animation or parallax.

Contrast tests calculate foregrounds over both dark and white backdrops, including the brightest glass highlight. This verifies the shared palette, not a claim of a complete WCAG certification or assistive-technology audit. Browser tests cover preference persistence, graph propagation, system reduction, keyboard focus, forced colours and responsive pages.

The local preview helper can retain the existing password through private `YGGDRESS_PREVIEW_PASSWORD`; that value is removed from the frontend child environment. Normal application authentication is unchanged. Current preview records and sign-in were preserved before refresh.

References: [Axess Lab article](https://axesslab.com/glassmorphism-meets-accessibility-can-frosted-glass-be-inclusive/), [WCAG text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), [WCAG non-text contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html), [MDN reduced transparency](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-transparency).

Verification results are recorded in `planning/nature-glass.md`. Screenshots remain in ignored runtime storage.
