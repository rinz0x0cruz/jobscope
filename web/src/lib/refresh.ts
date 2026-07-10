import { toast } from 'sonner'

// The live dashboard is a static build served from GitHub Pages; new results are
// produced by the `refresh.yml` Action (scan mailbox -> rescore -> republish).
// These helpers let the UI (a) pull the freshest published build into the PWA
// and (b) kick that Action on demand instead of waiting for the 3-hour cron.
const OWNER = 'rinz0x0cruz'
const REPO = 'jobscope'
const WORKFLOW = 'refresh.yml'
const REF = 'main'
const API = `https://api.github.com/repos/${OWNER}/${REPO}`
const WORKFLOW_PAGE = `https://github.com/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}`

/** localStorage key for an optional fine-grained GitHub PAT (Actions: write on
 *  this one repo) that enables one-tap scans. Kept only in this browser. */
export const GH_TOKEN_KEY = 'jobscope-gh-token'

const SCAN_AT_KEY = 'jobscope-scan-at'
/** Minimum spacing between manual scans; the scheduled Action already runs
 *  every 3h, so on-demand scans just need to avoid stacking runs. */
export const SCAN_COOLDOWN_MS = 10 * 60 * 1000

export function hasGitHubToken(): boolean {
  try {
    return !!localStorage.getItem(GH_TOKEN_KEY)?.trim()
  } catch {
    return false
  }
}

/** Prompt for and store a fine-grained PAT (client-only) for 1-tap rescans. */
export function connectToken(): void {
  const token = window.prompt(
    'Paste a fine-grained GitHub token (Actions: Read and write on ' +
      'rinz0x0cruz/jobscope) for 1-tap rescans.\n\n' +
      'Stored only in this browser — sent to github.com and nowhere else.',
  )
  if (!token || !token.trim()) return
  try {
    localStorage.setItem(GH_TOKEN_KEY, token.trim())
    toast.success('GitHub token connected', {
      description: 'Refresh now dispatches the rescan directly.',
    })
  } catch {
    toast.error('Could not save the token in this browser.')
  }
}

export function disconnectToken(): void {
  try {
    localStorage.removeItem(GH_TOKEN_KEY)
  } catch {
    /* ignore */
  }
  toast('GitHub token removed')
}

function readToken(): string | null {
  try {
    return localStorage.getItem(GH_TOKEN_KEY)?.trim() || null
  } catch {
    return null
  }
}

/** ms remaining before another manual scan is allowed (0 = ready now). */
export function scanCooldownRemaining(): number {
  try {
    const at = Number(localStorage.getItem(SCAN_AT_KEY) || 0)
    return at ? Math.max(0, at + SCAN_COOLDOWN_MS - Date.now()) : 0
  } catch {
    return 0
  }
}

function markScanned(): void {
  try {
    localStorage.setItem(SCAN_AT_KEY, String(Date.now()))
  } catch {
    /* ignore */
  }
}

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms))

function ghHeaders(token: string): HeadersInit {
  return {
    Accept: 'application/vnd.github+json',
    Authorization: `Bearer ${token}`,
    'X-GitHub-Api-Version': '2022-11-28',
  }
}

interface WorkflowRun {
  status: string
  conclusion: string | null
}

/** Newest runs of the refresh workflow (needs the token's Actions: read). */
async function latestRuns(token: string, perPage = 3): Promise<WorkflowRun[]> {
  const res = await fetch(`${API}/actions/workflows/${WORKFLOW}/runs?per_page=${perPage}`, {
    headers: ghHeaders(token),
  })
  if (!res.ok) throw new Error(`runs ${res.status}`)
  const data = (await res.json()) as { workflow_runs?: WorkflowRun[] }
  return data.workflow_runs ?? []
}

const isActiveRun = (r: WorkflowRun) => r.status === 'queued' || r.status === 'in_progress'

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

/** Trigger the mailbox-scan Action, safely. Enforces a client cooldown and
 *  de-dupes against an already-running scan so rapid taps never stack runs.
 *  With a stored token it POSTs `workflow_dispatch` (and polls to completion);
 *  otherwise it opens GitHub's Run-workflow page — no secret ever required. */
export async function scanNewMail(): Promise<void> {
  const remaining = scanCooldownRemaining()
  if (remaining > 0) {
    toast('Scan on cooldown', {
      description: `Try again in ${fmtDuration(remaining)}. Auto-refresh still runs every 3h.`,
    })
    return
  }

  const token = readToken()
  if (!token) {
    window.open(WORKFLOW_PAGE, '_blank', 'noreferrer')
    markScanned()
    toast('Opening GitHub — tap “Run workflow” to scan new mail.', {
      description: 'New results land in ~2–3 min. Then hit Refresh here.',
    })
    return
  }

  const id = toast.loading('Checking for a running scan…')
  try {
    // De-dupe: never stack a scan on top of one already queued/running.
    const runs = await latestRuns(token)
    if (runs.some(isActiveRun)) {
      toast.dismiss(id)
      markScanned()
      toast('A scan is already running', {
        description: 'Hang tight — I’ll nudge you when results are ready.',
      })
      void pollUntilDone(token)
      return
    }

    const res = await fetch(`${API}/actions/workflows/${WORKFLOW}/dispatches`, {
      method: 'POST',
      headers: ghHeaders(token),
      body: JSON.stringify({ ref: REF }),
    })
    toast.dismiss(id)
    if (res.status === 204) {
      markScanned()
      toast.success('Mailbox scan started', {
        description: 'Scanning ~2–3 min. I’ll nudge you when it’s ready.',
      })
      void pollUntilDone(token)
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

/** Poll the newest run to completion, then offer a one-tap pull. Rate-limit
 *  friendly: a short head start, then ~12s spacing, capped at ~6 min. */
async function pollUntilDone(token: string): Promise<void> {
  const deadline = Date.now() + 6 * 60 * 1000
  await sleep(6000)
  while (Date.now() < deadline) {
    try {
      const [run] = await latestRuns(token, 1)
      if (run && !isActiveRun(run)) {
        if (run.conclusion === 'success') {
          toast.success('Scan complete — new results ready', {
            description: 'Give the deploy a few seconds, then pull the latest.',
            action: { label: 'Pull latest', onClick: () => void pullLatestData() },
            duration: 15000,
          })
        } else {
          toast.error('Scan finished with errors', {
            description: 'Check the Action log on GitHub.',
          })
        }
        return
      }
    } catch {
      /* transient network/API hiccup — keep polling */
    }
    await sleep(12000)
  }
}

function fmtDuration(ms: number): string {
  const m = Math.ceil(ms / 60000)
  return m <= 1 ? '1 min' : `${m} min`
}
