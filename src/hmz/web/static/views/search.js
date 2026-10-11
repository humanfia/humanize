// Finding a run, as ChatGPT finds a chat: a dialog over the page that lists the runs of this
// directory newest first -- how each ended or that it is going, its task, flow and agents,
// what it spent and how long it took -- found by how it went, by flow and by its task, a page
// at a time. The list `/epics` is in the terminal interface.

import { address, poll } from '../api.js'
import { shut, stays } from '../app.js'
import { nameOf, workspaces } from '../places.js'
import { ago, badge, flowName, empty, fill, h, headline, icon, iconButton, lasting, settled, when } from '../dom.js'

/** How a run can have ended, in the order the filter offers them. */
const ENDINGS = ['running', 'done', 'failed', 'stopped', 'unfinished']

/** How many rows a page of the list holds. */
const PAGE = 50

export function mount(root, { query }) {
  const chosen = {
    status: query.get('status') || '',
    flow: query.get('flow') || '',
    workspace: query.get('workspace') || '',
    q: query.get('q') || '',
    offset: Number(query.get('offset') || 0),
  }
  const search = h('input', { class: 'dialog-search', type: 'search', placeholder: 'Search epics by task or flow', value: chosen.q, 'aria-label': 'Find', autofocus: true })
  const statuses = h('div', { class: 'segmented', role: 'group', 'aria-label': 'How the epic went' })
  const flows = h('select', { 'aria-label': 'Flow' })
  const places = h('select', { 'aria-label': 'Workdir', 'data-hmz': 'search-workspace' }, h('option', { value: '' }, 'All workdirs'))
  workspaces().then((answer) => {
    fill(places, h('option', { value: '' }, 'All workdirs'), answer.workspaces.map((one) => h('option', { value: one.path, selected: one.path === chosen.workspace, title: one.path }, one.name)))
  }, () => {})
  places.addEventListener('change', () => {
    chosen.workspace = places.value
    chosen.offset = 0
    watch()
  })
  const body = h('div', { class: 'dialog-body', 'data-hmz': 'found' }, h('p', { class: 'loading', role: 'status' }, 'Reading the epics…'))
  const foot = h('div', { class: 'dialog-foot', role: 'status' })
  root.classList.add('dialog-search-box')
  root.setAttribute('aria-label', 'Search epics')
  fill(
    root,
    h('div', { class: 'dialog-head' }, icon('search'), search, iconButton('close', 'Close', { onclick: shut })),
    h('div', { class: 'dialog-filters' }, statuses, places, flows),
    body,
    foot,
  )

  let stop = () => {}
  const watch = () => {
    stop()
    stays({ status: chosen.status, flow: chosen.flow, workspace: chosen.workspace, q: chosen.q, offset: chosen.offset || '' })
    stop = poll(address('/api/runs', { status: chosen.status, flow: chosen.flow, workspace: chosen.workspace, q: chosen.q, offset: chosen.offset, limit: PAGE }), 5000, draw)
  }
  const again = settled(() => {
    chosen.offset = 0
    watch()
  }, 250)
  search.addEventListener('input', () => {
    chosen.q = search.value.trim()
    again()
  })
  flows.addEventListener('change', () => {
    chosen.flow = flows.value
    chosen.offset = 0
    watch()
  })

  function draw(data, error) {
    if (!data) {
      fill(body, error ? h('p', { class: 'error', role: 'alert' }, error.message) : h('p', { class: 'loading' }, 'Reading the epics…'))
      return
    }
    const all = Object.values(data.counts).reduce((sum, one) => sum + one, 0)
    fill(
      statuses,
      [['', 'All', all], ...ENDINGS.map((how) => [how, how, data.counts[how] || 0])].map(([how, said, count]) => {
        const button = h('button', { type: 'button', 'aria-pressed': String(chosen.status === how) }, said, h('span', { class: 'count' }, count))
        button.addEventListener('click', () => {
          chosen.status = how
          chosen.offset = 0
          watch()
        })
        return button
      }),
    )
    const names = [...new Set([...data.flows, chosen.flow].filter(Boolean))].sort()
    fill(flows, h('option', { value: '' }, 'All flows'), names.map((name) => h('option', { value: name, selected: name === chosen.flow }, name)))
    if (!data.total) {
      fill(body, error ? h('p', { class: 'error', role: 'alert' }, error.message) : null, empty(chosen.status || chosen.flow || chosen.q ? 'No epic is like that.' : 'No epic here yet.', chosen.status || chosen.flow || chosen.q ? ' Clear the filters to see every epic.' : ' Start a flow, and its epic is written down here as it goes.'))
      fill(foot)
      return
    }
    fill(
      body,
      error ? h('p', { class: 'error', role: 'alert' }, error.message) : null,
      h(
        'ul',
        { class: 'results', role: 'list' },
        data.runs.map((run) =>
          h(
            'li',
            {},
            h(
              'a',
              { class: ['result', run.held && 'held'], href: `#/epics/${encodeURIComponent(run.name)}`, 'data-hmz': 'epic' },
              h('span', { class: 'result-top' }, badge(run.how), h('span', { class: 'result-task' }, headline(run.task)), h('span', { class: 'result-when', title: when(run.began) }, ago(run.began))),
              h(
                'span',
                { class: 'result-meta' },
                h('span', { class: 'mono', title: run.workspace }, nameOf(run.workspace)),
                h('span', { class: 'mono', title: run.flow }, flowName(run.flow)),
                run.agents.map((one) => h('span', { class: 'chip', title: one.runs }, one.role, h('span', { class: 'dim' }, one.runs.split(':')[0]))),
                h('span', { class: 'mono' }, run.spent ? `${run.spent.money || '—'} · ${run.spent.tokens} out` : '—'),
                run.ended ? h('span', { class: 'mono' }, `took ${lasting((Date.parse(run.ended) - Date.parse(run.began)) / 1000)}`) : null,
                h('span', { class: 'mono' }, `${run.sessions} session${run.sessions === 1 ? '' : 's'}`),
                run.resumable && !run.held && run.how !== 'done' ? h('span', { class: 'node-tag' }, 'Resumable') : null,
              ),
            ),
          ),
        ),
      ),
    )
    const previous = h('button', { class: 'btn quiet small', type: 'button', disabled: data.offset === 0 }, 'Newer')
    const next = h('button', { class: 'btn quiet small', type: 'button', disabled: data.offset + data.runs.length >= data.total }, 'Older')
    previous.addEventListener('click', () => {
      chosen.offset = Math.max(0, data.offset - PAGE)
      watch()
    })
    next.addEventListener('click', () => {
      chosen.offset = data.offset + PAGE
      watch()
    })
    fill(foot, previous, next, `${data.offset + 1}–${data.offset + data.runs.length} of ${data.total}`)
  }

  watch()
  return () => stop()
}
