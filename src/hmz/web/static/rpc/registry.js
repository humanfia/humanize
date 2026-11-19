// The remote daemons the page keeps (Section 3.13 of protocol/web.md), in the browser's IndexedDB:
// each its name, the daemon id it pins and its routes in order, beside the STUN and TURN servers
// for WebRTC and the browser's DTLS certificate (Section 4.7.2 of protocol/wire.md). And pairing
// codes (Section 4.5), read and claimed to add a daemon.

import { fromBase64 } from './pipe.js'
import { reach } from './client.js'
import { routeKind } from './routes.js'

/** A daemon's name (Section 3.13.3 of protocol/web.md). */
const NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

/** A daemon id: an SPKI fingerprint, 52 characters of base32. */
const ID = /^[a-z2-7]{52}$/

/**
 * Refuses a remote daemon's name that is not one (Section 3.13.2 and 3.13.3 of protocol/web.md).
 *
 * @param {string} name
 */
function named(name) {
  if (typeof name !== 'string' || !NAME.test(name)) throw new Error(`${name} is not a daemon's name: start with a letter or a digit, then letters, digits, ., _ and -.`)
  if (name === 'local') throw new Error('local is Local\'s name.')
}

/** Refuses an entry whose routes are not routes. */
function routed(routes) {
  if (!Array.isArray(routes)) throw new Error('A daemon\'s routes are a list.')
  for (const route of routes) if (typeof route !== 'string' || !routeKind(route)) throw new Error(`${route} is not a route.`)
}

/** Local's one route, by where the page is shown (Section 4.9.1 and 4.9.2 of protocol/web.md). */
const LOCAL = /** @type {const} */ ({ web: 'unix:', macos: 'stdio:local', windows: 'stdio:wsl' })

/**
 * Where the page is shown: `web`, served by `hmz web`, or the desktop application on `macos` or
 * `windows`.
 *
 * @returns {keyof typeof LOCAL}
 */
function shown() {
  if (!(/** @type {any} */ (globalThis).__TAURI_INTERNALS__)) return 'web'
  return /^Win/.test(globalThis.navigator?.platform ?? '') ? 'windows' : 'macos'
}

/**
 * Local, the daemon of the machine the page is served from or shown on, as the page keeps it:
 * reached over `unix:` through `/rpc` in `hmz web`, and over `stdio:local` on macOS or
 * `stdio:wsl` on Windows in the desktop application (Section 3.5 of protocol/desktop.md), its id
 * pinned once first reached.
 *
 * @param {keyof typeof LOCAL} [where] Where the page is shown; found out where not given.
 * @returns {import('./client.js').DaemonEntry}
 */
export function local(where = shown()) {
  return { name: 'local', id: '', routes: [LOCAL[where]] }
}

/**
 * The page's keeping of remote daemons.
 *
 * @param {IDBFactory} [indexedDB]
 */
export function registry(indexedDB = globalThis.indexedDB) {
  /** @type {Promise<IDBDatabase> | null} */
  let base = null
  /**
   * Does `act` in one transaction, resolving with what it hands `done`, or rejecting with what it
   * hands `refuse`, which undoes the transaction.
   *
   * @param {string} name The store.
   * @param {IDBTransactionMode} mode
   * @param {(store: IDBObjectStore, done: (value: unknown) => void, refuse: (error: Error) => void) => void} act
   */
  function kept(name, mode, act) {
    base ||= new Promise((resolve, reject) => {
      const asked = indexedDB.open('hmz-daemons', 1)
      asked.onupgradeneeded = () => {
        asked.result.createObjectStore('daemons', { keyPath: 'name' })
        asked.result.createObjectStore('keys')
      }
      asked.onsuccess = () => resolve(asked.result)
      asked.onerror = () => reject(asked.error)
    })
    return base.then(
      (db) =>
        new Promise((resolve, reject) => {
          const doing = db.transaction(name, mode)
          let value
          let refused = null
          act(
            doing.objectStore(name),
            (got) => (value = got),
            (error) => {
              refused = error
              doing.abort()
            },
          )
          doing.oncomplete = () => resolve(value)
          doing.onabort = () => reject(refused ?? doing.error)
        }),
    )
  }
  /** @type {Promise<RTCCertificate> | null} The certificate, once asked: one, however many ask. */
  let certified = null
  /** What one request answered, handed to `then`. */
  const asked = (request, then) => (request.onsuccess = () => then(request.result))

  return {
    /** Every remote daemon, by name. @returns {Promise<import('./client.js').DaemonEntry[]>} */
    list: () => kept('daemons', 'readonly', (store, done) => asked(store.getAll(), done)),

    /** Keeps a new remote daemon, refusing a name already kept. @param {import('./client.js').DaemonEntry} entry */
    async add({ name, id, routes }) {
      named(name)
      routed(routes)
      return kept('daemons', 'readwrite', (store, done, refuse) =>
        asked(store.get(name), (got) => {
          if (got) refuse(new Error(`There is already a daemon ${name}.`))
          else asked(store.add({ name, id: id ?? '', routes: [...routes] }), done)
        }),
      )
    },

    /**
     * Changes a remote daemon: its id, its routes, or its name.
     *
     * @param {string} name
     * @param {{name?: string, id?: string, routes?: string[]}} changes
     */
    async update(name, changes) {
      if (changes.name !== undefined) named(changes.name)
      if (changes.routes !== undefined) routed(changes.routes)
      return kept('daemons', 'readwrite', (store, done, refuse) =>
        asked(store.get(name), (got) => {
          if (!got) return refuse(new Error(`There is no daemon ${name}.`))
          const now = { ...got, ...changes }
          const put = () => {
            if (now.name !== name) store.delete(name)
            asked(store.put(now), done)
          }
          if (now.name === name) put()
          else asked(store.get(now.name), (taken) => (taken ? refuse(new Error(`There is already a daemon ${now.name}.`)) : put()))
        }),
      )
    },

    /** Forgets how to reach a remote daemon. @param {string} name */
    remove: (name) => kept('daemons', 'readwrite', (store, done) => asked(store.delete(name), done)),

    /** The STUN and TURN servers WebRTC uses. @returns {Promise<RTCIceServer[]>} */
    iceServers: () => kept('keys', 'readonly', (store, done) => asked(store.get('ice'), (got) => done(got ?? []))),

    /** Keeps the STUN and TURN servers WebRTC uses. @param {RTCIceServer[]} servers */
    setIceServers: (servers) => kept('keys', 'readwrite', (store, done) => asked(store.put(servers, 'ice'), done)),

    /**
     * The browser's DTLS certificate: the one kept until it expires, else one made with `make`
     * and kept (Section 4.7.2 of protocol/wire.md).
     *
     * @param {() => Promise<RTCCertificate>} [make]
     * @returns {Promise<RTCCertificate>}
     */
    certificate(make = dtls) {
      const now = certified
      if (now) return now.then((held) => (held.expires > Date.now() ? held : ((certified = null), this.certificate(make))))
      certified = (async () => {
        const held = await kept('keys', 'readonly', (store, done) => asked(store.get('certificate'), done))
        if (held && held.expires > Date.now()) return held
        const made = await make()
        await kept('keys', 'readwrite', (store, done) => asked(store.put(made, 'certificate'), done))
        return made
      })()
      certified.catch(() => (certified = null))
      return certified
    },
  }
}

/** A DTLS certificate on ECDSA P-256 for as long as the browser allows: it caps what is asked. */
function dtls() {
  return RTCPeerConnection.generateCertificate(
    /** @type {any} */ ({ name: 'ECDSA', namedCurve: 'P-256', expires: 100 * 365 * 86400 * 1000 }),
  )
}

/**
 * Reads a pairing code (Section 4.5.2 of protocol/wire.md).
 *
 * @param {string} code
 * @returns {{v: 1, id: string, routes: string[], token: string, expires: number}}
 */
export function parsePairing(code) {
  const bad = new Error('That is not a pairing code.')
  const text = code.trim()
  if (!text.startsWith('hmz-pair:')) throw bad
  let read
  try {
    read = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(fromBase64(text.slice('hmz-pair:'.length))))
  } catch {
    throw bad
  }
  const keys = ['expires', 'id', 'routes', 'token', 'v']
  if (read === null || typeof read !== 'object' || Object.keys(read).sort().join() !== keys.join()) throw bad
  if (read.v !== 1 || typeof read.id !== 'string' || !ID.test(read.id) || typeof read.token !== 'string' || typeof read.expires !== 'number') throw bad
  if (!Array.isArray(read.routes) || !read.routes.every((route) => typeof route === 'string' && routeKind(route))) throw bad
  return read
}

/**
 * Adds a daemon from a pairing code (Section 4.5.7 of protocol/wire.md): reaches it over the
 * code's routes pinning the code's id, claims the code as `device`, and keeps the daemon as
 * `name` only once the claim succeeds. A P2P daemon's is claimed over `first`, its `easytier:`
 * route as this machine names it, in place of the code's own (Section 3.13.6 of protocol/web.md).
 *
 * @param {ReturnType<typeof registry>} store
 * @param {{name: string, code: string, device: string, first?: string}} asked `device` the name
 *   this browser is paired as.
 * @param {import('./client.js').Provider[]} providers
 * @param {{name: string, kind: string}} [client] As `session.hello` says it.
 * @returns {Promise<import('./client.js').DaemonEntry>}
 */
export async function claim(store, { name, code, device, first }, providers, client = { name: '', kind: 'web' }) {
  named(name)
  const { id, routes, token } = parsePairing(code)
  if ((await store.list()).some((one) => one.name === name)) throw new Error(`There is already a daemon ${name}.`)
  const entry = { name, id, routes: first ? [first, ...routes.filter((one) => routeKind(one) !== routeKind(first))] : routes }
  const session = await reach(entry, providers, { client })
  try {
    await session.peer.call('pair.claim', { token, name: device })
  } finally {
    session.peer.close('Claimed.')
  }
  await store.add(entry)
  return entry
}
