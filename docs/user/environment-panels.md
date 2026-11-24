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

The view also works from the keyboard. In the environment list, <kbd>Up</kbd>, <kbd>Down</kbd>, <kbd>Home</kbd>, and <kbd>End</kbd> move, and <kbd>Enter</kbd> or <kbd>Space</kbd> picks. On the panel tabs, <kbd>Left</kbd>, <kbd>Right</kbd>, <kbd>Home</kbd>, and <kbd>End</kbd> switch panels. On a focused divider, <kbd>Left</kbd> and <kbd>Right</kbd> resize by 16 pixels, and <kbd>Home</kbd> and <kbd>End</kbd> go to the narrowest and widest.

### Edit and search files

The **Files** panel is a code editor for the environment's folder.

![The Files panel: the explorer on the left and a Python file open in the editor](/shots/user-environment-panels-files.svg)

**Explorer.** Click a file to preview it; double-click to keep it open. Use the toolbar for **New file**, **New folder**, **Refresh**, **Collapse all**, and the **Filter** box. Right-click a row for **Open**, **New file…**, **New folder…**, **Rename…**, **Delete**, **Copy path**, and **Copy relative path**.

**Editor.** Every open file is a tab. A file you click once opens in a preview tab with an italic name; clicking another file replaces the preview. Double-click the file or its tab to keep it open. Drag tabs to reorder them.

Right-click a tab to choose **Close**, **Close others**, **Close all**, **Keep open** (on a preview tab), **Reveal in explorer** (to select the file in the explorer), or **Copy path**.

![The menu of an editor tab in the Files panel: Close, Close others, Close all, Keep open, Reveal in explorer and Copy path](/shots/user-environment-panels-tab-menu.svg)

Edits save automatically shortly after you stop typing. Closing a tab writes its edits first; if they cannot be written, the editor asks before it drops them. Use the status bar to change line endings, wrapping, and the current line, or to check the save state: **Saving…**, **Saved**, **Unsaved**, **Not saved**, **Conflict**, or **Read-only**. If a save fails, a banner shows the reason and a **Try again** button. If the file is deleted in the environment, a banner notifies you, and saving recreates the file.

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

In the explorer, with a row selected:

| Key | What it does |
| --- | --- |
| Arrow keys, <kbd>Home</kbd>, <kbd>End</kbd> | Move; <kbd>Right</kbd> and <kbd>Left</kbd> open and close a folder |
| <kbd>Enter</kbd> | Open the file and keep it open |
| <kbd>Space</kbd> | Preview the file |
| <kbd>F2</kbd> | Rename |
| <kbd>Delete</kbd> or <kbd>Cmd/Ctrl+Backspace</kbd> | Delete, after asking |
| Menu key or <kbd>Shift+F10</kbd> | Open the row's menu |

![The Search tab of the Files panel listing six matches in three files](/shots/user-environment-panels-search.svg)

**File conflicts.** Saving never overwrites external changes. If the agent changes a file you are editing, a banner offers **Compare**, **Keep mine**, or **Reload**.

![The editor with a banner saying the file changed in the environment, and the buttons Compare, Keep mine and Reload](/shots/user-environment-panels-conflict.svg)

### Review and commit changes

The **Changes** panel manages the environment's git repository. The header shows the branch and its ahead/behind count against upstream, with buttons for **View as Tree** (which becomes **View as List**) and **Refresh**. Files are grouped under **Merge Changes**, **Staged Changes**, **Changes**, and **Untracked**. The letter on a row is its status: `M` modified, `A` added, `D` deleted, `R` renamed, `C` copied, `U` conflict, `?` untracked.

![The Changes panel: the list of changed files on the left and a side-by-side diff of one file on the right](/shots/user-environment-panels-changes.svg)

**See a diff.** Click a file to view its diff. Double-click it to open it in the Files panel instead. Staged diffs are labelled **Index**, and unstaged diffs are labelled **Working Tree**. Use the diff toolbar to switch between side-by-side and inline views, step through changes (<kbd>F7</kbd>, <kbd>Shift+F7</kbd>), **Stage Changes** or **Unstage Changes**, click **Open File** to edit in the Files panel, or **Close the diff**.

| Condition | Behavior |
| --- | --- |
| Pane narrower than 560 pixels | Draws the diff inline until you choose a view. |
| File over 2 MiB | Prompts before drawing; declining leaves a **Show the diff** button. |
| Binary file or file over 8 MiB | Shows only the size before and after. |

**Stage, unstage, discard.** Hover over or right-click a file for **Stage Changes**, **Unstage Changes**, and **Discard Changes** (**Delete File** for an untracked file). Use a group header to act on all its files: **Stage All Changes**, **Unstage All Changes**, **Discard All Changes**, or **Delete All Untracked Files**. Discarding prompts for confirmation.

**Commit.** Type a message and press **Commit** or <kbd>Cmd/Ctrl+Enter</kbd>. Check **Amend** to replace the last commit. A counter beside **Amend** tracks the first line's length and changes colour past 50 and 72 characters.

If nothing is staged, the panel offers to stage all changes and commit. The panel blocks commits with `Write a commit message first.` or `There is nothing to commit.`. If files are under **Merge Changes**, the **Commit** button is disabled and the panel displays `Resolve the merge conflicts before committing.`.

**Commits** lists the last 50 commits. For **Snapshots**, see [Snapshots and rewind](/user/snapshots).

![Committing from the Changes panel: a file is staged, a message is typed, Commit is pressed, and the commit appears under Commits](/shots/user-environment-panels-commit.svg)

In the file list, press <kbd>Space</kbd> to stage or unstage, <kbd>Enter</kbd> to open the diff, and <kbd>Delete</kbd> or <kbd>Cmd/Ctrl+Backspace</kbd> to discard. Arrow keys, <kbd>Home</kbd>, <kbd>End</kbd>, <kbd>PageUp</kbd>, and <kbd>PageDown</kbd> move. Use Ctrl/Cmd-click and Shift-click to select multiple files, or <kbd>Cmd/Ctrl+A</kbd> to select all.

### Run a shell

The **Terminal** panel opens login shells in the environment's folder on its host machine. Click **New terminal** (the plus icon) to open another tab.

![The Terminal panel with two shell tabs; the first shows the output of git status](/shots/user-environment-panels-terminal.svg)

- Double-click a tab, or press <kbd>F2</kbd> on it, to rename it. <kbd>Left</kbd> and <kbd>Right</kbd> move between tabs. Click **Close terminal** to end what runs in it; it asks first.
- Press <kbd>Cmd/Ctrl+F</kbd> to find text in the output, with **Match case**, **Previous match**, and **Next match**. Press <kbd>Ctrl+Shift+C</kbd> to copy and <kbd>Ctrl+Shift+V</kbd> to paste; <kbd>Cmd/Ctrl+C</kbd> also copies while text is selected.
- Terminals run on the host. They stay running when you close the page, replay their output when you reopen it, and show the same output to every viewer.
- When a shell exits, its tab shows the exit status and a **Restart** button.

## In the terminal

In `hmz`, run `/env` to list the environments for the current chat or epic. Press <kbd>enter</kbd> to open one, or <kbd>/</kbd> to filter the list. Run `/env coder` to open the `coder` role's environment directly.

After you pick an earlier chat with `/resume`, `/env` works before you send a message: it brings the chat back up with nothing said, then opens the environments list, or the role you named. If no epic or chat environment is open, `/env` is refused with `no environment is open here`.

![The terminal interface: /env lists the environments, one is opened on its Files page, a file is opened in the editor, and the Changes page shows a diff](/shots/user-environment-panels-tui.svg)

An environment has up to four pages: Files, Changes, Terminal, and Snapshots. Press <kbd>tab</kbd> and <kbd>shift+tab</kbd> to switch pages, and <kbd>esc</kbd> to go back. For Snapshots, see [Snapshots and rewind](/user/snapshots).

### Edit and search files

| Key | What it does |
| --- | --- |
| <kbd>enter</kbd> | Open the folder, or the file in the built-in editor; a symbolic link opens what it leads to |
| <kbd>backspace</kbd> | Up one folder |
| <kbd>n</kbd> / <kbd>N</kbd> | New file / new folder |
| <kbd>r</kbd> | Rename |
| <kbd>d</kbd> | Delete, after asking |
| <kbd>e</kbd> | Open in your own editor: `$VISUAL`, else `$EDITOR`, else `vi` |
| <kbd>ctrl+p</kbd> | Open a file by name |
| <kbd>?</kbd> or <kbd>ctrl+shift+f</kbd> | Search in files |

The built-in editor saves one second after you stop typing. Press <kbd>ctrl+s</kbd> to save immediately, or <kbd>esc</kbd> to save and close. If the file changes on disk while you edit, choose **Reload**, **Keep mine**, or **Show the diff**.

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

Use the buttons below the list to act on all files: **Stage All Changes**, **Unstage All Changes**, and **Commit**.

![The commit form of the terminal interface, with a message field and an amend switch](/shots/user-environment-panels-tui-commit.svg)

### Run a shell

The Terminal page hands your terminal over to a login shell in the environment. Exit the shell to return to `hmz`. Type `~.` at the start of a line to return to `hmz` and leave the shell running; type `~~` to send a literal tilde. When you return to the page, choose a terminal left running or **New terminal**.

### Keep a pane open beside the chat

To read an agent's work next to the conversation, open a pane instead of a sheet. Press <kbd>f5</kbd> for Files, <kbd>f6</kbd> for Changes, or <kbd>f7</kbd> for Terminal. The pane opens to the right of the log for the environment of the chat or epic you are in, and refreshes when the agent finishes a turn or changes a file.

- Press <kbd>esc</kbd> to return to the prompt. The pane stays open while you keep talking to the agent.
- Press the pane's key again to go back to it, and once more to close it.
- Press <kbd>ctrl+w</kbd> to widen the pane: half the screen, then four fifths, then back to 48 columns.
- When the chat or epic has several environments, the first row names the one shown. Press <kbd>tab</kbd> for the next one. The choice is remembered for that chat or epic, across all three panes.

Each pane lists its keys at its foot.

**Files** shows a tree. <kbd>enter</kbd> opens or shuts a folder, and shows a file read-only in the pane with line numbers and colours; <kbd>backspace</kbd> returns to the tree. Press <kbd>e</kbd> to edit the file in the built-in editor, which saves as described above. <kbd>n</kbd> and <kbd>shift+n</kbd> make a file or a folder, <kbd>r</kbd> renames, <kbd>d</kbd> deletes after asking, <kbd>ctrl+p</kbd> opens a file by name, and <kbd>/</kbd> searches in files. Files over 1 MiB are not shown in the pane.

**Changes** shows the status list with the diff of the selected file under it. Move with <kbd>↑</kbd> and <kbd>↓</kbd>; the diff follows. <kbd>s</kbd> stages, <kbd>u</kbd> unstages, <kbd>x</kbd> discards after asking, <kbd>shift+s</kbd> and <kbd>shift+u</kbd> stage or unstage everything, and <kbd>c</kbd> opens the commit form with `message` and `amend`. <kbd>l</kbd> lists the commits. <kbd>p</kbd> lists the snapshots, where <kbd>enter</kbd> rewinds to one after asking. <kbd>backspace</kbd> returns to the changes.

**Terminal** shows the environment's terminals as tabs and draws the selected one live in the pane. It opens a shell if none is running and gives it the keys. While you type in it, every key goes to the shell, <kbd>esc</kbd> included. Type `~.` at the start of a line to return to the tabs and leave the shell running. On the tabs, <kbd>enter</kbd> types in the terminal again, <kbd>←</kbd> and <kbd>→</kbd> switch terminals, <kbd>n</kbd> opens another, and <kbd>x</kbd> closes one after asking. <kbd>ctrl+c</kbd> stays with `hmz`, so use the Shell page of `/env` for a program you need to interrupt.

## From the command line

`hmz env` does the same from a shell or a script, in the environments of a chat or an epic that is going. Run it in the project folder, or name the host with `-w DIR`, `--slot SLOT` or `--chat ID`.

| To | Run |
| --- | --- |
| List the environments | `hmz env list` |
| Browse and read files | `hmz env ls src`, `hmz env cat src/app.py` |
| Find a file or search for text | `hmz env find app`, `hmz env search TODO --glob '*.py'` |
| Write a file | `hmz env write notes.txt --from notes.txt` |
| Create, rename or delete | `hmz env mkdir docs`, `hmz env mv a.txt b.txt`, `hmz env rm build` |
| Review changes | `hmz env git status`, `hmz env git diff` |
| Stage and commit | `hmz env git stage src/app.py`, `hmz env git commit -m 'fix: empty input'` |
| Discard changes | `hmz env git discard src/app.py` |
| Run one command | `hmz env exec -- make test` |
| Open a shell | `hmz env term open` |

To avoid overwriting a change made since you read a file, pass the file's etag back when you write it:

```sh
ETAG=$(hmz env cat README.md --json | jq -r .etag)
hmz env write README.md --from README.md --if-match "$ETAG"
```

`hmz env rm` and `hmz env git discard` ask before they act; `--yes` skips the question. In `hmz env term open`, type `~.` at the start of a line to detach and leave the shell running, then `hmz env term list` and `hmz env term open --term ID` to come back to it.

Add `--json` to any command for one JSON document, and `--help` for everything it takes and prints. See [`hmz env`](/reference/cli#hmz-env).

## Good to know

- Every action in an environment runs as the daemon's user on the environment's machine.
- An epic's environments are writable only while the epic runs. Closed environments are read-only.
- The run history records under your name every file write, stage, discard, commit, and opened terminal, but not what you type in a terminal.
- In the app, pictures open as images, files over 5 MiB or non-UTF-8 files open read-only, and files over 20 MiB do not open. In the terminal, the built-in editor refuses both; press <kbd>e</kbd> to open them in your external editor.
- An unwatched terminal closes after 600 seconds. All terminals close when their environment closes.
- Paired devices can open terminals only when the host machine sets `envs.paired_terminals: true`. See [Security](/user/security).
