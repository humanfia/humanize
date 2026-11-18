import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { daemon, fakeIndexedDB, provider, sleep, until } from './helpers.mjs'

// As much of a browser as the page's modules touch as they load: they are loaded after it is.
const events = new EventTarget()
Object.assign(globalThis, {
  window: globalThis,
  location: { protocol: 'http:', host: 'page', hash: '', origin: 'http://page', search: '' },
  addEventListener: events.addEventListener.bind(events),
  removeEventListener: events.removeEventListener.bind(events),
  dispatchEvent: events.dispatchEvent.bind(events),
  document: Object.assign(new EventTarget(), { hidden: false, documentElement: { dataset: {} } }),
  matchMedia: () => Object.assign(new EventTarget(), { matches: false }),
  requestAnimationFrame: (fn) => setTimeout(fn, 0),
  indexedDB: fakeIndexedDB(),
})

/** A daemon whose host sends this page a terminal's messages, as to one that views it. */
let sub = ''
let peer = null
const served = daemon({
  methods: {
    'epic.attach': (params, to) => {
      sub = `s${served.calls.length}`
      peer = to
      setTimeout(() => to.notify('epic.event', { sub, message: { type: 'welcome', epoch: 'e1', client: 'c', workspace: params.workspace, slot: '' } }))
      return { sub, client: 'c', workspace: params.workspace, slot: '' }
    },
    'env.term.ack': () => ({}),
  },
})
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { follow, hearing } = await import('../../../../src/hmz/web/static/held.js')

after(async () => (await api.client('local')).close())

const acks = () => served.calls.filter((one) => one.method === 'env.term.ack').map((one) => one.params)
const acked = (term) =>
  acks()
    .filter((one) => one.term === term)
    .reduce((sum, one) => sum + one.bytes, 0)
const prints = (term, bytes) => peer.notify('epic.event', { sub, message: { type: 'term', term, data: Buffer.alloc(bytes, 97).toString('base64') } })

test('output of a terminal no panel draws is acknowledged, so that its host keeps reading it', async () => {
  let state = null
  const stop = follow('/w', (now) => (state = now))
  await until(() => state.connected)
  // Left running with no panel on it: more than the host sends unacknowledged, a chunk at a time.
  for (let sent = 0; sent < 20; sent++) prints('t1', 64 * 1024)
  prints('t1', 10)
  await until(() => acked('t1') === 20 * 64 * 1024 + 10)
  assert.ok(acks().every((one) => one.sub === sub))

  // A panel that draws it acknowledges it itself: here it is counted no more.
  const calls = acks().length
  const unhear = hearing('/w', (message) => message.type === 'term' && message.term === 't1')
  prints('t1', 64 * 1024)
  prints('t2', 64 * 1024)
  await until(() => acked('t2') === 64 * 1024)
  await sleep(100)
  assert.equal(acks().length, calls + 1)

  // The panel left, the page still attached: acknowledged here again.
  unhear()
  prints('t1', 5)
  await until(() => acked('t1') === 20 * 64 * 1024 + 15)
  stop()
})
