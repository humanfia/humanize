// What floats over the page for a moment -- a menu, a submenu, a menu at the pointer, a panel
// that is typed into -- kept as one chain: a root, and whatever was opened from inside it. One
// opening closes every other that it was not opened from, and the one set of listeners here
// closes them as a desktop app's are closed: by a press elsewhere, Escape, the focus leaving, a
// scroll that takes away what one stands by, the window sized or left, the page gone elsewhere.
// The tooltip and a box's completions yield to all of it; and each is put by what opened it
// here, against the window. Imports nothing, and keeps the chain without a document, so that
// it is tested without one.

/**
 * One thing that floats.
 *
 * @typedef {object} Layer
 * @property {Element} node What is drawn.
 * @property {Element|null} [anchor] What opened it, which it stands by: none for a menu at the
 *   pointer, or a panel that stands in its pane. One whose anchor is inside another's node was
 *   opened from that one.
 * @property {() => void} close Its owner's own closer: says `closed(layer)` first, then takes
 *   the node away. Closing what is closed does nothing.
 * @property {'menu'|'panel'} [kind] `menu`, the default, holds only choices; `panel` holds
 *   something typed, which the window sized or left does not lose.
 * @property {HTMLElement|null} [back] What has the focus back as it closes, in place of the anchor.
 * @property {Element|null} [over] What one with no anchor was opened over, a menu at the pointer:
 *   scrolled away, it closes as one whose anchor was.
 * @property {'within'} [escape] `within` where Escape closes it only while the focus is inside
 *   it: one that stands by a whole pane, whose other keys are the pane's own.
 */

/** The open chain, root first. */
const stack = []
/**
 * Whether one closing gives the focus back to what opened it: never (`NEVER`), as where a press
 * or the focus gone elsewhere closed it; where it held the focus (`HELD`); or where it held
 * it or nothing does (`LOOSE`), as where its owner closed it -- a choice, its button, Escape.
 */
const [NEVER, HELD, LOOSE] = [0, 1, 2]
let handing = LOOSE
/** Whether a press is moving the focus: it has closed what it closes, and the focus closes no more. */
let pressing = false
/**
 * The layer a press landed in whose focus the browser then put outside the chain -- one that
 * gives a button pressed no focus puts it on whatever holds the button -- or -1: that layer
 * holds the focus still, as far as giving it back goes.
 */
let strayed = -1
/**
 * Whether one opened in this frame: a scroll told of in it happened before that, and is told of
 * only now, as scrolls are -- once a frame.
 */
let fresh = false
/** What held the focus as the window was left: the focus it has back as the window is looked at again moved nowhere. */
let away = null
/** What takes the tooltip down. */
let untip = () => {}
/** What closes each list of completions that is open. */
const yielding = new Set()

const page = typeof window === 'undefined' ? null : window
const has = (holder, el) => Boolean(holder && el && holder.contains(el))

/** The topmost layer a thing is in, or is what opened: -1 for none. */
function layerOf(target) {
  for (let at = stack.length - 1; at >= 0; at--) if (has(stack[at].node, target) || has(stack[at].anchor, target)) return at
  return -1
}

/** Whether a thing has a box within the window. */
function boxed(el) {
  if (!el.getBoundingClientRect) return true
  const box = el.getBoundingClientRect()
  return box.width > 0 && box.height > 0 && box.bottom > 0 && box.right > 0 && box.top < innerHeight && box.left < innerWidth
}

/** Whether what a layer draws is gone without its closer: taken out of the page, or hidden with what holds it. */
function gone(node) {
  return node.isConnected === false || (typeof node.getClientRects === 'function' && node.getClientRects().length === 0)
}

/** Lets go of every layer drawn no more, so that no key or press is spent on one. */
function drop() {
  const at = stack.findIndex((one) => gone(one.node))
  if (at >= 0) shut(at, NEVER)
}

/** Closes a layer and all opened from it; `hand` says whether the focus goes back to what opened it. */
function shut(from, hand) {
  const one = stack[from]
  if (!one) return
  const was = handing
  handing = hand
  try {
    one.close()
  } finally {
    // One whose closer did not say so is out of the chain all the same.
    closed(one)
    handing = was
  }
}

/** Takes down what yields: the tooltip always, completions unless only the window changed. */
function quiet(why) {
  untip()
  if (why === 'opened' || why === 'route' || why === 'dialog') for (const close of [...yielding]) close()
}

let telling = false

/** Says the chain changed, once its owners are done with what changed it. */
function tell() {
  if (!page || telling) return
  telling = true
  queueMicrotask(() => {
    telling = false
    page.dispatchEvent(new CustomEvent('hmz:layers', { detail: stack.length }))
  })
}

/**
 * A transient opened: every open one it was not opened from is closed first, so that one chain
 * at most is open. Said once its node is in the page and before the focus goes into it.
 *
 * @param {Layer} layer
 */
export function opened(layer) {
  if (stack.includes(layer)) return
  drop()
  quiet('opened')
  let parent = -1
  for (let at = stack.length - 1; at >= 0 && parent < 0; at--) if (has(stack[at].node, layer.anchor)) parent = at
  shut(parent + 1, HELD)
  stack.push(layer)
  if (typeof requestAnimationFrame === 'function') {
    fresh = true
    requestAnimationFrame(() => (fresh = false))
  }
  tell()
}

/**
 * A transient closed, by whatever closed it: it and every one opened from inside it leave the
 * chain, and the focus they held, or that nothing holds, goes back to what opened it -- unless
 * a press or the focus going elsewhere closed it, which has the focus already. Said by a
 * layer's closer before it takes the node away.
 *
 * @param {Layer} layer
 */
export function closed(layer) {
  const at = stack.indexOf(layer)
  if (at < 0) return
  const within = typeof document === 'undefined' ? null : document.activeElement
  const nowhere = handing === LOOSE && (!within || within === document.body)
  const held = handing !== NEVER && (nowhere || strayed >= at || stack.slice(at).some((one) => has(one.node, within)))
  if (strayed >= at) strayed = -1
  for (const one of stack.splice(at).slice(1).reverse()) one.close()
  const to = layer.back ?? layer.anchor
  if (held && to && to.isConnected !== false && typeof to.focus === 'function') to.focus({ preventScroll: true })
  tell()
}

/**
 * Everything transient closed, the tooltip with it: the page gone elsewhere (`route`), a dialog
 * opening (`dialog`), the sidebar folded or its drawer moved (`fold`). The window sized
 * (`resize`) or left (`blur`) closes menus alone: a panel keeps what was typed into it, as does
 * a menu while a field of it is being typed into, and on `resize` either goes only where what
 * opened it has no box in the window any more, a frame on.
 *
 * @param {'route'|'dialog'|'fold'|'resize'|'blur'} why
 */
export function dismiss(why) {
  quiet(why)
  drop()
  if (why !== 'resize' && why !== 'blur') return shut(0, HELD)
  const within = typeof document === 'undefined' ? null : document.activeElement
  const typed = within && typeof within.matches === 'function' && within.matches('input, textarea, [contenteditable]') ? layerOf(within) : -1
  const at = stack.findIndex((one, i) => one.kind !== 'panel' && i > typed)
  if (at >= 0) shut(at, HELD)
  if (why !== 'resize') return
  // Looked at a frame on, once what was kept is placed again in the window as it is now.
  const off = () => {
    drop()
    const lost = stack.findIndex((one) => one.anchor && !boxed(one.anchor))
    if (lost >= 0) shut(lost, HELD)
  }
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(off)
  else off()
}

/** The open chain, root first. */
export function chain() {
  drop()
  return [...stack]
}

/**
 * The tooltip's own hider: called for every press, key and scroll -- with the event -- and
 * with nothing whenever a transient opens or everything is dismissed.
 *
 * @param {(event?: Event) => void} hide
 */
export function tipping(hide) {
  untip = hide
}

/**
 * A list of completions open under what is typed: it claims no place in the chain and closes
 * nothing, and is closed by any transient opening, the page going elsewhere and a dialog.
 *
 * @param {() => void} close
 * @returns {() => void} What says it closed by itself.
 */
export function yields(close) {
  yielding.add(close)
  return () => yielding.delete(close)
}

/**
 * Shows a native dialog over everything, as a modal one: whatever floats closes first, a press
 * on its backdrop closes it -- one begun inside it and let go of on the backdrop, what was
 * selected dragged out of it, does not -- and the page going elsewhere closes it as answered
 * `away`.
 *
 * @param {HTMLDialogElement} dialog In the page, not shown yet.
 * @param {string} [away] What it returns where the page went elsewhere under it.
 */
export function modal(dialog, away = '') {
  dismiss('dialog')
  const left = () => dialog.close(away)
  const backdrop = (event) => {
    const box = dialog.getBoundingClientRect()
    // Its own padding is not its backdrop.
    return event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)
  }
  let begun = false
  dialog.addEventListener('pointerdown', (event) => (begun = backdrop(event)))
  dialog.addEventListener('click', (event) => begun && backdrop(event) && dialog.close())
  dialog.addEventListener('close', () => (removeEventListener('hmz:route', left), drop()), { once: true })
  addEventListener('hmz:route', left)
  dialog.showModal()
}

/** Room kept between whatever floats and the window's edge, and between it and what opened it. */
export const EDGE = 8
export const GAP = 6
/** How far under a bar's line what opens from the bar stands, where that is further than by what opened it. */
const CLEAR = 4

/**
 * Puts a popup by what opened it, against the window rather than whatever holds it -- a dialog
 * or a list that scrolls would cut it off -- as a desktop app puts a menu: on the side asked for
 * where it fits, on the other where that has more room, no taller than the room it has, and
 * moved in from an edge rather than past it. Under a bar it opens clear of the bar's line.
 *
 * @param {HTMLElement} pop The popup, shown.
 * @param {Element} anchor What opened it.
 * @param {{align?: 'start'|'end', up?: boolean, span?: boolean, by?: Element|null, clear?: boolean}} how
 *   Which edge of it the popup lines up with, whether it would rather open over it, and whether
 *   it is as wide as it; `by`, a box it stands clear of as it does of what opened it, under
 *   both or over both; `clear`, false for what a bar's line is nothing to -- a tip.
 */
export function place(pop, anchor, { align = 'start', up = false, span = false, by = null, clear = true } = {}) {
  const box = anchor.getBoundingClientRect()
  const also = (by ?? anchor).getBoundingClientRect()
  // What opens from inside a box that is typed into opens over the whole box, never on it; a
  // chip of the row under the box opens from the chip itself.
  const typed = (anchor.closest('.composer-box') ?? anchor).getBoundingClientRect()
  const top = Math.min(box.top, also.top, typed.top)
  const bar = clear ? anchor.closest('.bar')?.getBoundingClientRect() : null
  const under = Math.max(Math.max(box.bottom, also.bottom) + GAP, bar ? bar.bottom + CLEAR : 0)
  if (span) pop.style.width = `${box.width}px`
  pop.style.removeProperty('--room')
  // Measured from the window's own edge: where it last stood, or stands before it is placed,
  // the window's far edge may leave it narrower than it is.
  pop.style.left = '0'
  const room = { below: innerHeight - under - EDGE, above: top - GAP - EDGE }
  const [first, second] = up ? ['above', 'below'] : ['below', 'above']
  const side = pop.offsetHeight <= room[first] || room[first] >= room[second] ? first : second
  pop.style.setProperty('--room', `${Math.max(room[side], 80)}px`)
  const { offsetWidth: wide, offsetHeight: tall } = pop
  pop.style.top = `${side === 'below' ? under : Math.max(EDGE, top - GAP - tall)}px`
  const left = align === 'end' ? box.right - wide : box.left
  pop.style.left = `${Math.max(EDGE, Math.min(left, innerWidth - wide - EDGE))}px`
}

/** Says that what a popup holds was drawn again, of another size: it is placed again at once. */
export function redrawn(inside) {
  inside.dispatchEvent(new Event('redrawn', { bubbles: true }))
}

/**
 * Places a popup and keeps it by what opened it as the window is sized or the popup grows; says
 * how to stop. What opened it scrolled away, it is closed, not sent after it.
 */
export function follow(pop, anchor, how) {
  const again = () => place(pop, anchor, how)
  again()
  // Placed again in the next frame rather than inside the observer's own: placing it sizes it,
  // which said there would be a size the observer is not told of, and an error.
  let frame = 0
  const grown = new ResizeObserver(() => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(again)
  })
  grown.observe(pop)
  addEventListener('resize', again)
  // What draws another thing in it says so (`redrawn`), and it is placed before it is seen:
  // a menu over its button would else stand a frame on the button.
  pop.addEventListener('redrawn', again)
  return () => {
    grown.disconnect()
    cancelAnimationFrame(frame)
    removeEventListener('resize', again)
    pop.removeEventListener('redrawn', again)
  }
}

/** How far each key moves through a menu's choices: to the first and the last for the other two. */
const MOVES = { ArrowDown: 1, ArrowUp: -1, Home: 0, End: 0 }

/** Moves the focus through the choices of the menu it is in, as a desktop app's arrow keys do. */
function rove(event) {
  const from = event.target
  if (!(event.key in MOVES) || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || typeof from?.closest !== 'function') return
  const menu = from.closest('[role=menu]')
  if (!menu || from.matches('select, textarea, [contenteditable], input[type=number], input[type=range], input[type=radio]')) return
  // A field's own Home and End are its text's.
  if (from.matches('input') && !MOVES[event.key]) return
  // This menu's own choices, not those of one opened from it.
  const items = [...menu.querySelectorAll('[role^=menuitem]:not(:disabled, [hidden])')].filter((one) => one.closest('[role=menu]') === menu)
  if (!items.length) return
  const at = items.indexOf(from)
  const to = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : event.key === 'ArrowDown' ? (at + 1) % items.length : (at <= 0 ? items.length : at) - 1
  event.preventDefault()
  items[to].focus()
}

if (page && typeof document !== 'undefined') {
  // The focus a press moves goes where the browser puts it -- off a button pressed, in some,
  // onto whatever holds it -- as the press goes down, a finger's as it ends: before the button
  // is let go of, and before anything else runs.
  const lifted = () => {
    pressing = false
  }
  const pressed = () => {
    pressing = true
    setTimeout(lifted)
  }
  // A press outside the chain closes it, and is not swallowed: what was pressed still answers.
  // One inside a layer, or on what opened it, closes only what was opened from that layer.
  document.addEventListener(
    'pointerdown',
    (event) => {
      pressed()
      untip(event)
      drop()
      const at = layerOf(event.target)
      if (strayed >= 0) strayed = at
      shut(at + 1, NEVER)
    },
    true,
  )
  document.addEventListener('mousedown', pressed, true)
  document.addEventListener('mouseup', lifted, true)
  // Escape closes the topmost alone, and goes no further: one press never closes two things.
  // One that takes it only from inside itself leaves it, pressed elsewhere, to what it was pressed in.
  document.addEventListener(
    'keydown',
    (event) => {
      untip(event)
      if (event.isComposing) return
      drop()
      const top = stack.at(-1)
      if (event.key !== 'Escape' || !top) return rove(event)
      if (top.escape === 'within' && !has(top.node, event.target)) return
      event.preventDefault()
      event.stopImmediatePropagation()
      shut(stack.length - 1, LOOSE)
    },
    true,
  )
  // The focus gone elsewhere, by Tab or by code, closes down to the layer that holds it. The
  // focus the window has back as it is looked at again, where it was, went nowhere and closes
  // nothing.
  document.addEventListener('focusin', (event) => {
    drop()
    const at = layerOf(event.target)
    strayed = pressing && at < 0 ? layerOf(event.relatedTarget) : -1
    if (!pressing && event.target !== away) shut(at + 1, NEVER)
    away = null
  })
  // What a layer stands by scrolled away, it closes rather than chase it. A menu at the pointer
  // stands by nothing: it closes as what it was opened over scrolls away or, opened over
  // nothing, on any scroll but its own. A panel that stands by nothing stands in its pane,
  // whatever scrolls.
  document.addEventListener(
    'scroll',
    (event) => {
      untip(event)
      if (fresh) return
      drop()
      const at = stack.findIndex((one, i) => {
        const by = one.anchor ?? one.over
        return by ? has(event.target, by) : one.kind !== 'panel' && !stack.slice(i).some((inner) => has(inner.node, event.target))
      })
      if (at >= 0) shut(at, HELD)
    },
    true,
  )
  addEventListener('resize', () => dismiss('resize'))
  // The focus gone into a frame is a press or a Tab this page is told nothing more of: it closes
  // what a press there would, a panel with the menus -- looked for once more a turn on, where
  // the browser says where the focus went only after saying the window was left.
  const framed = () => {
    const at = document.activeElement
    if (at?.tagName === 'IFRAME') shut(layerOf(at) + 1, NEVER)
  }
  addEventListener('blur', () => {
    away = document.activeElement
    dismiss('blur')
    framed()
    setTimeout(framed)
  })
  addEventListener('hmz:route', () => dismiss('route'))
}
