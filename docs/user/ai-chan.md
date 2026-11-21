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
3. Under the input box, pick her nous on the first chip. On the second chip, pick **Read only** or **Full access**, and under **Scope** pick **Daemon**, **Workspace**, or **Epic**.
4. Type in **Say something to Ai-chan** and press <kbd>enter</kbd>. This first line creates the conversation, and its first 80 characters become the title.

![The drawer is opened, a new conversation is started, the permission chip shows the presets and scopes, a question is typed and Ai-chan answers](/shots/user-ai-chan-new.svg)

![The permission chip's menu: Read only and Full access, then the scopes Daemon, Workspace and Epic](/shots/user-ai-chan-scope.svg)

*The scope rows name the current folder and epic.*

**Workspace** is disabled when there is no folder to hold her to, and **Epic** is disabled when the page shows no epic. If no nous is selected, the drawer shows **Pick a nous for Ai-chan.**

In an open conversation, her answers appear on the left and your lines appear on the right. Each tool call is a line you can expand. A line you send answers whatever she is waiting on, or joins her current turn if it is still open. When she asks a question with options, the options appear as buttons.

While she answers, the send button becomes **Stop**, which stops her turn at once. Click the pencil beside the title to **Rename**, or click **Back** to return to the list. Press <kbd>esc</kbd> inside the drawer, click **Close panel**, or click the avatar to close the drawer.

### Manage conversations

The list shows each conversation with an avatar, its title, and the start of the last line or `typing…`. Pinned conversations come first, followed by the most recent.

Open a row's menu by right-clicking it. On a touch screen, press and hold, or swipe left. On a keyboard, press the menu key, <kbd>shift+f10</kbd>, or <kbd>alt+enter</kbd>.

| Item | What it does |
| --- | --- |
| **Pin** / **Unpin** | Keeps the row at the top |
| **Mark as read** / **Mark as unread** | Clears or sets the unread dot and bold title |
| **Delete** | Asks **Delete this conversation?** in the row, then removes the conversation for good |

![A row is right-clicked and pinned, then Delete is chosen on another row and the row asks before deleting](/shots/user-ai-chan-list.svg)

Pins and read marks are saved per browser. A conversation becomes unread when new messages arrive after you last read it.

## In the terminal

1. Type `/ai`. The menu lists **New** and every conversation, newest first, with its scope, nous, preset, and state (`answering`, `between turns`, or `folded away`).
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

To delete a conversation, press <kbd>m</kbd> on its row in the menu, choose `forget`, and choose `forget` again to confirm.

## What she can do

Ai-chan has one tool per job. The same calls are on her `PATH` under the `hmz-ai` command, such as `hmz-ai epics-list`.

| Job | Tools | Needs Full access |
| --- | --- | --- |
| See what runs, list epics, read one epic, its transcripts, its timeline, and usage (Workspace or Daemon scope) | `overview`, `epics_list`, `epic_view`, `transcript_read`, `trace_read`, `usage` | No |
| Ask one session a [side question](/user/side-questions); the epic never sees it | `ask_session` | No |
| Say a line to a running epic, answer its question, stop or force stop it, or start an epic (Workspace or Daemon scope) | `say`, `answer`, `start`, `stop` | Yes |
| List, read and search the files of an epic's environments | `env_list`, `env_read`, `env_grep` | No |
| Write a file or run a command in an epic's environment | `env_write`, `env_exec` | Yes |
| Read settings (Workspace or Daemon scope) and list nous | `settings_get`, `nous_list` | No |
| Write settings or a nous (Daemon scope only) | `settings_set`, `nous_set` | Yes |
| List and call any other daemon method her reach allows | `hmz_methods`, `hmz_call` | Depends on the method |

She cannot create, list, rename, or delete Ai-chan conversations, pair or revoke devices, or create accounts.

## Good to know

You can run any number of conversations at once. The daemon keeps them across restarts until you delete them. Deleting a conversation removes it and its scratch directory permanently.

A conversation that no one is viewing folds away 60 seconds after her turn ends. Send a line or select it in `/ai` to resume where it stopped. If a conversation's chat fails, it shows why and accepts no more lines: a line you send is refused with **This conversation failed. Start a new one.**

Ai-chan has no [budget](/user/budgets) and always has network access. Her conversations are not listed with chats or epics, and `/btw` does not work in them. In a narrow window, the drawer covers the view.

Her process is sandboxed: it can write only to her scratch directory, read her scope's folder (and write to it under Full access; under Daemon scope that is the whole disk), and cannot open the daemon socket. On Linux under Landlock the conversation is refused; set `sandbox.backend` to `bwrap`. See [The sandbox](/user/sandbox).

She treats everything she reads in epics, files, and transcripts as data, not instructions. Only your lines in the conversation tell her what to do.
