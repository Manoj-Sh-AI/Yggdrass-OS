# Daily routine integration

## Code findings

1. Existing task blocks already store exact times, IANA zones, priorities and versions.
2. Existing call preferences own quiet hours and the reminder time zone.
3. Named timetable events can provide wake-up and review times.
4. A dedicated wake-up setting was absent.
5. Application and Brain records use separate schemas and permissions.
6. Lia is the knowledge boundary and requires approval before writes.
7. Android FCM and the LiveKit worker already exist.
8. Browser push needed subscription, response and service-worker plumbing.
9. The hosted backend already has Railway configuration.
10. Web deployment configuration exists for Vercel and Railway.
11. Existing task edits support version checks and execution history.
12. Existing call behavior includes actions beyond the reminder agent's allowed authority.
13. Daily routines therefore use a restricted reminder capability and three voice tools.
14. The local backup path already verifies a restore.
15. Hosted migration, account configuration and external backup storage require actual service verification.

## Approved choices

Continue through the catalogue layers. Prepare nightly filing proposals for owner approval.
Use text notifications and retain the original five-minute call deadline after Not yet.
Use a custom invented wake-up reminder to test reliability before the owner enters tasks.
Claude owns the interface design. Functional routine controls reuse existing components.

## Implementation entry points

The authenticated API lives under /v1/application/daily-routines.
GET returns settings, saved briefs, editions, selected important blocks and recent jobs.
POST /trigger accepts kind, dry_run, optional day, task_id and starts_at.
Every catalogue kind is callable there. The default is a read-only preview.
The web control page is /daily-routines. The manual CLI is
app/api/scripts/routine_trigger.py.

Scheduling uses app.scheduled_jobs, versioned task-block triggers, leases and attempt records.
Enablement is explicit through daily-routine settings. Fresh installations start disabled.
Named Wake up / Morning brief timetable items provide the morning anchor.
Fallback times stay empty until explicitly supplied.

## Assumptions

- daily_routine_settings.ANCHORS matches exact named timetable entries.
- routine_jobs.anchor_instant selects the first autumn fold and advances a spring gap.
- daily_routine_settings.anchor_times reserves Sunday as a rest day by default.
- routine_jobs.acknowledge records Not yet without moving the original deadline.
- routine_voice.CALL_LIMIT caps a reminder conversation at four minutes.
- routine_catalogue uses seeded code for daily and weekly random choices.
- routine_reflections reveals calibration scores after twenty resolved items per domain.
- daily_routine_settings ease-off thresholds are editable personal heuristics.
- routine_catalogue's counter-view uses concrete checks from task records without a paid critic call.
- Opportunity leads come from the owner's source pool until search providers are configured.

## Verification boundary

Automated delivery tests use an isolated PostgreSQL database and captured transports.
They establish application scheduling behavior. They cannot establish push delivery on a
locked physical phone, cloud agent startup, provider quotas or real speech quality.
Account keys, permission enrollment, worker uptime and device behavior require live activation.

## Deployment facts checked

Railway documents volume backups, including scheduled backups. The attachment's claim
that Railway has no managed backup facility should not be treated as established.
An independent object-storage export and restore test remains a deployment deliverable.
An always-running worker requires Railway Serverless sleeping to be disabled.

Sources checked on 22 November 2026

- [Railway backups](https://docs.railway.com/volumes/backups)
- [Railway Serverless](https://docs.railway.com/deployments/serverless)
- [LiveKit quotas](https://docs.livekit.io/deploy/admin/quotas-and-limits/)
- [Claude model pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [ECMWF probability verification](https://confluence.ecmwf.int/pages/viewpage.action?pageId=255078889)

No model price is used to authorize spending. Existing instructions permit no paid test calls.
