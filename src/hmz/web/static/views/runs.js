// The runs of this directory, newest first: how each went, what it was asked, which agents
// ran it and what it cost -- the list `/epics` is in the terminal interface.

import { address, poll, refresh } from '../api.js'
import { go, stays } from '../app.js'
import { ago, badge, empty, fill, h, lasting, settled, when } from '../dom.js'
import { follow } from '../held.js'

/** How a run can have ended, in the order the filter offers them. */
const ENDINGS = ['running', 'done', 'failed', 'stopped', 'unfinished']

/** How many rows a page of the list holds. */
const PAGE = 50

export function mount(root, { query }) {
  const chosen = {
    status: query.get('status') || '',
    flow: query.get('flow') || '',
    q: query.get('q') || '',
    offset: Number(query.get('offset') || 0),
  }
  const statuses = h('div', { class: 'segmented', role: 'group', 'aria-label': 'How the run went' })
  const flows = h('select', { 'aria-label': 'Flow' })
  const search = h('input', { class: 'search', type: 'search', placeholder: 'Find a task or flow', value: chosen.q, 'aria-label': 'Find' })
  const body = h('div', { 'data-hmz': 'runs' }, h('p', { class: 'loading', role: 'status' }, 'Reading the runs…'))
  fill(
    root,
    h(
      'div',
      { class: 'head' },
      h('div', {}, h('div', { class: 'kicker' }, 'this directory'), h('h1', {}, 'Runs'), h('p', { class: 'lede' }, 'Every run of a flow here, newest first.')),
      h('div', { class: 'actions' }, h('a', { class: 'btn primary', href: '#/start' }, 'Start a run')),
    ),
    h('div', { class: 'filters' }, statuses, flows, search),
    h('section', { class: 'panel' }, body),
  )

  let stop = () => {}
  const watch = () => {
    stop()
    stays({ status: chosen.status, flow: chosen.flow, q: chosen.q, offset: chosen.offset || '' })
    const url = address('/api/runs', { status: chosen.status, flow: chosen.flow, q: chosen.q, offset: chosen.offset, limit: PAGE })
    stop = poll(url, 5000, (data, error) => draw(data, error))
  }
  const redraw = settled(() => {
    chosen.offset = 0
    watch()
  }, 250)
  search.addEventListener('input', () => {
    chosen.q = search.value.trim()
    redraw()
  })
  flows.addEventListener('change', () => {
    chosen.flow = flows.value
    chosen.offset = 0
    watch()
  })

  function draw(data, error) {
    if (!data) {
      fill(body, error ? h('p', { class: 'error', role: 'alert' }, error.message) : h('p', { class: 'loading' }, 'Reading the runs…'))
      return
    }
    drawStatuses(data)
    drawFlows(data)
    fill(body, error ? h('p', { class: 'error', role: 'alert' }, error.message) : null, table(data))
  }

  function drawStatuses(data) {
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
  }

  function drawFlows(data) {
    const names = [...new Set([...data.flows, chosen.flow].filter(Boolean))].sort()
    fill(flows, h('option', { value: '' }, 'Every flow'), names.map((name) => h('option', { value: name, selected: name === chosen.flow }, name)))
  }

  function table(data) {
    if (!data.total) {
      return empty(
        chosen.status || chosen.flow || chosen.q ? 'No run is like that.' : 'Nothing has run here yet.',
        chosen.status || chosen.flow || chosen.q ? ' Clear the filters to see every run.' : ' Start a flow, and its run is written down here as it goes.',
        h('a', { class: 'btn', href: '#/start' }, 'Start a run'),
      )
    }
    const rows = data.runs.map((run) => {
      const link = `#/runs/${encodeURIComponent(run.name)}`
      const row = h(
        'tr',
        { class: ['link', run.held && 'held'], 'data-hmz': 'run' },
        h('td', {}, badge(run.how)),
        h(
          'td',
          { class: 'task' },
          h('a', { href: link }, run.task || h('span', { class: 'dim' }, '(no task)')),
          h('div', { class: 'dim mono' }, run.flow, run.held ? [' · ', h('span', { class: 'pill-live' }, 'live')] : null),
        ),
        h('td', { class: 'hide-narrow' }, h('div', { class: 'agents' }, run.agents.map((one) => h('span', { class: 'chip', title: one.runs }, one.role, h('span', { class: 'dim' }, one.runs.split(':')[0]))))),
        h('td', { class: 'num' }, run.spent ? run.spent.money || '—' : '—', run.spent ? h('div', { class: 'dim' }, `${run.spent.tokens} out`) : null),
        h('td', { class: 'num hide-narrow' }, run.ended ? lasting((Date.parse(run.ended) - Date.parse(run.began)) / 1000) : '—'),
        h('td', { class: 'num', title: when(run.began) }, ago(run.began)),
      )
      row.addEventListener('click', (event) => {
        if (event.target.closest('a')) return
        go(link.slice(1))
      })
      return row
    })
    const shown = `${data.offset + 1}–${data.offset + data.runs.length} of ${data.total}`
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
    return [
      h(
        'div',
        { class: 'table-wrap' },
        h(
          'table',
          {},
          h('caption', { class: 'sr-only' }, 'Runs of this directory, newest first'),
          h(
            'thead',
            {},
            h(
              'tr',
              {},
              h('th', { scope: 'col' }, 'Status'),
              h('th', { scope: 'col' }, 'Task'),
              h('th', { scope: 'col', class: 'hide-narrow' }, 'Agents'),
              h('th', { scope: 'col', class: 'num' }, 'Spent'),
              h('th', { scope: 'col', class: 'num hide-narrow' }, 'Took'),
              h('th', { scope: 'col', class: 'num' }, 'Began'),
            ),
          ),
          h('tbody', {}, rows),
        ),
      ),
      h('div', { class: 'pages', role: 'status' }, previous, next, shown),
    ]
  }

  watch()
  // A run starting or ending here is a row changing: read the list again as it does.
  let state = ''
  const unfollow = follow((held) => {
    const now = held.standing.run ? held.standing.run.state : ''
    if (state && now !== state) refresh('/api/runs')
    state = now
  })
  return () => {
    stop()
    unfollow()
  }
}
