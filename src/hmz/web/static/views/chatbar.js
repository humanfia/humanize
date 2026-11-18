// What a chat's bar is made of, as a chat app's session keeps its toolbar: the chat's title as a
// button with its menu right after it, and at the far right a button for each pane that opens
// beside the conversation -- its details, and the terminal, the changes and the files of the
// environment it works in -- then a menu of what else can be shown (Section 3.6.6.10 of
// protocol/web.md). Which pane a button is of, and what pressing it does, is desk.js's.

import { PANES, paneSaid } from '../desk.js'
import { h, svg } from '../dom.js'

/** The drawings of the bar's buttons, each a few strokes in a 24 by 24 box, as dom.js draws its own. */
const GLYPHS = {
  details: ['M3 4h18v16H3Z', 'M15 4v16'],
  terminal: ['M3 4h18v16H3Z', 'm7 9 3 3-3 3', 'M12 15h5'],
  changes: ['M8 4v8', 'M4 8h8', 'M4 18h8', 'M16 6v12', 'M13 15l3 3 3-3'],
  files: ['M3 6h6l2 2h10v11H3Z'],
  view: ['M4 6h10', 'M18 6h2', 'M4 12h4', 'M12 12h8', 'M4 18h12', 'M20 18h0', 'M16 4v4', 'M10 10v4', 'M18 16v4'],
  more: ['M4 11h2v2H4Z', 'M11 11h2v2h-2Z', 'M18 11h2v2h-2Z'],
  usage: ['M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z'],
}

/** One of the drawings above. */
export function glyph(name) {
  return svg(
    'svg',
    { class: `icon icon-${name}`, viewBox: '0 0 24 24', width: '18', height: '18', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'square', 'stroke-linejoin': 'miter', 'aria-hidden': 'true' },
    GLYPHS[name].map((d) => svg('path', { d })),
  )
}

/** A button of the bar, drawn as an icon alone and said by its label. */
export function barButton(name, label, props = {}) {
  const { class: extra, ...rest } = props
  return h('button', { type: 'button', 'aria-label': label, title: label, ...rest, class: ['icon-btn', ...[extra].flat()] }, glyph(name))
}

/**
 * The buttons of the panes beside a chat, in the bar's order, each pressed while its pane is the
 * one open.
 *
 * @param {(key: string) => void} press Told the pane whose button was pressed.
 * @returns {{nodes: HTMLElement[], said: (open: string, has: (key: string) => boolean, held: boolean) => void}}
 *   The buttons, and a way to say which pane is open, which the chat has now, and whether a
 *   host holds it.
 */
export function paneButtons(press) {
  const buttons = new Map(
    PANES.map((one) => [
      one.key,
      barButton(one.key, one.label, { class: ['pane-toggle', one.key === 'details' && 'panel-toggle'], 'aria-pressed': 'false', 'data-hmz': `pane-${one.key}`, onclick: () => press(one.key) }),
    ]),
  )
  return {
    nodes: [...buttons.values()],
    said(open, has, held) {
      for (const [key, button] of buttons) {
        button.setAttribute('aria-pressed', String(key === open))
        // A pane the chat has not got now -- no host holds it, or its environment keeps none --
        // is still said, cannot be opened, and says which of the two it is.
        button.disabled = !has(key)
        button.title = paneSaid(key, has(key), held)
      }
    },
  }
}
