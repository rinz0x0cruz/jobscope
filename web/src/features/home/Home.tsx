// The Home lens: the editorial Briefing narrative up top, then the pipeline-flow
// chart. Merges the former Briefing + Overview lenses into one landing view.

import { Briefing } from '@/features/briefing'
import type { Briefing as BriefingModel } from '@/lib/briefing'
import { Card } from '@/ui'
import type { Application } from '@/lib/schema'
import { PipelineFlow } from './PipelineFlow'

export interface HomeProps {
  briefing: BriefingModel
  apps: Application[]
  onOpen: (jobId: string) => void
}

export function Home({ briefing, apps, onOpen }: HomeProps) {
  return (
    <div className="space-y-6">
      <Briefing briefing={briefing} onOpen={onOpen} />
      <Card title="Pipeline flow">
        <PipelineFlow apps={apps} />
      </Card>
    </div>
  )
}
