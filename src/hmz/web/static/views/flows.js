// The flows there are to run here, by where each came from, and what one declares: its roles,
// its params and whether a run of it can be picked up -- with the way to start one.

import { get, poll } from '../api.js'
import { stays } from '../app.js'
import { empty, fill, h, permitted, problem } from '../dom.js'

export function mount(root, { query }) {
  let chosen = query.get('flow') || ''
  const list = h('div', { class: 'nodes', 'data-hmz': 'flows' })
  const shown = h('section', { class: 'panel', 'aria-live': 'polite' })
  fill(
    root,
    h('div', { class: 'head' }, h('div', {}, h('div', { class: 'kicker' }, 'what can run here'), h('h1', {}, 'Flows'), h('p', { class: 'lede' }, 'The flows of this directory, yours, and the flowverses installed here.'))),
    h('div', { class: 'grid wide' }, shown, h('section', { class: 'panel' }, h('h2', {}, 'On offer'), list)),
  )

  const stop = poll('/api/flows', 30000, (data, error) => {
    if (!data) {
      fill(list, error ? problem(error) : h('p', { class: 'loading' }, 'Reading the flows…'))
      return
    }
    const whose = {}
    for (const one of data.flows) (whose[one.whose] ||= []).push(one)
    fill(
      list,
      Object.entries(whose).map(([from, flows]) => [
        h('div', { class: 'kicker' }, from),
        flows.map((one) => {
          const button = h(
            'button',
            { class: ['node', one.name === chosen && 'working'], type: 'button', style: { textAlign: 'left', cursor: 'pointer' } },
            h('div', { class: 'top' }, one.name),
            one.about ? h('div', { class: 'meta' }, one.about) : null,
          )
          button.addEventListener('click', () => show(one.name))
          return button
        }),
      ]),
    )
    if (!chosen && data.flows.length) show(data.flow || data.flows[0].name)
  })

  async function show(name) {
    chosen = name
    stays({ flow: name })
    for (const button of list.querySelectorAll('.node')) button.classList.toggle('working', button.querySelector('.top').textContent === name)
    fill(shown, h('p', { class: 'loading', role: 'status' }, `Reading ${name}…`))
    let flow
    try {
      flow = await get(`/api/flow?name=${encodeURIComponent(name)}`)
    } catch (error) {
      if (chosen === name) fill(shown, problem(error))
      return
    }
    // Another flow was chosen while this one was read: what it says is no longer asked for.
    if (chosen !== name) return
    const params = Object.entries(flow.params.properties || {})
    fill(
      shown,
      h('header', {}, h('h2', {}, flow.name), h('a', { class: 'btn primary', href: `#/start?flow=${encodeURIComponent(flow.name)}` }, 'Start it')),
      flow.description ? h('p', { class: 'lede' }, flow.description) : null,
      h(
        'dl',
        { class: 'facts' },
        h('dt', {}, 'ref'),
        h('dd', { class: 'mono' }, flow.ref),
        h('dt', {}, 'resumable'),
        h('dd', {}, flow.resumable ? (flow.resumes ? 'yes, and a run of it here can be picked up' : 'yes') : 'no'),
        h('dt', {}, 'agents'),
        h('dd', {}, flow.agents.length ? flow.agents.map((role) => h('div', {}, h('b', {}, role.name), role.auto ? h('span', { class: 'dim' }, ' (a person, answering here)') : null, role.harness ? [' ', h('span', { class: 'chip' }, role.harness)] : null, role.auto ? null : h('div', { class: 'dim' }, permitted(role.permission)))) : '—'),
        h('dt', {}, 'environments'),
        h('dd', {}, flow.envs.length ? flow.envs.map((role) => h('div', {}, h('b', {}, role.name), role.auto ? h('span', { class: 'dim' }, ' (this directory)') : null)) : '—'),
        h('dt', {}, 'params'),
        h('dd', {}, params.length ? params.map(([key, one]) => h('div', {}, h('b', { class: 'mono' }, key), one.description ? h('span', { class: 'dim' }, ` — ${one.description}`) : null)) : 'none'),
      ),
    )
  }

  if (chosen) show(chosen)
  else fill(shown, empty('Pick a flow.', ' What it declares is shown here.'))
  return stop
}
