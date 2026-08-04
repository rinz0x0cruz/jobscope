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
| scheduler | Register the task per [Local Outreach Scheduler And Repair](#local-outreach-scheduler-and-repair). | Unregister the scheduled task; every command stays available manually. |
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

### Full database backup

`python -m jobscope.core.backup` creates, verifies, and restores encrypted full-database generations.
Each immutable generation contains only `jobscope.db.jsdb` and `manifest.json`; the encrypted file
includes all writable campaign and application state, unlike the redacted Pages/cloud-refresh snapshot.
The manifest records SQLite version/source ID, plaintext and ciphertext SHA-256, schema hash, table
counts, and creation time.

```bash
export JOBSCOPE_BACKUP_KEY='<separate long random key>'
python -m jobscope.core.backup create data/jobscope.db path/to/generations
python -m jobscope.core.backup verify path/to/generation
python -m jobscope.core.backup restore path/to/generation path/to/empty/jobscope.db
```

Restore refuses an existing destination. Creation uses SQLite's online backup API, converts the copy to
DELETE journal mode, validates it, encrypts it, verifies a decryption round trip, and atomically promotes the
generation. An interruption or disk-full error removes staging and preserves prior good generations.

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

1. Retain at least one generation under the old key.
2. Set a new long random `JOBSCOPE_BACKUP_KEY`.
3. Create a new generation and verify it decrypts.
4. Remove the old key only after recording that evidence.

## Local Outreach Scheduler And Repair

Registering `scripts/register-outreach-task.ps1` schedules `campaign tick` under the interactive user.
Each tick incrementally checks configured inboxes, reconciles replies, opt-outs, bounces, and complaints,
reports due approved work, and sends nothing. The task uses `MultipleInstances IgnoreNew`.

Adding `-Deliver` appends a second action running `campaign send-approved` after the tick, so a reply,
opt-out, or bounce always lands before the next send. It still sends at most one already-approved,
already-due message per run, inside the campaign's send window. Pacing outcomes (`nothing_due`,
`outside_send_window`, `minimum_spacing`, `daily_limit`, `followup_not_due`, `send_in_progress`) exit 0 so
an unattended run defers quietly; outcomes needing a human (`delivery_unknown`, `smtp_failed`,
`approval_required`, `policy_review_required`) still exit non-zero.

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

The weekly `.github/workflows/deps-audit.yml` installs `requirements.lock` and runs `pip-audit` over the
resulting environment. Auditing the installed set covers transitive pins and avoids re-resolving, which
otherwise tries to build numpy from source. It is scheduled rather than gating pushes so a newly published
advisory surfaces without blocking unrelated work.

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