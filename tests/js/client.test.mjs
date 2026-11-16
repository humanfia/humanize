import assert from 'node:assert/strict'
import { test } from 'node:test'

import { connect, Dropped, ERRORS, PROTOCOL, RpcError, WRITES } from '../../src/hmz/web/static/rpc/index.js'
import { daemon, provider, until } from './helpers.mjs'

const ID = 'a'.repeat(52)
const entry = (routes = ['tcp://box:1'], id = ID) => ({ name: 'box', id, routes })

/** Closes the session the daemon serves now, as a carrier dropping would. */
const drop = (served) => served.sessions.at(-1).peer.close('dropped')

test('a client reaches its daemon, says hello and calls', async () => {
  const served = daemon()
  const client = connect(entry(), [provider(served)], { client: { name: 'me', kind: 'web' } })
  const states = []
  client.watch((state) => states.push(state.state))
  assert.deepEqual(await client.call('echo', { x: 1 }), { x: 1 })
  assert.equal(client.state.state, 'up')
  assert.equal(client.hello.daemon_id, ID)
  assert.deepEqual(served.calls[0], { method: 'session.hello', params: { protocol: PROTOCOL, client: { name: 'me', kind: 'web' } } })
  assert.deepEqual(states, ['up'])
  client.close()
  assert.equal(client.state.state, 'idle')
})

test('a daemon answering another id fails as not the one paired with', async () => {
  const served = daemon({ id: 'b'.repeat(52) })
  const client = connect(entry(), [provider(served)])
  await until(() => client.state.state === 'failed')
  assert.equal(client.state.detail, 'box is not the daemon it was paired with.')
  await assert.rejects(client.call('echo', {}), (error) => error.code === ERRORS.UNAVAILABLE)
  client.close()
})

test('an id is pinned from a trusted route, and never from an untrusted one alone', async () => {
  const served = daemon()
  const pinned = []
  const client = connect(entry(['stdio:ssh://box'], ''), [provider(served)], { pinned: (id) => pinned.push(id) })
  await client.call('echo', {})
  assert.deepEqual(pinned, [ID])
  client.close()

  const untrusted = connect(entry(['tcp://box:1'], ''), [provider(served)])
  await until(() => untrusted.state.state === 'failed')
  assert.equal(untrusted.state.detail, 'tcp://box:1 cannot be reached from here.')
  untrusted.close()
})

test('a route no provider opens, and a text that is not a route, are refused', async () => {
  const served = daemon()
  const none = { opens: () => false, open: () => assert.fail('opened') }
  const client = connect(entry(['tcp://box:1']), [none])
  await until(() => client.state.state === 'failed')
  assert.equal(client.state.detail, 'tcp://box:1 cannot be reached from here.')
  client.close()
  const bad = connect(entry(['nowhere']), [provider(served)])
  await until(() => bad.state.state === 'failed')
  assert.equal(bad.state.detail, 'nowhere is not a route.')
  bad.close()
})

test('a client refused for its version says why and tries no more', async () => {
  let hellos = 0
  const served = daemon({
    methods: {
      'session.hello': () => {
        hellos++
        throw new RpcError(426, 'held for frontends by a newer Humanize; `hmz` of it reads it', { protocol: '4.0.0' })
      },
    },
  })
  const client = connect(entry(), [provider(served)])
  await until(() => client.state.state === 'failed')
  assert.equal(client.state.detail, 'held for frontends by a newer Humanize; `hmz` of it reads it')
  await new Promise((resolve) => setTimeout(resolve, 1300))
  assert.equal(hellos, 1)
  client.close()
})

test('a write is given an idem, and sent again with the same one where the session drops under it', async () => {
  let says = 0
  const served = daemon({
    methods: {
      'epic.say': (params, peer) => {
        says++
        if (says === 1) {
          peer.close('dropped')
          return new Promise(() => {})
        }
        return { said: params.text }
      },
      hold: () => new Promise(() => {}),
    },
  })
  const client = connect(entry(), [provider(served)])
  assert.deepEqual(await client.call('epic.say', { sub: 's1', text: 'hi' }), { said: 'hi' })
  const sent = served.calls.filter((call) => call.method === 'epic.say').map((call) => call.params.idem)
  assert.equal(sent.length, 2)
  assert.match(sent[0], /^[A-Za-z0-9_-]{22}$/)
  assert.equal(sent[0], sent[1])
  assert.ok(WRITES.has('epic.say') && !WRITES.has('epic.attach'))

  // A read is not sent again: the drop is the caller's.
  served.calls.length = 0
  const pending = assert.rejects(client.call('hold', {}), Dropped)
  await until(() => served.calls.some((call) => call.method === 'hold'))
  drop(served)
  await pending
  client.close()
})

test('an epic subscription is attached again with since after a drop, and missed records follow', async () => {
  const served = daemon()
  served.record('one')
  served.record('two')
  const client = connect(entry(), [provider(served)])
  const told = []
  const sub = await client.attach({ workspace: '/w', slot: '' }, (message) => told.push(message))
  await until(() => told.some((message) => message.type === 'live'))
  served.record('three')
  await until(() => told.some((message) => message.text === 'three'))

  drop(served)
  await until(() => client.state.state === 'connecting')
  served.record('four')
  await until(() => told.some((message) => message.text === 'four'), 5000)
  const attaches = served.calls.filter((call) => call.method === 'epic.attach').map((call) => call.params)
  assert.deepEqual(attaches, [
    { workspace: '/w', slot: '' },
    { workspace: '/w', slot: '', since: { epoch: 'e1', seq: 3 } },
  ])
  // Only what was missed came again.
  assert.deepEqual(told.filter((message) => message.type === 'said').map((message) => message.text), ['one', 'two', 'three', 'four'])
  assert.equal(sub.sub, 's1')

  await sub.close()
  assert.ok(served.calls.some((call) => call.method === 'epic.detach' && call.params.sub === 's1'))
  client.close()
})

test('an epic subscription fallen behind is attached again to the slot it was given, with since', async () => {
  const served = daemon()
  served.record('one')
  const client = connect(entry(), [provider(served)])
  const told = []
  const ended = []
  await client.attach({ workspace: '/w', slot: '' }, (message) => told.push(message), (why) => ended.push(why))
  await until(() => told.some((message) => message.type === 'live'))
  const { peer, subs } = served.sessions[0]
  const [sub] = subs.keys()
  peer.notify('epic.event', { sub, message: { type: 'gone', why: 'too far behind; attach again' } })
  await until(() => served.calls.filter((call) => call.method === 'epic.attach').length === 2)
  assert.deepEqual(served.calls.filter((call) => call.method === 'epic.attach')[1].params, { workspace: '/w', slot: '', since: { epoch: 'e1', seq: 1 } })
  assert.ok(!told.some((message) => message.type === 'gone'))
  // Any other gone ends it.
  const [, again] = subs.keys()
  peer.notify('epic.event', { sub: again, message: { type: 'gone', why: 'let go' } })
  await until(() => ended.length === 1)
  assert.deepEqual(ended, ['let go'])
  client.close()
})

test('a new chat attached to is attached to again by the slot it was given, not as a new one', async () => {
  const served = daemon({
    methods: {
      'epic.attach': (params) => ({ sub: `c${served.calls.length}`, client: 'c', workspace: '/w', slot: params.slot === 'chat:' ? 'chat:ab' : params.slot }),
    },
  })
  const client = connect(entry(), [provider(served)])
  await client.attach({ workspace: '/w', slot: 'chat:', figures: true }, () => {})
  drop(served)
  await until(() => served.calls.filter((call) => call.method === 'epic.attach').length === 2, 5000)
  assert.deepEqual(served.calls.filter((call) => call.method === 'epic.attach')[1].params, { workspace: '/w', slot: 'chat:ab', figures: true })
  client.close()
})

test('notices are followed again after the last one heard', async () => {
  const served = daemon()
  served.notice('before')
  const client = connect(entry(), [provider(served)])
  const told = []
  await client.notices((notice) => told.push(notice.text))
  served.notice('first')
  await until(() => told.length === 1)
  drop(served)
  await until(() => client.state.state === 'connecting')
  served.notice('missed')
  await until(() => told.length === 2, 5000)
  served.notice('after')
  await until(() => told.length === 3)
  assert.deepEqual(told, ['first', 'missed', 'after'])
  const subscribes = served.calls.filter((call) => call.method === 'notices.subscribe').map((call) => call.params)
  assert.deepEqual(subscribes, [{}, { after: 2 }])
  client.close()
})

test('a drop is tried again after 1 second, and calls made meanwhile wait for the session', async () => {
  const served = daemon()
  const client = connect(entry(), [provider(served)])
  await client.call('echo', {})
  drop(served)
  await until(() => client.state.state === 'connecting')
  const t0 = Date.now()
  assert.deepEqual(await client.call('echo', { back: true }), { back: true })
  const waited = Date.now() - t0
  assert.ok(waited >= 900 && waited < 2000, `waited ${waited} ms`)
  client.close()
  await assert.rejects(client.call('echo', {}), Dropped)
})

test('a daemon that fails is tried again after 1 s, then 2 s, doubling', async () => {
  const tries = []
  const t0 = Date.now()
  const failing = {
    opens: () => true,
    open: async () => {
      tries.push(Date.now() - t0)
      throw new Error('Connection refused.')
    },
  }
  const client = connect(entry(), [failing])
  await until(() => tries.length === 3, 5000)
  client.close()
  const gaps = [tries[1] - tries[0], tries[2] - tries[1]]
  assert.ok(gaps[0] >= 950 && gaps[0] < 1500, `first wait ${gaps[0]} ms`)
  assert.ok(gaps[1] >= 1950 && gaps[1] < 2500, `second wait ${gaps[1]} ms`)
  assert.equal(client.state.state, 'idle')
})
