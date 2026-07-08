# jobscope — Architecture & Code Map

> A resume-driven job scout, enricher, and application-prep tool.
> **Deterministic-first, offline-first, AI-optional** — the core 80% (scoring, filtering,
> parsing, persistence) runs with no network and no API key; AI and network calls are
> optional upgrades that degrade gracefully.

This document is the living map of the codebase: what each module does, how they depend
on each other, the Python↔TypeScript data contract, and the modular sub-package
structure the codebase has settled into. Keep it current (see
[Keeping this doc current](#keeping-this-doc-current)).

---

## 1. Design philosophy

| Principle | What it means in code |
|-----------|-----------------------|
| **Deterministic-first** | `match`, `resume`, `mailrules`, `companies` are pure functions — no network, no LLM. Same input → same output. |
| **Offline-first** | Base layers have zero third-party network deps; scrapers/enrichers are best-effort and never break a run. |
| **AI-optional** | `ai.chat()` returns `None` when disabled; every AI caller has a deterministic fallback. The optional quorum backend accepts per-call `strategy`, `history`, and grounding `context` without changing the deterministic path. |
| **Additive persistence** | `store` upgrades old databases in place via `ALTER TABLE ADD COLUMN`; never a destructive migration. |
| **Best-effort enrichment** | Each enrich source is isolated; one failure is caught and does not stop the others. |

---

## 2. Repository layout

```
jobscope/
  jobscope/          Python package (the CLI + all logic)
    core/            Foundation: model, config, store/ (pkg), companies, httpx, ai
    ingest/          Acquire jobs & signals: scrape, ats, inbox, mailrules, reconcile
    analyze/         Deterministic core: match/ (pkg), classify, resume, profile, atscheck, coverage, insights
    enrich/          Best-effort intel (one module per source) + registry
    apply/           Tailor & submit: apply, tailor, outreach, interview, referrals, track, brief
    deliver/         Dashboards & exports: render, exporter, serve, pdf, email, schema/
    cli/             build_parser + cmd_* + main (+ pipeline, scaffold, selftest)
    __main__.py      Thin shim → cli.main (console-script + `python -m jobscope`)
  web/               Vite + React + TS dashboard (consumes the JSON contract; PWA/Pages UI)
    src/
  scripts/           Publish helpers, encrypted-apps template, cloud-refresh crypt/seed (crypt-file.mjs, seed-cloud-db.ps1)
  .github/           workflows/refresh.yml — cloud auto-refresh (scan Gmail + republish; encrypted DB on the `data` branch)
  tests/             pytest suite (offline; mirrors the module layout)
  data/              Runtime artifacts (SQLite db, dashboard json) — gitignored
  ARCHITECTURE.md    This file
  pyproject.toml     setuptools; console-script `jobscope`; find = ["jobscope*"]
```

---

## 3. Layered architecture

Modules live in concern sub-packages under `jobscope/` (`core`, `ingest`, `analyze`,
`enrich`, `apply`, `deliver`, `cli`); each group below is a real package on disk (see
[§2](#2-repository-layout)). This layered shape is the one the reorg landed on (see
[Modularity roadmap](#12-modularity-roadmap)).

```mermaid
flowchart TB
    CLI["cli (argparse + lazy imports) · __main__ shim"]
    PIPE["cli/pipeline · cli/scaffold · cli/selftest"]
    CLI --> PIPE

    subgraph INGEST["ingest"]
        scrape
        ats
        inbox
        mailrules
        reconcile
    end
    subgraph ANALYZE["analyze"]
        match
        classify
        resume
        profile
        atscheck
        coverage
        insights
    end
    subgraph ENRICH["enrich (package)"]
        coordinator["__init__ + registry"]
        comp
        stock
        reddit
        news
        glassdoor
        contacts
        ebrief["brief"]
    end
    subgraph APPLY["apply"]
        apply
        tailor
        outreach
        interview
        referrals
        track
        brief
    end
    subgraph DELIVER["deliver"]
        render
        exporter
        serve
        pdf
        email
    end

    CLI --> INGEST & ANALYZE & ENRICH & APPLY & DELIVER
    PIPE --> INGEST & ANALYZE & ENRICH & APPLY & DELIVER

    subgraph CORE["core — foundation"]
        model
        config
        store
        companies
        httpx
        ai
    end

    INGEST & ANALYZE & ENRICH & APPLY & DELIVER --> CORE

    WEB["web/ (React dashboard)"]
    DELIVER -. "dashboard.json contract" .-> WEB
```

**Purely dependency-free modules** (no internal imports — the stable bedrock):
`model`, `config`, `companies`, `httpx`, `mailrules`, plus the leaf enrich sources
(`comp`, `stock`, `reddit`, `news`, `glassdoor`). `store` depends only on `model`;
`ai` only on `config`. **No circular imports exist anywhere.**

---

## 4. Backend module inventory

LOC are exact (source lines incl. comments). Grouped by concern (= sub-package on disk).

### core — foundation (pure/near-pure, highest fan-in)

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [model.py](jobscope/core/model.py) | 228 | Core dataclasses + id/slug helpers | — | `Job`, `Resume`, `Application`, `Contact`, `MailEvent`, `job_id()`, `slugify()`, `derive_remote_scope()` |
| [config.py](jobscope/core/config.py) | 200 | Load YAML/JSON, deep-merge over `DEFAULT_CONFIG`, env-only secrets, AI/quorum strategy defaults | — | `DEFAULT_CONFIG`, `load_config()`, `api_key()`, `smtp_password()`, `inbox_password()` |
| [store/](jobscope/core/store/) | 527 | **Package** — SQLite persistence (10 tables) + additive migrations, split into `base` + `jobs`/`enrichment`/`applications`/`mail`/`profile`/`meta` mixins behind a `Store` facade | model | `Store`, `now_iso()` |
| [companies.py](jobscope/core/companies.py) | 128 | Curated prestige/size/funding tiers (deterministic) | — | `company_quality()`, `company_size()`, `company_funding()` |
| [httpx.py](jobscope/core/httpx.py) | 37 | Thin `requests` wrapper (UA, timeout, JSON) | — | `get()`, `get_json()`, `get_text()` |
| [ai.py](jobscope/core/ai.py) | 105 | OpenAI-compatible chat (Groq/Ollama) + optional quorum delegation with per-call strategy/history/context; bridges the keychain-resolved key into the environment for embedded quorum | config | `available()`, `strategy_for()`, `chat()` |

### ingest — acquire jobs & signals

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [scrape.py](jobscope/ingest/scrape.py) | 153 | JobSpy + ATS boards → `Job` upserts (per-term isolation) | model, store | `run()`, `_row_to_job()` |
| [ats.py](jobscope/ingest/ats.py) | 213 | Direct Greenhouse/Lever/Ashby board fetch | httpx, model, store | `fetch_company()`, `run()` |
| [inbox.py](jobscope/ingest/inbox.py) | 402 | Gmail IMAP sync (read-only, incremental) → weighted classify (+ optional quorum tie-break) → `mail_events`; drops transactional/OTP mail; `--reclassify` offline repair; recomputes the funnel after each sync | ats, config, model, store, mailrules, reconcile, (ai lazy) | `run()` |
| [mailrules.py](jobscope/ingest/mailrules.py) | 643 | Deterministic **weighted-keyword** email classification (smart-quote-normalized scoring + ambiguity flag) + transactional/OTP detection + company/role parsing (pure, no I/O) | — | `classify_signal()`, `classify_scored()`, `is_job_related()`, `is_transactional()`, `parse_company_role()`, `signal_to_status()`, `advance_status()`, `normalize_company()` |
| [reconcile.py](jobscope/ingest/reconcile.py) | 170 | Rebuild the funnel from the mail timeline — instance-split (reapply / concurrent roles) + conservative reclassify (drop OTP, downgrade false interview/assessment) | model, store, mailrules | `recompute()`, `reclassify()`, `split_instances()` |

### analyze — the deterministic core

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [match/](jobscope/analyze/match/) | 670 | **Package** — transparent fit scoring, tiers, filters, resume routing; split into `seniority`/`experience`/`filters`/`scoring`/`routing`/`run` submodules (all public + private names re-exported) | model, resume, (companies lazy) | `score_job()`, `apply_filters()`, `select_base()`, `run()`, `SENIORITY_RANK` |
| [classify.py](jobscope/analyze/classify.py) | 61 | Optional AI/quorum seniority + discipline tie-breaker, routed through the classify strategy | ai, match, model | `classify_seniority()` |
| [resume.py](jobscope/analyze/resume.py) | 345 | Parse Markdown/JSON-Resume/PDF/text → `Resume` + skills; seeds the search profile on first import | match, model, (profile lazy) | `import_resume()`, `parse_resume()`, `SKILL_LEXICON` |
| [profile.py](jobscope/analyze/profile.py) | 201 | Résumé-derived editable **search profile** (`data/profile.yaml`) that drives `scan` | model, resume | `build_profile()`, `load()`, `ensure_seeded()`, `apply_to_search()`, `run()` |
| [atscheck.py](jobscope/analyze/atscheck.py) | 217 | Deterministic **ATS parse check** — extracted fields + friendliness score + formatting warnings (+ optional JD keyword coverage) | model, (tailor lazy) | `ats_report()`, `coverage()`, `run()` |
| [coverage.py](jobscope/analyze/coverage.py) | 324 | Per-requirement JD↔résumé coverage (deterministic + optional AI); requirement extraction (perk/mission filtered) | model, resume, (tailor/ai lazy) | `coverage_report()`, `extract_requirements()`, `run()` |
| [insights.py](jobscope/analyze/insights.py) | 47 | Skill-gap analysis across matched jobs | resume, store | `skill_gap()`, `run()` |

### enrich — best-effort public intel (`enrich/` package)

| Module | LOC | Responsibility | Internal imports |
|--------|-----|----------------|------------------|
| [enrich/__init__.py](jobscope/enrich/__init__.py) | 78 | Per-company coordinator — iterates the source registry (toggles each by config) | registry, comp, stock, reddit, news, glassdoor, brief, contacts |
| [enrich/registry.py](jobscope/enrich/registry.py) | 60 | Source registry + `@source(...)` decorator; sources self-register at import | — |
| [enrich/stock.py](jobscope/enrich/stock.py) | 130 | Stock / IPO lookup (Yahoo, keyless) + 52wk position | httpx |
| [enrich/brief.py](jobscope/enrich/brief.py) | 84 | Risk-forward company brief (deterministic + optional AI) | ai, match |
| [enrich/contacts.py](jobscope/enrich/contacts.py) | 81 | Referral-lead discovery (search links + GitHub) | model, httpx |
| [enrich/reddit.py](jobscope/enrich/reddit.py) | 60 | Reddit sentiment (lexicon-based) | httpx |
| [enrich/news.py](jobscope/enrich/news.py) | 50 | Google News RSS + optional custom feeds | — |
| [enrich/comp.py](jobscope/enrich/comp.py) | 42 | Compensation (posting salary + Levels.fyi links) | — |
| [enrich/glassdoor.py](jobscope/enrich/glassdoor.py) | 27 | Glassdoor rating (defensive) | httpx |

### apply — tailor & submit

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [apply.py](jobscope/apply/apply.py) | 246 | Prep package + human-in-loop ATS autofill (Playwright); optional generative strategy for filled answers | ai, email, tailor, model, store | `prep()`, `apply()` |
| [tailor.py](jobscope/apply/tailor.py) | 198 | Per-job resume + cover tailoring (deterministic + AI/quorum rewrite grounded with full JD/news context) | ai, pdf, model, resume, store | `run()`, `analyze()` |
| [outreach.py](jobscope/apply/outreach.py) | 423 | Resolve a recruiter/HR contact (site-verified) + draft a tailored résumé email; preview/send guardrails; structured `/api/outreach` helpers | ai, email, tailor, model, store, httpx | `run()`, `api_preview()`, `api_send()`, `discover_emails()` |
| [interview.py](jobscope/apply/interview.py) | 112 | Interview-prep sheet (fit + JD topics + STAR + brief + referrals + notes); `--note` append | model, coverage, referrals, (tailor lazy) | `prep_sheet()`, `run()` |
| [referrals.py](jobscope/apply/referrals.py) | 136 | Network-activation digest + per-job referral view (leads + copy-ready draft) | store, (enrich.contacts lazy) | `pipeline_referrals()`, `paths_for()`, `run()` |
| [track.py](jobscope/apply/track.py) | 114 | Application funnel, status, follow-up reminders | model, store | `run()`, `run_new()` |
| [brief.py](jobscope/apply/brief.py) | 21 | Thin CLI wrapper → `enrich.brief.build()` | enrich.brief | `run()` |

### deliver — dashboards & exports

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [render.py](jobscope/deliver/render.py) | 272 | The JSON data contract for the React app — per-job records, overview, and the **Applications** board data (pipeline + kanban + email timelines) | companies, store | `build_data()`, `emit_json()`, `_job_record()`, `_application_records()`, `_overview_data()` |
| [pdf.py](jobscope/deliver/pdf.py) | 66 | Markdown → HTML → PDF (Playwright; degrades gracefully) | — | `markdown_to_html()`, `render_pdf()` |
| [email.py](jobscope/deliver/email.py) | 36 | SMTP summaries (optional) | config | `send()` |
| [serve.py](jobscope/deliver/serve.py) | ~430 | Serves the built SPA (`web/dist`) on 127.0.0.1 + a localhost-only, CSRF-guarded API: Refresh/publish (injects the Refresh widget), `/api/token`, and `/api/outreach` (recruiter preview/send) | render, store, (apply.outreach lazy) | `run()`, `perform_refresh()` |
| [exporter.py](jobscope/deliver/exporter.py) | 22 | Export ranked jobs to JSON/CSV | — | `run()` |

Plus [schema/dashboard.schema.json](jobscope/deliver/schema/dashboard.schema.json) — the JSON-Schema
artifact for the emitted `dashboard.json`, cross-checked by [tests/test_dashboard_json.py](tests/test_dashboard_json.py).

> **Note:** `render.py` is now a slim JSON emitter (~270 lines). The **React app in `web/`** is the single
> dashboard — served un-redacted locally by `jobscope serve` and published redacted to Pages — and owns the
> **Applications board** (kanban + per-application email timelines) and pipeline funnel. The data-contract
> logic (`build_data`/`_job_record`/`_application_records`/`_enrich_summary`/`_overview_data`/`emit_json`)
> is pinned by a JSON-Schema artifact + a contract test (§9); the legacy inline HTML `_TEMPLATE` has been
> removed.

### cli / orchestration

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [cli/__init__.py](jobscope/cli/__init__.py) | 519 | argparse dispatch for 28 subcommands — `build_parser` + all `cmd_*` + `main` (lazy per-command imports; `--db` is authoritative for the run) | ~all (lazy) | `main()`, `build_parser()` |
| [pipeline.py](jobscope/cli/pipeline.py) | 46 | One-shot `scan → match → enrich → prep → digest` | apply, email, enrich, match, scrape | `run()` |
| [selftest.py](jobscope/cli/selftest.py) | 233 | Offline self-tests (validate the full stack, no network), including quorum strategy defaults | model, config, store, match, mailrules, ats, inbox, ai | `run()` |
| [scaffold.py](jobscope/cli/scaffold.py) | 50 | `init`: scaffold config + data dir (non-destructive) | config | `run()` |
| [__main__.py](jobscope/__main__.py) | 9 | Thin entry-point shim at the package root (`from .cli import main`) | cli | `main` (re-exported) |
| [__init__.py](jobscope/__init__.py) | 6 | Package marker, `__version__` | — | `__version__` |

**Totals:** ~62 Python modules across 8 sub-packages (incl. the `store/` and `match/` sub-packages and
9 enrich modules) ≈ **7,300 LOC** of Python.

### web/ — React dashboard (SPA)

The single dashboard is a Vite + React + TypeScript PWA in `web/` that consumes the baked `dashboard.json`
(and, for a published build, a lazily-fetched AES-encrypted whole-site blob unlocked in-browser). It is served
two ways: un-redacted via `jobscope serve` on localhost, and redacted to GitHub Pages by the publish scripts —
where a passphrase swaps the redacted data for the full un-redacted payload at runtime.

- **Data flow:** `web/src/data/index.ts` imports the baked JSON → `App.tsx` holds URL/localStorage view state
  (`hooks/useSearchState`) → `lib/filters.ts` (tab pool → facets → fuzzy search) → the Overview / list /
  Applications surfaces. `lib/schema.ts` mirrors the Python contract (§10).
- **Surfaces:** a bento **Overview** (`components/overview/*` — Fit-distribution `Donut`, `Bars`,
  `SkillConstellation`, `TopMatches`), the ranked **list** (`JobList`/`JobCard`/`JobDrawer` with an archived
  job-description snapshot and, under local `serve`, an *Email recruiter* panel `RecruiterOutreach` →
  `/api/outreach`), and an **Applications** board (`components/applications/*` — List/Compact/Table/Grouped
  view switcher, Pipeline health, per-app email `ActivityFeed`, and an inline-SVG `PipelineFlow` Sankey).
- **Whole-site unlock:** `lib/unlock.ts` fetches (lazily) + AES-GCM-decrypts the encrypted blob; a header
  `UnlockControl` / `UnlockForm` (and the Applications `ApplicationsGate`) take the passphrase and swap the full
  un-redacted payload into `App` state (cached in sessionStorage for the tab).
- **Chrome:** `Header` (logo + search + ⌘K command pill + Refresh button), a generative `HeroBackdrop`
  (six `?hero=` variants, reduced-motion aware; touch / small screens default to the CSS `aurora`, and the canvas
  variants freeze + rescale under a pinch-zoom so the backdrop never glitches on mobile), and a `cmdk` command
  palette (`SearchPalette`).
- **Refresh:** `lib/refresh.ts` drives the header Refresh button — pull-latest (service-worker update + reload)
  and an on-demand Gmail rescan that POSTs `workflow_dispatch` when a fine-grained token is stored (else
  deep-links to GitHub), throttle-safe via a client cooldown + run de-dupe.
- **Tests:** a Vitest + Testing-Library suite in `web/test/` (kept outside `src/` so the production `tsc -b`
  never compiles it) covers the lib modules + the Refresh button. Runs via `npm test` and the `web` job in
  `.github/workflows/ci.yml`.

---

## 5. Coupling hotspots

Fan-in = how many modules import it; fan-out = how many it imports (internal only).

| Module | LOC | Fan-in | Fan-out | Read |
|--------|-----|:------:|:-------:|------|
| **core/store/** | 527 | ~11 | 1 | Every command persists through it. **Split done (P-D):** `base` + `jobs`/`enrichment`/`applications`/`mail`/`profile`/`meta` mixins behind a `Store` facade — same public API, one shared connection. |
| **core/model.py** | 228 | ~12 | 0 | Highest fan-in but **pure** — the ideal shape. Leave as-is. |
| **analyze/match/** | 670 | ~6 | 3 | Largest logic area. **Split done (P-E):** `seniority`/`experience`/`filters`/`scoring`/`routing`/`run` submodules, layered so leaves never import up; scores identical, all names re-exported. |
| **deliver/render.py** | 272 | 2 | 2 | Slim JSON emitter now that the inline HTML `_TEMPLATE` has retired (the React app in `web/` is the single dashboard). Healthy. |
| **cli/__init__.py** | 519 | 0 | ~28 | Orchestrator (`build_parser` + `cmd_*` + `main`); wide fan-out but **lazy imports** keep startup light. Healthy. |
| **core/config.py** | 200 | ~6 | 0 | Pure config layer, including AI/quorum defaults. Healthy. |
| **enrich/__init__.py** | 78 | 2 | 8 | Coordinator that **iterates the source registry** (P-B done); sources self-register via `@source(...)`. Healthy. |
| **core/ai.py** | 105 | ~4 | 1 | Optional layer; all callers have deterministic fallbacks. Quorum-only `strategy`/`history`/`context` arguments are additive and ignored by the single-model fallback. Healthy. |

---

## 6. Runtime flows

### CLI dispatch (`cli/__init__.py`)

The root [__main__.py](jobscope/__main__.py) is a thin shim (`from .cli import main`); the parser and
commands live in [cli/__init__.py](jobscope/cli/__init__.py). `build_parser()` defines one `argparse`
parser with subparsers; each subcommand does `set_defaults(func=cmd_<name>)`, and `main()` calls
`args.func(args, cfg)` inside a `Store` context manager. **Feature modules are imported lazily inside
each `cmd_*`** so the base CLI stays offline-friendly.

28 subcommands: `init`, `resume import`, `profile`, `scan`, `match`, `pipeline`, `enrich`,
`tailor`, `prep`, `apply`, `outreach`, `dashboard`, `serve`, `refresh`, `track`, `inbox`,
`new`, `referrals`, `interview`, `gaps`, `brief`, `atscheck`, `coverage`, `export`,
`purge`, `prune`, `secrets`, `selftest`.

### Pipeline (`pipeline.run`)

```mermaid
flowchart LR
    scan["scan · scrape.run"] --> match["match · match.run"]
    match --> enrich["enrich · enrich.run"]
    enrich --> prep["prep top-N Strong/Good · apply.prep"]
    prep --> digest["digest · log + optional email"]
```

Stages communicate **only through the store** (no shared in-memory state), which keeps each
stage independently runnable from its own subcommand.

### Optional AI/quorum overlay (`core/ai.py`)

All AI paths call [core/ai.py](jobscope/core/ai.py). `available(cfg)` gates the layer, and
`chat()` returns `None` on disabled config, missing keys, import failure, HTTP failure, or an empty quorum
result. Callers always keep a deterministic fallback.

When `quorum.enabled` is true and the optional `quorum` package is installed, `chat()` delegates to
`quorum.api.chat(...)` before the single-model OpenAI-compatible path. The delegation is additive:

- `strategy=ai.strategy_for(cfg, "generative")` routes summaries, cover letters, and filled answers through
  `quorum.strategy_generative` (default `council`).
- `strategy=ai.strategy_for(cfg, "classify")` routes seniority/discipline and ambiguous inbox-label calls
  through `quorum.strategy_classify` (default `ensemble`).
- `context=[...]` carries grounding data for generative calls (full job description and optional news hook);
  quorum frames it as DATA, not instructions.
- A `TypeError` retry preserves compatibility with older quorum builds that do not yet accept `strategy=`.
- Before delegating, `chat()` bridges the resolved key into `os.environ[ai.api_key_env]` (keychain-first via
  `config.api_key()`) so the **embedded** quorum backend — which reads provider keys from the environment —
  authenticates without a separate `.env`. Nothing is written to disk; the value is only exported in-process.

If quorum is absent or returns `None`, the single-model fallback ignores `strategy`/`history`/`context` and
uses the existing prompt/cache path.

---

## 7. Persistence model (`core/store/`)

A single `Store` **facade** over SQLite, composed from per-concern mixins (`base` + `jobs`/
`enrichment`/`applications`/`mail`/`profile`/`meta`) over one shared connection. **10 tables**: `jobs`,
`enrichment`, `contacts`,
`applications`, `profile`, `resumes`, `meta`, `ai_cache`, `runs`, `mail_events`.

**Migration pattern** — `_ensure_columns()` reads `PRAGMA table_info(...)` and issues
`ALTER TABLE ... ADD COLUMN` for any missing field. New columns (e.g. `resume_base`,
`remote_scope`, `ai_seniority`, `brief_json`) were all added this way, so older databases
upgrade silently and older code ignores unknown columns.

Representative API: `upsert_job()`, `update_score()`, `update_ai_seniority()`, `jobs()`,
`get_job()`, `save_enrichment()`, `get_enrichment()`, `save_contacts()`, `contacts_for()`,
`set_application()`, `applications()`, `get_application()`, `upsert_mail_event()`, `mail_events()`,
`ai_cache_get/put()`, `log_run()`.

---

## 8. Web dashboard (`web/` + encrypted apps shell)

Vite + React 19 + TS + Tailwind v4 + TanStack Router (hash) + Motion + Lottie. The build bakes in
[web/src/data/dashboard.json](web/src/data/dashboard.json) (emitted by `jobscope dashboard --emit-json`).
The public Pages build is redacted; with `-Encrypted`, applications are baked in as an AES-256-GCM blob
([web/src/data/applications.encrypted.json](web/src/data/index.ts)) that the Applications tab decrypts
in-browser. [scripts/apps-template.html](scripts/apps-template.html) remains a standalone reference shell.

| Area | Files | Responsibility |
|------|-------|----------------|
| **Entry** | [main.tsx](web/src/main.tsx), [router.tsx](web/src/router.tsx), [App.tsx](web/src/App.tsx) | Mount; hash route `/` with zod-validated search params; wire filters→search→display |
| **Data** | [data/index.ts](web/src/data/index.ts) | Static import of `dashboard.json` (+ optional `applications.encrypted.json` blob) typed as `DashboardData` |
| **Contract** | [lib/schema.ts](web/src/lib/schema.ts) | TS mirror of the Python payload (keep 1:1) |
| **State** | [lib/urlState.ts](web/src/lib/urlState.ts), [hooks/useSearchState.ts](web/src/hooks/useSearchState.ts) | URL = single source of truth; `FACETS`, `searchSchema`, `TAB_VALUES` |
| **Filter/search** | [lib/filters.ts](web/src/lib/filters.ts), [lib/search.ts](web/src/lib/search.ts), [lib/overview.ts](web/src/lib/overview.ts), [lib/format.ts](web/src/lib/format.ts) | `tabPool`→`applyFacets`→`makeFuse`→`fuzzy`→`buildDisplayItems`; Fuse.js; formatting |
| **Components** | `Header`, `SignalLottie`, `CyberSakura`, `Tabs`, `Switch`, `JobList`, `JobCard`, `JobDrawer`, `Kpis`, `applications/*`, `filters/*`, `overview/*` | Virtualized list, deep-linkable drawer, facets, KPI/donut/bars, Applications board, animated visual shell |
| **Hooks** | [hooks/useTheme.ts](web/src/hooks/useTheme.ts) | Dark/light toggle |
| **Motion helpers** | [lib/spotlight.ts](web/src/lib/spotlight.ts), [styles/theme.css](web/src/styles/theme.css) | Cursor-follow card spotlight, animated gradients, status rails, cyber-sakura leaves, reduced-motion guard |

**State pipeline** (all in `App.tsx`, driven by the URL):

```mermaid
flowchart LR
    URL[(URL search params)] --> S["useSearchState()"]
    S --> tabPool --> applyFacets --> makeFuse --> fuzzy --> buildDisplayItems --> JobList
    S --> JobDrawer
```

**Visual/motion layer:** the dashboard has a self-contained animated treatment: `SignalLottie` renders a
briefcase/scope mark over local Lottie data, `CyberSakura` draws a right-rail SVG cyber tree with falling
leaf spans, `SkillConstellation` renders the Overview skill-gap graph with selectable nodes, and `theme.css`
owns the aurora gradients, cursor spotlight, status rails, custom scrollbars, and reduced-motion fallbacks.
None of this changes the JSON contract or deterministic backend behavior.

**Layout width:** the React dashboard's main content rail is controlled in [web/src/App.tsx](web/src/App.tsx)
by the Tailwind max-width class on `<main>` (`max-w-6xl` as of this map). The cyber-sakura right rail is
positioned in [web/src/styles/theme.css](web/src/styles/theme.css) and should be checked in browser after
any width change so it stays decorative and never overlaps controls.

**Resume facet visibility:** `JobRow.base` is emitted from `job.resume_base`, exposed as the `resume` facet
in [web/src/lib/urlState.ts](web/src/lib/urlState.ts), and rendered by [FacetBar.tsx](web/src/components/filters/FacetBar.tsx)
only when there are 2+ available options. If it looks missing, the dataset probably has one distinct resume
base or the user has not rerun `match` after importing multiple named resumes.

**Encrypted applications shell (optional standalone):** the default `-Encrypted` publish bakes the blob into
the SPA's Applications tab ([web/src/components/applications/ApplicationsGate.tsx](web/src/components/applications/ApplicationsGate.tsx)
decrypts it in-browser). [scripts/apps-template.html](scripts/apps-template.html) is intentionally not part of
the Vite bundle; `scripts/build-secure-apps.mjs` can still inject an encrypted payload into it to produce a
standalone page. The shell has its own CSS/JS for pipeline bars, status rails, and cursor spotlight, and must
preserve `window.__ENC__ = __ENC_BLOB__;` so the sensitive payload remains encrypted at rest on Pages.

**Cloud auto-refresh ([.github/workflows/refresh.yml](.github/workflows/refresh.yml)).** The site can refresh
without a local machine: a scheduled + `workflow_dispatch` Action restores the encrypted DB, runs
`inbox → match` (AI off), re-saves the DB, and publishes — so a phone (the GitHub mobile *Run workflow*
button) can trigger a scan. The DB never leaves in the clear: it is AES-256-GCM/PBKDF2-encrypted by
[scripts/crypt-file.mjs](scripts/crypt-file.mjs) and force-pushed as a single blob to a private **`data`**
branch (seeded once from local by [scripts/seed-cloud-db.ps1](scripts/seed-cloud-db.ps1)); only the redacted
dashboard + the passphrase-encrypted applications blob reach `gh-pages`. Five repo secrets gate it
(`JOBSCOPE_CONFIG`, `JOBSCOPE_DB_KEY`, `JOBSCOPE_APPS_PASSPHRASE`, `JOBSCOPE_GMAIL_APP_PW[_2]`); missing any,
the job no-ops. Note the workflow only **pushes** `gh-pages` — the actual publish is GitHub's separate
"pages build and deployment" run, so a green refresh does not by itself prove a live update.

---

## 9. The Python↔TypeScript data contract

This is the **highest-friction seam** in the codebase: a change on one side must be mirrored
by hand on the other.

```mermaid
flowchart LR
    subgraph py["Python (deliver/render.py)"]
        build_data --> job["_job_record"]
        build_data --> ov["_overview_data"]
        build_data --> apprec["_application_records"]
        job --> es["_enrich_summary"]
        build_data --> emit["emit_json"]
    end
    emit --> json[("data/dashboard.json")]
    json --> ts["web/src/lib/schema.ts (types)"]
    ts --> react["App.tsx + components"]
```

`build_data(cfg, store, public)` → `{ generated, total, rows[], overview, applications[] }`;
`emit_json` writes it to `data/dashboard.json`. `_redact_public()` clears `contacts`,
`rationale`, `base`, `overview.funnel`, and `overview.targets` for the public build.

### Coupling seams (edit both sides together)

| # | Field / shape | Python source | TS sink | Risk |
|---|---------------|---------------|---------|------|
| 1 | `Tier` enum | `TIER_COLORS` keys + `job.tier` | `Tier`, `TIER_COLOR`, `--strong/good/stretch/skip` in `theme.css` | New/renamed tier breaks colors, filters, sort |
| 2 | `JobRow` fields (27) | `_job_record()` dict keys | `JobRow` interface | A renamed Python key silently becomes `undefined` in TS |
| 3 | `EnrichSummary` (nested) | `_enrich_summary()` | `EnrichSummary`/`StockSummary`/`CompSummary`/`RedditSummary`/`NewsItem` | Structural drift cascades |
| 4 | `Overview` | `_overview_data()` | `Overview` | `funnel`/`gaps`/`considered`/`targets` must line up |
| 5 | **`applications[]`** ✅ | `_application_records()` → `applications[]` (emitted **and** rendered in the HTML dashboard's Applications board) | `Application` + `ApplicationEvent` interfaces; `applications?` on `DashboardData` | **Closed** — the TS types exist and [tests/test_dashboard_json.py](tests/test_dashboard_json.py) guards the emitted shape; the React app can now mirror the HTML board |
| 6 | Facet keys | job fields (`base`,`country`,`place`,`remote`,`funding`,`remote_scope`) | `FACETS`, `FacetKey`, `searchSchema`, `FacetBar` | A new facet = 4 TS edits |
| 7 | Country/place values | `_country_of()`, `_place_of()` | displayed as-is | Grouping changes fragment facet options |
| 8 | Salary string | `_fmt_salary()` | `format.ts:compLabel()` | Python owns the format; TS cannot reparse |
| 9 | Stock/comp field pick | `_enrich_summary()` key subset | `format.ts:stockLabel()` | Added stock field invisible until schema updated |
| 10 | Public redaction | `_redact_public()` | no type-level public/private distinction | A missed field could leak private data |
| 11 | `gaps` tuple | `[[skill, count]]` | `[string, number][]` | Structural change breaks index access |
| 12 | Visual shell classes | `web/src/components/*`, `scripts/apps-template.html` | `theme.css` + encrypted apps inline CSS | Class drift silently drops animation/status affordances |

> **Mitigation (P-A · done):** a JSON-Schema artifact lives at
> [jobscope/deliver/schema/dashboard.schema.json](jobscope/deliver/schema/dashboard.schema.json) and a
> structural contract test ([tests/test_dashboard_json.py](tests/test_dashboard_json.py)) asserts the
> emitted `dashboard.json` matches the shape (and that the public build is redacted). *Opportunistic
> next:* generate `schema.ts` from Python so the mirror can't drift.
> The visual shell has a lightweight source-asset guard in [tests/test_web_assets.py](tests/test_web_assets.py)
> for Lottie/cyber-sakura/spotlight wiring and encrypted applications shell markers.

---

## 10. Extension recipes (how to add X today)

**Add a CLI subcommand:** write `cmd_<name>(args, cfg)` in [cli/__init__.py](jobscope/cli/__init__.py),
add a `sub.add_parser(...)` with `set_defaults(func=cmd_<name>)`, put logic in a feature module
(lazy-import it inside `cmd_<name>`).

**Add an enrichment source:** create `enrich/<src>.py` exposing `enrich(company, ...)` and decorate it
with `@source(section=..., config_key=...)` from [enrich/registry.py](jobscope/enrich/registry.py); add
the module to the import line in [enrich/__init__.py](jobscope/enrich/__init__.py) so its decorator runs
at import (import = register — no `if cfg[...]` ladder edit); add its toggle to the `enrich` section of
`DEFAULT_CONFIG` ([core/config.py](jobscope/core/config.py)); surface fields via `_enrich_summary` +
`schema.ts`.

**Add an AI-assisted path:** call `ai.chat()` with a deterministic fallback in the caller. For quorum-aware
tasks, pass `strategy=ai.strategy_for(cfg, "generative")` for prose generation or
`strategy=ai.strategy_for(cfg, "classify")` for constrained labels. Pass `context=[{"title": ..., "text": ...}]`
only for grounding data; never make scoring, filtering, storage, or CLI success depend on an LLM response.

**Add a `Job` field end-to-end:** add it to the `Job` dataclass ([model.py](jobscope/core/model.py)) →
add the column to `SCHEMA` + `_ensure_columns()` ([store/base.py](jobscope/core/store/base.py)) → set it
in `scrape`/`ats` → emit it in `_job_record` ([render.py](jobscope/deliver/render.py)) → add it to `JobRow`
  ([schema.ts](web/src/lib/schema.ts)) → use it in components.

**Add a web facet:** add the key to `FACETS`, `FacetKey`, and `searchSchema`
([urlState.ts](web/src/lib/urlState.ts)); render it in `FacetBar`; ensure the underlying field
is present on `JobRow`.

**Add a visual dashboard effect:** keep it self-contained in `web/src` or `theme.css`; no runtime CDN/fetch.
Decorative elements must be `aria-hidden` and `pointer-events: none`; interactive card effects should use
[lib/spotlight.ts](web/src/lib/spotlight.ts) or CSS variables rather than ad hoc listeners. If the same
affordance belongs on the encrypted applications page, mirror it in [scripts/apps-template.html](scripts/apps-template.html)
without touching the encrypted payload marker.

---

## 11. What's already healthy (leave alone)

- **No circular imports**; a clean acyclic dependency graph.
- **Pure bedrock** (`model`, `config`, `companies`, `httpx`, `mailrules`) — trivially testable.
- **Lazy CLI imports** keep startup fast and offline-friendly.
- **Additive migrations** — safe, reversible-by-omission schema evolution.
- **Isolated enrich sources** — best-effort, one failure never cascades.
- **Deterministic core with optional AI overlay** — respected consistently.

---

## 12. Modularity roadmap — shipped

The plan was **document now, refactor incrementally**. All three tiers have since landed; this
section is now a record of what shipped (plus the few genuinely-optional ideas left).

### Tier 1 — data-contract & config guards ✅ done

- **P-A · Data-contract SSOT — done.** The `applications[]` array is typed end-to-end:
  `Application` + `ApplicationEvent` interfaces and `applications?` on `DashboardData`
  ([web/src/lib/schema.ts](web/src/lib/schema.ts)); a JSON-Schema artifact
  ([jobscope/deliver/schema/dashboard.schema.json](jobscope/deliver/schema/dashboard.schema.json))
  and a structural contract test ([tests/test_dashboard_json.py](tests/test_dashboard_json.py))
  assert the emitted `dashboard.json` matches the shape and that the public build is redacted
  (seam #5 closed). *Invariant held:* the JSON shape stays identical.
- **P-B · Enrichment registry — done.** [enrich/__init__.py](jobscope/enrich/__init__.py) iterates
  `SECTION_SOURCES`; each source self-registers via the `@source(...)` decorator in
  [enrich/registry.py](jobscope/enrich/registry.py). A new intel source is one module + a decorator
  — the old `if cfg[...]` ladder is gone. *Invariant held:* each source stays independent and
  best-effort.
- **P-C · Config-drift guard — done.** [tests/test_config.py](tests/test_config.py) asserts
  `config.example.yaml` covers every `DEFAULT_CONFIG` key path. *Invariant held:* env-only secrets.

### Tier 2 — structural splits ✅ done

- **P-D · `store.py` → [core/store/](jobscope/core/store/) package — done.** `base` (connection +
  `SCHEMA` + additive `_ensure_columns`) plus `jobs`/`enrichment`/`applications`/`mail`/`profile`/
  `meta` mixins composed behind the `Store` facade. `from jobscope.core.store import Store` / `now_iso`
  unchanged; migrations still additive; same public method names.
- **P-E · `match.py` → [analyze/match/](jobscope/analyze/match/) package — done.**
  `seniority`/`experience`/`filters`/`scoring`/`routing`/`run` submodules, layered so leaves never
  import up. Scoring stays a pure, network-free function — identical scores; all public *and* private
  names are re-exported so tests/selftest are unchanged.

### Tier 3 — package reorganization ✅ done

The formerly-flat package is now grouped into concern sub-packages (§2/§3):

```
jobscope/
  core/      model, config, store/ (pkg), companies, httpx, ai
  ingest/    scrape, ats, inbox, mailrules
  analyze/   match/ (pkg), classify, resume, insights
  enrich/    sources + registry (already a package)
  apply/     apply, tailor, track, brief
  deliver/   render, exporter, serve, pdf, email, schema/
  cli/       build_parser + cmd_* + main (+ pipeline, scaffold, selftest)
  __main__.py  ← thin shim at the root: `from .cli import main`
```

The entry point stayed put — `pyproject.toml` maps `jobscope = "jobscope.__main__:main"` and
`python -m jobscope` both resolve to the root `__main__.py` shim. `[tool.setuptools.packages.find]
include = ["jobscope*"]` auto-discovers every sub-package (each has an `__init__.py`). Backend uses
relative imports (`from ..core.model import ...` across groups, `from .` within a group); tests use
absolute imports (`from jobscope.analyze.match import ...`). No compatibility shims — every call site
was updated.

### Opportunistic (optional, unscheduled)

- Split `resume.py` per-format parsers; split `tailor.py` (deterministic `analyze` vs AI rewrite);
  inline the thin [apply/brief.py](jobscope/apply/brief.py) wrapper.
- ~~Retire `render.py`'s inline HTML `_TEMPLATE`~~ **done** — `render.py` is now a slim JSON emitter; the
  React app in `web/` is the single dashboard (un-redacted locally via `jobscope serve`, redacted on Pages).
- Generate `schema.ts` from the Python shapes (or the JSON Schema) so the TS mirror can't drift.

**Invariants held across every tier:** deterministic-first, additive migrations, zero circular
imports; `pytest` + `jobscope selftest` + `npm run build` green.

---

## Keeping this doc current

Update this file when you:

- add/rename/move a module (§4 inventory) or change an import edge (§3/§5);
- change the emitted JSON shape — touch [render.py](jobscope/deliver/render.py) `build_data`/`_job_record`/
  `_enrich_summary`/`_overview_data` or [schema.ts](web/src/lib/schema.ts), and keep
  [deliver/schema/dashboard.schema.json](jobscope/deliver/schema/dashboard.schema.json) +
  [tests/test_dashboard_json.py](tests/test_dashboard_json.py) in step (§9 seam table);
- complete a roadmap item (§12) — move it to "shipped" and note the commit.

Consider adding a lightweight pointer to this file from the README. The JSON-Schema contract test
([tests/test_dashboard_json.py](tests/test_dashboard_json.py)) is the machine-checked half of §9.
