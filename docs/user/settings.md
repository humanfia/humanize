---
title: Settings
description: Find any setting in the app or the terminal, save it, and know where it is kept.
---

# Settings

Change what Humanize remembers from the settings dialog in the app or `/settings` in the terminal.

![The settings dialog of Humanize Desktop open on its General page, with the pages listed down the side](/shots/user-settings-general.svg)

## In the app

Click the gear button **Settings** in the sidebar. You can also open **Settings**, **Usage**, and **Manage** (the Daemons page) from the daemon menu at the foot of the sidebar, or open a folder's **Settings** (its Setup page) and **Usage** from the folder menu. Press **Close** or <kbd>esc</kbd> to close the dialog.

Settings pages fall into three groups, each stored in a different place.

![Three groups of pages: App pages are kept in this browser or app, Daemon pages in the picked daemon's settings.yaml, Workspace pages with one folder of that daemon](/diagrams/user-settings-1.svg)

| Group | Page | What it holds | Guide |
| --- | --- | --- | --- |
| App | **Themes** | Colours and pictures of the page | [Themes and language](/user/themes) |
| App | **Daemons** | Machines this page reaches | [Connect to other machines](/user/daemons) |
| App | **Notifications** | What every daemon tells you | [Notifications](/user/notifications) |
| App | **Language** | What the page is written in | [Themes and language](/user/themes) |
| Daemon | **General** | Display and reporting | below |
| Daemon | **Accounts** | Credentials agents run as | [Accounts](/user/accounts) |
| Daemon | **Nous** | Who takes a turn, and where it goes once it fails | [Nous](/user/nous) |
| Daemon | **Runtimes** | Machines environments run on | [Runtimes](/user/runtimes) |
| Daemon | **Backup** | Git repositories epics go to | [Back up to git](/user/backups) |
| Daemon | **Usage** | Spending by day and flow | [Cost and usage](/user/usage) |
| Workspace | **Setup** | What a folder was last set up with | below |
| Workspace | **Archived chats** | Chats of a folder that were put away | [Organise chats](/user/manage-chats) |

Each page has a direct address, `#/settings/<page>`, listed in [Page addresses and shortcuts](/reference/web).

### Pick the daemon and the folder

Use the **Daemon** select at the top of any Daemon or Workspace page to pick **Local** or a remote daemon. The page reads and writes that daemon directly, without switching the rest of the app to it.

On Workspace pages, use the **Workspace** select to pick a folder on that daemon; its full path appears beside the control. If a folder's directory was deleted on disk, it is marked **Missing**, but you can still select it to inspect or forget its setup. Switching daemons clears the selected folder.

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

### Workspace setup and Forget

Open **Setup** to see what a folder remembers: its **Directory**, its **Default flow**, and every flow **Configured** there. Press **Forget** and confirm to erase how every flow was set up in that folder. If the folder has no epics or chats, it also leaves the folder list.

![Pressing Forget on the Setup page, confirming, and the page answering Forgotten](/shots/user-settings-forget.svg)

## In the terminal

Type `/settings` to open a screen of nine cards: General, Notifications, Daemons, Accounts, Nous, Runtimes, Backup, Workspace, and Usage. Type `/settings <page>` (for example, `/settings workspace`) to open a page directly. The terminal does not have Themes or Language pages.

![The /settings screen in the terminal: nine cards, each with its name, what it holds and a summary](/shots/user-settings-terminal.svg)

| Key | What it does |
| --- | --- |
| <kbd>enter</kbd> | Open the card or the row under the cursor |
| <kbd>esc</kbd> or <kbd>backspace</kbd> | Go back to the cards; <kbd>esc</kbd> on the cards closes |
| <kbd>tab</kbd> | Move between the list and the buttons |
| <kbd>/</kbd> | Search a page that is a list |

You can also click cards, rows, and the breadcrumb path across the top.

### Save held changes

Changes are held until you save them, and any card with pending edits shows `unsaved`. Press <kbd>tab</kbd> to reach **Save**, then press <kbd>enter</kbd> to save held changes across all pages. If you leave with unsaved changes, Humanize asks whether to save them.

![Opening General, turning Details on, going back to a card marked unsaved, and saving](/shots/user-settings-terminal-held.svg)

Creating or signing in to an account, saving or checking a runtime, and changing daemons apply right away instead of being held. Rows that cannot apply to the current session show `takes effect on next launch` or `takes effect on next chat`.

### General

| Row | Values | What it does |
| --- | --- | --- |
| `Details` | `on`, `off` | Show every tool call and all thinking |
| `Chat prefers for $` | `native`, `flow` | Choose what `$<name>` starts in a chat when a skill and a flow share the name. See [Skills](/user/skills). |
| `Harness sessions` | `on`, `off` | List each coding agent's own sessions in `/resume` |
| `Error reports` | `on`, `off` | Send error reports to Humanize. Reads `not set` until you choose. |
| `What is sent` | | Show what reports include and what they never include |

### Workspace

Open `/settings workspace` to manage the directory `hmz` was started in.

![The Workspace page in the terminal: Default flow, Chat agent, Archived chats and Forget](/shots/user-settings-terminal-workspace.svg)

| Row | What it does |
| --- | --- |
| `Default flow` | Read-only: the flow last set up here. Change it with `/flow`. |
| `Chat agent` | The agent a new chat here talks to |
| `Archived chats` | Opens the chats archived here; pick one to restore it |
| `Forget` | Set to `on` and save to clear what this directory remembers for every flow |

## Where settings are kept

- **App pages** are stored in the browser or the desktop app window. Each browser and device keeps its own values, and clearing site data resets them.
- **Daemon and Workspace pages**, along with what you save in `/settings`, are stored by the daemon in `~/.hmz/settings.yaml` and shared across all interfaces connected to that daemon. See [settings.yaml](/reference/settings) for the keys. Account secrets are kept apart from that file, and Usage and Archived chats only read what epics and chats recorded.
- Notifications are stored per browser in the app, and in `settings.yaml` for the terminal.

## Good to know

- Once **Error reports** is set to **On** or **Off**, you cannot return it to **Not set**.
- Setting the `HUMANIZE_SENTRY` environment variable overrides the saved error-report choice for that run, and the terminal's General page notes the override.
- In the terminal, saving `Forget` at the same time as a changed `Chat agent` forgets both and does not write the agent.
- Forgetting a folder keeps its chats, epics, and files intact.
- When no folder exists yet, Workspace pages show **No folder yet.** and offer **New chat**.
- On a narrow window, the page list moves to a strip across the top of the dialog.
