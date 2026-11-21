// The remote daemons the page keeps (Section 3.13 of protocol/web.md), in the browser's IndexedDB:
// each its name, the daemon id it pins, its routes in order and the STUN and TURN servers its
// `webrtc:` routes are opened with, beside the browser's DTLS certificate (Section 4.7.2 of
// protocol/wire.md). And pairing codes (Section 4.5), read and claimed to add a daemon.

import { t } from '../i18n.js'
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
  if (typeof name !== 'string' || !NAME.test(name)) throw new Error(t('{name} is not a daemon\'s name: start with a letter or a digit, then letters, digits, ., _ and -.', { name }))
  if (name === 'local') throw new Error(t('local is Local\'s name.'))
}

/** Refuses an entry whose routes are not routes. */
function routed(routes) {
  if (!Array.isArray(routes)) throw new Error(t('A daemon\'s routes are a list.'))
  for (const route of routes) if (typeof route !== 'string' || !routeKind(route)) throw new Error(t('{route} is not a route.', { route }))
}

/** A STUN or TURN server's URL, as WebRTC takes one. */
const ICE = /^(stun|stuns|turn|turns):\S+$/

/**
 * Refuses STUN and TURN servers that are not ones: each its `urls`, one or a list, and for a TURN
 * server the `username` and `credential` it is used with, as Section 3.4.9.1 of protocol/files.md
 * writes them.
 */
function iced(servers) {
  if (!Array.isArray(servers)) throw new Error(t('A daemon\'s STUN and TURN servers are a list.'))
  for (const one of servers) {
    const urls = one === null || typeof one !== 'object' ? [] : [].concat(one.urls ?? [])
    if (!urls.length) throw new Error(t('A STUN or TURN server needs its URL.'))
    for (const url of urls) if (typeof url !== 'string' || !ICE.test(url)) throw new Error(t('{url} is not a STUN or TURN server.', { url }))
    for (const key of ['username', 'credential']) if (one[key] !== undefined && typeof one[key] !== 'string') throw new Error(t('A STUN or TURN server\'s {key} is text.', { key }))
  }
}

/** An entry as it is kept: its STUN and TURN servers only where it has any. */
function entered({ ice, ...rest }) {
  return ice?.length ? { ...rest, ice: ice.map((one) => ({ ...one })) } : rest
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
      const asked = indexedDB.open('hmz-daemons', 2)
      /** Whether whoever asked was already told it could not be opened. */
      let refused = false
      asked.onupgradeneeded = (event) => {
        if (event.oldVersion < 1) {
          asked.result.createObjectStore('daemons', { keyPath: 'name' })
          asked.result.createObjectStore('keys')
          return
        }
        // Version 1 kept one list of STUN and TURN servers for every daemon, under `ice` among the
        // keys: each daemon with a `webrtc:` route keeps it as its own from here on (Section
        // 3.13.1 of protocol/web.md), and the one list is gone.
        const keys = asked.transaction.objectStore('keys')
        const daemons = asked.transaction.objectStore('daemons')
        const read = keys.get('ice')
        read.onsuccess = () => {
          const servers = read.result
          keys.delete('ice')
          if (!Array.isArray(servers) || !servers.length) return
          const all = daemons.getAll()
          all.onsuccess = () => {
            for (const one of all.result) if (!one.ice?.length && one.routes.some((route) => routeKind(route) === 'webrtc')) daemons.put({ ...one, ice: servers })
          }
        }
      }
      // Another tab holds it as an earlier version kept it, and does not let go: said, where it
      // would otherwise be waited for with nothing shown, and asked for again by whoever asks next.
      asked.onblocked = () => {
        refused = true
        base = null
        reject(new Error(t('Another tab of this page is open on an earlier version: close or reload it.')))
      }
      asked.onsuccess = () => {
        const db = asked.result
        // Opened after all, once that tab went: nobody waits for this one any more.
        if (refused) return db.close()
        // A later version asks for it from another tab: let go, and opened again by the next use.
        db.onversionchange = () => {
          db.close()
          base = null
        }
        resolve(db)
      }
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
    async add({ name, id, routes, ice = [] }) {
      named(name)
      routed(routes)
      iced(ice)
      return kept('daemons', 'readwrite', (store, done, refuse) =>
        asked(store.get(name), (got) => {
          if (got) refuse(new Error(t('There is already a daemon {name}.', { name })))
          else asked(store.add(entered({ name, id: id ?? '', routes: [...routes], ice })), done)
        }),
      )
    },

    /**
     * Changes a remote daemon: its id, its routes, its STUN and TURN servers, or its name.
     *
     * @param {string} name
     * @param {{name?: string, id?: string, routes?: string[], ice?: RTCIceServer[]}} changes
     */
    async update(name, changes) {
      if (changes.name !== undefined) named(changes.name)
      if (changes.routes !== undefined) routed(changes.routes)
      if (changes.ice !== undefined) iced(changes.ice)
      return kept('daemons', 'readwrite', (store, done, refuse) =>
        asked(store.get(name), (got) => {
          if (!got) return refuse(new Error(t('There is no daemon {name}.', { name })))
          const now = entered({ ...got, ...changes })
          const put = () => {
            if (now.name !== name) store.delete(name)
            asked(store.put(now), done)
          }
          if (now.name === name) put()
          else asked(store.get(now.name), (taken) => (taken ? refuse(new Error(t('There is already a daemon {name}.', { name: now.name }))) : put()))
        }),
      )
    },

    /** Forgets how to reach a remote daemon. @param {string} name */
    remove: (name) => kept('daemons', 'readwrite', (store, done) => asked(store.delete(name), done)),

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
  const bad = new Error(t('That is not a pairing code.'))
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
 * `name` only once the claim succeeds. Where `first` is given -- an address typed, or an EasyTier
 * daemon's `easytier:` route as this machine names it -- it is tried first, in place of the code's
 * routes of its kind (Section 3.13.4 and 3.13.6 of protocol/web.md).
 * It is reached with `ice`, the STUN and TURN servers it is then kept with (Section 3.13.21).
 *
 * @param {ReturnType<typeof registry>} store
 * @param {{name: string, code: string, device: string, first?: string, ice?: RTCIceServer[]}} asked
 *   `device` the name this browser is paired as.
 * @param {import('./client.js').Provider[]} providers
 * @param {{name: string, kind: string}} [client] As `session.hello` says it.
 * @returns {Promise<import('./client.js').DaemonEntry>}
 */
export async function claim(store, { name, code, device, first, ice = [] }, providers, client = { name: '', kind: 'web' }) {
  named(name)
  iced(ice)
  const { id, routes, token } = parsePairing(code)
  if ((await store.list()).some((one) => one.name === name)) throw new Error(t('There is already a daemon {name}.', { name }))
  const entry = entered({ name, id, routes: first ? [first, ...routes.filter((one) => routeKind(one) !== routeKind(first))] : routes, ice })
  const session = await reach(entry, providers, { client })
  try {
    await session.peer.call('pair.claim', { token, name: device })
  } finally {
    session.peer.close(t('Claimed.'))
  }
  await store.add(entry)
  return entry
}
