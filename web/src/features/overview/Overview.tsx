// The Overview lens: a chart-first dashboard over the whole hunt — KPI tiles plus
// a fit-tier donut, a conversion funnel, a weekly surfacing trend, a score
// histogram, and top-N breakdowns (companies / locations / sources).

import { useEffect, useRef } from 'react'
import { Briefcase, CalendarClock, Gauge, Send, Star, Trophy } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Card, StatCard, animate } from '@/ui'
import type { OverviewModel } from '@/lib/overview'
import { BarRows, Donut, Funnel, TrendArea, VBars } from './charts'

export interface OverviewProps {
  model: OverviewModel
}

const KPI_ICON: Record<string, LucideIcon> = {
  roles: Briefcase,
  strong: Star,
  applied: Send,
  interviews: CalendarClock,
  offers: Trophy,
  avgfit: Gauge,
}

export function Overview({ model }: OverviewProps) {
  const rootRef = useRef<HTMLDivElement>(null)

  // Staggered fade+rise of the KPI tiles then each chart card on mount.
  // `animate` is a no-op under prefers-reduced-motion (items stay visible).
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    root.querySelectorAll<HTMLElement>('section > *').forEach((el, i) => {
      animate(
        el,
        [
          { opacity: 0, transform: 'translateY(8px)' },
          { opacity: 1, transform: 'translateY(0)' },
        ],
        {
          duration: 260,
          delay: Math.min(i * 35, 350),
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

      <section className="grid gap-4 lg:grid-cols-2">
        <Card title="Fit distribution">
          <Donut segs={model.tiers.segs} total={model.tiers.total} />
        </Card>

        <Card title="Pipeline funnel">
          <Funnel stages={model.funnel} />
        </Card>

        <Card title="Roles surfaced · last 8 weeks" className="lg:col-span-2">
          <TrendArea points={model.trend} />
        </Card>

        <Card title="Score distribution">
          <VBars items={model.scores} />
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
    </div>
  )
}
