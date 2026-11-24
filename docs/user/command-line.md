---
title: The command line
description: Run a flow or one chat turn from a script with hmz exec and hmz chat, capture the answer, read the events as JSON, and act on the exit status.
---

# The command line

Run flows and chats from scripts, cron, and CI with two non-interactive commands. `hmz exec` runs a flow to completion as a new epic. `hmz chat` sends one message to an agent and prints the answer. Both run in the current directory, start the daemon if needed, and never wait for you at a prompt during a run or a turn.

![A terminal: hmz exec runs the goal flow, the agent runs the tests, answers, and the turn's tokens and time are printed](/shots/user-command-line-exec.svg)

## Run a flow

```sh
hmz exec -f goal -a worker=claude/claude-haiku-4-5 -p budget.output_tokens=20000 "Add a discount code to checkout"
```

Pass the flow, a budget, and the task. The task is a single argument; place it after `--` if it starts with a dash. Put options in any order, before or after the task. Repeat `-a`, `-e`, and `-p`, or pass comma-separated values.

| Option | What it sets | More |
| --- | --- | --- |
| `-f FLOW` | The flow: an installed name (`goal`, `@local/FLOW`), a path starting with `.`, `/` or `~`, or `git+URL#subdir`. `hmz exec` never installs a flow. | [Find and install flows](/user/flows) |
| `-a ROLE=CLI[@ACCOUNT]/MODEL[:EFFORT]` | What each agent role runs. `ROLE=NAME` assigns a virtual nous. | [Start an epic](/user/epics) |
| `-e ROLE=BACKEND[@RUNTIME][/WORKDIR]` | Where each environment role the flow declares works. A required role left out refuses the run. The flow's own workspace is always the current directory and takes no `-e`. | [Environments](/user/environments) |
| `-p KEY=VALUE` | A flow param. | [Start an epic](/user/epics) |
| `-p budget.duration=`, `-p budget.cost=`, `-p budget.output_tokens=`, `-p budget.graceful=` | What the run may spend. At least one limit is required. | [Budgets](/user/budgets) |
| `--resume` | Pick up the newest run of this flow here instead of starting over. | [Resume a run](/user/resuming) |
| `--json` | Write events to stdout as NDJSON. | Below |
| `--backup NAME` | A backup target for the epic. Repeatable. `--backup none` disables backups. | [Back up to git](/user/backups) |
| `--profile-flow`, `--profile-environment` | Sample the flow's Python or the programs the agents start into the run's trace. | [Trace a run with Exomyth](/user/tracing) |

Invalid commands fail before any agent starts, printing the reason on one line to stderr and exiting with status 2.

![A terminal: hmz exec with no budget is refused with "goal requires a budget" and the exit status is 2](/shots/user-command-line-refused.svg)

## Ask one question

```sh
hmz chat -a claude/claude-haiku-4-5 "What does charge() do with an empty cart?"
```

`hmz chat` runs one chat turn and exits. It takes no flow, budget, or `--json`. It prints `hmz chat: chat <id>` as the first line on stderr so you can continue the chat later.

![A terminal: hmz chat prints the chat's id, then the agent's answer, its tokens and its time](/shots/user-command-line-chat.svg)

| Option | What it does |
| --- | --- |
| `-a CLI[@ACCOUNT]/MODEL[:EFFORT]` | The agent. If omitted, a new chat uses the directory's saved agent, or fails if none is saved. |
| `--resume CHAT` | Send the message as the next turn of an existing chat. It keeps its agent unless you pass `-a`. |
| `--worktree` | Start the chat in a new git worktree of this directory. Cannot combine with `--resume`. |
| `-e BACKEND[@RUNTIME][/DIRECTORY]` | Where the agent works. With `--resume`, moves the chat there. |
| `--list`, `--list --archived` | List this directory's chats, newest first: id, state, title. |
| `--rename CHAT TITLE`, `--fork CHAT`, `--archive CHAT`, `--unarchive CHAT`, `--delete CHAT` | Manage a chat without taking a turn. See [Organise chats](/user/manage-chats). |
| `--yes` | Skip confirmation with `--delete`. Required in scripts: without a terminal, `--delete` alone deletes nothing and exits 1. |

![A terminal: hmz chat --list prints one line with the chat's id, the state ready and its title](/shots/user-command-line-chat-list.svg)

## Capture the answer

Redirect stdout and stderr to separate the answer from the logs in both commands.

![Diagram: hmz exec writes answers or JSON events to stdout, progress and errors to stderr, and ends with an exit status](/diagrams/user-command-line-1.svg)

**stdout** receives each turn's answer and any flow output. **stderr** receives progress: active agents, tool calls, notices, errors, and each turn's tokens and time.

```sh
hmz exec -f goal -a worker=claude/claude-haiku-4-5 -p budget.output_tokens=20000 "Add a discount code to checkout" > answer.txt 2> run.log
```

![A terminal: the run's stdout goes to answer.txt and its stderr to run.log; the exit status is 0 and answer.txt holds only the agent's answer](/shots/user-command-line-streams.svg)

When both streams go to the same terminal, Humanize prints the answer once, inline with the progress.

## Read the events as JSON

Pass `--json` to `hmz exec` to stream one JSON object per event to stdout. Any flow output goes to stderr instead.

```sh
hmz exec -f goal -a worker=claude/claude-haiku-4-5 -p budget.output_tokens=20000 --json "Add a discount code to checkout" > events.ndjson
jq -c '{kind, cli, text}' events.ndjson
```

![A terminal: jq prints the kind, cli and text of each event: begins, tool, text, result, ends](/shots/user-command-line-json.svg)

Every object has the keys `at`, `agent`, `cli`, `model`, `session`, `kind`, `text`, `whose`, `tokens`, and `spent`. See [Events and records](/reference/events) for event kinds and their meanings.

## Control colour output

Only the progress on stderr is ever coloured; stdout is always plain. These rules are checked in order and the first match wins:

1. `NO_COLOR` is set and not empty: no colour.
2. `TERM=dumb`: no colour.
3. `FORCE_COLOR` is set, not empty, and not `0`: colour.
4. stderr is a terminal: colour. Otherwise, no colour.

A redirected stderr is plain. Set `FORCE_COLOR=1` for CI logs that render colour. The live clock under a run appears only on a terminal with colour enabled.

## Handle prompts without a user

`hmz exec` marks you as away for the entire run. If the flow asks a question, Humanize answers immediately with an empty response or the form's defaults, and the run continues. See [Answer a flow's questions](/user/questions).

`hmz chat` runs one turn, keeps the chat, and exits. Pass `--resume` to continue it.

## Start an epic and come back to it

`hmz exec` stays until its epic ends. `hmz epic start` starts the same epic in the daemon and returns at once, so a script can start it, do something else, and steer it later:

```bash
hmz epic start goal 'fix the failing test' -a worker=claude/claude-haiku-4-5:low -p budget.cost=2
hmz epic status          # running, stopping or idle, and the questions waiting
hmz epic attach          # follow it; ctrl+c leaves it running
hmz epic say 'use the staging database'
hmz epic stop
```

Roles, params and the budget are written as for `hmz exec`. Unlike `hmz exec`, roles are not away: a question waits until you answer it with `hmz epic answer`, in the app or in the terminal. Pass `--away` to have nobody asked, and `--follow` to stay until the epic ends.

Each command reaches the epic of the current directory. Pass `-w DIR` for another workspace and `--slot SLOT` for an epic that is not on the workspace's own host, such as one started by `hmz exec` or with `--slot exec:`. `hmz hosts list` prints every workspace and slot, and `hmz hosts stop` closes one.

Every `hmz epic` and `hmz hosts` command takes `--json` and documents itself under `--help`. See [`hmz epic`](/reference/cli#hmz-epic).

## Stop a run with a signal

| Signal | `hmz exec` | `hmz chat` |
| --- | --- | --- |
| <kbd>ctrl+c</kbd> (SIGINT), SIGTERM, SIGHUP | Stops the epic, waits for it to end, then exits. | Detaches from the chat, leaves it running in the daemon, and exits. |
| A second <kbd>ctrl+c</kbd> | Forces the stop: closes open turns and exits immediately. | |

Both commands exit with 128 plus the signal number: 130 for SIGINT, 143 for SIGTERM, and 129 for SIGHUP.

![A terminal: hmz exec is sent SIGTERM while the agent works; it says the turn was cut off and the exit status is 143](/shots/user-command-line-signal.svg)

Signals already ignored at startup stay ignored, such as SIGHUP under `nohup`. If `hmz exec` dies any other way, the epic keeps running in the daemon. See [Stop a run](/user/stopping).

## Check the exit status

| Status | `hmz exec` | `hmz chat` |
| --- | --- | --- |
| 0 | The flow returned, or its budget ran out. | The turn finished. |
| 1 | The flow failed, or the daemon was unreachable. | The turn failed, the daemon was unreachable, or a delete was not confirmed. |
| 2 | The command was refused before starting. | The command or chat was refused. |
| 128 + N | Signal N stopped it. | Signal N ended it. |

Exhausting the budget is a normal exit. `hmz exec` prints `hmz exec: stopped -- <reason>` to stderr and exits 0.

## Good to know

No option of `hmz exec` or `hmz chat` reads from an environment variable; pass everything on the command line. The coding agent's CLI must be installed and signed in on the machine; see [Coding agents](/user/agents).

After the epic ends, `hmz exec` waits up to 60 seconds for backups to finish, then leaves a slow one and says so on stderr. Pass `--backup none` to skip them. A cost limit cannot stop a model with no listed price; `hmz exec` warns on stderr and continues.

`hmz chat` rejects messages that match Humanize's `/` commands or a `$` flow name; run flows with `hmz exec`. The agent's own `/`, `$`, `!` and `@` lines work as in any chat; see [Commands, skills and files in a chat](/user/chat-input). For all flags, see the [CLI reference](/reference/cli). For a complete example, see [Run a flow every night in CI](/tutorials/nightly-in-ci).
