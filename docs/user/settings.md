---
title: Settings
description: Find any setting in the app or the terminal, save it, and know where it is kept.
---

# Settings

Change what Humanize remembers from the settings dialog in the app or `/settings` in the terminal.

![The settings dialog of Humanize Desktop open on its General page, with the pages listed down the side](/shots/user-settings-general.svg)

## In the app

Click the gear button **Settings** in the sidebar. You can also open **Settings**, **Usage**, and **Manage** (the Daemons page) from the daemon menu at the foot of the sidebar. Press **Close** or <kbd>esc</kbd> to close the dialog.

Settings pages fall into two groups, **App** and **Daemon**. What one folder keeps is not a page of Settings: it is that folder's own dialog, [Workspace settings](#workspace-settings). Each of the three is stored in a different place.

![App pages are kept in this browser or app, Daemon pages in the settings.toml of the daemon shown, and a folder's Workspace settings with that folder](/diagrams/user-settings-1.svg)

| Group | Page | What it holds | Guide |
| --- | --- | --- | --- |
| App | **Themes** | Colours and pictures of the page | [Themes and language](/user/themes) |
| App | **Daemons** | Machines this page reaches, and the one it shows | [Connect to other machines](/user/daemons) |
| App | **Notifications** | What every daemon tells you | [Notifications](/user/notifications) |
| App | **Language** | What the page is written in | [Themes and language](/user/themes) |
| Daemon | **General** | Display and reporting | below |
| Daemon | **Accounts** | Credentials agents run as | [Accounts](/user/accounts) |
| Daemon | **Nous** | Who takes a turn, and where it goes once it fails | [Nous](/user/nous) |
| Daemon | **Runtimes** | Machines environments run on | [Runtimes](/user/runtimes) |
| Daemon | **Backup** | Git repositories epics go to | [Back up to git](/user/backups) |
| Daemon | **Usage** | What everything on the daemon spent, by day and flow | [Cost and usage](/user/usage) |

Each page has a direct address, `#/settings/<page>`, listed in [Page addresses and shortcuts](/reference/web).

### Which daemon the pages are of

The pages under **Daemon** always read and write the daemon the app shows. Its name is stated in a line at the top of each of them, **Daemon** then **Local** or the remote daemon's name; that line is not a control.

A daemon is chosen in two places only: the daemon menu at the foot of the sidebar, and the **Daemons** page, where the daemon shown is marked **Current** and every other has a **Switch** button. Either one switches the whole app: the sidebar, every view, and these pages. No other page, form, or menu offers a daemon. See [Connect to other machines](/user/daemons).

### Save and copy to other daemons

App pages save as you change them. On the General page, press **Save**; the button changes to **Saved**.

![Ticking List in sidebar on the General page, pressing Save, and the button reading Saved](/shots/user-settings-save.svg)

Use **Batch apply** on General, Nous, Runtimes, and Backup to copy the page's settings to other daemons. Tick the target daemons or **All**, then press **Apply**; each daemon reports **Applied** or its error. Batch apply adds and replaces items, and never removes a nous or a runtime on the target daemon. It is disabled on Accounts so secrets stay on their machine. See [Connect to other machines](/user/daemons).

### General

| Setting | Control | What it does |
| --- | --- | --- |
| **Details** | **Tool calls and thinking** | Shows a turn's tool calls and thinking, not only its answers. Off by default. |
| **Harness sessions** | **List in sidebar** | Lists each coding agent's own sessions after a folder's chats. Off by default. See [Continue sessions from other CLIs](/user/harness-sessions). |
| **Error reports** | **Not set**, **On**, **Off** | Sends reports when Humanize crashes. See [Report a problem](/user/reporting). |

### Workspace settings

Each folder has a settings dialog of its own, **Workspace settings**. Open it from the sidebar: point at the folder's heading, click **Group and sort**, and choose **Workspace settings**; or right-click the heading and choose **Workspace settings** (or **Usage**, which opens the same dialog on its Usage page). The dialog is about that one folder: its name and full path are stated at the top, with **Missing** if its directory was deleted on disk, and nothing in it picks another folder or a daemon.

| Page | What it holds | Guide |
| --- | --- | --- |
| **Setup** | What the folder was last set up with | below |
| **Usage** | What the folder spent, by day and flow | [Cost and usage](/user/usage) |
| **Archived chats** | Chats of the folder that were put away | [Organise chats](/user/manage-chats) |

Open **Setup** to see what a folder remembers: its **Default flow**, and every flow **Configured** there. Press **Forget** and confirm to erase how every flow was set up in that folder. If the folder has no epics or chats, it also leaves the folder list.

![Pressing Forget on the Setup page, confirming, and the page answering Forgotten](/shots/user-settings-forget.svg)

**Workspace settings** on the **No folder** heading opens the dialog for chats that have no folder. It holds **Archived chats** alone.

## In the terminal

Type `/settings` or press <kbd>F2</kbd> to open a screen of eleven cards in the same groups as the app:

| Group | Pages | Where it is kept |
| --- | --- | --- |
| **App** | Themes, Daemons, Notifications, Language | On this machine, for you |
| **Daemon** | General, Accounts, Nous, Runtimes, Backup, Usage | On the daemon |
| **Workspace** | Workspace | With the directory `hmz` was started in |

Type `/settings <page>` (for example, `/settings themes`) to open a page directly. See [Themes and language](/user/themes) for the Themes and Language pages.

![The /settings screen in the terminal: nine cards, each with its name, what it holds and a summary](/shots/user-settings-terminal.svg)

| Key | What it does |
| --- | --- |
| <kbd>enter</kbd> | Open the card or the row under the cursor |
| <kbd>esc</kbd> or <kbd>backspace</kbd> | Go back to the cards; <kbd>esc</kbd> on the cards closes |
| <kbd>tab</kbd> | Move between the list and the buttons |
| <kbd>/</kbd> | Search a page that is a list |

You can also click cards, rows, and the breadcrumb path across the top.

### Save held changes

Changes are held until you save them, and any card with pending edits shows `Unsaved`. Themes and Language are the exception: each is kept as soon as you choose it. Press <kbd>tab</kbd> to reach **Save**, then press <kbd>enter</kbd> to save held changes across all pages. If you leave with unsaved changes, Humanize asks whether to save them.

![Opening General, turning Details on, going back to a card marked unsaved, and saving](/shots/user-settings-terminal-held.svg)

Creating or signing in to an account, saving or checking a runtime, and changing daemons apply right away instead of being held. Rows that cannot apply to the current session show `on next launch` or `in the next chat`.

### General

| Row | Values | What it does |
| --- | --- | --- |
| `Details` | `On`, `Off` | Show every tool call and all thinking |
| `When $name is both` | `native`, `flow` | Choose what `$<name>` starts in a chat when a skill and a flow share the name. See [Skills](/user/skills). |
| `Harness sessions` | `On`, `Off` | List each coding agent's own sessions in `/resume` |
| `Error reports` | `On`, `Off` | Send error reports to Humanize. Reads `Not set` until you choose. |
| `What is sent` | | Show what reports include and what they never include |

### Workspace

Open `/settings workspace` to manage the directory `hmz` was started in.

![The Workspace page in the terminal: Default flow, Chat agent, Archived chats and Forget](/shots/user-settings-terminal-workspace.svg)

| Row | What it does |
| --- | --- |
| `Flow` | Read-only: the flow last set up here. Change it with `/flow`. |
| `Default agent` | The agent a new chat here talks to |
| `Archived chats` | Opens the chats archived here; pick one to restore it |
| `Forget` | Set to `On` and save to clear what this directory remembers for every flow |

## From the command line

`hmz settings` reads and writes the same settings through the daemon, for scripts and agents.

```sh
hmz settings get                      # every setting, one per line
hmz settings get details              # one value
hmz settings set details on           # prints Saved.
hmz settings set chat claude/claude-opus-4-1 -w ~/project
hmz settings forget -w ~/project      # Forgotten. or Nothing to forget.
```

Add `--json` for one JSON object. `hmz settings set --help` lists every setting it writes, including listeners, STUN and TURN servers and [backup targets](/user/backups). See the [CLI reference](/reference/cli#hmz-settings).

## Where settings are kept

- **App pages** are stored in the browser or the desktop app window. Each browser and device keeps its own values, and clearing site data resets them.
- **Daemon pages and Workspace settings**, along with what you save in `/settings`, are stored by the daemon in `~/.config/humanize/settings.toml` and shared across all interfaces connected to that daemon. See [settings.toml](/reference/settings) for the keys. Account secrets are kept apart from that file, and both Usage pages and Archived chats only read what epics and chats recorded.
- Notifications are stored per browser in the app, and in `settings.toml` for the terminal. The terminal's theme, appearance and language are stored under `tui` in the same file.

## Good to know

- Once **Error reports** is set to **On** or **Off**, you cannot return it to **Not set**.
- Setting the `HUMANIZE_SENTRY` environment variable overrides the saved error-report choice for that run, and the terminal's General page notes the override.
- In the terminal, saving `Forget` at the same time as a changed `Default agent` forgets both and does not write the agent.
- Forgetting a folder keeps its chats, epics, and files intact.
- An older address of a folder's page in Settings, such as `#/settings/workspace`, opens that folder's Workspace settings. An address with `daemon=<name>` in its query switches the whole app to that daemon.
- On a narrow window, the page list moves to a strip across the top of either dialog.
