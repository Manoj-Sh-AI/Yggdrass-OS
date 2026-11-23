# Nature glass surface hierarchy

2026-11-13, implementing Manoj's aesthetic request.

Use a final shared presentation layer rather than rewriting page components. This preserves working interactions and reduces regression risk, at the cost of a deliberate CSS override layer over the older page-specific styles. Tokens make the new material system consistent and reviewable.

Keep translucent navigation and containers, but give long-form text a stronger reading fill. Transparency provides atmosphere; contrast comes from the fill, not blur alone. Modest blur on top-level surfaces and no nested blur trade a little optical depth for lower GPU work and more stable reading. System/manual reduced transparency uses solid fills. No new landscape assets or decorative animation are required.

The graph receives presentation/accessibility messages through the existing authenticated frame bridge. No Brain renderer source or semantics are changed. Keep the system scenery engine and dark default; fresh nature should also feel calm at night.
