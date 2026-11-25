// The permission chip on a chat's box, as a chat app keeps one beside what is typed: it names
// what the assistant may touch, and opens a menu of the three a chat can be held to, each with
// one line saying what it lets the assistant do and a mark on the one in force (Section
// 3.6.6.14 of protocol/web.md). What picking one does is the box's: start the chat with it, set
// it on the chat's host, or keep it for when the chat is carried on. An Ai-chan conversation's
// is the same chip over her two presets, with what she may reach, her scope, said after it and
// picked under them (Section 3.16.3).

import { chipNamed } from '../desk.js'
import { fill, h, icon } from '../dom.js'
import { t } from '../i18n.js'
import { choice, menu } from '../shell.js'
import { toast } from '../ui.js'
import { MODES, modeOf, NOTE, offered, shown } from './permission-modes.js'

/**
 * @param {object} [made]
 * @param {string|null} [made.value] The permission it opens on; the default where none.
 * @param {(permission: string) => unknown} [made.pick] What picking another does; where it
 *   throws or rejects, the chip goes back to the one it showed and says why.
 * @param {boolean} [made.up] Whether its menu would rather open over it, as under a chat.
 * @param {{value: string, label: string, about: string}[]} [made.modes] What it offers, where
 *   not a chat's three.
 * @param {() => string} [made.beside] What else it says after the permission, where anything.
 * @param {(close: () => void) => unknown} [made.rows] What its menu holds under the permissions.
 * @returns {{node: HTMLElement, value: () => string, set: (permission: string|null) => void, again: () => void, fixed: (why: string) => void}}
 *   `again` says it anew, once what stands beside the permission has changed; `fixed` leaves it
 *   saying what it says and picking nothing, with why said where it is pointed at.
 */
export function permissionChip({ value = null, pick = () => {}, up = false, modes = MODES, beside = null, rows = null } = {}) {
  let now = modeOf(value, modes).value
  const said = h('span', { class: 'chip-value' })
  const button = h('button', { class: 'chip-btn permission-chip', type: 'button', 'data-hmz': 'permission' }, said, icon('down'))
  const node = h('div', { class: 'menu-holder permission' }, button)

  function set(permission) {
    const mode = modeOf(permission, modes)
    const also = beside ? beside() : ''
    now = mode.value
    fill(said, mode.label, also ? [h('span', { class: 'chip-part', 'aria-hidden': 'true' }, ' · '), h('span', { 'data-part': 'beside' }, also)] : null)
    button.setAttribute('aria-label', chipNamed(t('Permissions'), also ? t('{permission}, {scope}', { permission: mode.label, scope: also }) : mode.label))
    button.dataset.permission = now
    if (!button.disabled) button.dataset.tip = mode.about
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
      offered(now, modes).map((one) => {
        const item = choice({ label: one.label, about: one.about, chosen: one.chosen, act: () => choose(one.value), close })
        item.dataset.permission = one.value
        return item
      }),
      h('p', { class: 'permission-note' }, NOTE),
      rows ? [h('hr'), rows(close)] : null,
    ],
    { label: t('Permissions'), up, align: 'end' },
  )
  set(now)
  return {
    node,
    value: () => now,
    set,
    again: () => set(now),
    fixed(why) {
      button.disabled = true
      button.dataset.tip = why
    },
  }
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
