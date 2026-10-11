// The page itself, laid out as Codex and Claude lay theirs out: the sidebar of every workspace's
// epics on the left, and whichever view the address names beside it -- a new epic, its graph, one session's
// thread, the flows -- with finding a run and the settings opened over it as dialogs. Routed
// by the address's fragment, so that every view of the page is an address that can be kept,
// shared or opened again, and the server serves one page for all of them.

import { get } from './api.js'
import { fill, h, problem } from './dom.js'
import { applyTheme, mountSidebar } from './sidebar.js'
import { kept, toggleSidebar } from './shell.js'

/** Every view, by the first part of the address that names it. */
const VIEWS = {
  new: () => import('./views/new.js'),
  live: () => import('./views/epic.js'),
  epics: () => import('./views/epic.js'),
  flows: () => import('./views/flows.js'),
}

/** Every dialog, opened over the view the page was on. */
const DIALOGS = {
  search: () => import('./views/search.js'),
  settings: () => import('./views/settings.js'),
}

const page = document.getElementById('page')
const overlay = document.querySelector('.overlay')
/** The view drawn, what it was loaded by, and how it is left or moved within. */
let mounted = null
let closing = null
let out = false
/** Which routing is the latest: one overtaken while its view was loading draws nothing. */
let routed = 0
/** The address of the view under a dialog, which closing the dialog goes back to. */
let behind = ''
/** What the view drawn was drawn for, so a dialog opened over it leaves it standing. */
let shown = ''

/** Where the page is: the parts of the address's path, and its query. */
export function where() {
  const raw = location.hash.replace(/^#/, '') || '/new'
  const url = new URL(raw.startsWith('/') ? raw : `/${raw}`, 'http://page')
  return { parts: url.pathname.split('/').filter(Boolean).map(decodeURIComponent), query: url.searchParams }
}

/** Goes to another view of the page. */
export function go(path) {
  location.hash = path
}

/** Puts the query of the view the page is on in the address, without a step in its history. */
export function stays(query) {
  const { parts } = where()
  const said = new URLSearchParams()
  for (const [name, value] of Object.entries(query)) if (value !== '' && value !== undefined && value !== null) said.set(name, value)
  const text = said.toString()
  history.replaceState(null, '', `#/${parts.map(encodeURIComponent).join('/')}${text ? `?${text}` : ''}`)
}

/** Closes the dialog open, going back to the view under it. */
export function shut() {
  go(behind || '/new')
}

async function route() {
  if (out) return
  const mine = ++routed
  const { parts, query } = where()
  const dialog = DIALOGS[parts[0]]
  if (dialog) {
    if (!shown) await view(mine, ['new'], new URLSearchParams(), '/new')
    if (mine !== routed) return
    return open(mine, dialog, parts, query)
  }
  close()
  behind = location.hash.replace(/^#/, '') || '/new'
  const key = `${parts.join('/')}?${query}`
  if (key === shown) return
  await view(mine, parts, query, key)
}

async function view(mine, parts, query, key) {
  const load = VIEWS[parts[0]] || VIEWS.new
  const named = VIEWS[parts[0]] ? parts : ['new']
  // A view that can move within itself -- a run's graph to one of its sessions -- does.
  if (mounted && mounted.load === load && mounted.moved && mounted.moved({ parts: named, query })) {
    shown = key
    return
  }
  if (mounted) mounted.leave()
  mounted = null
  try {
    const module = await load()
    if (mine !== routed && !DIALOGS[where().parts[0]]) return
    shown = key
    fill(page)
    const made = module.mount(page, { parts: named, query })
    mounted = typeof made === 'function' ? { load, leave: made } : { load, leave: () => {}, ...made }
  } catch (error) {
    fill(page, h('div', { class: 'view' }, problem(`This view failed to open: ${error.message}`)))
  }
}

async function open(mine, load, parts, query) {
  if (closing) closing()
  closing = null
  const dialog = h('div', { class: 'dialog', role: 'dialog', 'aria-modal': 'true', 'data-hmz': `dialog-${parts[0]}` })
  try {
    const module = await load()
    if (mine !== routed) return
    fill(overlay, h('div', { class: 'dialog-scrim', onclick: shut }), dialog)
    overlay.hidden = false
    document.body.classList.add('dialog-open')
    closing = module.mount(dialog, { parts, query }) || null
    dialog.querySelector('[autofocus], input, button, a')?.focus()
  } catch (error) {
    fill(overlay, h('div', { class: 'dialog-scrim', onclick: shut }), h('div', { class: 'dialog' }, problem(error)))
    overlay.hidden = false
  }
}

function close() {
  if (closing) closing()
  closing = null
  if (overlay.hidden) return
  overlay.hidden = true
  fill(overlay)
  document.body.classList.remove('dialog-open')
  page.focus({ preventScroll: true })
}

document.addEventListener('keydown', (event) => {
  const mod = event.metaKey || event.ctrlKey
  if (mod && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    go('/search')
  } else if (mod && event.shiftKey && event.key.toLowerCase() === 'o') {
    event.preventDefault()
    go('/new')
  } else if (mod && event.key === '.') {
    event.preventDefault()
    toggleSidebar()
  } else if (event.key === 'Escape' && !overlay.hidden) {
    shut()
  }
})

document.querySelector('.scrim').addEventListener('click', () => toggleSidebar(false))
if (kept('hmz-sidebar', '') === 'folded') document.querySelector('.app').classList.add('side-folded')

matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme)
window.addEventListener('storage', (event) => event.key === 'hmz-theme' && applyTheme())

window.addEventListener('hmz:out', () => {
  if (out) return
  out = true
  if (mounted) mounted.leave()
  close()
  fill(
    page,
    h(
      'div',
      { class: 'view' },
      h(
        'div',
        { class: 'empty' },
        h('strong', {}, 'This browser is not let in.'),
        'Open the address ',
        h('code', {}, 'hmz web'),
        ' printed when it started: it carries the key that lets a browser in.',
      ),
    ),
  )
})

window.addEventListener('hashchange', route)

get('/api/held')
  .then((context) => {
    document.title = `humanize · ${context.machine}`
    mountSidebar(document.getElementById('sidebar'), context, where)
    route()
  })
  .catch((error) => {
    if (!out) fill(page, h('div', { class: 'view' }, problem(error)))
  })
