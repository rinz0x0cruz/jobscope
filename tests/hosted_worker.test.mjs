import assert from 'node:assert/strict'
import test from 'node:test'

import worker from '../cloudflare/worker.mjs'

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