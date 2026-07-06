import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { scanNewMail } from '@/lib/refresh'

/** Single header action: rescan Gmail for new application results. Delegates to
 *  scanNewMail (throttle-safe: client cooldown + run de-dupe), which dispatches
 *  the refresh Action, polls it to completion, then offers a one-tap pull of the
 *  fresh data. With no token stored it opens GitHub's Run-workflow page instead. */
export function RefreshButton() {
  const [busy, setBusy] = useState(false)

  const onClick = async () => {
    if (busy) return
    setBusy(true)
    try {
      await scanNewMail()
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Refresh — rescan Gmail for new results"
      title="Rescan Gmail (inbox + junk) for new application emails"
      className="group flex h-10 items-center gap-2 rounded-[12px] border border-border bg-card px-3 text-dim transition hover:border-border-h hover:text-fg"
    >
      <RefreshCw
        size={15}
        className={`opacity-80 transition group-hover:opacity-100 ${busy ? 'animate-spin' : ''}`}
      />
      <span className="hidden text-[12.5px] font-medium sm:inline">Refresh</span>
    </button>
  )
}
