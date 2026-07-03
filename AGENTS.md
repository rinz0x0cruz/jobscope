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
  `from jobscope.match import score_job` (etc.) must still work — re-export the public names from
  the package `__init__` so importers and tests don't change.
- **Keep the Python↔TS data contract in sync.** Editing `render.build_data` / `_job_record` /
  `_enrich_summary` / `_overview_data` means editing `web/src/lib/schema.ts` (ARCHITECTURE.md §9).

## Invariants (never break)

- No circular imports.
- `pytest`, `jobscope selftest`, and `npm run build` all green.
- Deterministic scoring unchanged — identical inputs produce identical scores/tiers.

## Modularity roadmap & file ownership

Phases run in dependency **waves**, one subagent at a time — **not** concurrently on shared files.
Edit only the files your phase owns; if you need a change elsewhere, note it in your report for the
orchestrator. Full detail in ARCHITECTURE.md §12.

| Phase | Owns (may edit) | Goal |
|-------|-----------------|------|
| **P-A** data-contract SSOT | `web/src/lib/schema.ts`, `tests/test_dashboard_json.py`, new `jobscope/schema/*.json` (optional) | Add `Application`/timeline types (seam #5); assert emitted `dashboard.json` matches the contract |
| **P-B** enrich registry | `jobscope/enrich/*`, `jobscope/config.py`, `jobscope/render.py` (`_enrich_summary` only) | `@source(...)` self-registration; a new source = one file |
| **P-C** config-drift guard | `tests/test_config*.py`, `config.example.yaml` | Test `config.example.yaml` keys ⊇ `DEFAULT_CONFIG` |
| **P-D** split `store.py` | `jobscope/store.py` → `jobscope/store/` package | Domain stores behind a `Store` facade; same public API |
| **P-E** split `match.py` | `jobscope/match.py` → `jobscope/match/` package | `seniority`/`experience`/`filters`/`scoring`; same public names |
| **Tier 3** package reorg | ALL (solo, last) | Group into `core/ingest/analyze/enrich/apply/deliver/cli`; keep root `__main__.py` |

When invoked as a phase subagent: read this file and ARCHITECTURE.md §9/§12 first, make only your
phase's edits, verify green with the commands above, then report changed files + test/build results.
