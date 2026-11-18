# Chat

Talk to one coding agent, a turn at a time, as you would at its own prompt. A **chat** is the
other kind of epic beside a [flow](/user/concepts#flow): one agent, one conversation, in one
directory, with no flow, no params and no budget around it. `hmz` opens on one, and a flow is
started from it when the work should run on its own.

::: info At a glance
- **You will** ask an agent something, type its CLI's own `/` commands, skills, `!` and `@`
  lines in Humanize, start a flow from the chat, and come back to it.
- **Use it when** you want to talk the work through, or do something small, before or between
  flows.
- **You need** Humanize and one signed-in coding agent CLI ([Installation](/user/installation)).
:::

## Try it

In a repository:

```sh
hmz
```

```text
❯ What does this repository do?
```

The agent answers, and waits for your next line. `$ralph_loop Make the tests pass` starts a
flow from there, once that flow is [installed](/user/first-run#_3-choose-a-flow), and `/chat`
comes back to the chat.

## Chat or flow

| | Chat | Flow |
| --- | --- | --- |
| Who works | one agent, the **assistant**, with everything its CLI can do, the web included | every role the flow declares, each with what the flow grants it |
| How it goes on | one turn per line you say, in one conversation | as the flow's Python says, until it ends or its budget is spent |
| Budget | none: it spends what its turns spend | always one |
| Params, environments | none: it works in the directory it was started in, on this machine | as the flow declares |
| Stopping | never stopped: it waits between turns, and [folds away](#leaving-and-carrying-on) | `ctrl+c` twice, `/stop`, **Stop** |
| In `/epics` and the web's sidebar | an epic of kind `chat`, offering `continue` | an epic of its flow, offering `resume epic` |

A chat is not a flow, and no flow is a chat: a flow of your own named `chat` is an ordinary
flow, started as any other.

## Starting one

| Where | A chat | A flow |
| --- | --- | --- |
| [`hmz`](/reference/tui) | it opens on a new chat; type a line | `$<flow> <task>`, or `/flow <flow> <task>` |
| [`hmz web`](/user/web#starting-an-epic) | **New epic** › **Chat**: the directory, the model, and the first message | **New epic** › **Flow** |
| the shell | `hmz chat "<message>"` ([below](#from-the-shell)) | [`hmz exec -f <flow>`](/user/unattended) |

### The chat's agent {#the-chats-agent}

Each directory remembers the agent of the last chat started or changed in it, apart from the
setup of its flows, and a new chat there starts with it. Where none is remembered yet, `hmz`
fills it as it fills a flow's role: the first CLI it finds. Change it:

- in the terminal, with **Chat agent** on the [Workspace page of
  `/settings`](/user/settings#workspace);
- in the browser, from the model chip on the box of **Chat** under **New epic**, or of a chat
  going, whose menu says the `/model` or `/effort` line below for you;
- in the chat, with the CLI's own `/model` or `/effort`, where it has them (Claude Code,
  Codex): the chat goes on with the new model or effort, and the directory remembers it;
- in the shell, with `hmz chat -a`, which remembers nothing.

`/flow` never offers a chat: it sets flows up.

### What the chat may touch {#permission}

A chat has a **permission**, one of three, which says what its agent may change. It is the
[grant](/user/permissions) its agent runs under: the same presets a flow's role is given, held
the same way, with the network on.

| In `hmz web` | Its name | The agent |
| --- | --- | --- |
| **Read only** | `read-only` | reads the machine and runs commands, and changes no file |
| **Edit this folder** | `workspace-write` (the default) | changes files in the chat's directory, and only reads the rest |
| **Full access** | `danger-full-access` | changes files anywhere you can |

None of them asks you before the agent acts: Humanize never holds an agent by putting its
actions to approval, so there is no "ask first" mode. What limits the agent is what it may
touch.

Set it:

- in the browser, with the chip on the box you type in: on **New epic** › **Chat** before the
  first message, and under a chat at any time;
- from a program, with `permission` on [`chat.start` and `chat.set`](/reference/daemon#chats).

A chat started from the terminal or the shell runs at `workspace-write`.

A permission set while the chat goes on holds from your next message. The turn that is open is
left as it is; ahead of the next one the conversation is closed and carried on in one opened
under the new permission, so the agent remembers what was said. Where the conversation cannot
be carried on, the chat says why and goes on in a new one; where this machine cannot hold the
permission you picked, the chat says so and keeps the one it had. The permission is kept in the
chat's epic, and carrying the chat on keeps it.

## In the terminal

`hmz` opens on a chat, its agent the one this directory remembers. The first line you type is
its first turn; every line after is the next.

| To | Type |
| --- | --- |
| start a flow, leaving the chat going on its own | `$<flow> <task>`, or `/flow <flow> <task>` |
| set a flow up first | `/flow`, or `/flow <flow>` |
| put the chat back on the screen | `/chat` |
| start a new chat, leaving this one to fold away | `/clear` |
| carry on an earlier chat of this directory | `/resume` in the chat: a list of them, newest first |
| ask a side question | `/btw <question>` |
| leave | `/exit`, `/quit`, or `ctrl+c` twice; the chat is left to its host |
| say how a `$` name that is both is read | `/prefer`, `/prefer native`, `/prefer flow` |

A flow started from the chat takes the screen, and the chat waits on its own host. A plain
line said while the flow runs [steers](/user/steering) the flow; once the flow has ended, a
plain line goes back to the chat, and `/chat` brings it back at any time. Only one flow runs in
a directory at a time; a chat runs beside it.

Outside a chat -- with a flow on the screen -- `/resume` picks the last flow up, as it always
has ([Picking a run up](/user/resuming)).

## What a line means {#what-a-line-means}

In a chat, a line that starts with `/`, `$`, `!` or `@` is read the way your agent's own CLI
reads it, wherever Humanize can carry it there. In order:

1. **A name Humanize keeps.** `/clear`, `/resume`, `/exit`, `/quit`, `/btw`, `/flow`,
   `/epics`, `/settings`, `/chat` and `/prefer` are Humanize's in every interface, whatever
   the CLI has of the same name; at the `hmz` prompt, so is each of its other
   [commands](/reference/tui#commands), such as `/afk` and `/stop`. The five the CLIs have too
   do what the CLI's own does: `/clear` starts a new conversation, as a new chat; `/resume`
   picks an earlier chat to carry on; `/exit` and `/quit` leave; `/btw` asks a side question.
2. **A `$` name.** A native skill or a flow: [below](#a-name-that-is-both).
3. **An entry of the CLI's catalogue.** Served as the [table](#native-input-by-cli) says.
4. **A `/` name the CLI does not have.** Refused, naming it -- unless the CLI takes no `/`
   commands through Humanize at all, when the line goes to it as text.
5. **Anything else**, an `!` or `@` line the CLI has no entry for included, is said to the
   agent as it is.

Typing a sigil opens the completion list on what it can be: the CLI's entries, the names
Humanize keeps and, for `$`, the native skills and the flows grouped apart, each tagged with
where it comes from.

### A name that is both {#a-name-that-is-both}

`$<name>` names one of your agent's own skills (Codex's `$skill`) or a flow:

| `<name>` is | The line |
| --- | --- |
| a native skill only | is served by the agent's CLI |
| a flow only | starts the flow, as a `$` line [always has](/reference/tui#starting-a-flow-outright) |
| neither | is said to the agent as prose |
| both | goes by the chat's **preference**: `native` (the default) serves the skill, `flow` starts the flow |

Where a name is both, the completion list says which one the preference picks, and that
`/flow <name>` starts the flow: `/flow` always names a flow, whatever the preference.

The preference is this machine's, `native` until you say otherwise, and any one chat can
override it:

| To set | Where |
| --- | --- |
| every chat's | **Chat prefers for `$`** on the [General page of `/settings`](/user/settings#general), or `chat.prefer` in [the settings file](/reference/settings) |
| this chat's | `/prefer native` or `/prefer flow` in the chat; **Skill or flow** in the chat's **More** menu in `hmz web`, where `native` reads **Use the skill** and `flow` **Start the flow** |

`/prefer` alone says which is in force and whether it comes from the settings or this chat. A
chat's own preference is kept in its epic, and carrying the chat on keeps it.

```yaml
# ~/.hmz/settings.yaml
chat:
  prefer: flow      # native (default) or flow
```

## Native input, by CLI {#native-input-by-cli}

How each line is served is one of four:

| How | What Humanize does |
| --- | --- |
| pass | puts the line into the turn unchanged, and the CLI expands it itself |
| call | calls the CLI's own operation for it: a compaction, a review, a skill input |
| emulate | does what the CLI's interactive interface would do ([`!` below](#shell-lines)) |
| refuse | refuses it, saying why: only the CLI's own interactive interface can serve it, as a settings dialog or a login can only be shown there |

What each CLI takes:

| CLI | Line | How |
| --- | --- | --- |
| `claude` | `/<name>` for every command and skill its session lists | pass |
| `claude` | `/model`, `/effort` | call |
| `claude` | `!<command>` | emulate |
| `claude` | `@<path>` | pass |
| `claude` | `/config`, `/mcp`, `/agents`, `/login`, `/permissions`, `/doctor` | refuse |
| `codex` | `$<skill>` for every skill in its skills list | call, as a skill input |
| `codex` | `@<path>` | call, as a mention, or as an image for an image file |
| `codex` | `!<command>` | call, as the app server's shell command; emulate where Codex's own sandbox holds the [fence](/user/permissions) |
| `codex` | `/compact`, `/review`, `/rename`, `/model`, `/effort` | call |
| `pi`, `omp` | `/<name>` for every command in its own list | pass |
| `pi`, `omp` | `!<command>`, and `!!<command>`, which runs it without sending it to the agent | call |
| `pi`, `omp` | `/compact` | call |

Every other built-in CLI takes what the way Humanize drives it can reach, and every other line
as text. `litellm`, and a CLI you added that speaks ACP, take no native input: every line is
text.

A flow's prompts are never read this way: a flow that writes `/compact` into a prompt is
talking about compaction, not asking for one.

### `!` lines {#shell-lines}

Where Humanize emulates `!` (Claude Code; Codex when its sandbox holds the fence),
`!<command>`:

- runs in the chat's directory, under the same [confinement](/user/permissions) as the
  agent's own commands;
- shows the command and its output in the conversation, dim, in the style of a shell;
- opens no turn: the agent is not asked anything;
- is carried into the next turn you take, ahead of your message, as `<bash-input>`,
  `<bash-stdout>` and `<bash-stderr>` blocks, so the agent sees what you ran and what it
  printed.

## Leaving and carrying on {#leaving-and-carrying-on}

A chat is never stopped: `/stop` and **Stop** are not offered, and `ctrl+c` stops nothing in
it. It is `running` while its agent answers and `done` between turns. A chat nobody has looked
at for a minute between turns **folds away**: it ends, keeping its conversation. Say something
in it -- from `/epics` (`continue`), from `/resume` in a chat, or in the browser -- and it is
carried on, in the same epic, by an agent that remembers what was said and keeps the name
the epic wrote it down under, so a side question reaches every session it opened. See
[Picking a run up](/user/resuming).

## From the shell {#from-the-shell}

`hmz chat` takes one turn of a chat in the current directory, with nobody at a prompt, and
ends it:

```sh
hmz chat -a claude/claude-opus-5:high "What does this repository do?"
```

| Part | Means |
| --- | --- |
| `-a`, `--agent` | the agent, as `-a` writes one [after `<role>=`](/user/unattended#name-an-agent-for-each-role): `cli[@account]/model[:effort]`, or the name of a virtual nous. Without it, the agent this directory remembers; with none remembered, refused |
| `--resume <epic>` | carry that chat of this directory on, the message as its next turn, with its own agent unless `-a` says another |
| the message | exactly one argument, not empty; one that starts with `-` goes after `--` |

The message is read as [a line in a chat](#what-a-line-means) is, except that a `$` line
naming a flow, and the names Humanize keeps, are refused: run a flow with `hmz exec`. The turn
is drawn on stderr and the answer written to stdout, as `hmz exec` does; a `!<command>` takes
no turn, and what it printed is written to stdout in the answer's place. It exits `0` once the
turn is done, `1` where the turn failed, `2` where it was refused before it started, and 128
plus the signal's number where a signal ended it, leaving the chat to its host. It changes
nothing this directory remembers. See [CLI › `hmz chat`](/reference/cli#hmz-chat).

## Troubleshooting

### `no such command: /<name>`

The agent's CLI has no `/<name>` that Humanize can reach. The completion list after `/` shows
what it has. Before a chat's first turn some CLIs have not said all their commands yet, so a
`/<name>` not listed then is said to the agent as it was typed.

### `/<name> is served only by the harness's own interactive interface`

The command opens a dialog, a login or a setting of the CLI itself. Run the CLI on its own,
outside Humanize, for it.

### A `$` line started a flow when I meant the skill, or the other way

The name is both, and the [preference](#a-name-that-is-both) chose. `/prefer native` serves the
skill from then on in this chat; `/flow <name> <task>` starts the flow whatever it says.

### `hmz chat` says to give an agent with `-a`

No chat has been started in this directory yet, so there is no agent to remember. Give one with
`-a`, or start a chat here once from `hmz` or `hmz web`.

## Next steps

- [Your first run](/user/first-run): set a flow up and start it from the chat.
- [Talking to a running turn](/user/steering): what a line does while the agent works.
- [Side questions (/btw)](/user/btw): ask about a chat or a flow without changing it.
- [TUI reference › Chat](/reference/tui#chat): every rule of a chat at the prompt.
