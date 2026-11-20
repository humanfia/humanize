// Themes made in a browser (themes.js): one made, read from a file or forgotten is always a
// light and a dark under one key, whatever the file held of them.

import assert from 'node:assert/strict'
import { test } from 'node:test'

import { page } from './page.mjs'

page()
const held = new Map()
Object.assign(globalThis, {
  localStorage: { getItem: (name) => held.get(name) ?? null, setItem: (name, value) => void held.set(name, String(value)), removeItem: (name) => void held.delete(name) },
  CSS: { supports: (_, said) => /^#[0-9a-f]{3,8}$/i.test(said) },
  // theme.js's, which paints a side's colours and says which side that was.
  hmzPaint: (given) => given ?? { id: '', images: {} },
})

const { choose, chosen, create, imported, picture, remove, sides, themes } = await import('../../../../src/hmz/web/static/themes.js')

/** The sides this browser keeps, as they are written down. */
const kept = () => JSON.parse(held.get('hmz-themes') ?? '[]')

const PICTURE = 'data:image/png;base64,AAAA'

test('a file an earlier Humanize wrote of one side makes a theme of two, the other plain', async () => {
  const two = await imported(JSON.stringify({ hmztheme: 1, name: 'Night', base: 'dark', colors: { paper: '#102030', nothing: '#000', ink: 'no colour' }, images: { page: { fit: 'tile', data: PICTURE } } }))
  assert.deepEqual(two.map((one) => [one.base, one.name, one.colors, one.images]), [['light', 'Night', {}, {}], ['dark', 'Night', { paper: '#102030' }, { page: { fit: 'tile' } }]])
  assert.equal(two[0].pair, two[1].pair)
  assert.deepEqual(kept(), two)
  assert.deepEqual(sides(two[0].pair), two)
  assert.equal(await picture(two[1].id, 'page'), PICTURE)
  assert.equal(await picture(two[0].id, 'page'), null)
})

test('a file of both sides makes both as it says them', async () => {
  const two = await imported(JSON.stringify({ hmztheme: 1, name: 'Both', light: { colors: { paper: '#ffffff' } }, dark: { colors: { paper: '#000000' } } }))
  assert.deepEqual(two.map((one) => [one.base, one.colors]), [['light', { paper: '#ffffff' }], ['dark', { paper: '#000000' }]])
  assert.equal(new Set(two.map((one) => one.pair)).size, 1)
})

test('what holds neither both sides nor which one it is, is no theme file', async () => {
  const before = kept()
  for (const text of ['{}', 'not json', 'null', JSON.stringify({ hmztheme: 1, name: 'Half', light: { colors: {} } }), JSON.stringify({ hmztheme: 1, name: 'None', colors: {} }), JSON.stringify({ hmztheme: 2, name: 'Later', base: 'dark' })]) {
    await assert.rejects(imported(text), /This is not a theme file/)
  }
  assert.deepEqual(kept(), before)
})

test('a theme made of another copies both its sides under a key and a name of its own', async () => {
  const before = kept().length
  const from = sides(chosen())
  assert.deepEqual(from.map((one) => one.base), ['light', 'dark'])
  const two = await create(from, 'Mine')
  assert.equal(kept().length, before + 2)
  assert.deepEqual(two.map((one) => one.base), ['light', 'dark'])
  assert.equal(two[0].pair, two[1].pair)
  assert.deepEqual(two.map((one) => one.colors), from.map((one) => one.colors))
  assert.ok(themes().some((one) => one.key === two[0].pair && one.name === 'Mine' && one.mine))
  // A name taken is numbered.
  const again = await create(from, 'Mine')
  assert.deepEqual(again.map((one) => one.name), ['Mine 2', 'Mine 2'])
  assert.notEqual(again[0].pair, two[0].pair)
})

test('a theme forgotten leaves neither side, nor its pictures, and is chosen no more', async () => {
  const two = await imported(JSON.stringify({ hmztheme: 1, name: 'Gone', light: { colors: {}, images: { page: { data: PICTURE } } }, dark: { colors: { paper: '#000000' } } }))
  const key = two[0].pair
  const others = kept().filter((one) => one.pair !== key)
  choose(key)
  assert.equal(chosen(), key)

  await remove(key)

  assert.deepEqual(kept(), others)
  assert.deepEqual(sides(key), [])
  assert.equal(held.has('hmz-pair'), false)
  assert.equal(chosen(), 'humanize')
  assert.equal(await picture(two[0].id, 'page'), null)
  // Every theme left has its two sides still.
  for (const one of themes()) assert.deepEqual(sides(one.key).map((it) => it.base), ['light', 'dark'])
})
