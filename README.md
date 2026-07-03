# jobscope

**Resume-driven job scout, enricher, and application-prep tool.** Point it at your
resume; it scrapes fitting roles, ranks them by a transparent fit score, enriches each
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
- **Local-first & private.** Your resume, data, and secrets stay on your machine
  (SQLite + gitignored files).

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

The setup script creates a virtualenv, installs dependencies, and downloads the
Chromium runtime used for PDF rendering and assisted apply:

```bash
python -m venv .venv
. .venv/bin/activate           # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

## Quick start

```bash
python -m jobscope init                          # scaffold config.yaml + data/ + .env
# add your resume at data/resume.md, edit config.yaml (search.terms / location)
python -m jobscope resume import data/resume.md
python -m jobscope scan                           # scrape jobs (JobSpy)
python -m jobscope match                          # rank by fit score
python -m jobscope enrich                         # comp / stock / reddit / news / contacts (top N)
python -m jobscope tailor <job_id>                # tailored resume + cover letter (PDF)
python -m jobscope prep   <job_id>                # full review-ready application package
python -m jobscope dashboard --open               # browse everything
```

Or run the whole loop in one shot:

```bash
python -m jobscope pipeline                        # scan -> match -> enrich -> prep top picks -> digest
```

## Commands

| Command | What it does |
|---|---|
| `init` | Scaffold `config.yaml`, `data/`, `.env` |
| `resume import <path> [--name N]` | Parse `.md`/`.json`/`.pdf`/`.txt` into a (named) base resume |
| `scan` | Scrape jobs for your configured searches (JobSpy) |
| `match` | Fit scoring + tiers, **multi-resume selection**, and **filters** (clearance/sponsorship/block-list) |
| `pipeline` | scan -> match -> enrich -> prep top picks -> digest (one shot) |
| `enrich [--job ID]` | Comp, stock/IPO, Reddit, news, Glassdoor, referral contacts, **company brief** |
| `tailor <job_id>` | Keyword-aligned resume + cover letter (using the best base resume), rendered to PDF |
| `prep <job_id>` | Application package (docs + pre-filled answers + link + contacts + brief) |
| `apply <job_id> [--assist]` | Open the application; `--assist` pre-fills public ATS forms, stops before submit |
| `brief <job_id>` | Blunt, risk-forward company brief (no marketing fluff) |
| `gaps [--top N]` | Skill-gap learning plan: skills to learn ranked by jobs unlocked |
| `new` | New Strong/Good jobs since you last reviewed |
| `dashboard [--open] [--public]` / `serve` | Render / serve the local HTML dashboard (click a card to expand full detail); `--public` writes a redacted copy safe to host |
| `track [--set job_id=status] [--timeline job_id]` | Application funnel, rates, follow-up reminders, and a per-application email timeline |
| `inbox [--dry-run] [--backfill] [--since D] [--account E]` | Sync Gmail over read-only IMAP and auto-advance the funnel from application emails |
| `export [--format json\|csv]` | Export ranked jobs |
| `selftest` | Offline self-tests (no network, no keys) |

## Inbox: auto-track applications from Gmail

`jobscope inbox` reads the Gmail inbox(es) you configure and turns application
emails into funnel updates automatically — confirmations → `applied`,
interview/assessment invites → `interview`, offers → `offer`, rejections →
`rejected`. Classification is **deterministic** (sender-domain + keyword rules for
Greenhouse / Lever / Ashby / Workday / iCIMS / Workable / LinkedIn / Indeed and
friends); AI is never required — an optional model only refines the residual
`other` bucket when `ai.enabled`.

It connects over **read-only IMAP** with a Gmail **App Password** — no Google
Cloud project, no OAuth, and it never marks your mail as read. The first run scans
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
python -m jobscope inbox                      # sync (incremental) -> funnel
python -m jobscope inbox --backfill           # rescan lookback_days
python -m jobscope track                      # updated funnel + response/interview/offer rates
python -m jobscope track --timeline <job_id>  # email history for one application
python -m jobscope dashboard --open           # Applications board: pipeline columns + email timelines
```

Multiple mailboxes: add more entries under `accounts`, each with its own
`password_env`. Everything stays local in SQLite; app passwords live only in your
environment. Runs well from cron / Task Scheduler.

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

The dashboard is master–detail: cards show only the essentials (score, title,
company · location, a couple of intel dots), and clicking one slides open a drawer
with the company brief, compensation, stock/IPO, Reddit, Glassdoor, news, referral
leads, and the score rationale. Close with the ✕, the backdrop, or `Esc`.

Remote roles carry a **remote scope**: the dashboard's *remote scope* facet splits
global remote ("Remote (anywhere)") from geo-restricted remote ("Remote in Ireland"),
and geo-restricted cards show a `Remote · <region>` badge. Set `match.remote_scope_strict:
true` to down-rank geo-restricted remote whose region isn't in your `prefer_locations`
or search country (off by default; global remote is never penalized).

## Publish to GitHub Pages (view on mobile)

The dashboard is a single self-contained HTML file, so you can host it and open it
from your phone. The full dashboard embeds private data (referral contacts, your
application funnel, and search terms), so publish the **redacted** copy:

```bash
python -m jobscope dashboard --public   # -> data/public-dashboard.html (no contacts / funnel / search terms)
```

`scripts/publish.ps1` (Windows) / `scripts/publish.sh` (macOS/Linux) render that
redacted copy and publish it as `index.html` to this repo's **`gh-pages` branch**,
which GitHub Pages serves. `main` is never touched and your database never leaves your
machine. One-time setup:

1. Run the publish script once by hand to push the first `index.html` to `gh-pages`
   and cache your git credential.
2. Enable Pages: **Settings → Pages → Deploy from a branch → `gh-pages` / root**.
   The dashboard is then live at `https://<user>.github.io/jobscope/`.
3. Auto-refresh (Windows): `scripts/register-publish-task.ps1` registers a daily
   Scheduled Task that re-renders and pushes while you're logged on.

> GitHub Pages is **public**. Only the redacted copy is published, but treat the URL
> as shareable — keep real data in the local (`dashboard`) view.

## Multi-resume matching

Import several base resumes and jobscope auto-picks the best-fitting one per job,
then tailors from it:

```bash
python -m jobscope resume import research.md   --name research
python -m jobscope resume import consulting.md --name consulting
python -m jobscope match          # each job records which base scored highest
```

## Search profiles (remote + on-site)

A single search only covers one location/recency window, so remote-only scans miss
on-site and hybrid roles. Add `search.profiles` to run several searches in one scan —
each reuses your base `search` fields and overrides only what it lists:

```yaml
search:
  # ...terms, sites, results_wanted...
  profiles:
    - name: "remote"          # global remote, last 7 days
      location: "Remote"
      is_remote: true
      hours_old: 168
    - name: "onsite-local"    # on-site / hybrid across India, last 30 days
      location: "India"       # or a city, e.g. "Pune, Maharashtra"
      is_remote: false
      hours_old: 720
      country_indeed: "India"
```

Results are de-duplicated by URL, so overlapping profiles won't create duplicates.
Leave `profiles: []` for a single search from the base fields.

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

## Free AI backends

AI is optional. When enabled, jobscope talks to any OpenAI-compatible endpoint:

- **Groq** (default) — fast, generous free tier
- **Google Gemini** free tier, **OpenRouter** free models, or **Ollama** (fully local)

Set `ai.enabled: true` and `JOBSCOPE_AI_API_KEY` in `.env`.

### Multi-model deliberation (quorum) + seniority tie-breaker

With the optional [`quorum`](https://github.com/rinz0x0cruz/quorum) package installed,
set `quorum.enabled: true` to route the AI layer through a multi-model deliberation
(`strategy: ensemble | council | refine | debate | moa`) instead of a single model.

```bash
pip install -e ".[quorum]"   # fetches quorum from GitHub; then set quorum.enabled: true + the AI key
```

When AI is on, jobscope also runs a **seniority tie-breaker**: only for postings that
have no deterministic level signal *and* still landed in a good tier (i.e. actually
leaking), it asks the model for a normalized level + required years, then re-applies the
same cap/score. It's bounded to that ambiguous set, cached, and a complete no-op when
`ai.enabled` is false:

```yaml
match:
  ai_seniority_tiebreak: true   # classify only ambiguous, non-Skip postings
  ai_tiebreak_max_calls: 0      # 0 = unbounded; else cap AI calls per match run
```

## Responsible use

jobscope favors a *filter*, not spray-and-pray: it helps you find the few roles worth
your time and prepares strong, tailored applications you review before sending. Respect
the Terms of Service of any site you interact with. Referral discovery uses only public
data and search links — no scraping of private profiles, no email harvesting.

## License

MIT — see [LICENSE](LICENSE).
