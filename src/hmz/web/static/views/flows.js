// The flows there are to run here, as ChatGPT lays out what it can be: a card for each, by
// where it came from, and -- one opened -- what it declares: its roles, its environments, its
// params and whether a run of it can be picked up, with the way to start one.

import { get, poll } from '../api.js'
import { stays } from '../app.js'
import { empty, fill, h, icon, permitted, problem } from '../dom.js'
import { workspacePicker } from '../places.js'
import { bar } from '../shell.js'

export function mount(root, { query }) {
  let chosen = query.get('flow') || ''
  // A workspace's flows: its own and yours, and the flowverses installed.
  let workspace = query.get('workspace') || ''
  const place = workspacePicker(workspace, (path) => {
    workspace = path
    chosen = ''
    watch()
  })
  const list = h('div', { class: 'gallery', 'data-hmz': 'flows' }, h('p', { class: 'loading', role: 'status' }, 'Reading the flows…'))
  const shown = h('section', { class: 'flow-detail', 'aria-live': 'polite', hidden: true })
  fill(
    root,
    h(
      'div',
      { class: 'view' },
      bar({ title: 'Flows', actions: [place.node] }),
      h('div', { class: 'view-scroll' }, h('div', { class: 'view-pad wide' }, shown, list)),
    ),
  )

  let stop = () => {}
  const watch = () => {
    stop()
    stays({ workspace, flow: chosen })
    stop = poll(`/api/flows?workspace=${encodeURIComponent(workspace)}`, 30000, drawn)
    if (chosen) show(chosen)
    else {
      shown.hidden = false
      fill(shown, empty('Pick a flow.', ' What it declares is shown here.'))
    }
  }

  function drawn(data, error) {
    if (!data) {
      fill(list, error ? problem(error) : h('p', { class: 'loading' }, 'Reading the flows…'))
      return
    }
    const whose = {}
    for (const one of data.flows) (whose[one.whose] ||= []).push(one)
    fill(
      list,
      Object.entries(whose).map(([from, flows]) =>
        h(
          'section',
          { class: 'gallery-group' },
          h('h2', { class: 'kicker' }, from),
          h(
            'div',
            { class: 'cards' },
            flows.map((one) => {
              const card = h(
                'button',
                { class: ['card', one.name === chosen && 'chosen'], type: 'button', 'data-flow': one.name, 'aria-pressed': String(one.name === chosen) },
                h('span', { class: 'card-mark', 'aria-hidden': 'true' }, one.name.slice(0, 1).toUpperCase()),
                h('span', { class: 'card-name' }, one.name, one.name === data.flow ? h('span', { class: 'node-tag' }, 'Default') : null),
                one.about ? h('span', { class: 'card-about' }, one.about) : null,
              )
              card.addEventListener('click', () => show(one.name))
              return card
            }),
          ),
        ),
      ),
    )
  }

  async function show(name) {
    chosen = name
    stays({ workspace, flow: name })
    for (const card of list.querySelectorAll('.card')) {
      card.classList.toggle('chosen', card.dataset.flow === name)
      card.setAttribute('aria-pressed', String(card.dataset.flow === name))
    }
    shown.hidden = false
    fill(shown, h('p', { class: 'loading', role: 'status' }, `Reading ${name}…`))
    let flow
    try {
      flow = await get(`/api/flow?name=${encodeURIComponent(name)}&workspace=${encodeURIComponent(workspace)}`)
    } catch (error) {
      if (chosen === name) fill(shown, problem(error))
      return
    }
    // Another flow was chosen while this one was read: what it says is no longer asked for.
    if (chosen !== name) return
    const params = Object.entries(flow.params.properties || {})
    fill(
      shown,
      h(
        'header',
        {},
        h('div', {}, h('div', { class: 'kicker' }, 'flow'), h('h2', {}, flow.name)),
        h('a', { class: 'btn primary', href: `#/new?flow=${encodeURIComponent(flow.name)}&workspace=${encodeURIComponent(workspace)}` }, icon('new'), 'New epic'),
      ),
      flow.description ? h('p', { class: 'prose' }, flow.description) : null,
      h(
        'dl',
        { class: 'facts' },
        h('dt', {}, 'ref'),
        h('dd', { class: 'mono' }, flow.ref),
        h('dt', {}, 'resumable'),
        h('dd', {}, flow.resumable ? (flow.resumes ? 'yes, with an epic here to resume' : 'yes') : 'no'),
        h('dt', {}, 'agents'),
        h('dd', {}, flow.agents.length ? flow.agents.map((role) => h('div', {}, h('b', {}, role.name), role.auto ? h('span', { class: 'dim' }, ' (a person, answering here)') : null, role.harness ? [' ', h('span', { class: 'chip' }, role.harness)] : null, role.auto ? null : h('div', { class: 'dim' }, permitted(role.permission)))) : '—'),
        h('dt', {}, 'environments'),
        h('dd', {}, flow.envs.length ? flow.envs.map((role) => h('div', {}, h('b', {}, role.name), role.auto ? h('span', { class: 'dim' }, ' (this directory)') : null)) : '—'),
        h('dt', {}, 'params'),
        h('dd', {}, params.length ? params.map(([key, one]) => h('div', {}, h('b', { class: 'mono' }, key), one.description ? h('span', { class: 'dim' }, ` — ${one.description}`) : null)) : 'none'),
      ),
    )
  }

  watch()
  return () => stop()
}
