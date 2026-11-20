// What every view stands in: the bar over it, with the button that brings the sidebar back
// where it is folded away, a title and what can be done; the menus that open under a button;
// and the side panel a view can keep beside it. Whether the sidebar and the side panel are
// open is this browser's own, kept between visits.

import { h, icon, iconButton } from './dom.js'
import { t } from './i18n.js'
import { EDGE, GAP, closed, dismiss, follow, opened } from './layers.js'

// Where a popup is put is the chain's own (layers.js), offered here with the menus placed by it.
export { EDGE, GAP, follow, place } from './layers.js'

const app = () => document.querySelector('.app')
const narrow = matchMedia('(max-width: 860px)')
/** Which system Humanize Desktop's window is on, `macos` or `windows`, as theme.js found before the page was drawn; or none. */
export const shell = document.documentElement.dataset.shell
/** Whether the page is Humanize Desktop's window. */
export const inApp = Boolean(shell)

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
  // No menu is left floating by a sidebar that folded under it: one that held the focus gives
  // it back to what opened it first, which is then looked at below.
  dismiss('fold')
  const root = app()
  const side = root.querySelector('.sidebar')
  const within = side.contains(document.activeElement)
  // Nothing in particular holds the focus: the page, or the view as a whole, which is where a
  // browser that gives a button pressed no focus leaves it. Never what is being typed into,
  // which a key that folds the sidebar leaves alone.
  const loose = document.activeElement === document.body || document.activeElement === root.querySelector('.main')
  // A dialog over the page keeps the focus: the sidebar folds and opens under it all the same.
  const covered = !document.querySelector('.overlay').hidden
  if (narrow.matches) {
    const now = open ?? !root.classList.contains('side-open')
    drawer(now)
    // The drawer is over the page, which no key reaches while it is: the focus goes into it as
    // it opens, and back to what opens it as it closes.
    if (covered) return
    if (now) side.querySelector('.side-fold')?.focus()
    else if (within || loose) root.querySelector('.bar-side')?.focus()
    return
  }
  const now = open ?? root.classList.contains('side-folded')
  const pressed = loose || document.activeElement?.classList.contains('bar-side')
  root.classList.toggle('side-folded', !now)
  keep('hmz-sidebar', now ? null : 'folded')
  if (covered) return
  // The button pressed is gone with what it did: the one that undoes it has the focus.
  if (now && pressed) side.querySelector('.side-fold')?.focus()
  else if (!now && (within || loose)) root.querySelector('.bar-side')?.focus()
}

/** Opens or closes the drawer the sidebar is on a narrow screen: the page under it is out of reach while it is open. */
function drawer(open) {
  const root = app()
  if (root.classList.contains('side-open') !== open) dismiss('fold')
  // One thing over the view at a time: the drawer opening closes the panel that is.
  if (open) for (const pane of panes) pane.shut()
  root.classList.toggle('side-open', open)
  document.querySelector('.scrim').hidden = !open
  root.querySelector('.main').inert = open
}

/** Closes the drawer the sidebar is on a narrow screen, once somewhere in it was picked. */
export function settleSidebar() {
  if (narrow.matches && app().classList.contains('side-open')) drawer(false)
}

// The page gone elsewhere, by whatever was pressed: the drawer is not left over it.
addEventListener('hmz:route', settleSidebar)

/**
 * A row along the top of the window, which in Humanize Desktop's window moves it where it is
 * dragged, and zooms or maximizes it where it is double-clicked, by anything in it but what is clicked:
 * `deep` for all it holds, `''` for itself alone, `'false'` for none of what it holds. One that
 * is the top row only on a narrow window, or only on a wide one, says which in `when`, and moves
 * nothing on the other: a dialog's head, or a panel's tabs, there inside the window.
 */
export function dragged(el, how = 'deep', when = null) {
  if (!inApp) return el
  if (!when) el.setAttribute('data-tauri-drag-region', how)
  else {
    el.dataset.dragged = `${when} ${how}`
    reach(el)
  }
  return el
}

/** Makes a row dragged on a narrow window, or a wide one, so on this one or not. */
function reach(el) {
  const [when, how = ''] = el.dataset.dragged.split(' ')
  if ((when === 'narrow') === narrow.matches) el.setAttribute('data-tauri-drag-region', how)
  else el.removeAttribute('data-tauri-drag-region')
}

/** The bar over a view: what it is, and what can be done to it. Ai-chan's button ends it, on every view. */
export function bar({ title = '', sub = null, actions = [], lead = null } = {}) {
  return dragged(
    h(
      'header',
      { class: 'bar', 'data-hmz': 'bar' },
      iconButton('sidebar', t('Show sidebar'), { class: 'bar-side', onclick: () => toggleSidebar(true), 'aria-controls': 'sidebar' }),
      lead,
      h('div', { class: 'bar-title' }, title ? h('h1', {}, title) : null, sub ? h('div', { class: 'bar-sub' }, sub) : null),
      h('div', { class: 'bar-actions' }, actions, aiChanButton()),
    ),
  )
}

/** How far a menu opened from a choice of another stands over that one. */
const LAP = 4

/**
 * A menu by the button that opens it: a list of choices, each with what it is about and a
 * mark on the one chosen, closed by a choice, the button pressed again, and whatever closes
 * every layer (layers.js): a press elsewhere, Escape, the focus leaving, another one opening.
 *
 * @param {HTMLElement} anchor What it opens under.
 * @param {() => Node[]} items What it holds, made each time it opens.
 * @param {{align?: 'start'|'end', up?: boolean, span?: boolean, by?: Element|null, label: string, role?: 'menu'|'dialog'}} where
 *   See `place`: `by`, what it opens clear of with its button -- the box typed into that the
 *   button stands over, which it would lie on; `role`, `dialog` for one that holds what is read
 *   and not choices, which the arrow keys have nothing to move through.
 */
export function menu(anchor, items, { align = 'start', up = false, span = false, by = null, label, role = 'menu' }) {
  let open = null
  let unfollow = () => {}
  anchor.setAttribute('aria-haspopup', role)
  anchor.setAttribute('aria-expanded', 'false')
  const layer = { node: null, anchor, close }
  function close() {
    if (!open) return
    closed(layer)
    unfollow()
    open.remove()
    open = null
    anchor.setAttribute('aria-expanded', 'false')
  }
  anchor.addEventListener('click', (event) => {
    if (open) return close()
    // Not what the window is dragged by, though it opens in a row that is.
    open = dragged(h('div', { class: 'popover', role, 'aria-label': label }, items(close)), 'false')
    anchor.after(open)
    layer.node = open
    opened(layer)
    unfollow = follow(open, anchor, { align, up, span, by })
    anchor.setAttribute('aria-expanded', 'true')
    // What is read and not chosen from is left by Tab as by Escape: past its last stop, or back
    // past its first, it closes and what opened it has the focus, from where Tab goes on.
    if (role === 'dialog') {
      open.addEventListener('keydown', (event) => {
        if (event.key !== 'Tab' || event.target !== [...open.querySelectorAll('a[href], button, input, select, textarea')].at(event.shiftKey ? 0 : -1)) return
        event.preventDefault()
        close()
      })
    }
    enter(open, !event.detail)
  })
  return close
}

/**
 * Puts the focus in a menu just opened: on the one chosen, where one is, as a desktop app's menu
 * opens on it, and with the ring that says where the keys are only where a key opened it.
 *
 * @param {Element} menu
 * @param {boolean} keyed Whether a key opened it, not a pointer.
 */
export function enter(menu, keyed) {
  ;(menu.querySelector('.choice.chosen') || menu.querySelector('button, a'))?.focus({ focusVisible: keyed })
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

/**
 * A choice in a menu that opens a menu of its own beside it: on a pointer resting on it, a click,
 * a tap or the right arrow; shut as the pointer leaves both, by the left arrow or Escape, by the
 * choice pressed again once the menu was gone into, by another of its menu's opening, or with
 * the menu it is in.
 */
export function submenu({ label, about = '', glyph = null, items, hmz = null }) {
  const opener = h(
    'button',
    { class: 'choice', type: 'button', role: 'menuitem', 'aria-haspopup': 'menu', 'aria-expanded': 'false' },
    h('span', { class: 'choice-mark', 'aria-hidden': 'true' }, glyph ? icon(glyph) : null),
    h('span', { class: 'choice-text' }, h('span', { class: 'choice-label' }, label), about ? h('span', { class: 'choice-about' }, about) : null),
    h('span', { class: 'choice-more', 'aria-hidden': 'true' }, icon('chevron')),
  )
  const holder = h('div', { class: 'choice-sub' }, opener)
  let open = null
  let leaving = 0
  /** Whether it was gone into, by a click, a tap or a key: the choice pressed again then shuts it. */
  let entered = false
  const layer = { node: null, anchor: opener, close: shut }
  function shut() {
    clearTimeout(leaving)
    if (!open) return
    closed(layer)
    open.remove()
    open = null
    entered = false
    opener.setAttribute('aria-expanded', 'false')
  }
  /** Opens it; gone into where `keyed` says by what, a key or a pointer. */
  const show = (keyed) => {
    clearTimeout(leaving)
    if (!open) {
      const made = h('div', { class: 'popover sub', role: 'menu', 'aria-label': label, 'data-hmz': hmz }, items())
      holder.append(made)
      beside(made, holder.closest('.popover'), opener)
      // Over its own menu it would cover the choices a pointer passing this one is on its way
      // to: there it opens only where it is gone into, and a pointer passing closes nothing.
      if (keyed === undefined && !made.dataset.side) return made.remove()
      layer.node = open = made
      opened(layer)
      opener.setAttribute('aria-expanded', 'true')
    }
    if (keyed !== undefined) {
      entered = true
      enter(open, keyed)
    }
  }
  holder.addEventListener('pointerenter', (event) => event.pointerType === 'mouse' && show())
  holder.addEventListener('pointerleave', (event) => {
    if (event.pointerType === 'mouse') leaving = setTimeout(shut, 250)
  })
  opener.addEventListener('click', (event) => (open && entered ? shut() : show(!event.detail)))
  holder.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowRight' && event.target === opener) show(true)
    else if (event.key === 'ArrowLeft' && open) shut()
    else return
    event.preventDefault()
    // One opened from a choice of another shuts alone: the one it is in stays open.
    event.stopPropagation()
  })
  return holder
}

/**
 * Puts a menu opened from a choice beside the menu that choice is in, a little over its edge,
 * its first choice level with the one that opened it: on the right where there is room, else on
 * the left -- and, opened from a menu that is itself beside another, only on the side that one
 * took, never back over those it came from. With no room there -- on a phone -- it stands over
 * its menu, edge on edge and as wide at least, under the choice or, with no room there, above:
 * never on the choice that opened it, and over all of its menu on that side of the choice, so
 * that no other choice shows cut through. Opened from a menu that stands over a chip of the row
 * under a box typed into, it ends no lower than that menu: never on the chips, nor on the box.
 */
function beside(pop, parent, opener) {
  const outer = parent.getBoundingClientRect()
  const row = opener.getBoundingClientRect()
  const foot = opener.closest('.composer-under') ? Math.min(outer.bottom, innerHeight - EDGE) : innerHeight - EDGE
  pop.style.setProperty('--room', `${foot - EDGE}px`)
  // Measured from the window's own edge, as `place` measures.
  pop.style.left = '0'
  const wide = pop.offsetWidth
  const edge = getComputedStyle(pop)
  const at = { right: outer.right - LAP, left: outer.left + LAP - wide }
  const fits = { right: at.right + wide + EDGE <= innerWidth, left: at.left >= EDGE }
  const side = (parent.dataset.side ? [parent.dataset.side] : ['right', 'left']).find((one) => fits[one]) ?? ''
  pop.dataset.side = side
  const under = row.bottom + pop.offsetHeight <= foot
  if (!side) Object.assign(pop.style, { minWidth: `${outer.width}px`, minHeight: `${under ? outer.bottom - row.bottom : row.top - outer.top}px` })
  const tall = pop.offsetHeight
  const left = side ? at[side] : outer.left
  const top = side ? row.top - parseFloat(edge.paddingTop) - parseFloat(edge.borderTopWidth) : under ? row.bottom : row.top - tall
  pop.style.left = `${Math.max(EDGE, Math.min(left, innerWidth - pop.offsetWidth - EDGE))}px`
  pop.style.top = `${Math.max(EDGE, Math.min(top, foot - tall))}px`
}

/** A heading among a menu's choices. */
export function section(label) {
  return h('div', { class: 'popover-head', role: 'presentation' }, label)
}

/** Every side panel made that may still be in the page. */
const panes = new Set()
/** The least width a view keeps beside the panels open by it, on a wide window. */
const VIEW = 480

/** The panels open in the page, letting go of those a view left behind. */
function shown() {
  for (const pane of panes) {
    if (pane.node.isConnected) pane.seen = true
    else if (pane.seen) panes.delete(pane)
  }
  return [...panes].filter((pane) => pane.node.isConnected && !pane.node.hidden)
}

/**
 * How wide the view is left by the panels open in it and beside it. One open but not drawn yet
 * -- its view keeps it out of sight until it knows what it is of -- counts as wide as it will
 * be drawn, so that it gives way before it is seen rather than after.
 */
function left() {
  const main = app().querySelector('.main')
  const wide = (node) => node.getBoundingClientRect().width || parseFloat(getComputedStyle(node).width) || 0
  return shown().reduce((room, pane) => room - (main.contains(pane.node) ? wide(pane.node) : 0), main.getBoundingClientRect().width)
}

/**
 * Makes room for a panel the person opened: on a narrow screen it is the one thing over the
 * view, so the others and the sidebar's drawer close; on a wide one the others close only
 * where the view would be left too narrow to read, the one opened taking their place.
 */
function roomFor(pane) {
  const others = shown().filter((one) => one !== pane)
  if (narrow.matches) {
    if (app().classList.contains('side-open')) drawer(false)
    for (const one of others) one.shut()
  } else if (others.length && left() < VIEW) for (const one of others) one.shut()
}

/**
 * Looks at the panels open as they were last left: where they leave the view too narrow, or
 * are more than the one a narrow screen has over the view, the view's own gives way to one kept
 * beside every view, and is not kept as shut for it.
 */
function fit() {
  const main = app().querySelector('.main')
  for (let open = shown(); open.length > 1 && (narrow.matches || left() < VIEW); open = shown()) (open.find((one) => main.contains(one.node)) ?? open.at(-1)).yields()
}

let settling = 0

/** Looks at them once what was drawn is in the page. */
function settle() {
  cancelAnimationFrame(settling)
  settling = requestAnimationFrame(fit)
}

// Looked at again as the window is sized: what had room beside the view may have it no more.
addEventListener('resize', settle)

/** Closes the panel that is over the view on a narrow screen, where one is: whether one was. */
export function settlePanel() {
  const open = narrow.matches ? shown() : []
  for (const pane of open) pane.shut()
  return open.length > 0
}

/**
 * The panel a view keeps beside it, as Claude keeps an artifact or ChatGPT a canvas: open or
 * shut as this browser last left it, and over the view on a narrow screen. A panel of its own
 * -- Ai-chan's drawer -- is kept by its own `key`, shut where never left open, and told each
 * time it opens or shuts. One opened closes another where the view has no room for both.
 *
 * @param {string} label
 * @param {{key?: string, open?: boolean, hmz?: string, kind?: string, told?: (open: boolean) => void}} [how]
 */
export function sidePanel(label, { key = 'hmz-panel', open: first = true, hmz = 'inspector', kind = '', told = () => {} } = {}) {
  const body = h('div', { class: 'panel-body' })
  const shut = iconButton('close', t('Close panel'), { class: 'panel-close' })
  const node = h('aside', { class: ['inspector', kind], 'aria-label': label, 'data-hmz': hmz }, shut, body)
  const toggle = iconButton('panel', t('Toggle panel'), { class: 'panel-toggle' })
  const show = (open) => {
    node.hidden = !open
    toggle.setAttribute('aria-pressed', String(open))
    told(open)
  }
  const pane = { node, shut: () => node.hidden || set(false), yields: () => show(false) }
  const set = (open) => {
    show(open)
    if (!narrow.matches) keep(key, open === first ? null : open ? 'open' : 'shut')
    if (open) roomFor(pane)
  }
  // Open as it was last left, where the view has the room: another open beside it is looked
  // at once both are in the page.
  const read = () => {
    show(!narrow.matches && kept(key, first ? 'open' : 'shut') === 'open')
    panes.add(pane)
    settle()
  }
  read()
  toggle.addEventListener('click', () => set(node.hidden))
  shut.addEventListener('click', () => set(false))
  return {
    node,
    body,
    toggle,
    set,
    open: () => set(true),
    /** Keeps it from here on by another key, open or shut as that one was last left: a chat's panel, shut where never opened. */
    keptAs(other, opens) {
      key = other
      first = opens
      read()
      // In the page already, and about to be drawn: it gives way before it is.
      fit()
    },
  }
}

/**
 * The button, drawn as Ai-chan's avatar, that opens and closes her drawer (Section 3.16 of
 * protocol/web.md): on every view's bar, saying whether the drawer is open.
 */
export function aiChanButton() {
  const open = Boolean(app()?.classList.contains('aichan-open'))
  return h(
    'button',
    {
      class: 'icon-btn aichan-btn',
      type: 'button',
      'aria-label': 'Ai-chan',
      title: 'Ai-chan',
      'aria-controls': 'aichan',
      'aria-pressed': String(open),
      'data-hmz': 'aichan-toggle',
      onclick: () => dispatchEvent(new CustomEvent('hmz:aichan')),
    },
    h('img', { class: 'aichan-avatar', src: '/ai-chan/avatar.webp', alt: '', width: '24', height: '24' }),
  )
}

/**
 * Tabs over what a panel holds, each drawn when picked. The row is one stop of the Tab key, on
 * the tab picked; the arrow keys, Home and End move among its tabs, and Enter or Space picks.
 */
export function tabbed(tabs, picked, told) {
  const list = h('div', { class: 'tabs', role: 'tablist' })
  for (const [key, label] of tabs) {
    const tab = h('button', { type: 'button', role: 'tab', 'data-tab': key }, label)
    tab.addEventListener('click', () => told(key))
    list.append(tab)
  }
  list.addEventListener('keydown', (event) => {
    const all = [...list.querySelectorAll('[role=tab]')]
    const at = all.indexOf(event.target)
    const to = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: all.length - 1 }[event.key]
    if (at < 0 || to === undefined) return
    event.preventDefault()
    all[(to + all.length) % all.length].focus()
  })
  picks(list, picked)
  return list
}

/** Marks the tab of a key picked among a row's, and no other: it alone is a stop of the Tab key, the first where none is. */
export function picks(list, key) {
  const all = [...list.querySelectorAll('[role=tab]')]
  const at = all.findIndex((tab) => tab.dataset.tab === key)
  all.forEach((tab, n) => {
    tab.setAttribute('aria-selected', String(n === at))
    tab.setAttribute('tabindex', n === Math.max(at, 0) ? '0' : '-1')
  })
}

narrow.addEventListener('change', () => {
  for (const el of document.querySelectorAll('[data-dragged]')) reach(el)
  drawer(false)
})
