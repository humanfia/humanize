// What is true wherever humanize runs: whether a turn's working is shown, who a side question
// about a run is asked of, and whether humanize reports its own failures.

import { get, post } from '../../api.js'
import { acting, fill, h, problem } from '../../dom.js'

export function draw(holder) {
  const shown = (settings) => {
    const details = h('input', { type: 'checkbox', checked: settings.details })
    const btw = h('input', { type: 'text', value: settings.btw, placeholder: 'the flow’s first agent', 'aria-label': 'The agent a side question goes to', size: '32' })
    const reports = h(
      'select',
      { 'aria-label': 'Report humanize’s own failures' },
      h('option', { value: '', selected: settings.reports === null, disabled: true }, 'not answered yet'),
      h('option', { value: 'yes', selected: settings.reports === true }, 'yes, report them'),
      h('option', { value: 'no', selected: settings.reports === false }, 'no'),
    )
    const save = acting(
      'Save',
      async () => {
        const said = { btw: btw.value.trim(), details: details.checked }
        if (reports.value) said.reports = reports.value === 'yes'
        shown(await post('/api/settings', said))
      },
      { kind: 'btn primary', busy: 'Saving…', done: 'Saved' },
    )
    fill(
      holder,
      h(
        'section',
        { class: 'panel' },
        h(
          'div',
          { class: 'form' },
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'details'), h('label', { class: 'check' }, details, 'Show every tool call and all of the thinking')),
          h('div', { class: 'field' }, h('span', { class: 'label' }, '/btw agent'), btw, h('span', { class: 'hint' }, 'Who a side question about a run is asked of, as -a spells an agent. Empty asks the flow’s first agent.')),
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'error reports'), reports, h('span', { class: 'hint' }, 'Whether humanize sends a report of its own crashes. Nothing anybody typed, no file and no credential is ever sent.')),
          h('div', { class: 'row' }, save),
        ),
      ),
    )
  }
  get('/api/settings')
    .then(shown)
    .catch((error) => fill(holder, problem(error)))
}
