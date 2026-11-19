import assert from 'node:assert/strict'
import { test } from 'node:test'

import { following } from '../../../../src/hmz/web/static/held-core.js'

/** A host that answers one attach at a time, as the daemon's `epic.attach` does. */
function host() {
  const calls = []
  const subs = []
  const closed = []
  let closing = () => {}
  let hanging = false
  function attach(params, told, ended) {
    const sub = {
      sub: `s${subs.length + 1}`,
      told,
      ended: (why) => ended(why),
      close: async () => {
        closed.push(sub.sub)
        closing(sub)
        if (hanging) await new Promise(() => {})
      },
    }
    calls.push(params)
    subs.push(sub)
    return Promise.resolve(sub)
  }
  return {
    attach,
    calls,
    subs,
    closed,
    closing: (fn) => {
      closing = fn
    },
    hang: (value = true) => {
      hanging = value
    },
  }
}

const welcome = (epoch) => ({ type: 'welcome', epoch, client: 'c' })
const record = (seq, text) => ({ type: 'said', seq, text })
const seqs = (one) => one.state.records.map((one) => one.seq)

/** A following attached once, welcomed and given its first record. */
async function opened() {
  const h = host()
  const one = following('/w', '', { attach: h.attach })
  one.connect()
  await one.opening
  h.subs[0].told(welcome('e1'))
  h.subs[0].told(record(1, 'one'))
  return { h, one }
}

test('attaching again goes on from the last record read', async () => {
  const { h, one } = await opened()
  assert.deepEqual(h.calls, [{ workspace: '/w', slot: '', figures: true }])

  await one.refresh()
  assert.deepEqual(h.closed, ['s1'])
  assert.deepEqual(h.calls[1], { workspace: '/w', slot: '', figures: true, since: { epoch: 'e1', seq: 1 } })
})

test('a record after a refresh is not doubled', async () => {
  const { h, one } = await opened()
  await one.refresh()
  h.subs[1].told(welcome('e1'))
  h.subs[1].told(record(2, 'two'))

  assert.deepEqual(seqs(one), [1, 2])
})

test('a host that replays from the top is not doubled', async () => {
  const { h, one } = await opened()
  await one.refresh()
  h.subs[1].told(welcome('e1'))
  h.subs[1].told(record(1, 'one'))
  h.subs[1].told(record(2, 'two'))

  assert.deepEqual(seqs(one), [1, 2])
  assert.equal(one.state.seq, 2)
})

test('a new epoch starts the records over', async () => {
  const { h, one } = await opened()
  await one.refresh()
  h.subs[1].told(welcome('e2'))
  h.subs[1].told(record(1, 'again'))

  assert.equal(one.state.epoch, 'e2')
  assert.equal(one.state.seq, 1)
  assert.deepEqual(seqs(one), [1])
})

test('a close that says it ended does not make the page gone', async () => {
  const { h, one } = await opened()
  // A client-side close that still calls the ended callback of the subscription it closed.
  h.closing((sub) => sub.ended('let go'))

  await one.refresh()
  assert.equal(one.state.gone, '')
  h.subs[1].told(welcome('e1'))
  assert.equal(one.state.gone, '')
  assert.equal(one.state.connected, true)
})

test('a close that never answers does not hold the refresh', async () => {
  const { h, one } = await opened()
  h.hang()

  await one.refresh()
  assert.equal(one.refreshing, false)
  assert.deepEqual(h.closed, ['s1'])
  assert.deepEqual(h.calls[1], { workspace: '/w', slot: '', figures: true, since: { epoch: 'e1', seq: 1 } })

  h.subs[1].told(welcome('e1'))
  h.subs[1].told(record(2, 'two'))
  assert.deepEqual(seqs(one), [1, 2])
})
