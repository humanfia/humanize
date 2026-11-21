---
title: Daemon and wire
description: Look up the routes, listeners, session rules, error codes and JSON-RPC methods of the Humanize daemon.
---

# Daemon and wire

Every Humanize client connects to a daemon. This page lists the route syntax, session rules, error codes, and JSON-RPC methods of the daemon. For the normative specification, see `protocol/wire.md` and `protocol/daemon.md` in the repository.

![A session in layers: a carrier, its security layer, then frames that carry JSON-RPC](/diagrams/reference-daemon-1.svg)

*A carrier, its security layer, and the frames and methods shared across every carrier.*

For task guides, see [The daemon](/user/daemon), [Connect to other machines](/user/daemons), and [Relays and WebRTC](/user/relay).

## Routes

A route names one carrier to one daemon. Clients keep an ordered list of routes per daemon, and pairing codes carry a daemon's routes. Humanize supports nine route kinds:

| Route | Trusted | Carrier |
| --- | --- | --- |
| `unix:` | yes | The socket of this machine's daemon. Starts the daemon if none runs. |
| `unix:<path>` | yes | The Unix socket at an absolute path. Starts nothing. |
| `stdio:local` | yes | Standard input and output of `hmz daemon connect --stdio`, started on this machine through the login shell. |
| `stdio:ssh://[<user>@]<host>[:<port>][?<params>]` | yes | The same command run on the host through `ssh`. |
| `stdio:wsl[:<distro>]` | yes | The same command run in a WSL distribution through `wsl.exe`. Uses the default distribution when `<distro>` is omitted. |
| `tcp://<host>:<port>` | no | A TCP connection. |
| `ws://<host>[:<port>][/<path>]`, `wss://…` | no | A WebSocket carrying bytes in binary messages. |
| `easytier:<name>` | no | A TCP connection across the EasyTier network described by entry `<name>` in the `easytier` setting. |
| `relay:<ws-url>` | no | A byte splice through the relay at that WebSocket URL. |
| `webrtc:<ws-url>` | no | A WebRTC data channel signaled through the relay at that URL. Opened only by the page itself, in a browser or in Desktop. |

A trusted carrier sends frames directly and pairs the session from the start as the device `local`. An untrusted carrier wraps frames in mutual TLS 1.3 (ALPN `hmz`) pinned to the daemon ID, or in the DTLS data channel for `webrtc:`. Using `wss://` does not make a carrier trusted.

Grammar rules:

- A port is a number from 1 to 65535. A host is never empty. Wrap IPv6 addresses in brackets.
- Percent-encode parts as in a URL.
- `<name>` starts with a letter or digit, followed by letters, digits, `.`, `_`, or `-`.
- Invalid route text is refused whole: `<route> is not a route.`
- A valid route of a kind the client does not open is refused: `<route> cannot be reached from here.` A `stdio:ssh` route whose destination (`<user>@<host>`, or `<host>` with no user) starts with `-` or holds whitespace is refused the same way.
- An untrusted route without a pinned daemon ID is refused: `<route> needs the id of the daemon it reaches.`

### SSH route parameters

| Parameter | ssh option |
| --- | --- |
| `identity=<file>` | `IdentityFile` |
| `jump=<host>` | `ProxyJump` |
| `option=<Keyword>=<value>` | Any keyword of `ssh_config`, as in `option=ServerAliveInterval=30` |

Join parameters with `&`. They apply in the order given. If a host matches a `Host` entry in your SSH configuration, `ssh` resolves it on each connection. `ssh` always runs in batch mode: it never prompts for a password or accepts an unknown host key.

```text
unix:
stdio:ssh://alex@build.example.com:2222?identity=~%2F.ssh%2Fid_ed25519&jump=bastion
stdio:wsl:Ubuntu
tcp://studio.example.com:41817
wss://studio.example.com/hmz
easytier:home
relay:wss://relay.example.com
webrtc:wss://relay.example.com
```

### Supported routes by client

| Client | Routes it opens |
| --- | --- |
| `hmz` in a terminal, the SDK | Every kind except `webrtc:`. `stdio:wsl` only on Windows. |
| Humanize Desktop | The app opens `stdio:local` (not on Windows), `stdio:wsl` (Windows only), `stdio:ssh`, `tcp`, `ws`, `wss`, `easytier`, and `relay`. Its page opens `webrtc:`. |
| A browser page, directly | `webrtc:` |
| A browser page, through `hmz web` | This machine's daemon, and every kind except `unix:`, `stdio:local`, and `webrtc:` |

### Opening and reconnecting

| Rule | Value |
| --- | --- |
| Timeout to open a route, secure it, and answer `session.hello` | 30 seconds, then `<route> did not open within 30 seconds.` |
| Delay before starting the next route when racing several | 250 milliseconds after the previous route, or immediately if all earlier routes fail |
| Winning route | The first whose `session.hello` matches the pinned daemon ID. All others close. |
| Reconnect backoff for a lost session | 1 second, doubling up to 60 seconds |
| First line of a `stdio:` carrier | `hmz-stdio/1`. Up to 65 536 bytes before it are discarded. |

## Listeners

Alongside its local socket, a daemon listens on the addresses configured in the `listen` key of [settings.yaml](/reference/settings) or passed to repeatable `hmz daemon serve --listen SPEC` flags. Every listener is untrusted.

| Spec | Listens |
| --- | --- |
| `tcp://<address>:<port>` | On that TCP address. Port `0` picks any free port. |
| `ws://<address>:<port>` | As a plain `ws` WebSocket server at the root path. Port `0` picks any free port. Other requests get 404. |
| `relay:<ws-url>` | By registering at a relay for native clients. |
| `webrtc:<ws-url>` | By registering at a relay for pages, in a browser or in Desktop. Requires the `webrtc` extra of hmz. |
| `easytier:<name>` | By joining the EasyTier network of entry `<name>`. |

```yaml
listen:
  - tcp://0.0.0.0:41817
  - relay:wss://relay.example.com
  - webrtc:wss://relay.example.com
```

- Any other spec, including `wss://` or a `ws://` spec with a path, is refused by `--listen`: `<spec> is not a listener.` In the `listen` setting it is skipped and logged to `daemon.log`.
- Listeners in the `listen` setting open and close live as the setting changes.
- A `relay:` and a `webrtc:` listener at the same relay share one registration.
- If a listener fails to open, the daemon logs the failure to `daemon.log` and retries after 1 second, doubling up to 60 seconds.
- A daemon with a listener, or started by `hmz daemon serve`, never exits when idle.
- A pairing code created with `hmz daemon pair` includes the routes of all open listeners, unless `--route` names others.

## Devices and pairing

An untrusted session belongs to a device identified by its key fingerprint: 52 lowercase base32 characters. The daemon ID uses the same fingerprint format for the daemon's machine. A page over `webrtc:` is identified by `dtls:` followed by the fingerprint of its DTLS certificate.

| Session | Allowed methods |
| --- | --- |
| Over a trusted carrier | Every method, as the device `local` |
| Untrusted, device paired | Every method |
| Untrusted, device unpaired | `session.hello`, `pair.claim`, and `rpc.discover` only |

Any other call from an unpaired session fails with 401: `This device is not paired: claim a pairing code first.`

## Frames

Every byte of a session travels inside a frame.

| Part | Form |
| --- | --- |
| Length | Unsigned 32-bit integer, big-endian |
| Payload | One UTF-8 JSON object, from 1 to 33 554 432 bytes (32 MiB) |

A frame length of 0 or above 33 554 432 bytes closes the session.

## JSON-RPC

Each frame holds one JSON-RPC 2.0 request, notification, or response.

- The client sends requests and one notification: `session.cancel`. The daemon sends responses and notifications, never requests.
- Pass parameters by name in an object. Unknown parameters are refused.
- Request `id` values are strings or integers unique among unanswered calls in the session.
- Batch requests fail with -32600: `Send one request a frame.`
- The daemon answers each call once, in any order. Calls naming the same `sub` run in the order sent, except `epic.aside` and `env.*`.
- Send `session.cancel` with a call's `id` to cancel it. Cancelled calls fail with -32800.
- Clients ignore unknown notifications and fields.

## Hello and versions

Start every session by calling `session.hello`. Any other first call fails with -32600: `A client says session.hello first.` Calling it again fails with -32600: `This session has already said hello.`

| Parameter | Value |
| --- | --- |
| `protocol` | The client's protocol version. This release uses `3.0.0`. |
| `client.name` | The user's name for the client |
| `client.kind` | One of `tui`, `web`, `desktop`, `cli`, `sdk`, `bridge`, `ai-chan` |

| Response field | Value |
| --- | --- |
| `daemon_id` | The daemon's ID |
| `version` | The daemon's hmz version |
| `protocol` | The daemon's protocol version |
| `capabilities` | Optional features enabled on the daemon. `webrtc` is the only defined capability. |
| `machine` | The daemon's hostname up to its first `.` |
| `wsl` | The WSL distribution the daemon runs in, or `null` |
| `newer` | A newer available release of hmz, or `""` |
| `paired` | Whether the session is paired |
| `device` | The paired device name: `local` over a trusted carrier, or `""` when unpaired |

```json
{"jsonrpc": "2.0", "id": 1, "method": "session.hello",
 "params": {"protocol": "3.0.0", "client": {"name": "alex", "kind": "sdk"}}}
```

The daemon accepts clients with the same major protocol version and a minor version less than or equal to its own. Other clients fail with 426, with the daemon's version in `data.protocol`. After a 426 error, the client makes no further calls on that session.

| Client version | Message |
| --- | --- |
| Older than the daemon | ``held for frontends by a newer Humanize; `hmz` of it reads it`` |
| Newer than the daemon | `the runs on this machine are held by an older Humanize (pid <pid>); stop it with that version` |

## Error codes

Each error has a `code`, a one-sentence `message`, and an optional `data` object with method-specific fields.

| Code | Meaning |
| --- | --- |
| -32700 | Frame payload is not valid JSON: `Send JSON.` |
| -32600 | Invalid JSON-RPC 2.0 request, batch request, or call before `session.hello` |
| -32601 | Unknown method: `There is no method <method>.` |
| -32602 | Parameters do not match the OpenRPC schema |
| -32603 | Unhandled error: `Something went wrong here: <why>`. Traceback written to `daemon.log`. |
| -32800 | Call cancelled: `The call was cancelled.` |
| 400 | Invalid parameter value |
| 401 | Unpaired session |
| 403 | Forbidden for this device (including invalid pairing codes) or outside an Ai-chan session's reach |
| 404 | Target resource does not exist |
| 409 | Conflict with current state, including host refusals |
| 410 | Unknown subscription: `There is no subscription <sub>.` |
| 413 | Request or response exceeds size limit |
| 426 | Incompatible protocol version |
| 502 | Upstream program or service did not respond |
| 503 | Required resource is temporarily unreachable |

Parameter errors (-32602) return `<method> takes no <names>.`, `<method> takes <name> as <type>.`, or `<method> needs <name>.`

## Idempotent writes

Write methods accept an optional `idem` parameter: a unique 1-to-64-character string generated per write. If a connection drops and you retry the write with the same `idem`, the daemon returns the original response without repeating the action.

| Rule | Value |
| --- | --- |
| Response retention time | 600 seconds |
| Responses kept per device | Latest 1 024 |
| Reusing `idem` on a different method | Fails with 409: `That idem key was used for another method.` |

## Subscriptions and notifications

Call `epic.attach` or `notices.subscribe` to open a subscription and receive its `sub` ID. The daemon sends notifications for that `sub` in order.

| Notification | Parameters | Carries |
| --- | --- | --- |
| `epic.event` | `sub`, `message` | One message from an epic subscription |
| `notices.event` | `sub`, `notice` or `gone` | One notice, or the end of a subscription that fell behind |

- A subscription ends when you call `epic.detach` or `notices.unsubscribe`, when an epic subscription sends `gone`, or when the session closes.
- Calling a method with a closed or unknown `sub` fails with 410.
- When reconnecting, pass `since` (`{epoch, seq}`) to `epic.attach` or `after` to `notices.subscribe` to receive only records or notices newer than the last one seen.
- An `epic.event` `message` is identified by its `type`. An epic subscription ends with the message `gone`, whose `why` is `let go`, `the host was closed`, `too far behind; attach again`, `the host went away`, or, for an Ai-chan session, `out of Ai-chan's scope`.

See [Events and records](/reference/events#messages-of-an-attached-epic) for every message of an epic subscription, and [its Notices section](/reference/events#notices) for notice kinds and keys.

## Limits

| Limit | Value |
| --- | --- |
| Frame payload | 33 554 432 bytes. Larger responses fail with 413; larger requests close the session. |
| Queued frames for a slow session | 64 MiB. Exceeding this drops queued notifications and closes all session subscriptions with `too far behind; attach again` (epics) or `too far behind; subscribe again` (notices). Responses are kept. |
| Write handle file size | 2 147 483 648 bytes |
| `files.read` or `files.write` chunk | 1 048 576 bytes |
| Idle handle timeout | 600 seconds |

## Methods

The daemon serves 142 methods. Their parameter and result schemas live in the OpenRPC document.

A method's scope defines what it acts on and whether an [Ai-chan](/user/ai-chan) session may call it. Standard paired sessions may call every method.

| Scope | Acts on | Ai-chan access |
| --- | --- | --- |
| `any` | Nothing workspace-specific, or lists filtered to the session's reach | Always |
| `daemon` | The daemon, its machine, or all workspaces | Only with `daemon` scope |
| `workspace` | The workspace named in its parameters | When the workspace is in reach |
| `epic` | The epic or host named in its parameters | When the epic or host is in reach |
| `never` | Pairing, devices, credentials, network secrets, Ai-chan conversations | Never |

Write methods accept `idem`, except `hosts.open`, `hosts.detach`, `env.term.open`, `env.term.input`, `env.term.resize`, and `env.term.close`.

### Session and discovery

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `session.hello` | `any` |  | Open the session with the client's protocol version and name. |
| `session.cancel` | `any` |  | Cancel an in-flight call (notification; sends no response). |
| `rpc.discover` | `any` |  | Return the OpenRPC document. |

### Pairing and devices

See [Connect to other machines](/user/daemons) for the pairing workflow.

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `pair.create` | `never` | yes | Create a pairing code. |
| `pair.claim` | `never` |  | Pair this session's device using a pairing code token. |
| `devices.list` | `never` |  | List paired devices. |
| `devices.revoke` | `never` | yes | Revoke a paired device and close its sessions. |

### Hosts

A host process runs one workspace and slot. These methods manage hosts without attaching to them.

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `hosts.list` | `any` |  | List all active hosts. |
| `hosts.running` | `any` |  | List hosts with a running or stopping epic or chat. |
| `hosts.open` | `epic` | yes | Start a host for a workspace and slot without attaching. |
| `hosts.status` | `epic` |  | Get a host's status. |
| `hosts.detach` | `epic` | yes | Detach all frontends from a host. |
| `hosts.stop` | `epic` | yes | Close a host. |
| `hosts.env.list` | `epic` |  | List environments of the epic running on a host. |
| `hosts.env.read` | `epic` |  | Read a file in an env. |
| `hosts.env.write` | `epic` | yes | Overwrite a file in an env. |
| `hosts.env.exec` | `epic` | yes | Run a command in an env's working directory. |
| `hosts.env.grep` | `epic` |  | Search files in an env. |

### Epics

`epic.attach` opens a subscription and returns its `sub` ID. All other `epic.*` methods take that `sub`.

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `epic.attach` | `epic` |  | Attach to a host as a frontend and open an epic subscription. |
| `epic.start` | `workspace` | yes | Start an epic on the host. |
| `epic.say` | `epic` | yes | Send a message line. |
| `epic.answer` | `epic` | yes | Answer a question with text or a schema value. |
| `epic.face` | `epic` |  | Read a flow's face by its hash. |
| `epic.stop` | `epic` | yes | Stop the running epic. |
| `epic.force` | `epic` | yes | Force-stop a stopping epic. |
| `epic.afk` | `epic` | yes | Mark one or all roles away or back. |
| `epic.claim` | `epic` | yes | Claim a role for this frontend. |
| `epic.release` | `epic` | yes | Release a role. |
| `epic.board` | `epic` | yes | Write or remove a board line. |
| `epic.aside` | `epic` |  | Open or query a side conversation on this frontend. |
| `epic.unaside` | `epic` |  | Close a side conversation. |
| `epic.status` | `epic` |  | Get the host's status. |
| `epic.detach` | `any` |  | Detach this frontend. |
| `epic.quit` | `epic` | yes | Close the host. |

### Environments of an attached epic

Manage files, terminals, and Git in an environment of the epic attached under `sub`.

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `env.list` | `epic` |  | List a directory in an environment. |
| `env.stat` | `epic` |  | Stat a path in an environment. |
| `env.read` | `epic` |  | Read a file in an environment. |
| `env.find` | `epic` |  | List files in an environment for quick-open. |
| `env.search` | `epic` |  | Search file contents in an environment. |
| `env.write` | `epic` | yes | Write a file in an environment. |
| `env.mkdir` | `epic` | yes | Create a directory and its parents in an environment. |
| `env.rename` | `epic` | yes | Move or rename a path in an environment. |
| `env.remove` | `epic` | yes | Recursively remove a path in an environment. |
| `env.term.open` | `epic` | yes | Open or reattach to a terminal in an environment. |
| `env.term.input` | `epic` | yes | Send input to a terminal. |
| `env.term.resize` | `epic` | yes | Resize a terminal. |
| `env.term.ack` | `epic` |  | Acknowledge bytes of terminal output rendered by this frontend. |
| `env.term.close` | `epic` | yes | Kill a terminal. |
| `env.term.list` | `epic` |  | List terminals in an environment. |
| `env.git.status` | `epic` |  | Get Git status of an environment. |
| `env.git.diff` | `epic` |  | Get the before and after contents of a changed file. |
| `env.git.log` | `epic` |  | List recent commits in an environment. |
| `env.git.stage` | `epic` | yes | Stage paths. |
| `env.git.unstage` | `epic` | yes | Unstage paths. |
| `env.git.discard` | `epic` | yes | Discard working tree changes for paths. |
| `env.git.commit` | `epic` | yes | Commit staged changes. |
| `env.git.snapshots` | `epic` |  | List snapshots of an environment. |
| `env.git.rewind` | `epic` | yes | Rewind an environment to a snapshot. |

### Chats

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `chat.start` | `workspace` | yes | Start or resume a chat on a chat host. |
| `chat.say` | `epic` | yes | Send the next message in a chat. |
| `chat.commands` | `epic` |  | List native entries, hmz names, flows, and preferences for chat prefixes. |
| `chat.set` | `epic` | yes | Override a chat's preference for $ names or set its permission mode. |
| `chat.move` | `epic` | yes | Move a chat to another env between turns. |
| `chat.stop` | `epic` | yes | Stop the active turn and leave the chat idle. |
| `chat.list` | `workspace` |  | List saved chats. |
| `chat.get` | `daemon` |  | Get a chat and optionally its transcript. |
| `chat.rename` | `daemon` | yes | Rename a chat. |
| `chat.fork` | `daemon` | yes | Fork a new chat from an existing conversation. |
| `chat.archive` | `daemon` | yes | Archive a chat to hide it from the list. |
| `chat.unarchive` | `daemon` | yes | Restore an archived chat to the list. |
| `chat.backup` | `daemon` | yes | Back up a chat to its configured or specified targets. |
| `chat.delete` | `daemon` | yes | Permanently delete a chat and its harness sessions. |
| `chat.harness.list` | `daemon` |  | List native harness sessions in a workspace. |
| `chat.harness.get` | `daemon` |  | Get a native harness session and optionally its transcript. |
| `chat.harness.adopt` | `daemon` | yes | Fork a new Humanize chat from a native harness session. |

### Side questions and Ai-chan

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `btw.list` | `epic` |  | List side conversations for an epic. |
| `btw.ask` | `epic` |  | Ask a side question. |
| `btw.leave` | `workspace` |  | Close side conversations. |
| `aichan.create` | `never` | yes | Create an Ai-chan conversation and start its host. |
| `aichan.list` | `never` |  | List Ai-chan conversations, newest first. |
| `aichan.rename` | `never` | yes | Rename an Ai-chan conversation. |
| `aichan.forget` | `never` | yes | Delete an Ai-chan conversation and close its host. |

Call `aichan.create` to get `id`, `workspace`, and `slot`. Each row in `aichan.list` has the same `workspace`, a `slot` of the form `ai:<hex>`, and a `state`: `running` during an open turn, `waiting` between turns, or `folded` when no host holds the conversation. Call `epic.attach` with that workspace and slot to follow the conversation; attaching to a folded conversation restarts its host. Send a line with `chat.say`, naming that workspace and slot, and stop an open turn with `epic.stop` or `chat.stop`.

### Runs, backups and file transfer

`files.*` transfers files through a handle in chunks up to 1 048 576 bytes. A handle closes when its session ends, when you call `files.close`, after 600 seconds of inactivity, or once the method it was given to has taken it.

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `runs.list` | `any` |  | List recorded epics. |
| `runs.get` | `epic` |  | Get an epic. |
| `runs.trace` | `epic` |  | Get an epic's transcripts. |
| `runs.timeline` | `epic` |  | Get an epic's Exomyth timeline. |
| `runs.span` | `epic` |  | Get one span from the last generated timeline. |
| `runs.bundle` | `epic` |  | Bundle an epic into a .hmzepic archive and return a read handle. |
| `runs.backup` | `epic` | yes | Back up an epic. |
| `runs.import` | `daemon` | yes | Import an archive from a write handle or file path. |
| `runs.usage` | `workspace` |  | Get epic usage totals. |
| `backups.epics` | `daemon` |  | List epics and chats stored in a backup target. |
| `backups.pull` | `daemon` | yes | Download an epic or chat from a backup target. |
| `files.create` | `any` |  | Create a write handle. |
| `files.write` | `any` |  | Append a chunk to a write handle. |
| `files.read` | `any` |  | Read a chunk from a read handle. |
| `files.close` | `any` |  | Close a handle. |

### Flows, flowverses and workspaces

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `flows.list` | `workspace` |  | List available flows, including workspace flows when a workspace is given. |
| `flows.get` | `workspace` |  | Get a flow's declaration. |
| `flows.backends` | `any` |  | List installed CLIs, their accounts, and their models. |
| `flows.setup` | `workspace` | yes | Save a workspace's flow configuration. |
| `flows.check` | `workspace` |  | Validate a flow and its configuration without starting an epic. |
| `flows.fork` | `workspace` | yes | Copy a flow into the workspace. |
| `flowverses.list` | `any` |  | List all flowverses and installed flows. |
| `flowverses.get` | `any` |  | Get a flowverse. |
| `flowverses.add` | `daemon` | yes | Add a flowverse. |
| `flowverses.fetch` | `daemon` | yes | Fetch a flowverse's index. |
| `flowverses.remove` | `daemon` | yes | Remove a flowverse and its installed flows. |
| `flowverses.install` | `daemon` | yes | Install a flow release. |
| `flowverses.uninstall` | `daemon` | yes | Uninstall a flow. |
| `workspaces.list` | `any` |  | List all workspaces. |
| `workspaces.add` | `workspace` | yes | Add a workspace to settings. |
| `workspaces.forget` | `workspace` | yes | Remove a workspace's saved configuration. |
| `paths.list` | `daemon` |  | List a directory. |
| `paths.complete` | `daemon` |  | Autocomplete a directory path. |

### Settings, accounts, nous and runtimes

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `settings.get` | `workspace` |  | Get machine and workspace settings. |
| `settings.set` | `daemon` | yes | Update settings. |
| `settings.forget` | `workspace` | yes | Clear a workspace's saved settings. |
| `accounts.list` | `any` |  | List every account by its names. |
| `accounts.create` | `never` | yes | Create an account. |
| `accounts.correct` | `never` | yes | Overwrite an account. |
| `accounts.remove` | `daemon` | yes | Remove an account. |
| `accounts.models` | `daemon` | yes | Query the models a CLI offers under an account. |
| `accounts.copy` | `never` | yes | Copy an account to another CLI. |
| `nous.list` | `any` |  | List every nous. |
| `nous.scan` | `daemon` | yes | Scan all installed harnesses and accounts for available models. |
| `nous.set` | `daemon` | yes | Write a nous entry. |
| `nous.rename` | `daemon` | yes | Rename a virtual nous. |
| `nous.clear` | `daemon` | yes | Remove a nous. |
| `runtimes.list` | `any` |  | List all runtimes. |
| `runtimes.set` | `daemon` | yes | Write a runtime. |
| `runtimes.remove` | `daemon` | yes | Remove a runtime. |
| `runtimes.check` | `daemon` |  | Reach a runtime and report what it has. |
| `runtimes.hosts` | `daemon` |  | List hosts from the SSH configuration. |
| `runtimes.import` | `daemon` | yes | Import SSH hosts as runtimes. |
| `easytier.list` | `daemon` |  | List EasyTier entries without secrets. |
| `easytier.set` | `never` | yes | Write an EasyTier entry. |
| `easytier.remove` | `never` | yes | Remove an EasyTier entry. |
| `easytier.nodes` | `any` |  | List shared EasyTier nodes. |

### Notices

| Method | Scope | Write | Description |
| --- | --- | --- | --- |
| `notices.list` | `any` |  | List notices after a given ID. |
| `notices.subscribe` | `any` |  | Open a notices subscription. |
| `notices.unsubscribe` | `any` |  | Close a notices subscription. |

## The OpenRPC document

The OpenRPC 1.3 specification at `protocol/openrpc.json` in the repository defines every method the daemon serves. Methods outside this document are rejected.

- Every method entry lists its named parameters, the JSON Schema for each parameter and result, and its error codes.
- `x-hmz-reach` defines the method's scope and which parameters carry the workspace, slot, epic, or `sub`.
- `x-hmz-writes` is `true` for write methods.
- Daemon notifications are defined under `x-notifications` at the root.

Call `rpc.discover` from any session, paired or unpaired, to fetch the document:

```python
from hmz.sdk import Client

client = Client.local(name="docs")
print(client.protocol, client.device)
document = client.call("rpc.discover")
print(document["info"]["version"], len(document["methods"]))
client.close()
```

```text
3.0.0 local
3.0.0 142
```

`Client.local` connects to this machine's daemon over its Unix socket and starts the daemon if needed. See [The Python SDK](/builder/sdk) for the full `Client` API.
