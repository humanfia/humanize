// What a desktop app does about the pointer that a page does not do by itself: a right click
// opens what can be done to the thing under it -- its own menu, never the browser's -- save in
// what is there to be read or written, where the browser's own menu copies and pastes; and a
// tip says in full what is cut short, at once rather than when the browser gets round to it.

import { h, icon } from './dom.js'

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
    if (opener === button) return close()
    const box = button.getBoundingClientRect()
    const { items, kind } = menus.get(of)
    open(items, box.left, box.bottom + 4, kind)
    if (!opened) return
    opener = button
    button.setAttribute('aria-expanded', 'true')
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
  open(menu.items, box.left + 8, box.bottom, menu.kind)
  if (opened) from = back
  return Boolean(opened)
}

let toasting = null

/** Says one short thing at the foot of the page, for a moment. */
export function toast(said) {
  toasting?.remove()
  toasting = h('div', { class: 'toast', role: 'status' }, said)
  document.body.append(toasting)
  const mine = toasting
  setTimeout(() => mine.remove(), 1600)
}

let opened = null
/** What the focus goes back to as a menu opened by a key closes. */
let from = null
/** The popup button the menu open was opened by, if by one. */
let opener = null

/** Shuts the menu open; `back` gives the focus back to the button that opened it. */
function close(back = false) {
  if (from && opened?.contains(document.activeElement)) from.focus()
  from = null
  opened?.remove()
  opened = null
  const by = opener
  opener = null
  if (!by) return
  by.setAttribute('aria-expanded', 'false')
  if (back === true) by.focus()
}

/** Where the browser's own menu is the right one: what is there to be read, copied or written. */
function readable(target) {
  return Boolean(target.closest('input, textarea, select, [contenteditable], .selectable, .thread, .prose, pre, code, dd, .said, .error, .note, .bar-sub .mono'))
}

function open(items, x, y, kind = '') {
  close()
  const made = items().filter((one) => one !== null && one !== false && one !== undefined)
  if (!made.length) return
  const menu = h('div', { class: ['popover context', kind], role: 'menu' })
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
      close(true)
      if (one.act) one.act()
    })
    menu.append(item)
  }
  if (menu.lastChild && menu.lastChild.tagName === 'HR') menu.lastChild.remove()
  document.body.append(menu)
  // Kept on the screen, as a desktop app's menu is: flipped back from an edge it would cross,
  // and no taller than the window, where it scrolls.
  menu.style.setProperty('--room', `${innerHeight - 8}px`)
  const { width, height } = menu.getBoundingClientRect()
  menu.style.left = `${Math.max(4, Math.min(x, innerWidth - width - 4))}px`
  menu.style.top = `${Math.max(4, Math.min(y + height > innerHeight - 4 ? y - height : y, innerHeight - height - 4))}px`
  opened = menu
  menu.querySelector('button, a')?.focus()
}

document.addEventListener('contextmenu', (event) => {
  const target = event.target instanceof Element ? event.target : null
  if (!target) return
  // The thing nearest the pointer that has a menu of its own.
  let at = target
  while (at && !menus.has(at)) at = at.parentElement
  if (at && !(readable(target) && String(getSelection()))) {
    event.preventDefault()
    const x = event.clientX || at.getBoundingClientRect().left + 8
    const y = event.clientY || at.getBoundingClientRect().bottom
    const { items, kind } = menus.get(at)
    open(items, x, y, kind)
    return
  }
  // Nothing to offer here, and nothing to read or write: the browser's menu is no app's.
  if (!readable(target)) event.preventDefault()
})

document.addEventListener('pointerdown', (event) => {
  // A press on the button that opened it is that button's to answer: it shuts the menu.
  if (opened && !opened.contains(event.target) && !opener?.contains(event.target)) close()
}, true)
document.addEventListener('keydown', (event) => {
  if (opened && event.key === 'Escape') {
    event.stopPropagation()
    close(true)
  }
}, true)
window.addEventListener('blur', () => close())
window.addEventListener('hashchange', () => close())
document.addEventListener('scroll', () => close(), true)

// ------------------------------------------------------------------ tips

let tip = null
let waiting = 0
let over = null

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

function show(el, text) {
  tip?.remove()
  tip = h('div', { class: 'tip', role: 'tooltip' }, text)
  document.body.append(tip)
  const box = el.getBoundingClientRect()
  const { width, height } = tip.getBoundingClientRect()
  const below = box.bottom + 6 + height < innerHeight
  tip.style.left = `${Math.max(4, Math.min(box.left, innerWidth - width - 4))}px`
  tip.style.top = `${below ? box.bottom + 6 : box.top - height - 6}px`
}

/** Takes down the tip showing, if any: for what it is about once that is being used. */
export function hideTip() {
  hide()
}

function hide() {
  clearTimeout(waiting)
  tip?.remove()
  tip = null
  over = null
}

document.addEventListener('mouseover', (event) => {
  const target = event.target instanceof Element ? event.target : null
  if (!target) return
  // The nearest thing with something to say: given, or cut short and so not said in full.
  let at = target
  let text = ''
  while (at && at !== document.body) {
    text = said(at)
    if (text) break
    if (at.matches('.side-label, .bar-title h1, [data-hmz=flow-picker] b, .result-task, .card-about, .node-spec, .chip, .crumbs, .side-folder-name, .path, .path-entry span, .choice-about') && cut(at)) {
      text = at.textContent.trim()
      break
    }
    at = at.parentElement
  }
  if (at === over) return
  hide()
  if (!text || !at) return
  over = at
  waiting = setTimeout(() => show(at, text), 250)
})
document.addEventListener('mouseout', (event) => {
  if (over && !over.contains(event.relatedTarget)) hide()
})
document.addEventListener('pointerdown', hide, true)
window.addEventListener('blur', hide)
document.addEventListener('scroll', hide, true)
