// One JSON-RPC 2.0 session over a pipe (Section 6.4 of protocol/wire.md), either side of it: the
// calls it makes and their answers, the notifications it sends, and the calls and notifications
// the other side sends it. A session that closes fails every call still unanswered with `Dropped`.

import { t } from '../i18n.js'
import { encode, Frames, FrameError } from './frames.js'

const decoder = new TextDecoder('utf-8', { fatal: true })

/** What a frame that is JSON but no JSON-RPC 2.0 message is refused with (Section 6.4.1). */
const NOT_REQUEST = 'That is not a JSON-RPC 2.0 request.'

/** The error codes of Section 6.6.2 of protocol/wire.md. */
export const ERRORS = Object.freeze({
  PARSE: -32700,
  INVALID_REQUEST: -32600,
  NO_METHOD: -32601,
  INVALID_PARAMS: -32602,
  INTERNAL: -32603,
  CANCELLED: -32800,
  REFUSED: 400,
  NOT_PAIRED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  NO_SUBSCRIPTION: 410,
  TOO_LARGE: 413,
  PROTOCOL: 426,
  UPSTREAM: 502,
  UNAVAILABLE: 503,
})

/** An error a call was answered with, or one the session gave it. */
export class RpcError extends Error {
  /**
   * @param {number} code
   * @param {string} message
   * @param {object} [data]
   */
  constructor(code, message, data) {
    super(message)
    this.code = code
    this.data = data
  }
}

/** A call the session closed under before it was answered: it may or may not have been carried out. */
export class Dropped extends Error {}

/**
 * @typedef {object} Handlers What a peer does with what the other side sends it.
 * @property {(method: string, params: object, signal: AbortSignal) => unknown} [call] Answers a
 *   call; throws an `RpcError` to refuse it. Without it, every call is refused -32601.
 * @property {(method: string, params: object) => void} [notified] Told each notification but
 *   `session.cancel`.
 */

export class Peer {
  #pipe
  #frames = new Frames()
  #handlers
  #next = 1
  /** @type {Map<number, {resolve: (value: unknown) => void, reject: (error: Error) => void}>} */
  #pending = new Map()
  /** @type {Map<string | number, AbortController>} The other side's calls being answered. */
  #answering = new Map()
  /** @type {string | null} */
  #why = null
  /** @type {(why: string) => void} */
  #done = () => {}

  /**
   * @param {import('./pipe.js').Pipe} pipe
   * @param {Handlers} [handlers]
   */
  constructor(pipe, handlers = {}) {
    this.#pipe = pipe
    this.#handlers = handlers
    /** Resolves with why the session closed, once it has. */
    this.closed = new Promise((resolve) => (this.#done = resolve))
    pipe.listen(
      (bytes) => this.#read(bytes),
      (why) => this.#end(why),
    )
  }

  /** Whether the session is still open. */
  get open() {
    return this.#why === null
  }

  /**
   * Calls `method` and resolves with its result, or rejects with the `RpcError` it was answered
   * with, or `Dropped` where the session closed first. Given up after `timeout` milliseconds or
   * once `signal` aborts, after asking the other side to give it up with `session.cancel`.
   *
   * @param {string} method
   * @param {object} [params]
   * @param {{timeout?: number, signal?: AbortSignal}} [options]
   */
  call(method, params, { timeout, signal } = {}) {
    if (this.#why !== null) return Promise.reject(new Dropped(this.#why))
    if (signal?.aborted) return Promise.reject(new RpcError(ERRORS.CANCELLED, t('The call was cancelled.')))
    const id = this.#next++
    let frame
    try {
      frame = encode(params === undefined ? { jsonrpc: '2.0', id, method } : { jsonrpc: '2.0', id, method, params })
    } catch (error) {
      if (!(error instanceof FrameError)) throw error
      return Promise.reject(new RpcError(ERRORS.TOO_LARGE, t('That is more than a call here may carry.')))
    }
    return new Promise((resolve, reject) => {
      let timer
      const giveUp = () => {
        if (!this.#pending.delete(id)) return
        this.notify('session.cancel', { id })
        settled()
        reject(new RpcError(ERRORS.CANCELLED, t('The call was cancelled.')))
      }
      const settled = () => {
        clearTimeout(timer)
        signal?.removeEventListener('abort', giveUp)
      }
      this.#pending.set(id, {
        resolve: (value) => (settled(), resolve(value)),
        reject: (error) => (settled(), reject(error)),
      })
      if (timeout !== undefined) timer = setTimeout(giveUp, timeout)
      signal?.addEventListener('abort', giveUp, { once: true })
      this.#pipe.send(frame)
    })
  }

  /**
   * Sends a notification.
   *
   * @param {string} method
   * @param {object} [params]
   */
  notify(method, params) {
    this.#write(params === undefined ? { jsonrpc: '2.0', method } : { jsonrpc: '2.0', method, params })
  }

  /** Closes the session and its pipe. */
  close(why = 'closed') {
    this.#pipe.close(why)
  }

  #write(message) {
    if (this.#why === null) this.#pipe.send(encode(message))
  }

  #read(bytes) {
    for (const payload of this.#frames.push(bytes)) {
      if (this.#why !== null) return
      let message
      try {
        message = JSON.parse(decoder.decode(payload))
      } catch {
        this.#write({ jsonrpc: '2.0', id: null, error: { code: ERRORS.PARSE, message: 'Send JSON.' } })
        continue
      }
      this.#take(message)
    }
    if (this.#frames.broken !== null) this.close(this.#frames.broken)
  }

  /** Takes one message (Section 6.4.1 and 6.4.3): a call, a notification or a response. */
  #take(message) {
    if (Array.isArray(message)) return this.#refuse(null, 'Send one request a frame.')
    if (message === null || typeof message !== 'object' || message.jsonrpc !== '2.0') return this.#refuse(null, NOT_REQUEST)
    if ('method' in message) {
      const params = 'params' in message ? message.params : {}
      const formed = typeof message.method === 'string' && params !== null && typeof params === 'object' && !Array.isArray(params)
      if (!('id' in message)) {
        if (!formed) return
        if (message.method === 'session.cancel') this.#answering.get(params.id)?.abort()
        else this.#handlers.notified?.(message.method, params)
        return
      }
      const id = message.id
      if (typeof id !== 'string' && !Number.isInteger(id)) return this.#refuse(null, NOT_REQUEST)
      // A refusal with the id of a call still unanswered would answer it (Section 6.4.3).
      if (this.#answering.has(id)) return this.#refuse(null, 'That id is in use by another call.')
      if (!formed) return this.#refuse(id, NOT_REQUEST)
      return this.#answer(id, message.method, params)
    }
    if (!('id' in message) || !('result' in message || 'error' in message)) return this.#refuse(null, NOT_REQUEST)
    // A response that answers no call still unanswered is dropped.
    const pending = this.#pending.get(message.id)
    if (!pending) return
    this.#pending.delete(message.id)
    if (message.error) pending.reject(new RpcError(message.error.code, message.error.message, message.error.data))
    else pending.resolve(message.result)
  }

  /** Refuses a frame -32600 (Section 6.4.1). @param {string | number | null} id @param {string} why */
  #refuse(id, why) {
    this.#write({ jsonrpc: '2.0', id, error: { code: ERRORS.INVALID_REQUEST, message: why } })
  }

  async #answer(id, method, params) {
    if (!this.#handlers.call) {
      this.#write({ jsonrpc: '2.0', id, error: { code: ERRORS.NO_METHOD, message: `There is no method ${method}.` } })
      return
    }
    const abort = new AbortController()
    this.#answering.set(id, abort)
    const cancelled = new Promise((resolve) => abort.signal.addEventListener('abort', resolve, { once: true }))
    let answer
    try {
      const result = await Promise.race([this.#handlers.call(method, params, abort.signal), cancelled])
      answer = abort.signal.aborted
        ? { error: { code: ERRORS.CANCELLED, message: 'The call was cancelled.' } }
        : { result: result ?? {} }
    } catch (error) {
      answer =
        error instanceof RpcError
          ? { error: error.data === undefined ? { code: error.code, message: error.message } : { code: error.code, message: error.message, data: error.data } }
          : { error: { code: ERRORS.INTERNAL, message: `Something went wrong here: ${error?.message ?? error}` } }
    }
    this.#answering.delete(id)
    try {
      this.#write({ jsonrpc: '2.0', id, ...answer })
    } catch (error) {
      if (!(error instanceof FrameError)) throw error
      this.#write({ jsonrpc: '2.0', id, error: { code: ERRORS.TOO_LARGE, message: 'That is more than an answer here may carry.' } })
    }
  }

  #end(why) {
    if (this.#why !== null) return
    this.#why = why
    for (const pending of this.#pending.values()) pending.reject(new Dropped(why))
    this.#pending.clear()
    for (const abort of this.#answering.values()) abort.abort()
    this.#done(why)
  }
}
