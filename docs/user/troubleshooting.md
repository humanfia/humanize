---
# Every entry is one h3, and there are dozens: an outline of the messages themselves is a wall
# of half-sentences cut off at the same width. The outline names where a problem happens; the
# page lists the messages.
outline: 2
---

<script setup>
import TroubleFilter from '../.vitepress/theme/components/user-troubleshooting/TroubleFilter.vue'
</script>

# Troubleshooting

Find the message you got, or the thing you saw, and what to do about it. The entries are
grouped by where you meet them. Paste the message into the box to see only the entries that
match.

<TroubleFilter />

## Starting a flow

`hmz exec` prints these after `hmz exec: error:` and exits with status 2. Nothing has run. At
the prompt, the same words follow `hmz:`.

### `rlar needs an agent for 'actor', 'reviewer'; give each with -a ROLE=CLI/MODEL:EFFORT`

The flow has agent roles that nothing on the line fills. Give one `-a` per role, named after
the role:

```sh
hmz exec -f rlar -a actor=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high \
    -b cost=20 "fix the build"
```

### `ralph_loop has no agent role 'builder'; its agent roles are 'agent'`

The line names a role the flow does not have: a typo, or another flow's role. Use a name from
the list at the end of the message. `chat` has `assistant`, `ralph_loop` has `agent`, and
`rlar` has `actor` and `reviewer`.

### `…: 'human' is filled by the runtime -- whoever is outside the run -- and is not given with -a`

That role is the person outside the run, and humanize fills it. Take it off the line.
`… is the workspace the run is started in, and is not given with -e` is the same for an
environment: it is the directory you ran `hmz exec` in.

### `-a 'claude/claude-opus-5:high': expected <role>=<harness>[@<provider>]/<model>:<effort>`

The agent has no role in front of it. Say which role it fills:
`-a agent=claude/claude-opus-5:high`.

### `-a 'agent=claude:high': expected [NAME=]CLI[@PROVIDER]/MODEL:EFFORT`

A part is missing. The CLI, the model and the effort are all required, and `auto` is the effort
that asks for none:

```sh
-a agent=claude/claude-opus-5:high
-a agent=opencode/anthropic/claude-opus-5:auto   # a model may hold slashes
```

### `ralph_loop: a run is given a budget -- -b duration=...,cost=...,output_tokens=... -- and this one was given none`

Every flow except `chat` runs under a budget. Give it one with `-b`:

```sh
-b cost=20
-b duration=6h,output_tokens=10m
```

See [Allowances](/features/allowances) for what each key stops.

### `agent=claude/claude-opus-5:ultra: claude cannot be asked to think at 'ultra'; expected one of ultracode, max, xhigh, high, medium, low`

That effort is not on the backend's ladder. Pick one from the list, or `auto` for none. A CLI
you added at [`/providers`](/user/providers) takes any effort.

### `cursor-agent lists no gpt-5.2-medium: this account runs gpt-5.2 as gpt-5.2-low, gpt-5.2-high`

cursor-agent writes the effort into the model's id, and this account does not offer the model
at that effort. Pick an effort the message lists.

### `…: 'reviewer' needs GoalCommandAgentMixin, which pi does not do`

The role asks for something that CLI cannot do: pursue a goal, be steered, or answer a hook.
Give the role a CLI that can. [Reference › Flows](/reference/flows) has the table of which CLI
does what.

### `…: 'builder' is claude, and codex was given`

The role is written for one CLI only. Give it that CLI.

### `nosuchflow: no flow is called 'nosuchflow', and it is not a path`

`-f` names a flow that nothing offers. A name is looked up in this project's `.humanize/flows`,
then in `~/.humanize/flows`, then among humanize's own flows and every
[flowverse](/weaver/flowverses) fetched here. Anything else is read as a path.

### `ralph_loop: the official flowverse has not been fetched yet -- open /flowverses and press r on it`

The name is right, but the flowverse has not been downloaded yet. `hmz` fetches flowverses in
the background every time it starts. To fetch one now, open `/flowverses` and press
<kbd>r</kbd> on it.

### `… holds gen-idea, gen-plan, rlcr and none is called 'humanize1'; name one as humanize1:<flow>`

The directory holds several flows, and none is named after it. Say which one you mean:
`-f humanize1:gen-plan`. A name that is not among them gets
`… holds no flow called '…'; it holds …`, with the list to choose from.

### `…: 1 validation error for Params`

`-p` gave a key the flow does not take, or a value its type cannot read. The lines after it
name the key and say what was wrong:

```
hmz exec: error: chat:chat: 1 validation error for Params
foo
  Extra inputs are not permitted [type=extra_forbidden, input_value=1, input_type=int]
```

Fix the value, or leave the key off to get its default.

### `ralph_loop has no run here to pick up: none got as far as writing anything down`

`--resume` found no run of this flow in this directory that saved anything to pick up from.
Run it without `--resume`. `… does not say it can be picked up, so there is no run of it to
resume` means the flow cannot be resumed at all.

### `hmz exec: nobody lists a price for my-model, so cost=5 cannot stop what it spends`

A warning, and the run goes ahead. humanize knows no price for that model, so a `cost` cap
never fills. Cap something it can count as well:

```sh
-b cost=5,output_tokens=2m
```

## At the prompt

The interface prints most of these in red, after `hmz:`.

### `no coding agent is installed here`

You typed a task, and the flow has no agent to run it on. humanize looks for a coding agent CLI
on your `PATH` and in the directories installers use, such as `~/.local/bin` and
`/usr/local/bin`. Check what it can find:

```sh
command -v agy claude codex cursor-agent grok kimi mimo opencode pi qwen zcode
```

Install one from [Installation](/user/installation), then open `hmz` again. If one is
installed, open `/flow` and give the role a CLI and a model.

### `no such flow: ralph`

A `$` line names a flow by the name it is offered under:

| Flow | Typed as |
| --- | --- |
| humanize's own, and the official flowverse's | `$ralph_loop` |
| this project's, in `.humanize/flows` | `$local/twice` |
| yours, in `~/.humanize/flows` | `$user/twice` |
| another flowverse's | `$<flowverse>/name` |

A flowverse not fetched yet offers nothing: open `/flowverses` and press <kbd>r</kbd> on it.

### `no such command: /foo`

Type `/` to see the commands. There are fourteen, listed in
[Reference › TUI](/reference/tui).

### `a flow is running; no choosing a flow`

A `/flow <name>` or a `$` line while a flow runs. Starting another flow would stop this one, so
humanize refuses. Stop it first with [`/stop`](/user/stopping), or <kbd>ctrl+c</kbd> twice on
an empty line. `/flow` on its own still opens, on the roles of the flow that is running.
`a flow is already running` has the same cause.

### `reviewer is not set up yet`

Said in `/flow` when you save. The role has no CLI and model yet. Open it and choose both.
`a run of this flow is given a budget: set what it may spend first` is the same for the budget.

### `nothing was set up, so nothing was started`

A `$` line named a flow this directory has never set up, so `/flow` opened on it, and you left
without saving. Type the line again and save the menu this time.

### `say on or off, not 'yes'`

`/details` and `/afk` switch over when you give them nothing. Given a word, they take only `on`
or `off`.

### `/btw needs a flow that is running`

[`/btw`](/user/btw) asks the running flow's agents a side question, so it needs a flow that is
running. `/btw needs a coding agent that supports read-only turns` means the flow has no coding
agent to ask. `/btw already has 4 questions in progress` means four are still out: wait for one
to answer.

### A line I typed did not reach the agent

A typed line goes to the agent you are reading. When you are reading all of them, it goes to
whichever has a turn open. Until that agent takes it, the line stays pinned above the prompt.

- **Between turns**, it waits for the next turn to start.
- **Several lines** go one at a time, so the later ones wait a turn or two.
- **When the flow ends**, lines nobody took move into the transcript marked `never sent`.

To send it to another agent, press <kbd>tab</kbd> to read that one first. See
[Steering](/user/steering).

### The screen is unreadable in my terminal

The interface draws in your terminal's own 16 colours, so the usual cause is a terminal theme
with too little contrast between two of them. Change the terminal's theme, or run
`NO_COLOR=1 hmz` for no colour at all, or `TEXTUAL_THEME=textual-dark hmz` for a fixed palette.

### The token count sits still, then jumps

Claude Code, Codex, Kimi Code, ZCode and DeepSeek Harness count as they go. The other backends
report at the end of each turn, so their count jumps. An agent working on another machine
reports at the end of each turn too.

If one of those five sits still, it is writing its log somewhere `hmz` is not looking. `hmz`
looks where its own `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `KIMI_CODE_HOME` or `DSH_HOME` points,
and in `~/.zcode` under its own `HOME`. Start `hmz` with the same values the CLI runs with.

## Agents, accounts and models

A failed turn ends with what the CLI said, then the kind of failure in brackets:

```text{2}
Command '['claude', …]' returned non-zero exit status 1. 429 rate limit exceeded
(throttled: this account has spent its quota; another one, or a wait, is what answers it)
```

humanize waits, retries, or moves to the next account or [fallback](/user/fallback) by itself,
depending on the kind. The entries below say what is left for you to do. A failure with no
brackets is one humanize did not recognise, and it is retried as that place says.

### The agent fails on its first turn

Run the CLI yourself with the same model, under the same account. A model that account cannot
run fails there the same way. humanize checks the effort before it starts, but only the CLI
knows which models your account may use.

### `(throttled: this account has spent its quota; another one, or a wait, is what answers it)`

The account hit its rate limit. humanize waits, tries once more, then moves to the next account
of that CLI. Give it one to move to: add an account at [`/providers`](/user/providers) and set
what it falls back to.

### `(refused: that account needs signing in again)`

The credential was refused, or the login expired. humanize moves straight on to the next
account. Sign the account back in, with the CLI's own login for the account this machine uses:

```sh
claude auth login
```

For an account humanize keeps, open `/providers`, choose the account, and pick
**sign in again**.

### `(unlisted: … this account was last offered …)`

The account is signed in, but it may not use that model. The bracket says whether humanize's
list of this account's models is out of date:

```
(unlisted: the 3 models this account was last offered (asked 2026-09-10) still name it, so
that list is the stale part; r on its models asks again)
```

humanize never asks an account again on its own. In `/flow`, open the agent, open its `model`
row, and press <kbd>r</kbd> to ask the CLI what this account runs now. Then choose one of
those.

### `(retired: the model is gone or was never this account's; another place is what answers it)`

The CLI says there is no such model. No account of that CLI has it, so the turn goes straight
to the next [fallback](/user/fallback). Choose another model: press <kbd>r</kbd> on the agent's
`model` row to see what the CLI runs.

### `(missing: npm i -g @anthropic-ai/claude-code)`

The CLI is not installed where the agent runs, or would not start. The bracket holds the
command that installs it. See [Installation](/user/installation).

### `(sandboxed: this machine will not let it sandbox itself; run it without one, or somewhere it can)`

The CLI could not start its own sandbox, usually with `bwrap: … Permission denied` just before.
An unprivileged container is the common cause. Run it where the kernel allows unprivileged user
namespaces, or give the role another CLI.

### `(contended: two turns of it are sharing one database)`

Two turns of opencode or mimocode wrote to the CLI's one database at once and got
`database is locked`. humanize retries three times, a second apart, which nearly always clears
it. If it keeps happening, run fewer of those agents at once.

### `(killed: the machine it runs on may be out of memory)`

The CLI was killed rather than answering: out of memory, or a crash signal. humanize waits a
moment, reopens it and tries once more. If it keeps happening, free memory or run fewer agents.

### `(dropped)`

The connection to the CLI or its service was lost. humanize reopens it and resumes the same
conversation. Nothing to do unless it keeps happening.

### `the watchdog stopped this turn: claude is idle and has said nothing for 903s`

The CLI was still running but had gone silent, so humanize ended the turn. It fails like any
other turn and is retried the same way. The words before `has said nothing` say what it saw:
`is gone` is a crash to look for in the CLI's own log, `is stopped` means something suspended
it, and `is idle` means it was waiting on something that never answered.

humanize looks at a turn after 15 minutes of complete silence, 6 for DeepSeek Harness, and ends
it unless the CLI is visibly busy. If your turns really go quiet for longer, give them more
room, in seconds, or `0` to turn this off:

```sh
HUMANIZE_WATCHDOG=3600 hmz
```

### `codex: this machine will not run an agent at bypass, so it runs at auto, where what it asks for is granted` {#codex-this-machine-will-not-run-an-agent-at-bypass-so-it-runs-at-auto}

A note, not a failure. This Codex has requirements set by whoever manages it, an enterprise
policy or the machine's own, and they forbid full access. So the agent runs one
[permission](/user/permissions) rung down, at `auto`: Codex asks before it reaches past the
workspace, and humanize says yes. The work goes on.

## Exporting a run

### `… · 0 sessions, 0 slices` {#_0-sessions-0-slices}

[**export it**](/user/export) in `/epics` wrote the archive, but its trace holds nothing. In
order of likelihood:

1. **The run ended before its first turn.** `/epics` says how many sessions each run opened.
2. **The agent was cursor-agent.** humanize cannot read its sessions into a trace. The rest of
   the archive is still there.
3. **The CLI keeps its logs somewhere else now.** Start `hmz` with the same home variables the
   run had, such as `CLAUDE_CONFIG_DIR`, `CODEX_HOME` or `KIMI_CODE_HOME`.

## Remote machines and containers

These come from an agent whose work lands on another machine: an `ssh@` environment given with
`-e`, a container, or a [remote execution](/user/remote-execution) target.

### `could not reach build-box over ssh: …` {#the-target-cannot-be-reached}

Run `ssh build-box` yourself first. humanize uses your own ssh config, agent and keys, and adds
nothing. `there is no ssh host build-box: …` means ssh could not resolve the name at all.
[Reference › Remote execution](/reference/remote-execution) has a check that walks the whole
path to a target without starting an agent.

### `humanize: no python 3.12 or newer on this machine; looked for: …`

The target needs Python 3.12 or newer, and it has none. Install one there. It does not have to
be on the `PATH`: the message lists every place humanize looked.

### `could not install humanize on docker://…: … is not running; the container said: …`

humanize copies itself to a target before the agent starts, and this target refused. What it
said follows the colon. A container that is `not running` stopped as soon as it started, which
is what an image with no Python 3.12 or newer does: its last words say where it looked.

### `humanize intercepts syscalls with a Linux seccomp filter and a ptrace supervisor, and this host is 'darwin'. …`

An agent whose work lands elsewhere can only run on Linux. On a Mac, run humanize inside a
Linux virtual machine: Docker Desktop, colima and lima each give you one, on Intel and Apple
silicon alike. The Mac can still be a target for an agent running somewhere else.

### `humanize has a register map for aarch64, x86_64; this host reports 'riscv64', …`

An agent whose work lands elsewhere must run on an x86-64 or aarch64 Linux machine. Run it from
one of those. The target can be any architecture, this machine included.

### `the target speaks protocol …, this humanize speaks …`

The two ends are different versions of humanize, usually a target that was left listening
before you upgraded. Start it again with the humanize you have now.

### `unsupported target '…'; expected ssh://HOST, docker://CONTAINER, tcp://HOST:PORT, peer://TICKET@HOST:PORT or local[:PATH]`

humanize cannot read the target. Write it in one of the forms the message lists. `peer://` is
one humanize writes for itself; you do not type it.

### `refusing to listen on a non-loopback address without --token`

A target listening on the network is a shell on that machine for anyone who reaches it. Give
`--token` a real secret, or use `ssh://` or `docker://`, which open no port at all.

### `… already contains files and is not an humanize mirror. …`

The agent works in a local mirror of the target, and humanize replaces a mirror's contents with
the target's. So it will not take a directory holding other files, or one mirroring another
target (`… mirrors ssh://a, not ssh://b. …`). Use an empty directory, or pass `--force` if you
mean it.

### A command ran against stale files

Only file contents reach the target. A permission change made through a file that is already
open does not, and ownership, device nodes and extended attributes never do. The full list is
in [Reference › Remote execution](/reference/remote-execution).

### `could not start a container of python:3.12: …`

Docker's own words follow. The usual causes are no Docker daemon to reach, an image that is not
pulled, and an image with no shell in it.

### `no directory to give the container`

The workspace directory does not exist. Create it first. humanize refuses rather than letting
Docker create it, owned by root.

### Containers left behind after a run was killed

Every container humanize starts is labelled with your uid, so this removes yours and nobody
else's:

```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```

## Writing a flow

For whoever wrote the flow. See [Writing a flow](/weaver/writing-a-flow).

### `… defines no flow`

Nothing in the module is decorated with `@flow`. A function is a flow because it is decorated,
not because of its name.

### ``… a flow is an `async def` function``

The function under `@flow` is a plain `def`. Make it `async def`.

### `Agents.reviewer: 'Reviewer' cannot be resolved: …`

The role's type is imported only under `if TYPE_CHECKING:`. humanize reads the roles when the
flow runs, so import the type at runtime.

## Still stuck

- Turn on [`/details`](/user/details) to see everything the agents do, and press <kbd>esc</kbd>
  for [`/monitor`](/user/monitor) to see which one is doing what.
- [Export the run](/user/export) from `/epics` and attach the archive to an issue, with the
  output of `hmz --version`. Credentials are struck out, but your task and the agents'
  transcripts are in it.
- Ask in [issues](https://github.com/humanfia/humanize/issues).
