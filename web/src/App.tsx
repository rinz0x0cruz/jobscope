import { useMemo, useState } from 'react'
import { dashboard, encryptedSite } from '@/data'
import type { FacetKey, TabValue } from '@/lib/urlState'
import { FACET_KEYS } from '@/lib/urlState'
import type { FacetOption } from '@/lib/filters'
import {
  activeChips,
  applyFacets,
  buildDisplayItems,
  countActive,
  facetOptions,
  tabPool,
  toggleValue,
} from '@/lib/filters'
import { fuzzy, makeFuse } from '@/lib/search'
import { fmtGenerated } from '@/lib/format'
import { useSearchState } from '@/hooks/useSearchState'
import { Header } from '@/components/Header'
import { Kpis } from '@/components/Kpis'
import { PrimaryNav, primaryFor, type Primary } from '@/components/PrimaryNav'
import { TierSegment } from '@/components/TierSegment'
import { FacetBar } from '@/components/filters/FacetBar'
import { ActiveChips } from '@/components/filters/ActiveChips'
import { SearchPalette } from '@/components/filters/SearchPalette'
import { JobList } from '@/components/JobList'
import { Overview } from '@/components/overview/Overview'
import { Applications } from '@/components/applications/Applications'
import { Outreach } from '@/components/outreach/Outreach'
import { ShellV2 } from '@/app/ShellV2'
import { readCachedUnlock, clearUnlock } from '@/lib/unlock'
import type { DashboardData } from '@/lib/schema'
import { JobDrawer } from '@/components/JobDrawer'
import { HeroBackdrop, HERO_VARIANTS, type HeroVariant } from '@/components/HeroBackdrop'
import { Toaster } from 'sonner'

// Preview switcher: pick the hero backdrop with `?hero=constellation|flowfield|dotgrid|aurora`.
const heroParam = new URLSearchParams(window.location.search).get('hero') ?? ''
// Touch / small screens default to the CSS aurora: the canvas variants re-rasterise
// a fixed backdrop during a pinch-zoom (which glitches on phones), while the blurred
// aurora scales smoothly with the page. An explicit `?hero=` always wins.
const prefersCalmHero =
  window.matchMedia?.('(pointer: coarse)').matches || window.innerWidth < 640
const HERO: HeroVariant = (HERO_VARIANTS as string[]).includes(heroParam)
  ? (heroParam as HeroVariant)
  : prefersCalmHero
    ? 'aurora'
    : 'constellation'

// v2 UX rebuild preview (?shell=v2): render the new warm light AppShell around the
// existing content. Force the light theme so v1 content reads coherently until the
// phased re-skin lands. Default (no flag) = the current v1 shell, untouched.
const SHELL_V2 = new URLSearchParams(window.location.search).get('shell') === 'v2'
if (SHELL_V2 && typeof document !== 'undefined') {
  // v2 is light-first, but honor a persisted choice so dark mode sticks on reload.
  let stored: string | null = null
  try {
    stored = localStorage.getItem('jobscope-theme')
  } catch {
    stored = null
  }
  const el = document.documentElement
  el.classList.remove('dark', 'light')
  el.classList.add(stored === 'dark' ? 'dark' : 'light')
}

export default function App() {
  const { state, set } = useSearchState()
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set())
  // A redacted public build unlocks to the full un-redacted payload at runtime:
  // passphrase-gated, decrypted in-browser (lib/unlock), cached in sessionStorage
  // for the tab. Unlocking swaps in the un-redacted rows (JDs, rationale,
  // contacts), applications, and overview funnel wholesale.
  const [unlocked, setUnlocked] = useState<DashboardData | null>(() => readCachedUnlock())
  const relock = () => {
    clearUnlock()
    setUnlocked(null)
  }
  const data = unlocked ?? dashboard
  const rows = data.rows
  const apps = data.applications ?? []
  const overview = data.overview

  const tabCounts = useMemo(() => {
    const base = tabPool(rows, 'all', state.hideClosed)
    const c: Record<TabValue, number> = { overview: base.length, applications: apps.length, outreach: 0, all: base.length, Strong: 0, Good: 0, Stretch: 0, Skip: 0 }
    for (const r of base) c[r.tier] += 1
    return c
  }, [rows, state.hideClosed, apps.length])

  const tabbed = useMemo(
    () => tabPool(rows, state.tab, state.hideClosed),
    [rows, state.tab, state.hideClosed],
  )
  const faceted = useMemo(() => applyFacets(tabbed, state), [tabbed, state])
  const fuse = useMemo(() => makeFuse(faceted), [faceted])
  const searched = useMemo(() => fuzzy(fuse, faceted, state.q), [fuse, faceted, state.q])

  const options = useMemo(() => {
    const o = {} as Record<FacetKey, FacetOption[]>
    for (const k of FACET_KEYS) o[k] = facetOptions(tabbed, state, k)
    return o
  }, [tabbed, state])

  const selected = useMemo(() => {
    const s = {} as Record<FacetKey, string[]>
    for (const k of FACET_KEYS) s[k] = state[k]
    return s
  }, [state])

  const items = useMemo(
    () => buildDisplayItems(searched, state.group, collapsed),
    [searched, state.group, collapsed],
  )
  const chips = useMemo(() => activeChips(state), [state])
  const nActive = countActive(state)
  const openJob = useMemo(() => rows.find((r) => r.id === state.job) ?? null, [rows, state.job])
  const openDrawer = (id: string) => set({ job: id })
  const closeDrawer = () => set({ job: undefined })

  const toggleFacet = (key: FacetKey, value: string) =>
    set({ [key]: toggleValue(state[key], value) } as Partial<typeof state>)
  const removeChip = (key: FacetKey, value: string) =>
    set({ [key]: state[key].filter((v) => v !== value) } as Partial<typeof state>)
  const clearAll = () =>
    set(Object.fromEntries(FACET_KEYS.map((k) => [k, []])) as Partial<typeof state>)
  const toggleCollapse = (company: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(company)) next.delete(company)
      else next.add(company)
      return next
    })
  const onPrimary = (p: Primary) =>
    set({ tab: p === 'jobs' ? (primaryFor(state.tab) === 'jobs' ? state.tab : 'all') : p })

  const tabContent =
    state.tab === 'overview' ? (
      <Overview rows={rows} stats={overview} apps={apps} onOpen={openDrawer} />
    ) : state.tab === 'applications' ? (
      <Applications apps={apps} encBlob={encryptedSite} onUnlock={setUnlocked} onOpen={openDrawer} />
    ) : state.tab === 'outreach' ? (
      <Outreach profile={data.profile} applied={data.applied_outreach ?? []} />
    ) : (
      <>
        <TierSegment value={state.tab} counts={tabCounts} onChange={(t) => set({ tab: t })} />
        <FacetBar
          options={options}
          selected={selected}
          onToggle={toggleFacet}
          group={state.group}
          onGroup={(v) => set({ group: v })}
          hideClosed={state.hideClosed}
          onHideClosed={(v) => set({ hideClosed: v })}
          activeCount={nActive}
          onClear={clearAll}
        />
        <ActiveChips chips={chips} onRemove={removeChip} />
        <JobList items={items} collapsed={collapsed} onToggleCollapse={toggleCollapse} onOpen={openDrawer} />
      </>
    )

  const overlays = (
    <>
      <SearchPalette rows={rows} onNavigate={(t) => set({ tab: t })} />
      <JobDrawer job={openJob} allRows={rows} onOpen={openDrawer} onClose={closeDrawer} />
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: 'var(--card)',
            color: 'var(--fg)',
            border: '1px solid var(--border)',
          },
        }}
      />
    </>
  )

  if (SHELL_V2) {
    return (
      <ShellV2
        data={data}
        search={state.q}
        onSearch={(v) => set({ q: v }, { replace: true })}
        onLock={relock}
        onOpenJob={openDrawer}
        openJob={openJob}
        onCloseJob={closeDrawer}
      />
    )
  }

  return (
    <div className="relative min-h-screen overflow-x-clip">
      <HeroBackdrop variant={HERO} />
      <Header
        total={rows.length}
        shown={searched.length}
        generated={fmtGenerated(data.generated)}
        query={state.q}
        onQuery={(v) => set({ q: v }, { replace: true })}
        encBlob={encryptedSite}
        unlocked={!!unlocked}
        onUnlock={setUnlocked}
        onLock={relock}
      />
      <main className="relative z-10 mx-auto flex max-w-7xl flex-col gap-4 px-6 py-6">
        <Kpis rows={rows} />
        <PrimaryNav tab={state.tab} jobsCount={tabCounts.all} appsCount={apps.length} onSelect={onPrimary} />
        {tabContent}
      </main>
      {overlays}
    </div>
  )
}
