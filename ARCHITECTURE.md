# jobscope — Architecture & Code Map

> A resume-driven job scout, enricher, and application-prep tool.
> **Deterministic-first, offline-first, AI-optional** — the core 80% (scoring, filtering,
> parsing, persistence) runs with no network and no API key; AI and network calls are
> optional upgrades that degrade gracefully.

This document is the living map of the codebase: what each module does, how they depend
on each other, the Python↔TypeScript data contract, and a phased roadmap for making the
project more modular as features are added. Keep it current (see
[Keeping this doc current](#keeping-this-doc-current)).

---

## 1. Design philosophy

| Principle | What it means in code |
|-----------|-----------------------|
| **Deterministic-first** | `match`, `resume`, `mailrules`, `companies` are pure functions — no network, no LLM. Same input → same output. |
| **Offline-first** | Base layers have zero third-party network deps; scrapers/enrichers are best-effort and never break a run. |
| **AI-optional** | `ai.chat()` returns `None` when disabled; every AI caller (`classify`, `tailor`, `enrich/brief`) has a deterministic fallback. |
| **Additive persistence** | `store` upgrades old databases in place via `ALTER TABLE ADD COLUMN`; never a destructive migration. |
| **Best-effort enrichment** | Each enrich source is isolated; one failure is caught and does not stop the others. |

---

## 2. Repository layout

```
jobscope/
  jobscope/          Python package (the CLI + all logic)
    enrich/          Enrichment sub-package (one module per intel source)
  web/               Vite + React + TS dashboard (consumes the JSON contract)
    src/
  tests/             pytest suite (offline; mirrors the module layout)
  data/              Runtime artifacts (SQLite db, dashboard json) — gitignored
  ARCHITECTURE.md    This file
  pyproject.toml     setuptools; console-script `jobscope`; find = ["jobscope*"]
```

---

## 3. Layered architecture

Modules today live **flat** in `jobscope/`, but they form clear conceptual layers.
The groups below double as the **target sub-package layout** (see
[Modularity roadmap](#12-modularity-roadmap)).

```mermaid
flowchart TB
    CLI["cli · __main__ (argparse + lazy imports)"]
    PIPE["pipeline / scaffold / selftest"]
    CLI --> PIPE

    subgraph INGEST["ingest"]
        scrape
        ats
        inbox
        mailrules
    end
    subgraph ANALYZE["analyze"]
        match
        classify
        resume
        insights
    end
    subgraph ENRICH["enrich (package)"]
        coordinator["__init__"]
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

LOC are exact (source lines incl. blanks/comments). Grouped by concern (= target sub-package).

### core — foundation (pure/near-pure, highest fan-in)

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [model.py](jobscope/model.py) | 228 | Core dataclasses + id/slug helpers | — | `Job`, `Resume`, `Application`, `Contact`, `MailEvent`, `job_id()`, `slugify()`, `derive_remote_scope()` |
| [config.py](jobscope/config.py) | 176 | Load YAML/JSON, deep-merge over `DEFAULT_CONFIG`, env-only secrets | — | `DEFAULT_CONFIG`, `load_config()`, `api_key()`, `smtp_password()`, `inbox_password()` |
| [store.py](jobscope/store.py) | 457 | SQLite persistence (10 tables) + additive migrations | model | `Store`, `now_iso()` |
| [companies.py](jobscope/companies.py) | 128 | Curated prestige/size/funding tiers (deterministic) | — | `company_quality()`, `company_size()`, `company_funding()` |
| [httpx.py](jobscope/httpx.py) | 37 | Thin `requests` wrapper (UA, timeout, JSON) | — | `get()`, `get_json()`, `get_text()` |
| [ai.py](jobscope/ai.py) | 82 | OpenAI-compatible chat (Groq/Ollama); optional | config | `available()`, `chat()` |

### ingest — acquire jobs & signals

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [scrape.py](jobscope/scrape.py) | 153 | JobSpy + ATS boards → `Job` upserts (per-term isolation) | model, store | `run()`, `_row_to_job()` |
| [ats.py](jobscope/ats.py) | 213 | Direct Greenhouse/Lever/Ashby board fetch | httpx, model, store | `fetch_company()`, `run()` |
| [inbox.py](jobscope/inbox.py) | 283 | Gmail IMAP sync (read-only, incremental) → classify → `mail_events` → advance funnel | ats, config, model, store, mailrules | `run()` |
| [mailrules.py](jobscope/mailrules.py) | 340 | Deterministic email classification + company/role parsing (pure, no I/O) | — | `classify_signal()`, `is_job_related()`, `parse_company_role()`, `signal_to_status()`, `advance_status()`, `normalize_company()` |

### analyze — the deterministic core

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [match.py](jobscope/match.py) | 508 | Transparent fit scoring, tiers, filters, resume routing | model, resume, (companies lazy) | `score_job()`, `apply_filters()`, `select_base()`, `run()`, `SENIORITY_RANK` |
| [classify.py](jobscope/classify.py) | 60 | Optional AI seniority + discipline tie-breaker | ai, match, model | `classify_seniority()` |
| [resume.py](jobscope/resume.py) | 339 | Parse Markdown/JSON-Resume/PDF/text → `Resume` + skills | match, model | `import_resume()`, `parse_resume()`, `SKILL_LEXICON` |
| [insights.py](jobscope/insights.py) | 47 | Skill-gap analysis across matched jobs | resume, store | `skill_gap()`, `run()` |

### enrich — best-effort public intel (`enrich/` package)

| Module | LOC | Responsibility | Internal imports |
|--------|-----|----------------|------------------|
| [enrich/__init__.py](jobscope/enrich/__init__.py) | 72 | Per-company coordinator (toggles each source by config) | brief, comp, contacts, glassdoor, news, reddit, stock |
| [enrich/stock.py](jobscope/enrich/stock.py) | 128 | Stock / IPO lookup (Yahoo, keyless) + 52wk position | httpx |
| [enrich/brief.py](jobscope/enrich/brief.py) | 84 | Risk-forward company brief (deterministic + optional AI) | ai, match |
| [enrich/contacts.py](jobscope/enrich/contacts.py) | 81 | Referral-lead discovery (search links + GitHub) | model, httpx |
| [enrich/reddit.py](jobscope/enrich/reddit.py) | 58 | Reddit sentiment (lexicon-based) | httpx |
| [enrich/news.py](jobscope/enrich/news.py) | 47 | Google News RSS + optional custom feeds | — |
| [enrich/comp.py](jobscope/enrich/comp.py) | 39 | Compensation (posting salary + Levels.fyi links) | — |
| [enrich/glassdoor.py](jobscope/enrich/glassdoor.py) | 25 | Glassdoor rating (defensive) | httpx |

### apply — tailor & submit

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [apply.py](jobscope/apply.py) | 243 | Prep package + human-in-loop ATS autofill (Playwright) | ai, email, tailor, model, store | `prep()`, `apply()` |
| [tailor.py](jobscope/tailor.py) | 190 | Per-job resume + cover tailoring (deterministic + AI rewrite) | ai, pdf, model, resume, store | `run()`, `analyze()` |
| [track.py](jobscope/track.py) | 114 | Application funnel, status, follow-up reminders | model, store | `run()`, `run_new()` |
| [brief.py](jobscope/brief.py) | 21 | Thin CLI wrapper → `enrich.brief.build()` | enrich.brief | `run()` |

### deliver — dashboards & exports

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [render.py](jobscope/render.py) | 850 | HTML dashboard (job buckets + **Applications** board: pipeline-flow Sankey + kanban + email timelines) **+** the JSON data contract | companies, store | `build()`, `build_data()`, `emit_json()`, `_application_records()` |
| [pdf.py](jobscope/pdf.py) | 66 | Markdown → HTML → PDF (Playwright; degrades gracefully) | — | `markdown_to_html()`, `render_pdf()` |
| [email.py](jobscope/email.py) | 36 | SMTP summaries (optional) | config | `send()` |
| [serve.py](jobscope/serve.py) | 27 | Local HTTP server for the dashboard | render, store | `run()` |
| [exporter.py](jobscope/exporter.py) | 22 | Export ranked jobs to JSON/CSV | — | `run()` |

> **Note:** the bulk of `render.py` is the inline HTML `_TEMPLATE` string — a self-contained,
> dependency-free dashboard, currently the **only** UI with the **Applications board** (kanban +
> per-application email timelines) and the inline-SVG **pipeline-flow Sankey**; the React app hasn't
> mirrored these yet. The data-contract logic (`build_data`/`_job_record`/`_application_records`/
> `_enrich_summary`/`_overview_data`/`emit_json`) is the remainder. Once the web app supersedes the
> HTML page, the template can shrink and `render.py` becomes a slim emitter.

### cli / orchestration

| Module | LOC | Responsibility | Internal imports | Key exports |
|--------|-----|----------------|------------------|-------------|
| [__main__.py](jobscope/__main__.py) | 195 | argparse dispatch for 18 subcommands (lazy per-command imports) | ~all (lazy) | `main()`, `build_parser()` |
| [pipeline.py](jobscope/pipeline.py) | 42 | One-shot `scan → match → enrich → prep → digest` | apply, email, enrich, match, scrape | `run()` |
| [selftest.py](jobscope/selftest.py) | 229 | Offline self-tests (validate the full stack, no network) | model, config, store, match, mailrules, ats, inbox | `run()` |
| [scaffold.py](jobscope/scaffold.py) | 50 | `init`: scaffold config + data dir (non-destructive) | config | `run()` |
| [__init__.py](jobscope/__init__.py) | 6 | Package marker, `__version__` | — | `__version__` |

**Totals:** 27 top-level modules + 8 enrich modules ≈ **6,050 LOC** of Python.

---

## 5. Coupling hotspots

Fan-in = how many modules import it; fan-out = how many it imports (internal only).

| Module | LOC | Fan-in | Fan-out | Read |
|--------|-----|:------:|:-------:|------|
| **store.py** | 457 | ~11 | 1 | **God module** — every command persists through it. Mixed concerns (jobs / enrichment / applications / mail / ai-cache in one class). Top split candidate. |
| **model.py** | 228 | ~12 | 0 | Highest fan-in but **pure** — the ideal shape. Leave as-is. |
| **match.py** | 508 | ~6 | 3 | Largest logic module; bundles 5 sub-concerns (seniority, experience, filters, scoring, routing). Split candidate. |
| **render.py** | 850 | 2 | 2 | Big only because of the inline HTML template; the emitter is small. Shrinks once the HTML page retires. |
| **__main__.py** | 195 | 0 | ~18 | Orchestrator; wide fan-out but **lazy imports** keep startup light. Healthy. |
| **config.py** | 176 | ~6 | 0 | Pure config layer. Healthy. |
| **enrich/__init__.py** | 72 | 2 | 7 | Coordinator over 7 isolated sources. Registry candidate (see P-B). |
| **ai.py** | 82 | ~4 | 1 | Optional layer; all callers have deterministic fallbacks. Healthy. |

---

## 6. Runtime flows

### CLI dispatch (`__main__.py`)

`build_parser()` defines one `argparse` parser with subparsers; each subcommand does
`set_defaults(func=cmd_<name>)`, and `main()` calls `args.func(args, cfg)` inside a
`Store` context manager. **Feature modules are imported lazily inside each `cmd_*`** so the
base CLI stays offline-friendly.

18 subcommands: `init`, `resume import`, `scan`, `match`, `pipeline`, `enrich`, `tailor`,
`prep`, `apply`, `dashboard`, `serve`, `track`, `inbox`, `new`, `gaps`, `brief`, `export`,
`selftest`.

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

---

## 7. Persistence model (`store.py`)

A single `Store` class over SQLite. **10 tables**: `jobs`, `enrichment`, `contacts`,
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

## 8. Web dashboard (`web/`)

Vite + React 19 + TS + Tailwind v4 + TanStack Router (hash) + Motion. The build bakes in
[web/src/data/dashboard.json](web/src/data/dashboard.json) (emitted by `jobscope dashboard --emit-json`).

| Area | Files | Responsibility |
|------|-------|----------------|
| **Entry** | [main.tsx](web/src/main.tsx), [router.tsx](web/src/router.tsx), [App.tsx](web/src/App.tsx) | Mount; hash route `/` with zod-validated search params; wire filters→search→display |
| **Data** | [data/index.ts](web/src/data/index.ts) | Static import of `dashboard.json` typed as `DashboardData` |
| **Contract** | [lib/schema.ts](web/src/lib/schema.ts) | TS mirror of the Python payload (keep 1:1) |
| **State** | [lib/urlState.ts](web/src/lib/urlState.ts), [hooks/useSearchState.ts](web/src/hooks/useSearchState.ts) | URL = single source of truth; `FACETS`, `searchSchema`, `TAB_VALUES` |
| **Filter/search** | [lib/filters.ts](web/src/lib/filters.ts), [lib/search.ts](web/src/lib/search.ts), [lib/overview.ts](web/src/lib/overview.ts), [lib/format.ts](web/src/lib/format.ts) | `tabPool`→`applyFacets`→`makeFuse`→`fuzzy`→`buildDisplayItems`; Fuse.js; formatting |
| **Components** | `Header`, `Tabs`, `Switch`, `JobList`, `JobCard`, `JobDrawer`, `Kpis`, `filters/*`, `overview/*` | Virtualized list, deep-linkable drawer, facets, KPI/donut/bars |
| **Hooks** | [hooks/useTheme.ts](web/src/hooks/useTheme.ts) | Dark/light toggle |

**State pipeline** (all in `App.tsx`, driven by the URL):

```mermaid
flowchart LR
    URL[(URL search params)] --> S["useSearchState()"]
    S --> tabPool --> applyFacets --> makeFuse --> fuzzy --> buildDisplayItems --> JobList
    S --> JobDrawer
```

---

## 9. The Python↔TypeScript data contract

This is the **highest-friction seam** in the codebase: a change on one side must be mirrored
by hand on the other.

```mermaid
flowchart LR
    subgraph py["Python (render.py)"]
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
| 5 | **`applications[]`** | `_application_records()` — emitted **and** rendered in the HTML dashboard's Applications board | **no React type yet** | HTML board (kanban + email timelines + pipeline-flow Sankey) is built; the **React** app still needs an `Application` type to mirror it |
| 6 | Facet keys | job fields (`base`,`country`,`place`,`remote`,`funding`,`remote_scope`) | `FACETS`, `FacetKey`, `searchSchema`, `FacetBar` | A new facet = 4 TS edits |
| 7 | Country/place values | `_country_of()`, `_place_of()` | displayed as-is | Grouping changes fragment facet options |
| 8 | Salary string | `_fmt_salary()` | `format.ts:compLabel()` | Python owns the format; TS cannot reparse |
| 9 | Stock/comp field pick | `_enrich_summary()` key subset | `format.ts:stockLabel()` | Added stock field invisible until schema updated |
| 10 | Public redaction | `_redact_public()` | no type-level public/private distinction | A missed field could leak private data |
| 11 | `gaps` tuple | `[[skill, count]]` | `[string, number][]` | Structural change breaks index access |

> **Mitigation (roadmap P-A):** emit a JSON Schema from the Python shapes and assert
> `dashboard.json` matches it in a pytest; share the tier/facet constant lists. Later,
> generate `schema.ts` from Python so the mirror can't drift.

---

## 10. Extension recipes (how to add X today)

**Add a CLI subcommand:** write `cmd_<name>(args, cfg)` in [__main__.py](jobscope/__main__.py),
add a `sub.add_parser(...)` with `set_defaults(func=cmd_<name>)`, put logic in a feature module
(lazy-import it inside `cmd_<name>`).

**Add an enrichment source:** create `enrich/<src>.py` exposing `enrich(company, ...)`; import
and call it in [enrich/__init__.py](jobscope/enrich/__init__.py) `run()`; add its toggle to the
`enrich` section of `DEFAULT_CONFIG`; surface fields via `_enrich_summary` + `schema.ts`.
*(P-B turns steps 2–3 into self-registration.)*

**Add a `Job` field end-to-end:** add it to the `Job` dataclass ([model.py](jobscope/model.py)) →
add the column to `SCHEMA` + `_ensure_columns()` ([store.py](jobscope/store.py)) → set it in
`scrape`/`ats` → emit it in `_job_record` ([render.py](jobscope/render.py)) → add it to `JobRow`
  ([schema.ts](web/src/lib/schema.ts)) → use it in components.

**Add a web facet:** add the key to `FACETS`, `FacetKey`, and `searchSchema`
([urlState.ts](web/src/lib/urlState.ts)); render it in `FacetBar`; ensure the underlying field
is present on `JobRow`.

---

## 11. What's already healthy (leave alone)

- **No circular imports**; a clean acyclic dependency graph.
- **Pure bedrock** (`model`, `config`, `companies`, `httpx`, `mailrules`) — trivially testable.
- **Lazy CLI imports** keep startup fast and offline-friendly.
- **Additive migrations** — safe, reversible-by-omission schema evolution.
- **Isolated enrich sources** — best-effort, one failure never cascades.
- **Deterministic core with optional AI overlay** — respected consistently.

---

## 12. Modularity roadmap

Approved direction: **document now, refactor incrementally** as features land. Each item lists
its trigger, the change, and the invariant to preserve. Nothing here is a big-bang rewrite.

### Tier 1 — low risk, high feature-velocity (do next)

- **P-A · Data-contract SSOT** — *trigger: applications board (HTML board shipped; React mirror pending).* Add a JSON Schema for the
  `dashboard.json` payload and a pytest asserting the emitted file validates; extract shared
  tier/facet constants. Add the missing `Application` type (seam #5) to `schema.ts` so the React app can render the board too. *Later:*
  generate `schema.ts` from Python. *Invariant:* the JSON shape stays identical.
- **P-B · Enrichment registry** — *trigger: new intel sources.* Replace hardcoded imports in
  [enrich/__init__.py](jobscope/enrich/__init__.py) with a `@source("name")` decorator; sources
  self-register; config toggles by name; `_enrich_summary` + `schema.ts` iterate the registry.
  *Invariant:* each source stays independent and best-effort.
- **P-C · Config-drift guard** — a pytest asserting `config.example.yaml` keys are a superset of
  `DEFAULT_CONFIG`. *Invariant:* env-only secrets.

### Tier 2 — structural health (do per-feature)

- **P-D · Split `store.py`** — *trigger: next persistence change.* Break into `JobStore`,
  `EnrichmentStore`, `ApplicationStore`, `MailStore`, `ProfileStore` behind a `Store` facade
  that delegates. *Invariant:* additive `_ensure_columns` migrations; same public method names.
- **P-E · Split `match.py`** — *trigger: next scoring change.* Extract
  `match/{seniority,experience,filters,scoring}.py`; `match.py` becomes the orchestrator.
  *Invariant:* scoring stays a pure, network-free function; identical scores.
- **Opportunistic:** split `resume.py` per-format parsers; split `tailor.py` (deterministic
  `analyze` vs AI rewrite); inline the thin `brief.py` wrapper; retire `render.py`'s HTML
  template once the web app is canonical.

### Tier 3 — package reorganization (staged)

> `inbox`/`mailrules` are now committed and shipped, so this tier is unblocked.

Group the flat package into sub-packages mirroring §3:

```
jobscope/
  core/      model, config, store, companies, httpx, ai
  ingest/    scrape, ats, inbox, mailrules
  analyze/   match, classify, resume, insights
  enrich/    (already a package)
  apply/     apply, tailor, track, brief
  deliver/   render, exporter, serve, pdf, email
  cli/       parser + cmd_* bodies (+ pipeline, scaffold, selftest)
  __main__.py  ← STAYS at root (thin; calls cli.main)
```

**Mechanics & guardrails:**

- **Entry point stays put.** `pyproject.toml` maps `jobscope = "jobscope.__main__:main"` and
  `python -m jobscope` both need a root `__main__.py`. Keep it as a thin shim; move only the
  parser/`cmd_*` bodies into `cli/`.
- **Packaging.** `[tool.setuptools.packages.find] include = ["jobscope*"]` auto-discovers
  sub-packages **if each has an `__init__.py`** — no explicit list to maintain. Verify with
  `pip install -e .` after.
- **Import churn (~170 mechanical edits).** Backend uses **relative** imports (~93 sites:
  `from .model import` → `from ..core.model import` across groups; within-group stays `from .`).
  Tests use **absolute** imports (~79 sites: `from jobscope.match import` →
  `from jobscope.analyze.match import`). No compatibility shims — we own every call site.
- **Sequencing.** One feature branch; `git mv` per group (preserve history); low-fan-in groups
  first (`deliver` → `apply` → `ingest` → `analyze`), **`core` last**; run `pytest` +
  `npm run build` green **after each group** before moving on. `enrich/` is already a package.
- **Invariants (all tiers):** deterministic-first, additive migrations, zero circular imports.

---

## Keeping this doc current

Update this file when you:

- add/rename/move a module (§4 inventory) or change an import edge (§3/§5);
- change the emitted JSON shape — touch [render.py](jobscope/render.py) `build_data`/`_job_record`/
  `_enrich_summary`/`_overview_data` or [schema.ts](web/src/lib/schema.ts) (§9 seam table);
- complete a roadmap item (§12) — move it to "healthy" and note the commit.

Consider adding a lightweight pointer to this file from the README. Once P-A lands, the
JSON-Schema test becomes the machine-checked half of §9.
