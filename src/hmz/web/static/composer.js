// The box a person types into at the foot of a view, as in a chat: it grows with what is
// typed, Enter sends it and Shift+Enter starts a new line, and what refused it is said over it.
// Given what to complete with, it offers, over itself, what the word being typed could become,
// picked with the arrows and taken with Tab or Enter, as a terminal's prompt completes. Told
// what stops what it is typed to (`stops`), its button stops that in place of sending, while
// Enter still sends what is typed.

// A box of a chat's -- a new chat's, a chat's, a new epic's -- is drawn as a chat app's desk
// (`desk`): inside it only the Add button, what is typed and the button that sends; every
// choice beside it is a quiet chip in the row under it, where it runs at the left and how it
// runs at the right (Section 3.6.6.15 of protocol/web.md).

import { added, addsOf } from './desk.js'
import { fill, h, icon, iconButton, problem } from './dom.js'
import { t } from './i18n.js'
import { yields } from './layers.js'
import { choice, menu } from './shell.js'

/**
 * @param {object} made
 * @param {string} made.placeholder What it says while empty.
 * @param {string} made.label What it is, to whoever cannot see it.
 * @param {(text: string) => Promise<unknown>} made.submit What sending does; what it throws is said.
 * @param {Node[]} [made.tools] What stands on its bar beside the send button.
 * @param {string} [made.value] What it holds to begin with.
 * @param {boolean} [made.empty] Whether it may be sent empty.
 * @param {string} [made.busy] What it says over itself while what was sent is being taken.
 * @param {(text: string, caret: number) => Promise<Completing|null>|Completing|null} [made.complete] What the word at the caret could become.
 * @param {{left?: Node[], right?: Node[], add?: true | string[], able?: (key: string) => string} | null} [made.desk]
 *   Drawn as a chat's desk: the chips under the box, at its left and at its right; what its Add
 *   menu offers -- all of it, or the keys of desk.js's `ADDS` it does; and `able`, which says why
 *   one of them cannot be picked now, or '' where it can. `tools` then stand at the right under
 *   the box, never in it.
 */
export function composer({ placeholder, label, submit, tools = [], value = '', empty = false, busy = t('Sending…'), complete = null, desk = null }) {
  const text = h('textarea', { rows: '1', placeholder, 'aria-label': label, 'data-hmz': 'composer-text' }, value)
  const send = h('button', { class: 'send', type: 'submit', 'aria-label': t('Send'), title: t('Send') }, icon('send'))
  const said = h('div', { class: 'composer-said', 'aria-live': 'polite' })
  const tray = h('div', { class: desk ? 'under-right' : 'composer-tools' }, desk ? [tools, desk.right || []] : tools)
  const left = desk ? h('div', { class: 'under-left' }, desk.left || []) : null
  const form = desk
    ? h(
        'form',
        { class: 'composer composer-desk', 'data-hmz': 'composer' },
        said,
        h('div', { class: 'composer-box' }, desk.add ? adder(text, desk.add, desk.able) : null, text, send),
        h('div', { class: 'composer-under', 'data-hmz': 'composer-under' }, left, tray),
      )
    : h('form', { class: 'composer', 'data-hmz': 'composer' }, said, text, h('div', { class: 'composer-bar' }, tray, send))
  const grow = () => {
    text.style.height = 'auto'
    text.style.height = `${Math.min(text.scrollHeight, 320)}px`
  }
  text.addEventListener('input', grow)
  const offered = complete ? completer(text, complete) : null
  if (offered) form.prepend(offered.node)
  text.addEventListener('keydown', (event) => {
    if (offered && offered.key(event)) return
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault()
      form.requestSubmit()
    }
  })
  /** What the button does in place of sending, while there is something to stop. */
  let stop = null
  const stops = (act) => {
    if (Boolean(act) !== Boolean(stop)) {
      const said = act ? t('Stop') : t('Send')
      send.classList.toggle('stop', Boolean(act))
      send.setAttribute('aria-label', said)
      send.title = said
      send.dataset.hmz = act ? 'stop' : 'send'
      fill(send, icon(act ? 'stop' : 'send'))
    }
    stop = act
  }
  send.dataset.hmz = 'send'
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    // The button pressed, while there is something to stop, stops it: what refused is said.
    if (stop && event.submitter === send) {
      if (send.disabled) return
      send.disabled = true
      try {
        await stop()
        fill(said)
      } catch (error) {
        fill(said, problem(error))
      } finally {
        send.disabled = false
      }
      return
    }
    if ((!empty && !text.value.trim()) || send.disabled) return
    send.disabled = true
    form.classList.add('busy')
    form.setAttribute('aria-busy', 'true')
    send.setAttribute('aria-label', busy)
    fill(said, h('p', { class: 'loading', role: 'status' }, busy))
    try {
      await submit(text.value)
      fill(said)
      text.value = ''
      grow()
      offered?.close()
    } catch (error) {
      fill(said, problem(error))
    } finally {
      send.disabled = false
      form.classList.remove('busy')
      form.removeAttribute('aria-busy')
      send.setAttribute('aria-label', stop ? t('Stop') : t('Send'))
    }
  })
  // Measured again whenever its box changes, so one built before it is shown fits once shown.
  new ResizeObserver(() => requestAnimationFrame(grow)).observe(text)
  return { node: form, text, tray, left, said, send, stops, again: () => offered?.again() }
}

/**
 * The Add button of a chat's box, and its menu: each choice types the prefix a line of that kind
 * starts with, and the box then offers what it could become, as it does where the prefix is typed.
 */
function adder(text, which, able = () => '') {
  const button = iconButton('plus', t('Add'), { class: 'composer-add', 'data-hmz': 'composer-add' })
  menu(
    button,
    (close) =>
      addsOf(which).map((one) => {
        const why = able(one.key)
        const item = choice({
          label: one.label,
          about: why,
          glyph: one.glyph,
          close,
          act: () => {
            const now = added(text.value, text.selectionStart ?? text.value.length, one.sigil)
            text.value = now.text
            text.focus()
            text.setSelectionRange(now.caret, now.caret)
            text.dispatchEvent(new Event('input'))
          },
        })
        item.dataset.add = one.key
        item.disabled = Boolean(why)
        return item
      }),
    { up: true, label: t('Add') },
  )
  return h('div', { class: 'menu-holder' }, button)
}

/**
 * @typedef {object} Completing What the word at the caret could become.
 * @property {number} from Where the word starts, which what is taken replaces.
 * @property {number} to Where it ends.
 * @property {{label: string, items: {insert: string, name: string, about: string, tag: string, hint: string, refused: boolean}[]}[]} groups
 *   What is offered, in groups each saying where its items come from.
 */

/**
 * The list a box offers completions in, read again as the caret moves: the newest reading only is
 * drawn, so a slow one never draws over what was typed since.
 */
function completer(text, complete) {
  const list = h('div', { class: 'composer-complete', role: 'listbox', 'aria-label': t('Completions'), 'data-hmz': 'completions', hidden: true })
  let shown = null
  let items = []
  let active = 0
  let asked = 0
  /** What says it closed by itself, while it is open. */
  let done = null

  async function again() {
    const mine = ++asked
    let got = null
    try {
      got = await complete(text.value, text.selectionStart ?? text.value.length)
    } catch {
      got = null
    }
    if (mine !== asked) return
    shown = got && got.groups.some((one) => one.items.length) ? got : null
    items = shown ? shown.groups.flatMap((one) => one.items) : []
    // Typed further, the best of what is offered now is the one picked.
    active = 0
    draw()
  }

  function draw() {
    list.hidden = !shown
    // Open, it yields to whatever floats: a menu opening closes it, as a dialog does (layers.js).
    if (shown) done ||= yields(close)
    else {
      done?.()
      done = null
      return fill(list)
    }
    let at = 0
    fill(
      list,
      shown.groups.map((group) => [
        h('div', { class: 'complete-group', role: 'presentation' }, group.label),
        group.items.map((one) => {
          const index = at++
          return h(
            'div',
            {
              class: ['complete-item', index === active && 'active', one.refused && 'refused'],
              role: 'option',
              'aria-selected': String(index === active),
              'data-hmz': 'completion',
              // Pressed, not clicked: the box keeps its focus, and so its caret.
              onmousedown: (event) => {
                event.preventDefault()
                take(index)
              },
            },
            h('span', { class: 'complete-name' }, one.name),
            h('span', { class: ['complete-tag', `tag-${one.tag}`] }, one.tag),
            one.about ? h('span', { class: 'complete-about' }, one.about) : null,
            one.hint ? h('span', { class: 'complete-hint', 'data-hmz': 'completion-hint' }, one.hint) : null,
          )
        }),
      ]),
    )
    list.querySelector('.active')?.scrollIntoView({ block: 'nearest' })
  }

  function take(index) {
    const one = items[index]
    if (!one || !shown) return
    const { from, to } = shown
    text.value = text.value.slice(0, from) + one.insert + text.value.slice(to)
    const caret = from + one.insert.length
    text.setSelectionRange(caret, caret)
    text.dispatchEvent(new Event('input'))
  }

  function close() {
    asked++
    shown = null
    items = []
    draw()
  }

  text.addEventListener('input', again)
  text.addEventListener('click', again)
  text.addEventListener('blur', close)
  return {
    node: list,
    again,
    close,
    /** Whether a key was the list's: moving through it, taking from it, or closing it. */
    key(event) {
      if (!shown || event.isComposing) return false
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        active = (active + (event.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length
        draw()
      } else if (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey)) {
        // What would change nothing is not taken: Enter sends the line as it stands.
        if (event.key === 'Enter' && items[active].insert === text.value.slice(shown.from, shown.to)) return false
        take(active)
      } else if (event.key === 'Escape') close()
      else return false
      event.preventDefault()
      return true
    },
  }
}

/** A choice on a composer's bar, drawn as a chip: a word saying what it chooses, and the choice. */
export function chipSelect(label, select) {
  return h('label', { class: 'chip-select' }, h('span', { class: 'chip-label' }, label), select)
}
