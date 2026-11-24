---
title: CLI
description: Look up every command, subcommand and flag of hmz, what each prints, and what each exit status means.
---

# CLI

Look up every `hmz` command, flag, and exit status. To script them, see [The command line](/user/command-line).

## hmz

```text
hmz
hmz --version
hmz --help
hmz COMMAND [ARGS...]
python -m hmz ...
```

| Line | What it does |
| --- | --- |
| `hmz` | Opens the terminal interface in the current directory. Takes no flags. See [The terminal interface](/user/terminal). |
| `hmz --version` | Prints `hmz <version>` and exits 0. Works only as the whole command line. |
| `hmz --help`, `hmz -h` | Lists the commands. |
| `hmz COMMAND --help` | Prints the help of one command. |

| Command | What it does |
| --- | --- |
| `exec` | Run an agent flow in this directory. |
| `web` | Open this machine's epics in a browser on it. |
| `daemon` | Run, reach, pair and install this machine's daemon. |
| `relay` | Relay daemons and the devices that reach them. |
| `update` | Update hmz to its newest release. |
| `backup` | Back epics up to git repositories, or download them. |
| `internal` | Commands Humanize spawns for itself. Do not run them directly. |
| `chat` | Start chats with an agent, send messages, and manage them. |
| `devices` | List and revoke the devices paired with this daemon. |

There is no shell-completion command. Outside `hmz internal`, no option has an environment-variable equivalent; `HUMANIZE_RELEASES` alone changes where `hmz update` looks.

`hmz`, `exec`, `chat`, `web`, `daemon connect`, `daemon pair`, `daemon devices` and `devices` start the daemon if none runs. `relay`, `update` and `backup` do not.

When the terminal interface closes, it waits up to 15 seconds for queued backups.

## Exit statuses

| Status | Meaning |
| --- | --- |
| `0` | The command succeeded. For `exec`, the flow returned or spent its budget. For `web`, `relay serve` and `daemon serve`, a signal stopped it. |
| `1` | Execution failed: the daemon is unreachable or incompatible, the flow or chat turn failed, a backup target failed, the update did not complete, a delete was not confirmed, or a listener could not open. |
| `2` | Usage error, or a refusal before start. `exec` writes `hmz exec: error: <reason>`. |
| `3` | A [declared command](#declared-commands) could not reach the daemon, or got no answer in time. |
| `126` | `hmz internal fence` could not put the fence up. |
| `127` | `hmz internal anchor`, `cred` or `fence` found no `coganchor` binary for this machine, `anchor --native` found no such harness on the target, or `fence` could not start its program. |
| `129` | `exec`, `chat start` or `chat say` ended on SIGHUP. |
| `130` | `exec`, `chat start` or `chat say` ended on SIGINT, or `daemon connect --stdio` or `hmz internal anchor` was interrupted. |
| `143` | `exec`, `chat start` or `chat say` ended on SIGTERM. |

## Output streams

| Stream | What goes there |
| --- | --- |
| stdout | Machine-readable output: help, version, turn answers, the NDJSON stream, listing lines, addresses, pairing codes, paths. |
| stderr | Progress, spinners and diagnostics. Diagnostics start with `hmz: ` or the command's name, such as `hmz exec: `. |

Two stdout lines contain secrets: the `hmz web` address (which carries the page key) and the `hmz daemon pair` code. Every other printed URL has its credentials removed.

The first matching rule sets colour per stream:

| Rule | Escapes |
| --- | --- |
| `NO_COLOR` is set and not empty | No |
| `TERM=dumb` | No |
| `FORCE_COLOR` is set, not empty and not `0` | Yes |
| Otherwise | Only if the stream is a terminal |

Spinners and the live clock require both a terminal and escapes. `FORCE_COLOR` does not enable them.

## hmz exec

Run one flow in the current directory as a new epic, to completion, with no interface. The command answers any flow question immediately with nothing or with its defaults.

```text
hmz exec -f FLOW [-a ROLE=SPEC[,...]]... [-e ROLE=SPEC[,...]]... [-p KEY=VALUE[,...]]...
         [--profile-flow] [--profile-environment] [--resume] [--json]
         [--backup NAME]... [--] TASK
```

Pass `-f`, a budget, and a single `TASK` argument. Put options in any order, before or after the task.

| Option | Value | What it does |
| --- | --- | --- |
| `-f`, `--flow` | `FLOW` | The flow to run. Required. The last one wins. |
| `-a`, `--agents` | `ROLE=SPEC[,...]` | What an agent role runs. Repeatable. |
| `-e`, `--envs` | `ROLE=SPEC[,...]` | Where an environment role works. Repeatable. |
| `-p`, `--params` | `KEY=VALUE[,...]` | A flow param, or a budget limit. Repeatable. |
| `--profile-flow` | | Samples the flow's own Python into the run's trace. |
| `--profile-environment` | | Samples the programs the agents start into the run's trace. |
| `--resume` | | Resumes the newest stopped run of this flow here that saved progress. |
| `--json` | | Writes the run to stdout as NDJSON. |
| `--backup` | `NAME` | A backup target from settings. Repeatable. `none` disables backup and cannot be combined with a target; omitting it uses the default targets. |

### Flow names

| Form | Meaning |
| --- | --- |
| `NAME` | Looked up in the workspace's flows, then the user's flows, then the `official` flowverse, then every other flowverse. |
| `OWNER/FLOW` | A flow listed under an owner in the `official` flowverse. |
| `@VERSE/[OWNER/]FLOW` | A flow of one flowverse. |
| `@local/FLOW` | A flow in `.hmz/flows` of the workspace. |
| `@user/FLOW` | A flow in `~/.local/share/humanize/flows`. |
| `./PATH`, `/PATH`, `~/PATH` | A flow loaded from disk. Relative paths must start with `./`. |
| `git+URL[@REV][#SUBDIR]` | A flow loaded from a git repository. |
| `NAME:OTHER` | Another flow defined in the same module. |

`hmz exec` never installs a flow. Paths and git references execute as Python code; trust them as you would a program. See [Find and install flows](/user/flows).

### Agent specs

```text
-a ROLE=CLI[@ACCOUNT]/MODEL[:EFFORT]
-a ROLE=NOUS
```

| Part | Rule |
| --- | --- |
| `ROLE` | A role the flow declares. Specify each role once. |
| `CLI` | A harness, such as `claude` or `codex`. |
| `@ACCOUNT` | A saved account. Defaults to the machine's own login. |
| `MODEL` | Passed to the harness unchecked. May contain `/` and `:`. |
| `:EFFORT` | The text after the last `:`, if it is an effort word. Empty or `auto` uses the harness default. |
| `NOUS` | A value with no `/` names a virtual nous from settings. |

See [Agents and harnesses](/reference/agents).

### Environment specs

```text
-e ROLE=BACKEND[@PROVIDER][/WORKDIR]
```

| Part | Rule |
| --- | --- |
| `BACKEND` | `local`, `ssh`, `docker`, `swarm`, `apple-container` or `slurm`. |
| `@PROVIDER` | A runtime saved in settings. For `ssh` alone, a host in brackets: `ssh@[me@box:22]/srv`. `local` takes none. `ssh` requires one. Others default to this machine. |
| `/WORKDIR` | The working directory. Optional only if the saved runtime sets one. `/~/...` is relative to the target's home directory. |

See [Environments and runtimes](/reference/environments).

### Params and the budget

`-p KEY=VALUE` parses as the param's declared type, or as JSON. Items split only at commas followed by another `KEY=`, so `-p tags=a,b,c` is one item. Specify each key once.

Keys starting with `budget.` set the budget. At least one of the first three is required.

| Key | Value |
| --- | --- |
| `budget.duration` | Seconds, units `w` `d` `h` `m` `s` (each at most once) such as `2h30m`, an ISO 8601 duration, or `HH:MM:SS`. |
| `budget.cost` | US dollars, with an optional `$`. `inf` means no limit. |
| `budget.output_tokens` | A whole number, or a decimal with `k` or `m`, such as `1.5m`. |
| `budget.graceful` | `true` or `false` (also `1`, `yes`, `on`, `0`, `no`, `off`): whether limits stop the run gracefully. |
| `budget.graceful.<limit>` | The same, for one limit: `budget.graceful.cost=off`. |

When a budget stops a run, `hmz exec` prints `hmz exec: stopped -- <reason>` to stderr and exits 0. See [Budgets](/user/budgets).

### Output

Without `--json`, stderr shows progress and stdout receives each turn's answer and any lines the flow prints. If stdout and stderr share a terminal, the answer is not repeated on stdout.

With `--json`, stdout receives only NDJSON, one object per event, and flow output goes to stderr. Every object has these keys:

| Key | Value |
| --- | --- |
| `at` | Unix time. |
| `agent` | The agent's own name, not its role. |
| `cli` | The harness. |
| `model` | The model as configured. |
| `session` | The harness's session id, or `""` before it has one. |
| `kind` | `begins`, `ends`, `text`, `reasoning`, `tool`, `subagent`, `subagent-ends`, `asks`, `took`, `notice`, `failed` or `result`. |
| `text` | The event's text. |
| `whose` | The subagent's id on subagent events, else `""`. |
| `tokens` | On `result`, tokens by model. Else `{}`. |
| `spent` | On `result`, tokens by kind. Else `{}`. |

See [Events and records](/reference/events).

### Signals and exit

| Event | What happens | Exit |
| --- | --- | --- |
| The flow returns | | `0` |
| The budget is spent | Prints one line on stderr. | `0` |
| The flow fails or crashes | Prints the exception or traceback on stderr. | `1` |
| The daemon cannot be reached | `hmz: the daemon cannot be reached: <why>` | `1` |
| The line is refused before start | `hmz exec: error: <reason>` | `2` |
| SIGINT, SIGTERM or SIGHUP | Stops and unwinds the epic, waiting for completion. | `130`, `143`, `129` |
| A second SIGINT | Forces the epic, closes open turns, and exits immediately. | `130` |

A second SIGTERM or SIGHUP is ignored. Signals ignored at startup (such as SIGHUP under `nohup`) stay ignored. If the process ends any other way, the epic continues in the daemon.

After the epic ends, the command waits up to 60 seconds for backups, unless stopped by a signal.

## hmz chat

Start chats with an agent, send them messages, and manage them. `hmz chat` is a group of [declared commands](#declared-commands): each takes `--json`, and `hmz chat COMMAND --help` prints its arguments, examples, JSON fields and exit statuses.

```text
hmz chat start [-a AGENT] [-e ENV] [-w DIR | --no-folder] [--worktree]
               [--permission PERMISSION] [--prefer native|flow] [--remember]
               [--detach] [--events] [--] MESSAGE
hmz chat say CHAT [--detach] [--events] [--] MESSAGE
hmz chat list [-w DIR | --all] [--archived] [-q TEXT] [--limit N] [--offset N]
hmz chat show CHAT [--trace]
hmz chat rename CHAT TITLE
hmz chat fork CHAT
hmz chat archive CHAT
hmz chat unarchive CHAT
hmz chat delete CHAT [-y]
hmz chat stop CHAT
hmz chat set CHAT [--permission PERMISSION] [--prefer native|flow]
hmz chat move CHAT ENV
hmz chat agent CHAT AGENT
hmz chat commands CHAT
hmz chat backup CHAT [--to TARGET]...
hmz chat harness list [-w DIR] [--limit N] [--offset N]
hmz chat harness show HARNESS SESSION [-w DIR] [--trace]
hmz chat harness adopt HARNESS SESSION [-w DIR] [-a AGENT]
```

`CHAT` is a chat's id, as `hmz chat list` prints it. `AGENT` is `CLI[@ACCOUNT]/MODEL[:EFFORT]` or a nous name, written as in [`hmz exec -a`](#agent-specs) without `ROLE=`. `ENV` is `BACKEND[@RUNTIME][/DIRECTORY]`. `PERMISSION` is `read-only`, `workspace-write` or `danger-full-access`.

### start and say

`start` begins a chat with its first message; `say` sends the next message to a chat. Both wait until the agent has answered, then print the answer.

| Option | Command | What it does |
| --- | --- | --- |
| `-a`, `--agent` | `start` | The agent. Defaults to the agent remembered for the folder; fails if none is remembered. |
| `-e`, `--env` | `start` | Where the agent works. Defaults to the folder itself. |
| `-w`, `--workspace` | `start` | The folder the chat is of. Defaults to the current directory. |
| `--no-folder` | `start` | Starts the chat in no folder; the daemon makes a directory for it. Needs `-a`. |
| `--worktree` | `start` | Works in a new git worktree of the folder. |
| `--permission` | `start` | What the agent may change. Defaults to `workspace-write`. |
| `--prefer` | `start` | Which one a `$name` line runs when both a skill of the harness (`native`) and a flow (`flow`) have that name. |
| `--remember` | `start` | Remembers the agent for the folder, for the next `start` without `-a`. |
| `--detach` | both | Returns as soon as the message is sent. Prints the chat's id. |
| `--events` | both | Prints each record of the turn as one JSON object per line, then the final document. |

| Output | Where |
| --- | --- |
| The answer, and what a `!` command printed | Standard output. |
| `Chat <id>` (`start` only), then the turn as it goes | Standard error. |
| With `--json` | `{"chat", "workspace", "slot", "answer", "notes", "detached"}` on standard output; nothing on standard error. |
| With `--json`, when the turn failed | `{"error": {"code": 0, "message"}, "chat", "workspace", "slot"}` |

`notes` holds what the chat said beside the answer, such as why it refused the message. The records `--events` prints are the host's history records: see [Events and records](/reference/events).

| Event | Exit |
| --- | --- |
| The turn is done | `0` |
| The turn failed, or the daemon refused the request | `1` |
| The command line could not be read | `2` |
| The daemon could not be reached, or went away during the turn | `3` |
| SIGINT, SIGTERM or SIGHUP | `130`, `143`, `129` |

- Signals detach the command without stopping the turn; the chat continues in the daemon. Stop a turn with `hmz chat stop`.
- When its turn is done, `start` ends the chat's host, and so does `say` if no host held the chat before. The chat rests until the next `say`. With `--detach`, the host stays until it folds on its own.
- `say` to a chat whose turn is still open waits for the turn that takes the message.
- `say` refuses hmz's own `/` commands and `$NAME` lines that name a flow, in the daemon's words. Start flows with `hmz exec`.
- A line that starts with `!` runs a shell command and takes no turn.

### Managing chats

| Command | Text output | `--json` |
| --- | --- | --- |
| `list` | One line per chat, newest first: id, state, title cut to 60 characters. | `{"chats": [CHAT...], "total", "offset", "limit"}` |
| `show CHAT` | One line per field, name then value. With `--trace`, what each harness session said and did. | The chat row, plus `at`, `task`, `prefer`, `forked`, `adopted`, `agents`, `sessions`, `earlier`, `backup`, `backed`, and `trace` with `--trace`. |
| `rename CHAT TITLE`, `archive CHAT`, `unarchive CHAT`, `agent CHAT AGENT` | The chat's line, as `list` prints it. | The chat row. |
| `fork CHAT` | The new chat's id. | `{"chat": <id>}` |
| `delete CHAT` | Nothing. Asks on standard error first unless `-y` is given. | `{"deleted": <id>}` |
| `stop CHAT` | `Stopped` | `{"stopped": <id>}` |
| `set CHAT` | `permission`, `prefer` and `prefer_from`, one per line. | `{"chat", "permission", "prefer", "prefer_from"}` |
| `move CHAT ENV` | The environment the chat works in from then on. | `{"chat", "env"}` |
| `commands CHAT` | One line per entry: sigil and name, source, what it does. | `{"entries": [{"sigil", "name", "about", "how", "source"}], "prefer", "prefer_from", "permission", "listed"}` |
| `backup CHAT` | The targets the backup was queued for. | `{"queued": [<target>]}` |

A chat row has `id`, `title`, `state`, `agent`, `model`, `permission`, `env`, `workdir`, `workspace`, `folderless`, `slot`, `asking`, `began`, `updated`, `archived` and `spent`. `state` is `turn` while the agent works, `asking` while it waits for an answer, `going` while a host holds the chat between turns, `failed`, or `resting`.

- `list` shows the chats of the current directory. `-w DIR` names another folder, `--all` lists every folder, `--archived` lists archived chats instead, and `-q TEXT` keeps chats whose title, first message or id contains the text. `--limit` is at most 200.
- `delete` without `-y` deletes nothing and exits `1` when standard input is not a terminal, with `--json`, or when the answer is not `y` or `yes`.
- `set` takes either option or both. A permission holds from the chat's next turn.
- `move` works only between turns. `agent` changes the model or effort within the chat's harness and account.
- `stop`, `set` and `commands` act on the host that holds the chat. A resting chat is carried on first, with nothing said. `move` carries a resting chat on in the new environment.

### Harness sessions

A harness session is a conversation a harness such as Claude Code or Codex had on its own in a folder, outside hmz.

| Command | Text output | `--json` |
| --- | --- | --- |
| `harness list` | One line per session, last written first: harness, id, when it was last written, title. | `{"sessions": [SESSION...], "total", "offset", "limit"}` |
| `harness show HARNESS SESSION` | One line per field. With `--trace`, what was said and done in it. | The session row, and `trace` with `--trace`. |
| `harness adopt HARNESS SESSION` | The new chat's id. | `{"chat": <id>}` |

A session row has `id`, `harness`, `title`, `workspace`, `model`, `began`, `updated` and `continuable`. `adopt` copies a continuable session into a new chat and leaves the session as it is; `-a` names an agent of the same harness to continue with. Send the new chat a message with `hmz chat say`.

See [Chat with an agent](/user/chat) and [Organise chats](/user/manage-chats).

## hmz web

Serve the browser interface for all workspaces until stopped, on `127.0.0.1` and, where the machine has it, on `::1` at the same port, and on nothing else. Prints `hmz web: http://127.0.0.1:<port>/?key=<key>` on stdout.

```text
hmz web [--port PORT] [--origin ORIGIN] [--no-open] [--attached]
```

| Option | Value | What it does |
| --- | --- | --- |
| `--port` | `0` to `65535` | The loopback port. `0` picks any free port. Defaults to the last port `hmz web` used, or any free port if there is none or it is taken. |
| `--origin` | `http://HOST[:PORT]` or `https://HOST[:PORT]` | The public origin of a reverse proxy that rewrites `Host`. The page's requests are accepted from it too. Any other value is a usage error. See [The browser page](/user/web#behind-a-reverse-proxy). |
| `--no-open` | | Prints the address without opening a browser. |
| `--attached` | | Stops when standard input closes. |

A browser opens automatically on macOS, or when `DISPLAY` or `WAYLAND_DISPLAY` is set. SIGINT, SIGTERM or SIGHUP stops the server with exit 0 without stopping any epics. Exits 1 if the page cannot be served. See [The browser page](/user/web).

## hmz daemon

```text
hmz daemon serve [--listen SPEC]...
hmz daemon connect --stdio
hmz daemon pair [--route ROUTE]... [--seconds SECONDS]
hmz daemon devices
hmz daemon devices revoke NAME
hmz daemon install
hmz daemon uninstall
```

| Subcommand | What it does |
| --- | --- |
| `serve` | Runs the daemon in the foreground until SIGINT or SIGTERM. SIGHUP is ignored, so closing the terminal does not stop it. Listens on its socket, configured listeners, and each `--listen`, printing `hmz daemon: listening on <route>` for each. Exits 1 if a daemon already runs. |
| `connect --stdio` | Bridges standard input and output to the daemon's socket, starting with `hmz-stdio/1`. `--stdio` is required. |
| `pair` | Prints a one-time pairing code on stdout and its expiration time on stderr. |
| `devices` | Lists paired devices, oldest first, one tab-separated line per device: name, fingerprint, date added, last seen. |
| `devices revoke NAME` | Revokes a device and closes its sessions. Prints `hmz daemon devices: revoked <name>; <n> sessions closed`. |
| `install` | Installs and starts a per-user login service for `hmz daemon serve` (launchd on macOS, systemd on Linux). Prints `hmz daemon: installed <path>`. Exits 1 on any other system. |
| `uninstall` | Stops and removes the login service. Prints `hmz daemon: uninstalled <path>`. Exits 1 if none is installed. |

| Option | Of | Value | What it does |
| --- | --- | --- | --- |
| `--listen` | `serve` | `SPEC` | An additional listener to open. Repeatable. |
| `--stdio` | `connect` | | Required. |
| `--route` | `pair` | `ROUTE` | A route to embed in the code. Repeatable. Defaults to the daemon's own listener routes. |
| `--seconds` | `pair` | `60` to `86400` | Code validity in seconds. Default `600`. |

| Listener spec | Meaning |
| --- | --- |
| `tcp://ADDRESS:PORT` | A TCP listener. |
| `ws://ADDRESS:PORT` | A WebSocket listener. |
| `relay:URL` | Registers at a relay. |
| `webrtc:URL` | Registers at a relay for WebRTC. |
| `easytier:NAME` | Joins an EasyTier network from settings. |

The installed service runs without `--listen` flags, using only listeners from settings. See [The daemon](/user/daemon), [Connect to other machines](/user/daemons) and [Daemon and wire](/reference/daemon).

## hmz relay

Serve a plain WebSocket relay for daemons and devices until SIGINT or SIGTERM. Prints `hmz relay: listening on ws://<host>:<port>` on stdout.

```text
hmz relay serve [--listen HOST:PORT]
```

| Option | Value | What it does |
| --- | --- | --- |
| `--listen` | `HOST:PORT` | Listen address. Default `127.0.0.1:8765`. Bracket IPv6 hosts. |

Reads no settings and starts no daemon. Place behind a TLS proxy for `wss`. Exits 1 if it cannot listen. See [Relays and WebRTC](/user/relay).

## hmz update

Update this installation to the newest PyPI release using its original installer (`uv tool`, `pipx`, or `pip`). Takes no arguments.

```text
hmz update
```

| Result | Output | Exit |
| --- | --- | --- |
| Already current | `hmz <version> is the newest release` | `0` |
| Updated | `Updated hmz to <new>` | `0` |
| Run from source, installed from a URL, installer missing or failed, PyPI not reached | A line starting `hmz update: ` on stderr. | `1` |

The newest release is asked of PyPI, or of the URL or file `HUMANIZE_RELEASES` names. If that variable is `off`, `0`, `no`, `none` or empty, the command exits 1 with `hmz update: PyPI could not be asked for the newest release`.

Running daemons continue on the old release until restarted. See [Install and update](/user/install).

## hmz backup

Back up an epic or chat to git repositories, list remote backups, or pull one locally.

```text
hmz backup [--to NAME]... EPIC
hmz backup --list [--to NAME]...
hmz backup --pull EPIC [--to NAME]...
```

| Argument | Value | What it does |
| --- | --- | --- |
| `EPIC` | A name, a chat id, or a path | The local epic or chat to back up. |
| `--to` | `NAME` | A backup target from settings. Repeatable. For backups, defaults to the epic's targets, or the global defaults. For `--list` and `--pull`, defaults to all targets. |
| `--list` | | Lists all epics and chats across the targets, from every machine. |
| `--pull` | `EPIC` | Downloads an epic or chat from the first target holding it and prints its path. `EPIC` is a name, a chat id, or `<machine>/<workspace>/<epic>`. |

`--list` and `--pull` are mutually exclusive.

| Result | Output | Exit |
| --- | --- | --- |
| Every target took it | `<target>: backed up to <url>` on stdout, per target. | `0` |
| A target failed | `<target>: failed: <reason>` on stderr. | `1` |
| `--pull` failed, or the epic is already on this machine | `hmz backup: <why>` | `1` |
| No such epic, no such target, no target configured, or a name held from several machines | A usage error. | `2` |

See [Back up to git](/user/backups).

## Declared commands {#declared-commands}

`hmz chat` and `hmz devices` are commands written as one declaration. Every such command is a client of the daemon, takes the same three options, and prints the same kind of help.

| Option | What it does |
| --- | --- |
| `--json` | Prints one JSON document on standard output instead of text, and nothing on standard error. |
| `--daemon NAME` | Asks the daemon kept under `NAME` instead of this machine's. |
| `--no-color` | Prints without terminal colours. |
| `-h`, `--help` | Prints everything about the command: usage, arguments, options, examples, the text and JSON it prints, exit statuses, and the daemon methods it calls. |

A group named alone, such as `hmz devices`, lists its commands.

| Status | Meaning |
| --- | --- |
| `0` | The command did what was asked. |
| `1` | The daemon refused the request, or a chat turn failed. |
| `2` | The command line could not be read. |
| `3` | The daemon could not be reached. |

On failure, the command writes `hmz <command>: <message>` to standard error. With `--json` it prints `{"error": {"code": <code>, "message": <message>}}` on standard output instead; `code` is the daemon's error code, `503` if the daemon is unreachable, or `504` if it did not answer in time.

## hmz devices

```text
hmz devices list
hmz devices revoke NAME
hmz devices pair [--route ROUTE]... [--seconds N]
```

| Command | Text output | `--json` |
| --- | --- | --- |
| `list` | One line per device: name, fingerprint, when it was paired, when it was last seen. | `{"devices": [{"name", "fingerprint", "added", "seen"}]}`; `seen` is `null` for a device never seen. |
| `revoke NAME` | How many sessions were closed. | `{"dropped": <n>}` |
| `pair` | The code alone on standard output, and when it expires on standard error. | `{"code": <code>, "expires": <seconds since the epoch>}` |

`--route` adds a route the code carries; without it, the code carries the routes the daemon listens on. `--seconds` sets how long the code can be claimed for.

## hmz internal

Humanize spawns these six internal commands for its own processes. Use this reference to diagnose failures; do not run them directly.

```text
hmz internal anchor [OPTIONS] [PROGRAM]...
hmz internal anchor serve --export VIRTUAL[:REAL]... (--stdio | --listen [HOST:]PORT | --peer TICKET@HOST:PORT)
hmz internal anchor rendezvous [--listen [HOST:]PORT] [--punching SECONDS]
hmz internal cred (--map FROM=TO | --keep FROM=TO)... [--] PROGRAM [ARGS...]
hmz internal fence (--policy JSON | --relay DIR) [--sandbox BACKEND] [--] PROGRAM [ARGS...]
hmz internal hook --at SOCKET
hmz internal tools --at SOCKET
hmz internal cli --at SOCKET --name NAME [-- WORDS...]
```

| Command | What it does | Exit |
| --- | --- | --- |
| `anchor` | Runs an agent turn whose work lands on another machine. | The program's own. `1` on a connection or protocol error. `130` if interrupted. `127` with no `coganchor`. |
| `anchor serve` | Executes requests from `anchor` on the target machine. With `--listen`, prints `hmz internal anchor serve listening <host> <port>` on stderr. | `0` when the session ends or on SIGINT. `1` if it cannot listen or connect. `2` for a refused line. |
| `anchor rendezvous` | Connects `anchor` and `anchor serve` when they cannot dial each other directly. Prints `hmz internal anchor rendezvous listening <bound> <landed>` on stderr. | `0` on SIGINT. `1` if it cannot listen. `2` for a malformed address. |
| `cred` | Runs a program with credentials from an account. | The program's own. `1` off Linux, where nothing can supervise it. `127` with no `coganchor`. |
| `fence` | Runs a program restricted by its flow's policy. | The program's own. `126` if the fence fails. `127` with no `coganchor`, or if the program cannot be started. |
| `hook` | Relays one agent hook call (from JSON on stdin) to a flow. | `0` after reading input. `1` for bad arguments. |
| `tools` | Relays agent tool calls to a flow. | `0` when either end closes. `1` if the socket is unreachable. |
| `cli` | Relays one flow CLI invocation to the flow. | The flow's return status. `1` if the flow is gone. |

Run `hmz internal COMMAND --help` for full options.

`anchor`, `cred` and `fence` become the bundled `coganchor` binary, which takes the same options, reads the same variables and exits with the same statuses:

| `hmz internal ...` | Runs |
| --- | --- |
| `anchor ...` | `coganchor cog ...` |
| `anchor serve ...` | `coganchor anchor ...` |
| `anchor rendezvous ...` | `coganchor broker ...` |
| `fence ...` | `coganchor internal fence ...` |
| `cred ...` | `coganchor internal cred ...` |

`coganchor --version` prints `coganchor <version>`. `coganchor internal able [--policy JSON|@PATH] [--sandbox BACKEND]` prints what this machine can fence, as `{"fs": bool, "net": bool}`; with `--policy`, an `"unheld"` key says why it cannot hold what that policy carves out.

### anchor options

| Option | Value | What it does |
| --- | --- | --- |
| `--target` | `URL` | Where the work lands. Default `local`. |
| `--harness` | `WHERE` | Where the harness runs: `local`, or a target URL. |
| `--broker` | `HOST` | Where the two halves meet when harness and target differ. |
| `--workspace` | `PATH` | The project directory on the target. Default: this directory. |
| `--remote-path` | `PATH` | The directory standing in for the target's copy of the workspace. |
| `--shadow` | `PATH` | The mirror directory on the harness's machine. |
| `--local-path` | `PATH` | A path that stays on this machine. Repeatable. |
| `--local-exec` | `PATH` | A program that runs on this machine. Repeatable. |
| `--redirect` | `FROM=TO` | Redirects an absolute path to another. Repeatable. |
| `--chdir` | `PATH` | Where the agent starts. |
| `--private` | `NAME` | An environment variable withheld from commands on the target. Repeatable. |
| `--net` | `local` or `remote` | Where the agent's own TCP connections go. Default `local`. |
| `--net-allow` | `HOST[:PORT]` | A host that stays local under `--net remote`. Repeatable. |
| `--token` | `TOKEN` | The shared secret the target expects. |
| `--token-file` | `FILE` | A file holding that secret. |
| `--force` | | Uses the mirror directory even if it holds something else. |
| `--native` | | Runs the CLI installed on the target. |
| `--hush` | `NAME` | A file in the CLI's home excluded from the target. Repeatable. |
| `--project` | `NAME=DIR` | A project directory to keep for the CLI. Repeatable. |
| `--bring` | `NAME/PATH=DIR` | A file to retrieve from the target. Repeatable. |
| `--tell` | `DIR` | Where to tell the target's CLI its state is kept. |
| `--home` | `JSON` | The CLI's virtual home. |
| `--installs` | `LINE` | The shell command to install CLI dependencies on the target. |
| `--fence` | `JSON` | The fence policy applied to the agent. |
| `--check` | | Queries the target identity and exits. |
| `--log-level` | `debug`, `info`, `warning`, `error` | Default `warning`. |

`--target` accepts `ssh://[USER@]HOST[:PORT]`, `docker://CONTAINER[@ENDPOINT]`, `apple-container://NAME`, `slurm://JOBID`, `tcp://HOST:PORT`, `peer://TICKET@HOST:PORT` or `local[:DIR]`.

### anchor serve and anchor rendezvous options

| Option | Of | Value | What it does |
| --- | --- | --- | --- |
| `--export` | `serve` | `VIRTUAL[:REAL]` | A directory to serve. Repeatable. At least one required. |
| `--stdio` | `serve` | | Serves one session over standard input and output. |
| `--listen` | `serve` | `[HOST:]PORT` | Serves sessions on this address. Host defaults to `127.0.0.1`. A host that is not loopback needs `--token`, `--token-file` or `HUMANIZE_TOKEN`; without one it is refused with `cannot listen on a non-loopback address without --token`. |
| `--peer` | `serve` | `TICKET@HOST:PORT` | Serves one session met through a broker. |
| `--token` | `serve` | `TOKEN` | The secret a client must prove. Not with `--peer`, whose ticket is the secret. |
| `--token-file` | `serve` | `FILE` | A file holding that secret. |
| `--listen` | `rendezvous` | `[HOST:]PORT` | Listen address. Default `0.0.0.0:0`. |
| `--punching` | `rendezvous` | `SECONDS` | Direct connection timeout before falling back to relay. Default `4`. |
| `--log-level` | both | `debug`, `info`, `warning`, `error` | Default `warning` for `serve`, `info` for `rendezvous`. |

### cred, fence, hook, tools and cli options

| Option | Of | Value | What it does |
| --- | --- | --- | --- |
| `--map` | `cred` | `FROM=TO` | Maps an absolute path to another. Repeatable. |
| `--keep` | `cred` | `FROM=TO` | Like `--map`, but never copies. `FROM` accepts globs. Repeatable. |
| `--policy` | `fence` | `JSON` or `@PATH` | The fence policy, or a file holding it. |
| `--relay` | `fence` | `DIR` | Carries loopback through this directory inside a network namespace. |
| `--sandbox` | `fence` | `auto`, `landlock` or `bwrap` | The Linux sandbox backend. |
| `--at` | `hook`, `tools`, `cli` | `SOCKET` | The socket the flow serves. Required. |
| `--name` | `cli` | `NAME` | The invoked command name. Required. |

The `anchor` options `--target`, `--harness`, `--broker`, `--shadow`, `--token` and `--log-level`, `--token` and `--log-level` of `anchor serve`, and `--log-level` of `anchor rendezvous` default to environment variables. See [Environment variables](/reference/environment).
