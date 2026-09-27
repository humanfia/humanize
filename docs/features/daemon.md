---
pageClass: hmz-feature
---

# The terminal can leave

Close the terminal and the run keeps going. Run `hmz` in the same directory later and you are
back in it, with the whole screen drawn again.

<HmzDaemon />

<p class="hmz-note">
Close both windows and the run carries on. Open one and run hmz to come back. The buttons on
the run leave it, stop it, or lose it with the machine.
</p>

## What you get

- **A lost terminal is not a stopped run.** Close the window, or lose the SSH connection to the
  machine the run is on, and the flow carries on taking its turns.
- **`hmz` brings you back.** In the same directory, it opens the run already going there and
  draws the whole screen again, at your terminal's size.
- **More than one terminal can watch.** Run `hmz` in a second terminal and both show the run.
  Either can type.
- **One run per directory.** Another checkout of the same project is another directory, with a
  run of its own.

## Leaving is not stopping

When a flow is running, `/exit` (or <kbd>ctrl+q</kbd>) asks what you mean:

| You choose | What happens |
| --- | --- |
| **leave it running** | Every terminal lets go. The run carries on, and `hmz` opens it again. |
| **stop it, then leave** | The flow stops, and the interface closes. |

The other ways to stop a run are on [Stopping](/user/stopping).

## More than one person on one run

A run can also be held for **frontends** rather than for a terminal: a program on the
[SDK](/reference/sdk#link) starts it, and each person reads it with
[`hmz attach`](/reference/cli#hmz-attach) from a terminal of their own.

- **Each answers for their own part.** `hmz attach -c reviewer` makes the reviewer's questions
  yours alone; a question nobody claimed goes to whoever answers first.
- **Everybody sees who did what.** Every answer and every line said to an agent says who said
  it, and whoever arrives late reads the run from the top.
- **Leaving hands your part back.** A frontend that goes gives its roles back, and whatever it
  was asked waits for somebody else. `/afk` stays said after you have gone.

The details are in the [daemon reference](/reference/daemon#hosting).

## What it does not survive

The run lives on the machine it started on. If that machine restarts, or the run's process is
killed, the run ends. What it wrote down is still there, and a flow that can be
[picked up](/features/resuming) carries on from where it stood.

::: details When a run is not held apart from the terminal
Only the terminal interface, started at a real terminal, keeps its run apart. Otherwise the run
lives and ends with the terminal, and `/exit` offers to stay rather than to leave it running:

- **`hmz exec`** runs in the process you started. For a run with no terminal at all, see
  [Run it unattended](/user/unattended).
- **Output to a file, or input from a pipe.** There is no terminal to hand over.
- **`HUMANIZE_DAEMON=off`** in the environment (`0` and `no` work too) turns it off.
:::

## Where the detail is

- [Stopping](/user/stopping): stopping a flow, and what it leaves behind
- [Run it unattended](/user/unattended): running with no terminal at all
- [Picking a run up](/user/resuming): carrying on after the run itself has gone
- [Daemon reference](/reference/daemon): how a run is held, and doing it all from Python
