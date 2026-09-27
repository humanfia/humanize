---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# Daemon reference

`hmz` holds a directory's runs in a process of their own -- a **host**, one per directory --
and opens the [interface](/reference/tui) in your terminal's own process as one **frontend**
of them, over a socket. Closing the terminal lets go of that frontend; the run goes on taking
turns, and `hmz` in the same directory opens another interface on it, read from the top.

```text
 hmz (alice@tui) ──────┐                       ┌── daemon, one per directory ───────┐
 hmz (bob@tui) ────────┤                       │  the host: the run going, claims,  │
 hmz attach -c planner ┼── daemon.sock ───────▶│  away, lines, questions, history   │
 a bot on the SDK ─────┘  JSON requests in,    │        │                           │
                          messages out         │     the flow and its agents        │
                                               └────────────────────────────────────┘
```

For what this means day to day, see [The terminal can leave](/features/daemon).

## From the prompt

| | |
| --- | --- |
| `hmz` | Opens an interface on the runs a host holds in this directory, starting a host where none is. Every `hmz` is a whole interface of its own on the same runs. |
| `/exit`, <kbd>ctrl+q</kbd> | With a flow running, asks: **stop it, then leave**, which stops it for everybody, or **leave it running**, which lets go of this interface alone. With nothing running, leaves. |
| <kbd>ctrl+c</kbd> twice | Stops the flow, for everybody reading it. It never lets go of the interface. |

## When runs are not held

The interface holds its runs in its own process, as a host nobody else reaches, when:

| Case | |
| --- | --- |
| stdin or stdout is not a terminal | Output to a file, input from a pipe, a test driving the interface. |
| `HUMANIZE_DAEMON` is `off`, `0` or `no` | This repository's test suite sets it. `hmz.daemon.host` starts a host whatever it says. |
| The runs cannot be held | No fork, no writable home, no socket. Said on stderr, then done without. |

Then `/exit` offers **stay here** in place of **leave it running**: closing that interface
closes the run.

A directory whose runs are held by a daemon of an older humanize -- one that held a run on a
pseudoterminal -- is refused: `hmz: the runs in <dir> are held by an older humanize (pid <n>);
stop it with that version`. `hmz attach` says the same and exits `1`.

## One per directory

One daemon per workspace, so two runs never write over one epic. The directory is named for the
project and a digest of its whole path, so two checkouts of one repository are two workspaces.
The command line says nothing about what to run, so an interface arriving at held runs brings
no second setup to them: while a run goes, every interface shows the roles and agents it was
started with.

## Runs held for frontends {#hosting}

The host holds a workspace's runs for any number of **frontends** at once. A frontend is
anything that attaches: an [interface](/reference/tui#several-people-on-one-run),
[`hmz attach`](/reference/cli#hmz-attach), or a program written against the
[SDK](/reference/sdk#link). Each gets its own stream of what the runs do, and each asks for what
it wants done.

Several people can then share one run, each answering for a different part of it:

- **Claims.** An `Outworlder` role a frontend claims -- `/claim` at the interface, `-c` on
  `hmz attach` -- is that frontend's alone to answer. Claiming
  one somebody else holds is refused (`reviewer is alice@cli's`) unless it takes it over, and the
  old owner is told. A claim is given back when its frontend lets go; claims are not written down.
- **Questions.** A question is shown to every frontend, with its owner: the claimant, or nobody.
  A frontend may answer one whose owner is nobody or itself, and the first answer wins; a later
  one is refused with `already answered by …`. With nobody attached a question stays up, and the
  next frontend to arrive reads it. When a claimant leaves, its questions become anybody's.
- **Away.** `afk` is per role and held by the host, so it outlives the frontend that said it. A
  frontend may not be away for a role somebody else holds; away for everything leaves those
  roles as they were.
- **Lines.** A line said to the run goes into the turn open on the view it was said on -- a
  conversation (`coder/2`), a role's newest, or, with no view, the first working one -- one at a
  time per agent, and waits for the next turn where none is open. Claims do not limit who may
  steer an agent.
- **Runs.** One runs at a time. Any frontend may start, stop or force it.

A host goes once nothing is running or stopping and nobody is attached. A run that ended with
nobody attached, and that nobody stopped, keeps it up until one frontend has come and read it.
It goes when stopped, telling every frontend why, and one nobody reaches within a minute of
starting does not wait.

What a flow prints in the host is said to every frontend, a line at a time. What the CLIs it
starts write straight to their descriptors goes to `daemon.log`.

### The protocol {#protocol}

The socket carries frames of a 1-byte kind and a 4-byte length, 4 MiB at most. A frontend and
a host exchange `M` frames, each one JSON object. A text longer than 256 KiB in a message is cut,
ending `… (n more characters)`.

A **request** is `{"id": "r7", "do": …, …}`. Each is answered, on the connection it came in on,
with `{"type": "reply", "to": "r7", "ok": true|false, "why"?: …}`. A frontend says `hello` first.
Requests are carried out off the thread carrying the bytes, in the order each frontend sent
them; an `aside` runs apart from the rest.

| `do` | Takes | Answers |
| --- | --- | --- |
| `hello` | `name`, `kind` (`tui`, `cli`, `sdk`), `replay` (default `true`) | `client` |
| `start` | `flow`, `task`, `agents` `{role: spec}`, `envs`, `params`, `budget` (a Budget as JSON), `resume` (`false`, `true`, or an epic's path) | `run` |
| `say` | `text`, `to` (the view it was said on, `""` for none) | |
| `answer` | `question`, `text` (a number picks an offered answer) | |
| `stop`, `force` | | `force` answers `closed`: the conversations closed under their turns |
| `afk` | `on`, `role` (optional) | |
| `claim`, `release` | `role`, and `take` for `claim` | |
| `board` | `key`, `value` (`""` takes the line off) | |
| `aside` | to open one: `key` of a conversation, with `fork` to fork it, or `runs` (an agent as `-a` spells it) | `side`, `forked` |
| `aside` | to ask one: `side`, `prompt` | `answer` |
| `unaside` | `side` | |
| `status`, `detach`, `quit` | | `quit` closes the host |

A frontend is first told `welcome` -- `client`, `name`, `kind`, `workspace`, `pid`,
`protocol: 1` -- then the **history** of the run going or the last one, in order, then how
everything stands (**snapshots**), then `live` -- `seq` and `elided`, how many of the oldest
records were not kept -- and after that everything as it happens. With `replay: false` the
history is left out.

History records carry `seq`, and `run` where they belong to one:

| `type` | Fields |
| --- | --- |
| `started` | `flow`, `ref`, `task`, `by`, `client`, `roles`, `outworlders`, `agents`, `envs`, `params`, `budget`, `resume`, `began` (host monotonic), `at` (wall clock) |
| `opened` | `role`, `key` (`coder/2`), `agent`, `cli`, `model`, `counts` (sorted), `forks`, `person`, `kept` (the directory its logs are under, `""` for the CLI's own home), `mono` |
| `event` | `key`, `session` (the key where the event named a conversation, else `""`), `agent`, `cli`, `model`, `ident` (the backend's name for the conversation), `kind`, `text`, `whose`, `tokens`, `spent`, `at`, `mono` |
| `asked` | `question`, `role`, `text`, `options`, `mode` (`ask` with options or a turn open, else `listen`) |
| `answered` | `question`, `role`, `by`, `client`, `text` |
| `withdrawn` | `question`, `why` (`away` or `over`) |
| `said` | `text`, `key`, `by`, `client`: a line an agent took |
| `refused` | `agent`, `text`, `because`: a line an agent would not take, back at the head of the queue |
| `unheld` | `agent`, `texts`: lines a turn ended without saying it had |
| `dropped` | `given`, `queued`, `because` (`stopped` or `ended`) |
| `printed` | `text` |
| `stopping` | `by`, `client` |
| `ended` | `how` (`done`, `stopped`, `budget`, `refused`, `failed`, `crashed`), `why`, `mono` |

Snapshots say how one thing stands; only the latest of each is kept:

| `type` | Fields |
| --- | --- |
| `clients` | `clients`: `[{client, name, kind}]` |
| `claims` | `claims`: `{role: client}` |
| `away` | `all`, `of`: `{role: bool}` |
| `run` | `state` (`idle`, `running`, `stopping`), `run`, the `started` fields of the run going or the last, and `stopping`: the run still stopping, or `null` |
| `sessions` | `run`, `open`, `working`: keys |
| `calls` | `calls`: `[{ref, name, depth, since, id, parent}]` |
| `waiting` | `queued`: `[{text, by, client, to}]`, `given`: `[{agent, text, by, client}]` |
| `pending` | `pending`: `[{question, run, role, text, options, mode, owner}]` |
| `usage` | `run`, `usage`, `budget` |
| `board` | `items`, or `null` for a run with no board |

The last message a frontend is told is `gone`, with `why`: `let go`, `the host was closed`, or
`too far behind; attach again` for one that stopped taking what it was sent and fell further
behind than a whole run.

A reader that sends a host any other kind of frame -- an older humanize's terminal, reaching for
a run held on a pseudoterminal -- is told `GONE` with why, and let go of, rather than being
left to wait.

## What is on disk

`~/.humanize/daemons/<project>-<digest>/`, under
[`HUMANIZE_HOME`](/reference/cli#environment-variables):

| File | |
| --- | --- |
| `daemon.sock` | The socket frontends reach the runs through. `0600`. |
| `daemon.json` | `pid`, `workspace`, `started` (UTC), `kind: "host"` and `protocol: 1`. One without `protocol` is an older humanize's. |
| `daemon.lock` | Held by the daemon while it runs. The kernel drops it when the process goes, however it goes. |
| `daemon.log` | What could not be said to a frontend: the daemon's own failures, and a process that could not reach the socket. What the CLIs a host starts write straight to their descriptors lands here too. |

A `daemon.json` whose process has gone reads as nothing held: a stale socket file would be a
frontend that hangs rather than one that says nothing is running.

## How it is held

`host` forks so the caller is not kept waiting, calls `setsid` so the terminal that started it
is no longer its controlling terminal (a hangup cannot reach it), and forks again so it can
never take one. That is what `screen` does underneath, done in-process. The host reads nothing,
ignores an interrupt, closes its runs on a terminate -- waiting up to 15 seconds for them to
let go of what they made, a container included -- and says what is printed in it to its
frontends.

The interface draws in the process of the terminal it was opened in, and knows the runs only
as the messages it is told and the requests it asks: the same [`Link`](#link) whether they are
held by a host or in its own process.

## Python

<span id="from-outside-the-interface"></span>From a tool, reach held runs through
[`hmz.sdk.Daemons`](/reference/sdk):

```python
from hmz.sdk import Daemons

held = Daemons().here()          # this directory's host, or None
for one in Daemons().all():      # every host on this machine
    print(one.workspace, one.status()["flows"])
```

| `Daemons` | |
| --- | --- |
| `here(workspace=None)` | The [`Daemon`](#daemon) holding runs in that workspace, or `None`. |
| `all()` | Every daemon on this machine, oldest first. |
| `host(workspace=None)` | The `Daemon` [hosting](#hosting) that workspace's runs, started where none is. Raises `OSError` where an older humanize holds them, or no host came up. |

The same, one layer down:

```python
from hmz.daemon import Daemon, Hmz, Host, Link, daemons, host, linked, running
```

| `hmz.daemon` | |
| --- | --- |
| `running(workspace=None)` | As `Daemons().here()`. |
| `daemons()` | As `Daemons().all()`. |
| `host(workspace=None, *, seconds=10.0)` | As `Daemons().host()`, waiting `seconds` for the socket. |
| `linked(host, name="", kind="tui", *, replay=True)` | A [`Link`](#link) to a `Host` in this process, as `Hmz().host()` answers one. |
| `Hmz`, `Host` | The runtime's own, handed through. |

### `Daemon`

One daemon. Attributes `at` (its directory), `workspace`, `pid`, `started` and `protocol`
(`1` for a [host](#hosting), `0` for an older humanize's, which no frontend reaches).

| | |
| --- | --- |
| `alive` | Whether the process holding it is still there. |
| `link(name="", kind="sdk", *, replay=True)` | Attaches a frontend to the runs a host holds, and returns its [`Link`](#link). `name` defaults to `HUMANIZE_NAME`, else your login, then `@kind`; a name already attached gets `#2`. `OSError` where nothing answers, or an older humanize holds them. |
| `status()` | What it says about itself (below). One that will not answer, starting up or wedged, is answered for from `daemon.json`. |
| `detach()` | Lets go of every frontend, leaving the runs running. How many. |
| `stop(*, seconds=20.0)` | Closes the runs, lets every frontend go, and waits for the daemon to go. Whether it has gone. |
| `kill(*, seconds=20.0)` | `SIGTERM`, then `SIGKILL`, whatever the run was doing; removes the socket and `daemon.json`. Whether it has gone. |
| `asked(said)` | Sends one control request (below) and returns the answer, or `{}` where none came in 5 s. |

`status()` answers with these keys. A daemon that did not answer gives only the ones marked †,
from `daemon.json`, with `attached` `0` and `flows` and `calls` empty.

| Key | |
| --- | --- |
| `ok` | `true`: the daemon answered. |
| `pid`, `workspace`, `started`, `kind`, `protocol` † | As in `daemon.json`. |
| `attached` † | How many frontends are reading. |
| `clients` | Who: `[{client, name, kind}]`. |
| `state`, `run` | `idle`, `running` or `stopping`, and the number of the run going or the last. |
| `flows` † | The refs of the flows running, outermost first. |
| `calls` † | The same as objects: `ref`, `name`, `depth`, `seconds` running, `id`, and `parent`, the index of the call that made it. |
| `flow` | The flow of the run going or the last. |
| `budget`, `usage` | What the run may spend and has spent, as JSON (`Infinity` for no cost limit). `null` with nothing running. |

### Control requests

A request is `{"do": …}` over the socket; `Daemon.asked` sends one.

| `do` | Answer |
| --- | --- |
| `status` | `{"ok": true, …}`, as above. |
| `detach` | `{"ok": true, "let go": <count>}`: every frontend let go of. |
| `stop` | `{"ok": true}`, then the host closes its runs and lets every frontend go, telling each why. |
| anything else | `{"ok": false, "why": "no such request: '<do>'"}` |

### `Link` {#link}

One frontend: a context manager, iterable of messages until a listener is set. The same class
whether the runs are held by a host or in this process.

| | |
| --- | --- |
| `client` | Its client id, which `owner` and `client` in messages name it by. |
| `heard(listener)` | Hands every message to `listener`, those already waiting first, on a thread of the link's own. |
| `for said in link` | Every message, until `gone`. |
| `asked(said, *, seconds=None)` | One [request](#protocol), answered. Raises [`Refused`](/reference/sdk#refused) with the host's `why`, or `TimeoutError`. |
| `start(flow, task, *, agents=None, envs=None, params=None, budget=None, resume=False)` | `start`; `params` and `budget` may be models. |
| `say(text, *, to="")`, `answer(question, text)` | `say`, `answer`. |
| `stop()`, `force()` | `stop`, `force`. |
| `afk(*, on, role="")`, `claim(role, *, take=False)`, `release(role)` | `afk`, `claim`, `release`. |
| `board(key, value)`, `aside(**said)` | `board`, `aside`. |
| `close()` | Lets go of the runs, which go on. |

```python
from hmz.sdk import Daemons

with (Daemons().here() or Daemons().host()).link(name="ci", replay=False) as link:
    link.claim("reviewer")
    for said in link:
        if said["type"] == "pending":
            for asked in said["pending"]:
                if asked["owner"] == link.client:
                    link.answer(asked["question"], "looks good")
```
