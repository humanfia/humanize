// What a workspace was last set up with: the flow it opens on and every flow set up there, and
// forgetting all of it -- which also stops it being offered, where no epic ran there.

import { address, get, post } from '../../api.js'
import { confirming, fill, h, pathText, problem } from '../../dom.js'

export function draw(holder, query, parts, scope) {
  let workspace = query.get('workspace') || ''
  const choosing = h('select', { 'aria-label': 'Workdir', 'data-hmz': 'settings-workdir' })
  const body = h('div', { class: 'reading' }, h('p', { class: 'loading', role: 'status' }, 'Reading the settings…'))
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
          h('dd', {}, pathText(settings.workspace)),
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
              const answer = await post(scope.at('/api/settings/forget'), { workspace: settings.workspace })
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
    get(address(scope.at('/api/settings'), { workspace }))
      .then((settings) => mine === reading && shown(settings))
      .catch((error) => mine === reading && fill(body, problem(error)))
      .finally(() => mine === reading && body.removeAttribute('aria-busy'))
  }

  get(scope.at('/api/workspaces')).then((answer) => {
    if (!workspace) workspace = answer.here
    fill(choosing, answer.workspaces.map((one) => h('option', { value: one.path, selected: one.path === workspace }, one.path)))
    read()
  }, (error) => fill(body, problem(error)))
}
