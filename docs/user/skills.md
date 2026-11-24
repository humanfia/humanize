---
title: Skills
description: Find out which skills an agent carries, use one in a chat, see what a flow adds for its roles, and teach an agent to use hmz.
---

# Skills

A skill is a folder holding a `SKILL.md`: instructions a coding agent loads when a task calls for them. Each agent carries the skills you installed for its CLI, plus any skills a flow brings for its role.

![A session's home holds links to your skills and to the flow's, and the coding agent is started in it](/diagrams/user-skills-1.svg)

## Find your skills

Humanize does not change or disable your skills. It installs exactly one, the [hmz skill](#teach-an-agent-to-use-hmz), and only when you run `hmz skills add`. Each CLI loads them from its own folders, one skill per `<name>/SKILL.md` subfolder. Every agent of a CLI carries that CLI's skills in every chat and flow.

| CLI | Yours | The project's |
| --- | --- | --- |
| `claude` | `~/.claude/skills/` | `.claude/skills/` |
| `codex` | `~/.codex/skills/`, `~/.agents/skills/` | `.agents/skills/`, `.codex/skills/` |
| `agy` | `~/.gemini/antigravity-cli/skills/` | `.agents/skills/` |
| `cursor-agent` | `~/.cursor/skills/`, `~/.config/cursor/skills/` | `.cursor/skills/` |
| `grok` | `~/.grok/skills/`, `~/.agents/skills/`, `~/.claude/skills/`, `~/.cursor/skills/` | `.grok/skills/`, `.agents/skills/`, `.claude/skills/`, `.cursor/skills/` |
| `kimi` | `~/.kimi-code/skills/`, `~/.agents/skills/` | `.kimi-code/skills/`, `.agents/skills/` |
| `mcode` | `~/.minimax/skills/`, `~/.agents/skills/`, `~/.claude/skills/`, `~/.codex/skills/` | `.minimax/skills/`, `.claude/skills/`, `.agents/skills/` |
| `mimo` | `~/.config/mimocode/skills/`, `~/.agents/skills/` | `.mimocode/skills/`, `.agents/skills/` |
| `omp` | `~/.omp/agent/skills/`, `~/.agents/skills/` | `.omp/skills/`, `.agents/skills/` |
| `opencode` | `~/.config/opencode/skills/`, `~/.agents/skills/`, `~/.claude/skills/` | `.opencode/skills/`, `.agents/skills/`, `.claude/skills/` |
| `pi` | `~/.pi/agent/skills/`, `~/.agents/skills/` | Only in a project you trusted in pi |
| `qwen` | `~/.qwen/skills/`, `~/.agents/skills/` | `.qwen/skills/`, `.agents/skills/` |
| `dsh` | `~/.dsh/skills/`, `~/.agents/skills/` | `.dsh/skills/`, `.agents/skills/`, at the project's root |
| `litellm` | None | None |

## Use a skill in a chat

Call a skill in a chat the same way you call it in the CLI's own prompt:

| CLI | What to type |
| --- | --- |
| Claude Code, Kimi Code, Qwen Code, OpenCode, MiMo Code | `/name` |
| Codex | `$name` |
| Pi, Oh My Pi | `/skill:name` |

Every other CLI gets the line as typed. Antigravity expands a `/name` line itself; Grok Build, Cursor CLI and MiniMax Code read it as plain text, and their agents load a skill on their own when the task calls for it.

### In the app

1. Type `/` (or `$` for Codex) in the chat box. The completion list shows your skills and the project's skills: among Claude Code's commands, each described as `a skill`, or under **Skills** for Codex.
2. Press <kbd>tab</kbd> to complete the skill name, add your prompt, and press <kbd>enter</kbd>.

![Typing /rel in a chat's box offers the release-notes skill; tab completes it, and the agent answers using it](/shots/user-skills-chat.svg)

*A skill of yours, used from the chat's box.*

![The list after a slash in a Claude Code chat: its commands, then price-check and release-notes, each marked a skill](/shots/user-skills-offered.svg)

### In the terminal

In `hmz`, type the same prefix in a chat. After `/`, the CLI's commands and skills follow Humanize's own; after `$`, skills come before flows.

![The terminal interface after /p is typed in a chat: /prefer, then /price-check marked a skill](/shots/user-skills-terminal.svg)

### From the command line

Pass the skill call as the message:

```sh
hmz chat start -a claude/claude-haiku-4-5 "/release-notes for 0.4.0"
```

See [Commands, skills and files in a chat](/user/chat-input) for other chat box inputs.

## See what a flow adds

A flow can bring its own skills and assign them to specific roles. For example, in `rlar`, the reviewer carries `review-notes`, while the actor does not.

Humanize starts each role's session in a temporary home built for that process. That home's skills folder links to your skills and to the flow's skills. When the process stops, Humanize removes the temporary home without writing to your project or your skills folders.

![hmz exec of rlar: the actor lists its skills folder and finds release-notes; the reviewer finds release-notes and review-notes](/shots/user-skills-exec.svg)

*Both agents list their skills folder. Only the reviewer has the flow's `review-notes`.*

A flow stores its skills in its `skills/` folder or references them by git URL. Installing a flow fetches its git skills once so runs need no network. An uninstalled flow, such as one in `.hmz/flows/`, fetches its git skills on each run.

To customize a flow's skills, copy the flow into your project with **Copy here** in the terminal (see [Find and install flows](/user/flows)) and edit its `skills/` folder. To add skills to a flow you write, see [Skills](/builder/skills) in the Builder Guide.

## Teach an agent to use hmz

The hmz skill tells a coding agent how to use the `hmz` command line: how to find a command, what every command shares, and one line per command. Install it for every CLI installed on this machine:

```sh
hmz skills add
```

1. Run `hmz skills add`. It writes a folder `hmz` holding `SKILL.md` into each installed CLI's own skills folder, the first folder under **Yours** in the table above, and prints each path.
2. Run `hmz skills list` to see each CLI's folder and whether the skill there is `Current`, `Older`, `Not installed` or `Not written by hmz`.
3. After `hmz update`, run `hmz skills add` again to replace an `Older` skill.

| To | Run |
| --- | --- |
| Install for some CLIs only, installed or not | `hmz skills add --for claude --for codex` |
| Install into a folder several CLIs share | `hmz skills add --dir ~/.agents/skills` |
| Read the skill without installing it | `hmz skills show` |
| Remove it everywhere | `hmz skills remove` |

`hmz skills remove` asks before each removal; pass `--yes` to skip the question. It removes only the skill `hmz skills add` wrote. If a folder already holds a skill named `hmz` that Humanize did not write, `add` refuses and `remove` leaves it alone.

The skill is generated from the commands of the hmz that writes it, so it never describes a command that hmz lacks. `dsh` and `litellm` cannot be named with `--for`; for `dsh`, use `--dir ~/.dsh/skills`. For all options, see the [CLI reference](/reference/cli#hmz-skills).

## Resolve name collisions with flows

For CLIs whose skills use `$`, such as Codex, `$name` in a chat can mean either a skill or a flow. The chat's preference decides, and defaults to running the skill. Type `/flow name` to always start the flow.

Switch the preference with `/prefer native` or `/prefer flow`, or in the app under the chat's menu (`…`) > **Skill or flow**. See [Commands, skills and files in a chat](/user/chat-input) for details.

## Good to know

- A skill's name is the `name` in its `SKILL.md` front matter, or its folder's name when it states none.
- As the first message of a Kimi Code chat, `/name` is sent as plain text, because Kimi lists its skills only once the conversation exists. Call the skill from the second message on.
- If a flow's skill shares a name with one of yours, the session uses the flow's skill and leaves yours untouched on disk.
- `litellm` loads no skills. Roles with skills still run on it, without the skills.
- `dsh` gets the flow's skills as a copy beside the patch its runtime starts with, read after the project's skills and before yours, and removed when the runtime closes. A session kept in a run's epic still reads your skills, and keeps your static `skill-filesystem` settings (custom folders, a moved home, a disabled provider); a dynamic or structural change to that provider is reported as unsupported. A change to a session's skills applies from its next turn, in the same conversation. A flow skill that cannot be copied is left out with a warning and tried again next turn.
- A `dsh` agent whose harness runs on another machine gets neither the flow's skills nor yours from this machine.
- `opencode` and `mimo` do not get a temporary home; Humanize passes the flow's skills in each run's configuration. Both CLIs also read a `skill/` folder beside their own `skills/` folders, such as `.opencode/skill/`.
- If a git-referenced skill cannot be fetched, the run fails before its first turn, and the error names the role that asked for it. A repository fetched before keeps working offline.
- Moving a CLI's home with an environment variable such as `CODEX_HOME` moves its skills folder with it.
- An agent running on [another machine](/user/runtimes) gets copies of the flow's skills in the temporary home built for it there. `opencode` and `mimo` run there without the flow's skills.
- An [error report](/user/reporting) sent from the terminal interface lists the skills each installed CLI would load, by name only.
