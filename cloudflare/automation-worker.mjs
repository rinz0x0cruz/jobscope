const AUTOMATION_HEADER = 'X-Jobscope-Automation'
const EDGE_HEADER = 'X-Jobscope-Edge'
const ROUTES = new Map([
  ['/api/automation/status', 'GET'],
  ['/api/automation/snapshot', 'GET'],
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
    const incoming = new URL(requestUrl)
    if (origin.protocol !== 'https:' || origin.username || origin.password) return null
    if ((origin.pathname && origin.pathname !== '/') || origin.search || origin.hash) return null
    if (origin.origin === incoming.origin) return null
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

export default {
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