// Exomyth's Flame: the epic's spans as a flame graph, drawn from the model model.js reads
// (see the comment at its top), over the stretch of time picked on the Timeline or the whole.

import { empty, fill } from '../../dom.js'

/**
 * Draws the Flame into an element.
 *
 * @param {HTMLElement} el Where it is drawn.
 * @param {object} model The model, as model.js reads it.
 * @param {{from: number, to: number}|null} range The stretch of time picked, µs, or null.
 * @returns {{update?: (model: object, range: object|null) => void, leave?: () => void}} How it
 *   is drawn again, and left.
 */
export function mount(el, model, range) {
  fill(el, empty('Nothing here yet.', ' The flame graph comes next.'))
  return { update() {} }
}
