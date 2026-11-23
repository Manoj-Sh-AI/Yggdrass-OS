# Focused Today material study

1. Interpret the new image as neutral optical material and spatial hierarchy, rather than another brand colour.
2. Research Apple/Fluent guidance. Separate navigation/control material from reading content and avoid stacking glass layers everywhere.
3. Build an isolated synthetic Today composition: one floating workspace, restrained sidebar/header, spacious greeting, line-based agenda, a quieter focus/insight rail and unobtrusive capture.
4. Render at 1344 × 896 and a phone width, inspect the result, and present the actual prototype for feedback before touching the website-wide theme again.

This study can be served read-only from `app/web/public` on a separate loopback port. It contains no real notes, credentials or application database connection. The existing site is left running.

References:
- https://developer.apple.com/videos/play/wwdc2025/219/
- https://fluent2.microsoft.design/material
- User-supplied smoked-glass image, 2026-11-13.

Verification, 2026-11-13: rendered and inspected at 1344 × 896 and 390 × 844, with dawn/night previews. Browser interaction checks passed for scene switching, agenda search, local capture, routine progress/completion, and reduced transparency. No horizontal page overflow or page script errors were observed. These checks cover the isolated synthetic study only, not the production application's integrations. Preview: http://127.0.0.1:3002/design-studies/smoked-glass/.
