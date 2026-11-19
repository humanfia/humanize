// As much of a page as the modules that draw one touch, for tests that run without a browser:
// elements that hold what they are given, find each other by a simple selector, take the focus
// and have the box they are told. Installed before the modules are loaded, which read it then.

import { fakeIndexedDB } from './helpers.mjs'

/** One part of a selector -- a tag, classes, attributes -- as what an element must have. */
function part(text) {
  const wants = []
  for (const [bit] of text.replace(/:[\w-]+/g, '').matchAll(/\.[\w-]+|\[[^\]]+\]|[\w-]+/g)) {
    if (bit[0] === '.') wants.push((el) => el.classList.contains(bit.slice(1)))
    else if (bit[0] === '[') {
      const [name, value] = bit.slice(1, -1).split('=')
      wants.push((el) => (value === undefined ? name in el.attributes : el.attributes[name] === value.replace(/['"]/g, '')))
    } else wants.push((el) => el.tagName === bit.toUpperCase())
  }
  return (el) => wants.every((want) => want(el))
}

class El extends EventTarget {
  constructor(tag, text = '') {
    super()
    Object.assign(this, { tagName: tag.toUpperCase(), attributes: {}, dataset: {}, kids: [], parent: null, hidden: false, disabled: false, value: '', text })
    this.style = { setProperty: (name, value) => (this.style[name] = value), removeProperty: (name) => delete this.style[name] }
    /** Where it is drawn, as a test says: `left`, `top`, `width`, `height`. */
    this.box = { left: 0, top: 0, width: 100, height: 20 }
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value)
    if (name === 'hidden') this.hidden = true
    if (name === 'value') this.value = String(value)
  }
  getAttribute(name) {
    return this.attributes[name] ?? null
  }
  removeAttribute(name) {
    delete this.attributes[name]
  }
  get classList() {
    const has = () => (this.attributes.class || '').split(' ').filter(Boolean)
    return { contains: (name) => has().includes(name) }
  }
  append(...kids) {
    for (const kid of kids) {
      kid.remove()
      kid.parent = this
      this.kids.push(kid)
    }
  }
  prepend(kid) {
    kid.remove()
    kid.parent = this
    this.kids.unshift(kid)
  }
  after(kid) {
    kid.remove()
    kid.parent = this.parent
    this.parent.kids.splice(this.parent.kids.indexOf(this) + 1, 0, kid)
  }
  remove() {
    if (this.parent) this.parent.kids.splice(this.parent.kids.indexOf(this), 1)
    this.parent = null
  }
  replaceChildren(...kids) {
    for (const kid of [...this.kids]) kid.remove()
    this.append(...kids)
  }
  get textContent() {
    return this.text + this.kids.map((kid) => kid.textContent).join('')
  }
  set textContent(said) {
    this.replaceChildren()
    this.text = String(said)
  }
  contains(other) {
    for (let at = other; at; at = at.parent) if (at === this) return true
    return false
  }
  get isConnected() {
    return document.body.contains(this)
  }
  /** Whether it is drawn: in the page, and neither it nor what holds it hidden. */
  getClientRects() {
    for (let at = this; at; at = at.parent) if (at.hidden) return []
    return this.isConnected ? [this.box] : []
  }
  getBoundingClientRect() {
    const { left, top, width, height } = this.box
    return { left, top, width, height, right: left + width, bottom: top + height }
  }
  get offsetWidth() {
    return this.box.width
  }
  get offsetHeight() {
    return this.box.height
  }
  matches(selector) {
    return selector.split(',').some((one) => part(one)(this))
  }
  closest(selector) {
    for (let at = this; at; at = at.parent) if (at.matches(selector)) return at
    return null
  }
  querySelectorAll(selector) {
    return this.kids.flatMap((kid) => [...(kid.matches(selector) ? [kid] : []), ...kid.querySelectorAll(selector)])
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] ?? null
  }
  focus() {
    if (this.getClientRects().length) document.activeElement = this
  }
  click() {
    this.dispatchEvent(new Event('click'))
  }
  scrollIntoView() {}
  setSelectionRange(at) {
    this.selectionStart = at
  }
}

/**
 * Puts the page in place of a browser's. Answers its body, what makes an element in it, and
 * what tells the page of a press or a key as a browser would: on the document, as from `target`.
 */
export function page() {
  const events = new EventTarget()
  const body = new El('body')
  Object.assign(globalThis, {
    window: globalThis,
    Node: El,
    innerWidth: 1320,
    innerHeight: 860,
    location: { protocol: 'http:', host: 'page', hash: '', origin: 'http://page', search: '' },
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    dispatchEvent: events.dispatchEvent.bind(events),
    document: Object.assign(new EventTarget(), {
      hidden: false,
      body,
      activeElement: body,
      documentElement: new El('html'),
      createElement: (tag) => new El(tag),
      createElementNS: (_, tag) => new El(tag),
      createTextNode: (text) => new El('#text', text),
      querySelector: (selector) => body.querySelector(selector),
    }),
    matchMedia: () => Object.assign(new EventTarget(), { matches: false }),
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    cancelAnimationFrame: clearTimeout,
    ResizeObserver: class {
      observe() {}
      disconnect() {}
    },
    fetch: async () => ({ ok: false, status: 404 }),
    indexedDB: fakeIndexedDB(),
  })
  const told = (type, target, more = {}) => {
    const event = Object.assign(new Event(type, { cancelable: true }), more)
    Object.defineProperty(event, 'target', { value: target })
    document.dispatchEvent(event)
  }
  return {
    body,
    el: (tag, props = {}, ...kids) => {
      const made = new El(tag)
      for (const [name, value] of Object.entries(props)) made.setAttribute(name, value)
      made.append(...kids)
      return made
    },
    press: (target) => told('pointerdown', target),
    key: (key, target = document.activeElement) => told('keydown', target, { key }),
  }
}
