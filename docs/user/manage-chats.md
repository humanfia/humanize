---
title: Organise chats
description: Rename, fork, pin, archive, delete and find your chats from the app, the terminal and the command line.
---

# Organise chats

Humanize keeps every chat until you delete it. You can rename, fork, pin, archive, restore, delete, and search your chats. The daemon stores them, so changes on one interface appear on the others.

![The More options button of a chat's row is clicked, Rename is picked, a new title is typed, and the row shows it](/shots/user-manage-chats-rename.svg)

## In the app

Humanize Desktop and the web page work the same way.

### Open a chat's menu

Hover over a chat in the sidebar and click **More options** (`…`), or right-click the row. You can also click **More options** on the top bar of an open chat. Results in **Search** have the same menu, except for **Rename**.

![A chat's menu: Open, Pin, Mark as unread, Rename, New chat like it, Fork, Copy link, Copy first message, Copy ID, Upload, Archive, Delete](/shots/user-manage-chats-menu.svg)

| Item | What it does |
| --- | --- |
| **Open** | Opens the chat. |
| **Pin** / **Unpin** | Lists the chat first, under **Pinned**. |
| **Mark as unread** / **Mark as read** | Shows or hides a dot on the row. |
| **Rename** | Turns the title into an editable field. |
| **New chat like it** | Opens a new chat with the same folder and agent. |
| **Fork** | Copies the chat into a new chat and opens the copy. |
| **Copy link**, **Copy first message**, **Copy ID** | Copies the value to the clipboard. |
| **Upload** | Backs the chat up now. See [Back up to git](/user/backups). |
| **Archive** / **Unarchive** | Removes the chat from the list, or restores it. |
| **Delete** | Permanently deletes the chat after confirmation. |

### Rename a chat

1. Pick **Rename** in the menu, or click the title on the bar of the open chat.
2. Type the new title and press <kbd>enter</kbd> or click elsewhere to save it. Press <kbd>esc</kbd> to keep the old title.

A title is at most 240 characters. Until you rename a chat, its title is the first line of its first message.

### Fork a chat

Select **Fork** to create a new chat in the same folder. The new chat continues from a copy of the conversation so far, using the same agent, permission, and place of work. The original chat stays unchanged. You cannot fork a chat while its turn is open.

### Pin and mark unread

Select **Pin** to keep a chat at the top of the list under **Pinned**. Select **Mark as unread** to show a dot on the row until you open the chat. [Notifications](/user/notifications) mark rows unread the same way.

![The sidebar with one chat under Pinned and a dot on a chat marked unread](/shots/user-manage-chats-pinned.svg)

Each row also shows the state of its chat. It displays `Running` while the agent answers and `Failed` if the chat fails. When the agent waits for your answer, a dot appears that reads `Awaiting input` on hover. A resting chat shows only its title. On touch screens, every row also shows the chat's age.

### Archive and restore

Select **Archive** to remove a chat from the sidebar and from Search. Nothing else about the chat changes.

To view and restore archived chats:

1. Open **Settings**, then click **Archived chats** under **Workspace**.
2. Pick the **Daemon** if you have several, then pick the folder in **Workspace**.
3. Click a title to read the chat, **Unarchive** to restore it to the list, or **Delete** to remove it.

Chats started with **No folder** appear under the **No folder** heading below the folder's archived chats. This heading appears for any selected folder, and when the daemon has no folders.

An open archived chat also has an **Unarchive** button on its top bar.

![Settings, Archived chats: two archived chats of the folder shop and, under No folder, one started without a folder, each with Unarchive and Delete](/shots/user-manage-chats-archived.svg)

### Delete a chat

Select **Delete** to open a confirmation dialog that names the chat. Click **Delete** to confirm or **Cancel** to keep it.

![The Delete chat dialog names the chat and says it cannot be undone, with Cancel and Delete](/shots/user-manage-chats-delete.svg)

::: warning
Deleting removes the chat's record and its saved sessions, and cannot be undone. Any git worktree the chat used stays on disk.
:::

You cannot delete a chat while its turn is open. Stop the turn or wait for it to finish.

### Group and sort the list

Hover over any group heading in the sidebar and click **Group and sort**.

![Group and sort is opened from a heading, Group by is set to Date, and the list is regrouped under Today with the folders last](/shots/user-manage-chats-group-sort.svg)

| Menu | Choices | Default |
| --- | --- | --- |
| **Group by** | **Folder**, **Date** (**Today**, **Yesterday**, **Last 7 days**, **Last 30 days**, **Older**), **None** (one group, **All**) | **Folder** |
| **Sort by** | **Last updated**, **Created** | **Last updated** |
| **Show** | **Chats**, **Epics** | both |

Click **Reset to defaults** to restore all three settings. Pinned rows always appear first. A group shows 20 rows; click **Show N more** under it to see the rest.

### Work with folders

When you group by folder, each folder appears as a heading above its chats and epics. Chats started without a folder appear under **No folder**.

- Click the heading to collapse or expand the group.
- Click `+` on the heading to start a new chat in that folder.
- Right-click the heading to open the folder's menu.

![A folder's menu: New chat here, New epic here, Search here, Copy path, Collapse, Settings, Usage](/shots/user-manage-chats-folder-menu.svg)

If a folder contains no chats and no epics, its menu includes **Forget**, which removes the folder from the list. When you group by date or not at all, folders appear at the bottom under **Folders** with the same menu; click one to start a new chat in it. A folder whose directory was deleted is tagged `missing`: its chats can still be read, but nothing new starts there.

### Search for chats

1. Click **Search** in the sidebar or press <kbd>⌘K</kbd> (<kbd>ctrl+K</kbd> on Windows and Linux).
2. Type to find chats by title, first message, or ID. Select the **Chats** tab to exclude epics.
3. Press <kbd>↑</kbd> and <kbd>↓</kbd> to move through results, and press <kbd>enter</kbd> to open one.
4. Right-click a result, or press <kbd>option+enter</kbd> (<kbd>alt+enter</kbd>), to open its menu.

Select **Search here** in a folder's menu to search only that folder. For search filters and epics, see [History and search](/user/history).

![Search is opened with cmd+K and lists every chat; typing catalogue leaves the two chats whose title says it](/shots/user-manage-chats-search.svg)

## In the terminal

`hmz` opens directly into a chat. To manage chats in the current directory:

1. Type `/resume` inside a chat and press <kbd>enter</kbd>. You see the directory's chats, newest first, with the chat you are in ticked once it has a message. (Outside a chat, `/resume` resumes an epic instead; see [Resume a run](/user/resuming).)
2. Press <kbd>enter</kbd> on a chat to continue it, <kbd>/</kbd> to search the list, or <kbd>m</kbd> to open the menu for the selected chat.

![/resume lists the chats of the directory; m opens one chat's menu; archive takes the chat out of the list](/shots/user-manage-chats-resume.svg)

| Menu row | What it does |
| --- | --- |
| `rename` | Prompts for a new title. |
| `fork` | Creates a new chat continuing from this one and switches to it. |
| `archive` | Removes the chat from the list. |
| `upload` | Backs the chat up. Shown only when a backup target is set. |
| `delete` | Prompts `Delete <title>?` with `keep` selected first, then deletes it permanently. |
| `copy id` | Copies the chat's ID. |

If you archive or delete the active chat, closing the list starts a new chat.

To restore an archived chat, type `/settings workspace`, open **Archived chats**, and press <kbd>enter</kbd> on the chat. The list stays open so you can restore several chats at once.

![Archived chats in the terminal: two archived chats of the directory, each put back with enter](/shots/user-manage-chats-archived-terminal.svg)

## From the command line

Run `hmz chat` to manage chats in the current directory by ID without starting a turn.

```sh
hmz chat --list
```

![hmz chat --list prints three chats, one per line: ID, state, title](/shots/user-manage-chats-cli-list.svg)

Each line prints the chat's ID, state, and title. The state is `turn` while the agent answers, `asking` while it waits for you, `failed`, or `ready`.

```sh
hmz chat --rename 20261121T041901.042Z-f214a8 "Discount codes"
```

![hmz chat --rename with an ID and a title prints the chat's line with the new title](/shots/user-manage-chats-cli-rename.svg)

| Option | What it does | Prints |
| --- | --- | --- |
| `--list` | Lists the chats, newest first. | One line per chat. |
| `--list --archived` | Lists only the archived chats. | One line per chat. |
| `--rename CHAT TITLE` | Sets a new title for the chat. | The chat's line. |
| `--fork CHAT` | Creates a new chat that continues from this one. | The new chat's ID. |
| `--archive CHAT` | Removes the chat from the lists. | The chat's line. |
| `--unarchive CHAT` | Restores an archived chat. | The chat's line. |
| `--delete CHAT` | Permanently deletes the chat after asking `[y/N]`. | Nothing. |
| `--delete CHAT --yes` | Deletes the chat without asking. | Nothing. |

Pass one action option at a time. Without `--yes`, `--delete` prompts only in an interactive terminal; in a script, it deletes nothing and exits with status 1. To continue a chat by ID, run `hmz chat --resume` (see [Chat with an agent](/user/chat)).

## Good to know

- Pins, unread marks, **Group and sort** settings, and collapsed groups stay in the current browser, which keeps at most 200 pins and 200 unread marks. Other browsers, the terminal, and the command line do not see them. The daemon stores titles, forks, archives, and deletions, so every connected interface shows them.
- The terminal and command line list chats for the current directory only. The app lists all folders.
- List lines in the terminal and on the command line show at most 60 characters of a title.
- An archived chat appears only on the **Archived chats** page, under its folder or under **No folder**, never under **Pinned**.
- You cannot fork a chat if its coding agent stores the conversation outside the chat's own record.
- You can list standalone sessions from other coding CLIs alongside your chats. See [Continue sessions from other CLIs](/user/harness-sessions).
