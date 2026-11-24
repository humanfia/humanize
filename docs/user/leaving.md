---
title: Leave it running and come back
description: Close the terminal or the app while a flow runs, and attach to the same epic again later.
---

# Leave it running and come back

A background daemon on the machine holds every epic. Close the terminal or the app and the flow keeps working. Open either again to attach to the same epic.

![Humanize Desktop, the browser page and hmz in a terminal all attach to one epic that the daemon holds](/diagrams/user-leaving-1.svg)

## In the app

Humanize Desktop and the browser page leave running epics and chat turns untouched when you exit.

| Action | Effect on a running epic |
| --- | --- |
| Close the Humanize Desktop window | Hides the window. The app stays in the Dock (macOS) or the tray (Windows). The epic runs. |
| Quit Humanize Desktop | Stops the app and its child processes. The epic runs. |
| Close the browser tab | Detaches the page. The epic runs. |
| Stop `hmz web` with <kbd>ctrl+c</kbd> | Stops serving the page. The epic runs. |

Open the app or the browser page again to return. The sidebar marks an active epic as **Running** with a **live** badge, and counts all live epics at the bottom. Click the row to attach and read everything the epic did while you were away.

![Humanize Desktop open on a running epic: the sidebar row says Running and live](/shots/user-leaving-app.svg)

*An epic the terminal started, opened in the app while it runs.*

Press **Stop** before leaving if you want to end the epic. See [Stop a run](/user/stopping).

## In the terminal

Type `/exit`, `/quit`, or press <kbd>ctrl+q</kbd> while a flow runs in `hmz`. A box titled `A flow is running.` asks what to do.

![The leave box in the terminal: /exit, then down to Detach and exit](/shots/user-leaving-box.svg)

| Choice | Effect |
| --- | --- |
| **Stop the flow and exit** | Focused by default. Stops the epic for everyone attached, waits up to 10 seconds, then exits. |
| **Detach and exit** | Press <kbd>down</kbd> or <kbd>tab</kbd>, then <kbd>enter</kbd>. Exits while the epic keeps running. |
| <kbd>esc</kbd> | Stays in `hmz`. |

Closing the terminal window or dropping an ssh connection detaches and exits.

When nothing is running, `/exit` leaves at once. Leaving a chat also exits at once and never ends the chat.

### Reconnect in the terminal

Run `hmz` in the same folder from any terminal on that machine:

```sh
cd ~/shop
hmz
```

`hmz` attaches to the folder's epic and reads it from the start.

![hmz run again in the folder: the whole epic so far, still working](/shots/user-leaving-back.svg)

Type `/epics` to list every epic in the folder. Active epics say `still going`. Press <kbd>ctrl+t</kbd> in that view to list every folder on the machine.

![The /epics list with one epic marked still going](/shots/user-leaving-epics.svg)

If the epic ended while you were away, `hmz` shows the final state. Run `/resume` to continue a resumable flow. See [Resume a run](/user/resuming).

## From the command line

`hmz exec` holds the terminal until its epic ends, then exits.

![hmz exec printing an epic until it ends](/shots/user-leaving-exec.svg)

Closing the terminal, pressing <kbd>ctrl+c</kbd>, or running `kill` stops the epic. Ignore the hangup signal to keep a command-line run going after you log out:

```sh
nohup hmz exec -f goal -a worker=claude/claude-haiku-4-5 -p budget.duration=30m "Add a discount code to checkout" &
```

Watch the running epic from the app's sidebar or `/epics`. See [The command line](/user/command-line).

## Attach several windows to one epic

Attach any number of terminals, app windows, or browsers on other devices to the same epic at once. Every window reads the full epic and can steer or stop it. Closing one window leaves the others attached.

Check **Frontends** in the app's **Epic** panel to see who is attached.

![The Frontends list in the Epic panel: a terminal and this page](/shots/user-leaving-frontends.svg)

Each window uses your login name and interface type, such as `alex@tui` or `alex@web`, to label lines you type. Set `HUMANIZE_NAME` before starting `hmz` to change the name prefix. See [Talk to a running flow](/user/steering).

## Automatic shutdown

The daemon and its helpers stop on their own when idle:

- A folder's host, the process that holds its epics, closes when no epic is running and no window is attached.
- An idle chat with no open window closes after 60 seconds between turns. Open it again to continue.
- The daemon exits 2 seconds after the last host and window close, unless you started it with `hmz daemon serve` or as a login service, or it listens for other machines. See [The daemon](/user/daemon).

## Good to know

- Pressing <kbd>ctrl+c</kbd> twice in `hmz` stops the running flow instead of detaching. Use `/exit` to leave it running.
- The machine running the epic must stay awake and powered on. A reboot ends the epic. You can close your laptop only if the epic runs on a remote machine.
- On Windows, epics run in WSL. If you quit Humanize Desktop, epics last only while WSL keeps the distribution running.
- A flow pauses if it asks a question while you are away. Mark yourself away before leaving: see [Answer a flow's questions](/user/questions).
- Set a budget so the epic does not overspend while unattended: see [Budgets](/user/budgets).
- `hmz` waits up to 15 seconds on exit for queued backups to finish.
- For a full walkthrough, see [Leave a long task running overnight](/tutorials/overnight-run).
