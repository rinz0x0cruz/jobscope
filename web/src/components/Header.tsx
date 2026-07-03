import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
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
  const reduce = useReducedMotion()
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
          className="w-64 rounded-[10px] border border-border bg-card py-2 pl-9 pr-9 text-[13px] text-fg outline-none transition-[width,box-shadow,border-color] focus:w-72 focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-dim)]"
        />
        <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-border px-1.5 py-0.5 text-[10px] text-mute">
          /
        </kbd>
      </label>

      <button
        type="button"
        onClick={toggle}
        aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        className="relative grid h-9 w-9 place-items-center overflow-hidden rounded-[10px] border border-border bg-card text-dim transition hover:border-border-h hover:text-fg"
      >
        <AnimatePresence initial={false}>
          <motion.span
            key={theme}
            initial={reduce ? false : { rotate: -90, scale: 0, opacity: 0 }}
            animate={reduce ? { opacity: 1 } : { rotate: 0, scale: 1, opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { rotate: 90, scale: 0, opacity: 0 }}
            transition={{ duration: reduce ? 0 : 0.22, ease: 'easeInOut' }}
            className="absolute grid place-items-center"
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </motion.span>
        </AnimatePresence>
      </button>
    </header>
  )
}
