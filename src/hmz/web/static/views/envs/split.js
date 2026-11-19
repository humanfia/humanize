// The line between a list and what stands beside it, which sizes the list: the tree of
// environments against the one picked, the explorer against the editor, the list of changes
// against the diff. Dragged, or moved by the arrow keys, it sets how wide the list is, in whole
// pixels, on what holds them both, and this browser keeps it; double-clicked, the list is as
// wide as its stylesheet makes it.

import { h } from '../../dom.js'
import { keep, kept } from '../../shell.js'
import { clampWidth } from './tree.js'

/** How far a key moves the line, in pixels. */
const STEP = 16

/**
 * @param {HTMLElement} holder What holds the list, the line and what is beside them: its
 *   stylesheet lays the list out as wide as its custom property `name` says.
 * @param {object} how
 * @param {string} how.name The custom property.
 * @param {string} how.key What this browser keeps the width under.
 * @param {string} how.label What the line is called.
 * @param {string} [how.kind] A class it is drawn with, beside the one every such line has.
 * @param {number} [how.least] The narrowest the list may be, in pixels.
 * @param {(whole: number) => number} how.most The widest it may be, out of how wide what holds
 *   it is: both as its stylesheet holds it.
 * @param {string} how.hmz
 * @returns {HTMLElement} The line, which stands right after the list.
 */
export function splitter(holder, { name, key, label, kind = '', least = 160, most, hmz }) {
  const el = h('div', { class: ['envs-resizer', kind], role: 'separator', tabindex: '0', 'aria-orientation': 'vertical', 'aria-label': label, 'aria-valuemin': String(least), 'data-hmz': hmz })
  /** How wide the list is drawn. */
  const wide = () => Math.round(el.previousElementSibling?.getBoundingClientRect().width || 0)
  const said = () => {
    el.setAttribute('aria-valuenow', String(wide()))
    el.setAttribute('aria-valuemax', String(clampWidth(Infinity, most(holder.clientWidth), least)))
  }
  /** Asks for the list that wide: its stylesheet may draw it narrower. */
  const size = (to) => holder.style.setProperty(name, `${clampWidth(to, most(holder.clientWidth), least)}px`)
  /**
   * Keeps the list as wide as it is drawn now. Drawn no wider or narrower than `from`, as it
   * was before it was sized, it was held by its stylesheet: what sized it then, `before`, is
   * put back, since a width kept here would hold the list once there is room again.
   */
  const settle = (from, before) => {
    const now = wide()
    if (now === from) holder.style.setProperty(name, before)
    else {
      holder.style.setProperty(name, `${now}px`)
      keep(key, String(now))
    }
    said()
  }
  // The width kept is asked for as it is: the stylesheet draws what there is room for.
  const was = Number(kept(key, ''))
  if (was > 0) holder.style.setProperty(name, `${clampWidth(was, Infinity, least)}px`)
  // Sized by nothing of its own, the list is as wide as what holds it leaves it.
  new ResizeObserver(said).observe(holder)
  el.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return
    event.preventDefault()
    const from = wide()
    const before = holder.style.getPropertyValue(name)
    el.setPointerCapture(event.pointerId)
    el.classList.add('dragging')
    const move = (at) => {
      size(from + at.clientX - event.clientX)
      said()
    }
    const up = () => {
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerup', up)
      el.removeEventListener('pointercancel', up)
      el.classList.remove('dragging')
      settle(from, before)
    }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
    el.addEventListener('pointercancel', up)
  })
  el.addEventListener('dblclick', () => {
    holder.style.removeProperty(name)
    keep(key, null)
    said()
  })
  el.addEventListener('keydown', (event) => {
    const to = { ArrowLeft: wide() - STEP, ArrowRight: wide() + STEP, Home: 0, End: Infinity }[event.key]
    if (to === undefined) return
    event.preventDefault()
    const from = wide()
    const before = holder.style.getPropertyValue(name)
    size(to)
    settle(from, before)
  })
  return el
}
