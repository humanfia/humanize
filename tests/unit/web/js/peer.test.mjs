import assert from 'node:assert/strict'
import { test } from 'node:test'

import { Dropped, encode, ERRORS, MAX, Peer, RpcError } from '../../../../src/hmz/web/static/rpc/index.js'
import { duplex, sleep, until } from './helpers.mjs'

/** Two peers joined end to end, each answering `add` and telling its notifications. */
function pair(handlers = {}) {
  const [a, b] = duplex()
  const told = { left: [], right: [] }
  const side = (name) => ({
    call: async (method, params, signal) => {
      if (method === 'add') return { sum: params.a + params.b, by: name }
      if (method === 'refuse') throw new RpcError(409, 'Not now.', { why: 'busy' })
      if (method === 'break') throw new Error('it broke')
      if (method === 'wait') return new Promise((resolve) => signal.addEventListener('abort', () => resolve({ late: true })))
      throw new RpcError(ERRORS.NO_METHOD, `There is no method ${method}.`)
    },
    notified: (method, params) => told[name].push({ method, params }),
    ...handlers,
  })
  return { left: new Peer(a, side('left')), right: new Peer(b, side('right')), told }
}

test('calls go both ways and are answered', async () => {
  const { left, right } = pair()
  assert.deepEqual(await left.call('add', { a: 1, b: 2 }), { sum: 3, by: 'right' })
  assert.deepEqual(await right.call('add', { a: 5, b: 6 }), { sum: 11, by: 'left' })
  const many = await Promise.all([1, 2, 3].map((n) => left.call('add', { a: n, b: n })))
  assert.deepEqual(many.map((one) => one.sum), [2, 4, 6])
})

test('notifications go both ways', async () => {
  const { left, right, told } = pair()
  left.notify('ping', { n: 1 })
  right.notify('pong', { n: 2 })
  await until(() => told.left.length && told.right.length)
  assert.deepEqual(told.right, [{ method: 'ping', params: { n: 1 } }])
  assert.deepEqual(told.left, [{ method: 'pong', params: { n: 2 } }])
})

test('a refusal carries its code, message and data; a failure is -32603', async () => {
  const { left } = pair()
  await assert.rejects(left.call('refuse'), (error) => error instanceof RpcError && error.code === 409 && error.message === 'Not now.' && error.data.why === 'busy')
  await assert.rejects(left.call('break'), (error) => error.code === ERRORS.INTERNAL && error.message === 'Something went wrong here: it broke')
  await assert.rejects(left.call('nothing'), (error) => error.code === ERRORS.NO_METHOD)
})

test('a peer that answers nothing refuses every call -32601', async () => {
  const [a, b] = duplex()
  const left = new Peer(a)
  new Peer(b)
  await assert.rejects(left.call('add', {}), (error) => error.code === ERRORS.NO_METHOD && error.message === 'There is no method add.')
})

test('a call timed out is cancelled on the other side with session.cancel', async () => {
  let cancelled = false
  const { left } = pair({
    call: (method, params, signal) =>
      new Promise((resolve) =>
        signal.addEventListener('abort', () => {
          cancelled = true
          resolve({})
        }),
      ),
  })
  await assert.rejects(left.call('wait', {}, { timeout: 20 }), (error) => error.code === ERRORS.CANCELLED)
  await until(() => cancelled)
  // The answer that follows, -32800, is for a call no longer waited on.
  await sleep(10)
  assert.ok(left.open)
})

test('closing fails every call still unanswered with Dropped, and later calls too', async () => {
  const { left, right } = pair({ call: () => new Promise(() => {}) })
  const waiting = left.call('wait')
  right.close('gone away')
  await assert.rejects(waiting, Dropped)
  assert.equal(await left.closed, 'The other side closed.')
  await assert.rejects(left.call('add', {}), Dropped)
})

test('an oversize frame closes the session; an oversize call is refused 413 before it is sent', async () => {
  const [a, b] = duplex()
  const peer = new Peer(a)
  const header = new Uint8Array(4)
  new DataView(header.buffer).setUint32(0, MAX + 1)
  b.send(header)
  const why = await peer.closed
  assert.match(why, /frame/)

  const { left } = pair()
  await assert.rejects(left.call('add', { big: 'x'.repeat(MAX) }), (error) => error.code === ERRORS.TOO_LARGE)
  assert.ok(left.open)
})

test('a batch is refused -32600 and a frame not holding JSON -32700, with id null', async () => {
  const [a, b] = duplex()
  new Peer(a)
  const answers = []
  const frames = new (await import('../../../../src/hmz/web/static/rpc/frames.js')).Frames()
  b.listen((bytes) => answers.push(...frames.push(bytes).map((payload) => JSON.parse(new TextDecoder().decode(payload)))), () => {})
  b.send(encode([{ jsonrpc: '2.0', id: 1, method: 'x' }]))
  const junk = new TextEncoder().encode('nope')
  b.send(Uint8Array.of(0, 0, 0, junk.length, ...junk))
  // Not UTF-8 is not JSON either; the session stays open.
  b.send(Uint8Array.of(0, 0, 0, 2, 0xc3, 0x28))
  await until(() => answers.length === 3)
  assert.deepEqual(answers.map((one) => [one.id, one.error.code, one.error.message]), [
    [null, ERRORS.INVALID_REQUEST, 'Send one request a frame.'],
    [null, ERRORS.PARSE, 'Send JSON.'],
    [null, ERRORS.PARSE, 'Send JSON.'],
  ])
})

test('a frame that is JSON but no JSON-RPC 2.0 message is refused -32600, with the id of a call alone', async () => {
  const [a, b] = duplex()
  let release
  const told = []
  new Peer(a, { call: () => new Promise((resolve) => (release = resolve)), notified: (method) => told.push(method) })
  const answers = []
  const frames = new (await import('../../../../src/hmz/web/static/rpc/frames.js')).Frames()
  b.listen((bytes) => answers.push(...frames.push(bytes).map((payload) => JSON.parse(new TextDecoder().decode(payload)))), () => {})
  for (const message of [
    42,
    { id: 1, method: 'x' },
    { jsonrpc: '2.0', id: 2, method: 7 },
    { jsonrpc: '2.0', id: 3, method: 'x', params: [1] },
    { jsonrpc: '2.0', id: 1.5, method: 'x' },
    { jsonrpc: '2.0', id: 4 },
    // Dropped: a notification not well formed, and a response that answers no call.
    { jsonrpc: '2.0', method: 7 },
    { jsonrpc: '2.0', method: 'n', params: 'x' },
    { jsonrpc: '2.0', method: 'n', params: null },
    { jsonrpc: '2.0', id: 9, result: {} },
    // A call, and another reusing its id while it is unanswered.
    { jsonrpc: '2.0', id: 'c', method: 'x' },
    { jsonrpc: '2.0', id: 'c', method: 'x' },
    { jsonrpc: '2.0', id: 'c', method: 7 },
    { jsonrpc: '2.0', id: 5, method: 'x', params: null },
  ])
    b.send(encode(message))
  await until(() => answers.length === 9)
  assert.deepEqual(answers.map((one) => [one.id, one.error.code, one.error.message]), [
    [null, ERRORS.INVALID_REQUEST, 'That is not a JSON-RPC 2.0 request.'],
    [null, ERRORS.INVALID_REQUEST, 'That is not a JSON-RPC 2.0 request.'],
    [2, ERRORS.INVALID_REQUEST, 'That is not a JSON-RPC 2.0 request.'],
    [3, ERRORS.INVALID_REQUEST, 'That is not a JSON-RPC 2.0 request.'],
    [null, ERRORS.INVALID_REQUEST, 'That is not a JSON-RPC 2.0 request.'],
    [null, ERRORS.INVALID_REQUEST, 'That is not a JSON-RPC 2.0 request.'],
    [null, ERRORS.INVALID_REQUEST, 'That id is in use by another call.'],
    [null, ERRORS.INVALID_REQUEST, 'That id is in use by another call.'],
    [5, ERRORS.INVALID_REQUEST, 'That is not a JSON-RPC 2.0 request.'],
  ])
  assert.deepEqual(told, [])
  release({ ok: true })
  await until(() => answers.length === 10)
  assert.deepEqual(answers[9], { jsonrpc: '2.0', id: 'c', result: { ok: true } })
})
