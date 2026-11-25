// The chats of a workspace that were archived, which no other list holds: each put back among
// the others, or deleted (Section 3.11.2.11.1 of protocol/web.md). The workspace is the one the
// dialog is of (views/workspace.js). Under them, whichever folder that is and where it is none,
// the archived chats of no folder, which no folder would list.

import { hash } from '../../api.js'
import { archiving, deletingAt } from '../../chat-actions.js'
import { pathOf } from '../../chats.js'
import { acting, ago, empty, fill, h, headline, problem, when } from '../../dom.js'
import { t } from '../../i18n.js'
import { NO_FOLDER } from '../../sidebar-view.js'

export function draw(holder, query, parts, scope) {
  const archived = h('section', { class: 'panel archived-chats', 'data-hmz': 'archived-chats' }, h('p', { class: 'loading', role: 'status' }, t('Reading the settings…')))
  fill(holder, archived)

  /** Some archived chats as a list, each put back or deleted. */
  const rows = (chats) =>
    h(
      'ul',
      { class: 'archived-list' },
      chats.map((one) => {
        const chat = { kind: 'chat', name: one.id, title: one.title }
        return h(
          'li',
          { class: 'archived-row', 'data-hmz': 'archived-chat', 'data-chat': one.id },
          h('a', { class: 'archived-title', href: hash(pathOf(chat)), title: one.title }, headline(one.title)),
          h('span', { class: 'dim archived-when', title: when(one.updated) }, ago(one.updated)),
          acting(t('Unarchive'), () => archiving(chat, false).then(read), { kind: 'btn small' }),
          h('a', { class: 'btn small danger', href: deletingAt(chat), 'data-hmz': 'archived-delete' }, t('Delete')),
        )
      }),
    )

  /**
   * Lists the archived chats of the dialog's workspace, newest first, and under them those of no
   * folder: each of them is of a directory of its own that no folder names, so they are
   * read out of every workspace's.
   */
  function read() {
    const none = { chats: [], total: 0 }
    Promise.all([scope.workspace ? scope.call('chat.list', { workspace: scope.workspace, archived: true, limit: 200 }) : none, scope.call('chat.list', { archived: true, limit: 200 })]).then(
      ([answer, every]) => {
        const more = answer.total - answer.chats.length
        const nowhere = every.chats.filter((one) => one.folderless)
        fill(
          archived,
          answer.chats.length ? rows(answer.chats) : nowhere.length ? null : empty(t('No archived chats.'), t(' A chat you archive from its menu leaves the sidebar and is kept here.')),
          more > 0 ? h('p', { class: 'dim' }, t('{n} more', { n: more })) : null,
          // Under a folder's own, named; in the settings of `No folder`, which the dialog names, they are all there is.
          nowhere.length ? h('div', { class: 'archived-nowhere', 'data-hmz': 'archived-nowhere' }, scope.workspace ? h('h4', {}, NO_FOLDER) : null, rows(nowhere)) : null,
        )
      },
      (error) => fill(archived, problem(error)),
    )
  }
  read()
}
