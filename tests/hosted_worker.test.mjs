import assert from 'node:assert/strict'
import test from 'node:test'

import worker from '../cloudflare/worker.mjs'

function accessToken(payload) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'RS256', kid: 'test' })}.${encode(payload)}.signature`
}

test('rejects requests without an Access assertion', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = () => { throw new Error('origin must not be called') }
  try {
    const response = await worker.fetch(
      new Request('https://jobscope-private.example.workers.dev/api/token'),
      { ORIGIN_URL: 'https://origin.example' },
    )
    assert.equal(response.status, 403)
    assert.equal(response.headers.get('Cache-Control'), 'no-store')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('rejects invalid and recursive origins', async () => {
  for (const origin of [
    '',
    'http://origin.example',
    'https://user@origin.example',
    'https://origin.example/path',
    'https://jobscope-private.example.workers.dev',
  ]) {
    const response = await worker.fetch(
      new Request('https://jobscope-private.example.workers.dev/healthz', {
        headers: { 'Cf-Access-Jwt-Assertion': 'signed-access-token' },
      }),
      { ORIGIN_URL: origin },
    )
    assert.equal(response.status, 503)
  }
})

test('forwards authenticated requests and strips session cookies', async () => {
  const originalFetch = globalThis.fetch
  let forwarded
  globalThis.fetch = async (request) => {
    forwarded = request
    return new Response('proxied', {
      status: 202,
      headers: { 'Set-Cookie': 'origin=private', 'X-Origin': 'jobscope' },
    })
  }
  try {
    const response = await worker.fetch(
      new Request('https://jobscope-private.example.workers.dev/api/automation/tick?dry=1', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Cookie': 'other=value; CF_Authorization=signed.access.token; theme=dark',
          'Origin': 'https://jobscope-private.example.workers.dev',
        },
        body: '{"probe":true}',
      }),
      { ORIGIN_URL: 'https://railway-origin.example' },
    )

    assert.equal(response.status, 202)
    assert.equal(await response.text(), 'proxied')
    assert.equal(response.headers.get('Set-Cookie'), null)
    assert.equal(response.headers.get('X-Origin'), 'jobscope')
    assert.equal(forwarded.url, 'https://railway-origin.example/api/automation/tick?dry=1')
    assert.equal(forwarded.method, 'POST')
    assert.equal(forwarded.headers.get('Cf-Access-Jwt-Assertion'), 'signed.access.token')
    assert.equal(forwarded.headers.get('Cookie'), null)
    assert.equal(forwarded.headers.get('Origin'), 'https://jobscope-private.example.workers.dev')
    assert.equal(await forwarded.text(), '{"probe":true}')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('scopes the configured service token to automation endpoints', async () => {
  const originalFetch = globalThis.fetch
  const clientId = 'automation-client.access'
  const signedToken = accessToken({ common_name: clientId, type: 'app' })
  let forwarded
  globalThis.fetch = async (request) => {
    forwarded = request
    return new Response('proxied')
  }
  try {
    for (const [url, token] of [
      ['https://jobscope-private.example.workers.dev/api/dashboard', signedToken],
      [
        'https://jobscope-private.example.workers.dev/api/automation/status',
        accessToken({ common_name: 'another-client.access', type: 'app' }),
      ],
    ]) {
      const response = await worker.fetch(
        new Request(url, { headers: { 'Cf-Access-Jwt-Assertion': token } }),
        {
          ORIGIN_URL: 'https://railway-origin.example',
          AUTOMATION_CLIENT_ID: clientId,
        },
      )
      assert.equal(response.status, 403)
    }

    const response = await worker.fetch(
      new Request('https://jobscope-private.example.workers.dev/api/automation/status', {
        headers: {
          'Cf-Access-Jwt-Assertion': signedToken,
          'CF-Access-Client-Id': clientId,
          'CF-Access-Client-Secret': 'private', // pragma: allowlist secret
        },
      }),
      {
        ORIGIN_URL: 'https://railway-origin.example',
        AUTOMATION_CLIENT_ID: clientId,
      },
    )

    assert.equal(response.status, 200)
    assert.equal(forwarded.headers.get('Cf-Access-Jwt-Assertion'), signedToken)
    assert.equal(forwarded.headers.get('CF-Access-Client-Id'), null)
    assert.equal(forwarded.headers.get('CF-Access-Client-Secret'), null)
  } finally {
    globalThis.fetch = originalFetch
  }
})