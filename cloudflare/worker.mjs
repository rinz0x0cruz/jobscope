const ACCESS_HEADER = 'Cf-Access-Jwt-Assertion'

function cookieValue(header, name) {
  for (const part of (header || '').split(';')) {
    const [key, ...value] = part.trim().split('=')
    if (key === name && value.length) return value.join('=')
  }
  return ''
}

function serviceTokenCommonName(token) {
  try {
    const encoded = token.split('.')[1]
    if (!encoded) return ''
    const normalized = encoded.replaceAll('-', '+').replaceAll('_', '/')
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
    const payload = JSON.parse(atob(padded))
    return typeof payload.common_name === 'string' ? payload.common_name : ''
  } catch {
    return ''
  }
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
    const accessToken = request.headers.get(ACCESS_HEADER)
      || cookieValue(request.headers.get('Cookie'), 'CF_Authorization')
    if (!accessToken) return denied(403, 'forbidden')
    const incoming = new URL(request.url)
    const serviceToken = serviceTokenCommonName(accessToken)
    if (serviceToken && (
      !env.AUTOMATION_CLIENT_ID
      || serviceToken !== env.AUTOMATION_CLIENT_ID
      || !incoming.pathname.startsWith('/api/automation/')
    )) return denied(403, 'forbidden')
    const origin = originUrl(env.ORIGIN_URL, request.url)
    if (!origin) return denied(503, 'private origin is not configured')

    origin.pathname = incoming.pathname
    origin.search = incoming.search
    const headers = new Headers(request.headers)
    headers.delete('Cookie')
    headers.delete('Host')
    headers.delete('CF-Access-Client-Id')
    headers.delete('CF-Access-Client-Secret')
    headers.set(ACCESS_HEADER, accessToken)

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