# jobscope — feature & behaviour reference

A running catalogue of every feature and exactly how it behaves. Grouped by area.
Keep this in sync when behaviour changes.

**Design doctrine:** deterministic-first (≈80% logic / 20% optional AI), offline-first,
human-in-the-loop. AI is **off by default** and everything degrades gracefully without it.
No authenticated-account automation; a human always reviews before submit.

---

## Pipeline / data flow

```
scan → store jobs → match (score + filters + resume routing) → enrich top N
     → tailor → prep package → (human review) → apply/deep-link → track → digest

inbox (read-only Gmail IMAP) → classify emails → mail_events (timeline)
     → advance the application funnel   ← automated inbound side of `track`
```

`pipeline` runs `scan → match → enrich → prep top picks → digest` in one shot.

---

## CLI commands

Invoke as `python -m jobscope <command>`. Global flags: `--version`, `--config <path>`, `--db <path>`.

| Command | Behaviour |
| --- | --- |
| `init` | Scaffolds `config.yaml` + `data/` dir. |
| `resume import <path> --name <n>` | Parses `.md/.json/.pdf/.txt` into a structured resume and stores it under a name. Import several names for multi-resume matching. |
| `scan` | Scrapes jobs for every search term across every **profile**, then pulls configured companies' **public ATS boards** directly (see Scraping + Company-direct ATS boards). De-dupes by URL. |
| `match` | Scores every stored job, applies **filters**, and records the best-fit resume per job. Prints tier counts + filtered count. |
| `pipeline [--no-prep]` | scan → match → enrich → prep top picks → email digest. `--no-prep` stops after enrich. |
| `enrich [--job <id>]` | Adds public intel per company (comp, stock/IPO, Reddit, news, Glassdoor, contacts, brief). Default: top N by score. |
| `tailor <job_id>` | Produces a non-destructive tailored resume + cover letter (deterministic ATS keyword pass; AI-upgraded if enabled). |
| `prep <job_id>` | Builds a review-ready application package folder (tailored resume/cover PDF, filled-answers, index, contacts) and marks status `prepared`. |
| `apply <job_id> [--assist]` | Opens the posting URL for you to submit. `--assist` = headed Playwright autofill of a **public** ATS form that **stops before submit**. |
| `dashboard [--open] [--public]` | Renders the self-contained `data/dashboard.html` (job buckets **and** an **Applications** board: pipeline-flow Sankey + kanban columns + per-application email timelines). `--public` also writes a **redacted** copy (per-job contacts/rationale/resume-base, the Overview funnel/targets, **and all applications** stripped) to `output.public_dashboard_path` — safe to host publicly. |
| `serve [--port 8799] [--open]` | Serves the dashboard over local HTTP. |
| `track [--set job_id=status] [--timeline job_id]` | Shows the application funnel + response/interview/offer rates + follow-up reminders. `--set` updates a status; `--timeline` prints one application's email history. |
| `inbox [--dry-run] [--backfill] [--since D] [--account E]` | Syncs configured Gmail inbox(es) over **read-only IMAP** and auto-advances the funnel from application emails (see Inbox). `--dry-run` classifies without writing; `--backfill`/`--since` widen the scan; `--account` limits to one mailbox. |
| `new` | Lists new Strong/Good jobs since your last review, then advances the review marker. |
| `prune [--yes] [--dry-run]` | Deletes stored jobs outside your geographic scope (`search.home_country` + eligible remote). Previews by default; `--yes` deletes. |
| `gaps [--top 15]` | Skill-gap learning plan: skills that recur in your matched jobs but are on none of your resumes, ranked by jobs unlocked. |
| `brief <job_id>` | Blunt, risk-forward company brief (facts + risks, no marketing fluff). |
| `export [--format json\|csv] [--out <path>]` | Exports ranked jobs. |
| `selftest` | Offline self-tests (no network, no keys). |

---

## Dashboard UX / motion layer

- **Published React dashboard:** Vite/React/PWA build with static `dashboard.json` baked in. The public build
  is redacted: contacts, rationale, resume-base, search targets, funnel, and all applications are stripped.
- **Flashy system skin:** animated aurora gradients, neon blue/cyan/violet/emerald card frames, a Lottie-powered
  briefcase/scope logo, and a decorative cyber-sakura tree with occasional falling leaves. These are all local
  code/assets — no CDN or runtime animation fetch.
- **Interaction polish:** KPI, role, and application cards use cursor-follow spotlight variables (`--spot-x`,
  `--spot-y`) and preserve keyboard focus rings. Application cards also get status-colored rails; `interview`
  and `offer` rails pulse gently to surface active outcomes.
- **Applications page:** `applications.html` is a standalone encrypted shell. Its UI shell mirrors the
  dashboard's status rails and cursor spotlight after unlock, while the sensitive applications payload remains
  AES-GCM encrypted and only decrypts in-browser with the passphrase.
- **Reduced motion:** CSS, Motion, and Lottie animation respects the global `prefers-reduced-motion` guard;
  decorative layers are `aria-hidden`/`pointer-events: none`.

---

## Resume import & parsing

- Accepts Markdown / JSON Resume / PDF / plain text.
- Extracts skills (section + lexicon merge), titles (from experience headings like `### Company — Title`;
  bullet/sentence fragments are rejected — a title must be short, Title-Cased, and contain a whole-word role
  keyword), and month-aware date ranges scoped to the experience section (so education dates don't inflate tenure).
- **Seniority is years-anchored:** derived from tenure, with a seniority word in a title nudging it by at most
  one band. So a stray "Senior" on a ~1-year resume can't inflate it, while a genuine "Senior … + 10y" stays senior.
- Multiple named resumes are supported (e.g. `research`, `consulting`).

## Multi-resume selection & discipline routing

- With 2+ resumes, `match` records **which resume fits each job best** (`resume_base`).
- **Discipline routing:** each resume and job gets a *lean* in `[-1,+1]` from keyword signals
  (`+1` = hands-on/read-code technical, `-1` = advisory/GRC).
  - When a job clearly leans (`|lean| ≥ LEAN_DECISIVE = 0.25`), it routes **directionally** to the
    most-technical resume (technical roles) or most-advisory resume (advisory roles); fit score only
    breaks ties.
  - Ambiguous jobs fall back to best fit score with a small aligned nudge (`DISCIPLINE_SELECT_WEIGHT = 5`).
- **Headline score/tier = best fit across all resume framings**, so the routed resume is never
  under-credited for a keyword it happens to omit. The rationale notes `→ tailor from <resume> (… role)`
  when the shown score came from a different framing.

---

## Scraping (multi-profile)

- Engine: JobSpy across `indeed`, `linkedin`, `google` (configurable). `zip_recruiter` omitted (Cloudflare 403).
- **Search profiles:** `search.profiles` is a list of per-search overrides; each reuses the base `search`
  fields and overrides only what it lists (`location`, `is_remote`, `hours_old`, `country_indeed`,
  `results_wanted`). One scan runs them all. Empty `profiles: []` = a single search from the base.
  - Use case: one `remote` profile (global, last 7 days) + one `onsite-local` profile (e.g. `India`,
    on-site, last 30 days) so both remote and on-site/hybrid roles are covered.
- De-duplication is by canonical URL across all profiles (reposts update `last_seen`, never duplicate).
- Note: when `hours_old` is set, the `is_remote` flag isn't sent to JobSpy (recency is preferred); remote
  scoping then comes from the `location` string.
- **Remote is corroborated:** JobSpy's `is_remote` flag over-reports (it can mark an on-site role remote off a
  stray description mention), so a row counts as remote only when the location/title says so
  (`remote`/`anywhere`/`wfh`/…) or the flag is set with no concrete location. ATS rows use the same keyword rule.
- **Geographic scope (India + remote):** ingestion is scoped to roles you can actually take from
  `search.home_country` (default `India`) — onsite/hybrid in the home country, or remote that is global /
  home-eligible (incl. APAC / Asia for India). Region-locked remote (`Remote - US`, `Remote (EMEA)`) and
  foreign on-site are dropped at `scan` and by the ATS filter. Unknown/ambiguous locations are kept, never
  dropped on a guess. Toggle with `search.scope_to_home: false`; the predicate lives in `core/geo.py`
  (`in_scope`). Run `jobscope prune` to purge already-stored out-of-scope jobs.

## Company-direct ATS boards

- **Why:** keyword search on LinkedIn/Indeed rarely ranks well-funded companies (unicorns, public) into
  the top results, so their roles are missed. `scan` also pulls named companies' **public** job boards
  directly — no login, no API key — surfacing India/remote roles keyword search never sees.
- **Providers:** Greenhouse (`boards-api.greenhouse.io`), Lever (`api.lever.co`), Ashby
  (`api.ashbyhq.com`). All are logged-out public JSON endpoints (consistent with the no-auth-automation rule).
- **Config:** `search.companies` is a list of entries. Each is either a known name resolved via
  `jobscope/ats.py` `COMPANY_BOARDS` (e.g. `databricks` → greenhouse/databricks) or an explicit
  `"Name|provider|slug"` override. Empty list = ATS boards skipped.
- **Filtering:** each board is filtered to your locations (target countries/cities from `profiles` +
  `country_indeed`, plus any remote role when `is_remote` is set) **and** role keywords derived from
  `search.terms` (+ a small security/SWE lexicon), then normalized to the `Job` schema and de-duped by URL
  like any other source (`source = "ats"`).
- **Best-effort:** a wrong slug or dead board yields nothing rather than failing the scan. ATS runs even if
  JobSpy isn't installed (it needs only `requests`).

## Taken-down (closed) detection

- Jobs carry a `status` (`open` / `closed`) and a `closed_at` timestamp. A re-seen posting is always
  reopened on upsert.
- **Authoritative for ATS boards:** each board fetch returns the company's *full* current listing, so any
  job previously stored from that company that is no longer on the board is marked `closed` (taken down).
  This only runs on a **successful** (non-empty) fetch, so a transient network failure never mass-closes a
  company. `scan` reports e.g. `[databricks] ... (3 taken down)`.
- JobSpy postings (LinkedIn/Indeed) can't be re-verified reliably, so they aren't auto-closed -- only the
  authoritative ATS signal flips `status`.
- **Dashboard:** closed roles show a red `⚑ Taken down` badge with a struck-through title, an Overview
  **Taken down** KPI, and a **Hide taken-down** toggle. Applications keep the job's `status` so you can see
  if a role you applied to has since been pulled.

---

## Matching & scoring

Deterministic 0–100 fit score = `100 × Σ(weight × signal)` minus a ghost/scam penalty, clamped to 0–100.

**Weights** (`match.weights`, sum = 1.0):

| Signal | Weight | Behaviour |
| --- | --- | --- |
| `skills` | 0.34 | Fraction of resume skills found in the JD, saturating at `SKILL_TARGET = 6` hits (→ 1.0). |
| `title` | 0.18 | Token overlap between job title and resume titles, plus a role-word bonus (engineer/analyst/…). |
| `seniority` | 0.12 | Distance between the resume's seniority and the job title's seniority. |
| `comp` | 0.10 | Salary vs `min_salary`; a disclosed salary is itself a positive signal. |
| `location` | 0.10 | `prefer_locations` match → full; remote when wanted; else resume-location overlap. |
| `recency` | 0.04 | Newer postings score higher (age buckets). |
| `company` | 0.12 | Prestige tier, blended with the size preference (see Prioritization). |

- **Ghost/scam penalty** (`ghost_penalty = 15`): subtracted when scam/ghost-job signals fire (commission-only,
  clickbait, empty description + no salary, buzzphrases).
- **Tiers** (`match.tiers`): Strong ≥ 75, Good ≥ 55, Stretch ≥ 35, else Skip.
- **Rationale**: every job carries a short "why this rank" string (top signals, matched skills, routing note,
  any warnings/filter reason).

## Prioritization

- **Company quality** (`weights.company`): curated offline tiers boost prestigious / top-security employers
  (FAANG, NVIDIA/OpenAI/Anthropic, Palo Alto Networks, CrowdStrike, Zscaler, Okta, Wiz, …). Unknown = neutral.
- **Company size** (`match.prefer_company_size`): `any | large | mid | small`. Curated headcount bands
  (mega/large/mid/small/startup). `large` favours big established employers, `small` favours startups,
  `mid` peaks at scaleups. When set, the company score = 60% size-fit + 40% prestige; unknown = neutral.
- **Location** (`match.prefer_locations`): substring list (e.g. `["Remote","India","Bengaluru"]`); a match
  gives the full location score. `match.prefer_companies` force-boosts named employers.

## Filters (forced Skip with a reason)

Set under `filters`; matching jobs become tier `Skip` with a `⛔ reason` in the rationale.

| Key | Behaviour |
| --- | --- |
| `needs_sponsorship` | Drops roles that state no visa sponsorship. |
| `exclude_clearance` | Drops US security-clearance / citizenship-only roles. |
| `block_companies` | Drops listed companies (substring). |
| `block_keywords` | Drops jobs whose description contains any keyword. |
| `block_title_keywords` | Drops jobs whose title contains any keyword. |
| `max_age_days` | Drops postings older than N days (0 = off). |
| `max_years_experience` | Drops roles asking clearly more experience than the cap (0 = off). Required years are inferred from the title seniority (Senior ~4y, Staff ~6y, Principal ~8y) and explicit `N+ years` / `N-M years` / `N years … experience` phrases, taking the highest bar. Set to your years + a small buffer to focus on roles you can actually apply for. |

---

## Enrichment

Per company, best-effort and non-blocking (`enrich` toggles):

| Source | Behaviour |
| --- | --- |
| `compensation` | Posting salary + Levels.fyi link. |
| `stock` | yfinance ticker, price, % change, market cap, 52-wk position, IPO/public vs private. |
| `reddit` | old.reddit JSON search + lexicon sentiment + count (AI summary if enabled). |
| `news` | Google News RSS headlines (via feedparser). |
| `glassdoor` | Best-effort rating (off by default). |
| `contacts` | Legit-only referral leads: LinkedIn/Google people-search links + public GitHub profiles + AI outreach draft (optional). No PII harvesting. |
| `brief` | Blunt company brief: facts + risks, no hype; leads with risks; only states given facts. |

`enrich.top_n` controls how many top jobs get enriched by default.

## AI backend (optional)

- OpenAI-compatible client; **Groq by default** (`ai.provider`, `ai.base_url`, `ai.model`).
- **Off unless** `ai.enabled: true` **and** the API key env var (`ai.api_key_env`) is set. Ollama needs no key.
- Responses are cached in SQLite (`ai_cache`) keyed by hash(prompt+model).
- Optional `quorum` backend: when `quorum.enabled` is true and the package is installed, `ai.chat()`
  delegates to quorum instead of one direct model. Per-task overrides keep the strategy matched to the
  task: `quorum.strategy_generative` (default `council`) for summaries, cover letters, and "why here";
  `quorum.strategy_classify` (default `ensemble`) for seniority/discipline and ambiguous inbox labels.
  Empty overrides inherit the global `quorum.strategy`; older quorum versions are retried without the
  per-call strategy argument.
- Quorum generative calls get fuller grounding: tailored summary/cover calls pass the full job description
  (and the recent-news hook when present) as `context` DATA rather than truncating all useful evidence into
  the prompt. The single-model fallback ignores `strategy`/`context` and behaves as before.
- AI is used only for: resume summary/cover rewrite, application free-text answers, seniority/discipline
  tie-breaks, ambiguous inbox label tie-breaks, Reddit/news summaries, and outreach drafts. Everything has
  a deterministic fallback.

## Tailoring & PDF

- Deterministic ATS pass: matched vs missing keywords, coverage %, non-destructive tailored resume + cover.
- AI upgrades the summary/cover when enabled; the quorum path uses the generative strategy and receives
  the full JD/news context as grounding data. If AI is off or unavailable, the deterministic template is used.
- PDF via Playwright (Markdown → ATS-friendly HTML → PDF); graceful HTML fallback if Chromium is absent.

## Apply / prep

- `prep` builds an application package folder: tailored resume + cover (PDF), `filled-answers.md`,
  `application.md` index, referral contacts; sets status `prepared`. Optional email summary.
- `apply` opens the posting; **you submit**. Opt-in `--assist` autofills a **public** ATS form
  (Greenhouse/Lever/Ashby/Workday, no login) and **stops before submit**. Never automates logged-in accounts.

## Email digest

- SMTP; off unless `email.enabled` + credentials (`email.password_env`). Sends the pipeline digest.

## Tracking

- `track` shows the funnel (counts by status), **response/interview/offer rates**, and follow-up
  reminders (`apply.followup_days`).
- `track --set job_id=status` updates a status.
- `track --timeline <job_id>` prints one application's email history (each `mail_event` with date + signal).
- `new` lists new Strong/Good jobs since the stored `last_review` marker, then advances it.

## Inbox — Gmail application tracking

The automated inbound side of `track`: `inbox` reads the Gmail inbox(es) you configure and turns
application emails into funnel updates, so the pipeline reflects reality without manual `--set`.

- **Access — read-only IMAP with an App Password.** stdlib `imaplib`/`email`; no Google Cloud project,
  no OAuth, no browser. `SELECT` is `readonly=True` and every fetch uses `BODY.PEEK`, so mail is **never
  marked read** and nothing is mutated. App passwords live in `.env` (`inbox.accounts[].password_env`),
  never in config — consistent with the no-account-automation rule (reads only, never sends or acts).
- **Deterministic classification (AI never required).** `mailrules.py` (pure functions) classifies each
  email by **sender domain** (Greenhouse / Lever / Ashby / Workday / iCIMS / Workable / LinkedIn / Indeed …)
  + **weighted keyword scoring** into a signal: `confirmation / recruiter / assessment / interview / offer /
  rejection / other`. Each phrase carries a weight (3 = decisive, 2 = moderate, 1 = weak/boilerplate) and
  subject-line hits count double; the highest-scoring signal wins. A decisive rejection/offer phrase
  short-circuits from anywhere and a subject-authority rule pins plain confirmations, so a rejection that
  also says "interview" isn't mis-read and a precedence order breaks exact ties. When two or more signals
  finish in a genuine close-call tie, the optional quorum classify strategy can arbitrate **only among the
  tied labels**; it never invents a new status and is skipped when AI/quorum is unavailable.
- **Precision.** ATS domains always count as job-related; job-board/unknown domains need a strong signal,
  and board digests/alerts/community senders are dropped — so newsletters and social noise never reach the
  funnel.
- **Signal → status (monotonic).** confirmation/recruiter → `applied`, assessment/interview → `interview`,
  offer → `offer`, rejection → `rejected`. Status only advances forward (a late "received" can't undo an
  offer); `rejected` is terminal. Granular per-email signals are preserved in `mail_events` even though the
  funnel uses the coarse statuses.
- **Linking.** Each email links to a scraped job by fuzzy company match (stdlib `difflib`) when one exists,
  otherwise to a stable email-only application (`mail:<hash>`), so applications you made outside jobscope
  still track. Company/role are parsed from the subject/sender.
- **Incremental & cheap.** A per-account UID watermark (in `meta`) means normal runs only look at new mail;
  the first run (or `--backfill`) scans `inbox.lookback_days` back. `inbox.accounts[].lookback_days`
  overrides the window per account. Re-runs are idempotent (dedup by `Message-ID`). Per-message try/except
  keeps one bad email from sinking the run. Cron / Task-Scheduler friendly.
- **Setup.** Enable 2-Step Verification, create an App Password (`myaccount.google.com/apppasswords`), put
  it in `.env`, set `inbox.enabled: true`, and list your account(s). See README → *Inbox*.

## Skill gaps

- `gaps` scans your Strong/Good/Stretch jobs for lexicon skills present in JDs but absent from **all** your
  resumes, ranked by how many jobs each would unlock, with example companies. Advisory only — add a skill to
  a resume only if genuinely true.

---

## Dashboard

Self-contained `data/dashboard.html` (inline CSS/JS, no deps, no network). Your data stays local.

### Tabs
- **Overview**, **Applications**, + one tab per score bucket: **Strong / Good / Stretch / Skip**, each with a live count.
- A bucket tab shows only that tier's jobs; **Overview** and **Applications** show summary/pipeline panels (no job list).

### Overview tab
- **KPI cards:** Total, Strong, Good, Avg score, Filtered.
- **Analyzed donut:** tier distribution with counts + percentages.
- **Targeting these roles:** your search terms, plus *by-resume* and *by-location* split bars.
- **Application funnel:** counts by application status (from the tracker).
- **Top companies:** most frequent employers in view.
- **Skill gaps:** top gap skills as bars (jobs unlocked).
- **Top matches table:** highest-scoring jobs; click a row to open the detail drawer.

### Applications tab
Fed by `track` + `inbox` — your application pipeline, not the job search.
- **KPI cards:** Applications, Submitted, Response %, Interview %, Offer %, Rejected.
- **Pipeline flow:** an inline-SVG Sankey (no libraries) — the **Applied** flow *splits* into
  **Interview / Rejected / No response**, and the Interview branch splits again into **Offer / Rejected /
  In process**; band widths are proportional to counts, so you see how far each application got.
- **Kanban board:** columns by status (Applied → Interview → Offer → Rejected, plus any New/Prepared/Skipped);
  each card shows the company, role, applied date, and the application's **email timeline** (a colored signal
  chip + subject + date per message).
- Applications are **private** — stripped from the public dashboard.

### List (bucket tabs)
- **Cards** (minimal): score + bar, title, company · location, matched-resume tag, `NEW` (<24h), intel dots
  (funding, salary, stock ticker/Private, Glassdoor, Reddit, contacts, news), tier pill.
- **Detail drawer** (click a card): company brief, compensation, stock/IPO, Reddit, Glassdoor, recent news,
  referral leads, "why this rank", and — when grouped — an "All postings" list. Close with ✕, backdrop, or `Esc`.
- **Grouping** (`Group: on/off`, on by default): collapses duplicate postings of the same role
  (same company + normalized title) into one card with a `×N postings` badge; the drawer lists each posting
  (source · location · score + link).

### Controls (apply within the active bucket / scope)
- **Search** box (`/` to focus, `Esc` to clear): filters by title / company / rationale; also scopes the Overview.
- **Facet filters** — **Resume** (2+ resumes), **Country** (from location), **Location** (city/region,
  top places + Remote), **Work mode** (Remote / On-site), and **Funding** (`public` / `unicorn` — a
  compensation proxy from curated funding data). All stack together (AND) with search, the active tab,
  and grouping; each auto-hides when there's only one value.
- **Group** on/off; **theme** light/dark (persisted). Lists are ordered by score (desc).

---

## Export & self-test

- `export --format json|csv` writes ranked jobs to `data/` (or `--out`).
- `selftest` runs offline checks (scoring, filters, routing, company tiers/size, parsing) — no network/keys.

---

## Public dashboard & hosting (mobile viewing)

- `dashboard --emit-json --public` emits a **redacted** payload to `data/dashboard.public.json` (gitignored).
  `render._redact_public` strips per-job `contacts`, `rationale`, and `resume_base`, plus the Overview
  `funnel`/`targets` and all `applications`; it keeps company, title, location, score, tier, salary, brief,
  enrichment, and links. (`dashboard --public` still writes the redacted single-file HTML for local viewing.)
- **Hosting:** the code repo is **public**; the published dashboard is the **Vite/React app** (`web/`),
  served by GitHub Pages from a dedicated **`gh-pages`** branch (kept separate from `main`) at
  <https://rinz0x0cruz.github.io/jobscope/>.
- `scripts/publish.ps1` / `publish.sh` emit the redacted payload, bake it into the web app, `npm run build`,
  and push `web/dist` (+ `.nojekyll`) to the `gh-pages` branch via a gitignored persistent single-branch clone
  (`.dashboard-repo/`), pinned to the `rinz0x0cruz` identity. `scripts/register-publish-task.ps1` runs it as a
  daily Windows Scheduled Task.
- **Rules:** publishing originates locally (the SQLite DB is local/gitignored, so CI can't regenerate it);
  only ever publish the **redacted** copy — never `data/dashboard.html`.

---

## Configuration reference (`config.yaml`)

Copy from `config.example.yaml`; secrets go in `.env`. Key groups:

- `profile` — resume path, identity (name/email/phone/location), links.
- `search` — `sites`, `terms`, `google_term`, `location`, `country_indeed`, `results_wanted`, `hours_old`,
  `is_remote`, `distance`, `linkedin_fetch_description`, `proxies`, `profiles[]`.
- `match` — `weights{}`, `min_salary`, `seniority`, `prefer_locations[]`, `prefer_companies[]`,
  `prefer_company_size`, `tiers{}`, `ghost_penalty`.
- `filters` — `needs_sponsorship`, `exclude_clearance`, `block_companies[]`, `block_keywords[]`,
  `block_title_keywords[]`, `max_age_days`.
- `enrich` — `compensation`, `stock`, `reddit`, `news`, `glassdoor`, `contacts`, `brief`, `news_feeds[]`, `top_n`.
- `ai` — `enabled`, `provider`, `base_url`, `model`, `temperature`, `max_tokens`, `api_key_env`.
- `email` — `enabled`, `smtp_host`, `smtp_port`, `from_addr`, `to_addr`, `password_env`.
- `inbox` — `enabled`, `accounts[]` (`email`, `password_env`, optional per-account `lookback_days`),
  `imap_host`, `imap_port`, `folder`, `lookback_days`.
- `apply` — `assist`, `package_dir`, `auto_prep_top`, `followup_days`.
- `output` — `db_path`, `dashboard_path`.

## Storage

Local SQLite (`data/jobscope.db`): `jobs`, `enrichment`, `contacts`, `applications` (+ email-derived
`company`/`title`/`source` fallbacks), `mail_events` (classified application emails — the funnel timeline),
`resumes`, `meta` (markers incl. per-account inbox UID watermarks), `ai_cache`, `runs`. Schema evolves via
additive `_ensure_columns` migrations. Everything stays on your machine; `config.yaml`, `.env`, and `data/`
are gitignored.

## Responsible use

Public, logged-out scraping only; no fake accounts. AI output is advisory and a human reviews before submit.
Assisted apply never submits and never touches authenticated sessions.
