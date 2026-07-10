// The Home lens: a chart dashboard (KPI tiles + fit / score / companies /
// locations / sources charts + the pipeline-flow Sankey) above the editorial
// Briefing narrative. Merges the former Briefing + Overview lenses into one view.

import { useEffect, useRef } from 'react'
import { Briefcase, CalendarClock, Gauge, Send, Star, Trophy } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Briefing } from '@/features/briefing'
import type { Briefing as BriefingModel } from '@/lib/briefing'
import { Card, StatCard, animate } from '@/ui'
import type { OverviewModel } from '@/lib/overview'
import type { Application } from '@/lib/schema'
import { BarRows, Donut, TrendArea, VBars } from './charts'
import { PipelineFlow } from './PipelineFlow'

export interface HomeProps {
  model: OverviewModel
  briefing: BriefingModel
  apps: Application[]
  onOpen: (jobId: string) => void
}

const KPI_ICON: Record<string, LucideIcon> = {
  roles: Briefcase,
  strong: Star,
  applied: Send,
  interviews: CalendarClock,
  offers: Trophy,
  avgfit: Gauge,
}

export function Home({ model, briefing, apps, onOpen }: HomeProps) {
  const rootRef = useRef<HTMLDivElement>(null)

  // Staggered fade+rise of the KPI tiles then each chart card on mount.
  // `animate` is a no-op under prefers-reduced-motion (items stay visible).
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    root.querySelectorAll<HTMLElement>('[data-stagger] > *').forEach((el, i) => {
      animate(
        el,
        [
          { opacity: 0, transform: 'translateY(8px)' },
          { opacity: 1, transform: 'translateY(0)' },
        ],
        {
          duration: 260,
          delay: Math.min(i * 30, 320),
          easing: 'cubic-bezier(.2,0,0,1)',
          fill: 'backwards',
        },
      )
    })
  }, [])

  return (
    <div ref={rootRef} className="space-y-6">
      <section
        aria-label="Key figures"
        data-stagger
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6"
      >
        {model.kpis.map((k) => {
          const Icon = KPI_ICON[k.key] ?? Briefcase
          return (
            <StatCard
              key={k.key}
              label={k.label}
              value={k.value.toLocaleString()}
              icon={<Icon size={16} aria-hidden="true" />}
            />
          )
        })}
      </section>

      <section data-stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card title="Fit distribution">
          <Donut segs={model.tiers.segs} total={model.tiers.total} />
        </Card>
        <Card title="Score distribution">
          <VBars items={model.scores} />
        </Card>
        <Card title="Roles surfaced · last 8 weeks">
          <TrendArea points={model.trend} />
        </Card>
        <Card title="Pipeline flow" className="sm:col-span-2 lg:col-span-3">
          <PipelineFlow apps={apps} />
        </Card>
        <Card title="Top companies">
          <BarRows items={model.companies} emptyLabel="No companies yet" />
        </Card>
        <Card title="Where roles are">
          <BarRows items={model.locations} color="var(--good)" emptyLabel="No locations yet" />
        </Card>
        <Card title="Sources">
          <BarRows items={model.sources} color="var(--stretch)" emptyLabel="No sources yet" />
        </Card>
      </section>

      <Briefing briefing={briefing} onOpen={onOpen} showFigures={false} />
    </div>
  )
}
