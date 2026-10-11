// The box a person types into at the foot of a view, as in a chat: it grows with what is
// typed, Enter sends it and Shift+Enter starts a new line, and what refused it is said over it.

import { fill, h, icon, problem } from './dom.js'

/**
 * @param {object} made
 * @param {string} made.placeholder What it says while empty.
 * @param {string} made.label What it is, to whoever cannot see it.
 * @param {(text: string) => Promise<unknown>} made.submit What sending does; what it throws is said.
 * @param {Node[]} [made.tools] What stands on its bar beside the send button.
 * @param {string} [made.value] What it holds to begin with.
 * @param {boolean} [made.empty] Whether it may be sent empty.
 */
export function composer({ placeholder, label, submit, tools = [], value = '', empty = false }) {
  const text = h('textarea', { rows: '1', placeholder, 'aria-label': label, 'data-hmz': 'composer-text' }, value)
  const send = h('button', { class: 'send', type: 'submit', 'aria-label': 'Send', title: 'Send' }, icon('send'))
  const said = h('div', { class: 'composer-said', 'aria-live': 'polite' })
  const tray = h('div', { class: 'composer-tools' }, tools)
  const form = h('form', { class: 'composer', 'data-hmz': 'composer' }, said, text, h('div', { class: 'composer-bar' }, tray, send))
  const grow = () => {
    text.style.height = 'auto'
    text.style.height = `${Math.min(text.scrollHeight, 320)}px`
  }
  text.addEventListener('input', grow)
  text.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault()
      form.requestSubmit()
    }
  })
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    if ((!empty && !text.value.trim()) || send.disabled) return
    send.disabled = true
    form.classList.add('busy')
    fill(said)
    try {
      await submit(text.value)
      text.value = ''
      grow()
    } catch (error) {
      fill(said, problem(error))
    } finally {
      send.disabled = false
      form.classList.remove('busy')
    }
  })
  requestAnimationFrame(grow)
  return { node: form, text, tray, said, send }
}

/** A choice on a composer's bar, drawn as a chip: a word saying what it chooses, and the choice. */
export function chipSelect(label, select) {
  return h('label', { class: 'chip-select' }, h('span', { class: 'chip-label' }, label), select)
}
