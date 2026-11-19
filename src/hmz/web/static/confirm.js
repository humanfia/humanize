// A question asked in place of its button, kept among what floats over the page while it is
// asked: one at a time, and taken back -- as its own Cancel takes it back -- by Escape, a press
// elsewhere, the focus leaving it, a menu or a dialog opening, and the page going elsewhere.

import { confirming as asking } from './dom.js'
import { closed, opened } from './layers.js'

/**
 * dom.js's `confirming`, with the same say: a button that asks before it does something that
 * cannot be undone. Taken back, its button has the focus the question held.
 *
 * @param {Parameters<typeof asking>[0]} how
 * @returns {HTMLElement}
 */
export function confirming(how) {
  const holder = asking(how)
  /** The answer that takes the question back, while it is asked and not yet answered. */
  const no = () => {
    const answers = holder.querySelectorAll('button')
    return answers.length === 2 && !answers[1].disabled ? answers[1] : null
  }
  // It stands in the page, by nothing that a scroll could take from it, and what it asks is
  // not lost by the window sized or left: a panel.
  const layer = {
    node: holder,
    kind: 'panel',
    close() {
      const within = holder.contains(document.activeElement)
      closed(layer)
      no()?.click()
      if (within) holder.querySelector('button:enabled')?.focus()
    },
  }
  // Told once whichever of its buttons was pressed has done what it does: its own button asks,
  // and an answer ends the asking -- Cancel giving the focus to the button drawn again.
  holder.addEventListener('click', () => {
    if (no()) return opened(layer)
    layer.back = holder.querySelector('button:enabled')
    closed(layer)
  })
  return holder
}
