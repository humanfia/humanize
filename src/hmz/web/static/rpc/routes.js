// Routes (Section 3.3 of protocol/wire.md): the text naming one carrier to one daemon, which of
// them are trusted (Section 3.5), and racing several routes to one daemon (Section 3.6.1).

import { t } from '../i18n.js'

const UNRESERVED = "[A-Za-z0-9._~-]"
const PCT = '%[0-9A-Fa-f]{2}'
const SUB = "[!$&'()*+,;=]"
// Section 3.3.4: a host is never empty, and a port is a decimal number from 1 to 65535.
const HOST = `(?:\\[[0-9A-Fa-f:.vV]+\\]|(?:${UNRESERVED}|${PCT}|${SUB})+)`
const PORT = '0*(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])'
const USERINFO = `(?:${UNRESERVED}|${PCT}|${SUB}|:)*`
const SEGMENT = `(?:${UNRESERVED}|${PCT}|${SUB}|[:@])*`
const WS_URL = `wss?://${HOST}(?::${PORT})?(?:/${SEGMENT})*`
const SSH_PARAM = `(?:identity=|jump=|option=)(?:${UNRESERVED}|${PCT}|=)+`

/** Each kind of route, as the grammar names it, and the pattern of it. */
const KINDS = /** @type {const} */ ([
  ['unix', new RegExp(`^unix:(?:/(?:${UNRESERVED}|${PCT}|/)*)?$`)],
  ['stdio:local', /^stdio:local$/],
  ['stdio:ssh', new RegExp(`^stdio:ssh://(?:${USERINFO}@)?${HOST}(?::${PORT})?(?:\\?${SSH_PARAM}(?:&${SSH_PARAM})*)?$`)],
  ['stdio:wsl', new RegExp(`^stdio:wsl(?::(?:${UNRESERVED}|${PCT})+)?$`)],
  ['tcp', new RegExp(`^tcp://${HOST}:${PORT}$`)],
  ['ws', new RegExp(`^${WS_URL}$`)],
  ['easytier', /^easytier:[A-Za-z0-9][A-Za-z0-9._-]*$/],
  ['relay', new RegExp(`^relay:${WS_URL}$`)],
  ['webrtc', new RegExp(`^webrtc:${WS_URL}$`)],
])

/** The kinds of carrier that are trusted alone (Section 3.5.1). */
const TRUSTED = new Set(['unix', 'stdio:local', 'stdio:ssh', 'stdio:wsl'])

/**
 * The kind of a route -- `unix`, `stdio:local`, `stdio:ssh`, `stdio:wsl`, `tcp`, `ws` (`wss`
 * included), `easytier`, `relay` or `webrtc` -- or null where it is not a route.
 *
 * @param {string} route
 * @returns {string | null}
 */
export function routeKind(route) {
  for (const [kind, pattern] of KINDS) if (pattern.test(route)) return kind
  return null
}

/** Whether a route's carrier is trusted (Section 3.5). */
export function trusted(route) {
  return TRUSTED.has(routeKind(route) ?? '')
}

/**
 * Races attempts at routes (Section 3.6.1): each started 250 milliseconds after the one before
 * it, or at once where every one started before it has failed. Resolves with the first to
 * succeed, closing every other, or rejects with the failure of the last to fail.
 *
 * @template T
 * @param {string[]} routes
 * @param {(route: string, signal: AbortSignal) => Promise<T>} attempt
 * @param {(won: T) => void} discard Closes a success that came too late.
 * @returns {Promise<T>}
 */
export function race(routes, attempt, discard) {
  return new Promise((resolve, reject) => {
    if (!routes.length) {
      reject(new Error(t('There is no route to try.')))
      return
    }
    const aborts = []
    let started = 0
    let failed = 0
    let won = false
    let timer
    const start = () => {
      clearTimeout(timer)
      if (won || started >= routes.length) return
      const abort = new AbortController()
      aborts.push(abort)
      const route = routes[started++]
      Promise.resolve()
        .then(() => attempt(route, abort.signal))
        .then(
          (value) => {
            if (won) {
              discard(value)
              return
            }
            won = true
            clearTimeout(timer)
            for (const other of aborts) if (other !== abort) other.abort()
            resolve(value)
          },
          (error) => {
            failed++
            if (won) return
            if (failed === routes.length) reject(error)
            else if (failed === started) start()
          },
        )
      if (started < routes.length) timer = setTimeout(start, 250)
    }
    start()
  })
}
