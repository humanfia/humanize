---
title: Talk to a running flow
description: Say a line to an agent while a flow runs, see where the line waits and when it is taken, and tell who said what when several interfaces follow one epic.
---

# Talk to a running flow

Send a line to an agent while an epic runs. The agent takes the line into its current or next turn without stopping or restarting.

![Humanize Desktop: a line is typed into the box of an agent's session, it waits, and the agent's next turn takes it and answers](/shots/user-steering-say.svg)

## Where a line goes

![A line goes into the agent's open turn, or it waits until that agent's next turn starts](/diagrams/user-steering-1.svg)

Each line targets one agent. If the agent has an open turn, the line enters that turn. Otherwise, the line waits until the agent's next turn starts. Waiting lines are never dropped while the epic runs.

The agent's harness determines whether a line can enter a running turn:

| Harness | A line said mid-turn |
| --- | --- |
| Claude Code, Codex, Kimi Code, Pi, Oh My Pi | goes into the running turn |
| every other harness | is refused, waits, and goes into the next turn |

Agents take lines one at a time. The next line waits until the agent takes the previous one.

## In the app

Humanize Desktop and the web page work the same way.

1. Open the running epic. The box under the graph says **Message the epic**.
2. Choose a recipient in the **To** chip.
3. Type the line and press <kbd>enter</kbd>.

![The box under a running epic, with the To chip set to Next turn](/shots/user-steering-box.svg)

| **To** | The line goes |
| --- | --- |
| **Next turn** | into the first session that has a turn open or, with none open, into the next turn any agent starts. If a question you may answer is waiting for a typed line, the line answers it instead. |
| an agent's name | into that agent's newest session with a turn open |
| a session: an agent's name and a number | into that session. A session in the middle of a turn is marked `(working)`. |
| a role followed by `(person)` | to no agent: it answers that role's question once one waits for a typed line. If another interface holds the role, the line is refused. |

To skip the chip, select an agent or session in the sidebar. The box changes to `Message` followed by that name, and sends every line there. If that session is asking you a question, your line answers it.

Once a turn takes the line, it appears in the session thread labeled with the sender, such as `alex@web said`. If a line cannot be sent, the reason appears under the box.

## In the terminal

Type a line at the `hmz` prompt and press <kbd>enter</kbd>.

The line goes to the agent whose transcript is on screen. Press <kbd>shift+tab</kbd> to switch to another agent first. When you view an agent, the line goes to its newest session with an open turn.

![The terminal interface: a line is typed, it is pinned above the prompt, and the agent's next turn takes it into the transcript](/shots/user-steering-terminal.svg)

Untaken lines stay pinned above the prompt behind `❯`.

![Three lines pinned above the prompt: one with an agent, one waiting, and one said from another interface](/shots/user-steering-pinned.svg)

| On the pin | Meaning |
| --- | --- |
| `· with` and an agent's name | The line has been put into that agent's running turn. The agent has not confirmed it yet. |
| no `with` | The line waits for a turn to start. |
| `· by` and a name | Another interface said the line. |
| `… 2 more waiting` | The pin shows at most 5 rows. The lines that do not fit are counted, here two. |

When a turn takes the line, it leaves the pin and joins the transcript. A line can also end in one of these ways:

| The terminal says | What happened |
| --- | --- |
| a red line with the harness's reason | The harness refused the line mid-turn. The line goes back to the front of the waiting lines. |
| `sent to` the agent, `which ended its turn without acknowledging it` | The turn ended before the agent confirmed the line. It may or may not have reached the model. Say it again if it matters. |
| `never sent` | The epic ended while the line still waited. |
| `sent to the agent, not acknowledged` | The epic ended while an agent held the line unconfirmed. |

If a question is waiting for you, your line answers it. On a person's role view with no waiting question, the terminal refuses the line with `is not asking anything now`, or with `to answer, not yours` when another interface holds that role.

## From the command line

`hmz epic say` says a line to the epic of the current directory, from a script or another shell:

```bash
hmz epic say 'use the staging database'
hmz epic say --to NeiKos 'skip the migration'
```

Without `--to`, the line goes where a line typed in the app's message box goes. `--to` takes an agent's name, a session such as `NeiKos/2`, or `outworlder:<role>`. `hmz epic attach` follows the epic and shows the line when a session takes it. See [`hmz epic`](/reference/cli#hmz-epic) for `-w` and `--slot`, which name an epic elsewhere.

## Follow one epic from several interfaces

Connect any number of windows, web pages, and terminals to the same epic to talk to its agents. Open the epic panel and check **Frontends** to see every connected interface.

![The Frontends section of the epic panel, listing this page and a terminal](/shots/user-steering-frontends.svg)

Each interface uses your login name and its type, such as `alex@tui` or `alex@web`. Set the environment variable `HUMANIZE_NAME` to replace the login name. Duplicate names get a number, such as `#2` or `#3`.

Every interface sees every line. A line, an answer or an epic started from another interface carries that interface's name. Each question takes one answer: the first answer wins, and other interfaces see who answered. Stopping the epic stops it everywhere.

## Hold a role, or step away

A role a person fills can be held by one interface, so that only it answers that role's questions.

- In the app, open the epic panel and select **People**. Click **Claim**, **Take over** or **Release** beside a role, **Away** or **Back** to say whether anybody is there for it, and **Away for all** for every role.
- In the terminal, press <kbd>ctrl+o</kbd> and then <kbd>3</kbd>. <kbd>enter</kbd> claims, takes over or releases the role under the cursor, <kbd>w</kbd> sets it away or back, and <kbd>shift+w</kbd> does so for every role. `/claim` and `/afk` do the same from the prompt.

While a role is away, a question asked of it is answered at once with nothing, and the epic carries on.

## Use the board

Some runs keep a board of key-value pairs that both you and the run can edit. Nothing waits on the board. It appears only when the run uses one.

- In the app, open the epic panel and select **Board**. Click **Edit** then **Save** to change a value, or **Remove** twice to delete a line. Fill in **Key** and **Value** and click **Add** to create a line.
- In the terminal, press <kbd>ctrl+o</kbd> and then <kbd>2</kbd> to open **Board** beside the log. Press <kbd>a</kbd> to add a line, <kbd>enter</kbd> to edit the line under the cursor and <kbd>d</kbd> to remove it; removing asks first. The monitor (<kbd>←</kbd> at an empty prompt) shows the same board under the graph.

- From the command line, `hmz epic board` prints the board, `hmz epic board KEY VALUE` writes a line, and `hmz epic board KEY --remove` removes it.

Lines tagged **Flow** in the app or `flow's` in the terminal belong to the run and are read-only.

## Good to know

- Flows written with `hmz.flows` keep no board, so their epics show no **Board** tab and no board in the monitor.
- The app does not show waiting lines. Check the terminal pins to see lines that have not been taken yet.
- Sending a line never stops a run. To stop a run, see [Stop a run](/user/stopping).
- To ask about a run without an agent hearing, [ask a side question](/user/side-questions). To answer a flow, see [Answer a flow's questions](/user/questions).
- `hmz exec` has no prompt and takes no lines.
- A flow can send a line into its own agent's running turn. See [Sessions and turns](/builder/turns).
