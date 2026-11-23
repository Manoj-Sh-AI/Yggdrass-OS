# Authorized Notes enhancement — BlockNote

Source: user's implementation authorization, 2026-11-08. This scoped specification records that request; existing architecture and roadmap remain unchanged.

Enhance the existing authenticated `/notes` page and note drawer using official MPL-2.0 BlockNote core/React/UI packages, reusing native menus, formatting, block manipulation, shortcuts and history. No XL, paid features, second editor engine, real Brain connection, memory-code/test changes or deployment.

Acceptance: desktop navigation/editor/context panels; collapsible keyboard-accessible synthetic shelves and note navigation; title/content search with highlights; create/edit/read/switch/delete; dark responsive editor with built-in formatting, lists/checklists, headings, code, quotes, divider and basic tables. Preserve delete preview/confirmation and opaque mock version checks. Show source and accurate save/failure/conflict states.

Use a separate, versioned structured-document serializer so rich block information is preserved. Markdown export must warn about lossy styles/blocks; JSON remains lossless. Retain the existing mock Brain adapter boundary. Isolate browser-local development drafts, clearly label their scope/limitations, debounce saves and transformations, flush before note switching and recover interrupted edits on refresh. No application SQL note tables or new Brain behavior.

Verify editor formatting/slash menus/blocks/reordering/undo/redo, navigation/search/empty and long notes, serialization, autosave/recovery/failures/conflicts, explicit deletion, mobile/keyboard behavior and Phase 1 regression checks. Inspect exact installed licenses, preserve notices, and record delivery/limitations without rewriting architecture documents.
