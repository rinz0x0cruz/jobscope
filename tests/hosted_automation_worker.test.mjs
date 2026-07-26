import assert from 'node:assert/strict'
import test from 'node:test'

import worker from '../cloudflare/automation-worker.mjs'

const env = {
  AUTOMATION_TOKEN: 'a'.repeat(43),
  EDGE_TOKEN: 'e'.repeat(43),
  ORIGIN_URL: 'https://railway-origin.example',
}

test('rejects unknown routes, methods, and invalid credentials', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = () => { throw new Error('origin must not be called') }
  try {
    for (const request of [
      new Request('https://jobscope-automation.example.workers.dev/api/dashboard'),
      new Request('https://jobscope-automation.example.workers.dev/api/automation/status', {
        method: 'POST',
        headers: { 'X-Jobscope-Automation': env.AUTOMATION_TOKEN },
      }),
      new Request('https://jobscope-automation.example.workers.dev/api/automation/status'),
      new Request('https://jobscope-automation.example.workers.dev/api/automation/status', {
        headers: { 'X-Jobscope-Automation': 'wrong' },
      }),
    ]) {
      const response = await worker.fetch(request, env)
      assert.ok([403, 404].includes(response.status))
      assert.equal(response.headers.get('Cache-Control'), 'no-store')
    }
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('forwards only authenticated automation requests with an origin-only token', async () => {
  const originalFetch = globalThis.fetch
  let forwarded
  globalThis.fetch = async (request) => {
    forwarded = request
    return new Response('{"ok":true}', {
      headers: { 'Content-Type': 'application/json', 'Set-Cookie': 'private=value' },
    })
  }
  try {
    const response = await worker.fetch(
      new Request('https://jobscope-automation.example.workers.dev/api/automation/tick', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Cookie': 'private=value',
          'Cf-Access-Jwt-Assertion': 'forged',
          'CF-Access-Client-Id': 'client',
          'CF-Access-Client-Secret': 'secret', // pragma: allowlist secret
          'X-Jobscope-Automation': env.AUTOMATION_TOKEN,
          'X-Jobscope-Edge': 'caller-controlled',
        },
        body: '{}',
      }),
      env,
    )

    assert.equal(response.status, 200)
    assert.equal(response.headers.get('Set-Cookie'), null)
    assert.equal(response.headers.get('Cache-Control'), 'no-store')
    assert.equal(forwarded.url, 'https://railway-origin.example/api/automation/tick')
    assert.equal(forwarded.method, 'POST')
    assert.equal(forwarded.headers.get('Origin'), 'https://jobscope-automation.example.workers.dev')
    assert.equal(forwarded.headers.get('X-Jobscope-Automation'), env.AUTOMATION_TOKEN)
    assert.equal(forwarded.headers.get('X-Jobscope-Edge'), env.EDGE_TOKEN)
    assert.equal(forwarded.headers.get('Cookie'), null)
    assert.equal(forwarded.headers.get('Cf-Access-Jwt-Assertion'), null)
    assert.equal(forwarded.headers.get('CF-Access-Client-Id'), null)
    assert.equal(forwarded.headers.get('CF-Access-Client-Secret'), null)
    assert.equal(await forwarded.text(), '{}')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('fails closed without valid origin and edge secrets', async () => {
  for (const values of [
    { ...env, ORIGIN_URL: '' },
    { ...env, ORIGIN_URL: 'http://railway-origin.example' },
    { ...env, ORIGIN_URL: 'https://jobscope-automation.example.workers.dev' },
    { ...env, EDGE_TOKEN: 'short' },
  ]) {
    const response = await worker.fetch(
      new Request('https://jobscope-automation.example.workers.dev/api/automation/status', {
        headers: { 'X-Jobscope-Automation': env.AUTOMATION_TOKEN },
      }),
      values,
    )
    assert.equal(response.status, 503)
  }
})