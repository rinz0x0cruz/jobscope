# jobscope — handoff & next-steps (continue on another machine)

> Written 2026-07-02. This folder is committed so it travels with `git pull`.
> The private code repo syncs; **your data and config do not** (see below).

---

## 1. Where things stand

- Branch `main`, CI green (py3.11 + py3.12: `selftest` + `pytest`).
- Live public dashboard: <https://rinz0x0cruz.github.io/jobscope-dashboard/> (redacted, HTTP 200).
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

1. **Geo-restricted remote:** tag `"Remote in <country>"` roles distinctly from global remote (e.g. Stripe's
   "Remote in Ireland" isn't relevant-remote for an India search). Add a `work_region` / `remote_scope` signal
   and a dashboard facet; keep the `_derive_remote` keyword rule as the base.
2. **Grow `COMPANY_BOARDS`:** find correct slugs for the ones that returned 0 (snyk, confluent, hashicorp)
   and add more security unicorns. Big Workday employers (CrowdStrike / Palo Alto / Zscaler) have no simple
   public board API — skip unless a clean source appears.
3. **Publishing hygiene:** the daily publish must push from **one** machine only (avoid double pushes).
   `scripts/register-publish-task.ps1` designates the publisher by writing a gitignored `.publish-primary`
   marker (hostname + UTC timestamp); `scripts/publish.ps1` / `scripts/publish.sh` skip the git push on any
   machine whose marker is missing or names a different host, unless `-Force` / `--force` (or
   `JOBSCOPE_PUBLISH_FORCE=1`). `scripts/unregister-publish-task.ps1` retires a machine (removes the task +
   marker). The task on this machine is registered (`jobscope publish`, daily 08:00); on another machine run
   `register-publish-task.ps1` there only after retiring this one.
4. **Optional:** store the raw JobSpy `is_remote` separately so future re-derivations don't lose signal.

## 5. Guardrails (don't regress these)

- Keep the **code repo private** (early history has a work-email author; making it public would expose it).
- Publish only the **redacted** copy (`dashboard --public`) — never `data/dashboard.html`.
- `jobscope-dashboard` Pages must stay **Actions-based** (`build_type=workflow`), not legacy Jekyll.
- Publishing must originate **locally** (the DB is local/gitignored; CI can't regenerate the dashboard).
- CI installs only `pyyaml requests feedparser markdown pytest` — new code + tests must degrade gracefully
  without `pandas`/`python-jobspy`.
