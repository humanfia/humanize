// The sidebar, as Codex and Claude keep theirs: a new epic, finding one, the flows, and every
// workspace of this machine as a folder of its epics, newest first -- each epic opened out into
// its agents, and each agent into the sessions it opened. Under them, the machine, how many
// epics are going on it, and a menu of the settings and what the epics spent.

import { address, get, poll, post, refresh } from './api.js'
import { ask } from './held.js'
import { pick } from './importing.js'
import { copy, menuOn, toast } from './ui.js'
import { ago, fill, flowName, h, headline, icon, iconButton, when } from './dom.js'
import { sessionsOf } from './epic.js'
import { nameOf } from './places.js'
import { choice, dragged, keep, kept, menu, section, settleSidebar, toggleSidebar } from './shell.js'

/** How many epics a page of the list holds. */
const PAGE = 60

/** What an epic ending each way is marked with in the list. */
const MARKS = { running: '●', stopping: '◐', done: '✔', failed: '✕', stopped: '■', budget: '■', refused: '✕', crashed: '✕', unfinished: '○' }

/**
 * @param {HTMLElement} root The sidebar.
 * @param {{machine: string, here: string, newer: string}} context What the server said this page is of.
 * @param {() => {parts: string[], query: URLSearchParams}} where Where the page is.
 */
export function mountSidebar(root, context, where) {
  const list = h('nav', { class: 'side-runs', 'aria-label': 'Epics', 'data-hmz': 'epics' }, h('p', { class: 'side-quiet', role: 'status' }, 'Reading the epics…'))
  const more = h('button', { class: 'side-more', type: 'button', hidden: true }, 'Show more')
  const state = h('span', { class: 'side-state', 'data-hmz': 'state' })
  // How many installed flows have a newer release, as the indexes were fetched as it started.
  const updates = h('span', { class: 'side-badge', 'data-hmz': 'updates', hidden: true })
  poll('/api/flowverses', 60000, (answer) => {
    const count = answer ? answer.updates.length : 0
    updates.hidden = !count
    updates.textContent = String(count)
    updates.title = count ? `${count} flow${count === 1 ? ' has' : 's have'} a newer release` : ''
  })
  const account = h(
    'button',
    { class: 'side-account', type: 'button', 'data-hmz': 'machine-menu' },
    h('span', { class: 'side-avatar', 'aria-hidden': 'true' }, (context.machine || 'h').slice(0, 1).toUpperCase()),
    h('span', { class: 'side-account-text' }, h('b', {}, context.machine || 'This machine'), state),
    // A newer release of humanize, as PyPI said when it was last asked.
    context.newer ? h('span', { class: 'side-badge', 'data-hmz': 'newer', title: `hmz ${context.newer} is out` }, '↑') : null,
  )
  menu(
    account,
    (close) => [
      context.newer ? choice({ label: 'Update', about: `hmz ${context.newer}`, glyph: 'up', act: () => copy('hmz update', 'Copied hmz update'), close }) : null,
      choice({ label: 'Import', glyph: 'file', act: pick, close }),
      choice({ label: 'Settings', glyph: 'gear', href: '#/settings/general', close }),
      choice({ label: 'Usage', glyph: 'chart', href: '#/settings/usage', close }),
    ],
    { up: true, label: 'Machine' },
  )
  fill(
    root,
    dragged(
      h(
        'div',
        { class: 'side-top' },
        h('a', { class: 'brand', href: '#/new', 'aria-label': 'humanize, a new epic' }, h('img', { src: '/mark.svg', alt: '', width: '24', height: '24' }), h('strong', {}, 'humanize')),
        iconButton('sidebar', 'Hide sidebar', { class: 'side-fold', onclick: () => toggleSidebar(false), 'aria-controls': 'sidebar' }),
      ),
    ),
    h(
      'div',
      { class: 'side-nav' },
      h('a', { href: '#/new', 'data-nav': 'new' }, icon('new'), h('span', {}, 'New epic'), h('kbd', {}, '⇧⌘O')),
      h('a', { href: '#/search', 'data-nav': 'search' }, icon('search'), h('span', {}, 'Search epics'), h('kbd', {}, '⌘K')),
      h('a', { href: '#/flows', 'data-nav': 'flows' }, icon('flows'), h('span', {}, 'Flows'), updates),
    ),
    h('div', { class: 'side-scroll' }, list, more),
    h('div', { class: 'side-foot' }, account),
  )
  // The band across its top, above the row.
  dragged(root, '')
  // What is offered between the epics, rather than on one of them.
  menuOn(list, () => [{ label: 'Import', glyph: 'file', act: pick }])
  root.addEventListener('click', (event) => {
    if (event.target.closest('a[href]')) settleSidebar()
  })

  let limit = PAGE
  let data = null
  let places = null
  /** Which epics are opened out, by name, as this browser last left them. */
  const opened = new Set(JSON.parse(kept('hmz-opened', '[]') || '[]'))
  /** Which epics were folded here, the one in front among them. */
  const folded = new Set()
  /** Which workspaces are folded away, by path, as this browser last left them. */
  const shut = new Set(JSON.parse(kept('hmz-shut', '[]') || '[]'))
  /** Each epic opened out, as its epic says it, with how it stood when read. */
  const details = new Map()

  more.addEventListener('click', () => {
    limit += PAGE
    watch()
  })

  let stop = () => {}
  const watch = () => {
    stop()
    stop = poll(address('/api/runs', { limit }), 4000, (answer, error) => {
      if (answer) data = answer
      if (!data) fill(list, h('p', { class: 'error', role: 'alert' }, error ? error.message : 'Reading the epics…'))
      else draw()
    })
  }
  poll('/api/workspaces', 10000, (answer) => {
    if (!answer) return
    places = answer
    if (data) draw()
  })

  function draw() {
    const { parts, query } = where()
    const here = parts[0] === 'epics' ? parts[1] : ''
    for (const link of root.querySelectorAll('.side-nav a')) {
      if (link.dataset.nav === parts[0] || (link.dataset.nav === 'new' && (!parts[0] || parts[0] === 'new'))) link.setAttribute('aria-current', 'page')
      else link.removeAttribute('aria-current')
    }
    const going = data.runs.filter((one) => one.held).length
    fill(state, h('span', { class: ['dot', going && 'live'], 'aria-hidden': 'true' }), going ? `${going} live` : 'idle')
    // Every workspace offered, each with its epics: those going first, then the latest.
    const groups = new Map()
    for (const one of places ? places.workspaces : []) groups.set(one.path, { path: one.path, runs: [] })
    for (const run of data.runs) {
      if (!groups.has(run.workspace)) groups.set(run.workspace, { path: run.workspace, runs: [] })
      groups.get(run.workspace).runs.push(run)
    }
    const order = [...groups.values()].sort((a, b) => rank(b) - rank(a))
    const scrolled = list.parentElement.scrollTop
    const chosen = parts[0] === 'new' ? query.get('workspace') || '' : ''
    fill(
      list,
      order.map((group) => {
        const open = !shut.has(group.path)
        const toggle = h('button', { class: 'side-toggle', type: 'button', 'aria-expanded': String(open), 'aria-label': open ? 'Collapse' : 'Expand' }, icon('chevron'))
        toggle.addEventListener('click', () => {
          if (open) shut.add(group.path)
          else shut.delete(group.path)
          keep('hmz-shut', JSON.stringify([...shut].slice(-60)))
          draw()
        })
        const folder = h(
            'div',
            { class: ['side-folder', chosen === group.path && 'current'] },
            toggle,
            h('span', { class: 'side-folder-name', title: group.path }, icon('folder'), h('span', { class: 'side-label' }, nameOf(group.path))),
            iconButton('plus', `New epic in ${nameOf(group.path)}`, { class: 'side-add', onclick: () => (location.hash = `/new?workspace=${encodeURIComponent(group.path)}`) }),
          )
        const where = encodeURIComponent(group.path)
        menuOn(folder, () => [
          { head: group.path },
          { label: 'New epic here', glyph: 'new', href: `#/new?workspace=${where}` },
          { label: 'Flows here', glyph: 'flows', href: `#/flows?workspace=${where}` },
          { label: 'Search here', glyph: 'search', href: `#/search?workspace=${where}` },
          '-',
          { label: 'Copy path', glyph: 'copy', act: () => copy(group.path, 'Path copied') },
          { label: open ? 'Collapse' : 'Expand', glyph: 'chevron', act: () => toggle.click() },
          '-',
          { label: 'Settings', glyph: 'gear', href: `#/settings/workspace?workspace=${where}` },
          { label: 'Usage', glyph: 'chart', href: `#/settings/usage?workspace=${where}` },
          group.runs.length ? null : { label: 'Forget', danger: true, act: () => forget(group.path) },
        ])
        return h(
          'section',
          { class: 'side-group', 'data-hmz': 'workspace', 'data-path': group.path },
          folder,
          open ? (group.runs.length ? h('ul', { role: 'list' }, group.runs.map((run) => item(run, here, parts))) : h('p', { class: 'side-quiet nested' }, 'No epics')) : null,
        )
      }),
    )
    list.parentElement.scrollTop = scrolled
    more.hidden = data.runs.length >= data.total
  }

  function rank(group) {
    const live = group.runs.some((one) => one.held) ? 1e13 : 0
    const last = group.runs.length ? Date.parse(group.runs[0].began) || 0 : 0
    return live + last
  }

  function item(run, here, parts) {
    const shown = (opened.has(run.name) || run.name === here) && !folded.has(run.name)
    const link = `#/epics/${encodeURIComponent(run.name)}`
    const toggle = h('button', { class: 'side-toggle', type: 'button', 'aria-expanded': String(shown), 'aria-label': shown ? 'Collapse' : 'Expand' }, icon('chevron'))
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
    menuOn(row, () => epicMenu(run))
    return h('li', { class: 'side-item', 'data-epic': run.name }, row, shown ? tree(run, here, parts) : null)
  }

  /** What an epic opened out holds: its agents, each with the sessions it opened. */
  function tree(run, here, parts) {
    // Read again while it goes, as its sessions open; once, once it has ended.
    const read = details.get(run.name)
    const stale = !read || read.how !== run.how || (run.held && Date.now() - read.at > 3000)
    if (stale && !(read && read.asking)) {
      details.set(run.name, { ...(read || {}), asking: true })
      get(`/api/runs/${encodeURIComponent(run.name)}`).then(
        (detail) => {
          details.set(run.name, { how: run.how, at: Date.now(), detail })
          draw()
        },
        () => details.set(run.name, { how: run.how, at: Date.now(), detail: null }),
      )
    }
    const detail = read && read.detail
    const sessions = detail ? sessionsOf(detail) : []
    const agents = run.agents.map((one) => ({ role: one.role, runs: one.runs, sessions: sessions.filter((session) => session.role === one.role) }))
    if (!agents.length) return h('p', { class: 'side-quiet nested' }, 'No agents')
    const base = `#/epics/${encodeURIComponent(run.name)}`
    const logged = run.name === here && parts[2] === 'logs' && !parts[3]
    const mythed = run.name === here && parts[2] === 'exomyth'
    return h(
      'ul',
      { class: 'side-tree', role: 'list' },
      h(
        'li',
        {},
        menuOn(h('a', { class: ['side-agent', logged && 'current'], href: `${base}/logs`, 'aria-current': logged ? 'page' : null, 'data-hmz': 'log' }, icon('thread'), h('span', { class: 'side-label' }, 'Log')), () => [
          { label: 'Open', glyph: 'open', href: `${base}/logs` },
          { label: 'Copy link', glyph: 'link', act: () => copy(`${location.origin}/${base}/logs`, 'Link copied') },
        ]),
      ),
      h(
        'li',
        {},
        menuOn(h('a', { class: ['side-agent', mythed && 'current'], href: `${base}/exomyth`, 'aria-current': mythed ? 'page' : null, 'data-hmz': 'exomyth-link' }, icon('chart'), h('span', { class: 'side-label' }, 'Exomyth')), () => [
          { label: 'Open', glyph: 'open', href: `${base}/exomyth` },
          { label: 'Copy link', glyph: 'link', act: () => copy(`${location.origin}/${base}/exomyth`, 'Link copied') },
        ]),
      ),
      agents.map((agent) => {
        const at = run.name === here && parts[2] === 'agents' && parts[3] === agent.role
        return h(
          'li',
          {},
          menuOn(
            h(
              'a',
              { class: ['side-agent', at && 'current'], href: `${base}/agents/${encodeURIComponent(agent.role)}`, 'aria-current': at ? 'page' : null, title: agent.runs, 'data-hmz': 'agent' },
              icon('agent'),
              h('span', { class: 'side-label' }, agent.role),
              h('span', { class: 'side-meta mono' }, agent.runs.split('/')[0]),
            ),
            () => [
              { head: agent.runs },
              { label: 'Show on graph', glyph: 'flows', href: `${base}/agents/${encodeURIComponent(agent.role)}` },
              { label: 'Open log', glyph: 'thread', href: `${base}/logs/${encodeURIComponent(agent.role)}` },
              '-',
              { label: 'Copy agent', glyph: 'copy', act: () => copy(agent.runs, 'Agent copied') },
            ],
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
                    menuOn(
                      h(
                        'a',
                        { class: ['side-session', on && 'current'], href: `${base}/sessions/${encodeURIComponent(session.key)}`, 'aria-current': on ? 'page' : null, title: session.ident ? `${session.key} · ${session.backend} ${session.ident}` : session.key, 'data-hmz': 'session' },
                        h('span', { class: 'side-mark', 'aria-hidden': 'true' }, '○'),
                        h('span', { class: 'side-label mono' }, session.key),
                      ),
                      () => [
                        { head: session.ident ? `${session.backend} ${session.ident}` : session.key },
                        { label: 'Open', glyph: 'open', href: `${base}/sessions/${encodeURIComponent(session.key)}` },
                        { label: 'Copy link', glyph: 'link', act: () => copy(`${location.origin}/${base}/sessions/${encodeURIComponent(session.key)}`, 'Link copied') },
                        session.ident ? { label: 'Copy session ID', glyph: 'copy', act: () => copy(session.ident, 'Session ID copied') } : null,
                      ],
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
  window.addEventListener('hashchange', () => data && draw())
}

/** What can be done to one epic, from wherever it is listed. */
export function epicMenu(run) {
  const base = `#/epics/${encodeURIComponent(run.name)}`
  const resumes = run.resumable && !run.held && run.how !== 'done'
  return [
    { head: run.task.split('\n')[0] },
    { label: 'Open', glyph: 'open', href: base },
    { label: 'Open log', glyph: 'thread', href: `${base}/logs` },
    { label: 'Exomyth', glyph: 'chart', href: `${base}/exomyth` },
    resumes ? { label: 'Resume', glyph: 'resume', href: `#/new?flow=${encodeURIComponent(run.flow)}&resume=${encodeURIComponent(run.name)}&workspace=${encodeURIComponent(run.workspace)}` } : null,
    { label: 'New epic like it', glyph: 'new', href: `#/new?flow=${encodeURIComponent(run.flow)}&workspace=${encodeURIComponent(run.workspace)}` },
    '-',
    { label: 'Copy link', glyph: 'link', act: () => copy(`${location.origin}/${base}`, 'Link copied') },
    { label: 'Copy task', glyph: 'copy', act: () => copy(run.task, 'Task copied') },
    { label: 'Copy name', glyph: 'copy', act: () => copy(run.name, 'Name copied') },
    run.held ? null : { label: 'Export', glyph: 'download', act: () => (location.href = `/api/runs/${encodeURIComponent(run.name)}/bundle`) },
    { label: 'Upload', glyph: 'up', title: backedSaid(run.backed), act: () => upload(run.name) },
    run.held ? '-' : null,
    run.held ? { label: 'Stop', glyph: 'stop', danger: true, act: () => ask(run.workspace, 'stop').then(() => toast('Stopping'), (error) => toast(error.message)) } : null,
  ]
}

/** Backs an epic up to its targets now, behind the page: how it went is read as the epic is. */
export function upload(name) {
  post(`/api/runs/${encodeURIComponent(name)}/backup`, {}).then((answer) => toast(`Uploading to ${answer.queued.join(', ')}`), (error) => toast(error.message))
}

/** How an epic's last backup to each target went, each in turn, or '' where it has none. */
export function backedSaid(backed) {
  return Object.entries(backed || {})
    .map(([name, one]) => `${name}: ${one.ok ? 'uploaded' : `failed, ${one.error}`} ${when(one.at)}`)
    .join(' · ')
}

/** Forgets a workspace nothing ran in, which takes it out of the list. */
function forget(path) {
  post('/api/workspaces/forget', { workspace: path }).then(() => {
    refresh('/api/workspaces')
    toast('Forgotten')
  }, (error) => toast(error.message))
}

function tone(how) {
  return { stopping: 'running', budget: 'stopped', refused: 'failed', crashed: 'failed' }[how] || how
}
