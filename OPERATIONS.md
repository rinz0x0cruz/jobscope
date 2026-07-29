# Jobscope Operations

This runbook covers the scheduled refresh, encrypted state, publication, recovery,
and rollback paths. Jobscope remains a single-user, local-first SQLite application;
these controls make that linear pipeline fail closed and observable.

## Preflight

Run the offline readiness check before enabling a schedule or after changing config:

```bash
python -m jobscope doctor
```

Errors block a reliable run. Warnings identify optional readiness gaps such as a
missing publication passphrase or an unhealthy ATS
source. The command never opens a network connection or prints secret values.

Install Python dependencies from `requirements.lock` and web dependencies with
`npm ci`. Regenerate the Python lock only when intentionally updating dependencies:

```bash
python -m pip install "pip<25" pip-tools==7.5.0
python -m piptools compile requirements.txt --output-file requirements.lock \
  --resolver=backtracking --strip-extras --allow-unsafe
```

Review both `requirements.txt` and `requirements.lock` in the same change.

## Activation Readiness

`doctor` answers "is this install healthy". `readiness` answers the narrower
question "is this lane safe to switch on right now":

```bash
python -m jobscope readiness              # report every lane
python -m jobscope readiness --json       # machine-readable report
python -m jobscope readiness --require smtp   # exit nonzero until SMTP is ready
```

The report is read-only. It opens no network connection and, apart from an
explicit `--canary`, writes nothing. It prints lane names, states, blocker codes,
evidence age, and config hashes only: never an address, secret, message body,
resume text, or prompt.

States are `disabled`, `configured`, `preflight_passed`, `canary_passed`,
`active`, and `paused`. Dependencies run storage before inbox and SMTP, both
before outreach, and outreach before the scheduler. AI is never a dependency of
any lane, so an AI-off install reports fully ready. A disabled optional lane is
healthy, not an error: it only fails the exit code under `--require`.

Readiness invalidates itself automatically. Missing, failed, or 30-day-old canary
evidence, a changed lane config hash, a different artifact ID, an unhealthy
dependency, or an unresolved delivery outcome each produce a blocker code and
push the lane back below `canary_passed`.

`--require LANE` exits `0` only when that lane and every dependency hold current
passing evidence, `1` when anything blocks, and `2` for an unknown lane. Use it
as the gate in front of any activation step below.

### Activation and rollback per lane

Run `python -m jobscope readiness --require <lane>` after every step; stop at the
first nonzero exit. Activate one lane at a time, never two in the same change.

| Lane | Activate | Roll back |
| --- | --- | --- |
| storage | Restore or create the database, then confirm `refresh` succeeds once. | Restore the last verified snapshot per [Snapshot Recovery](#snapshot-recovery). |
| discovery | Add company monitors, resolve them, then run `refresh`. | Pause the monitors; cached jobs stay readable. |
| inbox | Set `inbox.accounts` and the app password, run `readiness --canary inbox --account <address>`, then enable `inbox.enabled`. | Disable `inbox.enabled`, stop the tick schedule, revoke the app password. |
| smtp | Set `email.*` and the password env var, run `readiness --canary smtp`, then enable `email.enabled`. | Disable `email.enabled` and revoke the credential; queued drafts stay unsent. |
| outreach | Confirm `campaign ready`, resolve any delivery blocker, then enable `apply.outreach.enabled`. | Disable `apply.outreach.enabled`; approved drafts remain stored and unsent. |
| scheduler | Hosted: follow [Scheduled Automation Clock](#scheduled-automation-clock). Local: register the task per [Local Outreach Scheduler And Repair](#local-outreach-scheduler-and-repair). | Set the kill switch, then remove the cron; every command stays available manually. |
| ai | Enable `ai.enabled` with an allowlisted local model and purpose. | Disable `ai.enabled`; deterministic output is unchanged because AI is advisory only. |

The inbox and SMTP canaries are the only live checks. The inbox canary is the
non-mutating `readonly`/`BODY.PEEK` probe described in
[Inbox Activation Canary](#inbox-activation-canary). The SMTP canary is a
preflight that authenticates and quits without issuing `MAIL`, `RCPT`, or `DATA`,
so it can never deliver a message. Both record one evidence row in `meta` under
`readiness:canary:<lane>` and change nothing else.

If a lane is rolled back, its readiness evidence stays on disk but the config
hash changes as soon as you edit that lane, so a later reactivation requires a
fresh canary rather than inheriting stale proof.
Scheduled Automation Clock

The `jobscope-automation` Cloudflare Worker is the only autonomous writer.
`refresh.yml` has no `schedule:` trigger, `hosted-ops` stays manual, and the
local Windows task in
[Local Outreach Scheduler And Repair](#local-outreach-scheduler-and-repair) is
for local-only installs. Never run the local task and the hosted cron against
the same database.

Platform cron is treated as at-least-once, possibly late, and occasionally
skipped. Every slot therefore carries its own identity:

- The Worker sends `X-Jobscope-Slot-Time` (the UTC `scheduledTime`) and
  `X-Jobscope-Slot-Period`. It never sends a slot ID.
- The backend re-derives the ID from the operation version plus that instant and
  claims it with one `BEGIN IMMEDIATE` compare-and-set, so simultaneous or
  retried deliveries of the same slot execute once and share one result.
- Outcomes are `claimed`, `duplicate` (200, returns the original result),
  `superseded` (200, an out-of-order slot), `stale` (200, later than 30 minutes),
  `busy` (409, other work in progress), `disabled` (503), and `invalid` (400).
- A slot dated more than five minutes in the future is `invalid`. Accepting one
  would make every later real slot look superseded, so a skewed clock or a forged
  header cannot wedge the schedule.
- Missed slots are counted, not replayed: one latest execution runs and records
  `missed` and `lateness_ms`.
- Only `17 */3 * * *` (refresh) and `*/30 * * * *` (tick) are recognized. Any
  other pattern throws instead of guessing an operation.
- The Worker retries only genuine faults. `400`, `401`, and `403` throw loudly
  because retrying cannot fix a credential or identity mismatch; `503` is a
  deliberate refusal and is final for that slot; any other `5xx` throws so the
  platform retries the same scheduled time.

Worker configuration: `ORIGIN_URL` (the private origin), `WORKER_ORIGIN` (this
Worker's own origin, sent as `Origin`), `AUTOMATION_TOKEN`, `EDGE_TOKEN`, and
`AUTOMATION_MODE`. `AUTOMATION_MODE` defaults to `observe`, in which a scheduled
slot calls only the read-only status path and mutates nothing.

### Activation

Do not skip a step; each one must pass before the next.

1. Confirm `python -m jobscope readiness --require smtp` and `--require outreach`
   exit zero, and that no target is stuck in `delivery_unknown`.
2. Deploy the backend with slot claiming, heartbeat, and kill switch while
   `triggers.crons` is still `[]`. No slot can exist yet.
3. Deploy the Worker with `AUTOMATION_MODE=observe`, then add one cron pattern to
   `triggers.crons` in `cloudflare/automation-wrangler.jsonc` and deploy.
4. Cron changes are not instant. Wait for at least two scheduled slots and
   confirm arrival from `wrangler tail` rather than assuming a fixed delay.
5. Observe at least three slots. Each must reach the status path and leave the
   database unchanged.
6. Set `AUTOMATION_MODE=active` with `email.enabled` false. Confirm the refresh
   slot runs, then check the heartbeat.
7. Run one tick slot with no eligible recipient and confirm nothing was sent.
8. Only then schedule one manually approved controlled-mailbox canary.

### Verification

`GET /api/automation/status` returns a `heartbeat` block for an independent
read-only observer: `state`, `operation`, `scheduled`, `finished`, `code`,
`run_id`, `duration_ms`, `lateness_ms`, `missed`, `artifact`, `age_ms`,
`running`, `disabled`, and `stale`. It contains no payload, address, or body.

`stale` is true when no terminal heartbeat exists at all, or when the last one is
older than twice its own period. A heartbeat that lags because a write was lost
also reads as stale, which is the safe direction.

### Kill switch and rollback

Stop mutation first, remove the schedule second. Cron removal propagates on
Cloudflare's schedule; the kill switch does not.

1. Set `JOBSCOPE_AUTOMATION_DISABLED=1` on the backend, or set the `meta` key
   `automation:disabled` to `1` for an immediate stop without a redeploy. Every
   new slot is refused with `disabled` while in-flight work finishes normally.
2. Deploy `"triggers": { "crons": [] }` and set `AUTOMATION_MODE=observe`.
3. Wait past two scheduled periods and confirm from `wrangler tail` and the
   heartbeat that no later slot was accepted. Verify; do not assume a bound.
4. Only after that verification may another clock take ownership. Bump
   `OPERATION_VERSION` in `jobscope/deliver/automation.py` when the new owner
   must not be deduplicated against the previous owner's slot history.

## Private Hosted Control Plane

The repository contains an opt-in hosted server contract, an immutable multi-stage `Dockerfile`,
`railway.json`, and a Linux CI container smoke test. No Railway/Cloudflare resources, schedules,
secrets, or data are created by these files.

Required topology:

1. Let the green `container` CI job publish its already-smoke-tested image to GHCR. Configure exactly
   one Jobscope service from the immutable `ghcr.io/<owner>/jobscope@sha256:<digest>` reported in the
   job summary and mount one volume at `/data`. For an image-source
   service, mirror `railway.json`'s `/healthz`, 30-second timeout, and bounded on-failure restart settings.
   The image builds SQLite 3.53.4 from the checksum-pinned official archive and verifies its exact
   `sqlite_source_id()`. Hosted startup rejects any other runtime identity and audits an existing database
   with full `integrity_check` and `foreign_key_check` before constructing the server.
2. Put sanitized configuration at `/data/config.yaml` with `output.db_path: /data/jobscope.db`.
3. Set only secret values in Railway variables. Keep `ai.enabled`, `email.enabled`, and
   `apply.outreach.enabled` false for the canary. Generate a distinct 32+ character
   `JOBSCOPE_AUTOMATION_TOKEN`; give the same value to the hosted service and GitHub Actions. Set
   `JOBSCOPE_CF_ACCESS_TEAM_DOMAIN` to `https://<team>.cloudflareaccess.com`, set
   `JOBSCOPE_CF_ACCESS_AUD` to the Access application's Audience tag, and store
   `JOBSCOPE_APPS_PASSPHRASE` only in the hosted secret manager. Generate a separate long random
   `JOBSCOPE_BACKUP_KEY` and store the same value in Railway and repository Actions secrets. Never reuse
   the dashboard passphrase, database snapshot key, automation token, or edge token as the backup key.
4. Route a Cloudflare Tunnel hostname to the private service on port 8799. Enable **Protect with
   Access** so `cloudflared` validates the Access JWT and forwards `Cf-Access-Jwt-Assertion`.
5. Set `JOBSCOPE_PUBLIC_ORIGIN` to that exact HTTPS origin. Access must deny by default and allow
   only the intended identity. `/healthz` is the only application route that does not require the
   Access header.

If the account has no Cloudflare-managed zone, use the zone-less edge in `cloudflare/`:

1. Deploy `jobscope-private` to its single `workers.dev` route with `preview_urls: false`.
2. Store the Railway service URL as the Worker's `ORIGIN_URL` secret.
3. In Workers & Pages > jobscope-private > Settings > Domains & Routes, enable Cloudflare Access
   for `workers.dev` and allow only the intended email identity.
4. Copy that Access application's Audience tag into Railway as `JOBSCOPE_CF_ACCESS_AUD`, set
   `JOBSCOPE_CF_ACCESS_TEAM_DOMAIN`, and set `JOBSCOPE_PUBLIC_ORIGIN` to the `workers.dev` URL.
5. Keep the Railway origin domain undocumented and rely on in-process JWT validation as the
   mandatory bypass defense. The Worker also rejects missing assertions and strips Access cookies.

Use the separate free automation edge instead of a card-gated Access service token:

1. Deploy `cloudflare/automation-worker.mjs` as `jobscope-automation` on its single `workers.dev`
   route with preview URLs disabled. Do not enable Access on this route.
2. Give the Worker three secrets: the Railway `ORIGIN_URL`, the existing 32+ character
   `AUTOMATION_TOKEN` shared with GitHub, and a different random 32+ character `EDGE_TOKEN` shared
   only with Railway.
3. Set Railway `JOBSCOPE_AUTOMATION_ORIGIN` to the automation Worker origin and
   `JOBSCOPE_AUTOMATION_EDGE_TOKEN` to the same edge token. Railway accepts automation only when
   the caller supplies both tokens and the exact automation Origin.
4. Configure GitHub variable `JOBSCOPE_AUTOMATION_ORIGIN` plus secret
   `JOBSCOPE_AUTOMATION_TOKEN`. The Worker exposes only the six fixed `/api/automation/*` routes,
   rejects every other route/method, strips caller-controlled edge and Access headers, and adds the
   origin-only edge token. This path uses the normal Workers free allowance and requires no card.

Do not migrate real data yet. Start the immutable image with an empty volume, verify unauthenticated
requests are denied, sign in through Access, make a temporary profile change, restart the same image,
and prove the change, `PRAGMA integrity_check`, and zero-row `PRAGMA foreign_key_check` survive. Confirm **Sign out** clears the live workspace,
`sw.js` unregisters itself instead of precaching, and the security headers deny framing. The CI
`container` job performs the equivalent image/volume/header/automation smoke on Linux.

Cut over with one writer:

1. Pause local refresh/outreach tasks and disable `.github/workflows/refresh.yml`; record the last
   encrypted `data` and Pages commits.
2. Stop the empty canary. Back up the local full database and profiles, run
   `python -m jobscope.core.snapshot data/jobscope.db`, and record file hashes and table counts.
   This is the one-time pre-enforcement audit: it must report a healthy database and zero foreign-key
   violations. Do the same read-only audit against the hosted volume before replacing its image.
3. Upload the validated database, `profiles/`, and sanitized config to `/data`; retain the local copy
   untouched. Stored résumé source paths may be Windows-absolute: re-upload every named résumé through
   hosted Settings so it lands under `/data/resumes`, then review and re-approve affected drafts. Run
   `campaign ready`; it must report no missing/changed approved attachment. Start the same tested image,
   then compare jobs, applications, mail events, reviews, profiles, campaigns, and SQLite integrity.
4. Add Gmail credentials only after those checks pass. Run one manual refresh with SMTP/outreach still
   disabled and confirm the retained stage timings. Do not enable a hosted schedule while the old
   workflow can still write its independent database.
5. Configure repository variables `JOBSCOPE_HOSTED_ORIGIN` and `JOBSCOPE_AUTOMATION_ORIGIN` plus
   the protected Actions value `JOBSCOPE_AUTOMATION_TOKEN`. Run `hosted-ops.yml` manually with
   `refresh`; it calls only
   `/api/automation/refresh` and polls the exact durable run ID. Run `hosted-publish.yml` manually;
   it fetches only the hosted-encrypted snapshot, then reuses the shared empty-shell builder and
   artifact verifier. The workflow never receives the plaintext payload or passphrase. Add schedules
   only after both manual workflows and the restore drill pass.
6. Run `hosted-backup.yml`. It downloads only a JSDB-encrypted full database and non-secret manifest,
   independently decrypts and validates it on the runner, uploads the two verified files as a uniquely
   named 90-day Actions artifact, and only then acknowledges that exact backup ID and ciphertext hash.
   Hosted outreach ticks remain disabled after every process start and after every failed or unacknowledged
   backup. Keep Railway daily/weekly/monthly volume backups enabled as an independent second layer.

Before declaring cutover complete, run `hosted-restore-drill.yml` with the published safe image digest,
successful backup workflow run ID, and exact artifact name. The drill downloads that immutable generation,
restores it into a disposable directory using the pulled digest, runs `doctor`, starts in
`JOBSCOPE_RECOVERY_MODE=1`, verifies the encrypted principal read API, proves refresh/tick are disabled,
restarts, and repeats the checks. Its summary records artifact digest, backup ID, restored-data age, and
measured recovery time. These values are evidence, not an advance RPO/RTO claim.

Rollback disables hosted triggers and outbound effects, stops the hosted service, and restores the selected
verified full generation with the retained safe image digest. Once the first safe deployment and drill pass,
record that digest as the rollback floor and remove the vulnerable image from every deployment/rollback target.
Never roll back to an affected SQLite image. Do not delete old encrypted generations, Railway backups, or
secrets until both scheduled operation and restore evidence pass.

The hosted workflows are intentionally `workflow_dispatch`-only. `hosted-ops.yml` has read-only
repository permission and can invoke either refresh or one reply-check/send tick. `hosted-publish.yml`
alone has `contents: write` so it can push one verified encrypted artifact to `gh-pages`.
`hosted-backup.yml` has read-only repository permission and writes its encrypted generation only to the
Actions artifact service; `hosted-restore-drill.yml` has read-only repository/package/artifact access.
Backup, publish, refresh, and tick share one concurrency group. Never grant the automation service identity access to `/api/campaigns/action`.
Any in-progress or unknown SMTP outcome halts all subsequent delivery across campaigns and processes;
resolve it in the private workspace before running another tick.

## Cloud Refresh Invariants

The scheduled workflow in `.github/workflows/refresh.yml` requires an existing
`data` branch. It will not initialize a replacement database. Before inbox or match
work begins, it must:

1. Fetch the exact `data` branch tip.
2. Decrypt `jobscope.db.enc`, or the retained `jobscope.db.previous.enc` fallback.
3. Validate SQLite magic, full `PRAGMA integrity_check`, zero-row `PRAGMA foreign_key_check`, and Jobscope's stable tables.
4. Record the restored commit SHA.

Company-first ordering is fixed: restore/validate DB → idempotent `companies seed` → apply an optional
validated mutation batch → scan active monitored portals → inbox → match → review sync → save encrypted DB → verify/publish. Monitor
errors are optional/degraded and fail closed: only a complete non-empty board may mark linked jobs closed.

Pages mutations require the existing fine-grained Actions read/write token. Save/Dismiss/company changes are
collapsed by entity in browser storage and dispatched together. An active workflow or failed run keeps the
queue intact; only a successful refresh clears it. The workflow receives JSON through an environment variable
and file, then validates it in Python—never through shell evaluation.

Operational checks:

```bash
python -m jobscope companies list
python -m jobscope companies scan
python -m jobscope reviews list --state pending
python -m jobscope doctor   # warns on unresolved portals and unhealthy monitor sources
```

After refresh, it validates SQLite again, encrypts and decrypts a round-trip copy,
then pushes with `--force-with-lease` against the restored SHA. A concurrent or
unexpected branch change fails instead of being overwritten. The ciphertext that
successfully restored is retained as the next `jobscope.db.previous.enc`.

Before encryption, `jobscope.core.snapshot --cloud-copy` creates a consistent SQLite
backup and writes an allowlisted read-only campaign projection to
`meta.campaign:snapshot:v1`. It then empties campaign, target, run, and suppression
tables, enables secure deletion, and vacuums free pages. The projection carries batch,
recipient, subject, state, schedule, and delivery/reply summary only; it excludes bodies,
approval/resume hashes, résumé paths, raw message IDs, suppression internals, and send
controls. The original local database is never modified by this redaction step.

Seed the branch once from a validated local database:

```powershell
$env:JOBSCOPE_DB_KEY = '<same value as the repository secret>'
./scripts/seed-cloud-db.ps1
```

The seed script validates SQLite, verifies encryption byte-for-byte, and creates
both current and fallback generations.

## Reconciliation Audit And Recovery

The audit migration is additive. A pre-audit database gets one completed,
count-only `baseline_only` run with no fabricated decisions. The current database
state is the baseline; a historical transition cannot be reconstructed without a
matching snapshot.

Rehearse against a copy before migrating operational data:

```powershell
Copy-Item data/jobscope.db data/jobscope-audit-rehearsal.db
python -m jobscope --db data/jobscope-audit-rehearsal.db inbox --reclassify
python -m jobscope --db data/jobscope-audit-rehearsal.db inbox --reclassify
python -m jobscope --db data/jobscope-audit-rehearsal.db applications audit
```

The second reclassification must preserve the same active/tombstone sets and show no
unexplained mutation decisions. Inspect or recover against the selected database:

```bash
python -m jobscope applications audit
python -m jobscope applications audit --run <run_id>
python -m jobscope applications recover <job_id> --yes
```

Recovery is idempotent, records its own immutable run/decision, and marks the restored
row reconciliation-exempt. Run `jobscope doctor` after reconciliation; it warns on
stuck runs, orphan decisions, malformed tombstones, missing application links, and
large count drops using bounded IDs/counts only.

Detailed decisions follow `retention.reconciliation_audit_days` (default 730):

```bash
python -m jobscope purge --audit --older-than 730
python -m jobscope purge --applications
python -m jobscope purge --tombstones --yes
```

The first command retains run summaries and tombstones. Active-application purge also
retains tombstones. The final command is the separate, irreversible recovery-data
purge. Audit detail and tombstones persist to the encrypted `data` branch and encrypted
site payload only; workflow output contains aggregate counts, never individual email or
recruiter content.

## Snapshot Recovery

### Hosted full database

Use a successful `hosted-backup.yml` artifact for hosted recovery. Each immutable generation contains only
`jobscope.db.jsdb` and `manifest.json`; the encrypted file includes all writable campaign and application
state, unlike the redacted Pages/cloud-refresh snapshot. The manifest records the application artifact,
SQLite version/source ID, plaintext and ciphertext SHA-256, schema hash, table counts, and creation time.

Verify or restore a downloaded generation without replacing an existing database:

```bash
export JOBSCOPE_BACKUP_KEY='<separate long random key>'
python -m jobscope.core.backup verify path/to/generation
python -m jobscope.core.backup restore path/to/generation path/to/empty/jobscope.db
```

Restore refuses an existing destination. Creation uses SQLite's online backup API, converts the copy to
DELETE journal mode, validates it, encrypts it, verifies a decryption round trip, and atomically promotes the
generation. An interruption or disk-full error removes staging, preserves prior good generations, and clears
hosted outbound readiness. A later successfully retained and acknowledged generation restores readiness.
Use `hosted-restore-drill.yml` for the required pulled-image restart/read/outbound-disable rehearsal.

### Redacted cloud-refresh snapshot

If cloud restore fails, do not delete the `data` branch or rerun with an empty DB.

1. Download `jobscope.db.enc` and `jobscope.db.previous.enc` from the `data` branch.
2. Decrypt each locally with the repository's `JOBSCOPE_DB_KEY`:

   ```bash
   node scripts/crypt-file.mjs decrypt jobscope.db.enc recovered.db
   python -m jobscope.core.snapshot recovered.db
   ```

3. If only the fallback validates, preserve the failed current blob for diagnosis,
   replace local `data/jobscope.db` with the validated fallback, and reseed with
   `scripts/seed-cloud-db.ps1`.
4. If neither validates, restore a known local backup. Do not let the workflow create
   a new DB under the same branch.

Wrong keys, corrupted ciphertext, unsupported JSDB versions, and invalid SQLite all
fail closed. Keep `JOBSCOPE_DB_KEY` separate from the dashboard passphrase.

Cloud snapshots intentionally contain no campaign state. Replacing a local database
with a recovered cloud snapshot preserves jobs, applications, monitors, reviews, and
mail events, but yields empty campaign tables. Keep timestamped local database backups
if campaign drafts, approvals, schedules, or suppressions must be recoverable.

### Backup key rotation

1. Leave hosted tick disabled and retain at least one generation under the old key.
2. Set a new long random `JOBSCOPE_BACKUP_KEY` in Railway and repository Actions secrets.
3. Restart the service, run `hosted-backup.yml`, and verify its acknowledgement succeeds.
4. Run `hosted-restore-drill.yml` against the new generation and retained safe image digest.
5. Remove the old key only after recording the successful drill evidence.

## Local Outreach Scheduler And Repair

Registering `scripts/register-outreach-task.ps1` schedules `campaign tick` under the interactive user.
Each tick incrementally checks configured inboxes, reconciles replies, opt-outs, bounces, and complaints,
reports due approved work, and sends nothing. The task uses `MultipleInstances IgnoreNew`.

Build a follow-up review queue with `campaign followups --count N` or **Build follow-up queue** in
the local UI. This operation writes drafts only. Before approval and again before sending, Jobscope
checks that the source is still pending, `apply.followup_days` has elapsed since the latest action,
the application has not advanced or received a response, and any original recipient/thread is unchanged.

If Outreach reports **delivery unknown**, do not retry until checking the SMTP provider's Sent
folder for the stored Message-ID. Resolve it in the local UI as **Confirmed in Sent** or
**Confirmed not sent**. The latter returns it to Draft and clears approval, so an intentional retry
requires review and approval again. If a scheduler process dies while a send is claimed, the claim remains
locked for 15 minutes; the next tick then exposes it as delivery unknown for this same manual check. A generic same-domain reply is linked only when one unresolved
target exists for that domain; exact `In-Reply-To` matching always takes precedence.

Hard bounces create terminal recipient suppressions; complaints suppress recipient and domain. A transient
bounce blocks every later delivery until **Confirmed delivered** or **Confirmed hard bounce** is selected.
Duplicate provider events are retained once and ignored on replay. Use `campaign export-eml --target-id ID`
to review the exact MIME message with SMTP, inbox, and AI disabled.

## Key Rotation

### Database Key

1. Pause or disable the refresh schedule.
2. Decrypt the current snapshot with the old key and validate it.
3. Set a new long random `JOBSCOPE_DB_KEY` locally and in repository Secrets.
4. Reseed using the validated plaintext database.
5. Trigger one manual refresh and confirm restore, save, publish, and doctor output.
6. Remove the old key only after the new snapshot has completed a decrypt round trip.

### Dashboard Passphrase

1. Set a new `JOBSCOPE_APPS_PASSPHRASE` locally/keychain and in repository Secrets.
2. Run a no-push artifact check:

   ```powershell
   ./scripts/publish.ps1 -Encrypted -VerifyOnly -Force
   ```

   ```bash
   scripts/publish.sh --encrypted --verify-only --force
   ```

3. Publish once and verify that the new passphrase unlocks the site and the old one
   fails. Existing ciphertext does not need to remain decryptable after rotation.

## Publication And Rollback

Both publish scripts acquire `.jobscope-publish.lock`, build from temporary JSON and
ciphertext into a temporary Vite output directory, and invoke the shared artifact
verifier. They do not mutate `web/src/data` or `web/dist`. Publication is allowed only
after the verifier confirms:

- The baked dashboard is an empty public shell.
- The encrypted marker points to `site.enc.json`.
- The AES-GCM envelope has the supported version, KDF, and field lengths.
- The bundled ciphertext matches its source exactly.
- No private field/value serialization appears in text assets.
- `deployment-manifest.json` records the source commit and SHA-256 of every artifact.

The monitoring, audit, and local campaign migrations are additive. Follow-up support adds campaign
purpose plus target provenance, thread, sequence, and recipient-lock columns/indexes through
`ALTER TABLE ADD COLUMN`; back up the local SQLite file before the first upgraded run. Rolling code back
leaves their tables ignored but intact; it does not delete raw jobs, application
history, dismiss tombstones, company provenance, or local campaign rows. The previous
encrypted cloud DB generation remains the first recovery option for cloud-managed
state, but never for local-only campaigns. `search.companies` is retained as seed input for
`companies seed`, so a rollback to a build that still carried the direct ATS batch scan
will also still find its configuration.

Local data refresh and publication are independent. A successful scan/sync/match advances
`refresh:last_date`; only a verified encrypted publish advances
`publish:last_date`. If publication fails, current SQLite data remains available through
`jobscope serve`. Check `refresh:last_failed_stage` with `jobscope doctor`, repair the
stage, and rerun `jobscope refresh` to publish current data without rescanning (or use
`--force` to repeat every stage). `jobscope refresh --local-only` never publishes.

To roll back GitHub Pages, reset the disposable `gh-pages` branch to a previously
verified deployment commit and push it. Compare that commit's
`deployment-manifest.json` before rollback. Do not copy individual hashed assets
between deployments; treat each manifest and artifact directory as one unit.

## Source Health

ATS and inbox checks update the `source_health` table while the `runs` table
keeps history. Meanings:

- `ok`: complete successful result.
- `empty`: successful source with zero jobs; valid and non-destructive.
- `partial`: some postings parsed; never authoritative for closing jobs.
- `recovered`: Gmail or IMAP succeeded after bounded recovery/retry.
- `invalid`, `error`, `unsupported`: unhealthy; never authoritative for closing jobs.

The weekly `.github/workflows/ats-canary.yml` probes every curated board. Valid empty
boards pass. Partial, malformed, unsupported, or failed mappings fail the workflow
and identify the exact provider/slug. Probes run with bounded concurrency; each HTTP
attempt has a 12-second timeout and at most two capped retry delays, so third-party
rate limits can make a canary batch take several minutes without blocking other jobs.

New automatic sources require an explicit review before code/config activation: publisher-controlled public
API/feed documentation and permission basis, exact HTTPS request host, no authentication or evasion, typed
malformed/error/empty/partial behavior, non-destructive reconciliation tests, and canary coverage. Unknown
providers, Phenom, arbitrary careers HTML, and aggregator scraping stay quarantined.

The first inbox run after upgrading an older database may replay
`inbox.uid_recovery_days` because historical UID watermarks predate UIDVALIDITY
tracking. Message-ID deduplication makes this replay non-destructive. A future
`ANALYSIS_VERSION` bump intentionally leaves older job-analysis rows in place and
reads only the current version; rerun `jobscope enrich` to populate the new version.

## Inbox Activation Canary

Use a dedicated job-search Gmail account with one pre-existing benign application message. Keep SMTP,
AI, outreach, and snippet persistence disabled. Run:

```bash
python -m jobscope inbox-canary --account canary@example.com
```

The command forces verified TLS, a 30-second connection timeout, `readonly=True`, `BODY.PEEK`, `dry_run`,
and one explicitly selected account. It creates a throwaway SQLite database outside the configured data path,
prints the classification, asserts that no mail event or UID/UIDVALIDITY marker was written, and deletes the
database on exit. Confirm in Gmail that the benign message remains unread and unmodified. Do not use a
production mailbox fixture or enable SMTP for this check.

Rollback: disable `inbox.enabled`, stop any inbox/tick schedule, and revoke the dedicated app password in the
Google account. This removes network access immediately and needs no data migration. Keep the account disabled
until the certificate, hostname, timeout, UID-search, and fetch failure tests pass again.

## CI And Release Gate

Pull requests must pass:

- Python 3.11 and 3.12 lint, offline selftest, unit tests, and Node crypto tests.
- Web ESLint, TypeScript, Vitest, and a production locked-shell build.
- A real encrypted `publish.sh --verify-only` artifact build.
- Secret scan and repository compliance checks.

Do not publish or enable scheduled refresh after a failed required check. Live ATS
canaries are intentionally scheduled rather than part of pull requests because they
depend on third-party availability.