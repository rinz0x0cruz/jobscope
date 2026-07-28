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

test('forwards an authenticated encrypted backup response without buffering policy changes', async () => {
  const originalFetch = globalThis.fetch
  let forwarded
  globalThis.fetch = async (request) => {
    forwarded = request
    return new Response(new Uint8Array([0x50, 0x4b, 0x03, 0x04]), {
      headers: { 'Content-Type': 'application/zip', 'X-Jobscope-Backup-Id': 'backup-id' },
    })
  }
  try {
    const response = await worker.fetch(
      new Request('https://jobscope-automation.example.workers.dev/api/automation/backup', {
        headers: { 'X-Jobscope-Automation': env.AUTOMATION_TOKEN },
      }),
      env,
    )

    assert.equal(response.status, 200)
    assert.equal(response.headers.get('Content-Type'), 'application/zip')
    assert.equal(response.headers.get('Cache-Control'), 'no-store')
    assert.equal(forwarded.url, 'https://railway-origin.example/api/automation/backup')
    assert.equal(forwarded.method, 'GET')
    assert.deepEqual(new Uint8Array(await response.arrayBuffer()), new Uint8Array([0x50, 0x4b, 0x03, 0x04]))
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('forwards only POST for backup retention acknowledgement', async () => {
  const originalFetch = globalThis.fetch
  let forwarded
  globalThis.fetch = async (request) => {
    forwarded = request
    return new Response('{"ok":true}', { headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const wrongMethod = await worker.fetch(
      new Request('https://jobscope-automation.example.workers.dev/api/automation/backup/ack', {
        headers: { 'X-Jobscope-Automation': env.AUTOMATION_TOKEN },
      }),
      env,
    )
    assert.equal(wrongMethod.status, 404)

    const response = await worker.fetch(
      new Request('https://jobscope-automation.example.workers.dev/api/automation/backup/ack', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Jobscope-Automation': env.AUTOMATION_TOKEN,
        },
        body: '{"backup_id":"id","encrypted_sha256":"hash"}',
      }),
      env,
    )
    assert.equal(response.status, 200)
    assert.equal(forwarded.method, 'POST')
    assert.equal(await forwarded.text(), '{"backup_id":"id","encrypted_sha256":"hash"}')
  } finally {
    globalThis.fetch = originalFetch
  }
})

const scheduledEnv = { ...env, WORKER_ORIGIN: 'https://jobscope-automation.example.workers.dev' }

function collector() {
  const pending = []
  return { pending, ctx: { waitUntil: (promise) => pending.push(promise) } }
}

async function runSchedule(cron, values, scheduledTime = 1800000000000) {
  const originalFetch = globalThis.fetch
  const sent = []
  globalThis.fetch = async (request) => {
    sent.push(request)
    return new Response('{"ok":true}', { headers: { 'Content-Type': 'application/json' } })
  }
  const { pending, ctx } = collector()
  try {
    await worker.scheduled({ cron, scheduledTime }, values, ctx)
    await Promise.all(pending)
    return sent
  } finally {
    globalThis.fetch = originalFetch
  }
}

test('rejects any cron pattern outside the allowlist', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = () => { throw new Error('origin must not be called') }
  try {
    for (const cron of ['* * * * *', '0 0 * * *', '', undefined]) {
      await assert.rejects(
        () => worker.scheduled({ cron, scheduledTime: 1800000000000 }, scheduledEnv, collector().ctx),
        /unrecognized cron trigger/,
      )
    }
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('observes a read-only path by default and mutates nothing', async () => {
  for (const values of [scheduledEnv, { ...scheduledEnv, AUTOMATION_MODE: 'observe' }]) {
    const sent = await runSchedule('17 */3 * * *', values)

    assert.equal(sent.length, 1)
    assert.equal(sent[0].url, 'https://railway-origin.example/api/automation/status')
    assert.equal(sent[0].method, 'GET')
    assert.equal(sent[0].headers.get('X-Jobscope-Slot-Time'), null)
    assert.equal(sent[0].headers.get('X-Jobscope-Slot-Period'), null)
  }
})

test('routes each allowlisted cron to its own operation with a stable slot identity', async () => {
  const active = { ...scheduledEnv, AUTOMATION_MODE: 'active' }
  const expected = new Map([
    ['17 */3 * * *', ['https://railway-origin.example/api/automation/refresh', '10800000']],
    ['*/30 * * * *', ['https://railway-origin.example/api/automation/tick', '1800000']],
  ])

  for (const [cron, [url, period]] of expected) {
    const sent = await runSchedule(cron, active)

    assert.equal(sent[0].url, url)
    assert.equal(sent[0].method, 'POST')
    assert.equal(sent[0].headers.get('X-Jobscope-Slot-Time'), '1800000000000')
    assert.equal(sent[0].headers.get('X-Jobscope-Slot-Period'), period)
    assert.equal(sent[0].headers.get('Origin'), scheduledEnv.WORKER_ORIGIN)
    assert.equal(sent[0].headers.get('X-Jobscope-Edge'), env.EDGE_TOKEN)
    assert.equal(await sent[0].text(), '{}')
  }
})

test('a retried slot repeats the identical scheduled time so the backend can deduplicate', async () => {
  const active = { ...scheduledEnv, AUTOMATION_MODE: 'active' }

  const first = await runSchedule('*/30 * * * *', active, 1800000000000)
  const retry = await runSchedule('*/30 * * * *', active, 1800000000000)
  const later = await runSchedule('*/30 * * * *', active, 1800000000000 + 1800000)

  assert.equal(
    first[0].headers.get('X-Jobscope-Slot-Time'),
    retry[0].headers.get('X-Jobscope-Slot-Time'),
  )
  assert.notEqual(
    first[0].headers.get('X-Jobscope-Slot-Time'),
    later[0].headers.get('X-Jobscope-Slot-Time'),
  )
})

test('a failing slot throws so the platform retries the same scheduled time', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => new Response('{"ok":false}', { status: 502 })
  const { pending, ctx } = collector()
  try {
    await worker.scheduled(
      { cron: '17 */3 * * *', scheduledTime: 1800000000000 },
      { ...scheduledEnv, AUTOMATION_MODE: 'active' },
      ctx,
    )
    await assert.rejects(() => Promise.all(pending), /origin returned 502/)
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('a scheduled slot fails closed without a validated origin and worker identity', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = () => { throw new Error('origin must not be called') }
  try {
    for (const values of [
      { ...scheduledEnv, ORIGIN_URL: '' },
      { ...scheduledEnv, ORIGIN_URL: 'http://railway-origin.example' },
      { ...scheduledEnv, WORKER_ORIGIN: '' },
      { ...scheduledEnv, EDGE_TOKEN: 'short' },
      { ...scheduledEnv, AUTOMATION_TOKEN: '' },
    ]) {
      const { pending, ctx } = collector()
      await worker.scheduled({ cron: '17 */3 * * *', scheduledTime: 1800000000000 }, values, ctx)
      await assert.rejects(() => Promise.all(pending), /not configured/)
    }
  } finally {
    globalThis.fetch = originalFetch
  }
})

async function scheduleAgainstStatus(status, values = { ...scheduledEnv, AUTOMATION_MODE: 'active' }) {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => new Response('{"ok":false}', { status })
  const { pending, ctx } = collector()
  try {
    await worker.scheduled({ cron: '17 */3 * * *', scheduledTime: 1800000000000 }, values, ctx)
    return await Promise.all(pending).then(() => null, (error) => error)
  } finally {
    globalThis.fetch = originalFetch
  }
}

test('a deliberate refusal is final and is never retried', async () => {
  // 200 accepted, 200 duplicate/superseded/stale, 409 busy, 503 refused by
  // policy: each is an answer about this slot, so retrying cannot help.
  for (const status of [200, 409, 503]) {
    assert.equal(await scheduleAgainstStatus(status), null)
  }
})

test('a misconfigured slot fails loudly instead of silently doing nothing', async () => {
  for (const status of [400, 401, 403]) {
    const error = await scheduleAgainstStatus(status)
    assert.match(String(error), new RegExp(`rejected the slot: ${status}`))
  }
})

test('an unexpected origin failure retries the same scheduled time', async () => {
  for (const status of [500, 502, 504]) {
    const error = await scheduleAgainstStatus(status)
    assert.match(String(error), new RegExp(`origin returned ${status}`))
  }
})

test('the active mode flag tolerates padding and casing but nothing else', async () => {
  for (const mode of [' active ', 'ACTIVE', 'Active']) {
    const sent = await runSchedule('*/30 * * * *', { ...scheduledEnv, AUTOMATION_MODE: mode })
    assert.equal(sent[0].url, 'https://railway-origin.example/api/automation/tick')
  }
  for (const mode of ['', 'act', 'observe', 'true', '1', undefined]) {
    const sent = await runSchedule('*/30 * * * *', { ...scheduledEnv, AUTOMATION_MODE: mode })
    assert.equal(sent[0].url, 'https://railway-origin.example/api/automation/status')
  }
})

test('a slot without a usable scheduled time is refused before any request', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = () => { throw new Error('origin must not be called') }
  try {
    for (const scheduledTime of [undefined, null, NaN, Infinity, 'soon', -1, 0]) {
      const { pending, ctx } = collector()
      await worker.scheduled(
        { cron: '17 */3 * * *', scheduledTime },
        { ...scheduledEnv, AUTOMATION_MODE: 'active' },
        ctx,
      )
      await assert.rejects(() => Promise.all(pending), /scheduled time/)
    }
  } finally {
    globalThis.fetch = originalFetch
  }
})