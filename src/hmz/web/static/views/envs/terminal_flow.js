// What a terminal panel works out without a page: bytes to and from base64, how much of what a
// shell said has been drawn and so is acknowledged to the host (protocol/core.md, `env.term.ack`),
// what is typed gathered and sent one call at a time in order, what a terminal missed while the
// page was away, its colours from the page's tokens, and what its tab is called. views/envs/
// terminal.js draws with these; tests/unit/web/js/envs_terminal.test.mjs reads them in node.

/** How many drawn bytes are acknowledged at once. */
export const ACK_EVERY = 64 * 1024

/** The most output the host sends a viewer that has not acknowledged it. */
export const CREDIT = 1024 * 1024

/** The most of what is typed one `env.term.input` carries. */
export const INPUT_MOST = 64 * 1024

/** How long drawing stays idle before what is drawn and unacknowledged is acknowledged. */
export const IDLE_MS = 50

const ENCODER = new TextEncoder()

/** Bytes as base64, however many: built in slices, as a string of one char per byte cannot be passed whole. */
export function toBase64(bytes) {
  let text = ''
  for (let at = 0; at < bytes.length; at += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(at, at + 0x8000))
  return btoa(text)
}

/** Base64 back to its bytes. */
export function fromBase64(data) {
  const text = atob(data || '')
  const bytes = new Uint8Array(text.length)
  for (let at = 0; at < text.length; at++) bytes[at] = text.charCodeAt(at)
  return bytes
}

/** What is typed, as the UTF-8 it is sent as. */
export function utf8(text) {
  return ENCODER.encode(text)
}

/** What xterm calls binary -- one char per byte, as a mouse report in X10 mode is -- as its bytes. */
export function binary(text) {
  const bytes = new Uint8Array(text.length)
  for (let at = 0; at < text.length; at++) bytes[at] = text.charCodeAt(at) & 0xff
  return bytes
}

/** Several byte arrays as one. */
export function joined(parts) {
  const out = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0))
  let at = 0
  for (const part of parts) {
    out.set(part, at)
    at += part.length
  }
  return out
}

/** Bytes as a string of one char per byte, which the string search built in looks through fast. */
function latin1(bytes) {
  let text = ''
  for (let at = 0; at < bytes.length; at += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(at, at + 0x8000))
  return text
}

/**
 * Acknowledges output only once it is drawn: a renderer slow to draw is slow to acknowledge, and
 * the host, past `CREDIT` unacknowledged, stops sending -- so the page is never flooded. What is
 * drawn is acknowledged `every` bytes at a time, and what is left once drawing goes idle.
 */
export class Flow {
  /**
   * @param {{ack: (bytes: number) => void, every?: number, idle?: number,
   *   later?: (fn: () => void, ms: number) => unknown, cancel?: (handle: unknown) => void}} options
   */
  constructor({ ack, every = ACK_EVERY, idle = IDLE_MS, later = (fn, ms) => setTimeout(fn, ms), cancel = (handle) => clearTimeout(handle) }) {
    this.ack = ack
    this.every = every
    this.idle = idle
    this.later = later
    this.cancel = cancel
    /** Bytes received and not yet drawn. */
    this.drawing = 0
    /** Bytes drawn and not yet acknowledged. */
    this.pending = 0
    this.timer = null
  }

  /** Bytes received and not yet acknowledged: what the host counts against its credit. */
  get unacked() {
    return this.drawing + this.pending
  }

  /** Bytes received, handed to be drawn. */
  got(bytes) {
    this.drawing += bytes
    this.settle()
  }

  /** Bytes the renderer has drawn: acknowledged once there are `every` of them, or drawing idles. */
  wrote(bytes) {
    this.drawing = Math.max(0, this.drawing - bytes)
    this.pending += bytes
    if (this.pending >= this.every) this.flush()
    else this.settle()
  }

  /** Acknowledges whatever is drawn now. */
  flush() {
    this.unwait()
    if (!this.pending) return
    const bytes = this.pending
    this.pending = 0
    this.ack(bytes)
  }

  /** Forgets every count, as for a viewer the host has just begun counting for. */
  reset() {
    this.unwait()
    this.drawing = 0
    this.pending = 0
  }

  /** Stops, acknowledging nothing more. */
  stop() {
    this.unwait()
    this.ack = () => {}
  }

  settle() {
    this.unwait()
    if (this.pending && !this.drawing) this.timer = this.later(() => ((this.timer = null), this.flush()), this.idle)
  }

  unwait() {
    if (this.timer !== null) this.cancel(this.timer)
    this.timer = null
  }
}

/**
 * What is typed, gathered for a frame and sent as one call, one call at a time and in order:
 * nothing typed while a call is out is sent before it, nor lost. `send` returns a promise; a call
 * that fails is told `failed`, and what follows still goes.
 */
export class Typing {
  /**
   * @param {{send: (bytes: Uint8Array) => Promise<unknown>, failed?: (error: unknown) => void,
   *   frame?: (fn: () => void) => unknown, most?: number}} options
   */
  constructor({ send, failed = () => {}, frame = (fn) => requestAnimationFrame(fn), most = INPUT_MOST }) {
    this.send = send
    this.failed = failed
    this.frame = frame
    this.most = most
    /** @type {Uint8Array[]} */
    this.queued = []
    this.scheduled = false
    this.sending = false
    this.stopped = false
    /** @type {Promise<void>} Settles once everything typed so far is sent. */
    this.idle = Promise.resolve()
    this.settled = () => {}
  }

  /** Bytes typed, sent with whatever else is typed this frame. */
  push(bytes) {
    if (this.stopped || !bytes.length) return
    if (!this.queued.length && !this.sending) this.idle = new Promise((done) => (this.settled = done))
    this.queued.push(bytes)
    if (this.scheduled || this.sending) return
    this.scheduled = true
    this.frame(() => {
      this.scheduled = false
      this.pump()
    })
  }

  /** Sends what is gathered now, not at the next frame. */
  now() {
    if (!this.sending) this.pump()
  }

  /** Sends nothing more. */
  stop() {
    this.stopped = true
    this.queued = []
    this.settled()
  }

  async pump() {
    if (this.sending) return
    this.sending = true
    try {
      while (this.queued.length && !this.stopped) {
        const all = joined(this.queued)
        const piece = all.subarray(0, this.most)
        this.queued = piece.length < all.length ? [all.slice(piece.length)] : []
        try {
          await this.send(piece)
        } catch (error) {
          this.failed(error)
        }
      }
    } finally {
      this.sending = false
      if (!this.queued.length) this.settled()
    }
  }
}

/** Calls `fn` once calls to what is returned stop for `ms`; `.cancel()` drops one waiting. */
export function debounced(fn, ms, later = (f, t) => setTimeout(f, t), cancel = (handle) => clearTimeout(handle)) {
  let timer = null
  const call = (...args) => {
    if (timer !== null) cancel(timer)
    timer = later(() => {
      timer = null
      fn(...args)
    }, ms)
  }
  call.cancel = () => {
    if (timer !== null) cancel(timer)
    timer = null
  }
  return call
}

/** The last bytes a terminal drew, kept so that, attached again, it is told only what it missed. */
export class Tail {
  constructor(most = 4096) {
    this.most = most
    this.bytes = new Uint8Array(0)
  }

  push(bytes) {
    if (bytes.length >= this.most) this.bytes = bytes.slice(bytes.length - this.most)
    else {
      const all = joined([this.bytes, bytes])
      this.bytes = all.length > this.most ? all.slice(all.length - this.most) : all
    }
  }

  /** Starts over from what a replay drew. */
  set(bytes) {
    this.bytes = new Uint8Array(0)
    this.push(bytes)
  }
}

/**
 * What a terminal attached again has to draw of its scrollback `replay`, given the `tail` it drew
 * last: what follows that tail where the replay holds it once -- nothing, where nothing was
 * missed -- or `null`, for the terminal to be cleared and drawn anew, where the replay does not
 * hold it or holds it more than once, so that where it was left cannot be told.
 */
export function missed(tail, replay) {
  if (!tail.length) return null
  const have = latin1(replay)
  const left = latin1(tail)
  const at = have.lastIndexOf(left)
  if (at < 0 || have.indexOf(left) !== at) return null
  return replay.subarray(at + tail.length)
}

/** How far back from a replay's end output that raced an attach is looked for. */
export const RACED = 64 * 1024

/**
 * What of `next` -- output that came while a terminal was being attached -- the `replay` it was
 * attached with does not already hold: all of it, save what the replay holds whole near its end,
 * or the part of it the replay ends with. An overlap shorter than `least` bytes is taken for
 * chance, not the same output; only the last `RACED` bytes of the replay are looked through.
 */
export function unseen(replay, next, least = 4) {
  if (!next.length) return next
  const have = latin1(replay.subarray(Math.max(0, replay.length - RACED - next.length)))
  const coming = latin1(next)
  if (coming.length >= least) {
    const at = have.lastIndexOf(coming)
    if (at >= 0 && have.length - at - coming.length <= RACED) return next.subarray(next.length)
  }
  // The longest end of the replay that `next` starts with, found where `next`'s first byte is.
  const most = Math.min(have.length, coming.length, RACED)
  for (let at = have.indexOf(coming[0], have.length - most); at >= 0 && have.length - at >= least; at = have.indexOf(coming[0], at + 1)) {
    if (coming.startsWith(have.slice(at))) return next.subarray(have.length - at)
  }
  return next
}

/** A colour `#rgb`, `#rrggbb` or `rgb(…)`/`rgba(…)` as `[r, g, b, a]`, or null. */
export function parseColor(text) {
  const value = String(text || '').trim()
  let match = /^#([0-9a-f]{3,8})$/i.exec(value)
  if (match) {
    let hex = match[1]
    if (hex.length === 3 || hex.length === 4) hex = [...hex].map((c) => c + c).join('')
    if (hex.length !== 6 && hex.length !== 8) return null
    const n = (at) => parseInt(hex.slice(at, at + 2), 16)
    return [n(0), n(2), n(4), hex.length === 8 ? n(6) / 255 : 1]
  }
  match = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)$/i.exec(value)
  if (match) {
    const alpha = match[4] === undefined ? 1 : match[4].endsWith('%') ? parseFloat(match[4]) / 100 : parseFloat(match[4])
    return [Number(match[1]), Number(match[2]), Number(match[3]), alpha]
  }
  return null
}

const hex2 = (n) => Math.round(Math.min(255, Math.max(0, n))).toString(16).padStart(2, '0')

/** `[r, g, b]` as `#rrggbb`. */
export function hexOf([r, g, b]) {
  return `#${hex2(r)}${hex2(g)}${hex2(b)}`
}

/** `a` moved `amount` of the way to `b`, both colours as text; `a` alone where either is unreadable. */
export function mix(a, b, amount) {
  const one = parseColor(a)
  const two = parseColor(b)
  if (!one || !two) return a
  return hexOf([0, 1, 2].map((at) => one[at] + (two[at] - one[at]) * amount))
}

/** A colour seen over `under`: one partly see-through laid on what is beneath it. */
export function over(color, under) {
  const top = parseColor(color)
  const bottom = parseColor(under)
  if (!top || !bottom) return color
  return hexOf([0, 1, 2].map((at) => bottom[at] + (top[at] - bottom[at]) * top[3]))
}

/** The light ANSI palette, where the page's tokens leave a colour unsaid. */
const LIGHT = {
  black: '#1e2428', red: '#cf3552', green: '#2a9468', yellow: '#80590c', blue: '#2f6fb7', magenta: '#b83a72', cyan: '#0b7080', white: '#d8dee1',
  brightBlack: '#5d6a72', brightRed: '#e0566f', brightGreen: '#3cae7e', brightYellow: '#a87512', brightBlue: '#4a8fd8', brightMagenta: '#8b72d6', brightCyan: '#1590a3', brightWhite: '#ffffff',
}

/** The dark ANSI palette, likewise. */
const DARK = {
  black: '#1d272e', red: '#ff6f88', green: '#5fdca3', yellow: '#f2c862', blue: '#86b8f2', magenta: '#ff94c2', cyan: '#4fd8ea', white: '#e6eff1',
  brightBlack: '#82939a', brightRed: '#ff95a8', brightGreen: '#8ae9be', brightYellow: '#f7da92', brightBlue: '#aacdf6', brightMagenta: '#ffb8d7', brightCyan: '#7fe4f1', brightWhite: '#ffffff',
}

/**
 * A terminal's colours, as xterm takes them, from the page's tokens (each resolved to a colour
 * already): its paper and ink, cursor and selection, and the sixteen ANSI colours from the
 * tokens of the same hue -- read on light paper or dark, as the theme is.
 */
export function palette({ dark, tokens = {} }) {
  const base = dark ? DARK : LIGHT
  const token = (name) => (parseColor(tokens[name]) ? tokens[name] : null)
  const background = token('surface') || token('paper') || (dark ? '#172026' : '#fbfdfd')
  const foreground = token('ink') || (dark ? '#e6eff1' : '#141a1f')
  const accent = token('cyan') || base.cyan
  const colour = (name, fallback) => token(name) || fallback
  const named = {
    black: dark ? colour('raised', base.black) : colour('ink', base.black),
    red: colour('fail', base.red),
    green: colour('done', base.green),
    yellow: dark ? colour('gold', base.yellow) : colour('budget-ink', base.yellow),
    blue: colour('lane-5', base.blue),
    magenta: dark ? colour('pink', base.magenta) : colour('pink-ink', base.magenta),
    cyan: dark ? colour('cyan', base.cyan) : colour('cyan-ink', base.cyan),
    white: dark ? colour('ink-2', base.white) : colour('line-strong', base.white),
  }
  // A bright colour is its colour lifted toward the ink on dark paper, and on light paper the
  // colour itself where the dim one is its darker ink.
  const brighter = (name) => mix(named[name], dark ? '#ffffff' : base[`bright${name[0].toUpperCase()}${name.slice(1)}`], dark ? 0.3 : 0.35)
  return {
    background: hexOf(parseColor(background)),
    foreground: hexOf(parseColor(foreground)),
    cursor: hexOf(parseColor(foreground)),
    cursorAccent: hexOf(parseColor(background)),
    selectionBackground: over(`rgba(${parseColor(accent).slice(0, 3).join(', ')}, ${dark ? 0.35 : 0.25})`, background),
    selectionInactiveBackground: over(`rgba(${parseColor(accent).slice(0, 3).join(', ')}, 0.15)`, background),
    ...Object.fromEntries(Object.entries(named).map(([name, value]) => [name, hexOf(parseColor(over(value, background)))])),
    brightBlack: hexOf(parseColor(over(colour('ink-3', base.brightBlack), background))),
    brightRed: brighter('red'),
    brightGreen: brighter('green'),
    brightYellow: brighter('yellow'),
    brightBlue: brighter('blue'),
    brightMagenta: brighter('magenta'),
    brightCyan: brighter('cyan'),
    brightWhite: dark ? '#ffffff' : colour('ink-2', base.brightWhite),
  }
}

/** What a shell is called on its tab: its program's name, from its command line or argv. */
export function shellName(shell) {
  const argv = Array.isArray(shell) ? shell : typeof shell === 'string' ? shell.trim().split(/\s+/) : []
  const program = (argv[0] || '').split('/').pop().replace(/^-/, '')
  return program || 'shell'
}

/** What a terminal's tab says: the name given it, or the title its program set, or its shell's. */
export function tabTitle({ named = '', titled = '', shell = null }) {
  return (named || titled || shellName(shell)).trim().slice(0, 60) || 'shell'
}

/** Whether a refusal is the one a paired device gets opening a terminal. */
export function pairedRefusal(text) {
  return /Terminals are off for paired devices/.test(String(text || ''))
}

/** Whether a refusal says the environment has closed. */
export function closedRefusal(text) {
  return /That environment has closed\./.test(String(text || ''))
}

/** Whether a refusal says a terminal is no more. */
export function goneRefusal(text) {
  return /There is no terminal /.test(String(text || ''))
}
