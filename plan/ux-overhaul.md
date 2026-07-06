# jobscope dashboard — UX overhaul · Stage 1: current-state feature & UX inventory

> **Purpose.** A complete, honest catalogue of *what the dashboard is today* — every surface,
> component, data source, interaction, and the current visual/motion system — so we can overhaul the
> **look, layout, and feel** without dropping a single capability.
>
> **This is Stage 1 of 2 (delivered for review first).**
> - **Stage 1 (this doc):** the feature + UX inventory + the guardrails + a seeded list of overhaul
>   opportunities. *No redesign decisions yet.*
> - **Stage 2 (follow-up):** the actual UX overhaul plan (information architecture, surface-by-surface
>   redesign, no functionality break) **+ 2–3 distinct visual concepts** (palette, gradients, motion,
>   hero animation) for you to pick from.
>
> Scope: the **`web/` React SPA** (the published GitHub-Pages dashboard). The Python pipeline
> (`scan → match → enrich → inbox`) and the JSON contract are **out of scope to change**.
> Baseline sources: [FEATURES.md](../FEATURES.md), [ARCHITECTURE.md](../ARCHITECTURE.md) §8,
> [plan/ui-upgrade.md](./ui-upgrade.md) (the now-shipped React migration), and `web/src/**`.

---

## 0. Guardrails — what the overhaul must NOT break

These are hard constraints; the redesign lives entirely *inside* them.

1. **PWA + fully offline.** Opens from `file://` and as an installed PWA; **no runtime CDN, no
   external fetch, no telemetry**. Every font, icon, animation asset, and the data itself is baked
   into the bundle at build time. *(A new typeface or motion library must be self-hosted/local.)*
2. **Static export + redaction.** The app static-exports to `web/dist` (relative `base: './'`) and is
   published to the `gh-pages` branch. Two payloads, one build: full (local) vs **redacted public**
   (`_redact_public` strips per-job `contacts`/`rationale`/`resume_base`, the Overview
   `funnel`/`targets`, and **all applications**). The redaction guarantee must hold.
3. **Python ↔ TS JSON contract is fixed.** UI consumes `dashboard.json` shaped by `render.py`
   (`_job_record`, `_overview_data`, `_application_records`, `_enrich_summary`). A redesign may
   re-arrange or restyle fields but **must not require new backend fields** without a matching
   contract change (guarded by `tests/test_dashboard_json.py`). Prefer presentation-only changes.
4. **Keep the funnel / pipeline-flow visualization** (the inline-SVG Sankey). It can be *restyled*
   and improved, but the "how far each application got" story stays.
5. **Encrypted Applications tab stays end-to-end.** The AES-256-GCM blob decrypts **in-browser**
   behind the passphrase gate; the sensitive payload is never served in the clear.
6. **Accessibility floor holds or improves.** Keyboard nav, visible focus rings, and the global
   `prefers-reduced-motion` kill-switch (decorative layers `aria-hidden` / `pointer-events:none`)
   must survive.

Everything else — palette, gradients, layout, density, typography, the hero animation, the
cyber-sakura tree — is **open** (per direction: *"nothing sacred; make the tree larger or replace it
with a better animation"*).

---

## 1. Tech substrate (today)

Vite 6 · React 19 · TypeScript · **Tailwind v4** (CSS-var theme, `@theme inline`) · **TanStack Router**
(hash routing, zod-validated search params = shareable state) · **Motion** (Framer Motion) · **Lottie**
(local JSON) · **Fuse.js** (fuzzy search) · **vite-plugin-pwa / Workbox** (installable + offline) ·
**lucide-react** icons. Charts are **hand-built inline SVG/CSS** (donut, bars, Sankey) — no chart lib
at runtime. `web/src/styles/theme.css` (≈17 KB) is the single design-system file.

**Data flow:** `jobscope dashboard --emit-json[ --public]` → `data/dashboard.json` → baked into the
bundle (`web/src/data/index.ts`, no runtime fetch) → typed by `web/src/lib/schema.ts`.

---

## 2. Information architecture

- **Single route** `#/` with URL-synced search params (tab, open job, facets, search, group) →
  every view is bookmarkable/shareable and survives `file://`.
- **Tabs (7):** `Overview` · `Applications` · **Strong** · **Good** · **Stretch** · **Skip** — each
  score bucket carries a live count. Overview + Applications are *summary* surfaces (no job list); the
  four bucket tabs are *filtered job lists*.
- **URL = single source of truth:** `useSearchState` → `tabPool → applyFacets → makeFuse → fuzzy →
  buildDisplayItems`. Controls (search, facets, group, theme) all fold into the URL.

---

## 3. Surface-by-surface inventory

### 3.1 Global shell
| Element | File | What it does today |
|---|---|---|
| **Header** | `components/Header.tsx` | App title + Lottie mark, live "N roles · <date>" line, **header search input** (focus with `/`, `Esc` clears; also scopes the Overview), light/dark toggle. Has a periodic **sheen sweep** (`jsHeaderSweep`). |
| **Brand mark** | `components/SignalLottie.tsx` | Local Lottie briefcase/scope logo (respects reduced-motion). |
| **Animated background** | `styles/theme.css` (`body`, `.js-ambient`) | Drifting multi-stop gradient wash + faint 86px **grid** (`jsBgDrift 11s`), plus a fixed blurred **conic "aurora" blob** (`.js-ambient`, `jsAmbientDrift 9s`). |
| **Cyber-sakura tree** | `components/CyberSakura.tsx` + `.js-cyber-tree` | Right-rail SVG tree that **draws itself in** (`jsTreeTrace`) with occasional **falling leaves** (`jsLeafFall`). Currently `width: clamp(180px, 22vw, 315px)`, `height: min(68vh, 510px)`, and positioned **mostly off the right edge** (`right: max(-260px, …)`) so only a sliver shows on most screens. |
| **Theme** | `hooks/useTheme.ts` | Class-based light/dark, persisted, no FOUC. |
| **Container** | `App.tsx` `<main>` | Single centered rail (`max-w-6xl`). |

### 3.2 Tabs
`components/Tabs.tsx` — the 7-tab bar with per-tab live counts; active-tab indicator; drives the URL `tab` param.

### 3.3 Overview tab (`components/overview/Overview.tsx`)
| Panel | File | Content |
|---|---|---|
| **KPI cards** | `Kpis.tsx` + `overview/CountUp.tsx` | Total · Strong · Good · Avg score · Filtered — with spring **count-up**. |
| **Analyzed donut** | `overview/Donut.tsx` | Tier distribution (counts + %), hand-drawn conic/SVG, draw-in on mount. |
| **Targeting these roles** | `overview/Bars.tsx` | Your search terms + **by-resume** and **by-location** split bars. |
| **Application funnel** | `overview/Overview.tsx` | Counts by application status (compact bars; the *rich* Sankey lives in Applications). |
| **Top companies** | `overview/Bars.tsx` | Most frequent employers in view. |
| **Skill gaps** | `overview/SkillConstellation.tsx` | Interactive **constellation graph** of recurring missing skills; select a node → roles that mention the gap. |
| **Top matches** | `overview/TopMatches.tsx` | Highest-scoring jobs; row → detail drawer. |

### 3.4 Applications tab (`components/applications/Applications.tsx`)
| Panel | File | Content |
|---|---|---|
| **KPI cards** | `Applications.tsx` | Applications · Submitted · Response % · Interview % · Offer % · Rejected. |
| **Pipeline flow (Sankey)** ⭐ | `applications/PipelineFlow.tsx` | Inline-SVG flow: **Applied** splits into Interview / Rejected / No-response, then Interview splits into Offer / Rejected / In-process; band widths ∝ counts. **(Must-keep — restyle only.)** |
| **Kanban board** | `applications/Applications.tsx` + `AppCard.tsx` | Columns by status (Applied → Interview → Offer → Rejected, + New/Prepared/Skipped). |
| **Application card** | `applications/AppCard.tsx` | Company · role · applied date + the **email timeline** (colored signal chip + subject + date per message). |
| **Encrypted gate** | `applications/ApplicationsGate.tsx` | Passphrase → in-browser WebCrypto decrypt of the baked blob → renders the board. Shown only on the public build until unlocked. |
| Status/colors | `applications/constants.ts` | Per-status colors + labels. |

### 3.5 Bucket tabs — job list (Strong / Good / Stretch / Skip)
| Element | File | Content |
|---|---|---|
| **Virtualized list** | `components/JobList.tsx` | 500+ rows at 60 fps (windowed). |
| **Job card** | `components/JobCard.tsx` | Score + bar, title, company · location, matched-resume tag, `NEW` (<24h), **intel dots** (funding, salary, stock ticker/Private, Glassdoor, Reddit, contacts, news), tier pill, `⚑ Taken down` badge (struck title) when closed. **Cursor-follow spotlight** + status-colored rail (interview/offer rails pulse). |
| **Detail drawer** | `components/JobDrawer.tsx` (largest component, ≈10.7 KB) | Radix Dialog sliding from the right (`jsDrawerIn/Out`): company brief, compensation, stock/IPO, Reddit, Glassdoor, recent news, referral leads, "why this rank", and — when grouped — an "All postings" list. Close via ✕ / backdrop / `Esc`; deep-linkable. |
| **Grouping** | `lib/filters.ts` | Collapses duplicate postings (same company + normalized title) into one card with `×N postings`; the drawer lists each posting. |

### 3.6 Controls (apply within the active bucket / scope)
| Control | File | Behaviour |
|---|---|---|
| **Search** | `components/Header.tsx` + `filters/SearchPalette.tsx` + `lib/search.ts` (Fuse.js) | Header input (`/` focus, `Esc` clear) over title/company/rationale; also scopes Overview; command-palette variant. |
| **Facets** | `filters/FacetBar.tsx`, `FacetSelect.tsx`, `ActiveChips.tsx` | Resume (2+), Country, Location, Work-mode, Funding — multi-select, per-option counts, fly-in active chips, auto-hide when single-valued, stack (AND). |
| **Group toggle** | `components/Switch.tsx` | On by default. |
| **Theme toggle** | `components/Header.tsx` | Light/dark. |

---

## 4. Current visual & motion system (the Stage-2 baseline)

### 4.1 Palette (as actually shipped in `theme.css`)
> ⚠️ **Naming drift to fix in Stage 2:** the CSS vars are named `--neon-cyan/blue/violet/emerald`
> but hold a **warm "sunset over deep navy"** palette (a re-skin left the names stale). The overhaul
> should rename tokens to match their role/hue.

- **Surfaces (dark, default):** `--bg #07111f` → `--bg2 #0a1628`, cards `--card #0d1728` / `--card-h #121f33`, borders `#1b2c45` → `#2d4667`.
- **Text:** `--fg #eef6ff`, `--dim #a9bbd2`, `--mute #687b92`.
- **Accent + "neon" (warm):** `--accent #fb923c` (orange), `--neon-cyan #ff6f5e` (coral), `--neon-blue #fb923c` (orange), `--neon-violet #fb7185` (rose), `--neon-emerald #2dd4bf` (teal), `--neon-amber #fbbf24`.
- **Tier semantics:** `--strong #4ade80` (green) · `--good #38bdf8` (blue) · `--stretch #fbbf24` (amber) · `--skip #71717a` (gray).
- **Light theme:** near-white surfaces, `--accent #c2410c`, softened shadow.
- **Shape:** `--radius 14px`, one elevation shadow; system font stack (`--font`) + mono (`--mono`) — no custom typeface yet.

### 4.2 Gradients & texture
- Body: animated 4-stop diagonal wash blended with the surface + a faint dual-axis 86 px grid.
- `.js-ambient`: fixed blurred **conic aurora** blob (coral/rose/orange), `blur(38px) saturate(1.7)`.
- Scrollbars: gradient thumbs (coral→rose, hover teal→coral).

### 4.3 Motion catalogue (all local CSS keyframes)
| Keyframe | Where | Effect |
|---|---|---|
| `jsBgDrift` (11s) | body | slow background wash + grid drift |
| `jsAmbientDrift` (9s) | `.js-ambient` | aurora blob skew/opacity drift |
| `jsTreeTrace` | cyber-sakura | SVG stroke draw-in |
| `jsLeafFall` | cyber-sakura | falling leaves (drift + rotate + fade) |
| `jsHeaderSweep` | header | periodic sheen sweep |
| `jsGradientSweep` | accents | gradient position sweep |
| `jsOverlayIn/Out`, `jsDrawerIn/Out` | drawer | overlay fade + right-slide (Radix-safe) |
| `jsSpin` | loaders | rotation |
| **JS-driven** | `lib/spotlight.ts` | cursor-follow `--spot-x/--spot-y` card spotlight |
| **Motion (Framer)** | cards/tabs | count-up, layout, enter/exit, tab indicator |

### 4.4 Signature elements (candidates to keep / evolve / replace)
- Cyber-sakura tree (self-drawing + leaves) — *currently under-sized & off-screen.*
- Lottie brand mark. · Cursor spotlight. · Pulsing status rails. · Skill **constellation**. · Aurora blob + grid.

---

## 5. Accessibility, responsive & performance (current)
- **A11y:** `:focus-visible` outlines, keyboard nav (Radix primitives), `prefers-reduced-motion`
  disables decorative motion; decorative layers `aria-hidden` + `pointer-events:none`.
- **Responsive:** single `max-w-6xl` rail; Tailwind breakpoints; mobile stack; installable PWA.
- **Perf:** virtualized list; data baked in (no fetch); charts are lightweight inline SVG; hashed
  chunks + Workbox precache.

---

## 6. Overhaul opportunities (seeds for Stage 2 — not decisions)

Observations that the redesign can act on, each *inside* the §0 guardrails:

1. **Token rename + palette reset.** Fix the `--neon-*`-holds-warm-values drift; define a coherent,
   named palette per concept (Stage 2 ships 2–3).
2. **Hero animation.** The cyber-sakura is a nice signature but is clamped small and pushed off the
   right edge. Options to explore: **enlarge & re-anchor it** as a real backdrop, or replace it with a
   stronger *local* hero (generative canvas/SVG field, particle/constellation weave, animated
   gradient mesh) — all offline-safe.
3. **Density & layout.** One narrow `max-w-6xl` rail leaves desktop whitespace; explore a wider,
   responsive **bento/grid** so Overview panels and tables breathe (prior art in the sibling projects).
4. **Overview information hierarchy.** Seven panels compete; consider a clearer "at-a-glance → drill
   down" order and a hero KPI strip.
5. **Applications is the emotional core.** The Sankey + kanban + email timeline tell the real story —
   give them more prominence and a refined, legible flow (must-keep, restyle).
6. **Card system.** Job vs application vs KPI cards each have bespoke styling; unify into one card
   language (elevation, spotlight, rails, badges) with consistent tokens.
7. **Motion coherence.** Many good one-off effects (sweep, drift, spotlight, count-up); define a
   single motion spec (durations, easings, stagger, reduced-motion tiers) so it feels intentional.
8. **Light mode parity.** Light theme is functional but plainer than dark; each concept should design
   both.
9. **Empty/first-run states.** Redacted/empty funnels and zero-result lists deserve designed empty
   states.

---

## 7. What Stage 2 will deliver (for your pick)

- **2–3 named visual concepts**, each with: palette + tokens, gradient/texture system, a hero-animation
  proposal (bigger tree *or* a better local alternative), typography, and a motion spec — with public
  inspiration cited (GitHub projects, dashboard galleries, Reddit, Medium).
- A **surface-by-surface overhaul plan** mapping every item in §3 to its redesigned form, explicitly
  annotated *"functionality preserved"* against the §0 guardrails and the JSON contract.
- A **phased execution plan** (tokens → shell/hero → per-tab → motion polish) so it ships incrementally
  behind the existing build, nothing regressing.

> **Review ask:** does §3–§6 match how you see the dashboard, and is anything missing from the
> inventory before I build the concepts? Any early lean between *evolve the cyber vibe* vs *go bolder*
> will help me aim the 2–3 concepts.
