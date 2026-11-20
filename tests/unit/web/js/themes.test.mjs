// Themes: what an earlier Humanize kept of them in a browser is kept as this one keeps them
// (themed.js) -- a theme always has a light and a dark and is chosen whole -- the side of it
// that is drawn is the one chosen, or under Auto the system's, before the page is (theme.js),
// and every theme Humanize comes with is named in the page's language.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'

import { OWN, PAIRS } from '../../../../src/hmz/web/static/presets.js'
import { migrated } from '../../../../src/hmz/web/static/themed.js'

/** Ids as they are made, in order: `p1`, `t2`, … */
function how(name = 'Custom') {
  let n = 0
  return { fresh: (kind) => `${kind}${++n}`, name }
}

const side = (id, base, more = {}) => ({ id, name: 'Night', base, colors: { paper: base === 'dark' ? '#102030' : '#fff8e0' }, images: {}, ...more })

test('a browser that holds nothing of an earlier Humanize is left as it is', () => {
  assert.equal(migrated({}, OWN, how()), null)
  assert.equal(migrated({ pair: 'peaceful-lilac', themes: [side('a', 'light', { pair: 'p' }), side('b', 'dark', { pair: 'p' })] }, OWN, how()), null)
})

test('a theme of one side gets the other, plain, under the same name', () => {
  const lone = side('a', 'dark', { images: { page: { fit: 'tile' } } })
  const was = migrated({ themes: [lone] }, OWN, how())
  assert.deepEqual(was, {
    pair: null,
    mode: null,
    themes: [
      { ...lone, pair: 'p1' },
      { id: 't2', name: 'Night', base: 'light', pair: 'p1', colors: {}, images: {} },
    ],
    copies: [],
  })
  // Its pictures stay under the id it had: nothing is copied.
  assert.equal(was.themes[0].id, 'a')
})

test('half of a theme of two sides gets the half it lost', () => {
  const was = migrated({ themes: [side('a', 'light', { pair: 'mine' })] }, OWN, how())
  assert.deepEqual(was.themes.map((one) => [one.id, one.base, one.pair]), [['a', 'light', 'mine'], ['t1', 'dark', 'mine']])
})

test('one side chosen outright chooses the theme it is a side of, shown on that side', () => {
  assert.deepEqual(migrated({ theme: 'devoted-pink-light' }, OWN, how()), { pair: 'devoted-pink', mode: 'light', themes: [], copies: [] })
  // Humanize's own is chosen by nothing kept, and so is a side that is gone, which shows none.
  assert.deepEqual(migrated({ theme: 'dark' }, OWN, how()), { pair: null, mode: 'dark', themes: [], copies: [] })
  assert.deepEqual(migrated({ theme: 'gone' }, OWN, how()), { pair: null, mode: null, themes: [], copies: [] })
  // A theme of one side, chosen: the theme it became.
  const was = migrated({ theme: 'a', light: 'critical-teal-light', themes: [side('a', 'dark')] }, OWN, how())
  assert.equal(was.pair, 'p1')
  assert.equal(was.mode, 'dark')
  assert.equal(was.themes.length, 2)
})

test('the light and the dark of one theme, followed with the system, choose that theme', () => {
  assert.deepEqual(migrated({ light: 'peaceful-lilac-light', dark: 'peaceful-lilac-dark' }, OWN, how()), { pair: 'peaceful-lilac', mode: null, themes: [], copies: [] })
  const two = [side('a', 'light', { pair: 'mine' }), side('b', 'dark', { pair: 'mine' })]
  assert.deepEqual(migrated({ light: 'a', dark: 'b', themes: two }, OWN, how()), { pair: 'mine', mode: null, themes: two, copies: [] })
})

test('two sides picked apart become one theme of the user’s own, as they were seen', () => {
  const night = side('a', 'dark', { images: { page: { fit: 'cover' } } })
  const was = migrated({ light: 'hateful-silver-light', dark: 'a', themes: [night] }, OWN, how())
  const silver = OWN.find((one) => one.id === 'hateful-silver-light')
  assert.equal(was.pair, 'p3')
  // Followed with the system then, they are now.
  assert.equal(was.mode, null)
  assert.deepEqual(was.themes.slice(2), [
    { id: 't4', name: 'Custom', base: 'light', pair: 'p3', colors: silver.colors, images: {} },
    { id: 't5', name: 'Custom', base: 'dark', pair: 'p3', colors: night.colors, images: { page: { fit: 'cover' } } },
  ])
  // What is copied is the user's from then on: changing it changes nothing it was copied from.
  assert.notEqual(was.themes[2].colors, silver.colors)
  assert.notEqual(was.themes[3].images.page, night.images.page)
  // The pictures of the side that has any are copied under the new side's id.
  assert.deepEqual(was.copies, [['a', 't5']])

  // Only one of the two picked: the other is Humanize's own, and a dark picked for the light is
  // kept as the light it was shown as.
  const half = migrated({ light: 'critical-teal-dark' }, OWN, how())
  assert.deepEqual(half.themes.map((one) => [one.base, Object.keys(one.colors).length > 0]), [['light', true], ['dark', false]])
  assert.equal(half.pair, 'p1')
})

test('a theme made of two picked apart takes a name no theme made here has', () => {
  const was = migrated({ light: 'critical-teal-light', themes: [side('a', 'light', { pair: 'x', name: 'Mixed' }), side('b', 'dark', { pair: 'x', name: 'Mixed' })] }, OWN, how('Mixed'))
  assert.equal(was.themes.at(-1).name, 'Mixed 2')
})

test('a theme already chosen whole stays chosen, whatever an earlier Humanize left', () => {
  assert.deepEqual(migrated({ pair: 'surviving-jade', theme: 'devoted-pink-dark', light: 'critical-teal-light' }, OWN, how()), { pair: 'surviving-jade', mode: 'dark', themes: [], copies: [] })
})

/** What theme.js draws, as the page is read, in a browser that keeps `kept` on a system that is dark or not. */
function drawn(kept, dark) {
  const style = []
  style.setProperty = (name, value) => style.push(name) && (style[name] = value)
  style.removeProperty = (name) => style.splice(style.indexOf(name), 1) && delete style[name]
  const root = { dataset: {}, style }
  const window = {}
  vm.runInNewContext(readFileSync(new URL('../../../../src/hmz/web/static/theme.js', import.meta.url), 'utf8'), {
    window,
    document: { documentElement: root },
    navigator: { userAgent: 'Mozilla/5.0' },
    localStorage: { getItem: (name) => kept[name] ?? null },
    matchMedia: (query) => ({ matches: query === '(prefers-color-scheme: dark)' && dark }),
  })
  return { side: root.dataset.theme, paper: style['--paper'] ?? null, paint: window.hmzPaint, root }
}

test('the side chosen is drawn whatever the system asks for, and Auto, or none chosen, follows it', () => {
  const lilac = OWN.filter((one) => one.pair === 'peaceful-lilac')
  const [light, dark] = lilac.map((one) => one.colors.paper)
  const kept = (mode) => ({ 'hmz-pair': 'peaceful-lilac', 'hmz-painted': JSON.stringify(lilac), ...(mode ? { 'hmz-mode': mode } : {}) })
  for (const system of [false, true]) {
    assert.deepEqual([drawn(kept('light'), system).side, drawn(kept('light'), system).paper], ['light', light])
    assert.deepEqual([drawn(kept('dark'), system).side, drawn(kept('dark'), system).paper], ['dark', dark])
    // None kept is Auto, and so is anything else a browser holds there.
    for (const auto of [null, 'auto', 'sepia']) assert.deepEqual([drawn(kept(auto), system).side, drawn(kept(auto), system).paper], system ? ['dark', dark] : ['light', light])
  }
  // Humanize's own, where no theme is chosen, has its two sides as well.
  assert.deepEqual([drawn({ 'hmz-mode': 'dark' }, false).side, drawn({ 'hmz-mode': 'dark' }, false).paper], ['dark', null])
  assert.equal(drawn({ 'hmz-mode': 'light' }, true).side, 'light')
  // A side being edited is drawn as it is given, whichever is chosen.
  const page = drawn(kept('light'), false)
  page.paint(lilac[1])
  assert.equal(page.root.dataset.theme, 'dark')
})

test('the choice of the side is one of three, Auto first, each said in the page’s language', () => {
  const view = readFileSync(new URL('../../../../src/hmz/web/static/views/settings/themes.js', import.meta.url), 'utf8')
  const table = view.slice(view.indexOf('const MODES = ['), view.indexOf('\n]', view.indexOf('const MODES = [')))
  assert.deepEqual([...table.matchAll(/^ {2}\['(\w+)', t\('(\w+)'\)\],$/gm)].map(([, mode, said]) => [mode, said]), [['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']])
})

test('every theme Humanize comes with is named in the page’s language, as its data names it', () => {
  const view = readFileSync(new URL('../../../../src/hmz/web/static/views/settings/themes.js', import.meta.url), 'utf8')
  const table = view.slice(view.indexOf('const NAMES = {'), view.indexOf('\n}', view.indexOf('const NAMES = {')))
  const named = [...table.matchAll(/^ {2}'([^']+)': t\('([^']+)'\),$/gm)]
  assert.deepEqual(named.map(([, name]) => name), PAIRS.map((pair) => pair.name))
  for (const [, name, said] of named) assert.equal(said, name)
  // Each has its two sides, a light and a dark.
  for (const pair of PAIRS) assert.deepEqual(OWN.filter((one) => one.pair === pair.key).map((one) => one.base), ['light', 'dark'])
})
