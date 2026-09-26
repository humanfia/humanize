---
pageClass: hmz-feature
---

# The anchor

An agent runs on this machine, unchanged. Everything it *does* happens on another machine:
reading and writing the project's files, running commands, and reaching the network from those
commands. The agent is told none of this. There is no plugin, no configuration and no flag in
its own settings that says where it is.

<HmzSyscalls />

In one line: **the work is over there, and the account is over here.** Your login, your keys
and the agent's connection to its model provider never reach the machine the work lands on.

## Files: a local copy, kept in step

The agent reads and writes a local copy of the target's workspace, at local speed, and humanize
keeps the two in step.

- **An edited file reaches the target whole**, before any command runs there, and again when
  the session ends. The target never holds half an edit.
- **Creating, removing, renaming and changing permissions happen on the target first**, so any
  error the agent sees is the target's own.
- **The local copy belongs to the target.** Anything in it that the target does not have is
  deleted. humanize refuses to use a directory that holds unrelated files, or that was last
  used for another target, unless told to.

## Commands: run on the target

A command the agent starts runs on the target, but behaves like an ordinary local program: the
same output and exit status. Several can run at once, and a long-running one can be talked to
while it runs. Signals travel both ways: stopping a command stops the real one on the target.

## What stays on this machine

- the agent's own program, and the runtime it runs on
- its state directory, and anything it runs from inside it
- the credentials of the [account](/features/accounts) it runs as, including a token it
  refreshes mid-turn
- any variable named as the agent's own, so a key it was given for its model provider is not
  handed to every command it runs
- the agent's own network connections, unless you ask otherwise

## Before you rely on it

::: danger Serving is not a sandbox
The program that serves a target limits which files a request may name, not what the commands
it runs may do. **A listening port is as good as a shell on that machine.** Prefer targets
reached over SSH or Docker, which open no port at all.
:::

- **One writer.** Nobody else may edit the target's workspace while an agent works on it.
- **Only file contents cross.** Ownership, device nodes and extended attributes stay in the
  local copy, and so does a permission change made through a file that is already open.
- **Losing the connection does not stop the agent.** Work that needs the target fails, files
  already copied still read, and the agent exits with its own status.
- **A request that gets no answer is given up here, not there.** It may still take effect on
  the target after the agent was told it failed.
- **Nothing crosses between the two.** Renaming or linking between the workspace and a path on
  this machine fails, and `sudo` does not work for the agent here. Commands run on the target,
  where `sudo` works as usual.
- **Names are looked up here** and dialled from the target, so split-horizon DNS can disagree.

::: details The agent itself can run elsewhere too
By default the agent runs here, and every file it opens is a round trip. It can instead run
beside its work, where opening a file costs nothing extra, or on a third machine, with humanize
introducing the two even when neither can reach the other. Either way the account and the
connection to the model provider go with the agent. See
[Remote execution reference](/reference/remote-execution).
:::

## What it needs

- **The machine the agent runs on:** Linux on x86-64 or aarch64.
- **The machine the work lands on:** any POSIX system with Python 3.12 or newer. No root, no
  compiler, nothing to install.

## Where the detail is

- [Remote execution](/user/remote-execution): pointing an agent at another machine
- [Remote execution reference](/reference/remote-execution): exactly what you can rely on
- [Security](/user/security): read this first
- [Two accounts of one CLI](/features/accounts): the accounts that stay on this machine
