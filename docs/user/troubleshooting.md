---
title: Troubleshooting
description: Find the cause of a failed install, a missing or signed-out agent, an unreachable daemon, a stalled run, a sandbox refusal or a remote runtime that will not answer, and fix it.
---

# Troubleshooting

Match the error you see to its cause and fix it.

![The terminal interface after a failed turn: a red line says HarnessRefused, what the CLI printed, and in brackets that the account needs signing in again](/shots/user-troubleshooting-signed-out.svg)

*A failed turn prints the reason in red and ends with the failure kind in brackets.*

## Read why a turn failed

When a turn fails, Humanize prints the coding agent CLI output followed by the failure kind and fix in brackets.

### In the app

The app marks the chat or epic **Failed** in the sidebar, and a chat shows `The chat failed` above its input box. The transcript shows a line starting with `hmz:` only when the coding agent CLI reported the failure itself. If there is none, send the same message from the terminal or command line to see the reason.

![A chat in Humanize Desktop marked Failed in the sidebar, with The chat failed over the input box](/shots/user-troubleshooting-chat-failed.svg)

### In the terminal

Run `hmz` and send the message. Read the red line that starts with `hmz:`.

### From the command line

Run `hmz chat` or `hmz exec`. Read the error line on standard error.

A failure Humanize could not classify ends with no brackets: read what the CLI printed.

### Failure kinds

| The line ends with | Cause | Fix |
| --- | --- | --- |
| `(refused: …)` | The account's sign-in expired or its key is wrong. | Sign the account in again: see [Accounts](/user/accounts). |
| `(throttled: …)` | The service is rate-limiting the account. | Wait. Humanize retries once after a pause. |
| `(spent: …)` | The account has used up its quota. | Wait, or use another account. |
| `(unlisted: …)` | The account may not use that model. | Pick a model the account lists: see [Coding agents](/user/agents). |
| `(retired: …)` | The model is gone. | Pick another model or nous. |
| `(missing: …)` | The CLI is not installed. | Run the install command the line names. |
| `(sandboxed: …)` | The CLI could not start its own sandbox on this machine, as in a container without user namespaces. | See [Sandbox refusals](#sandbox-refusals). |
| `(fenced: …)` | The flow gave the role no network, and the agent tried another host. | Nothing to sign in to. The flow must give the role network access. |
| `(unmirrored: …)` | A remote workdir's path cannot be created on this machine. | Use a workdir whose path you can create here, or set the runtime's harness to `env`: see [Runtimes](/user/runtimes). |
| `(contended: …)` | Two turns of one CLI share one database. | Humanize retries. |
| `(killed: …)` | The CLI was killed, often because the machine ran out of memory. | Free memory. Humanize retries once. |
| `(dropped)` | The connection was lost. | Humanize retries once. |

To switch accounts or models automatically on failure, set up a fallback: see [Nous: models, retries and fallback](/user/nous).

## Fix a missing agent

| What you see | Cause | Fix |
| --- | --- | --- |
| `hmz: No coding agent is installed.` in the terminal | Humanize found no coding agent CLI on this machine. | Install one and sign in to it: see [Coding agents](/user/agents). |
| `HarnessNotInstalled: codex is not installed here: npm i -g @openai/codex` | The line names a CLI that is not installed. | Run the install command the message ends with, or name a CLI you have. |
| The agent works in your terminal, but the app or the login service cannot find it | The daemon did not get your shell's `PATH`. | Put the CLI's directory on `PATH` in your login shell's profile, then restart the daemon: see [The daemon](/user/daemon). |

![The terminal interface answering a message that no coding agent is installed](/shots/user-troubleshooting-no-agent.svg)

![hmz exec refused: HarnessNotInstalled, codex is not installed here, followed by its install command](/shots/user-troubleshooting-refused.svg)

`hmz exec` checks the whole command before starting any agent. A refused command runs nothing, so fix it and run it again. See [The command line](/user/command-line).

## Fix install and startup errors

| What you see | Cause | Fix |
| --- | --- | --- |
| macOS will not open the app the first time | The app is not signed by Apple yet. | Allow it once: see [Install and update](/user/install). |
| `hmz is not installed on this machine.` under Local, on macOS | The app installs no `hmz` on macOS, and your login shell found none. | Install the CLI, then quit the app and open it again. |
| `WSL missing` in the launch window, on Windows | There is no WSL, or no Linux distribution in it. | Run `wsl --install` in PowerShell, then click **Retry**. |
| `Install failed` or `Update failed` | Installing `hmz` in WSL failed. The window shows what the installer said. | Check the connection and click **Retry**. Where **Continue** is offered, it uses the `hmz` already installed. |
| `Update waiting` | Epics are running in an older `hmz` that this app cannot open. | Wait for them to end, or click **Update now**, which may stop them. |

![The launch window on Windows saying WSL missing, then Install failed with what the installer said, then Update waiting](/shots/user-troubleshooting-startup.svg)

Every error in the launch window has a **Documentation** button. See [Humanize Desktop](/user/desktop#troubleshooting).

## Reach the daemon

| What you see | Cause | Fix |
| --- | --- | --- |
| `hmz: the daemon cannot be reached: <why>` | The daemon did not start, or stopped answering. | Read `daemon.log` for the reason. |
| `hmz: the runs on this machine are held by an older Humanize (pid <pid>); stop it with that version` | You updated `hmz` while a daemon of the old version was still running. | Let its runs finish or stop them, run `kill <pid>`, then run `hmz` again. |
| `… held for frontends by a newer Humanize …` | The daemon is newer than the `hmz` you ran. | Run the newer `hmz`, or update this one: see [Install and update](/user/install). |
| `That pairing code is not valid: ask for a new one.` | The code was already used or has expired, or the daemon restarted or made 16 newer codes. | Run `hmz devices pair` again on that machine and add it with the new code. |
| `<name> is not the daemon it was paired with.` | The machine at that address answers with another identity: its `identity/` directory was deleted, or the address now reaches another machine. | If you expect this, remove the daemon and add it again with a new pairing code. |
| `<route> needs the id of the daemon it reaches.` | The route is not a trusted one, and the daemon was saved with no daemon id. | Remove the daemon and add it again with a pairing code. |
| `hmz is not installed on <name>.` on a remote daemon | The SSH machine has no `hmz`, and you clicked **Not now**, pressed <kbd>esc</kbd>, or closed the dialog that offered to install it. Humanize does not retry this machine by itself. | Click **Connect**, then **Install** in the dialog. Or install `hmz` on that machine by hand, then click **Connect**: see [Install and update](/user/install). |
| `hmz <version> on <name> is too old to be reached: it has no daemon command.` | The `hmz` on the SSH machine was released before remote daemons existed, and Humanize did not replace it. This happens with a development build, which replaces no `hmz`. | Install a newer `hmz` on that machine by hand, then click **Connect**. |
| `The latest release of hmz is too old to be reached: it has no daemon command.` | You run a development build, and the latest released `hmz` cannot be reached by it. Humanize installed it on the SSH machine, found this, and removed it again. | Install `hmz` on that machine from the same source as your build, then click **Connect**. |
| A remote daemon shows as failed | The route to that machine is down. | Open **Settings → Daemons**, read the reason in the **State** column, and click **Connect** to try again: see [Connect to other machines](/user/daemons). |

After `hmz update`, a running daemon keeps its runs on the old version until it stops.

## Recover from a stalled run

Humanize watches every turn without configuration. If a CLI says nothing for 900 seconds (360 for `dsh`), Humanize checks its process. Active processes get more time, up to four more such waits. Idle processes are asked to stop, disconnected, and killed, logging each step. The turn fails with a line like this:

```text
the watchdog stopped this turn: claude is idle and has said nothing for 903s
```

If the CLI supports resuming, the next retry picks up the conversation. On `codex` and `kimi`, one server holds all of an agent's conversations, so stopping it ends that agent's other turns too.

A run waiting for your input is not stalled: see [Answer a flow's questions](/user/questions). To stop a run yourself, see [Stop a run](/user/stopping).

## Sandbox refusals {#sandbox-refusals}

| What you see | Cause | Fix |
| --- | --- | --- |
| `… cannot be held to its permission on this machine: …` or `… cannot fence the agent to its permission: it needs Landlock…`, before the first turn | The machine cannot enforce the agent's permission. Humanize refuses rather than run the agent with wider access. | On Linux, use a kernel with Landlock (5.13 or later; 6.7 or later for a role with no network) or install `bwrap`. See [The sandbox](/user/sandbox). |
| A turn fails with a line ending `(sandboxed: …)` | The coding agent CLI could not start its own sandbox on this machine. | Run the agent on a machine where its sandbox can start. |
| A command inside a run fails with `permission denied` or a refused connection | The sandbox is enforcing its rules. | Give the chat or the role a wider permission: see [Permissions](/user/permissions). |

## Fix an unresponsive remote runtime

Check a saved runtime before running work on it.

- In the app, open **Settings → Runtimes** and click **Check** on its row.
- In the terminal, run `/settings runtimes`, press <kbd>enter</kbd> on the runtime and choose `Check`.

| What you see | Cause | Fix |
| --- | --- | --- |
| `it did not answer`, or the error ssh printed | The machine was not reached. The check never asks for a password. | Make `ssh <host>` work from a terminal without a password prompt, with a key or an ssh agent. |
| `short of: …` | The machine has less than the runtime is saved to hand out. | Edit the runtime, or free the resource. |
| `could not reach <host> over ssh: …` when a run starts | The machine was not reached at the start of a run. | Check the runtime, or give it a fallback. |
| `… needs GitEnvMixin … needs git on the machine's PATH, and it has none` | The flow needs git where the work lands. | Install git on that machine. |

See [Runtimes: servers, containers and clusters](/user/runtimes).

## Find the logs

![The app writes Humanize Desktop.log, the daemon writes daemon.log, and each run writes host.log in its epic's folder](/diagrams/user-troubleshooting-1.svg)

| Log | Where | What it holds |
| --- | --- | --- |
| `Humanize Desktop.log` | `~/Library/Logs/ai.humanfia.humanize/` on macOS, `%LOCALAPPDATA%\ai.humanfia.humanize\logs\` on Windows | The app's startup, installs of `hmz`, connections and update checks. |
| `daemon.log` | `humanize-<uid>/` in the system's temporary directory | Failures of the daemon before any run. |
| `host.log` | The epic's directory, `~/.local/share/humanize/epics/<workspace>/<epic>/`: see [Files on disk](/reference/files#epic-directory) | Failures that belong to one run. |

## Good to know

- `Humanize Desktop.log` is emptied when it passes 40,000 bytes, and the app writes no secrets to it.
- `daemon.log` is never rotated.
- If you are still stuck, see [Report a problem](/user/reporting).
