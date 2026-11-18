import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import { easytier } from '../../../../src/hmz/web/static/rpc/easytier.js'

/** Local, answering the EasyTier methods from the entries it keeps, every call in `calls`. */
function daemon(networks = []) {
  const calls = []
  return { calls, call: async (method, params = {}) => (calls.push([method, params]), method === 'easytier.list' ? { networks } : {}) }
}

/** The desktop application, answering its EasyTier commands, every one invoked in `invoked`. */
function application(entries = []) {
  const invoked = []
  return { invoked, invoke: async (command, args) => (invoked.push([command, args]), command === 'easytier_list' ? entries : null) }
}

test('in a browser the entry of a P2P daemon is written to Local alone, and read from it', async () => {
  const local = daemon([{ name: 'home', nodes: ['tcp://n:1'], secret: true }])
  const kept = easytier(local.call, undefined)
  await kept.set({ name: 'home', secret: 's'.repeat(16), nodes: ['tcp://n:1'] })
  assert.deepEqual(await kept.list(), [{ name: 'home', nodes: ['tcp://n:1'], secret: true }])
  await kept.remove('old')
  assert.deepEqual(local.calls, [['easytier.set', { name: 'home', secret: 's'.repeat(16), nodes: ['tcp://n:1'] }], ['easytier.list', {}], ['easytier.remove', { name: 'old' }]])
})

test('in the desktop application the entry is written to the app too, whose pipes open the route with it', async () => {
  const local = daemon([{ name: 'home', nodes: ['tcp://stale:1'], secret: true }])
  const app = application([{ name: 'home', nodes: ['tcp://n:1'], secret: true }])
  const kept = easytier(local.call, app)
  await kept.set({ name: 'home', secret: 's'.repeat(16), nodes: ['tcp://n:1'] })
  // No secret given: the app keeps the one written.
  await kept.set({ name: 'home', nodes: ['tcp://n:2'] })
  // What the app opens the route with is what the form shows.
  assert.deepEqual(await kept.list(), [{ name: 'home', nodes: ['tcp://n:1'], secret: true }])
  await kept.remove('old')
  assert.deepEqual(app.invoked, [
    ['easytier_set', { name: 'home', secret: 's'.repeat(16), nodes: ['tcp://n:1'] }],
    ['easytier_set', { name: 'home', nodes: ['tcp://n:2'] }],
    ['easytier_list', undefined],
    ['easytier_remove', { name: 'old' }],
  ])
  assert.deepEqual(local.calls.map(([method]) => method), ['easytier.set', 'easytier.set', 'easytier.remove'])
})

test('what the app refuses is said as an error', async () => {
  const kept = easytier(daemon().call, { invoke: () => Promise.reject('A secret must be at least 16 bytes.') })
  await assert.rejects(kept.set({ name: 'home', secret: 'short', nodes: ['tcp://n:1'] }), new Error('A secret must be at least 16 bytes.'))
})

test('the daemons form keeps its EasyTier entries through both, never by Local alone', () => {
  const view = readFileSync(new URL('../../../../src/hmz/web/static/views/settings/daemons.js', import.meta.url), 'utf8')
  // Not `assert.match`, which would say the whole file where it fails.
  assert.ok(view.includes("from '../../rpc/easytier.js'"), 'the form does not write through rpc/easytier.js')
  assert.ok(!/'easytier\.(list|set|remove)'/.test(view), 'the form asks Local for an entry itself')
})
