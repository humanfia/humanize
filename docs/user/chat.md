---
title: Chat with an agent
description: Start a chat with one coding agent, read its answers, stop a turn, and carry the chat on later from the app, the terminal or the command line.
---

# Chat with an agent

A chat is a conversation with one coding agent in one folder. It runs without a flow, a budget or extra setup. Each message you send starts the agent's next turn. You can run as many chats as you want alongside any running epic.

![Humanize Desktop: New chat is clicked, a message is typed and sent, and the agent answers](/shots/user-chat-start.svg)

## In the app

Humanize Desktop and the web page work the same way.

### Start a chat

1. Click **New chat** in the sidebar, or press <kbd>⇧⌘O</kbd> (<kbd>ctrl+shift+O</kbd> on Windows and Linux).
2. Type into **Message** and press <kbd>enter</kbd>. Press <kbd>shift+enter</kbd> to start a new line.

The chat opens and takes the first line of your message as its title.

If you have not picked an agent, sending opens the agent menu and says `Pick a nous for the chat.`

### Choose where and how it runs

Click the chips under the message box to configure the chat.

![The message box with its chips: shop, This computer, Claude Code Haiku 4.5 Default, Edit this folder, and the usage ring](/shots/user-chat-box.svg)

| Chip | What it sets | More |
| --- | --- | --- |
| Folder (`shop`) | The folder for the chat. **No folder** gives the chat a directory of its own, kept until the chat is deleted. | [Environments](/user/environments) |
| Environment (`This computer`) | Where commands run and files live: the folder itself, a **New worktree**, or a saved runtime. | [Environments](/user/environments) |
| Nous (`Claude Code Haiku 4.5 Default`) | The agent's harness, account, model and effort. Defaults to the last agent used in the folder. | [Nous](/user/nous) |
| Permission (`Edit this folder`) | What the agent may touch: **Read only**, **Edit this folder** or **Full access**. | [Permissions](/user/permissions) |
| Usage (the ring) | What this chat and folder have spent. | [Cost and usage](/user/usage) |

Once a chat starts, it keeps the environment, nous, permission and usage chips under its box. The folder chip appears only on the new chat page. Between turns, pick another place from the environment chip to [move the chat](/user/environments). Pick another model or effort from the nous chip at any time, on an old chat too: see [Change the model or effort](/user/chat-input#change-the-model-or-effort).

### Read the chat

![An open chat in Humanize Desktop with its transcript, the bar across the top and the Details pane open at the right](/shots/user-chat-open.svg)

Your messages appear on the right. The agent's answers appear beside a green dot. Tool calls and reasoning show as small grey lines; click a folded line to expand it. `Worked for` marks the end of each turn.

Right-click any line to open **Copy** and **Copy thread**. Right-click a `!` shell line to choose **Copy** (the command and its output) or **Copy output** (the output alone). To use the keyboard, press <kbd>tab</kbd> to focus the conversation, press <kbd>↑</kbd> and <kbd>↓</kbd> to move between lines, and press <kbd>alt+enter</kbd> (<kbd>option+enter</kbd> on a Mac) or the menu key to open the line menu.

In the sidebar, a chat row shows `Running` during an open turn, `Failed` when the chat has failed, and a dot when the agent waits for your answer.

Use the top bar to manage the chat and open side panels:

| Control | What it does |
| --- | --- |
| Title | Click to rename the chat. |
| **More options** (`…`) | Pin, fork, archive or delete the chat. See [Organise chats](/user/manage-chats). |
| **Details**, **Terminal**, **Changes**, **Files** | Click to open a panel beside the chat; click again to close it. For the last three, see [Files, changes and terminal](/user/environment-panels). |
| **View options** | Open **Side questions** ([Ask a side question](/user/side-questions)) and, while the chat keeps one, **Board**. |

Open the **Details** pane to view usage, the first message, the **Open its environment** button, and **About this chat**: **Chat ID**, **Saved at** (where its record is kept), **Folder**, **Started**, **Nous**, **Environment**, **Options**, and **Limits**. If the chat runs outside its folder, **Works in** names the worktree, directory, or runtime.

### Stop a turn

Click **Stop** (where the send button was) while the agent works to interrupt the turn. The chat shows `That turn was stopped.` and waits for your next message.

![A turn is open and the send button is a Stop button; after the click the chat says That turn was stopped](/shots/user-chat-stop.svg)

Press <kbd>enter</kbd> during a turn to send another message. The agent receives it in the same turn if its harness accepts mid-turn messages, or on the next turn if not.

### Answer a waiting chat

Type a message to answer an agent that asks a question mid-turn. If the question offers options, they appear as buttons under it; click one to answer with it. Waiting chats also appear in the middle of the **New chat** page with their title and `Asked a question`. Click a row to open the chat, or click **Dismiss** to hide it until it asks again.

### Resume a chat

Select any earlier chat in the sidebar and send a message to continue it. A chat that nobody has open folds away after about a minute between turns, but keeps the conversation. Your next message restarts it with the same agent, permission and environment. Opening the **Terminal**, **Changes** or **Files** pane also restarts it without sending a message.

## In the terminal

Run `hmz` in a folder to start a new chat with the folder's last agent, or with the first installed harness if the folder remembers none. Type a line and press <kbd>enter</kbd>.

![The terminal interface: a message is typed after the prompt, the agent works, and its answer appears](/shots/user-chat-terminal.svg)

| Type | What it does |
| --- | --- |
| <kbd>enter</kbd> | Send the line. Press <kbd>shift+enter</kbd> or <kbd>ctrl+j</kbd> for a new line. |
| `/stop` | Stop the current turn. |
| `/clear` | Start a new chat. |
| `/resume` | Pick an earlier chat from this folder and continue it. |
| `/chat` | Return to the chat after a flow takes the screen. |
| <kbd>ctrl+c</kbd> twice, <kbd>ctrl+q</kbd>, `/exit` or `/quit` | Quit without stopping an active turn. |

### Start a chat from the New chat page

Press <kbd>ctrl+n</kbd> for the New chat page. It has the same chips as the app, above the message: **Folder**, **Environment**, **Model**, **Effort** and **Permissions**. Each shows what the chat will start with, so the short way is to type the message and press <kbd>enter</kbd>.

To change one, press <kbd>tab</kbd> or <kbd>shift+tab</kbd> to reach it, press <kbd>enter</kbd>, and pick from the list. **Environment** offers **This computer**, **New worktree** in a git repository, and your saved runtimes. Below the message, the page lists the chats of this folder that wait for your answer, then its harness sessions. Press <kbd>enter</kbd> on one to open it.

A chat started in another folder runs there. The terminal keeps showing its own folder and prints where the chat was started. Run `hmz` in that folder to read it.

### Change a chat while it runs

Press <kbd>ctrl+g</kbd> for **Details** of the open chat, to the right of the log. Move with <kbd>↑</kbd> and <kbd>↓</kbd> and press <kbd>enter</kbd> to change a row.

| Row | What it changes |
| --- | --- |
| **Model**, **Effort** | The model and effort from the next turn on. The harness and account stay the same. |
| **Permissions** | **Read only**, **Edit this folder** or **Full access**, from the next turn on. |
| **Skill or flow** | What `$name` runs when it names both a skill and a flow. |
| **Environment** | Moves the chat to this computer or a saved runtime, between turns. |
| **Rename…**, **Fork**, **Archive**, **Delete chat** | The same actions as the chat's menu in the app. **Delete chat** asks first. |

**Usage** shows what the chat has spent and what the folder spent over the last 7 days. Press <kbd>esc</kbd> to return to the prompt and <kbd>ctrl+g</kbd> twice to close the pane.

The line above the prompt names the agent. The status line shows `Running…` during a turn and `Done` when it finishes. Turn on **Details** in `/settings general` to show tool calls and reasoning. Use **Chat agent** in `/settings workspace` to change the agent the next chat here starts with.

## From the command line

Run `hmz chat start` to start a chat, execute one turn and exit. It writes progress to standard error and the answer to standard output for scripts to capture.

```sh
hmz chat start -a claude/claude-haiku-4-5 "What does charge() do?"
```

![hmz chat start, run in a terminal: it prints the chat's id, the agent works, and the answer and token counts follow](/shots/user-chat-cli.svg)

The first line printed (`Chat <id>`) gives the chat's id. Pass it to `hmz chat say` to send the next message:

```sh
hmz chat say 20261121T034814.744Z-299560 "And how is it tested?"
```

| Command or option | What it does |
| --- | --- |
| `hmz chat start MESSAGE` | Start a chat in the current folder. |
| `-a AGENT` | Set the agent as `CLI[@PROVIDER]/MODEL[:EFFORT]`. Defaults to the folder's remembered agent. Add `--remember` to remember this one. |
| `--worktree` | Start the chat in a new git worktree of the folder. |
| `-e ENV` | Set the working environment as `BACKEND[@RUNTIME][/DIRECTORY]`. |
| `--no-folder` | Start the chat in no folder. |
| `hmz chat say CHAT MESSAGE` | Send the next message to the chat with this id. |
| `hmz chat stop CHAT` | Stop the turn the chat is taking. |
| `hmz chat agent CHAT AGENT` | Carry the chat on with another model or effort. |
| `hmz chat move CHAT ENV` | Move the chat to another environment. |
| `--json`, `--events`, `--detach` | On `start` and `say`: print JSON, print the turn's records as JSON lines, or return without waiting. |

Put the message after `--` if it starts with a dash. Run `hmz chat --help` to list every command. To list and manage chats, see [Organise chats](/user/manage-chats) and the [CLI reference](/reference/cli).

## Good to know

- See [Commands, skills and files in a chat](/user/chat-input) to use `/` commands, `$` skills, `@` files and `!` shell lines in your messages.
- A chat is never an epic. It has no graph, trace or force stop.
- If the first turn fails, the chat ends as failed. If a later turn fails, the chat reports the error and continues.
- If a conversation cannot be resumed, the chat reports why and answers in a new conversation within the same chat.
- In the CLI, `hmz chat start` and `hmz chat say` exit with `0` when the turn finishes and `1` when it fails or the daemon refuses the request.
- If you omit `-a` in a folder with no remembered agent, it is refused with ``No agent is remembered for this folder; name one with `-a`.``
- Pressing <kbd>ctrl+c</kbd> during `hmz chat start` or `hmz chat say` does not stop the turn; the command exits with `130`, the chat continues in the daemon, and you can open it in the app or run `hmz chat say` to continue.
