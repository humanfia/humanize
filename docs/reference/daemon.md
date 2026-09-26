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

For what this means day to day, see [The terminal can leave](/features/daemon).

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
| `daemon.json` | `pid`, `workspace`, `started` (UTC) and `term`. |
| `daemon.lock` | Held by the daemon while it runs. The kernel drops it when the process goes, however it goes. |
| `daemon.log` | What could not be said through a terminal: the daemon's own failures, and a process that could not reach the socket. |

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

The same, one layer down:

```python
from hmz.daemon import Daemon, Held, Hmz, Session, daemons, running, start
```

| `hmz.daemon` | |
| --- | --- |
| `running(workspace=None)` | As `Daemons().here()`. |
| `daemons()` | As `Daemons().all()`. |
| `start(opens, workspace=None, *, columns=0, rows=0, seconds=10.0)` | As `Daemons().hold()`, waiting `seconds` for the socket. `columns` and `rows` are the size to draw for until a terminal arrives; `0` is this terminal's. |

### `Daemon`

One held run. Attributes `at` (its directory), `workspace`, `pid` and `started`.

| | |
| --- | --- |
| `alive` | Whether the process holding it is still there. |
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
| `stop` | `{"ok": true}`, then the interface stops its flow and closes. `{"ok": false, "why": "this run cannot be stopped from outside it"}` where nothing registered a stop. |
| anything else | `{"ok": false, "why": "no such request: '<do>'"}` |

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
