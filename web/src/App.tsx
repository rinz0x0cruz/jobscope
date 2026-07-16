import { dashboard, encryptedSite } from '@/data'
import { useSearchState } from '@/hooks/useSearchState'
import { AuthGate } from '@/app/AuthGate'
import { ShellV2 } from '@/app/ShellV2'

// Apply the persisted light/dark theme (light-first) before first render. The
// index.html anti-FOUC script sets the same class from the 'jobscope-theme' key;
// this keeps dev (uncached HTML) in sync and defaults to light when unset.
if (typeof document !== 'undefined') {
  let stored: string | null
  try {
    stored = localStorage.getItem('jobscope-theme')
  } catch {
    stored = null
  }
  const el = document.documentElement
  el.classList.remove('dark', 'light')
  el.classList.add(stored === 'dark' ? 'dark' : 'light')
}

/**
 * Application root. The whole app lives behind {@link AuthGate}: a local
 * un-redacted build renders straight through, while the published (empty) build
 * shows the passphrase lock until the encrypted payload is unlocked in-browser.
 * The unlocked (or baked) data is handed to the Feed + Reader shell.
 */
export default function App() {
  const { state, set } = useSearchState()
  return (
    <AuthGate baked={dashboard} encrypted={encryptedSite}>
      {(data, lock) => (
        <ShellV2
          data={data}
          state={state}
          onStateChange={set}
          onLock={lock}
        />
      )}
    </AuthGate>
  )
}
