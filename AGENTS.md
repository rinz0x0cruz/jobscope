# AGENTS.md — jobscope

Operational guide for AI coding agents working in this repo. The deep architecture map lives in
[ARCHITECTURE.md](ARCHITECTURE.md) — read it before any structural work.

## What this is

A **deterministic-first, offline-first, AI-optional** resume-driven job scout. Python CLI
(`jobscope/`) + a Vite/React dashboard (`web/`), SQLite persistence. The core 80% (scoring,
filtering, parsing, persistence) runs with no network and no API key; AI and network calls are
optional and degrade gracefully. See ARCHITECTURE.md §1.

## Environment (Windows / PowerShell)

- **Python** runs from the venv: `.venv\Scripts\python.exe` — do **not** assume a global `python`.
- In a fresh shell, refresh PATH before tool calls:
  `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`
- npm is blocked by execution policy; prefix web commands with:
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force`

## Build / test / verify — must be green before you hand back

```powershell
.venv\Scripts\python.exe -m pytest -q                      # unit tests
.venv\Scripts\python.exe -m jobscope selftest              # offline self-test
.venv\Scripts\python.exe -m jobscope dashboard --emit-json # regenerate web/src/data/dashboard.json
cd web; npm run build                                       # tsc -b && vite build
```

Iterate with targeted tests (`pytest -q tests/test_x.py`); run the full suite + selftest before done.

## Conventions

- **Conventional Commits**: `type(scope): summary` (feat / fix / docs / refactor / test / chore).
- **Selective staging only — never `git add -A`.** Other sessions may hold uncommitted WIP; stage
  your files by explicit path. **Agents do not commit or push** unless explicitly told — the
  orchestrator reviews and commits centrally.
- **Deterministic-first.** No network/LLM in core paths; anything AI goes through `ai.chat()` and
  must have a deterministic fallback. Don't add dependencies without a strong need (the tool must
  run offline and dep-light).
- **Additive persistence only** — new columns via `store._ensure_columns()` /
  `ALTER TABLE ADD COLUMN`; never a destructive migration.
- **Preserve public import paths when splitting a module into a package.** After splitting,
  `from jobscope.analyze.match import score_job` (etc.) must still work — re-export the public names
  from the package `__init__` so importers and tests don't change.
- **Keep the Python↔TS data contract in sync.** Editing `deliver/render.py` `build_data` / `_job_record` /
  `_enrich_summary` / `_overview_data` means editing `web/src/lib/schema.ts` — and keeping
  `jobscope/deliver/schema/dashboard.schema.json` + `tests/test_dashboard_json.py` in step
  (ARCHITECTURE.md §9).

## Invariants (never break)

- No circular imports.
- `pytest`, `jobscope selftest`, and `npm run build` all green.
- Deterministic scoring unchanged — identical inputs produce identical scores/tiers.

## Modularity — what shipped

The incremental-refactor plan is **complete**: the data-contract/config guards (P-A/P-B/P-C), the
`store.py`/`match.py` package splits (P-D/P-E), and the whole-package reorg (Tier 3) all landed. Full
history in ARCHITECTURE.md §12. Landmarks, for orienting a change:

| Phase | Landed as | What it bought |
|-------|-----------|----------------|
| **P-A** data-contract SSOT *(done)* | `web/src/lib/schema.ts` (`Application`/`ApplicationEvent`), `jobscope/deliver/schema/dashboard.schema.json`, `tests/test_dashboard_json.py` | `applications[]` typed end-to-end (seam #5 closed); a test guards the emitted `dashboard.json` shape |
| **P-B** enrich registry *(done)* | `jobscope/enrich/registry.py` + `jobscope/enrich/__init__.py` | `@source(...)` self-registration; a new source = one module + a decorator |
| **P-C** config-drift guard *(done)* | `tests/test_config.py`, `config.example.yaml` | `config.example.yaml` keys ⊇ `DEFAULT_CONFIG` |
| **P-D** split `store.py` *(done)* | `jobscope/core/store/` package (`base` + `jobs`/`enrichment`/`applications`/`mail`/`profile`/`meta` mixins) | Domain mixins behind a `Store` facade; same public API |
| **P-E** split `match.py` *(done)* | `jobscope/analyze/match/` package (`seniority`/`experience`/`filters`/`scoring`/`routing`/`run`) | Layered submodules; same public/private names; identical scores |
| **Tier 3** package reorg *(done)* | `core/ingest/analyze/enrich/apply/deliver/cli` + thin root `__main__.py` | Flat package grouped by concern; `build_parser` + `cmd_*` + `main` now in `cli/__init__.py` |

**Opportunistic (optional, unscheduled):** split `resume.py` per-format parsers; split `tailor.py`
(deterministic vs AI); inline the thin `apply/brief.py`; retire `render.py`'s inline HTML template once
the React app is canonical; generate `schema.ts` from Python so the TS mirror can't drift.

When making a structural change: read this file and ARCHITECTURE.md §9/§12 first, edit by explicit path,
verify green with the commands above, then report changed files + test/build results.
