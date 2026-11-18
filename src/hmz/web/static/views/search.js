// Finding a chat or an epic, as Claude's window finds a session: a dialog over the page with the
// field at its top, under it a row of tabs -- everything, the chats, the epics -- then what was
// found, newest first, a line apiece, and a foot that says what the keys do. The arrows move
// along what was found and Enter opens it; what else there is to say of one -- its flow and
// agents, what it spent and how long it took -- is said in a line over the foot once a key or
// the pointer has moved to it, and under each where no pointer hovers or the window is narrow.
// The filters by how it went, by folder and by flow open under the tabs. The list `/epics` is in
// the terminal interface.

import { given, hash, poll } from '../api.js'
import { shut, stays } from '../app.js'
import { chatting, markOf } from '../epic.js'
import { nameOf, workspaces } from '../places.js'
import { epicMenu } from '../sidebar.js'
import { epicSaid, rowSaid } from '../sidebar-rows.js'
import { pick } from '../importing.js'
import { menuOf, menuOn } from '../ui.js'
import { dragged } from '../shell.js'
import { ago, flowName, empty, fill, h, headline, icon, iconButton, lasting, tone, when } from '../dom.js'
import { PAGE, TABS, asked, chosenOf, filtered, heading, hints, keyed, moved, nothing, onFlow, onTab, paged, turned } from '../search-model.js'

/** How a run can have ended, in the order the filter offers them. */
const ENDINGS = ['running', 'done', 'failed', 'stopped', 'unfinished']

export function mount(root, { query }) {
  let chosen = chosenOf(query)
  // A box that lists what it finds under it and names the one moved to: the focus stays in it.
  const search = h('input', {
    class: 'dialog-search',
    type: 'text',
    role: 'combobox',
    inputmode: 'search',
    enterkeyhint: 'go',
    placeholder: 'Search',
    value: chosen.q,
    'aria-label': 'Search',
    'aria-controls': 'search-list',
    'aria-expanded': 'true',
    'aria-autocomplete': 'list',
    autocomplete: 'off',
    spellcheck: 'false',
    autofocus: true,
  })
  /** What the pointer presses without the focus leaving the field, so that the keys go on. */
  const pressed = (el) => {
    el.addEventListener('mousedown', (event) => event.preventDefault())
    return el
  }
  const tabOf = new Map(TABS.map(([kind, name]) => [kind, h('button', { type: 'button', role: 'tab', 'data-kind': kind || 'all', onclick: () => choose(onTab(chosen, kind)) }, name)]))
  const tabs = pressed(h('div', { class: 'search-tabs', role: 'tablist', 'aria-label': 'Type', 'data-hmz': 'search-tabs' }, [...tabOf.values()]))
  const statusOf = new Map(
    [['', 'All'], ...ENDINGS.map((how) => [how, epicSaid(how)])].map(([how, name]) => {
      const count = h('span', { class: 'count' })
      return [how, { count, button: h('button', { type: 'button', 'data-how': how || 'all', onclick: () => choose({ ...chosen, status: how, offset: 0 }) }, name, count) }]
    }),
  )
  const statuses = pressed(h('div', { class: 'segmented', role: 'group', 'aria-label': 'How it went' }, [...statusOf.values()].map((one) => one.button)))
  const flows = h('select', { 'aria-label': 'Flow', 'data-hmz': 'search-flow' })
  const places = h('select', { 'aria-label': 'Folder', 'data-hmz': 'search-workspace' }, h('option', { value: '' }, 'All folders'))
  const filters = h('div', { class: 'dialog-filters', id: 'search-filters', 'data-hmz': 'search-filters', hidden: !filtered(chosen) }, statuses, places, flows)
  const filtering = pressed(h('button', { class: 'search-filtering', type: 'button', 'aria-controls': 'search-filters', 'aria-expanded': String(!filters.hidden), 'data-hmz': 'search-filtering' }, icon('sliders'), 'Filters'))
  const body = h('div', { class: 'dialog-body', 'data-hmz': 'found' }, h('p', { class: 'loading', role: 'status' }, 'Reading the list…'))
  const detail = h('div', { class: 'search-detail', 'data-hmz': 'search-detail' })
  const turn = (label, step) => h('button', { class: 'btn quiet small', type: 'button', onclick: () => choose({ ...chosen, offset: Math.max(0, chosen.offset + step * PAGE) }) }, label)
  const newer = turn('Newer', -1)
  const older = turn('Older', 1)
  const pages = pressed(h('div', { class: 'search-pages', hidden: true }, newer, older))
  // The keys, as this system writes them.
  const mac = /Mac|iPhone|iPad/.test(navigator.platform)
  const foot = h(
    'div',
    { class: 'dialog-foot search-foot' },
    h('div', { class: 'search-hints', 'data-hmz': 'search-hints' }, hints(mac).map(([does, keys]) => h('span', { class: 'search-hint' }, does, keys.map((key) => h('kbd', {}, key))))),
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
  /** Whether a key or the pointer moved to it: the first of a list drawn is only where they start. */
  let told = false
  /** The epics found, by their names. */
  let runs = new Map()
  const point = (to, { scroll = false, by = told } = {}) => {
    active = to?.dataset.key || ''
    told = Boolean(to) && by
    for (const one of options()) {
      one.classList.toggle('active', one === to)
      one.setAttribute('aria-selected', String(one === to))
    }
    if (to) search.setAttribute('aria-activedescendant', to.id)
    else search.removeAttribute('aria-activedescendant')
    // The line over the foot takes its room from the list, so the one moved to is looked for after.
    fill(detail, told && runs.has(active) ? more(runs.get(active)) : null)
    if (scroll) to?.scrollIntoView({ block: 'nearest' })
  }
  /** One line of the list: moved to as the pointer comes over it, and opened as it is pressed. */
  const option = (el, key) => {
    el.setAttribute('role', 'option')
    el.id = `search-option-${key}`
    el.dataset.key = key
    el.tabIndex = -1
    el.addEventListener('pointermove', (event) => (active === key && told) || event.pointerType === 'touch' || point(el, { by: true }))
    return el
  }

  // ---------------------------------------------------------------- what is asked for

  let stop = () => {}
  /** Whether Enter was pressed while the list was still of what was asked for before. */
  let opening = false
  /** What waits for the typing to pause before it asks. */
  let typing = 0
  const watch = () => {
    clearTimeout(typing)
    typing = 0
    stop()
    // What is listed stays, marked old, until what was asked for now is read.
    body.setAttribute('aria-busy', 'true')
    stays({ kind: chosen.kind, status: chosen.status, flow: chosen.flow, workspace: chosen.workspace, q: chosen.q, offset: chosen.offset || '' })
    marked()
    // A chat is of no flow: the filter by flow is offered where an epic can be found.
    flows.hidden = chosen.kind === 'chat'
    stop = poll('runs.list', given(asked(chosen)), 5000, draw)
  }
  const choose = (next) => {
    chosen = next
    opening = false
    flows.value = chosen.flow
    watch()
  }
  /**
   * The tabs and the filter by how it went, marked for what is chosen, each the element it was:
   * the one pressed keeps the focus. Only the tab chosen is in the order Tab goes by.
   */
  const marked = () => {
    for (const [kind, tab] of tabOf) {
      tab.setAttribute('aria-selected', String(kind === chosen.kind))
      tab.tabIndex = kind === chosen.kind ? 0 : -1
    }
    for (const [how, { button }] of statusOf) button.setAttribute('aria-pressed', String(how === chosen.status))
  }
  const unfold = (open) => {
    filters.hidden = !open
    filtering.setAttribute('aria-expanded', String(open))
  }
  filtering.addEventListener('click', () => unfold(filters.hidden))
  search.addEventListener('input', () => {
    chosen.q = search.value.trim()
    chosen.offset = 0
    opening = false
    // What is listed is of what was typed before: it is not read again, nor opened by Enter,
    // and what is found next starts at its top.
    stop()
    stop = () => {}
    body.setAttribute('aria-busy', 'true')
    active = ''
    told = false
    clearTimeout(typing)
    typing = setTimeout(watch, 250)
  })
  places.addEventListener('change', () => choose({ ...chosen, workspace: places.value, offset: 0 }))
  flows.addEventListener('change', () => choose(onFlow(chosen, flows.value)))

  // The keys, wherever in the dialog the focus is, and where it is nowhere: the arrows move along
  // what was found and Enter opens the one moved to. Left and right change the tab, and a slash
  // opens the filters, where they would do nothing else: in the field while it is empty, and on
  // the tabs.
  /** When the menu key was last pressed: the menu the browser has for the field is not opened. */
  let menued = 0
  const key = (event) => {
    if (event.isComposing || event.defaultPrevented) return
    const target = event.target
    if (target !== document.body && !root.contains(target)) return
    const where = target === search ? 'field' : tabs.contains(target) ? 'tabs' : target instanceof HTMLSelectElement ? 'select' : 'else'
    const does = keyed(event, where, !search.value)
    if (!does) return
    event.preventDefault()
    const all = options()
    const on = all.findIndex((one) => one.dataset.key === active)
    if (does === 'down' || does === 'up') {
      point(all[moved(on, all.length, does === 'down' ? 'ArrowDown' : 'ArrowUp')], { scroll: true, by: true })
    } else if (does === 'open') {
      // What was typed is opened, not what was listed before it: Enter waits for the list.
      if (body.hasAttribute('aria-busy')) {
        opening = true
        if (typing) watch()
      } else all[on]?.click()
    } else if (does === 'act') {
      // What can be done with the one moved to, under it; the focus comes back to the field.
      if (event.key !== 'Enter') menued = performance.now()
      if (all[on]) {
        all[on].scrollIntoView({ block: 'nearest' })
        menuOf(all[on], search)
      }
    } else if (does === 'left' || does === 'right') {
      const kind = turned(chosen.kind, does === 'left' ? -1 : 1)
      if (kind !== chosen.kind) choose(onTab(chosen, kind))
      if (where === 'tabs') tabOf.get(chosen.kind).focus()
    } else unfold(filters.hidden)
  }
  document.addEventListener('keydown', key)
  root.addEventListener('contextmenu', (event) => {
    if (performance.now() - menued > 500) return
    event.preventDefault()
    event.stopPropagation()
  })

  // ---------------------------------------------------------------- what was found

  /**
   * How one found stands, in the words the sidebar's row says it in: a chat's only where it goes,
   * asks or failed, a flow's epic's mark.
   */
  const stood = (run) => {
    const chat = chatting(run)
    const how = markOf(run.how, { chat, turn: run.turn, asked: run.asking || [], epic: run.name })
    return { how, said: rowSaid(how, chat) }
  }

  /** What else is said of one epic: over the foot while it is moved to, or under its own line. */
  const more = (run, { how, said } = stood(run)) =>
    h(
      'span',
      { class: 'result-meta' },
      said ? h('span', { class: `badge tone-${tone(how)}`, 'data-hmz': 'result-state' }, said) : null,
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
      opening = false
      fill(body, error ? h('p', { class: 'error', role: 'alert' }, error.message) : h('p', { class: 'loading' }, 'Reading the list…'))
      return
    }
    // How many went each way, of the tab's kind (Section 4.16.1.2 of protocol/daemon.md).
    const all = Object.values(data.counts).reduce((sum, one) => sum + one, 0)
    for (const [how, { count }] of statusOf) count.textContent = String(how ? data.counts[how] || 0 : all)
    // A chat is of no flow: the tab `Chats` finds them, not this.
    const names = [...new Set([...data.flows, chosen.flow].filter((name) => name && name !== 'chat'))].sort()
    fill(flows, h('option', { value: '' }, 'All flows'), names.map((name) => h('option', { value: name, selected: name === chosen.flow }, name)))
    runs = new Map(data.runs.map((run) => [run.name, run]))
    // Only what the arrows move along is in the list: what is said beside it stands over it.
    const list = h(
      'div',
      { class: 'search-list', id: 'search-list', role: 'listbox', 'aria-label': 'Found' },
      data.total
        ? h(
            'div',
            { class: 'search-group', role: 'group', 'aria-label': `${heading(chosen)}, ${paged(data)}` },
            h('div', { class: 'search-heading', 'aria-hidden': 'true' }, h('span', {}, heading(chosen)), h('span', { 'data-hmz': 'search-count' }, paged(data))),
            h(
              'div',
              { class: 'results', role: 'presentation' },
              data.runs.map((run) => {
                const standing = stood(run)
                return menuOn(
                  option(
                    h(
                      'a',
                      { class: ['result', run.held && 'held'], href: hash(`/epics/${encodeURIComponent(run.name)}`), title: run.task, 'data-hmz': 'epic', 'data-kind': run.kind },
                      h('span', { class: 'result-task' }, headline(run.task)),
                      standing.said ? h('span', { class: 'result-how', 'data-hmz': 'result-how' }, standing.said) : null,
                      h('span', { class: 'result-where', title: run.workspace }, nameOf(run.workspace)),
                      h('span', { class: 'result-when', title: when(run.began) }, ago(run.began)),
                      h('span', { class: 'result-more' }, more(run, standing)),
                    ),
                    run.name,
                  ),
                  () => epicMenu(run),
                )
              }),
            ),
          )
        : null,
      actions(),
    )
    fill(body, error ? h('p', { class: 'error', role: 'alert' }, error.message) : null, data.total ? null : empty(...nothing(chosen)), list)
    // The one moved to stays so across a list read again; a list of others starts at its top,
    // which nothing has moved to yet.
    const found = options()
    const same = found.find((one) => one.dataset.key === active)
    point(same || found[0], { by: Boolean(same) && told })
    pages.hidden = data.total <= data.runs.length
    newer.disabled = data.offset === 0
    older.disabled = data.offset + data.runs.length >= data.total
    // One of them pressed by a key until it could go no further gives the focus back.
    if (document.activeElement?.disabled && pages.contains(document.activeElement)) search.focus()
    if (opening) {
      opening = false
      found[0]?.click()
    }
  }

  watch()
  return () => {
    clearTimeout(typing)
    document.removeEventListener('keydown', key)
    stop()
  }
}
