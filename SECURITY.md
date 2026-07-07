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
| Secrets (Gmail app password, API keys) | OS keychain **or** `.env` | never in `config.yaml`, never committed |
| Published dashboard | `gh-pages` branch → GitHub Pages | **redacted** (see *Publication*) |

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
- Wipe stored data anytime:
  ```bash
  jobscope purge --mail                 # delete stored email events (recruiter PII + snippets)
  jobscope purge --mail --older-than 90 # retention: drop email events older than 90 days
  jobscope purge --applications         # delete the tracked application funnel
  ```

## Publication (the public dashboard is redacted)

- `jobscope dashboard --public` / `--emit-json --public` produces a **redacted** payload that strips:
  referral contacts, score rationale, résumé-variant labels, archived job descriptions, the application
  funnel, your search targets, and **all applications**. Only public-safe job info + fit scores remain.
- The `scripts/publish.*` scripts always emit with `--public`, so an unredacted build cannot reach
  `gh-pages`. Two tests lock this in: `test_public_build_data_redacts_all_pii` and
  `test_public_json_has_no_pii_markers` (`tests/test_dashboard_json.py`).
- **Whole-site unlock (opt-in, `-Encrypted`):** the *full* un-redacted dashboard is additionally published
  as a single **AES-256-GCM** blob (PBKDF2-SHA256, 210k iterations) in a separate, lazily-fetched
  `site.enc.json`. It is useless without your passphrase, which is entered **only in the browser** and never
  sent anywhere; decryption and the swap to un-redacted data happen client-side. The plaintext un-redacted
  payload never leaves your machine.

## Recruiter outreach (opt-in, not a mailer)

`jobscope outreach <job_id>` can email a recruiter your résumé, but it is built to be a considered,
one-at-a-time action — never a bulk mailer:

- **Preview by default.** It renders the recipient + email + attachment and sends nothing unless you
  pass `--send`; sending also requires `apply.outreach.enabled: true` and a configured `email.*` SMTP.
- **No fabricated addresses.** The recipient is only ever a real address a recruiter emailed you from,
  or a conventional role inbox (`careers@`, `jobs@`, …) on a **confirmed** company domain (the employer's
  own site, or a domain that emailed you). It never guesses an address from a company name.
- **Deduped + cooldown + opt-out.** One outreach per company (recorded on the application), a
  configurable `cooldown_days`, and a `do_not_contact` list are all honored before anything sends.
- **Your identity, your account.** Mail is sent from your own SMTP account (honest sender), so normal
  anti-spam / CAN-SPAM / GDPR expectations apply — keep it relevant and low-volume.

## Hardening checklist

1. `pip install "jobscope[secure]"` and move secrets into the keychain (`jobscope secrets import-env`),
   then blank them in `.env`.
2. Use a **dedicated job-search Gmail account**; enable 2-Step Verification; create an app password.
3. Keep `inbox.store_snippets: false` (the default); run `jobscope purge` periodically.
4. Keep `data/` and `.env` owner-only; don't sync them to a shared/cloud drive unencrypted.
5. Never commit `.env`, `config.yaml`, or `data/` (all gitignored); let the pre-commit/CI secret scan run.

## Deferred (not implemented)

Intentionally out of scope for now, to stay portable and dependency-light:

- **Encryption at rest** (e.g. SQLCipher) — requires a native dependency. Today the DB relies on file
  permissions + data minimization.
- **OAuth `gmail.readonly`** — scoped, revocable access requires a Google Cloud project + consent
  screen. Today jobscope uses read-only IMAP with an app password.

## Reporting a vulnerability

This is a personal, local-first tool with no server component. If you find a security issue, please
open a GitHub issue (omit any secret values) or contact the maintainer privately.
