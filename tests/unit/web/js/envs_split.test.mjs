import assert from 'node:assert/strict'
import { test } from 'node:test'

import { page } from './page.mjs'

page()
/** What this browser keeps. */
const store = new Map()
globalThis.localStorage = { getItem: (name) => store.get(name) ?? null, setItem: (name, value) => store.set(name, String(value)), removeItem: (name) => store.delete(name) }
const { splitter } = await import('../../../../src/hmz/web/static/views/envs/split.js')

/**
 * A list and its line on a holder `whole` wide, laid out as a stylesheet would: the list as wide
 * as the holder's `--side` says, 240px where it says nothing, and never over `cap(whole)`.
 */
function laid(whole, cap, most = cap) {
  const props = new Map()
  const holder = {
    clientWidth: whole,
    style: { setProperty: (name, value) => (value ? props.set(name, value) : props.delete(name)), getPropertyValue: (name) => props.get(name) ?? '', removeProperty: (name) => props.delete(name) },
  }
  const list = { getBoundingClientRect: () => ({ width: Math.min(cap(holder.clientWidth), parseFloat(props.get('--side') ?? '240')) }) }
  const line = splitter(holder, { name: '--side', key: 'side', label: 'Resize', most, hmz: 'split' })
  Object.defineProperty(line, 'previousElementSibling', { value: list })
  const key = (name) => line.dispatchEvent(Object.assign(new Event('keydown', { cancelable: true }), { key: name }))
  return { holder, line, key, asked: () => props.get('--side') ?? '' }
}

test('a line moved by a key sizes its list, and the width drawn is the one kept', () => {
  store.clear()
  const { line, key, asked } = laid(1000, (whole) => whole * 0.4)
  key('ArrowRight')
  assert.equal(asked(), '256px')
  assert.equal(store.get('side'), '256')
  assert.equal(line.getAttribute('aria-valuenow'), '256')
  assert.equal(line.getAttribute('aria-valuemax'), '400')
  key('End')
  assert.equal(asked(), '400px')
  assert.equal(store.get('side'), '400')
  key('Home')
  assert.equal(asked(), '160px')
  assert.equal(store.get('side'), '160')
})

test('a list its stylesheet draws narrower than was asked for is kept as wide as it is drawn', () => {
  store.clear()
  // The stylesheet holds the list to two fifths of the holder; the line is told half of it.
  const { key, asked } = laid(1000, (whole) => whole * 0.4, (whole) => whole * 0.5)
  key('End')
  assert.equal(asked(), '400px')
  assert.equal(store.get('side'), '400')
})

test('a key that moves nothing keeps nothing: the list is as wide as it was asked once there is room', () => {
  store.clear()
  store.set('side', '240')
  // The holder leaves the list 165px, less than the 240px kept.
  const { holder, line, key, asked } = laid(725, (whole) => whole - 560)
  assert.equal(asked(), '240px')
  key('ArrowRight')
  key('End')
  assert.equal(asked(), '240px')
  assert.equal(store.get('side'), '240')
  assert.equal(line.getAttribute('aria-valuenow'), '165')
  assert.equal(line.getAttribute('aria-valuemax'), '165')
  // Narrower, it is moved, and that is kept.
  key('Home')
  assert.equal(asked(), '160px')
  assert.equal(store.get('side'), '160')
  holder.clientWidth = 1045
  key('End')
  assert.equal(asked(), '485px')
})

test('a list its stylesheet holds wider than the line asks for is kept as it is drawn, and says its least', () => {
  store.clear()
  const props = new Map()
  const holder = { clientWidth: 1000, style: { setProperty: (name, value) => (value ? props.set(name, value) : props.delete(name)), getPropertyValue: (name) => props.get(name) ?? '', removeProperty: (name) => props.delete(name) } }
  const line = splitter(holder, { name: '--side', key: 'side', label: 'Resize', least: 200, most: (whole) => whole * 0.4, hmz: 'split' })
  Object.defineProperty(line, 'previousElementSibling', { value: { getBoundingClientRect: () => ({ width: Math.max(200, parseFloat(props.get('--side') ?? '340')) }) } })
  line.dispatchEvent(Object.assign(new Event('keydown', { cancelable: true }), { key: 'Home' }))
  assert.equal(props.get('--side'), '200px')
  assert.equal(store.get('side'), '200')
  assert.equal(line.getAttribute('aria-valuemin'), '200')
})

test('a line double-clicked leaves its list to its stylesheet', () => {
  store.clear()
  const { line, key, asked } = laid(1000, (whole) => whole * 0.4)
  key('ArrowRight')
  line.dispatchEvent(new Event('dblclick'))
  assert.equal(asked(), '')
  assert.equal(store.has('side'), false)
  assert.equal(line.getAttribute('aria-valuenow'), '240')
})
