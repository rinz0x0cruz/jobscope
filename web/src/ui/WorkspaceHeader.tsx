import type { ReactNode } from 'react'

export interface WorkspaceHeaderProps {
  eyebrow: ReactNode
  title: string
  description: ReactNode
  actions?: ReactNode
  meta?: ReactNode
  accent?: 'brand' | 'signal' | 'none'
}

export function WorkspaceHeader({
  eyebrow,
  title,
  description,
  actions,
  meta,
  accent = 'none',
}: WorkspaceHeaderProps) {
  return (
    <header className="workspace-header relative shrink-0 border-b border-line bg-panel px-5 py-4 sm:px-7">
      {accent !== 'none' && (
        <span
          aria-hidden="true"
          className={`absolute inset-y-0 left-0 w-1 ${accent === 'brand' ? 'bg-brand' : 'bg-signal'}`}
        />
      )}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 max-w-3xl">
          <p className={`text-[11px] font-semibold ${accent === 'signal' ? 'text-signal' : accent === 'brand' ? 'text-brand' : 'text-ink-3'}`}>
            {eyebrow}
          </p>
          <h1 className="mt-0.5 font-display text-2xl font-semibold leading-tight text-ink">{title}</h1>
          <p className="mt-1 text-[13px] leading-5 text-ink-3">{description}</p>
          {meta && <div className="mt-1.5 text-[11px] text-ink-3">{meta}</div>}
        </div>
        {actions && <div className="flex max-w-full flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  )
}