import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'

// The page's document, as far as a question asked in place and the chain's listeners use it:
// elements that hold others, are pressed and take the focus, and what the document listens for.
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
  /** What held the focus and is taken out of the page leaves it with the page, as a browser does. */
  replaceChildren() {
    if (this.kids.some((kid) => kid instanceof Element && kid.contains(document.activeElement))) document.activeElement = document.body
    for (const kid of this.kids) kid.parent = null
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

const { chain, dismiss, opened } = await import('../../../../src/hmz/web/static/layers.js')
const { confirming } = await import('../../../../src/hmz/web/static/confirm.js')

/** A question in the page, and what its answer did. */
function question(how = {}) {
  const done = []
  const holder = confirming({ label: 'Stop', ask: 'Stop this epic?', yes: 'Stop', act: async () => done.push('stopped'), ...how })
  document.body.append(holder)
  const said = () => holder.querySelectorAll('button').map((one) => one.textContent)
  return { holder, done, said, press: (at) => holder.querySelectorAll('button')[at].click() }
}

const escape = () => heard.keydown({ key: 'Escape', preventDefault() {}, stopImmediatePropagation() {} })

afterEach(() => {
  dismiss('route')
  document.body.replaceChildren()
  document.activeElement = null
})

test('its button pressed asks, as the one thing that floats', () => {
  const one = question()
  assert.deepEqual(one.said(), ['Stop'])
  assert.equal(chain().length, 0)
  one.press(0)
  assert.equal(one.holder.textContent, 'Stop this epic?StopCancel')
  assert.equal(chain().length, 1)
  assert.equal(chain()[0].node, one.holder)
  // Its answer has the focus.
  assert.equal(document.activeElement, one.holder.querySelectorAll('button')[0])
})

test('Escape takes it back, and its button has the focus it held', () => {
  const one = question()
  one.press(0)
  escape()
  assert.deepEqual(one.said(), ['Stop'])
  assert.equal(chain().length, 0)
  assert.equal(document.activeElement, one.holder.querySelector('button'))
  assert.deepEqual(one.done, [])
})

test('its own Cancel takes it back the same', () => {
  const one = question()
  one.press(0)
  one.press(1)
  assert.deepEqual(one.said(), ['Stop'])
  assert.equal(chain().length, 0)
  assert.equal(document.activeElement, one.holder.querySelector('button'))
})

test('a dialog opening, the page gone elsewhere and another thing floating take it back', () => {
  for (const away of [() => dismiss('dialog'), () => dismiss('route'), () => opened({ node: new Element('div'), close() {} })]) {
    const one = question()
    one.press(0)
    away()
    assert.deepEqual(one.said(), ['Stop'])
    assert.deepEqual(one.done, [])
    dismiss('route')
  }
})

test('the window sized or left keeps it', () => {
  const one = question()
  one.press(0)
  dismiss('resize')
  dismiss('blur')
  assert.deepEqual(one.said(), ['Stop', 'Cancel'])
  assert.equal(chain().length, 1)
})

test('one asked takes back another', () => {
  const first = question()
  const second = question({ label: 'Remove', ask: 'Remove it?', yes: 'Remove' })
  first.press(0)
  second.press(0)
  assert.deepEqual(first.said(), ['Stop'])
  assert.deepEqual(second.said(), ['Remove', 'Cancel'])
  assert.equal(chain().length, 1)
})

test('answered, it floats no more and is not taken back while it is done', async () => {
  let finish = () => {}
  const one = question({ act: () => new Promise((resolve) => (finish = resolve)) })
  one.press(0)
  one.press(0)
  assert.equal(chain().length, 0)
  assert.deepEqual(one.said(), ['Stop…', 'Cancel'])
  // Nothing floats: Escape and a dialog are not its to take.
  dismiss('dialog')
  assert.deepEqual(one.said(), ['Stop…', 'Cancel'])
  finish()
  await new Promise((resolve) => setTimeout(resolve))
  assert.deepEqual(one.said(), ['Stop'])
})

test('one drawn again while it asks is let go of', () => {
  const one = question()
  one.press(0)
  document.body.replaceChildren()
  assert.equal(chain().length, 0)
})
