import { Moon, Search, Sun } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'

interface Props {
  total: number
  shown: number
  generated: string
  query: string
  onQuery: (v: string) => void
}

export function Header({ total, shown, generated, query, onQuery }: Props) {
  const { theme, toggle } = useTheme()
  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center gap-4 border-b border-border bg-bg/70 px-6 py-3.5 backdrop-blur-lg backdrop-saturate-150">
      <div className="flex items-center gap-2.5">
        <div className="h-[22px] w-[22px] rounded-[7px] bg-gradient-to-br from-accent to-[#b7a6ff] shadow-[0_6px_16px_-6px_var(--accent)]" />
        <div>
          <h1 className="text-base font-semibold leading-none tracking-tight">jobscope</h1>
          <div className="mt-0.5 text-xs text-mute tnum">
            {shown === total ? `${total} roles` : `${shown} / ${total} roles`} &middot; {generated}
          </div>
        </div>
      </div>

      <div className="flex-1" />

      <label className="relative">
        <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 opacity-50" />
        <input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Search title, company, place…"
          className="w-64 rounded-[10px] border border-border bg-card py-2 pl-9 pr-3 text-[13px] text-fg outline-none transition-[width,box-shadow,border-color] focus:w-72 focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-dim)]"
        />
      </label>

      <button
        type="button"
        onClick={toggle}
        aria-label="Toggle theme"
        className="grid h-9 w-9 place-items-center rounded-[10px] border border-border bg-card text-dim transition hover:border-border-h hover:text-fg"
      >
        {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
      </button>
    </header>
  )
}
