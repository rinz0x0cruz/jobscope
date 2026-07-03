import type { ReactNode } from 'react'

export function Switch({
  checked,
  onChange,
  label,
  icon,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  icon?: ReactNode
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={
        'flex items-center gap-1.5 rounded-[10px] border px-2.5 py-1.5 text-[13px] transition ' +
        (checked
          ? 'border-accent bg-accent-dim text-accent'
          : 'border-border bg-card text-dim hover:border-border-h hover:text-fg')
      }
    >
      {icon}
      {label}
    </button>
  )
}
