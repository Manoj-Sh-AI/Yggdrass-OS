# Moving the backend to an always-on server

Status: approved 2026-11-20 with Manoj's choices: **Railway** hosts the backend (its own
HTTPS address, so no DuckDNS); **notes are database rows** (D44, in effect since
`YGGDRAS_BRAIN_SOURCE=rows`), so there is no Git sync of notes. Nothing has been created,
bought or deployed yet. Follows `planning/supabase-database-move.md` (done: the
database is in Supabase) and comes before Vercel.

## Why

Today every program runs on the laptop. With the laptop asleep or off, nothing rings,
and the phone can only answer over a USB cable. Supabase hosts the database but cannot
run long-lived Python programs (its Edge Functions are short TypeScript functions). A
small always-on host runs the backend; the laptop, the phone and (later) Vercel become
clients of it. Owner choice (20 Nov): Railway, for the quickest setup (deploys from
GitHub, no server to maintain). It replaces the 16 Nov Oracle choice.

## What runs on the server

| Program | Today (laptop) | On the server |
|---|---|---|
| Application API + 15-second call scheduler | `local_runtime serve` | Railway service `api` (`yggdress_app.cli serve`), public HTTPS address |
| Voice worker (LiveKit agent) | child of serve | Railway service `voice` (no public address) |
| Brain service + Lia (Yggdrass-OS-main) | child of serve, port 8100 | Railway service `brain`, private network only |
| Temporal (agent workflows) | local dev server + SQLite | Railway service `temporal` with a small volume (private network only) |
| Database | Supabase | Supabase (unchanged); Railway EU West (Amsterdam) is ~10 ms from Frankfurt |
| Web app | Next.js on the laptop | the laptop for now; Vercel next (`YGGDRESS_API_URL` points at the `api` service) |
| HTTPS | none | provided by Railway (`*.up.railway.app`) |

## What has to move besides code (measured)

| Data | Today | Plan |
|---|---|---|
| Notes | Already in Supabase: the `brain` rows are the brain (D44, `YGGDRAS_BRAIN_SOURCE=rows`). The markdown folder `C:\Users\shman\yggdras-brain` is frozen (rollback only) | Nothing to move. Lia on Railway reads and writes rows, with Manoj's approval as today. To check before deploying: which files Lia still needs from disk (skills, manual), and bundle them with the brain service. |
| Connector accounts | `%LOCALAPPDATA%\Yggdras\connectors` (Fernet key file + encrypted store, portable) | Into a Railway volume on the `api` service, copied once; the key as a Railway secret variable. |
| Secrets (Anthropic, LiveKit, Firebase, database roles) | `runtime.json`, brain `.env` | Railway service variables (encrypted, visible only to the project). Never in Git or chat. |
| Temporal history | `%LOCALAPPDATA%\Yggdras\temporal` | Not moved: short-lived job history, recreated empty. |
| Backups | laptop, nightly | Kept on the laptop as a scheduled Windows task that dumps straight from Supabase (verified, 14 days), so a backup exists outside Supabase and Railway even when the backend no longer runs on the laptop. |

## Decisions (Manoj, 2026-11-20)

1. **Host: Railway** (Hobby plan, region EU West). Faster to set up than a server; costs
   about USD 5/month minimum, likely USD 5-15 for these four services.
2. **Address:** Railway's own HTTPS address; a custom domain can be added later.
3. **Notes:** database rows, edited by Manoj or by Lia with his approval (D44). No Git.
4. **The laptop afterwards:** its local backend is switched off and kept installed for
   rollback; the desktop app opens the hosted web app.
5. **Code must be on GitHub to deploy:** Railway builds from a GitHub repository, so
   today's uncommitted work is committed (Manoj's go-ahead) before the first deploy.

## Code changes needed (small, tested before deploying)

- A hosted mode: run the API, voice worker and brain service as separate Railway services
  instead of children of `local_runtime serve` (which also starts Next.js and owns the
  local PostgreSQL on Windows). Settings come from environment variables, not
  `runtime.json`. One Dockerfile (or Nixpacks config) per service.
- The web app's server-side proxy already takes `YGGDRESS_API_URL` and `YGGDRESS_ORIGIN`;
  the phone app gets the server address instead of `127.0.0.1` over USB.
- Health endpoint for monitoring; logs stay on the server (rotated), never transcripts.

## Steps (each checked before the next)

1. **Account (Manoj):** create a Railway account, choose the Hobby plan and connect
   GitHub (the card is entered by Manoj only).
2. **Commit and push** today's work (Manoj's go-ahead); the brain project repo too.
3. **Hosted mode code** + Dockerfiles, tested locally first.
4. **Create the project** in EU West: services `api`, `voice`, `brain`, `temporal`;
   private networking between them; only `api` gets a public address.
5. **Secrets** as Railway variables (entered by Manoj from his own files, or by me only
   where they are generated app passwords); connector vault into a volume.
6. **Test with calls and scheduling OFF** while the laptop still runs, against the same
   Supabase database: sign-in, calendar, a Lia question, a note read.
7. **Switch (about 2 minutes):** stop the laptop backend, turn scheduling and calls on
   in Railway, point the desktop app and phone at the hosted address, one live test call.
8. **Rollback:** stop the Railway services and start the laptop backend again. No data
   moves either way: both use the same Supabase database.

## Security

- Only the `api` service is public (HTTPS); the brain service, Temporal and the voice
  worker are reachable only on Railway's private network.
- The existing sign-in rules apply (password, lockout after 5 failures, 30-day phone and
  8-hour desktop sessions); HTTPS is now mandatory, so cookies are secure.
- Secrets live in Railway variables, never in Git or chat.
- Railway processes note contents in memory (reading rows, calling Lia); covered by the
  2026-11-20 amendment (`rationale/decisions/supabase-database.md`).

## Costs

Railway Hobby: USD 5/month including USD 5 of usage; expected USD 5-15/month for four
small always-on services. Unchanged: Supabase Free, LiveKit Build, Claude usage, Firebase.

## Risks

- Cost grows with memory use: the brain service (Lia) and the voice worker are the
  heaviest; measured after the first day and reported.
- Railway outage = no calls (same as the laptop being off today); rollback to the laptop
  takes about 2 minutes.
- Railway's containers restart on deploy; a call in progress during a deploy ends.
