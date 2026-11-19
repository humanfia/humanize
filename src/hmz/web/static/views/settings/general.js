// What is true wherever Humanize runs: whether a turn's working is shown, whether the sessions
// each harness had of its own are listed, the nous a new Ai-chan conversation defaults to, and
// whether Humanize reports its own failures.

import { refresh } from '../../api.js'
import { acting, fill, h, problem } from '../../dom.js'
import { nousField } from '../../pickers.js'

export function draw(holder, query, parts, scope) {
  const shown = (settings, offered) => {
    const details = h('input', { type: 'checkbox', checked: settings.details })
    const harness = h('input', { type: 'checkbox', checked: settings.harness_sessions === true, 'data-hmz': 'harness-sessions' })
    // The nous a new Ai-chan conversation defaults to: none until one is picked.
    const aiChan = nousField(settings.ai_chan || '', offered, { label: 'Ai-chan’s nous', hmz: 'ai-chan-nous', placeholder: 'None' })
    const reports = h(
      'select',
      { 'aria-label': 'Report Humanize’s own failures' },
      h('option', { value: '', selected: settings.reports === null, disabled: true }, 'Not set'),
      h('option', { value: 'yes', selected: settings.reports === true }, 'On'),
      h('option', { value: 'no', selected: settings.reports === false }, 'Off'),
    )
    const said = () => {
      const given = { ai_chan: aiChan.input.value.trim(), details: details.checked, harness_sessions: harness.checked }
      if (reports.value) given.reports = reports.value === 'yes'
      return given
    }
    // Saved where it stands: the button says so, rather than the form being drawn again over it.
    // The sidebar lists by what was saved, at once.
    const save = acting('Save', () => scope.call('settings.set', said()).then(() => refresh('settings.get')), { kind: 'btn primary', busy: 'Saving…', done: 'Saved' })
    fill(
      holder,
      h(
        'section',
        { class: 'panel' },
        h(
          'div',
          { class: 'form' },
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'Details'), h('label', { class: 'check' }, details, 'Tool calls and thinking')),
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'Harness sessions'), h('label', { class: 'check' }, harness, 'List in sidebar'), h('span', { class: 'hint' }, 'The sessions each harness had of its own in a folder, which Humanize did not run, listed after its chats. They are only read: continuing one copies it into a chat, and the harness’s own files are never changed.')),
          h('div', { class: 'field', 'data-hmz': 'ai-chan-setting' }, h('span', { class: 'label' }, 'Ai-chan'), aiChan.node, h('span', { class: 'hint' }, 'The nous a new Ai-chan conversation starts with: a nous by its name, or an agent such as claude/claude-opus-5. With none, each conversation names its own.')),
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'Error reports'), reports, h('span', { class: 'hint' }, 'Whether Humanize sends a report of its own crashes. Nothing anybody typed, no file and no credential is ever sent.')),
          h('div', { class: 'row' }, save, scope.batch(() => [['settings.set', said()]])),
        ),
      ),
    )
  }
  Promise.all([scope.call('settings.get'), scope.call('nous.list').catch(() => null)])
    .then(([settings, nous]) => shown(settings, nous))
    .catch((error) => fill(holder, problem(error)))
}
