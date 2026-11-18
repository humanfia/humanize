// The permission chip on a chat's box, as a chat app keeps one beside what is typed: it names
// what the assistant may touch, and opens a menu of the three a chat can be held to, each with
// one line saying what it lets the assistant do and a mark on the one in force (Section
// 3.6.6.14 of protocol/web.md). What picking one does is the box's: start the chat with it, set
// it on the chat's host, or keep it for when the chat is carried on.

import { chipNamed } from '../desk.js'
import { h, icon } from '../dom.js'
import { choice, menu } from '../shell.js'
import { toast } from '../ui.js'
import { modeOf, NOTE, offered, shown } from './permission-modes.js'

/**
 * @param {object} [made]
 * @param {string|null} [made.value] The permission it opens on; the default where none.
 * @param {(permission: string) => unknown} [made.pick] What picking another does; where it
 *   throws or rejects, the chip goes back to the one it showed and says why.
 * @param {boolean} [made.up] Whether its menu would rather open over it, as under a chat.
 * @returns {{node: HTMLElement, value: () => string, set: (permission: string|null) => void}}
 */
export function permissionChip({ value = null, pick = () => {}, up = false } = {}) {
  let now = modeOf(value).value
  const said = h('span', { class: 'chip-value' })
  const button = h('button', { class: 'chip-btn permission-chip', type: 'button', 'data-hmz': 'permission' }, said, icon('down'))
  const node = h('div', { class: 'menu-holder permission' }, button)

  function set(permission) {
    const mode = modeOf(permission)
    now = mode.value
    said.textContent = mode.label
    button.setAttribute('aria-label', chipNamed('Permissions', mode.label))
    button.dataset.permission = now
    button.dataset.tip = mode.about
  }

  async function choose(permission) {
    const before = now
    if (permission === before) return
    set(permission)
    try {
      await pick(permission)
    } catch (error) {
      // Only where nothing was picked since: a later choice is not undone by an earlier one's refusal.
      if (now === permission) set(before)
      toast(error.message)
    }
  }

  menu(
    button,
    // Under no heading: the menu is named, and holds nothing but the three and the note.
    (close) => [
      offered(now).map((one) => {
        const item = choice({ label: one.label, about: one.about, chosen: one.chosen, act: () => choose(one.value), close })
        item.dataset.permission = one.value
        return item
      }),
      h('p', { class: 'permission-note' }, NOTE),
    ],
    { label: 'Permissions', up },
  )
  set(now)
  return { node, value: () => now, set }
}

/**
 * The chip of a chat there already is: on what its host says while one holds it, where picking
 * sets it there, and on what its epic records once it has folded away, where what is picked is
 * kept for the chat to be carried on with. Not drawn for a chat whose host says it has none to
 * set.
 *
 * @param {{permission?: string}} epic The chat's epic, as `runs.get` answers it.
 * @param {(permission: string) => unknown} sets Sets it on the chat's host, or answers
 *   `null` for a chat no host holds, whose pick is kept.
 * @returns {{node: HTMLElement, picked: () => string|null, host: (said: object) => void}}
 *   `picked` is what a chat folded away is carried on with, `null` for what it had; `host` is
 *   told what `chat.commands` answered.
 */
export function chatPermission(epic, sets) {
  let picked = null
  let host = null
  const chip = permissionChip({
    up: true,
    pick: async (permission) => {
      if ((await sets(permission)) === null) picked = permission
      else if (host) host = { ...host, permission }
    },
  })
  const draw = () => {
    const permission = shown({ picked, host, epic })
    chip.node.hidden = permission === null
    if (permission !== null) chip.set(permission)
  }
  draw()
  return {
    node: chip.node,
    picked: () => picked,
    host(said) {
      host = said
      picked = null
      draw()
    },
  }
}
