// Finding a chat or an epic, as Claude's window finds a session: a dialog over the page with the
// field at its top, under it a row of tabs -- everything, the chats, the epics -- then what was
// found, newest first, a line apiece, and a foot that says what the keys do. The arrows move
// along what was found and Enter opens it; what else there is to say of the one moved to -- its
// flow and agents, what it spent and how long it took -- is said in a line over the foot. The
// filters by how it went, by folder and by flow open under the tabs. The list `/epics` is in
// the terminal interface.

import { given, hash, poll } from '../api.js'
import { shut, stays } from '../app.js'
import { nameOf, workspaces } from '../places.js'
import { epicMenu } from '../sidebar.js'
import { pick } from '../importing.js'
import { menuOn } from '../ui.js'
import { dragged } from '../shell.js'
import { ago, badge, flowName, empty, fill, h, headline, icon, iconButton, lasting, settled, when } from '../dom.js'
import { HINTS, PAGE, TABS, asked, chosenOf, filtered, heading, moved, narrowed, onFlow, onTab, paged, turned } from '../search-model.js'

/** How a run can have ended, in the order the filter offers them. */
const ENDINGS = ['running', 'done', 'failed', 'stopped', 'unfinished']

export function mount(root, { query }) {
  let chosen = chosenOf(query)
  const search = h('input', { class: 'dialog-search', type: 'search', placeholder: 'Search chats and epics', value: chosen.q, 'aria-label': 'Find', 'aria-controls': 'search-found', autocomplete: 'off', autofocus: true })
  const tabs = h('div', { class: 'search-tabs', role: 'tablist', 'aria-label': 'Type', 'data-hmz': 'search-tabs' })
  const statuses = h('div', { class: 'segmented', role: 'group', 'aria-label': 'How it went' })
  const flows = h('select', { 'aria-label': 'Flow', 'data-hmz': 'search-flow' })
  const places = h('select', { 'aria-label': 'Folder', 'data-hmz': 'search-workspace' }, h('option', { value: '' }, 'All folders'))
  const filters = h('div', { class: 'dialog-filters', id: 'search-filters', 'data-hmz': 'search-filters', hidden: !filtered(chosen) }, statuses, places, flows)
  const filtering = h('button', { class: 'search-filtering', type: 'button', 'aria-controls': 'search-filters', 'aria-expanded': String(!filters.hidden), 'data-hmz': 'search-filtering' }, icon('sliders'), 'Filters')
  const body = h('div', { class: 'dialog-body', id: 'search-found', 'data-hmz': 'found' }, h('p', { class: 'loading', role: 'status' }, 'Reading the list…'))
  const detail = h('div', { class: 'search-detail', 'data-hmz': 'search-detail' })
  const pages = h('div', { class: 'search-pages' })
  const foot = h(
    'div',
    { class: 'dialog-foot search-foot' },
    h('div', { class: 'search-hints', 'data-hmz': 'search-hints' }, HINTS.map(([does, keys]) => h('span', { class: 'search-hint' }, does, keys.map((key) => h('kbd', {}, key))))),
    pages,
  )
  workspaces().then((answer) => {
    fill(places, h('option', { value: '' }, 'All folders'), answer.workspaces.map((one) => h('option', { value: one.path, selected: one.path === chosen.workspace, title: one.path }, one.name)))
  }, () => {})
  root.classList.add('dialog-search-box')
  root.setAttribute('aria-label', 'Search')
  fill(
    root,
    // The top row of a narrow window, which it fills.
    dragged(h('div', { class: 'dialog-head' }, search, iconButton('close', 'Close', { onclick: shut })), 'deep', 'narrow'),
    h('div', { class: 'search-types', role: 'group', 'aria-label': 'Filters' }, tabs, filtering),
    filters,
    body,
    detail,
    foot,
  )

  // ---------------------------------------------------------------- what is moved to

  /** What was found and what can be done, in the order drawn: what the arrows move along. */
  const options = () => [...body.querySelectorAll('[role=option]')]
  /** Which one is moved to, by what it is, so that the list read again leaves it moved to. */
  let active = ''
  /** What there is to say of each epic found beyond its line, by its name. */
  let said = new Map()
  const point = (to, scroll = false) => {
    active = to?.dataset.key || ''
    for (const one of options()) {
      one.classList.toggle('active', one === to)
      one.setAttribute('aria-selected', String(one === to))
    }
    if (to) search.setAttribute('aria-activedescendant', to.id)
    else search.removeAttribute('aria-activedescendant')
    if (scroll) to?.scrollIntoView({ block: 'nearest' })
    fill(detail, said.get(active) || null)
  }
  /** One line of the list: moved to as the pointer comes over it, and opened as it is pressed. */
  const option = (el, key) => {
    el.setAttribute('role', 'option')
    el.id = `search-option-${key}`
    el.dataset.key = key
    el.tabIndex = -1
    el.addEventListener('pointermove', () => active === key || point(el))
    return el
  }

  // ---------------------------------------------------------------- what is asked for

  let stop = () => {}
  const watch = () => {
    stop()
    // What is listed stays, marked old, until what was asked for now is read.
    body.setAttribute('aria-busy', 'true')
    stays({ kind: chosen.kind, status: chosen.status, flow: chosen.flow, workspace: chosen.workspace, q: chosen.q, offset: chosen.offset || '' })
    tabbed()
    stop = poll('runs.list', given(asked(chosen)), 5000, draw)
  }
  const choose = (next) => {
    chosen = next
    flows.value = chosen.flow
    watch()
  }
  /** The tabs, drawn for the one chosen: only that one is in the order Tab goes by. */
  const tabbed = () =>
    fill(
      tabs,
      TABS.map(([kind, name]) => {
        const at = kind === chosen.kind
        return h('button', { type: 'button', role: 'tab', 'aria-selected': String(at), tabindex: at ? '0' : '-1', 'data-kind': kind || 'all', onclick: () => choose(onTab(chosen, kind)) }, name)
      }),
    )
  const unfold = (open) => {
    filters.hidden = !open
    filtering.setAttribute('aria-expanded', String(open))
  }
  filtering.addEventListener('click', () => unfold(filters.hidden))
  const again = settled(() => {
    chosen.offset = 0
    watch()
  }, 250)
  search.addEventListener('input', () => {
    chosen.q = search.value.trim()
    body.setAttribute('aria-busy', 'true')
    again()
  })
  places.addEventListener('change', () => choose({ ...chosen, workspace: places.value, offset: 0 }))
  flows.addEventListener('change', () => choose(onFlow(chosen, flows.value)))

  // The keys, wherever in the dialog the focus is: the arrows move along what was found and
  // Enter opens the one moved to. Left and right change the tab, and a slash opens the filters,
  // where they would do nothing else: in the field while it is empty, and on the tabs.
  root.addEventListener('keydown', (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.isComposing) return
    const inField = event.target === search
    const onTabs = tabs.contains(event.target)
    const all = options()
    const at = all.findIndex((one) => one.dataset.key === active)
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!inField && !onTabs && !body.contains(event.target)) return
      event.preventDefault()
      point(all[moved(at, all.length, event.key)], true)
    } else if (event.key === 'Enter' && inField) {
      event.preventDefault()
      all[at]?.click()
    } else if ((event.key === 'ArrowLeft' || event.key === 'ArrowRight') && ((inField && !search.value) || onTabs)) {
      event.preventDefault()
      const kind = turned(chosen.kind, event.key === 'ArrowLeft' ? -1 : 1)
      if (kind !== chosen.kind) choose(onTab(chosen, kind))
      if (onTabs) tabs.querySelector('[aria-selected=true]').focus()
    } else if (event.key === '/' && ((inField && !search.value) || onTabs)) {
      event.preventDefault()
      unfold(filters.hidden)
    }
  })

  // ---------------------------------------------------------------- what was found

  /** What is said of one epic over the foot while it is the one moved to. */
  const more = (run) =>
    h(
      'span',
      { class: 'result-meta' },
      badge(run.how),
      h('span', { class: 'mono', title: run.workspace }, nameOf(run.workspace)),
      run.flow ? h('span', { class: 'mono', title: run.flow }, flowName(run.flow)) : null,
      run.agents.map((one) => h('span', { class: 'chip', title: `${one.role} · ${one.runs}` }, one.name, h('span', { class: 'dim' }, one.runs.split(':')[0]))),
      h('span', { class: 'mono' }, run.spent ? `${run.spent.money || '—'} · ${run.spent.tokens} out` : '—'),
      run.ended ? h('span', { class: 'mono' }, `took ${lasting((Date.parse(run.ended) - Date.parse(run.began)) / 1000)}`) : null,
      h('span', { class: 'mono' }, `${run.sessions} session${run.sessions === 1 ? '' : 's'}`),
      run.resumable && !run.held && run.how !== 'running' && run.how !== 'done' ? h('span', { class: 'node-tag' }, 'Resumable') : null,
    )

  /** What can be done from Search, under what was found: a new chat, and an epic brought in. */
  const actions = () =>
    h(
      'div',
      { class: 'search-group', role: 'group', 'aria-label': 'Actions' },
      h('div', { class: 'search-heading', 'aria-hidden': 'true' }, 'Actions'),
      option(h('a', { class: 'search-action', href: hash('/new/chat'), 'data-hmz': 'search-new-chat' }, 'New chat'), 'new-chat'),
      option(h('button', { class: 'search-action', type: 'button', 'data-hmz': 'import', onclick: pick }, 'Import'), 'import'),
    )

  function draw(data, error) {
    body.removeAttribute('aria-busy')
    if (!data) {
      fill(body, error ? h('p', { class: 'error', role: 'alert' }, error.message) : h('p', { class: 'loading' }, 'Reading the list…'))
      return
    }
    const all = Object.values(data.counts).reduce((sum, one) => sum + one, 0)
    fill(
      statuses,
      [['', 'All', all], ...ENDINGS.map((how) => [how, how, data.counts[how] || 0])].map(([how, name, count]) =>
        h('button', { type: 'button', 'aria-pressed': String(chosen.status === how), onclick: () => choose({ ...chosen, status: how, offset: 0 }) }, name, h('span', { class: 'count' }, count)),
      ),
    )
    // A chat is of no flow: the tab `Chats` finds them, not this.
    const names = [...new Set([...data.flows, chosen.flow].filter((name) => name && name !== 'chat'))].sort()
    fill(flows, h('option', { value: '' }, 'All flows'), names.map((name) => h('option', { value: name, selected: name === chosen.flow }, name)))
    said = new Map(data.runs.map((run) => [run.name, more(run)]))
    fill(
      body,
      error ? h('p', { class: 'error', role: 'alert' }, error.message) : null,
      data.total
        ? h(
            'div',
            { class: 'search-group', role: 'group', 'aria-label': heading(chosen) },
            h('div', { class: 'search-heading' }, h('span', { 'aria-hidden': 'true' }, heading(chosen)), h('span', { 'data-hmz': 'search-count' }, paged(data))),
            h(
              'div',
              { class: 'results' },
              data.runs.map((run) =>
                menuOn(
                  option(
                    h(
                      'a',
                      { class: ['result', run.held && 'held'], href: hash(`/epics/${encodeURIComponent(run.name)}`), title: run.task, 'data-hmz': 'epic', 'data-kind': run.kind },
                      h('span', { class: 'result-task' }, headline(run.task)),
                      h('span', { class: 'result-how' }, run.how),
                      h('span', { class: 'result-where', title: run.workspace }, nameOf(run.workspace)),
                      h('span', { class: 'result-when', title: when(run.began) }, ago(run.began)),
                    ),
                    run.name,
                  ),
                  () => epicMenu(run),
                ),
              ),
            ),
          )
        : empty(narrowed(chosen) ? 'Nothing is like that.' : 'Nothing here yet.', narrowed(chosen) ? ' Clear the filters to see every chat and epic.' : ' Start a chat or an epic, and it is written down here as it goes.'),
      actions(),
    )
    body.setAttribute('role', 'listbox')
    body.setAttribute('aria-label', 'Found')
    // The one moved to stays so across a list read again; a list of others starts at its top.
    const found = options()
    point(found.find((one) => one.dataset.key === active) || found[0])
    const turn = (label, to, off) => h('button', { class: 'btn quiet small', type: 'button', disabled: off, onclick: () => choose({ ...chosen, offset: to }) }, label)
    fill(
      pages,
      data.total > data.runs.length ? [turn('Newer', Math.max(0, data.offset - PAGE), data.offset === 0), turn('Older', data.offset + PAGE, data.offset + data.runs.length >= data.total)] : null,
    )
  }

  watch()
  return () => stop()
}
