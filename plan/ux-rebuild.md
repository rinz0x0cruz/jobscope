# jobscope UX Rebuild — Research: Code Structure & Modularity

**Date:** 2026-07-09  ·  **Status:** research + plan (no teardown yet)  ·  **Stack:** React 19 · TS 6 · Vite 8 · Tailwind v4 · TanStack Router/Virtual · motion

This is the engineering research the rebuild is gated on. It audits the current
web code for **structure and modularity**, then defines a **modular target
architecture** and a phased plan to tear the UI down and rebuild it in a clean,
light, sidebar-first SaaS style (per the reference shots) — while preserving the
data contract, the tests, and the one thing we keep by request: the
**applied → interview / rejected / offer funnel graph**.

---

## 1. Objectives & hard requirements

From the brief:

1. **Full teardown + rebuild** of every UX component in a new style (light,
   sidebar-navigation, card-dense SaaS dashboard like the Pahalan / jobi refs).
2. **Keep the interview / rejected / accepted graph** — the Applications funnel
   (`applications/PipelineFlow.tsx` Sankey + status funnel). Restyle only.
3. **Whole app behind auth this time** — no public/redacted view. Nothing renders
   until the user authenticates; the shipped site is encrypted-only.
4. **Modularity first** — decompose the `App.tsx` god-component; separate a design
   system, a layout shell, feature modules, and a pure domain layer.
5. Related, tracked separately: **profile-driven scraper + 10-at-a-time loading**
   (issue #71) and the **residual interview false positives** (issue #70). The
   scraper's paging touches the jobs list UI, so the rebuild must leave a seam
   for "load more".

**Non-negotiable invariants (do NOT break):**

- The **Python↔TS data contract** (`jobscope/deliver/schema/dashboard.schema.json`
  ↔ `web/src/lib/schema.ts` ↔ `tests/test_dashboard_json.py`). The UI is free;
  the payload shape is fixed and guarded by tests.
- **Offline / no-heavy-deps / redaction / a11y / zero-regression** guardrails.
- The green test suite (`pytest` 346, `selftest` 68, `vitest` 62) and the
  `test_web_assets.py` markers that assert web structure.

---

## 2. Current-state audit

### 2.1 Layer map (what exists today)

```
web/src/
  App.tsx                     ← ORCHESTRATOR (god-component, ~200 lines)
  main.tsx, router.tsx        ← bootstrap + TanStack hash router (1 route)
  data/index.ts               ← bakes dashboard.json (+ optional encrypted blob)
  hooks/  useScoreFormat, useSearchState(?), useTheme(?)
  lib/    (PURE DOMAIN — the strong part)
    filters.ts  search.ts  overview.ts  pipeline.ts  gamification.ts
    schema.ts   urlState.ts  unlock.ts   format.ts   exportSvg.ts
    spotlight.ts  refresh.ts  outreach.ts  draft.ts
  components/  (PRESENTATION — the part we rebuild)
    Header, Kpis, PrimaryNav, TierSegment, HeroBackdrop, SignalLottie,
    JobList, JobCard, JobDrawer, RefreshButton, UnlockControl, UnlockForm,
    Switch, RecruiterOutreach
    overview/     Overview, Momentum, Donut, Bars, SkillConstellation, TopMatches, CountUp
    applications/ Applications, views, AppCard, ActivityFeed, ApplicationsGate,
                  PipelineFlow ★keep, PipelineHealth, constants
    filters/      FacetBar, FacetSelect, ActiveChips, SearchPalette
    outreach/     Outreach, ProfileCard, ResumeUpload, CompanySearch, CompanyCard, AppliedOutreach
  styles/theme.css            ← design tokens (CSS vars) + js-* utility classes
```

### 2.2 The central modularity finding: `App.tsx` is a god-component

`App.tsx` single-handedly owns **all** of:

- **State**: `useSearchState()` (URL hash), `collapsed` set, `unlocked` payload.
- **Derivation pipeline** (7 chained `useMemo`s): `tabPool → applyFacets → makeFuse
  → fuzzy → buildDisplayItems`, plus `facetOptions`, `activeChips`, `tabCounts`.
- **All handlers**: `openDrawer/closeDrawer`, `toggleFacet`, `removeChip`,
  `clearAll`, `toggleCollapse`, `onPrimary`, unlock/relock.
- **Layout**: hero + header + `<main>` + per-tab branch + drawer + palette + toasts.

Consequences: every filter keystroke re-runs the whole pipeline and re-renders the
tree; features can't be tested or restyled in isolation; prop-drilling
(`onOpen`, `rows`, `apps`) threads through every branch. **This is the #1 thing the
rebuild must fix** — not the CSS.

### 2.3 Coupling assessment

| Layer | State | Verdict |
|---|---|---|
| `lib/*` (filters, search, overview, pipeline, gamification, schema, format, unlock, urlState) | Pure functions, no React, no DOM | **Strong — keep as-is.** This is the domain core. |
| `hooks/*` | Thin React wrappers over lib | Keep; add `useData`, `useJobPipeline`. |
| `components/*` presentation | Tightly bound to the current dark/gradient aesthetic + App's prop shape | **Rebuild the UI**, salvage the logic. |
| `App.tsx` | Orchestration + layout in one | **Decompose** into shell + providers + feature views. |
| `styles/theme.css` | Token architecture is good (CSS vars, light/dark swap); the *values* are dark "Nightshift", and there are many decorative `js-*` glow/gradient/canvas utilities | **Keep the token mechanism, re-theme values light-first, retire decorative utilities.** |

### 2.4 Auth / publish model today

- Publish emits a **redacted public** `dashboard.json` (rows + overview only; apps,
  JDs, contacts, profile, applied_outreach stripped) **plus** an encrypted
  `site.enc.json` (AES-256-GCM, PBKDF2-SHA256 from the passphrase).
- `App` boots on the **public** payload and *optionally* unlocks
  (`lib/unlock.unlockDashboard` → swap in the full payload; cached in
  `sessionStorage`). **So the dashboard is partially public today.**

---

## 3. Target architecture (modular)

Adopt a **layered + feature-sliced** structure. Dependencies point downward only
(`app → layout/features → ui → lib`); nothing in `lib` imports React.

```
web/src/
  app/
    App.tsx           ← THIN: <Providers><AuthGate><AppShell/></AuthGate></Providers>
    AuthGate.tsx      ← whole-app gate (reuses lib/unlock crypto)
    AppShell.tsx      ← Sidebar + Topbar + routed content region
    providers.tsx     ← DataProvider (decrypted payload) + Theme + ScoreFormat
  layout/
    Sidebar.tsx  Topbar.tsx  PageHeader.tsx  RightRail.tsx  (SaaS shell)
  features/           ← self-contained modules (view + local components + local hooks)
    overview/  jobs/  applications/  outreach/  settings/
  ui/                 ← design-system primitives (no domain knowledge)
    Button Card StatCard Chip Segmented Table Dialog Drawer Field Avatar Badge Spinner EmptyState
  hooks/              ← cross-cutting: useData, useSearchState, useJobPipeline, useTheme, useScoreFormat, useDrawer
  lib/                ← UNCHANGED domain core (filters, search, overview, pipeline, gamification, schema, unlock, format, urlState, exportSvg)
  styles/             ← tokens.css (light-first) + base.css
  data/               ← encrypted-only payload loader
```

### 3.1 Decompose the god-component

- **`useJobPipeline(rows, state, collapsed)`** — move the 7-stage memo chain +
  `facetOptions`/`activeChips`/`tabCounts` here. Returns `{ items, options,
  chips, counts, shown }`. Pure, unit-testable, reused by the jobs feature.
- **`DataProvider` + `useData()`** — holds the decrypted `DashboardData`; features
  read from context instead of prop-drilling `rows`/`apps`/`profile`.
- **`useDrawer()`** — the `job` URL param already deep-links; wrap read/open/close.
- Result: `App.tsx` shrinks to providers + gate + shell; each **feature** owns its
  own view and only the state it needs.

### 3.2 Design-system layer (`ui/`)

Extract the repeated primitives the refs need into a small, headless-ish kit that
consumes tokens only: `Card`, `StatCard`, `Button`, `Chip/Badge`, `Segmented`
(tier switch), `Table`, `Dialog`/`Drawer` (wrap Radix), `Field` (inputs/upload),
`Avatar`, `EmptyState`, `Spinner`. Every current component re-implements these
inline — centralizing them is the biggest modularity win after the god-component.

### 3.3 Design tokens — light-first re-theme

Keep the **mechanism** (`@theme inline` mapping CSS vars → Tailwind utilities, with
`.light`/`.dark` class swap) — it's genuinely good. Change the **values** to a
light SaaS palette (white cards, slate text, one saturated brand + the
green/positive accent from the refs) and **retire** the decorative utilities:
`js-gradient-card`, `js-spotlight-card`, `js-neon-title`, `js-logo-mark`,
`js-header-gradient`, `js-skill-*`, `js-cyber-tree`, `js-sakura-*`, the aurora/
scanline/ambient layers, and `HeroBackdrop` + `SignalLottie` entirely. Tier colors
stay semantic (Strong/Good/Stretch/Skip) but re-valued for light.

---

## 4. New information architecture & UX (from the refs)

**Shell:** persistent **left sidebar** + **top bar**, light theme, generous
whitespace, card-dense content — replacing today's top `Header` + `PrimaryNav`.

- **Sidebar**: brand/logo · primary nav (Overview · Jobs · Applications · Outreach ·
  Settings) · résumé/profile-completion mini-card at the bottom (like jobi).
- **Topbar**: page title · global search · Refresh · theme · **lock** (re-lock the
  session) · avatar/profile.
- **Content per section** (a `PageHeader` + a card grid):
  - **Overview** → stat-card row (rebuilt `Kpis`) + charts (fit distribution donut,
    momentum, top companies, top matches) + skill gaps. Rebuild cards; keep the
    `lib/overview.ts` + `lib/gamification.ts` math.
  - **Jobs** → tier **Segmented** control + facet bar + **paginated list (10 at a
    time)** (issue #71 seam) + drawer. Rebuild `JobCard`/`JobList` chrome; keep
    virtualization + `lib/filters`/`lib/search`.
  - **Applications** → **KEEP the funnel graph** (`PipelineFlow` Sankey +
    status funnel), restyled light; rebuild the view switcher/cards.
  - **Outreach** → the slices we just shipped (profile card + résumé upload +
    applied-company contacts + company search), re-skinned into the new cards.
- **Right rail** (optional, ref-style): profile summary / communication on
  Overview.

IA mapping is 1:1 with today's `TabValue`s, so `lib/urlState.ts` and deep links
survive; only the **navigation chrome** changes (sidebar vs top tabs).

---

## 5. Auth model — whole app behind auth

**Change:** stop shipping a usable public payload; gate the entire app.

- **Publish**: emit **encrypted-only** — the baked `dashboard.json` becomes an
  empty/placeholder stub (or is dropped) and the real payload ships solely as the
  encrypted `site.enc.json`. Update `deliver/render.py` / `publish.sh` so the
  published `data/index.ts` has no consumable rows without the passphrase.
- **App shell**: `AuthGate` wraps everything. On boot: `readCachedUnlock()` →
  if present, render the app; else render a full-screen **auth screen**
  (passphrase → `unlockDashboard` → `cacheUnlock` → render). A **Lock** action in
  the Topbar clears the session (`clearUnlock`) back to the gate.
- **Reuse**: the crypto (`lib/unlock.ts` AES-256-GCM / PBKDF2, `UnlockForm`) is
  already exactly this — we're promoting the existing *optional* unlock to a
  *required* gate. Local `jobscope serve` can still inject the un-redacted payload
  directly for dev (no gate) behind the loopback token, or honor the same gate.
- **Security win**: nothing (rows, overview, counts) is public anymore; a scraper
  or casual visitor sees only ciphertext. Keep the Python-side redaction code as
  defense-in-depth even though the shipped build is encrypted-only.
- **Contract**: no schema change — same `DashboardData`, just delivered encrypted.

---

## 6. Keep / Rebuild / Retire matrix

| Area | Files | Action |
|---|---|---|
| Domain logic | `lib/filters, search, overview, pipeline, gamification, schema, urlState, format, unlock, exportSvg, refresh, outreach, draft` | **KEEP** (maybe split `filters.ts`). |
| Funnel graph | `applications/PipelineFlow.tsx`, status funnel, `lib/pipeline.ts` | **KEEP** (restyle light only). |
| Outreach slices | `outreach/*` (Profile, ResumeUpload, CompanySearch, CompanyCard, AppliedOutreach) | **KEEP logic, re-skin** into `ui/` cards. |
| Orchestration | `App.tsx` | **REBUILD** → thin shell + `useJobPipeline` + `DataProvider`. |
| Nav chrome | `Header.tsx`, `PrimaryNav.tsx`, `TierSegment.tsx` | **REBUILD** → `Sidebar` + `Topbar` + `ui/Segmented`. |
| Cards/lists | `Kpis, JobCard, JobList, JobDrawer, AppCard, views, Momentum, Donut, Bars, TopMatches` | **REBUILD UI** on `ui/*`; keep the data hooks. |
| Filters | `filters/FacetBar, FacetSelect, ActiveChips, SearchPalette` | **REBUILD UI**; keep `lib/filters`+`lib/search`. |
| Decoration | `HeroBackdrop.tsx`, `SignalLottie.tsx`, `spotlight.ts`, all `js-*` glow/gradient/canvas/tree/sakura utilities | **RETIRE.** |
| Design tokens | `styles/theme.css` | **KEEP mechanism, re-theme light-first**, split into `tokens.css` + `base.css`. |
| Deps to drop | `lottie-react`, likely `motion` (swap for CSS transitions) | **Evaluate for removal** (bundle: ~357 KB gz today). |

---

## 7. Rollout plan (phased, tests stay green)

Each phase is a mergeable PR; the app stays runnable throughout.

- **P0 — Scaffolding & tokens.** Add `ui/` primitives + `app/`+`layout/` shells
  behind a `?shell=v2` flag; re-theme `tokens.css` light-first (dark kept). No IA
  change yet. *Guard:* vitest for `ui/` primitives.
- **P1 — Auth gate + encrypted-only publish.** Promote unlock to `AuthGate`; switch
  publish to encrypted-only; update `data/index.ts`. *Guard:* a test that the
  public build ships no consumable rows; existing redaction tests stay.
- **P2 — Shell swap.** Replace `Header`+`PrimaryNav` with `Sidebar`+`Topbar`;
  route the 4 sections through `AppShell`. Decompose `App.tsx` → `DataProvider` +
  `useJobPipeline`. *Guard:* `web/test/Nav.test.tsx` rewritten for the sidebar.
- **P3 — Overview + Jobs rebuild.** New `StatCard` row + charts; new `JobCard`/
  list on `ui/`; wire the **10-at-a-time** paging seam (issue #71). *Guard:*
  vitest for pagination + facet behavior.
- **P4 — Applications rebuild (keep funnel).** Re-skin views; keep `PipelineFlow`.
  *Guard:* funnel render test stays.
- **P5 — Outreach re-skin + cleanup.** Move outreach into `ui/` cards; delete
  `HeroBackdrop`/`SignalLottie`/decorative CSS/dead deps; drop the `?shell` flag.
  *Guard:* full `pytest` + `selftest` + `vitest` + bundle-size check.

**Discipline:** contract seams (`schema.json` ↔ `schema.ts` ↔ `test_dashboard_json.py`)
change only in lockstep; run full `pytest` even for web-only phases (the
`test_web_assets.py` markers guard web structure).

---

## 8. Risks & guardrails

- **Contract drift** → keep all four seams in lockstep; the artifact cross-check
  test already enforces it.
- **Auth lockout / dev friction** → keep local `serve` able to inject the payload
  for development; document the passphrase flow.
- **Scope creep** (rebuild everything at once) → the `?shell=v2` flag + phased PRs
  keep `main` shippable and each change reviewable.
- **Bundle regressions** → track gz size each phase; the retirement of
  lottie/motion/canvas should *reduce* it.
- **A11y regressions** → the sidebar/topbar need the same focus-visible, ARIA
  roles, and reduced-motion support the current build has.

---

## 9. Open decisions (confirm before P0)

> **Resolved 2026-07-09 — see §10.** Light-first (dark kept) · dedicated Settings/
> Profile section · client-side "load more" first (#71) · whole-app auth ·
> **warm-neutral palette + a distinctive non-blue (coral) accent** · a
> **dependency-free native motion layer** (drop `motion` + `lottie-react`).

1. **Palette**: adopt the refs' green/positive accent as brand, or keep amber? Keep
   a dark mode, or ship light-only?
2. **Motion**: drop `motion` for CSS transitions (smaller bundle), or keep it?
3. **Auth**: passphrase-only (current crypto), or add a lightweight username too
   (cosmetic — crypto stays passphrase-derived)?
4. **Sidebar sections**: add a dedicated **Settings/Profile** section (résumé
   upload, theme, tokens) split out of Outreach?
5. **Scraper paging (#71)**: client-side "load more" over the baked payload first,
   or wire a `serve` cursor now?

---

## 10. Researched direction — color system & motion (confirmed)

From a dedicated palette + motion research pass (rather than picking defaults).
**Confirmed:** light-first with dark kept · a dedicated Settings/Profile section ·
client-side "load more" first · whole-app auth · and — from the research below — a
**warm editorial-neutral** base with a **distinctive non-blue accent**, plus a
**dependency-free native motion layer** (drop `motion` **and** `lottie-react`).

### 10.1 Color — warm editorial neutrals + a non-blue accent

**Why (research):** the differentiated, non-generic direction for current dashboards
moves away from the default cool-grey/blue SaaS look toward **warm sophisticated
neutrals** (cream / bone / greige with an ink text) paired with **one distinctive
non-blue accent** (coral, olive/sage, or rust). It reads premium, lowers eye strain
for a data-dense tool, and — critically — lets the **semantic tier + status colors
pop** against a warm ground instead of fighting a blue brand.

**Light tokens (default):**
- Surfaces: `--surface-0 #FAF8F5` (warm bone page) · `--surface-1 #FFFFFF` (cards) ·
  `--surface-2 #F3F0EA` (insets) · `--edge #E7E2D9` (hairline borders).
- Text: `--text-1 #1D1B18` (warm ink) · `--text-2 #5C574F` · `--text-3 #8A847A`.
- **Brand accent: terracotta/coral `--brand #E0654A`** (warm, non-blue),
  `--brand-weak #FCEBE6`, hover `#C8543B`. Alternatives kept as commented tokens:
  olive `#6B7A4F`, rust `#B5533A`.
- Semantic (kept, re-valued for warm light): positive/Strong `#3F9E6E` ·
  good `#3E7CB1` (the *one* sanctioned blue — data only) · warning/Stretch `#D9932B` ·
  skip `#9A938A` · danger `#C4483B`. Focus ring = `--brand`; charts use the semantic
  ramp, never the brand.

**Dark (kept, warm-inflected):** `--surface-0 #17150F` (warm near-black) · cards
`#201D16` · ink `#F2EEE6` · brand coral lightened to `#EA7358`.

**Gradients:** retire the neon multi-stop borders/sweeps/conics. Allow at most **one
restrained, flat brand wash** (`--brand-weak → transparent`) on the auth screen /
hero stat — low-contrast, no animation. No rotating/glow/scanline effects.

### 10.2 Motion — dependency-free native layer (drop Lottie & `motion`)

**Why (research):** **Rive** is the modern Lottie successor (runtime state machines,
~90% smaller assets; Spotify/Duolingo) but needs its own editor + a runtime dep;
**Motion** (motion.dev) is a tiny WAAPI-backed lib. For a **calm, data-dense SaaS
dashboard**, the strongest "from scratch, not Lottie" answer is a **native layer with
no animation dependency**:

- **CSS transitions + `@keyframes`** for ~95% (hover, press, enter/exit, bar/donut
  grow), driven by the existing motion tokens (`--dur-fast/base/slow`, `--ease-*`).
- **Web Animations API** via one small `animate()` helper in `ui/` for the few
  imperative cases (count-up, list stagger, drawer spring) — **replaces `motion`**.
- **View Transitions API** for section switches and the **auth → app reveal**
  (graceful no-op where unsupported) — shared-element polish for free.
- **`prefers-reduced-motion`** honored globally (already the pattern); the WAAPI
  helper early-returns to the final state.
- **Net:** removes `motion` **and** `lottie-react` + the `SignalLottie` asset →
  meaningful bundle drop; "motion" becomes tokens + ~2 tiny helpers in `ui/`.

These fold into §6 (deps to drop) and §7: **P0** adds the motion tokens + `animate()`
helper and the light warm-neutral `tokens.css`; **P5** removes `motion` /
`lottie-react` / `SignalLottie` with the rest of the decoration.

