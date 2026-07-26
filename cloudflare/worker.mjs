const ACCESS_HEADER = 'Cf-Access-Jwt-Assertion'

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

export default {
  async fetch(request, env) {
    if (!request.headers.get(ACCESS_HEADER)) return denied(403, 'forbidden')
    const origin = originUrl(env.ORIGIN_URL, request.url)
    if (!origin) return denied(503, 'private origin is not configured')

    const incoming = new URL(request.url)
    origin.pathname = incoming.pathname
    origin.search = incoming.search
    const headers = new Headers(request.headers)
    headers.delete('Cookie')
    headers.delete('Host')

    const init = {
      method: request.method,
      headers,
      redirect: 'manual',
    }
    if (!['GET', 'HEAD'].includes(request.method)) init.body = await request.arrayBuffer()
    const response = await fetch(new Request(origin, init))
    const responseHeaders = new Headers(response.headers)
    responseHeaders.delete('Set-Cookie')
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    })
  },
}