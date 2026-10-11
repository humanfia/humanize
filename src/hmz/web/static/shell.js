// What every view stands in: the bar over it, with the button that brings the sidebar back
// where it is folded away, a title and what can be done; the menus that open under a button;
// and the side panel a view can keep beside it. Whether the sidebar and the side panel are
// open is this browser's own, kept between visits.

import { h, icon, iconButton } from './dom.js'

const app = () => document.querySelector('.app')
const narrow = matchMedia('(max-width: 860px)')

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

/** The bar over a view: what it is, and what can be done to it. */
export function bar({ title = '', sub = null, actions = [], lead = null } = {}) {
  return h(
    'header',
    { class: 'bar', 'data-hmz': 'bar' },
    iconButton('sidebar', 'Show sidebar', { class: 'bar-side', onclick: () => toggleSidebar(true), 'aria-controls': 'sidebar' }),
    lead,
    h('div', { class: 'bar-title' }, title ? h('h1', {}, title) : null, sub ? h('div', { class: 'bar-sub' }, sub) : null),
    h('div', { class: 'bar-actions' }, actions),
  )
}

/**
 * A menu under the button that opens it: a list of choices, each with what it is about and a
 * mark on the one chosen, closed by a choice, a click elsewhere or Escape.
 *
 * @param {HTMLElement} anchor What it opens under.
 * @param {() => Node[]} items What it holds, made each time it opens.
 * @param {{align?: 'start'|'end', up?: boolean, label: string}} where
 */
export function menu(anchor, items, { align = 'start', up = false, label }) {
  let open = null
  anchor.setAttribute('aria-haspopup', 'menu')
  anchor.setAttribute('aria-expanded', 'false')
  const close = () => {
    if (!open) return
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
    open = h('div', { class: ['popover', up && 'up', align === 'end' && 'end'], role: 'menu', 'aria-label': label }, items(close))
    anchor.after(open)
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
