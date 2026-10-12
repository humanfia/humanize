// What every view stands in: the bar over it, with the button that brings the sidebar back
// where it is folded away, a title and what can be done; the menus that open under a button;
// and the side panel a view can keep beside it. Whether the sidebar and the side panel are
// open is this browser's own, kept between visits.

import { h, icon, iconButton } from './dom.js'

const app = () => document.querySelector('.app')
const narrow = matchMedia('(max-width: 860px)')
/** Whether the page is the macOS app's window, as theme.js found before the page was drawn. */
const inApp = document.documentElement.dataset.shell === 'macos'

/** Reads a choice this browser keeps, or the default where it keeps none or cannot. */
export function kept(name, otherwise) {
  try {
    return localStorage.getItem(name) ?? otherwise
  } catch {
    return otherwise
  }
}

/** Keeps a choice in this browser, where it can. */
export function keep(name, value) {
  try {
    if (value === null) localStorage.removeItem(name)
    else localStorage.setItem(name, value)
  } catch {
    // A browser that keeps nothing forgets it: the page works the same.
  }
}

/** Opens or folds the sidebar: a drawer over the page on a narrow screen, a column beside it otherwise. */
export function toggleSidebar(open) {
  const root = app()
  if (narrow.matches) {
    const now = open ?? !root.classList.contains('side-open')
    root.classList.toggle('side-open', now)
    document.querySelector('.scrim').hidden = !now
    return
  }
  const now = open ?? root.classList.contains('side-folded')
  root.classList.toggle('side-folded', !now)
  keep('hmz-sidebar', now ? null : 'folded')
}

/** Closes the drawer the sidebar is on a narrow screen, once somewhere in it was picked. */
export function settleSidebar() {
  if (!narrow.matches) return
  app().classList.remove('side-open')
  document.querySelector('.scrim').hidden = true
}

/**
 * A row along the top of the window, which in the macOS app's window moves it where it is
 * dragged, and zooms it where it is double-clicked, by anything in it but what is clicked:
 * `deep` for all it holds, `''` for itself alone, `'false'` for none of what it holds.
 */
export function dragged(el, how = 'deep') {
  if (inApp) el.setAttribute('data-tauri-drag-region', how)
  return el
}

/** The bar over a view: what it is, and what can be done to it. */
export function bar({ title = '', sub = null, actions = [], lead = null } = {}) {
  return dragged(
    h(
      'header',
      { class: 'bar', 'data-hmz': 'bar' },
      iconButton('sidebar', 'Show sidebar', { class: 'bar-side', onclick: () => toggleSidebar(true), 'aria-controls': 'sidebar' }),
      lead,
      h('div', { class: 'bar-title' }, title ? h('h1', {}, title) : null, sub ? h('div', { class: 'bar-sub' }, sub) : null),
      h('div', { class: 'bar-actions' }, actions),
    ),
  )
}

/** Room kept between a popup and the window's edge, and between it and what opened it. */
const EDGE = 8
const GAP = 6

/**
 * Puts a popup by what opened it, against the window rather than whatever holds it -- a dialog
 * or a list that scrolls would cut it off -- as a desktop app puts a menu: on the side asked for
 * where it fits, on the other where that has more room, no taller than the room it has, and
 * moved in from an edge rather than past it.
 *
 * @param {HTMLElement} pop The popup, shown.
 * @param {Element} anchor What opened it.
 * @param {{align?: 'start'|'end', up?: boolean, span?: boolean}} how Which edge of it the popup
 *   lines up with, whether it would rather open over it, and whether it is as wide as it.
 */
export function place(pop, anchor, { align = 'start', up = false, span = false } = {}) {
  const box = anchor.getBoundingClientRect()
  if (span) pop.style.width = `${box.width}px`
  pop.style.removeProperty('--room')
  const room = { below: innerHeight - box.bottom - GAP - EDGE, above: box.top - GAP - EDGE }
  const [first, second] = up ? ['above', 'below'] : ['below', 'above']
  const side = pop.offsetHeight <= room[first] || room[first] >= room[second] ? first : second
  pop.style.setProperty('--room', `${Math.max(room[side], 80)}px`)
  const { offsetWidth: wide, offsetHeight: tall } = pop
  pop.style.top = `${side === 'below' ? box.bottom + GAP : Math.max(EDGE, box.top - GAP - tall)}px`
  const left = align === 'end' ? box.right - wide : box.left
  pop.style.left = `${Math.max(EDGE, Math.min(left, innerWidth - wide - EDGE))}px`
}

/** Places a popup and keeps it by what opened it as the page scrolls, the window is sized or the popup grows; says how to stop. */
export function follow(pop, anchor, how) {
  const again = (event) => {
    if (!event || !(event.target instanceof Node) || !pop.contains(event.target)) place(pop, anchor, how)
  }
  again()
  const grown = new ResizeObserver(() => again())
  grown.observe(pop)
  addEventListener('scroll', again, true)
  addEventListener('resize', again)
  return () => {
    grown.disconnect()
    removeEventListener('scroll', again, true)
    removeEventListener('resize', again)
  }
}

/**
 * A menu by the button that opens it: a list of choices, each with what it is about and a
 * mark on the one chosen, closed by a choice, a click elsewhere or Escape.
 *
 * @param {HTMLElement} anchor What it opens under.
 * @param {() => Node[]} items What it holds, made each time it opens.
 * @param {{align?: 'start'|'end', up?: boolean, span?: boolean, label: string}} where See `place`.
 */
export function menu(anchor, items, { align = 'start', up = false, span = false, label }) {
  let open = null
  let unfollow = () => {}
  anchor.setAttribute('aria-haspopup', 'menu')
  anchor.setAttribute('aria-expanded', 'false')
  const close = () => {
    if (!open) return
    unfollow()
    open.remove()
    open = null
    anchor.setAttribute('aria-expanded', 'false')
    document.removeEventListener('pointerdown', outside, true)
    document.removeEventListener('keydown', escape, true)
  }
  const outside = (event) => {
    if (open && !open.contains(event.target) && !anchor.contains(event.target)) close()
  }
  const escape = (event) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      close()
      anchor.focus()
    }
  }
  anchor.addEventListener('click', () => {
    if (open) return close()
    // Not what the window is dragged by, though it opens in a row that is.
    open = dragged(h('div', { class: 'popover', role: 'menu', 'aria-label': label }, items(close)), 'false')
    anchor.after(open)
    unfollow = follow(open, anchor, { align, up, span })
    anchor.setAttribute('aria-expanded', 'true')
    document.addEventListener('pointerdown', outside, true)
    document.addEventListener('keydown', escape, true)
    open.querySelector('button, a')?.focus()
  })
  return close
}

/** One choice in a menu. */
export function choice({ label, about = '', chosen = false, href = null, glyph = null, act = null, close }) {
  const kids = [
    h('span', { class: 'choice-mark', 'aria-hidden': 'true' }, chosen ? icon('check') : glyph ? icon(glyph) : null),
    h('span', { class: 'choice-text' }, h('span', { class: 'choice-label' }, label), about ? h('span', { class: 'choice-about' }, about) : null),
  ]
  const props = { class: ['choice', chosen && 'chosen'], role: 'menuitem' }
  const el = href ? h('a', { ...props, href }, kids) : h('button', { ...props, type: 'button' }, kids)
  el.addEventListener('click', () => {
    if (act) act()
    close()
  })
  return el
}

/** A heading among a menu's choices. */
export function section(label) {
  return h('div', { class: 'popover-head', role: 'presentation' }, label)
}

/**
 * The panel a view keeps beside it, as Claude keeps an artifact or ChatGPT a canvas: open or
 * shut as this browser last left it, and over the view on a narrow screen.
 */
export function sidePanel(label) {
  const body = h('div', { class: 'panel-body' })
  const shut = iconButton('close', 'Close panel', { class: 'panel-close' })
  const node = h('aside', { class: 'inspector', 'aria-label': label, 'data-hmz': 'inspector' }, shut, body)
  const toggle = iconButton('panel', 'Toggle panel', { class: 'panel-toggle' })
  const set = (open) => {
    node.hidden = !open
    toggle.setAttribute('aria-pressed', String(open))
    if (!narrow.matches) keep('hmz-panel', open ? null : 'shut')
  }
  set(!narrow.matches && kept('hmz-panel', 'open') !== 'shut')
  toggle.addEventListener('click', () => set(node.hidden))
  shut.addEventListener('click', () => set(false))
  return { node, body, toggle, open: () => set(true) }
}

/** Tabs over what a panel holds, each drawn when picked. */
export function tabbed(tabs, picked, told) {
  const list = h('div', { class: 'tabs', role: 'tablist' })
  for (const [key, label] of tabs) {
    const tab = h('button', { type: 'button', role: 'tab', 'aria-selected': String(key === picked) }, label)
    tab.addEventListener('click', () => told(key))
    list.append(tab)
  }
  return list
}

narrow.addEventListener('change', () => {
  app().classList.remove('side-open')
  document.querySelector('.scrim').hidden = true
})
