import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'

// The page's document, as far as a question asked by its button and the chain's listeners use
// it: elements that hold others, have a box, are pressed and take the focus, and what the
// document listens for.
class Node {}
class Element extends Node {
  constructor(tag) {
    super()
    this.tag = tag
    this.kids = []
    this.parent = null
    this.heard = {}
    this.attributes = {}
    this.disabled = false
    this.said = ''
    this.style = { setProperty: (name, value) => (this.style[name] = value), removeProperty: (name) => delete this.style[name] }
    this.offsetWidth = 200
    this.offsetHeight = 40
  }
  setAttribute(name, value) {
    this.attributes[name] = value
  }
  addEventListener(type, fn) {
    ;(this.heard[type] ||= []).push(fn)
  }
  append(...kids) {
    for (const kid of kids) {
      kid.parent = this
      this.kids.push(kid)
    }
  }
  after(kid) {
    kid.parent = this.parent
    this.parent.kids.splice(this.parent.kids.indexOf(this) + 1, 0, kid)
  }
  /** What held the focus and is taken out of the page leaves it with the page, as a browser does. */
  remove() {
    if (this.contains(document.activeElement)) document.activeElement = document.body
    this.parent.kids.splice(this.parent.kids.indexOf(this), 1)
    this.parent = null
  }
  replaceChildren() {
    for (const kid of [...this.kids]) kid instanceof Element ? kid.remove() : (kid.parent = null)
    this.kids = []
  }
  get isConnected() {
    return this === document.body || Boolean(this.parent?.isConnected)
  }
  get textContent() {
    return this.said + this.kids.map((kid) => kid.textContent).join('')
  }
  set textContent(said) {
    this.replaceChildren()
    this.said = said
  }
  contains(other) {
    for (let at = other; at; at = at.parent) if (at === this) return true
    return false
  }
  closest() {
    return null
  }
  /** In the far half of a window 1000 wide. */
  getBoundingClientRect() {
    return { left: 800, top: 100, right: 880, bottom: 128 }
  }
  /** Every button within, in the order drawn: all the page asks for is `button` and `button:enabled`. */
  querySelectorAll(what) {
    const found = this.kids.flatMap((kid) => (kid instanceof Element ? [...(kid.tag === 'button' ? [kid] : []), ...kid.querySelectorAll('button')] : []))
    return what.endsWith(':enabled') ? found.filter((one) => !one.disabled) : found
  }
  querySelector(what) {
    return this.querySelectorAll(what)[0] ?? null
  }
  focus() {
    document.activeElement = this
  }
  /** A press: told to the thing pressed, then to each thing that held it as it was pressed. */
  click() {
    if (this.disabled) return
    const path = []
    for (let at = this; at; at = at.parent) path.push(at)
    for (const at of path) for (const fn of at.heard.click || []) fn({ target: this })
  }
}
class Text extends Node {
  constructor(said) {
    super()
    this.textContent = said
  }
}

const heard = {}
globalThis.Node = Node
globalThis.document = {
  body: new Element('body'),
  activeElement: null,
  createElement: (tag) => new Element(tag),
  createTextNode: (said) => new Text(said),
  addEventListener: (type, fn) => (heard[type] = fn),
}
globalThis.window = { dispatchEvent: () => {} }
globalThis.addEventListener = () => {}
globalThis.removeEventListener = () => {}

globalThis.innerWidth = 1000
globalThis.innerHeight = 800

const { chain, dismiss, opened } = await import('../../../../src/hmz/web/static/layers.js')
const { confirming } = await import('../../../../src/hmz/web/static/confirm.js')

/** A question's button in the page, what it asks while it does, and what its answer did. */
function question(how = {}) {
  const done = []
  const holder = confirming({ label: 'Stop', ask: 'Stop this epic?', yes: 'Stop', act: async () => done.push('stopped'), ...how })
  document.body.append(holder)
  const button = holder.querySelector('button')
  const asked = () => chain().find((one) => one.anchor === button)?.node ?? null
  // What it asks with: the answer that takes it back, then the one that does it.
  const answers = () => asked().querySelectorAll('button')
  return { holder, button, done, asked, answers }
}

const escape = () => heard.keydown({ key: 'Escape', preventDefault() {}, stopImmediatePropagation() {} })
const settled = () => new Promise((resolve) => setTimeout(resolve))

afterEach(() => {
  dismiss('route')
  document.body.replaceChildren()
  document.activeElement = null
})

test('its button pressed asks by it, as the one thing that floats, and stays as it was', () => {
  const one = question()
  assert.equal(chain().length, 0)
  one.button.click()
  assert.equal(chain().length, 1)
  assert.equal(one.asked().textContent, 'Stop this epic?CancelStop')
  assert.equal(one.asked().attributes['aria-label'], 'Stop this epic?')
  // Under its button, into the line the button ends.
  assert.deepEqual([one.asked().style.left, one.asked().style.top], ['680px', '134px'])
  // Nothing takes the button's place: what is beside it stands where it stood.
  assert.equal(one.button.parent, one.holder)
  assert.equal(one.button.textContent, 'Stop')
  assert.equal(one.button.attributes['aria-expanded'], 'true')
  // The answer that takes it back has the focus.
  assert.equal(document.activeElement, one.answers()[0])
})

test('a button in the near half of the window asks from its start', () => {
  const one = question()
  one.button.getBoundingClientRect = () => ({ left: 100, top: 100, right: 180, bottom: 128 })
  one.button.click()
  assert.equal(one.asked().style.left, '100px')
})

test('one that asks nothing in words asks by its answers alone', () => {
  const one = question({ label: 'Remove', ask: '', yes: 'Remove' })
  one.button.click()
  assert.equal(one.asked().textContent, 'CancelRemove')
  assert.equal(one.asked().attributes['aria-label'], 'Remove')
})

test('Escape, its own Cancel and its button pressed again take it back, and its button has the focus it held', () => {
  for (const back of [escape, (one) => one.answers()[0].click(), (one) => one.button.click()]) {
    const one = question()
    one.button.click()
    back(one)
    assert.equal(chain().length, 0)
    assert.equal(one.holder.textContent, 'Stop')
    assert.equal(one.button.attributes['aria-expanded'], 'false')
    assert.equal(document.activeElement, one.button)
    assert.deepEqual(one.done, [])
  }
})

test('a dialog opening, the page gone elsewhere, the window sized or left and another thing floating take it back', () => {
  for (const away of [() => dismiss('dialog'), () => dismiss('route'), () => dismiss('resize'), () => dismiss('blur'), () => opened({ node: new Element('div'), close() {} })]) {
    const one = question()
    one.button.click()
    away()
    assert.equal(one.asked(), null)
    assert.equal(one.holder.textContent, 'Stop')
    assert.deepEqual(one.done, [])
    dismiss('route')
  }
})

test('one asked takes back another', () => {
  const first = question()
  const second = question({ label: 'Remove', ask: 'Remove it?', yes: 'Remove' })
  first.button.click()
  second.button.click()
  assert.equal(first.asked(), null)
  assert.equal(second.asked().textContent, 'Remove it?CancelRemove')
  assert.equal(chain().length, 1)
})

test('answered, it floats no more, and its button says it is busy until it is done', async () => {
  let finish = () => {}
  const one = question({ act: () => new Promise((resolve) => (finish = resolve)) })
  one.button.click()
  one.answers()[1].click()
  assert.equal(chain().length, 0)
  assert.equal(one.holder.textContent, 'Stop…')
  assert.ok(one.button.disabled)
  // Pressed while it is busy, it asks nothing more.
  one.button.click()
  assert.equal(chain().length, 0)
  finish()
  await settled()
  assert.equal(one.holder.textContent, 'Stop')
  assert.ok(!one.button.disabled)
})

test('refused, it says why in place of its button, which is back in a while', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const one = question({
    act: async () => {
      throw new Error('No such epic.')
    },
  })
  one.button.click()
  one.answers()[1].click()
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(one.holder.textContent, 'No such epic.')
  t.mock.timers.tick(4000)
  assert.equal(one.holder.textContent, 'Stop')
  assert.equal(one.button.parent, one.holder)
  assert.ok(!one.button.disabled)
})

test('one drawn again while it asks is let go of', () => {
  const one = question()
  one.button.click()
  document.body.replaceChildren()
  assert.equal(chain().length, 0)
})
