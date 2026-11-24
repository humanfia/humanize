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
| `chat` | Say one message to an agent in this directory. |
| `web` | Open this machine's epics in a browser on it. |
| `daemon` | Run, reach and install this machine's daemon. |
| `relay` | Relay daemons and the devices that reach them. |
| `update` | Update hmz to its newest release. |
| `backup` | Back epics up to git repositories, or download them. |
| `internal` | Commands Humanize spawns for itself. Do not run them directly. |
| `daemons` | List, add, pair and remove the daemons of other machines. |
| `devices` | List and revoke the devices paired with this daemon. |
| `easytier` | List, write and remove this machine's EasyTier networks. |
| `runtimes` | List, write, check and remove the runtimes environments are put on. |

There is no shell-completion command. Outside `hmz internal`, no option has an environment-variable equivalent; `HUMANIZE_RELEASES` alone changes where `hmz update` looks.

`hmz`, `exec`, `chat`, `web`, `daemon connect`, `devices`, `runtimes` and `easytier` start the daemon if none runs. `relay`, `update` and `backup` do not.

When the terminal interface closes, it waits up to 15 seconds for queued backups.

## Exit statuses

| Status | Meaning |
| --- | --- |
| `0` | The command succeeded. For `exec`, the flow returned or spent its budget. For `web`, `relay serve` and `daemon serve`, a signal stopped it. |
| `1` | Execution failed: the daemon is unreachable or incompatible, the flow or chat turn failed, a backup target failed, the update did not complete, a delete was not confirmed, or a listener could not open. |
| `2` | Usage error, or a refusal before start. `exec` and `chat` write `hmz exec: error: <reason>` or `hmz chat: error: <reason>`. |
| `3` | A [declared command](#declared-commands) could not reach the daemon, or got no answer in time. |
| `126` | `hmz internal fence` could not put the fence up. |
| `127` | `hmz internal anchor`, `cred` or `fence` found no `coganchor` binary for this machine, `anchor --native` found no such harness on the target, or `fence` could not start its program. |
| `129` | `exec` or `chat` ended on SIGHUP. |
| `130` | `exec` or `chat` ended on SIGINT, or `daemon connect --stdio` or `hmz internal anchor` was interrupted. |
| `143` | `exec` or `chat` ended on SIGTERM. |

## Output streams

| Stream | What goes there |
| --- | --- |
| stdout | Machine-readable output: help, version, turn answers, the NDJSON stream, listing lines, addresses, pairing codes, paths. |
| stderr | Progress, spinners and diagnostics. Diagnostics start with `hmz: ` or the command's name, such as `hmz exec: `. |

Two stdout lines contain secrets: the `hmz web` address (which carries the page key) and the `hmz devices pair` code. Every other printed URL has its credentials removed.

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

Send one message to an agent in the current directory, print the answer, and exit. Prints `hmz chat: chat <id>` first on stderr.

```text
hmz chat [-a SPEC] [-e ENV] [--resume CHAT | --worktree] [--] MESSAGE
hmz chat --list [--archived]
hmz chat --rename CHAT TITLE
hmz chat --fork CHAT
hmz chat --archive CHAT
hmz chat --unarchive CHAT
hmz chat --delete CHAT [--yes]
```

| Option | Value | What it does |
| --- | --- | --- |
| `-a`, `--agent` | `CLI[@ACCOUNT]/MODEL[:EFFORT]` or `NOUS` | The agent, written as in [`hmz exec -a`](#agent-specs) without `ROLE=`. New chats default to the directory's remembered agent, or fail if none exists. Resumed chats keep their own unless `-a` is given with `--resume`, which carries the chat on with that agent. |
| `-e`, `--env` | `BACKEND[@RUNTIME][/DIRECTORY]` | Where the agent works. With `--resume`, moves the chat there. |
| `--resume` | `CHAT` | Appends the message as the next turn of this chat. Incompatible with `--worktree`. |
| `--worktree` | | Starts the chat in a new git worktree of this directory. |
| `--list` | | Lists this directory's chats, newest first: id, state (`ready`, `turn`, `asking` or `failed`), title. |
| `--archived` | | With `--list`, lists only archived chats. |
| `--rename` | `CHAT` | Sets the chat's title and prints its line. |
| `--fork` | `CHAT` | Branches a new chat from this one and prints the new id. |
| `--archive` | `CHAT` | Archives the chat and prints its line. |
| `--unarchive` | `CHAT` | Restores an archived chat and prints its line. |
| `--delete` | `CHAT` | Permanently deletes the chat after prompting on stderr. |
| `--yes` | | Skips the confirmation prompt for `--delete`. |

`--list`, `--rename`, `--fork`, `--archive`, `--unarchive` and `--delete` are mutually exclusive, run no turn, and reject `-a`, `-e`, `--resume` and `--worktree`.

Messages work as in any chat interface, except `/`-prefixed interface commands and `$NAME` flow calls are refused. Prefixing a line with `!` runs a shell command and prints its output to stdout.

There is no `--json` and no budget.

| Event | Exit |
| --- | --- |
| The turn is done | `0` |
| The turn failed, or the daemon cannot be reached | `1` |
| `--delete` without `--yes` and nobody at a terminal | `1` |
| A usage error, or a refusal by the daemon | `2` |
| SIGINT, SIGTERM or SIGHUP | `130`, `143`, `129` |

Signals detach the command without stopping the turn; the chat continues in the daemon. See [Chat with an agent](/user/chat) and [Organise chats](/user/manage-chats).

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
hmz daemon install
hmz daemon uninstall
```

| Subcommand | What it does |
| --- | --- |
| `serve` | Runs the daemon in the foreground until SIGINT or SIGTERM. SIGHUP is ignored, so closing the terminal does not stop it. Listens on its socket, configured listeners, and each `--listen`, printing `hmz daemon: listening on <route>` for each. Exits 1 if a daemon already runs. |
| `connect --stdio` | Bridges standard input and output to the daemon's socket, starting with `hmz-stdio/1`. `--stdio` is required. |
| `install` | Installs and starts a per-user login service for `hmz daemon serve` (launchd on macOS, systemd on Linux). Prints `hmz daemon: installed <path>`. Exits 1 on any other system. |
| `uninstall` | Stops and removes the login service. Prints `hmz daemon: uninstalled <path>`. Exits 1 if none is installed. |

| Option | Of | Value | What it does |
| --- | --- | --- | --- |
| `--listen` | `serve` | `SPEC` | An additional listener to open. Repeatable. |
| `--stdio` | `connect` | | Required. |

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

`hmz devices`, `hmz runtimes`, `hmz easytier` and `hmz daemons` are commands written as one declaration. Every such command is a client of the daemon, takes the same three options, and prints the same kind of help.

| Option | What it does |
| --- | --- |
| `--json` | Prints one JSON document on standard output instead of text, and nothing on standard error. |
| `--daemon NAME` | Asks the daemon kept under `NAME` by [`hmz daemons`](#hmz-daemons) instead of this machine's. `local` is this machine's. |
| `--no-color` | Prints without terminal colours. |
| `-h`, `--help` | Prints everything about the command: usage, arguments, options, examples, the text and JSON it prints, exit statuses, and the daemon methods it calls. |

A group named alone, such as `hmz devices`, lists its commands.

| Status | Meaning |
| --- | --- |
| `0` | The command did what was asked. |
| `1` | The daemon refused the request. |
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

`--route` adds a route the code carries; without it, the code carries the routes the daemon listens on. `--seconds` sets how long the code can be claimed for, from `60` to `86400`; the default is `600`.

## hmz runtimes

```text
hmz runtimes list
hmz runtimes show BACKEND [NAME]
hmz runtimes set BACKEND NAME [--set FIELD=VALUE]... [--replace]
hmz runtimes remove BACKEND NAME
hmz runtimes check BACKEND NAME
hmz runtimes hosts
hmz runtimes import [HOST]... [--update]
```

`BACKEND` is `ssh`, `docker`, `swarm`, `apple-container` or `slurm`. See [Environments and runtimes](/reference/environments) for each backend's fields, and [Runtimes](/user/runtimes#from-the-command-line) for a walk-through.

| Command | Text output | `--json` |
| --- | --- | --- |
| `list` | A line for the daemon's own machine (`local` and its host name), then one line per runtime: backend, name, how it was made. | `{"local", "runtimes": [{"backend", "name", "made", "fields"}], "blanks"}`; `blanks` holds every field of each backend with its default. |
| `show BACKEND [NAME]` | One `field=value` line per field, the form `--set` takes. Without `NAME`, the fields a new runtime of the backend starts with. | `{"backend", "name", "made", "fields"}`; `name` and `made` are `null` without `NAME`. |
| `set BACKEND NAME` | `Saved` | `{"runtimes": [...]}`, every runtime afterwards. |
| `remove BACKEND NAME` | `Removed` | `{"runtimes": [...]}` |
| `check BACKEND NAME` | One line per field of the answer: name, then value. | `{"reached", "said", "home", "cpus", "memory", "gpus", "usable", "gpu_memory", "runtimes", "version", "short", "nodes"}` |
| `hosts` | One line per host of the SSH config on the daemon's machine: alias, machine, user, port, and `Saved` if a runtime of that name exists. | `{"hosts": [{"alias", "host", "user", "port", "identity_files", "proxy_jump", "saved"}]}` |
| `import [HOST]...` | `Imported` | `{"runtimes": [...]}` |

| Option | Of | What it does |
| --- | --- | --- |
| `--set FIELD=VALUE` | `set` | Sets one field. Repeatable. For a list field, repeat it once per item or give a JSON array. For a mapping field (`options`, `nodes`), write `FIELD=KEY=VALUE` once per pair or give a JSON object. An empty value clears a list or a mapping. |
| `--replace` | `set` | Changes the runtime already saved under that backend and name. Fields the line does not set keep their values. Without it, a name already saved is refused. |
| `--update` | `import` | Rewrites a runtime imported before from the host's current SSH config. |

`check` exits with status 4 if the runtime did not answer; its reason is in `said`.

## hmz easytier

```text
hmz easytier list
hmz easytier set NAME [--node URL]... [--secret-stdin] [--secret-env VAR]
hmz easytier remove NAME
hmz easytier nodes
```

| Command | Text output | `--json` |
| --- | --- | --- |
| `list` | One line per entry: name, `true` or `false` for whether a secret is saved, and its nodes. | `{"networks": [{"name", "nodes", "keyed"}]}`; `keyed` is a boolean. |
| `set NAME` | `Saved` | `{"networks": [...]}`, every entry afterwards. |
| `remove NAME` | `Removed` | `{"networks": [...]}` |
| `nodes` | One line per shared node: URL, `up` or `down`, uptime over 24 hours, EasyTier version, name. | `{"nodes": [{"url", "name", "version", "up", "uptime"}]}` |

| Option | Of | What it does |
| --- | --- | --- |
| `--node URL` | `set` | A shared node, as `tcp://host:port` (or `udp`, `ws`, `wss`, `quic`, `wg`). Repeatable. Without it, an existing entry keeps its nodes. |
| `--secret-stdin` | `set` | Reads the secret from standard input. |
| `--secret-env VAR` | `set` | Reads the secret from the environment variable `VAR`. |

A secret is at least 16 bytes. It is never read from the command line and never printed. Without either secret option, an existing entry keeps its secret. `remove` is refused while the daemon listens on the entry.

## hmz daemons

```text
hmz daemons list
hmz daemons add NAME [ROUTE]... [--id ID] [--replace]
hmz daemons remove NAME
hmz daemons show NAME [--connect]
hmz daemons pair NAME CODE [--device DEVICE] [--replace]
```

These commands keep the list of other machines' daemons that `--daemon NAME` names. The list is stored on this machine under the `daemons` key of `settings.toml` and is the one the terminal interface uses. `list`, `add` and `remove` contact no daemon.

| Command | Text output | `--json` |
| --- | --- | --- |
| `list` | One line per daemon: name, pinned daemon id, routes. This machine's is first, as `local`. | `{"daemons": [{"name", "id", "routes"}]}` |
| `add NAME ROUTE...` | `Added`, or `Saved` with `--replace`. | `{"name", "id", "routes"}` |
| `remove NAME` | `Removed` | `{"name"}` |
| `show NAME` | One line per field: name, then value. | `{"name", "id", "routes", "state", "version"}`; `state` and `version` are `null` without `--connect`. |
| `pair NAME CODE` | `Added` | `{"name", "id", "routes"}` |

| Option | Of | What it does |
| --- | --- | --- |
| `--id ID` | `add` | The daemon id to pin. Required unless the first route is an SSH route. |
| `--replace` | `add`, `pair` | Overwrites the daemon already kept under `NAME`. |
| `--connect` | `show` | Reaches the daemon and reports `state` `up` and its hmz `version`. Exits with status 3 if it cannot be reached. |
| `--device DEVICE` | `pair` | The name this machine is paired as there. Defaults to this machine's host name. |

A route is `stdio:ssh://[USER@]HOST[:PORT]`, `tcp://HOST:PORT`, `ws://…`, `wss://…`, `relay:wss://…`, `webrtc:wss://…` or `easytier:ENTRY`; routes are tried in the order given. See [Daemon and wire](/reference/daemon) for the route grammar. `pair` claims a code that `hmz devices pair` printed on the other machine; pass `-` as `CODE` to read it from standard input.

With `--daemon NAME`, any declared command asks that daemon instead of this machine's. An unknown name exits with status 1 and `No daemon is kept under the name <name>.`; a daemon that cannot be reached exits with status 3. `hmz` is never installed on a machine that has none.

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
