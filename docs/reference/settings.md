---
title: settings.toml
description: Look up every key of settings.toml, with its type, its default and what it does.
---

# settings.toml

Humanize stores its settings in `~/.config/humanize/settings.toml`: `settings.toml` under `$XDG_CONFIG_HOME/humanize`, or `~/.config/humanize` if `XDG_CONFIG_HOME` is unset. The interfaces write most keys for you; see [Settings](/user/settings).

## File rules

| Rule | What happens |
| --- | --- |
| Created | Created on the first write with mode `0600`. Existing files keep their mode. |
| Missing, unreadable, or invalid TOML | Read as empty. It never stops `hmz` from starting. |
| Wrong value type | Read as absent, so the default applies. |
| No null | TOML has no null: a key with no value is left out. A change that clears a key removes it. |
| Unlisted keys | Preserved at the top level and inside workspace entries. |
| Writing | One change per write. The writer locks `.settings.toml.lock`, re-reads the file, applies its change, writes a new file, and renames it into place. Concurrent changes are preserved, and so are comments beside keys the change leaves alone. |
| Exists but unreadable or invalid TOML | Never overwritten. Fix or remove the file. |
| `settings.yaml` from an earlier release | Converted once, on first run, when there is no `settings.toml`: written to `settings.toml` with mode `0600`, nulls dropped, and the YAML file renamed `settings.yaml.migrated`. A YAML file that cannot be parsed is left in place, and the settings read as unreadable until you fix it. If both files exist, `settings.toml` wins and `settings.yaml` is ignored. |
| Failed write | A change to `nous`, `clis`, `daemons`, `notifications`, `listen`, `ice_servers`, `easytier`, or a runtime is refused with an error naming the file. Any other change stays in effect for the running process only, with no error. |
| Secrets | Account credentials are never stored here: accounts appear only as names after `@` and live elsewhere in the home; see [Files on disk](/reference/files). The file does hold each `easytier` `secret` and each TURN `credential` in `ice_servers`. |

A writer waits up to 30 seconds for the lock, then writes without it.

## Example

```toml
enable_sentry = false
details = true
harness_sessions = true
listen = ["tcp://0.0.0.0:41817"]
spelling = 2

[workspaces."/home/alex/shop"]
flow = "rlar"
chat = { agent = "claude/claude-opus-5:high" }

[workspaces."/home/alex/shop".flows.rlar]
agents = { actor = "claude/claude-opus-5:high", reviewer = "codex@work/gpt-5.6-sol:high" }
envs = { box = "ssh@gpu-box/home/alex/shop" }
params = { rounds = 5 }
budget = { duration = "PT6H", cost = 20.0, graceful = true }
profile_flow = true
backup = ["lab"]

[chat]
prefer = "native"

[notifications]
kinds = { done = true, failed = true, stopped = true, asked = true, listening = false }
system = true

[[daemons]]
name = "lab"
id = ""
routes = ["stdio:ssh://lab"]

[[ice_servers]]
urls = "stun:stun.example.org:3478"

[sandbox]
backend = "auto"
native = ["codex"]

[envs]
paired_terminals = false

[nous."claude@work/claude-opus-5"]
tries = 3
policy = "exponential"
timeout = 600.0
then = ["codex/gpt-5.6-sol"]

[nous.smart.graph]
start = "pool"

[nous.smart.graph.nodes.pool]
balance = "least-busy"
among = { "claude@work/claude-opus-5" = 1, "claude@team/claude-opus-5" = 2 }
next = "cheap"

[nous.smart.graph.nodes.cheap]
use = "codex/gpt-5.6-sol"

[clis]
my-agent = ["my-agent", "--acp"]

[runtimes.ssh]
gpu-box = { host = "10.0.0.2", user = "alex" }

[runtimes.slurm]
hpc = { partition = "batch", time = "04:00:00", via = "tcp", max_jobs = 8 }

[backup]
defaults = ["lab"]

[[backup.targets]]
name = "lab"
url = "git@github.com:alex/epics.git"
branch = "main"
policies = ["session", "end"]
every = 30
```

## Machine keys

Every top-level key except `workspaces` applies to the whole machine.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `enable_sentry` | boolean | absent (unasked) | Send error reports. The terminal interface asks on first start. `HUMANIZE_SENTRY` overrides it for one process. See [Report a problem](/user/reporting). |
| `details` | boolean | `false` | Show every tool call and thinking step of a turn, not only responses. Only `true` enables it. |
| `harness_sessions` | boolean | `false` | Include standalone coding CLI sessions in a folder's chat list. Only `true` enables it. See [Continue sessions from other CLIs](/user/harness-sessions). |
| `every_epic` | boolean | `false` | Make `/epics` in the terminal list epics from the whole machine, not only the current folder. Only `true` enables it. |
| `ai_chan` | string | `""` | Nous used for the last Ai-chan conversation: a nous name or `<harness>[@<account>]/<model>[:<effort>]`. Written by the daemon; new conversations start with it. See [Ai-chan](/user/ai-chan). |
| `chat.prefer` | `native` or `flow` | `native` | Meaning of `$<name>` in a chat when it matches both a harness skill and a flow. Other values read as `native`. A chat's own choice overrides this. See [Commands, skills and files in a chat](/user/chat-input). |
| `notifications` | mapping | all enabled | Notices shown by the terminal interface. See [`notifications`](#notifications). |
| `tui` | mapping | defaults | Theme, appearance and language of the terminal interface. See [`tui`](#tui). |
| `daemons` | list | `[]` | Remote daemons reachable by the terminal interface, `hmz exec`, and the SDK. See [`daemons`](#daemons). |
| `listen` | list of strings | `[]` | Extra listeners opened by this machine's daemon beside its socket. See [`listen`](#listen). |
| `ice_servers` | list | `[]` | STUN and TURN servers used by this machine's daemon to answer WebRTC. See [`ice_servers`](#ice-servers). |
| `easytier` | mapping | `{}` | EasyTier networks this machine listens on and dials. See [`easytier`](#easytier). |
| `sandbox` | mapping | see below | How this machine enforces agent permissions. Edited by hand only. See [`sandbox`](#sandbox). |
| `envs.paired_terminals` | boolean | `false` | When `true`, lets a paired device or EasyTier session open and type into an environment terminal. Local and SSH sessions always may. Edited by hand only. See [Files, changes and terminal](/user/environment-panels). |
| `nous` | mapping | `{}` | Retries, fallback, and virtual nous. See [`nous`](#nous). |
| `clis` | mapping | `{}` | Custom coding CLIs. See [`clis`](#clis). |
| `runtimes` | mapping | `{}` | Saved machines where environments run. See [`runtimes`](#runtimes). |
| `backup` | mapping | no targets | Git repositories where epics are backed up. See [`backup`](#backup). |
| `spelling` | integer | absent | Format version for environment specs in this file. Every write sets it to `2`. Do not edit. |

Set **Details**, **Harness sessions**, and **Error reports** in **Settings > General** in the app, or with `/settings general` in the terminal.

Two legacy keys are still recognized: `fallbacks` is read as `nous` entries and removed on the next `nous` write, and `btw` is ignored.

### `notifications` {#notifications}

Set terminal notifications with `/settings notifications`. Only the terminal interface reads this key; the app and browser page store their own choices in the browser.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `kinds.done` | boolean | `true` | Notify when an epic finishes, or a chat turn does. |
| `kinds.failed` | boolean | `true` | Notify when an epic fails, runs out of budget, or is refused at start. |
| `kinds.stopped` | boolean | `true` | Notify when an epic is stopped. |
| `kinds.asked` | boolean | `true` | Notify when a flow asks a question. |
| `kinds.listening` | boolean | `true` | Notify when a flow waits for what you say next. |
| `system` | boolean | `true` | Also show operating system notifications. |

Only `false` disables a notice. See [Notifications](/user/notifications).

### `tui` {#tui}

Set these with `/settings themes` and `/settings language`. Only the terminal interface reads this key; the app and browser page store their own choices in the browser.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `theme` | string | `humanize` | The preset in use, by its key: `humanize`, `temperate-gold`, `concordant-scarlet`, `restrained-crimson`, `critical-teal`, `desirous-indigo`, `peaceful-lilac`, `hateful-silver`, `devoted-pink`, `self-negating-plum`, `dominant-azure`, `surviving-jade` or `lamenting-orchid`. |
| `appearance` | string | `auto` | Which side is drawn: `auto`, `light`, `dark`, or `terminal` for the terminal's own colours. |
| `language` | string | `""` | `en`, `zh-Hans` or `zh-Hant`; empty follows `LC_ALL`, `LC_MESSAGES` or `LANG`. |

Any other value reads as the default. `TEXTUAL_THEME` and `NO_COLOR` override `theme` and `appearance`. See [Themes and language](/user/themes).

### `daemons` {#daemons}

Add remote daemons with `/settings daemons` or a pairing code. The app and browser page keep their own lists. See [Connect to other machines](/user/daemons).

| Key | Type | Meaning |
| --- | --- | --- |
| `name` | string | Daemon name. Starts with a letter or digit, followed by letters, digits, `.`, `_`, or `-`. Cannot be `local`. Must be unique. |
| `id` | string | 52-character base32 daemon ID. `""` until filled in when the daemon first answers over a trusted route. |
| `routes` | list of strings | Routes tried in order (at least one). While `id` is `""`, the first route must be trusted, such as `stdio:ssh://…`. See [Daemon and wire](/reference/daemon). |

Entries with unknown keys, invalid values, or duplicate names are ignored and removed on the next write. The local daemon is never listed. Entries written by an earlier release (with `via`, `host`, and similar keys) are still read, and rewritten in this form on the next write.

### `listen` {#listen}

Each item is a listener spec. If empty, the daemon listens only on its local socket.

| Spec | Listener |
| --- | --- |
| `tcp://<address>:<port>` | TCP |
| `ws://<address>:<port>` | WebSocket |
| `relay:<ws-url>` | Registers with that relay |
| `webrtc:<ws-url>` | Registers with that relay and answers WebRTC |
| `easytier:<name>` | EasyTier network of that name under `easytier` |

Port `0` selects any free port. Invalid specs are skipped and logged by the daemon. See [The daemon](/user/daemon).

### `ice_servers` {#ice-servers}

A list of WebRTC ICE server entries. See [Relays and WebRTC](/user/relay).

| Key | Type | Meaning |
| --- | --- | --- |
| `urls` | string or list of strings | One or more `stun:`, `turn:`, or `turns:` URLs. |
| `username` | string | TURN server username. |
| `credential` | string | TURN server credential. |

### `easytier` {#easytier}

Maps network names to EasyTier configurations. Names follow the same rules as a daemon `name`.

| Key | Type | Meaning |
| --- | --- | --- |
| `secret` | string | Shared network secret (at least 16 bytes). |
| `nodes` | list of strings | Shared EasyTier rendezvous nodes (at least one), each as `<protocol>://<host>:<port>`, where the protocol is `tcp`, `udp`, `ws`, `wss`, `quic`, or `wg`. |

An entry referenced by a listener cannot be removed from the interfaces.

### `sandbox` {#sandbox}

Humanize never writes this key. See [The sandbox](/user/sandbox).

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `backend` | `auto`, `landlock` or `bwrap` | `auto` | Linux sandbox backend: Landlock or bubblewrap. Other values read as `auto`. |
| `native` | list of strings | `[]` | Harnesses that use their own sandbox instead. Only `codex` is honored. |

## `workspaces`

Maps a folder's resolved absolute path (symlinks resolved) to its saved setup.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `flow` | string | absent | Last flow set up in this folder. |
| `chat.agent` | string | absent | Default agent for new chats here, as `<harness>[@<account>]/<model>[:<effort>]`. Updated when you start a chat in the app or terminal, or change a chat's agent. `hmz chat` uses it when `-a` is omitted and never updates it. |
| `flows` | mapping | absent | Per-flow setups, keyed by flow name (such as `rlar` or `@local/twice`). |

An entry may be empty: the browser page writes an empty entry when you open a folder by path, and lists every folder present here. Use **Forget** on the **Setup** page of the folder's **Workspace settings** or `/settings workspace` to remove the entry.

### Flow setup entry

Located under `workspaces.<path>.flows.<flow>`.

| Key | Type | Meaning | If invalid |
| --- | --- | --- | --- |
| `agents` | mapping of role to string | Agent per role, formatted like `-a` after `<role>=`. | One invalid value makes all of `agents` absent. |
| `envs` | mapping of role to string | Environment per role, formatted like `-e` after `<role>=`. | One non-string value makes all of `envs` absent. |
| `params` | mapping | Flow parameters. | Validated against the flow's parameters. Validation failure marks the flow as not set up. |
| `budget` | mapping | `duration` (ISO 8601), `cost` (number or `"Infinity"`), `output_tokens` (integer), each left out for no limit, and `graceful` (boolean, or a boolean per limit). | Absent. |
| `profile_flow` | boolean | Profile the flow's own Python code. Written only as `true`. | Off. |
| `profile_environment` | boolean | Profile programs started by agents. Written only as `true`. | Off. |
| `backup` | list of strings | Backup target names for epics of this flow. `[]` means no target. | Absent or non-list uses the default targets. |

Saving a flow setup updates `flow` and replaces that flow's entry, carrying over any omitted keys from the existing file.

The app and terminal interface read these entries to configure epics. In the terminal, a flow starts without prompting only when its entry is complete: agent roles match the flow, all required environment roles are set, parameters validate, and a budget is present. `hmz exec` and the SDK ignore `workspaces`.

See [Start an epic](/user/epics), [Budgets](/user/budgets), and [Trace a run with Exomyth](/user/tracing).

## `nous`

Maps a nous name to retry and fallback rules. A name is either a concrete nous (`<harness>[@<account>]/<model>[:<effort>]`) or a virtual nous matching `[A-Za-z][A-Za-z0-9_.-]*` that is not a harness name. See [Nous: models, retries and fallback](/user/nous).

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `tries` | integer, 0 or more | `0` | Retries at this nous before falling back to `then`. |
| `policy` | string | `exponential-jitter` | Wait policy between tries: `none`, `constant`, `linear`, `exponential`, `exponential-jitter`, or `fibonacci`. |
| `timeout` | number of seconds | `0` | Maximum retry duration. `0` means no limit. |
| `graph` | graph | absent | Target graph for a virtual nous. Required for virtual nous; forbidden on concrete nous. |
| `then` | graph | absent | Fallback graph after all tries fail. |

A graph takes one of three forms:

| Form | Meaning |
| --- | --- |
| a string | A single nous. |
| a list of strings | Nous tried in order as each previous one fails. |
| a mapping with `start` and `nodes` | `nodes` maps node IDs to nodes; `start` is the initial node ID. |

Each node is either a use node or a balance node, plus routing edges:

| Key | Type | Meaning |
| --- | --- | --- |
| `use` | string | Use node: routes the turn to this nous. |
| `balance` | string | Balance node strategy: `shuffle`, `round-robin`, `least-busy`, `latency`, `usage`, or `cost`. |
| `among` | mapping of nous to integer | Candidate nous for a balance node, mapped to weights of 1 or more. |
| `spread` | integer, 0 or more | How many candidates a balance node tries before it fails. Default `0`: all of them. |
| `on` | mapping | Edges mapping a fault class (or `*` for any other failure) to the next node ID. |
| `next` | string | Shorthand for `on` with only `*`. |

See [Agents and harnesses](/reference/agents) for fault classes.

A virtual nous may name other virtual nous at most 32 levels deep. A walk that goes deeper, re-enters a name, or reaches a virtual nous with no entry fails at that point with the fault `missing`, which follows the node's `missing` or `*` edge.

An entry is ignored if its name is invalid, its graph is invalid, a concrete nous defines `graph`, a virtual nous omits `graph`, or a concrete nous has `tries` set to `0` and no `then`. Negative or non-numeric `tries` and `timeout` values read as `0`. Unknown `policy` values read as `exponential-jitter`.

## `clis`

Maps a custom coding CLI name to the command that starts it. The CLI must speak the Agent Client Protocol. See [Gateways, LiteLLM and custom CLIs](/user/gateways).

A value is either a command (list of strings) or a mapping:

| Key | Type | Meaning |
| --- | --- | --- |
| `command` | list of strings | Non-empty command that starts the CLI. |
| `hosts` | list of strings | Hosts the CLI may reach when a flow blocks network access: hostname, `name:port`, `*.suffix`, IP address, or URL (host part kept). Edited by hand. |
| `state` | list of strings | Extra writable paths for the CLI. Edited by hand. |

Editing a CLI in the interfaces preserves `hosts` and `state`.

When the file is read, Humanize fixes two kinds of mistakes in it and logs each fix: a key one typo away from `command`, `hosts` or `state` (such as `host`) is renamed, and a `hosts` or `state` written as one string becomes a list of that string. Any other mistake is not fixed: a command that is not a non-empty list (a command written as one string included), an unknown key, or a `hosts` or `state` that is not a list. That entry is ignored and logged as an error, and naming that CLI, as in `-a my-agent/MODEL`, fails with an error that names the file and the mistake.

## `runtimes`

Saved machines under `runtimes.<backend>.<name>`. `<backend>` is `ssh`, `docker`, `swarm`, `apple-container`, or `slurm`. `<name>` starts with a letter or digit, followed by letters, digits, `.`, `_`, or `-`. Entries with unknown fields or invalid values are ignored; the legacy list field `affinity` is read as `harness` (its first item, `self` meaning `env`). See [Runtimes: servers, containers and clusters](/user/runtimes) and [Environments and runtimes](/reference/environments).

All backends share these fields:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `workdir` | string | `""` | Default working directory when the environment spec omits one: empty, `~`, absolute path, or starting with `~/`. |
| `fallback` | list of strings | `[]` | Runtimes tried in order if this runtime cannot host an environment, each as `<backend>:<name>`. |
| `harness` | string | `env` | Where the coding CLI runs: `env`, `local`, or `<backend>:<name>` (cannot be this runtime). |
| `made` | string | `typed` | `typed`, or `imported` for SSH runtimes read from an SSH config. |

Limit fields (`cpus`, `memory`, and every `max_` field) default to `0` (no limit). `memory` and `gpu_memory` are in bytes.

### `ssh`

Requires `host` or `alias`.

| Field | Type | Default |
| --- | --- | --- |
| `host`, `user`, `alias` | string | `""` |
| `port` | integer, 0 to 65535 | `0` (uses SSH config port) |
| `identity_file`, `proxy_jump` | string | `""` |
| `config` | string | `""` (custom SSH config file) |
| `options` | mapping of string to string | `{}` (SSH keywords except `HostName`, `User`, `Port`, `IdentityFile`, and `ProxyJump`) |

### `docker`

| Field | Type | Default |
| --- | --- | --- |
| `endpoint` | string | `local`. Also accepts `unix://<path>`, `tcp://<host>:<port>`, `ssh://[<user>@]<host>[:<port>]`, `ssh:<name>`, or `context:<name>`. |
| `tls_dir` | string | `""`. For `tcp://` endpoints: directory containing `ca.pem`, `cert.pem`, and `key.pem`. |
| `container` | string | `""`. A running container that every environment works in. With it, the image and limit fields must stay empty. |
| `exec_user` | string | `""`. Format: `<uid>[:<gid>]`. |
| `exec_env` | list of strings | `[]`. Format: `<NAME>=<value>`. |
| `exec_wrapper` | list of strings | `[]`. Wrapper command prefix for all executed commands. |
| `image`, `runtime`, `name_prefix` | string | `""` |
| `run_args`, `gpus` | list of strings | `[]` |
| `cpus` | number | `0` |
| `memory`, `gpu_memory`, `max_containers` | integer | `0` |

### `swarm`

| Field | Type | Default |
| --- | --- | --- |
| `endpoint` | string | `local`. Swarm manager endpoint, formatted like `docker`. |
| `tls_dir`, `image`, `name_prefix`, `gpu_resource` | string | `""` |
| `run_args` | list of strings | `[]` |
| `constraints` | list of strings | `[]`. Format: `<attribute>==<value>` or `<attribute>!=<value>`. |
| `nodes` | mapping of string to string | `{}`. Maps node hostnames to a saved SSH runtime name or `[<user>@]<host>[:<port>]`. |
| `cpus` | number | `0` |
| `memory`, `max_tasks` | integer | `0` |

### `apple-container`

| Field | Type | Default |
| --- | --- | --- |
| `image` | string | `""` |
| `run_args` | list of strings | `[]` |
| `cpus` | number | `0` |
| `memory`, `max_containers` | integer | `0` |

### `slurm`

| Field | Type | Default |
| --- | --- | --- |
| `partition`, `account`, `qos`, `constraint` | string | `""` |
| `time` | string | `""`. Minutes, `MM:SS`, `HH:MM:SS`, `D-HH[:MM[:SS]]`, `UNLIMITED`, or `INFINITE`. |
| `via` | `srun` or `tcp` | `srun` |
| `python` | string | `""`. Accepted and ignored. |
| `run_args` | list of strings | `[]` |
| `cpus` | number | `0` |
| `memory`, `max_jobs` | integer | `0` |
| `max_wait` | integer, seconds | `0` |

## `backup`

Git repositories for epic backups, read whenever an epic starts. See [Back up to git](/user/backups).

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `targets[].name` | string | required | Target name referenced by `defaults` and flow `backup` lists. Starts with a letter or digit, then letters, digits, `-`, or `_` (max 32 characters, unique). |
| `targets[].url` | string | required | Git push URL, using this machine's SSH key or credential helper. |
| `targets[].branch` | string | `main` | Target branch for epic commits. |
| `targets[].policies` | list of `session`, `interval`, `end` | `[]` | Automatic backup triggers: on session close, at regular intervals, or when the epic ends. `[]` means manual backup only. |
| `targets[].every` | integer, 1 or more | `30` | Minutes between `interval` backups. |
| `defaults` | list of strings | `[]` | Default targets used when an epic starts without an explicit backup list. |

Invalid targets and duplicate target names are skipped. Default entries that do not match a valid target are dropped.

## Related

- [Environment variables](/reference/environment): environment variables read by `hmz`.
- [Files on disk](/reference/files): all other files in the Humanize home directory.
