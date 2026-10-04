---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# Daemon reference

The **daemon**: one process per machine and user, which every frontend reaches and which
hands each to the **host** of the workspace it names: one process per workspace, holding that
workspace's runs. And the protocol **frontends** use to read and drive them. A frontend is an
`hmz` interface (`kind` `tui`) or a program linked through the [SDK](/reference/sdk#link)
(`kind` `sdk`). Package: `hmz.daemon`. Notation: [Conventions](/reference/#conventions).

```text
 hmz (alice@tui) ──┐                               ┌─ host process, ~/src/api ──────────────────┐
 hmz (bob@tui) ────┼── daemon.sock ── daemon ──┬──▶│ Host: the run, claims, away, queued lines, │
 program (ci@sdk) ─┘   (one per machine)       │   │ questions, history, snapshots              │
                                               │   └────────────────────────────────────────────┘
 MESSAGE frames: JSON requests in, messages    └──▶┌─ host process, ~/src/web ──────────────────┐
 out; CONTROL frames. The daemon hands each        │ …                                          │
 socket to its host and carries none of it.        └────────────────────────────────────────────┘
```

## Terms {#terms}

| Term | Definition |
| --- | --- |
| host | `hmz.runtime.Host`: a workspace's runs as every attached frontend shares them. Held either in a host process or in the interface's own process. |
| daemon | The detached process, one per machine and user, listening on `daemon.sock` and handing each connection to the host process of the workspace it names. |
| host process | The detached process, one per workspace, standing in that workspace and holding its `Host`. Reached only through the daemon. |
| frontend | One attachment to a host, through a [`Link`](#link). Has a client id (`c1`, `c2`, …) and a name. |
| run | One run of one flow on the host, numbered from 1 per host. |
| request | A JSON object a frontend sends, with `do`. |
| message | A JSON object the host sends, with `type`. |

## When a daemon is used {#when-used}

| Caller | Host |
| --- | --- |
| `hmz` at a terminal | A host process, found or started (see [CLI › Where the runs are held](/reference/cli#where-runs-are-held)). |
| `hmz` with stdin or stdout not a TTY, or `HUMANIZE_DAEMON` = `off`/`0`/`no` | In the interface's process. |
| `hmz` after 3 failed attempts, 0.5 s apart | In the interface's process; stderr says `hmz: runs cannot be detached from the terminal (<why>), so they will run in this process instead`. |
| `Daemons().host()`, `hmz.daemon.host()` | A host process, found or started. `HUMANIZE_DAEMON` is not consulted. |
| `Hmz().host()` | In the calling process. |
| `hmz exec` | No host. |

A host in the interface's process is reached through the same `Link` class; closing that
interface closes its runs, so `/exit` offers **Cancel** instead of **Detach and exit**.

## Files {#files}

Directory: `<tmp>/humanize-<uid>/`, where `<tmp>` is Python's `tempfile.gettempdir()` (`$TMPDIR`,
`$TEMP` or `$TMP`, else `/tmp`) and `<uid>` the user's id: `hmz.machine()`, shared with the
[bundle cache](/reference/files#temporary). Made `0700` where missing; one that is not a
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
(output of CLIs the run spawns), and entries written by `logged()`: `the daemon could not carry
a round of messages`, `a <type> message was too long to carry`. The run is the one going, else
the one stopping, else the last.

```json
{
  "pid": 41237,
  "started": "2026-09-30T08:15:42Z",
  "kind": "daemon",
  "protocol": 2
}
```

| Key | Type | Value |
| --- | --- | --- |
| `pid` | int | The daemon process. |
| `started` | string | UTC, `%Y-%m-%dT%H:%M:%SZ`. |
| `kind` | string | `"daemon"`. |
| `protocol` | int | `2`. A `daemon.json` without it, or with another, is an older humanize's daemon, which nothing here reaches. |

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
| `running(workspace=None)` | `Daemon \| None` | The host of that workspace, where the daemon's `daemon.json` parses as an object with an int `pid` of a live process (`kill(pid, 0)`; `EPERM` counts as alive), its socket accepts a connection within 1 s, its CONTROL [`list`](#routing) names the workspace, and that host's pid is alive. Where the daemon's `protocol` is not `2`: a `Daemon` for the daemon itself, with its `protocol` (`0` for none). Otherwise `None`. |
| `daemons()` | `list[Daemon]` | Every host the daemon lists whose pid is alive, sorted by `started` (oldest first); the daemon itself where its `protocol` is not `2`; `[]` with no daemon. |
| `host(workspace=None, *, seconds=10.0)` | `Daemon` | Starts the daemon where none is, then `running(workspace)`, else starts a host process; waits up to `seconds` for each. Tried twice, 0.1 s apart: a daemon that went as its host came up is started again. |
| `older(daemon)` | `str` | `the runs in <workspace> are held by an older humanize (pid <pid>); stop it with that version`, or `on this machine` for a daemon. |

`host()` raises `OSError`:

| Condition | `OSError` text |
| --- | --- |
| an older humanize's daemon (protocol not `2`), or a host it left holding the workspace | `[Errno 98] ` + `older(daemon)` (`EADDRINUSE`) |
| the daemon or the new host reported a failure | the reported text, e.g. `the run could not be held: <why>` |
| no daemon is listening after the wait | `this machine's daemon did not come up` |
| no host is listed after both tries | `the runs in <workspace> did not come up` |

Two callers racing to start the daemon: the loser's lock fails (`[Errno 11] Resource
temporarily unavailable`), and `host()` uses the winner. Two racing to start a host of one
workspace: the daemon refuses the second (`the runs in <workspace> are already held`), and
`host()` returns the first.

## Process {#process}

`host()` starts the daemon, where none is, and then the workspace's host process, each by
double fork:

| Step | Process | Action |
| --- | --- | --- |
| 1 | caller | Creates a pipe; flushes stdout/stderr; forks. Waits on the pipe (polled every 0.1 s, up to `seconds`), then reaps the middle process. |
| 2 | middle | `setsid()` (no controlling terminal); forks; exits `0`. |
| 3 | daemon or host | Ignores `SIGHUP`; stdin from `/dev/null`; fds 1, 2 to `daemon.log`. |
| 4 | daemon | Takes the lock, binds the socket, writes `daemon.json`, writes `listening\n` to the pipe, [routes](#routing). |
| 4 | host | Changes to the workspace; ignores `SIGINT`; `Hmz().reports()`; makes the `Host`; fds 1, 2 to a pipe a thread appends to the run's `host.log` (`daemon.log` before any run); replaces `sys.stdout` and `sys.stderr` with `Printed`; on `SIGTERM` closes the host from a new thread. Connects to the daemon and sends CONTROL `serve` (`pid`, `workspace`, `started`, `kind` `host`, `protocol`); the daemon answers one byte `+`, or closes the connection where another host holds the workspace. Writes `listening\n` to the pipe, serves. |
| — | either, on failure | Writes `the run could not be held: <why>\n` to the pipe, closes it, puts fds 1, 2 back on `daemon.log` and logs a traceback there, exits `1`. |

The caller reads the pipe: `listening…` or EOF returns; any other text raises `OSError` with it.
A timeout without either returns silently, and `host()` then raises only if nothing is
listed.

**`Printed`.** In the host, each complete line written to `sys.stdout`/`sys.stderr` (a flow's
`print`, a Python traceback) becomes a [`printed`](#history-records) message to every frontend.
Output written directly to descriptors 1 and 2 by child processes goes to the run's `host.log`.

**Shutdown.** `Host.close()` withdraws questions, drops queued lines, stops every run, tells
every frontend `gone` (`the host was closed`), and waits up to **15 s** from the first close for
runs to release what they made (containers included). The carrier then flushes for up to
**5 s** and the host process exits; the daemon stops handing it anything.

## Routing {#routing}

The daemon reads the first frame of each connection without taking it off the socket
(`MSG_PEEK`, up to 64 KiB, within 10 s), and then:

| First frame | The daemon |
| --- | --- |
| CONTROL `serve` | Reads it; takes the connection as that workspace's host, kept for as long as it is open. A second host of a workspace whose host is alive is refused by closing. |
| CONTROL without `workspace` | Answers it: `list` with `{"ok": true, "held": [{"pid", "workspace", "started"}, …]}` (registration order); anything else with `{"ok": false, "why": "no such request: <repr of do>"}`. |
| MESSAGE or CONTROL whose `workspace` a host holds | Passes the socket to that host down its connection (`SCM_RIGHTS`, beside one byte `+`), and keeps its own descriptor until the host says it has it with one byte back. The host reads the frame itself. |
| MESSAGE or CONTROL whose `workspace` nobody holds | MESSAGE: a `reply` with `to` the request's `id`, `ok: false`, `why: no runs are held in <workspace>`. CONTROL: `{"ok": false, "why": …}`. Then closes. |
| another kind | Answers with `GONE` (``held for frontends by a newer humanize; `hmz` of it reads it``) and closes. |
| a length no frame has, nothing within 10 s, or EOF | Closes. |

The daemon closes once it has held no host for **2 s**, or **60 s** after it started where no
host ever came, and on `SIGTERM`: it closes every host's connection, unbinds the socket, and
removes `daemon.json`. A host whose connection to the daemon closes closes its runs as a
CONTROL `stop` does: nobody new could reach them.

## Lifecycle {#lifecycle}

Each host process's carrier checks every **0.5 s**. The host closes itself, and its process
exits, when it is **idle** and either a
frontend has ever said `hello` or **60 s** have passed since it started. Idle means all of:

- no frontend attached;
- no run going, starting or stopping;
- no *kept* run: a run that ended while no frontend was attached, and that nobody stopped, is
  kept until a frontend attaches.

It also closes on `SIGTERM`, a CONTROL [`stop`](#control-requests), a MESSAGE
[`quit`](#requests), or after 8 consecutive failed carrier rounds (each logged). Connections
arriving after close are closed at once. CONTROL connections do not count as reaching the host.

| `Daemon` method | Effect |
| --- | --- |
| `detach()` | CONTROL `detach`: every frontend is told `gone` (`let go`); runs continue. Returns the count. |
| `stop(*, seconds=20.0)` | CONTROL `stop`; polls every 0.1 s for the pid to go. Returns whether it went. If the request is not answered `ok`, returns `not alive`. |
| `kill(*, seconds=20.0)` | `SIGTERM` to the workspace's host process; after `seconds`, `SIGKILL` and up to 20 s more. The daemon and other workspaces' hosts are left alone. Returns whether it went. |

## Frames {#protocol}

Both directions carry frames:

```text
+------+----------------------+-------------------+
| kind | length (u32, big-end) | payload (length)  |
| 1 B  | 4 B                  |                   |
+------+----------------------+-------------------+
```

| Kind | Byte | Payload |
| --- | --- | --- |
| `MESSAGE` | `M` | One UTF-8 JSON object: a request (frontend → host) or a message/reply (host → frontend). |
| `CONTROL` | `C` | One JSON object: a [control request](#control-requests) or its answer. |
| `GONE` | `X` | UTF-8 text: why the reader is let go. |

| Rule | Value |
| --- | --- |
| Largest payload a reader accepts | 4 194 304 bytes (`1 << 22`). A larger length is a protocol error: the host drops the connection; a `Link` reads it as `gone` (`the host went away`). |
| Largest frame the host sends | 4 194 303 bytes including the 5-byte header. A larger message is dropped and logged (`a <type> message was too long to carry`). Replies are not checked. |
| Frame kind the daemon or host does not know | Answered with `GONE`: ``held for frontends by a newer humanize; `hmz` of it reads it``, then closed. |
| Text clipping | Every string longer than 262 144 characters in a history record or snapshot is cut to that length plus `… (<n> more characters)`. Not applied to `welcome`, `live`, `gone` or replies. |
| JSON | `ensure_ascii=False`; values not JSON-native are `str()`-ed. |
| `PROTOCOL` | `2`. |

## Control requests {#control-requests}

One CONTROL frame per connection; no `hello`. With `workspace`, the daemon passes it to that
workspace's host, which answers with one CONTROL frame (5 s send timeout) and closes; without,
the daemon answers it ([Routing](#routing)). `Daemon.asked(said)` sends one with the daemon's
`workspace` added (no connect timeout; 5 s send/receive) and returns `{}` on any failure.

| `do` | Answer |
| --- | --- |
| `status` | `{"ok": true, …what the host said to the daemon, …status keys}` |
| `detach` | `{"ok": true, "let go": <n>}` after telling each frontend `gone` (`let go`). |
| `stop` | `{"ok": true}` at once; the host then closes. |
| other | `{"ok": false, "why": "no such request: <repr of do>"}` |

### Status {#status}

`Daemon.status()`, `Host.status()` and MESSAGE `status`:

| Key | Type | Value |
| --- | --- | --- |
| `ok` | bool | `true` (CONTROL answer only). |
| `pid`, `workspace`, `started`, `kind`, `protocol` † | | The host process's, as it said them to the daemon (`kind` `host`) (CONTROL answer and fallback only). |
| `attached` † | int | Frontends attached. |
| `clients` | list | `[{client, name, kind}]`. |
| `state` | string | `running`, `stopping` or `idle`. |
| `run` | int | The run going, else the one stopping, else the last; `0` for none. |
| `flow` | string | That run's flow, or `""`. |
| `budget`, `usage` | object \| null | As JSON, for the run going; `null` while stopping or idle. An infinite cost is the JSON string `"Infinity"`. |
| `flows` † | list[string] | Canonical refs of the flow calls in progress. |
| `calls` † | list | `[{ref, name, depth, seconds, id, parent}]`, oldest-started first across every run in the process; `seconds` rounded to 0.001; `parent` the index of the calling entry, or `null`. |

A host that does not answer (starting, wedged) yields only the † keys: the `Daemon`'s own
fields with `attached: 0`, `flows: []`, `calls: []`.

## Requests {#requests}

A frontend's first request must be `hello`. Every request may carry `id`. Each is answered, on
the connection it came in on, by one `reply` whose `to` is that `id` (`""` where none), with
`ok` and the answer's fields, or `ok: false` and `why`:

```json
{"type": "reply", "to": "r7", "ok": true, "run": 3}
{"type": "reply", "to": "r8", "ok": false, "why": "a flow is already running"}
```

Requests of one frontend are carried out in the order sent, on a thread per frontend, off the
thread carrying bytes. `aside` requests run on threads of their own, outside that order.
An exception inside a request is refused with `str(exception)` or its type name.

| Any request | Refusal |
| --- | --- |
| before `hello` | `a frontend says hello first` |
| unknown `do` | `no such request: '<do>'` |
| from a frontend no longer attached | `this frontend is not attached` |

| `do` | Fields (type, default) | Answer | Refusals |
| --- | --- | --- | --- |
| `hello` | `workspace` (str: the daemon hands the frontend to its host; not read by the host), `name` (str, `""`: `<login>@<kind>`), `kind` (str, `"sdk"`), `replay` (bool, `true`; only a literal `false` disables) | `client` | `this frontend has already said hello`, `the frontend went while it was saying hello`, `this host has closed` |
| `start` | `flow` (str, required), `task` (str), `agents` (`{role: -a spec}`), `envs` (`{role: -e spec}`), `params` (object), `budget` (Budget JSON), `profile` (bool; whether the run is [profiled](/reference/tracing#profiling-a-run)), `resume` (`false`, `true`, or an epic path) | `run` (int) | `a flow to start is named`, `a flow is already running`, `a flow is already starting`, `this host has closed`, any [`Refused`](/reference/cli#what-is-refused-before-anything-runs) message. A run that is only *stopping* does not block `start`. |
| `say` | `text` (str, required), `to` (str, `""`) | — | `a line says something`, `no flow is running to say it to` (also while stopping), `<role> is <name>'s` (for `to: "outworlder:<role>"`) |
| `answer` | `question` (id), `text` (str, required; a number `1‥n` that is not itself an option picks that option) | — | `an answer says something`, `already answered by <name>`, `no question <id> is waiting`, `<role> is <name>'s` |
| `stop` | — | — | `the flow is already stopping: it is closing out the turn it was in`, `no flow is running, so there is nothing to stop` |
| `force` | — | `closed` (int): conversations closed mid-turn | `no flow is running, so there is nothing to stop` |
| `afk` | `on` (bool, required), `role` (str, `""` = every role) | — | `afk is on or off`, `<role> is <name>'s`. Needs no run. |
| `claim` | `role` (str, required), `take` (bool, `false`) | — | `a role to claim is named`, `<role> is <name>'s` (without `take`). Needs no run; role not checked against the flow. |
| `release` | `role` | — | `<role> is not yours to release` |
| `board` | `key`, `value` (`""` removes the line); acts on the last run's board as `user` | — | `this run has no board`, `<key> is not on the board`, `<key> is flow's to change, not user's` (and other `<key> is <whose>'s to change, not <by>'s` refusals) |
| `aside` (open) | `key` (`<role>/<n>` of the last run) with `fork` (bool), **or** `runs` (an `-a` spec after `<role>=`) | `side` (`s<n>`), `forked` (bool) | `<key> has no conversation to ask`, `<runs> is not an agent that can be made here`, `an aside is about a conversation, or asks an agent`, `this frontend has gone` |
| `aside` (ask) | `side`, `prompt` | `answer` (str, stripped) | `no aside <side> is open`, `the aside is still answering the last question` |
| `unaside` | `side` | — | `no aside <side> is open` |
| `status` | — | [status keys](#status) without the † host keys | — |
| `detach` | — | — (then `gone`: `let go`) | — |
| `quit` | — | — (the host closes) | — |

### Routing of `say` {#say-routing}

| `to` | The line |
| --- | --- |
| `""` | Answers a pending *listen* question the sender may answer, else goes to the first conversation with a turn open (in opening order). |
| `<role>` | That role's newest conversation with a turn open. |
| `<role>/<n>` | That conversation. |
| `outworlder:<role>` | Answers that role's pending listen question only; never put into a turn. |

A line enters a conversation only while a turn is open, one line per agent at a time; it
waits otherwise, and the next turn to start takes the oldest matching line into its prompt.
Accepted lines are reported with `said`; a backend's refusal with `refused` (the line returns
to the head of the queue).

### Asides {#asides}

An aside is a read-only side session: `permission` read-only, no goals, no skills, no allowed
tools, MCP approval off, watched by nothing. Only the newest 256 conversations of the last run
can be forked. An aside is closed on `unaside`, when its frontend detaches, when a run starts,
and when the host closes. No message announces asides.

## Messages {#messages}

On `hello`, atomically:

1. `welcome`: `client`, `name`, `kind`, `workspace`, `pid` (host process), `protocol` (`2`).
2. The history records, oldest first (omitted with `replay: false`).
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
| `started` | `flow`, `ref`, `task`, `by` (frontend name), `client`, `roles` (declared agent roles the line fills), `outworlders` (runtime-filled roles), `agents` (`{role: spec}`), `envs` (`{role: spec}`), `params` (object), `budget` (Budget JSON), `profile` (bool), `resume` (`""`, or `str()` of what was given: `"True"`, an epic path), `began` (host monotonic), `at` (Unix time) |
| `opened` | `role`, `key` (`<role>/<n>`), `agent` (agent id), `cli`, `model`, `counts` (sorted token kinds the backend reports), `forks` (bool), `person` (bool), `kept` (directory of the session's logs; `""` for a person or the CLI's own home), `env`, `harness`, `mono` |
| `event` | `key`, `session` (`key` where the event names a conversation, else `""`), `agent`, `cli`, `model`, `ident` (backend's conversation id, `""` until named), `kind`, `text`, `whose`, `tokens`, `spent`, `at`, `mono`. Same fields as [`hmz exec --json`](/reference/cli#ndjson). |
| `asked` | `question` (`q<n>`, host-wide), `role` (default `outworlder`), `text`, `options` (list), `mode` (`ask` where there are options or a turn is open, else `listen`) |
| `answered` | `question`, `role`, `by`, `client`, `text` (the option chosen, or the text) |
| `withdrawn` | `question`, `why`: `away` (the role went afk) or `over` (the run ended, stopped, was forced or the host closed) |
| `said` | `text`, `key`, `by`, `client`: a line a conversation took |
| `refused` | `agent`, `text`, `because` (the backend's error text, or `the agent refused it`) |
| `unheld` | `agent`, `texts`: lines a turn ended without acknowledging; discarded |
| `dropped` | `given` `[{agent, text, by, client}]`, `queued` `[{text, by, client, to}]`, `because` (`stopped` or `ended`); only where something was waiting |
| `printed` | `text`: one line printed in the host |
| `notice` | `text`: humanize's own note about the run, after `started` and before its first turn: `nobody lists a price for <model>[, …], so cost=<n> cannot stop what it spends` where the run's `cost` limit cannot be enforced; `<backend>:<a> cannot hold '<role>': <why>; using <backend>:<b>` where an environment [fell back](/reference/machines#falling-back) to another runtime. The interface shows it as `hmz: <text>`, in yellow. |
| `stopping` | `by`, `client` |
| `ended` | `how`, `why`, `mono` |

`opened.env`: `null` where the driver reported no placement, else:

| Key | Value |
| --- | --- |
| `role` | The environment role the session works in, `""` if unnamed. |
| `kind` | `local`, `ssh`, `docker`, `swarm` or `apple-container`. |
| `target` | The ssh host or container runtime; `""` for local. |
| `workdir` | The directory there. |
| `anchored` | `true` where the agent reaches another machine (ssh and container environments). |

`opened.harness`: where the session's harness went.

| Value | When |
| --- | --- |
| `""` | A person, or an agent working on this machine without an anchor. |
| `local` | Harness here, work on another machine. |
| `self` | Harness on the environment's machine (native CLI). |
| `<backend>:<name>` | Harness on the saved runtime of that name, which the affinity of the runtime the work is on sent it to (`docker:gpubox`). |

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
| `run` | `state` (`idle`, `running`, `stopping`), then the `started` fields of the run going or the last (`run: 0` for none), `stopping` (run number or `null`) | `idle` |
| `sessions` | `run`, `open` (keys still open), `working` (keys with a turn open) | `0`, `[]`, `[]` |
| `calls` | `calls`: `[{ref, name, depth, since (host monotonic), id, parent (index or null)}]` | `[]` |
| `waiting` | `queued` `[{text, by, client, to}]`, `given` `[{agent, text, by, client}]` | `[]`, `[]` |
| `pending` | `pending`: `[{question, run, role, text, options, mode, owner (client id or null)}]` | `[]` |
| `usage` | `run`, `usage` (Usage JSON or `null`), `budget`; refreshed at most once a second | `0`, `null`, `null` |
| `board` | `items`: `[{key, value, about, whose (both, user, flow), by, at}]`, or `null` for a run with no board; reset to `null` on start | `null` |

### `gone` {#gone}

The last message a frontend receives: `{"type": "gone", "why": …}`.

| `why` | Cause |
| --- | --- |
| `let go` | `detach` (MESSAGE or CONTROL), the frontend closing its socket, or an in-process `Link.close()` |
| `the host was closed` | CONTROL `stop`, `quit`, `SIGTERM`, idle close |
| `fell too far behind; open it again` | The host's queue for this frontend exceeded 64 MiB (cleared first) |
| `too far behind; attach again` | The socket backlog exceeded 64 MiB (cut back to the frame in progress) |
| ``held for frontends by a newer humanize; `hmz` of it reads it`` | A `GONE` frame, converted by `Link` |
| `the host went away` | Synthesised by `Link` on EOF, a socket error or a bad frame |

After `gone` the host sends no more messages but still sends replies, and gives the socket up
to 5 s to drain.

## Frontends {#hosting}

<span id="several-frontends"></span>

| Rule | |
| --- | --- |
| Names | `hello.name`, used verbatim; `""` becomes `<HUMANIZE_NAME or login or "somebody">@<kind>`. A name already attached gets `#2`, `#3`, …. The final name is sent in `welcome`. |
| Client ids | `c1`, `c2`, … per host; never reused. |
| Claims | A claimed `Outworlder` role may be answered, spoken to (`outworlder:<role>`) and set away only by its holder. `take: true` takes it from another holder, which learns it only from the `claims` and `pending` snapshots. Claims are released when the holder detaches; its questions' `owner` becomes `null`. Claims are not persisted. Claims do not restrict `say` to agents. |
| Questions | Recorded only while the run is current, the host open, and the role not away; otherwise the flow gets no answer at once. Shown to every frontend with `owner`. Answerable by the owner, or by anybody where `owner` is `null`; the first answer wins. They stay pending with nobody attached. |
| Away | Held by the host, per role. `afk` with `role` sets that role. Without `role`: with no claims, sets every role and clears per-role values; with claims, roles held by other frontends keep their value. Outlives the frontend that set it. |
| Runs | Any frontend may `start`, `stop`, `force` or `quit`. |
| Late arrival | A frontend attaching mid-run with `replay: true` reads the run from its `started` record. |

## `Link` {#link}

`hmz.daemon.Link`, exported as [`hmz.sdk.Link`](/reference/sdk#link). Signatures are on the
SDK page; transport behaviour:

| Aspect | Over a socket (`reached`) | In process (`linked`) |
| --- | --- | --- |
| Made by | `Daemon.link(name="", kind="sdk", *, replay=True)`, `hmz.daemon.reached(at, workspace, name="", kind="sdk", *, replay=True)` | `hmz.daemon.linked(host, name="", kind="tui", *, replay=True)` |
| Attach failure | `OSError` (nothing listening; no `hello` reply within 10 s; refused hello, including `no runs are held in <workspace>`) | `RuntimeError("this host has closed")` |
| Requests | Ids `r1`, `r2`, …; `seconds` honoured: `TimeoutError("no answer to '<do>' in <s>s")` | Run synchronously; `seconds` ignored |
| Refusal | `Refused(why)` | `Refused(why)` |
| Host gone | Pending and later requests are refused with the `gone` reason; a send error with `the host could not be reached: <err>` | — |
| `close()` | Shuts the socket (sends no `detach`; the host sees EOF and says `let go`). Idempotent. | `host.detach(client)` |

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
def running(workspace=None) -> Daemon | None: ...
def daemons() -> list[Daemon]: ...
def host(workspace=None, *, seconds: float = 10.0) -> Daemon: ...
def older(daemon: Daemon) -> str: ...
def linked(host: Host, name: str = "", kind: str = "tui", *, replay: bool = True) -> Link: ...
def reached(at: Path, workspace: str, name: str = "", kind: str = "sdk", *,
            replay: bool = True) -> Link: ...
Hmz, Host                                           # hmz.runtime's, fetched on access
```

`hmz.daemon.proto`: `GONE = b"X"`, `CONTROL = b"C"`, `MESSAGE = b"M"`, `PROTOCOL = 2`,
`frame(kind, payload=b"") -> bytes`, `spoken(kind, said) -> bytes` (JSON-encodes a dict),
`asked(payload) -> dict` (`{}` for bad JSON or a non-object), `Frames().feed(data) ->
list[tuple[kind, payload]]` (returns complete frames once each; raises `ValueError("a frame of <n> bytes is not one of these")` for an oversize length).
