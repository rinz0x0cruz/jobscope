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
| `dashboard [--open]` / `serve` | Render / serve the local HTML dashboard |
| `track [--set job_id=status]` | Application funnel, rates, and follow-up reminders |
| `export [--format json\|csv]` | Export ranked jobs |
| `selftest` | Offline self-tests (no network, no keys) |

## Multi-resume matching

Import several base resumes and jobscope auto-picks the best-fitting one per job,
then tailors from it:

```bash
python -m jobscope resume import research.md   --name research
python -m jobscope resume import consulting.md --name consulting
python -m jobscope match          # each job records which base scored highest
```

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

## Responsible use

jobscope favors a *filter*, not spray-and-pray: it helps you find the few roles worth
your time and prepares strong, tailored applications you review before sending. Respect
the Terms of Service of any site you interact with. Referral discovery uses only public
data and search links — no scraping of private profiles, no email harvesting.

## License

MIT — see [LICENSE](LICENSE).
