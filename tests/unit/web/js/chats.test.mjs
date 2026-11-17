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

/**
 * A daemon serving chats: `chat.start` mints a slot for `chat:`, and attaching with `scratch`
 * makes the directory `/tmp/hmz-x`, which the host's welcome names.
 */
const served = daemon({
  methods: {
    'epic.attach': (params, peer) => {
      const sub = `s${served.calls.length}`
      const workspace = params.scratch ? '/tmp/hmz-x' : params.workspace
      const slot = params.slot === 'chat:' ? 'chat:ab' : params.slot || ''
      setTimeout(() => peer.notify('epic.event', { sub, message: { type: 'welcome', epoch: 'e1', client: 'c', workspace, slot } }))
      return { sub, client: 'c', workspace, slot }
    },
    'epic.start': () => ({ run: 1, workspace: '/w', slot: '' }),
    'chat.start': (params) => ({ slot: params.slot === 'chat:' ? 'chat:cd' : params.slot, epic: 'e1' }),
    'chat.say': () => ({}),
  },
})
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { ask, chatAsk } = await import('../../../../src/hmz/web/static/held.js')
const { chatting } = await import('../../../../src/hmz/web/static/epic.js')

after(async () => (await api.client('local')).close())

const calls = (method) => served.calls.filter((one) => one.method === method).map((one) => one.params)

test('a chat started at a workspace alone is started by chat.start on a new chat slot', async () => {
  const started = await chatAsk('/w', 'start', { agent: 'claude/opus', task: 'hello', remember: true })
  assert.deepEqual(started, { slot: 'chat:cd', epic: 'e1', workspace: '/w' })
  const [said] = calls('chat.start')
  assert.equal(said.workspace, '/w')
  assert.equal(said.slot, 'chat:')
  assert.equal(said.agent, 'claude/opus')
  assert.equal(said.task, 'hello')
  assert.equal(said.remember, true)
  assert.ok(said.idem, 'chat.start is a write, sent with idem')
  // Nothing of a chat goes through epic.start.
  assert.equal(calls('epic.start').length, 0)
})

test('a chat carried on is started on its own slot, with what it resumes', async () => {
  served.calls.length = 0
  await chatAsk({ workspace: '/w', slot: 'chat:ef' }, 'start', { task: 'more', resume: 'e1' })
  const [said] = calls('chat.start')
  assert.equal(said.slot, 'chat:ef')
  assert.equal(said.resume, 'e1')
})

test('a chat with no workspace starts on the host of a directory made for it', async () => {
  served.calls.length = 0
  const started = await chatAsk('', 'start', { agent: 'claude/opus', task: 'hi', scratch: true })
  const [attached] = calls('epic.attach')
  assert.equal(attached.scratch, true)
  assert.equal(attached.slot, 'chat:')
  // On the host made, as its welcome named it; and let go of once the chat has started.
  const [said] = calls('chat.start')
  assert.equal(said.scratch, undefined)
  assert.equal(said.workspace, '/tmp/hmz-x')
  assert.equal(said.slot, 'chat:ab')
  assert.deepEqual(started, { slot: 'chat:ab', epic: 'e1', workspace: '/tmp/hmz-x' })
  await until(() => calls('epic.detach').length > 0)
})

test('the other methods of a chat are called by its workspace and slot', async () => {
  served.calls.length = 0
  await chatAsk({ workspace: '/w', slot: 'chat:ab' }, 'say', { text: '/help' })
  assert.deepEqual(calls('chat.say').map(({ idem, ...rest }) => rest), [{ text: '/help', workspace: '/w', slot: 'chat:ab' }])
})

test('an epic of a flow named chat is started by epic.start on the workspace host', async () => {
  served.calls.length = 0
  await ask('/w', 'start', { flow: 'chat', task: 'go' })
  assert.equal(calls('epic.attach')[0].slot, '')
  assert.equal(calls('epic.start')[0].flow, 'chat')
  assert.equal(calls('chat.start').length, 0)
})

test('an epic is a chat by its kind, and an old one with no kind by its flow named chat', () => {
  assert.equal(chatting({ kind: 'chat', flow: '' }), true)
  assert.equal(chatting({ kind: 'flow', flow: 'chat' }), false)
  assert.equal(chatting({ epic_kind: 'chat', flow: '' }), true)
  assert.equal(chatting({ flow: 'chat' }), true)
  assert.equal(chatting({ flow: './flows/chat/' }), true)
  assert.equal(chatting({ flow: 'ralph' }), false)
  assert.equal(chatting(null), false)
})
