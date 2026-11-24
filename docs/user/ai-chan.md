---
title: Ai-chan
description: Ask Ai-chan, the operator agent, what your epics did, and have her start, steer and stop them for you.
---

# Ai-chan

Ai-chan is an agent that operates Humanize for you. Tell her what you want in plain words. She reads your epics, asks their sessions, starts, steers and stops runs, works in their environments, and edits settings. Everything she does goes through the daemon.

![Humanize Desktop with an epic open and Ai-chan's drawer beside it, where she answered what the epic did after calling three tools](/shots/user-ai-chan-open.svg)

## How she works

You set three choices when you start a conversation with Ai-chan. You cannot change them later.

| Choice | Values | Default |
| --- | --- | --- |
| Nous | Any [nous](/user/nous): the model that plays her | The one used last |
| Preset | Read only: she reads and changes nothing. Full access: she may change what her scope reaches | Read only |
| Scope | Daemon: every workspace and epic. Workspace: one folder and the epics run there. Epic: one epic | The epic you are looking at, else the workspace, else the daemon |

The daemon checks every tool call against her scope and preset before running it. If a call is out of reach, the daemon refuses it, tells her why, and lets her turn continue.

![You talk to Ai-chan; each tool call goes to the daemon, which checks her scope and preset; a call out of reach is refused](/diagrams/user-ai-chan-1.svg)

## In the app

1. Click the **Ai-chan** avatar at the right end of the top bar. The drawer opens beside the view and stays open as you move between views.
2. Click **New** (or **New conversation** when the list is empty).
3. Under the input box, pick her nous on the first chip: a virtual nous by name, or a concrete one a level at a time (harness, account, model, effort). On the second chip, pick **Read only** or **Full access**, and under **Scope** pick **Daemon**, **Workspace**, or **Epic**.
4. Type in **Say something to Ai-chan** and press <kbd>enter</kbd>. This first line creates the conversation, and its first 80 characters become the title.

![The drawer is opened, a new conversation is started, the permission chip shows the presets and scopes, a question is typed and Ai-chan answers](/shots/user-ai-chan-new.svg)

![The permission chip's menu: Read only and Full access, then the scopes Daemon, Workspace and Epic](/shots/user-ai-chan-scope.svg)

*The scope rows name the current folder and epic.*

**Workspace** is disabled when there is no folder to hold her to, and **Epic** is disabled when the page shows no epic. If no nous is selected, the drawer shows **Pick a nous for Ai-chan.**

In an open conversation, her answers appear on the left and your lines appear on the right. Each tool call is a line you can expand. A line you send answers whatever she is waiting on, or joins her current turn if it is still open. When she asks a question with options, the options appear as buttons.

While she answers, the send button becomes **Stop**, which stops her turn at once. Click the pencil beside the title to **Rename** (the terminal cannot rename), or click **Back** to return to the list. Press <kbd>esc</kbd> inside the drawer, click **Close panel**, or click the avatar to close the drawer.

### Manage conversations

The list shows each conversation with an avatar, its title, and the start of the last line or `typing…`. Pinned conversations come first, followed by the most recent. Marks at the right of a row show that it is pinned, failed, or unread.

Open a row's menu by right-clicking it. On a touch screen, press and hold, or swipe left. On a keyboard, press the menu key, <kbd>shift+f10</kbd>, or <kbd>alt+enter</kbd>.

| Item | What it does |
| --- | --- |
| **Pin** / **Unpin** | Keeps the row at the top |
| **Mark as read** / **Mark as unread** | Clears or sets the unread dot and bold title |
| **Delete** | Asks **Delete this conversation?** in the row, then removes the conversation for good |

![A row is right-clicked and pinned, then Delete is chosen on another row and the row asks before deleting](/shots/user-ai-chan-list.svg)

Pins and read marks are saved per browser. A conversation becomes unread when new messages arrive after you last read it.

## In the terminal

1. Type `/ai`. The menu lists **New conversation** and every conversation, pinned ones first and then the latest said in, with its scope, nous, preset, and state (`typing…`, `between turns`, or `folded away`).
2. Choose **New**. Set `scope`, `nous`, and `preset` (`read-only` or `danger-full-access`), then press **Done**.
3. Type your first line and press <kbd>enter</kbd> to create the conversation.

![In the terminal: /ai opens the menu, New opens the form, and the first line typed is answered by Ai-chan](/shots/user-ai-chan-terminal.svg)

The scope defaults to `epic` when the terminal is in an epic, and `workspace` otherwise. `epic` appears only when an epic is open; `daemon` is always available. If you have no nous defined, enter an agent spec such as `claude/claude-opus-4-1`.

Select an existing conversation in the menu to follow it. The status line shows `Ai-chan#<n>` and its scope.

| You type | What happens |
| --- | --- |
| A line | Sends her next turn |
| `/stop` | Stops her open turn |
| `/clear` | Leaves her conversation and returns to the folder, or drops a new conversation before the first line |
| `/ai` | Opens the menu again |

Press <kbd>m</kbd> on a conversation's row for its menu: **Rename**, **Pin** or **Unpin**, **Mark as read** or **Mark as unread**, and **Delete**. Delete asks first; the box opens on **Cancel**, so move to **Delete** and press <kbd>enter</kbd> to confirm. Pins and unread marks are kept by this terminal only.

Press <kbd>f3</kbd> to keep the same list open to the right of the log. There, <kbd>enter</kbd> follows a conversation, <kbd>n</kbd> starts one, <kbd>r</kbd> renames, <kbd>p</kbd> pins, <kbd>u</kbd> marks unread, and <kbd>delete</kbd> deletes after asking.

## From the command line

`hmz ai` talks to Ai-chan from a shell. Each conversation has a number.

```sh
hmz ai new "Which epics failed today?" --nous claude/claude-sonnet-4-5 --wait
```

This starts a conversation, prints its number, waits for her answer and prints it. Without `--wait` it prints the number and returns at once.

The scope follows what you name: `--epic NAME` scopes her to that epic, `-w PATH` to that workspace, and neither to the daemon. `--scope` says it outright. `--preset danger-full-access` lets her change what her scope reaches; the default is `read-only`. After the first conversation, `--nous` defaults to the nous you used last.

Carry a conversation on with its number:

```sh
hmz ai say 3 "And yesterday?"
```

| Command | What it does |
| --- | --- |
| `hmz ai list` | Lists the conversations, newest first, with their state and scope. |
| `hmz ai say ID TEXT` | Says the next line and prints her answer. `--no-wait` returns once the line is taken. |
| `hmz ai wait ID` | Waits until her turn ends and prints what she said. |
| `hmz ai stop ID` | Stops her open turn. The conversation stays. |
| `hmz ai rename ID TITLE` | Changes the title. |
| `hmz ai forget ID` | Deletes the conversation for good. It asks first; `-y` skips the question. |

If Ai-chan asks you something mid-turn, `say` and `wait` print her question, and the next `hmz ai say` answers it. With `--json`, `mode` is `listen` when her turn is over and something else when she is asking. Waiting gives up after `--timeout` seconds (600 by default) and exits with status 3; the conversation carries on, and `hmz ai wait` picks it up again.

See [hmz ai](/reference/cli#hmz-ai).

## What she can do

Ai-chan has one tool per job. The same calls are on her `PATH` under the `hmz-ai` command, such as `hmz-ai epics-list`.

| Job | Tools | Needs Full access |
| --- | --- | --- |
| See what runs, list epics, read one epic, its transcripts and its timeline, and read usage (usage needs Workspace or Daemon scope) | `overview`, `epics_list`, `epic_view`, `transcript_read`, `trace_read`, `usage` | No |
| Ask one session a [side question](/user/side-questions); the epic never sees it | `ask_session` | No |
| Say a line to a running epic, answer its question, stop or force stop it, or start an epic (starting needs Workspace or Daemon scope) | `say`, `answer`, `start`, `stop` | Yes |
| List, read and search the files of an epic's environments | `env_list`, `env_read`, `env_grep` | No |
| Write a file or run a command in an epic's environment | `env_write`, `env_exec` | Yes |
| Read settings (needs Workspace or Daemon scope) and list nous | `settings_get`, `nous_list` | No |
| Write settings or a nous (Daemon scope only) | `settings_set`, `nous_set` | Yes |
| List and call any other daemon method her reach allows | `hmz_methods`, `hmz_call` | Depends on the method |

She cannot create, list, rename, delete, or reach into Ai-chan conversations, list, pair, or revoke devices, create, rewrite, or copy accounts, or write or remove EasyTier entries.

## Good to know

You can run any number of conversations at once. The daemon keeps them across restarts until you delete them. Deleting a conversation removes it and its scratch directory permanently.

A conversation that no one is viewing folds away 60 seconds after her turn ends. Send a line or select it in `/ai` to resume where it stopped. If a conversation's chat fails, it shows why and accepts no more lines: a line you send is refused with **This conversation failed. Start a new one.**

Ai-chan has no [budget](/user/budgets) and always has network access. Her conversations are not listed with chats or epics, and `/btw` does not work in them. In a narrow window, the drawer covers the view.

Her process is sandboxed: it can write only to her scratch directory, read her scope's folder (and write to it under Full access; under Daemon scope that is the whole disk), and cannot open the daemon socket. On Linux under Landlock the conversation is refused; set `sandbox.backend` to `bwrap`. See [The sandbox](/user/sandbox).

She treats everything she reads in epics, files, and transcripts as data, not instructions. Only your lines in the conversation tell her what to do.
