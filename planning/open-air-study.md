# Open-air Today study

Application screen; local synthetic design study, not a marketing site or production rollout.

## User direction

Keep the reviewed neutral smoked-glass material, restore useful Today information, and make entering Yggdress feel like entering a personal place in nature. More visual character and practical substance, without the rejected all-green treatment. Preserve study 01 for comparison. No Brain/API/data changes.

## Research and interpretation

Read the original Taste Skill's current frontend guidance and its classic dashboard guidance. The current version primarily targets company/marketing websites; its full-screen sales sections, random palettes and animation requirements do not fit this application. Borrow intentional composition, consistent edges, explicit typography hierarchy, restrained accents, material edge highlights, everyday-app density, interaction states, and real-browser visual checks. Do not install its tooling or hooks, replace the application stack, or claim its automated gate was run. Keep the existing licensed local font instead of adding a dependency merely to follow a font ban.

- Current Taste Skill: https://github.com/Leonxlnx/taste-skill/blob/main/skills/taste-skill/SKILL.md
- Classic dashboard guidance: https://github.com/Leonxlnx/taste-skill-classics/blob/main/skills/taste-skill-v1/SKILL.md
- Weiser and Brown, The Coming Age of Calm Technology: https://calmtech.com/papers/coming-age-calm-technology
- User's accessibility reference: https://axesslab.com/glassmorphism-meets-accessibility-can-frosted-glass-be-inclusive/
- Material research retained from study 01: Apple Meet Liquid Glass and Fluent 2 material.

Calm technology is used as a design principle: day context at the periphery, the next useful action at the center, and user control over what demands attention. This is a visual/interaction intention, not a medical claim or proof of a calming effect.

## Composition and dependencies

1. Existing generated alpine scene assets, loaded one selected scene at a time with a responsive source; no new asset library or third-party font request.
2. Narrow floating navigation and header controls in neutral smoked material. Landscape remains visible across the upper workspace.
3. Greeting plus a restrained summary, then one coherent reading desk. Agenda, next routine and focus form its first row; recent notes, weekly goals and activity form its second. Dividers group content without six competing glass layers.
4. Persistent capture action, searchable synthetic notes and a native-dialog note preview. Synthetic state lives under a separate study-only localStorage key.
5. On-request landscape view clears the interface; always provide keyboard dismissal and a visible return action. No mandatory entrance pause or continuous parallax.
6. Reduced transparency/motion and forced-colour fallbacks, minimum legible type, keyboard focus and small-screen stacking.

Design targets: moderate asymmetry (5/10), everyday information density (5/10), quiet motion (2/10). These are implementation choices for review, not new application requirements.

Verification: desktop 1344 × 896, tablet 820 × 1180, phone 390 × 844 and narrow 320 px. Check capture/search/reload, routine progress, task completion, scene selection, dialog focus, reduced preferences, asset failures and overflow. Do not run live Brain writes.

## Verified refinement 02b

The browser check in `app/web/scripts/check-open-air.cjs` passed at all four target widths. It covers capture → search → open → reload, safe literal text rendering, task/routine persistence with an unchanged goal, empty search, missing-scene fallback, manual transparency, system reduced motion, dialog Escape/focus restoration and preserving a capture draft when storage fails. The capture launcher now fits inside the 1344 × 896 reference viewport. Phone appearance controls are reachable from the top bar. Desktop/morning/night/tablet/phone screenshots were generated and inspected. These are study checks, not claims of production-app or live Brain verification.

Refinement choices: neutralise the reading-surface tint, enlarge primary text, simplify repeated soothing section labels, preserve a visible landscape horizon, and reduce excessive vertical space while retaining distinct groupings.

Latest steering: minimize noise and keep necessary, useful components. The default study now shows the agenda, daily ritual, focus and capture. Secondary notes/progress/activity sit in a native accessible disclosure, retaining their interactions. Browser checks passed after this change, including opening the disclosure and using its Notes action. Short native-dialog transitions and press feedback were added; reduced-motion and high-contrast preferences remain supported. Apple and minimalist research is recorded in `planning/interface-feel.md` and `requirements/spec-interface-experience.md`.
