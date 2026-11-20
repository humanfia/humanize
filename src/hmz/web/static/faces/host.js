// A question's face: the HTML app a flow ships for it, run in a sandboxed frame beside the
// question and spoken to over one MessageChannel port.
//
//   mountFace(question, {fetchFace, submit, theme, plain, shown, where}) -> HTMLElement
//
// `fetchFace(hash)` gives `{html, title}` (`epic.face`), kept here by hash; `submit(value)`
// answers the question, resolving where it was taken and rejecting, or resolving
// `{ok: false, errors}`, where it was refused; `theme` is the page's CSS variables, or a function
// giving them, read off the page where it is not given. `plain(on, reason)`, if given, is told
// whenever the plain form should be shown instead (`reason`: 'chosen', 'failed' or 'timeout')
// or no longer; the element also says so as a bubbling `hmz-face` event, `detail: {plain,
// reason}`. `shown` is the contexts the question's session was shown before now, oldest first:
// a face mounted anew is handed each of them with `show`, after its ask.
//
// A session keeps one frame across its asks: mounting the next question of the session gives
// back the same element, its face still in the state the person left it, told the new ask.
// `showFace(session, context, {where, run})` pushes context to it with no ask. A session is one
// epic's of one host (`where`, as held.js names it, and the question's `run`): another epic's of
// the same name is another session, with a frame of its own.

import { h } from '../dom.js'
import { t } from '../i18n.js'
import { PATIENCE_MS, SHOWN, TOKENS, askOf, cached, hashOf, heightOf, jsonOf, mountOf, outcome, overflow, rootRule, sessionOf, titleOf, tokenFor, tokensOf } from './logic.js'

const FRAME = new URL('./frame.html', import.meta.url).href
const SHEET = new URL('./host.css', import.meta.url).href

/** How long the bridge has to answer a ping before its frame is taken for a new document. */
const PING_MS = 1000

/** Each session's mount, the one used last at the end. */
const mounts = new Map()
const fetched = cached()

/** Mounts a question's face, or tells the session's mounted one its next ask. */
export function mountFace(question, { fetchFace, submit, theme, plain, shown, where } = {}) {
  const hash = hashOf(question)
  if (!hash) throw new Error(t('This question has no face.'))
  if (typeof fetchFace !== 'function' || typeof submit !== 'function') throw new TypeError('mountFace needs fetchFace and submit.')
  const session = mountOf(where, question.run, sessionOf(question))
  let mount = mounts.get(session)
  if (mount && mount.hash !== hash) {
    mount.drop()
    mount = undefined
  }
  const fresh = !mount
  if (fresh) {
    sheet()
    mount = new Mount(sessionOf(question), hash, titleOf(question))
    if (Array.isArray(shown)) mount.shows = shown.slice(-SHOWN)
  }
  mounts.delete(session)
  mounts.set(session, mount)
  for (const old of overflow([...mounts.keys()])) {
    mounts.get(old).drop()
    mounts.delete(old)
  }
  mount.ask(question, { fetchFace, submit, theme, plain })
  if (fresh) mount.start()
  watchTheme()
  return mount.el
}

/** Pushes context to a session's face, with nothing to answer. Whether a face took it. */
export function showFace(session, context, { where, run } = {}) {
  const mount = mounts.get(mountOf(where, run, String(session)))
  if (!mount) return false
  mount.show(Array.isArray(context) ? context : [])
  return true
}

/** Lets a session's face go, as its outworlder's session ends. */
export function dropFace(session, { where, run } = {}) {
  const key = mountOf(where, run, String(session))
  const mount = mounts.get(key)
  if (!mount) return
  mounts.delete(key)
  mount.drop()
}

function sheet() {
  if (document.querySelector('link[data-hmz=faces-css]')) return
  document.head.append(h('link', { rel: 'stylesheet', href: SHEET, 'data-hmz': 'faces-css' }))
}

/** The page's colours as a face is given them: every token of its style, and light or dark. */
export function pageTokens() {
  const root = document.documentElement
  const style = getComputedStyle(root)
  const names = new Set(TOKENS.map((name) => `--${name}`))
  for (let at = 0; at < style.length; at += 1) if (style[at].startsWith('--')) names.add(style[at])
  const tokens = {}
  for (const name of names) {
    const value = style.getPropertyValue(name).trim()
    if (value) tokens[name] = value
  }
  tokens['--scheme'] = root.dataset.theme === 'dark' ? 'dark' : 'light'
  return tokens
}

let watching = false

/** Tells every mounted face the page's colours again whenever they change. */
function watchTheme() {
  if (watching) return
  watching = true
  let last = ''
  const again = () => {
    // Told only where a token changed: the root's style changes for much besides colours.
    const said = JSON.stringify(pageTokens())
    if (said === last) return
    last = said
    for (const mount of mounts.values()) mount.retheme()
  }
  last = JSON.stringify(pageTokens())
  new MutationObserver(again).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'style', 'class'] })
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', again)
}

class Mount {
  constructor(session, hash, title) {
    this.session = session
    this.hash = hash
    this.title = title
    this.options = {}
    this.question = null
    this.shows = []
    this.state = 'loading'
    this.plain = false
    this.reason = ''
    this.fellBack = false
    this.port = null
    this.token = ''
    this.expecting = true
    this.timer = 0
    this.sending = false
    this.pongs = new Map()
    this.label = h('span', { class: 'face-title', 'data-hmz': 'face-title' }, title || t('Custom view'))
    this.note = h('p', { class: 'face-note', role: 'status', 'data-hmz': 'face-note', hidden: true })
    this.retry = h('button', { type: 'button', class: 'btn quiet small', 'data-hmz': 'face-retry', hidden: true, onclick: () => this.start() }, t('Try again'))
    this.switch = h('button', { type: 'button', class: 'btn quiet small face-switch', 'aria-pressed': 'false', 'data-hmz': 'face-plain', onclick: () => this.choose(!this.plain) }, t('Plain form'))
    this.skeleton = h(
      'div',
      { class: 'face-skeleton', 'aria-hidden': 'true', 'data-hmz': 'face-skeleton' },
      h('span', { class: 'face-bone wide' }),
      h('span', { class: 'face-bone' }),
      h('span', { class: 'face-bone short' }),
    )
    this.stage = h('div', { class: 'face-stage', 'data-hmz': 'face-stage', 'aria-busy': 'true' }, this.skeleton)
    this.el = h(
      'section',
      { class: 'face', 'data-hmz': 'face', 'data-state': 'loading', 'data-session': session, 'aria-label': title || t('Custom view') },
      h('header', { class: 'face-bar' }, h('span', { class: 'face-mark', 'aria-hidden': 'true' }, '◇'), this.label, h('span', { class: 'face-gap' }), this.retry, this.switch),
      this.note,
      this.stage,
    )
  }

  /** Tells the face its next ask, and whom to answer it through. */
  ask(question, options) {
    this.options = options
    this.question = question
    this.send({ type: 'ask', ask: askOf(question) })
    // A card drawn anew for a session showing the plain form is told so as it is drawn.
    if (this.plain) queueMicrotask(() => this.options.plain?.(true, this.reason))
  }

  show(context) {
    this.shows.push(context)
    if (this.shows.length > SHOWN) this.shows.splice(0, this.shows.length - SHOWN)
    this.send({ type: 'show', context })
  }

  retheme() {
    const theme = this.tokens()
    this.scheme(theme)
    this.send({ type: 'theme', theme })
  }

  /** The frame drawn in the face's light or dark, so no opaque backdrop shows behind it. */
  scheme(theme) {
    if (this.frame) this.frame.style.colorScheme = theme['--scheme'] === 'dark' ? 'dark' : 'light'
  }

  tokens() {
    const { theme } = this.options
    try {
      return tokensOf(typeof theme === 'function' ? theme() : theme && typeof theme === 'object' ? theme : pageTokens())
    } catch {
      return tokensOf(pageTokens())
    }
  }

  /** Loads the frame afresh: a new document, a new port, the face written into it again. */
  start() {
    this.close()
    this.set('loading')
    this.note.hidden = true
    this.retry.hidden = true
    this.frame?.remove()
    this.expecting = true
    this.frame = h('iframe', {
      class: 'face-frame',
      src: FRAME,
      sandbox: 'allow-scripts allow-forms',
      referrerpolicy: 'no-referrer',
      title: this.title || t('Custom view'),
      'data-hmz': 'face-frame',
      onload: () => this.loaded(),
    })
    this.frame.style.height = `${heightOf()}px`
    this.stage.append(this.frame)
    this.timer = setTimeout(() => this.fail('timeout', t('This view took too long to open.')), PATIENCE_MS)
    const html = fetched(this.hash, (hash) => this.options.fetchFace(hash))
    this.html = html
    html.catch((error) => {
      if (this.html === html) this.fail('failed', t('This view could not be fetched: {why}', { why: error instanceof Error ? error.message : error }))
    })
  }

  /** The frame loaded a document: ours, to hand the port to, or one it went to by itself. */
  async loaded() {
    if (!this.frame || this.state === 'failed') return
    if (!this.expecting) {
      // The face written in, loaded: the bridge still answers on the port. Otherwise the frame
      // was loaded again as it was moved in the page, or navigated away by the face: it is
      // sent back to frame.html, and given a new port there, never this one.
      if (await this.alive()) return
      if (this.expecting || !this.frame || this.state === 'failed') return
      this.close()
      this.set('loading')
      this.expecting = true
      this.frame.src = FRAME
      this.timer = setTimeout(() => this.fail('timeout', t('This view took too long to open.')), PATIENCE_MS)
      return
    }
    this.expecting = false
    const frame = this.frame
    let face
    try {
      face = await this.html
    } catch {
      return
    }
    if (frame !== this.frame || !frame.contentWindow) return
    if (face.title && !this.title) {
      this.title = face.title
      this.label.textContent = face.title
      this.el.setAttribute('aria-label', face.title)
      frame.title = face.title
    }
    const channel = new MessageChannel()
    this.token = tokenFor()
    this.port = channel.port1
    const token = this.token
    channel.port1.onmessage = (event) => this.heard(event.data, token)
    frame.contentWindow.postMessage({ hmz: 'hello', token }, '*', [channel.port2])
    const theme = this.tokens()
    this.scheme(theme)
    this.send({ type: 'face', html: face.html, theme, rule: rootRule(theme) })
    if (this.question) this.send({ type: 'ask', ask: askOf(this.question) })
    for (const context of this.shows) this.send({ type: 'show', context })
  }

  /** Whether the document the port was handed to still answers on it. */
  alive() {
    if (!this.port) return Promise.resolve(false)
    const nonce = tokenFor()
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.pongs.delete(nonce)
        resolve(false)
      }, PING_MS)
      this.pongs.set(nonce, () => {
        clearTimeout(timer)
        resolve(true)
      })
      this.send({ type: 'ping', nonce })
    })
  }

  /** One message on this mount's port, from the frame given that token alone. */
  async heard(message, token) {
    if (!message || typeof message !== 'object' || token !== this.token || message.token !== token) return
    if (message.type === 'pong') {
      const answered = this.pongs.get(message.nonce)
      this.pongs.delete(message.nonce)
      answered?.()
    } else if (message.type === 'ready') {
      clearTimeout(this.timer)
      this.set('ready')
      this.stage.removeAttribute('aria-busy')
      this.switch.hidden = false
      if (this.fellBack) {
        this.fellBack = false
        this.choose(false, 'ready')
      }
    } else if (message.type === 'failed') {
      if (this.state === 'loading') this.fail('failed', t('This view stopped with an error: {why}', { why: String(message.message || '').slice(0, 200) }))
    } else if (message.type === 'height') {
      if (this.frame) this.frame.style.height = `${heightOf(message.height)}px`
    } else if (message.type === 'submit') {
      const id = message.id
      let result
      if (this.state !== 'ready') result = { ok: false, errors: [{ path: [], message: t('This view is not ready to answer.') }] }
      else if (this.sending) result = { ok: false, errors: [{ path: [], message: t('An answer is on its way already.') }] }
      else {
        this.sending = true
        try {
          result = await outcome(this.options.submit, jsonOf(message.value) ?? null)
        } finally {
          this.sending = false
        }
      }
      if (token === this.token) this.send({ type: 'answered', id, result })
    }
  }

  send(message) {
    if (this.port) this.port.postMessage({ ...message, token: this.token })
  }

  set(state) {
    this.state = state
    this.el.dataset.state = state
  }

  /** The face could not be shown: said plainly, with a way to try again, and the plain form. */
  fail(reason, sentence) {
    if (this.state === 'failed') return
    this.close()
    this.set('failed')
    this.frame?.remove()
    this.frame = null
    this.stage.removeAttribute('aria-busy')
    this.note.textContent = t('{why} The plain form is below.', { why: sentence })
    this.note.hidden = false
    this.retry.hidden = false
    this.switch.hidden = true
    if (!this.plain) this.fellBack = true
    this.choose(true, reason)
  }

  /** Shows the plain form instead of the face, or the face again; the face keeps its state. */
  choose(plain, reason = 'chosen') {
    const changed = this.plain !== plain
    this.plain = plain
    this.reason = plain ? reason : ''
    this.el.dataset.plain = plain ? 'true' : 'false'
    this.switch.setAttribute('aria-pressed', plain ? 'true' : 'false')
    this.switch.textContent = plain ? (this.title ? t('Back to {name}', { name: this.title }) : t('Back to the custom view')) : t('Plain form')
    this.stage.hidden = plain
    if (!changed) return
    try {
      this.options.plain?.(plain, reason)
    } finally {
      this.el.dispatchEvent(new CustomEvent('hmz-face', { bubbles: true, detail: { plain, reason } }))
    }
  }

  close() {
    clearTimeout(this.timer)
    this.timer = 0
    this.port?.close()
    this.port = null
    this.token = ''
  }

  drop() {
    this.close()
    this.frame?.remove()
    this.frame = null
    this.set('dropped')
  }
}
