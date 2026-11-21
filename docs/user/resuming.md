---
title: Resume a run
description: Pick up an epic that stopped, from the app, the terminal or the command line, and know what carries over.
---

# Resume a run

When an epic stops before the work is done—because you stopped it, its budget ran out, or the machine went down—you can resume it. Resuming starts a new epic that continues from the saved state of the earlier one.

![Resuming copies the saved state of the earlier epic into a new epic](/diagrams/user-resuming-1.svg)

## Check if you can resume

You can resume an epic if it uses a resumable flow, saved state, and is not currently running. A resumable flow saves progress as it runs, so you can pick up even a killed run. In the official [catalogue](https://humanfia.ai/flows/), `stateful_ralph` and `rlar` are resumable, for example; the one-turn `goal` is not. On the [Flows](/user/flows) page, click an installed flow's card: its **Resumable** row says yes or no. If a flow is not resumable, [start it again](/user/epics).

## In the app

1. Open the ended epic and click **Resume** in the top bar, or click **Resume** in the `Ended · Resume` note at the bottom of the page.

![An ended epic in Humanize Desktop with the Resume button in its bar](/shots/user-resuming-app-ended.svg)

2. The **Resume epic** page opens with the earlier epic's flow, folder, agents, budget, profiling switches, and task filled in, alongside the note `Picks up <name>, carrying on from where it stopped.`
3. Adjust any settings, such as a larger budget, and press <kbd>enter</kbd> in the task box.

![The Resume epic page, filled in from the earlier epic](/shots/user-resuming-app-form.svg)

You can also resume from the sidebar. Click **More options** on the epic's row (or right-click it) and select **Resume**. Right-clicking the epic's title in the top bar opens the same menu. This option appears for resumable epics that did not finish as done.

![The row menu of a stopped epic, with Resume](/shots/user-resuming-app-menu.svg)

On the new epic's **Epic** tab, the **Resumed from** row links to the earlier epic.

![The Epic tab of the new epic, with a Resumed from link](/shots/user-resuming-app-origin.svg)

## In the terminal

To choose an epic from the current directory:

1. Type `/epics`.
2. Press <kbd>enter</kbd> on a row ending with `resumable`.
3. Choose `resume epic`.

![Opening /epics, choosing an epic and then resume epic](/shots/user-resuming-terminal-epics.svg)

To resume the newest epic immediately, type `/resume` while a flow is on the screen, such as right after it stops. `/resume` takes no argument.

![A new epic running after /resume](/shots/user-resuming-terminal-resume.svg)

Both commands run the epic's recorded flow, agents, environments, params, budget, profiling switches, and task, ignoring the terminal's current settings.

When the screen shows a chat, as it does when `hmz` opens with no flow on it, `/resume` lists earlier chats instead: use `/epics` to resume an epic. See [Organise chats](/user/manage-chats).

## From the command line

Add `--resume` to `hmz exec` in the directory where the earlier epic ran:

```sh
hmz exec -f stateful_ralph -a agent=claude/claude-haiku-4-5 -p budget.output_tokens=300 --resume "Add a discount code to checkout"
```

![hmz exec --resume carrying on until its new budget is spent](/shots/user-resuming-exec.svg)

`--resume` takes no value. It resumes the newest epic of the `-f` flow in this directory that saved state and is not running. The new epic uses the agents, environments, params, and budget from your new command line, not the earlier ones. Without `--resume`, `hmz exec` starts from the beginning.

If the flow is not resumable, or no epic in the directory can be picked up, `hmz exec` exits with status 2 before starting any agent.

![hmz exec refusing --resume for a flow that is not resumable](/shots/user-resuming-refused.svg)

## What carries over

| Item | Carried over? |
| --- | --- |
| Flow state | Yes. |
| Conversations saved in flow state | Yes, the agent remembers them. Every other session starts fresh. |
| Temporary clones and scratch directories | Yes. |
| Files changed in your folder | Left as the earlier epic modified them. |
| Earlier budget spent | No. The new budget counts from zero. |
| The earlier epic | Unchanged. The new epic gets its own name, sessions, and trace. |

## Troubleshoot resume errors

When `/resume` or `resume epic` cannot run, it shows one of these messages:

| Message | Meaning |
| --- | --- |
| `no flow has been run here, so there is nothing to resume` | No epic in this directory. |
| `no epic here was of a flow that can be resumed, so there is nothing to resume` | Every epic here is of a flow that is not resumable. |
| `<flow> does not support resuming, so <epic> cannot be resumed` | The flow is not currently resumable. |
| `<epic> cannot be resumed: <why>` | The flow can no longer be loaded. |
| `<epic> cannot be read, so there is nothing to resume` | The epic's record is unreadable. |
| `<epic> has no saved state to resume: enter a task to start the flow from the beginning` | The run ended before saving state. |
| `<epic> cannot be resumed here: <why>` | An imported epic whose folder or commit is not on this machine. |
| `cannot resume an epic while a flow is running: press ctrl+c twice to stop it first` | An epic is running. See [Stop a run](/user/stopping). In `/epics` the message is `a flow is running; press ctrl+c twice to stop it before resuming another`. |
| `/resume takes no arguments: it resumes the last epic here; use /epics to choose another epic` | You passed an argument to `/resume`. |

On the command line, `hmz exec --resume` prints `hmz exec: error: <flow> does not support resuming, so there is no run to resume` or `hmz exec: error: <flow> has no run to resume here: none saved any progress`.

## Good to know

`/resume` checks only the newest epic of a resumable flow. If that epic cannot be resumed, it tells you why and does not fall back to an older epic. Use `/epics` to pick an older one. Outside a chat, `/resume` is hidden from the `/` menu when there is nothing to resume in the current directory.

`resume epic` refuses to run an epic from another directory, saying `this epic ran in <dir>; resume it from hmz there`. Open `hmz` in that directory first.

An [imported](/user/export) epic resumes only if its folder exists on this machine at the same path and, for a git repository, contains the recorded commit. Otherwise, its page shows `Imported · not resumable here: <why>`.

You do not resume chats this way. Type in the chat to continue it: see [Chat with an agent](/user/chat).

To make your own flow resumable, see [Resumable flows](/builder/resumable). To resume from Python, see [The Python SDK](/builder/sdk).
