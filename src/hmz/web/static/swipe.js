// A row swiped to the left by a finger, as a chat app's is: what stands past its right edge --
// what can be done to it -- comes in as far as the row is dragged, and stays once it is dragged
// past half of that; and a row a finger rests on opens its menu. One row is open at a time, and a touch
// anywhere else, or another row opened, shuts it. Only a finger does either: a pointer has the
// row's menu under its other button.

/** How far a finger moves before what it does is told: a swipe of the row, or a scroll of its list. */
export const SLOP = 8

/** How long a finger rests on a row before the row's menu opens, in milliseconds. */
export const HOLD = 500

/**
 * Which way a finger that moved is taken to go: `x`, along the row, which swipes it; `y`, which
 * scrolls its list; or '' while it has not moved far enough to say.
 */
export function axisOf(dx, dy) {
  if (Math.hypot(dx, dy) < SLOP) return ''
  return Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'
}

/**
 * How far to the left a row dragged by `dx` is drawn, as a number not above 0: from where it
 * stood -- shut, or open by the width of what stands past it -- and no further than that width.
 */
export function offsetOf(dx, width, open) {
  return Math.max(-width, Math.min(0, (open ? -width : 0) + dx))
}

/** Whether a row let go at an offset stays open: dragged past half of what stands past it. */
export function restsOpen(offset, width) {
  return width > 0 && -offset > width / 2
}

/** The row open now, as what shuts it, or null. */
let shown = null

/** Shuts the row a swipe left open, if any. */
export function unswiped() {
  shown?.()
}

/**
 * Lets a finger swipe a row to the left, bringing in what stands past its right edge, and open
 * its menu by resting on it. The row says how far it is drawn as its `--swipe`, which whatever
 * of it moves is moved by; `swiping` as a class while a finger drags it; and `swiped` while it
 * is open.
 *
 * @param {HTMLElement} row The row.
 * @param {HTMLElement} tray What stands past its right edge: inert until the row is open.
 * @param {{held?: () => void}} [how] `held`: what a finger resting on the row does.
 * @returns {{shut: () => void}}
 */
export function swiped(row, tray, { held = () => {} } = {}) {
  let open = false
  /** The touch followed: where it began, which way it goes, and the timer of its rest. */
  let touch = null

  const put = (offset, moving) => {
    row.classList.toggle('swiping', moving)
    if (offset) row.style.setProperty('--swipe', `${offset}px`)
    else row.style.removeProperty('--swipe')
  }
  const settle = (to) => {
    open = to
    row.classList.toggle('swiped', open)
    tray.inert = !open
    put(open ? -tray.offsetWidth : 0, false)
    if (open) {
      if (shown && shown !== shut) shown()
      shown = shut
    } else if (shown === shut) shown = null
  }
  const shut = () => settle(false)
  /** What stops the click of a press that was a swipe or a rest, until the finger is lifted. */
  let stopper = null
  const unclicked = () => {
    if (stopper) return
    stopper = (event) => {
      event.preventDefault()
      event.stopPropagation()
    }
    row.addEventListener('click', stopper, { capture: true })
  }
  /** The finger lifted, the click it made, if any, has come: the next press is its own. */
  const lifted = () => {
    const was = stopper
    if (!was) return
    setTimeout(() => {
      row.removeEventListener('click', was, { capture: true })
      if (stopper === was) stopper = null
    }, 50)
  }
  const done = () => {
    if (!touch) return
    clearTimeout(touch.resting)
    touch = null
  }

  row.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'touch' || !event.isPrimary) return
    done()
    touch = { id: event.pointerId, x: event.clientX, y: event.clientY, axis: '', offset: open ? -tray.offsetWidth : 0, resting: 0 }
    // On the row itself, never on what is under it: those are pressed, not rested on.
    if (!tray.contains(event.target))
      touch.resting = setTimeout(() => {
        if (!touch || touch.axis) return
        done()
        unclicked()
        held()
      }, HOLD)
  })
  row.addEventListener('pointermove', (event) => {
    if (!touch || event.pointerId !== touch.id) return
    const dx = event.clientX - touch.x
    if (!touch.axis) {
      touch.axis = axisOf(dx, event.clientY - touch.y)
      if (!touch.axis) return
      clearTimeout(touch.resting)
      if (touch.axis === 'x') {
        // Followed off the row, and never a press of it.
        try {
          row.setPointerCapture(event.pointerId)
        } catch {
          // A touch the browser no longer follows is followed while it stays on the row.
        }
        unclicked()
      }
    }
    if (touch.axis !== 'x') return
    touch.offset = offsetOf(dx, tray.offsetWidth, open)
    put(touch.offset, true)
  })
  const letGo = (event) => {
    lifted()
    if (!touch || event.pointerId !== touch.id) return
    const { axis, offset } = touch
    done()
    if (axis === 'x') settle(event.type === 'pointerup' ? restsOpen(offset, tray.offsetWidth) : open)
  }
  row.addEventListener('pointerup', letGo)
  row.addEventListener('pointercancel', letGo)
  // The browser's own menu of a finger at rest, where it has one, is the row's: opened once.
  row.addEventListener('contextmenu', done)
  return { shut }
}

// A touch or a press anywhere but on the row open shuts it, as does its list scrolled.
if (typeof document !== 'undefined') {
  document.addEventListener(
    'pointerdown',
    (event) => {
      if (shown && !(event.target instanceof Element && event.target.closest('.swiped'))) shown()
    },
    { capture: true },
  )
  document.addEventListener('scroll', () => shown?.(), { capture: true, passive: true })
}
