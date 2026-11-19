// What a desktop app does about the pointer that a page does not do by itself: a right click
// opens what can be done to the thing under it -- its own menu, never the browser's -- save in
// what is there to be read or written, where the browser's own menu copies and pastes; a tip
// says in full what is cut short, at once rather than when the browser gets round to it; and
// what is said for a moment -- a toast, a notice, a notification's card -- stands in one corner
// of the page, clear of what is typed.

import { h, icon } from './dom.js'
import { chain, closed, opened, tipping } from './layers.js'
import { EDGE, GAP, place } from './shell.js'

/** What each thing right-clicked offers, made as it is clicked. */
const menus = new WeakMap()

/**
 * Gives a thing a menu of its own, opened on a right click or the context menu key.
 *
 * @param {Element} el The thing.
 * @param {() => (Item|null|false|'-')[]} items What it offers, as `{label, glyph, act, href,
 *   danger, title}`, a `'-'` between groups, or a `{head}` saying what the menu is about.
 * @param {string} [kind] A class the menu is drawn with, where it is drawn another way.
 * @returns {Element} The thing.
 */
export function menuOn(el, items, kind = '') {
  menus.set(el, { items, kind })
  return el
}

/**
 * Makes a button the popup button of a thing's menu: pressed, it opens that menu under itself,
 * says it is open, shuts it where pressed again, and has the focus back once Escape shuts it or
 * a choice is made.
 *
 * @param {HTMLElement} button The button.
 * @param {Element} of The thing whose menu it opens, as `menuOn` gave it.
 * @returns {HTMLElement} The button.
 */
export function menuButton(button, of) {
  button.setAttribute('aria-haspopup', 'menu')
  button.setAttribute('aria-expanded', 'false')
  button.addEventListener('click', () => {
    if (shown?.anchor === button) return shown.close()
    const { items, kind } = menus.get(of)
    open(items, { kind, anchor: button })
  })
  return button
}

/** Copies text, saying so in a toast where it could and could not. */
export async function copy(text, what = 'Copied') {
  try {
    await navigator.clipboard.writeText(text)
    toast(what)
  } catch {
    toast('Copy failed')
  }
}

/**
 * Opens the menu a thing has, under it, as the menu key on it would: for a thing the keys move
 * to while the focus stays elsewhere.
 *
 * @param {Element} el The thing.
 * @param {HTMLElement|null} [back] What the focus goes back to as the menu closes.
 * @returns {boolean} Whether it has a menu.
 */
export function menuOf(el, back = null) {
  const menu = menus.get(el)
  if (!menu) return false
  const box = el.getBoundingClientRect()
  return open(menu.items, { x: box.left + 8, y: box.bottom, kind: menu.kind, back })
}

/** The one corner of the page where everything said for a moment stands, made as it is first used. */
let region = null
/** How many stand in it at most: the oldest goes as one more comes. */
const MOST = 3

/**
 * Says something for a moment in the corner of the page kept for it, over whatever was said
 * before: a toast, a notice that stays until what it is about answers, a notification's card.
 *
 * @param {HTMLElement} card What is said, drawn by whoever says it.
 * @param {number} [ms] How long it stays; 0, until what is given back is called.
 * @returns {() => void} What takes it away.
 */
export function posted(card, ms = 0) {
  if (!region) region = h('div', { class: 'toasts', 'data-hmz': 'toasts' })
  if (!region.isConnected) document.body.append(region)
  region.prepend(card)
  while (region.children.length > MOST) region.lastChild.remove()
  const away = () => card.remove()
  if (ms) setTimeout(away, ms)
  return away
}

let toasting = null

/** Says one short thing in that corner, for a moment -- or for as long as is asked -- in place of the last. */
export function toast(said, ms = 1600) {
  toasting?.remove()
  toasting = h('div', { class: 'toast', role: 'status' }, said)
  posted(toasting, ms)
}

/** The menu open, of those opened here: its layer, with what closes it. */
let shown = null

/** Where the browser's own menu is the right one: what is there to be read, copied or written. */
function readable(target) {
  return Boolean(target.closest('input, textarea, select, [contenteditable], .selectable, .thread, .prose, pre, code, dd, .said, .error, .note, .bar-sub .mono'))
}

/**
 * Opens a menu of what a thing offers: under the button that opens it, or with its corner at
 * a point -- the pointer, or the thing a key was pressed on. Whether there was anything to offer.
 *
 * @param {() => (Item|null|false|'-')[]} items
 * @param {{x?: number, y?: number, kind?: string, anchor?: HTMLElement|null, back?: HTMLElement|null}} where
 */
function open(items, { x = 0, y = 0, kind = '', anchor = null, back = null }) {
  const made = items().filter((one) => one !== null && one !== false && one !== undefined)
  if (!made.length) return false
  const menu = h('div', { class: ['popover context', kind], role: 'menu' })
  // The focus goes back, as it closes, to whatever held it as it opened.
  const held = document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null
  const layer = { node: menu, anchor, back: back ?? (anchor ? null : held), close }
  function close() {
    if (shown !== layer) return
    closed(layer)
    shown = null
    menu.remove()
    anchor?.setAttribute('aria-expanded', 'false')
  }
  for (const one of made) {
    if (one === '-') {
      if (menu.lastChild && menu.lastChild.tagName !== 'HR') menu.append(h('hr'))
      continue
    }
    if (one.head) {
      menu.append(h('div', { class: 'popover-head context-head selectable', title: one.head }, one.head))
      continue
    }
    const kids = [h('span', { class: 'choice-mark', 'aria-hidden': 'true' }, one.glyph ? icon(one.glyph) : null), h('span', { class: 'choice-text' }, h('span', { class: 'choice-label' }, one.label))]
    const item = one.href ? h('a', { class: ['choice', one.danger && 'danger'], role: 'menuitem', href: one.href, title: one.title || null }, kids) : h('button', { class: ['choice', one.danger && 'danger'], type: 'button', role: 'menuitem', disabled: one.disabled, title: one.title || null }, kids)
    item.addEventListener('click', () => {
      close()
      if (one.act) one.act()
    })
    menu.append(item)
  }
  if (menu.lastChild && menu.lastChild.tagName === 'HR') menu.lastChild.remove()
  document.body.append(menu)
  opened(layer)
  shown = layer
  if (anchor) {
    // Under the button or over it, whichever has the room, and never on it: pressed again,
    // the button shuts it.
    place(menu, anchor)
    anchor.setAttribute('aria-expanded', 'true')
  } else {
    // Its corner where the pointer is, as a desktop app's menu: moved in from an edge it would
    // cross, never thrown across the pointer, and no taller than the window, where it scrolls.
    menu.style.setProperty('--room', `${innerHeight - 2 * EDGE}px`)
    const { width, height } = menu.getBoundingClientRect()
    menu.style.left = `${Math.max(EDGE, Math.min(x, innerWidth - width - EDGE))}px`
    menu.style.top = `${Math.max(EDGE, Math.min(y, innerHeight - height - EDGE))}px`
  }
  menu.querySelector('button, a')?.focus()
  return true
}

document.addEventListener('contextmenu', (event) => {
  const target = event.target instanceof Element ? event.target : null
  if (!target) return
  // Inside what floats, or on the button whose menu is open: that one's, and nothing opens
  // behind it.
  if (target.closest('.popover, [role=menu], [aria-haspopup][aria-expanded="true"]') || chain().some((one) => one.node.contains(target) || one.anchor?.contains(target))) {
    if (!readable(target)) event.preventDefault()
    return
  }
  // The thing nearest the pointer that has a menu of its own.
  let at = target
  while (at && !menus.has(at)) at = at.parentElement
  if (at && !(readable(target) && String(getSelection()))) {
    event.preventDefault()
    const x = event.clientX || at.getBoundingClientRect().left + 8
    const y = event.clientY || at.getBoundingClientRect().bottom
    const { items, kind } = menus.get(at)
    open(items, { x, y, kind })
    return
  }
  // Nothing to offer here, and nothing to read or write: the browser's menu is no app's.
  if (!readable(target)) event.preventDefault()
})

// ------------------------------------------------------------------ tips

let tip = null
let waiting = 0
let over = null
/** Where the pointer last was, and whether what is under it there was used since: a press or a key. */
let px = 0
let py = 0
let used = false

/** What a thing says of itself on hover: what it was given, or its own text where cut short. */
function said(el) {
  if (el.dataset.tip) return el.dataset.tip
  if (el.hasAttribute('title')) {
    // Taken over, so that the browser's own slow tip never shows beside this one.
    el.dataset.tip = el.getAttribute('title')
    el.removeAttribute('title')
    return el.dataset.tip
  }
  return ''
}

function cut(el) {
  return el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1
}

/** Whether a thing is, or is in, a button whose own menu is open: the menu says more than a tip would, and stands where it would. */
function busy(el) {
  return Boolean(el.closest('[aria-haspopup][aria-expanded="true"]'))
}

/** Whether what a tip says is a path, which is said in the face a path is written in. */
const PATH = /^(?:~|\.{1,2})?\/\S|^[A-Za-z]:\\/

function show(el, text) {
  tip?.remove()
  tip = h('div', { class: ['tip', PATH.test(text) && !text.includes('\n') ? 'mono' : ''], role: 'tooltip' }, text)
  document.body.append(tip)
  const box = el.getBoundingClientRect()
  const { width, height } = tip.getBoundingClientRect()
  const below = box.bottom + GAP + height + EDGE <= innerHeight
  tip.style.left = `${Math.max(EDGE, Math.min(box.left, innerWidth - width - EDGE))}px`
  tip.style.top = `${below ? box.bottom + GAP : Math.max(EDGE, box.top - GAP - height)}px`
}

function hide() {
  lower()
  over = null
}

/** Takes the tip down and keeps it down for what the pointer is over, until the pointer leaves that. */
function lower() {
  clearTimeout(waiting)
  tip?.remove()
  tip = null
}

// The weakest thing on the page: down at every press, key and scroll of what it is about, and
// whenever anything that floats opens or closes.
tipping((event) => {
  // A scroll elsewhere moves nothing it says anything of.
  if (event?.type === 'scroll' && !(over && event.target instanceof Node && event.target.contains(over))) return
  if (event?.type === 'pointerdown' || event?.type === 'keydown') used = true
  lower()
})

document.addEventListener(
  'pointermove',
  (event) => {
    px = event.clientX
    py = event.clientY
  },
  { capture: true, passive: true },
)

document.addEventListener('pointerover', (event) => {
  const target = event.target instanceof Element ? event.target : null
  // Never from a finger, which rests on nothing; nor for what was drawn again under a pointer
  // that has not moved since it pressed.
  if (!target || event.pointerType === 'touch' || (used && event.clientX === px && event.clientY === py)) return
  used = false
  // The nearest thing with something to say: given, or cut short and so not said in full.
  let at = target
  let text = ''
  while (at && at !== document.body) {
    text = said(at)
    if (text) break
    if (at.matches('.side-label, .bar-title h1, [data-hmz=flow-picker] b, .result-task, .card-about, .node-spec, .chip, .crumbs, .side-folder-name, .path, .path-entry span, .choice-about, .ask-closed-asked, .ask-block-title, .ask-block-sum') && cut(at)) {
      text = at.textContent.trim()
      break
    }
    at = at.parentElement
  }
  if (at === over) return
  hide()
  // Nothing is said twice: what it reads in full already is all it would say.
  if (!text || !at || busy(at) || (text === at.textContent.trim() && ![at, ...at.querySelectorAll('*')].some(cut))) return
  over = at
  waiting = setTimeout(() => at.isConnected && !busy(at) && show(at, text), 250)
})
document.addEventListener('pointerout', (event) => {
  if (over && !over.contains(event.relatedTarget)) hide()
})
