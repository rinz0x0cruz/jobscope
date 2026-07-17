# jobscope — handoff & next-steps (continue on another machine)

> Written 2026-07-02. This folder is committed so it travels with `git pull`.
> The private code repo syncs; **your data and config do not** (see below).

---

## 1. Where things stand

- Branch `main`, CI green (py3.11 + py3.12: `selftest` + `pytest`).
- Live public dashboard: <https://rinz0x0cruz.github.io/jobscope/> (redacted, HTTP 200), served from
  this repo's own `gh-pages` branch.
- Recent shipped features (see `FEATURES.md` for behaviour):
  - **ATS-direct company boards** (`643daa2`) — `search.companies` pulls Greenhouse/Lever/Ashby public boards.
  - **Experience cap** (`3c7db0e`) — `filters.max_years_experience` hides over-senior roles (local cap = 2).
  - **Resume parser fix** (`5f6e1d1`) — precise titles + **years-anchored seniority** (both resumes → junior).
  - **Taken-down detection** (`5e7affb`) — ATS jobs pulled from a board are marked `closed`; dashboard badge/KPI.
  - **Remote corroboration** (`d827966`) — JobSpy `is_remote` false-positives fixed (on-site no longer shown remote).
  - **Redacted public dashboard + Pages publish** (`10ca833`, `95c1094`).

## 2. What does NOT sync via git (recreate on the other machine)

These are gitignored (`config.yaml`, `.env`, `data/*`, `.venv/`, `/.dashboard-repo/`):

- **`config.yaml`** — copy from `config.example.yaml` and fill in (resume path, profiles, `search.companies`,
  `filters.max_years_experience: 2`, `country_indeed`, etc.). Paths may differ per machine.
- **`.env`** — only if using AI/email (optional; off by default).
- **`data/jobscope.db`** — the SQLite store (jobs, resumes, applications). Each machine builds its own by
  scanning; the *published dashboard* is the shared view. Backups are `data/jobscope.db.bak-<ts>` (local only).
- **`.venv/`** — recreate; **resume `.md` files** live under `../../Resume/` (outside this repo).

## 3. Setup on the other machine

```powershell
cd <repo>\jobscope
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e .            # or: pip install -r requirements.txt
python -m playwright install chromium      # only needed for PDF + assisted apply
Copy-Item config.example.yaml config.yaml  # then edit: resume path, profiles, companies, filters
python -m jobscope resume import "<path>\Resume-...-Research.md"   --name research
python -m jobscope resume import "<path>\Resume-...-Consulting.md" --name consulting
python -m jobscope scan; python -m jobscope match; python -m jobscope dashboard
python -m jobscope serve --port 8799        # view at http://127.0.0.1:8799/dashboard.html
```

Run notes: `python -m jobscope` needs the repo root as CWD and `PYTHONPATH="."` (or `pip install -e .`).

## 4. Next thought plan (pick up here)

1. **Maintenance first:** Companies now separates the explicit **Watching** list from **Known / applied**
  history. Do not bulk-resolve known companies; promote only the employers worth continuously scanning.
2. **Selective ATS coverage:** add a board slug/provider only for a high-priority watched employer with a
  clean logged-out source. Workday/iCIMS/custom portals remain unsupported unless a stable public connector
  is justified.
3. **Optional signal retention:** store raw JobSpy `is_remote` separately so future geographic-rule changes
  can re-derive `remote_scope` without rescanning.
4. **Publishing:** encrypted cloud refresh is authoritative for scheduled/browser mutation publishing. Keep
  local publisher tasks disabled or single-primary to avoid competing `gh-pages` pushes.

## 5. Guardrails (don't regress these)

- **Repo visibility.** jobscope is **public** (required for free `gh-pages` Pages hosting). History was
  audited 2026-07-03: all 65 commits use the name `rinz0x0cruz` + GitHub **noreply** emails only — **no
  work-email / real name in history** — so the old "keep it private or the work-email leaks" caution does
  **not** apply. Being public exposes the code only; the local DB/config stay gitignored.
- Publish only the **redacted** copy (`dashboard --public`) — never `data/dashboard.html`.
- jobscope's own **`gh-pages`** branch hosts Pages (branch-based, `build_type=legacy`); keep a
  **`.nojekyll`** file so the single-file dashboard isn't mangled by the Jekyll builder. (The separate
  `jobscope-dashboard` repo is retired.)
- Cloud refresh restores the encrypted private DB, runs the pipeline, saves a new encrypted snapshot, and
  publishes the empty shell + encrypted payload. Local publishing remains an explicit recovery path.
- CI installs only `pyyaml requests feedparser markdown pytest` — new code + tests must degrade gracefully
  without `pandas`/`python-jobspy`.
