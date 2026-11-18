import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { daemon, fakeIndexedDB, provider, until } from './helpers.mjs'

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

/** A daemon with one CLI whose account lists its models only once it is asked for them. */
let asked = false
const served = daemon({
  methods: {
    'flows.backends': () => ({ clis: { claude: { accounts: [{ name: '', asked, models: asked ? [{ name: 'claude-haiku-4-5', efforts: [] }] : [] }] } } }),
    'accounts.models': () => {
      asked = true
      return {}
    },
  },
})
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { agentChoice, anyCli, readBackends } = await import('../../../../src/hmz/web/static/pickers.js')

after(async () => (await api.client('local')).close())

test('a choice that settles on the first model an account turns out to run is told as changed', async () => {
  await readBackends('/w')
  let told = 0
  const picked = agentChoice(anyCli('assistant'), '', () => {}, { changed: () => told++ })
  // As it is made nothing is told: whoever made it reads it next.
  picked.again()
  assert.equal(picked.value(), '')
  assert.equal(told, 0)
  // The CLI is asked what it runs, and the first model it answers is chosen with nobody picking.
  await until(() => picked.value() === 'claude/claude-haiku-4-5')
  assert.equal(told, 1)
  // Read again with nothing new, nothing is told; left, it hears no more.
  await readBackends('/w')
  assert.equal(told, 1)
  picked.leave()
})
