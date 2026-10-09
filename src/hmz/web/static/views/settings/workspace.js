// What this directory was last set up with: the flow it opens on and every flow set up here,
// and forgetting all of it.

import { get, post } from '../../api.js'
import { confirming, fill, h, problem } from '../../dom.js'

export function draw(holder) {
  const shown = (settings, forgot) => {
    fill(
      holder,
      h(
        'section',
        { class: 'panel' },
        h(
          'dl',
          { class: 'facts' },
          h('dt', {}, 'directory'),
          h('dd', { class: 'mono' }, settings.workspace),
          h('dt', {}, 'default flow'),
          h('dd', {}, settings.flow || 'none', h('div', { class: 'dim' }, 'what Start opens on, and what /flow chose last')),
          h('dt', {}, 'set up'),
          h('dd', {}, settings.flows.length ? settings.flows.join(', ') : 'nothing yet'),
        ),
        forgot === undefined ? null : h('p', { class: 'note', role: 'status' }, forgot ? 'Forgotten: every flow here starts from nothing again.' : 'There was nothing here to forget.'),
        h(
          'p',
          { class: 'row' },
          confirming({
            label: 'Forget this directory',
            ask: `Forget what ${settings.flows.length || 'every'} flow${settings.flows.length === 1 ? ' was' : 's were'} set up with here?`,
            yes: 'Forget it',
            no: 'Keep it',
            act: async () => {
              const answer = await post('/api/settings/forget')
              shown(answer, answer.forgot)
            },
          }),
        ),
      ),
    )
  }
  get('/api/settings')
    .then((settings) => shown(settings))
    .catch((error) => fill(holder, problem(error)))
}
