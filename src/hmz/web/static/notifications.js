// The notifications, of every daemon at once rather than the one shown: a bell with how many are
// unread, a menu of them newest first, a card for each as it comes, and -- while the page is not
// looked at -- one the system shows, by the macOS app or by the browser. Each opens what it is
// about: the epic going, for a question or a chat's next turn, or the epic that ended. None is
// told of the epic the page is on while it is looked at: that one is read as it comes.

import { daemon, get, post } from './api.js'
import { ago, fill, h, headline, icon, iconButton } from './dom.js'
import { inApp, menu, section } from './shell.js'

/** What each kind is called, and the mark it is drawn with. */
const KINDS = {
  done: ['Done', '✔', 'done'],
  failed: ['Failed', '✕', 'failed'],
  stopped: ['Stopped', '■', 'stopped'],
  asked: ['Question', '?', 'running'],
  listening: ['Chat turn', '›', 'running'],
}

/** How long a card stays, and how many stand at once. */
const SHOWN = 6000
const CARDS = 3

/** The notifications held, newest first. */
let items = []
let button = null
let count = null
let drawMenu = null
let cards = null
/** Where the page is, as the sidebar is told it. */
let where = null

/**
 * The bell, made once and the feed started with it: hidden while the server has no notifications.
 *
 * @param {() => {parts: string[], query: URLSearchParams}} at Where the page is.
 */
export function bell(at) {
  if (button) return button
  where = at
  count = h('span', { class: 'notify-count', 'data-hmz': 'notification-count', hidden: true })
  button = h('button', { class: 'icon-btn notify-bell', type: 'button', 'aria-label': 'Notifications', title: 'Notifications', 'data-hmz': 'notifications', hidden: true }, icon('bell'), count)
  menu(button, (close) => {
    const list = h('div', { class: 'notify-list' })
    drawMenu = () => drawList(list, close)
    drawMenu()
    const read = h('button', { class: 'btn quiet small', type: 'button', 'data-hmz': 'notifications-read', onclick: () => markRead(null) }, 'Mark read')
    const clear = h('button', { class: 'btn quiet small', type: 'button', 'data-hmz': 'notifications-clear', onclick: clearAll }, 'Clear')
    return [h('div', { class: 'notify-menu', 'data-hmz': 'notification-menu' }, h('div', { class: 'notify-head' }, section('Notifications'), read, clear), list)]
  }, { label: 'Notifications' })
  start()
  return button
}

/** How long a failed read waits before the next, which doubles up to five minutes. */
let wait = 10000
/** What was heard since the list was last asked for, which an older answer must not drop. */
let fresh = new Map()

async function start() {
  try {
    await reread()
  } catch (error) {
    // A server without notifications has no bell, nor a browser not let in; else it is asked again.
    if (error.status !== 404 && error.status !== 401) {
      setTimeout(start, wait)
      wait = Math.min(wait * 2, 300000)
    }
    return
  }
  button.hidden = false
  const stream = new EventSource('/api/notifications/stream')
  stream.addEventListener('notification', (event) => heard(JSON.parse(event.data)))
  // Read again whenever the stream opens, for what came before it did, and as the page is
  // looked at again, for what another tab read or cleared.
  stream.addEventListener('open', () => reread().catch(() => {}))
  document.addEventListener('visibilitychange', () => document.hidden || reread().catch(() => {}))
  // What is of the epic the page comes to, or is looked at again on, is read there.
  addEventListener('hashchange', seen)
  addEventListener('focus', seen)
}

/** Whether a notification is of the epic the page is on, while it is looked at. */
function here(item) {
  if (document.hidden || !document.hasFocus() || (item.daemon || 'local') !== daemon()) return false
  const { parts, query } = where()
  if (parts[0] === 'live') return Boolean(item.workspace) && query.get('workspace') === item.workspace
  return parts[0] === 'epics' && Boolean(item.epic) && parts[1] === item.epic
}

/** Reads every notification of the epic the page is on. */
function seen() {
  const ids = items.filter((one) => !one.read && here(one)).map((one) => one.id)
  if (ids.length) markRead(ids)
}

/** The epics, and the workspaces they are of, that a notification unread is of on a daemon. */
export function unreadOn(name) {
  const mine = items.filter((one) => !one.read && (one.daemon || 'local') === name)
  return { epics: new Set(mine.map((one) => one.epic)), workspaces: new Set(mine.map((one) => one.workspace)) }
}

async function reread() {
  fresh = new Map()
  const answer = await get('/api/notifications')
  const known = new Set((answer.items || []).map((one) => one.id))
  items = [...[...fresh.values()].reverse().filter((one) => !known.has(one.id)), ...(answer.items || [])]
  draw()
  seen()
}

function heard(item) {
  fresh.set(item.id, item)
  if (items.some((one) => one.id === item.id)) return
  items.unshift(item)
  if (here(item)) return markRead([item.id])
  draw()
  card(item)
  system(item)
}

function draw() {
  const unread = items.filter((one) => !one.read).length
  count.hidden = !unread
  count.textContent = unread > 99 ? '99+' : String(unread)
  if (drawMenu && button.getAttribute('aria-expanded') === 'true') drawMenu()
  // For the sidebar's marks of what is unread.
  window.dispatchEvent(new CustomEvent('hmz:notifications'))
}

function drawList(list, close) {
  if (!items.length) return fill(list, h('p', { class: 'notify-none' }, 'Nothing yet'))
  fill(
    list,
    items.map((item) =>
      h(
        'button',
        { class: ['choice', 'notify-item', !item.read && 'notify-unread'], type: 'button', role: 'menuitem', 'data-hmz': 'notification', onclick: () => (close(), opens(item)) },
        mark(item),
        h('span', { class: 'choice-text' }, h('span', { class: 'choice-label' }, `${kindOf(item)} · ${daemonOf(item)}`), h('span', { class: 'choice-about' }, about(item)), h('span', { class: 'notify-when' }, ago(item.at))),
      ),
    ),
  )
}

function mark(item) {
  const [, glyph, tone] = KINDS[item.kind] || ['', '·', 'idle']
  return h('span', { class: `choice-mark tone-${tone}`, 'aria-hidden': 'true' }, h('span', { class: 'glyph' }, glyph))
}

const kindOf = (item) => (KINDS[item.kind] || [item.kind])[0]
const daemonOf = (item) => (!item.daemon || item.daemon === 'local' ? 'Local' : item.daemon)
const about = (item) => [item.flow, item.text || (item.task ? headline(item.task) : item.epic)].filter(Boolean).join(' · ')

/** Where a notification opens: the epic going for what waits on a person, else the epic itself. */
export function addressOf(item) {
  const at = !item.daemon || item.daemon === 'local' ? '#/' : `#/@${encodeURIComponent(item.daemon)}/`
  if ((item.kind === 'asked' || item.kind === 'listening' || !item.epic) && item.workspace) return `${at}live?${new URLSearchParams({ workspace: item.workspace })}`
  return item.epic ? `${at}epics/${encodeURIComponent(item.epic)}` : `${at}live`
}

function opens(item) {
  if (items.some((one) => one.id === item.id && !one.read)) markRead([item.id])
  location.hash = addressOf(item)
}

async function markRead(ids) {
  for (const one of items) if (!ids || ids.includes(one.id)) one.read = true
  draw()
  try {
    await post('/api/notifications/read', ids ? { ids } : { all: true })
  } catch {
    // Read here alone, until the list is read again.
  }
}

async function clearAll() {
  items = []
  draw()
  try {
    await post('/api/notifications/clear')
  } catch {
    // Cleared here; read back as they are when the page is looked at again.
  }
}

/** A card for a notification as it comes, at the foot of the window, gone after a moment. */
function card(item) {
  if (!cards) {
    cards = h('div', { class: 'notify-toasts', 'data-hmz': 'notification-toasts', role: 'status', 'aria-live': 'polite' })
    document.body.append(cards)
  }
  const shut = iconButton('close', 'Dismiss', { class: 'notify-shut' })
  const one = h(
    'div',
    { class: 'notify-card', 'data-hmz': 'notification-toast' },
    h('button', { class: 'notify-open', type: 'button', onclick: () => (one.remove(), opens(item)) }, mark(item), h('span', { class: 'choice-text' }, h('span', { class: 'choice-label' }, `${kindOf(item)} · ${daemonOf(item)}`), h('span', { class: 'choice-about' }, about(item)))),
    shut,
  )
  shut.addEventListener('click', () => one.remove())
  cards.prepend(one)
  while (cards.children.length > CARDS) cards.lastChild.remove()
  setTimeout(() => one.remove(), SHOWN)
}

/** One the system shows, while the page is not looked at and the settings let it. */
async function system(item) {
  if (!document.hidden && document.hasFocus()) return
  // Read as one comes, rare as they are, so a change in Settings holds at once.
  const said = await get('/api/notifications/settings').catch(() => null)
  if (!said || !said.system) return
  const title = `${kindOf(item)} · ${daemonOf(item)}`
  const body = about(item)
  const address = addressOf(item)
  if (inApp) {
    window.__TAURI_INTERNALS__?.invoke('notify', { title, body, address })?.catch?.(() => {})
    return
  }
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  const shown = new Notification(title, { body, tag: String(item.id) })
  shown.onclick = () => {
    window.focus()
    opens(item)
    shown.close()
  }
}
