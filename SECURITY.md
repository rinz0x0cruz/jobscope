# Security & Privacy

jobscope is a **local-first** tool: it reads your Gmail (read-only) to track job applications,
stores everything in a local SQLite database, and can publish a **redacted** dashboard to GitHub
Pages. This document describes what data it holds, how it's protected, and how to harden your setup.

## What data jobscope holds, and where

| Data | Where it lives | Notes |
|------|----------------|-------|
| Résumé(s), profile (name, email, phone) | `data/jobscope.db` (SQLite) | gitignored |
| Scraped jobs, scores, rationale | `data/jobscope.db` | gitignored |
| Referral contacts (names, public profile links) | `data/jobscope.db` | public-data leads only |
| Application funnel + email events (recruiter name/domain, subject) | `data/jobscope.db` | see *Data minimization* |
| Campaign ranks, recipients, drafts, approvals, schedules, suppressions | `data/jobscope.db` | local-only; never added to dashboard payloads |
| Secrets (Gmail app password, API keys) | OS keychain **or** `.env` | never in `config.yaml`, never committed |
| Published dashboard | `gh-pages` branch → GitHub Pages | empty locked shell + encrypted full payload (see *Publication*) |
| Cloud refresh database | private `data` branch | current + last-known-good JSDB v1 AES-GCM ciphertext; campaign tables stripped and vacuumed |

Everything under `data/`, plus `.env` and `config.*`, is **gitignored** and never leaves your
machine — except the redacted dashboard you explicitly publish.

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
- Campaign tables are intentionally excluded from the empty shell, encrypted dashboard payload, and the
  encrypted cloud SQLite copy. Campaign APIs exist only on loopback `jobscope serve`; GitHub Pages and
  Actions never expose or send campaign mail. Campaign recovery therefore requires a local database backup.

## Recruiter outreach (opt-in, individually approved)

`jobscope outreach <job_id>` handles one role. Local Campaigns can pace several companies, but every message
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
  your machine; disable site discovery with `apply.outreach.discover: false` and omit finder keys to disable providers.
- **Deduped + cooldown + opt-out.** One outreach per company (recorded on the application), a
  configurable `cooldown_days`, `do_not_contact`, application-history exclusion, and local opt-out suppressions
  are all rechecked before a campaign send.
- **No bulk approval.** Campaign edits clear approval. The scheduler sends one due approved target per run and
  also enforces the configured local window, daily cap, and minimum spacing. It has no force-send option.
- **Durable reply correlation.** Campaign mail carries a stable Message-ID. Read-only IMAP sync matches
  `In-Reply-To` first and confirmed-domain/post-send time second. Generic replies and opt-outs are classified
  deterministically; opt-out bodies need not be retained for suppression to work.
- **Unknown delivery fails closed.** SMTP acceptance cannot be atomically committed with SQLite. Once
  `sendmail` starts, an exception becomes `delivery_unknown`, never an automatic retry. The user must inspect
  Sent mail and explicitly resolve the attempt. Error records contain only safe exception type/code metadata.
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

## Deferred (not implemented)

Intentionally out of scope for now, to stay portable and dependency-light:

- **Encryption at rest** (e.g. SQLCipher) — requires a native dependency. Today the DB relies on file
  permissions + data minimization.
- **OAuth `gmail.readonly`** — scoped, revocable access requires a Google Cloud project + consent
  screen. Today jobscope uses read-only IMAP with an app password.

## Reporting a vulnerability

This is a personal, local-first tool with no Internet-facing backend. Its optional HTTP control plane binds
only to loopback and requires a per-process token plus same-origin checks. If you find a security issue, please
open a GitHub issue (omit any secret values) or contact the maintainer privately.
