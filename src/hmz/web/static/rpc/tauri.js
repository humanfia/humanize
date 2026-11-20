// The pipe provider of the desktop application (Section 3.12 of protocol/desktop.md): the commands
// `pipe_open` `{route, id}`, `pipe_send` `{pipe, data}` and `pipe_close` `{pipe}`, and the events
// `pipe_state`, `pipe_data` and `pipe_closed`, `data` the base64 of the bytes carried.

import { t } from '../i18n.js'
import { Pipe, fromBase64, onAbort, toBase64 } from './pipe.js'
import { routeKind } from './routes.js'

/** The kinds of route the app opens (Section 3.12.2 of protocol/desktop.md). */
const OPENED = new Set(['stdio:local', 'stdio:wsl', 'stdio:ssh', 'tcp', 'ws', 'easytier', 'relay'])

/**
 * @typedef {object} Internals What Tauri gives the page as `window.__TAURI_INTERNALS__`.
 * @property {(command: string, args?: object) => Promise<any>} invoke
 * @property {(callback: (event: {payload: any}) => void) => number} transformCallback
 */

/**
 * @param {Internals} [internals]
 * @returns {import('./client.js').Provider}
 */
export function tauri(internals = /** @type {any} */ (globalThis).__TAURI_INTERNALS__) {
  const { invoke } = internals
  /** @type {Map<string, {state: (payload: any) => void, data: (payload: any) => void, closed: (payload: any) => void}>} */
  const pipes = new Map()
  /** @type {Map<string, [string, any][]>} Events of a pipe told before `pipe_open` answered. */
  const early = new Map()
  /** @type {Set<string>} The pipes the page is done with, whose last events are dropped. */
  const done = new Set()
  let listening

  const told = (kind) => (event) => {
    const payload = event.payload
    const one = pipes.get(payload.pipe)
    if (one) one[kind](payload)
    else if (done.has(payload.pipe)) {
      if (kind === 'closed') done.delete(payload.pipe)
    } else if (early.has(payload.pipe)) early.get(payload.pipe).push([kind, payload])
    else early.set(payload.pipe, [[kind, payload]])
  }
  /** Closes a pipe the page is done with. */
  const closing = (name) => {
    pipes.delete(name)
    done.add(name)
    invoke('pipe_close', { pipe: name }).catch(() => done.delete(name))
  }
  const listen = () =>
    (listening ??= Promise.all(
      [
        ['pipe_state', 'state'],
        ['pipe_data', 'data'],
        ['pipe_closed', 'closed'],
      ].map(([event, kind]) =>
        invoke('plugin:event|listen', { event, target: { kind: 'Any' }, handler: internals.transformCallback(told(kind)) }),
      ),
    ))

  return {
    opens: (route) => OPENED.has(routeKind(route) ?? ''),
    async open(route, id, { state, signal }) {
      // A command the app refuses rejects with the sentence itself, a string and not an Error.
      const { pipe: name } = await listen()
        .then(() => invoke('pipe_open', { route, id }))
        .catch((error) => {
          throw new Error(error?.message ?? error)
        })
      return new Promise((resolve, reject) => {
        let sent = Promise.resolve()
        /** @type {Pipe | null} */
        let pipe = null
        let said = ''
        const stop = onAbort(signal, () => {
          closing(name)
          reject(new Error(t('Given up.')))
        })
        const one = {
          state: ({ state: now, detail }) => {
            said = detail ?? said
            if (now === 'up' && !pipe) {
              stop()
              // One send after another: the app is to carry them in the order sent.
              const opened = (pipe = new Pipe(
                (bytes) =>
                  (sent = sent
                    .then(() => invoke('pipe_send', { pipe: name, data: toBase64(bytes) }))
                    .catch((error) => opened.close(t('Could not send: {why}', { why: error?.message ?? error })))),
                () => closing(name),
              ))
              resolve(pipe)
            } else if (now === 'connecting' || now === 'installing') state(now, said)
          },
          data: ({ data }) => pipe?.feed(fromBase64(data)),
          closed: ({ why }) => {
            pipes.delete(name)
            if (pipe) pipe.end(why || said)
            else {
              stop()
              reject(new Error(why || said || t('{route} closed.', { route })))
            }
          },
        }
        pipes.set(name, one)
        for (const [kind, payload] of early.get(name) ?? []) one[kind](payload)
        early.delete(name)
      })
    },
  }
}
