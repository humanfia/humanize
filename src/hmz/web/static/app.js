// The page itself: the bar on top, and whichever view the address names under it. Routed by
// the address's fragment, so that every view of the page is an address that can be kept,
// shared or opened again, and the server serves one page for all of them.

import { get } from './api.js'
import { fill, h } from './dom.js'
import { follow } from './held.js'

/** Every view, by the first part of the address that names it. */
const VIEWS = {
  runs: { label: 'Runs', load: () => import('./views/runs.js') },
  live: { label: 'Live', load: () => import('./views/run.js'), hidden: true },
  start: { label: 'Start', load: () => import('./views/start.js') },
  flows: { label: 'Flows', load: () => import('./views/flows.js') },
  usage: { label: 'Usage', load: () => import('./views/usage.js') },
  settings: { label: 'Settings', load: () => import('./views/settings.js') },
}

const page = document.getElementById('page')
const bar = document.querySelector('.topbar')
let leaving = null
let out = false
/** Which routing is the latest: one overtaken while its view was loading draws nothing. */
let routed = 0

/** Where the page is: the parts of the address's path, and its query. */
export function where() {
  const raw = location.hash.replace(/^#/, '') || '/runs'
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

async function route() {
  if (out) return
  const mine = ++routed
  const { parts, query } = where()
  const name = parts[0] in VIEWS ? parts[0] : 'runs'
  const view = parts[0] === 'runs' && parts[1] ? { load: () => import('./views/run.js') } : VIEWS[name]
  for (const link of bar.querySelectorAll('.nav a')) {
    if (link.dataset.view === name) link.setAttribute('aria-current', 'page')
    else link.removeAttribute('aria-current')
  }
  if (leaving) leaving()
  leaving = null
  try {
    const module = await view.load()
    if (mine !== routed) return
    fill(page)
    leaving = module.mount(page, { parts, query }) || null
  } catch (error) {
    fill(page, h('p', { class: 'error', role: 'alert' }, `This view failed to open: ${error.message}`))
  }
}

function drawBar(context) {
  const theme = h('button', { class: 'theme', type: 'button', 'aria-label': 'Change the colours' }, themeSaid())
  theme.addEventListener('click', () => {
    const next = { system: 'light', light: 'dark', dark: 'system' }[themeChosen()]
    if (next === 'system') localStorage.removeItem('hmz-theme')
    else localStorage.setItem('hmz-theme', next)
    applyTheme()
    theme.textContent = themeSaid()
  })
  const state = h('a', { class: 'state', href: '#/live', 'data-hmz': 'state' })
  fill(
    bar,
    h('a', { class: 'brand', href: '#/runs' }, h('img', { src: '/mark.svg', alt: '' }), h('strong', {}, 'humanize')),
    h('span', { class: 'where', title: context.workspace }, context.workspace),
    h(
      'nav',
      { class: 'nav', 'aria-label': 'Views' },
      Object.entries(VIEWS)
        .filter(([, one]) => !one.hidden)
        .map(([name, one]) => h('a', { href: `#/${name}`, 'data-view': name }, one.label)),
    ),
    state,
    theme,
  )
  follow((held) => drawState(state, held))
}

function drawState(el, held) {
  const run = held.standing.run
  let dot = 'gone'
  let said = held.gone || 'reaching the runs'
  if (held.connected && run) {
    dot = run.state === 'idle' ? '' : 'live'
    said = run.state === 'idle' ? 'no run going' : `${run.state === 'stopping' ? 'stopping' : 'live'} · ${run.flow || 'a flow'}`
  } else if (!held.gone) dot = 'waiting'
  fill(el, h('span', { class: ['dot', dot], 'aria-hidden': 'true' }), said)
}

function themeChosen() {
  return localStorage.getItem('hmz-theme') || 'system'
}

function themeSaid() {
  return { system: 'auto', light: 'light', dark: 'dark' }[themeChosen()]
}

function applyTheme() {
  const chosen = themeChosen()
  const dark = chosen === 'system' ? matchMedia('(prefers-color-scheme: dark)').matches : chosen === 'dark'
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme)
window.addEventListener('storage', (event) => event.key === 'hmz-theme' && applyTheme())

window.addEventListener('hmz:out', () => {
  if (out) return
  out = true
  if (leaving) leaving()
  fill(
    page,
    h(
      'div',
      { class: 'empty' },
      h('strong', {}, 'This browser is not let in.'),
      'Open the address ',
      h('code', {}, 'hmz web'),
      ' printed when it started: it carries the key that lets a browser in.',
    ),
  )
})

window.addEventListener('hashchange', route)

get('/api/held')
  .then((context) => {
    document.title = `humanize · ${context.workspace.split('/').filter(Boolean).pop() || context.workspace}`
    drawBar(context)
    route()
  })
  .catch((error) => {
    if (!out) fill(page, h('p', { class: 'error', role: 'alert' }, error.message))
  })
