// A pipe: one carrier as the page holds it, whichever provider opened it -- the bytes it carries
// each way, in order, until either side closes it. A provider feeds it what the carrier brings and
// ends it when the carrier closes; the session reads it through `listen`.

export class Pipe {
  #send
  #close
  /** @type {Uint8Array[]} What came before anyone listened. */
  #early = []
  /** @type {((bytes: Uint8Array) => void) | null} */
  #ondata = null
  /** @type {((why: string) => void) | null} */
  #onclose = null
  /** @type {string | null} Why it ended, once it has. */
  #ended = null

  /**
   * @param {(bytes: Uint8Array) => void} send Carries bytes to the other side.
   * @param {() => void} close Closes the carrier.
   */
  constructor(send, close) {
    this.#send = send
    this.#close = close
  }

  /** Whether the pipe has ended. */
  get ended() {
    return this.#ended !== null
  }

  /** @param {Uint8Array} bytes */
  send(bytes) {
    if (this.#ended === null) this.#send(bytes)
  }

  /** Closes the carrier, and ends the pipe for `why`. */
  close(why = 'closed') {
    if (this.#ended !== null) return
    this.end(why)
    this.#close()
  }

  /**
   * Tells `ondata` every byte the carrier brings, those already come first, and `onclose` once.
   *
   * @param {(bytes: Uint8Array) => void} ondata
   * @param {(why: string) => void} onclose
   */
  listen(ondata, onclose) {
    this.#ondata = ondata
    this.#onclose = onclose
    for (const bytes of this.#early.splice(0)) ondata(bytes)
    if (this.#ended !== null) onclose(this.#ended)
  }

  /** For the provider: bytes the carrier brought. */
  feed(bytes) {
    if (this.#ended !== null) return
    if (this.#ondata) this.#ondata(bytes)
    else this.#early.push(bytes)
  }

  /** For the provider: the carrier closed, for `why`. */
  end(why) {
    if (this.#ended !== null) return
    this.#ended = why || 'closed'
    this.#onclose?.(this.#ended)
  }
}

/**
 * Bytes as base64 with padding.
 *
 * @param {Uint8Array} bytes
 */
export function toBase64(bytes) {
  let text = ''
  for (let at = 0; at < bytes.length; at += 0x8000) text += String.fromCharCode(...bytes.subarray(at, at + 0x8000))
  return btoa(text)
}

/**
 * The bytes of base64 or base64url, with or without padding.
 *
 * @param {string} text
 */
export function fromBase64(text) {
  const plain = atob(text.replace(/-/g, '+').replace(/_/g, '/'))
  const bytes = new Uint8Array(plain.length)
  for (let at = 0; at < plain.length; at++) bytes[at] = plain.charCodeAt(at)
  return bytes
}

/** Bytes as base64url without padding. */
export function toBase64url(bytes) {
  return toBase64(bytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Bytes as base32 (Section 6 of RFC 4648) in lowercase, without padding. */
export function toBase32(bytes) {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz234567'
  let out = ''
  let bits = 0
  let value = 0
  for (const byte of bytes) {
    value = (value << 8) | byte
    bits += 8
    while (bits >= 5) {
      out += alphabet[(value >>> (bits - 5)) & 31]
      bits -= 5
    }
    value &= (1 << bits) - 1
  }
  if (bits) out += alphabet[(value << (5 - bits)) & 31]
  return out
}

/**
 * Calls `stop` once `signal` is aborted, at once where it already is.
 *
 * @param {AbortSignal | undefined} signal
 * @param {() => void} stop
 * @returns {() => void} What stops listening.
 */
export function onAbort(signal, stop) {
  if (!signal) return () => {}
  if (signal.aborted) {
    stop()
    return () => {}
  }
  signal.addEventListener('abort', stop, { once: true })
  return () => signal.removeEventListener('abort', stop)
}
