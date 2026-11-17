// The face's side of the bridge, run in faces/frame.html before the face is: it installs
// `window.hmz`, takes the one port the page hands over at load, and writes the face's HTML into
// this document with the page's colours already set on `:root` and kit.css beneath it.
//
//   hmz.on('ask', ({prompt, context, schema, errors}) => ...)   each ask of the session
//   hmz.on('show', (context) => ...)                            context pushed with no ask
//   hmz.on('theme', (tokens) => ...)                            the page's CSS variables
//   hmz.submit(value) -> Promise<{ok: true} | {ok: false, errors}>
//   hmz.resize(height)                                          a height of its own; 0 for auto
//
// Nothing else reaches the page: the port is the only way out, and the page answers on it only
// what it asked for. A plain script, not a module, so that it runs before anything is parsed.
;(() => {
  'use strict'

  const here = document.currentScript ? document.currentScript.src : location.href
  const kit = new URL('kit.css', here).href
  const listeners = { ask: [], show: [], theme: [] }
  /** What came before anyone listened for it: the latest ask and theme, and every show. */
  const latest = { ask: null, theme: null, shows: [] }
  const waiting = new Map()
  let port = null
  let token = ''
  let listening = false
  let next = 0
  let fixed = 0
  let told = 0

  const send = (message) => {
    if (port) port.postMessage({ ...message, token })
  }

  const said = (error) => (error && error.message ? String(error.message) : String(error))

  const deliver = (kind, value, only) => {
    for (const listener of only ? [only] : listeners[kind]) {
      try {
        listener(value)
      } catch (error) {
        setTimeout(() => {
          throw error
        })
      }
    }
  }

  const paint = (tokens) => {
    const root = document.documentElement
    if (!root) return
    for (const [name, value] of Object.entries(tokens || {})) if (/^--[\w-]+$/.test(name)) root.style.setProperty(name, String(value))
    if (tokens && (tokens['--scheme'] === 'dark' || tokens['--scheme'] === 'light')) {
      root.style.colorScheme = tokens['--scheme']
      root.dataset.theme = tokens['--scheme']
    }
  }

  const height = () => {
    if (fixed) return fixed
    const root = document.documentElement
    return root ? Math.ceil(root.getBoundingClientRect().height) : 0
  }

  let measuring = 0
  const measure = () => {
    if (measuring) return
    measuring = requestAnimationFrame(() => {
      measuring = 0
      const now = height()
      if (now && Math.abs(now - told) >= 1) {
        told = now
        send({ type: 'height', height: now })
      }
    })
  }

  /** Writes the face in, its theme set and the kit beneath it, failures before it listens told. */
  const write = (html, tokens, rule) => {
    const failed = (message) => {
      if (!listening) send({ type: 'failed', message })
    }
    const body = String(html).replace(/^\s*(?:<!--[\s\S]*?-->\s*)*<!doctype[^>]*>/i, '')
    const scheme = tokens && tokens['--scheme'] === 'dark' ? 'dark' : 'light'
    document.open()
    addEventListener('error', (event) => failed(event.message || 'The view threw an error.'))
    addEventListener('unhandledrejection', (event) => failed(said(event.reason)))
    document.write(
      `<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="${kit}">` +
        `<style data-hmz="theme">${String(rule || '').replace(/</g, '')}</style>` +
        body,
    )
    document.close()
    document.documentElement.dataset.theme = scheme
    // Nothing a face does navigates its frame: a form is sent, and a link followed, through
    // `hmz` alone, so that a face never unloads itself by a stray submit.
    document.addEventListener('submit', (event) => event.preventDefault(), true)
    document.addEventListener(
      'click',
      (event) => {
        const link = event.target instanceof Element ? event.target.closest('a[href]') : null
        if (link && !link.getAttribute('href').startsWith('#')) event.preventDefault()
      },
      true,
    )
    new ResizeObserver(measure).observe(document.documentElement)
    addEventListener('load', measure)
    measure()
  }

  const heard = (event) => {
    const message = event.data
    if (!message || typeof message !== 'object' || message.token !== token) return
    if (message.type === 'ping') {
      send({ type: 'pong', nonce: message.nonce })
    } else if (message.type === 'face') {
      latest.theme = message.theme || null
      write(message.html, latest.theme, message.rule)
    } else if (message.type === 'ask') {
      latest.ask = message.ask
      deliver('ask', message.ask)
    } else if (message.type === 'show') {
      if (listeners.show.length) deliver('show', message.context)
      else latest.shows.push(message.context)
    } else if (message.type === 'theme') {
      latest.theme = message.theme
      paint(message.theme)
      deliver('theme', message.theme)
    } else if (message.type === 'answered') {
      const resolve = waiting.get(message.id)
      waiting.delete(message.id)
      if (resolve) resolve(message.result)
    }
  }

  // The page's port, handed over once by the window that framed this one, and nothing else.
  addEventListener('message', (event) => {
    if (port || event.source !== parent) return
    const message = event.data
    if (!message || message.hmz !== 'hello' || typeof message.token !== 'string' || !event.ports[0]) return
    port = event.ports[0]
    token = message.token
    port.onmessage = heard
  })

  const hmz = {
    /** Listens for `ask`, `show` or `theme`; what came already is told at once. Returns an off. */
    on(kind, listener) {
      if (!Object.hasOwn(listeners, kind)) throw new TypeError(`hmz.on: no event "${kind}"; there are ask, show and theme.`)
      if (typeof listener !== 'function') throw new TypeError('hmz.on: the listener must be a function.')
      listeners[kind].push(listener)
      if (kind === 'ask' && latest.ask) queueMicrotask(() => deliver('ask', latest.ask, listener))
      if (kind === 'theme' && latest.theme) queueMicrotask(() => deliver('theme', latest.theme, listener))
      if (kind === 'show' && latest.shows.length) {
        const shows = latest.shows.splice(0)
        queueMicrotask(() => shows.forEach((context) => deliver('show', context, listener)))
      }
      if (kind === 'ask' && !listening) {
        listening = true
        send({ type: 'ready' })
      }
      return () => {
        const at = listeners[kind].indexOf(listener)
        if (at >= 0) listeners[kind].splice(at, 1)
      }
    },
    /** Answers the current ask; refused where the value does not fit, with where and why. */
    submit(value) {
      let json
      try {
        json = JSON.parse(JSON.stringify(value === undefined ? null : value))
      } catch (error) {
        return Promise.resolve({ ok: false, errors: [{ path: [], message: `The answer is not JSON: ${said(error)}` }] })
      }
      if (!port) return Promise.resolve({ ok: false, errors: [{ path: [], message: 'The page is not connected yet.' }] })
      return new Promise((resolve) => {
        const id = ++next
        waiting.set(id, resolve)
        send({ type: 'submit', id, value: json })
      })
    },
    /** Draws the frame `height` pixels tall, or as tall as the face is for 0. */
    resize(height) {
      const number = Number(height)
      fixed = Number.isFinite(number) && number > 0 ? Math.ceil(number) : 0
      told = 0
      measure()
    },
  }
  Object.defineProperty(window, 'hmz', { value: Object.freeze(hmz), enumerable: true })
})()
