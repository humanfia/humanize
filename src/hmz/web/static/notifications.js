// The notifications, of every daemon at once rather than the one shown (Section 3.15 of
// protocol/web.md): each notice marks its chat or epic unread in the sidebar and is shown by the
// system -- by Humanize Desktop, or by the browser once it allows it -- and by nothing the page
// draws. A click on one opens what it is about: the chat, by its id; the epic going, for a
// question; or the epic that ended. None of the chat or epic the page is on is marked, nor
// shown while the page is looked at, and one made long before it is heard is marked alone.

import { call, client, daemon, onState } from './api.js'
import { followed, fresh, of, onScreen, shownAs } from './notified.js'
import { inApp, settleSidebar } from './shell.js'
import { stored } from './stored.js'

/** Where each daemon's notices are taken up, and what this browser wants told of them. */
const store = stored('hmz-notifications')
export const kept = followed(store)

/** Each daemon followed, by name: the client its subscription is on. */
const following = new Map()
/** Every notice told by this page, by its key: one sent again is told once. */
const told = new Set()
/** Where the page is, and what marks a row unread, as the sidebar gives them. */
let where = null
let unread = null

/**
 * Follows the notices of every daemon the page reaches; once.
 *
 * @param {() => {parts: string[], query: URLSearchParams}} at Where the page is.
 * @param {(daemon: string, name: string, on?: boolean) => void} mark Marks a chat or epic of a daemon unread, or read.
 */
export function notifying(at, mark) {
  if (where) return
  where = at
  unread = mark
  // The list an earlier page kept here is kept no longer (Section 3.15.2.1 of protocol/web.md).
  store.drop('items').catch(() => {})
  // Local, and every remote daemon once the page has reached it, while it is up.
  onState((name, now) => now.state === 'up' && follow(name))
  follow('local')
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

async function heard(name, notice) {
  const item = await kept.heard(name, notice).catch(() => null)
  if (!item || told.has(item.key)) return
  told.add(item.key)
  // On what it is of, the page has no row to mark; looked at as well, it has nothing to tell.
  const at = { daemon: daemon(), ...where() }
  if (onScreen(item, { ...at, looked: !document.hidden && document.hasFocus() })) return
  if (!onScreen(item, { ...at, looked: true })) unread(item.daemon, of(item))
  if (fresh(item)) system(item)
}

/** One the system shows, where the settings let it. */
async function system(item) {
  // Read as one comes, rare as they are, so a change in Settings holds at once.
  const said = await kept.preferences().catch(() => null)
  if (!said || !said.system) return
  const { title, body, address, tag } = shownAs(item)
  if (inApp) {
    window.__TAURI_INTERNALS__?.invoke('notify', { title, body, address })?.catch?.(() => {})
    return
  }
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  const shown = new Notification(title, { body, tag })
  shown.onclick = () => {
    window.focus()
    // The page comes to what it is of, wherever its address leads.
    unread(item.daemon, of(item), false)
    // Where the page is on it already the address does not change, and the drawer is still not left over it.
    settleSidebar()
    location.hash = address
    shown.close()
  }
}
