// `#/delete/<id>`: deleting a chat, asked first in a dialog over the page, as a chat app asks it:
// which chat, what goes with it and that it cannot be undone, then `Cancel` and `Delete`
// (Section 3.6.6.26 of protocol/web.md). What the daemon refuses -- a chat still going -- is
// said in the dialog, in the daemon's words, and the chat stays.

import { call, hash } from '../api.js'
import { shut, under } from '../app.js'
import { chatsChanged } from '../chat-actions.js'
import { DELETING } from '../chats.js'
import { fill, h, headline, problem } from '../dom.js'
import { t } from '../i18n.js'
import { logKey, logs } from '../logged.js'
import { dragged } from '../shell.js'

export function mount(root, { parts }) {
  const id = parts[1] || ''
  const named = h('p', { class: 'delete-title', 'data-hmz': 'delete-title' }, id)
  const said = h('div', { class: 'delete-said', role: 'alert' })
  const doing = h('button', { class: 'btn danger', type: 'button', 'data-hmz': 'delete-confirm' }, t('Delete'))
  const keep = h('button', { class: 'btn quiet', type: 'button', autofocus: true, 'data-hmz': 'delete-cancel', onclick: shut }, t('Cancel'))
  root.classList.add('dialog-delete')
  root.setAttribute('aria-label', t('Delete chat'))
  fill(
    root,
    // No button to close it by but `Cancel`, which the dialog opens on.
    dragged(h('div', { class: 'dialog-head delete-head' }, h('h2', { class: 'dialog-title' }, t('Delete chat'))), 'deep', 'narrow'),
    h('div', { class: 'dialog-body delete-body' }, named, h('p', { class: 'delete-about' }, DELETING), said),
    h('div', { class: 'dialog-foot delete-foot' }, keep, doing),
  )
  let gone = false
  call('chat.get', { chat: id }).then(
    (chat) => {
      if (gone) return
      named.textContent = headline(chat.title)
      named.title = chat.title
    },
    (error) => {
      if (gone) return
      // No such chat: there is nothing to delete.
      fill(said, problem(error))
      doing.disabled = true
    },
  )
  doing.addEventListener('click', async () => {
    doing.disabled = keep.disabled = true
    doing.textContent = t('Deleting…')
    fill(said)
    try {
      await call('chat.delete', { chat: id })
    } catch (error) {
      if (gone) return
      fill(said, problem(error))
      doing.disabled = keep.disabled = false
      doing.textContent = t('Delete')
      return
    }
    // Nothing of it is kept to draw it by again.
    logs.drop(logKey('chat', id, on.on))
    chatsChanged()
    // Closed meanwhile, there is no dialog left to close.
    if (gone) return
    // Deleted from over its own view, there is no chat left to go back to: a new chat, in its place.
    if (under().split('?')[0].endsWith(`/chats/${encodeURIComponent(id)}`)) addEventListener('hashchange', () => location.replace(hash('/new/chat')), { once: true })
    shut()
  })
  return () => {
    gone = true
  }
}
