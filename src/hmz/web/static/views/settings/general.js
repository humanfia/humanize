// What is true wherever Humanize runs: whether a turn's working is shown, whether the sessions
// each harness had of its own are listed, and whether Humanize reports its own failures.

import { refresh } from '../../api.js'
import { acting, fill, h, problem } from '../../dom.js'
import { t } from '../../i18n.js'

export function draw(holder, query, parts, scope) {
  const shown = (settings) => {
    const details = h('input', { type: 'checkbox', checked: settings.details })
    const harness = h('input', { type: 'checkbox', checked: settings.harness_sessions === true, 'data-hmz': 'harness-sessions' })
    const reports = h(
      'select',
      { 'aria-label': t('Report Humanize’s own failures') },
      h('option', { value: '', selected: settings.reports === null, disabled: true }, t('Not set')),
      h('option', { value: 'yes', selected: settings.reports === true }, t('On')),
      h('option', { value: 'no', selected: settings.reports === false }, t('Off')),
    )
    const said = () => {
      const given = { details: details.checked, harness_sessions: harness.checked }
      if (reports.value) given.reports = reports.value === 'yes'
      return given
    }
    // Saved where it stands: the button says so, rather than the form being drawn again over it.
    // The sidebar lists by what was saved, at once.
    const save = acting(t('Save'), () => scope.call('settings.set', said()).then(() => refresh('settings.get')), { kind: 'btn primary', busy: t('Saving…'), done: t('Saved') })
    fill(
      holder,
      h(
        'section',
        { class: 'panel' },
        h(
          'div',
          { class: 'form' },
          h('div', { class: 'field' }, h('span', { class: 'label' }, t('Details')), h('label', { class: 'check' }, details, t('Tool calls and thinking'))),
          h('div', { class: 'field' }, h('span', { class: 'label' }, t('Harness sessions')), h('label', { class: 'check' }, harness, t('List in sidebar')), h('span', { class: 'hint' }, t('The sessions each harness had of its own in a folder, which Humanize did not run, listed after its chats. They are only read: continuing one copies it into a chat, and the harness’s own files are never changed.'))),
          h('div', { class: 'field' }, h('span', { class: 'label' }, t('Error reports')), reports, h('span', { class: 'hint' }, t('Whether Humanize sends a report of its own crashes. Nothing anybody typed, no file and no credential is ever sent.'))),
          h('div', { class: 'row' }, save, scope.batch(() => [['settings.set', said()]], { small: false })),
        ),
      ),
    )
  }
  scope
    .call('settings.get')
    .then(shown)
    .catch((error) => fill(holder, problem(error)))
}
