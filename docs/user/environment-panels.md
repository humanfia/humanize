---
title: Files, changes and terminal
description: Browse and edit files, review and commit changes, and open a shell in the environment an agent works in, from the app or the terminal.
---

# Files, changes and terminal

An environment is the folder and machine an agent works in. You can edit its files, review and commit its changes, and open a shell in it while the agent runs.

![A chat in Humanize Desktop: the Changes, Files and Terminal panes open one after another beside the conversation](/shots/user-environment-panels-panes.svg)

*The three panes of a chat's environment.*

An environment shows panels for the capabilities it has: files, a shell, and git. To choose where a chat or an epic works, see [Environments](/user/environments).

## In the app

Humanize Desktop and the web page have the same panels.

### Open an environment

**From a chat.** Click **Details**, **Terminal**, **Changes**, or **Files** on the right of the chat bar to open that pane beside the conversation. Click the same button to close it, or open it from **More options** > **Environment**. Opening a pane brings up the folder even on old chats. A button is disabled when the environment has no shell, git repository, or files. **Details** shows chat info; see [Chat](/user/chat). Click **Open in its own view** in the pane header to expand the environment to the full page.

**From an epic.** While the epic runs, open the **Epic** panel, find **Environments**, and click **Open its environment** (or **Open its 3 environments** when it has three), or click an entry in the list. The Environments view lists every environment in the epic. Derived environments, such as git worktrees, sit nested under their parent.

![The Environments view of a running epic: a workspace with two worktrees nested under it, and the Files panel of one worktree](/shots/user-environment-panels-view.svg)

Select an environment to see its host, folder, CPUs, memory, and which capabilities (files, shell, git) the flow uses. A dot on a tab marks a panel the flow uses. Drag the divider beside a list to resize it; double-click the divider to reset it.

### Edit and search files

The **Files** panel is a code editor for the environment's folder.

![The Files panel: the explorer on the left and a Python file open in the editor](/shots/user-environment-panels-files.svg)

**Explorer.** Click a file to preview it; double-click to keep it open. Use the toolbar for **New file**, **New folder**, **Refresh**, **Collapse all**, and the **Filter** box. Right-click a row for **Rename…**, **Delete**, **Copy path**, and **Copy relative path**.

**Editor.** Edits save automatically shortly after you stop typing. The status bar shows **Saving…**, **Saved**, or **Unsaved**, and lets you change line endings, wrapping, and the current line.

**Search.** Open the **Search** tab to search across all files with **Match case**, **Use regular expression**, and **Files to include**.

| Key | What it does |
| --- | --- |
| <kbd>Cmd/Ctrl+P</kbd> | Go to file by name, or `path:line` |
| <kbd>Cmd/Ctrl+Shift+F</kbd> | Search in files |
| <kbd>Cmd/Ctrl+Shift+E</kbd> | Back to the explorer, on the open file |
| <kbd>Cmd/Ctrl+S</kbd> | Save now |
| <kbd>Cmd/Ctrl+F</kbd> | Find and replace in the file |
| <kbd>Cmd/Ctrl+G</kbd> | Go to line |
| <kbd>Cmd/Ctrl+W</kbd> | Close the tab |
| <kbd>Alt+Z</kbd> | Wrap lines |
| <kbd>F2</kbd> | Rename the selected file |

![The Search tab of the Files panel listing six matches in three files](/shots/user-environment-panels-search.svg)

**File conflicts.** Saving never overwrites external changes. If the agent changes a file you are editing, a banner offers **Compare**, **Keep mine**, or **Reload**.

![The editor with a banner saying the file changed in the environment, and the buttons Compare, Keep mine and Reload](/shots/user-environment-panels-conflict.svg)

### Review and commit changes

The **Changes** panel manages the environment's git repository. The header shows the branch and its ahead/behind count against upstream, with buttons for **View as Tree** and **Refresh**. Files are grouped under **Merge Changes**, **Staged Changes**, **Changes**, and **Untracked**.

![The Changes panel: the list of changed files on the left and a side-by-side diff of one file on the right](/shots/user-environment-panels-changes.svg)

**See a diff.** Click a file to view its diff. Use the diff toolbar to switch between side-by-side and inline views, step through changes (<kbd>F7</kbd>, <kbd>Shift+F7</kbd>), or click **Open File** to edit it in the Files panel.

**Stage, unstage, discard.** Hover over or right-click a file for **Stage Changes**, **Unstage Changes**, and **Discard Changes** (**Delete File** for an untracked file). Use a group header to act on all its files: **Stage All Changes**, **Unstage All Changes**, **Discard All Changes**, or **Delete All Untracked Files**. Discarding prompts for confirmation.

**Commit.** Type a message and press **Commit** or <kbd>Cmd/Ctrl+Enter</kbd>. Check **Amend** to replace the last commit. If nothing is staged, the panel offers to stage all changes and commit.

**Commits** lists the last 50 commits. For **Snapshots**, see [Snapshots and rewind](/user/snapshots).

![Committing from the Changes panel: a file is staged, a message is typed, Commit is pressed, and the commit appears under Commits](/shots/user-environment-panels-commit.svg)

In the file list, press <kbd>Space</kbd> to stage or unstage, <kbd>Enter</kbd> to open the diff, and <kbd>Delete</kbd> to discard. Use Ctrl/Cmd-click and Shift-click to select multiple files.

### Run a shell

The **Terminal** panel opens login shells in the environment's folder on its host machine. Click **New terminal** (the plus icon) to open another tab.

![The Terminal panel with two shell tabs; the first shows the output of git status](/shots/user-environment-panels-terminal.svg)

- Double-click a tab to rename it. Click **Close terminal** to end what runs in it; it asks first.
- Press <kbd>Cmd/Ctrl+F</kbd> to find text in the output, <kbd>Ctrl+Shift+C</kbd> to copy, and <kbd>Ctrl+Shift+V</kbd> to paste.
- Terminals run on the host. They stay running when you close the page, replay their output when you reopen it, and show the same output to every viewer.
- When a shell exits, its tab shows the exit status and a **Restart** button.

## In the terminal

In `hmz`, run `/env` to list the environments for the current chat or epic. Press <kbd>enter</kbd> to open one, or <kbd>/</kbd> to filter the list. Run `/env coder` to open the `coder` role's environment directly.

![The terminal interface: /env lists the environments, one is opened on its Files page, a file is opened in the editor, and the Changes page shows a diff](/shots/user-environment-panels-tui.svg)

An environment has up to four pages: Files, Changes, Shell, and Snapshots. Press <kbd>tab</kbd> and <kbd>shift+tab</kbd> to switch pages, and <kbd>esc</kbd> to go back. For Snapshots, see [Snapshots and rewind](/user/snapshots).

### Edit and search files

| Key | What it does |
| --- | --- |
| <kbd>enter</kbd> | Open the folder, or the file in the built-in editor |
| <kbd>backspace</kbd> | Up one folder |
| <kbd>n</kbd> / <kbd>N</kbd> | New file / new folder |
| <kbd>r</kbd> | Rename |
| <kbd>d</kbd> | Delete, after asking |
| <kbd>e</kbd> | Open in your own editor: `$VISUAL`, else `$EDITOR`, else `vi` |
| <kbd>ctrl+p</kbd> | Open a file by name |
| <kbd>?</kbd> | Search in files |

The built-in editor saves one second after you stop typing. Press <kbd>ctrl+s</kbd> to save immediately, or <kbd>esc</kbd> to save and close. If the file changes on disk while you edit, choose `reload`, `keep mine`, or `show diff`.

![The built-in editor of the terminal interface with a Python file open](/shots/user-environment-panels-tui-editor.svg)

### Review and commit changes

| Key | What it does |
| --- | --- |
| <kbd>enter</kbd> | Show the file's diff (<kbd>esc</kbd> or <kbd>q</kbd> goes back) |
| <kbd>s</kbd> | Stage |
| <kbd>u</kbd> | Unstage |
| <kbd>x</kbd> | Discard, after asking |
| <kbd>c</kbd> | Commit: a form with `message` and `amend` |
| <kbd>r</kbd> | Refresh |

![The Changes page of the terminal interface: one staged file, one changed file and one untracked file](/shots/user-environment-panels-tui-changes.svg)

Use the buttons below the list to act on all files: `Stage all`, `Unstage all`, and `Commit…`.

![The commit form of the terminal interface, with a message field and an amend switch](/shots/user-environment-panels-tui-commit.svg)

### Run a shell

The Shell page hands your terminal over to a login shell in the environment. Exit the shell to return to `hmz`. Type `~.` at the start of a line to return to `hmz` and leave the shell running; type `~~` to send a literal tilde. When you return to the page, choose a running shell or `new shell`.

## Good to know

- Every action in an environment runs as the daemon's user on the environment's machine.
- An epic's environments are writable only while the epic runs. Closed environments are read-only.
- The run history records under your name every file write, stage, discard, commit, and opened terminal, but not what you type in a terminal.
- In the app, pictures open as images, files over 5 MiB or non-UTF-8 files open read-only, and files over 20 MiB do not open. In the terminal, the built-in editor refuses both; press <kbd>e</kbd> to open them in your external editor.
- An unwatched terminal closes after 600 seconds. All terminals close when their environment closes.
- Paired devices can open terminals only when the host machine sets `envs.paired_terminals: true`. See [Security](/user/security).
