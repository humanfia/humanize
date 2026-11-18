// The notifications, of every daemon at once rather than the one shown: a bell with how many are
// unread, a menu of them newest first, a card for each as it comes, and -- while the page is not
// looked at -- one the system shows, by Humanize Desktop or by the browser. Each opens what it is
// about: the epic going, for a question or a chat's next turn, or the epic that ended. None is
// told of the epic the page is on while it is looked at: that one is read as it comes.

import { call, client, daemon, onState } from './api.js'
import { ago, fill, h, headline, icon, iconButton } from './dom.js'
import { gathered, kindOf as wantedAs } from './notified.js'
import { inApp, menu, section } from './shell.js'
import { stored } from './stored.js'

/** What each kind is called, and the mark it is drawn with. */
const KINDS = {
  done: ['Done', '✔', 'done'],
  failed: ['Failed', '✕', 'failed'],
  stopped: ['Stopped', '■', 'stopped'],
  asked: ['Question', '?', 'asking'],
  listening: ['Waiting', '›', 'asking'],
}

/** How long a card stays, and how many stand at once. */
const SHOWN = 6000
const CARDS = 3

/** The notifications this browser keeps, and what it wants told of them. */
export const kept = gathered(stored('hmz-notifications'))

/** The notifications held, newest first. */
let items = []
let button = null
let count = null
let drawMenu = null
let cards = null
/** Where the page is, as the sidebar is told it. */
let where = null

/**
 * The bell, made once and the notices of every daemon followed with it.
 *
 * @param {() => {parts: string[], query: URLSearchParams}} at Where the page is.
 */
export function bell(at) {
  if (button) return button
  where = at
  count = h('span', { class: 'notify-count', 'data-hmz': 'notification-count', hidden: true })
  button = h('button', { class: 'icon-btn notify-bell', type: 'button', 'aria-label': 'Notifications', title: 'Notifications', 'data-hmz': 'notifications' }, icon('bell'), count)
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

/** Each daemon followed, by name: the client its subscription is on. */
const following = new Map()

async function start() {
  await reread().catch(() => {})
  // Local, and every remote daemon once the page has reached it, while it is up.
  onState((name, now) => now.state === 'up' && follow(name))
  follow('local')
  // Read again as the page is looked at again, for what another tab read or cleared.
  document.addEventListener('visibilitychange', () => document.hidden || reread().catch(() => {}))
  // What is of the epic the page comes to, or is looked at again on, is read there.
  addEventListener('hashchange', seen)
  addEventListener('focus', seen)
}

/**
 * Follows one daemon's notices (`notices.subscribe`, Section 3.15.1.1 of protocol/web.md), after
 * the last heard of it, or from where its first subscription stood; again on a client of its own.
 */
async function follow(name) {
  let reaching
  try {
    reaching = await client(name)
  } catch {
    return
  }
  if (following.get(name) === reaching) return
  following.set(name, reaching)
  const after = await kept.after(name).catch(() => undefined)
  try {
    await reaching.notices((notice) => heard(name, notice), after === undefined ? {} : { after })
  } catch {
    // Not up after all: followed again once it is.
    if (following.get(name) === reaching) following.delete(name)
    return
  }
  if (after === undefined) {
    const { last } = await call('notices.list', {}, { on: name }).catch(() => ({ last: undefined }))
    if (typeof last === 'number') await kept.from(name, last).catch(() => {})
  }
}

/** Whether a notification is of the epic the page is on, while it is looked at. */
function here(item) {
  if (document.hidden || !document.hasFocus() || (item.daemon || 'local') !== daemon()) return false
  const { parts, query } = where()
  if (parts[0] === 'live') return Boolean(item.workspace) && query.get('workspace') === item.workspace && (query.get('slot') || '') === (item.slot || '')
  return parts[0] === 'epics' && Boolean(item.epic) && parts[1] === item.epic
}

/** Reads every notification of the epic the page is on. */
function seen() {
  const keys = items.filter((one) => !one.read && here(one)).map((one) => one.key)
  if (keys.length) markRead(keys)
}

/** The epics, and the workspaces they are of, that a notification unread is of on a daemon. */
export function unreadOn(name) {
  const mine = items.filter((one) => !one.read && (one.daemon || 'local') === name)
  return { epics: new Set(mine.map((one) => one.epic)), workspaces: new Set(mine.map((one) => one.workspace)) }
}

/** Reads every notification of one epic of a daemon, as its row's menu asks. */
export function readOf(name, epic) {
  const keys = items.filter((one) => !one.read && (one.daemon || 'local') === name && one.epic === epic).map((one) => one.key)
  if (keys.length) markRead(keys)
}

async function reread() {
  items = await kept.items()
  draw()
  seen()
}

async function heard(name, notice) {
  const item = await kept.heard(name, notice).catch(() => null)
  if (!item) return
  items = [item, ...items.filter((one) => one.key !== item.key)].slice(0, 200)
  if (here(item)) return markRead([item.key])
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
  const [, glyph, tone] = KINDS[wantedAs(item)] || ['', '·', 'idle']
  return h('span', { class: `choice-mark tone-${tone}`, 'aria-hidden': 'true' }, h('span', { class: 'glyph' }, glyph))
}

const kindOf = (item) => (KINDS[wantedAs(item)] || [item.kind])[0]
const daemonOf = (item) => (!item.daemon || item.daemon === 'local' ? 'Local' : item.daemon)
const about = (item) => [item.flow, item.text || (item.task ? headline(item.task) : item.epic)].filter(Boolean).join(' · ')

/** Where a notification opens: the epic going for what waits on a person, else the epic itself. */
export function addressOf(item) {
  const at = !item.daemon || item.daemon === 'local' ? '#/' : `#/@${encodeURIComponent(item.daemon)}/`
  if ((item.kind === 'asked' || item.kind === 'listening' || !item.epic) && item.workspace) return `${at}live?${new URLSearchParams({ workspace: item.workspace, ...(item.slot ? { slot: item.slot } : {}) })}`
  return item.epic ? `${at}epics/${encodeURIComponent(item.epic)}` : `${at}live`
}

function opens(item) {
  if (items.some((one) => one.key === item.key && !one.read)) markRead([item.key])
  location.hash = addressOf(item)
}

async function markRead(keys) {
  for (const one of items) if (!keys || keys.includes(one.key)) one.read = true
  draw()
  await kept.read(keys).catch(() => {})
}

async function clearAll() {
  items = []
  draw()
  await kept.clear().catch(() => {})
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
  const said = await kept.preferences().catch(() => null)
  if (!said || !said.system) return
  const title = `${kindOf(item)} · ${daemonOf(item)}`
  const body = about(item)
  const address = addressOf(item)
  if (inApp) {
    window.__TAURI_INTERNALS__?.invoke('notify', { title, body, address })?.catch?.(() => {})
    return
  }
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  const shown = new Notification(title, { body, tag: item.key })
  shown.onclick = () => {
    window.focus()
    opens(item)
    shown.close()
  }
}
