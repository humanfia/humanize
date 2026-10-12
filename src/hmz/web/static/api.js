// How the page asks the server anything: one wrapper for reading and writing, which turns a
// refusal into the sentence the server gave, and one store for what is read again and again,
// shared by every view of it. Everything is asked of the daemon the address names -- `#/@<name>/…`,
// Local where it names none -- under `/d/<name>/api/…`, save what is the same for every daemon.

/** What is asked of Local whichever daemon the page is on: the daemons, and the notifications. */
const GLOBAL = /^\/api\/(daemons|notifications)(\/|\?|$)/

/** The daemon the address names, or '' where it names none. */
function named(address) {
  const match = /^#?\/?@([^/?]*)/.exec(address)
  try {
    return match ? decodeURIComponent(match[1]) : ''
  } catch {
    return match[1]
  }
}

let naming = named(location.hash)
/** How many times the page has switched daemons: what was asked before the last is not told. */
let era = 0
const switched = new Set()

/** The daemon the page is on. */
export function daemon() {
  return naming || 'local'
}

/** Where an address of the API is asked: of the daemon the page is on, unless it is global. */
export function scoped(path) {
  return path.startsWith('/api/') && !GLOBAL.test(path) ? `/d/${encodeURIComponent(daemon())}${path}` : path
}

/** The address of a view of the page, on the daemon the page is on, as the address names it. */
export function hash(path) {
  if (path.startsWith('#')) path = path.slice(1)
  if (path.startsWith('/@')) return `#${path}`
  return naming ? `#/@${encodeURIComponent(naming)}${path}` : `#${path}`
}

/** Switches the page to another daemon, on the view given, a new epic where none is. */
export function toDaemon(name, path = '/new') {
  location.hash = name === 'local' ? path : `/@${encodeURIComponent(name)}${path}`
}

/** Tells `fn` the daemon the page switched to, each time it does, until what it returns is called. */
export function onDaemon(fn) {
  switched.add(fn)
  return () => switched.delete(fn)
}

// Ahead of the page's own routing, which is told by the event to draw everything again.
window.addEventListener('hashchange', () => {
  const was = daemon()
  naming = named(location.hash)
  if (daemon() === was) return
  era += 1
  // What was read of the last daemon is not this one's: read again, once whoever leaves has.
  for (const read of reads.values()) Object.assign(read, { text: undefined, data: undefined, error: null, failures: 0, stale: true })
  setTimeout(() => {
    for (const read of reads.values()) if (read.stale) fetchNow(read)
  })
  for (const fn of [...switched]) fn(daemon())
  window.dispatchEvent(new CustomEvent('hmz:daemon', { detail: { daemon: daemon() } }))
})

/** A refusal: the server's own sentence, the status it came with, and what else it said. */
export class Refused extends Error {
  constructor(message, status, said = null) {
    super(message)
    this.status = status
    this.said = said || {}
  }
}

/** Reads one answer, or throws the server's sentence. */
export async function get(url) {
  return answered(await fetch(scoped(url), { headers: { Accept: 'application/json' } }))
}

/** Writes, sending JSON, and reads the answer, or throws the server's sentence. */
export async function post(url, body = {}) {
  return answered(
    await fetch(scoped(url), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

/** Sends a file as it is, under its name, and reads the answer, or throws the server's sentence. */
export async function send(url, file, kind) {
  return answered(
    await fetch(scoped(url), {
      method: 'POST',
      headers: { 'Content-Type': kind, 'X-Hmz-Filename': encodeURIComponent(file.name), Accept: 'application/json' },
      body: file,
    }),
  )
}

async function answered(response) {
  const text = await response.text()
  let said = null
  try {
    said = text ? JSON.parse(text) : null
  } catch {
    said = null
  }
  if (response.status === 401) window.dispatchEvent(new CustomEvent('hmz:out'))
  if (!response.ok) {
    throw new Refused((said && said.error) || text || `The server answered ${response.status}.`, response.status, said)
  }
  return said
}

/** Every address read again and again, with who is reading it. */
const reads = new Map()

/** The shortest a failed read waits before the next, and the longest. */
const SOON = 1600
const LONGEST = 30000

/**
 * Reads an address every so often for as long as something is watching it: once for all of
 * them, at the shortest interval any of them asked for, and not while the page is hidden. A
 * read that fails is tried again later and later, and whoever is watching keeps what it had.
 *
 * @param {string} url What to read.
 * @param {number|null} every How often, in milliseconds, or null for once.
 * @param {(data: any, error: Error|null) => void} told What is told each answer.
 * @returns {() => void} What stops watching.
 */
export function poll(url, every, told) {
  let read = reads.get(url)
  if (!read) {
    read = { url, watchers: new Set(), timer: 0, failures: 0, text: undefined, data: undefined, error: null }
    reads.set(url, read)
  }
  const watcher = { every, told }
  read.watchers.add(watcher)
  if (read.text !== undefined || read.error) told(read.data, read.error)
  if (read.watchers.size === 1 || read.text === undefined) fetchNow(read)
  else schedule(read)
  return () => {
    read.watchers.delete(watcher)
    if (!read.watchers.size) {
      clearTimeout(read.timer)
      reads.delete(url)
    }
  }
}

/** Reads an address again now, for whoever watches it: after a write that changed it. */
export function refresh(url) {
  for (const read of reads.values()) if (read.url === url || read.url.startsWith(`${url}?`)) fetchNow(read)
}

async function fetchNow(read) {
  clearTimeout(read.timer)
  read.stale = false
  // A page nobody looks at reads nothing again until looked at -- but what it has never read
  // it reads, so a page opened in a tab behind is drawn once it is looked at.
  if (document.hidden && read.text !== undefined) return
  const mine = era
  try {
    const response = await fetch(scoped(read.url), { headers: { Accept: 'application/json' } })
    const text = await response.text()
    if (mine !== era) return
    if (response.status === 401) window.dispatchEvent(new CustomEvent('hmz:out'))
    if (!response.ok) {
      let said = null
      try {
        said = JSON.parse(text)
      } catch {
        said = null
      }
      throw new Refused((said && said.error) || `The server answered ${response.status}.`, response.status)
    }
    read.failures = 0
    // An answer the same as the last is nothing new: nobody is told it again.
    if (text !== read.text || read.error) {
      read.text = text
      read.data = JSON.parse(text)
      read.error = null
      for (const watcher of read.watchers) watcher.told(read.data, null)
    }
  } catch (error) {
    if (mine !== era) return
    read.failures += 1
    read.error = error
    for (const watcher of read.watchers) watcher.told(read.data, error)
  }
  schedule(read)
}

function schedule(read) {
  clearTimeout(read.timer)
  if (!reads.has(read.url)) return
  let every = Infinity
  for (const watcher of read.watchers) if (watcher.every) every = Math.min(every, watcher.every)
  if (read.failures) every = Math.min(SOON * 2 ** (read.failures - 1), LONGEST)
  if (every !== Infinity) read.timer = setTimeout(() => fetchNow(read), every)
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) for (const read of reads.values()) fetchNow(read)
})

/** An address with the query given, leaving out what is empty. */
export function address(path, query = {}) {
  const params = new URLSearchParams()
  for (const [name, value] of Object.entries(query)) if (value !== '' && value !== undefined && value !== null) params.set(name, value)
  const said = params.toString()
  return said ? `${path}?${said}` : path
}
