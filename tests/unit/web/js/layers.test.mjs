import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'

// The page's document and window, as far as the chain's listeners use them: what each listens
// for is kept, to be said as the browser would say it.
const heard = { document: {}, window: {} }
const told = []
globalThis.document = { activeElement: null, addEventListener: (type, fn) => (heard.document[type] = fn) }
globalThis.window = { dispatchEvent: (event) => told.push(event.detail) }
globalThis.addEventListener = (type, fn) => (heard.window[type] = fn)
globalThis.removeEventListener = () => {}
globalThis.innerWidth = 1000
globalThis.innerHeight = 800
/** What waits for the next frame, run as `frame()` says one came. */
const waiting = []
globalThis.requestAnimationFrame = (fn) => waiting.push(fn)
const frame = () => waiting.splice(0).forEach((fn) => fn())

const { chain, closed, dismiss, opened, tipping, yields } = await import('../../../../src/hmz/web/static/layers.js')

/** A thing in the page: inside `parent`, with the box it is given, taking the focus when asked. */
function el(name, parent = null, box = { left: 10, top: 10, width: 100, height: 20 }) {
  const node = {
    name,
    parent,
    contains(other) {
      for (let at = other; at; at = at.parent) if (at === node) return true
      return false
    },
    focus() {
      document.activeElement = node
    },
    getBoundingClientRect: () => ({ ...box, right: box.left + box.width, bottom: box.top + box.height }),
  }
  return node
}

/** What closed, in the order it did. */
let log = []

/**
 * A layer opened, a frame ago unless `fresh`: its node inside `inside`, by `anchor`; its closer
 * says so first, as an owner's does.
 */
function layer(name, { anchor = null, inside = null, kind, back, quiet = false, fresh = false } = {}) {
  const one = { name, node: el(name, inside), anchor, kind, back, open: true }
  one.close = () => {
    if (!one.open) return
    if (!quiet) closed(one)
    one.open = false
    log.push(name)
  }
  opened(one)
  if (!fresh) frame()
  return one
}

const names = () => chain().map((one) => one.name)
const key = (name, target) => {
  const event = { key: name, target, prevented: false, stopped: false, preventDefault: () => (event.prevented = true), stopImmediatePropagation: () => (event.stopped = true) }
  heard.document.keydown(event)
  return event
}

/** What a press set going is over by the next turn. */
const settled = () => new Promise((resolve) => setTimeout(resolve))

afterEach(async () => {
  frame()
  dismiss('route')
  tipping(() => {})
  document.activeElement = null
  log = []
  await settled()
})

test('one opening closes every other it was not opened from', () => {
  const bell = el('bell')
  layer('notifications', { anchor: bell })
  layer('daemon', { anchor: el('daemon-bar') })
  assert.deepEqual(names(), ['daemon'])
  assert.deepEqual(log, ['notifications'])
  // One at the pointer stands by nothing, and is opened from nothing.
  layer('context')
  assert.deepEqual(names(), ['context'])
})

test('one opened from inside another keeps it, and closes what else was opened from it', () => {
  const root = layer('model', { anchor: el('chip') })
  const effort = layer('effort', { anchor: el('effort-opener', root.node), inside: root.node })
  assert.deepEqual(names(), ['model', 'effort'])
  const more = layer('more', { anchor: el('more-opener', root.node), inside: root.node })
  assert.deepEqual(names(), ['model', 'more'])
  assert.equal(effort.open, false)
  layer('account', { anchor: el('account-opener', more.node), inside: more.node })
  assert.deepEqual(names(), ['model', 'more', 'account'])
  // A sibling of the first submenu closes it and what was opened from it, the topmost first.
  log = []
  layer('effort', { anchor: el('effort-opener', root.node), inside: root.node })
  assert.deepEqual(log, ['account', 'more'])
  assert.deepEqual(names(), ['model', 'effort'])
})

test('one said twice is in the chain once, and the chain given is a copy', () => {
  const one = layer('menu', { anchor: el('button') })
  opened(one)
  assert.equal(chain().length, 1)
  chain().pop()
  assert.equal(chain().length, 1)
})

test('one closed takes what was opened from it, and a second closing does nothing', () => {
  const root = layer('root', { anchor: el('button') })
  const sub = layer('sub', { anchor: el('opener', root.node), inside: root.node })
  root.close()
  assert.deepEqual(log, ['sub', 'root'])
  assert.deepEqual(names(), [])
  root.close()
  sub.close()
  closed(root)
  assert.deepEqual(log, ['sub', 'root'])
})

test('one whose closer does not say it closed leaves the chain all the same', () => {
  layer('mute', { anchor: el('button'), quiet: true })
  dismiss('dialog')
  assert.deepEqual(names(), [])
  assert.deepEqual(log, ['mute'])
})

test('the page gone elsewhere, a dialog and the sidebar folded close everything', () => {
  for (const why of ['route', 'dialog', 'fold']) {
    const root = layer('form', { anchor: el('chip'), kind: 'panel' })
    layer('picker', { anchor: el('browse', root.node), inside: root.node })
    dismiss(why)
    assert.deepEqual(names(), [], why)
  }
})

test('the window left closes menus and keeps a panel, with what was typed into it', () => {
  const form = layer('form', { anchor: el('chip'), kind: 'panel' })
  layer('picker', { anchor: el('browse', form.node), inside: form.node })
  dismiss('blur')
  assert.deepEqual(names(), ['form'])
  // A panel opened from a menu goes with the menu.
  dismiss('route')
  const menu = layer('menu', { anchor: el('button') })
  layer('panel', { anchor: el('field', menu.node), inside: menu.node, kind: 'panel' })
  dismiss('blur')
  assert.deepEqual(names(), [])
})

test('a menu whose field is being typed into is kept as a panel is, with the menus it was opened from', () => {
  const model = layer('model', { anchor: el('chip') })
  const more = layer('more', { anchor: el('opener', model.node), inside: model.node })
  layer('account', { anchor: el('account', more.node), inside: more.node })
  const field = { ...el('field', more.node), matches: (what) => what.includes('input') }
  document.activeElement = field
  dismiss('blur')
  assert.deepEqual(names(), ['model', 'more'])
  dismiss('resize')
  assert.deepEqual(names(), ['model', 'more'])
  // Not once the focus is on a choice again.
  document.activeElement = { ...el('choice', more.node), matches: () => false }
  dismiss('blur')
  assert.deepEqual(names(), [])
})

test('the window sized closes menus, and a panel only where what opened it has no box left', () => {
  layer('menu', { anchor: el('button') })
  dismiss('resize')
  assert.deepEqual(names(), [])
  layer('form', { anchor: el('chip'), kind: 'panel' })
  dismiss('resize')
  assert.deepEqual(names(), ['form'])
  dismiss('route')
  layer('form', { anchor: el('chip', null, { left: -400, top: 10, width: 100, height: 20 }), kind: 'panel' })
  dismiss('resize')
  assert.deepEqual(names(), [])
  layer('form', { anchor: el('chip', null, { left: 10, top: 10, width: 0, height: 0 }), kind: 'panel' })
  dismiss('resize')
  assert.deepEqual(names(), [])
})

test('one drawn no more is let go of without a key or a press spent on it', () => {
  const stale = layer('stale', { anchor: el('button') })
  stale.node.isConnected = false
  assert.deepEqual(names(), [])
  assert.equal(stale.open, false)
  const hidden = layer('hidden', { anchor: el('button') })
  hidden.node.getClientRects = () => []
  const event = key('Escape', el('page'))
  assert.equal(event.stopped, false)
  assert.equal(hidden.open, false)
})

test('the tooltip comes down whenever one opens or all are dismissed, and at every press, key and scroll', () => {
  let hidden = 0
  tipping(() => hidden++)
  layer('menu', { anchor: el('button') })
  assert.equal(hidden, 1)
  for (const why of ['route', 'dialog', 'fold', 'resize', 'blur']) dismiss(why)
  assert.equal(hidden, 6)
  heard.document.pointerdown({ target: el('page') })
  key('a', el('page'))
  heard.document.scroll({ target: el('list') })
  assert.equal(hidden, 9)
})

test('completions yield to one opening, the page going elsewhere and a dialog, and to nothing else', () => {
  let shut = 0
  const stop = yields(() => shut++)
  for (const why of ['fold', 'resize', 'blur']) dismiss(why)
  assert.equal(shut, 0)
  layer('menu', { anchor: el('chip') })
  assert.equal(shut, 1)
  dismiss('route')
  dismiss('dialog')
  assert.equal(shut, 3)
  // Open, they claim no place in the chain.
  assert.deepEqual(names(), [])
  stop()
  layer('menu', { anchor: el('chip') })
  assert.equal(shut, 3)
})

test('a press outside closes the chain, one inside a layer only what was opened from it', () => {
  const chip = el('chip')
  const root = layer('root', { anchor: chip })
  const opener = el('opener', root.node)
  layer('sub', { anchor: opener, inside: root.node })
  heard.document.pointerdown({ target: el('choice', root.node) })
  assert.deepEqual(names(), ['root'])
  const sub = layer('sub', { anchor: opener, inside: root.node })
  // On what opened one, it is that one's to answer: pressed again, it closes it.
  heard.document.pointerdown({ target: opener })
  assert.deepEqual(names(), ['root', 'sub'])
  heard.document.pointerdown({ target: el('inner', sub.node) })
  assert.deepEqual(names(), ['root', 'sub'])
  heard.document.pointerdown({ target: chip })
  assert.deepEqual(names(), ['root'])
  heard.document.pointerdown({ target: el('page') })
  assert.deepEqual(names(), [])
})

test('Escape closes the topmost alone and goes no further, and with none open is left alone', () => {
  const root = layer('root', { anchor: el('chip') })
  layer('sub', { anchor: el('opener', root.node), inside: root.node })
  const first = key('Escape', root.node)
  assert.deepEqual(names(), ['root'])
  assert.ok(first.stopped && first.prevented)
  key('Escape', root.node)
  assert.deepEqual(names(), [])
  const third = key('Escape', el('page'))
  assert.ok(!third.stopped && !third.prevented)
  // What is being composed is the input method's, Escape included.
  layer('root', { anchor: el('chip') })
  heard.document.keydown({ key: 'Escape', isComposing: true, target: el('field') })
  assert.deepEqual(names(), ['root'])
})

test('the focus gone elsewhere closes down to the layer that holds it; one from nowhere closes nothing', () => {
  const chip = el('chip')
  const root = layer('root', { anchor: chip })
  const choice = el('choice', root.node)
  layer('sub', { anchor: el('opener', root.node), inside: root.node })
  heard.document.focusin({ target: el('elsewhere'), relatedTarget: null })
  assert.deepEqual(names(), ['root', 'sub'])
  heard.document.focusin({ target: choice, relatedTarget: el('sub-choice') })
  assert.deepEqual(names(), ['root'])
  // Back on what opened it, it stays open.
  heard.document.focusin({ target: chip, relatedTarget: choice })
  assert.deepEqual(names(), ['root'])
  heard.document.focusin({ target: el('elsewhere'), relatedTarget: chip })
  assert.deepEqual(names(), [])
})

test('the focus a press moves closes nothing more than the press did', async () => {
  const root = layer('root', { anchor: el('chip') })
  const choice = el('choice', root.node)
  // A browser that gives a button pressed no focus puts it on whatever holds the button.
  heard.document.pointerdown({ target: choice })
  heard.document.focusin({ target: el('page'), relatedTarget: choice })
  assert.deepEqual(names(), ['root'])
  // A finger's goes as its press ends, after the mouse press the browser makes of it.
  await settled()
  heard.document.mousedown({ target: choice })
  heard.document.focusin({ target: el('page'), relatedTarget: choice })
  assert.deepEqual(names(), ['root'])
  // Let go of, the press moves it no more: what the click does with the focus is as any code's.
  heard.document.mouseup({ target: choice })
  heard.document.focusin({ target: el('page'), relatedTarget: choice })
  assert.deepEqual(names(), [])
})

test('a scroll that takes away what a layer stands by closes it; one inside a layer closes nothing', () => {
  const list = el('list')
  const button = el('button', list)
  const root = layer('root', { anchor: button, inside: list })
  const opener = el('opener', root.node)
  layer('sub', { anchor: opener, inside: root.node })
  heard.document.scroll({ target: el('transcript') })
  assert.deepEqual(names(), ['root', 'sub'])
  // The menu's own choices scrolled take the submenu's opener away, not the menu's.
  heard.document.scroll({ target: root.node })
  assert.deepEqual(names(), ['root'])
  heard.document.scroll({ target: list })
  assert.deepEqual(names(), [])
  // One at the pointer stands by nothing: any scroll but its own, or one inside what it opened, closes it.
  const context = layer('context')
  const inner = layer('inner', { anchor: el('opener', context.node), inside: context.node })
  heard.document.scroll({ target: inner.node })
  assert.deepEqual(names(), ['context', 'inner'])
  heard.document.scroll({ target: el('transcript') })
  assert.deepEqual(names(), [])
  // A panel that stands by nothing stands in its pane, whatever scrolls beside it.
  layer('palette', { kind: 'panel' })
  heard.document.scroll({ target: el('transcript') })
  assert.deepEqual(names(), ['palette'])
})

test('a scroll told of in the frame one opened in happened before it, and closes nothing', () => {
  const list = el('list')
  layer('menu', { anchor: el('button', list), inside: list, fresh: true })
  heard.document.scroll({ target: list })
  assert.deepEqual(names(), ['menu'])
  frame()
  heard.document.scroll({ target: list })
  assert.deepEqual(names(), [])
})

test('the window sized, left, and the page gone elsewhere are heard on the window', () => {
  layer('menu', { anchor: el('button') })
  heard.window.resize()
  assert.deepEqual(names(), [])
  layer('menu', { anchor: el('button') })
  heard.window.blur()
  assert.deepEqual(names(), [])
  layer('form', { anchor: el('chip'), kind: 'panel' })
  heard.window['hmz:route']()
  assert.deepEqual(names(), [])
})

test('the focus one held goes back to what opened it, unless a press or the focus elsewhere closed it', () => {
  const chip = el('chip')
  const root = layer('root', { anchor: chip })
  const choice = el('choice', root.node)
  // By a choice, the same button or Escape.
  choice.focus()
  root.close()
  assert.equal(document.activeElement, chip)
  // The focus elsewhere already is left where it is.
  const other = el('field')
  const again = layer('root', { anchor: chip })
  other.focus()
  again.close()
  assert.equal(document.activeElement, other)
  // A press outside puts the focus where it lands.
  const third = layer('root', { anchor: chip })
  const held = el('choice', third.node)
  held.focus()
  heard.document.pointerdown({ target: el('page') })
  assert.equal(document.activeElement, held)
  // One opened by a key gives it back to what the key was pressed on.
  const search = el('search')
  const context = layer('context', { back: search })
  el('choice', context.node).focus()
  key('Escape', context.node)
  assert.equal(document.activeElement, search)
  // A submenu closed alone gives it to the choice that opened it; the page gone elsewhere, to the root's.
  const model = layer('model', { anchor: chip })
  const opener = el('opener', model.node)
  const sub = layer('sub', { anchor: opener, inside: model.node })
  el('choice', sub.node).focus()
  key('Escape', sub.node)
  assert.equal(document.activeElement, opener)
  const deep = layer('sub', { anchor: opener, inside: model.node })
  el('choice', deep.node).focus()
  dismiss('route')
  assert.equal(document.activeElement, chip)
})

test('the focus nothing holds goes to what opened one its owner or Escape closed, and nowhere otherwise', () => {
  const chip = el('chip')
  // A choice drawn again, or pressed in a browser that gives it no focus, leaves it nowhere.
  layer('root', { anchor: chip }).close()
  assert.equal(document.activeElement, chip)
  document.activeElement = null
  layer('root', { anchor: chip })
  key('Escape', el('page'))
  assert.equal(document.activeElement, chip)
  document.activeElement = null
  layer('root', { anchor: chip })
  dismiss('route')
  assert.equal(document.activeElement, null)
  layer('root', { anchor: chip })
  layer('other', { anchor: el('bell') })
  assert.equal(document.activeElement, null)
})

test('a layer whose focus a press put outside the chain gives it back as one that holds it', () => {
  const chip = el('chip')
  const root = layer('root', { anchor: chip })
  const first = el('first', root.node)
  const page = el('page')
  first.focus()
  // The choice pressed takes no focus: the browser puts it on the page that holds the menu.
  heard.document.pointerdown({ target: el('choice', root.node) })
  page.focus()
  heard.document.focusin({ target: page, relatedTarget: first })
  root.close()
  assert.equal(document.activeElement, chip)
  // Not once the focus was put elsewhere on purpose.
  const again = layer('root', { anchor: chip })
  const held = el('first', again.node)
  held.focus()
  heard.document.pointerdown({ target: el('choice', again.node) })
  page.focus()
  heard.document.focusin({ target: page, relatedTarget: held })
  const field = el('field')
  field.focus()
  heard.document.focusin({ target: field, relatedTarget: null })
  again.close()
  assert.equal(document.activeElement, field)
})

test('every change of the chain is told once its owners are done, with how many are open', async () => {
  told.length = 0
  const root = layer('root', { anchor: el('chip') })
  layer('sub', { anchor: el('opener', root.node), inside: root.node })
  assert.deepEqual(told, [])
  await null
  assert.deepEqual(told, [2])
  root.close()
  await null
  assert.deepEqual(told, [2, 0])
})

test('the arrow keys, Home and End move through the choices of the menu the focus is in', () => {
  const items = []
  const menu = { closest: () => menu, matches: () => false, querySelectorAll: () => items }
  const item = (name) => {
    const one = { name, closest: () => menu, matches: () => false, focus: () => (document.activeElement = one) }
    items.push(one)
    return one
  }
  const [first, second, last] = [item('first'), item('second'), item('last')]
  const press = (name, target, more = {}) => {
    const event = { key: name, target, prevented: false, preventDefault: () => (event.prevented = true), ...more }
    heard.document.keydown(event)
    return event
  }
  assert.ok(press('ArrowDown', first).prevented)
  assert.equal(document.activeElement, second)
  press('ArrowDown', last)
  assert.equal(document.activeElement, first)
  press('ArrowUp', first)
  assert.equal(document.activeElement, last)
  press('Home', last)
  assert.equal(document.activeElement, first)
  press('End', first)
  assert.equal(document.activeElement, last)
  // From what is not a choice -- a field over them -- down is the first and up the last.
  const field = { closest: () => menu, matches: (what) => what === 'input' }
  press('ArrowDown', field)
  assert.equal(document.activeElement, first)
  press('ArrowUp', field)
  assert.equal(document.activeElement, last)
  // Its Home and End are its text's, and a key held with another is not the menu's.
  assert.ok(!press('Home', field).prevented)
  assert.ok(!press('ArrowDown', last, { metaKey: true }).prevented)
  // Outside a menu the keys are whatever they were.
  assert.ok(!press('ArrowDown', { closest: () => null, matches: () => false }).prevented)
})
