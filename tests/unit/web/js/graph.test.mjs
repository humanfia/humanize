import assert from 'node:assert/strict'
import { test } from 'node:test'

import { page } from './page.mjs'

page()

const { abreast, fit } = await import('../../../../src/hmz/web/static/graph.js')

/** A control in a corner of the view: the zoom's 128 by 30, 12 from its edges. */
const corner = { width: 152, height: 54 }
/** Three agents in one flow, two side by side and a person under them, with the room for their bows. */
const frames = { width: 702, height: 414 }
const stage = { width: 758, height: 694 }
/** The same three, one over another, as a narrow view lays them out. */
const stacked = { frames: { width: 304, height: 654 }, stage: { width: 558, height: 808 } }

/** Where the frames stand in a view, fitted and in its middle. */
function placed(view, of = { frames, stage }) {
  const at = fit(view, of.stage, of.frames, corner)
  const wide = of.frames.width * at
  const tall = of.frames.height * at
  return { at, left: (view.width - wide) / 2, right: (view.width + wide) / 2, top: (view.height - tall) / 2, bottom: (view.height + tall) / 2 }
}

/** Whether the frames are whole in the view and under no control in a corner of it. */
function clear(view, { left, right, top, bottom }) {
  const whole = left >= 16 && top >= 16 && right <= view.width - 16 && bottom <= view.height - 16
  const beside = left >= corner.width && right <= view.width - corner.width
  const between = top >= corner.height && bottom <= view.height - corner.height
  return whole && (beside || between)
}

test('a view with the room draws a graph at its own size, the room round its frames kept', () => {
  assert.equal(fit({ width: 1000, height: 816 }, stage, frames, corner), 1)
  // No wider than the view, the room at its sides counted.
  assert.equal(fit({ width: 685, height: 816 }, stage, frames, corner), (685 - 32) / stage.width)
  // A view a little short shrinks it to keep the room over and under it.
  assert.equal(fit({ width: 1000, height: 500 }, stage, frames, corner), (500 - 32) / stage.height)
})

test('a view too short for the room fits the frames alone, every one whole and clear of the corners', () => {
  for (const view of [{ width: 685, height: 260 }, { width: 685, height: 180 }, { width: 1400, height: 260 }]) {
    const at = placed(view)
    assert.ok(at.at <= 0.55, `${view.width}x${view.height}: ${at.at}`)
    assert.ok(clear(view, at), `${view.width}x${view.height}: ${JSON.stringify(at)}`)
  }
  // Wide enough to stand between the corners' columns, it is no smaller than its height asks.
  assert.equal(fit({ width: 1400, height: 240 }, stage, frames, corner), (240 - 32) / frames.height)
})

test('a narrow, short view fits agents stacked one over another', () => {
  for (const view of [{ width: 390, height: 260 }, { width: 405, height: 260 }, { width: 320, height: 260 }]) {
    const at = placed(view, stacked)
    assert.ok(clear(view, at), `${view.width}x${view.height}: ${JSON.stringify(at)}`)
  }
})

test('a graph is never fitted smaller than it can be zoomed out to', () => {
  assert.equal(fit({ width: 300, height: 120 }, { width: 5000, height: 9000 }, { width: 4900, height: 8600 }, corner), 0.2)
})

test('a view tall enough to drag through keeps a graph readable, however tall the graph', () => {
  const tall = { frames: { width: 702, height: 900 }, stage: { width: 758, height: 1180 } }
  for (const view of [{ width: 1000, height: 600 }, { width: 800, height: 320 }]) assert.equal(fit(view, tall.stage, tall.frames, corner), 0.55)
  // Only a strip, too short to stand two nodes one over another, has it whole and smaller.
  assert.equal(fit({ width: 1000, height: 319 }, tall.stage, tall.frames, corner), (319 - 32) / tall.frames.height)
})

test('agents stand side by side as the view has the width for, and two in any view shorter than wide', () => {
  assert.deepEqual([[330, 600], [390, 700], [700, 760], [1100, 700], [2000, 900]].map(([width, height]) => abreast({ width, height })), [1, 1, 2, 4, 4])
  assert.deepEqual([[390, 260], [405, 260], [685, 260]].map(([width, height]) => abreast({ width, height })), [2, 2, 2])
})
