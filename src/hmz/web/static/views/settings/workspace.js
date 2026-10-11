// What a workspace was last set up with: the flow it opens on and every flow set up there, and
// forgetting all of it -- which also stops it being offered, where no epic ran there.

import { get, post } from '../../api.js'
import { confirming, fill, h, problem } from '../../dom.js'
import { workspaces } from '../../places.js'

export function draw(holder, query) {
  let workspace = query.get('workspace') || ''
  const choosing = h('select', { 'aria-label': 'Workdir', 'data-hmz': 'settings-workdir' })
  const body = h('div')
  fill(holder, h('label', { class: 'field' }, h('span', { class: 'label' }, 'Workdir'), choosing), body)
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
          h('dt', {}, 'directory'),
          h('dd', { class: 'mono' }, settings.workspace),
          h('dt', {}, 'default flow'),
          h('dd', {}, settings.flow || 'none'),
          h('dt', {}, 'configured'),
          h('dd', {}, settings.flows.length ? settings.flows.join(', ') : 'none'),
        ),
        forgot === undefined ? null : h('p', { class: 'note', role: 'status' }, forgot ? 'Forgotten.' : 'Nothing to forget.'),
        h(
          'p',
          { class: 'row' },
          confirming({
            label: 'Forget',
            ask: `Forget how ${settings.flows.length || 'every'} flow${settings.flows.length === 1 ? ' was' : 's were'} set up here?`,
            yes: 'Forget',
            no: 'Cancel',
            act: async () => {
              const answer = await post('/api/settings/forget', { workspace: settings.workspace })
              shown(answer, answer.forgot)
            },
          }),
        ),
      ),
    )
  }

  function read() {
    get(`/api/settings?workspace=${encodeURIComponent(workspace)}`)
      .then((settings) => shown(settings))
      .catch((error) => fill(body, problem(error)))
  }

  workspaces().then((answer) => {
    if (!workspace) workspace = answer.here
    fill(choosing, answer.workspaces.map((one) => h('option', { value: one.path, selected: one.path === workspace }, one.path)))
    read()
  }, (error) => fill(body, problem(error)))
}
