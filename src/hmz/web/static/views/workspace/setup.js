// What a workspace was last set up with: the flow it opens on and every flow set up there -- its
// directory is said over the page, by the dialog -- and
// forgetting all of it -- which also stops it being offered, where no epic ran there. The
// workspace is the one the dialog is of (views/workspace.js, Section 3.11.2.11 of
// protocol/web.md).

import { confirming } from '../../confirm.js'
import { fill, h, problem } from '../../dom.js'
import { t } from '../../i18n.js'

export function draw(holder, query, parts, scope) {
  const body = h('div', { class: 'reading' }, h('p', { class: 'loading', role: 'status' }, t('Reading the settings…')))
  fill(holder, body)

  const shown = (settings, forgot) => {
    fill(
      body,
      h(
        'section',
        { class: 'panel' },
        h(
          'dl',
          { class: 'facts' },
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

  scope
    .call('settings.get', { workspace: scope.workspace })
    .then(shown)
    .catch((error) => fill(body, problem(error)))
}
