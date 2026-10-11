// The sidebar, as Codex and Claude keep theirs: a new run, finding one, the flows, and every
// run of this directory newest first under the day it began -- each one opened out into its
// agents, and each agent into the sessions it opened. Under them, the directory, whether the
// runs are reached, and a menu of the colours, the settings and what the runs spent.

import { address, get, poll, refresh } from './api.js'
import { ago, fill, flowName, h, headline, icon, iconButton, when } from './dom.js'
import { current, follow } from './held.js'
import { sessionsOf } from './epic.js'
import { choice, keep, kept, menu, section, settleSidebar, toggleSidebar } from './shell.js'

/** How many runs a page of the list holds. */
const PAGE = 50

/** What a run ending each way is marked with in the list. */
const MARKS = { running: '●', stopping: '◐', done: '✔', failed: '✕', stopped: '■', budget: '■', refused: '✕', crashed: '✕', unfinished: '○' }

/**
 * @param {HTMLElement} root The sidebar.
 * @param {{workspace: string}} context What the server said this page is of.
 * @param {() => {parts: string[]}} where Where the page is.
 */
export function mountSidebar(root, context, where) {
  const list = h('nav', { class: 'side-runs', 'aria-label': 'Epics', 'data-hmz': 'epics' }, h('p', { class: 'side-quiet', role: 'status' }, 'Reading the epics…'))
  const more = h('button', { class: 'side-more', type: 'button', hidden: true }, 'Show more')
  const state = h('span', { class: 'side-state', 'data-hmz': 'state' })
  const named = context.workspace.split('/').filter(Boolean).pop() || context.workspace
  const account = h(
    'button',
    { class: 'side-account', type: 'button', 'data-hmz': 'workspace-menu' },
    h('span', { class: 'side-avatar', 'aria-hidden': 'true' }, named.slice(0, 1).toUpperCase()),
    h('span', { class: 'side-account-text' }, h('b', { title: context.workspace }, named), state),
  )
  menu(
    account,
    (close) => [
      section(context.workspace),
      ['system', 'light', 'dark'].map((one) => choice({ label: { system: 'Adaptive', light: 'Light', dark: 'Dark' }[one], chosen: themeChosen() === one, act: () => setTheme(one), close })),
      h('hr'),
      choice({ label: 'Settings', glyph: 'gear', href: '#/settings/general', close }),
      choice({ label: 'Usage', glyph: 'chart', href: '#/settings/usage', close }),
    ],
    { up: true, label: 'Workspace' },
  )
  fill(
    root,
    h(
      'div',
      { class: 'side-top' },
      h('a', { class: 'brand', href: '#/new', 'aria-label': 'humanize, a new epic' }, h('img', { src: '/mark.svg', alt: '', width: '24', height: '24' }), h('strong', {}, 'humanize')),
      iconButton('sidebar', 'Hide sidebar', { class: 'side-fold', onclick: () => toggleSidebar(false), 'aria-controls': 'sidebar' }),
    ),
    h(
      'div',
      { class: 'side-nav' },
      h('a', { href: '#/new', 'data-nav': 'new' }, icon('new'), h('span', {}, 'New epic'), h('kbd', {}, '⇧⌘O')),
      h('a', { href: '#/search', 'data-nav': 'search' }, icon('search'), h('span', {}, 'Search epics'), h('kbd', {}, '⌘K')),
      h('a', { href: '#/flows', 'data-nav': 'flows' }, icon('flows'), h('span', {}, 'Flows')),
    ),
    h('div', { class: 'side-scroll' }, list, more),
    h('div', { class: 'side-foot' }, account),
  )
  root.addEventListener('click', (event) => {
    if (event.target.closest('a[href]')) settleSidebar()
  })

  let limit = PAGE
  let data = null
  let held = null
  /** Which runs are opened out, by name, as this browser last left them. */
  const opened = new Set(JSON.parse(kept('hmz-opened', '[]') || '[]'))
  /** Which runs were folded here, the one in front among them. */
  const folded = new Set()
  /** Each run written down that was opened out, as its epic says it, with how it stood when read. */
  const details = new Map()

  more.addEventListener('click', () => {
    limit += PAGE
    watch()
  })

  let stop = () => {}
  const watch = () => {
    stop()
    stop = poll(address('/api/runs', { limit }), 5000, (answer, error) => {
      if (answer) data = answer
      if (!data) fill(list, h('p', { class: 'error', role: 'alert' }, error ? error.message : 'Reading the epics…'))
      else draw()
    })
  }

  function draw() {
    const { parts } = where()
    const here = parts[0] === 'epics' ? parts[1] : ''
    for (const link of root.querySelectorAll('.side-nav a')) {
      if (link.dataset.nav === parts[0] || (link.dataset.nav === 'new' && (!parts[0] || parts[0] === 'new'))) link.setAttribute('aria-current', 'page')
      else link.removeAttribute('aria-current')
    }
    if (!data.runs.length) {
      fill(list, h('p', { class: 'side-quiet' }, 'No epic here yet.'))
      more.hidden = true
      return
    }
    const groups = new Map()
    for (const run of data.runs) {
      const day = dayOf(run.began)
      if (!groups.has(day)) groups.set(day, [])
      groups.get(day).push(run)
    }
    const scrolled = list.parentElement.scrollTop
    fill(
      list,
      [...groups].map(([day, runs]) =>
        h('section', { class: 'side-group' }, h('h2', { class: 'side-day' }, day), h('ul', { role: 'list' }, runs.map((run) => item(run, here, parts)))),
      ),
    )
    list.parentElement.scrollTop = scrolled
    more.hidden = data.runs.length >= data.total
  }

  function item(run, here, parts) {
    const shown = (opened.has(run.name) || run.name === here) && !folded.has(run.name)
    const link = `#/epics/${encodeURIComponent(run.name)}`
    const toggle = h(
      'button',
      { class: 'side-toggle', type: 'button', 'aria-expanded': String(shown), 'aria-label': shown ? 'Collapse' : 'Expand' },
      icon('chevron'),
    )
    toggle.addEventListener('click', () => {
      if (shown) {
        opened.delete(run.name)
        folded.add(run.name)
      } else {
        opened.add(run.name)
        folded.delete(run.name)
      }
      keep('hmz-opened', JSON.stringify([...opened].slice(-40)))
      draw()
      // The list was drawn again: the toggle pressed is the one that keeps the focus.
      for (const one of list.querySelectorAll('.side-item')) if (one.dataset.epic === run.name) one.querySelector('.side-toggle').focus()
    })
    const how = run.how
    const row = h(
      'div',
      { class: ['side-run', run.name === here && !parts[2] && 'current', run.held && 'held'] },
      toggle,
      h(
        'a',
        { href: link, 'aria-current': run.name === here && !parts[2] ? 'page' : null, title: `${run.task}\n${flowName(run.flow)} · ${how} · ${when(run.began)}`, 'data-hmz': 'epic' },
        h('span', { class: ['side-mark', `tone-${tone(how)}`], 'aria-label': how }, MARKS[how] || '·'),
        h('span', { class: 'side-label' }, headline(run.task)),
        h('span', { class: 'side-meta' }, run.held ? h('span', { class: 'pill-live' }, 'live') : ago(run.began)),
      ),
    )
    return h('li', { class: 'side-item', 'data-epic': run.name }, row, shown ? tree(run, here, parts) : null)
  }

  /** What a run opened out holds: its agents, each with the sessions it opened. */
  function tree(run, here, parts) {
    let agents
    if (run.held && held) {
      const { records } = current(held)
      const working = new Set(((held.figures && held.figures.sessions) || []).filter((one) => one.working).map((one) => one.name))
      const sessions = records.filter((one) => one.type === 'opened' && !one.person)
      agents = run.agents.map((one) => ({ role: one.role, runs: one.runs, sessions: sessions.filter((session) => session.role === one.role).map((session) => ({ key: session.key, working: working.has(session.key) })) }))
      for (const session of sessions) {
        if (!agents.some((one) => one.role === session.role)) agents.push({ role: session.role, runs: session.cli, sessions: [{ key: session.key, working: working.has(session.key) }] })
      }
    } else {
      const read = details.get(run.name)
      if (!read || read.how !== run.how) {
        if (!read || !read.asking) {
          details.set(run.name, { how: run.how, asking: true, detail: read && read.detail })
          get(`/api/runs/${encodeURIComponent(run.name)}`).then(
            (detail) => {
              details.set(run.name, { how: run.how, detail })
              draw()
            },
            () => details.set(run.name, { how: run.how, detail: null, failed: true }),
          )
        }
      }
      const detail = details.get(run.name).detail
      const sessions = detail ? sessionsOf(detail) : []
      agents = run.agents.map((one) => ({ role: one.role, runs: one.runs, sessions: sessions.filter((session) => session.role === one.role).map((session) => ({ key: session.key, working: false })) }))
    }
    if (!agents.length) return h('p', { class: 'side-quiet nested' }, 'No agent yet.')
    const base = `#/epics/${encodeURIComponent(run.name)}`
    return h(
      'ul',
      { class: 'side-tree', role: 'list' },
      agents.map((agent) => {
        const at = run.name === here && parts[2] === 'agents' && parts[3] === agent.role
        return h(
          'li',
          {},
          h(
            'a',
            { class: ['side-agent', at && 'current'], href: `${base}/agents/${encodeURIComponent(agent.role)}`, 'aria-current': at ? 'page' : null, title: agent.runs, 'data-hmz': 'agent' },
            icon('agent'),
            h('span', { class: 'side-label' }, agent.role),
            h('span', { class: 'side-meta mono' }, agent.runs.split('/')[0]),
          ),
          agent.sessions.length
            ? h(
                'ul',
                { role: 'list' },
                agent.sessions.map((session) => {
                  const on = run.name === here && parts[2] === 'sessions' && parts[3] === session.key
                  return h(
                    'li',
                    {},
                    h(
                      'a',
                      { class: ['side-session', on && 'current', session.working && 'working'], href: `${base}/sessions/${encodeURIComponent(session.key)}`, 'aria-current': on ? 'page' : null, 'data-hmz': 'session' },
                      h('span', { class: 'side-mark', 'aria-hidden': 'true' }, session.working ? '●' : '○'),
                      h('span', { class: 'side-label mono' }, session.key),
                    ),
                  )
                }),
              )
            : null,
        )
      }),
    )
  }

  watch()
  // A run starting or ending here is a row changing: read the list again as it does, and the
  // run going's sessions as they open.
  let was = ''
  let sessions = 0
  let working = ''
  follow((state) => {
    held = state
    drawState(state)
    const now = state.standing.run ? state.standing.run.state : ''
    if (was && now !== was) refresh('/api/runs')
    was = now
    const opening = current(state).records.filter((one) => one.type === 'opened').length
    const busy = JSON.stringify(((state.figures && state.figures.sessions) || []).map((one) => one.working))
    if (data && (opening !== sessions || busy !== working)) draw()
    sessions = opening
    working = busy
  })
  window.addEventListener('hashchange', () => data && draw())

  function drawState(seen) {
    const run = seen.standing.run
    let dot = 'gone'
    let said = seen.gone || 'reaching the host'
    if (seen.connected && run) {
      dot = run.state === 'idle' ? '' : 'live'
      said = run.state === 'idle' ? 'no epic going' : `${run.state === 'stopping' ? 'stopping' : 'live'} · ${run.flow || 'a flow'}`
    } else if (!seen.gone) dot = 'waiting'
    fill(state, h('span', { class: ['dot', dot], 'aria-hidden': 'true' }), said)
  }
}

/** The heading a run is listed under: the day it began, as somebody says it. */
function dayOf(stamp) {
  const at = new Date(stamp)
  if (Number.isNaN(at.getTime())) return 'Undated'
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Math.floor((today - new Date(at.getFullYear(), at.getMonth(), at.getDate())) / 86400000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return 'Previous 7 days'
  if (days < 30) return 'Previous 30 days'
  return at.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

function tone(how) {
  return { stopping: 'running', budget: 'stopped', refused: 'failed', crashed: 'failed' }[how] || how
}

export function themeChosen() {
  return kept('hmz-theme', null) || 'system'
}

export function setTheme(chosen) {
  keep('hmz-theme', chosen === 'system' ? null : chosen)
  applyTheme()
}

export function applyTheme() {
  const chosen = themeChosen()
  const dark = chosen === 'system' ? matchMedia('(prefers-color-scheme: dark)').matches : chosen === 'dark'
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}
