import assert from 'node:assert/strict'
import { test } from 'node:test'

import { encode, FrameError, Frames, MAX } from '../../../../src/hmz/web/static/rpc/index.js'

const parsed = (payload) => JSON.parse(new TextDecoder().decode(payload))

const joined = (...parts) => {
  const out = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0))
  let at = 0
  for (const part of parts) out.set(part, (at += part.length) - part.length)
  return out
}

test('a frame is its length in four big-endian bytes, then its JSON in UTF-8 unescaped', () => {
  const frame = encode({ said: 'héllo ✓' })
  const text = '{"said":"héllo ✓"}'
  const length = new TextEncoder().encode(text).length
  assert.deepEqual([...frame.subarray(0, 4)], [0, 0, 0, length])
  assert.equal(new TextDecoder().decode(frame.subarray(4)), text)
})

test('frames cut at every byte offset are each read once, in order', () => {
  const values = [{ a: 1 }, { b: 'twö' }, { c: [1, 2, 3], d: null }]
  const bytes = joined(...values.map(encode))
  for (let cut = 0; cut <= bytes.length; cut++) {
    const frames = new Frames()
    const read = [...frames.push(bytes.subarray(0, cut)), ...frames.push(bytes.subarray(cut))]
    assert.deepEqual(read.map(parsed), values, `cut at ${cut}`)
  }
  // And one byte at a time.
  const frames = new Frames()
  const read = []
  for (const byte of bytes) read.push(...frames.push(Uint8Array.of(byte)))
  assert.deepEqual(read.map(parsed), values)
})

test('a length of 0 or above the most a frame may carry breaks the reading, after the frames before it', () => {
  const zero = new Frames()
  assert.deepEqual(zero.push(joined(encode({ a: 1 }), Uint8Array.of(0, 0, 0, 0))).map(parsed), [{ a: 1 }])
  assert.equal(zero.broken, 'A frame of 0 bytes is not read.')
  assert.deepEqual(zero.push(encode({ b: 2 })), [])
  const over = new Uint8Array(4)
  new DataView(over.buffer).setUint32(0, MAX + 1)
  const frames = new Frames()
  frames.push(over)
  assert.match(frames.broken, /33554433/)
  const most = new Uint8Array(4)
  new DataView(most.buffer).setUint32(0, MAX)
  const fine = new Frames()
  assert.deepEqual(fine.push(most), [])
  assert.equal(fine.broken, null)
})

test('a value too large for a frame is not encoded', () => {
  assert.throws(() => encode({ big: 'x'.repeat(MAX) }), FrameError)
})
