// What can be done to a chat besides talking in it, as a chat app's session offers it: renaming
// it in place, forking it, archiving it and putting it back, and deleting it once that is
// confirmed (Section 4.25.7 of protocol/daemon.md, Sections 3.5.12 and 3.6.6.23 to 3.6.6.26 of
// protocol/web.md). Offered alike wherever a chat is listed or open; what the daemon refuses is
// said in the daemon's own words.

import { call, hash, refresh } from './api.js'
import { covered, go } from './app.js'
import { TITLE_MOST, pathOf, titled } from './chats.js'
import { h } from './dom.js'
import { t } from './i18n.js'
import { toast } from './ui.js'

/** How long a refusal is said for, in milliseconds: a sentence, read whole. */
const REFUSED = 6000

/** Reads again every list of chats and every chat read, after a write that changed one. */
export function chatsChanged() {
  refresh('chat.list')
  refresh('chat.get')
}

const refused = (error) => toast(error.message, REFUSED)

/**
 * Renames a chat in place: what shows its title gives way to a field holding it, which Enter
 * saves with `chat.rename`, as leaving the field does, and Escape leaves as it was.
 *
 * @param {HTMLElement} shown What shows the title, and has the focus back once the field is done with.
 * @param {{name: string, title: string}} chat The chat.
 * @param {object} [how] Where it is not a chat's title: an Ai-chan conversation's.
 * @param {(title: string) => Promise<unknown>} [how.saves] What records the title.
 * @param {HTMLElement} [how.back] What has the focus back, where `shown` takes none.
 */
export function retitling(shown, chat, { saves = (title) => call('chat.rename', { chat: chat.name, title }).then(chatsChanged), back: focused = shown } = {}) {
  if (shown.hidden) return
  const field = h('input', { class: 'title-edit', type: 'text', 'aria-label': t('Chat title'), maxlength: TITLE_MOST, value: chat.title, 'data-hmz': 'title-edit' })
  let over = false
  let saving = false
  const end = (back) => {
    if (over) return
    over = true
    field.remove()
    shown.hidden = false
    if (back) focused.focus()
  }
  const save = async (back) => {
    if (over || saving) return
    const title = titled(field.value)
    // Nothing typed, or nothing changed: the title stays.
    if (!title || title === chat.title) return end(back)
    saving = true
    field.readOnly = true
    try {
      await saves(title)
      end(back)
    } catch (error) {
      refused(error)
      saving = false
      field.readOnly = false
    }
  }
  field.addEventListener('keydown', (event) => {
    // The keys are the field's alone: no shortcut of the page, and no dialog's Escape.
    event.stopPropagation()
    if (event.key === 'Enter') {
      event.preventDefault()
      save(true)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      end(true)
    }
  })
  field.addEventListener('blur', () => save(false))
  // A press in the field is no press on what holds it -- a row that opens its chat, say.
  field.addEventListener('click', (event) => event.stopPropagation())
  shown.hidden = true
  shown.after(field)
  field.focus()
  field.select()
}

/** Forks a chat and opens the fork, a chat as any other. */
export async function forking(chat) {
  try {
    const { chat: fork } = await call('chat.fork', { chat: chat.name })
    chatsChanged()
    const path = pathOf({ kind: 'chat', name: fork })
    // From a dialog, in the dialog's place: Back from the fork never opens the dialog again.
    if (covered()) location.replace(hash(path))
    else go(path)
  } catch (error) {
    refused(error)
  }
}

/** Archives a chat, or puts it back among the others, on the daemon shown or another. */
export async function archiving(chat, archived, { on = '' } = {}) {
  await call(archived ? 'chat.archive' : 'chat.unarchive', { chat: chat.name }, on ? { on } : {})
  chatsChanged()
}

/** The address of the dialog that deletes a chat, of the daemon shown or another the page keeps. */
export function deletingAt(chat, { on = '' } = {}) {
  return hash(`/delete/${encodeURIComponent(chat.name)}${on ? `?daemon=${encodeURIComponent(on)}` : ''}`)
}

/**
 * What a chat's menu offers of these, each as an item of it.
 *
 * @param {{name: string, title: string, archived?: boolean}} chat The chat.
 * @param {{rename?: (() => void) | null}} [how] What renames it where the menu is opened: nothing
 *   where its title is not drawn to be edited.
 */
export function chatActions(chat, { rename = null } = {}) {
  return {
    rename: rename ? { label: t('Rename'), glyph: 'compose', act: rename } : null,
    fork: { label: t('Fork'), glyph: 'fork', act: () => forking(chat) },
    archive: chat.archived
      ? { label: t('Unarchive'), glyph: 'archive', act: () => archiving(chat, false).then(() => toast(t('Unarchived')), refused) }
      : { label: t('Archive'), glyph: 'archive', act: () => archiving(chat, true).then(() => toast(t('Archived')), refused) },
    delete: { label: t('Delete'), glyph: 'trash', danger: true, href: deletingAt(chat) },
  }
}
