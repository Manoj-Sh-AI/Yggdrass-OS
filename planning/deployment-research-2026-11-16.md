# Deployment research — personal Yggdras

Research date: 16 November 2026, Europe/Berlin. Recommendation only: no resource
creation, deployment, database migration, provider call or application-code change
was authorized or performed during this research.

## Subsequent owner selection

The owner subsequently chose a free-first target: Vercel Hobby, **one Supabase
project** containing separate `app` and `brain` schemas/roles, Oracle Always Free
for the existing backend and workers (subject to actual capacity/compatibility),
and LiveKit Build for later in-app voice. This supersedes the paid-budget
recommendation below as the owner's preferred target, not its price evidence.

The owner separately authorized local database consolidation before deployment;
see [the local consolidation procedure](shared-postgresql.md). No cloud resource
has been provisioned. One Supabase Free project shares its 500 MB database
allowance across Brain/application data. Attachments, indexes and execution/chat
records count too; unlimited API requests do not mean unlimited processing.
Properly self-hosting Temporal on Oracle is an option for avoiding Cloud usage
fees, subject to sizing and production configuration; the current local Temporal
development server is not a public deployment configuration. Claude/speech usage
and services exceeding free allowances remain separately billable.

Owner's constraints: one user; prefer free tiers where useful; aim for €15–25 per
month excluding Claude and calling usage. First calling target is voice inside
web/desktop/mobile apps, rather than regular telephone-number calls.

## Recommendation

Use **Vercel Hobby + an 8 GB Linux VPS + self-hosted PostgreSQL + Temporal Cloud
Developer + LiveKit Build**, with encrypted off-server backups in Cloudflare R2.
Coolify self-hosted is an optional free deployment panel on the VPS. Keep it a
single-server personal pilot with an explicit backup/restore procedure.

First server candidate: OVHcloud 8 GB x86 VPS in an EU region. Alternative: Hetzner
CX33 if actually available at its cost-optimized rate. Target €10–15 per month for
the server on a flexible term; that is a planning allowance, not a confirmed
checkout quote. Choose the monthly term and validate compatibility before an
annual commitment.

The recommendation is based on the code's actual requirements: Next.js frontend,
FastAPI application service, existing separate Brain API, existing Lia environment
and skills, persistent PostgreSQL, and always-running Temporal workers. Model
inference stays with Anthropic; this pilot does not need a GPU server. An 8 GB
machine is an initial sizing recommendation, to be verified under representative
load rather than a measured capacity guarantee.

## Suggested allocation

| Component | Service | Expected starting charge |
|---|---|---|
| Next.js frontend and server-side API proxy | Vercel Hobby | $0 within personal-use quotas |
| Application API, existing Brain API, Lia runtime and workers | 8 GB Linux VPS | Budget €10–15/month; verify region, term, IP and renewal price |
| App records and Brain records | Two distinct PostgreSQL databases/roles on that VPS | Covered by the server bill; no separate database service subscription |
| Deployment control | Coolify self-hosted, if desired | $0 software charge; consumes VPS resources |
| Durable orchestration service | Temporal Cloud Developer | No base fee; metered Actions/storage plus support percentage |
| In-app voice/media | LiveKit Build | $0 platform tier within quotas; speech/model inference remains separate |
| Off-server backups | Cloudflare R2 Standard | Free within storage/request allowances; meter anything above them |

For light personal usage, **€15–25/month is a reasonable initial hosting budget**,
not a fixed-price bundle or hard billing cap. It includes a reserve for Temporal
usage and small storage overages. A custom domain, exchange-rate movement,
applicable taxes on USD services, Claude, speech-to-text and text-to-speech are
additional. Temporary credits are not counted as permanent savings.

## Price evidence and qualifications

### Frontend

[Vercel Hobby](https://vercel.com/docs/plans/hobby) is free for personal,
non-commercial use, subject to quotas. This matches the owner's present one-user
use. Commercial use would need a plan review. The existing Next.js application
includes server-side routes, so the deployment must support Next.js server behavior.

### VPS

[OVHcloud's German VPS page](https://www.ovhcloud.com/de/vps/) advertises an
8 GB / 4-vCore / 75 GB NVMe option from **€8.58/month including German VAT**.
Its linked configurator selects `pricing=upfront12`; the headline is not a
verified month-to-month price. The configurator also selects a Local Zone plan;
region and backup characteristics must be checked against the selected offer.

[Hetzner's official June 2026 adjustment](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)
lists the EU CX33 at **€8.49/month excluding VAT**. IPv4 is separately priced.
The [cost-optimized product page](https://www.hetzner.com/cloud/cost-optimized/)
shows CX33 availability constraints, so that offer must be confirmed in the
account/region before selecting it. A more expensive replacement should get a
new budget comparison.

Both options require operating the server and PostgreSQL. A deployment panel
does not turn the database into a fully managed service. Automated encrypted
database backups and a tested restore are part of the planned deployment.

### Temporal

The [current official pricing source](https://github.com/temporalio/documentation/blob/main/docs/evaluate/cloud/pricing.mdx)
lists Developer support with **no base fee**, Actions at **$50 per million**, and
support at **10% of usage spend**. Storage is additional: active histories are
$0.042/GB-hour and retained histories $0.00105/GB-hour. Older cached pricing pages
still show the former $100 Essentials minimum; the Developer selection and its
terms must be confirmed during signup.

Illustration: 100,000 billable Actions are $5; including 10% support makes that
$5.50 **before storage and tax**. An Action is not a chat message or a Claude API
call. This is an arithmetic example, not a forecast of this application's usage.
Measure Actions and history storage after launch; use budget alerts and bounded
retention. Long-lived approval histories also use active storage.

The current local app uses a private SQLite-backed development server. Hosting
needs either Temporal Cloud or a properly operated self-hosted Temporal service.
The [official self-hosting guide](https://docs.temporal.io/self-hosted-guide)
distinguishes the local development server from production deployment.

Workers still run on our VPS; Temporal Cloud coordinates their work rather than
hosting the application code. Select an appropriate region and configure payload
encryption because workflow inputs/results can contain note context. Lia's memory
engine remains unchanged.

### Voice

[LiveKit pricing](https://livekit.com/pricing) lists Build at $0/month with
5,000 WebRTC participant minutes and 1,000 hosted-agent session minutes, along with
limited inference credit. Participant and agent minutes are distinct meters;
they must not be described as a blanket allowance of free AI conversation time.
Its $50 Ship base plan would exceed this pilot's target, so it is not the starting
recommendation. Build-hosted agent compute can have cold starts; verify first-call
latency. A future always-on voice adapter on our VPS is another option to evaluate
against its media quotas.

Voice needs an adapter for microphone audio, speech recognition, the existing
Yggdras application interface, speech output and interruption handling. Claude
processing remains server-side. Speech/model fees are additional after applicable
credits even when media transport is within the free allowance. No PSTN provider
or phone-number subscription is needed for the chosen in-app-first scope.

An open web/desktop app can establish an audio session. Ringing a locked phone
with the app in the background is separate native-mobile/push work. For example,
Apple documents the incoming-call integration through
[PushKit and CallKit](https://developer.apple.com/documentation/pushkit/responding-to-voip-notifications-from-pushkit).
Hosting and a LiveKit account do not implement this behavior by themselves.

### Backups and deployment control

[Cloudflare R2 Standard](https://developers.cloudflare.com/r2/pricing/) includes
10 GB-month storage, 1 million Class A requests and 10 million Class B requests
monthly; egress is free. Storage beyond the allowance is $0.015/GB-month, with
request overages separately priced. Apply retention to encrypted PostgreSQL dumps
and verify restoration. It is backup/object storage, not the live PostgreSQL disk.

[Coolify self-hosted](https://coolify.io/pricing) is free. Coolify Cloud starts at
$5/month and still requires a separately paid server, so its $5 price must not
be mistaken for the entire hosting bill. Self-hosted Coolify's documented minimum
resources also need room in the VPS budget.

## Alternatives compared

| Bundle | Cost model | Assessment for this owner |
|---|---|---|
| Recommended mixed bundle | Free frontend/media tiers, one small paid VPS, metered Temporal | Best balance within €15–25 if the server's flexible-term quote fits |
| Railway for frontend/API/workers/Postgres + Temporal + LiveKit | Railway Hobby $5 minimum or Pro $20 minimum, credited against usage; RAM/CPU/storage extra | Easier server operations; total is usage-dependent rather than a $5 all-inclusive bundle |
| Vercel + Supabase + worker hosting + Temporal + LiveKit | Frontend can be free; Supabase Free has caps or paid Pro starts $25; worker compute still required | Useful managed-DB option, but more providers/cost than needed initially |
| Oracle Always Free compute + free frontend/media | Potential $0 compute; remaining services/metered usage still apply | Experimental fallback; capacity/ARM compatibility and idle reclamation make it a weaker sole home for personal data |

[Railway resource pricing](https://docs.railway.com/pricing) lists $10/GB-month RAM,
$20/vCPU-month, $0.15/GB-month volume storage and $0.05/GB service egress. One GB of
average always-on RAM alone is roughly $10/month. Platform provisioning and
database backup/availability settings need separate review.

[Supabase Free](https://supabase.com/pricing) allows two active projects, each with
a 500 MB database; inactive free projects can pause after one week. Two projects
could keep App and Brain distinct. The existing chat attachment bytes currently
occupy PostgreSQL, so image/file use can exhaust the database allowance. The code
also opens fresh connections and reconciles regularly; remote free-tier bandwidth
and connection behavior must be checked. Pro is $25 with the first project, and
additional projects start at $10/month, making two paid projects approximately
$35 before extra usage. PostgreSQL on our paid VPS avoids a separate DB subscription.

[Oracle's current Always Free documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
lists eligible compute/storage, but also permits reclaiming idle compute. Its
current page lists 2 A1 OCPUs and 12 GB total memory; older internet guides advertise
larger allowances. Availability and the console's actual entitlement must govern
any experiment.

Vercel now advertises [Daemons](https://vercel.com/daemons) for continuous workers. It should not be described
as incapable of running them. However, that newer product's access, beta status,
runtime compatibility and current billing would need a dedicated validation before
selecting it for this budget. This recommendation uses ordinary persistent Linux
containers for the existing Python/Brain/worker environment.

## Application-specific deployment work still required

This research does not certify the Windows-oriented runtime as cloud-ready.
The next deployment task would need to:

1. Package the application API, existing Brain API and original Lia environment
   for Linux, with static skills available privately. Keep the memory engine intact.
2. Preserve App and Brain in separate PostgreSQL databases/roles, migrate and
   verify both, and test restoration. Hosting only the frontend while leaving the
   Brain service on the laptop would retain the laptop dependency.
3. Replace the local Temporal development-server launcher with authenticated,
   encrypted Temporal Cloud configuration; retain existing receipts and budgets.
4. Configure HTTPS, application origins, server-only secrets and the frontend
   proxy. Expose the application entry point; keep databases, Brain endpoints and
   receiver credentials private.
5. Keep the worker/API together initially, since the current receiver adapter
   explicitly uses loopback. Separate services can follow through a reviewed
   private-network adapter. Existing chat buffering also needs review for voice.
6. Deploy from a private repository/image path, verify Notes/Chat/tasks/calendar/
   graph against the online services, and point the existing desktop wrapper to
   that shared backend. Native wrapper updates remain separate from web updates.
7. Add in-app voice as its own integration after the hosted text/data path works.
   Native locked-phone incoming calls remain later mobile work.

## Initiation recommendation

Create free Vercel Hobby, LiveKit Build and R2 accounts when ready. Obtain a
month-to-month 8 GB VPS quote, then confirm Temporal Cloud Developer's current
signup pricing. Choose the EU region consistently where supported. Do not buy
annual plans, Vercel Pro, Supabase Pro or LiveKit Ship for this first single-user
release without a demonstrated need. Deployment itself requires a subsequent
explicit instruction.
