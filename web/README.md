# jobscope — web dashboard

Motion-first, statically-exported dashboard for [jobscope](../README.md), built with
**Vite + React 19 + TypeScript + Tailwind v4 + Motion + TanStack Virtual**. It replaces the
Python-rendered single-file HTML dashboard (see [../plan/ui-upgrade.md](../plan/ui-upgrade.md)).

The job data is **baked in at build time** — the app imports `src/data/dashboard.json`, so the
built output runs fully offline (from `file://` or GitHub Pages) with no runtime API. `base: './'`
keeps all asset paths relative.

## Develop

```bash
# 1. emit the data contract from the Python side (repo root)
python -m jobscope dashboard --emit-json          # -> data/dashboard.json  (full, local)
#   ...or the redacted copy for the public build:
python -m jobscope dashboard --emit-json --public  # -> data/dashboard.public.json

# 2. copy it into the app (gitignored)
cp ../data/dashboard.json src/data/dashboard.json

# 3. run
npm install
npm run dev        # http://localhost:5173 (HMR)
npm run build      # tsc + vite build -> dist/  (static, relative paths)
npm run preview    # serve dist/ locally
```

## Layout

```
src/
  lib/schema.ts     1:1 TypeScript mirror of the Python data contract (render.py)
  lib/format.ts     card label helpers (comp / stock / dates)
  data/             baked dashboard.json (gitignored) + wrapper
  hooks/useTheme.ts class-based light/dark, persisted, no FOUC
  styles/theme.css  ported design tokens (--bg/--accent/--card/…) + Tailwind theme
  components/       Header, Kpis, JobCard, JobList (virtualized)
```

## Status

Phase 2 (scaffold) of the migration: virtualized card list, tier KPIs, search, tier filters, and
theme toggle over the real dataset. Overview charts, the detail drawer, the command palette,
URL-shareable state, and the PWA land in later phases (see the plan).
