// What floats over the page for a moment -- a menu, a submenu, a menu at the pointer, a panel
// that is typed into -- kept as one chain: a root, and whatever was opened from inside it. One
// opening closes every other that it was not opened from, and the one set of listeners here
// closes them as a desktop app's are closed: by a press elsewhere, Escape, the focus leaving, a
// scroll that takes away what one stands by, the window sized or left, the page gone elsewhere.
// The tooltip and a box's completions yield to all of it. Imports nothing, and keeps the chain
// without a document, so that it is tested without one.

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
 * opened it has no box in the window any more.
 *
 * @param {'route'|'dialog'|'fold'|'resize'|'blur'} why
 */
export function dismiss(why) {
  quiet(why)
  drop()
  if (why !== 'resize' && why !== 'blur') return shut(0, HELD)
  const within = typeof document === 'undefined' ? null : document.activeElement
  const typed = within && typeof within.matches === 'function' && within.matches('input, textarea, [contenteditable]') ? layerOf(within) : -1
  const at = stack.findIndex((one, i) => (one.kind !== 'panel' && i > typed) || (why === 'resize' && one.anchor && !boxed(one.anchor)))
  if (at >= 0) shut(at, HELD)
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
 * on its backdrop closes it, and the page going elsewhere closes it as answered `away`.
 *
 * @param {HTMLDialogElement} dialog In the page, not shown yet.
 * @param {string} [away] What it returns where the page went elsewhere under it.
 */
export function modal(dialog, away = '') {
  dismiss('dialog')
  const left = () => dialog.close(away)
  dialog.addEventListener('click', (event) => {
    const box = dialog.getBoundingClientRect()
    // Its own padding is not its backdrop.
    if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) dialog.close()
  })
  dialog.addEventListener('close', () => (removeEventListener('hmz:route', left), drop()), { once: true })
  addEventListener('hmz:route', left)
  dialog.showModal()
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

if (typeof document !== 'undefined') {
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
  document.addEventListener(
    'keydown',
    (event) => {
      untip(event)
      if (event.isComposing) return
      drop()
      if (event.key !== 'Escape' || !stack.length) return rove(event)
      event.preventDefault()
      event.stopImmediatePropagation()
      shut(stack.length - 1, LOOSE)
    },
    true,
  )
  // The focus gone elsewhere, by Tab or by code, closes down to the layer that holds it. One
  // that came from nowhere -- the window looked at again, a choice drawn again -- closes nothing.
  document.addEventListener('focusin', (event) => {
    drop()
    const at = layerOf(event.target)
    strayed = pressing && at < 0 ? layerOf(event.relatedTarget) : -1
    if (!pressing && event.relatedTarget) shut(at + 1, NEVER)
  })
  // What a layer stands by scrolled away, it closes rather than chase it. A menu at the pointer
  // stands by nothing, and closes on any scroll but its own; a panel that stands by nothing
  // stands in its pane, whatever scrolls.
  document.addEventListener(
    'scroll',
    (event) => {
      untip(event)
      if (fresh) return
      drop()
      const at = stack.findIndex((one, i) => (one.anchor ? has(event.target, one.anchor) : one.kind !== 'panel' && !stack.slice(i).some((inner) => has(inner.node, event.target))))
      if (at >= 0) shut(at, HELD)
    },
    true,
  )
  addEventListener('resize', () => dismiss('resize'))
  addEventListener('blur', () => dismiss('blur'))
  addEventListener('hmz:route', () => dismiss('route'))
}
