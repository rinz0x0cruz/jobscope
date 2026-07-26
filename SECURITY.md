# Security & Privacy

jobscope is a **local-first** tool: it reads your Gmail (read-only) to track job applications,
stores everything in SQLite, and can publish a **redacted** dashboard to GitHub Pages. An explicit
hosted mode can move the private control plane and full data directory to one protected persistent
volume. This document describes what data it holds, how it's protected, and how to harden your setup.

## What data jobscope holds, and where

| Data | Where it lives | Notes |
|------|----------------|-------|
| Résumé(s), profile (name, email, phone) | `data/jobscope.db` (SQLite) | gitignored |
| Scraped jobs, scores, rationale | `data/jobscope.db` | gitignored |
| Referral contacts (names, public profile links) | `data/jobscope.db` | public-data leads only |
| Application funnel + email events (recruiter name/domain, subject) | `data/jobscope.db` | see *Data minimization* |
| Campaign ranks, recipients, subjects, state, schedules, delivery/reply summary | local SQLite; allowlisted read-only projection in encrypted snapshots | visible only after passphrase unlock; no bodies or mutation controls |
| Campaign draft bodies, approval/resume hashes, résumé paths, raw message IDs, suppressions | `data/jobscope.db` or an opted-in private hosted volume | never added to Pages or cloud-refresh snapshots |
| Secrets (Gmail app password, API keys) | OS keychain, `.env`, or hosted secret manager | never in `config.yaml`, never committed |
| Published dashboard | `gh-pages` branch → GitHub Pages | empty locked shell + encrypted full payload (see *Publication*) |
| Cloud refresh database | private `data` branch | current + last-known-good JSDB v1 AES-GCM ciphertext; campaign tables stripped and vacuumed |
| Optional hosted control plane | one private persistent volume | full SQLite/profile state is plaintext while the service runs; the provider becomes part of the trust boundary |

In the default local mode, everything under `data/`, plus `.env` and `config.*`, is **gitignored**
and never leaves your machine except through the explicit encrypted publication/refresh paths.
Opting into hosted mode deliberately moves the full `data/` state to the configured private volume.

## Private hosted control plane

Hosted mode is not safe on a directly public origin. It binds externally only after explicit
`--hosted` selection and requires `JOBSCOPE_PUBLIC_ORIGIN` to be one HTTPS origin with no path.
Every supported request except the non-sensitive `/healthz` probe must carry
`Cf-Access-Jwt-Assertion`; unsafe API calls must also have that exact Origin and the existing
per-process Jobscope token.

The application validates every Access JWT against Cloudflare's rotating remote JWKS using exact
RS256, issuer, audience, expiry, and issued-at checks. Hosted startup fails without the exact
`JOBSCOPE_CF_ACCESS_TEAM_DOMAIN` and application `JOBSCOPE_CF_ACCESS_AUD`. Keep **Protect with
Access** enabled as a second gate. The Railway service must have no generated/public domain, and
Cloudflare Access must deny by default.
Run one application replica because SQLite and refresh state remain single-writer. Keep AI, SMTP,
and campaign ticking disabled during the empty canary and initial data cutover.

Hosted automation is optional and fails closed without a 32+ character
`JOBSCOPE_AUTOMATION_TOKEN`, a distinct 32+ character `JOBSCOPE_AUTOMATION_EDGE_TOKEN`, and the
exact `JOBSCOPE_AUTOMATION_ORIGIN`. The free automation Worker accepts only four fixed routes,
validates the GitHub-held token, strips untrusted forwarding headers, and adds the origin-only edge
token. Those fixed routes can refresh,
report status, run one paced tick, or return the already-encrypted Pages snapshot. Encryption uses
the hosted `JOBSCOPE_APPS_PASSPHRASE`; GitHub Actions receives neither plaintext nor passphrase. They cannot
accept campaign IDs, draft content, recipients, or generic campaign actions. Hosted builds deploy
a self-destroying service worker, detect Access HTML/redirect responses, clear live state, and offer
explicit Access logout. API and HTML responses remain `no-store` and deny framing.

When no custom zone is available, `cloudflare/worker.mjs` is the browser edge. It runs at one
Access-protected `workers.dev` route with preview URLs
disabled, rejects requests that lack `Cf-Access-Jwt-Assertion`, strips the
`CF_Authorization` cookie before proxying, and forwards the signed assertion to the
origin. The browser Worker rejects service-token JWTs unless an explicit client identity is
configured; the no-card topology leaves that binding absent. The separate
`cloudflare/automation-worker.mjs` edge never receives browser data and cannot proxy non-automation
paths. The Railway service may have a generated origin hostname, but every private
route still fails closed unless the assertion validates for the exact Access audience.

## Secrets

- Secrets are referenced by **env-var name** in config (e.g. `password_env: JOBSCOPE_GMAIL_APP_PW`),
  never by value. They are resolved **keychain-first**: the OS keychain (Windows Credential Manager /
  macOS Keychain / Linux Secret Service) via the optional [`keyring`](https://pypi.org/project/keyring/)
  package, then the environment / `.env`.
- **Recommended:** store secrets in the keychain instead of plaintext `.env`:
  ```bash
  pip install "jobscope[secure]"            # or: pip install keyring
  jobscope secrets set JOBSCOPE_GMAIL_APP_PW   # prompts; input hidden
  jobscope secrets import-env                  # migrate existing .env values into the keychain
  jobscope secrets list                        # status only — never prints values
  ```
  Then delete those lines from `.env`.
- **Rotate a leaked app password immediately** at <https://myaccount.google.com/apppasswords>
  (revoke + regenerate). App passwords grant **full mailbox access**, so treat them like a password.
- `.env` is gitignored; keep it `chmod 600` (POSIX). CI runs `detect-secrets` and the
  `.pre-commit-config.yaml` hook blocks accidental secret commits.

## Gmail access

- jobscope connects over **read-only IMAP** with a Gmail **app password** (requires 2-Step
  Verification). It uses `readonly=True` and `BODY.PEEK`, so it **never marks mail as read** and
  never modifies your mailbox.
- An app password authenticates the whole account. To reduce blast radius, point jobscope at a
  **dedicated job-search Gmail account** and forward recruiter mail to it — its app password then
  can't reach your primary inbox.
- Prefer app passwords over broader access. (A future option is scoped OAuth `gmail.readonly`, which
  is revocable per-app; it's not implemented yet — see *Deferred*.)

## Data at rest & minimization

- The SQLite DB and its `data/` directory are set **owner-only** on creation (best-effort `0600`/`0700`;
  on Windows `chmod` only toggles the read-only bit — use NTFS ACLs / an encrypted user profile for
  stronger isolation).
- **Email bodies are not persisted by default.** Snippets are used in memory to classify a message,
  then discarded; set `inbox.store_snippets: true` only if you want to keep a short excerpt.
- Campaign reply reconciliation stores only target state/timestamps and the matching mail-event ID. It never
  copies a subject or snippet into campaign or suppression records.
- Wipe stored data anytime:
  ```bash
  jobscope purge --mail                 # delete stored email events (recruiter PII + snippets)
  jobscope purge --mail --older-than 90 # retention: drop email events older than 90 days
  jobscope purge --applications         # delete the tracked application funnel
  ```

## Publication (the public dashboard is locked)

- `jobscope dashboard --public` / `--emit-json --public` produces an **empty, schema-valid shell**:
  no job rows, referral contacts, score rationale, résumé data, descriptions, funnel, search targets,
  or applications are present. The encrypted full payload is the only source of dashboard data.
- The `scripts/publish.*` scripts always emit with `--public`, build from isolated temporary
  inputs/output under a shared process lock, and run `jobscope.deliver.publish_artifact` before
  touching `gh-pages`. The gate validates the empty shell, encrypted envelope, ciphertext hash,
  private-field absence, and writes `deployment-manifest.json` with SHA-256 hashes.
- **Whole-site unlock (opt-in, `-Encrypted`):** the *full* un-redacted dashboard is additionally published
  as a single **AES-256-GCM** blob (PBKDF2-SHA256, 210k iterations) in a separate, lazily-fetched
  `site.enc.json`. It is useless without your passphrase, which is entered **only in the browser** and never
  sent anywhere; decryption and the swap to un-redacted data happen client-side. The plaintext un-redacted
  payload never leaves your machine.
- The cloud SQLite snapshot is separately encrypted as versioned JSDB AES-256-GCM. Restore and
  save fail closed, retain one validated fallback generation, validate SQLite before use, and use
  a guarded `force-with-lease` update. See [OPERATIONS.md](OPERATIONS.md) for recovery and rotation.
- Writable campaign tables are stripped and vacuumed from cloud SQLite. Before removal, Jobscope stores
  one fixed-field read-only projection under `campaign:snapshot:v1`; scheduled refreshes carry that
  projection forward and publish it only inside `site.enc.json`. Draft bodies, approval/resume hashes,
  résumé paths, raw message IDs, suppression internals, and mutation controls are excluded. Outreach APIs
  remain private-control-plane only; GitHub Pages and Actions never approve, mutate, schedule, or send mail.
  Full campaign recovery still requires a local database or hosted-volume backup.
- `GET /api/engagements` is token/origin guarded and derives an allowlisted correspondence view at read time.
  It emits recipient/subject/state/timestamps/follow-up counts and summaries only for retained inbound snippets.
  It cannot emit campaign bodies, résumé paths/hashes, approval hashes, suppression internals, or raw
  message/thread/reply IDs. The same fixed-field projection may appear only inside the passphrase-encrypted
  Pages payload and encrypted cloud snapshot; the public shell remains empty.

## Recruiter outreach (opt-in, individually approved)

`jobscope outreach <job_id>` handles one role. Private Outreach batches can pace several companies, but every message
still requires its own explicit approval and immutable content hash:

- **Preview by default.** It renders the recipient + email + attachment and sends nothing unless you
  pass `--send`; sending also requires `apply.outreach.enabled: true` and a configured `email.*` SMTP.
- **No fabricated addresses.** The recipient is only ever a real address a recruiter
  emailed you from, a published email **found on the employer's own website** (whose domain is confirmed
  by loading the site and matching the company name), or a conventional role inbox (`careers@`, …) on that
  confirmed domain. Optional Hunter/Apollo lookups run only when you configure their key environment variables;
  every result must be valid, non-automated, non-ATS, and on that confirmed domain. Confidence/source is shown,
  role inboxes are not auto-selected for campaigns, and Jobscope never guesses an address.
- **Discovery is best-effort + locally controlled.** Employer-page discovery and optional finders run from
  the active private workspace; disable site discovery with `apply.outreach.discover: false` and omit finder
  keys to disable providers. Shared HTTP GETs reject credentials, non-HTTP schemes, private/loopback/link-local/
  reserved IPv4 and IPv6 destinations, mixed public/private DNS answers, and redirects to those destinations.
  Each request connects to the vetted IP directly while preserving the original Host, TLS SNI, and certificate
  hostname, so DNS cannot change between validation and connection.
- **Deduped + cooldown + opt-out.** One outreach per company (recorded on the application), a
  configurable `cooldown_days`, `do_not_contact`, application-history exclusion, and local opt-out suppressions
  are all rechecked before a campaign send.
- **Follow-ups preserve identity.** Cold follow-ups are addressed only to the original cold recipient and
  carry the original thread identity. Application follow-ups reuse and lock a prior outreach recipient when
  one exists; otherwise they require a verified recruiter/company contact. A newer application action,
  response, terminal status, suppression, or changed source invalidates approval or blocks sending.
- **No bulk approval.** Campaign edits clear approval. The scheduler sends one due approved target per run and
  also enforces the configured local window, daily cap, and minimum spacing. It has no force-send option.
- **Durable reply correlation.** Campaign mail carries a stable Message-ID. Read-only IMAP sync matches
  the immediate `In-Reply-To` parent first and confirmed-domain/post-send time second. Follow-up mail also
  carries `References`; generic replies and opt-outs are classified deterministically, and opt-out bodies
  need not be retained for suppression to work.
- **Unknown delivery fails closed.** SMTP acceptance cannot be atomically committed with SQLite. Once
  `sendmail` starts, an exception becomes `delivery_unknown`, never an automatic retry. The user must inspect
  Sent mail and explicitly resolve the attempt. A process that dies after atomically claiming a send leaves
  `sending`; after 15 minutes the next scheduler tick moves that stale claim to `delivery_unknown` for the same
  manual resolution, never an automatic retry. One atomic SQLite claim is global across campaigns and processes;
  any `sending` or `delivery_unknown` target blocks every later delivery until resolved. Error records contain
  only safe exception type/code metadata.
- **Generated documents isolate untrusted content.** Job, company, résumé, news, and optional model text is
  HTML-escaped before Markdown rendering. The PDF browser disables JavaScript, aborts subresource requests,
  and receives a deny-by-default CSP, so a listing cannot execute script or fetch remote pixels beside résumé PII.
- **JobSpy descriptions avoid its Markdown converter.** Discovery requests HTML and immediately reduces it to
  plain text with Jobscope's script/style-stripping normalizer. The upstream Markdownify dependency remains
  installed for JobSpy compatibility but its vulnerable heading-conversion path is not invoked by Jobscope.
- **Quorum is advisory.** If explicitly enabled, Quorum may rewrite a draft or break an ordinary inbox-label
  tie. It never controls ranking, recipient validity, approval, sending, reply correlation, or suppression.
  Campaign reply and opt-out labels cannot be overwritten by the model path.
- **AI cache minimization.** Cache identity is derived from a SHA-256 key; new cache rows retain the response
  but not the plaintext prompt. Existing local rows are not rewritten automatically.
- **Your identity, your account.** Mail is sent from your own SMTP account (honest sender), so normal
  anti-spam / CAN-SPAM / GDPR expectations apply — keep it relevant and low-volume.

## Hardening checklist

1. `pip install "jobscope[secure]"` and move secrets into the keychain (`jobscope secrets import-env`),
   then blank them in `.env`.
2. Use a **dedicated job-search Gmail account**; enable 2-Step Verification; create an app password.
3. Keep `inbox.store_snippets: false` (the default); run `jobscope purge` periodically.
4. Keep `data/` and `.env` owner-only; don't sync them to a shared/cloud drive unencrypted.
5. Never commit `.env`, `config.yaml`, or `data/` (all gitignored); let the pre-commit/CI secret scan run.
6. Run `jobscope doctor` before enabling schedules and after rotating keys or changing config.
7. Before hosted scheduling, run `jobscope campaign ready`; it rejects unresolved delivery and approved
  targets whose résumé attachment is missing or changed after migration.

## Deferred (not implemented)

Intentionally out of scope for now, to stay portable and dependency-light:

- **Encryption at rest** (e.g. SQLCipher) — requires a native dependency. Today the DB relies on file
  permissions + data minimization.
- **OAuth `gmail.readonly`** — scoped, revocable access requires a Google Cloud project + consent
  screen. Today jobscope uses read-only IMAP with an app password.

## Reporting a vulnerability

This is a personal, local-first tool. Its default HTTP control plane binds only to loopback and requires a
per-process token plus same-origin checks. Optional hosted mode adds a private Tunnel/Access boundary but no
public origin. If you find a security issue, open a GitHub issue without secret values or contact the
maintainer privately.
