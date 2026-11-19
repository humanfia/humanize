---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# Web reference

The web interface `hmz web` serves: a page, drawn in a browser on this machine, that is a
JSON-RPC client of this machine's [daemon](/reference/daemon) and of every other daemon the
user adds -- one more [frontend](/reference/daemon#hosting) of the runs each daemon holds, as
the terminal interface is. Its command line, how a browser is let in, what is refused, the
page's files, the bridges `/rpc` and `/dial` that carry the page to a daemon, the page's
addresses and what it keeps. Package `hmz.web`. Notation:
[Conventions](/reference/#conventions). The task-by-task guide is [In a browser](/user/web).

The server is the standard library's `http.server`, its WebSockets spoken by `websockets`, and
the page is plain ES modules served as they are: `hmz web` builds nothing. It holds no epic
itself: the server serves the page's files, where it started, and two bridges -- everything
else the page does, it does over JSON-RPC to a daemon.

## Command line {#command-line}

```text
hmz web [--port <port>] [--no-open] [--attached]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--port <port>` | the port the last `hmz web` of this home listened on, kept in `~/.hmz/web-port`; `0` where none is kept | The port to listen on, on `127.0.0.1` and, where this machine has IPv6, on `::1` too. `0` picks any free one on both. Where the port kept is taken, any free one. |
| `--no-open` | off | Print the address and open no browser. |
| `--attached` | off | Stop once standard input closes. |

Before it listens it reaches this machine's daemon, starting it where none runs. Once
listening it writes the port to `~/.hmz/web-port` (where it changed, replacing the file
whole), so that the next `hmz web` listens on the same one and an address kept in a browser
keeps its origin -- and with it what the page keeps there. A `web-port` that does not hold a
port from 1 to 65535 is read as none; delete it whenever you like.

Then it prints one line to stdout, flushed, and serves until `SIGINT`, `SIGTERM` or `SIGHUP`
-- or, with `--attached`, until standard input closes, so that the program that started it
takes it down by exiting, crashed or killed included. Each stops it the same way, exiting `0`:
every bridge closes, the port is let go of, and the page below is removed. A `SIGTERM`,
`SIGHUP` or closed stdin while it stops is ignored and a second `SIGINT` cuts the stopping
short; a signal already ignored when it starts, as a hangup is under `nohup`, stays ignored.
No epic stops with it.

Unless `--no-open` was given, or there is no desktop to open a browser on (Linux with neither
`DISPLAY` nor `WAYLAND_DISPLAY`), it also opens a browser, through Python's `webbrowser`, on a
page that only this account can read -- `web-<port>.html` in this machine's own directory,
removed when it stops -- which sends the browser on to the address: the key is never on a
browser's command line, which every account on the machine can read.

```text
hmz web: http://127.0.0.1:<port>/?key=<key>
```

`hmz web` serves every workspace of every daemon the page reaches, wherever it is started; the
directory it started in is only the one a new epic is offered first ([`/here`](#here)).

### Exit statuses {#exit-statuses}

| Status | stderr | When |
| --- | --- | --- |
| `0` | — | Stopped, as above, after it was serving. |
| `1` | `hmz: <why>` | This machine's daemon is one of an older Humanize. |
| `1` | `hmz: the web interface cannot be served: <OSError>` | The daemon could not be reached, or the port could not be listened on. |
| `2` | argparse's usage error | The line was wrong: a `--port` not from 0 to 65535, say. |

## Letting a browser in {#sign-in}

| Step | What happens |
| --- | --- |
| The key | 32 random bytes, URL-safe base64 (43 characters), made afresh each time `hmz web` starts, and only ever printed in the address. |
| `GET /?key=<key>` | `303` to `/`, setting `hmz-<port>=<key>; HttpOnly; SameSite=Strict; Path=/`. A key that is not this server's: `403`. |
| `/here`, `/rpc`, `/dial` | Answered only where the cookie carries the key; otherwise `401`, and the page says `This browser is not let in.` |
| The page's own files | Served without the cookie; they hold nothing of the runs. |

## What is refused {#refused}

Every refusal is JSON, `{"error": "<one sentence>"}`, `application/json; charset=utf-8`, with
the status below. They are checked in this order.

| Status | Condition | `error` |
| --- | --- | --- |
| `403` | The connection did not come from a loopback address | `Open the address hmz web printed, on the machine it runs on.` |
| `403` | `GET /?key=` with a key that is not this server's | `That key is not this server's: open the address hmz web printed.` |
| `401` | `/here`, `/rpc` or `/dial` without the key's cookie | `Open the address hmz web printed to let this browser in.` |
| `403` | `/here`, `/rpc` or `/dial` that the browser says came from another page: `Sec-Fetch-Site` other than `same-origin`; or, from a browser that sends no `Sec-Fetch-Site`, an `Origin` that is not `http` or whose host and port are not the `Host` asked | `Use this server's own page to make this request.` |
| `405` | A method other than `GET` | `Only the page's own files are here.` |
| `400` | `/rpc` or `/dial` that is not a WebSocket upgrade | `Open this as a WebSocket.` |
| `404` | A path that is none of the page's files | `There is nothing here by that name.` |
| `500` | Anything else, with a traceback on `hmz web`'s stderr | `Something went wrong here: <why>` |

Which name the server was reached by is not asked: a port forwarded over ssh, or proxied on to
it by a server on this machine, is answered under whatever name the browser used, once that
browser has been let in there with the key. A web page elsewhere that points a name of its own
at `127.0.0.1` reaches the server, but its browser hands it that name's cookies only, never the
key's, so it is answered `401`. A page served from another port of this machine is the same
site to a cookie, so its browser sends the cookie along; it is refused all the same, by what
the browser says of where the request came from. A connection that says nothing for **60 s**
is closed; a WebSocket of `/rpc` or `/dial` is never closed for being quiet.

## The page's files {#files}

The files under `hmz/web/static/` are served as they are, `/` being `index.html`, each as its
extension says: `.html`, `.js`, `.css`, `.svg`, `.json`. A path whose parts are not each
letters, digits, `_` or `-`, whose last part has no one extension of lowercase letters or
digits, or that is over **200** characters, is `404`. Every answer carries
`X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY`,
a weak `ETag` and `Cache-Control: no-cache` (`304` when it has not changed). A page itself
carries:

```text
Content-Security-Policy: default-src 'self'; img-src 'self' data: blob:;
  style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' ws: wss:;
  frame-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'
```

`'self'` lets the page reach the server's own `/rpc` and `/dial`, and frame its own
`faces/frame.html`; `ws:` and `wss:` the relay of a `webrtc:` route, whose host the server
cannot know. `'unsafe-inline'` in `style-src` lets the editor and the terminal style what they
draw from their own scripts; scripts stay the server's own files only.

`faces/frame.html`, the document a [face](/weaver/faces) runs in, is the one file the page may
frame: it carries `X-Frame-Options: SAMEORIGIN` and a policy of its own, which it also says in
a `<meta>` of its own:

```text
Content-Security-Policy: default-src 'none'; script-src 'unsafe-inline' 'self';
  style-src 'unsafe-inline' 'self'; img-src data: blob:; font-src data:;
  connect-src 'none'; frame-ancestors 'self'
```

A file under `vendor/` asked for with `Origin: null`, as a face's opaque origin asks, is
answered with `Access-Control-Allow-Origin: null`, so a face can import it; no other answer
says `Access-Control-Allow-Origin`.

The page's only third-party code is served from `/vendor/`: the editor (CodeMirror 6) at
`codemirror.js`, the terminal (xterm.js) at `xterm.js` and `xterm_css.css`, Markdown (marked
and DOMPurify) at `markdown.js`, and charts (Vega-Lite through vega-embed, its expressions
interpreted rather than compiled, so no `eval` is needed) at `vega.js`. They are built from the
pinned packages in `src/hmz/web/vendor/`; see
[Rebuilding the vendored code](/contributing/architecture#vendored-web-code).

## `/here` {#here}

`GET /here` answers `{"here": "<the directory hmz web started in>"}`, with
`Cache-Control: no-store`: the workspace of Local a new epic is offered first.

## `/rpc` {#rpc}

`GET /rpc`, as a WebSocket, is carried to this machine's daemon's socket, starting the daemon
where none runs: every binary message the page sends goes to the socket as bytes, and every
byte from the socket comes back in binary messages, unchanged and in order. What the bytes
are -- frames, and JSON-RPC inside them -- is the page's and the daemon's, as the
[wire protocol](https://github.com/humanfia/humanize/blob/main/protocol/wire.md) states. The
session is trusted, as one over the socket is.

| Close | Reason | When |
| --- | --- | --- |
| `1011` | `The daemon cannot be reached: <why>`, cut to 120 bytes | The daemon could not be reached or started. |
| `1000` | `The daemon closed.` | The daemon closed its end. |
| `1000` | | The page closed, or sent a text message. |

## `/dial` {#dial}

`GET /dial?route=<route>&id=<daemon id>`, as a WebSocket, opens a
[route](/reference/daemon#listeners) to another machine's daemon as this machine's device --
the carriers a browser cannot open itself: `stdio:ssh`, `stdio:wsl`, `tcp`, `ws`, `easytier`
and `relay`. Over an untrusted route it opens mutual TLS, pinning `id`; an `easytier:<name>`
route joins the EasyTier entry of that name in this machine's settings, which the page writes
through Local's `easytier.set`.

Until the carrier is open, the page is told how it goes in text messages, one JSON object each:

```json
{"state": "installing", "detail": "Downloading EasyTier 2.6.4"}
```

`state` is `connecting`, `installing`, `up` -- the carrier is open -- or `failed`, which is
sent just before the WebSocket is closed; `detail` is what was said last, such as uv's last
line while `hmz` is installed over ssh. From `up` on, it carries bytes both ways as `/rpc`
does. Once it closes, the `ssh`, `wsl.exe` and EasyTier processes it started are stopped where
no other `/dial` of the same route still needs them.

| Close | Reason | When |
| --- | --- | --- |
| `1008` | `<route> is not a route.` | `route` is not a route. |
| `1008` | `<route> is not dialed here.` | A `unix:` or `stdio:local` route, which `/rpc` covers, or a `webrtc:` one, which the browser opens itself. |
| `1008` | `<route> needs the id of the daemon it reaches.` | An untrusted route without `id`. |
| `1011` | What went wrong, as `failed` said it | The carrier did not open. |
| `1000` | The last line the route's `ssh` or `wsl.exe` said on standard error, cut to 120 bytes | That process ended failing, such as `hmz daemon connect` there reaching no daemon. |
| `1000` | `The daemon closed.` | The far end closed. |
| `1000` | | The page closed, or sent a text message. |

## The page {#page}

The page speaks one JSON-RPC session to each daemon it reaches -- Local over `/rpc`, a remote
daemon over `/dial`, or over the browser's own WebRTC for a `webrtc:` route -- saying
`session.hello` as `kind` `web` (`desktop` in [Humanize Desktop](/user/desktop)). Everything it
shows and does is the [daemon's methods](/reference/daemon), the same any client calls:
`hosts.running` and `epic.attach` for the epics going, [`chat.*`](/reference/daemon#chats) to
list, read, start, talk to, stop and complete a chat, `runs.*` for the epics written down,
`flows.*`, `settings.*`, `accounts.*`, `notices.subscribe` and the rest. Section 4.20 of
[`protocol/daemon.md`](https://github.com/humanfia/humanize/blob/main/protocol/daemon.md#420-methods-and-the-interfaces-they-replace)
maps every route of the HTTP interface `hmz web` served before to the method that serves it now.

Each view is an address after `#`, so it can be kept and opened again:

| Address | View |
| --- | --- |
| `#/new[?workspace=&flow=&resume=<name>]` | A new epic, **Chat** or **Flow**: in the workspace picked (where `hmz web` started by default), a [chat](/user/chat) with the agent that workspace remembers, the flow picked, or the epic named picked up. The page opens here. |
| `#/live[?workspace=&slot=]` | The epic going on that host -- the workspace's own -- or the chat going on a chat's; its address becomes `#/epics/<name>` once it is written down -- a chat's, `#/chats/<id>`. |
| `#/chats/<id>` | One chat, by its id: its conversation, read with `chat.get`; live where a host holds it. |
| `#/harness/<harness>/<id>?workspace=<path>` | One [harness session](/reference/daemon#harness-sessions) of that workspace, read with `chat.harness.get` and only read; **Continue in chat** calls `chat.harness.adopt` and opens the chat it answers, and is offered only where the row is `continuable`: otherwise the view says `A session of <harness> cannot be continued in a chat.` |
| `#/epics/import?path=<file>` | Imports the `.hmzepic` at that whole path -- in Humanize Desktop as it is opened, read from the app and sent in chunks to the daemon shown, as one picked is; in a browser, from the daemon's machine as `runs.import` `{path}` does, which any page elsewhere could have sent here, once **Import** under the path is pressed -- then stands in for itself with `#/epics/<name>/exomyth`, its [Exomyth](/user/web#exomyth) -- going back does not import it again; a refusal is said in its place, with the epic's own address where it is here already. What the desktop app is to open a `.hmzepic` with. |
| `#/epics/<name>` | One epic, by its directory's name, drawn as a graph of its agents; live where it is the epic going. An epic an earlier Humanize recorded for a chat is one of these, its flow said as `chat`, and only read. |
| `#/epics/<name>/agents/<role>` | The same graph, with that agent picked out. |
| `#/epics/<name>/sessions/<agent>/<n>` | The thread of the `n`-th session that agent opened, as the epic going names it (`/` written `%2F`). |
| `#/epics/<name>/logs/<role>` | One agent's log, across its sessions; or one person's, what they are asked and answer. `#/epics/<name>/logs`, with neither, opens `#/epics/<name>`. |
| `#/epics/<name>/exomyth[?tab=flame]` | The epic's [Exomyth](/user/web#exomyth): its timeline, or its flame graph. |
| `#/flows[?workspace=&flow=]` | The flows on offer in a workspace, one opened. |
| `#/flows?tab=verses[&verse=]` | The flowverses, one opened. |
| `#/search[?status=&flow=&q=&offset=]` | A dialog finding epics. `status`: how it went, `running` or `unfinished`. |
| `#/download[?target=]` | A dialog downloading an epic out of a backup target: the first in settings without `target`. |
| `#/settings/<page>[?daemon=&days=]` | A dialog: `themes`, `daemons` or `notifications`, the page's own; or `general`, `accounts`, `nous`, `runtimes`, `backup`, `workspace` or `usage`, of the daemon `daemon` names (the one shown without it); `days` is how far `usage` looks back (7, 30, 90 or 365; default 30), by UTC day. |
| `#/delete/<id>[?daemon=]` | A dialog asking before a chat is deleted: `Cancel` or `Delete`. Of the daemon `daemon` names (the one shown without it). |

Every address above is of one daemon. `#/@<name>/<view>` -- `#/@local/new`, `#/@gpu/epics/<name>`
-- is that view of the daemon named; an address naming none is Local's. The page shows only the
daemon its address names: every link it draws keeps the `@<name>` the address carries, and going
to another daemon's address draws the view and the sidebar again, of that daemon, letting go of
what the page followed of the last. The notifications, the daemons and the page's own settings
are the same whichever daemon is shown.

Every view's bar carries Ai-chan's avatar at its right, the page's file `ai-chan/avatar.png`, a button that
opens and closes the [Ai-chan drawer](/user/web#ai-chan) beside it, kept open from view to view
of one daemon. The drawer lists that daemon's conversations (`aichan.list`), makes one
(`aichan.create`) from its **New** form, forgets one (`aichan.forget`) after asking, and draws
one as a chat attached to its `ai:` slot (`epic.attach`), its **Stop** being `epic.stop`. On a
phone's width it covers the view.

### What the page keeps {#kept}

Nothing of the page is kept in any daemon's settings. The browser keeps it, for the server's
origin -- which is why `hmz web` keeps its port:

| Where | What |
| --- | --- |
| IndexedDB `hmz-daemons` | The remote daemons, each its name, the daemon id it pins (`""` until it is first reached over a trusted route) and its routes in order; the STUN and TURN servers WebRTC uses; and the browser's own certificate, which a daemon paired with it knows it by. |
| IndexedDB `hmz-notifications` | The notifications: the notices every reached daemon's `notices.subscribe` told, the newest **200**, each with its daemon and whether it is read; where each daemon's notices are taken up again; and which kinds are told, and whether the system shows them. |
| IndexedDB `hmz` | The pictures of the [themes](/user/web#themes) made here. |
| `localStorage` | Conveniences, each forgotten without harm: the theme chosen as `hmz-theme` (and under Auto `hmz-theme-light` and `hmz-theme-dark`), the themes made here as `hmz-themes`, a sidebar folded away as `hmz-sidebar` and how wide it was dragged as `hmz-side-wide`, a side panel closed as `hmz-panel`, which epics are opened out in the sidebar as `hmz-opened` and which of its groups folded away as `hmz-shut`, how its list is grouped, sorted and filtered as `hmz-list`, which epics are pinned as `hmz-pinned` and which marked unread as `hmz-unread`, whether an epic's agents are drawn as a list as `hmz-shape`, and which questions were looked at as `hmz-seen`. |

Another browser, or another port, starts with none of it: add the daemons there again.

## Module `hmz.web` {#module}

```python
@contextlib.contextmanager
def listening(*, port: int = 0) -> Generator[Site]: ...
def serve(*, port: int | None = None, shown: Callable[[str], object] = print,
          opened: Callable[[str], object] | None = None) -> None: ...
def kept_port() -> int: ...
```

`listening` reaches this machine's daemon, starting it where none runs, and listens, answering
nothing until `Site.serve_forever` is called, with a key made up as it starts. `serve` is both, until `KeyboardInterrupt`, on the port given
-- `None` for the one `kept_port` says, any free one where that is taken -- writing the port
it took to `web-port`, telling `shown` the address once it listens and handing it to `opened`.
`kept_port` is the port `web-port` holds, or `0`. `Site.address` is the address with its key;
`Site.port` the port; `Site.here` the directory it started in. Each raises `hmz.daemon.Older`
for a daemon of an older Humanize, and `OSError` where the daemon cannot be reached or the port
listened on.
