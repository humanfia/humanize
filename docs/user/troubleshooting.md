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

Find the message you got, or the thing you saw, and what to do about it. Paste the message into
the box to see only the entries that match, or scan the groups below: they are in the order you
meet them, from starting a flow to writing one.

Every entry says the same four things: the **symptom** you see, its **cause**, the **fix**, and
how to **verify** that the fix worked. A message quoted here with `…` or a name such as
`build-box` matches yours with your own names in those places.

<TroubleFilter />

## Starting a flow

`hmz exec` prints these after `hmz exec: error:` and exits with status 2. Nothing has run. At
the prompt, the same words follow `hmz:`. Every one of them is checked before the first turn,
so trying a line by hand takes a second: see [Run it
unattended](/user/unattended#check-the-line-before-you-schedule-it).

### `rlar needs an agent for 'actor', 'reviewer'; specify each with -a ROLE=CLI/MODEL:EFFORT` {#rlar-needs-an-agent-for-actor-reviewer-give-each-with-a-role-cli-model-effort}

**Symptom.** `hmz exec` refuses the line, naming the roles left empty.

**Cause.** The flow has agent roles that nothing on the line fills.

**Fix.** Give one `-a` per role, named after the role:

```sh
hmz exec -f rlar -a actor=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high \
    -b cost=20 "fix the build"
```

**Verify.** The line gets past the check and the first agent starts working.

### `ralph_loop has no agent role 'builder'; available roles are 'agent'` {#ralph-loop-has-no-agent-role-builder-its-agent-roles-are-agent}

**Symptom.** `hmz exec` refuses an `-a`, and lists the roles the flow does have.

**Cause.** The line names a role the flow does not have: a typo, or another flow's role.

**Fix.** Use a name from the list at the end of the message. `chat` has `assistant`,
`ralph_loop` has `agent`, and `rlar` has `actor` and `reviewer`. Each flow's page lists its
roles.

**Verify.** The line is refused for nothing, or for the next thing it is missing.

### `…: 'human' is assigned automatically by the runtime and cannot be set with -a` {#human-is-filled-by-the-runtime-whoever-is-outside-the-run-and-is-not-given-with-a}

**Symptom.** `hmz exec` refuses an `-a` for a role such as `human`.

**Cause.** That role is the person outside the run, and humanize fills it.
`… is the workspace the run started in and cannot be set with -e` is the same for an
environment: it is the directory you ran `hmz exec` in.

**Fix.** Take the role off the line. For the workspace, run `hmz exec` from the directory you
want the agents to work in.

**Verify.** The line runs without it.

### `-a 'claude/claude-opus-5:high': expected <role>=<harness>[@<provider>]/<model>[:<effort>]`

**Symptom.** `hmz exec` prints its usage, then this.

**Cause.** The agent has no role in front of it.

**Fix.** Say which role it fills: `-a agent=claude/claude-opus-5:high`.

**Verify.** The usage line is gone.

### `-a 'agent=claude:high': expected [NAME=]CLI[@PROVIDER]/MODEL[:EFFORT]`

**Symptom.** `hmz exec` prints its usage, then this.

**Cause.** A part is missing, or the CLI is not one humanize knows. The CLI and the model are
required; the effort may be left off, which asks for none.

**Fix.** Write the CLI, a `/` and the model, and the effort after a `:` if you want one. `auto`
is the effort that asks for none:

```sh
-a agent=claude/claude-opus-5:high
-a agent=opencode/anthropic/claude-opus-5:auto   # a model may hold slashes
```

**Verify.** The usage line is gone. Try a spec in the reader on [Run it
unattended](/user/unattended#name-an-agent-for-each-role) to see how it is read.

### `ralph_loop requires a budget: specify with -b duration=...,cost=...,output_tokens=...` {#ralph-loop-a-run-is-given-a-budget-b-duration-cost-output-tokens-and-this-one-was-given-none}

**Symptom.** `hmz exec` refuses the line before anything runs.

**Cause.** Every flow except `chat` runs under a budget, and the line gives none.

**Fix.** Give it one with `-b`:

```sh
-b cost=20
-b duration=6h,output_tokens=10m
```

See [Every run has a budget](/features/allowances) for what each key stops.

**Verify.** The run starts. When it later reaches a limit, it ends with
`hmz exec: stopped -- …` and exit status 0.

### `agent=claude/claude-opus-5:ultra: claude cannot be asked to think at 'ultra'; expected one of ultracode, max, xhigh, high, medium, low`

**Symptom.** `hmz exec` refuses the agent, and lists the efforts its CLI takes.

**Cause.** That effort is not on the backend's ladder.

**Fix.** Pick one from the list, or `auto` for none. A CLI you added on [the Accounts page of
`/settings`](/user/settings#accounts) takes any effort. Every ladder is on
[Efforts](/user/efforts).

**Verify.** The line gets past the check.

### `cursor-agent lists no gpt-5.2-medium: this account runs gpt-5.2 as gpt-5.2-low, gpt-5.2-high`

**Symptom.** A Cursor Agent role is refused, with the ids this account offers.

**Cause.** cursor-agent writes the effort into the model's id, and this account does not offer
the model at that effort.

**Fix.** Pick an effort the message lists: here `gpt-5.2:low` or `gpt-5.2:high`.

**Verify.** The line gets past the check.

### `…: 'reviewer' needs GoalCommandAgentMixin, which pi does not support` {#reviewer-needs-goalcommandagentmixin-which-pi-does-not-do}

**Symptom.** `hmz exec` refuses a CLI for one role.

**Cause.** The role asks for something that CLI cannot do: pursue a goal, be steered, or answer
a hook.

**Fix.** Give the role a CLI that can. [Reference › Flows](/reference/flows) has the table of
which CLI does what, and the agent sheet at `/flow` offers only the CLIs that can.

**Verify.** The line gets past the check.

### `…: 'builder' requires claude, but got codex` {#builder-is-claude-and-codex-was-given}

**Symptom.** `hmz exec` refuses a CLI for one role, naming the one it wants.

**Cause.** The role is written for one CLI only.

**Fix.** Give it that CLI.

**Verify.** The line gets past the check.

### `nosuchflow: no flow is called 'nosuchflow', and it is not a path`

**Symptom.** `hmz exec` cannot find the flow `-f` names.

**Cause.** Nothing offers a flow by that name. A name is looked up in this project's
`.humanize/flows`, then in `~/.humanize/flows`, then among humanize's own flows and every
[flowverse](/weaver/flowverses) fetched here. Anything else is read as a path.

**Fix.** Check the spelling against the names `/flow` offers, or give the flow's path, or its
repository as `git+https://…#<flow>`.

**Verify.** The line is refused for nothing, or for what the flow itself needs.

### `ralph_loop: the official flowverse has not been fetched yet -- open the flowverses page of /settings and fetch it from its own sheet`

**Symptom.** `hmz exec` refuses a flow by name, on a machine that has not fetched the official
flowverse. Until it is fetched, any name that nothing else offers gets this message, even one
that is misspelled.

**Cause.** The flowverse has not been downloaded yet. `hmz` fetches flowverses in the
background every time it starts, and `hmz exec` never does.

**Fix.** Open `hmz` once and let it fetch, or fetch now: type `/settings flowverses`, open the
flowverse, and choose `fetch`. On a machine that never opens `hmz`, such as a CI runner, name
the flow by its repository:

```sh
-f 'git+https://github.com/humanfia/flowverse@main#ralph_loop'
```

**Verify.** The flowverse's sheet says it was fetched, and the line gets past the check.

### `… holds gen-idea, gen-plan, rlcr and none is called 'humanize1'; name one as humanize1:<flow>`

**Symptom.** `-f` names a directory of flows, and `hmz exec` asks which one.

**Cause.** The directory holds several flows, and none is named after it.

**Fix.** Say which one you mean: `-f humanize1:gen-plan`. A name that is not among them gets
`… holds no flow called '…'; it holds …`, with the list to choose from.

**Verify.** The line gets past the check.

### `…: 1 validation error for Params`

**Symptom.** `hmz exec` refuses the `-p`, with the lines after it naming the key:

```
hmz exec: error: chat:chat: 1 validation error for Params
foo
  Extra inputs are not permitted [type=extra_forbidden, input_value=1, input_type=int]
```

**Cause.** `-p` gave a key the flow does not take, or a value its type cannot read.

**Fix.** Fix the value, or leave the key off to get its default. The flow's page lists its
params.

**Verify.** The line gets past the check.

### `hmz exec: error: unrecognized arguments: -H …`

**Symptom.** `hmz exec` prints its usage, then this.

**Cause.** `hmz exec` takes no `-H`: where each agent's CLI runs is not said on the line. It
is the affinity of the runtime the work is on, saved with the host or the daemon.

**Fix.** Drop `-H`. For `-H local`, save the host or daemon with `local` in its `harness runs
on` row on [the runtimes page](/user/settings#runtimes); for `-H env`, with `self`; for
`-H standalone:…`, with that other saved runtime, as `ssh:gpu-box`. See [Where the agent
runs](/user/remote-execution#where-the-agent-runs).

**Verify.** The usage line is gone.

### `build-box: 'somewhere' is not where a harness runs: self, local or <ssh|docker>:<runtime name>`

**Symptom.** Saving a host or a daemon on the runtimes page, or `Hmz().runtimes.new(…)`, is
refused with this, or with `… is in its affinity twice` or `… its affinity names itself; self
is its own machine`.

**Cause.** Its affinity, the `harness runs on` row, holds an entry that is none of `self`,
`local` and `<backend>:<name>`, names one twice, or names the runtime itself.

**Fix.** Write each entry as one of those, apart by commas, as `self, docker:gpubox, local`.
For the runtime itself, write `self`.

**Verify.** It saves.

### `ralph_loop has no run to resume here: none saved any progress` {#ralph-loop-has-no-run-here-to-pick-up-none-got-as-far-as-writing-anything-down}

**Symptom.** A `--resume` line is refused.

**Cause.** `--resume` found no run of this flow in this directory that saved anything to pick up
from. The runs are kept on the machine that ran them, so a fresh CI runner never has one.
`… does not support resuming, so there is no run to resume` means the flow cannot be resumed at
all.

**Fix.** Run the line without `--resume`, from the directory the earlier run started in if
there was one. See [Picking a run up](/user/resuming).

**Verify.** `/epics` in that directory lists the run as **resumable**.

### `hmz exec: nobody lists a price for my-model, so cost=5 cannot stop what it spends`

**Symptom.** A warning before the first turn. The run goes ahead.

**Cause.** humanize knows no price for that model, so a `cost` cap never fills. It happens for a
model the price list does not have, and for every model on a machine that has never opened
`hmz`, which is what fetches the list.

**Fix.** Cap something it can count as well:

```sh
-b cost=5,output_tokens=2m
```

**Verify.** The warning is still printed, but the run now stops at the other limit, with
`hmz exec: stopped -- … its budget's output tokens are spent`.

### `the following arguments are required: task`

**Symptom.** `hmz exec` prints its usage, then this, although the line has a task.

**Cause.** The task starts with a dash, so it was read as a flag.

**Fix.** Put `--` before it:

```sh
hmz exec -f chat -a assistant=claude/claude-opus-5:high -- "--force is not a flag here"
```

**Verify.** The run starts.

## At the prompt

The interface prints most of these in red, after `hmz:`.

### `no coding agent is installed` {#no-coding-agent-is-installed-here}

**Symptom.** You typed a task, and nothing started.

**Cause.** The flow has no agent to run it on. humanize looks for a coding agent CLI on your
`PATH` and in the directories installers use, such as `~/.local/bin` and `/usr/local/bin`, and
found none.

**Fix.** Check what it can find:

```sh
command -v agy claude codex cursor-agent grok kimi mcode mimo opencode pi qwen
```

Install one from [Installation](/user/installation), then open `hmz` again. If one is
installed, open `/flow` and give the role a CLI and a model.

**Verify.** `command -v` prints a path, and the task starts a turn.

### `no such flow: ralph`

**Symptom.** A `$` line is refused.

**Cause.** A `$` line names a flow by the name it is offered under:

| Flow | Typed as |
| --- | --- |
| humanize's own, and the official flowverse's | `$ralph_loop` |
| this project's, in `.humanize/flows` | `$local/twice` |
| yours, in `~/.humanize/flows` | `$user/twice` |
| another flowverse's | `$<flowverse>/name` |

**Fix.** Type `$` and let [completion](/user/completion) offer the names. A flowverse not
fetched yet offers nothing: type `/settings flowverses`, open it, and choose `fetch`.

**Verify.** The flow's `/flow` sheet opens, or it starts.

### `no such command: /foo`

**Symptom.** A `/` line is refused.

**Cause.** There is no command by that name. There are ten, listed in
[Reference › TUI](/reference/tui).

**Fix.** Type `/` alone: the list above the prompt shows the commands that would do something
now.

**Verify.** The command runs.

### `no flow is running`, `the flow is already stopping` {#nothing-to-stop}

**Symptom.** A `/stop` did nothing but say this.

**Cause.** There was nothing to stop. `/stop` is listed only while a flow runs and has not
already been told to stop; typed out otherwise, it says why it did nothing. The same goes for
every command the list leaves out: `/resume` with a flow going or nothing here to carry on,
`/btw` with nobody to ask.

**Fix.** Nothing to do. Wait for a flow that is stopping to finish its turn.

**Verify.** The status line no longer shows the flow running.

### `cannot choose a flow while one is running` {#a-flow-is-running-no-choosing-a-flow}

**Symptom.** A `/flow <name>` or a `$` line is refused while a flow runs.
`a flow is already running` has the same cause.

**Cause.** Starting another flow would stop this one, so humanize refuses.

**Fix.** Stop it first with [`/stop`](/user/stopping), or <kbd>ctrl+c</kbd> twice on an empty
line. `/flow` on its own still opens, on the roles of the flow that is running.

**Verify.** Once the run has stopped, the same line opens or starts the flow.

### `reviewer is not configured yet` {#reviewer-is-not-set-up-yet}

**Symptom.** `/flow` will not save.

**Cause.** The role has no CLI and model yet. `this flow requires a budget: set the budget
first` is the same for the budget.

**Fix.** Open the role's row, choose a CLI and a model, and save the agent. For the budget,
open the `budget` row and set at least one limit.

**Verify.** `save` closes the sheet, and the row shows what fills the role.

### `flow not set up; nothing started` {#nothing-was-set-up-so-nothing-was-started}

**Symptom.** A `$` line opened `/flow`, and when you left it nothing ran.

**Cause.** The flow has never been set up in this directory, and you left the sheet without
saving.

**Fix.** Type the line again, fill every role, and choose `save` this time.

**Verify.** The flow starts on the task.

### `expected 'on' or 'off', not 'yes'` {#say-on-or-off-not-yes}

**Symptom.** An `/afk` or a `/claim` with a word after it is refused.

**Cause.** Given nothing, they switch over. Given a word, they take only `on` or `off`.

**Fix.** Type `/afk`, `/afk on` or `/afk off`.

**Verify.** The status line starts with `afk` while you are away, and does not once you are
back.

### `reviewer is bob@tui's to answer, not yours`

**Symptom.** A line typed on an outworlder's transcript is refused.

**Cause.** Another interface reading the same run, or a program on the SDK, has
[claimed](/reference/tui#several-people-on-one-run) that outworlder: what it asks is theirs
alone to answer. `reviewer is bob@tui's` says the same about an answer, and
`reviewer is bob@tui's: cannot claim it` or `…: cannot say whether it is away` about a `/claim`
or an `/afk` typed on its transcript, where neither is offered while somebody else holds it.
Lines said to the agents are never refused this way.

**Fix.** Ask them to `/claim off`, or wait for them to leave, which gives it back.

**Verify.** The outworlder's transcript no longer says `<name>'s to answer` under its question.

### `already answered by alice@tui`

**Symptom.** Your answer to a question was refused.

**Cause.** Nobody had claimed that outworlder, so its question went to whoever answered first,
and that was somebody else.

**Fix.** Nothing to do. If their answer was wrong, say so to the agent on its next turn.

**Verify.** Their answer is in the transcript, marked ` · by alice@tui`.

### `hmz: the runs in … are held by an older humanize (pid …); stop it with that version`

**Symptom.** `hmz` will not open in a directory after an upgrade.

**Cause.** A daemon an older humanize started still holds this directory. It held its run on a
pseudoterminal, which this version cannot read.

**Fix.** Open it with that version and stop it, or end the process named, then run `hmz`
again.

**Verify.** `hmz` opens.

### `hmz: fell too far behind; open it again` {#hmz-too-far-behind-attach-again}

**Symptom.** The interface closed with this.

**Cause.** It stopped taking what the host sent until it was a whole run behind, and was let go
of. The run is untouched.

**Fix.** Run `hmz` again in the same directory.

**Verify.** It opens on the run, read from the top.

### `/btw requires a coding agent` {#btw-needs-a-coding-agent-to-ask}

**Symptom.** A [`/btw`](/user/btw) in the view of every agent is refused.

**Cause.** There, `/btw` asks the btw agent. None is set in `/settings`, and no flow is set up to
copy one from. `btw is still answering the last question` means the side conversation has not
answered yet.

**Fix.** Choose a flow, or set the **/btw agent** on the Settings page of `/settings`. For the
second message, wait for the answer.

**Verify.** `/btw` opens the side conversation.

### A line I typed did not reach the agent

**Symptom.** A line you typed stays pinned above the prompt, or ends in the transcript marked
`never sent`.

**Cause.** A typed line goes to the agent you are reading. When you are reading all of them, it
goes to whichever has a turn open. Until that agent takes it, the line stays pinned:

- **Between turns**, it waits for the next turn to start.
- **Several lines** go one at a time, so the later ones wait a turn or two.
- **When the flow ends**, lines nobody took move into the transcript marked `never sent`.
- **Somebody else's lines** wait beside yours, marked ` · by <name>`, where another interface
  reads the same run.
- **On an outworlder's transcript** a line answers its question and is not said to an agent;
  with nothing asked, it is refused.

**Fix.** To send it to another agent, press <kbd>shift+tab</kbd> to read that one first. See
[Steering](/user/steering).

**Verify.** The pinned line goes, and the agent's transcript shows it taken.

### The screen is unreadable in my terminal

**Symptom.** Text is hard or impossible to read against its background.

**Cause.** The interface draws in your terminal's own 16 colours, so the usual cause is a
terminal theme with too little contrast between two of them.

**Fix.** Change the terminal's theme, or run `NO_COLOR=1 hmz` for no colour at all, or
`TEXTUAL_THEME=textual-dark hmz` for a fixed palette.

**Verify.** The transcript and the status line read clearly.

### The token count sits still, then jumps

**Symptom.** The [readout](/user/tally) above the prompt does not move during a turn, then
jumps when it ends.

**Cause.** Some CLIs report tokens as each request to the model comes back; the others only at
the end of each turn. An agent working on another machine reports at the end of each turn too.
[Cost and rate › When it moves](/user/tally#when-it-moves) lists which.

**Fix.** Nothing to do: the figure is right once the turn ends.

**Verify.** The count catches up at the turn's `✻` line.

## Agents, accounts and models

A failed turn ends with what the CLI said, then the kind of failure in brackets:

```text{2}
Command '['claude', …]' returned non-zero exit status 1. 429 rate limit exceeded
(throttled: this account has spent its quota; another one, or a wait, is what answers it)
```

humanize waits, retries, or moves to the next account or [fallback](/user/settings#fallback) by
itself, depending on the kind. The entries below say what is left for you to do. A failure with
no brackets is one humanize did not recognise, and it is retried as that place says. Under
`hmz exec`, a failure nothing recovers from ends the run with a traceback whose last line is
the same message, and exit status 1.

### The agent fails on its first turn

**Symptom.** The first turn fails, with no bracket humanize recognises, or with the CLI's own
complaint about the model.

**Cause.** Usually a model that account cannot run. humanize checks the effort before it starts,
but only the CLI knows which models your account may use.

**Fix.** Run the CLI yourself with the same model, under the same account, and fix what it
says. Then choose a model it runs.

**Verify.** The CLI answers on its own, and the next turn under humanize does too.

### `(throttled: this account has spent its quota; another one, or a wait, is what answers it)`

**Symptom.** A turn fails with this bracket, and the run pauses or moves to another account.

**Cause.** The account hit its rate limit. humanize waits, tries once more, then moves to the
next account of that CLI.

**Fix.** Give it one to move to: add an account on [the Accounts page of
`/settings`](/user/settings#accounts) and set what it falls back to on the Fallback page.

**Verify.** The next time it happens, the transcript says the turn moved to the other account.

### `(refused: that account needs signing in again)`

**Symptom.** A turn fails with this bracket.

**Cause.** The credential was refused, or the login expired. humanize moves straight on to the
next account.

A login that renews itself (Codex with ChatGPT, Claude Code with a subscription) is also
revoked, with `refresh token was revoked`, when two copies of it renewed apart: a copy of
`~/.codex/auth.json` or `~/.claude/.credentials.json` put in a container, on another machine or
in a test's temporary home. humanize never makes one, but a copy made by hand does.

**Fix.** Sign the account back in, with the CLI's own login for the account this machine uses:

```sh
claude auth login
codex login
```

For an account humanize keeps, type `/settings accounts`, choose the account, and pick **sign
in again**. Then delete every copy of the file that was made, so it cannot happen again: on
another machine, sign its CLI in there instead.

**Verify.** The CLI answers when you run it yourself, and the next turn goes through.

### `… this account signs in with a token that refreshes itself, and another turn is using it …` {#this-account-signs-in-with-a-token-that-refreshes-itself}

**Symptom.** A turn fails with this line, or with
`… and a copy of it is out on another machine for a turn there …`, then with
`(contended: …)` once its three tries are spent.

**Cause.** The role's `@account` is a login that renews itself, and the CLI of one of the turns
using it runs on another machine (`self` in the runtime's affinity, or no affinity and the
CLI there). Two copies renewing
apart get the login revoked, so a copy goes to another machine only while no other turn is
using the account, and comes back renewed before any other turn may use it again. Turns on this
machine share the one file and run side by side.

**Fix.** One of:

- give the roles that run at the same time an account each, or an account signed in with a key;
- put `local` first in the affinity of the runtime those roles work on, where every turn uses
  the one file in place;
- sign the CLI in on that machine and drop the `@account`.

**Verify.** The next turn starts. See
[Providers › A sign-in that refreshes itself](/reference/providers#a-sign-in-that-refreshes-itself).

### `(unlisted: … this account was last offered …)`

**Symptom.** A turn fails because the account may not use that model. The bracket says whether
humanize's list of this account's models is out of date:

```
(unlisted: the 3 models this account was last offered (asked 2026-09-10) still list it, so
that list is stale; the "check again" row under its models checks again)
```

**Cause.** The account is signed in, but may not use that model. humanize never asks an account
again on its own.

**Fix.** In `/flow`, open the agent, open its `model` row, and choose `check again` to ask the
CLI what this account runs now. Then choose one of those.

**Verify.** The model is in the list `check again` brings back, and the next turn goes through.

### `(retired: the model is gone or was never this account's; another place is what answers it)`

**Symptom.** A turn fails with this bracket, and goes straight to the next fallback.

**Cause.** The CLI says there is no such model. No account of that CLI has it.

**Fix.** Choose another model: `check again` under the agent's `model` row shows what the CLI
runs.

**Verify.** The next turn goes through on the new model.

### `(missing: npm i -g @anthropic-ai/claude-code)`

**Symptom.** A turn fails with this bracket, or `… is not installed here: …`.

**Cause.** The CLI is not installed where the agent runs, or would not start. The bracket holds
the command that installs it.

**Fix.** Run that command, or see [Installation](/user/installation).

**Verify.** `command -v claude` (or the CLI's own name) prints a path.

### `(sandboxed: this machine will not let it sandbox itself; run it without one, or somewhere it can)`

**Symptom.** A turn fails with this bracket, usually with `bwrap: … Permission denied` just
before.

**Cause.** The CLI could not start its own sandbox. An unprivileged container is the common
cause.

**Fix.** Run it where the kernel allows unprivileged user namespaces, or give the role another
CLI.

**Verify.** The turn starts.

### `(unmirrored: that path cannot be made here; …)`

**Symptom.** A turn fails with this bracket, after
`cannot keep the local copy of the work at <path>: Permission denied: …`.

**Cause.** The agent's CLI runs here and works in a copy of another machine's directory, kept
at that directory's own path for an `ssh` environment, and that path cannot be made on this
machine: a parent you may not write, or a file where a directory should be. No account was
refused, and signing in again changes nothing.

**Fix.** Use a workdir whose path you can create here, or run the CLI on that machine with
`self` in the affinity of the runtime the work is on. See [The path is taken here too](/user/remote-execution#the-path-is-taken-here-too).

**Verify.** The turn starts.

### `(contended: two turns of it are sharing one database)`

**Symptom.** A turn of opencode or mimocode fails with this bracket.

**Cause.** Two turns wrote to the CLI's one database at once and got `database is locked`.
humanize retries three times, a second apart, which nearly always clears it. A turn of any CLI
whose account is a login that renews itself can end here too, when another turn holds it the
other way round: see
[the entry above](#this-account-signs-in-with-a-token-that-refreshes-itself).

**Fix.** If it keeps happening, run fewer of those agents at once.

**Verify.** The bracket stops appearing.

### `(killed: the machine it runs on may be out of memory)`

**Symptom.** A turn fails with this bracket.

**Cause.** The CLI was killed rather than answering: out of memory, or a crash signal.
humanize waits a moment, reopens it and tries once more.

**Fix.** If it keeps happening, free memory or run fewer agents.

**Verify.** `free -h` shows room, and the bracket stops appearing.

### `(dropped)`

**Symptom.** A turn fails with this bracket, then carries on.

**Cause.** The connection to the CLI or its service was lost. humanize reopens it and resumes
the same conversation.

**Fix.** Nothing, unless it keeps happening: then check this machine's network.

**Verify.** The next turn goes through.

### `the watchdog stopped this turn: claude is idle and has said nothing for 903s`

**Symptom.** A turn is ended with this, and retried like any failed turn.

**Cause.** The CLI was still running but had gone silent, so humanize ended the turn. The words
before `has said nothing` say what it saw: `is gone` is a crash to look for in the CLI's own
log, `is stopped` means something suspended it, and `is idle` means it was waiting on
something that never answered. humanize looks at a turn after 15 minutes of complete silence,
6 for DeepSeek Harness, and ends it unless the CLI is visibly busy.

**Fix.** If your turns really go quiet for longer, give them more room, in seconds, or `0` to
turn this off:

```sh
HUMANIZE_WATCHDOG=3600 hmz
```

**Verify.** Long quiet turns finish instead of being stopped.

### `codex: this machine will not run an agent at bypass, so it runs at auto, where what it asks for is granted` {#codex-this-machine-will-not-run-an-agent-at-bypass-so-it-runs-at-auto}

**Symptom.** A note when a Codex agent starts. The work goes on.

**Cause.** This Codex has requirements set by whoever manages it, an enterprise policy or the
machine's own, and they forbid full access. So the agent runs one
[permission](/user/permissions) rung down, at `auto`: Codex asks before it reaches past the
workspace, and humanize says yes.

**Fix.** Nothing to do.

**Verify.** The agent's turns go through as usual.

### `claude: this account will not run an agent at bypass, so it runs at acceptEdits, where what it asks for is granted` {#claude-this-account-will-not-run-an-agent-at-bypass-so-it-runs-at-acceptedits}

**Symptom.** A note during a Claude Code agent's first turn. The work goes on.

**Cause.** The Claude account's managed settings carry `"disableBypassPermissionsMode":
"disable"`, or Claude runs as root, so Claude will not run at `bypassPermissions`. The agent
runs at `acceptEdits` instead: Claude asks before what that mode does not cover, and humanize
says yes.

**Fix.** Nothing to do.

**Verify.** The agent's turns go through as usual.

### `… cannot be held to its permission on this machine: it does not enforce it natively, and fencing it from outside needs …`

**Symptom.** A role is refused before its first turn (`HarnessSandboxed`).

**Cause.** The role's [permission](/user/permissions) is narrower than everything, and this
machine cannot hold it: a Linux kernel older than 5.13 or booted without Landlock, or a Mac
where humanize itself runs inside another sandbox (an agent's own, say), which cannot start
Seatbelt again. Cutting the network needs Linux 6.7 or later. A `cursor-agent` or `mcode` role whose `online`
is `NONE` is refused on any machine, since its web search runs on its vendor's servers.

**Fix.** Run humanize on a Linux machine with Landlock, or on a Mac outside any other
sandbox, or give that role a CLI and a permission this machine can hold. The message says
what is needed.

**Verify.** The role's first turn starts.

## Exporting a run

### `… · 0 sessions, 0 slices` {#_0-sessions-0-slices}

**Symptom.** [**export run**](/user/export) in `/epics` wrote the archive, but its trace holds
nothing.

**Cause.** In order of likelihood:

1. **The run ended before its first turn.** `/epics` says how many sessions each run opened.
2. **The agent was cursor-agent.** humanize cannot read its sessions into a trace. The rest of
   the archive is still there.
3. **The run's sessions were moved or deleted** since it ran.

**Fix.** For the first, there is nothing to trace: run again. For the second, watch a Cursor
Agent run live on [the monitor](/user/monitor) instead. For the third, restore the sessions if
you have them.

**Verify.** Exporting again reports `1 session` or more, and a count of slices.

## Remote machines and containers

These come from an agent whose work lands on another machine: an `ssh@` or `docker@`
environment given with `-e`, a container, or a [remote execution](/user/remote-execution)
target.

### `onbox needs an environment for 'box'; specify each with -e ROLE=BACKEND@RUNTIME/WORKDIR`

**Symptom.** `hmz exec` refuses the line before anything runs.

**Cause.** The flow has an environment role that nothing on the line places.

**Fix.** Say where it is, with `-e` or at `/flow`:

```sh
-e box=ssh@build-box/home/me/build/myproject
```

**Verify.** The line gets past the check.

### `ralph_loop has no environment role 'box'; available roles are none`

**Symptom.** `hmz exec` refuses an `-e`.

**Cause.** That flow only works in the directory you start it in. Most flows do.

**Fix.** Take the `-e` off, and start `hmz exec` in the project's directory; or use a flow
written for another machine, as [Remote execution](/user/remote-execution) shows.

**Verify.** The line gets past the check.

### `could not reach build-box over ssh: …` {#the-target-cannot-be-reached}

**Symptom.** The run is refused, or its first turn fails, with ssh's own words after the colon.
`there is no ssh host build-box: …` means ssh could not resolve the name at all.

**Cause.** humanize uses your own ssh config, agent and keys, and adds nothing. Whatever stops
`ssh build-box` stops it too.

**Fix.** Run `ssh build-box` yourself and fix what it says: the host name, the key, the
`known_hosts` entry. [Reference › Remote execution](/reference/remote-execution) has a check that
walks the whole path to a target without starting an agent.

**Verify.** `ssh build-box true` returns with no prompt and exit status 0.

### `the workdir /home/me/build/myproject is not there`

**Symptom.** The run is refused before any agent starts.

**Cause.** The directory `-e` names does not exist on that machine.

**Fix.** Put the project on the host at that path, or name the path it is at.

**Verify.** `ssh build-box ls /home/me/build/myproject` lists it.

### `… 'box' needs 8 GPUs, and the environment given has 0`

**Symptom.** The run is refused before any agent starts.

**Cause.** The flow asks more of the machine, in CPUs, memory or GPUs, than it has.

**Fix.** Pick a machine that has it.

**Verify.** The line gets past the check.

### `docker@gpubox has 0 of 2 GPUs free, and 'box' asks for 1 …`

**Symptom.** A `docker@` role is refused before any agent starts. The message names every
resource that is short (containers, CPUs, memory, GPUs) and which containers hold the rest.

**Cause.** The docker daemon saved as `gpubox` may hand out only so much, and running
containers of humanize's already hold it.

**Fix.** Wait for those runs to end, stop them, or give the daemon more to hand out on the
[runtimes page of `/settings`](/user/settings#runtimes). A daemon that names no GPU says
so: list its GPUs there.

**Verify.** The line gets past the check.

### `…: 'box' needs GitEnvMixin, which ssh@build-box/… does not support: GitEnvMixin needs git on the machine's PATH, and it has none`

**Symptom.** The run is refused before any agent starts.

**Cause.** The flow works with git on that machine, and the machine has no `git`.
`GitWorktreeEnvMixin` is refused the same way, and `BashEnvMixin` where the machine has no
`bash` (`… BashEnvMixin needs bash on the machine's PATH …`).

**Fix.** Install git (or bash) there.

**Verify.** `ssh build-box git --version` prints a version.

### `ssh@build-box: nowhere its affinity (self) names has room for claude's harness; the last: claude is not installed on ssh@build-box: …`

**Symptom.** `hmz exec` refuses the run with this before the flow starts, with exit status 2.
The message ends `… there, or put local in the affinity of the runtime it is on`.

**Cause.** The host's affinity puts the agent's CLI on the host (`self`) and nowhere after it,
and the host does not have it on the `PATH` its shell gives a command. With no affinity it
would have run here instead.

**Fix.** Install the CLI there, and sign it in there, with the line the message gives; or add
`local` after `self` in the host's affinity, or clear it.

**Verify.** `ssh build-box command -v claude` prints a path, and the transcript at the prompt
says `builder's harness runs on its environment's machine`.

### `… cannot fence the agent to its permission: it needs Landlock; grant the agent everything, or put local in the affinity of the runtime it is on`

**Symptom.** `hmz exec` refuses the run with this, after `nowhere its affinity (self) names has
room …`, before the flow starts. `… cannot fence the commands the agent runs there: it needs
Landlock …` is the same, for an agent whose CLI runs here.

**Cause.** The role's permission is narrower than everything, and the machine the work lands on
cannot hold it: a kernel older than 5.13 or without Landlock, or a container whose seccomp
profile refuses Landlock. Cutting the network needs Linux 6.7 or later there. A Mac target
fences with Seatbelt, but an agent supervised here (its CLI runs here, its work there) needs
Landlock on this machine too.

**Fix.** Add `local` after `self` in the runtime's affinity, move the work to a machine with
Landlock, or copy the flow and grant the role everything. Docker's default seccomp profile
allows Landlock.

**Verify.** The role's first turn starts.

### `… a fence cannot hold a harness that runs on another machine`

**Symptom.** `hmz exec` refuses the run with this, after `nowhere its affinity (ssh:gpu-box)
names has room …`, before the flow starts, with exit status 2.

**Cause.** The affinity of the runtime the work is on puts the CLI on another runtime, where
humanize cannot hold a permission narrower than everything. Only a role granted `ALL` in every
scope can run that way; any other passes it by, and nothing came after it.

**Fix.** Add `local` or `self` after it in the affinity, or copy the flow and grant the role
everything.

**Verify.** The run starts.

### `humanize: no python 3.12 or newer on this machine; looked for: …`

**Symptom.** The run fails when it first reaches the machine.

**Cause.** The target needs Python 3.12 or newer, and it has none that humanize can find. It
does not have to be on the `PATH`: the message lists every place humanize looked.

**Fix.** Install Python 3.12 or newer there.

**Verify.** One of the places the message lists now holds a `python3` that prints 3.12 or
newer for `--version`.

### `could not install humanize on docker://…: … is not running; the container said: …`

**Symptom.** A container's first turn fails with this.

**Cause.** humanize copies itself to a target before the agent starts, and this target refused.
What it said follows the colon. A container that is `not running` stopped as soon as it
started, which is what an image with no Python 3.12 or newer does: its last words say where it
looked.

**Fix.** Use an image with Python 3.12 or newer.

**Verify.** `docker run --rm <image> python3 --version` prints 3.12 or newer.

### `humanize intercepts syscalls with a Linux seccomp filter and a ptrace supervisor, and this host is 'darwin'. …`

**Symptom.** An agent whose work lands elsewhere will not start on a Mac.

**Cause.** An agent supervised here while its work lands elsewhere can only run on Linux.

**Fix.** Run humanize inside a Linux virtual machine: Docker Desktop, colima and lima each give
you one, on Intel and Apple silicon alike. The Mac can still be a target for an agent running
somewhere else.

**Verify.** The same line, run in the Linux machine, starts the agent.

### `humanize has a register map for aarch64, x86_64; this host reports 'riscv64', …`

**Symptom.** An agent whose work lands elsewhere will not start on this machine.

**Cause.** An agent supervised here while its work lands elsewhere must run on an x86-64 or
aarch64 Linux machine.

**Fix.** Run it from one of those. The target can be any architecture, this machine included.

**Verify.** The agent starts.

### `the target speaks protocol …, this humanize speaks …`

**Symptom.** The first turn on a target fails with this.

**Cause.** The two ends are different versions of humanize, usually a target that was left
listening before you upgraded.

**Fix.** Start it again with the humanize you have now.

**Verify.** The turn starts.

### `unsupported target '…'; expected ssh://HOST, docker://CONTAINER[@ENDPOINT], tcp://HOST:PORT, peer://TICKET@HOST:PORT or local[:PATH]`

**Symptom.** A target is refused.

**Cause.** humanize cannot read the target as written.

**Fix.** Write it in one of the forms the message lists. `peer://` is one humanize writes for
itself; you do not type it.

**Verify.** The target is accepted.

### `unsupported docker endpoint '…'; expected local, unix:///PATH, tcp://HOST:PORT[?tls=DIR], ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...] or context:NAME`

**Symptom.** A docker daemon is refused.

**Cause.** The daemon after a container's `@`, or in a saved docker environment's `endpoint`, is
not one humanize can read. A socket path and a `?tls=` directory must be absolute.

**Fix.** Write it in one of the forms the message lists. See
[Endpoints](/reference/machines#endpoints).

**Verify.** Saving the daemon on the runtimes page of `/settings` checks it and succeeds.

### `no directory to give the container on …`

**Symptom.** A container on a daemon elsewhere will not start.

**Cause.** The container is given the workspace at the path it has on *that* host, and that
host has no such directory.

**Fix.** Make it there, or name one it has.

**Verify.** The container starts.

### `cannot listen on a non-loopback address without --token` {#refusing-to-listen-on-a-non-loopback-address-without-token}

**Symptom.** A target will not start listening.

**Cause.** A target listening on the network is a shell on that machine for anyone who reaches
it.

**Fix.** Give `--token` a real secret, or use `ssh://` or `docker://`, which open no port at all.

**Verify.** The target listens, and an agent given the token reaches it.

### `hmz: ignoring HUMANIZE_LOG='verbose', which is not one of debug, info, warning, error`

**Symptom.** A turn on another machine, or `hmz internal anchor` run by hand, starts with this
line on stderr.

**Cause.** [`HUMANIZE_LOG`](/reference/environment#humanize-log) is set to something that is not
a log level. It is ignored, and the command logs at its default level.

**Fix.** Set it to `debug`, `info`, `warning` or `error`, or unset it.

**Verify.** The line is gone.

### `… already contains files and is not an humanize mirror. …`

**Symptom.** An agent whose work lands elsewhere will not start.

**Cause.** The agent works in a local copy of the target at the same path, and humanize replaces
a copy's contents with the target's. So it will not take a directory holding other files, or
one copying another target (`… mirrors ssh://a, not ssh://b. …`).

**Fix.** Use a path that is free on this machine, or an empty directory. Pass `--force` only if
you mean the directory to be overwritten. `self` in the runtime's affinity runs the CLI on the target and
needs no copy here. See [Remote execution](/user/remote-execution).

**Verify.** The agent starts.

### A command ran against stale files

**Symptom.** A command on the target read a file as it was, not as the agent had just left it.

**Cause.** Only file contents reach the target. A permission change made through a file that is
already open does not, and ownership, device nodes and extended attributes never do.

**Fix.** Make the change by a command run on the target instead. The full list is in
[Reference › Remote execution](/reference/remote-execution).

**Verify.** The next command sees the change.

### `could not start a container of python:3.12-slim on …: …`

**Symptom.** A container will not start. Docker's own words follow.

**Cause.** Usually no Docker daemon to reach, an image that is not pulled, or an image with no
shell in it.

**Fix.** Check `docker info` against that daemon, `docker pull` the image, or choose one with a
shell.

**Verify.** `docker run --rm <image> sh -c true` succeeds.

### `no directory to give the container`

**Symptom.** A container will not start.

**Cause.** The workspace directory does not exist. humanize refuses rather than letting Docker
create it, owned by root.

**Fix.** Create it first.

**Verify.** The container starts.

### Containers left behind after a run was killed

**Symptom.** `docker ps` lists containers from runs that are over.

**Cause.** The run was killed before it could take them down: <kbd>ctrl+c</kbd>, `kill` and a
hangup all let it take them down first, but a second <kbd>ctrl+c</kbd>, `kill -9` or a machine
that went down do not. The
next run on the same daemon takes down those whose run has gone.

**Fix.** Every container humanize starts is labelled with your uid, so this removes yours and
nobody else's:

```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```

**Verify.** `docker ps --filter label=humanize=$(id -u)` lists nothing.

## Writing a flow

For whoever wrote the flow. See [Writing a flow](/weaver/writing-a-flow).

### `… defines no flow`

**Symptom.** `-f` names your file, and nothing is found in it.

**Cause.** Nothing in the module is decorated with `@flow`. A function is a flow because it is
decorated, not because of its name.

**Fix.** Put `@flow(...)` on the function.

**Verify.** `/flow` lists it under `local/`.

### ``… a flow is an `async def` function``

**Symptom.** The flow is refused when it is loaded.

**Cause.** The function under `@flow` is a plain `def`.

**Fix.** Make it `async def`.

**Verify.** The flow loads.

### `Agents.reviewer: 'Reviewer' cannot be resolved: …`

**Symptom.** The flow is refused when it is loaded.

**Cause.** The role's type is imported only under `if TYPE_CHECKING:`. humanize reads the roles
when the flow runs.

**Fix.** Import the type at runtime.

**Verify.** The flow loads, and `/flow` shows the role.

## Still stuck

- Turn on [details](/user/settings#details) to see everything the agents do, and press
  <kbd>←</kbd> for [the monitor](/user/monitor) to see which one is doing what.
- [Export the run](/user/export) from `/epics` and attach the archive to a
  [bug report](https://github.com/humanfia/humanize/issues/new?template=bug_report.yml), with
  the output of `hmz --version`. Credentials are struck out, but your task and the agents'
  transcripts are in it.
