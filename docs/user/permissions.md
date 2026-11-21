---
title: Permissions
description: Choose what a chat's agent may change, read what a flow lets its agents touch, and know how that limit is held.
---

# Permissions

A permission controls which files an agent may change and whether it may go online. You set it for each chat. For a flow, the author sets it on each role.

![A chat's chip or a flow's role gives a permission, and a fence holds the coding agent and every command it runs to it](/diagrams/user-permissions-1.svg)

::: warning Agents never ask first
Agents do not wait for your approval before editing a file or running a command. Set the permission before you send the task.
:::

## Permission presets

| In the app | In a flow | Reads | Changes |
| --- | --- | --- | --- |
| **Read only** | `read-only` | everything | nothing |
| **Edit this folder** | `workspace-write` | everything | the folder it works in, and the temporary directories |
| **Full access** | `danger-full-access` | everything | anything your user account may change |

**Edit this folder** is the default for every chat and role. At **Read only**, the agent can still run commands such as builds or tests, but any write to a file is refused.

## Set a chat's permission

### In the app

Find the permission chip under the message box, at the right, both on the **New chat** page and inside an active chat.

1. Click the chip. It displays the current permission, which defaults to **Edit this folder**.
2. Select **Read only**, **Edit this folder** or **Full access**.

![The Permissions menu open over the chip: Read only, Edit this folder (checked) and Full access, each with one line saying what it allows](/shots/user-permissions-menu.svg)

In a new chat, your selection applies from the first message. In an active chat, it applies on the next turn while any running turn finishes under the old permission. Resumed chats keep their permission.

![A chat is set to Read only from its chip, then asked to save a file: the agent answers that it could not](/shots/user-permissions-pick.svg)

*Under Read only, the agent cannot save a file.*

If the daemon refuses the change, the chip reverts and a message says why. Chats always have network access. [Ai-chan](/user/ai-chan) uses her own presets.

### In the terminal

Chats started in `hmz` use `workspace-write`. You cannot change the preset in the terminal interface. To use another preset, change it on the chat's chip in the app, then resume the chat in the terminal.

![A chat in the terminal interface asked to write one file in its folder and one outside: the first is written, the second refused](/shots/user-permissions-terminal.svg)

### From the command line

`hmz chat` has no permission flag. New chats start at `workspace-write`. Run `hmz chat --resume CHAT` to continue a chat with its existing permission.

## Read a flow's permissions

You choose which agent fills a role, but the flow defines what that role may touch. You cannot change role permissions from the **New epic** page or with `hmz exec` flags. A role's permission has three parts:

| Part | Values | Default |
| --- | --- | --- |
| `preset` | `read-only`, `workspace-write`, `danger-full-access` | `workspace-write` |
| `network` | `True` or `False` | `True` |
| `granular` | path rules laid over the preset | none |

Check a flow's page in the [catalogue](https://humanfia.ai/flows/) or read its source code to see what it grants:

```python
class Reviewer(Agent):
    _permission = Permission("read-only", network=False, granular=(deny("~/.ssh"),))
```

- **Path rules.** `allow(path)` grants read and write access to a path and everything under it. `read_only(path)` grants read access. `deny(path)` blocks all access. Paths must start with `.` (the working folder), `~` (your home directory) or `/`. The last matching rule wins.
- **`network=False`.** The agent can reach only its model and sign-in hosts. Its built-in web search is also disabled when the CLI supports it.

In the app, point at a role's name on the **New epic** page to see what the flow grants it, for example `read-only · goes online`.

To change a role's permission, edit a local copy of the flow. See [Find and install flows](/user/flows) and [Skills and permissions](/builder/skills).

![hmz exec runs a flow whose role is read-only: the agent's command to write AUDIT.md is refused and it says so](/shots/user-permissions-exec.svg)

*A `read-only` role tries to write a file and is refused.*

## How permissions are enforced

Humanize runs every agent inside an OS fence that enforces the permission on the CLI and every command it spawns. See [The sandbox](/user/sandbox). Humanize also configures each CLI's own flags:

| What | How it is held |
| --- | --- |
| Approvals | Every CLI runs without prompts: `bypassPermissions` on Claude Code and approval `never` on Codex. If a managed policy forbids those modes, Claude Code uses `acceptEdits`, Codex uses `workspace-write` with approval `on-request`, and Humanize approves every request. |
| Read-only roles | File-writing tools are disabled when the CLI supports it. The shell stays enabled, and the fence blocks any file writes it attempts. |
| `network=False` | The fence cuts the network, and Humanize disables the CLI's web search where supported. `cursor-agent` and `mcode` run searches on vendor servers, so they are refused for offline roles. Any CLI added over ACP must declare its hosts. |
| Hooks | A flow can attach a hook to approve or reject each tool call. Claude Code, Codex and Kimi Code are then configured to ask, and the hook answers. See [Hooks](/builder/hooks). |

## Good to know

- If Humanize cannot enforce a permission, the session fails to open with `HarnessSandboxed`. An agent never runs with wider access than its permission allows.
- When an agent reports a refused write, the permission is working. Start the chat in the folder you want changed, or select a wider preset.
- Under **Edit this folder**, the agent can also write to `/tmp`, `/var/tmp` and `$TMPDIR`.
- Under any preset, every agent can write to its own settings, sign-in and session files.
- Path rules do not accept globs like `*.env` or `..` segments.
- **Full access** with network enabled imposes no limits. Use it only when the task requires it.
- Third-party flows use the permissions set by their authors. Read [Security](/user/security) before running them.
