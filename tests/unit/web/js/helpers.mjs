// Fakes the RPC client's tests share: an in-memory duplex of two pipes, a daemon that answers a
// few methods over one, a provider that opens pipes to it, and an IndexedDB held in memory.

import { Peer, Pipe, RpcError } from '../../../../src/hmz/web/static/rpc/index.js'

/** Two pipes, each carrying to the other, as a carrier would: asynchronously and in order. */
export function duplex() {
  /** @type {Pipe} */
  let a
  /** @type {Pipe} */
  let b
  a = new Pipe(
    (bytes) => queueMicrotask(() => b.feed(bytes.slice())),
    () => queueMicrotask(() => b.end('The other side closed.')),
  )
  b = new Pipe(
    (bytes) => queueMicrotask(() => a.feed(bytes.slice())),
    () => queueMicrotask(() => a.end('The other side closed.')),
  )
  return [a, b]
}

/** Resolves after `ms` milliseconds. */
export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** Resolves once `check` holds, looking every few milliseconds, or rejects after `ms`. */
export async function until(check, ms = 5000) {
  const end = Date.now() + ms
  while (!check()) {
    if (Date.now() > end) throw new Error('Waited too long.')
    await sleep(5)
  }
}

/**
 * A daemon with one epic and its notices, kept across sessions: every call it is made is in
 * `calls`, every session it served in `sessions`. `methods` adds or replaces methods.
 *
 * @param {{id?: string, methods?: Record<string, (params: object, peer: Peer) => unknown>}} [options]
 */
export function daemon({ id = 'a'.repeat(52), methods = {} } = {}) {
  const state = {
    id,
    epoch: 'e1',
    records: [],
    notices: [],
    /** @type {{method: string, params: object}[]} */
    calls: [],
    /** @type {{peer: Peer, subs: Map<string, string>}[]} */
    sessions: [],
    /** Adds a history record and sends it to every attached session. */
    record(text) {
      const record = { type: 'said', seq: state.records.length + 1, run: 1, text }
      state.records.push(record)
      for (const { peer, subs } of state.sessions)
        for (const [sub, kind] of subs) if (kind === 'epic' && peer.open) peer.notify('epic.event', { sub, message: record })
    },
    /** Adds a notice and sends it to every subscribed session. */
    notice(text) {
      const notice = { id: state.notices.length + 1, kind: 'done', text }
      state.notices.push(notice)
      for (const { peer, subs } of state.sessions)
        for (const [sub, kind] of subs) if (kind === 'notices' && peer.open) peer.notify('notices.event', { sub, notice })
    },
    /** Serves one session over `pipe`. */
    serve(pipe) {
      const subs = new Map()
      let next = 0
      const session = { peer: /** @type {Peer} */ (/** @type {unknown} */ (null)), subs }
      const own = {
        'session.hello': (params) => {
          if (params.protocol.split('.')[0] !== '3') throw new RpcError(426, 'held for frontends by a newer Humanize; `hmz` of it reads it', { protocol: '3.0.0' })
          return { daemon_id: state.id, version: '0.0.0', protocol: '3.0.0', capabilities: [], machine: 'here', wsl: null, newer: '', paired: true, device: 'local' }
        },
        echo: (params) => params,
        'epic.attach': (params, peer) => {
          const sub = `s${++next}`
          subs.set(sub, 'epic')
          setTimeout(() => {
            const since = params.since
            const from = since && since.epoch === state.epoch ? since.seq : 0
            const send = (message) => peer.notify('epic.event', { sub, message })
            send({ type: 'welcome', epoch: state.epoch, client: 'c', workspace: '/w', slot: '' })
            for (const record of state.records.slice(from)) send(record)
            send({ type: 'live', seq: state.records.length, elided: 0 })
          })
          return { sub, client: 'c', workspace: '/w', slot: '' }
        },
        'epic.detach': ({ sub }) => (subs.delete(sub), {}),
        'notices.subscribe': (params, peer) => {
          const sub = `s${++next}`
          subs.set(sub, 'notices')
          if (params.after !== undefined)
            setTimeout(() => {
              for (const notice of state.notices.slice(params.after)) peer.notify('notices.event', { sub, notice })
            })
          return { sub, last: state.notices.length }
        },
        'notices.unsubscribe': ({ sub }) => (subs.delete(sub), {}),
        ...methods,
      }
      session.peer = new Peer(pipe, {
        call: (method, params) => {
          state.calls.push({ method, params })
          const fn = own[method]
          if (!fn) throw new RpcError(-32601, `There is no method ${method}.`)
          return fn(params, session.peer)
        },
      })
      state.sessions.push(session)
      return session.peer
    },
  }
  return state
}

/**
 * A provider opening every route as a pipe to `served`, telling `opened` each route it opens and
 * `servers` the STUN and TURN servers it was given to open it with.
 */
export function provider(served, opened = [], servers = []) {
  return {
    opens: () => true,
    async open(route, id, { iceServers } = {}) {
      opened.push(route)
      servers.push(iceServers)
      const [mine, theirs] = duplex()
      served.serve(theirs)
      return mine
    },
  }
}

/**
 * An IndexedDB held in memory: as much of it as the registry uses. A base opened at a version
 * above the one it is at is upgraded first, in a transaction over every store of it, and is open
 * once that is over.
 */
export function fakeIndexedDB() {
  const bases = new Map()
  return {
    open(name, version = 1) {
      const asked = /** @type {any} */ ({})
      setTimeout(() => {
        const base = bases.get(name) ?? new FakeBase()
        bases.set(name, base)
        asked.result = base
        const opened = () => {
          asked.transaction = null
          asked.onsuccess?.()
        }
        if (base.version >= version) return opened()
        const oldVersion = base.version
        base.version = version
        asked.transaction = new FakeTransaction(base)
        asked.transaction.oncomplete = opened
        asked.onupgradeneeded?.({ oldVersion, newVersion: version })
      })
      return asked
    },
  }
}

class FakeBase {
  version = 0
  stores = new Map()
  createObjectStore(name, { keyPath } = {}) {
    this.stores.set(name, { keyPath, data: new Map() })
  }
  deleteObjectStore(name) {
    this.stores.delete(name)
  }
  get objectStoreNames() {
    return [...this.stores.keys()]
  }
  transaction() {
    return new FakeTransaction(this)
  }
}

class FakeTransaction {
  #base
  /** What each store it touched held before, to put back where it is aborted. */
  #before = new Map()
  #pending = 0
  #over = false
  error = null
  constructor(base) {
    this.#base = base
    this.#settle()
  }
  objectStore(name) {
    const store = this.#base.stores.get(name)
    if (!this.#before.has(store)) this.#before.set(store, new Map(store.data))
    const ask = (work) => {
      const asked = /** @type {any} */ ({})
      this.#pending++
      setTimeout(() => {
        this.#pending--
        if (this.#over) return
        asked.result = work()
        asked.onsuccess?.()
        this.#settle()
      })
      return asked
    }
    const key = (value, given) => (store.keyPath ? value[store.keyPath] : given)
    return {
      get: (k) => ask(() => structuredClone(store.data.get(k))),
      getAll: () => ask(() => [...store.data.keys()].sort().map((k) => structuredClone(store.data.get(k)))),
      put: (value, given) => ask(() => (store.data.set(key(value, given), structuredClone(value)), key(value, given))),
      add: (value, given) =>
        ask(() => {
          if (store.data.has(key(value, given))) throw new Error('ConstraintError')
          store.data.set(key(value, given), structuredClone(value))
          return key(value, given)
        }),
      delete: (k) => ask(() => void store.data.delete(k)),
    }
  }
  abort() {
    if (this.#over) return
    this.#over = true
    for (const [store, data] of this.#before) store.data = data
    setTimeout(() => this.onabort?.())
  }
  #settle() {
    setTimeout(() => {
      if (this.#over || this.#pending) return
      this.#over = true
      this.oncomplete?.()
    })
  }
}
