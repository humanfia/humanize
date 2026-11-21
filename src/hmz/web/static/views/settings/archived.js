// The chats of a workspace that were archived, which no other list holds: each put back among
// the others, or deleted (Section 3.11.2.11.1 of protocol/web.md). The workspace is the one picked
// over the page (views/settings.js), under `Workspace`.

import { daemon, hash } from '../../api.js'
import { archiving, deletingAt } from '../../chat-actions.js'
import { pathOf } from '../../chats.js'
import { acting, ago, empty, fill, h, headline, problem, when } from '../../dom.js'
import { t } from '../../i18n.js'

export function draw(holder, query, parts, scope) {
  const archived = h('section', { class: 'panel archived-chats', 'data-hmz': 'archived-chats' }, h('p', { class: 'loading', role: 'status' }, t('Reading the settings…')))
  fill(holder, archived)
  // A chat of another daemon than the page's is no address of this page: it is acted on there.
  const on = scope.name === daemon() ? '' : scope.name

  /** Lists the archived chats of the workspace picked, newest first. */
  function read() {
    scope.call('chat.list', { workspace: scope.workspace, archived: true, limit: 200 }).then(
      (answer) => {
        const more = answer.total - answer.chats.length
        fill(
          archived,
          answer.chats.length
            ? h(
                'ul',
                { class: 'archived-list' },
                answer.chats.map((one) => {
                  const chat = { kind: 'chat', name: one.id, title: one.title }
                  return h(
                    'li',
                    { class: 'archived-row', 'data-hmz': 'archived-chat', 'data-chat': one.id },
                    on ? h('span', { class: 'archived-title', title: one.title }, headline(one.title)) : h('a', { class: 'archived-title', href: hash(pathOf(chat)), title: one.title }, headline(one.title)),
                    h('span', { class: 'dim archived-when', title: when(one.updated) }, ago(one.updated)),
                    acting(t('Unarchive'), () => archiving(chat, false, { on }).then(read), { kind: 'btn small' }),
                    h('a', { class: 'btn small danger', href: deletingAt(chat, { on }), 'data-hmz': 'archived-delete' }, t('Delete')),
                  )
                }),
              )
            : empty(t('No archived chats.'), t(' A chat you archive from its menu leaves the sidebar and is kept here.')),
          more > 0 ? h('p', { class: 'dim' }, t('{n} more', { n: more })) : null,
        )
      },
      (error) => fill(archived, problem(error)),
    )
  }
  read()
}
