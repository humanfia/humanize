import assert from 'node:assert/strict'
import { test } from 'node:test'

import { connect, Dropped, ERRORS, PROTOCOL, reach, RpcError, WRITES } from '../../../../src/hmz/web/static/rpc/index.js'
import { daemon, duplex, provider, sleep, until } from './helpers.mjs'

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

  // Refused before the carrier is opened.
  const opened = []
  const untrusted = connect(entry(['tcp://box:1'], ''), [provider(served, opened)])
  await until(() => untrusted.state.state === 'failed')
  assert.equal(untrusted.state.detail, 'tcp://box:1 needs the id of the daemon it reaches.')
  assert.deepEqual(opened, [])
  untrusted.close()
})

test('a daemon with no route has no route to try', async () => {
  const client = connect(entry([]), [provider(daemon())])
  await until(() => client.state.state === 'failed')
  assert.equal(client.state.detail, 'There is no route to try.')
  client.close()
})

test('a route is given up where session.hello is not answered within 30 seconds of starting it', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const served = daemon({ methods: { 'session.hello': () => new Promise(() => {}) } })
  const reaching = reach(entry(['stdio:ssh://box']), [provider(served)])
  // `until` sleeps on the timers mocked here: settle on the event loop instead.
  const settle = () => new Promise((resolve) => setImmediate(resolve))
  while (served.calls.length < 1) await settle()
  t.mock.timers.tick(29999)
  await settle()
  assert.ok(served.sessions[0].peer.open)
  t.mock.timers.tick(1)
  await assert.rejects(reaching, { message: 'stdio:ssh://box did not open within 30 seconds.' })
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

const NONE = 'hmz is not installed on box.'

/**
 * A provider whose `stdio:ssh` routes find no hmz, and ask before they install it; every route it
 * opens is in `opened`, and a route other than those is open once `gate` is.
 */
function asker(served, opened = [], gate = Promise.resolve()) {
  return {
    opens: () => true,
    async open(route, id, { state, asked }) {
      opened.push(route)
      if (route.startsWith('stdio:ssh')) {
        state('asking', NONE)
        if (!(await asked())) throw new Error(NONE)
        state('installing', 'hmz 1.2.3')
      } else {
        state('connecting', 'dialing')
        await gate
      }
      const [mine, theirs] = duplex()
      served.serve(theirs)
      return mine
    },
  }
}

test('a route that finds no hmz leaves the daemon asking, and a yes installs and is not asked again', async () => {
  const served = daemon()
  const client = connect(entry(['stdio:ssh://box']), [asker(served)])
  const states = []
  client.watch((state) => states.push(state.state))
  await until(() => client.state.state === 'asking')
  assert.deepEqual(client.state, { state: 'asking', detail: NONE })
  assert.equal(served.sessions.length, 0)
  client.answer(true)
  assert.deepEqual(await client.call('echo', { a: 1 }), { a: 1 })
  assert.deepEqual(states, ['asking', 'connecting', 'installing', 'up'])
  // Reached again, it finds none again, and installs without asking.
  states.length = 0
  drop(served)
  await until(() => served.sessions.length === 2 && client.state.state === 'up')
  assert.ok(!states.includes('asking'), states.join(' '))
  // Answering a daemon that is not asking does nothing.
  client.answer(false)
  assert.equal(client.state.state, 'up')
  client.close()
})

test('a daemon the user said yes for beforehand is never asking', async () => {
  const served = daemon()
  const client = connect(entry(['stdio:ssh://box']), [asker(served)], { install: true })
  const states = []
  client.watch((state) => states.push(state.state))
  assert.deepEqual(await client.call('echo', {}), {})
  assert.deepEqual(states, ['installing', 'up'])
  client.close()
})

test('the 30 seconds do not run while a route asks, and start afresh once it is answered', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const settle = () => new Promise((resolve) => setImmediate(resolve))
  const served = daemon({ methods: { 'session.hello': () => new Promise(() => {}) } })
  let answered
  const states = []
  const reaching = reach(entry(['stdio:ssh://box']), [asker(served)], {
    state: (state) => states.push(state),
    asked: () => new Promise((resolve) => (answered = resolve)),
  })
  while (!answered) await settle()
  t.mock.timers.tick(600000)
  await settle()
  assert.deepEqual(states, ['asking'])
  answered(true)
  while (served.calls.length < 1) await settle()
  t.mock.timers.tick(29999)
  await settle()
  assert.ok(served.sessions[0].peer.open)
  t.mock.timers.tick(1)
  await assert.rejects(reaching, { message: 'stdio:ssh://box did not open within 30 seconds.' })
})

test('with nobody to ask, a route that finds no hmz fails as not installed', async () => {
  const served = daemon()
  await assert.rejects(reach(entry(['stdio:ssh://box']), [asker(served)]), { message: NONE })
  assert.equal(served.sessions.length, 0)
})

test('a no leaves the daemon failed, and it is not reached again by itself', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const settle = () => new Promise((resolve) => setImmediate(resolve))
  const served = daemon()
  const opened = []
  const client = connect(entry(['stdio:ssh://box']), [asker(served, opened)])
  while (client.state.state !== 'asking') await settle()
  const calling = client.call('echo', {})
  client.answer(false)
  await assert.rejects(calling, { code: ERRORS.UNAVAILABLE, message: NONE })
  assert.deepEqual(client.state, { state: 'failed', detail: NONE })
  for (let waited = 0; waited < 5; waited++) {
    t.mock.timers.tick(60000)
    await settle()
  }
  assert.deepEqual(opened, ['stdio:ssh://box'])
  assert.deepEqual(client.state, { state: 'failed', detail: NONE })
  await assert.rejects(client.call('echo', {}), { code: ERRORS.UNAVAILABLE, message: NONE })
  client.close()
})

test('a daemon stays asking whatever its other routes say, and one of them reached ends the question', async () => {
  const served = daemon()
  let open
  const client = connect(entry(['stdio:ssh://box', 'tcp://box:1']), [asker(served, [], new Promise((resolve) => (open = resolve)))])
  const states = []
  client.watch((state) => states.push(state.state))
  await until(() => client.state.state === 'asking')
  // The second route starts 250 ms after the first, and says it is connecting.
  await new Promise((resolve) => setTimeout(resolve, 400))
  assert.deepEqual(client.state, { state: 'asking', detail: NONE })
  open()
  assert.deepEqual(await client.call('echo', {}), {})
  assert.deepEqual(states, ['asking', 'up'])
  client.answer(true)
  assert.equal(client.state.state, 'up')
  assert.equal(served.sessions.length, 1)
  client.close()
})

test('a no stands for the reach it was said in: a later route that finds no hmz is not asked about', async () => {
  const served = daemon()
  // The second route starts 250 ms after the first, and finds no hmz either.
  const asks = []
  const slow = {
    opens: () => true,
    async open(route, id, { state, asked }) {
      state('asking', NONE)
      asks.push(route)
      if (!(await asked())) throw new Error(NONE)
      throw new Error('never')
    },
  }
  const client = connect(entry(['stdio:ssh://box', 'stdio:ssh://box.lan']), [slow])
  const states = []
  client.watch((state) => states.push(state.state))
  await until(() => client.state.state === 'asking')
  assert.equal(client.answer(false), true)
  await until(() => client.state.state === 'failed')
  assert.deepEqual(asks, ['stdio:ssh://box', 'stdio:ssh://box.lan'])
  assert.deepEqual(states, ['asking', 'connecting', 'failed'])
  assert.deepEqual(client.state, { state: 'failed', detail: NONE })
  assert.equal(served.sessions.length, 0)
  client.close()
})

test('a route that asked and fails by itself is asked about no more, and its other routes go on', async () => {
  const served = daemon()
  let fail
  let open
  const opening = {
    opens: () => true,
    async open(route, id, { state, asked }) {
      if (route.startsWith('stdio:ssh')) {
        state('asking', NONE)
        asked()
        await new Promise((resolve, reject) => (fail = reject))
      }
      state('connecting', 'dialing')
      await new Promise((resolve) => (open = resolve))
      const [mine, theirs] = duplex()
      served.serve(theirs)
      return mine
    },
  }
  const client = connect(entry(['stdio:ssh://box', 'tcp://box:1']), [opening])
  const states = []
  client.watch((state) => states.push(state))
  await until(() => client.state.state === 'asking' && open)
  fail(new Error('ssh carrier closed'))
  await until(() => client.state.state !== 'asking')
  assert.deepEqual(client.state, { state: 'connecting', detail: '' })
  // Nothing waits for an answer: one given is to nobody, and neither kept nor a no to retrying.
  assert.equal(client.answer(false), false)
  assert.deepEqual(client.state, { state: 'connecting', detail: '' })
  open()
  assert.deepEqual(await client.call('echo', {}), {})
  assert.deepEqual(states.map((one) => one.state), ['asking', 'connecting', 'up'])
  client.close()
})

test('closing a client that asks gives its routes up, and one closed is never asking', async () => {
  const served = daemon()
  const signals = []
  const answers = []
  let late
  const opening = {
    opens: () => true,
    async open(route, id, { state, asked, signal }) {
      signals.push(signal)
      // The second client's route finds no hmz only once the client is closed.
      if (signals.length === 2) await new Promise((resolve) => (late = resolve))
      state('asking', NONE)
      asked().then((install) => answers.push(install))
      if (signal.aborted) throw new Error('Given up.')
      await new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new Error('Given up.'))))
    },
  }
  const asking = connect(entry(['stdio:ssh://box']), [opening])
  await until(() => asking.state.state === 'asking')
  asking.close()
  assert.equal(signals[0].aborted, true)
  assert.equal(asking.state.state, 'idle')

  const probing = connect(entry(['stdio:ssh://box']), [opening])
  const states = []
  probing.watch((state) => states.push(state.state))
  await until(() => late)
  probing.close()
  assert.equal(signals[1].aborted, true)
  late()
  await sleep(20)
  assert.deepEqual(states, ['idle'])
  assert.equal(probing.answer(true), false)
  assert.equal(probing.state.state, 'idle')
  // Let go of, nobody was answered.
  assert.deepEqual(answers, [])
  assert.equal(served.sessions.length, 0)
})
