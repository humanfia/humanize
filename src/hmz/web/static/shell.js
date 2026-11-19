// What every view stands in: the bar over it, with the button that brings the sidebar back
// where it is folded away, a title and what can be done; the menus that open under a button;
// and the side panel a view can keep beside it. Whether the sidebar and the side panel are
// open is this browser's own, kept between visits.

import { h, icon, iconButton } from './dom.js'

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
  const root = app()
  const side = root.querySelector('.sidebar')
  const within = side.contains(document.activeElement)
  // Nothing in particular holds the focus: the page, or the view as a whole, which is where a
  // browser that gives a button pressed no focus leaves it. Never what is being typed into,
  // which a key that folds the sidebar leaves alone.
  const loose = document.activeElement === document.body || document.activeElement === root.querySelector('.main')
  if (narrow.matches) {
    const now = open ?? !root.classList.contains('side-open')
    drawer(now)
    // The drawer is over the page, which no key reaches while it is: the focus goes into it as
    // it opens, and back to what opens it as it closes.
    if (now) side.querySelector('.side-fold')?.focus()
    else if (within || loose) root.querySelector('.bar-side')?.focus()
    return
  }
  const now = open ?? root.classList.contains('side-folded')
  const pressed = loose || document.activeElement?.classList.contains('bar-side')
  root.classList.toggle('side-folded', !now)
  keep('hmz-sidebar', now ? null : 'folded')
  // The button pressed is gone with what it did: the one that undoes it has the focus.
  if (now && pressed) side.querySelector('.side-fold')?.focus()
  else if (!now && (within || loose)) root.querySelector('.bar-side')?.focus()
}

/** Opens or closes the drawer the sidebar is on a narrow screen: the page under it is out of reach while it is open. */
function drawer(open) {
  const root = app()
  root.classList.toggle('side-open', open)
  document.querySelector('.scrim').hidden = !open
  root.querySelector('.main').inert = open
}

/** Closes the drawer the sidebar is on a narrow screen, once somewhere in it was picked. */
export function settleSidebar() {
  if (narrow.matches) drawer(false)
}

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

/**
 * The bar over a view: what it is, and what can be done to it. Ai-chan's button ends it, save
 * where the view offers her among its own -- a chat's, whose bar ends as a chat app's does.
 */
export function bar({ title = '', sub = null, actions = [], lead = null, aichan = true } = {}) {
  return dragged(
    h(
      'header',
      { class: 'bar', 'data-hmz': 'bar' },
      iconButton('sidebar', 'Show sidebar', { class: 'bar-side', onclick: () => toggleSidebar(true), 'aria-controls': 'sidebar' }),
      lead,
      h('div', { class: 'bar-title' }, title ? h('h1', {}, title) : null, sub ? h('div', { class: 'bar-sub' }, sub) : null),
      h('div', { class: 'bar-actions' }, actions, aichan ? aiChanButton() : null),
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
  // Placed again in the next frame rather than inside the observer's own: placing it sizes it,
  // which said there would be a size the observer is not told of, and an error.
  let frame = 0
  const grown = new ResizeObserver(() => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => again())
  })
  grown.observe(pop)
  addEventListener('scroll', again, true)
  addEventListener('resize', again)
  return () => {
    grown.disconnect()
    cancelAnimationFrame(frame)
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
    removeEventListener('hmz:route', away)
  }
  // The page gone elsewhere -- a dialog opened over it by a key, say -- it is not left open over
  // that; what opened it has the focus it held, before the page looks at what holds it.
  const away = () => {
    const held = open && open.contains(document.activeElement)
    close()
    if (held) anchor.focus()
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
    addEventListener('hmz:route', away)
    // On the one chosen, where one is, as a desktop app's menu opens on it.
    ;(open.querySelector('.choice.chosen') || open.querySelector('button, a'))?.focus()
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

/**
 * A choice in a menu that opens a menu of its own beside it: on a pointer resting on it, a click,
 * or the right arrow; shut as the pointer leaves both, by the left arrow, or with the menu it is in.
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
  const shut = () => {
    open?.remove()
    open = null
    opener.setAttribute('aria-expanded', 'false')
  }
  const show = (focus) => {
    clearTimeout(leaving)
    if (!open) {
      open = h('div', { class: 'popover sub', role: 'menu', 'aria-label': label, 'data-hmz': hmz }, items())
      holder.append(open)
      opener.setAttribute('aria-expanded', 'true')
      // Beside the menu it is in, on the right where there is room, else on the left, else -- on
      // a phone -- over it, under the choice that opened it or, with no room there, above it.
      const outer = holder.closest('.popover').getBoundingClientRect()
      const row = opener.getBoundingClientRect()
      const { offsetWidth: wide, offsetHeight: tall } = open
      const right = outer.right + wide + EDGE <= innerWidth
      const beside = right || outer.left - wide >= EDGE
      const left = right ? outer.right - 2 : beside ? outer.left - wide + 2 : outer.left + 12
      const top = beside ? row.top - 8 : row.bottom + tall + EDGE <= innerHeight ? row.bottom : row.top - tall
      open.style.left = `${Math.max(EDGE, Math.min(left, innerWidth - wide - EDGE))}px`
      open.style.top = `${Math.max(EDGE, Math.min(top, innerHeight - tall - EDGE))}px`
    }
    if (focus) open.querySelector('button, a')?.focus()
  }
  holder.addEventListener('pointerenter', (event) => event.pointerType === 'mouse' && show(false))
  holder.addEventListener('pointerleave', (event) => {
    if (event.pointerType === 'mouse') leaving = setTimeout(shut, 250)
  })
  opener.addEventListener('click', () => (open && !open.contains(document.activeElement) ? open.querySelector('button, a')?.focus() : show(true)))
  holder.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowRight' && event.target === opener) show(true)
    else if (event.key === 'ArrowLeft' && open) {
      shut()
      opener.focus()
    } else return
    event.preventDefault()
    // One opened from a choice of another shuts alone: the one it is in stays open.
    event.stopPropagation()
  })
  return holder
}

/** A heading among a menu's choices. */
export function section(label) {
  return h('div', { class: 'popover-head', role: 'presentation' }, label)
}

/**
 * The panel a view keeps beside it, as Claude keeps an artifact or ChatGPT a canvas: open or
 * shut as this browser last left it, and over the view on a narrow screen. A panel of its own
 * -- Ai-chan's drawer -- is kept by its own `key`, shut where never left open, and told each
 * time it opens or shuts.
 *
 * @param {string} label
 * @param {{key?: string, open?: boolean, hmz?: string, kind?: string, told?: (open: boolean) => void}} [how]
 */
export function sidePanel(label, { key = 'hmz-panel', open: first = true, hmz = 'inspector', kind = '', told = () => {} } = {}) {
  const body = h('div', { class: 'panel-body' })
  const shut = iconButton('close', 'Close panel', { class: 'panel-close' })
  const node = h('aside', { class: ['inspector', kind], 'aria-label': label, 'data-hmz': hmz }, shut, body)
  const toggle = iconButton('panel', 'Toggle panel', { class: 'panel-toggle' })
  const set = (open) => {
    node.hidden = !open
    toggle.setAttribute('aria-pressed', String(open))
    if (!narrow.matches) keep(key, open === first ? null : open ? 'open' : 'shut')
    told(open)
  }
  const read = () => set(!narrow.matches && kept(key, first ? 'open' : 'shut') === 'open')
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
    h('img', { class: 'aichan-avatar', src: '/ai-chan/avatar.png', alt: '', width: '24', height: '24' }),
  )
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
  for (const el of document.querySelectorAll('[data-dragged]')) reach(el)
  drawer(false)
})
