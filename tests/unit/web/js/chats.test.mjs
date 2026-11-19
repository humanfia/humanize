import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { RpcError } from '../../../../src/hmz/web/static/rpc/index.js'
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
      setTimeout(() => {
        const send = (message) => peer.notify('epic.event', { sub, message })
        send({ type: 'welcome', epoch: 'e1', client: 'c', workspace, slot })
        // A chat folded away and carried on, the same chat on another life of its host: its host
        // names it as `chat`, and no epic.
        if (workspace === '/carried') {
          const life = (epoch) => {
            send({ type: 'welcome', epoch, client: 'c', workspace, slot })
            send({ type: 'run', state: 'running', run: 1, kind: 'chat', epic: '', chat: 'c7', slot, turn: 'running' })
            send({ type: 'started', seq: 1, run: 1, task: 'hello' })
            send({ type: 'live', seq: 1, elided: 0 })
          }
          life('e1')
          setTimeout(() => {
            carried = 1
            life('e2')
          }, 50)
        }
        // What a host holds of a run that ended before anybody looked: at `/failed` alone.
        if (workspace !== '/failed') return
        send({ type: 'run', state: 'idle', run: 1, kind: slot ? 'chat' : 'flow', epic: slot ? '' : 'e9', chat: slot ? 'c9' : '', slot, turn: 'done' })
        send({ type: 'started', seq: 1, run: 1, task: 'hello' })
        send({ type: 'ended', seq: 2, run: 1, how: 'failed', why: 'HarnessSandboxed: no fence here' })
        send({ type: 'live', seq: 2, elided: 0 })
      })
      return { sub, client: 'c', workspace, slot }
    },
    'epic.start': () => ({ run: 1, workspace: '/w', slot: '' }),
    'chat.start': (params) => ({ slot: params.slot === 'chat:' ? 'chat:cd' : params.slot, chat: 'c1' }),
    'chat.say': () => ({}),
    'chat.stop': () => {
      if (stopped) throw new RpcError(409, 'no turn is open, so there is nothing to stop')
      stopped = true
      return {}
    },
    'chat.get': ({ chat, trace }) => ({ ...CHAT, id: chat, earlier: carried, ...(trace ? { trace: [{ key: 'claude:s1', actions: [] }] } : {}) }),
    // An epic an earlier hmz recorded for a chat: of the kind `chat`, and of no flow.
    'runs.get': ({ name }) => ({ name, kind: 'chat', flow: '', task: 'an old chat', workspace: '/old', how: 'stopped', held: false, resumable: true, picks_up: true, agents: [], sessions: [] }),
  },
})
/** How many sessions the chat at `/carried` opened before it was last carried on. */
let carried = 0
/** Whether the turn open was stopped: there is none to stop after. */
let stopped = false
/** A chat as `chat.get` answers one that failed. */
const CHAT = { title: 'hello', workspace: '/failed', workdir: '/failed', agent: 'claude/opus:high', model: 'opus', began: '2026-01-01T00:00:00Z', updated: '2026-01-01T00:01:00Z', state: 'failed', slot: '', asking: [], permission: 'workspace-write', archived: false, spent: null, at: '/home/chats/failed/c9', task: 'hello\nthere', prefer: '', forked: '', agents: [], sessions: [], backup: [], backed: {} }
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { ask, chatAsk } = await import('../../../../src/hmz/web/static/held.js')
const { chatting, watch } = await import('../../../../src/hmz/web/static/epic.js')

after(async () => (await api.client('local')).close())

const calls = (method) => served.calls.filter((one) => one.method === method).map((one) => one.params)

test('a chat started at a workspace alone is started by chat.start on a new chat slot', async () => {
  const started = await chatAsk('/w', 'start', { agent: 'claude/opus', task: 'hello', remember: true })
  assert.deepEqual(started, { slot: 'chat:cd', chat: 'c1', workspace: '/w' })
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

test('a chat carried on is started on its own slot, resuming it by its id', async () => {
  served.calls.length = 0
  await chatAsk({ workspace: '/w', slot: 'chat:ef' }, 'start', { task: 'more', resume: 'c1' })
  const [said] = calls('chat.start')
  assert.equal(said.slot, 'chat:ef')
  assert.equal(said.resume, 'c1')
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
  assert.deepEqual(started, { slot: 'chat:ab', chat: 'c1', workspace: '/tmp/hmz-x' })
  await until(() => calls('epic.detach').length > 0)
})

test('the other methods of a chat are called by its workspace and slot', async () => {
  served.calls.length = 0
  await chatAsk({ workspace: '/w', slot: 'chat:ab' }, 'say', { text: '/help' })
  assert.deepEqual(calls('chat.say').map(({ idem, ...rest }) => rest), [{ text: '/help', workspace: '/w', slot: 'chat:ab' }])
})

test('the turn open is stopped by chat.stop, by workspace and slot, and a refusal says why', async () => {
  served.calls.length = 0
  stopped = false
  await chatAsk({ workspace: '/w', slot: 'chat:ab' }, 'stop')
  assert.deepEqual(calls('chat.stop').map(({ idem, ...rest }) => rest), [{ workspace: '/w', slot: 'chat:ab' }])
  assert.ok(calls('chat.stop')[0].idem, 'chat.stop is a write, sent with idem')
  // Nothing of a chat is stopped as an epic is.
  assert.equal(calls('epic.stop').length, 0)
  await assert.rejects(chatAsk({ workspace: '/w', slot: 'chat:ab' }, 'stop'), (error) => error.status === 409 && /no turn is open/.test(error.message))
})

test('an epic of a flow named chat is started by epic.start on the workspace host', async () => {
  served.calls.length = 0
  await ask('/w', 'start', { flow: 'chat', task: 'go' })
  assert.equal(calls('epic.attach')[0].slot, '')
  assert.equal(calls('epic.start')[0].flow, 'chat')
  assert.equal(calls('chat.start').length, 0)
})

test('what is read is a chat by its kind, and a host run with no kind by its flow named chat', () => {
  assert.equal(chatting({ kind: 'chat', flow: '' }), true)
  assert.equal(chatting({ kind: 'flow', flow: 'chat' }), false)
  assert.equal(chatting({ epic_kind: 'chat', flow: '' }), true)
  assert.equal(chatting({ flow: 'chat' }), true)
  assert.equal(chatting({ flow: './flows/chat/' }), true)
  assert.equal(chatting({ flow: 'ralph' }), false)
  assert.equal(chatting(null), false)
})

test('a chat that ended before its host was looked at is still the chat its host names, read by chat.get', async () => {
  /** @type {{name: string, none: boolean, ended: string}[]} */
  const told = []
  const stop = watch('', { workspace: '/failed', slot: 'chat:gh' }, (seen) => told.push({ name: seen.detail ? seen.detail.name : '', none: seen.none, ended: seen.going && seen.going.ended ? seen.going.ended.why : '' }))
  try {
    // Named, with the records that say why it failed, and never said to be no chat at all.
    await until(() => told.some((one) => one.name === 'c9'))
    assert.equal(told.at(-1).ended, 'HarnessSandboxed: no fence here')
    assert.deepEqual(told.filter((one) => one.none), [])
    // By its id, off its own record: never as an epic.
    assert.ok(calls('chat.get').some((one) => one.chat === 'c9'))
    assert.equal(calls('runs.get').length, 0)
  } finally {
    stop()
  }
})

test('an epic that ended on a workspace host is not the one going there', async () => {
  /** @type {{name: string, none: boolean}[]} */
  const told = []
  const stop = watch('', { workspace: '/failed', slot: '' }, (seen) => told.push({ name: seen.detail ? seen.detail.name : '', none: seen.none }))
  try {
    await until(() => told.some((one) => one.none))
    assert.deepEqual(told.filter((one) => one.name), [])
  } finally {
    stop()
  }
})

test('a chat carried on while its host is followed is read again, with what it opened before', async () => {
  /** @type {{epoch: string, earlier: number}[]} */
  const told = []
  const stop = watch('', { workspace: '/carried', slot: 'chat:ij' }, (seen) => told.push({ epoch: seen.held ? seen.held.epoch : '', earlier: seen.detail ? seen.detail.earlier : -1 }))
  try {
    // First as it began, with nothing before it.
    await until(() => told.some((one) => one.epoch === 'e1' && one.earlier === 0))
    // Carried on, the same chat: what it wrote down is read again, not kept as first read.
    await until(() => told.some((one) => one.epoch === 'e2' && one.earlier === 1), 2000)
  } finally {
    stop()
  }
})

test('a chat named is followed by chat.get, as a chat: titled, told by its first message, never an epic', async () => {
  const told = []
  const stop = watch('c5', '', (seen) => told.push(seen.detail), { chat: true })
  try {
    await until(() => told.some(Boolean))
    const detail = told.findLast(Boolean)
    assert.deepEqual([detail.name, detail.kind, detail.title, detail.task, detail.how], ['c5', 'chat', 'hello', 'hello\nthere', 'failed'])
    assert.equal(chatting(detail), true)
  } finally {
    stop()
  }
})

test('an epic an earlier hmz recorded for a chat is followed as an epic of the flow chat, only read', async () => {
  const told = []
  const stop = watch('e-old', '', (seen) => told.push(seen.detail))
  try {
    await until(() => told.some(Boolean))
    const detail = told.findLast(Boolean)
    assert.deepEqual([detail.name, detail.kind, detail.flow], ['e-old', 'flow', 'chat'])
    assert.equal(chatting(detail), false)
    // Nothing carries it on, and nothing resumes it.
    assert.deepEqual([detail.picks_up, detail.resumable], [false, false])
  } finally {
    stop()
  }
})
