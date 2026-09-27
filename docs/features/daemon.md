---
pageClass: hmz-feature
---

# The terminal can leave

Close the terminal and the run keeps going. Run `hmz` in the same directory later and you are
back in it, read from the top.

<HmzDaemon />

<p class="hmz-note">
Close both windows and the run carries on. Open one and run hmz to come back. The buttons on
the run leave it, stop it, or lose it with the machine.
</p>

## What you get

- **A lost terminal is not a stopped run.** Close the window, or lose the SSH connection to the
  machine the run is on, and the flow carries on taking its turns.
- **`hmz` brings you back.** In the same directory, it opens an interface on the run already
  going there and reads it from the top: what was said, asked and answered, and how things
  stand now.
- **More than one interface can read.** Run `hmz` in a second terminal and it is a whole
  interface of its own on the same run -- its own views, its own monitor. Either can type.
- **One run per directory.** Another checkout of the same project is another directory, with a
  run of its own.

## Leaving is not stopping

When a flow is running, `/exit` (or <kbd>ctrl+q</kbd>) asks what you mean:

| You choose | What happens |
| --- | --- |
| **leave it running** | This interface lets go, and nothing else does. The run carries on, and `hmz` reads it again. |
| **stop it, then leave** | The flow stops for everybody reading it, and this interface closes. |

The other ways to stop a run are on [Stopping](/user/stopping).

## Several people on one run

Every interface on a run is one **frontend** of it, and so is
[`hmz attach`](/reference/cli#hmz-attach) and a program on the [SDK](/reference/sdk#link). Each
takes the part of the run that is its own:

```sh
# pane A: start a flow whose outworlders are a planner and a reviewer
HUMANIZE_NAME=alice hmz

# pane B, same directory: the same run, read from the top
HUMANIZE_NAME=bob hmz            # tab to the reviewer's transcript, then /claim

# pane C: one more, answering for the planner alone
hmz attach -c planner
```

- **Each answers for their own part.** `/claim` on an outworlder's transcript, or
  `hmz attach -c reviewer`, makes that role's questions yours alone. Everybody else sees it
  marked `bob@tui's`. A question nobody claimed goes to whoever answers first.
- **Everybody sees who did what.** Every answer, every line said to an agent and every run
  started says who did it (` · by alice@tui`), and the monitor lists who is reading.
- **Stopping is for everybody.** `/stop` and <kbd>ctrl+c</kbd> twice stop the one run all of
  them are reading, and each is told who stopped it.
- **Leaving hands your part back.** A frontend that goes gives its roles back, and whatever it
  was asked waits for somebody else. `/afk` stays said after you have gone.

A name is `HUMANIZE_NAME`, else your login, then what the frontend is: `alice@tui`, `bob@cli`.
The details are in the [daemon reference](/reference/daemon#hosting).

## What it does not survive

The run lives on the machine it started on. If that machine restarts, or the process holding
it is killed, the run ends. What it wrote down is still there, and a flow that can be
[picked up](/features/resuming) carries on from where it stood.

::: details When a run is not held apart from the terminal
Only the terminal interface, started at a real terminal, holds its runs apart. Otherwise the
interface holds them in its own process, the run lives and ends with it, and `/exit` offers to
stay rather than to leave it running:

- **`hmz exec`** runs in the process you started. For a run with no terminal at all, see
  [Run it unattended](/user/unattended).
- **Output to a file, or input from a pipe.** There is no terminal to come back to.
- **`HUMANIZE_DAEMON=off`** in the environment (`0` and `no` work too) turns it off.
:::

## Where the detail is

- [Stopping](/user/stopping): stopping a flow, and what it leaves behind
- [Run it unattended](/user/unattended): running with no terminal at all
- [Picking a run up](/user/resuming): carrying on after the run itself has gone
- [Daemon reference](/reference/daemon): how runs are held, and doing it all from Python
