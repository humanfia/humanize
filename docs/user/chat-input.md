---
title: Commands, skills and files in a chat
description: Use your coding agent's own slash commands, skills, shell lines and file mentions in a chat, change its model mid-chat, and start a flow from the chat's box.
---

# Commands, skills and files in a chat

A chat accepts the same inputs as its coding agent's command line. Start a line with `/`, `$`, `!` or `@` to use that CLI's commands, skills, shell lines or file mentions. Humanize completes them as you type.

![Humanize Desktop: the Add button is clicked, Slash commands is picked, the box lists the commands, and /review is completed](/shots/user-chat-input-add.svg)

## Prefixes you can type

| Starts with | It is | Example |
| --- | --- | --- |
| `/` | A command or skill of the chat's CLI, or a Humanize command | `/compact` |
| `$` | A skill of the CLI, or a flow to start | `$goal fix the build` |
| `!` | A shell command, run in the chat's folder | `!git status --short` |
| `@` | A file or directory put in front of the agent | `What does @shop/cart.py add up?` |

`/` and `$` work only at the start of a line. `@` works at the start of any word. All other text goes to the agent as a normal message.

Available prefixes depend on the chat's CLI. See [What each CLI takes](#what-each-cli-takes).

## In the app

Humanize Desktop and the browser page work the same way.

### Open the Add menu and completion list

Click **Add** (`+`) in the chat box, or type a prefix directly. The menu offers **Add files**, **Slash commands**, **Skills and flows** and **Run a shell command**.

![The Add menu open over a chat's box: Add files, Slash commands, Skills and flows, Run a shell command](/shots/user-chat-input-menu.svg)

Type `/`, `$` or `@` to open the completion list. Each row shows a tag (`command`, `skill`, `hmz`, `flow`, `dir` or `file`) and a description. Rows are grouped into **Files**, **Commands** (**Skills** after `$`), **Humanize**, and **Flows**. Greyed rows work only in the CLI's own interactive interface.

![The list after a slash: Claude Code's commands, a skill, /model and /effort, and greyed commands that are served only by Claude Code's own interface](/shots/user-chat-input-commands.svg)

| Key | What it does |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move in the list |
| <kbd>tab</kbd> or <kbd>enter</kbd> | Select the highlighted row |
| <kbd>esc</kbd> | Close the list |

Selecting a row completes the text without sending it. Press <kbd>enter</kbd> again to send the message.

On the new chat and new epic pages, only **Add files** is available because no CLI is running yet. While the folder chip says **No folder**, **Add files** is greyed and says `Pick a folder first`: the chat's directory is made only as it starts.

### Mention a file

Type `@` and the start of a path. The list shows files and directories from the chat's folder, worktree or runtime. Type `.` to include hidden names that start with `.`.

![A message with @shop/c typed: the list offers cart.py, catalogue.py and checkout.py](/shots/user-chat-input-files.svg)

### Run a shell command

Start a line with `!` to run a shell command in the chat's folder with the agent's permissions. The chat shows the command, its output, and any non-zero exit status. Running a command does not start a turn; the agent receives the command and its output with your next message.

![A chat in Humanize Desktop: a !git status line drawn as a shell prompt with its output, a question mentioning a file, and /config refused over the box](/shots/user-chat-input-shell.svg)

If the CLI cannot run a line here, Humanize refuses it, shows the reason above the box, and leaves your text in the box.

### Run skills and flows

Type `$` to list the CLI's skills and your installed flows. Enter `$` followed by a flow name and a task to start an epic using that folder's last setup for the flow:

```text
$ralph_loop add a discount code to checkout
```

Omit the task to open the new epic form for that flow. You can also type `/flow <name> [task]`, which always means the flow, never a skill of that name.

![The list after a dollar sign: the installed flows, each tagged flow, with what it does](/shots/user-chat-input-flows.svg)

When a skill and a flow share a name, the chat's preference decides which one runs. The default is `native`, which runs the skill, and the completion list says which one a shared name runs. To change it for the current chat, open the chat menu (`…`), select **Skill or flow**, and pick **Use the skill** or **Start the flow**. You can also type `/prefer native` or `/prefer flow`, or type `/prefer` alone to toggle between them.

![The chat's menu with Skill or flow open: Use the skill is ticked, Start the flow is the other choice, From settings is said below](/shots/user-chat-input-prefer.svg)

### Change the model or effort

Click the nous chip under the box, choose **Model** or **Effort**, and pick a value. To use a model that is not listed, type its name in the **Other model** field under the models and press <kbd>enter</kbd>. The chip shows the new value at once, and the chat uses it from its next turn, in the same conversation. This works on every chat, at any time: one that is running, one between turns, and an old one you have just opened from the list. The page does not reload, no message is sent to the agent for it, and an old chat is not started up until you say something.

![The nous chip is clicked, Model is opened, Opus 4.1 is picked, and the chip now says Opus 4.1](/shots/user-chat-input-model.svg)

Where the CLI has its own `/model` and `/effort` (Claude Code and Codex), you can also type `/model <id>` or `/effort <level>` in the box of a running chat.

The harness and account are locked once a chat starts: a conversation belongs to the harness that had it. Click **New chat** at the bottom of the menu to start a chat with a different harness or account. A few harnesses cannot go on from an earlier conversation at all (Cursor CLI, MiniMax Code, Antigravity and DeepSeek Harness), and a CLI added by hand is never told a model; picking another model or effort for a chat of theirs is refused with a message that says so, and the chip goes back to what the chat runs.

### Built-in Humanize commands

Humanize handles these commands itself and never passes them to the CLI.

| Line | In the app |
| --- | --- |
| `/clear`, `/chat` | Opens a new chat in the same folder |
| `/resume`, `/epics` | Opens Search for the folder |
| `/exit`, `/quit` | Opens the new epic page |
| `/settings` | Opens Settings |
| `/btw <question>` | Asks a [side question](/user/side-questions) in the panel |
| `/flow <name> [task]` | Starts the flow |
| `/prefer [native\|flow]` | Sets whether a shared `$` name runs the skill or the flow |

## In the terminal

In `hmz`, chats use the same four prefixes. Type `/` to open a list of up to ten rows above the prompt, showing Humanize commands first and CLI commands second. Type more letters to filter the list, use <kbd>↑</kbd> <kbd>↓</kbd> to move, press <kbd>tab</kbd> or <kbd>enter</kbd> to select a row, or press <kbd>esc</kbd> to hide the list.

![The terminal interface in a chat: a slash lists Humanize's commands, /re adds Claude Code's /release-notes and /review, and a !git status line prints its output](/shots/user-chat-input-terminal.svg)

- `$` lists the CLI's skills first, then flows, tagged `skill` or `flow`.
- `@` at the start of a line completes a path when the CLI supports `@`.
- `$<flow> <task>` starts the flow, or opens `/flow` first if the flow is not set up in this folder yet.
- `!` lines and their output appear dimmed.
- `/model <id>` and `/effort <level>` change the chat's model and effort.
- Refused lines print an error in red starting with `hmz:`.
- Commands that only the CLI's own interface serves are left out of the list here; the app lists them greyed.

Type `/prefer` to see whether shared `$` names run the skill or the flow and where that setting comes from. Type `/prefer native` or `/prefer flow` to change it for the current chat.

![The terminal interface after /prefer: $<name> runs the skill where it names both: native, from the settings file](/shots/user-chat-input-terminal-prefer.svg)

To change the default for all chats on your machine, run `/settings general` and set **Chat prefers for $**, or set `chat.prefer` in [settings.toml](/reference/settings).

See [Terminal commands and keys](/reference/tui) for the full list of Humanize commands (`/clear`, `/resume`, `/exit` and others).

## From the command line

`hmz chat start` and `hmz chat say` parse prefixes the same way. A `!` line prints the command and its output without taking a turn:

```sh
hmz chat start -a claude/claude-haiku-4-5 '!git log --oneline'
```

![hmz chat run with a !git log line: it prints the chat's id, the command, and the one commit](/shots/user-chat-input-cli.svg)

`hmz chat say` refuses Humanize commands like `/clear` and `$` lines that name a flow. To start a flow from the shell, run `hmz exec -f <name>` instead. See [The command line](/user/command-line).

## What each CLI takes {#what-each-cli-takes}

| CLI | `/` | `$` | `!` | `@` |
| --- | --- | --- | --- | --- |
| Claude Code | Its commands and skills, `/model`, `/effort` | No | Yes | Yes |
| Codex | `/compact`, `/review`, `/rename`, `/model`, `/effort` | Its skills | Yes | Yes, images too |
| Pi, Oh My Pi | Their commands, `/compact` | No | Yes, and `!!` runs a command without telling the model | No |
| Kimi Code | `/compact` and its skills | No | No | No |
| Qwen Code | Its commands | No | No | Yes |
| OpenCode, MiMo Code | Their commands and skills | No | No | Yes |

Every other CLI, including LiteLLM, has no list of its own: Humanize passes each line to it as typed. "No" in the table means the same for that prefix.

## Good to know

- In Claude Code, skills use `/`, so `$` lists only flows.
- A CLI reports its commands when its conversation opens. Before the first turn, the list is short and unknown `/` lines pass through as text; after the first turn, unknown `/` names fail with `No such command`.
- Commands that open an interactive CLI dialog, such as `/config`, `/login` or `/permissions`, are refused.
- Humanize stops any `!` command it runs after 10 minutes.
- A chat's `/prefer` setting is saved with the chat and persists when you resume it.
- Flow prompts never parse these prefixes. A flow prompt containing `/compact` sends that literal text to the agent.
- An [Ai-chan](/user/ai-chan) conversation in the app has no Add menu and no completion list, and it refuses `/model` and `/effort`: her nous stays as picked when the conversation was made.
- See [Skills](/user/skills) for how skills reach an agent, and [Nous](/user/nous) and [Effort and swarm mode](/user/efforts) for model, effort and account settings.
