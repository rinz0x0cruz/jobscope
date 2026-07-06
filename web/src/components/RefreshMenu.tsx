import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Check, ChevronDown, DownloadCloud, KeyRound, MailSearch, RefreshCw, Unplug } from 'lucide-react'
import { GH_TOKEN_KEY, hasGitHubToken, pullLatestData, scanCooldownRemaining, scanNewMail } from '@/lib/refresh'

interface Props {
  /** Pre-formatted "generated" timestamp shown in the popover footer. */
  updated: string
}

const mmss = (ms: number) => {
  const s = Math.ceil(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** Header control to refresh the dashboard: a primary button pulls the freshest
 *  published results into the PWA, and a caret opens on-demand scan + token
 *  options so you don't have to wait for the scheduled Action. */
export function RefreshMenu({ updated }: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [connected, setConnected] = useState(hasGitHubToken)
  const [cooldown, setCooldown] = useState(0)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const tick = () => setCooldown(scanCooldownRemaining())
    tick()
    const t = window.setInterval(tick, 1000)
    return () => window.clearInterval(t)
  }, [open])

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const pull = async () => {
    setBusy(true)
    setOpen(false)
    await pullLatestData() // reloads on new data; resets on the fresh page load
    setBusy(false)
  }

  const scan = () => {
    setOpen(false)
    void scanNewMail()
  }

  const connect = () => {
    const token = window.prompt(
      'Paste a fine-grained GitHub token (Actions: Read and write on ' +
        'rinz0x0cruz/jobscope) to enable one-tap scans.\n\n' +
        'Stored only in this browser — sent to github.com and nowhere else.',
    )
    if (token && token.trim()) {
      try {
        localStorage.setItem(GH_TOKEN_KEY, token.trim())
        setConnected(true)
      } catch {
        /* localStorage unavailable — ignore */
      }
    }
  }

  const disconnect = () => {
    try {
      localStorage.removeItem(GH_TOKEN_KEY)
    } catch {
      /* ignore */
    }
    setConnected(false)
  }

  return (
    <div ref={ref} className="relative flex">
      <button
        type="button"
        onClick={pull}
        aria-label="Refresh — pull the latest results"
        title="Pull the latest published results"
        className="group flex h-10 items-center gap-2 rounded-l-[12px] border border-border bg-card px-3 text-dim transition hover:border-border-h hover:text-fg"
      >
        <RefreshCw
          size={15}
          className={`opacity-80 transition group-hover:opacity-100 ${busy ? 'animate-spin' : ''}`}
        />
        <span className="hidden text-[12.5px] font-medium sm:inline">Refresh</span>
      </button>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="More refresh options"
        aria-expanded={open}
        className="grid h-10 w-8 place-items-center rounded-r-[12px] border border-l-0 border-border bg-card text-dim transition hover:border-border-h hover:text-fg"
      >
        <ChevronDown size={14} className={`transition ${open ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.16, ease: 'easeOut' }}
            className="absolute right-0 top-full z-30 mt-2 w-72 overflow-hidden rounded-[14px] border border-border bg-card shadow-[var(--shadow)]"
          >
            <div className="p-1.5">
              <button
                type="button"
                onClick={scan}
                disabled={cooldown > 0}
                className="flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left transition hover:bg-card-h disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
              >
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[9px] border border-border text-accent">
                  <MailSearch size={16} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-semibold text-fg">Scan new mail</span>
                  <span className="block text-[11px] text-mute">
                    {cooldown > 0
                      ? `On cooldown — ${mmss(cooldown)}`
                      : connected
                        ? 'Runs the mailbox scan (~2–3 min)'
                        : 'Opens GitHub to run the scan'}
                  </span>
                </span>
              </button>
              <button
                type="button"
                onClick={pull}
                className="flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left transition hover:bg-card-h"
              >
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[9px] border border-border text-cool">
                  <DownloadCloud size={16} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-semibold text-fg">Pull latest data</span>
                  <span className="block text-[11px] text-mute">
                    Reload with the freshest published results
                  </span>
                </span>
              </button>
            </div>
            <div className="flex items-center justify-between gap-2 border-t border-border px-3 py-2.5">
              <span className="min-w-0 truncate text-[11px] text-mute">Updated {updated}</span>
              {connected ? (
                <button
                  type="button"
                  onClick={disconnect}
                  className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-dim transition hover:text-hot"
                >
                  <Unplug size={12} /> Disconnect
                </button>
              ) : (
                <button
                  type="button"
                  onClick={connect}
                  className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-dim transition hover:text-fg"
                >
                  <KeyRound size={12} /> 1-tap scan
                </button>
              )}
            </div>
            {connected && (
              <div className="flex items-center gap-1.5 border-t border-border bg-bg2/60 px-3 py-1.5 text-[10px] text-signal">
                <Check size={11} /> Token connected — scans run instantly
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
