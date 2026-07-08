import { Layers, X } from 'lucide-react'
import type { FacetOption } from '@/lib/filters'
import type { FacetKey } from '@/lib/urlState'
import { FACETS } from '@/lib/urlState'
import { FacetSelect } from './FacetSelect'
import { Switch } from '../Switch'

export function FacetBar({
  options,
  selected,
  onToggle,
  group,
  onGroup,
  hideClosed,
  onHideClosed,
  activeCount,
  onClear,
}: {
  options: Record<FacetKey, FacetOption[]>
  selected: Record<FacetKey, string[]>
  onToggle: (key: FacetKey, value: string) => void
  group: boolean
  onGroup: (v: boolean) => void
  hideClosed: boolean
  onHideClosed: (v: boolean) => void
  activeCount: number
  onClear: () => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {FACETS.map((f) => {
        if (options[f.key].length > 1) {
          return (
            <FacetSelect
              key={f.key}
              label={f.label}
              options={options[f.key]}
              selected={selected[f.key]}
              onToggle={(v) => onToggle(f.key, v)}
            />
          )
        }
        // The Resume facet only filters with 2+ resume bases in the data. Rather
        // than hide it (which reads as a missing feature), show a disabled hint
        // that explains how to enable it. #10
        if (f.key === 'resume') {
          return (
            <button
              key={f.key}
              type="button"
              disabled
              title="Import 2+ named resumes and rerun match to filter by resume"
              className="flex cursor-not-allowed items-center gap-1 rounded-[10px] border border-dashed border-border bg-card/50 px-2.5 py-1.5 text-[13px] text-mute"
            >
              {f.label}
            </button>
          )
        }
        return null
      })}

      <div className="mx-1 h-5 w-px bg-border" />

      <Switch checked={group} onChange={onGroup} icon={<Layers size={13} />} label="Group" />
      <Switch checked={hideClosed} onChange={onHideClosed} label="Hide closed" />

      {activeCount > 0 && (
        <button
          type="button"
          onClick={onClear}
          className="flex items-center gap-1 rounded-[10px] border border-border bg-card px-2.5 py-1.5 text-[13px] text-dim transition hover:border-border-h hover:text-fg"
        >
          <X size={13} /> Clear {activeCount}
        </button>
      )}
    </div>
  )
}
