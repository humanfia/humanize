// One daemon as the page reaches it (Sections 3.6 and 6 of protocol/wire.md): its routes raced
// through the pipe providers the page has, `session.hello` said and the daemon id checked against
// the one pinned, the session tried again with backoff whenever it drops or fails, every
// subscription attached again with `since` once it is back, and every write given an `idem`.

import { Dropped, ERRORS, Peer, RpcError } from './peer.js'
import { onAbort, toBase64url } from './pipe.js'
import { race, routeKind, trusted } from './routes.js'
import { WRITES } from './writes.js'

/** The protocol version this client speaks (Section 6.5.1). */
export const PROTOCOL = '3.0.0'

/** How long a carrier and its `session.hello` may take, but while hmz is installed (Section 3.4.9). */
const OPENING = 30000

/** The first wait before trying a daemon again, and the longest (Section 3.6.4). */
const FIRST = 1000
const LONGEST = 60000

/** Why an epic subscription that fell behind ended (Section 6.10.1). */
const BEHIND = 'too far behind; attach again'

/** What a provider throws where the daemon at the other end is not the one pinned. */
export class NotPinned extends Error {}

/**
 * @typedef {object} DaemonEntry A daemon as the page keeps it (Section 3.8.1 of protocol/daemon.md).
 * @property {string} name
 * @property {string} id The daemon id pinned, '' until first reached over a trusted carrier.
 * @property {string[]} routes In the order they are tried.
 * @property {RTCIceServer[]} [ice] The STUN and TURN servers its `webrtc:` routes are opened
 *   with (Section 3.13.21 of protocol/web.md); none where absent.
 *
 * @typedef {object} Provider What opens carriers of some routes for the page.
 * @property {(route: string) => boolean} opens Whether it opens this route.
 * @property {(route: string, id: string, options: {state: (state: string, detail: string) => void,
 *   signal: AbortSignal, iceServers: RTCIceServer[]}) => Promise<import('./pipe.js').Pipe>} open
 *   Opens one, telling `state` `connecting` or `installing` and what was said last until it is
 *   open; closes it and rejects once `signal` aborts. `iceServers` are the daemon's own STUN and
 *   TURN servers, which a provider of `webrtc:` routes alone uses.
 *
 * @typedef {object} Session
 * @property {Peer} peer
 * @property {object} hello What `session.hello` answered.
 * @property {string} route The route it is over.
 * @property {{notified?: (method: string, params: object) => void}} handlers
 */

/** A fresh `idem` (Section 6.7.1): 16 random bytes in base64url. */
export function idem() {
  return toBase64url(crypto.getRandomValues(new Uint8Array(16)))
}

/**
 * Races a daemon's routes once and resolves with the first session whose `session.hello` answers
 * the daemon id pinned (Section 3.6.2), or rejects with the failure of the last route to fail.
 *
 * @param {DaemonEntry} entry
 * @param {Provider[]} providers
 * @param {{client?: {name: string, kind: string}, state?: (state: string, detail: string) => void,
 *   handlers?: Session['handlers']}} [options]
 * @returns {Promise<Session>}
 */
export function reach(entry, providers, { client = { name: '', kind: 'web' }, state = () => {}, handlers } = {}) {
  return race(entry.routes, attempt, (session) => session.peer.close('Another route was reached first.'))

  /** @param {string} route @param {AbortSignal} signal */
  async function attempt(route, signal) {
    if (!routeKind(route)) throw new Error(`${route} is not a route.`)
    const provider = providers.find((one) => one.opens(route))
    if (!provider) throw new Error(`${route} cannot be reached from here.`)
    // An id is pinned from a trusted carrier alone (Section 3.5.6 and 4.4.7 of protocol/wire.md).
    if (!entry.id && !trusted(route)) throw new Error(`${route} needs the id of the daemon it reaches.`)
    const late = new AbortController()
    let timer
    const arm = () => {
      clearTimeout(timer)
      timer = setTimeout(() => late.abort(), OPENING)
    }
    arm()
    const both = AbortSignal.any([signal, late.signal])
    let installing = false
    let stop = () => {}
    /** @type {Peer | null} */
    let peer = null
    try {
      const pipe = await provider.open(route, entry.id, {
        signal: both,
        iceServers: entry.ice ?? [],
        state: (now, detail) => {
          // The 30 seconds wait while hmz is installed, and start afresh after.
          if (now === 'installing') clearTimeout(timer)
          else if (installing) arm()
          installing = now === 'installing'
          state(now, detail)
        },
      })
      peer = new Peer(pipe, handlers ?? {})
      const opened = peer
      stop = onAbort(both, () => opened.close('Given up.'))
      if (installing) arm()
      const hello = /** @type {{daemon_id: string}} */ (await peer.call('session.hello', { protocol: PROTOCOL, client }))
      if (entry.id && hello.daemon_id !== entry.id) throw new NotPinned()
      return { peer, hello, route, handlers: handlers ?? {} }
    } catch (error) {
      peer?.close('Not reached.')
      if (error instanceof NotPinned) throw new Error(`${entry.name} is not the daemon it was paired with.`)
      if (late.signal.aborted) throw new Error(`${route} did not open within 30 seconds.`)
      throw error
    } finally {
      clearTimeout(timer)
      stop()
    }
  }
}

/**
 * Reaches a daemon, and keeps reaching it until closed.
 *
 * @param {DaemonEntry} entry
 * @param {Provider[]} providers
 * @param {{client?: {name: string, kind: string}, pinned?: (id: string) => void}} [options]
 *   `client` as `session.hello` says it; `pinned`, told the daemon id first answered over a
 *   trusted carrier where `entry` pins none, to keep it.
 */
export function connect(entry, providers, options = {}) {
  return new Client(entry, providers, options)
}

/**
 * @typedef {object} Subscription
 * @property {string | null} sub Its `sub` on the session it is open on now.
 * @property {() => Promise<void>} close Detaches or unsubscribes.
 */

export class Client {
  #entry
  #providers
  #options
  /** @type {Session | null} */
  #session = null
  #state = { state: 'idle', detail: '' }
  /** @type {Set<(state: {state: string, detail: string}) => void>} */
  #watchers = new Set()
  /** @type {Set<{resolve: (session: Session) => void, reject: (error: Error) => void}>} */
  #waiting = new Set()
  /** @type {Set<object>} Every subscription held. */
  #subs = new Set()
  #closed = false
  #wake = () => {}

  /**
   * @param {DaemonEntry} entry
   * @param {Provider[]} providers
   * @param {{client?: {name: string, kind: string}, pinned?: (id: string) => void}} options
   */
  constructor(entry, providers, options) {
    this.#entry = { ...entry }
    this.#providers = providers
    this.#options = options
    this.#run()
  }

  /** The daemon's state (Section 3.8.2.2 of protocol/daemon.md) and what was said last. */
  get state() {
    return this.#state
  }

  /** What `session.hello` answered on the session up now, or null. */
  get hello() {
    return this.#session?.hello ?? null
  }

  /**
   * Tells `fn` the state each time it changes, until what it returns is called.
   *
   * @param {(state: {state: string, detail: string}) => void} fn
   */
  watch(fn) {
    this.#watchers.add(fn)
    return () => this.#watchers.delete(fn)
  }

  /**
   * Calls a method once the session is up. A write is given a fresh `idem` unless it carries one,
   * and is sent again with it, once, on the next session where the session drops under it.
   * Rejects with 503 at once where the daemon is `failed`.
   *
   * @param {string} method
   * @param {object} [params]
   * @param {{timeout?: number, signal?: AbortSignal}} [options]
   */
  async call(method, params, { timeout, signal } = {}) {
    if (WRITES.has(method) && params?.idem === undefined) params = { ...params, idem: idem() }
    const signals = [signal, timeout === undefined ? undefined : AbortSignal.timeout(timeout)].filter((one) => one !== undefined)
    const until = signals.length ? AbortSignal.any(signals) : undefined
    for (let retried = false; ; retried = true) {
      const session = await this.#ready(until)
      try {
        return await session.peer.call(method, params, { signal: until })
      } catch (error) {
        if (!(error instanceof Dropped) || retried || params?.idem === undefined) throw error
      }
    }
  }

  /**
   * Attaches to an epic (`epic.attach`, Section 4.7.1 of protocol/daemon.md), telling `told` each
   * message of it, and attaches again with `since` after each reconnection.
   *
   * @param {object} params Those of `epic.attach`.
   * @param {(message: object) => void} told
   * @param {(why: string) => void} [ended] Told where the subscription ended on its own: `gone`, or
   *   an attach again refused.
   * @returns {Promise<Subscription>}
   */
  attach(params, told, ended) {
    return this.#subscribe({ kind: 'epic', params, told, ended, epoch: null, seq: null })
  }

  /**
   * Follows the daemon's notices (`notices.subscribe`, Section 4.19.2 of protocol/daemon.md),
   * telling `told` each, and subscribes again after the last heard after each reconnection, and
   * where it fell behind.
   *
   * @param {(notice: object) => void} told
   * @param {{after?: number}} [params]
   * @returns {Promise<Subscription>}
   */
  notices(told, params = {}) {
    return this.#subscribe({ kind: 'notices', params, told, ended: undefined, last: params.after ?? null })
  }

  /** Closes the session and stops reaching the daemon. */
  close() {
    if (this.#closed) return
    this.#closed = true
    this.#wake()
    this.#session?.peer.close('Closed.')
    this.#session = null
    for (const waiter of this.#waiting) waiter.reject(new Dropped('Closed.'))
    this.#waiting.clear()
    this.#subs.clear()
    this.#set('idle', '')
  }

  async #run() {
    let wait = FIRST
    while (!this.#closed) {
      this.#set('connecting', this.#state.detail)
      /** @type {Session['handlers'] & {subs: Map<string, object>, early: Map<string, object[]>}} */
      const handlers = { subs: new Map(), early: new Map() }
      handlers.notified = (method, params) => this.#notified(handlers, method, params)
      try {
        const session = await reach(this.#entry, this.#providers, {
          client: this.#options.client,
          state: (state, detail) => this.#set(state, detail),
          handlers,
        })
        if (this.#closed) {
          session.peer.close('Closed.')
          return
        }
        if (!this.#entry.id) {
          this.#entry.id = /** @type {{daemon_id: string}} */ (session.hello).daemon_id
          this.#options.pinned?.(this.#entry.id)
        }
        wait = FIRST
        this.#session = session
        this.#set('up', '')
        for (const waiter of this.#waiting) waiter.resolve(session)
        this.#waiting.clear()
        await Promise.all([...this.#subs].map((one) => this.#resume(one, session)))
        const why = await session.peer.closed
        this.#session = null
        if (this.#closed) return
        this.#set('connecting', why)
      } catch (error) {
        if (this.#closed) return
        this.#set('failed', error.message)
        const refused = new RpcError(ERRORS.UNAVAILABLE, error.message)
        for (const waiter of this.#waiting) waiter.reject(refused)
        this.#waiting.clear()
        // A client refused for its version calls nothing more (Section 6.5.7).
        if (error instanceof RpcError && error.code === ERRORS.PROTOCOL) return
      }
      await new Promise((resolve) => {
        const timer = setTimeout(resolve, wait)
        this.#wake = () => (clearTimeout(timer), resolve(undefined))
      })
      wait = Math.min(wait * 2, LONGEST)
    }
  }

  /** @param {AbortSignal} [signal] @returns {Promise<Session>} */
  #ready(signal) {
    if (this.#closed) return Promise.reject(new Dropped('Closed.'))
    if (this.#session?.peer.open) return Promise.resolve(this.#session)
    if (this.#state.state === 'failed') return Promise.reject(new RpcError(ERRORS.UNAVAILABLE, this.#state.detail))
    return new Promise((resolve, reject) => {
      const waiter = {
        resolve: (session) => (stop(), resolve(session)),
        reject: (error) => (stop(), reject(error)),
      }
      const stop = onAbort(signal, () => {
        this.#waiting.delete(waiter)
        reject(new RpcError(ERRORS.CANCELLED, 'The call was cancelled.'))
      })
      this.#waiting.add(waiter)
    })
  }

  async #subscribe(one) {
    const session = await this.#ready()
    await this.#open(one, session)
    this.#subs.add(one)
    return {
      get sub() {
        return one.sub
      },
      close: async () => {
        if (!this.#subs.delete(one)) return
        const now = this.#session
        if (!now || now !== one.session || !now.peer.open) return
        now.handlers.subs.set(one.sub, null)
        await now.peer.call(one.kind === 'epic' ? 'epic.detach' : 'notices.unsubscribe', { sub: one.sub }).catch(() => {})
      },
    }
  }

  /** Opens a subscription on a session, resuming where it left off (Section 6.8.4 and 6.8.5). */
  async #open(one, session) {
    let params = one.params
    if (one.kind === 'epic' && one.epoch !== null && one.seq !== null) params = { ...params, since: { epoch: one.epoch, seq: one.seq } }
    if (one.kind === 'notices' && one.last !== null) params = { after: one.last }
    const result = /** @type {{sub: string, last?: number}} */ (
      await session.peer.call(one.kind === 'epic' ? 'epic.attach' : 'notices.subscribe', params)
    )
    if (one.kind === 'notices' && one.last === null) one.last = result.last ?? null
    if (one.kind === 'epic') {
      // Attached again, it is to the slot attached to, not to a new slot or scratch directory.
      const { scratch, since, ...kept } = one.params
      one.params = { ...kept, workspace: result.workspace, slot: result.slot }
    }
    one.sub = result.sub
    one.session = session
    const handlers = /** @type {any} */ (session.handlers)
    handlers.subs.set(result.sub, one)
    const early = handlers.early.get(result.sub) ?? []
    handlers.early.delete(result.sub)
    for (const params of early) this.#deliver(handlers, one, params)
  }

  async #resume(one, session) {
    try {
      await this.#open(one, session)
    } catch (error) {
      if (error instanceof Dropped) return
      this.#subs.delete(one)
      one.ended?.(error.message)
    }
  }

  /** Tells each event to its subscription; an event of a `sub` not yet answered waits for it. */
  #notified(handlers, method, params) {
    if (method !== 'epic.event' && method !== 'notices.event') return
    if (handlers.subs.has(params.sub)) {
      const one = handlers.subs.get(params.sub)
      if (one) this.#deliver(handlers, one, params)
    } else if (handlers.early.has(params.sub)) handlers.early.get(params.sub).push(params)
    else handlers.early.set(params.sub, [params])
  }

  #deliver(handlers, one, params) {
    const behind = one.kind === 'epic' ? params.message.type === 'gone' && params.message.why === BEHIND : params.gone !== undefined
    if (behind) {
      // Fallen behind: attached again with `since`, or subscribed again after the last heard
      // (Section 6.10.1).
      handlers.subs.set(params.sub, null)
      if (this.#session) this.#resume(one, this.#session)
      return
    }
    if (one.kind === 'epic') {
      const message = params.message
      if (message.type === 'welcome') one.epoch = message.epoch
      if (typeof message.seq === 'number') one.seq = message.seq
      one.told(message)
      if (message.type === 'gone') {
        handlers.subs.set(params.sub, null)
        if (this.#subs.delete(one)) one.ended?.(message.why)
      }
      return
    }
    if (typeof params.notice?.id === 'number') one.last = params.notice.id
    one.told(params.notice)
  }

  #set(state, detail) {
    if (this.#state.state === state && this.#state.detail === detail) return
    this.#state = { state, detail }
    for (const fn of this.#watchers) fn(this.#state)
  }
}
