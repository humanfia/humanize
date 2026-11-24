---
title: Finish your first task in the terminal
description: Install hmz, chat with a coding agent, install a flow, run it on a task under a budget, stop it and read back what it did, all from one terminal.
---

# Finish your first task in the terminal

In ten minutes, you install `hmz`, chat with a coding agent, install a flow, and run it on a task in your project. Everything happens in one terminal.

![The terminal interface as it opens: a banner, the agent it will talk to, and a prompt](/shots/tutorials-first-task-terminal-home.svg)

## What you need

- A terminal on macOS or Linux, or a WSL terminal on Windows.
- [uv](https://github.com/astral-sh/uv). Install it with `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- A project directory. This page uses `~/shop`.
- An account with one coding agent, such as Claude Code, and `npm` to install its CLI. Humanize runs that CLI under your login.

## 1. Install the CLI

Install `hmz`:

```sh
uv tool install hmz
```

Verify the installation:

```sh
hmz --version
```

![hmz --version prints the version](/shots/tutorials-first-task-terminal-version.svg)

## 2. Sign in to a coding agent

Humanize drives a coding agent CLI, called a harness. You need one. To set up Claude Code, install it and sign in:

```sh
npm i -g @anthropic-ai/claude-code
claude auth login
```

Skip this step if you already have a coding agent CLI on this machine. See [Coding agents](/user/agents) for other harnesses.

## 3. Open hmz in your project

Open your project directory and start `hmz`:

```sh
cd ~/shop
hmz
```

The terminal interface opens on a new chat. The line above the prompt shows the active agent: the harness, model, and effort. On first run, a box asks `Report errors to Humanize?`. Answer `yes` or `no`.

If the line says `No harness installed`, return to step 2. To switch agents, type `/settings workspace` and open **Chat agent**.

## 4. Chat with the agent

Type a question and press <kbd>enter</kbd>:

```text
Where is checkout handled?
```

The agent answers. A chat needs no flow or budget.

![A question is typed, the agent works, and its answer appears](/shots/tutorials-first-task-terminal-chat.svg)

## 5. Install a flow

A flow is a loop that runs agents on a task. Humanize starts with no flows installed. You install them from a flowverse, and the official flowverse is already listed.

1. Type `/flow` and press <kbd>enter</kbd>. The **Installed** page is empty and **Install more…** is highlighted.
2. Press <kbd>enter</kbd>. The **Flowverses** page lists `official`.
3. Press <kbd>enter</kbd> to view its flows.
4. Select `ralph_loop` and press <kbd>enter</kbd> to see its releases.
5. Press <kbd>enter</kbd> on the newest release. It shows `✔ installed`.
6. Press <kbd>esc</kbd> until the menu closes.

![The flow menu: Install more, the official flowverse, ralph_loop, its release, installed](/shots/tutorials-first-task-terminal-install.svg)

`ralph_loop` gives one agent the same task in a fresh session every round until its budget runs out or you stop it. The [catalogue](https://humanfia.ai/flows/) describes the other flows.

::: tip
If `official` says `not fetched`, press <kbd>tab</kbd>, select **Fetch**, and press <kbd>enter</kbd>. `hmz` fetches this index in the background each time it opens, so this only happens when that fetch has not finished or failed.
:::

## 6. Give the flow a budget

Every flow run requires a budget to know when to stop.

1. Type `/flow ralph_loop` and press <kbd>enter</kbd>. The page lists the flow's settings. The `agent` row already names an agent; press <kbd>enter</kbd> on it to choose another.
2. Select `budget` and press <kbd>enter</kbd>.
3. On `duration`, press <kbd>enter</kbd>, type `10m`, and press <kbd>enter</kbd> again.
4. Press <kbd>tab</kbd> to reach **Set**, then press <kbd>enter</kbd>. The `budget` row now reads `stops at 10m`.
5. Press <kbd>esc</kbd>. A box asks `Save?`. Press <kbd>enter</kbd> on **Save**.

![The budget is opened, set to ten minutes, and saved](/shots/tutorials-first-task-terminal-budget.svg)

The transcript shows `set up: /flow ralph_loop <task> starts it`. A budget can also limit `cost` in US dollars and `output_tokens`. The run stops at the first limit it reaches.

## 7. Start it on a task

Run the flow on a task:

```text
/flow ralph_loop Add a discount code to checkout
```

The screen switches from the chat to the flow's agent. Each round appears as the agent finishes it. This recorded run of a flow is called an epic.

![The flow's agent at work on the task, round by round](/shots/tutorials-first-task-terminal-running.svg)

## 8. Watch the monitor

With the prompt empty, press <kbd>←</kbd>. The monitor displays the epic: its state, turns taken, budget time used, a box per agent, and tokens spent.

![The monitor: the epic's state and budget, the agent's box, and the tokens it has used](/shots/tutorials-first-task-terminal-monitor.svg)

Press <kbd>→</kbd> to return to the agent's transcript.

## 9. Stop the run

Left alone, the run stops after ten minutes once the current turn finishes. To stop it now, press <kbd>ctrl+c</kbd>. The transcript says `— Press ctrl+c again to stop the flow —`. Press <kbd>ctrl+c</kbd> again within three seconds. Typing `/stop` stops the run immediately without confirmation.

![The transcript after ctrl+c twice: the flow is stopping and the open turn is cut off](/shots/tutorials-first-task-terminal-stopped.svg)

The agent's changes stay in your project.

## 10. Read the result

1. Type `/epics` and press <kbd>enter</kbd>. Every epic for this directory appears, newest first, with its flow, task, duration, and status.
2. Press <kbd>enter</kbd> on the epic, then <kbd>enter</kbd> on `Graph`.
3. Press <kbd>enter</kbd> on a session to read the task, each tool call and output, and the agent's response.

![The list of epics, with the stopped ralph_loop run](/shots/tutorials-first-task-terminal-epics.svg)

![One session read back: the task, a tool call and its output, and the agent's answer](/shots/tutorials-first-task-terminal-session.svg)

Press <kbd>esc</kbd> to back out of each page. Type `/exit` to leave `hmz`.

## What you did

- Installed `hmz` and chatted with a coding agent.
- Installed `ralph_loop` from the official flowverse.
- Set a budget and started an epic on a task.
- Watched the epic in the monitor and stopped it.
- Read the session history in `/epics`.

## Next

- [Find and install flows](/user/flows): browse other flows, update them, and add your own.
- [Budgets](/user/budgets): learn about all limit types and what happens when a run hits one.
- [Watch a run](/user/watch-a-run): see everything the monitor shows.
- [Leave a long task running overnight](/tutorials/overnight-run): close the terminal and return later.
