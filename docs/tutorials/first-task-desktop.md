---
title: Finish your first task in Humanize Desktop
description: Install Humanize Desktop, chat with a coding agent, install a flow, and run it on a task under a budget until it is done.
---

# Finish your first task in Humanize Desktop

In fifteen minutes, you install the app, chat with a coding agent, install a flow, and run it on a task in your project until it is done.

![Humanize Desktop showing a finished epic: two agents in a graph, and the time and tokens it used](/shots/tutorials-first-task-desktop-done.svg)

## What you need

- A Mac with macOS 11 or later, or a PC with Windows 10 or later and WSL 2.
- A project folder. This page uses `~/shop`. On Windows, keep it under your Linux home in WSL.
- An account with one coding agent, such as Claude Code, and `npm` to install its CLI.
- On a Mac: [uv](https://github.com/astral-sh/uv), to install the Humanize CLI.

## 1. Install the Humanize CLI

Humanize Desktop is a window onto the Humanize CLI, `hmz`, which runs a coding agent CLI in your project.

![Humanize Desktop starts hmz, hmz runs the coding agent CLI, and the agent edits your project; on Windows the last three are inside WSL](/diagrams/tutorials-first-task-desktop-1.svg)

On a Mac, install `hmz` in a terminal:

```sh
uv tool install hmz
```

On Windows, skip this step. The app installs `hmz` in WSL. If you do not have WSL yet, run `wsl --install` in PowerShell first.

## 2. Sign in to a coding agent

Humanize drives a coding agent CLI, called a harness. To set up Claude Code, run these commands in a terminal (on Windows, use a WSL terminal):

```sh
npm i -g @anthropic-ai/claude-code
claude auth login
```

Skip this step if a coding agent CLI is already signed in. See [Coding agents](/user/agents) for other harnesses.

## 3. Install the app

Download the installer from the [latest release](https://github.com/humanfia/humanize/releases/latest).

- Mac: open `humanize-<version>-macos-universal.dmg` and drag **Humanize Desktop** onto **Applications**.
- Windows: run `humanize-<version>-windows-x64-setup.exe`. It installs for your user without administrator rights.

## 4. Open the app

Open **Humanize Desktop** from Applications, or from the Start menu on Windows. The window shows `Starting`, then opens a new chat.

![The app's window opens on Starting, then shows a new chat](/shots/tutorials-first-task-desktop-open.svg)

If macOS blocks the app on first launch, click **Done**, open **System Settings → Privacy & Security**, and click **Open Anyway**.

On Windows, the first launch shows `Installing Humanize CLI` while the app installs `hmz` in WSL.

![The launch window on Windows: Installing Humanize CLI, with a progress bar and the step Installing hmz](/shots/tutorials-first-task-desktop-installing.svg)

## 5. Add an account

Click **Settings** (the gear at the bottom of the sidebar), then click **Accounts**. When the page says `No account yet.`, every agent uses your sign-in from step 2. On a Mac, skip to step 6.

To run agents with another account, such as an API key, fill in **New account**:

1. Set **CLI** to `Claude Code` and **Sign-in method** to `key`.
2. Type a **Name**, such as `work`.
3. Paste your key under `ANTHROPIC_API_KEY`.
4. Click **Create**.

![Settings, Accounts: the New account form filled in for Claude Code with an API key, named work](/shots/tutorials-first-task-desktop-account.svg)

To use the account, click the agent chip under a message box, open **Account**, and pick `work`.

::: warning
An account you add for Claude Code works only where the agent runs on Linux. That includes the Windows app, which runs agents in WSL. On a Mac, use the sign-in from step 2.
:::

## 6. Open your project and chat

1. Click **New chat** in the sidebar.
2. Click the folder chip under the message box and choose **Open folder…**.
3. Type `~/shop` and click **Open**.

![The folder chip's box with ~/shop typed and the Open button](/shots/tutorials-first-task-desktop-folder.svg)

The agent chip shows the harness, model, and effort. Click it to pick another.

Type a question and press <kbd>enter</kbd>:

```text
Where is checkout handled?
```

![A question is typed in a new chat, the agent works, and its answer appears](/shots/tutorials-first-task-desktop-chat.svg)

A chat runs directly without a flow or a budget.

## 7. Install a flow

A flow is a loop that runs agents on a task. Humanize starts with no flows installed. You install flows from a flowverse, and the official flowverse is already listed.

1. Click **Flows** in the sidebar.
2. Click **Browse Flowverses**. The `Official` tab lists the available flows.
3. Click **Install** beside `rlar`. The row updates to show its version and `installed`.

![Flows, Browse Flowverses, then Install beside rlar, which becomes installed](/shots/tutorials-first-task-desktop-install.svg)

In `rlar`, an actor works on the task until a fresh reviewer marks it done. See the [catalogue](https://humanfia.ai/flows/) for other flows.

## 8. Start an epic

An epic is one recorded run of a flow.

1. Click **New epic** in the sidebar. The flow defaults to `rlar`, and **Folder** is `shop`.
2. Under **Agents**, the `actor` and `reviewer` roles already have agents assigned. Click an agent to change it.
3. Under **Budget**, type `10` in **Time, min**. Every epic requires at least one limit; you can also set **Cost, $** and **Output tokens**.
4. Type the task at the bottom and press <kbd>enter</kbd>:

```text
Add a discount code to checkout
```

![The New epic page: flow rlar, folder shop, an agent for actor and reviewer, a budget of 10 minutes, and the task typed](/shots/tutorials-first-task-desktop-new-epic.svg)

## 9. Watch it run

The epic opens in the `running` state. The graph draws a box for each agent and highlights the active one. The right panel tracks elapsed time, token usage, and how much of the budget is used.

![A running epic: the actor's box is lit, the reviewer has not started, and the panel shows time used of the 10 minute budget](/shots/tutorials-first-task-desktop-running.svg)

To end the run early, click **Stop**, then click **Stop** again to confirm.

## 10. See it finish

When the reviewer approves the work, the epic state changes to `done`. An arrow in the graph shows the actor handing off to the reviewer.

Click any session under an agent, in the graph or the sidebar, to inspect its tool calls, outputs, and final answer.

![The actor's session read back: it read and edited checkout.py, ran the tests, and said what it changed](/shots/tutorials-first-task-desktop-session.svg)

The agent's changes are now in your project folder.

## What you did

- You installed Humanize Desktop, opened your project, and chatted with a coding agent.
- You installed `rlar` from the official flowverse.
- You ran an epic on a task under a budget.
- You inspected the agents' sessions once the run finished.

## Next

- [Humanize Desktop](/user/desktop): learn what else the app does and how to troubleshoot startup issues.
- [Find and install flows](/user/flows): browse, update, and add your own flows.
- [Budgets](/user/budgets): see all limit types and what happens when a run reaches one.
- [Leave a long task running overnight](/tutorials/overnight-run): close the window and return to a finished run.
