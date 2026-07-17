# jobscope — feature & behaviour reference

A running catalogue of every feature and exactly how it behaves. Grouped by area.
Keep this in sync when behaviour changes.

**Design doctrine:** deterministic-first (≈80% logic / 20% optional AI), offline-first,
human-in-the-loop. AI is **off by default** and everything degrades gracefully without it.
No authenticated-account automation; a human always reviews before submit.

---

## Pipeline / data flow

```
resume import → profile → company watchlist (every refresh) + discovery (daily)
  → match → review sync (pending monitored/discovery → save/dismiss) → enrich
     → tailor → prep package → (human review) → apply / outreach → interview prep → track → digest

inbox (read-only Gmail IMAP) → classify emails → mail_events (timeline)
     → reconcile (instance-split the funnel)   ← automated inbound side of `track`
```

`pipeline` runs `scan → match → enrich → prep top picks → digest` in one shot.

---

## CLI commands

Invoke as `python -m jobscope <command>`. Global flags: `--version`, `--config <path>`, `--db <path>`.

| Command | Behaviour |
| --- | --- |
| `init` | Scaffolds `config.yaml` + `data/` dir. |
| `resume import <path> --name <n>` | Parses `.md/.json/.pdf/.txt` into a structured resume and stores it under a name. Up to three named profiles are supported; local Settings can upload, build, replace, and switch them. |
| `profile [build\|show] [--resume N] [--force]` | Builds/shows the editable, résumé-derived **search profile** (`data/profile.yaml`): target roles from your titles + a skills→role map, your locations, remote. `scan` fetches from it (config.search is the fallback); `--force` regenerates, never clobbering edits otherwise. |
| `companies [seed\|list\|scan\|apply]` | Persistent explicit watchlist and official-portal scans. `seed` imports configured monitors and softly archives legacy application-only monitors; application/collected companies remain visible as **Known** until explicitly promoted. `apply` consumes the validated workflow action file. |
| `scout <company>` | Ephemeral ATS resolution/ranked preview. The durable workflow is to monitor the company. |
| `scan [--mode all\|monitored\|discovery]` | Monitored portals are primary; broad JobSpy discovery is secondary and cadence-gated (24h by default). |
| `reviews [sync\|list]` | Durable pending/saved/dismissed review decisions with monitored/discovery provenance. |
| `match` | Scores every stored job, applies **filters**, and records the best-fit resume per job. Prints tier counts + filtered count. |
| `pipeline [--no-prep]` | scan → match → enrich → prep top picks → email digest. `--no-prep` stops after enrich. |
| `enrich [--job <id>]` | Adds public intel per company (comp, stock/IPO, Reddit, news, Glassdoor, contacts, brief). Default: top N by score. |
| `tailor <job_id>` | Produces a non-destructive tailored resume + cover letter (deterministic ATS keyword pass; AI-upgraded if enabled). |
| `prep <job_id>` | Builds a review-ready application package folder (tailored resume/cover PDF, filled-answers, index, contacts) and marks status `prepared`. |
| `apply <job_id> [--assist]` | Opens the posting URL for you to submit. `--assist` = headed Playwright autofill of a **public** ATS form that **stops before submit**. |
| `outreach <job_id> [--to E] [--send] [--force]` | Drafts a tailored recruiter email + attaches your résumé and **previews it by default**. Resolves a contact deterministically: a real recruiter who emailed you (no-reply/ATS relays filtered out), a published HR/careers email **discovered on the employer's own site** (domain verified by fetching it + matching the company name), or a `careers@` role inbox on that verified domain — or `--to`. Sending is opt-in (`apply.outreach.enabled` + `email.*` + `--send`), **deduped per company** with a cooldown, and honors a do-not-contact list. |
| `dashboard [--public] [--emit-web]` | Emits the private dashboard payload; `--public` writes an **empty schema-valid shell**. `--emit-web` mirrors private data for local development. Publish scripts ship only the empty shell plus encrypted `site.enc.json`. |
| `serve [--port 8799] [--open]` | Builds (if needed) + serves the **web SPA** on 127.0.0.1 with a localhost-only **Refresh & Publish** button (syncs Gmail -> rescore -> publish -> rebuild). |
| `track [--set job_id=status] [--timeline job_id]` | Shows the application funnel + response/interview/offer rates + follow-up reminders. `--set` updates a status; `--timeline` prints one application's email history. |
| `inbox [--dry-run] [--backfill] [--since D] [--account E] [--include-spam] [--reclassify]` | Syncs configured Gmail inbox(es) over **read-only IMAP** and auto-advances the funnel from application emails (see Inbox). `--dry-run` classifies without writing; `--backfill`/`--since` widen the scan; `--account` limits to one mailbox; `--include-spam` also sweeps the `[Gmail]/Spam` folder this run (overrides `inbox.include_spam`), catching a real application email Gmail misfiled as spam; `--reclassify` is an **offline** repair — re-check stored mail with the current rules + rebuild the funnel (instance-split), with no Gmail sync. |
| `new` | Lists new Strong/Good jobs since your last review, then advances the review marker. |
| `prune [--yes] [--dry-run]` | Deletes stored jobs outside your geographic scope (`search.home_country` + eligible remote). Previews by default; `--yes` deletes. |
| `gaps [--top 15]` | Skill-gap learning plan: skills that recur in your matched jobs but are on none of your resumes, ranked by jobs unlocked. |
| `atscheck [--resume N] [--job ID]` | Deterministic **ATS view** of your parsed résumé (the fields + skills an ATS extracts) with a 0–100 friendliness score and formatting warnings (missing contact, tables/columns, image-only PDFs, corrupting glyphs). `--job` adds the JD keyword-coverage diff. |
| `coverage <job_id> [--resume N]` | Per-requirement JD coverage: walks the role's responsibilities/qualifications and marks each **covered / partial / missing** with tailoring tips. AI-optional, deterministic fallback. |
| `brief <job_id>` | Blunt, risk-forward company brief (facts + risks, no marketing fluff). |
| `referrals [--job ID] [--discover] [--top N]` | Surfaces referral paths across your pipeline — every company you have leads for (public profiles + search links + a copy-ready outreach draft), best live match first; closed roles still shown. `--job` = one company's leads; `--discover` fetches fresh leads. |
| `interview <job_id> [--note "…"] [--resume N]` | Interview-prep sheet: fit (strengths + gaps), likely JD topics, a STAR story bank, the company brief, referral path, and your notes. `--note` appends a date-stamped note. |
| `export [--format json\|csv] [--out <path>]` | Exports ranked jobs. |
| `selftest` | Offline self-tests (no network, no keys). |

---

## Dashboard UX

- **Company-first IA:** Review, Companies, Pipeline, Applications, Activity, Settings. Review defaults
  to pending monitored matches; broad Discovery, Saved, and Dismissed never mix implicitly. Companies
  owns portal resolution, source health, scan/pause/remove, and per-company pending/saved roles.
- **Local + encrypted Pages actions:** localhost uses loopback/CSRF APIs immediately. Static Pages stores
  optimistic actions locally and sends one `mutations_json` batch through the existing guarded GitHub
  workflow. The queue survives failures and clears only after a successful encrypted republish.

- **Published React dashboard:** Vite/React/PWA build with an empty baked payload. The private contract is
  fetched from `site.enc.json` and decrypted in-browser before any application surface mounts.
- **Operational visual system:** warm coral commands, green/amber/red status signals, IBM Plex Sans UI,
  Source Serif role prose, compact controls, stable split panes, and light/dark themes.
- **Command palette (⌘K):** jumps between all six views, fuzzy-searches roles, toggles theme, and runs refresh actions.
- **Header Refresh button:** rescans Gmail on demand — with a stored fine-grained token it POSTs `workflow_dispatch`
  directly, otherwise it opens GitHub's Run-workflow page. Throttle-safe: a client cooldown plus a check for an
  already-running scan means rapid taps never stack workflow runs; it then polls the run and offers to pull the fresh build.
- **Email recruiter (local `serve`):** the job drawer gains an *Email recruiter* panel when opened under
  `jobscope serve` — it resolves a contact, shows the tailored draft (editable To/Subject/Body), notes the résumé
  it will attach, and sends via the same guardrails as the CLI. Backed by a loopback, CSRF-guarded `/api/outreach`;
  hidden on the public static site (no backend to reach).
- **Review workspace:** ranked monitored/discovery/saved/dismissed buckets, source-aware actions, preserved
  list position, desktop reader/pipeline split, and a full-screen mobile role reader.
- **Market intelligence on cards:** structured posting pay is compared with compatible public compensation
  benchmarks; Glassdoor rating, Reddit sentiment/thread count, recent news, and verified recruiter mail surface
  only when backed by stored public data. Missing recruiter mail can be resolved through guarded local outreach.
- **Companies workspace:** defaults to the explicit **Watching** list; **Known / applied** preserves companies
  from collected roles and application history without scanning them. Known companies can be promoted with
  **Monitor company**. Only watched companies count toward Needs setup and expose source health,
  scan/pause/resume/remove, and editable portal controls. Job scans and recruiter lookup are separate explicit
  actions; scheduled contact refresh is opt-in to bound domain probes.
- **Recruiter preference:** verified inbound recruiters remain highest confidence; within comparable sources,
  cybersecurity/security recruiter titles rank ahead of technical/engineering, then general recruiting/HR.
  Employer domains must come from the company site, verified name/domain match, or inbox evidence—never
  LinkedIn, Indeed, Greenhouse, Lever, Workday, or another aggregator/ATS mail domain.
- **Applications + Activity:** operational inbox/board/offers views, preserved Sankey, action queue, and a
  chronological event stream with unique event identity.
- **Whole-site unlock:** the private payload includes jobs, descriptions, rationale, contacts, profile,
  monitors, reviews, and applications. Only its AES-256-GCM ciphertext and a tiny pointer are published.
- **UX tests:** Vitest + Testing Library cover routing, Review/Companies actions, queue synchronization,
  refresh de-duplication, models, readers, and application workflows.

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

## Search profile (résumé-driven fetch)

- `resume import` seeds `data/profile.yaml` from your parsed résumé; you edit it, and `scan` fetches from it —
  so the search follows your résumé instead of a hand-typed keyword in `config.yaml`.
- **Derivation (deterministic).** `search_terms` come from your résumé titles (seniority-stripped, so
  "Security Researcher Intern" → "Security Researcher") plus a skills→role map (appsec → Application Security
  Engineer; detection/SIEM → Detection Engineer; cloud-security/k8s/terraform → Cloud Security Engineer; …),
  capped at six; `locations` = Remote + your résumé location; `remote` from config. `seniority`/`top_skills`
  mirror the résumé for reference (matching still reads the résumé itself, not this file).
- **Editable + safe.** Plain YAML with an explanatory header at `<db-dir>/profile.yaml` (gitignored). Seeded on
  the **first** import only — it never clobbers your edits; `profile build --force` regenerates.
- **Drives `scan`.** The profile's `search_terms` become the scan terms and each `location` a per-location
  search; `config.search` stays the fallback when no profile exists.

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
- **Persistent watchlist:** SQLite `company_monitors` is authoritative for explicit user/configured watches
  after `companies seed`. Existing `search.companies` entries remain migration/fallback input. Application-only
  companies are derived into the encrypted payload as **Known** and never scanned or counted as Needs setup;
  legacy application-only monitor rows are softly archived, preserving links and history.
- **Config seed:** `search.companies` is a list of entries. Each is either a known name resolved via
  `jobscope/ats.py` `COMPANY_BOARDS` (e.g. `databricks` → greenhouse/databricks) or an explicit
  `"Name|provider|slug"` override. Empty list = ATS boards skipped.
- **Filtering:** each board is filtered to your locations (target countries/cities from `profiles` +
  `country_indeed`, plus any remote role when `is_remote` is set) **and** role keywords derived from
  `search.terms` (+ a small security/SWE lexicon), then normalized to the `Job` schema and de-duped by URL
  like any other source (`source = "ats"`).
- **Best-effort and fail-closed:** errors/partial/empty boards update source health but never close stored
  roles. Only a complete, non-empty `OK` board reconciles missing postings. ATS monitoring runs without
  JobSpy. Workday/iCIMS/custom HTML portals are explicit unsupported/Needs-setup states in the MVP.

## Taken-down (closed) detection

- Jobs carry a `status` (`open` / `closed`) and a `closed_at` timestamp. A re-seen posting is always
  reopened on upsert.
- **Authoritative for ATS boards:** each board fetch returns the company's *full* current listing, so any
  job previously stored from that company that is no longer on the board is marked `closed` (taken down).
  This only runs on a **successful** (non-empty) fetch, so a transient network failure never mass-closes a
  company. `scan` reports e.g. `[databricks] ... (3 taken down)`.
- JobSpy postings (LinkedIn/Indeed) can't be re-verified reliably, so they aren't auto-closed -- only the
  authoritative ATS signal flips `status`.
- **Dashboard:** closed roles leave the active Review queue. Applications retain the posting status, so a
  tracked application can still show that its source role was pulled.

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
  tied labels**; it never invents a new status and is skipped when AI/quorum is unavailable. Text is normalized
  for smart quotes/dashes (a curly *you're* / *we're* still matches), and application-received acknowledgments
  ("great that you're interested", "track the status of your application") are read as confirmations even when
  their body mentions "interview" in boilerplate.
- **Precision — noise dropped by sender.** ATS domains always count as job-related; job-board/unknown
  domains need a strong signal. Senders that only *look* like applications are dropped up front by domain,
  whatever keyword they score: newsletters/digests/community blasts, online-course platforms (a Thinkific
  "Training & Assessment" enrollment), and consumer/transactional receipts (a food-delivery order) — so a
  lifecycle keyword colliding in their subject never reaches the funnel. Account plumbing — email-verification
  codes, one-time passcodes, and password resets — is likewise dropped even from a careers/ATS domain, so an
  OTP whose footer mentions "assessment" never lands in the funnel.
- **Employer, not the ATS platform.** When mail arrives *through* an applicant-tracking or relay platform
  (SuccessFactors, Workday, Greenhouse, Oracle, iCIMS…), the company is recovered from the real employer —
  the sender display name (including an embedded `HR@employer.com`), a subject pattern (`…applying to
  <Company>`), or a body signal (a Workday careers-URL tenant, `employer.wdN.myworkdayjobs.com`) — never the
  platform's own domain, and a trailing platform token glued onto the display ("NCR Voyix Workday") is
  stripped. Real mis-parses are pinned as regression cases in `tests/test_fp_corpus.py`.
- **Spam-folder aware.** With `inbox.include_spam: true` the scan also reads `[Gmail]/Spam` (or
  `inbox.spam_folder`), since genuine confirmations occasionally land there; the same read-only `BODY.PEEK`
  rules apply.
- **Signal → status, timeline-aware.** confirmation/recruiter → `applied`, assessment/interview → `interview`,
  offer → `offer`, rejection → `rejected`. Within one application instance status advances forward; granular
  per-email signals are preserved in `mail_events` even though the funnel uses the coarse statuses.
- **Funnel reconcile (instance-split).** After each sync (and via `inbox --reclassify`) the funnel is rebuilt
  from each company's mail timeline in date order, split into **instances**: a rejection closes an instance, a
  later application/interview starts a **new active** instance (a re-application), and a distinct role gets its
  own. So re-applying — or applying to two roles where one is rejected — keeps an active row for the company
  instead of collapsing it to a single rejected one. `inbox --reclassify` also re-checks stored mail with the
  current rules (dropping OTP/verification mail, downgrading a false interview/assessment to a clear
  confirmation/rejection) and is wired into the cloud refresh so the published dashboard self-heals. Idempotent.
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

## Résumé ↔ JD intelligence

- **`atscheck` — ATS parse check.** Renders the "ATS view" of your parsed résumé
  (name/email/phone/location/seniority/skills/titles) with a transparent 0–100 friendliness score
  (start 100; −22 error / −9 warn / −3 info) and deterministic formatting warnings: missing contact fields,
  no/few skills, no Skills/Experience heading, unparseable dates, pipe/tab **tables**, **multi-column** layout,
  **image-only PDFs**, and corrupting **glyphs** (ligatures / box-drawing / icon-font / replacement chars).
  `--job` adds the JD keyword-coverage diff. Deterministic, no AI.
- **`coverage` — per-requirement JD coverage.** Walks a JD's actual responsibilities/qualifications (bullets
  first, then requirement sentences; perks / form-noise / mission boilerplate filtered) and marks each
  **covered / partial / missing** with a weighted % and tailoring tips. Deterministic (résumé-skill match +
  token overlap); an optional AI pass re-judges semantically and phrases the tips, falling back wholesale to the
  deterministic verdict when AI is off / garbled. Complements `atscheck`'s keyword coverage with
  responsibility-level coverage.

## Interview prep

- `interview <job_id>` assembles a per-job prep sheet from what jobscope already knows: your **fit** (score/tier,
  strengths to lead with, gaps to prepare), **likely topics** drawn from the JD, a **STAR** story-bank scaffold
  seeded from your top matched skills, the **company brief**, the **referral path**, and your **notes**.
- `--note "…"` appends a date-stamped note to the application (`applications.notes`, append-only).
- Deterministic + offline; reuses `tailor.analyze`, `coverage.extract_requirements`, the stored brief, and referrals.

## Referral surfacing (network activation)

- `referrals` surfaces where in your pipeline you already have a way in: every company you have **legit-only**
  leads for (public GitHub profiles + LinkedIn/Google people-search links, each with a deterministic outreach
  draft), best **live** match first — a company whose role has since closed still appears ("network anyway"),
  because a referral outlasts a posting.
- `referrals --job <id>` is the moment-of-applying view (real profiles + search links + the copy-ready draft);
  `--discover` fetches fresh leads for that company on demand. Reads the leads `enrich` stored — no PII harvesting.

---

## Dashboard

The React SPA in `web/` is served privately on localhost or unlocked from the encrypted Pages artifact.

- **Review:** monitored roles first; Discovery, Saved, and Dismissed are explicit durable buckets. Save,
  dismiss, restore, and monitor-company actions update locally or enter the Pages sync queue.
- **Companies:** add/resolve official portals; inspect board health and counts; scan, pause, resume, edit, or
  remove monitors; open pending/saved roles without leaving the company context.
- **Pipeline:** application Sankey plus outcome and response metrics.
- **Applications:** operational list, compact/table/grouped views, board, and offer register.
- **Activity:** overdue action queue plus application-event history.
- **Settings:** up to three résumé-derived profiles, local upload/build/switch, explicit Gmail scan, data
  freshness, GitHub sync token, privacy, display, and lock controls.
- Desktop uses a persistent Review reader and company list/detail split. Mobile uses five primary slots with
  Activity/Settings in More and opens readers/details full-screen.

---

## Export & self-test

- `export --format json|csv` writes ranked jobs to `data/` (or `--out`).
- `selftest` runs offline checks (scoring, filters, routing, company tiers/size, parsing) — no network/keys.

---

## Public dashboard & hosting (mobile viewing)

- `dashboard --emit-json --public` emits an **empty schema-valid shell** to `data/dashboard.public.json`.
  It contains no jobs, companies, reviews, profile, applications, contacts, or search targets.
- **Hosting:** the code repo is **public**; the published dashboard is the **Vite/React app** (`web/`),
  served by GitHub Pages from a dedicated **`gh-pages`** branch (kept separate from `main`) at
  <https://rinz0x0cruz.github.io/jobscope/>.
- `scripts/publish.ps1` / `publish.sh` emit the empty shell, encrypt the full payload, run `npm run build`,
  and push `web/dist` (+ `.nojekyll`) to the `gh-pages` branch via a gitignored persistent single-branch clone
  (`.dashboard-repo/`), pinned to the `rinz0x0cruz` identity. `scripts/register-publish-task.ps1` runs it as a
  daily Windows Scheduled Task.
- **Cloud auto-refresh (no PC needed).** A GitHub Actions workflow (`.github/workflows/refresh.yml`) scans
  your Gmail and republishes on a schedule (every 3h) **and on demand — including from the GitHub mobile
  app's *Run workflow* button, so you can refresh from your phone.** It runs the same deterministic
  `companies seed/apply/scan → cadence-gated discovery → inbox → match → reviews sync → publish` (AI off).
  Privacy model: the SQLite DB is kept
  **AES-256-GCM-encrypted** on a private, force-updated **`data`** branch (only the latest blob is stored,
  useless without the key); only the empty shell + passphrase-encrypted whole-site blob are
  published to `gh-pages`, exactly like the local publish. Gated on repository secrets (config, DB key, site
  passphrase, two Gmail app-passwords); without them the workflow no-ops.
- **Rules:** only publish the **empty** public build plus verified ciphertext — never the plaintext private
  payload. Locally the SQLite DB stays on your machine; in the cloud it is only ever
  present **encrypted** (restored from the `data` branch for the run, re-encrypted before the push).

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
  `imap_host`, `imap_port`, `folder`, `lookback_days`, `include_spam`, `spam_folder`, `store_snippets`.
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
