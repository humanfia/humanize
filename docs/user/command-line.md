---
title: The command line
description: Run a flow or a chat from a script with hmz exec and hmz chat, capture the answer, read the events as JSON, and act on the exit status.
---

# The command line

Run flows and chats from scripts, cron, and CI with two non-interactive commands. `hmz exec` runs a flow to completion as a new epic. `hmz chat start` and `hmz chat say` send one message to an agent and print the answer. Both run in the current directory, start the daemon if needed, and never wait for you at a prompt during a run or a turn.

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
hmz chat start -a claude/claude-haiku-4-5 "What does charge() do with an empty cart?"
```

`hmz chat start` starts a chat, runs one turn and exits. It takes no flow or budget. It prints `Chat <id>` as the first line on stderr so you can continue the chat later.

![A terminal: hmz chat prints the chat's id, then the agent's answer, its tokens and its time](/shots/user-command-line-chat.svg)

Send the next message with `hmz chat say`:

```sh
hmz chat say 20261121T034814.744Z-299560 "And how is it tested?"
```

In a script, read the id and the answer from one JSON document:

```sh
id=$(hmz chat start --json -a claude/claude-haiku-4-5 "What does charge() do?" | jq -r .chat)
hmz chat say --json "$id" "And how is it tested?" | jq -r .answer
```

| Command | What it does |
| --- | --- |
| `hmz chat start [-a AGENT] MESSAGE` | Start a chat and print the answer. Without `-a`, uses the directory's saved agent, or fails if none is saved. |
| `hmz chat say CHAT MESSAGE` | Send the next message to a chat and print the answer. |
| `hmz chat list` | List this directory's chats, newest first: id, state, title. |
| `hmz chat show CHAT` | Print one chat. `--json` gives its `state` for a script to poll. |
| `hmz chat stop CHAT` | Stop the turn a chat is taking. |
| `hmz chat rename`, `fork`, `archive`, `unarchive`, `delete` | Manage a chat without taking a turn. See [Organise chats](/user/manage-chats). |

| Option of `start` and `say` | What it does |
| --- | --- |
| `--json` | Print one JSON document with `chat`, `answer` and `notes` instead of text. |
| `--events` | Print each record of the turn as one JSON object per line, then that document. |
| `--detach` | Return as soon as the message is sent, and print the chat's id. |
| `--worktree` (`start`) | Start the chat in a new git worktree of this directory. |
| `-e BACKEND[@RUNTIME][/DIRECTORY]` (`start`) | Where the agent works. Move a chat later with `hmz chat move`. |
| `--permission` (`start`) | What the agent may change: `read-only`, `workspace-write` or `danger-full-access`. |

Run `hmz chat COMMAND --help` for every argument, example, JSON field and exit status of one command.

![A terminal: hmz chat list prints one line with the chat's id, its state and its title](/shots/user-command-line-chat-list.svg)

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

`hmz chat start` and `hmz chat say` run one turn, keep the chat, and exit. Run `hmz chat say` to continue it.

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
| 1 | The flow failed, or the daemon was unreachable. | The turn failed, the daemon refused the request, or a delete was not confirmed. |
| 2 | The command was refused before starting. | The command line could not be read. |
| 3 | | The daemon was unreachable. |
| 128 + N | Signal N stopped it. | Signal N ended it. |

Exhausting the budget is a normal exit. `hmz exec` prints `hmz exec: stopped -- <reason>` to stderr and exits 0.

## Good to know

No option of `hmz exec` or `hmz chat` reads from an environment variable; pass everything on the command line. The coding agent's CLI must be installed and signed in on the machine; see [Coding agents](/user/agents).

After the epic ends, `hmz exec` waits up to 60 seconds for backups to finish, then leaves a slow one and says so on stderr. Pass `--backup none` to skip them. A cost limit cannot stop a model with no listed price; `hmz exec` warns on stderr and continues.

`hmz chat say` rejects messages that match Humanize's `/` commands or a `$` flow name; run flows with `hmz exec`. The agent's own `/`, `$`, `!` and `@` lines work as in any chat; see [Commands, skills and files in a chat](/user/chat-input). For all flags, see the [CLI reference](/reference/cli). For a complete example, see [Run a flow every night in CI](/tutorials/nightly-in-ci).
