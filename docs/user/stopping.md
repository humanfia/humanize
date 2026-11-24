---
title: Stop a run
description: Stop a running epic from any interface, force one that will not let go, and stop one turn of a chat.
---

# Stop a run

Stopping an epic interrupts every open turn and cancels the flow. The flow closes every session and environment it opened, and deletes its temporary directories. If an epic takes too long to unwind, you can force it to stop.

![An epic goes from running to stopping to stopped; a force stop skips the wait](/diagrams/user-stopping-1.svg)

Stopping an epic stops it in every open interface. A terminal following it prints `stopping the flow`, and names the interface that stopped it when that was another one.

## In the app {#in-the-app}

1. Open the running epic and click **Stop** in its bar.
2. When the app asks **Stop this epic?**, click **Stop** to confirm or **Cancel** to keep it running.

![The Stop button of an epic, the question it asks, and the epic stopped](/shots/user-stopping-app.svg)

The button shows **Stopping…** for up to ten seconds until the epic begins stopping.

To stop an epic from the sidebar without opening it, open the **More options** menu on its row and select **Stop**. This stops the epic without asking for confirmation.

![The menu of an epic's row in the sidebar, with Stop as its last item](/shots/user-stopping-app-menu.svg)

### Force a stop {#force-a-stop}

While an epic is stopping, the button changes to **Force stop**. Click it, then click **Force stop** when asked **Close every session now?**. Every session still in a turn closes immediately, and those turns fail instead of finishing.

![An epic that is stopping, with Force stop asking whether to close every session now](/shots/user-stopping-app-force.svg)

### Stop one turn of a chat {#chat-turn-in-the-app}

While a chat agent is answering, the **Send** button becomes **Stop**. Click it to interrupt the turn. The chat shows `That turn was stopped.` and waits for your next message.

![A chat whose open turn is stopped with the button of its message box](/shots/user-stopping-app-turn.svg)

## In the terminal {#in-the-terminal}

<kbd>ctrl+c</kbd> does a different thing in each state. The end of the status line always says what the next press does.

| State | <kbd>ctrl+c</kbd> does |
| --- | --- |
| Text in the prompt | Clears the text. |
| A flow is running | The first press says `press ctrl+c again to stop the flow`. A second press within 3 seconds stops it. |
| The flow is stopping | Forces it. If turns were still open, it says how many: `closed 2 conversation(s) mid-turn`. |
| Nothing is running, or a chat | The first press says `press ctrl+c again to exit`. A second press within 3 seconds leaves `hmz`. |

![A flow stopped with two presses of ctrl+c, then forced with a third](/shots/user-stopping-terminal.svg)

Run `/stop` to stop the flow immediately without confirmation. If nothing is running, it fails with `no flow is running`. If a stop is already in progress, it fails with `the flow is already stopping: it is finishing the turn it was in`.

You can also stop an epic from the monitor:

1. Press <kbd>←</kbd> to open the monitor.
2. Move up to the epic's row and press <kbd>enter</kbd> to open the epic's page.
3. Press <kbd>tab</kbd> to reach **Stop**, then press <kbd>enter</kbd>.
4. It asks `Stop this epic?` Press <kbd>enter</kbd> to stop, or <kbd>esc</kbd> to cancel.

While the epic is stopping, this button becomes **Force stop** and asks `Close every session now?`.

![The epic's page in the monitor, asking whether to stop the epic](/shots/user-stopping-terminal-page.svg)

### Stop one turn of a chat {#chat-turn-in-the-terminal}

In a chat, `/stop` interrupts the open turn and keeps the chat. With no turn open it is refused: `no turn is open, so there is nothing to stop`. <kbd>ctrl+c</kbd> never stops a chat's turn. It only leaves.

![A chat in the terminal after /stop: the turn was stopped and the prompt is ready](/shots/user-stopping-terminal-turn.svg)

## From the command line {#from-the-command-line}

Send a signal to `hmz exec` to stop its epic. The command waits for the epic to close everything, then exits with 128 plus the signal number.

| Signal | How to send it | Exit status |
| --- | --- | --- |
| `SIGINT` | <kbd>ctrl+c</kbd> | `130` |
| `SIGTERM` | `kill <pid>` | `143` |
| `SIGHUP` | closing the terminal | `129` |

![hmz exec interrupted with ctrl+c: the turn is cut off and the exit status is 130](/shots/user-stopping-exec.svg)

A second <kbd>ctrl+c</kbd> while the epic is stopping forces it and ends the command at once. A second `SIGTERM` or `SIGHUP` is ignored.

Sending a signal to `hmz chat` does not stop the turn. The command detaches from the chat, leaves it running in the daemon, and exits with 128 plus the signal number.

`hmz epic stop` stops an epic the command line did not start, or one started with `hmz epic start`:

```bash
hmz epic stop                        # the epic of this directory
hmz epic stop --force                # also close turns that are still open
hmz hosts list --running             # find the workspace and slot of another epic
hmz epic stop -w ~/work/app --slot exec:1f2e
```

`hmz hosts stop` closes the whole host instead, stopping the epic or chat it runs. `hmz epic quit` does the same as one of the host's frontends. `hmz hosts detach` stops nothing: it lets go every app, terminal and command following the host and leaves the epic running.

## What a stop leaves {#what-a-stop-leaves}

A stopped epic is recorded as `stopped`, and its sessions and figures remain readable. Files stay as they were when interrupted, without rolling back partial writes. You cannot restart a stopped epic, so [resume it](/user/resuming) if the flow supports resuming, or start a new epic.

## Good to know {#good-to-know}

- An epic that exhausts its [budget](/user/budgets) is also recorded as `stopped`.
- Stopping a chat ends only its open turn; the chat stays ready for your next message. You cannot force-stop a chat turn.
- In the terminal, running `/stop` while following [Ai-chan](/user/ai-chan) stops only her open turn.
- Closing the browser tab or the app does not stop an epic. Leaving the terminal interface while a flow runs asks whether to stop it or leave it running; see [Leave it running and come back](/user/leaving).
- If `hmz exec` is killed any other way, such as with `kill -9`, its epic keeps running in the daemon.
- Any signal already ignored when `hmz exec` starts stays ignored, such as `SIGHUP` under `nohup` or `SIGINT` for a background job in a script.
