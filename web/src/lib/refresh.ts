import { toast } from 'sonner'

// The live dashboard is a static build served from GitHub Pages; new results are
// produced by the `refresh.yml` Action (scan mailbox -> rescore -> republish).
// These helpers let the UI (a) pull the freshest published build into the PWA
// and (b) kick that Action on demand instead of waiting for the 3-hour cron.
const OWNER = 'rinz0x0cruz'
const REPO = 'jobscope'
const WORKFLOW = 'refresh.yml'
const REF = 'main'
const WORKFLOW_PAGE = `https://github.com/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}`

/** localStorage key for an optional fine-grained GitHub PAT (Actions: write on
 *  this one repo) that enables one-tap scans. Kept only in this browser. */
export const GH_TOKEN_KEY = 'jobscope-gh-token'

export function hasGitHubToken(): boolean {
  try {
    return !!localStorage.getItem(GH_TOKEN_KEY)?.trim()
  } catch {
    return false
  }
}

function readToken(): string | null {
  try {
    return localStorage.getItem(GH_TOKEN_KEY)?.trim() || null
  } catch {
    return null
  }
}

/** Ask the service worker for the newest precache, then reload so the freshly
 *  published data + assets take over. Falls back to a plain reload when there's
 *  no SW (e.g. `file://` or a dev server). */
export async function pullLatestData(): Promise<void> {
  const id = toast.loading('Checking for new results…')
  let done = false
  const reload = () => {
    if (done) return
    done = true
    window.location.reload()
  }
  try {
    if ('serviceWorker' in navigator) {
      const reg = await navigator.serviceWorker.getRegistration()
      if (reg) {
        // If a newer worker activates, `controllerchange` fires -> reload with
        // fresh data. Otherwise the grace timeout reloads to re-fetch anyway.
        navigator.serviceWorker.addEventListener('controllerchange', reload)
        await reg.update()
        reg.waiting?.postMessage({ type: 'SKIP_WAITING' })
        window.setTimeout(reload, 1200)
        return
      }
    }
  } catch {
    /* fall through to a plain reload */
  }
  toast.dismiss(id)
  reload()
}

/** Trigger the mailbox-scan Action. With a stored token this POSTs
 *  `workflow_dispatch` directly; otherwise it opens GitHub's Run-workflow page
 *  (works from the GitHub mobile app too) so no secret is ever required. */
export async function scanNewMail(): Promise<void> {
  const token = readToken()
  if (!token) {
    window.open(WORKFLOW_PAGE, '_blank', 'noreferrer')
    toast('Opening GitHub — tap “Run workflow” to scan new mail.', {
      description: 'New results land in ~2–3 min. Then hit Refresh here.',
    })
    return
  }
  const id = toast.loading('Starting mailbox scan…')
  try {
    const res = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: 'POST',
        headers: {
          Accept: 'application/vnd.github+json',
          Authorization: `Bearer ${token}`,
          'X-GitHub-Api-Version': '2022-11-28',
        },
        body: JSON.stringify({ ref: REF }),
      },
    )
    toast.dismiss(id)
    if (res.status === 204) {
      toast.success('Mailbox scan started', {
        description: 'New results in ~2–3 min. Then hit Refresh to pull them.',
      })
    } else if (res.status === 401 || res.status === 403) {
      toast.error('GitHub rejected the token', {
        description: 'Reconnect a fine-grained token with Actions: write.',
      })
    } else {
      toast.error(`Could not start the scan (HTTP ${res.status})`)
    }
  } catch {
    toast.dismiss(id)
    toast.error('Network error — could not reach GitHub.')
  }
}
