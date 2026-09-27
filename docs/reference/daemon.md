---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# Daemon reference

`hmz` holds the [interface](/reference/tui), and the run inside it, in a process of its own:
one per directory. Your terminal reads that process. Closing the terminal lets go of it; the
run goes on taking turns, and `hmz` in the same directory opens it again from the top.

```text
 your terminal ──┐                  ┌── daemon, one per directory ──┐
 another one   ──┼── daemon.sock ──▶│  pseudoterminal               │
 (ssh, tmux…)  ──┘  keys in,        │     ▲                         │
                    screen out      │  the interface ── the flow    │
                                    └───────────────────────────────┘
```

For what this means day to day, see [The terminal can leave](/features/daemon). A daemon
can also hold a workspace's runs for [several frontends at once](#hosting).

## From the prompt

| | |
| --- | --- |
| `hmz` | Reads the run held in this directory, or starts one where none is. |
| `/exit`, <kbd>ctrl+q</kbd> | With a flow running, asks: **stop it, then leave**, or **leave it running**, which lets go of this terminal. The terminal left prints `detached`. With nothing running, leaves. |
| <kbd>ctrl+c</kbd> twice | Stops the flow. It never lets go of the terminal. |

Several terminals may read one run at once. Each says how big it is as it arrives, and the
screen is laid out again for it.

## When a run is not held

The interface opens in the terminal's own process, with nothing held, when:

| Case | |
| --- | --- |
| stdin or stdout is not a terminal | Output to a file, input from a pipe, a test driving the interface. |
| `HUMANIZE_DAEMON` is `off`, `0` or `no` | This repository's test suite sets it. `hmz.daemon.start` holds a run whatever it says. |
| The run cannot be held | No fork, no writable home, no socket. Said on stderr, then done without. |

Then `/exit` offers **stay here** in place of **leave it running**: closing that terminal
closes the run.

## One per directory

One daemon per workspace, so two runs never write over one epic. The directory is named for the
project and a digest of its whole path, so two checkouts of one repository are two workspaces.
The command line says nothing about what to run, so a terminal arriving at a held run brings no
second setup to it.

## Runs held for frontends {#hosting}

A daemon can hold a workspace's runs a second way: as a **host**, for any number of
**frontends** at once. A frontend is anything that attaches: [`hmz attach`](/reference/cli#hmz-attach),
a program written against the [SDK](/reference/sdk#link), or an interface of its own. Each gets
its own stream of what the runs do, and each asks for what it wants done.

```text
 hmz attach -c planner ──┐                       ┌── daemon, one per directory ───────┐
 hmz attach -c reviewer ─┼── daemon.sock ───────▶│  the host: the run going, claims,  │
 a bot on the SDK ───────┘  JSON requests in,    │  away, lines, questions, history   │
                            messages out         │        │                           │
                                                 │     the flow and its agents        │
                                                 └────────────────────────────────────┘
```

Several people can then share one run, each answering for a different part of it:

- **Claims.** An `Outworlder` role a frontend claims is that frontend's alone to answer. Claiming
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
| `opened` | `role`, `key` (`coder/2`), `agent`, `cli`, `model`, `counts` (sorted), `forks`, `person`, `mono` |
| `event` | `key`, `session` (the key where the event named a conversation, else `""`), `agent`, `cli`, `model`, `ident` (the backend's name for the conversation), `kind`, `text`, `whose`, `tokens`, `spent`, `at`, `mono` |
| `asked` | `question`, `role`, `text`, `options`, `mode` (`ask` with options or a turn open, else `listen`) |
| `answered` | `question`, `role`, `by`, `client`, `text` |
| `withdrawn` | `question`, `why` (`away` or `over`) |
| `said` | `text`, `key`, `by`, `client`: a line an agent took |
| `refused` | `agent`, `text`, `because`: a line an agent would not take, back at the head of the queue |
| `unheld` | `agent`, `texts`: lines a turn ended without saying it had |
| `dropped` | `given`, `queued`, `because` (`stopped` or `ended`) |
| `printed` | `text` |
| `stopping` | `by` |
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

A terminal that reaches a host is told `GONE` -- `held for frontends; hmz attach reads it` --
and a frontend that reaches a run held for a terminal is told `held for a terminal; hmz opens
it`, rather than either being left to wait.

## The terminal it draws for {#what-kind-of-terminal-it-draws-for}

A held run keeps one pseudoterminal for its whole life, with the `TERM` of the shell that first
ran `hmz` there. A terminal of another kind that reads it later is drawn for in that first
one's language; [`status()`](#daemon) says which, under `term`. To change it, stop the held run
and run `hmz` again from the terminal you want.

<span id="what-a-terminal-is-put-back-to"></span>When a terminal stops reading, however it
stops, it puts itself back: out of the alternate screen, cursor shown, mouse and focus
reporting off, bracketed paste off, keyboard protocol popped, line wrapping on.

## What is on disk

`~/.humanize/daemons/<project>-<digest>/`, under
[`HUMANIZE_HOME`](/reference/cli#environment-variables):

| File | |
| --- | --- |
| `daemon.sock` | The socket terminals reach the run through. `0600`. |
| `daemon.json` | `pid`, `workspace`, `started` (UTC) and `term`; for a [host](#hosting), `kind: "host"` and `protocol: 1` in place of `term`. |
| `daemon.lock` | Held by the daemon while it runs. The kernel drops it when the process goes, however it goes. |
| `daemon.log` | What could not be said through a terminal: the daemon's own failures, and a process that could not reach the socket. A host's CLIs write here too. |

A `daemon.json` whose process has gone reads as nothing held: a stale socket file would be a
terminal that hangs rather than one that says nothing is running.

## How it is held

`start` forks so the caller is not kept waiting, calls `setsid` so the terminal that started it
is no longer its controlling terminal (a hangup cannot reach it), forks again so it can never
take one, and opens a pseudoterminal for the interface to draw on when nobody is reading. That
is what `screen` does underneath, done in-process.

The interface knows nothing of it: it draws on a terminal. Everything it *does* runs in the
held process, which is why [`Hmz`](/reference/sdk) is reached from there: `hmz.daemon` hands it
through, and the interface asks it directly. The socket is only for the terminals outside.

## Python

<span id="from-outside-the-interface"></span>From a tool, reach held runs through
[`hmz.sdk.Daemons`](/reference/sdk):

```python
from hmz.sdk import Daemons

held = Daemons().here()          # this directory's run, or None
for one in Daemons().all():      # every run held on this machine
    print(one.workspace, one.status()["flows"])
```

| `Daemons` | |
| --- | --- |
| `here(workspace=None)` | The [`Daemon`](#daemon) holding a run in that workspace, or `None`. |
| `all()` | Every run held on this machine, oldest first. |
| `hold(opens, workspace=None, *, columns=0, rows=0)` | Holds a run and returns its `Daemon` once it is listening. `opens` is called in the held process with the [`Held`](#held) run, and returns when the run is over. Raises `OSError` where one is already held there, or it did not come up. |
| `host(workspace=None)` | The `Daemon` [hosting](#hosting) that workspace's runs for frontends, started where none is. Raises `OSError` where a run is held there for a terminal, or no host came up. |

The same, one layer down:

```python
from hmz.daemon import Daemon, Held, Hmz, Link, Session, daemons, host, linked, running, start
```

| `hmz.daemon` | |
| --- | --- |
| `running(workspace=None)` | As `Daemons().here()`. |
| `daemons()` | As `Daemons().all()`. |
| `start(opens, workspace=None, *, columns=0, rows=0, seconds=10.0)` | As `Daemons().hold()`, waiting `seconds` for the socket. `columns` and `rows` are the size to draw for until a terminal arrives; `0` is this terminal's. |
| `host(workspace=None, *, seconds=10.0)` | As `Daemons().host()`. |
| `linked(host, name="", kind="tui", *, replay=True)` | A [`Link`](#link) to a `Host` in this process, as `Hmz().host()` answers one. |

### `Daemon`

One held run. Attributes `at` (its directory), `workspace`, `pid`, `started` and `protocol`
(`1` for a [host](#hosting), `0` for a run held for a terminal).

| | |
| --- | --- |
| `alive` | Whether the process holding it is still there. |
| `link(name="", kind="sdk", *, replay=True)` | Attaches a frontend to the runs a host holds, and returns its [`Link`](#link). `name` defaults to `HUMANIZE_NAME`, else your login, then `@kind`; a name already attached gets `#2`. `OSError` where nothing answers, or the run is held for a terminal. |
| `attach()` | Reads it from this terminal until it ends or lets go. `0`, or `1` where there was nothing to read. |
| `status()` | What it says about itself (below). A run that will not answer, starting up or wedged, is answered for from `daemon.json`. |
| `detach()` | Lets go of every terminal reading it, leaving the run running. How many. |
| `stop(*, seconds=20.0)` | Asks the run to stop, as closing the interface does, and waits. Whether it has gone. |
| `kill(*, seconds=20.0)` | `SIGTERM`, then `SIGKILL`, whatever the run was doing; removes the socket and `daemon.json`. Whether it has gone. |
| `asked(said)` | Sends one control request (below) and returns the answer, or `{}` where none came in 5 s. |

`status()` answers with these keys. A run that did not answer gives only the ones marked †,
from `daemon.json`, with `attached` `0` and `flows` and `calls` empty.

| Key | |
| --- | --- |
| `ok` | `true`: the run answered. |
| `pid`, `workspace`, `started`, `term` † | As in `daemon.json`. |
| `attached` † | How many terminals are reading. |
| `flows` † | The refs of the flows running, outermost first. |
| `calls` † | The same as objects: `ref`, `name`, `depth`, `seconds` running, `id`, and `parent`, the index of the call that made it. |
| `flow` | The flow the interface is running or set up to run. |
| `budget`, `usage` | What the run may spend and has spent, as JSON (`Infinity` for no cost limit). `null` with nothing running. |

### Control requests

A request is `{"do": …}` over the socket; `Daemon.asked` sends one.

| `do` | Answer |
| --- | --- |
| `status` | `{"ok": true, …}`, as above. |
| `detach` | `{"ok": true, "let go": <count>}` |
| `stop` | `{"ok": true}`, then the interface stops its flow and closes -- or a host closes its runs and lets every frontend go. `{"ok": false, "why": "this run cannot be stopped from outside it"}` where nothing registered a stop. |
| anything else | `{"ok": false, "why": "no such request: '<do>'"}` |

A host answers `status` with `kind`, `protocol`, `clients` (`[{client, name, kind}]`),
`state` (`idle`, `running`, `stopping`) and `run`, beside the keys above; `detach` lets go of
every frontend.

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

### `Held`

What `opens` is handed: the run being held. It is a [`Session`](#session), plus the three hooks
the held process registers.

| | |
| --- | --- |
| `redrawn(hook)` | Called on a thread of its own when a terminal arrives, to draw the whole screen again. |
| `stopping(hook)` | Called when a `stop` request arrives. |
| `says(hook)` | Returns a dict merged into `status()`. The flows running are added by the daemon itself. |

### `Session`

What whatever is drawing sees of the run holding it: a `Protocol`, so a held run and one opened
in the terminal's own process are one interface. The interface is handed one only where the run
is held, which is where `/exit` offers **leave it running**.

| | |
| --- | --- |
| `attached` | How many terminals are reading now. |
| `detach()` | Lets go of every terminal, leaving the run running. How many. |
