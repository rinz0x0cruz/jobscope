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
missing publication passphrase, a saturated JobSpy result cap, or an unhealthy ATS
source. The command never opens a network connection or prints secret values.

Install Python dependencies from `requirements.lock` and web dependencies with
`npm ci`. Regenerate the Python lock only when intentionally updating dependencies:

```bash
python -m pip install "pip<25" pip-tools==7.5.0
python -m piptools compile requirements.txt --output-file requirements.lock \
  --resolver=backtracking --strip-extras --allow-unsafe
```

Review both `requirements.txt` and `requirements.lock` in the same change.

## Private Hosted Control Plane

The repository contains an opt-in hosted server contract, an immutable multi-stage `Dockerfile`,
`railway.json`, and a Linux CI container smoke test. No Railway/Cloudflare resources, schedules,
secrets, or data are created by these files.

Required topology:

1. Let the green `container` CI job publish its already-smoke-tested image to GHCR. Configure exactly
   one Jobscope service from the immutable `ghcr.io/<owner>/jobscope@sha256:<digest>` reported in the
   job summary, with no Railway public domain, and mount one volume at `/data`. For an image-source
   service, mirror `railway.json`'s `/healthz`, 30-second timeout, and bounded on-failure restart settings.
2. Put sanitized configuration at `/data/config.yaml` with `output.db_path: /data/jobscope.db`.
3. Set only secret values in Railway variables. Keep `ai.enabled`, `email.enabled`, and
   `apply.outreach.enabled` false for the canary.
4. Route a Cloudflare Tunnel hostname to the private service on port 8799. Enable **Protect with
   Access** so `cloudflared` validates the Access JWT and forwards `Cf-Access-Jwt-Assertion`.
5. Set `JOBSCOPE_PUBLIC_ORIGIN` to that exact HTTPS origin. Access must deny by default and allow
   only the intended identity. `/healthz` is the only route that does not require the Access header.

Do not migrate real data yet. Start the immutable image with an empty volume, verify unauthenticated
requests are denied, sign in through Access, make a temporary profile change, restart the same image,
and prove the change and `PRAGMA quick_check` survive. The CI `container` job performs the equivalent
image/volume/header smoke on Linux.

Cut over with one writer:

1. Pause local refresh/outreach tasks and disable `.github/workflows/refresh.yml`; record the last
   encrypted `data` and Pages commits.
2. Stop the empty canary. Back up the local full database and profiles, run
   `python -m jobscope.core.snapshot data/jobscope.db`, and record file hashes and table counts.
3. Upload the validated database, `profiles/`, and sanitized config to `/data`; retain the local copy
   untouched. Start the same tested image, then compare jobs, applications, mail events, reviews,
   profiles, campaigns, and SQLite integrity.
4. Add Gmail credentials only after those checks pass. Run one manual refresh with SMTP/outreach still
   disabled and confirm the retained stage timings. Do not enable a hosted schedule while the old
   workflow can still write its independent database.
5. After the provider environment and Access service credentials exist, replace the old cloud writer
   with a manual, approval-gated trigger that calls `/api/token`, POSTs `/api/refresh` with the exact
   Origin, and polls `/api/status`. Add the three-hour schedule only after the manual trigger passes.

Before declaring cutover complete, restore a Railway volume backup into a temporary service, run
`PRAGMA quick_check`, and compare the recorded counts. Rollback disables hosted triggers, stops the
hosted service, restores the untouched local backup, and re-enables the recorded previous workflow.
Do not delete old snapshots or secrets until both scheduled refresh and restore evidence pass.

## Cloud Refresh Invariants

The scheduled workflow in `.github/workflows/refresh.yml` requires an existing
`data` branch. It will not initialize a replacement database. Before inbox or match
work begins, it must:

1. Fetch the exact `data` branch tip.
2. Decrypt `jobscope.db.enc`, or the retained `jobscope.db.previous.enc` fallback.
3. Validate SQLite magic, `PRAGMA quick_check`, and Jobscope's stable tables.
4. Record the restored commit SHA.

Company-first ordering is fixed: restore/validate DB → idempotent `companies seed` → apply an optional
validated mutation batch → scan active monitored portals → run broad discovery only when its 24-hour marker
is due (or `full_scan=true`) → inbox → match → review sync → save encrypted DB → verify/publish. Monitor
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
backup, empties the local-only campaign, target, run, and suppression tables, enables
secure deletion, and vacuums free pages. The encrypted `data` branch therefore cannot
expose or restore recruiter-campaign recipients, drafts, approvals, schedules, or
opt-outs, including follow-up source provenance and thread identifiers. The original
local database is never modified by this redaction step.

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

## Local Outreach Scheduler And Repair

Registering `scripts/register-outreach-task.ps1` first runs `campaign ready`, then schedules
`campaign tick` under the interactive user. Each tick incrementally checks configured inboxes,
reconciles replies/opt-outs, and sends at most one due approved email. The task uses
`MultipleInstances IgnoreNew`; it never force-sends or bypasses approval, quota, spacing, cooldown,
application-history, recipient-domain, résumé-hash, or suppression guards.

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
state, but never for local-only campaigns. `search.companies` is retained as
seed/fallback input, so old code can still run direct ATS scans during a rollback.

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

ATS, JobSpy, and inbox checks update the `source_health` table while the `runs` table
keeps history. Meanings:

- `ok`: complete successful result.
- `empty`: successful source with zero jobs; valid and non-destructive.
- `paged`: a ten-result JobSpy page committed and its next offset is ready; rerun `scan` to resume.
- `saturated`: JobSpy reached the configured per-cycle `results_wanted` cap; additional results may exist.
- `partial`: some postings parsed; never authoritative for closing jobs.
- `recovered`: Gmail or IMAP succeeded after bounded recovery/retry.
- `invalid`, `error`, `unsupported`: unhealthy; never authoritative for closing jobs.

The weekly `.github/workflows/ats-canary.yml` probes every curated board. Valid empty
boards pass. Partial, malformed, unsupported, or failed mappings fail the workflow
and identify the exact provider/slug. Probes run with bounded concurrency; each HTTP
attempt has a 12-second timeout and at most two capped retry delays, so third-party
rate limits can make a canary batch take several minutes without blocking other jobs.

The first inbox run after upgrading an older database may replay
`inbox.uid_recovery_days` because historical UID watermarks predate UIDVALIDITY
tracking. Message-ID deduplication makes this replay non-destructive. A future
`ANALYSIS_VERSION` bump intentionally leaves older job-analysis rows in place and
reads only the current version; rerun `jobscope enrich` to populate the new version.

## CI And Release Gate

Pull requests must pass:

- Python 3.11 and 3.12 lint, offline selftest, unit tests, and Node crypto tests.
- Web ESLint, TypeScript, Vitest, and a production locked-shell build.
- A real encrypted `publish.sh --verify-only` artifact build.
- Secret scan and repository compliance checks.

Do not publish or enable scheduled refresh after a failed required check. Live ATS
canaries are intentionally scheduled rather than part of pull requests because they
depend on third-party availability.