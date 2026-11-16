---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# Daemon reference

The **daemon**: one process per machine and user, the one JSON-RPC endpoint every client
reaches -- on its socket, and on whatever it [listens](#listeners) on beside it -- and which
speaks for each client to the **host** of the workspace it names: one process per workspace and
slot, holding that workspace's runs. Every client is a client of a daemon over a session of the
[wire protocol](https://github.com/humanfia/humanize/blob/main/protocol/wire.md): frames and
JSON-RPC 2.0 whose methods `protocol/openrpc.json` lists. A frontend is an
`hmz` interface (`kind` `tui`), the [web interface](/reference/web) `hmz web` serves (`kind`
`web`, named `browser`), or a program linked through the [SDK](/reference/sdk#link) (`kind`
`sdk`). Package: `hmz.daemon`. Notation: [Conventions](/reference/#conventions).

```text
 hmz (alice@tui) ──┐ daemon.sock (trusted)          ┌─ host process, ~/src/api ─────────────┐
 hmz web (browser) ┼────────────── daemon ─────┬──▶│ Host: the run, claims, away, queued  │
 program (ci@sdk) ─┘                (one per   │   │ lines, questions, history, snapshots │
 another machine ── tcp/ws/relay ── machine)   │   └──────────────────────────────────────┘
   (mutual TLS)     webrtc (DTLS)              └──▶┌─ host process, ~/src/web ─────────────┐
                                                   │ …                                     │
 JSON-RPC sessions end at the daemon, which        └───────────────────────────────────────┘
 speaks to each host down a link of its own.
```

## Terms {#terms}

| Term | Definition |
| --- | --- |
| host | `hmz.runtime.Host`: a workspace's runs as every attached frontend shares them. Held in a host process (or, for an epic run on fakes, in the calling program's [private daemon](/reference/sdk#fakes)). |
| daemon | The detached process, one per machine and user, serving JSON-RPC on `daemon.sock` and its listeners, and speaking to the host process of each workspace for its clients. |
| host process | The detached process, one per workspace and slot, started by the daemon, standing in that workspace and holding its `Host`. Reached only by the daemon, down a socket pair. |
| session | One client's connection to the daemon: `session.hello`, then calls, answers and notifications. |
| frontend | One attachment to a host: one epic subscription (`epic.attach`), held by a [`Link`](#link). Has a client id (`c1`, `c2`, …) and a name. |
| run | One run of one flow on the host, numbered from 1 per host. |
| request | A call to an epic, `epic.<do>`; a `Link` takes it as a JSON object with `do`. |
| message | A JSON object the host sends, with `type`, carried as the notification `epic.event`. |

## When a daemon is used {#when-used}

| Caller | Host |
| --- | --- |
| `hmz`, whatever the terminal | A host process, found or started (see [CLI › Where the runs are held](/reference/cli#where-runs-are-held)). After 3 failed attempts, 0.5 s apart, stderr says `hmz: the daemon cannot be reached: <why>` and it exits `1`. |
| `hmz web` | A host process, found or started with [`attach`](#module), tried 3 times 0.5 s apart; where none can be had it says so and exits `1`. |
| `hmz exec`, `Hmz().run()` | A host process on a new exec slot (`exec:<hex>`) of the workspace, started by this machine's daemon. |
| `Hmz().run()` with a driver object, `fakes.run_fake()` | A host in the calling program's own [private daemon](/reference/sdk#fakes). |
| `Daemons().host()`, `hmz.daemon.host()` | A host process, found or started. |

## Files {#files}

Directory: `<tmp>/humanize-<uid>/`, where `<tmp>` is Python's `tempfile.gettempdir()` (`$TMPDIR`,
`$TEMP` or `$TMP`, else `/tmp`) and `<uid>` the user's id: `hmz.machine()`, shared with
[other caches](/reference/files#temporary). Made `0700` where missing; one that is not a
directory, not this user's, or that its group or others can write is refused with
`PermissionError: <dir> is not a directory only this user can write; remove it`. Never under
`$HUMANIZE_HOME`: a daemon is one machine's process, and a home directory several machines
mount would list each machine's daemon on every other.

| File | Written | Mode | Content | Removed |
| --- | --- | --- | --- | --- |
| `daemon.sock` | when the daemon binds | `0600` | Unix stream socket, backlog 64. A stale one is unlinked only after the lock is held. | when the daemon closes |
| `daemon.json` | after binding, atomically (`.daemon.json.<random>.new`, fsync → rename) | `0600` | See below. | when the daemon closes |
| `daemon.lock` | at start | `0600` | Empty. Held with `flock(LOCK_EX \| LOCK_NB)` for the daemon's lifetime; the kernel releases it when the process ends. | never |
| `daemon.log` | at start; append | `0600` | What belongs to no run: the daemon's file descriptors 1 and 2, a host process's before it has held a run, start failures, socket-path `chdir` failures. Never rotated. | never |

What a host process writes while it holds a run goes into that run's epic instead, as
`host.log` (`0600`, append, never rotated) beside its
[`epic.jsonl`](/reference/files#h-epics-ws-stamp-hex6): the host's file descriptors 1 and 2
(output of CLIs the run spawns), and entries written by `logged()`. The run is the one going, else
the one stopping, else the last.

```json
{
  "pid": 41237,
  "started": "2026-09-30T08:15:42Z",
  "kind": "daemon",
  "protocol": "3.0.0"
}
```

| Key | Type | Value |
| --- | --- | --- |
| `pid` | int | The daemon process. |
| `started` | string | UTC, `%Y-%m-%dT%H:%M:%SZ`. |
| `kind` | string | `"daemon"`. |
| `protocol` | string | `3.0.0`, `hmz.rpc.PROTOCOL`. A `daemon.json` without it, or of another major version, is another Humanize's daemon, which nothing here reaches. |

A workspace is known by `str(Path(workspace or cwd).resolve())`: two checkouts of one
repository are two workspaces, and two spellings of one directory are one.

The temporary directory is the machine's to clean: a reboot empties it, and so may the system
(`systemd-tmpfiles`, macOS's periodic cleanup) for files left untouched. A running daemon marks
its directory and its four files as used every hour; `daemon.log` left behind by one that has
gone is cleaned with the rest.

**Socket path length.** Where `<dir>/daemon.sock` is longer than 100 bytes -- a long `$TMPDIR`
-- binding and connecting `chdir` into the directory and use the relative name.

## Discovery {#discovery}

| Function | Returns | Rule |
| --- | --- | --- |
| `running(workspace=None)` | `Daemon \| None` | The host of that workspace, where the daemon's `daemon.json` parses as an object with an int `pid` of a live process (`kill(pid, 0)`; `EPERM` counts as alive), its socket accepts a connection within 1 s, its `hosts.list` names the workspace, and that host's pid is alive. Where the daemon's `protocol` is not of major version `3`: a `Daemon` for the daemon itself, with its `protocol` (`""` for none). Otherwise `None`. |
| `daemons()` | `list[Daemon]` | Every host the daemon lists whose pid is alive, sorted by `started` (oldest first); the daemon itself where its `protocol` is of another major version; `[]` with no daemon. |
| `host(workspace=None, *, seconds=10.0, slot="")` | `Daemon` | Starts the daemon where none is, then calls `hosts.open`, which starts the host where none is; waits up to `seconds` for each. Tried twice, 0.1 s apart: a daemon that went as its host came up is started again. |
| `start(seconds=10.0)` | `None` | Starts the daemon where none is, as the first client that needs one does. |
| `older(daemon)` | `str` | `the runs in <workspace> are held by an older Humanize (pid <pid>); stop it with that version`, or `on this machine` for a daemon. |

`host()` raises `OSError`:

| Condition | `OSError` text |
| --- | --- |
| another Humanize's daemon (protocol of another major version), or one refusing `session.hello` with 426 | `[Errno <EADDRINUSE>] ` + `older(daemon)` (98 on Linux, 48 on macOS) |
| the daemon or the new host reported a failure | the reported text, e.g. `the run could not be held: <why>` |
| no daemon is listening after the wait | `this machine's daemon did not come up` |
| `hosts.open` refused | its message, e.g. `This chat has folded away.` |
| no host came up after both tries | `the runs in <workspace> did not come up` |

Two callers racing to start the daemon: the loser's lock fails (`EAGAIN`: `[Errno 11] Resource
temporarily unavailable` on Linux, `[Errno 35]` on macOS), and `host()` uses the winner. Two calls
needing a host of one slot of a workspace at once take on one, which both use.

## Process {#process}

The first client that needs the daemon starts it, and the daemon starts each host process,
each by double fork. A host process closes every descriptor it inherited from the daemon but
its end of a socket pair, which is its link:

| Step | Process | Action |
| --- | --- | --- |
| 1 | caller | Creates a pipe; flushes stdout/stderr; forks. Waits on the pipe (polled every 0.1 s, up to `seconds`), then reaps the middle process. |
| 2 | middle | `setsid()` (no controlling terminal); forks; exits `0`. |
| 3 | daemon or host | Ignores `SIGHUP`; stdin from `/dev/null`; fds 1, 2 to `daemon.log`. |
| 4 | daemon | Takes the lock, binds the socket, writes `daemon.json`, writes `listening\n` to the pipe, takes [sessions](#sessions) and opens its [listeners](#listeners). |
| 4 | host | Changes to the workspace; ignores `SIGINT`; `Hmz().reports()`; makes the `Host`; fds 1, 2 to a pipe a thread appends to the run's `host.log` (`daemon.log` before any run); replaces `sys.stdout` and `sys.stderr` with `Printed`; on `SIGTERM` closes the host from a new thread. Writes `listening\n` to the pipe and serves its [link](#links). |
| — | either, on failure | Writes `the run could not be held: <why>\n` to the pipe, closes it, puts fds 1, 2 back on `daemon.log` and logs a traceback there, exits `1`. |

The caller reads the pipe: `listening…` or EOF returns; any other text raises `OSError` with it.
A timeout without either returns silently, and `host()` then raises only if nothing is
listed.

**`Printed`.** In the host, each complete line written to `sys.stdout`/`sys.stderr` (a flow's
`print`, a Python traceback) becomes a [`printed`](#history-records) message to every frontend.
Output written directly to descriptors 1 and 2 by child processes goes to the run's `host.log`.

**Shutdown.** `Host.close()` withdraws questions, drops queued lines, stops every run, tells
every frontend `gone` (`the host was closed`), and waits up to **15 s** from the first close for
runs to release what they made (containers included). The host process then exits; the
daemon ends every subscription still attached to it with `gone` (`the host went away`).

## Sessions {#sessions}

<span id="routing"></span>

Every session is the same JSON-RPC 2.0 over frames (a big-endian u32 length, then one JSON
object, at most 32 MiB), whichever carrier it came over:

| Carrier | Security | Paired |
| --- | --- | --- |
| `daemon.sock` | none: the operating system admitted the user | from the start, as the device `local` |
| a `tcp`, `ws`, `relay` or `easytier` [listener](#listeners) | mutual TLS 1.3, ALPN `hmz`, each side's self-signed device certificate (`hmz.trust`) | where the client's SPKI fingerprint is a paired device |
| a `webrtc` listener | the DTLS of a data channel whose fingerprints the daemon signs (`hmz.rtc`) | where `dtls:<fingerprint>` is a paired device |

| Rule | Value |
| --- | --- |
| First call | `session.hello` `{protocol, client: {name, kind}}`; anything else first is refused -32600. Answered `daemon_id`, `version`, `protocol`, `capabilities` (`webrtc` where a `webrtc:` listener is open and `aiortc` is installed), `machine`, `wsl`, `newer`, `paired`, `device`. |
| Versions | A client of major version 3 and a minor version no greater than the daemon's is admitted; any other is refused 426 with `data.protocol`. |
| Unpaired | May call `session.hello`, `pair.claim` and `rpc.discover` alone; anything else is refused 401, `This device is not paired: claim a pairing code first.` |
| Order | Each call on a thread of its own; those naming one `sub` in the order sent, `epic.aside` apart. |
| Writes | A call carrying `idem` is carried out once per device and key; its answer is kept 600 s, the latest 1 024 per device. |
| Outgoing | One queue per session, written by a thread of its own; past 64 MiB its notifications are dropped and every subscription is ended: `gone` (`too far behind; attach again`), or `notices.event` with `gone`. |
| Calls the daemon makes | None. |

The methods served here are `session.*`, `rpc.discover`, `pair.*`, `devices.*`, [`hosts.*`](#control-requests),
[`epic.*`](#requests) and `btw.*`; every other family (settings, epics written down, flows, …)
is a module of `hmz.daemon.api` naming its own in `METHODS`, found by `pkgutil` as the daemon
starts. A method `protocol/openrpc.json` lists that nothing serves is refused -32601.

| Method | Answer |
| --- | --- |
| `pair.create` `{routes?, seconds?}` | `code` (`hmz-pair:…`) and `expires`; routes default to the listeners'. 409 `There is no route to pair over: give one, or listen.` |
| `pair.claim` `{token, name}` | `daemon_id`, `device`; pairs the session's device. 403 for a code not held, 409 on a paired session. |
| `devices.list` | `devices`: `[{name, fingerprint, added, seen, live}]`. |
| `devices.revoke` `{name}` | `dropped`; removes the device, answers, then closes every session of it. 400 for `local`, 404 for no such device. |

The daemon closes once it has held no host and no session for **2 s**, or **60 s** after it
started where nothing ever came -- unless it listens beyond its socket or `hmz daemon serve`
started it -- and on `SIGTERM`: it closes every session and host, unbinds the socket, and
removes `daemon.json`. A host whose link to the daemon closes closes its runs as `hosts.stop`
does: nobody could reach them.

### Listeners {#listeners}

The setting `listen` and each `hmz daemon serve --listen` name listener specs, opened beside
the socket; the setting's are opened and closed as it changes.

| Spec | Listens |
| --- | --- |
| `tcp://<address>:<port>` | A TCP socket; `0` takes any port. |
| `ws://<address>:<port>` | WebSocket binary messages; any other request is answered 404. |
| `relay:<ws-url>` | Registered at that relay under the daemon id, accepting native joins. |
| `webrtc:<ws-url>` | Registered at that relay, answering WebRTC joins with the STUN and TURN servers of `ice_servers`. |
| `easytier:<name>` | The EasyTier entry of that name joined, its virtual address `10.144.144.1` reaching port 41817 of the loopback. |

A listener's route -- `0.0.0.0` named by this machine's host name, port `0` by the port taken --
is what `pair.create` puts in a code. One that cannot be opened is written to `daemon.log` and
tried again after 1 s, doubling to 60 s.

### Links {#links}

The daemon speaks to each host process with JSON-RPC down a socket pair, of calls of its own no
client sees: `attach` `{tag, name, kind, replay, since}`, `ask` `{client, said}`, `detach`,
`status`, `detach_all`, and the notification `close`; the host sends each frontend's messages
up as `told` `{tag, message}`.

## Lifecycle {#lifecycle}

### Slots {#slots}

A workspace's runs are held by more than one host: its own, slot `""`, which runs its flows one
at a time and refuses a second (`a flow is already running`), and one per chat, slot
`chat:<hex>` (12 hex digits from `hmz.daemon.where.chat()`), and one per `hmz exec`, slot
`exec:<hex>`, beside it. `epic.attach` and `hosts.open` with `chat:` or `exec:` alone make a new
slot of that kind; one whose host has gone is refused 409 (`This chat has folded away.`, `This
epic has ended.`). A chat started on a slot
of its own never waits on a flow, nor a flow on it, and a second chat is a second slot. Every
call that reaches a host -- `attach`, `running`, `host`, `epic.attach`, `hosts.*` --
takes `slot`, and without one means the workspace's own. `where.slot(said)` checks one,
raising `ValueError` (`<slot> is not a slot`) for anything but `""`, `chat:<hex>` and `exec:<hex>`.

A chat's host **folds** its chat away once the chat has waited for its next line with no
frontend attached for **60 s** (`hmz.runtime.doing.hosting.FOLD`): every role is made away, the
question waiting is answered with nothing, and the chat ends `done`, keeping its conversation;
the host is then idle, and goes. A folded host refuses a start (`this chat has folded away;
carry it on from its epic`): the chat is carried on by starting `chat` on a new slot with
`resume` its epic, which goes on in that same epic.

Each host process checks every **0.5 s**. The host closes itself, and its process
exits, when it is **idle** and either a
frontend has ever attached or **60 s** have passed since it started. Idle means all of:

- no frontend attached;
- no run going, starting or stopping;
- no *kept* run: a run that ended while no frontend was attached, and that nobody stopped, is
  kept until a frontend attaches -- but never a chat folded away.

It also closes on `SIGTERM`, [`hosts.stop`](#control-requests), [`epic.quit`](#requests),
and when its link to the daemon closes. `hosts.*` calls do not count as attaching.

| `Daemon` method | Effect |
| --- | --- |
| `detach()` | `hosts.detach`: every frontend is told `gone` (`let go`); runs continue. Returns the count. |
| `stop(*, seconds=20.0)` | `hosts.stop`; polls every 0.1 s for the pid to go. Returns whether it went. Where the call is refused or not answered, returns `not alive`. |
| `kill(*, seconds=20.0)` | `SIGTERM` to the host's process; after `seconds`, `SIGKILL` and up to 20 s more. The daemon and every other host are left alone. Returns whether it went. |

## Hosts {#control-requests}

<span id="protocol"></span>

`hosts.*` ask about a host without attaching to it; all but `hosts.open` start none, and a
workspace and slot no host holds is refused 404, `no runs are held in <workspace>`, and ` for <slot>`
after it for a slot. `Daemon.asked(said)` calls `hosts.<do>` with the daemon's `workspace` and `slot`
over a session of its own (5 s) and returns `{}` on any failure.

| Method | Answer |
| --- | --- |
| `hosts.list` | `held`: `[{pid, workspace, started, slot}]`, in the order taken on. |
| `hosts.running` | `running`: every host whose epic is going or stopping, with `state`, `run`, `flow`, `epic`, `task`, `turn` (a chat's), `workspace`, `slot`, `asking` (`<run>:<question>`). |
| `hosts.open` `{workspace, slot?}` | Starts the host where none is: `pid`, `workspace`, `started`, `kind`, `protocol`, `slot`. |
| `hosts.status` `{workspace, slot?}` | The [status keys](#status). |
| `hosts.detach` `{workspace, slot?}` | `let_go`, after telling each frontend `gone` (`let go`). |
| `hosts.stop` `{workspace, slot?}` | `{}` at once; the host then closes. |

Text clipping: every string longer than 262 144 characters in a history record or snapshot is
cut to that length plus `… (<n> more characters)`.

### Status {#status}

`Daemon.status()`, `Host.status()`, `hosts.status` and `epic.status`:

| Key | Type | Value |
| --- | --- | --- |
| `pid`, `workspace`, `started`, `kind`, `protocol` † | | The host process's (`kind` `host`) (`hosts.status` and fallback only). |
| `attached` † | int | Frontends attached. |
| `clients` | list | `[{client, name, kind}]`. |
| `slot` | string | Which of its workspace's [hosts](#slots): `""` its own, `chat:<hex>` a chat's, `exec:<hex>` an `hmz exec`'s. |
| `state` | string | `running`, `stopping` or `idle`. |
| `run` | int | The run going, else the one stopping, else the last; `0` for none. |
| `flow` | string | That run's flow, or `""`. |
| `epic`, `task` | string | That run's epic (its directory's name, `""` before it has one) and task, or `""`. |
| `pending` | list | `[{question, role, text, mode}]`: the questions waited on, as the [`pending` snapshot](#snapshots) says them. |
| `ended` | object \| null | How the last run to end here ended: `how` (`done`, `stopped`, `refused`, `budget`, `failed` or `crashed`), `why`, `epic`, `at` (Unix seconds), `run`, `flow`, `task`; `null` before one has. |
| `budget`, `usage` | object \| null | As JSON, for the run going; `null` while stopping or idle. An infinite cost is the JSON string `"Infinity"`. |
| `flows` † | list[string] | Canonical refs of the flow calls in progress. |
| `calls` † | list | `[{ref, name, depth, seconds, id, parent}]`, oldest-started first across every run in the process; `seconds` rounded to 0.001; `parent` the index of the calling entry, or `null`. |

A host that does not answer (starting, wedged) yields only the † keys: the `Daemon`'s own
fields with `attached: 0`, `flows: []`, `calls: []`.

## Calls to an epic {#requests}

`epic.attach` `{workspace, slot?, replay?, since?, figures?, scratch?}` attaches the session to
a host as one frontend, starting the workspace's host where none is, and answers `sub`,
`client`, `workspace` and `slot`; the host's [messages](#messages) then arrive as
`epic.event` `{sub, message}`, none before the answer. `since` `{epoch, seq}` sends only the
records after `seq` where `epoch` is the host's and every one after it is kept; `figures`
also sends `figures`, at most once a second; `scratch` attaches to a new directory of its own.
Every other call to an epic is `epic.<do>` `{sub, …}`, answered with the host's fields, or
refused 409 with its `why`; a `sub` not open on the session is refused 410. `epic.start`,
`say`, `answer`, `stop`, `force`, `afk`, `claim`, `release`, `board` and `quit` are writes,
taking `idem`.

| Any call | Refusal |
| --- | --- |
| from a frontend no longer attached | `this frontend is not attached` |

| `epic.<do>` | Fields (type, default) | Answer | Refusals |
| --- | --- | --- | --- |
| `attach` | as above | `sub`, `client`, `workspace`, `slot` | `the frontend went while it was saying hello`, `this host has closed`, `This chat has folded away.`, `This epic has ended.` |
| `start` | `flow` (str, required), `task` (str), `agents` (`{role: -a spec}`), `envs` (`{role: -e spec}`), `params` (object), `budget` (Budget JSON), `profile_flow`, `profile_environment` (bool; whether the run's flow, and the programs its agents start, are [profiled](/reference/tracing#profiling-a-run)), `resume` (`false`, `true`, or an epic path), `backup` | `run` (int), `slot`, `workspace` | `a flow to start is named`, `a flow is already running`, `a flow is already starting`, `this host has closed`, any [`Refused`](/reference/cli#what-is-refused-before-anything-runs) message. A run that is only *stopping* does not block `start`. |
### Routing of `say` {#say-routing}

| `to` | The line |
| --- | --- |
| `""` | Answers a pending *listen* question the sender may answer, else goes to the first conversation with a turn open (in opening order). |
| `<agent>` | That agent's newest conversation with a turn open; with none open, in `chat` only, answers a pending listen question the sender may answer. |
| `<agent>/<n>` | That conversation; with no turn open in it, in `chat` only, answers a pending listen question the sender may answer. |
| `outworlder:<role>` | Answers that role's pending listen question only; never put into a turn. |

A line enters a conversation only while a turn is open, one line per agent at a time; it
waits otherwise, and the next turn to start takes the oldest matching line into its prompt. A
line that answered a listen question is taken by no turn.
Accepted lines are reported with `said`; a backend's refusal with `refused` (the line returns
to the head of the queue).

### Asides {#asides}

An aside is a read-only side session: `permission` read-only, no goals, no skills, no allowed
tools, MCP approval off, watched by nothing. Only the newest 256 conversations of the last run
can be forked. An aside about a session an earlier run kept is a fork of it carried on from
where that run kept it -- into a directory of the aside's own in this machine's directory,
removed as the aside is closed, never where that run keeps its sessions nor the CLI's own home --
and a fresh copy of its agent where its CLI does not fork or the session was not kept. An aside
is closed on `unaside`, when its frontend detaches, when a run starts, and when the host closes.
No message announces asides. A harness with no read-only rung (`mcode`, `dsh`, ACP) is refused:
`<harness> cannot answer a side question: it has no read-only rung`.

The Epic's aside (`runs` with `asks: true`) carries the `ask-conversation` skill, a pre-tool-use
and a stop hook, and the fake command line `hmz-ask` (`ask --to <agent>/<n> --question <q>`,
`list`). A run of it, caught by the hook or by the command, answers the turn's `aside` with
`ask`; the frontend carries it out and sends `answered`, and the turn goes on. The answer
reaches the agent as the hook's refusal on `claude` and `qwen`, as the command's output where it
ran, and otherwise as what the stop hook sends the agent on with. One question asked twice in a
turn is asked once. On `codex`, whose `read-only` sandbox refuses the socket `hmz-ask` reaches
the host on, `hmz-ask` alone runs outside the sandbox, by `prefix_rule(pattern=["hmz-ask"],
decision="allow")` in `rules/hmz.rules` of its virtual home; every other command stays in the
sandbox, network cut.

## Messages {#messages}

On `epic.attach`, atomically:

1. `welcome`: `client`, `name`, `kind`, `workspace`, `slot`, `pid` (host process), `protocol` (`3.0.0`), `epoch` (this life of the host).
2. The history records, oldest first (omitted with `replay: false`; only those after `since` where it holds).
3. Every snapshot, in the order `clients`, `claims`, `away`, `run`, `sessions`, `calls`,
   `waiting`, `pending`, `usage`, `board`.
4. `live`: `seq` (the last record's), `elided` (records dropped from the front).
5. Every later record and changed snapshot, as it happens.

### History records {#history-records}

Kept per host from the last `start` (plus anything before the first). Each carries `seq`, a
host-wide counter never reset. Kept up to 32 MiB of JSON; the oldest whole records are dropped
first (counted in `elided`), the newest always kept. Every record but `printed` carries `run`.

| `type` | Fields |
| --- | --- |
| `started` | `flow`, `ref`, `task`, `by` (frontend name), `client`, `roles` (declared agent roles the line fills), `names` (`{role: agent name}`: what the agent filling each is called, which its conversations are keyed by), `outworlders` (runtime-filled roles), `agents` (`{role: spec}`), `envs` (`{role: spec}`), `params` (object), `budget` (Budget JSON), `profile_flow`, `profile_environment` (bool), `resume` (`""`, or `str()` of what was given: `"True"`, an epic path), `began` (host monotonic), `at` (Unix time) |
| `opened` | `role` (the role its agent fills), `key` (`<agent>/<n>`), `agent` (the agent's own name, such as `NeiKos496`), `cli`, `model`, `counts` (sorted token kinds the backend reports), `forks` (bool), `person` (bool), `kept` (directory of the session's logs; `""` for a person or the CLI's own home), `env`, `harness`, `mono`, `wall` (Unix time) |
| `event` | `key`, `session` (`key` where the event names a conversation, else `""`), `agent`, `cli`, `model`, `ident` (backend's conversation id, `""` until named), `kind`, `text`, `whose`, `tokens`, `spent`, `at`, `mono`. Same fields as [`hmz exec --json`](/reference/cli#ndjson). |
| `asked` | `question` (`q<n>`, host-wide), `role` (default `outworlder`), `text`, `options` (list), `mode` (`ask` where there are options or a turn is open, else `listen`), `key` (`<agent>/<n>` of the one conversation with a turn open, else `""`) |
| `answered` | `question`, `role`, `by`, `client`, `text` (the option chosen, or the text) |
| `withdrawn` | `question`, `why`: `away` (the role went afk) or `over` (the run ended, stopped, was forced or the host closed) |
| `said` | `text`, `key`, `by`, `client`: a line a conversation took |
| `refused` | `agent`, `text`, `because` (the backend's error text, or `the agent refused it`) |
| `unheld` | `agent`, `texts`: lines a turn ended without acknowledging; discarded |
| `dropped` | `given` `[{agent, text, by, client}]`, `queued` `[{text, by, client, to}]`, `because` (`stopped` or `ended`); only where something was waiting |
| `printed` | `text`: one line printed in the host |
| `notice` | `text`: Humanize's own note about the run, after `started` and before its first turn: `nobody lists a price for <model>[, …], so cost=<n> cannot stop what it spends` where the run's `cost` limit cannot be enforced; `<backend>:<a> cannot hold '<role>': <why>; using <backend>:<b>` where an environment [fell back](/reference/machines#falling-back) to another runtime. The interface shows it as `hmz: <text>`, in yellow. |
| `stopping` | `by`, `client` |
| `ended` | `how`, `why`, `mono` |

`opened.env`: `null` where the driver reported no placement, else:

| Key | Value |
| --- | --- |
| `role` | The environment role the session works in, `""` if unnamed. |
| `kind` | `local`, `ssh`, `docker`, `swarm`, `apple-container` or `slurm`. |
| `target` | The ssh host or container runtime; `""` for local. |
| `workdir` | The directory there. |
| `anchored` | `true` where the agent reaches another machine (ssh and container environments). |

`opened.harness`: where the session's harness went.

| Value | When |
| --- | --- |
| `""` | A person, or an agent working on this machine without an anchor. |
| `local` | Harness here, work on another machine. |
| `env` | Harness on the environment's machine (native CLI). `self`, written by an earlier Humanize, means the same. |
| `<backend>:<name>` | Harness on the saved runtime of that name, which the harness setting of the runtime the work is on named (`docker:gpubox`). |

`ended.how` and `why`:

| `how` | `why` |
| --- | --- |
| `done` | `""`. Also for a stopped run whose flow returned normally. |
| `stopped` | `""` |
| `budget` | The limit reached. |
| `refused` | The [`Refused`](/reference/sdk#refused) message. |
| `failed` | `<ExceptionType>: <message>` |
| `crashed` | A traceback. |

### Snapshots {#snapshots}

The latest of each type is kept and re-sent on attach; a changed one is broadcast. No `seq`.

| `type` | Fields | Initial |
| --- | --- | --- |
| `clients` | `clients`: `[{client, name, kind}]` | `[]` |
| `claims` | `claims`: `{role: client}` | `{}` |
| `away` | `all` (bool), `of` (`{role: bool}`) | `false`, `{}` |
| `run` | `state` (`idle`, `running`, `stopping`), then the `started` fields of the run going or the last (`run: 0` for none), `stopping` (run number or `null`), `epic` (its directory's name, `""` before it has one), `slot` | `idle` |
| `sessions` | `run`, `open` (keys still open), `working` (keys with a turn open) | `0`, `[]`, `[]` |
| `calls` | `calls`: `[{ref, name, depth, since (host monotonic), id, parent (index or null)}]` | `[]` |
| `waiting` | `queued` `[{text, by, client, to}]`, `given` `[{agent, text, by, client}]` | `[]`, `[]` |
| `pending` | `pending`: `[{question, run, role, text, options, mode, key, owner (client id or null)}]` | `[]` |
| `usage` | `run`, `usage` (Usage JSON or `null`), `budget`; refreshed at most once a second | `0`, `null`, `null` |
| `board` | `items`: `[{key, value, about, whose (both, user, flow), by, at}]`, or `null` for a run with no board; reset to `null` on start | `null` |

### `gone` {#gone}

The last message a frontend receives: `{"type": "gone", "why": …}`.

| `why` | Cause |
| --- | --- |
| `let go` | `epic.detach`, `hosts.detach`, or an in-process `Link.close()`; a session closing ends its subscriptions without one |
| `the host was closed` | `hosts.stop`, `epic.quit`, `SIGTERM`, idle close |
| `too far behind; attach again` | The host's queue for this frontend, or the session's queue, exceeded 64 MiB |
| `the host went away` | The host process ended without closing; also synthesised by `Link` where its session ends |

After `gone` the subscription has ended: a call naming it is refused 410.

## Frontends {#hosting}

<span id="several-frontends"></span>

| Rule | |
| --- | --- |
| Names | `session.hello`'s `client.name`, used verbatim; `""` becomes `<HUMANIZE_NAME or login or "somebody">@<kind>`. A name already attached gets `#2`, `#3`, …. The final name is sent in `welcome`. |
| Client ids | `c1`, `c2`, … per host; never reused. |
| Claims | A claimed `Outworlder` role may be answered, spoken to (`outworlder:<role>`) and set away only by its holder. `take: true` takes it from another holder, which learns it only from the `claims` and `pending` snapshots. Claims are released when the holder detaches; its questions' `owner` becomes `null`. Claims are not persisted. Claims do not restrict `say` to agents. |
| Questions | Recorded only while the run is current, the host open, and the role not away; otherwise the flow gets no answer at once. Shown to every frontend with `owner`. Answerable by the owner, or by anybody where `owner` is `null`; the first answer wins. They stay pending with nobody attached. |
| Away | Held by the host, per role. `afk` with `role` sets that role. Without `role`: with no claims, sets every role and clears per-role values; with claims, roles held by other frontends keep their value. Outlives the frontend that set it. |
| Runs | Any frontend may `start`, `stop`, `force` or `quit`. |
| Late arrival | A frontend attaching mid-run with `replay: true` reads the run from its `started` record. |

## `Link` {#link}

`hmz.daemon.Link`, exported as [`hmz.sdk.Link`](/reference/sdk#link). Signatures are on the
SDK page; transport behaviour:

| Aspect | Through the daemon (`reached`) | In process (`linked`) |
| --- | --- | --- |
| Made by | `Daemon.link(name="", kind="sdk", *, replay=True)`, `hmz.daemon.reached(at, workspace, name="", kind="sdk", *, replay=True)` | `hmz.daemon.linked(host, name="", kind="tui", *, replay=True)` |
| Attach failure | `OSError` (nothing listening; `session.hello` or `epic.attach` refused or not answered within 10 s) | `RuntimeError("this host has closed")` |
| Requests | `epic.<do>` with its `sub`, writes with an `idem` of their own; `seconds` honoured: `TimeoutError("no answer to '<do>' in <s>s")`, the call then cancelled | Run synchronously; `seconds` ignored |
| Refusal | `Refused(why)` | `Refused(why)` |
| Host gone | Pending and later requests are refused with the `gone` reason; a send error with `the host could not be reached: <err>` | — |
| `close()` | Closes its session; the daemon lets its frontend go. Idempotent. | `host.detach(client)` |

Messages are delivered in order, either through iteration (`for said in link`, ending after
`gone` or `close()`) or to one listener set with `heard()`, on a thread named
`humanize-link-<client>`; listener exceptions are suppressed. Setting a listener twice, or
iterating with a listener set, raises `RuntimeError`. `Link` has no helpers for `unaside`,
`status`, `detach` or `quit`: send them with `asked({"do": …})`.

```python
from hmz.sdk import Daemons

with Daemons().host().link(name="watcher", replay=False) as link:
    for said in link:
        if said["type"] == "ended":
            print(said["how"], said["why"])
            break
```

## Module `hmz.daemon` {#module}

```python
@dataclass(frozen=True, slots=True)
class Daemon: ...                                   # see SDK › Daemon
def running(workspace=None, *, slot: str = "") -> Daemon | None: ...
def daemons() -> list[Daemon]: ...                  # every host, chats' included
def host(workspace=None, *, seconds: float = 10.0, slot: str = "") -> Daemon: ...
def start(seconds: float = 10.0) -> None: ...                # the daemon, where none runs
def older(daemon: Daemon) -> str: ...
class Older(RuntimeError): ...                      # the runs are held by an older Humanize
def attach(kind: str, name: str = "", *, workspace=None, slot: str = "") -> Link: ...
def linked(host: Host, name: str = "", kind: str = "tui", *, replay: bool = True) -> Link: ...
def reached(at: Path, workspace: str, name: str = "", kind: str = "sdk", *,
            replay: bool = True, slot: str = "") -> Link: ...
def remote(remotes: Remotes, daemon: str, workspace: str, slot: str = "") -> Link: ...
Hmz, Host, Refused                                  # hmz.runtime's, fetched on access
```

`hmz.daemon.link.remote` reaches the runs of a workspace on another machine through that
machine's daemon, over the session `Remotes.client` keeps to it, as `/epics @<name>` reaches
it: `epic.attach` there, as `reached` attaches over this machine's socket -- its `epic.event`
notifications are the messages told to the link, and each request is the call `epic.<do>`, a
refusal raised as `Refused`. `OSError` where that daemon is not reached or will not attach.
`close()` stops following.

`attach` is how `hmz` and `hmz web` reach runs held apart from them: it starts the daemon
where none is and attaches through it (`epic.attach` starts the host), as `kind`,
tried **3** times **0.5 s** apart while linking raises `OSError`, the last of which it raises. A
daemon of another `protocol` raises `Older`, saying what [`older`](#discovery) says,
and nothing is started beside it.

`hmz.daemon.link.dialed(at, name="", kind="sdk", *, serve=None, seconds=10.0)` opens a
session over the socket and says `session.hello`, answering the `hmz.rpc.Peer` and the hello;
`OSError` where nothing answers, `EADDRINUSE` with the refusal of another protocol.
