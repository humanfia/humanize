// How the page asks a daemon anything: one RPC client per daemon (rpc/index.js), Local's and each
// remote daemon's kept in this browser's IndexedDB (Section 3.13 of protocol/web.md), a wrapper
// that turns a refusal into the sentence the daemon gave, and one store for what is read again
// and again, shared by every view of it. Everything is asked of the daemon the address names --
// `#/@<name>/…`, Local where it names none -- unless the call names another.

import { bridge, claim, connect, ERRORS, local, registry, RpcError, tauri, webrtc } from './rpc/index.js'
import { fromBase64, toBase64 } from './rpc/pipe.js'
import { routeKind } from './rpc/routes.js'
import { t } from './i18n.js'

/** Where the page is shown: the desktop application's web view, or a browser. */
const DESKTOP = Boolean(globalThis.__TAURI_INTERNALS__)

/** What this page is to a daemon, as `session.hello` says it. */
const CLIENT = { name: '', kind: DESKTOP ? 'desktop' : 'web' }

/** The remote daemons this browser keeps, each with its STUN and TURN servers, and its WebRTC certificate. */
export const daemons = registry()

/** What opens a carrier for the page: the server's `/rpc` and `/dial`, or the app's pipes; and WebRTC. */
export const providers = [DESKTOP ? tauri() : bridge(), webrtc({ certificate: () => daemons.certificate() })]

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

/** The address of a view of the page, on the daemon the page is on, as the address names it. */
export function hash(path) {
  if (path.startsWith('#')) path = path.slice(1)
  if (path.startsWith('/@')) return `#${path}`
  return naming ? `#/@${encodeURIComponent(naming)}${path}` : `#${path}`
}

/** Switches the page to another daemon, on the view given, a new epic where none is. */
export function toDaemon(name, path = '/new/chat') {
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
  for (const read of reads.values()) if (!read.on) Object.assign(read, { text: undefined, data: undefined, error: null, failures: 0, stale: true })
  setTimeout(() => {
    for (const read of reads.values()) if (read.stale) readNow(read)
  })
  for (const fn of [...switched]) fn(daemon())
  window.dispatchEvent(new CustomEvent('hmz:daemon', { detail: { daemon: daemon() } }))
})

/** A refusal: the daemon's own sentence, the code it came with, and what else it said. */
export class Refused extends Error {
  constructor(message, status, said = null) {
    super(message)
    this.status = status
    this.said = said || {}
  }
}

/** Every daemon reached, by name. */
const clients = new Map()
/** Who is told each change of any daemon's state. */
const stateWatchers = new Set()

/**
 * The client of a daemon, by name: reached in the background from the first time it is asked for.
 *
 * @param {string} [name]
 * @returns {Promise<import('./rpc/client.js').Client>}
 */
export async function client(name = daemon()) {
  if (clients.has(name)) return clients.get(name)
  const entry = name === 'local' ? local() : (await daemons.list()).find((one) => one.name === name)
  if (!entry) throw new Refused(t('There is no daemon {name}.', { name }), ERRORS.NOT_FOUND)
  if (clients.has(name)) return clients.get(name)
  const made = connect(entry, providers, {
    client: CLIENT,
    // An id answered over a trusted route is pinned from then on (Section 3.8.2.7 of protocol/daemon.md).
    pinned: (id) => name !== 'local' && daemons.update(name, { id }).catch(() => {}),
  })
  clients.set(name, made)
  made.watch((state) => {
    // `/rpc` refused is seen only as closed: whether this browser is still let in, `/here` says.
    if (name === 'local' && !DESKTOP && state.state === 'failed') admitted()
    for (const fn of [...stateWatchers]) fn(name, state)
  })
  for (const fn of [...stateWatchers]) fn(name, made.state)
  return made
}

/** How a daemon stands now, `{state, detail}`: `idle` where it has not been asked for. */
export function stateOf(name) {
  return clients.get(name)?.state ?? { state: 'idle', detail: '' }
}

/** Tells `fn(name, state)` each change of any daemon's state, until what it returns is called. */
export function onState(fn) {
  stateWatchers.add(fn)
  return () => stateWatchers.delete(fn)
}

/**
 * What a daemon's `session.hello` answered -- its machine, `wsl`, version, `newer` -- once it is up.
 *
 * @param {string} [name]
 */
export async function hello(name = daemon()) {
  const one = await client(name)
  return new Promise((resolve, reject) => {
    const settles = (now) => {
      if (now.state === 'up' && one.hello) resolve(one.hello)
      // Failed, or let go of: whichever, not up.
      else if (now.state === 'failed' || now.state === 'idle') reject(refused(new RpcError(ERRORS.UNAVAILABLE, now.detail), name))
      else return false
      stop()
      return true
    }
    const stop = one.watch(settles)
    settles(one.state)
  })
}

/** Reaches a daemon again at once: one that failed, or one whose entry has changed. */
export async function reconnect(name) {
  forget(name)
  return client(name)
}

/** Stops reaching a daemon, and forgets its client: once it is removed or its entry changed. */
export function forget(name) {
  const held = clients.get(name)
  if (!held) return
  clients.delete(name)
  held.close()
  for (const fn of [...stateWatchers]) fn(name, { state: 'idle', detail: '' })
}

/** Local and every remote daemon this browser keeps, Local first. */
export async function known() {
  return [local(), ...(await daemons.list()).sort((one, other) => one.name.localeCompare(other.name))]
}

/** A remote daemon's kind, as the page names it (Section 3.13.18 of protocol/web.md). */
export function kindOf(entry) {
  const kind = routeKind(entry.routes[0] || '')
  return CARRIERS[kind] || kind || ''
}

/** What each kind of route a remote daemon is first reached over is called. */
const CARRIERS = { 'stdio:ssh': 'SSH', easytier: 'EasyTier', tcp: 'TCP', ws: 'WebSocket', relay: 'Relay', webrtc: 'WebRTC' }

/**
 * Adds a daemon from a pairing code, claiming it at once (Section 3.13.4 of protocol/web.md), as
 * the machine the page is served from is called, over `first` before the code's own routes
 * (Section 3.13.6); reached with, and then kept with, `ice`, its STUN and TURN servers (Section
 * 3.13.21).
 */
export async function pair(name, code, first, ice = []) {
  const device = (await hello('local').catch(() => null))?.machine || 'browser'
  try {
    return await claim(daemons, { name, code, device, first, ice }, providers, CLIENT)
  } catch (error) {
    throw refused(error, name)
  }
}

/** How a daemon is reached, as a failure to reach it says it. */
const STATES = { idle: t('idle@@link'), connecting: t('connecting'), installing: t('installing'), up: t('up'), failed: t('failed') }

/** A failure, said as the page says it: a refusal keeps its words, an unreachable daemon says so. */
function refused(error, name) {
  if (error instanceof Refused) return error
  if (error instanceof RpcError) {
    if (error.code === ERRORS.UNAVAILABLE && name !== 'local') {
      const { state: now, detail } = stateOf(name)
      const state = Object.hasOwn(STATES, now) ? STATES[now] : now
      return new Refused(detail ? t('{name} is unavailable, {state}: {detail}', { name, state, detail }) : t('{name} is unavailable, {state}.', { name, state }), error.code, error.data)
    }
    return new Refused(error.message, error.code, error.data)
  }
  return new Refused(error.message || String(error), ERRORS.UNAVAILABLE)
}

/**
 * Calls one method of a daemon, or throws its sentence as a `Refused`.
 *
 * @param {string} method
 * @param {object} [params]
 * @param {{on?: string, timeout?: number}} [options] `on` the daemon, the one shown by default.
 */
export async function call(method, params = {}, { on = daemon(), timeout } = {}) {
  try {
    return await (await client(on)).call(method, params, { timeout })
  } catch (error) {
    throw refused(error, on)
  }
}

/**
 * Attaches to one host of a daemon (`epic.attach`), telling `told` each message, and `ended`
 * where the subscription ended on its own.
 *
 * @returns {Promise<{close: () => Promise<void>}>}
 */
export async function attach(params, told, ended, { on = daemon() } = {}) {
  try {
    return await (await client(on)).attach(params, told, ended)
  } catch (error) {
    throw refused(error, on)
  }
}

/** Every call read again and again, with who is reading it. */
const reads = new Map()

/** The shortest a failed read waits before the next, and the longest. */
const SOON = 1600
const LONGEST = 30000

/**
 * Calls a method every so often for as long as something is watching it: once for all of them,
 * at the shortest interval any of them asked for, and not while the page is hidden. A call that
 * fails is tried again later and later, and whoever is watching keeps what it had.
 *
 * @param {string} method What to call.
 * @param {object} params With what.
 * @param {number|null} every How often, in milliseconds, or null for once.
 * @param {(data: any, error: Error|null) => void} told What is told each answer.
 * @param {{on?: string}} [options] `on` a daemon of its own, which a switch of the page leaves.
 * @returns {() => void} What stops watching.
 */
export function poll(method, params, every, told, { on } = {}) {
  const key = `${on ?? ''}\n${method}\n${JSON.stringify(params)}`
  let read = reads.get(key)
  if (!read) {
    read = { key, method, params, on, watchers: new Set(), timer: 0, failures: 0, text: undefined, data: undefined, error: null }
    reads.set(key, read)
  }
  const watcher = { every, told }
  read.watchers.add(watcher)
  if (read.text !== undefined || read.error) told(read.data, read.error)
  if (read.watchers.size === 1 || read.text === undefined) readNow(read)
  else schedule(read)
  return () => {
    read.watchers.delete(watcher)
    if (!read.watchers.size) {
      clearTimeout(read.timer)
      reads.delete(key)
    }
  }
}

/** Calls a method again now, for whoever watches it: after a write that changed what it answers. */
export function refresh(method) {
  for (const read of reads.values()) if (read.method === method) readNow(read)
}

async function readNow(read) {
  clearTimeout(read.timer)
  read.stale = false
  // A page nobody looks at reads nothing again until looked at -- but what it has never read
  // it reads, so a page opened in a tab behind is drawn once it is looked at.
  if (document.hidden && read.text !== undefined) return
  const mine = era
  try {
    const data = await call(read.method, read.params, { on: read.on })
    if (mine !== era && !read.on) return
    read.failures = 0
    const text = JSON.stringify(data)
    // An answer the same as the last is nothing new: nobody is told it again.
    if (text !== read.text || read.error) {
      read.text = text
      read.data = data
      read.error = null
      for (const watcher of read.watchers) watcher.told(read.data, null)
    }
  } catch (error) {
    if (mine !== era && !read.on) return
    read.failures += 1
    read.error = error
    for (const watcher of read.watchers) watcher.told(read.data, error)
  }
  schedule(read)
}

function schedule(read) {
  clearTimeout(read.timer)
  if (reads.get(read.key) !== read) return
  let every = Infinity
  for (const watcher of read.watchers) if (watcher.every) every = Math.min(every, watcher.every)
  if (read.failures) every = Math.min(SOON * 2 ** (read.failures - 1), LONGEST)
  if (every !== Infinity) read.timer = setTimeout(() => readNow(read), every)
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) for (const read of reads.values()) readNow(read)
})

/** Params with what is empty left out, as a method takes its defaults for what is not sent. */
export function given(params = {}) {
  const kept = {}
  for (const [name, value] of Object.entries(params)) if (value !== '' && value !== undefined && value !== null) kept[name] = value
  return kept
}

/** `/here`, the directory `hmz web` started in, or '' where the page is not served by it. */
let here = null
export function started() {
  here ||= admitted()
  return here
}

/** Asks `/here`, saying the browser is not let in where it is refused 401 (Section 3.3.3 of protocol/web.md). */
function admitted() {
  return fetch('/here', { headers: { Accept: 'application/json' } }).then(
    async (answer) => {
      if (answer.status === 401) window.dispatchEvent(new CustomEvent('hmz:out'))
      return answer.ok ? (await answer.json()).here || '' : ''
    },
    () => '',
  )
}

/** The most a chunk of a file carries (Section 6.9 of protocol/wire.md). */
const CHUNK = 1 << 20

/**
 * Downloads an epic as one archive (`runs.bundle` then `files.read`, Section 3.6.7.3 of
 * protocol/web.md), saving it as the daemon names it.
 *
 * @param {string} name The epic.
 * @param {{on?: string}} [options]
 */
export async function exported(name, { on = daemon() } = {}) {
  const { handle, filename, type } = await call('runs.bundle', { name }, { on })
  const parts = []
  try {
    for (let offset = 0; ; ) {
      const { data, eof } = await call('files.read', { handle, offset, length: CHUNK }, { on })
      const bytes = fromBase64(data)
      parts.push(bytes)
      offset += bytes.length
      if (eof) break
    }
  } finally {
    await call('files.close', { handle }, { on }).catch(() => {})
  }
  const url = URL.createObjectURL(new Blob(parts, { type }))
  const link = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

/**
 * Imports an exported epic into a daemon, sending it in chunks (`files.create`, `files.write` and
 * `runs.import`, Section 3.6.8.1 of protocol/web.md).
 *
 * @param {File} file
 * @param {{on?: string}} [options]
 */
export async function imported(file, { on = daemon() } = {}) {
  const { handle } = await call('files.create', { name: file.name, size: file.size }, { on })
  try {
    for (let offset = 0; offset < file.size; offset += CHUNK) {
      const bytes = new Uint8Array(await file.slice(offset, offset + CHUNK).arrayBuffer())
      await call('files.write', { handle, offset, data: toBase64(bytes) }, { on })
    }
  } catch (error) {
    // Not taken by `runs.import`: let go of here, with what it held.
    await call('files.close', { handle }, { on }).catch(() => {})
    throw error
  }
  return call('runs.import', { handle }, { on })
}
