// Frames (Section 6.3 of protocol/wire.md): each the length of its payload as an unsigned 32-bit
// big-endian integer, then the payload, one JSON object in UTF-8. A reader is fed bytes as they
// come, however they are cut, and hands out each whole frame once, in order.

import { t } from '../i18n.js'

/** The longest payload a frame may carry, in bytes. */
export const MAX = 33554432

const encoder = new TextEncoder()

/** Thrown where a value is too large for a frame. */
export class FrameError extends Error {}

/**
 * One value as one frame. `JSON.stringify` leaves non-ASCII characters as they are and writes a
 * `Date` as its text, as Section 6.3.3 asks.
 *
 * @param {object} value
 * @returns {Uint8Array}
 */
export function encode(value) {
  const payload = encoder.encode(JSON.stringify(value))
  if (!payload.length || payload.length > MAX) throw new FrameError(t('A frame of {count} bytes cannot be sent.', { count: payload.length }))
  const frame = new Uint8Array(4 + payload.length)
  new DataView(frame.buffer).setUint32(0, payload.length)
  frame.set(payload, 4)
  return frame
}

/** Reads frames out of bytes cut anywhere. */
export class Frames {
  /** @type {Uint8Array[]} */
  #chunks = []
  #held = 0
  /** The payload's length once its header is read, else -1. */
  #wanted = -1
  /** @type {string | null} Why the bytes are not frames, once a length of 0 or above `MAX` came. */
  broken = null

  /**
   * Takes more bytes and hands out the payload of every frame they complete, up to a length of 0
   * or above `MAX`, after which `broken` says why and nothing more is read.
   *
   * @param {Uint8Array} bytes
   * @returns {Uint8Array[]}
   */
  push(bytes) {
    if (this.broken !== null) return []
    if (bytes.length) {
      this.#chunks.push(bytes)
      this.#held += bytes.length
    }
    const out = []
    for (;;) {
      if (this.#wanted < 0) {
        if (this.#held < 4) break
        const header = this.#take(4)
        this.#wanted = new DataView(header.buffer, header.byteOffset, 4).getUint32(0)
        if (!this.#wanted || this.#wanted > MAX) {
          this.broken = t('A frame of {count} bytes is not read.', { count: this.#wanted })
          break
        }
      }
      if (this.#held < this.#wanted) break
      out.push(this.#take(this.#wanted))
      this.#wanted = -1
    }
    return out
  }

  /** The next `n` bytes held, which are there. */
  #take(n) {
    const first = this.#chunks[0]
    let out
    if (first.length >= n) {
      out = first.subarray(0, n)
      if (first.length === n) this.#chunks.shift()
      else this.#chunks[0] = first.subarray(n)
    } else {
      out = new Uint8Array(n)
      let at = 0
      while (at < n) {
        const chunk = this.#chunks[0]
        const part = Math.min(chunk.length, n - at)
        out.set(chunk.subarray(0, part), at)
        at += part
        if (part === chunk.length) this.#chunks.shift()
        else this.#chunks[0] = chunk.subarray(part)
      }
    }
    this.#held -= n
    return out
  }
}
