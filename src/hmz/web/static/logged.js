// The page's own keeping of what it last saw of each conversation (logs.js), and the reading
// ahead of the few latest in the sidebar while nothing else is asked, so that the first press on
// one of them draws it at once too (Section 3.6.12 of protocol/web.md).

import { call, daemon, idOf, unasked } from './api.js'
import { chatDetail } from './chats.js'
import { keyOf, logCache, warmable } from './logs.js'

/** The browser's IndexedDB, or none where it will not even be named: kept in memory alone. */
function browsers() {
  try {
    return globalThis.indexedDB || null
  } catch {
    return null
  }
}

/** What the page last saw of each conversation. */
export const logs = logCache({ indexedDB: browsers() })

/** What a conversation of the daemon shown is kept by. */
export function logKey(kind, id, on = daemon()) {
  return keyOf(on, kind, id)
}

/** How many of the latest conversations are read ahead, and how long before one is read ahead again. */
const WARM = 4
const AGAIN = 60000

/** How long, in milliseconds, reading ahead waits on what is being asked in front of it. */
const YIELDS = 300

/** When each conversation was last read ahead, by its key. */
const warmed = new Map()
/** Those waiting to be, the latest heard of first, and whether one is being read. */
let waiting = []
let reading = false
/** The conversation in front, which its own view reads. */
let front = ''

/** Says which conversation is in front, or '' for none: never read ahead. */
export function fronted(key) {
  front = key
}

/** Once the browser has nothing else to do, or after a while where it cannot say. */
function idle(act) {
  if (globalThis.requestIdleCallback) globalThis.requestIdleCallback(() => act(), { timeout: 5000 })
  else setTimeout(act, 1200)
}

/**
 * Reads ahead the latest conversations of the sidebar's list that are not kept as they now
 * stand: one at a time, while the browser is idle and the page asks nothing else, and never
 * through a host -- only what the daemon wrote down of each.
 *
 * @param {object[]} rows The list's rows, chats and epics.
 */
export function warm(rows) {
  const on = daemon()
  const lately = (key) => Date.now() - (warmed.get(key) || 0) < AGAIN
  waiting = warmable(rows, logs, on, { most: WARM, front, lately }).map((one) => ({ ...one, on }))
  if (reading || !waiting.length) return
  reading = true
  idle(next)
}

async function next() {
  const one = waiting.shift()
  // A page nobody looks at reads nothing ahead: the list read next asks again.
  if (!one || document.hidden) {
    reading = false
    return
  }
  // Whatever is asked in front goes first.
  if (!unasked()) {
    waiting.unshift(one)
    setTimeout(next, YIELDS)
    return
  }
  warmed.set(one.key, Date.now())
  try {
    const kept = { daemon: one.on, kind: one.kind, id: one.name, stamp: one.stamp }
    const behind = { on: one.on, behind: true }
    let detail = null
    let traced = null
    if (one.kind === 'chat') {
      const { trace, ...row } = await call('chat.get', { chat: one.name, trace: true }, behind)
      detail = chatDetail(row)
      traced = trace
    } else {
      detail = await call('runs.get', { name: one.name }, behind)
      traced = (await call('runs.trace', { name: one.name }, behind)).sessions
    }
    // Opened meanwhile, its own view keeps it. What a host told of it is kept only while a
    // host still holds it.
    if (one.key !== front) logs.put(one.key, { ...kept, of: idOf(one.on), workspace: detail.workspace, detail, traced, ...(detail.held ? {} : { live: null }) })
  } catch (error) {
    // Gone since it was listed: nothing is kept of it.
    if (error.status === 404) logs.drop(one.key)
  }
  idle(next)
}

// What is kept is written as the page goes, whatever it was about to write later.
globalThis.addEventListener?.('pagehide', () => void logs.flush())
