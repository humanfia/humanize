// What is true wherever humanize runs: whether a turn's working is shown, who a side question
// about a run is asked of, and whether humanize reports its own failures.

import { get, post } from '../../api.js'
import { acting, fill, h, problem } from '../../dom.js'
import { agentPicker, readBackends } from '../../pickers.js'

export function draw(holder, query, parts, scope) {
  const shown = (settings) => {
    const details = h('input', { type: 'checkbox', checked: settings.details })
    // Who a side question goes to: the flow's first agent, or one picked as an agent is picked.
    const whom = h('select', { 'aria-label': 'Who btw asks', 'data-hmz': 'btw-whom' }, h('option', { value: 'first', selected: !settings.btw }, 'First agent of the flow'), h('option', { value: 'chosen', selected: Boolean(settings.btw) }, 'Chosen agent'))
    if (picker) picker.leave()
    picker = agentPicker({ name: 'btw', get clis() { return backends ? Object.keys(backends.clis) : [] } }, settings.btw, () => {})
    picker.node.hidden = !settings.btw
    whom.addEventListener('change', () => (picker.node.hidden = whom.value !== 'chosen'))
    const reports = h(
      'select',
      { 'aria-label': 'Report humanize’s own failures' },
      h('option', { value: '', selected: settings.reports === null, disabled: true }, 'Not set'),
      h('option', { value: 'yes', selected: settings.reports === true }, 'On'),
      h('option', { value: 'no', selected: settings.reports === false }, 'Off'),
    )
    const said = () => {
      const given = { btw: whom.value === 'chosen' ? picker.value() : '', details: details.checked }
      if (reports.value) given.reports = reports.value === 'yes'
      return given
    }
    // Saved where it stands: the button says so, rather than the form being drawn again over it.
    const save = acting('Save', () => post(scope.at('/api/settings'), said()), { kind: 'btn primary', busy: 'Saving…', done: 'Saved' })
    fill(
      holder,
      h(
        'section',
        { class: 'panel' },
        h(
          'div',
          { class: 'form' },
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'Details'), h('label', { class: 'check' }, details, 'Tool calls and thinking')),
          h('div', { class: 'field', 'data-hmz': 'btw-agent' }, h('span', { class: 'label' }, 'btw agent'), whom, picker.node, h('span', { class: 'hint' }, 'Who a side question about a whole epic is asked of.')),
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'Error reports'), reports, h('span', { class: 'hint' }, 'Whether humanize sends a report of its own crashes. Nothing anybody typed, no file and no credential is ever sent.')),
          h('div', { class: 'row' }, save, scope.batch(() => [['/api/settings', said()]])),
        ),
      ),
    )
  }
  let picker = null
  let backends = null
  Promise.all([get(scope.at('/api/settings')), readBackends(undefined, scope.base)])
    .then(([settings, read]) => {
      backends = read
      shown(settings)
    })
    .catch((error) => fill(holder, problem(error)))
}
