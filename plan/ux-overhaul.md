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

---
---

# Stage 2 — visual concepts + surface-by-surface overhaul plan

> Direction (from review): **explore 2–3 distinct concepts to pick from**; preserve **PWA/offline** and
> the **funnel Sankey**; everything else open, incl. **making the tree bigger or replacing it with a
> better hero animation**. This stage proposes the look; **Stage 3 = implement the chosen concept**.

## A. Inspiration digest (public sources + your own stack)

- **Palette systems.** *Catppuccin* (19.4k★) — a warm **pastel** system, 4 flavors × 26 tokens, whose
  stated philosophy is *"colorful > colorless, balance (not too dull/bright), harmony > dissonance"* —
  a great model for a **balanced** (not garish) neon. *Nord* (6.8k★) — an **arctic, dimmed-pastel**,
  minimal-flat system (calm, professional). *Radix Colors / Tailwind* — accessible stepped scales for
  contrast-safe states.
- **Dashboard patterns.** *Tremor* (Tailwind + Radix, 35+ dashboard components) — data-first cards,
  KPIs, and charts with restrained chrome. The **bento-grid** trend (asymmetric, right-sized tiles).
  *Linear / Vercel / Stripe* — calm-premium: deep neutral base, one accent, big legible numerals,
  micro-motion. *Grafana*-style density for the data-heavy tabs.
- **Offline-safe hero/motion.** Generative **gradient mesh**, **particle/constellation** networks,
  **flow fields**, **dot-matrix** — all doable in local canvas/SVG (no CDN, honours the offline rule).
- **Your own aesthetic (cohesion).** The sibling **exploitrank** console is dark, **warm-amber,
  terminal/console, data-dense** (geo map + entity-linked "intel brief"). jobscope's current
  warm-sunset-over-navy is already in that family — so a warm-on-dark concept keeps your projects
  visually related, while a cool/premium concept deliberately sets jobscope apart.

## B. The three concepts

Each is a full token + motion system; all satisfy §0 guardrails (local fonts/assets, reduced-motion
tiers, contrast-safe). Palettes below are concrete starting hexes (dark; each ships a light twin).

### Concept A — **“Nightshift”** · *evolve the cyber vibe, done with discipline*
A refined version of today: warm signature + one cool data hue on deep ink, glassy cards, **tamed**
neon (edges & glows, not everywhere). Most cohesive with exploitrank.

| Token | Value | Role |
|---|---|---|
| `--bg` / `--bg2` | `#060b14` / `#0a1220` | deep ink base |
| `--card` / `--card-h` | `#0e1826` / `#132238` | glassy surface |
| `--border` | `#1c2b42` → `#2d4667` | hairline / hover |
| `--fg / --dim / --mute` | `#eaf2ff` / `#9fb2cc` / `#5f728c` | text ramp |
| **`--hot`** (signature warm) | `#fb7185` coral → `#f59e0b` amber | primary accent / CTAs |
| **`--cool`** (data) | `#22d3ee` cyan / `#2dd4bf` teal | charts, links, focus |
| tiers | strong `#34d399` · good `#38bdf8` · stretch `#fbbf24` · skip `#64748b` | |

- **Gradient/texture:** low-opacity aurora (cyan→violet→amber) confined to the hero; 1px card edge
  in `--hot`/`--cool` on hover; faint grid retained but quieter.
- **Hero animation:** **enlarge the tree into a real backdrop** *or* replace it with a **“signal
  constellation”** — a local canvas particle field whose nodes connect into a shifting network
  (nods to a job *network*). Bloom/parallax on scroll. (Tree stays as an option, just bigger + better-anchored.)
- **Type:** self-hosted **Inter** (UI) + **JetBrains Mono** (numerals/labels).
- **Motion:** energetic springs, glow-pulse on `interview`/`offer`, count-ups, shared-element card→drawer.
- **Feels like:** a premium cyber HUD. **Best if** you love the current energy but want it intentional.

### Concept B — **“Aurora Calm”** · *premium product dashboard (Linear / Vercel / Stripe)*
A deliberate pivot to calm precision: neutral base, **one** accent, generous space, big numerals,
micro-motion. Recruiter-shareable, timeless.

| Token | Value | Role |
|---|---|---|
| `--bg` / `--bg2` | `#0a0a0c` / `#101014` | near-black neutral |
| `--card` / `--card-h` | `#16161a` / `#1c1c22` | flat surface, hairline border `#26262c` |
| `--fg / --dim / --mute` | `#f4f4f5` / `#a1a1aa` / `#71717a` | zinc text ramp |
| **`--accent`** (single) | `#8b5cf6` violet *(or* `#f59e0b` amber *)* | the one hue; data uses its tints + grays |
| tiers | strong `#10b981` · good `#3b82f6` · stretch `#f59e0b` · skip `#52525b` | muted, contrast-safe |

- **Gradient/texture:** a single soft **aurora mesh** in the hero only; everything else flat with
  crisp hairlines and real elevation shadows. No grid, no scanlines.
- **Hero animation:** **retire the tree**; replace with a subtle **animated gradient-mesh** wash (very
  slow) behind a large KPI headline. Motion is ambient, never demanding.
- **Type:** self-hosted **Geist** / **Inter**; large tabular numerals; tight tracking.
- **Motion:** 150–250 ms purposeful transitions, layout animations, restrained; decorative motion
  minimal by default.
- **Feels like:** a funded SaaS analytics product. **Best if** you want it to read as serious/pro.

### Concept C — **“Mission Console”** · *editorial terminal / data-console (bold, distinctive)*
Leans all the way into the console identity (cohesive with exploitrank but its own thing): mono-forward
type, structured grid, the **Sankey as the hero**, a real **command bar**, terminal micro-motion.

| Token | Value | Role |
|---|---|---|
| `--bg` / `--bg2` | `#0b0a08` / `#12100c` | warm ink |
| `--card` | `#17140d` border `#2a2416` | panel |
| `--fg / --dim / --mute` | `#f5efe0` / `#b9ad92` / `#6b6350` | warm paper text |
| **`--amber`** (terminal) | `#fbbf24` → `#f59e0b` | primary; headings, section rules |
| **`--signal`** (cool) | `#38bdf8` | links / entities (like exploitrank's brief) |
| tiers | strong `#a3e635` · good `#38bdf8` · stretch `#fbbf24` · skip `#78716c` | |

- **Gradient/texture:** subtle **scanline / dot-matrix** overlay; amber section rules; monospace labels;
  data-ink maximised (Tufte-ish).
- **Hero animation:** the **pipeline Sankey becomes the hero**, plus a local **flow-field / dot-matrix**
  “signal” backdrop; the tree is reimagined as an **ASCII/tech-tree** motif or dropped.
- **Type:** **JetBrains Mono** (labels/data) + a grotesk (**Space Grotesk**/**Inter**) for headings.
- **Motion:** typewriter/section reveals, a live status ticker, scanline sweeps, terminal caret accents.
- **Feels like:** a mission-control console for your job hunt. **Best if** you want maximum character.

### Concept cheat-sheet
| | A · Nightshift | B · Aurora Calm | C · Mission Console |
|---|---|---|---|
| Vibe | refined cyber | calm premium | editorial terminal |
| Base | deep ink + warm/cool neon | near-black neutral | warm ink |
| Accents | coral+amber / cyan | one hue (violet/amber) | amber + cool signal |
| Density | medium-high | medium (airy) | high |
| Hero | bigger tree / constellation | gradient mesh | Sankey + flow-field |
| Risk | can still over-glow | may feel “safe” | mono can tire; needs finesse |
| Cohesion w/ exploitrank | ★★★ | ★ | ★★★ |

## C. Recommendation
**Lead with Concept A (“Nightshift”)** — it honours what you already like, fixes the palette-naming
drift, tames the neon into intentional accents, and delivers the “bigger/better hero” you asked for
(constellation *or* enlarged tree), while staying cohesive with exploitrank. Keep **B** as the
“go serious” pivot and **C** as the “go bold” option. A strong hybrid also exists: **A’s palette + C’s
command bar + Sankey-forward Applications tab.**

---
---

# Stage 3 — Execution & refinement plan (Concept A · "Nightshift, refined")

> Direction locked (from review + owner): **Concept A** is chosen and **Phase 1 shipped** — the
> Nightshift Console tokens (`dbfa6ad`) and the `grid` hero default (`4e634e4`) are on `main`. Owner's
> Stage-3 brief: keep & **elevate the cyber vibe** but make it **cleaner / calmer / more whitespace**,
> add **premium-SaaS polish** (Linear / Vercel / Stripe), stay **data-dense** where it earns it, lean
> into **gamification** (Chances / streaks), and — explicitly — **"lose the moving grid and replace it
> with a better one."** Guardrails: §0 above still bind (offline PWA, redaction, JSON contract, Sankey
> kept, encrypted Applications, a11y floor) **plus** *zero feature regressions* and *no heavy new deps
> (bundle ≤ current ~316 KB gz)*.

This stage turns the chosen concept into a **phased, shippable execution plan**. It does not re-litigate
Stage 1/2 — it builds on them.

## S3.0 — The refinement thesis (what a re-audit of the *shipped* Phase 1 revealed)

Concept A promised *"tamed neon — edges & glows, not everywhere."* The **implementation** hasn't yet
delivered that discipline: at rest, with no user action, the dashboard currently animates **~7 ambient
layers simultaneously**:

1. `body` `jsBgDrift` (11 s gradient wash + 86 px grid) · 2. `.js-ambient` conic aurora (`jsAmbientDrift`
9 s) · 3. `.js-scanlines` CRT texture · 4. `HeroBackdrop` canvas at 60 fps (default **`grid`**) ·
5. `.js-cyber-tree` self-drawing tree **+ `jsLeafFall` falling leaves** · 6. `.js-header-gradient`
sweep (`jsHeaderSweep` 8 s) · 7. per-card `.js-gradient-card` animated borders (`jsGradientSweep`
6.5 s) **+** a `::before` sweep — plus the logo (`jsGradientSweep` + rotating conic) and title
(`jsGradientSweep`).

**This is the single thing standing between "today" and "premium/calm."** It's loud, it competes with
the data, and it burns battery. So Stage 3's spine is one sentence:

> **Deliver the discipline Concept A already promised: collapse ~7 always-on ambient layers to one,
> move energy from *chrome* to *content + momentum*, and let hierarchy come from surface + type +
> spacing instead of perpetual glow.**

Everything below serves that thesis, inside the guardrails.

## S3.1 — Design-system refinement (extends the shipped Nightshift tokens)

Keep the Nightshift palette DNA (warm amber signal + cool cyan/sky data on deep ink). Add the missing
*structure* around it. All in `web/src/styles/theme.css`.

**Elevation ramp (replace animated gradient borders with real surfaces):**
```
--surface-0 = --bg      (page)        --surface-2 = --card   (card)
--surface-1 = --bg2     (sunken)      --surface-3 = new      (popover/drawer, ~+6% lightness)
--edge      = --border  (1px hairline, resting)
--edge-strong = --border-h (hover/active)
```
Retire `.js-gradient-card` animated borders → `--surface-2` + `1px --edge` + soft `--shadow` (+ optional
static 1px inset top-highlight). Keep `.js-spotlight-card` but hover-only, reduced intensity.

**Semantic color aliases (stop components reaching for `--neon-*`):**
```
--text-1/2/3 = --fg/--dim/--mute        --brand   = --accent  (the one warm CTA)
--entity     = --signal  (links/companies/data)   --positive/--warning/--danger = --strong/--stretch/--hot
--focus      = --accent
```
Reduce hues-per-screen to: ink neutrals + one entity-cool + one brand-warm + tier colors. The
violet/emerald neon quartet leaves with the animated borders. (This also fixes the Stage-1 §6.1
"neon-holds-warm-values" naming drift by making role-named aliases the public API.)

**Type scale + role assignment** (families already loaded — Inter / JetBrains Mono / Space Grotesk):
`display 40/700 Grotesk` (one hero number = Chances) · `h1 20/700` · `h2 16/600` · `body 14/450` ·
`label 12/500` · `micro 11/600 upper +0.08em`. **Rule: every number is JetBrains-Mono + tabular-nums**
(scores, KPIs, funnel, salary, dates, IDs). This is the cheapest "analyst-grade" upgrade.

**Motion tokens + doctrine:**
```
--dur-fast 120ms  --dur-base 200ms  --dur-slow 320ms
--ease-standard cubic-bezier(.2,0,0,1)  --ease-entrance cubic-bezier(0,0,0,1)  --ease-exit cubic-bezier(.4,0,1,1)
spring (interaction): stiffness 400–500 / damping 30–40  (standardize the existing usage)
```
Delete perpetual loops (`jsBgDrift`, `jsHeaderSweep`, card/logo/title `jsGradientSweep`, `jsLeafFall`).
Keep motion for **state change** (filter add/remove, tab/segment switch, drawer, count-up on first
paint, toast) and **one gated micro-delight** (streak week / first offer). Reduced-motion → instant +
single static backdrop frame (fewer layers = less to suppress).

**Density mode:** new `useDensity()` (`comfortable | compact`, localStorage — mirrors `useTheme` /
`useScoreFormat`). Compact tightens card padding, row height, and drops one type step in lists/tables —
serves "data-dense" without punishing casual use.

## S3.2 — The backdrop (retire the moving grid — the owner's explicit ask)

- **Delete** the `grid` variant (synthwave perspective) and, recommended, `radar`.
- **New default = "Signal"**: one calm, low-intensity layer — a sparse slow constellation + a single
  soft brand-tinted gradient wash at ~40–50 % of today's intensity, `mix-blend: screen`, **paused on
  blur / hidden tab / reduced-motion**. Keeps the "live job-network" metaphor without the grid's motion.
- **Collapse the ambient stack**: default page ships **backdrop only**. Move `.js-scanlines` +
  `.js-ambient` to opt-in; **retire the cyber-sakura tree + falling leaves** (Stage 1 §4.4 flagged it as
  under-sized/off-screen — recommend deletion, not enlargement). Net: **7 always-on layers → 1.**
- Keep the `?hero=` override (`constellation`, `aurora`, new `signal`) and the mobile static/aurora +
  pinch-zoom-freeze logic (`#46`). This is the highest-leverage calm + perf win in the plan.

## S3.3 — Information architecture refinement

7 tabs conflate *mode* and *filter*. Refine to **3 primary destinations + an in-context tier segment**:
```
Primary nav:  Overview · Jobs · Applications
Inside Jobs:  [ All · Strong · Good · Stretch · Skip ]  segmented control (radiogroup)  + facets + search
```
- `tab` param still accepts `Strong|Good|…` (deep links unchanged) — the segmented control writes the
  same param; **no `urlState.ts` schema change**, render-only.
- Consolidate display toggles (**theme · density · score-format**) into one header **View** menu; keep
  search + `⌘K` + Refresh + Unlock as the prominent actions. Promote `⌘K` as the primary accelerator.

## S3.4 — Surface-by-surface execution (maps Stage-1 §3 → redesigned form)

- **Global shell / Header** (`Header.tsx`, `App.tsx`): calm wordmark (drop title sweep), remove header
  sweep + tree + ambient mounts, **View** menu, prominent search + `⌘K`. Consider the Lottie mark → crisp
  static SVG (see S3.6 bundle note).
- **Overview** (`overview/*`): re-sequence the 7 panels into a narrative — **hero row: Momentum/Chances
  (large) + Fit donut**; then pipeline + top-companies; then skill-gaps full-width; then top-matches.
  Calmer `Card` (static border, hover-only spotlight). Momentum is the emotional anchor (display numeral,
  clean streak/velocity row, slim factor bars) — the gamification budget lives here.
- **Jobs list/card/drawer** (`JobList.tsx`, `JobCard.tsx`, `JobDrawer.tsx`): scannable JobCard (solid
  mono score/grade chip, 16/600 title, entity-cool company, 2–3 signal pills, quiet Apply); Strong-tier
  *pulse* → static tier chip; subtle lift; **density-aware**. Keep virtualization + grouping. Drawer:
  sticky header (score/tier/Apply/copy-link/prev-next) + clean accordion + better JD reading; keep JD
  search + recruiter outreach.
- **Applications** (`applications/*`): keep 4 views; **Table** becomes the data-dense showcase, **List**
  the comfortable default. **Sankey (must-keep)**: recolor to entity-cool flows + one warm for offers +
  `--danger` rejections + muted no-response, clearer labels, keep SVG export (#35). PipelineHealth →
  follow-ups-due as the actionable hero.
- **Filters / command** (`filters/*`): compact facet bar; mobile → single **Filters** popover w/ count;
  keep the disabled **Resume** hint (#10) and `ActiveChips` layout motion. Expand **SearchPalette (⌘K)**
  into a real command surface (navigate + act + fuzzy role search, grouped, recents).
- **System states**: first-class **empty / loading / skeleton / error** states (new `Skeleton.tsx`),
  per-tab empty states, keep the encrypted Applications gate.
- **Mobile**: static backdrop, segmented nav row, condensed header (mark + search + `⌘K` + "···"),
  single-column comfortable cards, sticky-first-column tables, hit targets ≥ 40 px.

## S3.5 — Phased rollout (foundation-first; each phase independently green; no contract change)

| Phase | Theme | Scope | Exit check |
|------|-------|-------|-----------|
| **P0 Foundation** | tokens & motion | elevation ramp, semantic aliases, type scale (mono numerals), motion tokens, `useDensity`; **delete the tree + collapse ambient to backdrop-only; retire `grid`; ship calm "Signal" default** | vitest + build green; visibly calmer; bundle ≤ current |
| **P1 Chrome & IA** | header + nav | header reorg, **View** menu, 3-primary nav + tier **segment**, expanded `⌘K` | deep-links resolve tiers; keyboard; a11y |
| **P2 Overview** | bento + Momentum hero | re-sequenced bento, calmer cards, Momentum hero, mono numerals | overview/render tests; screenshot |
| **P3 Jobs** | list/card/drawer + density | JobCard redesign, group headers, drawer accordion + sticky header, density mode | JobCard/drawer tests; virtualization intact |
| **P4 Applications** | board + Sankey/health | views refined, Sankey recolor, PipelineHealth clarity | applications tests; Sankey export works |
| **P5 Polish** | states/a11y/perf | empty/loading/skeleton/error, contrast audit, motion polish, bundle trims (lazy-split Applications + drawer; optional Lottie→SVG) | full vitest + build; a11y checklist; bundle ≤ baseline |

Per phase (mirrors `AGENTS.md`): branch → implement → `npm run test` + `tsc`/`vite build` +
`pytest`/`selftest` (untouched, green) → `dashboard --emit-web` + preview screenshot → PR → merge.
**Ship P0 alone first** so the calm is felt immediately and everything else layers onto a stable base.

## S3.6 — Accessibility & performance deltas

- **A11y:** contrast-audit the calmer palette (both themes) to AA/AAA; tier segment as `radiogroup` w/
  arrow keys; keep Radix focus-trap + global reduced-motion switch; hit targets ≥ 40 px; re-check
  `aria-label`s on the reorganized header/View menu.
- **Perf:** removing 5–6 always-on animation layers is *prettier and faster* (less idle CPU/GPU/battery).
  **No new deps** (G4); prefer subtraction — evaluate **Lottie → static SVG** mark and **code-splitting
  Applications + JobDrawer** to trim the ~316 KB gz initial bundle. Re-measure each phase; DoD = **≤
  baseline gzip**.

## S3.7 — Risks · definition of done · open decisions

**Risks:** scope creep → hard phase gating; regressions → keep full vitest + per-surface render tests +
screenshot review; taste → P0 ships the calm foundation first for a go/no-go; contrast regressions →
audit in P0 + P5; identity loss → keep the Nightshift duotone + one signature backdrop + mono-numeral
console feel (restraint ≠ generic).

**Definition of done:** reads calmer/premium (≤ 1 ambient layer at rest); bundle gzip ≤ current; **0
feature regressions**; `pytest` + `selftest` + full `vitest` green; **JSON contract untouched**
(`tests/test_dashboard_json.py` is the canary); all deep-links resolve; reduced-motion parity + AA
contrast + full keyboard.

**Open decisions (confirm before P0):** (1) tier tabs → segmented control *(rec: yes)*; (2) **retire the
sakura tree entirely** *(rec: yes)*; (3) backdrop default = new calm **"Signal"** *(rec: yes)*; (4)
Lottie → static SVG for bundle savings *(optional)*; (5) density default = comfortable + compact opt-in
*(rec: yes)*.

## Appendix S3 — file change-map (by phase)

- **P0:** `web/src/styles/theme.css` (tokens, elevation, type, motion; delete tree/ambient/sweep
  keyframes), `web/src/components/HeroBackdrop.tsx` (new `signal` default; drop `grid`/`radar`),
  `web/src/App.tsx` (remove `.js-ambient` / `.js-scanlines` / `CyberSakura` mounts), delete
  `web/src/components/CyberSakura.tsx`, new `web/src/hooks/useDensity.tsx`.
- **P1:** `components/Header.tsx`, new `components/ViewMenu.tsx`, `components/Tabs.tsx` (→ primary nav),
  new `components/TierSegment.tsx`, `components/filters/SearchPalette.tsx`.
- **P2:** `components/overview/{Overview,Momentum,Donut,Bars}.tsx` + `Card` wrapper.
- **P3:** `components/{JobCard,JobList,JobDrawer}.tsx` + density adoption.
- **P4:** `components/applications/{Applications,views,AppCard,PipelineFlow,PipelineHealth}.tsx`.
- **P5:** new `components/Skeleton.tsx` + empty/error states; `vite.config.ts` (lazy split); optional
  `SignalLottie` → SVG. Tests: extend `web/test/*` per surface; `tests/test_dashboard_json.py` stays
  untouched-and-green as the contract canary.

## D. Surface-by-surface overhaul (functionality preserved — concept-agnostic)

Every current surface (§3) maps to a redesigned form; **no data/route/contract change** unless noted.

| Surface | Overhaul | Functionality preserved |
|---|---|---|
| **Global shell** | Wider **responsive bento** rail (replaces the single `max-w-6xl`); unified card language (elevation, edge, spotlight, rails as tokens). | Same routes/tabs; layout only. |
| **Hero / background** | New hero per concept (constellation / mesh / flow-field); tree enlarged-or-replaced; grid/aurora re-tuned; all local + reduced-motion tiered. | Decorative only; still `aria-hidden`, offline. |
| **Header + search** | Promote search to a **command bar** (`/` or ⌘K) over the same Fuse.js index; clearer brand lockup. | Same search scope + URL sync. |
| **Tabs** | Restyled segmented control with animated indicator; counts as pills. | Same 7 tabs + URL `tab`. |
| **Overview** | Re-ordered hierarchy: **hero KPI strip → donut + funnel → targeting/top-companies → skill constellation → top-matches**; bento tiles. | Same panels + data. |
| **KPIs** | Large tabular numerals, count-up, sparkline option (from existing data). | Same metrics. |
| **Donut / bars** | Restyle inline SVG to the concept palette; draw-in; hover tooltips. | Same hand-drawn SVG, no chart lib. |
| **Skill constellation** | Keep the graph; align node/edge styling + selection to the concept. | Same interaction/data. |
| **Applications** ⭐ | Make it the emotional centrepiece: **Sankey restyled + enlarged**, kanban with the unified card, email-timeline as a refined vertical thread. | **Sankey kept** (restyle only); kanban/statuses unchanged. |
| **Encrypted gate** | Restyle the unlock as a focused, on-brand moment (still WebCrypto in-browser). | Same E2E decrypt. |
| **Job list / cards** | One card system: score meter, intel dots → legible chips, tier pill, taken-down state; spotlight + rails as tokens; virtualization kept. | Same fields, virtualization, grouping. |
| **Detail drawer** | Section redesign (brief/comp/stock 52-wk/reddit/news/contacts/rationale/all-postings) as collapsible cards; keep right-slide + deep-link. | Same content + deep-link. |
| **Controls / facets** | Facets as a compact popover/faceted combobox; active chips; “clear all”. | Same facet logic + counts. |
| **Empty / redacted states** | Designed empty states (redacted funnel, zero-results, locked apps). | New affordance; no data change. |
| **Light mode** | First-class light twin for the chosen concept. | Parity. |
| **Motion** | One **motion spec** (durations/easings/stagger + reduced-motion tiers) replacing ad-hoc effects. | Same effects, coherent. |

## E. Phased execution (ships incrementally; nothing regresses)
1. **Tokens + type** — rename/replace `--neon-*`, add the concept palette + self-hosted fonts; light twin. *(Pure CSS; instant rollback.)*
2. **Shell + hero** — bento rail, new background/hero (behind reduced-motion), command bar.
3. **Per-tab** — Overview hierarchy → Applications (Sankey-forward) → list/cards → drawer.
4. **Motion pass** — apply the single motion spec; delete ad-hoc effects.
5. **Polish** — empty states, a11y audit, light-mode QA, perf check; local build + screenshot review at each step.

Each phase is a small PR behind the existing build; the JSON contract + `tests/test_dashboard_json.py`
stay green throughout.

## F. Your pick
1. **Which concept** — **A · Nightshift** (recommended), **B · Aurora Calm**, **C · Mission Console**, or a **hybrid**?
2. **The hero** — for the chosen concept: **enlarge the sakura tree**, or go **generative** (constellation / gradient-mesh / flow-field)?
3. **Accent**, if B — **violet** or **amber**?

Say the word and Stage 3 starts at Phase 1 (tokens + type) in this worktree, with a local preview to eyeball before anything touches the live site.

---
---

# Stage 3 — build log

**Chosen direction: A × C hybrid — “Nightshift Console.”** Concept A's deep-ink + tamed warm/cool
neon palette, wearing Concept C's console identity (mono-forward type, a ⌘K command bar, scanline/
dot-matrix texture, a Sankey-forward Applications tab). Guardrails from §0 hold throughout.

Token spec (dark): base `--bg #060b14`/`--bg2 #0a1220`, cards `#0e1826`/`#132238`; **warm signature**
`--accent #f59e0b` (amber) + `--hot #fb7185` (coral); **cool data** `--cool #22d3ee` / `--signal #38bdf8`
/ `--teal #2dd4bf`; legacy `--neon-*` retuned to the cool half; tiers strong `#34d399` · good `#38bdf8`
· stretch `#fbbf24` · skip `#64748b`. Type: Inter (UI) + JetBrains Mono (data/labels) + Space Grotesk
(display), self-hosted in Phase 1b.

### Phase status
- **Phase 1 — tokens + type — ✅ done (preview).** Retuned `:root` + `html.light` to the Nightshift
  Console duotone, mono-forward type tokens, warm/cool ambient. Pure CSS (`web/src/styles/theme.css`);
  cascades via the existing `@theme inline` vars — no component edits, instant rollback. Previewed as
  an un-redacted local build.
- **Phase 1b — self-host fonts** (Inter / JetBrains Mono / Space Grotesk via `@fontsource`, bundled
  for offline) — next.
- **Phase 2 — shell + hero + command bar.** ✅ tree replaced with a 6-variant generative hero switcher
  (`?hero=` constellation/flowfield/dotgrid/aurora/radar/grid), scanline texture, mono numerals, wider
  rail; **hero decided: `grid` (synthwave perspective, amber horizon).** Remaining: bento rail + ⌘K bar.
- **Phase 3 — per-tab** (Overview hierarchy → Applications Sankey-forward → list/cards → drawer).
- **Phase 4 — motion spec.** · **Phase 5 — polish** (empty states, a11y, light-mode QA, perf).
