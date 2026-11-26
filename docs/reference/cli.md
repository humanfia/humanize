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
| `hmz --help`, `hmz -h` | Prints what `hmz` is, every command under what it is about, the options and exit statuses commands share, and what to run next. The same page as `hmz help`. |
| `hmz COMMAND --help` | Prints the help of one command. |
| `hmz help --json` | Prints every command as one JSON document. See [hmz help](#hmz-help). |

<!-- command list: written by scripts/cli_reference.py from the commands there are; do not edit by hand -->

| About | Command | What it does |
| --- | --- | --- |
| Chats and epics | `chat` | Start chats with an agent, send messages, and manage them. |
|  | `exec` | Run an agent flow in this directory. |
|  | `epic` | Start, follow and steer an epic held by this daemon. |
|  | `hosts` | List and close the hosts this daemon holds epics and chats in. |
| Past work and backups | `runs` | List, read back, export and import epics, and total their spend. |
|  | `backup` | Back epics up to git repositories, and download them again. |
| Environments | `env` | Work in the environments of a chat or an epic: their files, git and terminals. |
| Setting things up | `flows` | List flows, show what one declares, check and set up an epic. |
|  | `flowverses` | Add flowverses and install, update and uninstall their flows. |
|  | `workspaces` | List, add and forget workspaces, and browse the daemon's folders. |
|  | `settings` | Read and write the settings this daemon keeps. |
|  | `accounts` | List, add and remove the accounts agents run as. |
|  | `nous` | List, scan and write nous: models, tries and fallbacks. |
|  | `runtimes` | List, write, check and remove the runtimes environments are put on. |
|  | `easytier` | List, write and remove this machine's EasyTier networks. |
| Daemons and devices | `daemon` | Run, reach and install this machine's daemon. |
|  | `daemons` | List, add, pair and remove the daemons of other machines. |
|  | `devices` | List and revoke the devices paired with this daemon. |
|  | `relay` | Relay daemons and the devices that reach them. |
|  | `web` | Open this machine's epics in a browser on it. |
| Notices and questions | `notices` | List and follow what this daemon tells you about your epics and chats. |
|  | `ai` | Talk to Ai-chan, who operates hmz for you. |
|  | `btw` | Ask side questions of a session of an epic or chat. |
| This program | `skills` | Install, list and remove the hmz skill for using the CLI. |
|  | `help` | Show the help of hmz or of one command. |
|  | `update` | Update hmz to its newest release. |
|  | `internal` | Internal commands used by Humanize; do not run directly. |
| Other commands | `server` | Install and manage this machine's web server service. |

<!-- command list: end -->

`hmz help completions bash`, `zsh` or `fish` prints a completion script for that shell; see [hmz help](#hmz-help). Outside `hmz internal`, no option has an environment-variable equivalent; `HUMANIZE_RELEASES` alone changes where `hmz update` looks.

`hmz`, `exec`, `web`, `daemon connect` and every [declared command](#declared-commands) that asks this machine's daemon start the daemon if none runs. `relay`, `update`, `help` and `skills` do not, and neither does a command given `--daemon <name>` for another machine's daemon.

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
| `130` | `exec` or `chat` ended on SIGINT, or a [declared command](#declared-commands), `daemon connect --stdio` or `hmz internal anchor` was interrupted with Ctrl+C. |
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

## hmz server

Install and manage the web interface as a per-user service that starts at login.

```text
hmz server install
hmz server uninstall
hmz server status
```

| Subcommand | What it does |
| --- | --- |
| `install` | Installs and starts at login. Linux uses systemd --user; macOS uses a LaunchAgent. |
| `uninstall` | Stops the service, then removes its unit or plist. |
| `status` | If installed, prints its active and enabled state on Linux or loaded state on macOS, and the log path. Otherwise, prints that it is not installed and the service-file path. |

The service runs `hmz web --no-open`, is kept running, and writes stdout and stderr to a private per-user log. Stopping it lets the web server close cleanly. Exits 1 if the platform is unsupported or service management fails.

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

## Declared commands {#declared-commands}

Every command but `exec`, `web`, `daemon`, `relay`, `update` and `internal` is written as one declaration. Every such command prints the same kind of help and takes the same options. All but `hmz help` and `hmz skills` are clients of the daemon; a command that asks no daemon takes no `--daemon`, exits 1 when it refuses, and never exits 3.

| Option | What it does |
| --- | --- |
| `--json` | Prints one JSON document on standard output instead of text, and nothing on standard error. |
| `--daemon NAME` | Asks the daemon kept under `NAME` instead of this machine's. |
| `--no-color` | Prints without terminal colours. |
| `-h`, `--help` | Prints everything about the command: usage, arguments, options, examples, the text and JSON it prints, exit statuses, and the daemon methods it calls. |

A group named alone, such as `hmz devices`, lists its commands.

Help wraps to the terminal's width, up to 100 columns, and to 80 columns when standard output is not a terminal. Headings are bold where [colour](#output-streams) is allowed and `--no-color` is absent.

| Status | Meaning |
| --- | --- |
| `0` | The command did what was asked. |
| `1` | The daemon refused the request, or a question the command asked was not answered yes. |
| `2` | The command line could not be read. |
| `3` | The daemon could not be reached, did not answer in time, or went away while the command ran. |
| `130` | The command was interrupted with Ctrl+C. Nothing more is printed, and whatever the daemon holds goes on. |

A command that removes something asks first and takes `-y`/`--yes` to skip the question. It asks on standard error and only at a terminal: with `--json`, or when standard input is not a terminal, it exits 1 without `--yes`, as it does for any answer but `y` or `yes`. Nothing is changed in either case.

A relative `-w`/`--workspace` path is read from the directory the command is typed in. A path beginning `~` is expanded by the daemon, on its own machine.

On failure, the command writes `hmz <command>: <message>` to standard error. With `--json` it prints `{"error": {"code": <code>, "message": <message>}}` on standard output instead; `code` is the daemon's error code, `503` if the daemon is unreachable, or `504` if it did not answer in time.

The sections from here to `hmz internal` are written from the declarations by `scripts/cli_reference.py`.

<!-- declared commands: written by scripts/cli_reference.py from src/hmz/cli/commands; do not edit by hand -->

## hmz accounts

An account is a named set of credentials for one harness, kept apart from the harness's own sign-in. An agent is given one as `-a` spells it: `HARNESS@ACCOUNT/MODEL`. No command prints a credential, and a credential is never taken from the command line.

```text
hmz accounts list
hmz accounts ways [CLI]
hmz accounts add CLI NAME --way WAY [options]
hmz accounts correct CLI NAME [options]
hmz accounts remove CLI NAME
hmz accounts models CLI [NAME]
hmz accounts copy CLI NAME INTO
```

### hmz accounts list

List the accounts.

```text
hmz accounts list
```

| Example | What it does |
| --- | --- |
| `hmz accounts list` | List the accounts. |
| `hmz accounts list --json \| jq -r '.accounts[] \| "\(.cli)@\(.name)"'` | Print each account as `HARNESS@ACCOUNT` with jq. |

One line per account: harness, name (`Local` for the machine's own sign-in), sign-in method, the variables it sets, how many models it runs.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `gateway` | `string` | Name of the local gateway some ways of signing in go through. |
| `accounts` | `list` | Every account, the machine's own sign-in listed with an empty name. |
| `accounts[].cli` | `string` | The harness the account is for. |
| `accounts[].name` | `string` | Name of the account, empty for the machine's own sign-in. |
| `accounts[].way` | `string` | The sign-in method it was made by. |
| `accounts[].sets` | `list` | Names of the environment variables it sets, never their values. |
| `accounts[].made` | `string` | When it was made, ISO 8601, or empty for the machine's own sign-in. |
| `accounts[].models` | `list` | The models its harness last said it runs as this account. |
| `accounts[].asked` | `string` | When the harness was last asked for its models, ISO 8601, or empty if never. |
| `accounts[].serves` | `list` | The other harnesses the account can be copied to. |

Daemon methods: `accounts.list`.

### hmz accounts ways

Lists how an account can be made for each harness. A method marked `(at a terminal)` runs the harness's own sign-in and can only be used from `/settings` in `hmz`; any other is made by `hmz accounts add` from the answers it asks for.

```text
hmz accounts ways [CLI]
```

| Argument or option | What it is |
| --- | --- |
| `CLI` | List the sign-in methods of this harness only. |

| Example | What it does |
| --- | --- |
| `hmz accounts ways claude` | List the sign-in methods of `claude` and the variables each asks for. |
| `hmz accounts ways --json \| jq '.backends[].ways[] \| select(.terminal \| not) \| .name'` | Print the sign-in methods `hmz accounts add` can use with jq. |

One line per sign-in method: harness, method, what it is. Under it, indented, one line per answer it asks for: the variable and what it is.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `gateway` | `string` | Name of the local gateway some ways of signing in go through. |
| `backends` | `list` | Every harness of the daemon. |
| `backends[].cli` | `string` | Name of the harness. |
| `backends[].wants` | `string` | The command that installs what its gateway sign-in methods need, or empty. |
| `backends[].ways` | `list` | Its sign-in methods. |
| `backends[].ways[].name` | `string` | Name of the sign-in method, as `--way` takes it. |
| `backends[].ways[].about` | `string` | What the sign-in method is. |
| `backends[].ways[].group` | `string` | The gateway it goes through, or empty. |
| `backends[].ways[].terminal` | `boolean` | Whether it needs a terminal and so cannot be used by `hmz accounts add`. |
| `backends[].ways[].asks` | `list` | The answers it asks for. |
| `backends[].ways[].asks[].env` | `string` | The variable the answer is given as. |
| `backends[].ways[].asks[].about` | `string` | What the answer is. |
| `backends[].ways[].asks[].secret` | `boolean` | Whether the answer is a credential, taken by `--env` or `--stdin` only. |
| `backends[].ways[].asks[].fixed` | `string` | Its value where left unanswered, or empty where it must be answered. |

Daemon methods: `accounts.list`.

### hmz accounts add

Makes an account for a harness. `hmz accounts ways CLI` lists the sign-in methods and the answers each asks for. Give an answer that is a credential with `--env` or `--stdin`; `--set` refuses one, and no answer is ever printed.

```text
hmz accounts add CLI NAME --way WAY [options]
```

| Argument or option | What it is |
| --- | --- |
| `CLI` | The harness the account is for, such as `claude` or `codex`. |
| `NAME` | Name for the new account, such as `work`. |
| `--way WAY` | The sign-in method, as `hmz accounts ways` names it. |
| `--set NAME=VALUE` | An answer that is not a credential, as NAME=VALUE, NAME being the variable the way asks for. May be given more than once. |
| `--env NAME[=VAR]` | Take the answer NAME from the environment variable of the same name, or from VAR where written NAME=VAR; for credentials. May be given more than once. |
| `--stdin NAME` | Read the answer NAME from standard input, without its trailing line feed; for a credential. |

| Example | What it does |
| --- | --- |
| `hmz accounts add claude work --way key --env ANTHROPIC_API_KEY` | Make `claude@work` from the API key in the environment variable `ANTHROPIC_API_KEY`. |
| `pass show anthropic \| hmz accounts add claude work --way key --stdin ANTHROPIC_API_KEY` | Read the API key from standard input instead. |
| `hmz accounts add claude proxy --way anthropic-gateway --set ANTHROPIC_BASE_URL=https://llm.example.org --env ANTHROPIC_AUTH_TOKEN=PROXY_TOKEN` | Give a URL on the command line and a credential from the environment variable `PROXY_TOKEN`. |

The line `Made HARNESS@ACCOUNT.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `gateway` | `string` | Name of the local gateway some ways of signing in go through. |
| `accounts` | `list` | Every account, the machine's own sign-in listed with an empty name. |
| `accounts[].cli` | `string` | The harness the account is for. |
| `accounts[].name` | `string` | Name of the account, empty for the machine's own sign-in. |
| `accounts[].way` | `string` | The sign-in method it was made by. |
| `accounts[].sets` | `list` | Names of the environment variables it sets, never their values. |
| `accounts[].made` | `string` | When it was made, ISO 8601, or empty for the machine's own sign-in. |
| `accounts[].models` | `list` | The models its harness last said it runs as this account. |
| `accounts[].asked` | `string` | When the harness was last asked for its models, ISO 8601, or empty if never. |
| `accounts[].serves` | `list` | The other harnesses the account can be copied to. |

Daemon methods: `accounts.list`, `accounts.create`.

### hmz accounts correct

Changes the answers an account was made from. An answer not given stays as it was. Give a credential with `--env` or `--stdin`.

```text
hmz accounts correct CLI NAME [options]
```

| Argument or option | What it is |
| --- | --- |
| `CLI` | The harness the account is for, such as `claude` or `codex`. |
| `NAME` | Name of the account, as `hmz accounts list` prints it. |
| `--set NAME=VALUE` | An answer that is not a credential, as NAME=VALUE, NAME being the variable the way asks for. May be given more than once. |
| `--env NAME[=VAR]` | Take the answer NAME from the environment variable of the same name, or from VAR where written NAME=VAR; for credentials. May be given more than once. |
| `--stdin NAME` | Read the answer NAME from standard input, without its trailing line feed; for a credential. |

| Example | What it does |
| --- | --- |
| `hmz accounts correct claude work --env ANTHROPIC_API_KEY` | Replace the API key of `claude@work` with the one in the environment. |
| `hmz accounts correct claude proxy --set ANTHROPIC_BASE_URL=https://llm2.example.org` | Change the URL of `claude@proxy` and keep its credential. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `gateway` | `string` | Name of the local gateway some ways of signing in go through. |
| `accounts` | `list` | Every account, the machine's own sign-in listed with an empty name. |
| `accounts[].cli` | `string` | The harness the account is for. |
| `accounts[].name` | `string` | Name of the account, empty for the machine's own sign-in. |
| `accounts[].way` | `string` | The sign-in method it was made by. |
| `accounts[].sets` | `list` | Names of the environment variables it sets, never their values. |
| `accounts[].made` | `string` | When it was made, ISO 8601, or empty for the machine's own sign-in. |
| `accounts[].models` | `list` | The models its harness last said it runs as this account. |
| `accounts[].asked` | `string` | When the harness was last asked for its models, ISO 8601, or empty if never. |
| `accounts[].serves` | `list` | The other harnesses the account can be copied to. |

Daemon methods: `accounts.list`, `accounts.correct`.

### hmz accounts remove

Remove an account, credentials and all.

```text
hmz accounts remove CLI NAME
```

| Argument or option | What it is |
| --- | --- |
| `CLI` | The harness the account is for, such as `claude` or `codex`. |
| `NAME` | Name of the account, as `hmz accounts list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz accounts remove claude work` | Remove the account `claude@work`. |

The line `Removed`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `gateway` | `string` | Name of the local gateway some ways of signing in go through. |
| `accounts` | `list` | Every account, the machine's own sign-in listed with an empty name. |
| `accounts[].cli` | `string` | The harness the account is for. |
| `accounts[].name` | `string` | Name of the account, empty for the machine's own sign-in. |
| `accounts[].way` | `string` | The sign-in method it was made by. |
| `accounts[].sets` | `list` | Names of the environment variables it sets, never their values. |
| `accounts[].made` | `string` | When it was made, ISO 8601, or empty for the machine's own sign-in. |
| `accounts[].models` | `list` | The models its harness last said it runs as this account. |
| `accounts[].asked` | `string` | When the harness was last asked for its models, ISO 8601, or empty if never. |
| `accounts[].serves` | `list` | The other harnesses the account can be copied to. |

Daemon methods: `accounts.remove`.

### hmz accounts models

Asks the harness which models it runs as the account, and keeps the answer: it is what `hmz accounts list` and `hmz nous list` show from then on.

```text
hmz accounts models CLI [NAME]
```

| Argument or option | What it is |
| --- | --- |
| `CLI` | The harness the account is for, such as `claude` or `codex`. |
| `NAME` | Name of the account; the machine's own sign-in where not given. |

| Example | What it does |
| --- | --- |
| `hmz accounts models claude work` | Ask `claude` which models it runs as the account `work`. |
| `hmz accounts models codex` | Ask `codex` which models it runs as the machine's own sign-in. |

One model per line, or `No models listed`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `cli` | `string` | The harness that was asked. |
| `name` | `string` | Name of the account, empty for the machine's own sign-in. |
| `models` | `list` | The models the harness runs as the account. |
| `asked` | `string` | When the harness was asked, ISO 8601, or empty where the daemon does not say. |

Daemon methods: `accounts.models`, `nous.list`.

### hmz accounts copy

Writes an account down again for another harness its credentials can run. The `serves` field of `hmz accounts list --json` names the harnesses an account can be copied to.

```text
hmz accounts copy CLI NAME INTO
```

| Argument or option | What it is |
| --- | --- |
| `CLI` | The harness the account is for, such as `claude` or `codex`. |
| `NAME` | Name of the account, as `hmz accounts list` prints it. |
| `INTO` | The harness to copy it to. |

| Example | What it does |
| --- | --- |
| `hmz accounts copy claude work pi` | Copy the account `claude@work` to the harness `pi`. |

The line `Copied to HARNESS`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `gateway` | `string` | Name of the local gateway some ways of signing in go through. |
| `accounts` | `list` | Every account, the machine's own sign-in listed with an empty name. |
| `accounts[].cli` | `string` | The harness the account is for. |
| `accounts[].name` | `string` | Name of the account, empty for the machine's own sign-in. |
| `accounts[].way` | `string` | The sign-in method it was made by. |
| `accounts[].sets` | `list` | Names of the environment variables it sets, never their values. |
| `accounts[].made` | `string` | When it was made, ISO 8601, or empty for the machine's own sign-in. |
| `accounts[].models` | `list` | The models its harness last said it runs as this account. |
| `accounts[].asked` | `string` | When the harness was last asked for its models, ISO 8601, or empty if never. |
| `accounts[].serves` | `list` | The other harnesses the account can be copied to. |

Daemon methods: `accounts.copy`.

## hmz ai

Ai-chan is an agent that operates hmz for you within a scope: this daemon, one workspace or one epic. Each conversation with her has a number. These commands start a conversation, say the next line in one, and list, rename and delete conversations.

```text
hmz ai new TASK [options]
hmz ai list
hmz ai rename ID TITLE
hmz ai forget ID [options]
hmz ai say ID TEXT [options]
hmz ai wait ID [options]
hmz ai stop ID
```

### hmz ai new

Starts a conversation whose first message is TASK and prints its number. Without `--scope`, the scope is the epic where `--epic` is given, else the workspace where `--workspace` is given, else the daemon. With `--wait` it also waits for Ai-chan's answer and prints it.

```text
hmz ai new TASK [options]
```

| Argument or option | What it is |
| --- | --- |
| `TASK` | The first thing to tell Ai-chan; its first line becomes the conversation's title. |
| `--scope {daemon,workspace,epic}` | What Ai-chan reaches: every workspace and epic of this daemon, one workspace, or one epic. One of `daemon`, `workspace`, `epic`. |
| `-w, --workspace PATH` | The workspace of a workspace or epic scope, as an absolute path; when not given, the folder the command runs in. |
| `--epic NAME` | The epic of an epic scope, by its name. |
| `--nous NOUS` | The nous Ai-chan thinks with; when not given, the one the last conversation was started with. |
| `--preset {read-only,danger-full-access}` | What Ai-chan may do: read-only reads and changes nothing, danger-full-access changes what her scope reaches; read-only when not given. One of `read-only`, `danger-full-access`. |
| `--wait` | Also wait for Ai-chan's answer and print it. |
| `--timeout SECONDS` | How many seconds to wait for Ai-chan's answer before giving up. Default `600`. |

| Example | What it does |
| --- | --- |
| `hmz ai new "Which epics failed today?" --wait` | Starts a conversation scoped to this daemon and prints Ai-chan's answer. |
| `hmz ai new "Summarise this epic" --epic 20261117T100000.000Z-ab12cd --nous claude/claude-sonnet-4-5` | Starts a conversation scoped to one epic of this folder, with the nous named. |
| `id=$(hmz ai new "Tidy the worktrees" -w ~/project --preset danger-full-access --json \| jq .id)` | Starts a conversation that may change the workspace ~/project and keeps its number in a shell variable. |

Prints the conversation's number on the first line; with `--wait`, Ai-chan's answer after it.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `integer` | The conversation's number. |
| `workspace` | `string` | The workspace of the conversation's host. |
| `slot` | `string` | The slot of the conversation's host. |
| `answer` | `string\|null` | What Ai-chan said, with `--wait`; null without it. |
| `mode` | `string\|null` | With `--wait`, `listen` when her turn is over, anything else when she asks a question mid-turn; null without `--wait`. |

Daemon methods: `aichan.create`, `aichan.list`, `epic.attach`, `epic.status`, `epic.detach`.

### hmz ai list

List the conversations with Ai-chan, newest first.

```text
hmz ai list
```

| Example | What it does |
| --- | --- |
| `hmz ai list` | Lists the conversations with Ai-chan. |
| `hmz ai list --json \| jq '.conversations[] \| select(.state == "running") \| .id'` | Prints the numbers of the conversations Ai-chan is answering in. |

Prints one line per conversation, newest first: its number, state, scope, preset, nous and title.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `conversations` | `list` | The conversations, newest first. |
| `conversations[].id` | `integer` | The conversation's number. |
| `conversations[].title` | `string` | Its title. |
| `conversations[].scope` | `string` | What Ai-chan reaches in it: `daemon`, `workspace` or `epic`. |
| `conversations[].workspace` | `string` | The workspace of its host. |
| `conversations[].epic` | `string` | The epic of an epic scope, else empty. |
| `conversations[].nous` | `string` | The nous Ai-chan thinks with in it. |
| `conversations[].preset` | `string` | What she may do: `read-only` or `danger-full-access`. |
| `conversations[].slot` | `string` | The slot of the conversation's host. |
| `conversations[].state` | `string` | `running` while Ai-chan answers, `waiting` between turns, `folded` when no host holds it. |
| `conversations[].created` | `string` | When it was started, ISO 8601 in UTC. |
| `conversations[].latest` | `string` | The start of what was last said in it. |
| `conversations[].updated` | `string` | When that was said, ISO 8601 in UTC. |

Daemon methods: `aichan.list`.

### hmz ai rename

Change the title of a conversation with Ai-chan.

```text
hmz ai rename ID TITLE
```

| Argument or option | What it is |
| --- | --- |
| `ID` | The conversation's number, as `hmz ai list` prints it. |
| `TITLE` | The new title, 1 to 240 characters. |

| Example | What it does |
| --- | --- |
| `hmz ai rename 3 "Failed epics, Tuesday"` | Gives conversation 3 a new title. |

Prints that the conversation was renamed.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `integer` | The conversation's number. |
| `title` | `string` | The title given. |

Daemon methods: `aichan.rename`.

### hmz ai forget

Deletes the conversation and closes its host; it cannot be brought back. Asks first on standard error unless `--yes` is given; where nobody is at a terminal, or with `--json`, `--yes` is needed.

```text
hmz ai forget ID [options]
```

| Argument or option | What it is |
| --- | --- |
| `ID` | The conversation's number, as `hmz ai list` prints it. |
| `-y, --yes` | Do it without asking first. |

| Example | What it does |
| --- | --- |
| `hmz ai forget 3` | Asks, then deletes conversation 3. |
| `hmz ai forget 3 --yes` | Deletes conversation 3 without asking. |

Prints that the conversation was deleted.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `integer` | The conversation's number. |

| Status | Meaning |
| --- | --- |
| `1` | The daemon refused it, or you did not answer yes. |

Daemon methods: `aichan.list`, `aichan.forget`.

### hmz ai say

The line answers what Ai-chan waits on, or is said into her turn while she is answering; a conversation that was folded away is carried on first. Waits for her answer and prints it, unless `--no-wait` is given.

```text
hmz ai say ID TEXT [options]
```

| Argument or option | What it is |
| --- | --- |
| `ID` | The conversation's number, as `hmz ai list` prints it. |
| `TEXT` | The line to say to Ai-chan. |
| `--no-wait` | Return once the line is taken, without waiting for Ai-chan's answer. |
| `--timeout SECONDS` | How many seconds to wait for Ai-chan's answer before giving up. Default `600`. |

| Example | What it does |
| --- | --- |
| `hmz ai say 3 "And yesterday?"` | Says the next line in conversation 3 and prints Ai-chan's answer. |
| `hmz ai say 3 "Stop the oldest one" --no-wait && hmz ai wait 3 --json` | Says a line without waiting, then waits for the answer as JSON. |

Prints what Ai-chan said, or nothing with `--no-wait`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `integer` | The conversation's number. |
| `answer` | `string\|null` | What Ai-chan said, or null with `--no-wait`. |
| `mode` | `string\|null` | `listen` when her turn is over, anything else when she asks a question mid-turn, or null with `--no-wait`. |

Daemon methods: `aichan.list`, `epic.attach`, `epic.status`, `epic.answer`, `epic.say`, `epic.detach`.

### hmz ai wait

Waits while Ai-chan's turn is open, then prints what she waits on you with: her last answer, or a question she asks mid-turn. A conversation that was folded away is carried on first.

```text
hmz ai wait ID [options]
```

| Argument or option | What it is |
| --- | --- |
| `ID` | The conversation's number, as `hmz ai list` prints it. |
| `--timeout SECONDS` | How many seconds to wait for Ai-chan's answer before giving up. Default `600`. |

| Example | What it does |
| --- | --- |
| `hmz ai wait 3` | Waits for Ai-chan's answer in conversation 3 and prints it. |
| `hmz ai wait 3 --timeout 60 --json` | Waits at most a minute, and prints the answer as JSON. |

Prints what Ai-chan said.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `integer` | The conversation's number. |
| `answer` | `string` | What Ai-chan said. |
| `mode` | `string` | `listen` when her turn is over, anything else when she asks a question mid-turn. |

Daemon methods: `aichan.list`, `epic.attach`, `epic.status`, `epic.detach`.

### hmz ai stop

Stop Ai-chan's open turn, leaving the conversation between turns.

```text
hmz ai stop ID
```

| Argument or option | What it is |
| --- | --- |
| `ID` | The conversation's number, as `hmz ai list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz ai stop 3` | Stops what Ai-chan is doing in conversation 3. |

Prints that it was stopped.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `integer` | The conversation's number. |

Daemon methods: `aichan.list`, `epic.attach`, `epic.stop`, `epic.detach`.

## hmz backup

A backup target is a git repository set in Settings > Backup. These commands upload an epic to targets, list targets and what one holds, and download from one.

```text
hmz backup run EPIC [options]
hmz backup list [options]
hmz backup pull KEY --target NAME
```

### hmz backup run

Uploads the epic to the targets it was started with, else the default targets, and waits to say how each went. Interrupting this command does not stop the upload.

```text
hmz backup run EPIC [options]
```

| Argument or option | What it is |
| --- | --- |
| `EPIC` | The epic's name, as `hmz runs list` prints it. |
| `--to NAME` | A backup target to upload to, as `hmz backup list` prints it; when not given, the targets the epic was started with, else the default targets. May be given more than once. |
| `--no-wait` | Return once the daemon has queued the uploads, without waiting to hear how they went. |
| `--timeout SECONDS` | How many seconds to wait for the uploads to finish. Default `600`. |

| Example | What it does |
| --- | --- |
| `hmz backup run 20261012T091500.123Z-1a2b3c` | Uploads the epic to its own targets, or the default ones, and waits for the result. |
| `hmz backup run NAME --to lab --to home` | Uploads the epic to the targets `lab` and `home`. |
| `hmz backup run NAME --no-wait --json` | Queues the uploads and prints the targets queued, as JSON. |

Prints one line per target that took the epic. A target that did not is reported as the command's error, and the command exits `1`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `queued` | `list` | Names of the targets the upload was queued for. |
| `backed` | `object` | How each upload went, by target name, with `at`, `ok`, `error` and `why`; empty with `--no-wait`. |

Daemon methods: `runs.backup`, `runs.get`.

### hmz backup list

Without `--target` it lists the backup targets set up on this daemon. With `--target` it fetches that repository and lists every epic and chat it holds, from every machine.

```text
hmz backup list [options]
```

| Argument or option | What it is |
| --- | --- |
| `--target NAME` | The backup target whose epics and chats to list; the targets themselves are listed when not given. |

| Example | What it does |
| --- | --- |
| `hmz backup list` | Lists the backup targets. |
| `hmz backup list --target lab` | Lists the epics and chats the target lab holds. |
| `hmz backup list --target lab --json \| jq -r '.epics[] \| select(.here \| not) \| .key'` | Prints the key of every epic lab holds that this machine does not. |

Line per target: name, URL, branch, policies, `default` where it is one. With `--target`, line per epic or chat: key, status, flow or `chat`, `here` if held here, task.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `targets` | `list` | Without `--target`: the backup targets, each with `name`, `url`, `branch`, `policies` and `every`. |
| `defaults` | `list` | Without `--target`: names of the targets an epic is backed up to when it names none. |
| `epics` | `list` | With `--target`: the epics and chats the target holds, newest first. |
| `epics[].key` | `string` | What `hmz backup pull` takes: `&lt;machine>/&lt;workspace>/&lt;epic>`. |
| `epics[].machine` | `string` | The machine the epic ran on. |
| `epics[].workspace` | `string` | The workspace the epic ran in. |
| `epics[].epic` | `string` | The epic's name, or the chat's. |
| `epics[].flow` | `string` | The flow the epic ran, or an empty string for a chat. |
| `epics[].task` | `string` | The epic's task, or the chat's first message. |
| `epics[].began` | `string` | When it began, ISO 8601. |
| `epics[].ended` | `string` | When it ended, ISO 8601, or an empty string. |
| `epics[].how` | `string` | How it ended, or an empty string where it had not when backed up. |
| `epics[].head` | `string` | The commit of the target that holds it. |
| `epics[].chat` | `boolean` | Whether it is a chat rather than an epic. |
| `epics[].here` | `boolean` | Whether this machine already holds it. |

Daemon methods: `settings.get`, `backups.epics`.

### hmz backup pull

Fetches the target and writes the epic down on this daemon as an import does; a chat goes among the chats. One this machine already holds is refused.

```text
hmz backup pull KEY --target NAME
```

| Argument or option | What it is |
| --- | --- |
| `KEY` | The epic or chat, as `&lt;machine>/&lt;workspace>/&lt;epic>` or, where only one in the target has it, its name alone; `hmz backup list --target` prints both. |
| `--target NAME` | The backup target to download from, as `hmz backup list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz backup pull laptop/project/20261012T091500.123Z-1a2b3c --target lab` | Downloads that epic of the machine laptop from the target lab. |
| `hmz backup pull 20261012T091500.123Z-1a2b3c --target lab --json` | Downloads the one epic of that name lab holds and prints its name as JSON. |

The name of the epic or chat downloaded.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | Name of the epic or chat downloaded. |

Daemon methods: `backups.epics`, `backups.pull`.

## hmz btw

A side question asks one session of an epic or a chat about itself. A read-only copy of that session answers in a side conversation, so the question never reaches the epic or the chat. These commands ask one, list the side conversations that are open, and close them.

```text
hmz btw ask QUESTION [options]
hmz btw sessions [options]
hmz btw list [options]
hmz btw show ASIDE [options]
hmz btw leave [ASIDE] [options]
```

### hmz btw ask

The first question opens a side conversation and prints its name on standard error; give that name as `--aside` to ask the next question in the same side conversation. Without `--epic` or `--chat` the question is about the epic in view in the workspace.

```text
hmz btw ask QUESTION [options]
```

| Argument or option | What it is |
| --- | --- |
| `QUESTION` | The question to ask. |
| `--to SESSION` | The session to ask, written `&lt;agent>/&lt;n>` as `hmz btw sessions` prints it; with `--chat` and no `--to`, the chat's newest session is asked. |
| `--aside NAME` | The side conversation to go on in, by its name; when not given, a new side conversation is opened. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--epic NAME` | The epic the side questions are about, by its name; when not given, the epic in view in the workspace. |
| `--chat NAME` | The chat the side questions are about, by its name, in place of `--epic`. |

| Example | What it does |
| --- | --- |
| `hmz btw ask "What are you changing right now?" --to Ada/1` | Asks session Ada/1 of the epic in view in this folder a side question. |
| `hmz btw ask "Why did the tests fail?" --chat 20261117T100000-ab12cd` | Asks the newest session of that chat a side question. |
| `hmz btw ask "And after that?" --to Ada/1 --aside 3f9c2a1b` | Asks the next question in the side conversation named 3f9c2a1b. |

Prints the answer on standard output, and the name of a side conversation it opened on standard error.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `aside` | `string` | The name of the side conversation it was asked in. |
| `to` | `string` | The session that was asked, as `&lt;agent>/&lt;n>`. |
| `question` | `string` | The question that was asked. |
| `answer` | `string` | The answer the session's copy gave. |

Daemon methods: `btw.ask`, `btw.list`, `chat.get`.

### hmz btw sessions

List the sessions of an epic or a chat.

```text
hmz btw sessions [options]
```

| Argument or option | What it is |
| --- | --- |
| `--epic NAME` | The epic whose sessions are listed, by its name. |
| `--chat NAME` | The chat whose sessions are listed, by its name. |

| Example | What it does |
| --- | --- |
| `hmz btw sessions --epic 20261117T100000.000Z-ab12cd` | Lists the sessions of that epic, oldest first. |
| `hmz btw sessions --chat 20261117T100000-ab12cd --json \| jq -r '.sessions[-1].session'` | Prints the newest session of that chat. |

Prints one line per session, oldest first: the session as `--to` takes it, and its harness.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `sessions` | `list` | The sessions, oldest first. |
| `sessions[].session` | `string` | The session as `--to` takes it, `&lt;agent>/&lt;n>`. |
| `sessions[].agent` | `string` | The name of the agent whose session it is. |
| `sessions[].harness` | `string` | The harness that ran the session. |

Daemon methods: `runs.get`, `chat.get`.

### hmz btw list

List the side conversations open about an epic or chat.

```text
hmz btw list [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--epic NAME` | The epic the side questions are about, by its name; when not given, the epic in view in the workspace. |
| `--chat NAME` | The chat the side questions are about, by its name, in place of `--epic`. |

| Example | What it does |
| --- | --- |
| `hmz btw list` | Lists the side conversations open about the epic in view in this folder. |
| `hmz btw list --chat 20261117T100000-ab12cd --json` | Lists the side conversations open about that chat, as JSON. |

Prints one line per side conversation, in the order opened: its name, the session it asks, how many questions it has answered, and the question it is answering now.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `asides` | `list` | The side conversations open, in the order opened. |
| `asides[].aside` | `string` | The name of the side conversation. |
| `asides[].to` | `string` | The session it asks. |
| `asides[].question` | `string` | The question it is answering now, empty when it is answering none. |
| `asides[].said` | `list` | The questions it has answered, oldest first, each with `question` and `answer`. |

Daemon methods: `btw.list`.

### hmz btw show

Print the questions and answers of one side conversation.

```text
hmz btw show ASIDE [options]
```

| Argument or option | What it is |
| --- | --- |
| `ASIDE` | The name of the side conversation, as `hmz btw list` prints it. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--epic NAME` | The epic the side questions are about, by its name; when not given, the epic in view in the workspace. |
| `--chat NAME` | The chat the side questions are about, by its name, in place of `--epic`. |

| Example | What it does |
| --- | --- |
| `hmz btw show 3f9c2a1b` | Prints every side question asked in side conversation 3f9c2a1b and its answer. |
| `hmz btw show 3f9c2a1b --json \| jq -r '.said[-1].answer'` | Prints the latest answer of side conversation 3f9c2a1b. |

Prints each question on a line starting with `>`, followed by its answer, oldest first.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `aside` | `string` | The name of the side conversation. |
| `to` | `string` | The session it asks. |
| `question` | `string` | The question it is answering now, empty when it is answering none. |
| `said` | `list` | The questions answered in it, oldest first. |
| `said[].question` | `string` | One question that was asked. |
| `said[].answer` | `string` | The answer to that question. |

Daemon methods: `btw.list`.

### hmz btw leave

Close one side conversation, or every one in the workspace.

```text
hmz btw leave [ASIDE] [options]
```

| Argument or option | What it is |
| --- | --- |
| `ASIDE` | The name of the side conversation to close; left out with `--all`. |
| `--all` | Close every side conversation of the workspace. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |

| Example | What it does |
| --- | --- |
| `hmz btw leave 3f9c2a1b` | Closes the side conversation named 3f9c2a1b. |
| `hmz btw leave --all -w ~/project` | Closes every side conversation of the workspace ~/project. |

Prints that it was closed.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `aside` | `string\|null` | The name of the side conversation closed, or null when every one was closed. |

Daemon methods: `btw.leave`.

## hmz chat

A chat is one conversation with one agent in a folder, kept by the daemon under an id. `hmz chat start` and `hmz chat say` each print the agent's answer.

```text
hmz chat start MESSAGE [options]
hmz chat say CHAT MESSAGE [options]
hmz chat list [options]
hmz chat show CHAT [options]
hmz chat rename CHAT TITLE
hmz chat fork CHAT
hmz chat archive CHAT
hmz chat unarchive CHAT
hmz chat delete CHAT [options]
hmz chat stop CHAT
hmz chat set CHAT [options]
hmz chat move CHAT ENV
hmz chat agent CHAT AGENT
hmz chat commands CHAT
hmz chat backup CHAT [options]
hmz chat harness list [options]
hmz chat harness show HARNESS SESSION [options]
hmz chat harness adopt HARNESS SESSION [options]
```

### hmz chat start

Starts a chat in the current folder, sends MESSAGE and waits for the answer. A failed turn exits with status 1; a signal leaves the chat going in the daemon.

```text
hmz chat start MESSAGE [options]
```

| Argument or option | What it is |
| --- | --- |
| `MESSAGE` | The chat's first message; put `--` before a message that starts with a dash. |
| `-a, --agent AGENT` | The agent to talk to, written HARNESS[@ACCOUNT]/MODEL[:EFFORT]; when not given, the agent remembered for the folder. |
| `-e, --env ENV` | The environment the agent works in, written BACKEND[@RUNTIME][/DIRECTORY]; when not given, the folder itself. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--no-folder` | Start the chat in no folder; the daemon makes a directory for this chat alone. |
| `--worktree` | A new git worktree of the folder, which the folder itself is left out of. |
| `--permission {read-only,workspace-write,danger-full-access}` | What the agent may change; `workspace-write` when not given. One of `read-only`, `workspace-write`, `danger-full-access`. |
| `--prefer {native,flow}` | Which one a `$name` line runs when both a skill of the harness (`native`) and a flow (`flow`) have that name. One of `native`, `flow`. |
| `--remember` | Remember the agent for this folder, so that the next chat started here without `-a` uses it. |
| `--detach` | Return as soon as the message is sent, without waiting for the answer; read the answer later with `hmz chat show`. |
| `--events` | Print each record of the turn as one JSON object per line while it happens, and the final JSON document as the last line. |

| Example | What it does |
| --- | --- |
| `hmz chat start -a claude/claude-haiku-4-5 "What does charge() do?"` | Start a chat in this folder and print the agent's answer. |
| `id=$(hmz chat start --json -a codex/gpt-5.2:high "Fix the failing test" \| jq -r .chat)` | Start a chat from a script and keep its id for `hmz chat say`. |
| `hmz chat start --worktree --permission read-only "Review the parser"` | Start a chat in a new git worktree of the folder, with an agent that may only read. |
| `hmz chat start --detach "Run the whole test suite"` | Start a chat without waiting, and print its id. |

Prints the agent's answer on standard output, and the chat's id and the turn as it goes on standard error.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `chat` | `string` | The chat's id, which the other `hmz chat` commands take; also present beside `error` when the turn failed. |
| `workspace` | `string` | The folder the chat is of, as an absolute path. |
| `slot` | `string` | The slot of the host that holds the chat. |
| `answer` | `string` | What the agent answered; empty with `--detach`. |
| `notes` | `list` | What the chat said beside the answer, such as why it refused the message. |
| `detached` | `boolean` | Whether the command returned without waiting for the answer. |

| Status | Meaning |
| --- | --- |
| `129` | A hangup (SIGHUP) ended the command; the chat goes on in the daemon. |
| `130` | An interrupt (ctrl+c, SIGINT) ended the command; the chat goes on in the daemon. |
| `143` | A termination signal (SIGTERM) ended the command; the chat goes on in the daemon. |

Daemon methods: `chat.start`, `chat.say`, `epic.attach`, `epic.detach`, `settings.get`.

### hmz chat say

Sends MESSAGE as the chat's next turn and waits until the agent has answered. A chat that is resting is carried on first; a failed turn exits with status 1.

```text
hmz chat say CHAT MESSAGE [options]
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |
| `MESSAGE` | The next message; put `--` before a message that starts with a dash. |
| `--detach` | Return as soon as the message is sent, without waiting for the answer; read the answer later with `hmz chat show`. |
| `--events` | Print each record of the turn as one JSON object per line while it happens, and the final JSON document as the last line. |

| Example | What it does |
| --- | --- |
| `hmz chat say 20261117T100000.000Z-ab12cd "And how is it tested?"` | Send the next message to a chat and print the answer. |
| `hmz chat say --json "$id" "Now run the linter" \| jq -r .answer` | Send a message from a script and read the answer out of the JSON document with jq. |
| `hmz chat say --events "$id" "Now run the linter"` | Follow the turn as JSON lines, one record per line. |

Prints the agent's answer on standard output, and the chat's id and the turn as it goes on standard error.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `chat` | `string` | The chat's id, which the other `hmz chat` commands take; also present beside `error` when the turn failed. |
| `workspace` | `string` | The folder the chat is of, as an absolute path. |
| `slot` | `string` | The slot of the host that holds the chat. |
| `answer` | `string` | What the agent answered; empty with `--detach`. |
| `notes` | `list` | What the chat said beside the answer, such as why it refused the message. |
| `detached` | `boolean` | Whether the command returned without waiting for the answer. |

| Status | Meaning |
| --- | --- |
| `129` | A hangup (SIGHUP) ended the command; the chat goes on in the daemon. |
| `130` | An interrupt (ctrl+c, SIGINT) ended the command; the chat goes on in the daemon. |
| `143` | A termination signal (SIGTERM) ended the command; the chat goes on in the daemon. |

Daemon methods: `chat.get`, `chat.say`, `chat.start`, `epic.attach`, `epic.detach`.

### hmz chat list

List the chats of this folder, newest first.

```text
hmz chat list [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The folder whose chats are listed; by default, the current directory. |
| `--all` | List the chats of every folder. |
| `--archived` | List the archived chats instead of the others. |
| `-q, --search TEXT` | Only the chats whose title, first message or id contains this text. |
| `--limit N` | How many to list at most, up to 200. |
| `--offset N` | How many of the newest to skip. |

| Example | What it does |
| --- | --- |
| `hmz chat list` | List the chats of this folder. |
| `hmz chat list --all --json \| jq -r '.chats[] \| select(.state == "turn") \| .id'` | Print the ids of the chats of every folder whose turn is open, with jq. |
| `hmz chat list --archived -q parser` | Find archived chats by a word in their title. |

One line per chat: id, state, title.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `chats` | `list` | The chats, newest first. |
| `total` | `integer` | How many there are in all, beyond this page too. |
| `offset` | `integer` | How many were skipped. |
| `limit` | `integer` | How many were listed at most. |
| `chats[].id` | `string` | The chat's id. |
| `chats[].title` | `string` | The chat's title. |
| `chats[].state` | `string` | `turn` while the agent works, `asking` while it waits for an answer, `going` while a host holds the chat between turns, `failed`, or `resting`. |
| `chats[].agent` | `string` | The chat's agent, written HARNESS[@ACCOUNT]/MODEL[:EFFORT]. |
| `chats[].model` | `string` | The model the agent runs. |
| `chats[].permission` | `string` | What the agent may change: `read-only`, `workspace-write` or `danger-full-access`. |
| `chats[].env` | `string` | The environment the agent works in, written BACKEND[@RUNTIME][/DIRECTORY]. |
| `chats[].workdir` | `string` | The directory the agent works in. |
| `chats[].workspace` | `string` | The folder the chat is of, as an absolute path. |
| `chats[].folderless` | `boolean` | Whether the chat is of no folder. |
| `chats[].slot` | `string` | The slot of the host that holds the chat, empty when none does. |
| `chats[].asking` | `list` | The questions the agent asked and waits on. |
| `chats[].began` | `string` | When the chat started, ISO 8601. |
| `chats[].updated` | `string` | When the chat was last written, ISO 8601. |
| `chats[].archived` | `boolean` | Whether the chat is archived. |
| `chats[].spent` | `object` | What the chat has used: tokens, and cost where priced. |

Daemon methods: `chat.list`.

### hmz chat show

Print one chat, its state and what was said.

```text
hmz chat show CHAT [options]
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |
| `--trace` | Also print what was said and done in the chat, read from its logs. |

| Example | What it does |
| --- | --- |
| `hmz chat show 20261117T100000.000Z-ab12cd` | Print one chat. |
| `until [ "$(hmz chat show "$id" --json \| jq -r .state)" != turn ]; do sleep 2; done` | Wait for a detached chat's turn to finish by reading its state with jq. |

One line per field, name then value; with `--trace`, what each harness session said and did after them.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `string` | The chat's id. |
| `title` | `string` | The chat's title. |
| `state` | `string` | `turn` while the agent works, `asking` while it waits for an answer, `going` while a host holds the chat between turns, `failed`, or `resting`. |
| `agent` | `string` | The chat's agent, written HARNESS[@ACCOUNT]/MODEL[:EFFORT]. |
| `model` | `string` | The model the agent runs. |
| `permission` | `string` | What the agent may change: `read-only`, `workspace-write` or `danger-full-access`. |
| `env` | `string` | The environment the agent works in, written BACKEND[@RUNTIME][/DIRECTORY]. |
| `workdir` | `string` | The directory the agent works in. |
| `workspace` | `string` | The folder the chat is of, as an absolute path. |
| `folderless` | `boolean` | Whether the chat is of no folder. |
| `slot` | `string` | The slot of the host that holds the chat, empty when none does. |
| `asking` | `list` | The questions the agent asked and waits on. |
| `began` | `string` | When the chat started, ISO 8601. |
| `updated` | `string` | When the chat was last written, ISO 8601. |
| `archived` | `boolean` | Whether the chat is archived. |
| `spent` | `object` | What the chat has used: tokens, and cost where priced. |
| `at` | `string` | The directory the chat is written down in. |
| `task` | `string` | The chat's first message, whole. |
| `prefer` | `string` | What the chat set a `$name` to run, `native` or `flow`, empty when it follows the settings. |
| `forked` | `string` | The id of the chat this one was forked from, empty for none. |
| `adopted` | `string` | The harness session this chat continues, as HARNESS:ID, empty for none. |
| `agents` | `list` | The agents of the chat. |
| `sessions` | `list` | The harness sessions the chat opened. |
| `earlier` | `integer` | How many of its harness sessions were opened before the chat was last carried on. |
| `backup` | `list` | The backup targets the chat was started with. |
| `backed` | `object` | How each backup of the chat went, by target. |
| `trace` | `list` | With `--trace`, what each harness session said and did, read from its logs. |

Daemon methods: `chat.get`.

### hmz chat rename

Change a chat's title.

```text
hmz chat rename CHAT TITLE
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |
| `TITLE` | The new title, at most 240 characters. |

| Example | What it does |
| --- | --- |
| `hmz chat rename 20261117T100000.000Z-ab12cd "Discount codes"` | Give a chat a title. |

The chat's line, as `hmz chat list` prints it.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `string` | The chat's id. |
| `title` | `string` | The chat's title. |
| `state` | `string` | `turn` while the agent works, `asking` while it waits for an answer, `going` while a host holds the chat between turns, `failed`, or `resting`. |
| `agent` | `string` | The chat's agent, written HARNESS[@ACCOUNT]/MODEL[:EFFORT]. |
| `model` | `string` | The model the agent runs. |
| `permission` | `string` | What the agent may change: `read-only`, `workspace-write` or `danger-full-access`. |
| `env` | `string` | The environment the agent works in, written BACKEND[@RUNTIME][/DIRECTORY]. |
| `workdir` | `string` | The directory the agent works in. |
| `workspace` | `string` | The folder the chat is of, as an absolute path. |
| `folderless` | `boolean` | Whether the chat is of no folder. |
| `slot` | `string` | The slot of the host that holds the chat, empty when none does. |
| `asking` | `list` | The questions the agent asked and waits on. |
| `began` | `string` | When the chat started, ISO 8601. |
| `updated` | `string` | When the chat was last written, ISO 8601. |
| `archived` | `boolean` | Whether the chat is archived. |
| `spent` | `object` | What the chat has used: tokens, and cost where priced. |

Daemon methods: `chat.rename`.

### hmz chat fork

Make a new chat that goes on from this one's turns.

```text
hmz chat fork CHAT
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz chat fork 20261117T100000.000Z-ab12cd` | Fork a chat and print the new chat's id. |
| `hmz chat say $(hmz chat fork "$id") "Try it the other way"` | Fork a chat and send the fork a message. |

Prints the new chat's id.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `chat` | `string` | The new chat's id. |

Daemon methods: `chat.fork`.

### hmz chat archive

Archive a chat, hiding it from the list.

```text
hmz chat archive CHAT
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz chat archive 20261117T100000.000Z-ab12cd` | Archive a chat. |

The chat's line, as `hmz chat list` prints it.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `string` | The chat's id. |
| `title` | `string` | The chat's title. |
| `state` | `string` | `turn` while the agent works, `asking` while it waits for an answer, `going` while a host holds the chat between turns, `failed`, or `resting`. |
| `agent` | `string` | The chat's agent, written HARNESS[@ACCOUNT]/MODEL[:EFFORT]. |
| `model` | `string` | The model the agent runs. |
| `permission` | `string` | What the agent may change: `read-only`, `workspace-write` or `danger-full-access`. |
| `env` | `string` | The environment the agent works in, written BACKEND[@RUNTIME][/DIRECTORY]. |
| `workdir` | `string` | The directory the agent works in. |
| `workspace` | `string` | The folder the chat is of, as an absolute path. |
| `folderless` | `boolean` | Whether the chat is of no folder. |
| `slot` | `string` | The slot of the host that holds the chat, empty when none does. |
| `asking` | `list` | The questions the agent asked and waits on. |
| `began` | `string` | When the chat started, ISO 8601. |
| `updated` | `string` | When the chat was last written, ISO 8601. |
| `archived` | `boolean` | Whether the chat is archived. |
| `spent` | `object` | What the chat has used: tokens, and cost where priced. |

Daemon methods: `chat.archive`.

### hmz chat unarchive

Put an archived chat back in the list.

```text
hmz chat unarchive CHAT
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz chat unarchive 20261117T100000.000Z-ab12cd` | Put an archived chat back in the list. |

The chat's line, as `hmz chat list` prints it.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `string` | The chat's id. |
| `title` | `string` | The chat's title. |
| `state` | `string` | `turn` while the agent works, `asking` while it waits for an answer, `going` while a host holds the chat between turns, `failed`, or `resting`. |
| `agent` | `string` | The chat's agent, written HARNESS[@ACCOUNT]/MODEL[:EFFORT]. |
| `model` | `string` | The model the agent runs. |
| `permission` | `string` | What the agent may change: `read-only`, `workspace-write` or `danger-full-access`. |
| `env` | `string` | The environment the agent works in, written BACKEND[@RUNTIME][/DIRECTORY]. |
| `workdir` | `string` | The directory the agent works in. |
| `workspace` | `string` | The folder the chat is of, as an absolute path. |
| `folderless` | `boolean` | Whether the chat is of no folder. |
| `slot` | `string` | The slot of the host that holds the chat, empty when none does. |
| `asking` | `list` | The questions the agent asked and waits on. |
| `began` | `string` | When the chat started, ISO 8601. |
| `updated` | `string` | When the chat was last written, ISO 8601. |
| `archived` | `boolean` | Whether the chat is archived. |
| `spent` | `object` | What the chat has used: tokens, and cost where priced. |

Daemon methods: `chat.unarchive`.

### hmz chat delete

Asks before deleting unless `--yes` is given; without a terminal on standard input it deletes nothing without `--yes`. A deleted chat cannot be brought back.

```text
hmz chat delete CHAT [options]
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |
| `-y, --yes` | Do it without asking first. |

| Example | What it does |
| --- | --- |
| `hmz chat delete 20261117T100000.000Z-ab12cd` | Delete a chat after confirming at the terminal. |
| `hmz chat delete --yes "$id"` | Delete a chat from a script without being asked. |

Prints nothing on standard output, and asks the question on standard error.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `deleted` | `string` | The id of the chat that was deleted. |

| Status | Meaning |
| --- | --- |
| `1` | The daemon refused it, or you did not answer yes. |

Daemon methods: `chat.get`, `chat.delete`.

### hmz chat stop

Stop a chat's open turn, leaving it between turns.

```text
hmz chat stop CHAT
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz chat stop 20261117T100000.000Z-ab12cd` | Stop the turn a chat is taking. |

Prints `Stopped`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `stopped` | `string` | The id of the chat whose turn was stopped. |

Daemon methods: `chat.get`, `chat.start`, `chat.stop`.

### hmz chat set

Sets either or both. A permission holds from the chat's next turn; a resting chat is carried on first, with nothing said.

```text
hmz chat set CHAT [options]
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |
| `--permission {read-only,workspace-write,danger-full-access}` | What the agent may change, from the next turn. One of `read-only`, `workspace-write`, `danger-full-access`. |
| `--prefer {native,flow}` | Which one a `$name` line runs when both a skill of the harness (`native`) and a flow (`flow`) have that name. One of `native`, `flow`. |

| Example | What it does |
| --- | --- |
| `hmz chat set 20261117T100000.000Z-ab12cd --permission read-only` | Let a chat's agent only read from its next turn. |
| `hmz chat set "$id" --prefer flow` | Have `$name` lines of a chat run flows rather than the harness's skills. |

Prints the chat's permission and preference as they then are, one per line.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `chat` | `string` | The chat's id. |
| `permission` | `string\|null` | What the agent may change, or null for an Ai-chan chat. |
| `prefer` | `string` | What a `$name` both a skill and a flow answer to runs: `native` or `flow`. |
| `prefer_from` | `string` | `chat` where the chat sets it itself, `settings` where it follows the settings. |

Daemon methods: `chat.get`, `chat.start`, `chat.set`, `chat.commands`.

### hmz chat move

Move a chat to another environment between turns.

```text
hmz chat move CHAT ENV
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |
| `ENV` | The environment to move to, written BACKEND[@RUNTIME][/DIRECTORY]. |

| Example | What it does |
| --- | --- |
| `hmz chat move 20261117T100000.000Z-ab12cd ssh@gpu-box/srv/repo` | Move a chat to a folder on a runtime reached over ssh. |
| `hmz chat move "$id" local/~/shop` | Move a chat back to a folder of this machine. |

Prints the environment the chat works in from then on.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `chat` | `string` | The chat's id. |
| `env` | `string` | The environment the chat works in from then on. |

Daemon methods: `chat.get`, `chat.start`, `chat.move`.

### hmz chat agent

Carry a chat on with another model or effort.

```text
hmz chat agent CHAT AGENT
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |
| `AGENT` | The agent to go on with, written HARNESS[@ACCOUNT]/MODEL[:EFFORT], of the chat's own harness and account. |

| Example | What it does |
| --- | --- |
| `hmz chat agent 20261117T100000.000Z-ab12cd claude/claude-opus-5:high` | Carry a chat on with another model at high effort. |

The chat's line, as `hmz chat list` prints it.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `string` | The chat's id. |
| `title` | `string` | The chat's title. |
| `state` | `string` | `turn` while the agent works, `asking` while it waits for an answer, `going` while a host holds the chat between turns, `failed`, or `resting`. |
| `agent` | `string` | The chat's agent, written HARNESS[@ACCOUNT]/MODEL[:EFFORT]. |
| `model` | `string` | The model the agent runs. |
| `permission` | `string` | What the agent may change: `read-only`, `workspace-write` or `danger-full-access`. |
| `env` | `string` | The environment the agent works in, written BACKEND[@RUNTIME][/DIRECTORY]. |
| `workdir` | `string` | The directory the agent works in. |
| `workspace` | `string` | The folder the chat is of, as an absolute path. |
| `folderless` | `boolean` | Whether the chat is of no folder. |
| `slot` | `string` | The slot of the host that holds the chat, empty when none does. |
| `asking` | `list` | The questions the agent asked and waits on. |
| `began` | `string` | When the chat started, ISO 8601. |
| `updated` | `string` | When the chat was last written, ISO 8601. |
| `archived` | `boolean` | Whether the chat is archived. |
| `spent` | `object` | What the chat has used: tokens, and cost where priced. |

Daemon methods: `chat.agent`.

### hmz chat commands

List what a chat's lines can start with.

```text
hmz chat commands CHAT
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz chat commands 20261117T100000.000Z-ab12cd` | List what a chat's lines can start with. |
| `hmz chat commands "$id" --json \| jq -r '.entries[] \| select(.source == "flow") \| .name'` | Print the names of the flows a chat can start, with jq. |

Prints one line per entry: sigil and name, where it comes from, and what it does.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `entries` | `list` | What a line can start with. |
| `entries[].sigil` | `string` | `/`, `$`, `!` or `@`. |
| `entries[].name` | `string` | The name after the sigil. |
| `entries[].about` | `string` | What it does. |
| `entries[].how` | `string` | How hmz serves an entry of the harness: `pass`, `call`, `emulate` or `refuse`; empty for the others. |
| `entries[].source` | `string` | `native` for the harness's own, `hmz` for a command of hmz, `flow` for a flow. |
| `prefer` | `string` | What a `$name` both a skill and a flow answer to runs: `native` or `flow`. |
| `prefer_from` | `string` | `chat` where the chat sets it itself, `settings` where it follows the settings. |
| `permission` | `string\|null` | What the agent may change, or null for an Ai-chan chat. |
| `listed` | `boolean` | Whether the list is everything the harness lists, which it is once the chat has taken a turn. |

Daemon methods: `chat.get`, `chat.start`, `chat.commands`.

### hmz chat backup

Back a chat up to its backup targets, or those named.

```text
hmz chat backup CHAT [options]
```

| Argument or option | What it is |
| --- | --- |
| `CHAT` | The chat's id, as `hmz chat list` prints it. |
| `--to TARGET` | A backup target to back up to; when not given, the targets the chat was started with. May be given more than once. |

| Example | What it does |
| --- | --- |
| `hmz chat backup 20261117T100000.000Z-ab12cd` | Back a chat up to its targets. |
| `hmz chat backup "$id" --to lab` | Back a chat up to the target named `lab`. |

Prints the targets the backup was queued for, a line each; it does not wait for the backup.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `queued` | `list` | The targets the backup was queued for. |

Daemon methods: `chat.backup`.

### hmz chat harness list

List the harness sessions of this folder, last written first.

```text
hmz chat harness list [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The folder the harness sessions worked in; when not given, the current folder. |
| `--limit N` | How many to list at most, up to 200. |
| `--offset N` | How many of the newest to skip. |

| Example | What it does |
| --- | --- |
| `hmz chat harness list` | List the harness sessions of this folder. |
| `hmz chat harness list --json \| jq -r '.sessions[] \| select(.continuable) \| .id'` | Print the ids of the harness sessions that can be continued, with jq. |

Prints one line per harness session: harness, id, when it was last written, and title.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `sessions` | `list` | The harness sessions, last written first. |
| `total` | `integer` | How many there are in all, beyond this page too. |
| `offset` | `integer` | How many were skipped. |
| `limit` | `integer` | How many were listed at most. |
| `sessions[].id` | `string` | The id the harness gave the session. |
| `sessions[].harness` | `string` | The harness that ran it. |
| `sessions[].title` | `string` | The first line the person said in it. |
| `sessions[].workspace` | `string` | The folder it worked in. |
| `sessions[].model` | `string` | The model it last ran on, empty where its log gives none. |
| `sessions[].began` | `string` | When it started, in ISO 8601. |
| `sessions[].updated` | `string` | When its log was last written, in ISO 8601. |
| `sessions[].continuable` | `boolean` | Whether `hmz chat harness adopt` can continue it in a chat. |

Daemon methods: `chat.harness.list`.

### hmz chat harness show

Print one harness session, and what was said in it.

```text
hmz chat harness show HARNESS SESSION [options]
```

| Argument or option | What it is |
| --- | --- |
| `HARNESS` | The harness that ran the session, as `hmz chat harness list` prints it. |
| `SESSION` | The harness session's id, as `hmz chat harness list` prints it. |
| `-w, --workspace DIR` | The folder the harness sessions worked in; when not given, the current folder. |
| `--trace` | Also print what was said and done in the harness session, read from its logs. |

| Example | What it does |
| --- | --- |
| `hmz chat harness show claude 7c1d0f5e` | Print one harness session of Claude Code. |
| `hmz chat harness show claude 7c1d0f5e --trace --json \| jq .trace` | Read what was said in a harness session as JSON. |

One line per field, name then value; with `--trace`, what each harness session said and did after them.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `string` | The id the harness gave the session. |
| `harness` | `string` | The harness that ran it. |
| `title` | `string` | The first line the person said in it. |
| `workspace` | `string` | The folder it worked in. |
| `model` | `string` | The model it last ran on, empty where its log gives none. |
| `began` | `string` | When it started, in ISO 8601. |
| `updated` | `string` | When its log was last written, in ISO 8601. |
| `continuable` | `boolean` | Whether `hmz chat harness adopt` can continue it in a chat. |
| `trace` | `list` | With `--trace`, what was said and done in the harness session. |

Daemon methods: `chat.harness.get`.

### hmz chat harness adopt

Copies the harness session into a new chat of the folder and prints the chat's id; the session stays as it is. Send a message with `hmz chat say`.

```text
hmz chat harness adopt HARNESS SESSION [options]
```

| Argument or option | What it is |
| --- | --- |
| `HARNESS` | The harness that ran the session, as `hmz chat harness list` prints it. |
| `SESSION` | The harness session's id, as `hmz chat harness list` prints it. |
| `-w, --workspace DIR` | The folder the harness sessions worked in; when not given, the current folder. |
| `-a, --agent AGENT` | An agent of the same harness to continue with, as HARNESS[@ACCOUNT]/MODEL[:EFFORT]; by default, the session's own model. |

| Example | What it does |
| --- | --- |
| `hmz chat harness adopt claude 7c1d0f5e` | Continue a harness session of Claude Code in a new chat. |
| `hmz chat say $(hmz chat harness adopt codex 019a2b -a codex/gpt-5.2:high) "Carry on"` | Continue a harness session of Codex with another model, and send the new chat a message. |

Prints the new chat's id.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `chat` | `string` | The new chat's id. |

Daemon methods: `chat.harness.adopt`.

## hmz daemons

The daemons of other machines this machine can reach, each kept under a name with its routes. Give a name to `--daemon` on any command to ask that daemon.

```text
hmz daemons list
hmz daemons add NAME [ROUTE...] [options]
hmz daemons remove NAME
hmz daemons show NAME [options]
hmz daemons pair NAME CODE [options]
```

### hmz daemons list

List this machine's daemon and the daemons of other machines.

```text
hmz daemons list
```

| Example | What it does |
| --- | --- |
| `hmz daemons list` | List the daemons. |
| `hmz daemons list --json \| jq -r '.daemons[].name'` | Print the names `--daemon` takes. |

One line per daemon: its name, its daemon id where one is pinned, and its routes.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `daemons` | `list` | This machine's daemon as `local` first, then every daemon kept, in order. |
| `daemons[].name` | `string` | The name the daemon is kept under. |
| `daemons[].id` | `string` | The daemon id pinned for it, or empty until it is first reached over a trusted route. |
| `daemons[].routes` | `list` | Its routes, in the order they are tried. |

### hmz daemons add

Keeps a daemon under a name with its routes. A first route that is not ssh needs `--id`; a pairing code carries both, see `hmz daemons pair`.

```text
hmz daemons add NAME [ROUTE...] [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name the daemon is kept under: letters, digits, ., _ and -; it is what `--daemon` takes. |
| `ROUTE` | A route, tried in the order given: `stdio:ssh://[user@]host[:port]`, `tcp://host:port`, `ws://…`, `wss://…`, `relay:wss://…`, `webrtc:wss://…` or `easytier:&lt;entry>`. |
| `--id ID` | The daemon id to pin, 52 characters, as the other machine's daemon reports it; needed unless the first route is ssh. |
| `--replace` | Write over the daemon already kept under this name. |

| Example | What it does |
| --- | --- |
| `hmz daemons add gpu stdio:ssh://gpu-box` | Add the host `gpu-box` of your SSH config as the daemon `gpu`. |
| `hmz daemons add gpu stdio:ssh://me@10.0.0.7:2222 tcp://10.0.0.7:41817` | Add a daemon reached over ssh first, then over a TCP port. |
| `hmz daemons add lab easytier:lab --id abcdefghijklmnopqrstuvwxyz234567abcdefghijklmnopqrst` | Add a daemon reached over the EasyTier entry `lab`, pinning its daemon id. |
| `hmz daemons add far relay:wss://relay.example/hmz ws://far.example:8443 --id abcdefghijklmnopqrstuvwxyz234567abcdefghijklmnopqrst` | Add a daemon reached through a relay, then over a WebSocket, pinning its daemon id. |

The one word `Added`, or `Saved` with `--replace`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | The name the daemon is kept under. |
| `id` | `string` | The daemon id pinned for it, or empty until it is first reached over a trusted route. |
| `routes` | `list` | Its routes, in the order they are tried. |

### hmz daemons remove

Forget how to reach one daemon.

```text
hmz daemons remove NAME
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name the daemon is kept under: letters, digits, ., _ and -; it is what `--daemon` takes. |

| Example | What it does |
| --- | --- |
| `hmz daemons remove gpu` | Remove the daemon `gpu` from the list; nothing on its machine changes. |

The one word `Removed`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | The name of the daemon that was removed. |

### hmz daemons show

Print one daemon's id and routes, and with `--connect` reach it.

```text
hmz daemons show NAME [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name the daemon is kept under: letters, digits, ., _ and -; it is what `--daemon` takes. |
| `--connect` | Reach the daemon over its routes and print its state and hmz version; exits with status 3 where it cannot be reached. |

| Example | What it does |
| --- | --- |
| `hmz daemons show gpu` | Print the routes kept for the daemon `gpu`. |
| `hmz daemons show gpu --connect` | Check that the daemon `gpu` can be reached, and print its version. |

One line per field: the field's name, then its value.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | The name the daemon is kept under. |
| `id` | `string` | The daemon id pinned for it, or empty until it is first reached over a trusted route. |
| `routes` | `list` | Its routes, in the order they are tried. |
| `state` | `string\|null` | `up` once reached with `--connect`; null where it was not asked. |
| `version` | `string\|null` | The hmz version the daemon runs, where it was reached with `--connect`; null otherwise. |

### hmz daemons pair

Claims a pairing code `hmz devices pair` printed on the other machine: pairs this machine as a device of that daemon, and keeps the daemon under NAME.

```text
hmz daemons pair NAME CODE [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name the daemon is kept under: letters, digits, ., _ and -; it is what `--daemon` takes. |
| `CODE` | The pairing code, which starts with `hmz-pair:`; or `-` to read it from standard input. |
| `--device NAME` | The name this machine is paired as on that daemon; this machine's host name where not given. |
| `--replace` | Write over the daemon already kept under this name. |

| Example | What it does |
| --- | --- |
| `hmz daemons pair gpu hmz-pair:eyJ2IjoxLC…` | Claim a pairing code and keep its daemon as `gpu`. |
| `ssh gpu-box hmz devices pair \| hmz daemons pair gpu - --device laptop` | Make a pairing code on `gpu-box` over ssh and claim it here, pairing this machine as `laptop`. |

The one word `Added`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | The name the daemon is kept under. |
| `id` | `string` | The daemon id pinned for it, or empty until it is first reached over a trusted route. |
| `routes` | `list` | Its routes, in the order they are tried. |

Daemon methods: `pair.claim`.

## hmz devices

A paired device is a phone, browser or other machine let in to this daemon by claiming a pairing code. These commands list them and revoke one.

```text
hmz devices list
hmz devices revoke NAME
hmz devices pair [options]
```

### hmz devices list

List the paired devices.

```text
hmz devices list
```

| Example | What it does |
| --- | --- |
| `hmz devices list` | List the paired devices. |
| `hmz devices list --json \| jq -r '.devices[].name'` | List the paired devices as JSON and print their names with jq. |

One line per device: name, fingerprint, when it was paired, when it was last seen.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `devices` | `list` | The paired devices. |
| `devices[].name` | `string` | The name the device was paired as. |
| `devices[].fingerprint` | `string` | Fingerprint of the device's certificate. |
| `devices[].added` | `string` | When it was paired, ISO 8601. |
| `devices[].seen` | `string\|null` | When it last opened a session, ISO 8601, or null if never. |

Daemon methods: `devices.list`.

### hmz devices revoke

Revoke one paired device and close its open sessions.

```text
hmz devices revoke NAME
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name the device was paired as, as `hmz devices list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz devices revoke phone` | Revoke the device paired as `phone`. |

How many sessions were closed.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `dropped` | `integer` | How many of the device's open sessions were closed. |

Daemon methods: `devices.revoke`.

### hmz devices pair

Prints a one-time pairing code. Enter it on the device (in Settings > Daemons, or the desktop app) before it expires.

```text
hmz devices pair [options]
```

| Argument or option | What it is |
| --- | --- |
| `--route ROUTE` | A route the code carries to reach this daemon, or those it listens on. May be given more than once. |
| `--seconds N` | How long the code can be claimed for, in seconds. |

| Example | What it does |
| --- | --- |
| `hmz devices pair --seconds 600` | Make a pairing code that can be claimed for ten minutes. |

The code alone on standard output, and when it expires on standard error.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `code` | `string` | The pairing code. |
| `expires` | `integer` | When the code stops being claimable, seconds since the Unix epoch. |

Daemon methods: `pair.create`.

## hmz easytier

An EasyTier entry names one private network: a secret and the shared nodes machines meet through. Machines sharing a secret and a node reach each other without open ports.

```text
hmz easytier list
hmz easytier set NAME [options]
hmz easytier remove NAME
hmz easytier nodes
```

### hmz easytier list

List the EasyTier entries, without their secrets.

```text
hmz easytier list
```

| Example | What it does |
| --- | --- |
| `hmz easytier list` | List the EasyTier entries. |
| `hmz easytier list --json \| jq -r '.networks[].name'` | Print the names of the EasyTier entries. |

One line per entry: its name, `true` or `false` for whether a secret is written, and its nodes.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `networks` | `list` | Every EasyTier entry after this command. |
| `networks[].name` | `string` | The name of the EasyTier entry. |
| `networks[].nodes` | `list` | The shared nodes the network meets through, each a URL such as tcp://host:port. |
| `networks[].keyed` | `boolean` | Whether a secret is written for the entry; the secret itself is never printed. |

Daemon methods: `easytier.list`.

### hmz easytier set

Writes an EasyTier entry. A new entry needs a node and a secret of at least 16 bytes; written again, it keeps any secret and nodes not given here.

```text
hmz easytier set NAME [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name of the EasyTier entry, which a route or a listener names as `easytier:&lt;name>`: letters, digits, ., _ and -. |
| `--node URL` | A shared node the network meets through, as `tcp://host:port` (or udp, ws, wss, quic or wg); `hmz easytier nodes` lists ones to use. May be given more than once. |
| `--secret-stdin` | Read the secret from standard input; a secret is never taken from the command line and never printed. |
| `--secret-env VAR` | Read the secret from the environment variable VAR. |

| Example | What it does |
| --- | --- |
| `openssl rand -hex 24 \| hmz easytier set lab --node tcp://public.easytier.top:11010 --secret-stdin` | Add the entry `lab` with a new random secret read from standard input. |
| `hmz easytier set lab --node tcp://public.easytier.top:11010 --secret-env LAB_SECRET` | Add the entry `lab` with the secret in the environment variable `LAB_SECRET`. |
| `hmz easytier set lab --node tcp://a.example:11010 --node udp://b.example:11010` | Change the nodes of `lab`, keeping its secret. |

The one word `Saved`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `networks` | `list` | Every EasyTier entry after this command. |
| `networks[].name` | `string` | The name of the EasyTier entry. |
| `networks[].nodes` | `list` | The shared nodes the network meets through, each a URL such as tcp://host:port. |
| `networks[].keyed` | `boolean` | Whether a secret is written for the entry; the secret itself is never printed. |

Daemon methods: `easytier.list`, `easytier.set`.

### hmz easytier remove

Remove an EasyTier entry the daemon does not listen on.

```text
hmz easytier remove NAME
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name of the EasyTier entry, which a route or a listener names as `easytier:&lt;name>`: letters, digits, ., _ and -. |

| Example | What it does |
| --- | --- |
| `hmz easytier remove lab` | Remove the EasyTier entry `lab`. |

The one word `Removed`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `networks` | `list` | Every EasyTier entry after this command. |
| `networks[].name` | `string` | The name of the EasyTier entry. |
| `networks[].nodes` | `list` | The shared nodes the network meets through, each a URL such as tcp://host:port. |
| `networks[].keyed` | `boolean` | Whether a secret is written for the entry; the secret itself is never printed. |

Daemon methods: `easytier.remove`.

### hmz easytier nodes

List the shared EasyTier nodes to choose from.

```text
hmz easytier nodes
```

| Example | What it does |
| --- | --- |
| `hmz easytier nodes` | List the shared nodes and how each has stood. |
| `hmz easytier nodes --json \| jq -r '.nodes[] \| select(.up) \| .url'` | Print the URLs of the shared nodes that are up. |

One line per node: its URL, whether it is up, its uptime over 24 hours, its EasyTier version, and its name.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `nodes` | `list` | The shared EasyTier nodes on offer. |
| `nodes[].url` | `string` | The URL to give `--node`. |
| `nodes[].name` | `string` | What the node's monitor calls it: where it is and who runs it. |
| `nodes[].version` | `string` | The EasyTier version it runs, or empty where unknown. |
| `nodes[].up` | `boolean\|null` | Whether it answered last, or null where unknown. |
| `nodes[].uptime` | `number\|null` | The share of the last 24 hours it was up, from 0 to 1, or null where unknown. |

Daemon methods: `easytier.nodes`.

## hmz env

An environment is where the agents of a chat or an epic work, a folder on this machine, in a container or on another host. These commands do there what the Environments view of the web page does: browse, read, write and search files, stage and commit changes, rewind to a snapshot, run a command and open a terminal. The host is named with `--workspace` and `--slot`, or with `--chat`; an environment is open only while its chat or epic is going.

```text
hmz env list [options]
hmz env ls [PATH] [options]
hmz env stat PATH [options]
hmz env cat PATH [options]
hmz env find [NAME] [options]
hmz env search QUERY [options]
hmz env write PATH [options]
hmz env mkdir PATH [options]
hmz env mv PATH TO [options]
hmz env rm PATH [options]
hmz env exec [ARGV...] [options]
hmz env git status [options]
hmz env git diff [PATHS...] [options]
hmz env git log [options]
hmz env git stage [PATHS...] [options]
hmz env git unstage [PATHS...] [options]
hmz env git discard [PATHS...] [options]
hmz env git commit --message TEXT [options]
hmz env git snapshots [options]
hmz env git rewind REF [options]
hmz env term open [options]
hmz env term list [options]
hmz env term close TERM [options]
```

### hmz env list

Lists the environments of the chat or epic going on a host, or of its last one. An environment derived from another, such as a worktree or a clone, is listed after the one it came from. The id, chain or role printed here is what `--env` takes in the other commands.

```text
hmz env list [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |

| Example | What it does |
| --- | --- |
| `hmz env list` | List the environments of the epic going in the current folder. |
| `hmz env list -w ~/project --json \| jq -r '.envs[].id'` | Print the ids of the environments of another folder's epic. |
| `hmz env list --chat 20261124-fix-login` | List the environments of a chat. |

One line per environment: id, chain, backend, working directory, what it serves, and `closed` or `unavailable` where it is.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The folder of the host that was asked, as the daemon names it. |
| `slot` | `string` | The slot of the host that was asked, an empty string for the folder's own host. |
| `envs` | `list` | The environments, each root environment in the order of its roles and each derived one after the one it came from. |
| `envs[].id` | `string` | The id the host knows the environment by, which `--env` takes. |
| `envs[].role` | `string` | The environment role it fills in the flow. |
| `envs[].chain` | `string` | Its label: its role followed by each derivation that made it. |
| `envs[].parent` | `string\|null` | The id of the environment it was derived from, or null for a root environment. |
| `envs[].run` | `integer` | The number of the epic it belongs to. |
| `envs[].backend` | `string` | Its kind, such as `local`, `docker` or `ssh`. |
| `envs[].provider` | `string` | The runtime it is on. |
| `envs[].workdir` | `string` | Its working directory, on its own machine. |
| `envs[].available` | `boolean` | Whether it can be reached at all. |
| `envs[].open` | `boolean` | Whether it is open; a closed one is listed and refuses every command. |
| `envs[].caps` | `list` | What it serves, of `files`, `shell`, `bash`, `git`, `git_worktree`, `rewind`, `scratch` and `temp_clone`; a command needs `files`, `git` or `shell`. |
| `envs[].declared` | `list` | What its role declares in the flow, of the same names as `caps`. |
| `envs[].facts` | `object` | `cpu`, `memory`, `gpu_count` and `gpu_memory` as found on its machine, each null where not found. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `epic.detach`.

### hmz env ls

List a directory of an environment.

```text
hmz env ls [PATH] [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATH` | The directory to list, relative to the environment's working directory, or absolute. Default `.`. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env ls` | List the working directory of the first open environment. |
| `hmz env ls src --env coder --json` | List the directory `src` of the environment `coder` as JSON. |

One line per entry, directories first: its kind (`d` directory, `-` file, `l` link, `?` other), size in bytes, when it was last changed, and name.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `path` | `string` | The path as given on the command line. |
| `entries` | `list` | The entries of the directory, directories first and then by name. |
| `entries[].name` | `string` | The entry's file name. |
| `entries[].kind` | `string` | What the entry is: `file`, `dir`, `link` or `other`. |
| `entries[].size` | `integer` | Its size in bytes. |
| `entries[].mtime` | `number` | When it was last changed, in seconds since the Unix epoch. |
| `entries[].target` | `string\|null` | Where a link points, or null if not a link. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.list`, `epic.detach`.

### hmz env stat

Show what one path of an environment is.

```text
hmz env stat PATH [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATH` | A path in the environment, relative to its working directory, or absolute. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env stat src/app.py --json` | Print the kind, size and time of one file as JSON. |

One line, as `hmz env ls` prints an entry, with the absolute path in place of the name.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `path` | `string` | The path as an absolute path on the environment's machine. |
| `name` | `string` | The entry's file name. |
| `kind` | `string` | What the entry is: `file`, `dir`, `link` or `other`. |
| `size` | `integer` | Its size in bytes. |
| `mtime` | `number` | When it was last changed, in seconds since the Unix epoch. |
| `target` | `string\|null` | Where a link points, or null if not a link. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.stat`, `epic.detach`.

### hmz env cat

Prints the whole file, however long, unless `--offset` or `--length` asks for a piece of it. With `--json` it also gives the file's `etag`, which `hmz env write --if-match` takes so a write does not overwrite a change made since the file was read.

```text
hmz env cat PATH [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATH` | A path in the environment, relative to its working directory, or absolute. |
| `--offset N` | The byte to start reading at. |
| `--length N` | How many bytes to read, at most 1048576. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env cat README.md` | Print a file. |
| `hmz env cat README.md --json \| jq -r .etag` | Print the etag of a file, to write it back with `--if-match`. |
| `hmz env cat build.log --offset 0 --length 4096` | Print the first 4096 bytes of a file. |

The bytes of the file, exactly as they are.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `path` | `string` | The path as given on the command line. |
| `text` | `string` | What was read, as UTF-8 text; any byte that is not UTF-8 becomes U+FFFD. |
| `size` | `integer` | The size of the whole file in bytes. |
| `mtime` | `number` | When the file was last changed, as seconds since the Unix epoch. |
| `etag` | `string` | The SHA-256 of the whole file, which `hmz env write --if-match` takes. |
| `eof` | `boolean` | Whether what was read reaches the end of the file. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.read`, `epic.detach`.

### hmz env find

Lists the files under the environment's working directory, relative to it. In a git repository these are the files git tracks or does not ignore; elsewhere every file outside `.git` and `node_modules`.

```text
hmz env find [NAME] [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | Print only the paths that contain this text, whatever its case; when not given, every path. |
| `--limit N` | The most files the environment lists; 20000 when not given. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env find` | List every file of the environment. |
| `hmz env find test_ --json` | List the files whose path contains `test_` as JSON. |

One path per line, relative to the working directory.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `paths` | `list` | The paths found, relative to the working directory. |
| `truncated` | `boolean` | Whether the environment has more files than `--limit` let it list. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.find`, `epic.detach`.

### hmz env search

Search the files of an environment for text.

```text
hmz env search QUERY [options]
```

| Argument or option | What it is |
| --- | --- |
| `QUERY` | The text to look for, or with `--regex` a regular expression. |
| `--regex` | Read QUERY as a regular expression instead of literal text. |
| `--case` | Match case; without it `a` also finds `A`. |
| `--glob GLOB` | Search only the files whose path matches this glob, such as `*.py`. |
| `--limit N` | The most matches to print; 2000 when not given. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env search TODO` | Find every line that contains `TODO`. |
| `hmz env search 'def \w+_test' --regex --glob '*.py' --json` | Search the Python files with a regular expression and print the matches as JSON. |

One line per match, as `path:line:column:text`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `matches` | `list` | The matches found. |
| `matches[].path` | `string` | The file, relative to the working directory. |
| `matches[].line` | `integer` | The line number, counting from 1. |
| `matches[].column` | `integer` | The column the match starts at, counting from 1. |
| `matches[].text` | `string` | The line that matched. |
| `truncated` | `boolean` | Whether there were more matches than `--limit`. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.search`, `epic.detach`.

### hmz env write

Makes the file hold what is read from standard input, or from the local file `--from` names. With `--if-match` it writes only if the file is still as it was read, and is refused, leaving the file alone, if it changed since.

```text
hmz env write PATH [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATH` | A path in the environment, relative to its working directory, or absolute. |
| `--from FILE` | A file of this machine to read what is written from; when not given, standard input. |
| `--if-match ETAG` | Write only if the file's etag is still this one, as `hmz env cat --json` printed it; an empty value, `--if-match ''`, writes only if there is no file yet. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `echo hello \| hmz env write notes/hello.txt` | Write standard input to a file, making it or replacing what it holds. |
| `hmz env write src/app.py --from app.py` | Write a local file into the environment. |
| `hmz env write README.md --from README.md --if-match "$ETAG"` | Write only if the file has not changed since its etag was read. |
| `hmz env write new.txt --from new.txt --if-match ''` | Write a new file, and refuse if one is already there. |

`Saved.`

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `path` | `string` | The path as given on the command line. |
| `etag` | `string` | The file's new etag, for the next `--if-match`. |
| `size` | `integer` | How many bytes the file now holds. |
| `mtime` | `number` | When it was written, as seconds since the Unix epoch. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.write`, `epic.detach`.

### hmz env mkdir

Make a directory in an environment, with the directories above it.

```text
hmz env mkdir PATH [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATH` | A path in the environment, relative to its working directory, or absolute. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env mkdir docs/guides` | Make the directory `docs/guides`, and `docs` if it is missing. |

Prints `Created`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `path` | `string` | The path as given on the command line. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.mkdir`, `epic.detach`.

### hmz env mv

Move or rename a path of an environment.

```text
hmz env mv PATH TO [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATH` | A path in the environment, relative to its working directory, or absolute. |
| `TO` | The path to move it to. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env mv notes.txt docs/notes.md` | Move a file and rename it. |

Prints `Renamed`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `path` | `string` | The path as given on the command line. |
| `to` | `string` | The path it was moved to, as it was given. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.rename`, `epic.detach`.

### hmz env rm

Deletes the path and everything under it; this cannot be undone. It asks first; `--yes` skips the question, and is needed where nobody can be asked: with `--json`, or when standard input is not a terminal.

```text
hmz env rm PATH [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATH` | A path in the environment, relative to its working directory, or absolute. |
| `-y, --yes` | Do it without asking first. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env rm build` | Delete the folder `build` after asking. |
| `hmz env rm build --yes --json` | Delete it without asking, and answer as JSON. |

Prints the question on standard error, and then `Deleted`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `path` | `string` | The path as given on the command line. |

| Status | Meaning |
| --- | --- |
| `1` | The daemon refused it, or you did not answer yes. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.remove`, `epic.detach`.

### hmz env exec

Runs the command in the working directory of an environment of the epic or chat that is going, as its flow would, waits for it to end, and prints its output. Put `--` before the command so that its own options are not read as options of hmz. For an interactive shell use `hmz env term open`.

```text
hmz env exec [ARGV...] [options]
```

| Argument or option | What it is |
| --- | --- |
| `ARGV` | The command and its arguments, after `--`. |
| `--seconds N` | How long the command may run before it is stopped, from 1 to 3600 seconds; 120 when not given. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ROLE` | The role of the environment to run in, as `hmz env list` prints it; when not given, the first role of the flow. |

| Example | What it does |
| --- | --- |
| `hmz env exec -- git log --oneline -5` | Run a command in the environment of the current folder's epic. |
| `hmz env exec --env coder --seconds 600 --json -- make test` | Run the tests in the environment `coder` for up to ten minutes and answer as JSON. |

What the command wrote to standard output, on standard output, and what it wrote to standard error, on standard error; the last 1048576 bytes of each.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `code` | `integer\|null` | The command's exit status, or null if it was stopped at its time limit. |
| `stdout` | `string` | The last 1048576 bytes the command wrote to standard output, as text. |
| `stderr` | `string` | The last 1048576 bytes the command wrote to standard error, as text. |

| Status | Meaning |
| --- | --- |
| `5` | The command ran and exited with a status other than 0, or was stopped at its time limit. |

Daemon methods: `chat.get`, `hosts.env.list`, `hosts.env.exec`.

### hmz env git status

Show the branch and the changed files of an environment.

```text
hmz env git status [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env git status` | Show the branch and what has changed. |
| `hmz env git status --json \| jq -r '.files[].path'` | Print the path of every changed file. |

Prints the branch, then how far it is ahead of and behind its upstream, then one line per changed file: two characters for the index and the working tree, as `git status --short` writes them with `.` for unchanged, and the path.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `root` | `string` | The top directory of the repository. |
| `branch` | `string\|null` | The branch checked out, or null when none is. |
| `head` | `string\|null` | The commit checked out, or null before the first commit. |
| `upstream` | `string\|null` | The branch's upstream, or null when it has none. |
| `ahead` | `integer` | How many commits the branch is ahead of its upstream. |
| `behind` | `integer` | How many commits the branch is behind its upstream. |
| `files` | `list` | The changed files. |
| `files[].path` | `string` | The file, relative to the top of the repository. |
| `files[].orig` | `string` | The path it was renamed or copied from; present only where it was. |
| `files[].index` | `string` | One character for its change in the index: `M` modified, `A` added, `D` deleted, `R` renamed, `.` unchanged, `?` untracked. |
| `files[].worktree` | `string` | One character for its change in the working tree, read as `index` is. |
| `files[].state` | `string` | `conflict` for an unmerged file, `untracked` for an untracked one, `changed` otherwise. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.git.status`, `epic.detach`.

### hmz env git diff

Prints a unified diff of what is not yet staged, the working tree against the index. With `--staged` it prints what is staged, the index against the commit checked out. Without paths it covers every changed file.

```text
hmz env git diff [PATHS...] [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATHS` | The files to show, relative to the top of the repository; when none is given, every changed file. |
| `--staged` | Show what is staged instead of what is not. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env git diff` | Show every change that is not staged. |
| `hmz env git diff src/app.py --staged` | Show what is staged of one file. |

Prints a unified diff, file after file; a binary file is named in one line instead.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `staged` | `boolean` | Whether this is the diff of what is staged. |
| `files` | `list` | One entry per file, in the order asked for. |
| `files[].path` | `string` | The file, relative to the top of the repository. |
| `files[].binary` | `boolean` | Whether git reads the file as binary, in which case there is no diff text. |
| `files[].diff` | `string` | The unified diff of the file, an empty string where nothing changed or the file is binary. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.git.status`, `env.git.diff`, `epic.detach`.

### hmz env git log

List the latest commits of an environment.

```text
hmz env git log [options]
```

| Argument or option | What it is |
| --- | --- |
| `--limit N` | The most commits to list; 50 when not given. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env git log --limit 10` | List the ten latest commits. |
| `hmz env git log --json \| jq -r '.commits[0].hash'` | Print the hash of the commit checked out. |

One line per commit, newest first: short hash, date, author and subject.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `commits` | `list` | The commits, from the one checked out, newest first. |
| `commits[].hash` | `string` | The commit's full hash. |
| `commits[].parents` | `list` | The hashes of its parent commits. |
| `commits[].author` | `string` | Who wrote it. |
| `commits[].date` | `string` | When it was written, ISO 8601. |
| `commits[].subject` | `string` | The first line of its message. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.git.log`, `epic.detach`.

### hmz env git stage

Stage changes for the next commit.

```text
hmz env git stage [PATHS...] [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATHS` | The paths to act on, relative to the top of the repository as `hmz env git status` prints them. |
| `-A, --all` | Act on every changed path instead of naming paths. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env git stage src/app.py README.md` | Stage the changes to two files. |
| `hmz env git stage --all` | Stage every change, untracked files included. |

The paths acted on, one per line.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `paths` | `list` | The paths that were acted on. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.git.status`, `env.git.stage`, `epic.detach`.

### hmz env git unstage

Take staged changes out of the next commit, keeping them in the files.

```text
hmz env git unstage [PATHS...] [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATHS` | The paths to act on, relative to the top of the repository as `hmz env git status` prints them. |
| `-A, --all` | Act on every changed path instead of naming paths. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env git unstage README.md` | Unstage the changes to one file. |
| `hmz env git unstage --all` | Unstage everything that is staged. |

The paths acted on, one per line.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `paths` | `list` | The paths that were acted on. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.git.status`, `env.git.unstage`, `epic.detach`.

### hmz env git discard

Puts each file back as the index has it and deletes the untracked files named; this cannot be undone. It asks first; `--yes` skips the question, and is needed where nobody can be asked: with `--json`, or when standard input is not a terminal.

```text
hmz env git discard [PATHS...] [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATHS` | The paths to act on, relative to the top of the repository as `hmz env git status` prints them. |
| `-A, --all` | Act on every changed path instead of naming paths. |
| `-y, --yes` | Do it without asking first. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env git discard src/app.py` | Discard the changes to one file after asking. |
| `hmz env git discard --all --yes` | Discard every change that is not staged, without asking. |

The paths acted on, one per line.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `paths` | `list` | The paths that were acted on. |

| Status | Meaning |
| --- | --- |
| `1` | The daemon refused it, or you did not answer yes. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.git.status`, `env.git.discard`, `epic.detach`.

### hmz env git commit

Commit what is staged.

```text
hmz env git commit --message TEXT [options]
```

| Argument or option | What it is |
| --- | --- |
| `-m, --message TEXT` | The commit message. |
| `--amend` | Amend the commit checked out instead of adding a new one. |
| `-a, --all` | Stage every change first, untracked files included, then commit. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env git commit -m 'fix: handle empty input'` | Commit the staged changes. |
| `hmz env git commit --all -m 'docs: update'` | Stage every change and commit it. |
| `hmz env git commit --amend -m 'fix: handle no input'` | Replace the last commit with what is staged and a new message. |

The hash of the new commit.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `head` | `string` | The hash of the new commit. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.git.status`, `env.git.stage`, `env.git.commit`, `epic.detach`.

### hmz env git snapshots

A snapshot is the whole working tree as it was at one moment, kept by hmz as a git ref without touching the branch. The list is oldest first; `hmz env git rewind` takes one of these refs.

```text
hmz env git snapshots [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env git snapshots` | List the snapshot refs, oldest first. |
| `hmz env git snapshots --json \| jq -r '.snapshots[-1]'` | Print the latest snapshot ref. |

One snapshot ref per line.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `snapshots` | `list` | The snapshot refs, each a ref `hmz env git rewind` takes. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.git.snapshots`, `epic.detach`.

### hmz env git rewind

Resets the working tree to the snapshot; every change made since, committed or not, is lost. It is refused while an agent is working in the environment: stop it first. It asks first; `--yes` skips the question, and is needed with `--json` or when standard input is not a terminal.

```text
hmz env git rewind REF [options]
```

| Argument or option | What it is |
| --- | --- |
| `REF` | The snapshot to rewind to, a ref as `hmz env git snapshots` prints it. |
| `-y, --yes` | Do it without asking first. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env git rewind refs/hmz/snapshots/3` | Rewind to a snapshot after asking. |
| `hmz env git rewind refs/hmz/snapshots/3 --yes --json` | Rewind without asking, and answer as JSON. |

Prints the question on standard error, and then that the environment was rewound.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `ref` | `string` | The snapshot the environment was rewound to. |

| Status | Meaning |
| --- | --- |
| `1` | The daemon refused it, or you did not answer yes. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.git.rewind`, `epic.detach`.

### hmz env term open

Starts a shell in the environment's working directory, or comes back to a running one with `--term`, and attaches this terminal to it until the shell exits. Typing `~.` at the start of a line detaches and leaves it running. When standard input is not a terminal, it is typed into the shell and its output is printed until the shell exits. With `--json` it does not attach: it starts the terminal, prints its id and leaves it running.

```text
hmz env term open [options]
```

| Argument or option | What it is |
| --- | --- |
| `--term ID` | A running terminal to come back to, by its id as `hmz env term list` prints it; when not given, a new terminal is started. |
| `--cols N` | How many columns wide the terminal is; when not given, the width of this terminal. |
| `--rows N` | How many rows high the terminal is; when not given, the height of this terminal. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env term open` | Open a shell in the first open environment. |
| `hmz env term open --term t3` | Come back to a terminal that was left running. |
| `printf 'make test\nexit\n' \| hmz env term open` | Type two lines into a new shell and print its output until it exits. |
| `hmz env term open --json` | Start a terminal without attaching, and print its id. |

Prints what the terminal prints, as it prints it, and when it ends a line on standard error saying how.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `term` | `string` | The terminal's id, which `--term` and `hmz env term close` take. |
| `shell` | `list\|null` | The command the terminal runs, as a list of words, or null for the environment's login shell. |
| `replay` | `string` | What a terminal come back to with `--term` had already printed, as text; an empty string for a new one. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.term.open`, `env.term.input`, `env.term.resize`, `env.term.ack`, `epic.detach`.

### hmz env term list

List the terminals of an environment.

```text
hmz env term list [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env term list` | List the terminals of the first open environment. |
| `hmz env term list --json \| jq -r '.terms[] \| select(.alive) \| .term'` | Print the ids of the terminals still running. |

Prints one line per terminal: id, title, size as columns x rows, and `[exited]` once it has ended.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `terms` | `list` | The terminals that are running, or that somebody still has open. |
| `terms[].term` | `string` | The terminal's id. |
| `terms[].env` | `string` | The id of the environment it runs in. |
| `terms[].title` | `string` | Its name, as the page shows it. |
| `terms[].cols` | `integer` | How many columns wide it is. |
| `terms[].rows` | `integer` | How many rows high it is. |
| `terms[].alive` | `boolean` | Whether it is still running. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.term.list`, `epic.detach`.

### hmz env term close

Close a terminal, which ends the shell running in it.

```text
hmz env term close TERM [options]
```

| Argument or option | What it is |
| --- | --- |
| `TERM` | The terminal's id, as `hmz env term list` prints it. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | Which host of the folder to ask: `chat:&lt;id>` for a chat or `exec:&lt;id>` for an `hmz exec` epic; when not given, the folder's own host, where its epics run. |
| `--chat ID` | A chat's id as `hmz chat list` prints it; asks that chat's host instead of `--workspace` and `--slot`. |
| `--env ENV` | Which environment of the host to work in, by id, chain or role as `hmz env list` prints them; when not given, the first open environment. |

| Example | What it does |
| --- | --- |
| `hmz env term close t3` | Close one terminal and end its shell. |

Prints `Closed.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `term` | `string` | The id of the terminal that was closed. |

Daemon methods: `chat.get`, `hosts.status`, `epic.attach`, `env.term.close`, `epic.detach`.

## hmz epic

An epic is one run of a flow, held by the daemon on a host of its workspace. These commands start one, follow it, say lines to its agents, answer its questions and stop it. Each names the epic by `--workspace` and `--slot`; without them, the epic of the current directory's own host.

```text
hmz epic start FLOW [TASK] [options]
hmz epic attach [options]
hmz epic say TEXT [options]
hmz epic answer [TEXT] [options]
hmz epic face QUESTION [options]
hmz epic stop [options]
hmz epic quit [options]
hmz epic board [KEY] [VALUE] [options]
hmz epic claim [ROLE...] [options]
hmz epic release ROLE [options]
hmz epic afk [ROLE] [options]
hmz epic status [options]
```

### hmz epic start

Starts a flow as a new epic held by the daemon, and returns as soon as it has started; the epic runs on without this command. Roles, environments, params and the budget are written as `hmz exec` takes them. Questions the epic asks wait for `hmz epic answer`, unless `--away` is given. `--slot exec:` gives it a host of its own, beside any other epic of the workspace. `--follow` stays and writes the epic as `hmz epic attach` does, and exits with status 1 where the epic failed.

```text
hmz epic start FLOW [TASK] [options]
```

| Argument or option | What it is |
| --- | --- |
| `FLOW` | The flow to run: an installed flow's name, a path or a ref. |
| `TASK` | What the epic is to do. |
| `-a, --agents ROLE=SPEC` | What an agent role runs, as `&lt;harness>[@&lt;account>]/&lt;model>[:&lt;effort>]` or a nous name. May be given more than once. |
| `-e, --envs ROLE=SPEC` | Where an environment role is, as `&lt;backend>[@&lt;runtime>][/&lt;directory>]`. May be given more than once. |
| `-p, --params KEY=VALUE` | A param of the flow, or a limit of the budget as `budget.cost=5`, `budget.duration=30m` or `budget.output_tokens=200k`. May be given more than once. |
| `--resume` | Pick up the newest epic of this flow in the workspace. |
| `--resume-from EPIC` | Pick up this epic, named as `hmz runs list` prints it. |
| `--backup NAME` | A backup target the epic goes to, in place of the defaults. May be given more than once. |
| `--no-backup` | Back the epic up to no target. |
| `--profile-flow` | Sample the flow's own Python as it runs. |
| `--profile-environment` | Profile the programs the agents start. |
| `--remember` | Keep these roles, params and budget as the workspace's set-up of the flow. |
| `--scratch` | Run in a new folderless workspace instead of `--workspace`. |
| `--away` | Set every role away first, so that no question waits on a person. |
| `--follow` | Stay attached and write the epic until it ends. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic start goal 'fix the failing test' -a worker=claude/claude-haiku-4-5:low -p budget.cost=2` | Start the flow `goal` in the current directory and return. |
| `hmz epic start goal 'fix it' -p budget.cost=2 --slot exec: --away --follow --json` | Start it on a new slot beside other epics, with nobody to ask, and write its messages as JSON lines until it ends. |
| `hmz epic start goal --resume -p budget.duration=1h` | Pick up the newest epic of `goal` here with an hour more. |

One line naming the epic's number, workspace and slot. With `--follow`, that line and then what `hmz epic attach` prints.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `run` | `integer` | The epic's number on its host. |
| `slot` | `string` | The slot of the host that holds it, to pass as `--slot`. |
| `workspace` | `string` | The workspace it runs in, to pass as `--workspace`. |

| Status | Meaning |
| --- | --- |
| `130` | Interrupted while following; the epic goes on. |

Daemon methods: `epic.attach`, `epic.afk`, `epic.start`, `epic.detach`.

### hmz epic attach

Writes what the epic has done so far and then what it does, until it ends. Leaving with Ctrl-C does not stop the epic. Exits with status 1 where the epic failed. With `--json`, writes one JSON object a line, each a message of the host told apart by its `type`.

```text
hmz epic attach [options]
```

| Argument or option | What it is |
| --- | --- |
| `--no-replay` | Write only what happens from now on, not what the epic has done. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic attach` | Follow the epic of this directory. |
| `hmz epic attach --slot exec:1f2e --no-replay --json \| jq -c 'select(.type == "asked")'` | Print each question an epic on another slot asks from now on. |

What each agent does on standard error and each answer on standard output, as `hmz exec` prints them, with the questions asked and how the epic ended.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `type` | `string` | What the message is: `welcome`, `live`, `gone`, a history record such as `started`, `event`, `asked`, `answered` or `ended`, or a snapshot such as `run`, `pending` or `board`. |
| `seq` | `integer` | Of a history record, its place in the host's history. |
| `run` | `integer` | Of a history record, the epic's number. |
| `question` | `string` | Of `asked`, the id to answer it by with `hmz epic answer`. |
| `how` | `string` | Of `ended`: `done`, `stopped`, `budget`, `refused`, `failed` or `crashed`. |

| Status | Meaning |
| --- | --- |
| `130` | Interrupted while following; the epic goes on. |

Daemon methods: `hosts.status`, `epic.attach`, `epic.detach`.

### hmz epic say

Says a line to the epic that is going. Without `--to` it answers a question that is listening, or else goes to the first agent with a turn open; a line that cannot go in yet waits for the agent's next turn.

```text
hmz epic say TEXT [options]
```

| Argument or option | What it is |
| --- | --- |
| `TEXT` | The line to say. |
| `--to WHO` | Who the line is for: an agent's name, a session as `&lt;agent>/&lt;n>`, or `outworlder:&lt;role>`. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic say 'use the staging database'` | Say a line to the agent working now. |
| `hmz epic say --to NeiKos 'skip the migration'` | Say a line to the agent named NeiKos. |

One line once the daemon has taken it.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `text` | `string` | The line said. |
| `to` | `string` | Who it was said to, or empty. |

Daemon methods: `hosts.status`, `epic.attach`, `epic.say`, `epic.detach`.

### hmz epic answer

Answers a question the epic asked a person. Without `--question` it answers the only one waiting. The answer is text, the number of an offered option, or for a question with a schema a JSON value given as `--value`; one that does not fit is refused and the question stays.

```text
hmz epic answer [TEXT] [options]
```

| Argument or option | What it is |
| --- | --- |
| `TEXT` | The answer in words. |
| `-q, --question ID` | The id of the question, as `hmz epic status` prints it. |
| `--value JSON` | The answer as a JSON value of the question's schema, in place of the text. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic answer yes` | Answer the only question waiting. |
| `hmz epic answer -q q3 --value '{"verdict": "approve"}'` | Answer question q3 with a value of its schema. |

One line once the answer is taken.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `question` | `string` | The id of the question answered. |

Daemon methods: `hosts.status`, `epic.attach`, `epic.status`, `epic.answer`, `epic.detach`.

### hmz epic face

A flow can give a question a face, a page of HTML of its own that the web page shows in place of the plain question. This command prints that HTML for one waiting question, to save to a file and open in a browser. A question with no face is refused. Nothing in the HTML is run.

```text
hmz epic face QUESTION [options]
```

| Argument or option | What it is |
| --- | --- |
| `QUESTION` | The id of a waiting question, as `hmz epic status` prints it. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic face q3 > face.html` | Save the face of question q3 to a file to open in a browser. |
| `hmz epic face q3 --json \| jq -r .title` | Print the title of the face of question q3. |

Prints the HTML of the face, as the flow wrote it.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `question` | `string` | The id of the question the face belongs to. |
| `title` | `string` | The title of the face. |
| `html` | `string` | The HTML of the face, as the flow wrote it. |

Daemon methods: `hosts.status`, `epic.attach`, `epic.face`, `epic.detach`.

### hmz epic stop

Stops the epic: the turn under way is interrupted and the flow unwinds. `--force` also closes every session still in a turn, for an epic that does not stop.

```text
hmz epic stop [options]
```

| Argument or option | What it is |
| --- | --- |
| `--force` | Stop it and close every session that has a turn open. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic stop` | Stop the epic of this folder. |
| `hmz epic stop --force --slot exec:1f2e` | Force an epic on another slot that is still stopping. |

One line; with `--force`, how many sessions were closed.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `forced` | `boolean` | Whether `--force` was given. |
| `closed` | `integer` | How many sessions `--force` closed. |

Daemon methods: `hosts.status`, `epic.attach`, `epic.stop`, `epic.force`, `epic.detach`.

### hmz epic quit

Attaches to the host as a frontend and tells it to close. The host withdraws every waiting question, drops every line waiting to be said, stops every epic it runs, lets every frontend go and closes every side question; its process exits within 15 seconds. The epic's record is kept. `hmz hosts stop` does the same without attaching; `hmz epic stop` stops the epic and keeps the host.

```text
hmz epic quit [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic quit` | Close the host of the epic of this folder. |
| `hmz epic quit -w ~/work/app --slot exec:1f2e` | Close the host of one epic of another workspace. |

Prints one line once the host has taken the request.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace of the host closed. |
| `slot` | `string` | The slot of the host closed. |

Daemon methods: `hosts.status`, `epic.attach`, `epic.quit`, `epic.detach`.

### hmz epic board

The board is the lines an epic keeps for its agents and its person. With no argument this prints it; with a key, that line; with a key and a value it writes the line as the person; `--remove` removes it.

```text
hmz epic board [KEY] [VALUE] [options]
```

| Argument or option | What it is |
| --- | --- |
| `KEY` | The key of one line. |
| `VALUE` | What to write on that line. |
| `--remove` | Remove the line instead of writing it. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic board` | Print the board. |
| `hmz epic board deadline 'ship by Friday'` | Write the line `deadline`. |
| `hmz epic board deadline --remove` | Remove that line. |

One line per board line: key, value, whose it is and who wrote it. After writing or removing, one line saying so.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `items` | `list\|null` | When reading: the board's lines, or null where the epic has no board. |
| `items[].key` | `string` | The key of the line. |
| `items[].value` | `string` | What the line says. |
| `items[].about` | `string` | What the line is about. |
| `items[].whose` | `string` | Whose line it is: the person's or the flow's. |
| `items[].by` | `string` | Who last wrote it. |
| `items[].at` | `number` | When it was last written, seconds since the Unix epoch. |
| `key` | `string` | When writing: the key of the line. |
| `value` | `string` | When writing: what was written, empty where removed. |

Daemon methods: `hosts.status`, `epic.attach`, `epic.board`, `epic.detach`.

### hmz epic claim

Claims one or more roles for as long as this command runs, so that no other frontend answers for them, and follows the epic as `hmz epic attach` does. Each line typed on standard input answers the oldest question waiting on those roles. The roles are released when the command ends.

```text
hmz epic claim [ROLE...] [options]
```

| Argument or option | What it is |
| --- | --- |
| `ROLE` | A role to claim. |
| `--take` | Take a role from the frontend that claims it now. |
| `--no-replay` | Write only what happens from now on, not what the epic has done. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic claim reviewer` | Answer for `reviewer` from this terminal until the epic ends. |
| `printf 'approve\n' \| hmz epic claim reviewer --take --json` | Take `reviewer`, answer its next question with `approve`, and write the epic's messages as JSON lines. |

What `hmz epic attach` prints.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `type` | `string` | What the message is, as `hmz epic attach --json` writes it. |

| Status | Meaning |
| --- | --- |
| `130` | Interrupted while following; the epic goes on. |

Daemon methods: `hosts.status`, `epic.attach`, `epic.claim`, `epic.answer`, `epic.detach`.

### hmz epic release

Takes a role from whichever frontend claims it and releases it, so that any frontend may answer its questions again.

```text
hmz epic release ROLE [options]
```

| Argument or option | What it is |
| --- | --- |
| `ROLE` | The role to release. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic release reviewer` | Free `reviewer` from a window that was left open. |

One line naming the role released.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `role` | `string` | The role released. |

Daemon methods: `hosts.status`, `epic.attach`, `epic.claim`, `epic.release`, `epic.detach`.

### hmz epic afk

A role that is away is not asked: its questions are answered with nothing at once, so the epic does not wait on a person. Away stays set after this command ends, until `--back`.

```text
hmz epic afk [ROLE] [options]
```

| Argument or option | What it is |
| --- | --- |
| `ROLE` | The role, or every role. |
| `--back` | Set it back instead of away. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic afk` | Set every role away. |
| `hmz epic afk reviewer --back` | Set `reviewer` back. |

One line: away or back.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `away` | `boolean` | Whether it was set away. |
| `role` | `string` | The role, or empty for every role. |

Daemon methods: `hosts.status`, `epic.attach`, `epic.afk`, `epic.detach`.

### hmz epic status

Reads the status of the host without attaching to it: whether an epic is running, stopping or idle, which flow and task, and every question waiting on a person.

```text
hmz epic status [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot of the host that holds the epic, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz epic status` | Show the epic of this folder. |
| `hmz epic status --json \| jq -r '.pending[].question'` | Print the ids of the questions waiting. |

One line with the state, flow, epic and task, then one line per waiting question: its id, role and text.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The host's workspace. |
| `slot` | `string` | The host's slot. |
| `pid` | `integer` | The host's process id. |
| `started` | `string` | When the host started, ISO 8601. |
| `state` | `string` | `running`, `stopping` or `idle`. |
| `run` | `integer` | The number of the epic going, else of the last, or 0. |
| `epic_kind` | `string` | `flow` for an epic, `chat` for a chat, or empty for none. |
| `flow` | `string` | The epic's flow, as it was named. |
| `epic` | `string` | The name the epic is recorded under. |
| `chat` | `string` | The chat's name, on a chat's host. |
| `task` | `string` | The epic's task. |
| `pending` | `list` | The questions waiting on a person. |
| `pending[].question` | `string` | The question's id. |
| `pending[].role` | `string` | The role it is asked of. |
| `pending[].text` | `string` | What is asked. |
| `pending[].mode` | `string` | `ask` for a question, `listen` for one any line answers. |
| `ended` | `object\|null` | How the last epic on this host ended, with `how` and `why`, or null. |
| `attached` | `integer` | How many frontends are attached. |
| `clients` | `list` | The frontends attached, each with `client`, `name` and `kind`. |
| `budget` | `object\|null` | The budget of the epic going, or null. |
| `usage` | `object\|null` | What the epic going has spent, or null. |
| `flows` | `list` | The refs of the flow calls in progress. |
| `calls` | `list` | The flow calls in progress, oldest first. |

Daemon methods: `hosts.status`.

## hmz flows

A flow is what an epic runs. These commands list the flows on offer in a workspace, show what one declares, list the harnesses that can fill its roles, check an epic before it starts, save a workspace's set-up of a flow, and copy a flow into a workspace to change it. Flows are installed with `hmz flowverses`.

```text
hmz flows list [options]
hmz flows show NAME [options]
hmz flows backends
hmz flows check FLOW [options]
hmz flows setup FLOW [options]
hmz flows fork FLOW [options]
```

### hmz flows list

List the flows on offer in a workspace.

```text
hmz flows list [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |

| Example | What it does |
| --- | --- |
| `hmz flows list` | List the flows on offer in the current directory. |
| `hmz flows list -w ~/code/app --json \| jq -r '.flows[].name'` | Print the names of the flows on offer in the folder ~/code/app, with jq. |

One line per flow: its name, where it came from, and what it does.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `flows` | `list` | The flows on offer. |
| `flows[].name` | `string` | The name the flow is started by. |
| `flows[].whose` | `string` | Where the flow came from: `local` for the workspace's own, `user` for yours, or the name of a flowverse. |
| `flows[].about` | `string` | What the flow does, in one line. |
| `flow` | `string` | The flow last set up in the workspace, or empty. |
| `running` | `list` | The flows running in the workspace now. |
| `running[].ref` | `string` | The ref of the running flow. |
| `running[].name` | `string` | The name of the running flow. |
| `running[].depth` | `integer` | How many flows called it; 0 for the flow the epic started with. |
| `running[].since` | `string` | When it began, ISO 8601. |
| `running[].task` | `string` | The task it was given. |

Daemon methods: `flows.list`.

### hmz flows show

Prints what is needed to start an epic of the flow. Each agent role takes `-a ROLE=HARNESS/MODEL`, each environment role `-e ROLE=ENV`, each param `-p KEY=VALUE`, and the budget at least one of `-p budget.cost=USD`, `-p budget.duration=TIME` and `-p budget.output_tokens=N`. `hmz flows backends` lists the harnesses and models.

```text
hmz flows show NAME [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name of the flow, as `hmz flows list` prints it. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |

| Example | What it does |
| --- | --- |
| `hmz flows show ralph_loop` | Show what the flow `ralph_loop` declares. |
| `hmz flows show ralph_loop --json \| jq -r '.agents[] \| select(.required and (.auto \| not)) \| .name'` | Print the names of the agent roles of `ralph_loop` that need an agent, with jq. |

The flow's name and description, its ref, whether it is resumable, each agent role with the harnesses installed that can fill it and what it may touch, each environment role, each param with its type, default and description, the options this folder last set it up with, and an `hmz exec` line to fill in.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | The name of the flow. |
| `ref` | `string` | Where the flow is loaded from. |
| `description` | `string` | What the flow says it does. |
| `resumable` | `boolean` | Whether an epic of the flow can be resumed. |
| `resumes` | `boolean` | Whether the workspace has an epic of the flow to resume now. |
| `agents` | `list` | The agent roles the flow declares. |
| `agents[].name` | `string` | The role, as `-a ROLE=` names it. |
| `agents[].required` | `boolean` | Whether the role must be given an agent. |
| `agents[].auto` | `boolean` | Whether the role is a person answering, which takes no agent. |
| `agents[].harness` | `string` | The only harness that can fill the role, or empty for any. |
| `agents[].permission` | `object` | What the role's agent may touch: `preset`, `network`, and `granular` as a list of `path` and `access`. |
| `agents[].skills` | `list` | The skills the role's agent is given. |
| `agents[].clis` | `list` | The harnesses installed on the daemon's machine that can fill the role. |
| `envs` | `list` | The environment roles the flow declares. |
| `envs[].name` | `string` | The role, as `-e ROLE=` names it. |
| `envs[].required` | `boolean` | Whether the role must be given an environment. |
| `envs[].auto` | `boolean` | Whether the role is the folder the epic runs in, which takes no environment. |
| `envs[].cpu` | `number\|null` | How many CPUs the role asks for, or null. |
| `envs[].memory` | `string\|null` | How much memory the role asks for, or null. |
| `envs[].gpu` | `number\|null` | How many GPUs the role asks for, or null. |
| `envs[].image` | `string\|null` | The image the role asks for, or null. |
| `params` | `object` | The flow's params as a JSON schema; each key of `properties` is a `-p KEY=VALUE`. |
| `remembered` | `object` | What the workspace last set the flow up with: `agents`, `envs`, `params`, `budget`, `profile_flow`, `profile_environment`, `backup`. |

Daemon methods: `flows.get`.

### hmz flows backends

Lists what can fill an agent role on the daemon's machine, each written as `-a ROLE=` takes it: `HARNESS/MODEL` for this machine's own sign-in, `HARNESS@ACCOUNT/MODEL` for an account; an effort goes after the model as `:EFFORT`. Also lists the harnesses not installed and the backends an environment can be put on.

```text
hmz flows backends
```

| Example | What it does |
| --- | --- |
| `hmz flows backends` | List every harness, account and model that can fill an agent role. |
| `hmz flows backends --json \| jq -r '.clis \| keys[]'` | Print the names of the installed harnesses, with jq. |

Under Installed, one line per harness, account and model, written as `-a` takes it, then the efforts the model takes; under Not installed, the same for harnesses that can be installed; under environments, the backends `-e` takes.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `clis` | `object` | The installed harnesses, by name. |
| `clis.&lt;harness>.accounts` | `list` | The accounts the harness runs as, this machine's own sign-in first. |
| `clis.&lt;harness>.accounts[].name` | `string` | The account's name; empty for this machine's own sign-in. |
| `clis.&lt;harness>.accounts[].models` | `list` | The models the harness runs as that account, each `name` and `efforts`. |
| `clis.&lt;harness>.accounts[].asked` | `string` | When the harness was last asked for its models, or empty if never. |
| `installable` | `object` | The harnesses that can be installed, by name, each a list of models with `name` and `efforts`. |
| `envs` | `list` | The backends an environment can be put on, as `-e` writes each. |

Daemon methods: `flows.backends`.

### hmz flows check

Takes the options `hmz exec` takes and checks everything `hmz exec` checks before an epic starts: the flow, each role and what fills it, the params, the budget, the epic to resume and the backup targets. Starts no agent and no environment, and does not check whether an environment can be reached.

```text
hmz flows check FLOW [options]
```

| Argument or option | What it is |
| --- | --- |
| `FLOW` | The flow: a name `hmz flows list` prints, or a path or ref as `hmz exec -f` takes one. |
| `-a, --agents ROLE=AGENT` | The agent for one agent role, as `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` or the name of a nous. May be given more than once. |
| `-e, --envs ROLE=ENV` | The environment for one environment role, as `hmz exec -e` writes one, for example `local` or `ssh@NAME/DIRECTORY`. May be given more than once. |
| `-p, --params KEY=VALUE` | One param of the flow, or one limit of the budget as `budget.cost=5`, `budget.duration=1h` or `budget.output_tokens=200k`. May be given more than once. |
| `--profile-flow` | Profile the flow's own Python code during the epic. |
| `--profile-environment` | Profile the programs the epic's agents start. |
| `--backup NAME` | A backup target the epic is backed up to; `none` for no backup; the default targets when not given. May be given more than once. |
| `--resume` | Check resuming the newest epic of this flow in the workspace instead of starting a new one. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |

| Example | What it does |
| --- | --- |
| `hmz flows check ralph_loop -a coder=claude/claude-opus-5:high -p budget.cost=5` | Check an epic of `ralph_loop` with one agent and a cost limit of five dollars. |
| `hmz flows check ralph_loop --resume -p budget.cost=5 --json \| jq .names` | Check resuming the newest epic of `ralph_loop` and print the agent filling each role as JSON. |

A line saying the epic can start, then the flow's ref, the agent filling each role, the budget and the backup targets, and any limit of the budget that cannot be enforced.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `flow` | `string` | The flow, as it was named. |
| `ref` | `string` | Where the flow is loaded from. |
| `declared` | `object` | What the flow declares, with the fields `hmz flows show --json` prints. |
| `names` | `object` | The name of the agent filling each agent role, by role. |
| `budget` | `object\|null` | The budget the epic would run under: `duration`, `cost`, `output_tokens` and `graceful`. |
| `backup` | `list` | The backup targets the epic would go to. |
| `unreadable` | `string` | Every limit of the budget that nothing the epic runs can enforce, in words, or empty. |

Daemon methods: `flows.check`.

### hmz flows setup

Saves the agents, environments, params, budget, profiling and backup targets a workspace runs a flow with. A new epic of that flow in the workspace opens with them filled in, on the web page and in the terminal interface. Every required agent role needs an agent and the budget needs at least one limit.

```text
hmz flows setup FLOW [options]
```

| Argument or option | What it is |
| --- | --- |
| `FLOW` | The name of the flow, as `hmz flows list` prints it. |
| `-a, --agents ROLE=AGENT` | The agent for one agent role, as `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` or the name of a nous. May be given more than once. |
| `-e, --envs ROLE=ENV` | The environment for one environment role, as `hmz exec -e` writes one, for example `local` or `ssh@NAME/DIRECTORY`. May be given more than once. |
| `-p, --params KEY=VALUE` | One param of the flow, or one limit of the budget as `budget.cost=5`, `budget.duration=1h` or `budget.output_tokens=200k`. May be given more than once. |
| `--profile-flow` | Profile the flow's own Python code during the epic. |
| `--profile-environment` | Profile the programs the epic's agents start. |
| `--backup NAME` | A backup target the epic is backed up to; `none` for no backup; the default targets when not given. May be given more than once. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |

| Example | What it does |
| --- | --- |
| `hmz flows setup ralph_loop -a coder=claude/claude-opus-5:high -p budget.cost=5` | Save that `ralph_loop` runs in this folder with one agent and a cost limit of five dollars. |
| `hmz flows setup ralph_loop -w ~/code/app -a coder=codex/gpt-5 -p budget.duration=2h --backup none` | Save the set-up of `ralph_loop` for the folder ~/code/app, with a time limit and no backup. |

One line saying the set-up was saved.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | The name of the flow. |
| `ref` | `string` | Where the flow is loaded from. |
| `description` | `string` | What the flow says it does. |
| `resumable` | `boolean` | Whether an epic of the flow can be resumed. |
| `resumes` | `boolean` | Whether the workspace has an epic of the flow to resume now. |
| `agents` | `list` | The agent roles the flow declares. |
| `agents[].name` | `string` | The role, as `-a ROLE=` names it. |
| `agents[].required` | `boolean` | Whether the role must be given an agent. |
| `agents[].auto` | `boolean` | Whether the role is a person answering, which takes no agent. |
| `agents[].harness` | `string` | The only harness that can fill the role, or empty for any. |
| `agents[].permission` | `object` | What the role's agent may touch: `preset`, `network`, and `granular` as a list of `path` and `access`. |
| `agents[].skills` | `list` | The skills the role's agent is given. |
| `agents[].clis` | `list` | The harnesses installed on the daemon's machine that can fill the role. |
| `envs` | `list` | The environment roles the flow declares. |
| `envs[].name` | `string` | The role, as `-e ROLE=` names it. |
| `envs[].required` | `boolean` | Whether the role must be given an environment. |
| `envs[].auto` | `boolean` | Whether the role is the folder the epic runs in, which takes no environment. |
| `envs[].cpu` | `number\|null` | How many CPUs the role asks for, or null. |
| `envs[].memory` | `string\|null` | How much memory the role asks for, or null. |
| `envs[].gpu` | `number\|null` | How many GPUs the role asks for, or null. |
| `envs[].image` | `string\|null` | The image the role asks for, or null. |
| `params` | `object` | The flow's params as a JSON schema; each key of `properties` is a `-p KEY=VALUE`. |
| `remembered` | `object` | What the workspace last set the flow up with: `agents`, `envs`, `params`, `budget`, `profile_flow`, `profile_environment`, `backup`. |

Daemon methods: `flows.get`, `flows.setup`.

### hmz flows fork

Copies a flow into the workspace's own flows, where it can be edited. The copy is offered in that workspace as a `local` flow under the same name.

```text
hmz flows fork FLOW [options]
```

| Argument or option | What it is |
| --- | --- |
| `FLOW` | The name of the flow to copy, as `hmz flows list` prints it. |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |

| Example | What it does |
| --- | --- |
| `hmz flows fork ralph_loop` | Copy the flow `ralph_loop` into the current directory. |
| `hmz flows fork ralph_loop -w ~/code/app --json \| jq -r .at` | Copy `ralph_loop` into the folder ~/code/app and print where the copy is, with jq. |

What was copied and where to.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `said` | `string` | What was done, in words. |
| `at` | `string` | The path of the copy. |

Daemon methods: `flows.fork`.

## hmz flowverses

A flowverse is an index of flows kept in a git repository. These commands list the flowverses and the flows installed from them, show the flows and releases one lists, add, fetch and remove a flowverse, and install, update, switch and uninstall a flow. Flows cannot be installed, uninstalled or removed while an epic is running.

```text
hmz flowverses list
hmz flowverses show NAME
hmz flowverses add URL [options]
hmz flowverses fetch NAME
hmz flowverses remove NAME [options]
hmz flowverses install FLOW [options]
hmz flowverses uninstall FLOW [options]
```

### hmz flowverses list

List the flowverses, the installed flows and their newer releases.

```text
hmz flowverses list
```

| Example | What it does |
| --- | --- |
| `hmz flowverses list` | List the flowverses and the installed flows. |
| `hmz flowverses list --json \| jq -r '.updates[] \| "\(.flow) \(.to)"'` | Print each installed flow that has a newer release and that release, with jq. |

Under Flowverses, one line per flowverse: its name, its URL, how many flows are installed from it; under Installed, one line per installed flow: its name, its release, its flowverse, and the newer release where there is one.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `verses` | `list` | The flowverses. |
| `verses[].name` | `string` | The name of the flowverse. |
| `verses[].url` | `string` | Where it is fetched from, without credentials; empty for a local one. |
| `verses[].fetched` | `boolean` | Whether its index has been fetched. |
| `verses[].fixed` | `boolean` | Whether it is built in and cannot be removed. |
| `verses[].edited` | `boolean` | Whether something is written into its index, which fetching resets. |
| `verses[].installed` | `integer` | How many flows are installed from it. |
| `installed` | `list` | The installed flows. |
| `installed[].flow` | `string` | The name the flow is started by, and the name `hmz flowverses install` and `uninstall` take. |
| `installed[].verse` | `string` | The flowverse it was installed from. |
| `installed[].listed` | `string` | The name its flowverse lists it under. |
| `installed[].version` | `string` | The release installed. |
| `installed[].repo` | `string` | The repository the release came from. |
| `installed[].ref` | `string` | The git ref of the release. |
| `updates` | `list` | The installed flows that have a newer release. |
| `updates[].flow` | `string` | The name of the flow. |
| `updates[].from` | `string` | The release installed. |
| `updates[].to` | `string` | The newest release. |

Daemon methods: `flowverses.list`.

### hmz flowverses show

Show the flows one flowverse lists and every release of each.

```text
hmz flowverses show NAME
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name of the flowverse, as `hmz flowverses list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz flowverses show official` | Show the flows and releases the flowverse `official` lists. |
| `hmz flowverses show official --json \| jq -r '.flows[] \| select(.installed == "") \| .flow'` | Print the flows of `official` that are not installed, with jq. |

Prints the flowverse's name and URL, then one line per release, newest first under each flow: the flow as `hmz flowverses install` takes it, the release, whether it is installed, and its description; then what its index skipped and why.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | The name of the flowverse. |
| `url` | `string` | Where it is fetched from, without credentials; empty for a local one. |
| `fetched` | `boolean` | Whether its index has been fetched. |
| `fixed` | `boolean` | Whether it is built in and cannot be removed. |
| `edited` | `boolean` | Whether something is written into its index, which fetching resets. |
| `flows` | `list` | The flows its index lists. |
| `flows[].listed` | `string` | The name the flowverse lists the flow under. |
| `flows[].flow` | `string` | The name `hmz flowverses install` takes for it. |
| `flows[].installed` | `string` | The release installed, or empty. |
| `flows[].releases` | `list` | Every release, newest first, each `version`, `description`, `prerelease`, `license`, `repo` and `dependencies`. |
| `skipped` | `list` | What in the index could not be read, each `at` and `why`. |

Daemon methods: `flowverses.get`.

### hmz flowverses add

Add a flowverse by its repository.

```text
hmz flowverses add URL [options]
```

| Argument or option | What it is |
| --- | --- |
| `URL` | The flowverse's git repository, as `owner/repo` on GitHub or a URL. |
| `--name NAME` | The name to keep the flowverse under; the name its URL gives when not given. |

| Example | What it does |
| --- | --- |
| `hmz flowverses add acme/flows` | Add the flowverse kept in the GitHub repository `acme/flows`. |
| `hmz flowverses add https://git.example.com/team/flows.git --name team` | Add a flowverse from a git URL and keep it under the name `team`. |

Prints what was done, in one line.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `said` | `string` | What was done, in words. |
| `verses` | `list` | The flowverses. |
| `verses[].name` | `string` | The name of the flowverse. |
| `verses[].url` | `string` | Where it is fetched from, without credentials; empty for a local one. |
| `verses[].fetched` | `boolean` | Whether its index has been fetched. |
| `verses[].fixed` | `boolean` | Whether it is built in and cannot be removed. |
| `verses[].edited` | `boolean` | Whether something is written into its index, which fetching resets. |
| `verses[].installed` | `integer` | How many flows are installed from it. |
| `installed` | `list` | The installed flows. |
| `installed[].flow` | `string` | The name the flow is started by, and the name `hmz flowverses install` and `uninstall` take. |
| `installed[].verse` | `string` | The flowverse it was installed from. |
| `installed[].listed` | `string` | The name its flowverse lists it under. |
| `installed[].version` | `string` | The release installed. |
| `installed[].repo` | `string` | The repository the release came from. |
| `installed[].ref` | `string` | The git ref of the release. |
| `updates` | `list` | The installed flows that have a newer release. |
| `updates[].flow` | `string` | The name of the flow. |
| `updates[].from` | `string` | The release installed. |
| `updates[].to` | `string` | The newest release. |

Daemon methods: `flowverses.add`.

### hmz flowverses fetch

Fetches the flowverse's index from its repository, so that `hmz flowverses list` shows the newer releases. Fetching resets anything written into the index.

```text
hmz flowverses fetch NAME
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name of the flowverse, as `hmz flowverses list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz flowverses fetch official` | Fetch the index of the flowverse `official`. |
| `hmz flowverses fetch official --json \| jq -r '.updates[].flow'` | Fetch `official` and print the flows that now have a newer release, with jq. |

Prints what was done, in one line.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `said` | `string` | What was done, in words. |
| `verses` | `list` | The flowverses. |
| `verses[].name` | `string` | The name of the flowverse. |
| `verses[].url` | `string` | Where it is fetched from, without credentials; empty for a local one. |
| `verses[].fetched` | `boolean` | Whether its index has been fetched. |
| `verses[].fixed` | `boolean` | Whether it is built in and cannot be removed. |
| `verses[].edited` | `boolean` | Whether something is written into its index, which fetching resets. |
| `verses[].installed` | `integer` | How many flows are installed from it. |
| `installed` | `list` | The installed flows. |
| `installed[].flow` | `string` | The name the flow is started by, and the name `hmz flowverses install` and `uninstall` take. |
| `installed[].verse` | `string` | The flowverse it was installed from. |
| `installed[].listed` | `string` | The name its flowverse lists it under. |
| `installed[].version` | `string` | The release installed. |
| `installed[].repo` | `string` | The repository the release came from. |
| `installed[].ref` | `string` | The git ref of the release. |
| `updates` | `list` | The installed flows that have a newer release. |
| `updates[].flow` | `string` | The name of the flow. |
| `updates[].from` | `string` | The release installed. |
| `updates[].to` | `string` | The newest release. |

Daemon methods: `flowverses.fetch`.

### hmz flowverses remove

Removes the flowverse and uninstalls every flow installed from it. Asks first unless `-y` is given; any answer other than yes changes nothing and exits with status 1. Refused while an epic is running.

```text
hmz flowverses remove NAME [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The name of the flowverse, as `hmz flowverses list` prints it. |
| `-y, --yes` | Do it without asking first. |

| Example | What it does |
| --- | --- |
| `hmz flowverses remove team` | Remove the flowverse `team` after confirming. |
| `hmz flowverses remove team -y` | Remove the flowverse `team` without asking. |

Prints what was done, in one line.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `said` | `string` | What was done, in words. |
| `verses` | `list` | The flowverses. |
| `verses[].name` | `string` | The name of the flowverse. |
| `verses[].url` | `string` | Where it is fetched from, without credentials; empty for a local one. |
| `verses[].fetched` | `boolean` | Whether its index has been fetched. |
| `verses[].fixed` | `boolean` | Whether it is built in and cannot be removed. |
| `verses[].edited` | `boolean` | Whether something is written into its index, which fetching resets. |
| `verses[].installed` | `integer` | How many flows are installed from it. |
| `installed` | `list` | The installed flows. |
| `installed[].flow` | `string` | The name the flow is started by, and the name `hmz flowverses install` and `uninstall` take. |
| `installed[].verse` | `string` | The flowverse it was installed from. |
| `installed[].listed` | `string` | The name its flowverse lists it under. |
| `installed[].version` | `string` | The release installed. |
| `installed[].repo` | `string` | The repository the release came from. |
| `installed[].ref` | `string` | The git ref of the release. |
| `updates` | `list` | The installed flows that have a newer release. |
| `updates[].flow` | `string` | The name of the flow. |
| `updates[].from` | `string` | The release installed. |
| `updates[].to` | `string` | The newest release. |

| Status | Meaning |
| --- | --- |
| `1` | The daemon refused it, or you did not answer yes. |

Daemon methods: `flowverses.remove`.

### hmz flowverses install

Installs the newest release of a flow, or the release `--version` names. For a flow already installed this updates it or switches its release. Refused while an epic is running.

```text
hmz flowverses install FLOW [options]
```

| Argument or option | What it is |
| --- | --- |
| `FLOW` | The flow, as `hmz flowverses show` prints it: bare for the official flowverse, `@FLOWVERSE/FLOW` for another. |
| `--version VERSION` | The release to install; the newest when not given. |

| Example | What it does |
| --- | --- |
| `hmz flowverses install ralph_loop` | Install the newest release of `ralph_loop`, or update it to that release. |
| `hmz flowverses install @team/review --version 1.2.0` | Install release 1.2.0 of the flow `review` from the flowverse `team`. |

Prints what was done, in one line.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `said` | `string` | What was done, in words. |
| `verses` | `list` | The flowverses. |
| `verses[].name` | `string` | The name of the flowverse. |
| `verses[].url` | `string` | Where it is fetched from, without credentials; empty for a local one. |
| `verses[].fetched` | `boolean` | Whether its index has been fetched. |
| `verses[].fixed` | `boolean` | Whether it is built in and cannot be removed. |
| `verses[].edited` | `boolean` | Whether something is written into its index, which fetching resets. |
| `verses[].installed` | `integer` | How many flows are installed from it. |
| `installed` | `list` | The installed flows. |
| `installed[].flow` | `string` | The name the flow is started by, and the name `hmz flowverses install` and `uninstall` take. |
| `installed[].verse` | `string` | The flowverse it was installed from. |
| `installed[].listed` | `string` | The name its flowverse lists it under. |
| `installed[].version` | `string` | The release installed. |
| `installed[].repo` | `string` | The repository the release came from. |
| `installed[].ref` | `string` | The git ref of the release. |
| `updates` | `list` | The installed flows that have a newer release. |
| `updates[].flow` | `string` | The name of the flow. |
| `updates[].from` | `string` | The release installed. |
| `updates[].to` | `string` | The newest release. |

Daemon methods: `flowverses.install`.

### hmz flowverses uninstall

Uninstalls a flow installed from a flowverse. Asks first unless `-y` is given; any answer other than yes changes nothing and exits with status 1. Refused while an epic is running.

```text
hmz flowverses uninstall FLOW [options]
```

| Argument or option | What it is |
| --- | --- |
| `FLOW` | The installed flow, as `hmz flowverses list` prints it. |
| `-y, --yes` | Do it without asking first. |

| Example | What it does |
| --- | --- |
| `hmz flowverses uninstall ralph_loop` | Uninstall the flow `ralph_loop` after confirming. |
| `hmz flowverses uninstall @team/review -y` | Uninstall the flow `review` of the flowverse `team` without asking. |

Prints what was done, in one line.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `said` | `string` | What was done, in words. |
| `verses` | `list` | The flowverses. |
| `verses[].name` | `string` | The name of the flowverse. |
| `verses[].url` | `string` | Where it is fetched from, without credentials; empty for a local one. |
| `verses[].fetched` | `boolean` | Whether its index has been fetched. |
| `verses[].fixed` | `boolean` | Whether it is built in and cannot be removed. |
| `verses[].edited` | `boolean` | Whether something is written into its index, which fetching resets. |
| `verses[].installed` | `integer` | How many flows are installed from it. |
| `installed` | `list` | The installed flows. |
| `installed[].flow` | `string` | The name the flow is started by, and the name `hmz flowverses install` and `uninstall` take. |
| `installed[].verse` | `string` | The flowverse it was installed from. |
| `installed[].listed` | `string` | The name its flowverse lists it under. |
| `installed[].version` | `string` | The release installed. |
| `installed[].repo` | `string` | The repository the release came from. |
| `installed[].ref` | `string` | The git ref of the release. |
| `updates` | `list` | The installed flows that have a newer release. |
| `updates[].flow` | `string` | The name of the flow. |
| `updates[].from` | `string` | The release installed. |
| `updates[].to` | `string` | The newest release. |

| Status | Meaning |
| --- | --- |
| `1` | The daemon refused it, or you did not answer yes. |

Daemon methods: `flowverses.uninstall`.

## hmz help

Prints the help of hmz, or of the command named. Prints every command at once as text or JSON, and shell completion scripts.

```text
hmz help [COMMAND...] [options]
```

| Argument or option | What it is |
| --- | --- |
| `COMMAND` | The command to read about, as its words after `hmz`; or `completions` and a shell. |
| `--all` | Print the full help of every command, one after another. |

Asks no daemon, and takes no `--daemon`.

| Example | What it does |
| --- | --- |
| `hmz help` | Show the commands of hmz, grouped by what they are about. |
| `hmz help devices revoke` | Show everything about `hmz devices revoke`. |
| `hmz help --all` | Print the full help of every command. |
| `hmz help --json` | Print every command as one JSON document, for an agent to load. |
| `hmz help --json devices` | Print `hmz devices` and the commands under it as one JSON document. |
| `hmz help completions bash > ~/.local/share/bash-completion/completions/hmz` | Write the bash completion script to where bash loads completions from. |
| `hmz help completions zsh > ~/.zfunc/_hmz` | Write the zsh completion script to a directory of zsh's `fpath`. |
| `hmz help completions fish > ~/.config/fish/completions/hmz.fish` | Write the fish completion script to where fish loads completions from. |

Prints the help text, or the completion script.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `version` | `string` | The version of hmz. |
| `usage` | `string` | The line hmz itself takes. |
| `description` | `string` | What hmz is, in a sentence or two. |
| `conventions` | `object` | What commands share unless their own help says otherwise. |
| `conventions.options` | `list` | The options commands share, each as an entry of `commands[].arguments`. |
| `conventions.exit_status` | `object` | What each shared exit code means, by code. |
| `conventions.json` | `string` | What a command prints with `--json`, when it does what was asked and when it fails. |
| `groups` | `list` | The commands grouped by what they are about, in the order `hmz --help` lists them. |
| `groups[].title` | `string` | The heading of the group. |
| `groups[].commands` | `list` | The names of the commands in the group. |
| `commands` | `list` | Every command, or only the one named, each holding the commands under it. |
| `commands[].command` | `string` | The command as it is typed, starting with `hmz`. |
| `commands[].summary` | `string` | What the command does, in a line. |
| `commands[].description` | `string` | What the command does, in a paragraph. |
| `commands[].usage` | `string` | The line the command takes. |
| `commands[].help` | `string` | The line that prints the command's own help, for a command not described further here. |
| `commands[].commands` | `list` | The commands under a group, each shaped like this one. |
| `commands[].arguments` | `list` | What the command takes, positional arguments and options. |
| `commands[].arguments[].name` | `string` | The argument or option as its help shows it. |
| `commands[].arguments[].flags` | `list` | The spellings of an option, or the name of a positional argument. |
| `commands[].arguments[].description` | `string` | What the argument or option is. |
| `commands[].arguments[].positional` | `boolean` | Whether it is given by position rather than by name. |
| `commands[].arguments[].required` | `boolean` | Whether it must be given. |
| `commands[].arguments[].repeatable` | `boolean` | Whether it may be given more than once. |
| `commands[].arguments[].takes_value` | `boolean` | Whether an option is followed by a value. |
| `commands[].arguments[].choices` | `list` | The only values it takes, or an empty list for any. |
| `commands[].arguments[].default` | `any` | Its value when it is not given, or null. |
| `commands[].examples` | `list` | Command lines to type, each with its `line` and what it `does`. |
| `commands[].prints` | `string` | What the command prints without `--json`. |
| `commands[].json` | `list` | The fields of the command's `--json` document, each with `field`, `type` and `description`. |
| `commands[].exit_status` | `object` | What each exit code of the command means, by code. |
| `commands[].daemon_methods` | `list` | The daemon methods the command calls. |
| `commands[].see_also` | `list` | Other commands worth reading beside it. |
| `shell` | `string` | With `completions`, the shell the script is for. |
| `script` | `string` | With `completions`, the completion script. |

## hmz hosts

A host is the process the daemon holds one workspace's epic, or one chat, in. It is named by its workspace and its slot: empty for the workspace's own host, `exec:&lt;id>` for an epic beside it, `chat:&lt;id>` for a chat.

```text
hmz hosts list [options]
hmz hosts open [options]
hmz hosts detach [options]
hmz hosts stop [options]
```

### hmz hosts list

List the hosts and what each is running.

```text
hmz hosts list [options]
```

| Argument or option | What it is |
| --- | --- |
| `--running` | List only hosts whose epic or chat is running or stopping. |

| Example | What it does |
| --- | --- |
| `hmz hosts list` | List every host of this daemon. |
| `hmz hosts list --running --json \| jq -r '.hosts[] \| select(.asking != []) \| .workspace'` | Print the workspaces whose epics wait on an answer. |

One line per host: workspace, slot, state, flow and task.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `hosts` | `list` | The hosts, in the order they started. |
| `hosts[].workspace` | `string` | The host's workspace. |
| `hosts[].slot` | `string` | The host's slot, empty for the workspace's own host. |
| `hosts[].pid` | `integer` | The host's process id. |
| `hosts[].started` | `string` | When the host started, ISO 8601. |
| `hosts[].state` | `string` | `running`, `stopping` or `idle`. |
| `hosts[].kind` | `string` | `flow` for an epic, `chat` for a chat, empty when idle. |
| `hosts[].flow` | `string` | The flow of the epic going. |
| `hosts[].epic` | `string` | The name the epic going is recorded under. |
| `hosts[].chat` | `string` | The name of the chat going. |
| `hosts[].task` | `string` | The epic's task, or the chat's first message. |
| `hosts[].asking` | `list` | The questions it waits on, each `&lt;run>:&lt;question>`. |

Daemon methods: `hosts.list`, `hosts.running`.

### hmz hosts open

Starts the host of a workspace and slot where the daemon holds none, and attaches nothing to it; a host already held is answered as it is. `--slot exec:` or `--slot chat:` alone makes a new slot of that kind and prints the slot made. An epic is then started on it with `hmz epic start`.

```text
hmz hosts open [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The slot to open, as `hmz hosts list` prints it; `exec:` or `chat:` alone for a new slot of that kind; when not given, the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz hosts open` | Start the host of this folder. |
| `hmz hosts open --slot exec: --json \| jq -r .slot` | Make a new exec slot in this folder and print its name. |

Prints one line with the host's process id, workspace and slot.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `pid` | `integer` | The host's process id. |
| `workspace` | `string` | The host's workspace. |
| `started` | `string` | When the host started, ISO 8601. |
| `kind` | `string` | What the process is, always `host`. |
| `protocol` | `string` | The version of the protocol the host speaks. |
| `slot` | `string` | The host's slot. |

Daemon methods: `hosts.open`.

### hmz hosts detach

Lets go every frontend attached to the host of a workspace and slot -- every web page, terminal interface and command following it -- and leaves its epic or chat running. Roles the frontends had claimed are released. A frontend may attach again.

```text
hmz hosts detach [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The host's slot, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz hosts detach` | Let go every frontend of the host of this folder. |
| `hmz hosts detach --json \| jq .let_go` | Print how many frontends were let go. |

Prints one line saying how many frontends were let go.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace of the host. |
| `slot` | `string` | The slot of the host. |
| `let_go` | `integer` | How many frontends were let go. |

Daemon methods: `hosts.detach`.

### hmz hosts stop

Closes the host of a workspace and slot. An epic or chat it is running is stopped first. To stop an epic and keep its host, use `hmz epic stop`.

```text
hmz hosts stop [options]
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace DIR` | The workspace, a folder on the daemon's machine; the current directory when not given. |
| `--slot SLOT` | The host's slot, as `hmz hosts list` prints it, or the workspace's own host. |

| Example | What it does |
| --- | --- |
| `hmz hosts stop` | Close the host of this directory. |
| `hmz hosts stop -w ~/work/app --slot exec:1f2e` | Close the host of one epic of another workspace. |

One line once the daemon has taken the request.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace of the host closed. |
| `slot` | `string` | The slot of the host closed. |

Daemon methods: `hosts.stop`.

## hmz notices

The daemon makes a notice when an epic or a chat is done, fails, is stopped, asks you a question, or waits for what to say next. Each notice has a number greater than every earlier one. These commands list the notices kept and follow new ones as they arrive.

```text
hmz notices list [options]
hmz notices follow [options]
```

### hmz notices list

List the notices the daemon keeps, oldest first.

```text
hmz notices list [options]
```

| Argument or option | What it is |
| --- | --- |
| `--after ID` | List only the notices after the one with this number. |
| `--kind KIND` | Print only notices of this kind. One of `done`, `failed`, `stopped`, `asked`, `listening`. May be given more than once. |

| Example | What it does |
| --- | --- |
| `hmz notices list` | Lists the latest notices, oldest first. |
| `hmz notices list --after 41 --kind failed --kind asked --json` | Lists, as JSON, what failed or asked a question since notice 41. |

Prints one line per notice, oldest first: its number, the local time, its kind, the chat or epic it is about, and what it says.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `notices` | `list` | The notices, oldest first, at most the latest 200. |
| `notices[].id` | `integer` | Its number, greater than that of every earlier notice. |
| `notices[].kind` | `string` | `done`, `failed`, `stopped`, `asked` or `listening`. |
| `notices[].workspace` | `string` | The workspace of the host it is about. |
| `notices[].slot` | `string` | The slot of that host. |
| `notices[].epic` | `string` | The name of the epic it is about, empty for a chat. |
| `notices[].chat` | `string` | The name of the chat it is about, empty for an epic. |
| `notices[].flow` | `string` | The epic's flow, `chat` for a chat. |
| `notices[].task` | `string` | The epic's task, or the chat's first message. |
| `notices[].role` | `string` | The role a question is asked of, else empty. |
| `notices[].text` | `string` | What it says: the question, the reply, or why it failed. |
| `notices[].at` | `number` | When it was made, seconds since the Unix epoch. |
| `last` | `integer` | The number of the newest notice the daemon has made, 0 when there is none; `hmz notices follow --after` takes it. |

Daemon methods: `notices.list`.

### hmz notices follow

Prints one line for each notice as the daemon makes it and runs until you press ctrl+c. With `--after` it first prints the notices kept after that number. With `--json` each notice is one JSON object on a line of its own.

```text
hmz notices follow [options]
```

| Argument or option | What it is |
| --- | --- |
| `--after ID` | First print the notices kept after the one with this number; when not given, only notices made from now on are printed. |
| `--kind KIND` | Print only notices of this kind. One of `done`, `failed`, `stopped`, `asked`, `listening`. May be given more than once. |

| Example | What it does |
| --- | --- |
| `hmz notices follow` | Prints each notice as it arrives. |
| `hmz notices follow --kind asked --json \| jq -r .text` | Prints each question an epic asks you, as it is asked. |
| `hmz notices follow --after "$(hmz notices list --json \| jq .last)"` | Follows on from the newest notice, missing none made in between. |

Prints one line per notice as it arrives: its number, the local time, its kind, the chat or epic it is about, and what it says. With `--json`, prints one object per line instead.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `integer` | Its number, greater than that of every earlier notice. |
| `kind` | `string` | `done`, `failed`, `stopped`, `asked` or `listening`. |
| `workspace` | `string` | The workspace of the host it is about. |
| `slot` | `string` | The slot of that host. |
| `epic` | `string` | The name of the epic it is about, empty for a chat. |
| `chat` | `string` | The name of the chat it is about, empty for an epic. |
| `flow` | `string` | The epic's flow, `chat` for a chat. |
| `task` | `string` | The epic's task, or the chat's first message. |
| `role` | `string` | The role a question is asked of, else empty. |
| `text` | `string` | What it says: the question, the reply, or why it failed. |
| `at` | `number` | When it was made, seconds since the Unix epoch. |

Daemon methods: `notices.subscribe`, `notices.unsubscribe`.

## hmz nous

A concrete nous is a model of a harness, written `HARNESS[@ACCOUNT]/MODEL[:EFFORT]`. A virtual nous is a name for a graph of other nous: a turn that fails there is tried again, on the same model or on another. An agent is given either with `-a`.

```text
hmz nous list [options]
hmz nous scan
hmz nous set NAME [options]
hmz nous rename NAME TO
hmz nous clear NAME
```

### hmz nous list

List the nous written, or every concrete nous.

```text
hmz nous list [options]
```

| Argument or option | What it is |
| --- | --- |
| `--concrete` | Print every concrete nous the harnesses run instead, one per line. |

| Example | What it does |
| --- | --- |
| `hmz nous list` | List every nous that has tries, a limit or a graph written. |
| `hmz nous list --concrete` | List every model an agent can be given. |
| `hmz nous list --json \| jq -r '.policies[].name'` | Print the names of the ways of waiting with jq. |

One line per nous written: name, `Virtual` or `Concrete`, tries and policy, limit, graph, and where a turn goes once its tries are spent. A graph that is a chain is printed as its nous separated by commas, any other as JSON.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `nous` | `list` | Every nous that has something written of it. |
| `nous[].name` | `string` | The nous: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` for a concrete one, a name for a virtual one. |
| `nous[].virtual` | `boolean` | Whether it is a virtual nous, a name for a graph of other nous. |
| `nous[].tries` | `integer` | How many more goes a turn that fails there is given. |
| `nous[].policy` | `string` | How long is waited between tries, one of `policies`. |
| `nous[].timeout` | `number` | The limit of a turn in seconds, 0 for no limit. |
| `nous[].graph` | `object\|null` | The graph a virtual nous stands for, null for a concrete nous. |
| `nous[].graph.start` | `string` | Id of the node a turn starts at. |
| `nous[].graph.nodes` | `list` | The nodes, each `id`, `use` (a nous) or `balance` (a strategy) with `among` (each `nous` and `weight`) and `spread`, and `on` (fault to node id, `*` for any other). |
| `nous[].then` | `object\|null` | The graph a turn goes to once its tries are spent, in the same shape, or null for nowhere. |
| `policies` | `list` | The ways of waiting between tries, each `name` and `about`. |
| `default` | `string` | The policy used where none is given. |
| `strategies` | `list` | The ways a balance node picks among its members, each `name` and `about`. |
| `faults` | `list` | Every fault an edge of a graph can be for, and `*` for any other. |
| `concrete` | `list` | Every concrete nous the installed harnesses and the accounts run, without an effort. |
| `scanning` | `boolean` | Whether a scan of the harnesses is going on. |

Daemon methods: `nous.list`.

### hmz nous scan

Asks every harness installed on the daemon's machine which models it runs, as the machine's own sign-in and as each account. This starts each harness and can take a minute. A harness that does not answer is reported and does not fail the command.

```text
hmz nous scan
```

| Example | What it does |
| --- | --- |
| `hmz nous scan` | Ask every harness what it runs and print how many concrete nous were found. |
| `hmz nous scan --json \| jq '.failed'` | Print the harnesses that would not answer, with jq. |

How many concrete nous were found, on standard output; one line per harness that would not answer, on standard error.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `nous` | `list` | Every nous that has something written of it. |
| `nous[].name` | `string` | The nous: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` for a concrete one, a name for a virtual one. |
| `nous[].virtual` | `boolean` | Whether it is a virtual nous, a name for a graph of other nous. |
| `nous[].tries` | `integer` | How many more goes a turn that fails there is given. |
| `nous[].policy` | `string` | How long is waited between tries, one of `policies`. |
| `nous[].timeout` | `number` | The limit of a turn in seconds, 0 for no limit. |
| `nous[].graph` | `object\|null` | The graph a virtual nous stands for, null for a concrete nous. |
| `nous[].graph.start` | `string` | Id of the node a turn starts at. |
| `nous[].graph.nodes` | `list` | The nodes, each `id`, `use` (a nous) or `balance` (a strategy) with `among` (each `nous` and `weight`) and `spread`, and `on` (fault to node id, `*` for any other). |
| `nous[].then` | `object\|null` | The graph a turn goes to once its tries are spent, in the same shape, or null for nowhere. |
| `policies` | `list` | The ways of waiting between tries, each `name` and `about`. |
| `default` | `string` | The policy used where none is given. |
| `strategies` | `list` | The ways a balance node picks among its members, each `name` and `about`. |
| `faults` | `list` | Every fault an edge of a graph can be for, and `*` for any other. |
| `concrete` | `list` | Every concrete nous the installed harnesses and the accounts run, without an effort. |
| `scanning` | `boolean` | Whether a scan of the harnesses is going on. |
| `failed` | `list` | The harnesses that would not answer. |
| `failed[].cli` | `string` | The harness. |
| `failed[].account` | `string` | The account it was asked as, empty for the machine's own sign-in. |
| `failed[].why` | `string` | Why it would not answer. |

Daemon methods: `nous.scan`.

### hmz nous set

Writes what is kept of one nous. What is not given stays as it was written. A name with no `/` is a virtual nous and needs `--graph`. A graph is one or more nous tried in turn, or one JSON object of `start` and `nodes` as `hmz nous list --json` prints one.

```text
hmz nous set NAME [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The nous: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` for a concrete one, any other name for a virtual one. |
| `--tries N` | How many more goes a turn that fails there is given. |
| `--policy POLICY` | How long is waited between tries: one of the `policies` of `hmz nous list --json`, such as `exponential-jitter` or `constant`. |
| `--timeout SECONDS` | The limit of a turn in seconds, 0 for no limit. |
| `--graph GRAPH` | What a virtual nous stands for: a nous, or a JSON graph; given more than once, the nous are tried in turn. May be given more than once. |
| `--then GRAPH` | Where a turn goes once its tries are spent: a nous, or a JSON graph; given more than once, the nous are tried in turn. May be given more than once. |
| `--no-then` | Send a turn nowhere once its tries are spent, so that it fails. |

| Example | What it does |
| --- | --- |
| `hmz nous set claude/claude-opus-4-1 --tries 3 --timeout 600` | Give turns on that model three more goes and ten minutes each. |
| `hmz nous set careful --graph claude/claude-opus-4-1 --graph codex/gpt-6-sol --tries 1` | Make the virtual nous `careful`, which tries one model and then the other. |
| `hmz nous set claude/claude-haiku-4-5 --then careful` | Send a turn to `careful` once its tries on that model are spent. |
| `hmz nous set fast --graph '{"start": "a", "nodes": [{"id": "a", "balance": "round-robin", "among": [{"nous": "claude/claude-haiku-4-5", "weight": 1}, {"nous": "codex/gpt-6-luna", "weight": 1}]}]}'` | Make the virtual nous `fast`, which balances turns between two models. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `nous` | `list` | Every nous that has something written of it. |
| `nous[].name` | `string` | The nous: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` for a concrete one, a name for a virtual one. |
| `nous[].virtual` | `boolean` | Whether it is a virtual nous, a name for a graph of other nous. |
| `nous[].tries` | `integer` | How many more goes a turn that fails there is given. |
| `nous[].policy` | `string` | How long is waited between tries, one of `policies`. |
| `nous[].timeout` | `number` | The limit of a turn in seconds, 0 for no limit. |
| `nous[].graph` | `object\|null` | The graph a virtual nous stands for, null for a concrete nous. |
| `nous[].graph.start` | `string` | Id of the node a turn starts at. |
| `nous[].graph.nodes` | `list` | The nodes, each `id`, `use` (a nous) or `balance` (a strategy) with `among` (each `nous` and `weight`) and `spread`, and `on` (fault to node id, `*` for any other). |
| `nous[].then` | `object\|null` | The graph a turn goes to once its tries are spent, in the same shape, or null for nowhere. |
| `policies` | `list` | The ways of waiting between tries, each `name` and `about`. |
| `default` | `string` | The policy used where none is given. |
| `strategies` | `list` | The ways a balance node picks among its members, each `name` and `about`. |
| `faults` | `list` | Every fault an edge of a graph can be for, and `*` for any other. |
| `concrete` | `list` | Every concrete nous the installed harnesses and the accounts run, without an effort. |
| `scanning` | `boolean` | Whether a scan of the harnesses is going on. |

Daemon methods: `nous.list`, `nous.set`.

### hmz nous rename

Gives a virtual nous another name, in every graph that names it too.

```text
hmz nous rename NAME TO
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The virtual nous to rename. |
| `TO` | Its new name. |

| Example | What it does |
| --- | --- |
| `hmz nous rename careful slow` | Rename the virtual nous `careful` to `slow`. |

The line `Renamed`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `nous` | `list` | Every nous that has something written of it. |
| `nous[].name` | `string` | The nous: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` for a concrete one, a name for a virtual one. |
| `nous[].virtual` | `boolean` | Whether it is a virtual nous, a name for a graph of other nous. |
| `nous[].tries` | `integer` | How many more goes a turn that fails there is given. |
| `nous[].policy` | `string` | How long is waited between tries, one of `policies`. |
| `nous[].timeout` | `number` | The limit of a turn in seconds, 0 for no limit. |
| `nous[].graph` | `object\|null` | The graph a virtual nous stands for, null for a concrete nous. |
| `nous[].graph.start` | `string` | Id of the node a turn starts at. |
| `nous[].graph.nodes` | `list` | The nodes, each `id`, `use` (a nous) or `balance` (a strategy) with `among` (each `nous` and `weight`) and `spread`, and `on` (fault to node id, `*` for any other). |
| `nous[].then` | `object\|null` | The graph a turn goes to once its tries are spent, in the same shape, or null for nowhere. |
| `policies` | `list` | The ways of waiting between tries, each `name` and `about`. |
| `default` | `string` | The policy used where none is given. |
| `strategies` | `list` | The ways a balance node picks among its members, each `name` and `about`. |
| `faults` | `list` | Every fault an edge of a graph can be for, and `*` for any other. |
| `concrete` | `list` | Every concrete nous the installed harnesses and the accounts run, without an effort. |
| `scanning` | `boolean` | Whether a scan of the harnesses is going on. |

Daemon methods: `nous.rename`.

### hmz nous clear

Removes the tries, limit and graph written of a nous; a virtual nous is removed whole. A nous that another nous names in its graph is refused.

```text
hmz nous clear NAME
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The nous, as `hmz nous list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz nous clear careful` | Remove the virtual nous `careful`. |

The line `Removed`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `nous` | `list` | Every nous that has something written of it. |
| `nous[].name` | `string` | The nous: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` for a concrete one, a name for a virtual one. |
| `nous[].virtual` | `boolean` | Whether it is a virtual nous, a name for a graph of other nous. |
| `nous[].tries` | `integer` | How many more goes a turn that fails there is given. |
| `nous[].policy` | `string` | How long is waited between tries, one of `policies`. |
| `nous[].timeout` | `number` | The limit of a turn in seconds, 0 for no limit. |
| `nous[].graph` | `object\|null` | The graph a virtual nous stands for, null for a concrete nous. |
| `nous[].graph.start` | `string` | Id of the node a turn starts at. |
| `nous[].graph.nodes` | `list` | The nodes, each `id`, `use` (a nous) or `balance` (a strategy) with `among` (each `nous` and `weight`) and `spread`, and `on` (fault to node id, `*` for any other). |
| `nous[].then` | `object\|null` | The graph a turn goes to once its tries are spent, in the same shape, or null for nowhere. |
| `policies` | `list` | The ways of waiting between tries, each `name` and `about`. |
| `default` | `string` | The policy used where none is given. |
| `strategies` | `list` | The ways a balance node picks among its members, each `name` and `about`. |
| `faults` | `list` | Every fault an edge of a graph can be for, and `*` for any other. |
| `concrete` | `list` | Every concrete nous the installed harnesses and the accounts run, without an effort. |
| `scanning` | `boolean` | Whether a scan of the harnesses is going on. |

Daemon methods: `nous.clear`.

## hmz runs

A daemon writes down every epic it runs. `hmz runs` lists them, reads one back, exports or imports `.hmzepic` files, and totals what epics spent.

```text
hmz runs list [options]
hmz runs show NAME
hmz runs trace NAME
hmz runs timeline NAME [options]
hmz runs span NAME ID [options]
hmz runs export NAME [options]
hmz runs import FILE [options]
hmz runs usage [options]
```

### hmz runs list

List the epics written down, newest first.

```text
hmz runs list [options]
```

| Argument or option | What it is |
| --- | --- |
| `--workspace PATH` | List only the epics of the workspace at this folder path; every workspace when not given. |
| `--status STATUS` | List only the epics with this status. One of `running`, `done`, `failed`, `stopped`, `unfinished`. |
| `--flow NAME` | List only the epics of this flow. |
| `-q, --query TEXT` | List only the epics whose task, flow or name contains this text. |
| `--offset N` | How many of the newest matching epics to skip. |
| `--limit N` | The most epics to list, from 1 to 200. Default `50`. |

| Example | What it does |
| --- | --- |
| `hmz runs list` | Lists the newest 50 epics of every workspace. |
| `hmz runs list --status failed --flow ralph_loop -q parser` | Lists the failed epics of the flow ralph_loop whose task mentions parser. |
| `hmz runs list --json \| jq -r '.runs[].name'` | Lists the epics as JSON and prints their names with jq. |

One line per epic, newest first: name, status, flow, when it began, first line of its task. Where more match than were listed, standard error says so.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `runs` | `list` | The epics listed, newest first. |
| `runs[].name` | `string` | The epic's name. |
| `runs[].workspace` | `string` | Path of the workspace folder the epic ran in. |
| `runs[].folderless` | `boolean` | Whether that workspace has no folder of its own. |
| `runs[].kind` | `string` | Always `flow`. |
| `runs[].flow` | `string` | The flow the epic ran. |
| `runs[].task` | `string` | The first line of the epic's task, cut at 240 characters. |
| `runs[].began` | `string` | When the epic began, ISO 8601. |
| `runs[].ended` | `string` | When the epic ended, ISO 8601, or an empty string while it has not. |
| `runs[].how` | `string` | Its status: `running`, `done`, `failed`, `stopped` or `unfinished`. |
| `runs[].agents` | `list` | The epic's agents, each with `name`, `role` and `runs` (what it was started as). |
| `runs[].sessions` | `integer` | How many sessions the epic opened. |
| `runs[].resumable` | `boolean` | Whether the epic's flow can be resumed. |
| `runs[].spent` | `object\|null` | What the epic spent (cost, tokens, seconds, and each as text), or null where nothing was counted. |
| `runs[].held` | `boolean` | Whether a host of this daemon is running the epic now. |
| `runs[].slot` | `string` | The slot of the host running the epic, or an empty string. |
| `runs[].asking` | `list` | The questions the running epic waits on, each as `&lt;run>:&lt;question>`. |
| `runs[].backup` | `list` | Names of the backup targets the epic was started with. |
| `runs[].backed` | `object` | The last backup to each target, by target name, each with `at`, `ok`, `error` and `why`. |
| `total` | `integer` | How many epics match the filters. |
| `offset` | `integer` | How many matching epics were skipped. |
| `limit` | `integer` | The most epics this answer lists. |
| `counts` | `object` | How many epics there are of each status, over every epic, by status. |
| `flows` | `list` | The name of every flow an epic ran, sorted. |

Daemon methods: `runs.list`.

### hmz runs show

Read back an epic's task, agents, sessions, spend and backups.

```text
hmz runs show NAME
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The epic's name, as `hmz runs list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz runs show 20261012T091500.123Z-1a2b3c` | Prints what was written down of that epic. |
| `hmz runs show NAME --json \| jq .backed` | Prints how the last backup of the epic to each target went. |

Prints one line per field, the field's name and then its value, with the whole task last.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | The epic's name. |
| `workspace` | `string` | Path of the workspace folder the epic ran in. |
| `folderless` | `boolean` | Whether that workspace has no folder of its own. |
| `kind` | `string` | Always `flow`. |
| `flow` | `string` | The flow the epic ran. |
| `task` | `string` | The epic's whole task. |
| `began` | `string` | When the epic began, ISO 8601. |
| `ended` | `string` | When the epic ended, ISO 8601, or an empty string while it has not. |
| `how` | `string` | Its status: `running`, `done`, `failed`, `stopped` or `unfinished`. |
| `agents` | `list` | The epic's agents, each with `name`, `role`, `runs`, `backend`, `model`, `effort` and `provider`. |
| `sessions` | `list` | The sessions the epic opened, each with `agent`, `backend`, `provider`, `ident`, `name`, `at`, `flow`, `parent` and `harness`. |
| `resumable` | `boolean` | Whether the epic's flow can be resumed. |
| `spent` | `object\|null` | What the epic spent (cost, tokens, seconds, and each as text), or null where nothing was counted. |
| `held` | `boolean` | Whether a host of this daemon is running the epic now. |
| `slot` | `string` | The slot of the host running the epic, or an empty string. |
| `asking` | `list` | The questions the running epic waits on, each as `&lt;run>:&lt;question>`. |
| `backup` | `list` | Names of the backup targets the epic was started with. |
| `backed` | `object` | The last backup to each target, by target name, each with `at`, `ok`, `error` and `why`. |
| `at` | `string` | Path of the directory the epic is written down in, on the daemon's machine. |
| `ref` | `string` | The ref the epic's flow was started by. |
| `envs` | `list` | The environments the epic was started with. |
| `used` | `list` | The environments the epic used. |
| `params` | `object` | The params the epic was started with. |
| `budget` | `object\|null` | The budget the epic was started with, or null for none. |
| `picked_up` | `string` | Name of the epic this one resumed from, or an empty string. |
| `profile_flow` | `boolean` | Whether the flow's own Python was profiled. |
| `profile_environment` | `boolean` | Whether the programs its agents ran were profiled. |
| `picks_up` | `boolean` | Whether a new epic can resume from this one. |
| `foreign` | `string` | Why an imported epic cannot be resumed on this machine, or an empty string. |
| `calls` | `list` | The tree of flows the epic called, each with `flow`, `task`, `began`, `ended`, `how` and `calls`. |

Daemon methods: `runs.get`.

### hmz runs trace

Reads the logs the epic's agents kept and prints every action of every harness session: turns, model calls, tool calls, what was said. Slow for a long epic.

```text
hmz runs trace NAME
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The epic's name, as `hmz runs list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz runs trace NAME` | Prints every session of the epic and its actions in order. |
| `hmz runs trace NAME --json \| jq -r '.sessions[].actions[] \| select(.category == "tool") \| .name'` | Prints the name of every tool call of the epic. |

One line per harness session with its key and agent, then an indented line per action: when it started, seconds taken, category, name.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `sessions` | `list` | The sessions that did anything, in the order they started. |
| `sessions[].key` | `string` | The session, as `&lt;harness>:&lt;session id>`. |
| `sessions[].agent` | `string` | The agent the session belongs to. |
| `sessions[].actions` | `list` | What the session did, in order. |
| `sessions[].actions[].category` | `string` | The kind of action, such as `turn`, `llm` or `tool`. |
| `sessions[].actions[].name` | `string` | What the action was: the tool called, the model asked. |
| `sessions[].actions[].at` | `string` | When the action started, ISO 8601. |
| `sessions[].actions[].start` | `number` | When the action started, in seconds on the trace's clock. |
| `sessions[].actions[].seconds` | `number` | How long the action took, in seconds. |
| `sessions[].actions[].args` | `object` | Everything else the action carried, such as its input, its output and its tokens. |

Daemon methods: `runs.trace`.

### hmz runs timeline

Lays the epic out as the Exomyth view draws it: a process for the flow, each harness session and each profiled program, each with tracks of spans.

```text
hmz runs timeline NAME [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The epic's name, as `hmz runs list` prints it. |
| `--spans` | Also print every span under its track, with its id. |

| Example | What it does |
| --- | --- |
| `hmz runs timeline NAME` | Prints the processes and tracks of the epic's timeline. |
| `hmz runs timeline NAME --spans` | Also prints every span with the id `hmz runs span` takes. |
| `hmz runs timeline NAME --json \| jq .summary` | Prints the counts and time of the timeline by category. |

`hmz runs timeline` prints a line per process, and under it a line per track; with `--spans`, it prints each span too.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `version` | `integer` | The version of the timeline document, 1. |
| `layout` | `string` | What identifies this laying out; span ids are good only with it. |
| `epic` | `string` | The epic's name. |
| `origin` | `number` | The earliest moment in the timeline, in seconds since the Unix epoch. |
| `live` | `boolean` | Whether the epic has not ended yet. |
| `strings` | `list` | Every text of the document once; other text fields are indexes into this list. |
| `processes` | `list` | The processes, each with `id`, `kind`, `name`, `label`, `start`, `end`, `parent` and `tracks`; times are microseconds from `origin`. |
| `tracks` | `list` | The tracks, each with `process`, `name`, `first`, `count`, `depths` and `spans`, the columns of its spans; a span's id is `first` plus its index. |
| `spawns` | `object` | Which span started which process, as two columns `span` and `process`. |
| `summary` | `object` | Start and end, process, track and span counts, and count, time and tokens by category. |

Daemon methods: `runs.timeline`.

### hmz runs span

Prints one span whole: a model call with its prompt and answer, a tool call with its input and output. Without `--layout`, the timeline is laid out first.

```text
hmz runs span NAME ID [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The epic's name, as `hmz runs list` prints it. |
| `ID` | The span's id, as `hmz runs timeline --spans` prints it. |
| `--layout LAYOUT` | The `layout` of the timeline the id was read from; refused if the epic has been laid out again since. |

| Example | What it does |
| --- | --- |
| `hmz runs span NAME 42` | Prints span 42 of the epic's timeline as it is laid out now. |
| `hmz runs span NAME 42 --layout a1ed23f784909965 --json` | Prints span 42 as JSON, only if the timeline is still laid out as when the id was read. |

One line per field of the span, the field's name and then its value, and what it carried as indented JSON.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `id` | `integer` | The span's id. |
| `process` | `integer` | Id of the process the span belongs to. |
| `track` | `integer` | Index of the track the span is on. |
| `start` | `integer` | When the span started, in microseconds from the timeline's origin. |
| `dur` | `integer` | How long the span lasted, in microseconds. |
| `depth` | `integer` | How deeply the span is nested on its track. |
| `cat` | `string` | The span's category, such as `turn`, `llm` or `tool`. |
| `name` | `string` | The span's name. |
| `at` | `string` | When the span started, ISO 8601 UTC. |
| `args` | `object` | Everything the span carried, such as its input, its output and its tokens. |

Daemon methods: `runs.timeline`, `runs.span`.

### hmz runs export

The daemon packs the epic into one `.hmzepic` archive, credentials struck out, written on the machine this command runs on. `hmz runs import` reads it back.

```text
hmz runs export NAME [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | The epic's name, as `hmz runs list` prints it. |
| `-o, --output FILE` | The file to write, or a directory to write it into; `&lt;name>.hmzepic` in the current directory when not given; an existing file is replaced. |

| Example | What it does |
| --- | --- |
| `hmz runs export NAME` | Writes NAME.hmzepic in the current directory. |
| `hmz runs export NAME -o ~/epics/` | Writes the archive into the directory ~/epics. |

Prints the path of the file written.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `path` | `string` | Absolute path of the file written. |
| `filename` | `string` | The name the daemon gave the archive, `&lt;name>.hmzepic`. |
| `size` | `integer` | The archive's size in bytes. |

Daemon methods: `runs.bundle`, `files.read`, `files.close`.

### hmz runs import

Sends the file to the daemon, which writes the epic down under the workspace it ran in. An epic already there is refused.

```text
hmz runs import FILE [options]
```

| Argument or option | What it is |
| --- | --- |
| `FILE` | The `.hmzepic` file to import; with `--there`, its absolute path on the daemon's machine. |
| `--there` | Have the daemon read the file from that path on its own machine rather than sending it. |

| Example | What it does |
| --- | --- |
| `hmz runs import NAME.hmzepic` | Sends the file to the daemon and imports the epic. |
| `hmz runs import /srv/epics/NAME.hmzepic --there --daemon lab` | Has the daemon `lab` import a file already on its own machine. |

Prints the imported epic's name, and why it cannot be resumed here when it cannot.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | Name of the imported epic. |
| `workspace` | `string` | Path of the workspace folder the epic is kept under. |
| `resumable` | `boolean` | Whether the imported epic can be resumed on this daemon. |
| `why` | `string` | Why it cannot be resumed here, or an empty string. |

Daemon methods: `files.create`, `files.write`, `files.close`, `runs.import`.

### hmz runs usage

Total what chats and epics spent, by flow and by day.

```text
hmz runs usage [options]
```

| Argument or option | What it is |
| --- | --- |
| `--days N` | How many days back to count, today included, from 1 to 365. Default `30`. |
| `--workspace PATH` | Count only the chats and epics of the workspace at this folder. |

| Example | What it does |
| --- | --- |
| `hmz runs usage` | Totals what the last 30 days of chats and epics spent. |
| `hmz runs usage --days 7 --workspace . --json \| jq .whole.cost` | Prints the dollars this workspace spent in the last seven days. |

A table of flows, costliest first, a table of the days something ran, then the total: epics, cost, output tokens, time working. Chats count as the flow `chat`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `days_back` | `integer` | How many days were counted. |
| `days` | `list` | One entry per UTC day, oldest first, each with `day` and the figures of `whole`. |
| `flows` | `list` | One entry per flow, costliest first, each with `flow` and the figures of `whole`. |
| `ended` | `object` | How many chats and epics ended each way, by status. |
| `whole` | `object` | The totals over everything counted. |
| `whole.runs` | `integer` | How many chats and epics were counted. |
| `whole.cost` | `number` | What they cost, in US dollars. |
| `whole.output_tokens` | `integer` | How many output tokens they wrote. |
| `whole.seconds` | `number` | How many seconds their agents worked. |
| `whole.money` | `string` | The cost as text, such as `$1.25`. |
| `whole.tokens` | `string` | The output tokens as text, such as `12.5k`. |
| `whole.worked` | `string` | The time working as text, such as `3m 20s`. |

Daemon methods: `runs.usage`.

## hmz runtimes

A runtime is a machine an environment runs on, other than the daemon's own. `-e` of `hmz exec` and `hmz chat` names it as `&lt;backend>@&lt;name>`.

```text
hmz runtimes list
hmz runtimes show BACKEND [NAME]
hmz runtimes set BACKEND NAME [options]
hmz runtimes remove BACKEND NAME
hmz runtimes check BACKEND NAME
hmz runtimes hosts
hmz runtimes import [HOST...] [options]
```

### hmz runtimes list

List the runtimes, and this machine.

```text
hmz runtimes list
```

| Example | What it does |
| --- | --- |
| `hmz runtimes list` | List the runtimes. |
| `hmz runtimes list --json \| jq '.blanks.ssh'` | Print every field an ssh runtime has, with its default. |

A first line for the daemon's own machine (`local` and its host name), then one line per runtime: backend, name, and how it was made.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `local` | `object` | The daemon's own machine, where work runs that names no runtime: host, system, machine, cpus, and memory in bytes. |
| `runtimes` | `list` | Every runtime written down after this command, in the daemon's order. |
| `runtimes[].backend` | `string` | The runtime's backend: ssh, docker, swarm, apple-container or slurm. |
| `runtimes[].name` | `string` | The name the runtime is written down under. |
| `runtimes[].made` | `string` | How the runtime came to be written down: `typed`, or `imported` from the SSH config. |
| `runtimes[].fields` | `object` | The runtime's other fields by name, as `--set` takes them. |
| `blanks` | `object` | For each backend, every field a runtime of it has, with the value the field has when it is not set. |

Daemon methods: `runtimes.list`.

### hmz runtimes show

Prints one runtime's fields as lines `field=value`, the form `--set` takes. Without NAME, prints the fields a new runtime of the backend starts with.

```text
hmz runtimes show BACKEND [NAME]
```

| Argument or option | What it is |
| --- | --- |
| `BACKEND` | What kind of runtime it is: `ssh`, `docker`, `swarm`, `apple-container` or `slurm`. |
| `NAME` | The runtime to print; left out, the fields a new runtime of the backend starts with. |

| Example | What it does |
| --- | --- |
| `hmz runtimes show ssh gpu-box` | Print the fields of the ssh runtime `gpu-box`. |
| `hmz runtimes show docker` | Print every field a docker runtime takes, with its default. |

One line per field, `field=value`; a list or a mapping is written as JSON.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `backend` | `string` | The runtime's backend: ssh, docker, swarm, apple-container or slurm. |
| `name` | `string\|null` | The runtime's name, or null where only a backend was named. |
| `made` | `string\|null` | How the runtime was made, `typed` or `imported`, or null where only a backend was named. |
| `fields` | `object` | Every field of the runtime by name, the ones it does not set at their defaults. |

Daemon methods: `runtimes.list`.

### hmz runtimes set

Writes a runtime down. A name already written is refused unless `--replace` is given, which changes it and keeps the fields this line does not set.

```text
hmz runtimes set BACKEND NAME [options]
```

| Argument or option | What it is |
| --- | --- |
| `BACKEND` | What kind of runtime it is: `ssh`, `docker`, `swarm`, `apple-container` or `slurm`. |
| `NAME` | The name the runtime is written down under, as `hmz runtimes list` prints it. |
| `--set FIELD=VALUE` | One field of the runtime, as `hmz runtimes show BACKEND` lists them; repeat for each list item, and write `FIELD=KEY=VALUE` for each pair of a mapping. May be given more than once. |
| `--replace` | Change the runtime already written under this backend and name, keeping the fields this line does not set. |

| Example | What it does |
| --- | --- |
| `hmz runtimes set ssh gpu-box --set host=10.0.0.7 --set user=me --set port=2222` | Add the ssh host 10.0.0.7 as the runtime `gpu-box`, logging in as `me` on port 2222. |
| `hmz runtimes set docker lab --set endpoint=ssh:gpu-box --set image=ubuntu:24.04 --set gpus=0 --set gpus=1` | Add a docker runtime `lab` on the daemon reached through the ssh runtime `gpu-box`, with a default image and GPUs 0 and 1. |
| `hmz runtimes set ssh gpu-box --replace --set options=Compression=yes` | Change `gpu-box` to pass ssh the option `Compression=yes`, keeping its other fields. |
| `hmz runtimes set slurm cluster --set partition=gpu --set account=lab --set time=04:00:00` | Add a Slurm runtime `cluster` on partition `gpu`, account `lab`, with a four-hour time limit. |
| `hmz runtimes set docker lab --replace --set gpus= --set 'run_args=["--shm-size", "8g"]'` | Change the docker runtime `lab`: clear its GPUs and give its run arguments as a JSON array. |

The one word `Saved`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `runtimes` | `list` | Every runtime written down after this command, in the daemon's order. |
| `runtimes[].backend` | `string` | The runtime's backend: ssh, docker, swarm, apple-container or slurm. |
| `runtimes[].name` | `string` | The name the runtime is written down under. |
| `runtimes[].made` | `string` | How the runtime came to be written down: `typed`, or `imported` from the SSH config. |
| `runtimes[].fields` | `object` | The runtime's other fields by name, as `--set` takes them. |

Daemon methods: `runtimes.list`, `runtimes.set`.

### hmz runtimes remove

Remove one runtime.

```text
hmz runtimes remove BACKEND NAME
```

| Argument or option | What it is |
| --- | --- |
| `BACKEND` | What kind of runtime it is: `ssh`, `docker`, `swarm`, `apple-container` or `slurm`. |
| `NAME` | The name the runtime is written down under, as `hmz runtimes list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz runtimes remove ssh gpu-box` | Remove the ssh runtime `gpu-box`. |

The one word `Removed`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `runtimes` | `list` | Every runtime written down after this command, in the daemon's order. |
| `runtimes[].backend` | `string` | The runtime's backend: ssh, docker, swarm, apple-container or slurm. |
| `runtimes[].name` | `string` | The name the runtime is written down under. |
| `runtimes[].made` | `string` | How the runtime came to be written down: `typed`, or `imported` from the SSH config. |
| `runtimes[].fields` | `object` | The runtime's other fields by name, as `--set` takes them. |

Daemon methods: `runtimes.remove`.

### hmz runtimes check

Reaches the runtime the way an environment put on it would, and prints what it has: CPUs, memory, GPUs, version, and what it is short of.

```text
hmz runtimes check BACKEND NAME
```

| Argument or option | What it is |
| --- | --- |
| `BACKEND` | What kind of runtime it is: `ssh`, `docker`, `swarm`, `apple-container` or `slurm`. |
| `NAME` | The name the runtime is written down under, as `hmz runtimes list` prints it. |

| Example | What it does |
| --- | --- |
| `hmz runtimes check ssh gpu-box` | Check that the ssh runtime `gpu-box` answers, and print what it has. |
| `hmz runtimes check docker lab --json \| jq .gpus` | Print the GPUs the docker runtime `lab` reports. |

One line per field of the answer: the field's name, then its value.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `reached` | `boolean` | Whether the runtime answered at all. |
| `said` | `string` | Why it did not answer, in its own words; empty where it did. |
| `home` | `string` | The home directory of the login, for an ssh host. |
| `cpus` | `number` | How many CPUs it has. |
| `memory` | `integer` | Its memory in bytes. |
| `gpus` | `list` | Its GPUs, by device id. |
| `usable` | `list\|null` | The GPUs that answer, for a docker daemon whose host could be asked; null where it could not. |
| `gpu_memory` | `integer` | The memory of its smallest GPU in bytes, or 0 where unknown. |
| `runtimes` | `list` | The OCI runtimes a docker daemon offers, its default first. |
| `version` | `string` | The version of the docker daemon, of Apple's container system, or of Slurm. |
| `short` | `list` | What the runtime was written down as handing out that it has not got. |
| `nodes` | `list` | The host names of a swarm's or a Slurm partition's nodes that can be given work. |

| Status | Meaning |
| --- | --- |
| `4` | The runtime did not answer; its reason is in `said`. |

Daemon methods: `runtimes.check`.

### hmz runtimes hosts

List the hosts of the SSH config on the daemon's machine.

```text
hmz runtimes hosts
```

| Example | What it does |
| --- | --- |
| `hmz runtimes hosts` | List the hosts of the SSH config. |
| `hmz runtimes hosts --json \| jq -r '.hosts[] \| select(.saved \| not) \| .alias'` | Print the hosts of the SSH config not yet saved as runtimes. |

One line per host: its alias, the machine it reaches, user, port, and `Saved` where an ssh runtime of its name is written down.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `hosts` | `list` | Every Host of ~/.ssh/config on the daemon's machine, as ssh resolves it. |
| `hosts[].alias` | `string` | The name the SSH config gives the host. |
| `hosts[].host` | `string` | The machine it reaches (HostName). |
| `hosts[].user` | `string` | The user it logs in as. |
| `hosts[].port` | `integer` | The port it dials. |
| `hosts[].identity_files` | `list` | The key files the SSH config names for it; empty where ssh picks its own. |
| `hosts[].proxy_jump` | `string` | The host it is reached through, or empty. |
| `hosts[].saved` | `boolean` | Whether an ssh runtime of that name is already written down. |

Daemon methods: `runtimes.hosts`.

### hmz runtimes import

Import hosts from the SSH config as ssh runtimes.

```text
hmz runtimes import [HOST...] [options]
```

| Argument or option | What it is |
| --- | --- |
| `HOST` | The hosts to import, each by its Host in the SSH config, as `hmz runtimes hosts` prints it. |
| `--update` | Write a runtime imported before again, as its host stands in the SSH config now. |

| Example | What it does |
| --- | --- |
| `hmz runtimes import gpu-box build-box` | Import the hosts `gpu-box` and `build-box` of the SSH config as ssh runtimes. |
| `hmz runtimes import gpu-box --update` | Bring the runtime imported from `gpu-box` up to date with the SSH config. |

The one word `Imported`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `runtimes` | `list` | Every runtime written down after this command, in the daemon's order. |
| `runtimes[].backend` | `string` | The runtime's backend: ssh, docker, swarm, apple-container or slurm. |
| `runtimes[].name` | `string` | The name the runtime is written down under. |
| `runtimes[].made` | `string` | How the runtime came to be written down: `typed`, or `imported` from the SSH config. |
| `runtimes[].fields` | `object` | The runtime's other fields by name, as `--set` takes them. |

Daemon methods: `runtimes.import`.

## hmz settings

The settings a daemon keeps for its machine (details, error reports, harness sessions, what `$NAME` means in a chat, backup targets, listeners, STUN and TURN servers) and for one workspace (its chat agent and the flows set up there).

```text
hmz settings get [KEY] [options]
hmz settings set details VALUE
hmz settings set reports VALUE
hmz settings set harness_sessions VALUE
hmz settings set chat AGENT [options]
hmz settings set prefer VALUE
hmz settings set listen [SPEC...]
hmz settings set ice_servers [SERVER...]
hmz settings set backup VALUE
hmz settings set backup.target NAME [options]
hmz settings set backup.defaults [NAME...]
hmz settings forget --workspace PATH
```

### hmz settings get

Print the settings, or one of them.

```text
hmz settings get [KEY] [options]
```

| Argument or option | What it is |
| --- | --- |
| `KEY` | The one setting to print, a field of the JSON document such as `details` or `backup`; every setting where not given. |
| `-w, --workspace PATH` | The workspace folder, as a path; the home folder where not given. |

| Example | What it does |
| --- | --- |
| `hmz settings get` | Print every setting of this machine and of the home folder. |
| `hmz settings get chat -w ~/project` | Print the chat agent remembered for the workspace `~/project`. |
| `hmz settings get backup --json \| jq -r '.backup.targets[].name'` | Print the names of the backup targets with jq. |

One line per setting: its name and its value, text as it is and anything else as JSON. With KEY, the value alone.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.get`.

### hmz settings set details

Show or hide tool calls and thinking.

```text
hmz settings set details VALUE
```

| Argument or option | What it is |
| --- | --- |
| `VALUE` | `on` or `off`; `true` and `false` are taken too. One of `on`, `true`, `off`, `false`. |

| Example | What it does |
| --- | --- |
| `hmz settings set details on` | Show tool calls and thinking. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.set`.

### hmz settings set reports

Whether Humanize sends a report of its own crashes. Nothing anybody typed, no file and no credential is ever sent.

```text
hmz settings set reports VALUE
```

| Argument or option | What it is |
| --- | --- |
| `VALUE` | `on` or `off`; `true` and `false` are taken too. One of `on`, `true`, `off`, `false`. |

| Example | What it does |
| --- | --- |
| `hmz settings set reports off` | Stop Humanize reporting its own failures. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.set`.

### hmz settings set harness_sessions

The sessions each harness had of its own in a folder, which Humanize did not run, listed after its chats. They are only read: continuing one copies it into a chat, and the harness’s own files are never changed.

```text
hmz settings set harness_sessions VALUE
```

| Argument or option | What it is |
| --- | --- |
| `VALUE` | `on` or `off`; `true` and `false` are taken too. One of `on`, `true`, `off`, `false`. |

| Example | What it does |
| --- | --- |
| `hmz settings set harness_sessions on` | List harness sessions after the chats of a folder. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.set`.

### hmz settings set chat

Set the chat agent remembered for a workspace.

```text
hmz settings set chat AGENT [options]
```

| Argument or option | What it is |
| --- | --- |
| `AGENT` | The agent, as `-a` spells one: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` or the name of a nous. |
| `-w, --workspace PATH` | The workspace folder, as a path; the home folder where not given. |

| Example | What it does |
| --- | --- |
| `hmz settings set chat claude/claude-opus-4-1` | Make new chats in the home folder start with that agent. |
| `hmz settings set chat codex@work/gpt-6-sol:high -w ~/project` | Set the chat agent of the workspace `~/project`, with an account and an effort. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.set`.

### hmz settings set prefer

Sets the preference of every chat of this machine: whether `$NAME` typed in a chat runs the harness's own skill of that name or the flow of that name, where both exist. One chat can override it with `/prefer`.

```text
hmz settings set prefer VALUE
```

| Argument or option | What it is |
| --- | --- |
| `VALUE` | `native` for the harness's own skill, `flow` for the flow. One of `native`, `flow`. |

| Example | What it does |
| --- | --- |
| `hmz settings set prefer flow` | Make `$NAME` in a chat run the flow where a skill has the same name. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.set`.

### hmz settings set listen

Writes every listener the daemon opens, replacing the ones written; listeners open and close at once. Give none to listen nowhere.

```text
hmz settings set listen [SPEC...]
```

| Argument or option | What it is |
| --- | --- |
| `SPEC` | A listener spec such as `tcp://0.0.0.0:7000`, `ws://0.0.0.0:7001`, `relay:URL`, `webrtc:URL` or `easytier:NAME`; or one JSON list of them. |

| Example | What it does |
| --- | --- |
| `hmz settings set listen tcp://0.0.0.0:7000 ws://0.0.0.0:7001` | Listen on a TCP port and a WebSocket port. |
| `hmz settings set listen` | Close every listener. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.set`.

### hmz settings set ice_servers

Writes every STUN and TURN server, replacing the ones written. They are only used where this daemon is reached over a `webrtc:` route. A TURN server's credential is read from JSON on standard input, never from the command line; `"credential": true` keeps the one written.

```text
hmz settings set ice_servers [SERVER...]
```

| Argument or option | What it is |
| --- | --- |
| `SERVER` | A server's URL such as `stun:stun.example.org:3478`, a JSON object of `urls`, `username` and `credential`, one JSON list of them, or `-` to read that list from standard input. |

| Example | What it does |
| --- | --- |
| `hmz settings set ice_servers stun:stun.example.org:3478` | Use one STUN server. |
| `hmz settings set ice_servers - &lt; servers.json` | Read the servers, credentials included, from a JSON file. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.set`.

### hmz settings set backup

Writes the whole `backup` setting, replacing every target and the defaults. A target whose `url` is the one `hmz settings get backup` printed keeps the URL written, credentials included.

```text
hmz settings set backup VALUE
```

| Argument or option | What it is |
| --- | --- |
| `VALUE` | A JSON object of `targets` and `defaults`, as `hmz settings get backup --json` prints under `backup`; `-` reads it from standard input. |

| Example | What it does |
| --- | --- |
| `hmz settings set backup '{"targets": [], "defaults": []}'` | Remove every backup target. |
| `hmz settings set backup - &lt; backup.json` | Write the backup targets from a JSON file. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.set`.

### hmz settings set backup.target

Adds a backup target, or changes the one of that name; what is not given stays as it was, and a new target starts on the branch `main`, backed up by hand only. The other targets are kept.

```text
hmz settings set backup.target NAME [options]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | Name of the backup target. |
| `--url URL` | The git repository, as a URL git pushes to; needed for a new target. |
| `--branch BRANCH` | The branch pushed to. |
| `--policy POLICY` | When it is backed up to unasked: `session` on session close, `interval` every N minutes, `end` on epic end, or `manual` for by hand only. One of `session`, `interval`, `end`, `manual`. May be given more than once. |
| `--every N` | Minutes between backups under the `interval` policy. |
| `--default` | Back new epics up to it unless they say otherwise. |
| `--no-default` | Stop backing new epics up to it by default. |
| `--remove` | Remove the target instead. |

| Example | What it does |
| --- | --- |
| `hmz settings set backup.target lab --url git@github.com:you/epics.git --policy session --policy end --default` | Add the target `lab`, backed up to on session close and on epic end, as a default. |
| `hmz settings set backup.target lab --policy interval --every 30` | Back `lab` up every 30 minutes instead. |
| `hmz settings set backup.target lab --remove` | Remove the target `lab`. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.get`, `settings.set`.

### hmz settings set backup.defaults

Set the backup targets a new epic goes to.

```text
hmz settings set backup.defaults [NAME...]
```

| Argument or option | What it is |
| --- | --- |
| `NAME` | Name of a backup target; none given means a new epic is backed up nowhere by default. |

| Example | What it does |
| --- | --- |
| `hmz settings set backup.defaults lab` | Back new epics up to the target `lab`. |
| `hmz settings set backup.defaults` | Back new epics up to no target by default. |

The line `Saved.`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.get`, `settings.set`.

### hmz settings forget

Forgets the flow a workspace opens on and how every flow was set up there. Where no epic ran there, the workspace also stops being offered.

```text
hmz settings forget --workspace PATH
```

| Argument or option | What it is |
| --- | --- |
| `-w, --workspace PATH` | The workspace folder, as a path. |

| Example | What it does |
| --- | --- |
| `hmz settings forget -w ~/project` | Forget how the flows of `~/project` were set up. |

`Forgotten.`, or `Nothing to forget.` where nothing was set up there.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `forgot` | `boolean` | Whether there was anything to forget. |
| `workspace` | `string` | The workspace these settings are of, the home folder where none was named. |
| `flow` | `string` | The flow the workspace was last set up to run, or empty. |
| `flows` | `list` | Names of the flows set up in the workspace. |
| `chat` | `string` | The chat agent remembered for the workspace, as `-a` spells one, or empty. |
| `prefer` | `string` | What `$NAME` in a chat means where it names both a native skill and a flow: `native` or `flow`. |
| `ai_chan` | `string` | The nous the last Ai-chan conversation was made with, or empty. |
| `details` | `boolean` | Whether tool calls and thinking are shown. |
| `harness_sessions` | `boolean` | Whether harness sessions are listed in the sidebar. |
| `reports` | `boolean\|null` | Whether Humanize reports its own failures, or null if never answered. |
| `backup` | `object` | The backup targets and the defaults. |
| `backup.targets` | `list` | The git repositories epics are backed up to. |
| `backup.targets[].name` | `string` | Name of the backup target. |
| `backup.targets[].url` | `string` | URL of the repository, with its credentials removed. |
| `backup.targets[].branch` | `string` | The branch pushed to. |
| `backup.targets[].policies` | `list` | When it is backed up to unasked: any of `session`, `interval`, `end`; empty means by hand only. |
| `backup.targets[].every` | `integer` | Minutes between backups under the `interval` policy. |
| `backup.defaults` | `list` | Names of the targets a new epic is backed up to. |
| `listen` | `list` | The listener specs the daemon opens. |
| `ice_servers` | `list` | The STUN and TURN servers. |
| `ice_servers[].urls` | `string\|list` | URL or URLs of the server. |
| `ice_servers[].username` | `string` | Username of a TURN server, where it has one. |
| `ice_servers[].credential` | `boolean` | `true` where a credential is kept; its value is never printed. |

Daemon methods: `settings.forget`.

## hmz skills

The hmz skill is a `SKILL.md` telling a harness how to use the `hmz` command line. `hmz` installs no other skill and changes none of yours.

```text
hmz skills add [options]
hmz skills list [options]
hmz skills remove [options]
hmz skills show
```

### hmz skills add

Writes the folder `hmz` into the user-level skills folder of every installed harness, or those named. Running it again replaces it, unless `hmz` did not write it.

```text
hmz skills add [options]
```

| Argument or option | What it is |
| --- | --- |
| `--for HARNESS` | Install for this harness only, by the name `hmz skills list` prints (such as claude or codex), whether or not it is installed. May be given more than once. |
| `--dir PATH` | A skills folder to use instead of any harness's own; the skill is the folder `hmz` inside it. |

Asks no daemon, and takes no `--daemon`.

| Example | What it does |
| --- | --- |
| `hmz skills add` | Install the skill for every harness installed on this machine. |
| `hmz skills add --for claude --for codex` | Install the skill for Claude Code and Codex only. |
| `hmz skills add --dir ~/.agents/skills` | Install the skill into the skills folder several harnesses share. |

One line per skill written, naming the harness and the path of its `SKILL.md`.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `version` | `string` | The version of hmz the skill is written by. |
| `written` | `list` | The skills written, one per folder. |
| `written[].harness` | `string\|null` | The harness whose own skills folder it is, or null for any other folder (one given with `--dir`, or one several harnesses share). |
| `written[].path` | `string` | The path of the `SKILL.md` written. |
| `written[].changed` | `boolean` | Whether the file was written, false where it already held the same text. |

### hmz skills list

Show each harness's skills folder and the hmz skill's state.

```text
hmz skills list [options]
```

| Argument or option | What it is |
| --- | --- |
| `--for HARNESS` | Only this harness, by the name `hmz skills list` prints. May be given more than once. |
| `--dir PATH` | A skills folder to use instead of any harness's own; the skill is the folder `hmz` inside it. |

Asks no daemon, and takes no `--daemon`.

| Example | What it does |
| --- | --- |
| `hmz skills list` | Show where each harness keeps its skills and whether the hmz skill is there. |
| `hmz skills list --json \| jq -r '.harnesses[] \| select(.state == "older") \| .harness'` | Print the harnesses whose hmz skill was written by another version of hmz. |

One line per harness: its name, its user-level skills folder, and whether the hmz skill there is current, older, not installed, or not written by hmz.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `version` | `string` | The version of hmz the skill is written by. |
| `harnesses` | `list` | Every harness that has a user-level skills folder. |
| `harnesses[].harness` | `string\|null` | The harness's name, as `--for` takes it, or null for a folder that is not one harness's own (one given with `--dir`, or one several harnesses share). |
| `harnesses[].installed` | `boolean` | Whether the harness itself is installed on this machine. |
| `harnesses[].directory` | `string` | The harness's user-level skills folder. |
| `harnesses[].path` | `string` | Where the hmz skill's `SKILL.md` is, or would be written. |
| `harnesses[].state` | `string` | One of `current` (written by this version of hmz), `older` (written by another version), `absent` (not installed), or `foreign` (a skill named hmz that hmz did not write). |
| `harnesses[].version` | `string\|null` | The version of hmz that wrote the installed skill, or null where there is none. |

### hmz skills remove

Removes the hmz skill wherever `hmz skills add` wrote it, or from the harnesses named. Asks first unless `--yes` is given. Never removes a skill `hmz` did not write.

```text
hmz skills remove [options]
```

| Argument or option | What it is |
| --- | --- |
| `--for HARNESS` | Only this harness, by the name `hmz skills list` prints. May be given more than once. |
| `--dir PATH` | A skills folder to use instead of any harness's own; the skill is the folder `hmz` inside it. |
| `-y, --yes` | Do it without asking first. |

Asks no daemon, and takes no `--daemon`.

| Example | What it does |
| --- | --- |
| `hmz skills remove` | Remove the hmz skill from every harness, asking first. |
| `hmz skills remove --for codex --yes` | Remove the hmz skill from Codex without asking. |

One line per skill removed, with its path.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `removed` | `list` | The skills removed. |
| `removed[].harness` | `string\|null` | The harness whose own skills folder it is, or null for any other folder (one given with `--dir`, or one several harnesses share). |
| `removed[].path` | `string` | The path of the `SKILL.md` removed. |

### hmz skills show

Print the `SKILL.md` that `hmz skills add` would write.

```text
hmz skills show
```

Asks no daemon, and takes no `--daemon`.

| Example | What it does |
| --- | --- |
| `hmz skills show` | Print the skill without installing it. |
| `hmz skills show --json \| jq -r '.files[].name'` | Print the names of the files the skill is made of. |

The text of `SKILL.md` as it would be written.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `name` | `string` | The skill's name, which is `hmz`. |
| `version` | `string` | The version of hmz the skill is written by. |
| `files` | `list` | The files the skill is made of, `SKILL.md` first. |
| `files[].name` | `string` | The file's name inside the skill's folder. |
| `files[].text` | `string` | The file's whole text. |

## hmz workspaces

A workspace is a folder on the daemon's machine that epics run in and chats belong to. These commands list the workspaces, add a folder as one, forget one, and browse or complete folder paths on the daemon's machine to choose one.

```text
hmz workspaces list
hmz workspaces add PATH
hmz workspaces forget PATH
hmz workspaces browse [PATH] [options]
hmz workspaces complete TYPED
```

### hmz workspaces list

List the workspaces.

```text
hmz workspaces list
```

| Example | What it does |
| --- | --- |
| `hmz workspaces list` | List the workspaces. |
| `hmz workspaces list --json \| jq -r '.workspaces[] \| select(.running) \| .path'` | Print the paths of the workspaces with an epic running, with jq. |

One line per workspace: its path, how many epics and how many chats it has, when the latest began, and whether it is running or its folder is missing; the current directory comes first, then the running ones, then the most recent.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `here` | `string` | The absolute path of the directory the command was run in. |
| `workspaces` | `list` | The workspaces. |
| `workspaces[].path` | `string` | The absolute path of the folder. |
| `workspaces[].name` | `string` | The name of the folder. |
| `workspaces[].epics` | `integer` | How many epics ran there. |
| `workspaces[].chats` | `integer` | How many chats it has. |
| `workspaces[].last` | `string` | When its latest epic or chat began, ISO 8601, or empty. |
| `workspaces[].running` | `boolean` | Whether an epic or chat is running there. |
| `workspaces[].here` | `boolean` | Whether it is the directory the command was run in. |
| `workspaces[].there` | `boolean` | Whether the folder still exists. |

Daemon methods: `workspaces.list`.

### hmz workspaces add

Add a folder on the daemon's machine as a workspace.

```text
hmz workspaces add PATH
```

| Argument or option | What it is |
| --- | --- |
| `PATH` | The folder, which must exist on the daemon's machine; a relative path is taken from the current directory. |

| Example | What it does |
| --- | --- |
| `hmz workspaces add .` | Add the current directory as a workspace. |
| `hmz workspaces add ~/code/app --json \| jq -r .kept` | Add the folder ~/code/app as a workspace and print its absolute path as JSON. |

The absolute path of the workspace added.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `kept` | `string` | The absolute path of the workspace added. |
| `here` | `string` | The absolute path of the directory the command was run in. |
| `workspaces` | `list` | The workspaces. |
| `workspaces[].path` | `string` | The absolute path of the folder. |
| `workspaces[].name` | `string` | The name of the folder. |
| `workspaces[].epics` | `integer` | How many epics ran there. |
| `workspaces[].chats` | `integer` | How many chats it has. |
| `workspaces[].last` | `string` | When its latest epic or chat began, ISO 8601, or empty. |
| `workspaces[].running` | `boolean` | Whether an epic or chat is running there. |
| `workspaces[].here` | `boolean` | Whether it is the directory the command was run in. |
| `workspaces[].there` | `boolean` | Whether the folder still exists. |

Daemon methods: `workspaces.add`.

### hmz workspaces forget

Forgets the settings kept for a workspace, the set-up of each flow included. A workspace nothing ran in leaves the list; its folder, epics and chats are not touched.

```text
hmz workspaces forget PATH
```

| Argument or option | What it is |
| --- | --- |
| `PATH` | The workspace, as `hmz workspaces list` prints it; the folder need not exist any more. |

| Example | What it does |
| --- | --- |
| `hmz workspaces forget ~/code/old` | Forget the workspace ~/code/old. |
| `hmz workspaces forget . --json` | Forget the current directory's set-up and print the workspaces left as JSON. |

One word saying it was forgotten.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `here` | `string` | The absolute path of the directory the command was run in. |
| `workspaces` | `list` | The workspaces. |
| `workspaces[].path` | `string` | The absolute path of the folder. |
| `workspaces[].name` | `string` | The name of the folder. |
| `workspaces[].epics` | `integer` | How many epics ran there. |
| `workspaces[].chats` | `integer` | How many chats it has. |
| `workspaces[].last` | `string` | When its latest epic or chat began, ISO 8601, or empty. |
| `workspaces[].running` | `boolean` | Whether an epic or chat is running there. |
| `workspaces[].here` | `boolean` | Whether it is the directory the command was run in. |
| `workspaces[].there` | `boolean` | Whether the folder still exists. |

Daemon methods: `workspaces.forget`.

### hmz workspaces browse

Lists one directory of the machine the daemon runs on, to find the folder to give `hmz workspaces add` or `-w`. With `--env`, lists a directory of the machine a runtime is on.

```text
hmz workspaces browse [PATH] [options]
```

| Argument or option | What it is |
| --- | --- |
| `PATH` | The directory to list, `~` being the home directory there; the home directory when not given. Default `~`. |
| `--files` | List files as well as folders. |
| `--hidden` | List names that start with a dot as well. |
| `--env ENV` | List the directory on the machine of a runtime, written as `-e` writes one with no directory, for example `ssh@NAME`. |

| Example | What it does |
| --- | --- |
| `hmz workspaces browse` | List the folders in the home directory of the daemon's machine. |
| `hmz workspaces browse ~/code --files --hidden` | List the folders and files in ~/code, hidden ones included. |
| `hmz workspaces browse /srv --env ssh@box` | List the folders in /srv on the machine of the ssh runtime `box`. |

One absolute path per line, folders first and ending in `/`; at most 500, and how many were left out on standard error.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `at` | `string` | The folder listed, written from `~` where it is under the home directory. |
| `whole` | `string` | Its absolute path. |
| `up` | `string` | Its parent folder, or empty at the root. |
| `entries` | `list` | What is in it, folders first, at most 500. |
| `entries[].name` | `string` | The name of the entry. |
| `entries[].dir` | `boolean` | Whether the entry is a folder. |
| `more` | `integer` | How many entries were left out. |

Daemon methods: `paths.list`.

### hmz workspaces complete

Complete a partly typed folder path on the daemon's machine.

```text
hmz workspaces complete TYPED
```

| Argument or option | What it is |
| --- | --- |
| `TYPED` | The start of a path, as far as it has been typed, such as `~/co`. |

| Example | What it does |
| --- | --- |
| `hmz workspaces complete '~/co'` | List the folders whose path starts with `~/co`. |
| `hmz workspaces complete /srv/ --json` | Print the completions of `/srv/` as a JSON list. |

Prints one folder per line that the typed text could become, written as it was typed and ending in `/`, at most 50.

| `--json` field | Type | What it holds |
| --- | --- | --- |
| `paths` | `list` | The folders the typed text could become, sorted, at most 50. |

Daemon methods: `paths.complete`.

<!-- declared commands: end -->

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
