---
title: Continue sessions from other CLIs
description: List the sessions you had in Claude Code, Codex and other coding CLIs outside Humanize, read them, and continue one as a Humanize chat.
---

# Continue sessions from other CLIs

A harness session is a conversation you had in a coding CLI outside Humanize. You can list these sessions per folder, read what was said, and continue one as a Humanize chat.

![A Claude Code session is opened from the sidebar, continued in a chat, and answered](/shots/user-harness-sessions-continue.svg)

Continuing a session copies its files into a new chat. The original CLI files are never changed.

## Supported sessions

Humanize lists a session when its CLI is installed on your machine, it ran in the folder you are looking at, and no Humanize chat or epic started it.

| CLI | Listed and read | Continued in a chat |
| --- | --- | --- |
| Claude Code (`claude`) | yes | yes |
| Codex (`codex`) | yes | yes |
| Grok Build (`grok`) | yes | yes |
| Pi (`pi`) | yes | yes |
| Oh My Pi (`omp`) | yes | yes |
| Qwen Code (`qwen`) | yes | yes |
| Kimi Code (`kimi`) | yes | no |
| MiniMax Code (`mcode`) | yes | no |
| DeepSeek Harness (`dsh`) | yes | no |
| OpenCode (`opencode`) | yes | no |
| MiMo Code (`mimo`) | yes | no |
| Antigravity (`agy`) | yes | no |

## In the app

### Show sessions in the sidebar

The list is off by default.

1. Open **Settings** and select **General**.
2. Under **Harness sessions**, tick **List in sidebar**.
3. Click **Save**.

![In Settings, General, List in sidebar is ticked and saved, and three sessions appear in the sidebar](/shots/user-harness-sessions-switch.svg)

Sessions appear in the sidebar after the folder's chats. Each row shows your first message in italics and the CLI name. The sidebar lists up to 50 sessions per folder and refreshes every 15 seconds.

### Read a session

Click a row to read the full session, including your messages, the agent's answers, tool calls, thinking, and any sub-agents it started. Because the session is read-only, there is no message box.

![A Claude Code session open in the app, with the Continue in chat button under it](/shots/user-harness-sessions-read.svg)

Right-click a row to open its menu: **Open**, **Copy first message**, and **Copy session ID**.

![The menu of a Codex session row in the sidebar](/shots/user-harness-sessions-menu.svg)

### Continue in chat

Click **Continue in chat** below the session. Humanize copies the session into a new chat in the same folder using the same CLI and last-used model. Type your next message as in any [chat](/user/chat).

Once continued, the row moves from the harness session list to your chats.

If a CLI cannot be continued, the button is hidden and a note explains why.

![An OpenCode session that can be read but not continued](/shots/user-harness-sessions-read-only.svg)

## In the terminal

### Enable the session list

1. Type `/settings general`.
2. Select **Harness sessions**, press <kbd>enter</kbd>, and pick `on`.
3. Select **Save**.

![The Harness sessions row of /settings general, with on and off to pick from](/shots/user-harness-sessions-terminal-switch.svg)

### Resume a session

Type `/resume` in a chat. The list shows the current directory's chats followed by up to 200 harness sessions. Each session row ends with `read-only: a copy goes on as a chat` or `read-only: cannot be continued in a chat`.

![The /resume list with one chat and three harness sessions](/shots/user-harness-sessions-resume-list.svg)

Select a session and press <kbd>enter</kbd>. Humanize copies it into a new chat and waits for your input. You cannot preview a session or open a row menu in the terminal.

![In the terminal, /resume lists the sessions, one is picked, and the chat goes on](/shots/user-harness-sessions-resume.svg)

## Good to know

- The `harness_sessions` setting in `~/.hmz/settings.yaml` applies to the whole machine, so toggling it in the app also toggles it in the terminal (see [Settings](/user/settings)). There is no `hmz` CLI command for harness sessions; use the app or the terminal interface.
- Each row is titled after your first line in the session. Sub-agent sessions started by another session are not listed on their own.
- You can continue a session once. To branch again, use **Fork** on the new chat (see [Organise chats](/user/manage-chats)). If you delete the chat, the original session returns to the list.
- If a session's log omits the model name, you cannot continue it and Humanize shows `does not say the model it ran on`. If the CLI deleted the session files, Humanize shows `cannot be continued: its files are gone`.
