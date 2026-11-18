import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { daemon, fakeIndexedDB, provider, until } from './helpers.mjs'

/** As much of an element as the face host builds its mount out of. */
class Node {
  constructor(tag) {
    this.tag = tag
    this.style = {}
    this.dataset = {}
    this.kids = []
    this.heard = {}
    // What a frame's document is handed: the message, and the port that came with it.
    this.contentWindow = { posted: [], postMessage: (message, _origin, ports) => this.contentWindow.posted.push({ message, ports }) }
  }
  setAttribute() {}
  removeAttribute() {}
  addEventListener(name, fn) {
    this.heard[name] = fn
  }
  append(...kids) {
    this.kids.push(...kids)
  }
  remove() {}
  dispatchEvent() {}
}

// As much of a browser as the page's modules touch as they load: they are loaded after it is.
const events = new EventTarget()
const frames = []
Object.assign(globalThis, {
  window: globalThis,
  Node,
  location: { protocol: 'http:', host: 'page', hash: '', origin: 'http://page', search: '' },
  addEventListener: events.addEventListener.bind(events),
  removeEventListener: events.removeEventListener.bind(events),
  dispatchEvent: events.dispatchEvent.bind(events),
  document: Object.assign(new EventTarget(), {
    hidden: false,
    documentElement: { dataset: {} },
    head: new Node('head'),
    querySelector: () => null,
    createTextNode: (text) => text,
    createElement: (tag) => {
      const made = new Node(tag)
      if (tag === 'iframe') frames.push(made)
      return made
    },
  }),
  getComputedStyle: () => ({ length: 0, getPropertyValue: () => '' }),
  MutationObserver: class {
    observe() {}
  },
  matchMedia: () => Object.assign(new EventTarget(), { matches: false }),
  requestAnimationFrame: (fn) => setTimeout(fn, 0),
  indexedDB: fakeIndexedDB(),
})

const served = daemon()
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { follow, shownTo } = await import('../../../../src/hmz/web/static/held.js')
const { dropFace, mountFace } = await import('../../../../src/hmz/web/static/faces/host.js')

after(async () => (await api.client('local')).close())

/** Sends a host's record to every page attached, as the daemon's `record` does a line said. */
function record(message) {
  const sent = { seq: served.records.length + 1, run: 1, ...message }
  served.records.push(sent)
  for (const { peer, subs } of served.sessions) for (const [sub, kind] of subs) if (kind === 'epic' && peer.open) peer.notify('epic.event', { sub, message: sent })
}

const shown = (session, text) => ({ type: 'shown', role: 'human', session, context: [{ kind: 'markdown', text }] })

test('a face mounted for a session is handed what the session was shown before it, and after', async () => {
  // The history a page opened late, or loaded again, is told before any card is drawn.
  record(shown('human/1', 'before the first ask'))
  record(shown('human/2', 'to another session'))
  record(shown('human/1', 'between asks'))
  let state = { records: [] }
  const stop = follow('/w', (told) => (state = told))
  await until(() => state.records.length === 3)

  const told = shownTo('/w', 'human/1')
  assert.deepEqual(
    told.map(([block]) => block.text),
    ['before the first ask', 'between asks'],
  )
  assert.deepEqual(shownTo('/w', 'human/3'), [])
  assert.deepEqual(shownTo('/elsewhere', 'human/1'), [])

  // The card of the session's question mounts its face, as asking/card.js does.
  const question = { question: 'q1', run: 1, session: 'human/1', role: 'human', text: 'Ship?', face: { hash: 'ab12', title: 'Review' } }
  mountFace(question, { fetchFace: async () => ({ html: '<p>face</p>', title: 'Review' }), submit: async () => ({ ok: true }), theme: {}, shown: told, where: '/w' })
  const frame = frames.at(-1)
  frame.heard.load()
  await until(() => frame.contentWindow.posted.length === 1)
  const [port] = frame.contentWindow.posted[0].ports
  const heard = []
  port.onmessage = (event) => heard.push(event.data)
  try {
    await until(() => heard.length === 4)
    assert.deepEqual(
      heard.map((message) => message.type),
      ['face', 'ask', 'show', 'show'],
    )
    assert.deepEqual(
      heard.slice(2).map((message) => message.context[0].text),
      ['before the first ask', 'between asks'],
    )

    // What is shown from here on reaches the mounted face once, as it comes.
    record(shown('human/1', 'while asked'))
    await until(() => heard.length === 5)
    await until(() => state.records.length === 4)
    assert.deepEqual(
      heard.slice(2).map((message) => message.context[0].text),
      ['before the first ask', 'between asks', 'while asked'],
    )
  } finally {
    port.close()
    dropFace('human/1', { where: '/w', run: 1 })
    stop()
  }
})
