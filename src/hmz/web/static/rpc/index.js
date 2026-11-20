// The page's RPC client: how the page speaks to a daemon over protocol/wire.md, whichever pipe
// provider carries it. Layers, bottom up: a pipe (`pipe.js`), frames (`frames.js`), a JSON-RPC 2.0
// session (`peer.js`), and a daemon reached and kept reached (`client.js`).
//
// Reaching a daemon:
//
//   import { bridge, connect, local, registry, tauri, webrtc } from './rpc/index.js'
//
//   const store = registry()
//   const providers = window.__TAURI_INTERNALS__
//     ? [tauri(), webrtc({ certificate: () => store.certificate() })]
//     : [bridge(), webrtc({ certificate: () => store.certificate() })]
//   const here = connect(local(), providers, { client: { name: '', kind: 'web' } })
//   const remote = connect((await store.list())[0], providers, { client: { name: '', kind: 'web' } })
//
// `connect(entry, providers, {client, pinned})` returns a `Client` at once and reaches the daemon
// in the background: it races `entry.routes` 250 ms apart through the first provider that opens
// each, says `session.hello`, keeps the first session answering the id `entry` pins, and tries
// again after 1 s, doubling to 60 s, whenever the session drops or every route fails. Where
// `entry.id` is '', the id answered over a trusted route is pinned and told to `pinned`.
//
//   client.state                          {state, detail}: idle, connecting, installing, up, failed
//   client.watch(fn)                      tells fn each change of state; returns what stops it
//   client.hello                          what session.hello answered, while up
//   await client.call(method, params, {timeout, signal})
//                                         waits for the session, then calls; a write gets an idem
//                                         and is sent again once with it where the session drops
//   const sub = await client.attach({workspace, slot, …}, onMessage, onEnded)
//                                         epic.attach: each epic.event message to onMessage,
//                                         attached again with `since` after each reconnection
//   const sub = await client.notices(onNotice, {after})
//                                         notices.subscribe, subscribed again after the last heard
//   await sub.close()                     epic.detach or notices.unsubscribe
//   client.close()
//
// A call is refused with an `RpcError` carrying `code` (one of `ERRORS`), `message` and `data`,
// or rejected with `Dropped` where the session closed before it was answered.
//
// Pipe providers: `bridge()` for `hmz web` (`unix:` over `/rpc`, other native routes over
// `/dial`), `webrtc({certificate})` for `webrtc:` routes, opened with the STUN and TURN servers of
// the daemon reached (`entry.ice`), and `tauri()` for the desktop application's pipes.
//
// The daemons the page keeps: `local()`, Local's entry -- `unix:` in `hmz web`, `stdio:local` on
// macOS and `stdio:wsl` on Windows in the desktop application -- and `registry()` -- `list()`,
// `add(entry)`, `update(name, changes)`, `remove(name)` and `certificate()`, an entry its `name`,
// `id`, `routes` and, where it has any, `ice`, its STUN and TURN servers -- and
// `claim(store, {name, code, device, ice}, providers)`, which adds one from a pairing code;
// `parsePairing(code)` reads one.

export { bridge } from './bridge.js'
export { Client, connect, idem, NotPinned, PROTOCOL, reach } from './client.js'
export { encode, Frames, FrameError, MAX } from './frames.js'
export { Dropped, ERRORS, Peer, RpcError } from './peer.js'
export { Pipe } from './pipe.js'
export { claim, local, parsePairing, registry } from './registry.js'
export { race, routeKind, trusted } from './routes.js'
export { tauri } from './tauri.js'
export { webrtc } from './webrtc.js'
export { WRITES } from './writes.js'
