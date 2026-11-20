# Chat

Talk to one coding agent, a turn at a time, as you would at its own prompt. A **chat** is a
session of its own beside a [flow](/user/concepts#flow)'s [epic](/user/concepts#epic): one
agent, one conversation, in one directory, with no flow, no params and no budget around it. It
is not an epic: it is kept as a record of its own, under its own id. `hmz` opens on one, and a
flow is started from it when the work should run on its own.

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
| Params, environments | none: it works in the directory it was started in, or in [a worktree of it](#worktree), on this machine | as the flow declares |
| Stopping | its open turn only, with `/stop` or **Stop** ([below](#stopping-a-turn)); the chat itself is never ended or forced: it waits between turns, and [folds away](#leaving-and-carrying-on) | `ctrl+c` twice, `/stop`, **Stop** |
| Where it is listed | `/resume` in a chat, and the sidebar and **Search** of `hmz web`, by its title; never in `/epics` | `/epics` and the web's sidebar, an epic of its flow, offering `resume epic` |
| How it is named | its id, `<stamp>-<hex6>`, and its title | its epic's name |

A chat is not a flow, and no flow is a chat: a flow of your own named `chat` is an ordinary
flow, started as any other.

## Starting one

| Where | A chat | A flow |
| --- | --- | --- |
| [`hmz`](/reference/tui) | it opens on a new chat; type a line | `$<flow> <task>`, or `/flow <flow> <task>` |
| [`hmz web`](/user/web#starting-an-epic) | **New chat**: the directory, the model, and the first message | **New epic** |
| the shell | `hmz chat "<message>"`, with `--worktree` for [a worktree of its own](#worktree) ([below](#from-the-shell)) | [`hmz exec -f <flow>`](/user/unattended) |

### The chat's agent {#the-chats-agent}

Each directory remembers the agent of the last chat started or changed in it, apart from the
setup of its flows, and a new chat there starts with it. Where none is remembered yet, `hmz`
fills it as it fills a flow's role: the first CLI it finds. Change it:

- in the terminal, with **Chat agent** on the [Workspace page of
  `/settings`](/user/settings#workspace);
- in the browser, from the nous chip under the box of **New chat**, or of a chat
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

- in the browser, with the chip under the box you type in: on **New chat** before the
  first message, and under a chat at any time;
- from a program, with `permission` on [`chat.start` and `chat.set`](/reference/daemon#chats).

A chat started from the terminal or the shell runs at `workspace-write`.

A permission set while the chat goes on holds from your next message. The turn that is open is
left as it is; ahead of the next one the conversation is closed and carried on in one opened
under the new permission, so the agent remembers what was said. Where the conversation cannot
be carried on, the chat says why and goes on in a new one; where this machine cannot hold the
permission you picked, the chat says so and keeps the one it had. The permission is kept in the
chat's record, and carrying the chat on keeps it.

### In a worktree {#worktree}

A chat can be started in a git worktree of its own, so that what its agent changes stays out of
your checkout:

```sh
hmz chat --worktree -a claude/claude-opus-5:high "Try the other parser."
```

In `hmz web` it is the **Worktree** box under a new chat's first message. From a program it is `worktree: true` on [`chat.start`](/reference/daemon#chats). Humanize adds
a new worktree of the repository holding the directory, detached at its `HEAD` and on no
branch, under [`envs/`](/reference/files#environments) in Humanize's home, and the agent works
there in place of the directory. The chat is still a chat of the directory it was started in:
it is listed there, and carrying it on returns to the worktree.

Humanize never removes the worktree, not when the chat is [deleted](#managing) either: remove
it with `git worktree remove` once you have what you want from it. A directory that is in no
git repository refuses the start, with what `git` said, and a chat carried on is given no
worktree: it works where it worked.

## In the terminal

`hmz` opens on a chat, its agent the one this directory remembers. The first line you type is
its first turn; every line after is the next.

| To | Type |
| --- | --- |
| start a flow, leaving the chat going on its own | `$<flow> <task>`, or `/flow <flow> <task>` |
| set a flow up first | `/flow`, or `/flow <flow>` |
| put the chat back on the screen | `/chat` |
| stop the turn the agent is taking | `/stop` ([below](#stopping-a-turn)) |
| start a new chat, leaving this one to fold away | `/clear` |
| carry on an earlier chat of this directory | `/resume` in the chat: a list of them, newest first |
| rename, fork, archive, upload or delete a chat | `/resume` in the chat, then <kbd>m</kbd> on it ([below](#managing)) |
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
chat's own preference is kept in its record, and carrying the chat on keeps it.

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

## Stopping a turn {#stopping-a-turn}

The turn the agent is taking can be stopped; the chat cannot. Stopping interrupts the open
turn, says `That turn was stopped.` in the conversation, and leaves the chat between turns,
waiting for your next line.

| Where | How |
| --- | --- |
| `hmz` | `/stop` |
| `hmz web` | **Stop**, which the button that sends becomes while a turn is open |
| a program | [`chat.stop`](/reference/daemon#chats) |

With no turn open there is nothing to stop, and the request is refused: `no turn is open, so
there is nothing to stop`. There is no force stop for a chat, and nothing ends one: `ctrl+c`
stops nothing in it, and `/clear`, or a new chat in the browser, starts another and leaves it
going.

## Leaving and carrying on {#leaving-and-carrying-on}

In the terminal a chat's status line says `running` while its agent answers and `done` between
turns. A chat nobody has looked at for a minute between turns **folds away**: its host goes,
and the chat rests, keeping its conversation. Say something in it and it is carried on, the
same chat, by an agent that remembers what was said and keeps the name the chat wrote it down
under, so a side question reaches every session it opened:

| Where | How |
| --- | --- |
| `hmz` | `/resume` in a chat lists this directory's chats, newest first, by title, the one on the screen ticked; pick another and type the next line |
| `hmz web` | open the chat from the sidebar or from the **Chats** tab of **Search** -- its address is `#/chats/<id>` -- and type in its box |
| the shell | `hmz chat --resume <chat id> "<message>"` ([below](#from-the-shell)) |
| a program | [`chat.start`](/reference/daemon#chats) with `resume` the chat's id |

A chat is carried on only in the directory it was started in. `/epics` lists no chat, and
`/resume` outside a chat picks a flow's run up, never a chat. See
[Picking a run up](/user/resuming#a-chat-is-carried-on).

## Renaming, forking, archiving and deleting {#managing}

A chat has a **title**: the first line of its first message, until it is renamed. Beyond
talking in it, a chat can be:

| | [Method of the daemon](/reference/daemon#chats) | What it does |
| --- | --- | --- |
| renamed | `chat.rename` | sets its title, which carrying it on keeps |
| forked | `chat.fork` | makes a new chat of the same directory from a copy of the conversation so far, with the same title, agent, preference and permission, working where the chat works. The new chat rests until you say something in it, and the chat forked is left as it is. Refused while a turn is open, and where the agent's CLI keeps the conversation outside the chat |
| archived, and put back | `chat.archive`, `chat.unarchive` | takes it off the lists of chats, or puts it back, and changes nothing else of it; `chat.list` with `archived` lists the archived ones |
| backed up now | `chat.backup` | uploads it to its [backup targets](/user/backups), as an epic is backed up: **Upload** in a chat's menu in `hmz web` |
| deleted | `chat.delete` | removes its record and the sessions kept with it, for good: Humanize cannot bring it back. Refused while the chat is going -- a host holds it, between turns included -- so delete it once it has folded away. No epic and no [worktree](#worktree) is removed |

In `hmz web` each is in the chat's menu, and the archived chats of a directory are listed in
its settings: see [Managing a chat](/user/web#managing-a-chat).

In `hmz`, type `/resume` in a chat and press <kbd>m</kbd> on a chat of the list -- the one on
the screen is there too, ticked -- for its menu:

| Row | What happens |
| --- | --- |
| `rename` | a form opens on the chat's title; type the new one and press **done** |
| `fork` | the list closes on the new chat, drawn with what was said so far; the next line you type goes on in it |
| `archive` | the chat leaves the list. Archive the chat on the screen and closing the list starts a new chat, as `/clear` does |
| `upload` | offered once a [backup target](/user/backups) exists: the chat is queued to its targets, or the defaults |
| `delete` | a box asks first and says it is permanent; **keep** is the answer under the cursor, **delete** removes the chat for good |
| `copy id` | copies the chat's [id](#where-a-chat-is-kept) |

The line under the list says how each went, a refusal included: a chat that is still going
cannot be deleted, and one whose turn is open cannot be forked.

**Archived chats are put back in the directory's settings**: `/settings workspace`, then
**Archived chats**, lists them newest first, and <kbd>enter</kbd> on one puts it back on
`/resume` at once.

From the shell, [`hmz chat`](#from-the-shell) does the same by id: `--list` (with `--archived`
for the archived ones), `--rename`, `--fork`, `--archive`, `--unarchive` and `--delete`.
There is no `/rename`, `/fork` or `/archive` in a chat: a `/` line that is not one of
[Humanize's own](#what-a-line-means) belongs to the agent's CLI, which may have a command of
that name.

## Sessions a harness had of its own {#harness-sessions}

A session you had in `claude`, `codex` or another CLI directly -- not through Humanize -- is
not a chat, and by default Humanize lists none of them. Turn on **Harness sessions** on the
General page of the settings ([`harness_sessions`](/reference/settings#harness-sessions)) and
the sessions each installed CLI had in a directory are listed after that directory's chats:

| Where | What you see | Continuing one |
| --- | --- | --- |
| `hmz web` | quiet rows after the folder's chats, each ending in its CLI's name; a row opens the session to **read** | **Continue in chat** under it, where its CLI can be continued; otherwise a line saying it cannot |
| `hmz`, `/resume` in a chat | rows after the chats, each `<cli> session, read-only` and whether a copy goes on as a chat or it cannot be continued | pick it; one that cannot be continued says so and nothing else happens |

A harness session is only ever read. **Continuing** one copies its files into a new chat of
that directory and opens that chat: the chat is titled by the session's first line, talks to
the same CLI at the model the session last ran on, and goes on from the copy with the next
thing you say. The CLI's own session stays exactly as it was -- you can still `claude
--resume` it -- and it leaves the list while the chat made from it exists.

Listed are the sessions that worked in that very directory, of each of these CLIs that is
installed:

| CLI | Listed and read | Continued in a chat |
| --- | --- | --- |
| `claude`, `codex`, `grok`, `pi`, `omp`, `qwen` | yes | yes |
| `kimi`, `mcode`, `dsh`, `opencode`, `mimo`, `agy` | yes | no: read-only |
| `cursor-agent` | no | no |

The second row's CLIs either have no way of carrying a copy of a session on (`mcode`, `dsh`,
`agy`), or keep a session where a copy of it alone cannot be made (`opencode` and `mimo` in
one database shared by every session, `kimi` behind indexes shared by every session); their
databases are opened read-only and never written. A `dsh` session is listed only where its
log is not compressed. `cursor-agent` keeps a chat in a store nothing here reads. Anything
Humanize ran itself is not listed: those are chats and epics already. The methods behind it
are [`chat.harness.*`](/reference/daemon#harness-sessions), which say
[per CLI](/reference/daemon#harness-sessions) where each is read from.

## Where a chat is kept {#where-a-chat-is-kept}

Each chat is a directory of its own in [Humanize's home](/reference/files#chats),
`~/.hmz/chats/<workspace>/<stamp>-<hex6>/`, apart from every epic. The directory's name is the
chat's **id**: what `hmz chat --resume`, `#/chats/<id>` and every `chat.*` method name it by,
and what **Copy ID** in a chat's menu in `hmz web` copies. `chat.jsonl` in it is the chat's
record, and `sessions/` beside it holds the agent's conversation.

### Chats of an earlier Humanize {#earlier-chats}

A chat was once written down as an epic. Those stay where they are, as ordinary epics that are
only read: they are listed in `/epics` and among the epics of `hmz web`, their flow said as
`chat`, and they cannot be carried on as chats. Nothing is moved or converted.

## From the shell {#from-the-shell}

`hmz chat` takes one turn of a chat in the current directory, with nobody at a prompt, and
ends it:

```sh
hmz chat -a claude/claude-opus-5:high "What does this repository do?"
```

| Part | Means |
| --- | --- |
| `-a`, `--agent` | the agent, as `-a` writes one [after `<role>=`](/user/unattended#name-an-agent-for-each-role): `cli[@account]/model[:effort]`, or the name of a virtual nous. Without it, the agent this directory remembers; with none remembered, refused |
| `--resume <chat>` | carry the chat of that [id](#where-a-chat-is-kept) on, in this directory, the message as its next turn, with its own agent unless `-a` says another. An epic is not carried on |
| `--worktree` | start the chat in a [new git worktree](#worktree) of this directory; refused together with `--resume` |
| the message | exactly one argument, not empty; one that starts with `-` goes after `--` |

The message is read as [a line in a chat](#what-a-line-means) is, except that a `$` line
naming a flow, and the names Humanize keeps, are refused: run a flow with `hmz exec`. The turn
is drawn on stderr and the answer written to stdout, as `hmz exec` does; a `!<command>` takes
no turn, and what it printed is written to stdout in the answer's place. Where `--resume`
could not carry the conversation on, a `hmz chat: …` line on stderr says why, and the answer
is a new conversation's, in the same chat. It exits `0` once the
turn is done, `1` where the turn failed, `2` where it was refused before it started, and 128
plus the signal's number where a signal ended it, leaving the chat to its host. It changes
nothing this directory remembers. See [CLI › `hmz chat`](/reference/cli#hmz-chat).

As the chat starts, its id is written to stderr -- `hmz chat: chat <id>` -- which is what
`--resume` and the options below take. Each asks the daemon, and takes no turn:

```console
$ hmz chat --list
20261117T100000.123Z-ab12cd  resting  What does this repository do?
$ hmz chat --rename 20261117T100000.123Z-ab12cd "The tour"
20261117T100000.123Z-ab12cd  resting  The tour
$ hmz chat --fork 20261117T100000.123Z-ab12cd
20261119T091500.456Z-4d5e6f
$ hmz chat --archive 20261117T100000.123Z-ab12cd
20261117T100000.123Z-ab12cd  resting  The tour
$ hmz chat --list --archived
20261117T100000.123Z-ab12cd  resting  The tour
$ hmz chat --unarchive 20261117T100000.123Z-ab12cd
20261117T100000.123Z-ab12cd  resting  The tour
$ hmz chat --delete 20261119T091500.456Z-4d5e6f
hmz chat: delete 20261119T091500.456Z-4d5e6f  resting  The tour
for good? It cannot be brought back. [y/N] y
```

`--list` says the chats of this directory, newest first: id, how it stands (`resting`,
`going`, `turn`, `asking` or `failed`) and title. `--delete` asks unless `--yes` is given, and
deletes nothing where nobody is at a terminal to answer. `hmz backup <chat id>` backs a chat
up ([Backing epics up](/user/backups#chats)).

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
