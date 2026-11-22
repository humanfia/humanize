import assert from 'node:assert/strict'
import { test } from 'node:test'

import { load, spanAt } from '../../../../src/hmz/web/static/views/exomyth/model.js'

/** One track of one depth, read as the page reads it: its spans as [start, dur], ids from 10. */
function track(spans) {
  const nought = spans.map(() => 0)
  const process = { id: 0, kind: 'session', parent: -1, pid: 0, start: 0, end: 0, name: 0, key: 0, agent: 0, role: 0, backend: 0, model: 0, label: 0, record: 0, tracks: [0] }
  const columns = { start: spans.map(([start]) => start), dur: spans.map(([, dur]) => dur), depth: nought, cat: nought, name: nought, model: nought, in: nought, out: nought }
  const held = { process: 0, name: 0, first: 10, count: spans.length, depths: 1, spans: columns }
  return load({ version: 1, layout: '', epic: '', origin: 0, live: false, strings: [''], processes: [process], tracks: [held], summary: { end: 1 } }).tracks[0]
}

test('the span pointed at is the one the pointer is on, however near it the one before ended', () => {
  // A read, a thought and an edit, each starting as the last ends, drawn a few pixels wide.
  const held = track([[0, 700], [700, 1], [701, 1100]])
  assert.equal(spanAt(held, 0, 350, 600), 10)
  assert.equal(spanAt(held, 0, 1250, 600), 12)
})

test('a span too narrow to point at is taken from beside it, and nothing from further off', () => {
  const held = track([[1000, 1], [5000, 1]])
  assert.equal(spanAt(held, 0, 990, 20), 10)
  assert.equal(spanAt(held, 0, 1015, 20), 10)
  assert.equal(spanAt(held, 0, 3000, 20), null)
  assert.equal(spanAt(held, 0, 6000, 20), null)
  assert.equal(spanAt(held, 1, 1000, 20), null)
})
