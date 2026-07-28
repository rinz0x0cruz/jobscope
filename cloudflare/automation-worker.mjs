const AUTOMATION_HEADER = 'X-Jobscope-Automation'
const EDGE_HEADER = 'X-Jobscope-Edge'
const SLOT_TIME_HEADER = 'X-Jobscope-Slot-Time'
const SLOT_PERIOD_HEADER = 'X-Jobscope-Slot-Period'
const STATUS_PATH = '/api/automation/status'
// Only these exact patterns may drive mutation. An unrecognized cron is a
// configuration error and must fail loudly rather than pick a default.
const CRON_OPERATIONS = new Map([
  ['17 */3 * * *', { path: '/api/automation/refresh', periodMs: 3 * 60 * 60 * 1000 }],
  ['*/30 * * * *', { path: '/api/automation/tick', periodMs: 30 * 60 * 1000 }],
])
const ROUTES = new Map([
  ['/api/automation/status', 'GET'],
  ['/api/automation/snapshot', 'GET'],
  ['/api/automation/backup', 'GET'],
  ['/api/automation/backup/ack', 'POST'],
  ['/api/automation/refresh', 'POST'],
  ['/api/automation/tick', 'POST'],
])

function denied(status, message) {
  return new Response(JSON.stringify({ ok: false, error: message }), {
    status,
    headers: {
      'Cache-Control': 'no-store',
      'Content-Type': 'application/json',
      'X-Content-Type-Options': 'nosniff',
    },
  })
}

function originUrl(value, requestUrl) {
  try {
    const origin = new URL(value || '')
    if (origin.protocol !== 'https:' || origin.username || origin.password) return null
    if ((origin.pathname && origin.pathname !== '/') || origin.search || origin.hash) return null
    if (requestUrl && origin.origin === new URL(requestUrl).origin) return null
    return origin
  } catch {
    return null
  }
}

async function secretsMatch(supplied, expected) {
  if (!supplied || !expected) return false
  const encoder = new TextEncoder()
  const [left, right] = await Promise.all([
    globalThis.crypto.subtle.digest('SHA-256', encoder.encode(supplied)),
    globalThis.crypto.subtle.digest('SHA-256', encoder.encode(expected)),
  ])
  const leftBytes = new Uint8Array(left)
  const rightBytes = new Uint8Array(right)
  let different = 0
  for (let index = 0; index < leftBytes.length; index += 1) {
    different |= leftBytes[index] ^ rightBytes[index]
  }
  return different === 0
}

async function runScheduled(job, controller, env) {
  if (!env.AUTOMATION_TOKEN) throw new Error('automation token is not configured')
  if (!env.EDGE_TOKEN || env.EDGE_TOKEN.length < 32) {
    throw new Error('private origin is not configured')
  }
  const origin = originUrl(env.ORIGIN_URL)
  const self = originUrl(env.WORKER_ORIGIN)
  if (!origin || !self) throw new Error('private origin is not configured')
  if (!Number.isFinite(controller.scheduledTime) || controller.scheduledTime <= 0) {
    throw new Error(`unusable scheduled time: ${controller.scheduledTime}`)
  }

  // Observe-only is the default: the schedule proves itself against a read-only
  // path before it is ever allowed to mutate state.
  const active = String(env.AUTOMATION_MODE || 'observe').trim().toLowerCase() === 'active'
  origin.pathname = active ? job.path : STATUS_PATH
  const headers = new Headers({
    [AUTOMATION_HEADER]: env.AUTOMATION_TOKEN,
    [EDGE_HEADER]: env.EDGE_TOKEN,
    'Origin': self.origin,
  })
  const init = { method: active ? 'POST' : 'GET', headers, redirect: 'manual' }
  if (active) {
    // Identity is the scheduled instant itself, so a transport retry of this
    // same slot is deduplicated by the backend instead of running twice.
    headers.set('Content-Type', 'application/json')
    headers.set(SLOT_TIME_HEADER, String(controller.scheduledTime))
    headers.set(SLOT_PERIOD_HEADER, String(job.periodMs))
    init.body = '{}'
  }
  const response = await fetch(new Request(origin, init))
  // A rejected slot means this Worker and the backend disagree about identity
  // or credentials. Retrying cannot fix that, so surface it instead.
  if ([400, 401, 403].includes(response.status)) {
    throw new Error(`origin rejected the slot: ${response.status}`)
  }
  // 503 is a deliberate refusal (kill switch, recovery mode, backup required):
  // final for this slot. Any other 5xx is a fault worth retrying, and the retry
  // reuses this same scheduled time.
  if (response.status >= 500 && response.status !== 503) {
    throw new Error(`origin returned ${response.status}`)
  }
  return response.status
}

export default {
  async scheduled(controller, env, ctx) {
    const job = CRON_OPERATIONS.get(controller.cron)
    if (!job) throw new Error(`unrecognized cron trigger: ${controller.cron}`)
    ctx.waitUntil(runScheduled(job, controller, env))
  },

  async fetch(request, env) {
    const incoming = new URL(request.url)
    const method = ROUTES.get(incoming.pathname)
    if (!method || request.method !== method) return denied(404, 'not found')
    if (!(await secretsMatch(request.headers.get(AUTOMATION_HEADER), env.AUTOMATION_TOKEN))) {
      return denied(403, 'forbidden')
    }
    if (!env.EDGE_TOKEN || env.EDGE_TOKEN.length < 32) {
      return denied(503, 'private origin is not configured')
    }
    const origin = originUrl(env.ORIGIN_URL, request.url)
    if (!origin) return denied(503, 'private origin is not configured')

    origin.pathname = incoming.pathname
    origin.search = incoming.search
    const headers = new Headers(request.headers)
    headers.delete('Cookie')
    headers.delete('Host')
    headers.delete('Cf-Access-Jwt-Assertion')
    headers.delete('CF-Access-Client-Id')
    headers.delete('CF-Access-Client-Secret')
    headers.set('Origin', incoming.origin)
    headers.set(EDGE_HEADER, env.EDGE_TOKEN)

    const init = { method: request.method, headers, redirect: 'manual' }
    if (request.method === 'POST') init.body = await request.arrayBuffer()
    const response = await fetch(new Request(origin, init))
    const responseHeaders = new Headers(response.headers)
    responseHeaders.delete('Set-Cookie')
    responseHeaders.set('Cache-Control', 'no-store')
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    })
  },
}