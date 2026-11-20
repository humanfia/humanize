// The Usage chip that ends the row under a chat's box, as a chat app keeps a ring there: the
// ring alone, with no figure beside it, and a popup of its own by the chip saying everything --
// what this chat has used, what its workspace has used today and over the last 7 days, and the
// way to the Usage page of Settings (Sections 3.6.6.17 and 3.8.22 of protocol/web.md). The form
// of a new chat keeps the same chip with no chat's figures.

import { call, given, hash } from '../api.js'
import { usedLately } from '../desk.js'
import { fill, h, problem } from '../dom.js'
import { nameOf } from '../places.js'
import { choice, menu } from '../shell.js'
import { glyph } from '../views/chatbar.js'

/** How many days back the popup looks: the shortest range the Usage page offers. */
const DAYS = 7

/** One row: what is counted, a bar or a word about it, and the figure. */
const row = (one) => [
  h('dt', {}, one.label),
  h('dd', { class: 'usage-about' }, one.share === undefined ? one.about || null : h('div', { class: 'share', 'aria-hidden': 'true' }, h('span', { style: `width:${Math.round(one.share * 100)}%` }))),
  h('dd', { class: 'usage-value' }, one.value),
  one.sub ? h('dd', { class: 'usage-sub' }, one.sub) : null,
]

/**
 * @param {object} made
 * @param {string} made.hmz What the chip is found by: `chat-usage` or `new-usage`.
 * @param {string} made.tip What it says where pointed at.
 * @param {(() => {label: string, value: string, share?: number}[]) | null} [made.chat] The rows
 *   of the chat it stands under (`usageRows`); none on the form of a new chat.
 * @param {() => string} made.workspace The workspace whose usage it reads, '' for every one's.
 * @returns {{node: HTMLElement, read: () => void}} `read` is called as often as the chat is
 *   read, and draws the chat's part of the popup again while it is open.
 */
export function usageChip({ hmz, tip, chat = null, workspace }) {
  const button = h('button', { class: 'chip-btn desk-chip usage-chip', type: 'button', 'aria-label': 'Usage', 'data-hmz': hmz, 'data-tip': tip }, glyph('usage'))
  /** The popup's part for the chat while it is open, drawn again as the chat spends. */
  let mine = null
  /** Which opening the workspace's usage was asked for: an answer to an earlier one is dropped. */
  let asked = 0

  const drawChat = () => {
    const rows = chat()
    fill(mine, h('div', { class: 'popover-head' }, 'This chat'), rows.length ? h('dl', { class: 'usage-rows' }, rows.map(row)) : h('p', { class: 'usage-none' }, 'Nothing used yet'))
  }

  menu(
    button,
    (close) => {
      const folder = workspace()
      const lately = h('div', { class: 'usage-lately', 'aria-live': 'polite' }, h('p', { class: 'usage-none', role: 'status' }, 'Reading…'))
      const mark = ++asked
      const draw = (node) => mark === asked && lately.isConnected && fill(lately, node)
      call('runs.usage', given({ days: DAYS, workspace: folder })).then(
        (data) => draw(h('dl', { class: 'usage-rows' }, usedLately(data).map(row))),
        (error) => draw(problem(error)),
      )
      // A link among figures, not a choice of a menu.
      const settings = choice({ label: 'Usage settings', glyph: 'chart', href: hash(`/settings/usage${folder ? `?workspace=${encodeURIComponent(folder)}` : ''}`), close })
      settings.removeAttribute('role')
      settings.dataset.hmz = 'usage-settings'
      mine = chat ? h('div', { class: 'usage-mine' }) : null
      if (mine) drawChat()
      return h('div', { class: 'usage-pop', 'data-hmz': 'usage-pop' }, mine, h('div', { class: 'popover-head', title: folder }, folder ? nameOf(folder) : 'Every folder'), lately, h('hr'), settings)
    },
    { label: 'Usage', up: true, align: 'end', role: 'dialog' },
  )

  return {
    node: h('div', { class: 'menu-holder usage' }, button),
    read() {
      if (mine && mine.isConnected) drawChat()
    },
  }
}
