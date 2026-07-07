import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Lock, Unlock, X } from 'lucide-react'
import type { DashboardData, EncRef } from '@/lib/schema'
import { UnlockForm } from '@/components/UnlockForm'

/**
 * Header lock button. When the build is redacted (an encrypted blob is present),
 * it opens a passphrase dialog that swaps in the full un-redacted data; once
 * unlocked it turns into a re-lock button that restores the public view.
 */
export function UnlockControl({
  encBlob,
  unlocked,
  onUnlock,
  onLock,
}: {
  encBlob: EncRef
  unlocked: boolean
  onUnlock: (data: DashboardData) => void
  onLock: () => void
}) {
  const [open, setOpen] = useState(false)

  if (unlocked) {
    return (
      <button
        type="button"
        onClick={onLock}
        aria-label="Lock the dashboard (hide un-redacted data)"
        title="Unlocked — click to re-lock"
        className="grid h-10 w-10 place-items-center rounded-[12px] border border-border bg-card transition hover:border-border-h"
        style={{ color: 'var(--good)' }}
      >
        <Unlock size={16} />
      </button>
    )
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          aria-label="Unlock the full dashboard"
          title="Unlock the full dashboard"
          className="grid h-10 w-10 place-items-center rounded-[12px] border border-border bg-card text-dim transition hover:border-border-h hover:text-fg"
        >
          <Lock size={16} />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,26rem)] -translate-x-1/2 -translate-y-1/2 rounded-[16px] border border-border bg-bg2 p-6 shadow-2xl outline-none"
        >
          <div className="mb-1 flex items-center justify-between">
            <Dialog.Title className="text-sm font-semibold">Unlock</Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              className="grid h-7 w-7 place-items-center rounded-lg border border-border text-dim transition hover:border-border-h hover:text-fg"
            >
              <X size={14} />
            </Dialog.Close>
          </div>
          <UnlockForm
            blob={encBlob}
            onUnlock={(d) => {
              setOpen(false)
              onUnlock(d)
            }}
          />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
