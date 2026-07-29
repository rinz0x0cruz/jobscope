# jobscope

**Resume-driven company monitor, job scout, and application-prep tool.** Point it at your
resume; it monitors selected employers' reviewed public ATS feeds,
ranks fitting roles by a transparent fit score, enriches each
with public intel (compensation, stock/IPO, Reddit sentiment, company news, referral
leads), tailors your resume + cover letter per job, and assembles a **review-ready
application package** with an email summary.

Design principles:

- **Deterministic-first (80% logic, 20% AI).** Scraping, scoring, enrichment, and
  scam/ghost-job detection are plain code. AI is used only where it earns its keep
  (rewriting bullets, drafting cover letters, summarizing sentiment) and is **off by
  default** — the core loop works with no API key.
- **Your account is never at risk.** jobscope prepares everything and hands you a
  one-click link; **a human always clicks submit.** It never drives your logged-in
  LinkedIn/Indeed/Workday. An opt-in `--assist` mode can pre-fill *public* ATS forms
  (Greenhouse/Lever/Ashby) but always **stops before submit**.
- **Local-first & private.** By default your resume, data, and secrets stay on your
  machine (SQLite + gitignored files). An explicit private hosted mode moves that
  trust boundary to one protected volume and secret manager. The published dashboard
  remains redacted. See [SECURITY.md](SECURITY.md).

> Built as a sibling to [threatscope](../threatscope) / [exploitrank](../exploitrank):
> stdlib CLI, SQLite persistence, concurrent feeds, static dashboard, `selftest`.

---

## Install (fresh OS: clone → setup)

Requires Python 3.11+.

```bash
git clone https://github.com/rinz0x0cruz/jobscope
cd jobscope

# Windows (PowerShell)
./setup.ps1

# macOS / Linux
./setup.sh
```

The setup script creates a virtualenv and installs dependencies:

```bash
python -m venv .venv
. .venv/bin/activate           # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.lock
```

PDF export and `apply --assist` need Chromium, which is a separate opt-in because
the wheel plus browser is roughly 200 MB. Everything else works without it — the
tailor writes Markdown and HTML, and assisted fill reports itself unavailable:

```bash
pip install playwright==1.40.0
python -m playwright install chromium
```

Run `serve` from this source checkout, where `web/` is available, or use the repository Docker image.
The Python wheel contains the CLI package but does not bundle the React source/build.

## Quick start

```bash
python -m jobscope init                          # scaffold config.yaml + data/ + .env
# add your resume at data/resume.md
python -m jobscope resume import data/resume.md   # parse it + seed an editable search profile
python -m jobscope profile show                   # review roles/markets that drive scan
python -m jobscope companies seed                 # import configured watchlist; application companies stay known
python -m jobscope companies scan                 # check monitored supported career portals
python -m jobscope match                          # rank by fit score
python -m jobscope reviews sync                   # monitored/discovery roles enter the review queue
python -m jobscope enrich                         # comp / stock / reddit / news / contacts (top N)
python -m jobscope tailor <job_id>                # tailored resume + cover letter (PDF)
python -m jobscope prep   <job_id>                # full review-ready application package
python -m jobscope serve --open                   # live local workspace + profile editor
```

Or run the whole loop in one shot:

```bash
python -m jobscope pipeline                        # scan -> match -> enrich -> prep top picks -> digest
```

For Markdown, text, and extracted PDFs, tenure is derived only from a recognized
work/professional experience section; headingless education/project dates are ignored.

## Commands

| Command | What it does |
|---|---|
| `init` | Scaffold `config.yaml`, `data/`, `.env` |
| `resume import <path> [--name N]` | Parse `.md`/`.json`/`.pdf`/`.txt` into a named base resume (maximum 3 profiles) |
| `profile [build\|show] [--resume N] [--force]` | Editable search profile (target roles, preferred job markets, worldwide remote) that drives `scan`; résumé facts stay derived |
| `companies [seed\|list\|scan\|apply]` | Persistent company watchlist. A targeted scan fetches supported official-portal jobs; **Find recruiter** is a separate explicit action. |
| `scout <company> [--provider P --slug S]` | Preview one company's public ATS board and profile-ranked openings without monitoring it. |
| `scan [--mode all\|monitored]` | Scan active user-selected company monitors through reviewed Greenhouse, Lever, or Ashby public APIs. |
| `reviews [sync\|list] [--state S]` | Build/inspect the durable `pending` / `saved` / `dismissed` review queue without resetting prior decisions. |
| `match` | Fit scoring + tiers, **multi-resume selection**, and **filters** (clearance/sponsorship/block-list) |
| `pipeline` | scan -> match -> enrich -> prep top picks -> digest (one shot) |
| `serve [--open]` | Run the loopback control plane: live SQLite dashboard, immediate mutations, profile upload/edit, campaigns, and local refresh |
| `refresh [--local-only] [--force]` | Sync Gmail + rescore. Existing default also publishes the encrypted snapshot; `--local-only` never builds or publishes |
| `enrich [--job ID]` | Comp, stock/IPO, Reddit, news, Glassdoor, referral contacts, **company brief** |
| `tailor <job_id>` | Keyword-aligned resume + cover letter (using the best base resume), rendered to PDF |
| `prep <job_id>` | Application package (docs + pre-filled answers + link + contacts + brief) |
| `apply <job_id> [--assist]` | Open the application; `--assist` pre-fills public ATS forms, stops before submit |
| `outreach <job_id> [--send]` | Preview or individually send a résumé-backed recruiter note for one role; local SMTP only |
| `campaign <action>` | Build cold or due follow-up queues, review one draft at a time, and send at most one due approved email per invocation |
| `brief <job_id>` | Blunt, risk-forward company brief (no marketing fluff) |
| `gaps [--top N]` | Skill-gap learning plan: skills to learn ranked by jobs unlocked |
| `new` | New Strong/Good jobs since you last reviewed |
| `dashboard [--open] [--public]` / `serve` | Emit/serve the dashboard; `--public` writes the empty schema-valid shell used by encrypted publication |
| `track [--set job_id=status] [--timeline job_id]` | Application funnel, rates, follow-up reminders, and a per-application email timeline |
| `applications [audit\|recover]` | Inspect reconciliation counts/decisions or explicitly restore a recoverable application |
| `inbox [--dry-run] [--backfill] [--since D] [--account E]` | Sync Gmail over read-only IMAP and auto-advance the funnel from application emails |
| `inbox-canary --account E` | Classify one configured account over verified TLS in a no-send, read-only throwaway database; deletes the database on exit. |
| `export [--format json\|csv]` | Export ranked jobs |
| `selftest` | Offline self-tests (no network, no keys) |
| `doctor` | Offline config, SQLite, secret-reference, toolchain, refresh, and source-health checks |

## Outreach batches (private control plane)

Open **Outreach** under `jobscope serve`, choose **Cold batches** or **Follow-ups**, and review
each target in the same private workspace. Cold batches rank unique companies using the
India / compensation / growth weights. Jobscope combines Watching/Known employers with its curated
India-relevant cybersecurity pool, removes every company with application history, and stores the factor
scores and evidence behind each cold-campaign rank.

**Build follow-up queue** prepares due drafts from sent cold campaign mail and applications still in
`applied`. It uses `apply.followup_days`, keeps one target per company, prioritizes the oldest due action,
and excludes sources already queued, replied to, opted out, or advanced beyond `applied`. Building the queue
does not approve, schedule, or send anything. The CLI equivalent is:

```powershell
python -m jobscope campaign followups --name "Recruiter follow-ups" --count 10
```

Cold-email follow-ups reuse and lock the original recipient, subject thread, `In-Reply-To`, and
`References`. Application follow-ups reuse and lock a prior `outreach_to` address when present; otherwise
they select a cached verified recruiter/company contact or remain **Needs contact** for explicit discovery.
Role inboxes are never auto-selected.

Contact discovery reuses verified inbound and company-published addresses plus optional Hunter/Apollo results
when their key environment variables are configured. Finder results must still be valid, non-automated,
non-ATS, and on the confirmed employer domain. Conventional role inboxes remain visible fallbacks but are
never auto-selected.

Every target is reviewed separately. Approval binds the exact recipient, subject, body, résumé attachment,
follow-up thread identity, contact provenance, jurisdiction/classification decision, reviewer, and policy version;
editing any of them clears approval. Each sent email carries a stable Jobscope `Message-ID`; the local inbox
tracker links the immediate `In-Reply-To` parent exactly, with confirmed-domain + post-send timing as a
fallback for new threads.
The Outreach delivery history shows recipient, subject, send time, reply sender/subject/time, and opt-outs.

The local scheduler runs a reconciliation-only campaign tick: it checks configured inboxes for replies,
opt-outs, bounces, and complaints, reports due work, and never calls SMTP. Delivery is a separate explicit
action on one policy-approved target. Drafts can be exported as `.eml` while SMTP, inbox, and AI are disabled:

```powershell
python -m jobscope campaign ready
python -m jobscope campaign start --campaign-id ID  # no-send SMTP preflight, then activate
./scripts/register-outreach-task.ps1
python -m jobscope campaign replies          # check now; --no-fetch reconciles stored mail only
python -m jobscope campaign reconcile-delivery --target-id ID  # exact read-only Sent lookup
python -m jobscope new --reconcile-sent       # resolve an ambiguous digest by Message-ID
python -m jobscope campaign export-eml --target-id ID --out review.eml
```

Draft campaigns can be permanently deleted from their Outreach detail view. The CLI equivalent requires
explicit confirmation: `python -m jobscope campaign delete --campaign-id ID --yes`. Only campaigns still in
`draft` with no sent, replied, opted-out, in-progress, or delivery-unknown target can be deleted; use cancel
when delivery history must be retained.

SMTP cannot make delivery and the local SQLite update atomic. If the connection fails after delivery begins,
Jobscope records **delivery unknown**, locks the target out of automatic retries, and keeps its Message-ID.
Use **Check Sent** for an exact, read-only Message-ID lookup; zero, one, and multiple matches remain distinct.
Manual **Confirmed in Sent** / **Confirmed not sent** controls remain available when provider evidence must be
reviewed directly. The latter returns the message to Draft and requires a fresh approval before any retry.
Digest delivery uses the same durable stable-ID barrier through `new --reconcile-sent`.
Known pre-send or SMTP rejection failures retain that ID but are not retried by scheduled refreshes; run
`python -m jobscope new --email` explicitly after correcting the cause.

Writable campaign state, draft bodies, approvals, résumé paths/hashes, raw message IDs,
suppression internals, and send logs stay out of Pages. After passphrase unlock, Pages can
show an allowlisted **read-only Outreach snapshot** (batch/target state, recipient, subject,
schedule, and delivery/reply summary). GitHub Pages and GitHub Actions cannot approve,
mutate, schedule, or send campaign mail.
The private Applications ledger reads a separate, token-guarded engagement projection: it may show
recipient, subject, send/reply dates, state, follow-up count, and a retained inbound snippet summary.
It never exposes outbound bodies, résumé paths/hashes, approval hashes, or raw message/thread identifiers.
Campaign auto-drafting selects only valid, non-automated recipients on the confirmed company domain and never
auto-selects a role inbox. Off-domain recruiter or agency contacts may remain visible as evidence, but cannot
block a lower-ranked eligible Hunter, Apollo, or employer-published contact.

Optional AI is bounded here too. A local model may only redraft outreach copy, and its text is
validated against the supplied facts before it is used. Company ranking, recipient validation,
approval, sending, Message-ID/domain reply matching, and opt-out suppression remain deterministic.
AI cannot mark a campaign replied or opted out, cannot approve or send, and Jobscope works
identically with AI entirely disabled.

## Inbox: auto-track applications from Gmail

`jobscope inbox` reads the Gmail inbox(es) you configure and turns application
emails into funnel updates automatically — confirmations → `applied`,
interview/assessment invites → `interview`, offers → `offer`, rejections →
`rejected`. Classification is **deterministic** (sender-domain + keyword rules for
Greenhouse / Lever / Ashby / Workday / iCIMS / Workable / LinkedIn / Indeed and
friends); no model participates in mail classification at all.

It connects over certificate-authenticated **read-only IMAP** with a Gmail **App Password** — no Google
Cloud project, no OAuth, and it never marks your mail as read. Hostname/CA verification is mandatory and
each connection has a 30-second socket timeout. The first run scans
`inbox.lookback_days` back; later runs are incremental (a per-account UID
watermark), so it's cheap to run on a schedule. Each relevant email is stored as a
timeline entry and linked to the matching job (or a standalone email-only
application when you applied somewhere jobscope didn't scrape).

**Setup**

1. Turn on 2-Step Verification for the account, then create an App Password:
   <https://myaccount.google.com/apppasswords>
2. Put the 16-character password in `.env` (never in `config.yaml`):
   ```
   JOBSCOPE_GMAIL_APP_PW=xxxxxxxxxxxxxxxx
   ```
3. Enable the feature and list your account(s) in `config.yaml`:
   ```yaml
   inbox:
     enabled: true
     accounts:
       - email: "you@gmail.com"
         password_env: "JOBSCOPE_GMAIL_APP_PW"
   ```

**Use**

```bash
python -m jobscope inbox --dry-run            # classify + print, write nothing
python -m jobscope inbox-canary --account you@gmail.com  # isolated no-send activation check
python -m jobscope inbox                      # sync (incremental) -> funnel
python -m jobscope inbox --backfill           # rescan lookback_days
python -m jobscope track                      # updated funnel + response/interview/offer rates
python -m jobscope track --timeline <job_id>  # email history for one application
python -m jobscope dashboard --open           # Applications board: pipeline columns + email timelines
```

Multiple mailboxes: add more entries under `accounts`, each with its own
`password_env`. Everything stays local in SQLite; app passwords resolve from your OS
keychain (`jobscope secrets set JOBSCOPE_GMAIL_APP_PW`) or `.env`. Email bodies are
classified in memory and **not stored** unless `inbox.store_snippets` is on. You can
purge mail, active applications, audit detail, or confirmed tombstones separately with
`jobscope purge`. Runs well from cron /
Task Scheduler.

> **Tip:** point jobscope at a **dedicated job-search Gmail account** (forward recruiter
> mail to it) so its app password can't touch your primary inbox. See [SECURITY.md](SECURITY.md).

## Reconciliation audit and recovery

Every funnel recompute/reclassification records a bounded audit run: before/after
application and event counts, aggregate split/reclassification/drop/tombstone totals,
and controlled decision codes. Reconciliation no longer hard-deletes stale or orphaned
email-derived applications. It tombstones them, hides them from the active funnel, and
keeps their prior application fields available for explicit recovery.

```bash
python -m jobscope applications audit
python -m jobscope applications audit --run <run_id>
python -m jobscope applications recover <job_id>       # add --yes for terminal/rejected rows
python -m jobscope purge --audit --older-than 730      # decisions only
python -m jobscope purge --tombstones --yes             # irreversible recovery-data purge
```

A restored row is marked reconciliation-exempt so the next recompute does not remove it
again. `retention.reconciliation_audit_days` defaults to 730 and prunes detailed
decisions after successful inbox reconciliation; run summaries and tombstones persist
until explicit purge. Audit rows never copy email subjects/bodies/snippets/from-addresses,
recruiter addresses, notes, interview dates, or compensation.

When a pre-audit database is first opened, Jobscope records one count-only
`baseline_only` run. It does not fabricate historical decisions: if no matching old
snapshot exists, an earlier count transition such as 121 → 99 cannot be reconstructed.

## Prioritization (company quality + location)

Scoring blends deterministic signals into a 0–100 fit score. Two of the weights
nudge the ranking toward roles you actually want:

- **Company quality** (`weights.company`) — a curated tier list boosts prestigious
  and top security employers (FAANG, NVIDIA/OpenAI/Anthropic, Palo Alto Networks,
  CrowdStrike, Zscaler, Okta, Wiz, Stripe, Databricks, …). Unknown companies get a
  neutral score, so no one is penalized for being obscure.
- **Company size** (`prefer_company_size`) — bias ranking by headcount. Set
  `large` to prioritize big, established employers (FAANG-scale), `small` to favor
  startups, `mid` for scaleups, or `any` to ignore size. Sizes come from a curated
  headcount map; unknown companies stay neutral.
- **Location** (`weights.location`) — list the places you prefer and matching jobs
  get the full location score:

```yaml
match:
  prefer_locations: ["Remote", "India", "Bengaluru"]  # substring match -> full score
  prefer_companies: []                                # your own must-boost employers
  prefer_company_size: "large"                        # any | large | mid | small
```

The dashboard is company-first and master–detail. **Review** defaults to pending matches from
monitored portals, with Discovery, Saved, and Dismissed as explicit sibling queues. **Companies**
shows portal health, board/open/pending/saved counts, and a preferred recruiter. **Scan jobs** and
**Find recruiter** are separate actions, so a portal scan never waits on contact discovery. Contact ranking prefers
cybersecurity/security recruiters, then technical/engineering recruiters, then general recruiting/HR.
Cards show score, role/company/location, public-market compensation ratio when comparable,
Glassdoor/Reddit/news signals when available, and a verified recruiter mail or guarded local lookup.
Clicking one opens the Source Serif reader with the description, company brief, compensation,
stock/IPO, public reputation, referral leads, and score rationale. The toolbar and Settings both
provide **Scan Gmail**; local serve uses its CSRF-guarded refresh API and Pages dispatches the existing workflow.

Automatic scans support Greenhouse, Lever, and Ashby only. An unresolved Workday, iCIMS,
SmartRecruiters, Phenom, or custom portal stays **Needs setup** and does not trigger a crawler or fallback.
This deliberately trades broad aggregator coverage for publisher-documented feeds, predictable contracts,
and a smaller legal and operational risk surface. Add companies explicitly in Settings or as
`Name|provider|slug`; application-history companies are never promoted to monitored automatically.

Remote roles carry a **remote scope**: the dashboard's *remote scope* facet splits
global remote ("Remote (anywhere)") from geo-restricted remote ("Remote in Ireland"),
and geo-restricted cards show a `Remote · <region>` badge. Set `match.remote_scope_strict:
true` to down-rank geo-restricted remote whose region isn't in your `prefer_locations`
or search country (off by default; global remote is never penalized).

## Local workspace, optional private host, and published snapshot

`python -m jobscope serve --open` is the canonical local control plane. It reads current
SQLite data through a loopback-only, token-guarded API by default, so profile edits, company
actions, campaigns, and refreshed matches appear without rebuilding Vite. Settings
can upload or replace up to three résumés, select preferred job markets and worldwide-remote intent,
or explicitly reset intent from the stored résumé; résumé-derived skills, seniority,
and experience remain read-only facts.

`python -m jobscope --config /data/config.yaml serve --hosted` is the opt-in
container entry point for the same single-user workspace. It is **not** a public
server: hosted mode requires `JOBSCOPE_PUBLIC_ORIGIN`, a Cloudflare Access JWT on
every non-health request, an origin reachable only through a validating Cloudflare
Tunnel, `JOBSCOPE_CF_ACCESS_TEAM_DOMAIN` plus `JOBSCOPE_CF_ACCESS_AUD` for
in-process JWT signature/issuer/audience validation, one application replica, and
a persistent `/data` volume. Hosted builds
self-remove the Pages service worker and expose an explicit Access sign-out. Optional
automation requires a separate 32+ character `JOBSCOPE_AUTOMATION_TOKEN`; the
manual-only `hosted-ops.yml` and `hosted-publish.yml` workflows use fixed-purpose
routes rather than the browser campaign API. The private service encrypts the Pages
snapshot before returning it; GitHub Actions never receives the plaintext dashboard
or its passphrase. See
[OPERATIONS.md](OPERATIONS.md#private-hosted-control-plane) before deploying it.
No hosted instance, schedule, secret, or data migration is created automatically.

Accounts without a Cloudflare-managed custom zone can deploy the zero-dependency
`cloudflare/worker.mjs` proxy to one stable `workers.dev` route, disable preview URLs,
and enable Cloudflare Access on that route. The Worker requires the Access assertion,
strips the Access cookie, and forwards the assertion to the Railway origin for full
signature/issuer/audience verification.

GitHub automation does not require a paid Access service token. Deploy the separate
`cloudflare/automation-worker.mjs` on the Workers free allowance with preview URLs disabled. It
accepts only the four fixed automation routes, validates the GitHub-held automation token, and adds
a distinct Worker-to-Railway edge token. Railway requires both tokens and the exact automation
Worker Origin; the browser workspace remains behind Access unchanged.

GitHub Pages is an encrypted **read-only snapshot**, not the interactive backend.
After unlock, Outreach can link to `VITE_JOBSCOPE_PRIVATE_ORIGIN`; mutations still run
only in the Access-protected workspace. Actions remain useful for scheduled PC-off
inbox scans, encrypted database backup, queued Pages mutations, and publication. Local
Scan Gmail updates SQLite only; publication is an explicit script or `jobscope refresh`
operation.

## Publish to GitHub Pages (view on mobile)

The published dashboard is the **Vite/React app** in `web/`. Its public JavaScript embeds an
**empty shell**; all roles, monitored companies, review decisions, contacts, profile,
applications, and reconciliation audit/recovery data live only in the separately fetched
AES-256-GCM `site.enc.json` payload:

```bash
python -m jobscope dashboard --emit-json --public   # -> data/dashboard.public.json (redacted)
```

`scripts/publish.ps1` (Windows) / `scripts/publish.sh` (macOS/Linux) emit that redacted
payload, bake it into the web app, `npm run build`, and publish `web/dist` to this
repo's **`gh-pages` branch**, which GitHub Pages serves. `main` is never touched and
your database never leaves your machine. Requires Node.js/npm. One-time setup:

1. Run the publish script once by hand to push the first build to `gh-pages` and cache
   your git credential.
2. Enable Pages: **Settings → Pages → Deploy from a branch → `gh-pages` / root**.
   The dashboard is then live at `https://<user>.github.io/jobscope/`.
3. Auto-refresh (Windows): `scripts/register-publish-task.ps1` registers a daily
   Scheduled Task that re-builds and pushes while you're logged on.

**One-click refresh.** Double-click `scripts/refresh-and-publish.cmd` (Windows) to rerun
the tool and update the live site in one step — it refreshes your data
(`scan → match → inbox`), rebuilds the redacted dashboard, and pushes it to `gh-pages`.
Equivalent to `scripts/publish.ps1 -Refresh -Force` (or `scripts/publish.sh --refresh --force`);
add `-NoScan` / `--no-scan` for a quick applications-only refresh that skips the job scan.
The unlocked Pages app can queue Save/Dismiss/company-monitor actions in browser storage. With
the optional fine-grained GitHub token connected, **Sync N** sends one bounded action batch to
`refresh.yml`; changes clear only after the encrypted DB and site republish successfully.

**Private applications on your phone (encrypted).** To view your applications remotely
without exposing them, publish them **end-to-end encrypted** into the dashboard's
**Applications** tab: `scripts/publish.ps1 -Refresh -Encrypted -Force` (or double-click
`scripts/refresh-and-publish-secure.cmd`). You're prompted for a passphrase; the
un-redacted data is encrypted with **AES-256-GCM** and only the encrypted blob is
published, so it's safe on a public URL. Open `https://<user>.github.io/jobscope/` on
your phone, open the **Applications** tab, enter the passphrase, and it decrypts **in
your browser** — nothing is sent anywhere. Use a **long** passphrase (4–5 random words);
offline it's the only thing protecting your history. For scheduled runs the passphrase
can come from `$env:JOBSCOPE_APPS_PASSPHRASE` (never committed).

> GitHub Pages is **public**. Only the redacted dashboard — and, with `-Encrypted`, an
> AES-256-GCM-encrypted applications blob (useless without your passphrase) — is published.

Publication builds are process-locked and isolated in a temporary directory. Before
anything reaches `gh-pages`, the scripts validate the empty public shell, encrypted
envelope, ciphertext hash, private-data absence, and a deployment manifest. Run the
same gate without pushing with `scripts/publish.ps1 -Encrypted -VerifyOnly -Force` or
`scripts/publish.sh --encrypted --verify-only --force`. See [OPERATIONS.md](OPERATIONS.md)
for encrypted snapshot recovery, key rotation, failed-stage repair, and rollback.

## Multi-resume matching

Import several base resumes and jobscope auto-picks the best-fitting one per job,
then tailors from it:

```bash
python -m jobscope resume import research.md   --name research
python -m jobscope resume import consulting.md --name consulting
python -m jobscope match          # each job records which base scored highest
```

## Search profiles (remote + on-site)

Search profiles filter every selected company board by market and work mode. Add
`search.profiles` when you want both worldwide-remote and specific on-site markets:

```yaml
search:
  terms: ["security engineer", "product security"]
  profiles:
    - name: "remote"
      location: "Remote"
      is_remote: true
    - name: "onsite-local"
      location: "India"       # or a city, e.g. "Pune, Maharashtra"
      is_remote: false
      country_indeed: "India"
  companies:
    - databricks
    - "Acme|lever|acme"
```

Results are de-duplicated by URL, so overlapping profile filters do not create duplicates.
Leave `profiles: []` to use the base market. Jobscope does not scrape LinkedIn, Indeed,
Glassdoor, Google Jobs, arbitrary careers pages, or logged-in accounts.

## Seniority & experience level ("stop showing me senior roles")

Security listings skew senior, so a level-agnostic search returns lots of Senior/Staff/
Principal roles. jobscope curbs that **deterministically** (no AI needed):

```yaml
match:
  target_seniority: "junior"   # "" = infer from your resume; else intern/junior/mid/senior/staff
filters:
  max_years_experience: 3      # 0 = off; else Skip roles that clearly ask for more
```

- **`target_seniority`** sets the level you're aiming at. The seniority score is
  **asymmetric** — a role *above* your target is penalized hard, being over-qualified
  only mildly. It reads the title, LinkedIn's structured "Seniority level", and numeric
  codes (`Sr.`, `II`/`III`, `L5`, `IC4`).
- **`max_years_experience`** is a hard cap: a posting implying more years than this
  (Senior≈4y, Staff≈6y, Principal≈8y, or explicit "5+ years") is forced to `Skip`
  with a reason. On a real 584-job scan, `junior` + cap `3` moved **353 of 360**
  senior-ish titles out of the good tiers.

For postings with **no** level cue at all (plain title, no stated years), an optional
AI/quorum tie-breaker can classify them — see *Free AI backends* below.

## Filters (clearance / sponsorship / block-list)

Set `filters` in `config.yaml` to force irrelevant jobs to `Skip` with a reason.
Handy if you need visa sponsorship or want to avoid US-clearance-only roles:

```yaml
filters:
  needs_sponsorship: true   # drop roles that state "no visa sponsorship"
  exclude_clearance: true   # drop US security-clearance / citizenship-only roles
  block_companies: ["SomeStaffingAgency"]
  block_keywords: []
  max_age_days: 30
```

## Configuration

Everything lives in `config.yaml` (copy from `config.example.yaml`). Secrets go in
`.env` (copy from `.env.example`). See both files for the full annotated set of
options: search sites/terms, scoring weights, enrichment toggles, AI provider, and
SMTP for email summaries.

## Optional local AI

AI is optional, off by default, and **advisory only**. The first supported activation is a pinned
local model served by [Ollama](https://ollama.com) over loopback:

```yaml
ai:
  enabled: true
  provider: ollama
  base_url: "http://127.0.0.1:11434/v1"   # loopback + /v1 only; any key disables the route
  model: "qwen2.5:7b-instruct-q4_K_M"     # must also appear in ai.local_models
```

Every call names an exact purpose from `ai.local_purposes`, and one shared per-run budget bounds
calls, input characters/tokens, reserved output tokens, retries, fan-out, and wall time. When the
budget is exhausted, a route is disallowed, or output fails schema/length/grounding validation, the
deterministic result is used and **no HTTP request is made**. Hosted `serve --hosted` disables AI
outright, and quorum routes are rejected because their rounds/retries cannot share that budget.

Remote OpenRouter stays off until you add an explicit per-purpose model/provider allowlist under
`ai.remote.purposes`; requests then pin `order`/`only`, `allow_fallbacks: false`,
`require_parameters: true`, `data_collection: deny`, and `zdr: true`. Résumé tailoring, application
answers, outreach drafts, and coverage advice are local-only and never eligible for remote routing.

### What AI may and may not change

AI can suggest a company-brief bullet, a summary/cover/outreach draft, a coverage note, or a
seniority opinion. It **cannot** change a score, tier, resume routing, JD coverage percentage, inbox
signal, application status, send eligibility, or approved outbound content — those stay deterministic:

```yaml
match:
  ai_seniority_tiebreak: true   # print an advisory note for ambiguous postings only
  ai_tiebreak_max_calls: 0      # 0 = unbounded; else cap advisory calls per match run
```

## Responsible use

jobscope favors a *filter*, not spray-and-pray: it helps you find the few roles worth
your time and prepares strong, tailored applications you review before sending. Respect
the Terms of Service of any site you interact with. Referral discovery uses only public
data and search links — no scraping of private profiles, no email harvesting.

## License

MIT — see [LICENSE](LICENSE).
