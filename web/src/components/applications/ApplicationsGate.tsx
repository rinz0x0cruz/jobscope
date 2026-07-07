import type { DashboardData, EncRef } from '@/lib/schema'
import { UnlockForm } from '@/components/UnlockForm'

/**
 * Passphrase gate shown in the Applications tab when the build is locked. The
 * crypto + full-payload swap live in lib/unlock + UnlockForm; this just frames
 * the shared form inside a card in the tab.
 */
export function ApplicationsGate({ blob, onUnlock }: { blob: EncRef; onUnlock: (data: DashboardData) => void }) {
  return (
    <div className="grid min-h-40 place-items-center rounded-[14px] border border-border bg-card p-8">
      <div className="w-full max-w-sm">
        <UnlockForm blob={blob} onUnlock={onUnlock} />
      </div>
    </div>
  )
}
