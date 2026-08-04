# Security & Privacy

jobscope is a **local-first** tool: it reads your Gmail (read-only) to track job applications,
stores everything in SQLite, and can publish a **redacted** dashboard to GitHub Pages.
This document describes what data it holds, how it's protected, and how to harden your setup.

## What data jobscope holds, and where

| Data | Where it lives | Notes |
|------|----------------|-------|
| Résumé(s), profile (name, email, phone) | `data/jobscope.db` (SQLite) | gitignored |
| Scraped jobs, scores, rationale | `data/jobscope.db` | gitignored |
| Referral contacts (names, public profile links) | `data/jobscope.db` | public-data leads only |
| Referrer named in an email (`referred_by`) | `data/jobscope.db` | a third party's name; inside the encrypted snapshot only, never in the public shell |
| Application funnel + email events (recruiter name/domain, subject) | `data/jobscope.db` | see *Data minimization* |
| Campaign ranks, recipients, subjects, state, schedules, delivery/reply summary | local SQLite; allowlisted read-only projection in encrypted snapshots | visible only after passphrase unlock; no bodies or mutation controls |
| Campaign draft bodies, approval/resume hashes, résumé paths, raw message IDs, suppressions | `data/jobscope.db` | never added to Pages or cloud-refresh snapshots |
| Secrets (Gmail app password, API keys) | OS keychain or `.env` | never in `config.yaml`, never committed |
| Published dashboard | `gh-pages` branch → GitHub Pages | empty locked shell + encrypted full payload (see *Publication*) |
| Cloud refresh database | private `data` branch | current + last-known-good JSDB v1 AES-GCM ciphertext; campaign tables stripped and vacuumed |

Everything under `data/`, plus `.env` and `config.*`, is **gitignored**
and never leaves your machine except through the explicit encrypted publication/refresh paths.

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
- Dependabot alerts and security updates cover the full npm tree from `web/package-lock.json`
  and the direct Python pins in `requirements.txt`/`pyproject.toml`. Transitive Python pins live
  in `requirements.lock`, which Dependabot does not parse, so the weekly `deps-audit.yml`
  workflow runs `pip-audit` over the installed environment instead.

## Gmail access

- jobscope connects over **read-only IMAP** with a Gmail **app password** (requires 2-Step
  Verification). It uses a CA/hostname-verifying default SSL context, a finite 30-second socket timeout,
  `readonly=True`, and `BODY.PEEK`, so it **never marks mail as read** and never modifies your mailbox.
- An app password authenticates the whole account. To reduce blast radius, point jobscope at a
  **dedicated job-search Gmail account** and forward recruiter mail to it — its app password then
  can't reach your primary inbox.
- Prefer app passwords over broader access. (A future option is scoped OAuth `gmail.readonly`, which
  is revocable per-app; it's not implemented yet — see *Deferred*.)
- Rollback is configuration-only: set `inbox.enabled: false`, stop inbox/tick schedules, and revoke the
  account's app password. No schema or data migration is required. App passwords still authenticate the
  full mailbox; adopt Gmail API `gmail.readonly` when per-app revocable consent or authorization-enforced
  read-only scope becomes a requirement.

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
  Full campaign recovery still requires a local database backup.
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
- **No bulk approval.** Campaign edits clear approval. Scheduled ticks are reconciliation-only and
  never call SMTP. Manual delivery is one approved target at a time and enforces the local window, daily cap,
  minimum spacing, suppressions, reply state, attachment hash, contact provenance, and policy hash.
- **Durable reply correlation.** Campaign mail carries a stable Message-ID. Read-only IMAP sync matches
  the immediate `In-Reply-To` parent first and confirmed-domain/post-send time second. Follow-up mail also
  carries `References`; generic replies and opt-outs are classified deterministically, and opt-out bodies
  need not be retained for suppression to work.
- **Unknown delivery fails closed.** SMTP acceptance cannot be atomically committed with SQLite. Once
  submission starts, a timeout or disconnect becomes `delivery_unknown`, never an automatic retry. An exact
  read-only Sent-folder Message-ID check preserves zero, one, and multiple matches as separate outcomes; manual
  resolution remains available for direct provider review. A process that dies after atomically claiming a send leaves
  `sending`; after 15 minutes the next scheduler tick moves that stale claim to `delivery_unknown` for the same
  Message-ID. It requires explicit resolution, never an automatic retry. One atomic SQLite claim is global across campaigns and processes;
  any `sending` or `delivery_unknown` target blocks every later delivery until resolved. Error records contain
  only safe exception type/code metadata.
- **SMTP acceptance is not inbox delivery.** Messages use SMTP-policy MIME, include `Date`, and retain a stable
  `Message-ID` per durable intent. Explicit 4xx/5xx responses remain actionable rejections; successful submission
  means only that the MTA accepted responsibility. Campaign activation runs TLS-verified
  EHLO/STARTTLS/EHLO/AUTH/NOOP/QUIT preflight, checks the largest approved message against advertised SIZE, and
  issues no MAIL, RCPT, or DATA. Later DSNs preserve the original submission record while adding bounce or
  suppression evidence.
- **Provider feedback is durable.** DSNs and complaints correlate by stable Message-ID. Hard bounces suppress
  the recipient, complaints suppress recipient and domain, duplicate events are idempotent, and transient
  bounces block all delivery until explicit delivered/hard-bounce review. Ambiguous feedback changes nothing.
- **Generated documents isolate untrusted content.** Job, company, résumé, news, and optional model text is
  HTML-escaped before Markdown rendering. The PDF browser disables JavaScript, aborts subresource requests,
  and receives a deny-by-default CSP, so a listing cannot execute script or fetch remote pixels beside résumé PII.
- **Automatic acquisition is allowlisted.** Only exact Greenhouse, Lever, and Ashby public API hosts may be
  called by automatic job scans. Unknown providers and Phenom are unsupported; arbitrary careers pages are
  not crawled. The shipped dependency graph contains no JobSpy, browser impersonation, CAPTCHA, or proxy-
  rotation stack, and assisted apply has no browser submit action.
- **AI is advisory, local-first, and fail-closed.** It is off by default.
  Each call names an exact purpose; the first supported route is a pinned allowlisted model on loopback
  Ollama with no API key. Remote OpenRouter requires an explicit per-purpose model/provider allowlist and
  pins `allow_fallbacks: false`, `require_parameters: true`, `data_collection: deny`, and `zdr: true`;
  r\u00e9sum\u00e9 tailoring, application answers, outreach drafts, and coverage advice are never remote-eligible and
  remote input is redacted for emails, phone numbers, URLs, and bearer/API-key patterns. Quorum routes are
  rejected because their rounds, retries, and provider fallbacks cannot share one central budget.
- **One budget, no silent relaxation.** Calls, input characters/tokens, reserved output tokens, retries,
  fan-out, and wall time are reserved before any request, so exhaustion, policy mismatch, backend error, or
  schema/length/grounding failure performs zero HTTP and returns the deterministic result.
- **Model output cannot hold authority.** Scores, tiers, resume routing, JD coverage percentages, mail
  signals, application state, send eligibility, and approved outbound content are computed deterministically.
  Untrusted job, company, and mail text is passed as an encoded data payload with no tools, secrets, network,
  or outbound authority, and advisory text is validated against supplied facts before display.
- **AI data minimization.** Cache identity is a SHA-256 key; rows retain only the response, never the prompt.
  Sensitive purposes are never cached, provenance records only purpose/provider/model-hash, and the AI cache
  plus advisory brief text are stripped from cloud-safe snapshots. Existing local rows are not rewritten.
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
7. Before enabling campaign scheduling, run `jobscope campaign ready`; it rejects unresolved delivery and approved
  targets whose résumé attachment is missing or changed after migration.

## Deferred (not implemented)

Intentionally out of scope for now, to stay portable and dependency-light:

- **Encryption at rest** (e.g. SQLCipher) — requires a native dependency. Today the DB relies on file
  permissions + data minimization.
- **OAuth `gmail.readonly`** — scoped, revocable access requires a Google Cloud project + consent
  screen. Today jobscope uses read-only IMAP with an app password.

## Reporting a vulnerability

This is a personal, local-first tool. Its HTTP control plane binds only to loopback and requires a
per-process token plus same-origin checks. If you find a security issue, open a GitHub issue without secret values or contact the
maintainer privately.
