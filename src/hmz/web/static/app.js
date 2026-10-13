// The page itself, laid out as Codex and Claude lay theirs out: the sidebar of every workspace's
// epics on the left, and whichever view the address names beside it -- a new epic, its graph, one session's
// thread, the flows -- with finding a run and the settings opened over it as dialogs. Routed
// by the address's fragment, so that every view of the page is an address that can be kept,
// shared or opened again, and the server serves one page for all of them. An address names the
// daemon it is of first, `#/@<name>/<view>…`, or names none and is of Local.

import { daemon, get, hash } from './api.js'
import { fill, h, problem } from './dom.js'
import { mountSidebar } from './sidebar.js'
import { dragged, kept, toggleSidebar } from './shell.js'
import { paint } from './themes.js'
import './ui.js'
import './importing.js'

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
  download: () => import('./views/download.js'),
  settings: () => import('./views/settings.js'),
}

// The strip kept across its top for the window's traffic lights moves the window, as a title bar.
const page = dragged(document.getElementById('page'), '')
const overlay = document.querySelector('.overlay')
/** The view drawn, what it was loaded by, and how it is left or moved within. */
let mounted = null
let closing = null
let out = false
/** Which routing is the latest: one overtaken while its view was loading draws nothing. */
let routed = 0
/** The address routed last, as the view drawn for it has since said it. */
let routedTo = ''
/** How many routings are still drawing. */
let drawing = 0
/** The address of the view under a dialog, which closing the dialog goes back to. */
let behind = ''
/** What the view drawn was drawn for, so a dialog opened over it leaves it standing. */
let shown = ''

/** Where the page is: the parts of the address's path, after the daemon it names, and its query. */
export function where() {
  const raw = location.hash.replace(/^#/, '').replace(/^\/?@[^/?]*/, '') || '/new'
  const url = new URL(raw.startsWith('/') ? raw : `/${raw}`, 'http://page')
  return { parts: url.pathname.split('/').filter(Boolean).map(decodeURIComponent), query: url.searchParams }
}

/** Goes to another view of the page, on the daemon it is on. */
export function go(path) {
  location.hash = hash(path)
}

/** Puts the query of the view the page is on in the address, without a step in its history. */
export function stays(query) {
  // An address not routed yet is the next view's: a view finishing what it read in that moment
  // would otherwise put its own query into it, and the next view would open on that.
  if (location.hash !== routedTo) return
  const { parts } = where()
  // Only into the address of what is drawn: one gone on to, not drawn yet, is not its to say.
  const here = parts.join('/')
  if (here !== shown.split('?')[0] && here !== opened) return
  const said = new URLSearchParams()
  for (const [name, value] of Object.entries(query)) if (value !== '' && value !== undefined && value !== null) said.set(name, value)
  const text = said.toString()
  history.replaceState(null, '', hash(`/${parts.map(encodeURIComponent).join('/')}${text ? `?${text}` : ''}`))
  routedTo = location.hash
}

/** Whether the address names a dialog, over the view drawn: what that view does is not to say. */
export function covered() {
  return Boolean(DIALOGS[where().parts[0]])
}

/** Closes the dialog open, going back to the view under it. */
export function shut() {
  go(behind || '/new')
}

async function route() {
  if (out) return
  const mine = ++routed
  routedTo = location.hash
  // Busy until every address asked for is drawn: the view left stands until then, and is not
  // what the address names.
  drawing++
  page.setAttribute('aria-busy', 'true')
  try {
    await routing(mine)
  } finally {
    if (--drawing === 0) page.removeAttribute('aria-busy')
  }
}

async function routing(mine) {
  const { parts, query } = where()
  // An epic's log of every session is no more: its old address opens the epic, in its place.
  if (parts[0] === 'epics' && parts[2] === 'logs' && !parts[3]) return location.replace(location.hash.replace(/\/logs\/?(?=$|\?)/, ''))
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

/** An epic read back in by its path: an address under `epics` no epic is named. */
const IMPORT = () => import('./views/import.js')

async function view(mine, parts, query, key) {
  const load = parts[0] === 'epics' && parts[1] === 'import' && parts.length === 2 ? IMPORT : VIEWS[parts[0]] || VIEWS.new
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
    // Said where it happened, and to the console, where whoever is debugging the page looks.
    console.error(error)
    fill(page, h('div', { class: 'view' }, problem(`This view failed to open: ${error.message}`)))
  }
}

/** Which dialog is open, as the address named it: one asked for again is left as it is. */
let opened = ''

async function open(mine, load, parts, query) {
  // The same dialog, asked for again -- the address said once more, or a view under it putting
  // its own query in -- is not drawn again over whatever is being typed into it.
  const asked = parts.join('/')
  if (asked === opened && !overlay.hidden) return
  opened = asked
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
    console.error(error)
    fill(overlay, h('div', { class: 'dialog-scrim', onclick: shut }), h('div', { class: 'dialog' }, problem(error)))
    overlay.hidden = false
  }
}

function close() {
  opened = ''
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

// The chosen theme's pictures, after its colours, which theme.js painted before the page was.
paint()

window.addEventListener('hmz:out', () => {
  if (out) return
  out = true
  page.removeAttribute('aria-busy')
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

// Another daemon: everything drawn of the last is drawn again of this one, as the address
// routed next says -- told before that routing, which api.js is told of first.
window.addEventListener('hmz:daemon', () => {
  if (mounted) mounted.leave()
  mounted = null
  shown = ''
  opened = ''
  behind = ''
  named().catch(() => {})
})

/** Names the page by the machine the daemon it is on is. */
function named() {
  const asked = daemon()
  return get('/api/held').then((context) => {
    if (asked === daemon()) document.title = `humanize · ${context.machine}`
    return context
  })
}

window.addEventListener('hashchange', route)

named()
  .then((context) => {
    mountSidebar(document.getElementById('sidebar'), context, where)
    route()
  })
  .catch((error) => {
    if (out) return
    // A daemon out of reach: said where the view would be, the sidebar there to go elsewhere.
    mountSidebar(document.getElementById('sidebar'), {}, where)
    fill(page, h('div', { class: 'view' }, problem(error)))
  })
