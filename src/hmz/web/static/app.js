// The page itself, laid out as Codex and Claude lay theirs out: the sidebar of every workspace's
// chats and epics on the left, and whichever view the address names beside it -- a new chat or epic, its graph, one session's
// thread, the flows -- and Ai-chan's drawer beside it, with finding a run and the settings opened
// over it as dialogs. Routed by the address's fragment, so that every view of the page is an
// address that can be kept, shared or opened again, and the server serves one page for all of
// them. An address names the daemon it is of first, `#/@<name>/<view>…`, or names none and is of
// Local.

import { daemon, hash, hello, started } from './api.js'
import { unmoved } from './desk.js'
import { fill, h, problem } from './dom.js'
import { pieces, t } from './i18n.js'
import { dismiss } from './layers.js'
import { mountSidebar } from './sidebar.js'
import { bar, kept, settlePanel, toggleSidebar } from './shell.js'
import { paint } from './themes.js'
import './ui.js'
import './importing.js'

/** Every view, by the first part of the address that names it. */
const VIEWS = {
  new: () => import('./views/new.js'),
  live: () => import('./views/epic.js'),
  chats: () => import('./views/epic.js'),
  epics: () => import('./views/epic.js'),
  flows: () => import('./views/flows.js'),
  envs: () => import('./views/envs.js'),
  harness: () => import('./views/harness.js'),
}

/** Every dialog, opened over the view the page was on. */
const DIALOGS = {
  search: () => import('./views/search.js'),
  download: () => import('./views/download.js'),
  settings: () => import('./views/settings.js'),
  delete: () => import('./views/chatdelete.js'),
}

const page = document.getElementById('page')
const overlay = document.querySelector('.overlay')
// What index.html says before any script runs is English: said here in the page's language,
// which lang.js set before anything was drawn.
document.querySelector('.skip').textContent = t('Skip to the page')
document.getElementById('sidebar').setAttribute('aria-label', t('Chats and epics'))
for (const opening of page.querySelectorAll('.loading')) opening.textContent = t('Opening Humanize…')
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
/**
 * How many steps of the history the dialog open is past the view under it, so that closing it
 * steps back to that view and leaves the history as it was: 0 where the page was opened on the
 * dialog's address, with no view before it.
 */
let over = 0
/**
 * How many of those steps lead back to the dialog this one was opened from, which closing it
 * goes back to (Section 3.6.6.26 of protocol/web.md): 0 where it was opened over a view, and
 * for a page of the same dialog as the one before it, which closes as that one does.
 */
let up = 0
/** Which dialog the address routed last named, or none. */
let last = ''
/** Whether the dialog open is being stepped back from, until the page is where that leads. */
let leaving = false
/** What held the focus as the dialog opened, which has it back once the dialog closes over the same view. */
let focused = null
/** What held the focus as the address was last routed: where the person was as they asked for the view. */
let asked = null
/** The address the view under a dialog took meanwhile, put in the address once the dialog closes. */
let renaming = ''
/** What the view drawn is kept by once it put its own query in the address: come back to, it stands. */
let stayed = ''

/** What a view is kept by: the parts of its address's path, and its query. */
function keyOf(path) {
  const url = new URL(path, 'http://page')
  return `${url.pathname.split('/').filter(Boolean).map(decodeURIComponent).join('/')}?${url.searchParams}`
}

/** Where the page is: the parts of the address's path, after the daemon it names, and its query. */
export function where() {
  const raw = location.hash.replace(/^#/, '').replace(/^\/?@[^/?]*/, '') || '/new/chat'
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
  // What the entry is kept with stays: how far a dialog's is past the view under it.
  history.replaceState(history.state, '', hash(`/${parts.map(encodeURIComponent).join('/')}${text ? `?${text}` : ''}`))
  routedTo = location.hash
  if (here === shown.split('?')[0]) stayed = `${here}?${text}`
}

/**
 * Says the view drawn is at another address from now on -- an epic going, named; a chat, on its
 * conversation -- without a step in the history and without drawing it again: closing a dialog
 * goes back to that address, and the sidebar marks its row by it. Under a dialog the address is
 * the dialog's, so it is put there once the dialog has closed.
 */
export function renamed(path) {
  if (covered()) {
    renaming = path
    return
  }
  renaming = ''
  history.replaceState(history.state, '', hash(path))
  routedTo = location.hash
  shown = keyOf(path)
  stayed = ''
  behind = path
  // The sidebar marks the row the address names, as it does where the address changes.
  window.dispatchEvent(new CustomEvent('hmz:renamed'))
}

/** The address of the view drawn under whatever dialog is open. */
export function under() {
  return behind
}

/** Whether the address names a dialog, over the view drawn: what that view does is not to say. */
export function covered() {
  return Boolean(DIALOGS[where().parts[0]])
}

/**
 * Whether the person has gone to type in Ai-chan's drawer, beside the view drawn, since they asked
 * for that view: what it reads meanwhile takes no focus out of the drawer. One asked for from the
 * drawer itself, by its shortcut, is typed into as any other.
 */
export function beside() {
  const at = document.activeElement
  return at !== asked && Boolean(at?.closest('[data-hmz=aichan]'))
}

/**
 * What a view gives the focus by once what it reads is drawn, asked for as the reading begins:
 * the box typed into next takes the focus then, unless a dialog is over the view, the person
 * went to type in Ai-chan's drawer beside it, or the focus
 * went elsewhere while the view read -- a control pressed, Tab, a dialog closed that gave it
 * back -- which is not taken from where it was put.
 *
 * @returns {(el: HTMLElement) => void}
 */
export function focusing() {
  const held = document.activeElement
  return (el) => {
    if (!covered() && !beside() && unmoved(held, document.activeElement, [document.body, page])) el.focus()
  }
}

/**
 * Closes the dialog open, going back to what it was opened over -- the dialog it was opened
 * from, or the view under it: by the steps of the history the dialog took, so that it leaves
 * none behind and Back goes on to what was open before, as from a dialog that was never an
 * address.
 */
export function shut() {
  if (leaving) return
  if (over > 0) {
    leaving = true
    history.go(-(up || over))
  } else go(behind || '/new/chat')
}

async function route(event) {
  if (out) return
  // Told before anything of the address is drawn: whatever floats closes and gives its focus
  // back, and the drawer the sidebar is on a narrow window closes.
  window.dispatchEvent(new CustomEvent('hmz:route'))
  const mine = ++routed
  routedTo = location.hash
  asked = document.activeElement
  leaving = false
  // A dialog's entry is kept with how far it is past the view, and past the dialog it was
  // opened from: one come back to says so itself.
  const kind = covered() ? where().parts[0] : ''
  if (kind) {
    if (!history.state || typeof history.state.over !== 'number') history.replaceState({ over: event ? over + 1 : 0, up: !event || !last ? 0 : kind !== last ? 1 : up && up + 1 }, '')
    over = history.state.over
    up = history.state.up || 0
  } else over = up = 0
  last = kind
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
    if (!shown) await view(mine, ['new', 'chat'], new URLSearchParams(), '/new/chat')
    if (mine !== routed) return
    return open(mine, dialog, parts, query)
  }
  behind = location.hash.replace(/^#/, '') || '/new/chat'
  const key = `${parts.join('/')}?${query}`
  const same = key === shown || key === stayed
  close(same)
  if (same) {
    // What the view called itself while the dialog was over it.
    if (renaming) renamed(renaming)
    return
  }
  renaming = ''
  await view(mine, parts, query, key)
}

/** An epic read back in by its path: an address under `epics` no epic is named. */
const IMPORT = () => import('./views/import.js')

/** A new chat, `new/chat`, beside a new epic of a flow, `new` (Section 3.8.17 of protocol/web.md). */
const CHAT = () => import('./views/newchat.js')

/** What draws the view an address names. */
function loader(parts) {
  if (parts[0] === 'epics' && parts[1] === 'import' && parts.length === 2) return IMPORT
  if (parts[0] === 'new' && parts[1] === 'chat') return CHAT
  return VIEWS[parts[0]] || VIEWS.new
}

async function view(mine, parts, query, key) {
  const load = loader(parts)
  const named = VIEWS[parts[0]] ? parts : ['new']
  // A view that can move within itself -- a run's graph to one of its sessions -- does.
  if (mounted && mounted.load === load && mounted.moved && mounted.moved({ parts: named, query })) {
    shown = key
    stayed = ''
    return
  }
  if (mounted) mounted.leave()
  mounted = null
  try {
    const module = await load()
    if (mine !== routed && !DIALOGS[where().parts[0]]) return
    shown = key
    stayed = ''
    fill(page)
    const made = module.mount(page, { parts: named, query })
    mounted = typeof made === 'function' ? { load, leave: made } : { load, leave: () => {}, ...made }
  } catch (error) {
    // Said where it happened, and to the console, where whoever is debugging the page looks.
    console.error(error)
    // Under a bar, as every view is: the window is moved by it, and Ai-chan's button ends it.
    fill(page, h('div', { class: 'view' }, bar(), h('div', { class: 'view-scroll' }, problem(t('This view failed to open: {why}', { why: error.message })))))
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
    // Nothing is left floating over it: what was opened while it loaded closes first.
    dismiss('dialog')
    if (overlay.hidden) focused = document.activeElement
    fill(overlay, h('div', { class: 'dialog-scrim', onclick: shut }), dialog)
    overlay.hidden = false
    document.body.classList.add('dialog-open')
    closing = module.mount(dialog, { parts, query }) || null
    ;(dialog.querySelector('[autofocus]') || dialog.querySelector('input, button, a'))?.focus()
  } catch (error) {
    console.error(error)
    fill(overlay, h('div', { class: 'dialog-scrim', onclick: shut }), h('div', { class: 'dialog' }, problem(error)))
    overlay.hidden = false
  }
}

/** Closes the dialog open; `same` where the view under it is the one the page stays on. */
function close(same = false) {
  opened = ''
  if (closing) closing()
  closing = null
  const back = focused
  focused = null
  if (overlay.hidden) return
  overlay.hidden = true
  fill(overlay)
  document.body.classList.remove('dialog-open')
  // The focus goes back to where it was -- the box being typed into, or what opened the dialog --
  // where that is still there to be seen; else to the page.
  if (same && back instanceof HTMLElement && back !== document.body && seen(back)) back.focus({ preventScroll: true })
  else page.focus({ preventScroll: true })
}

/** Whether something is drawn within the window: not gone, hidden, or in a drawer slid away. */
function seen(el) {
  if (!el.isConnected) return false
  const box = el.getBoundingClientRect()
  return box.width > 0 && box.height > 0 && box.right > 0 && box.left < innerWidth
}

/** What Tab stops at. */
const STOPS = 'a[href], button, input, select, textarea, [tabindex]'

/**
 * Keeps Tab within the dialog open, as a modal one keeps it: it goes from stop to stop of the
 * dialog, the same in every browser -- one that leaves buttons out of its own order would go on
 * to the page under it -- and past its last stop is its first.
 */
function held(event) {
  const dialog = overlay.querySelector('.dialog')
  if (!dialog) return
  const stops = [...dialog.querySelectorAll(STOPS)].filter((el) => el.tabIndex >= 0 && !el.disabled && seen(el))
  if (!stops.length) return
  const at = stops.indexOf(document.activeElement)
  // A menu opened from it stands in the page, and keeps its own keys.
  if (at < 0 && document.activeElement?.closest('.popover')) return
  event.preventDefault()
  const step = event.shiftKey ? -1 : 1
  stops[at < 0 ? (step > 0 ? 0 : stops.length - 1) : (at + step + stops.length) % stops.length].focus()
}

/**
 * Goes where a shortcut leads: asked for where the page already is, it is a going there all the
 * same, at which whatever floats closes and the drawer the sidebar is on a narrow window shuts.
 */
function jump(path) {
  if (location.hash === hash(path)) window.dispatchEvent(new CustomEvent('hmz:route'))
  else go(path)
}

// What is opened from a dialog -- a chat found, a new chat -- takes the dialog's place in the
// history, so that Back from it goes to the view the dialog was over and never to the dialog.
document.addEventListener('click', (event) => {
  if (overlay.hidden || over !== 1 || event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  const link = event.target instanceof Element ? event.target.closest('a[href^="#"]') : null
  if (!link || link.target || link.hasAttribute('download')) return
  const first = link.getAttribute('href').replace(/^#\/?(@[^/?]*\/?)?/, '').split(/[/?]/)[0]
  if (DIALOGS[decodeURIComponent(first)]) return
  event.preventDefault()
  location.replace(link.href)
})

document.addEventListener('keydown', (event) => {
  const mod = event.metaKey || event.ctrlKey
  // A dialog of the browser's own over the page -- a confirmation -- is modal: Escape is its
  // own, and the page under it is not folded or closed by a key.
  const modal = Boolean(document.querySelector('dialog[open]'))
  if (event.key === 'Tab' && !overlay.hidden) return modal || held(event)
  if (mod && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    jump('/search')
  } else if (mod && event.shiftKey && event.key.toLowerCase() === 'o') {
    event.preventDefault()
    jump('/new/chat')
  } else if (mod && event.key === '.') {
    event.preventDefault()
    if (!modal) toggleSidebar()
  } else if (event.key !== 'Escape' || modal || event.defaultPrevented) {
    return
  } else if (!overlay.hidden) {
    event.preventDefault()
    shut()
  } else if (document.querySelector('.app').classList.contains('side-open')) {
    // The drawer the sidebar is on a narrow window closes as a dialog does.
    event.preventDefault()
    toggleSidebar(false)
  } else if (settlePanel()) {
    // And so does the panel that is over the view there.
    event.preventDefault()
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
      bar(),
      h(
        'div',
        { class: 'empty' },
        h('strong', {}, t('This browser is not let in.')),
        pieces('Open the address {command} printed when it started: it carries the key that lets a browser in.', { command: h('code', {}, 'hmz web') }),
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
  stayed = ''
  opened = ''
  behind = ''
  renaming = ''
  named().catch(() => {})
})

/** Names the page by the machine the daemon it is on is. */
function named() {
  const asked = daemon()
  return hello(asked).then((said) => {
    if (asked === daemon()) document.title = `Humanize · ${said.machine}`
    return said
  })
}

window.addEventListener('hashchange', route)

// Let in first: a browser that is not is told so (`hmz:out`), and is shown nothing else.
started().then((here) => {
  if (out) return
  mountSidebar(document.getElementById('sidebar'), { here }, where)
  route()
  // Ai-chan's drawer, beside every view: loaded once the page is let in, as the views are.
  import('./views/aichan.js').then(
    (drawer) => drawer.mount(document.querySelector('.app'), where),
    (error) => console.error(error),
  )
  // A daemon out of reach is said where each view asks it something; the page is named once it answers.
  named().catch(() => {})
})
