// A menu that picks a thing a level at a time, in the one place it opened: first a row a level,
// each saying what is picked at it, and from a row the choices of that level alone, with the way
// back over them. A level with one choice has no row; one that is said and not picked is a line
// that opens nothing. Every nous the page offers is picked through it -- its harness, its account,
// its model and its effort (chips/model.js) -- so that no menu lists them all at once.

import { fill, h, icon } from '../dom.js'
import { t } from '../i18n.js'
import { redrawn } from '../layers.js'

/**
 * @typedef {object} Level
 * @property {string} key What it is found by, and its word in `data-hmz`.
 * @property {string} title What it picks: `Model`.
 * @property {string} said What is picked at it now.
 * @property {boolean} [skip] Whether it has no row: it has one choice, or none.
 * @property {boolean} [fixed] Whether it is said and not picked.
 * @property {(to: {go: (key: string) => void, back: () => void}) => unknown} [rows] Its choices.
 */

/** A part that is said and not picked: its name where a choice's is, and what it is at its end. */
export function fact(label, value, mono = false) {
  return h('div', { class: 'model-fact' }, h('span', { class: 'label' }, label), h('span', { class: ['fact-value', mono && 'mono'] }, value))
}

/**
 * The body of such a menu.
 *
 * @param {object} made
 * @param {() => Level[]} made.levels Its levels, in the order they are picked, read each time it is drawn.
 * @param {(to: {go: (key: string) => void}) => unknown} [made.head] What stands over the rows of the levels.
 * @param {(to: {go: (key: string) => void}) => unknown} [made.foot] What stands under them.
 * @param {string} [made.hmz] What each row's `data-hmz` begins with.
 * @returns {{node: HTMLElement, go: (key: string) => void, back: () => void, again: () => void, at: () => string}}
 *   The body; a way to its level `key` and back to the rows; a way to draw it again where it
 *   stands, as what it offers changes under whoever reads it; and the level it is at, '' for the rows.
 */
export function stepped({ levels, head = () => null, foot = () => null, hmz = 'step' }) {
  const node = h('div', { class: 'model-menu steps' })
  let at = ''
  const to = { go, back }

  /** The row of a level: what it picks, what is picked, and the mark that it opens. */
  function row(one) {
    if (one.fixed) return fact(one.title, one.said)
    const el = h(
      'button',
      { class: 'choice step', type: 'button', role: 'menuitem', 'data-hmz': `${hmz}-${one.key}` },
      h('span', { class: 'choice-mark', 'aria-hidden': 'true' }),
      h('span', { class: 'choice-text' }, h('span', { class: 'choice-label' }, one.title), h('span', { class: 'choice-about' }, one.said)),
      h('span', { class: 'choice-more', 'aria-hidden': 'true' }, icon('chevron')),
    )
    el.addEventListener('click', () => go(one.key))
    el.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowRight') return
      event.preventDefault()
      go(one.key)
    })
    return el
  }

  /** Draws the rows, or the level it is at, and has the menu placed by its button again. */
  function draw() {
    drawn()
    redrawn(node)
  }

  function drawn() {
    const shown = levels().filter((one) => !one.skip)
    const level = shown.find((one) => one.key === at && !one.fixed)
    if (!level) at = ''
    node.dataset.step = at
    if (!level) return fill(node, head(to), shown.map(row), foot(to))
    const leave = h('button', { class: 'choice step-back', type: 'button', role: 'menuitem', 'data-hmz': `${hmz}-back`, 'aria-label': t('Back from {level}', { level: level.title }) }, h('span', { class: 'choice-mark', 'aria-hidden': 'true' }, icon('back')), h('span', { class: 'choice-text' }, h('span', { class: 'choice-label' }, level.title)))
    leave.addEventListener('click', back)
    return fill(node, leave, h('hr'), level.rows(to))
  }

  /** Puts the keys where they are wanted: on what is chosen, else the first choice past the way back. */
  function focus(on) {
    const all = [...node.querySelectorAll('button, a')]
    ;(on || node.querySelector('.choice.chosen') || all.find((one) => !one.classList.contains('step-back')) || all[0])?.focus()
  }

  function go(key) {
    at = key
    draw()
    focus()
  }

  function back() {
    const was = at
    at = ''
    draw()
    focus(node.querySelector(`[data-hmz=${hmz}-${was}]`))
  }

  /** Drawn again where it stands, the keys kept in it: but not while something is typed into it. */
  function again() {
    const held = document.activeElement
    if (!node.isConnected || (node.contains(held) && held.closest('input'))) return
    const mine = node.contains(held)
    const was = mine ? { hmz: held.dataset.hmz, value: held.dataset.value } : null
    draw()
    if (!mine) return
    focus([...node.querySelectorAll('button, a')].find((one) => (was.hmz ? one.dataset.hmz === was.hmz : was.value !== undefined && one.dataset.value === was.value)))
  }

  // The left arrow goes back, as it leaves a menu opened beside another: but not out of a field.
  node.addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowLeft' || !at || event.target?.closest?.('input')) return
    event.preventDefault()
    back()
  })
  draw()
  return { node, go, back, again, at: () => at }
}
