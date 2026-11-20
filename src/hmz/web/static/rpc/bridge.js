// The pipe provider of `hmz web` (Sections 4.7 to 4.9 of protocol/web.md): the WebSocket `/rpc` to
// the daemon of the server's machine for the route `unix:`, and `/dial?route=…&id=…` for the
// routes the server opens for the page, which tells the page `{state, detail}` in text until the
// carrier is up. From then on, binary messages carry the bytes each way.

import { t } from '../i18n.js'
import { Pipe, onAbort } from './pipe.js'
import { routeKind } from './routes.js'

/** The kinds of route `/dial` opens (Section 4.9.1 of protocol/web.md). */
const DIALED = new Set(['stdio:ssh', 'stdio:wsl', 'tcp', 'ws', 'easytier', 'relay'])

/**
 * @param {{base?: string, WebSocket?: typeof WebSocket}} [options] `base` the server's address,
 *   `ws://host:port`, by default the page's own.
 * @returns {import('./client.js').Provider}
 */
export function bridge({ base, WebSocket: Socket = globalThis.WebSocket } = {}) {
  const root = base ?? `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}`
  return {
    opens: (route) => route === 'unix:' || DIALED.has(routeKind(route) ?? ''),
    open(route, id, { state, signal }) {
      const dialed = route !== 'unix:'
      const url = dialed ? `${root}/dial?route=${encodeURIComponent(route)}&id=${encodeURIComponent(id)}` : `${root}/rpc`
      return new Promise((resolve, reject) => {
        const socket = new Socket(url)
        socket.binaryType = 'arraybuffer'
        /** @type {Pipe | null} */
        let pipe = null
        let said = ''
        const up = () => {
          pipe = new Pipe(
            (bytes) => socket.send(bytes),
            () => socket.close(1000),
          )
          stop()
          resolve(pipe)
        }
        const stop = onAbort(signal, () => {
          socket.close(1000)
          reject(new Error(t('Given up.')))
        })
        socket.onopen = () => {
          if (!dialed) up()
        }
        socket.onmessage = (event) => {
          if (typeof event.data !== 'string') {
            pipe?.feed(new Uint8Array(event.data))
            return
          }
          if (pipe) {
            socket.close(1000)
            pipe.end(t('The server sent text.'))
            return
          }
          let told
          try {
            told = JSON.parse(event.data)
          } catch {
            told = {}
          }
          said = told.detail ?? said
          if (told.state === 'up') up()
          else if (told.state === 'connecting' || told.state === 'installing') state(told.state, said)
        }
        socket.onclose = (event) => {
          const why = event.reason || said || `${route} closed.`
          if (pipe) pipe.end(why)
          else {
            stop()
            reject(new Error(why))
          }
        }
      })
    },
  }
}
