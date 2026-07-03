# jobscope — dashboard UI upgrade plan

> **Fully replace** the Python-rendered ~487 KB self-contained HTML dashboard
> ([jobscope/render.py](../jobscope/render.py)) with a modern, **motion-first**, statically-exported
> web app — without changing the Python pipeline (`scan → match → enrich`) or the project's
> offline / privacy / hosting doctrine.
>
> Status: **planning**. Written 2026-07-02; revised for full-replacement + heavy animation.
> Feature baseline = [FEATURES.md](../FEATURES.md) "Dashboard".

---

## 1. Why

The current dashboard works but is crude: hand-written CSS/JS in one giant string, all 500+ cards
in the DOM at once, `innerHTML` re-renders, minimal accessibility, no shareable state, and a single
487 KB line that even breaks the legacy Jekyll Pages builder. A real component stack buys
virtualization, rich animation, accessibility, URL-shareable views, and a PWA for mobile.

## 2. Hard constraints (must not regress)

1. **Offline / "your data stays local".** Opens from `file://`, no network at view time. → data is
   **baked in at build time** (no runtime server/API); fonts, icons, JS all bundled locally (no
   runtime CDN, no telemetry).
2. **Static hosting on GitHub Pages** from **jobscope's own `gh-pages` branch** (branch-based,
   served at `/jobscope/`; the separate `jobscope-dashboard` repo is retired). → the app must
   **static-export** to plain HTML/JS with a `.nojekyll` marker. A multi-file export also fixes
   today's "single 487 KB line breaks Jekyll" gotcha.
3. **Redaction model.** Full local build vs a redacted public build (`_redact_public` strips per-job
   `contacts`/`rationale`/`resume_base` + Overview `funnel`/`targets`). → two JSON payloads, one UI.
4. **Python pipeline untouched.** Only presentation changes. `scan/match/enrich/store` stay.
5. **Source stays private.** Code lives in the `jobscope` repo; only the redacted built
   output is published to the public `gh-pages` branch (early git history has a work-email author).
   ⚠ NOTE: `jobscope` is currently a **public** repo — this constraint is not met; see next-steps §5.

## 3. Stack (chosen — "your best", tuned for static + offline + heavy motion)

A purely static, data-baked SPA with no SSR needs, so a lighter build than Next.js is the best fit
and behaves better from `file://`:

- **Vite 6 + React 19 + TypeScript** — instant HMR, small/clean static output; `base: './'` yields
  **relative asset paths** that work from both `file://` (offline) and the Pages subpath, with no
  SSR abstractions to fight during export.
- **Tailwind CSS v4** (`@tailwindcss/vite`) — port the current design tokens (`--bg`, `--accent`,
  `--card`, …) into the theme to keep the look, then refine.
- **shadcn/ui (Radix)** — Tabs, Sheet (drawer), Combobox/Select, Command palette, Badge, Switch,
  Tooltip, DropdownMenu — accessible primitives.
- **Motion (Framer Motion) — the animation backbone** (see §8): layout animations, shared-element
  card→drawer morphs, spring physics, stagger, exit animations.
- **TanStack Table + TanStack Virtual** — sortable tables + a virtualized 500+ row list at 60 fps.
- **TanStack Router** — typed, URL-synced search params (tab / open-job / facets) → shareable views
  that survive static export and `file://`.
- **shadcn Charts** (the shadcn ecosystem's own chart blocks, **Recharts** under the hood) — donut
  + bars with draw-in animation; **Nivo** only if we later want richer viz.
- **Fuse.js** behind a **`cmdk`** command palette — fuzzy search.
- **lucide-react** icons + a tiny **class-based theme hook** (light/dark, persisted, no FOUC).
- **vite-plugin-pwa (Workbox)** — installable + offline PWA (precache app + baked data) for mobile.

**Grounded in community sentiment** (r/reactjs, top threads of the past year): for a client-side /
static / no-SSR app the recurring recommendation is exactly **"Vite + React + TanStack Router"**
(e.g. *"Should I ditch Next.js and go back to client-side React?"* — 116 comments; *"Considering
ditching Next.js/SSR for a simple React SPA"*), driven by free static hosting and TanStack Router's
type-safe JSON search-param routing. Vite is now the default React starter (~150M npm downloads).
**TanStack Start** — the SSR framework people are leaving Next.js for — is deliberately **not** used
here: we have no SSR needs. shadcn/ui + Tailwind + lucide are the de-facto UI defaults; **Motion (Framer Motion)** is the
standard animation library, with the **View Transitions API** trending for route/tab transitions.
For charts, r/reactjs's common picks are Recharts / Nivo / visx / ECharts; since we already use
shadcn, **shadcn Charts (Recharts-based)** keeps a single design system. Toasts: **Sonner**.

Everything is bundled locally — no runtime CDN, no telemetry — to honor the offline rule.

## 4. Data pipeline (preserves privacy)

```
SQLite → `jobscope dashboard --emit-json`  → data/dashboard.json         (full, local)
        (+ `--public`)                      → data/dashboard.public.json  (redacted)
     → web build (`vite build --base=./`, imports the JSON, bakes it in) → web/dist/
     → local:   `jobscope serve` serves web/dist/
     → publish: build from dashboard.public.json → push web/dist/ → jobscope `gh-pages` (Pages)
```

- The Python emitter reuses `_job_record` / `_overview_data` / `_redact_public` unchanged; emits a
  typed JSON contract mirrored in `web/src/lib/schema.ts`.
- Vite imports `dashboard.json` as a build-time module and inlines it into the bundle → **no data
  leaves the machine**; the public build only ever imports the redacted JSON. `--base=./` keeps
  assets relative so it runs from `file://` and the Pages subpath alike.

## 5. Feature → upgrade list

| # | Current feature (render.py / FEATURES.md) | Upgraded tech | UI / motion improvement |
|---|---|---|---|
| 1 | Single 487 KB inline HTML/CSS/JS | Vite static build, code-split | Faster load, cacheable, fixes Jekyll gotcha |
| 2 | Tabs (Overview + Strong/Good/Stretch/Skip) | shadcn `Tabs` + Router | Shared-`layoutId` indicator, directional cross-fade, deep-linkable |
| 3 | KPI cards | shadcn Card + count-up | Responsive grid, spring count-up |
| 4 | Analyzed donut (CSS conic-gradient) | Recharts `DonutChart` | Draw-in on mount, re-animate on scope change, tooltips |
| 5 | Targeting roles + by-resume/by-location bars | shadcn Chart bars + `Badge` | Animated bars, hover detail |
| 6 | Application funnel | animated bars + empty-state | Clear funnel, guidance when empty |
| 7 | Top companies / Skill-gaps bars | shadcn Chart bars + `Tooltip` | Example companies on hover, sortable |
| 8 | Top-matches table | TanStack Table | Sortable, sticky header, row → drawer |
| 9 | **List cards** (score/bar, title, company+Apply, Comp/Stock/Reputation, badges) | `<JobCard>` + TanStack Virtual | Virtualized 500+ rows, layout re-flow, enter/exit motion, hover lift |
| 10 | Detail **drawer** (overlay + Esc/backdrop) | shadcn `Sheet` (Radix) | **Shared-element morph** from card, deep-linkable `?job=`, mobile bottom-sheet |
| 11 | Drawer sections (brief/comp/stock/reddit/glassdoor/news/contacts/rationale/all-postings) | Section components | Collapsible, richer stock viz (52-wk bar), copy-link toast |
| 12 | Grouping (`groupItems`) | `useMemo` selector + `Switch` | Same logic, `×N` badge, animated collapse |
| 13 | Search (`/`, Esc) | `cmdk` palette + Fuse.js, URL-synced | Spring-open, fuzzy, keyboard-nav, shareable query |
| 14 | Facets (Resume/Country/Location/Work-mode/Funding/Remote-scope) | shadcn faceted `Combobox` + Router | Multi-select, per-option counts, fly-in active chips, "clear all" |
| 15 | Theme toggle | class-based theme hook | System/light/dark, no flash, sun/moon morph |
| 16 | Badges (NEW/taken-down/remote-scope/dupe/tier pill) | `<Badge>` variants + tokens | Consistent, accessible contrast, Strong-tier pulse |
| 17 | Redaction (public copy) | Two JSON payloads, one build | Same guarantees, simpler |
| 18 | Responsive (2 media queries) | Tailwind responsive + **PWA** | Mobile-first, installable, offline cache |
| 19 | *(new)* shareable URLs | Router search params | Bookmark/share filtered views + open job |
| 20 | *(new)* accessibility + reduced-motion | Radix + Motion kill-switch | Full keyboard nav, screen-reader support |

## 6. Migration phases (full replacement — no legacy fallback)

1. **Data contract** — split [render.py](../jobscope/render.py): move the record builders
   (`_job_record`, `_overview_data`, `_redact_public`, `_enrich_summary`, `_fmt_salary`,
   `_country_of`, `_place_of`) into `jobscope/dashboard_data.py`; add `dashboard --emit-json`
   writing `data/dashboard.json` (+ `--public` → `dashboard.public.json`). Only Python change;
   non-breaking on its own.
2. **Scaffold `web/`** — Vite + React 19 + TS + Tailwind v4 + shadcn/ui + Motion + TanStack
   Router/Table/Virtual; `base: './'`; port CSS tokens into the theme.
3. **List** — virtualized `<JobCard>` list, tabs, `cmdk`+Fuse search, faceted filters — all in URL
   state. Meet then exceed current parity.
4. **Overview** — KPIs, animated donut + bars, top-matches table.
5. **Drawer** — Sheet with every enrichment section; shared-element transition from the card;
   deep-linkable `?job=<id>`.
6. **Motion & PWA** — the full animation system (§8), offline PWA, mobile bottom-sheet, skeletons,
   empty states, a11y + reduced-motion pass.
7. **CLI + publishing** — `jobscope dashboard` = emit JSON → `vite build --base=./` → output to
   `data/dashboard/` (served by `jobscope serve`). Update `scripts/publish.ps1`/`publish.sh` to
   build from the redacted JSON and push `web/dist/`; keep branch-based Pages + `.nojekyll`.
8. **Delete the legacy renderer** — remove `_TEMPLATE` / `card()` / inline JS from render.py;
   `render.build()` becomes the JSON emitter. Update FEATURES.md, README, config docs.

## 7. Decisions (locked)

1. **Framework — Vite + React 19 + TypeScript.** Best fit for a static, offline, animation-heavy
   SPA; lighter and more `file://`-friendly than Next.js (which was only an example).
   *Community-validated:* r/reactjs's recurring pick for client-side/static apps is "Vite + React +
   TanStack Router"; Next.js is widely seen as overkill/costly for a no-SSR static site.
2. **Full replacement — no `--legacy` fallback.** The single-file Python renderer is deleted once
   the web app reaches parity; building the dashboard then requires Node (accepted).
3. **Repo placement — source in `jobscope`; push built `web/dist/` to its own public
   `gh-pages` branch.** Consolidated hosting model (`jobscope-dashboard` retired).
4. **Scope — full parity, motion-first throughout** (not a bare MVP), sequenced per §6.

## 8. Animation & dynamics

Motion is a first-class design goal. Principles: purposeful, fast (150–260 ms), spring-based, and
**fully disabled under `prefers-reduced-motion`**.

- **Shared-element card → drawer.** A Motion `layoutId` morph carries the card's title/score into
  the drawer header (continuous, not a fade).
- **Live list.** `AnimatePresence` + `layout` so filtering / sorting / grouping **re-flows with
  spring layout animation**; `<24h` cards get a highlight sweep; removed cards animate out;
  virtualized rows fade/scale in on scroll (stagger capped for large lists).
- **Tabs.** Shared-`layoutId` active indicator; content cross-fades with a directional slide keyed
  to tier order.
- **Numbers & charts.** KPI values spring-count up; the donut and bars **draw in** on mount and
  **re-animate** when the active scope changes.
- **Facets.** Result count animates on change; active-filter **chips fly in/out**; "clear all"
  collapses them.
- **Micro-interactions.** Card hover lift, animated Apply button, Strong-tier pill pulse, press/
  ripple states, sun/moon theme-toggle morph, copy-link toast.
- **Command palette.** `cmdk` opens with a spring scale; fuzzy results reorder with layout motion.
- **View Transitions API** where supported (progressive enhancement) for tab/route changes; Motion
  fallback elsewhere.
- **Skeletons / optimistic hydrate** so nothing pops in abruptly.

Perf guardrails: virtualization; `transform`/`opacity`-only (GPU) animations; layout animation
scoped to visible rows; sparing `will-change`; a global reduced-motion kill-switch.

## 9. Architecture (careful)

**Repo layout**

    jobscope/
      jobscope/
        dashboard_data.py    # record / overview / redaction builders (moved out of render.py)
        render.py            # -> JSON emitter: build() writes dashboard.json (+ public)
      web/                   # Vite + React app (source; stays in the private repo)
        index.html
        vite.config.ts       # base:'./', PWA + tailwind plugins
        src/
          main.tsx, App.tsx
          data/dashboard.json         # emitted by `dashboard --emit-json` (gitignored)
          lib/{schema.ts, filters.ts, group.ts, format.ts, search.ts}
          routes/                     # TanStack Router: tab + ?job / ?q / facets in search params
          components/
            JobCard.tsx, JobList.tsx (virtualized), JobDrawer.tsx
            overview/{Kpis,Donut,Bars,TopMatches}.tsx
            filters/{FacetBar,ActiveChips,SearchPalette}.tsx
            ui/                        # shadcn components
          hooks/{useJobs,useFacets,useTheme}.ts
          styles/theme.css            # ported design tokens
        dist/                # build output (gitignored) -> pushed to the public repo

**Data contract** (`web/src/lib/schema.ts` mirrors Python 1:1)
- `DashboardData = { generated: string; total: number; rows: JobRow[]; overview: Overview }`.
- `JobRow` mirrors `_job_record` exactly (id, title, company, location, remote, remote_scope, url,
  source, score, tier, base, salary, size, funding, country, place, industry, rationale, blocked,
  posted, first_seen, status, closed_at, enrich{comp,stock,glassdoor,reddit,news}, brief, contacts[]).
- A **schema test** (Python emits a fixture; TS `zod` parses it in CI) pins the contract so drift is
  caught early.

**State & URL** — all view state lives in TanStack Router search params: `tab`, `q`, `resume`,
`country`, `place`, `mode`, `funding`, `scope`, `group`, `hideClosed`, `job` → shareable,
back/forward, restorable. Derived (filtered/grouped/sorted) data via memoized selectors; the Fuse
index is built once.

**Build / serve / publish**
- `jobscope dashboard` → emit JSON → `vite build --base=./` → copy `web/dist` to `data/dashboard/`.
  `--public` builds from the redacted JSON.
- `jobscope serve` → static-serves `data/dashboard/`.
- `scripts/publish.*` → build public → push `web/dist` (site root) to jobscope's `gh-pages` branch
  (branch-based Pages); keep `.nojekyll`.
- **CI** — existing Python `selftest`/`pytest` gates unchanged; add a separate **web** job (Node:
  install, typecheck, `build`, schema test) that runs only on `web/**` changes and does **not** gate
  the Python checks.

## 10. Risks / watch-items

- **Node toolchain** is now required to build the dashboard (accepted with full replacement) —
  document the build step in README/setup.
- **`file://` + Pages subpath** — handled by `base: './'` + hash/history routing; test both.
- **Data-contract drift** — pinned by the shared schema + CI schema test.
- **Motion vs perf on 500+ rows** — mitigated by virtualization + transform-only animation and the
  reduced-motion kill-switch.
- **Offline assets** — self-host fonts/icons; PWA precache; no runtime CDN.

## 11. Not changing

`scan`, `match`, `enrich`, `store`, resume parsing, scoring, filters, ATS boards, the publishing
*trigger* (still local), and the redaction rules. This is a presentation-layer migration only.
