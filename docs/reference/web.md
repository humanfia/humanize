---
title: Page addresses and shortcuts
description: Look up every address, shortcut and stored key of the page, the bridge a face talks through, and the endpoints hmz web serves.
---

# Page addresses and shortcuts

Use this reference for the page that `hmz web` serves and that Humanize Desktop shows: its addresses, keyboard shortcuts, browser storage keys, the face bridge, and the three endpoints behind it. To learn how to use the page, see [The browser page](/user/web).

## Addresses

Bookmark, share, or open any view or dialog using the part of the URL after `#`.

![The parts of a page address: an optional daemon name, the view, what to open in the view, and the view's options](/diagrams/reference-web-1.svg)

An address names its daemon first, as `#/@<daemon>/<view>`. An address with no `@<daemon>` belongs to Local; `#/@gpu/flows` opens the Flows view of the `gpu` daemon. Every link the page draws keeps the current `@<daemon>`. Opening an address for another daemon redraws the sidebar and view for that daemon.

An empty address opens `#/new/chat`. An unrecognized first word opens `#/new`. Each path segment is URL-encoded on its own, so a `/` inside a name becomes `%2F`. Views write their options into the query string as you change them without adding entries to the browser history.

### Views

| Address | Opens |
| --- | --- |
| `#/new/chat` | A new chat. Query: `workspace` (the folder), `scratch=1` (no folder), `agent` (the agent spec the nous chip starts on). |
| `#/new` | The new epic form. Query: `workspace`, `scratch=1`, `flow` (the flow picked), `resume` (the name of the epic to resume). |
| `#/chats/<id>` | One chat. |
| `#/epics/<name>` | One epic, running or ended, as a graph or a list of its agents. |
| `#/epics/<name>/agents/<agent>` | The same epic with that agent picked out. |
| `#/epics/<name>/sessions/<key>` | The thread of one session. |
| `#/epics/<name>/logs/<role>` | The log of one agent across its sessions, or of one person. Without `<role>` it opens `#/epics/<name>`. |
| `#/epics/<name>/exomyth` | The trace of the epic. `?tab=flame` opens the flame graph instead of the timeline. |
| `#/epics/import?path=<file>` | Imports the `.hmzepic` file at that path: at once in Humanize Desktop, after you press **Import** in a browser. It then replaces itself with the address of what was imported. |
| `#/live?workspace=<dir>&slot=<slot>` | The run a host holds right now. The address changes to `#/epics/<name>` or `#/chats/<id>` once the run is written down. |
| `#/envs/live?workspace=<dir>&slot=<slot>` | The environments of that run. Query: `chat` (the id of the chat, for a chat), `env` (the environment shown), `tab` (`files`, `terminal` or `changes`). |
| `#/flows` | The Flows page. Query: `flow` (the flow opened), or `tab=verses` with `verse` (the flowverse opened). |
| `#/harness/<harness>/<id>?workspace=<dir>` | One session a coding CLI had on its own, read-only. |

### Dialogs

Open a dialog address to draw the dialog over the current view. Closing it returns to that view and leaves the browser history unchanged. Opening a dialog address directly draws a new chat underneath it.

| Address | Opens |
| --- | --- |
| `#/search` | Search. Query: `kind` (`chat` or `flow`; empty for all), `status` (`running`, `done`, `failed`, `stopped` or `unfinished`), `flow`, `workspace`, `q` (the text), `offset`. |
| `#/download` | Download from a backup target. Query: `target` (the first target when left out). |
| `#/settings/<page>` | Settings. `<page>` is `themes`, `daemons`, `notifications`, `language`, `general`, `accounts`, `nous`, `runtimes`, `backup`, `usage`, `workspace` or `archived`. Any other word opens `general`. `#/settings/themes/<id>` opens the editor of one custom theme. Query: `daemon`, `workspace`, and for `usage` `days` (`7`, `30`, `90` or `365`; default `30`). |
| `#/delete/<id>` | The confirmation before a chat is deleted. Query: `daemon`. |

## Shortcuts

Use these shortcuts on any view. Either <kbd>cmd</kbd> or <kbd>ctrl</kbd> works on every system.

| Keys | Does |
| --- | --- |
| <kbd>cmd+k</kbd> or <kbd>ctrl+k</kbd> | Opens Search. |
| <kbd>cmd+shift+o</kbd> or <kbd>ctrl+shift+o</kbd> | Opens a new chat. |
| <kbd>cmd+.</kbd> or <kbd>ctrl+.</kbd> | Hides or shows the sidebar. |
| <kbd>esc</kbd> | Closes the first of these that is open: a menu, the dialog, the sidebar drawer on a narrow window, the side panel over the view on a narrow window. Pressed inside the Ai-chan drawer, it closes the drawer. |
| <kbd>tab</kbd> and <kbd>shift+tab</kbd> | Inside a dialog, move between its controls and never leave it. |

A narrow window is 860 pixels wide or less. While a confirmation box is open, <kbd>esc</kbd> closes only that box and <kbd>cmd+.</kbd> does nothing.

View-specific keys (for the graph, editor, trace viewer, lists, and menus) are listed on each view's guide page.

## Browser storage

The page stores its layout, appearance, and remote daemons in the browser, never in a daemon. Because storage belongs to the origin, another browser, device, or port starts empty. `hmz web` reuses its last port to preserve your settings. A browser with storage disabled still works but forgets these choices, and clearing site data resets them.

### localStorage

| Key | Holds |
| --- | --- |
| `hmz-pair` | The theme in use. Absent for the default theme. |
| `hmz-mode` | `light` or `dark`. Absent for Auto. |
| `hmz-themes` | The custom themes. |
| `hmz-painted` | The colours of the preset in use, for the first paint. |
| `hmz-language` | `en`, `zh-Hans` or `zh-Hant`. Absent for System. |
| `hmz-sidebar` | `folded` when the sidebar is hidden. |
| `hmz-side-wide` | The sidebar width in pixels, when it is not the default. |
| `hmz-list` | The Group and sort choices of the sidebar list. |
| `hmz-pinned` | The pinned chats and epics, by daemon. |
| `hmz-unread` | The chats and epics marked unread, by daemon. |
| `hmz-opened` | The epics opened out into agents in the sidebar (the last 40). |
| `hmz-shut` | The folded groups of the sidebar (the last 60). |
| `hmz-next-dismissed` | The waiting chats dismissed from the new chat page. |
| `hmz-panel` | Whether the side panel of an epic is open. |
| `hmz-chat-panel` | Whether the side panel of a chat is open. |
| `hmz-shape` | `list` when an epic's agents are drawn as a list. Absent for the graph. |
| `hmz-seen` | The questions you have looked at (the last 500). |
| `hmz-owed` | What each chat last waited on you for. |
| `hmz-ask-draft:<question>` | The unsent answer to a question. Dropped after 14 days. |
| `hmz.nous.last` | The account, model and effort last picked for each harness. |
| `hmz-aichan` | Whether the Ai-chan drawer is open. |
| `hmz-aichan-marks` | Pinned, unread and read marks of Ai-chan conversations, by daemon. |
| `hmz-envs-tree` | The width of the environment list. |
| `hmz-files-side` | The width of the file explorer. |
| `hmz-changes-side` | The width of the list of changes. |
| `hmz-env:<workspace>:<environment>:<key>` | The state of an environment's panels: open file tabs, terminal names, the Changes layout and its commit message draft. |

### IndexedDB

| Database | Holds |
| --- | --- |
| `hmz-daemons` | The remote daemons: each one's name, the daemon id it pins, its routes in order and its STUN and TURN servers. Also this browser's own certificate, which a paired daemon knows it by. |
| `hmz-notifications` | Which kinds of notification you chose, whether the system shows them, and where each daemon's notices were last read up to. |
| `hmz` | The pictures of custom themes. |

## The face bridge

A [face](/builder/faces) is a flow's custom HTML view for a question. The page runs the face in a sandboxed frame and installs a frozen `window.hmz` object before the face's HTML runs. `window.hmz` is the only way a face communicates with the page.

```js
hmz.on('ask', ({ prompt, context, schema, errors }) => { /* draw the question */ })
hmz.on('show', (context) => { /* context pushed with no question */ })
hmz.on('theme', (tokens) => { /* the page's colours changed */ })

const result = await hmz.submit({ approved: true })
// { ok: true }  or  { ok: false, errors: [{ path, message }] }

hmz.resize(320) // a fixed height in pixels; 0 goes back to automatic
```

| Call | Meaning |
| --- | --- |
| `hmz.on(kind, listener)` | Listens for `ask`, `show` or `theme`. Returns a function that stops listening. Any other `kind` throws a `TypeError`. |
| `hmz.submit(value)` | Answers the current question with a JSON value. Returns a promise of `{ok: true}`, or of `{ok: false, errors}` when the answer is refused. It never rejects. |
| `hmz.resize(height)` | Draws the frame `height` pixels tall. `0` makes it as tall as the face's content. |

| Event | The listener gets |
| --- | --- |
| `ask` | `{prompt, context, schema, errors}`: the question text, its context blocks, its JSON schema or `null`, and the errors of the answer refused last. |
| `show` | One context pushed without a question. |
| `theme` | An object of the page's CSS variables by name, such as `--paper` and `--ink`, plus `--scheme`, which is `light` or `dark`. |

The page enforces these rules on a face:

- Registering the first `ask` listener marks the face ready. If a face throws an error before that, or is not ready 5 seconds after its frame loads, the page replaces it with the plain form.
- A listener added late still receives the latest `ask`, the latest `theme`, and every `show` that arrived before anyone listened.
- `hmz.submit` returns an error if the face is not ready or if an earlier answer is still in flight.
- Each entry in `errors` is `{path, message}`, where `path` is a list of property names and indexes into the answer.
- The frame height is clamped between 48 and 4000 pixels.
- The page keeps one frame per session across questions so the face retains its state. It caches frames for up to 8 sessions and replays up to 32 `show` contexts when reloading a face.
- The frame runs with `sandbox="allow-scripts allow-forms"`: it has no cookies, network, or shared storage. The page sets theme variables on `:root` and loads `kit.css` before the face's HTML.
- Form submissions and links to other documents do nothing inside a face; always answer through `hmz.submit`.
- A face can import the page's libraries under `/vendor/` as modules, but cannot reach any other host.

## Bridges

`hmz web` serves the page's static files and three endpoints: `/here`, `/rpc`, and `/dial`. The page does everything else over JSON-RPC to a daemon through the two WebSockets. See [Daemon and wire](/reference/daemon) for the RPC methods and the [CLI reference](/reference/cli) for the command flags.

![The page reaches the local daemon through /rpc, a remote daemon through /dial, and a remote daemon over WebRTC without hmz web](/diagrams/reference-web-2.svg)

### Admission

`hmz web` answers only loopback connections from this machine and prints its entry address on startup:

```text
hmz web: http://127.0.0.1:<port>/?key=<key>
```

| Request | Answer |
| --- | --- |
| `GET /?key=<key>` | `303` to `/`, and sets the cookie `hmz-<port>` to the key, `HttpOnly` and `SameSite=Strict`. A wrong key gets `403`. |
| The page's files | Served without the cookie. They hold nothing of your runs. |
| `/here`, `/rpc`, `/dial` | Need the cookie, and a request made by the server's own page. |

`hmz web` generates a new key on every start. It refuses invalid requests with `{"error": "<one sentence>"}`, checking in this order:

| Status | When | `error` |
| --- | --- | --- |
| `403` | The connection is not from a loopback address. | `Open the address hmz web printed, on the machine it runs on.` |
| `403` | `GET /?key=` with a wrong key. | `That key is not this server's: open the address hmz web printed.` |
| `401` | An endpoint asked without the cookie. The page then shows `This browser is not let in.` | `Open the address hmz web printed to let this browser in.` |
| `403` | An endpoint asked by another page: `Sec-Fetch-Site` is not `same-origin`, or, with no `Sec-Fetch-Site`, `Origin` does not match `Host` over `http`. | `Use this server's own page to make this request.` |
| `405` | Any method other than `GET`. | `Only the page's own files are here.` |
| `400` | `/rpc` or `/dial` asked without a WebSocket upgrade. | `Open this as a WebSocket.` |
| `404` | A path that is not one of the page's files. | `There is nothing here by that name.` |
| `500` | Anything else. The traceback goes to the standard error of `hmz web`. | `Something went wrong here: <why>` |

Idle HTTP connections close after 60 seconds. Open WebSockets never close for being idle.

### `/here`

`GET /here` returns `{"here": "<directory>"}` with `Cache-Control: no-store`, giving the directory where `hmz web` started. The page offers this directory first as the folder on Local.

### `/rpc`

Open `GET /rpc` as a WebSocket to reach the local daemon, starting it if needed. Every binary message from the page goes to the daemon's socket as raw bytes, and every byte from the daemon comes back in binary messages unchanged and in order.

| Close code | Reason | When |
| --- | --- | --- |
| `1011` | `The daemon cannot be reached: <why>` | The daemon could not be reached or started. |
| `1000` | `The daemon closed.` | The daemon closed its end. |
| `1000` | none | The page closed, or sent a text message. |

### `/dial`

Open `GET /dial?route=<route>&id=<daemon id>` as a WebSocket to connect to a remote daemon over routes a browser cannot open directly: `stdio:ssh`, `stdio:wsl`, `tcp`, `ws`, `easytier`, and `relay`. Pass the expected daemon ID in `id`; every route except `stdio:ssh` and `stdio:wsl` requires it.

While opening the route, the server sends progress as JSON text messages:

```json
{"state": "installing", "detail": "Downloading EasyTier 2.6.4"}
```

| `state` | Meaning |
| --- | --- |
| `connecting` | The route is being opened. |
| `installing` | Something the route needs is being installed. |
| `up` | The route is open. From here on the WebSocket carries bytes both ways, as `/rpc` does. |
| `failed` | The route did not open. The WebSocket closes next. |

`detail` holds the latest line of progress text, which may be empty. With `failed` it says what went wrong.

| Close code | Reason | When |
| --- | --- | --- |
| `1008` | `<route> is not a route.` | `route` cannot be read as a route. |
| `1008` | `<route> is not dialed here.` | A `unix:` or `stdio:local` route, which `/rpc` covers, or a `webrtc:` route, which the browser opens itself. |
| `1008` | `<route> needs the id of the daemon it reaches.` | `id` is missing for a route that needs it. |
| `1011` | What went wrong, as `failed` said it. | The route did not open. |
| `1000` | What the route said as it ended, or `The daemon closed.` | The far end closed. |
| `1000` | none | The page closed, sent a text message, or sent bytes before `up`. |

Close reasons are truncated to 120 bytes. Closing a `/dial` socket stops any helper process it started for its route. Stopping `hmz web` closes every open `/dial` socket without stopping any runs.
