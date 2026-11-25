---
title: Leave a long task running overnight
description: Start an epic under a time and cost budget, say you are away, close the terminal or the app, and come back to reattach, resume and read what it did.
---

# Leave a long task running overnight

Start a flow on a large task with an eight-hour, twenty-dollar budget, then close the terminal. In the morning, reattach, resume the run if the budget ended it, and read what it did.

![The daemon holds the epic: the terminal or the app attaches and detaches while the agent keeps taking turns](/diagrams/tutorials-overnight-run-1.svg)

## What you need

- You have `hmz` and a coding agent set up, as in [Finish your first task in the terminal](/tutorials/first-task-terminal).
- You have the `stateful_ralph` flow, installed the same way that tutorial installs `ralph_loop`. It saves its progress so you can resume a run.
- You have a machine that stays on and awake. A reboot ends the epic.

These steps use the terminal and point out the matching controls in the app.

## 1. Set a time and cost budget

Open `hmz` in your project:

```sh
cd ~/shop
hmz
```

1. Type `/flow stateful_ralph` and press <kbd>enter</kbd>.
2. Select `Budget` and press <kbd>enter</kbd>.
3. Select `duration`, press <kbd>enter</kbd>, type `8h`, and press <kbd>enter</kbd>.
4. Select `cost`, press <kbd>enter</kbd>, type `20`, and press <kbd>enter</kbd>.
5. Press <kbd>tab</kbd> to reach **Set**, then press <kbd>enter</kbd>. The `Budget` row reads `stops at 8h, $20.00`.
6. Press <kbd>esc</kbd>, then press <kbd>enter</kbd> on **Save**.

![The budget sheet: eight hours, twenty dollars, set and saved](/shots/tutorials-overnight-run-budget.svg)

The epic stops at the first limit it reaches, once the current turn finishes. Set both limits: a cost limit cannot stop a model without a list price, so the time limit backs it up.

In the app, click **New epic**, pick the flow, and fill in `Cost, $` and `Time, min` under **Budget**. Eight hours is `480` minutes.

![New epic in Humanize Desktop with a cost of 20 dollars and a time of 480 minutes](/shots/tutorials-overnight-run-app-budget.svg)

## 2. Start the task

Run the flow with your prompt:

```text
/flow stateful_ralph Add a discount code to checkout
```

Each round appears as the agent finishes it. In the app, type the task in the box under the form and press <kbd>enter</kbd>.

## 3. Mark yourself away

Type `/afk` and press <kbd>enter</kbd>.

![The transcript says away, and the status line starts with afk](/shots/tutorials-overnight-run-away.svg)

The status line now starts with `afk`. Normally, a flow that asks a person a question waits for an answer. While you are away, `hmz` answers each question immediately with an empty response so the epic keeps running.

In the app, open the **People** tab in the side panel and click **Away for all**. This tab appears only when the flow includes a person. `stateful_ralph` has none, so the picture shows a flow with a reviewer.

![The People tab is opened and Away for all is clicked](/shots/tutorials-overnight-run-app-away.svg)

## 4. Leave it running

Type `/exit` and press <kbd>enter</kbd>, or press <kbd>ctrl+q</kbd>. A dialog says `A flow is running.` Select **Detach and quit** and press <kbd>enter</kbd>.

![The leave box opens on /exit, and Detach and quit is selected](/shots/tutorials-overnight-run-leave.svg)

You return to your shell while the epic runs in the background. Closing the terminal window or losing an ssh connection detaches the same way.

::: warning
**Stop the flow and quit** ends the epic.
:::

In the app, closing the window, quitting Humanize Desktop, or closing the browser tab detaches automatically without stopping the epic. On Windows, epics run in WSL, which may shut down once the app has quit: see [Humanize Desktop](/user/desktop).

## 5. Get notified

Leave Humanize Desktop running to receive notifications. Closing its window hides it without quitting. Open **Settings**, then **Notifications**.

![The Notifications settings: the kinds Done, Failed, Stopped, Questions and Waiting, and System on](/shots/tutorials-overnight-run-app-notifications.svg)

Keep `Done`, `Failed`, and `Stopped` checked and **System** on, as they are by default. Humanize Desktop shows a system notification when the epic ends. In a browser, click **Allow** first. See [Notifications](/user/notifications) for terminal options.

## 6. Reattach to the epic

Run `hmz` in the same directory:

```sh
cd ~/shop
hmz
```

`hmz` reattaches and loads the transcript from the start. If the epic is still running, you watch it live. Here, the budget ended it overnight:

![Back in the terminal: the last rounds, then the line saying the cost budget is spent](/shots/tutorials-overnight-run-back.svg)

The transcript ends with `its budget's cost is spent`. The status line still shows `afk`. Type `/afk` again to mark yourself back. In the app, click the epic in the sidebar.

## 7. Resume the run

Type `/resume` and press <kbd>enter</kbd>.

![A new epic picks the task up, with the spend counted from zero](/shots/tutorials-overnight-run-resumed.svg)

`/resume` starts a new epic from the saved state of the newest epic in this directory. It keeps the flow, agent, task, and budget, and resets the budget spend to zero. The agent continues its previous conversation. Use `/resume` to continue after a reboot as well. If nothing can be resumed, `/resume` tells you why.

Type `/stop` to end this second epic. In the app, click **Resume** on the ended epic. The **Resume epic** form opens with the task, agent, and budget filled in. Press <kbd>enter</kbd> to start it.

## 8. Read what it did

Type `/epics` and press <kbd>enter</kbd>. You see both epics, newest first, with their spend, duration, and status.

![The list of epics: the resumed one and the one the budget stopped, both resumable](/shots/tutorials-overnight-run-epics.svg)

Press <kbd>enter</kbd> on an epic, select `Graph`, and press <kbd>enter</kbd> to read its sessions. In the app, the side panel shows `Spent`, `Output tokens`, `Took`, and `Sessions` under **Figures**, and the budget under **Setup**.

![An ended epic in Humanize Desktop: stopped, with a Resume button, what it spent and its budget](/shots/tutorials-overnight-run-app-ended.svg)

The agent's changes are in your working tree. Run `git diff` to review them before you commit.

## What you did

- Started a flow with a time limit and a cost limit.
- Marked yourself away so questions would not block the epic.
- Detached and left the epic running in the daemon.
- Reattached, resumed the epic, and inspected both runs.

## Next

- [Leave it running and come back](/user/leaving)
- [Budgets](/user/budgets)
- [Resume a run](/user/resuming)
- [Read back, export and share a run](/tutorials/read-back-a-run)
