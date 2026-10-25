# Vision

> Starter draft taken from the skills plan (Oct 23, 2026), synced to `planning/locked-plan-v1.md` on Oct 24, 2026. Edit freely: this is Manoj's file.

## Purpose

A personal second brain that organizes projects, work, learning and job search through focused phone notifications.

## Who it is for

- Now: Manoj.
- Later: anyone. Process and data stay separate so someone else's data can plug in.

## First slice: the brain (phase 1a)

Markdown files are the source of truth. Everything else is a derived index.

**In scope**
- 50 to 100 brain nodes written by hand, in a node format designed for later machine extraction
- `index.md` listing every node with a one-line description
- A gateway skill telling an agent how to navigate the brain
- An eval set with known answers, negative cases included

**Out of scope for now**
- Automated ingest and promotion of facts (later phases: Graphify link discovery in 1b, the filter agent in 3)
- Everything after phase 1a in the locked plan

## Later (parked, not forgotten)

From the locked plan's out-of-scope list, deferred rather than dropped:

- Model-agnostic switching between providers (the client still sits behind an interface, D27)
- Health monitoring and the emotion dashboard
- The language-learning page with its tree structures
- Voice models and the common agent across pages
- The life timeline page with deadline milestones
- The mobile web client
- Cloud hosting beyond the notification outbox, continuous deployment, versioned releases
- Sub-brains beyond the two agents of phase 4
- Product packaging, licensing or paid tiers

## What "done" means for the first slice

<!-- TODO (Manoj): one or two sentences. The plan's exit test is "ten real questions answered correctly by an agent reading only the index, the gateway skill, and the files it chooses from them." Detailed acceptance criteria go in requirements/. -->
