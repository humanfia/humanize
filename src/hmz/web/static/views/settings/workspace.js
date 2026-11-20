// What a workspace was last set up with: the flow it opens on and every flow set up there, and
// forgetting all of it -- which also stops it being offered, where no epic ran there. Under it,
// the chats of the workspace that were archived, which no other list holds: each put back among
// the others, or deleted (Section 3.11.2.11 of protocol/web.md).

import { daemon, given, hash, started } from '../../api.js'
import { archiving, deletingAt } from '../../chat-actions.js'
import { pathOf } from '../../chats.js'
import { confirming } from '../../confirm.js'
import { acting, ago, fill, h, headline, pathText, problem, when } from '../../dom.js'
import { t } from '../../i18n.js'
import { firstOf, there } from '../../places.js'

/** What a workdir is picked by: its folder's name, or with the folder it is in where another has the name. */
const shownAs = (one, twin) => (twin ? one.path.split('/').slice(-2).join('/') : one.name)

export function draw(holder, query, parts, scope) {
  let workspace = query.get('workspace') || ''
  const choosing = h('select', { 'aria-label': t('Workdir'), 'data-hmz': 'settings-workdir' })
  const body = h('div', { class: 'reading' }, h('p', { class: 'loading', role: 'status' }, t('Reading the settings…')))
  const archived = h('section', { class: 'panel archived-chats', 'data-hmz': 'archived-chats', hidden: true })
  fill(holder, h('label', { class: 'field' }, h('span', { class: 'label' }, t('Workdir')), choosing), body, archived)
  // A chat of another daemon than the page's is no address of this page: it is acted on there.
  const on = scope.name === daemon() ? '' : scope.name

  /** Lists the archived chats of the workspace picked, newest first. */
  function readArchived(mine) {
    const heading = h('h2', {}, t('Archived chats'))
    scope.call('chat.list', { workspace, archived: true, limit: 200 }).then(
      (answer) => {
        if (mine !== reading) return
        archived.hidden = false
        const more = answer.total - answer.chats.length
        fill(
          archived,
          heading,
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
                    acting(t('Unarchive'), () => archiving(chat, false, { on }).then(() => readArchived(reading)), { kind: 'btn small' }),
                    h('a', { class: 'btn small danger', href: deletingAt(chat, { on }), 'data-hmz': 'archived-delete' }, t('Delete')),
                  )
                }),
              )
            : h('p', { class: 'dim' }, t('No archived chats.')),
          more > 0 ? h('p', { class: 'dim' }, t('{n} more', { n: more })) : null,
        )
      },
      (error) => {
        if (mine !== reading) return
        archived.hidden = false
        fill(archived, heading, problem(error))
      },
    )
  }
  choosing.addEventListener('change', () => {
    workspace = choosing.value
    read()
  })

  const shown = (settings, forgot) => {
    fill(
      body,
      h(
        'section',
        { class: 'panel' },
        h(
          'dl',
          { class: 'facts' },
          h('dt', {}, t('directory')),
          h('dd', {}, pathText(settings.workspace)),
          h('dt', {}, t('default flow')),
          h('dd', {}, settings.flow || t('none')),
          h('dt', {}, t('configured')),
          h('dd', {}, settings.flows.length ? settings.flows.join(', ') : t('none')),
        ),
        forgot === undefined ? null : h('p', { class: 'note', role: 'status' }, forgot ? t('Forgotten.') : t('Nothing to forget.')),
        h(
          'p',
          { class: 'row' },
          confirming({
            label: t('Forget'),
            ask: settings.flows.length ? t('Forget how {n} flows were set up here?', { n: settings.flows.length }) : t('Forget how every flows were set up here?'),
            yes: t('Forget'),
            no: t('Cancel'),
            act: async () => {
              const answer = await scope.call('settings.forget', { workspace: settings.workspace })
              shown(answer, answer.forgot)
            },
          }),
        ),
      ),
    )
  }

  // What the last workdir had stays, plainly on its way out, until the next one's is read.
  let reading = 0
  function read() {
    const mine = ++reading
    if (!body.querySelector('.loading')) body.setAttribute('aria-busy', 'true')
    scope.call('settings.get', given({ workspace }))
      .then((settings) => mine === reading && shown(settings))
      .catch((error) => mine === reading && fill(body, problem(error)))
      .finally(() => mine === reading && body.removeAttribute('aria-busy'))
    if (workspace) readArchived(mine)
  }

  started()
    // Where `hmz web` started is a directory of Local's alone.
    .then((here) => scope.call('workspaces.list', given({ here: scope.name === 'local' ? here : '' })))
    .then((answer) => {
    // One whose directory is there first; one that went only where the address names it or no
    // other is listed: its set-up is still read, and forgotten, here.
    if (!workspace) workspace = answer.workspaces.some(there) ? firstOf(answer) : answer.here || answer.workspaces[0]?.path || ''
    // Each by its folder's name, which tells them apart where a path's start does not: two of
    // one name, with the folder each is in before it. The whole path is said under the picker.
    const twin = (one) => answer.workspaces.some((other) => other !== one && other.name === one.name)
    fill(choosing, answer.workspaces.map((one) => h('option', { value: one.path, selected: one.path === workspace, title: one.path }, there(one) ? shownAs(one, twin(one)) : t('{name} (missing)', { name: shownAs(one, twin(one)) }))))
    read()
  }, (error) => fill(body, problem(error)))
}
