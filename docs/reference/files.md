---
title: Files on disk
description: Find every file and directory Humanize keeps, what each one holds, and which ones you can delete.
---

# Files on disk

Every file and directory Humanize writes: the home, the machine directory, a workspace, an epic's directory, a chat's directory, and a backup target.

![The four places Humanize keeps files: the home, the machine directory, a workspace, and a backup target](/diagrams/reference-files-1.svg)

## Roots

| Root | Path | Holds |
| --- | --- | --- |
| Home | `$HUMANIZE_HOME`, else `~/.hmz/` | Settings, accounts, installed flows, epics, chats. Created by the first file written into it. Never removed. |
| Your flows | `~/.hmz/flows/` | Flows of the flowverse `user`. Always under `~`, whatever `HUMANIZE_HOME` is. |
| Workspace directory | `<workspace>/.hmz/` | Flows of the flowverse `local`. |
| Machine directory | `<tmp>/humanize-<uid>/` | The daemon's socket and log, caches, scratch. `<tmp>` is the first of `$TMPDIR`, `$TEMP`, `$TMP` that exists and is writable, else the first of `/tmp`, `/var/tmp` and `/usr/tmp` that is. `<uid>` is your numeric user id. |
| State directory | `$XDG_STATE_HOME/humanize/`, else `~/.local/state/humanize/` | Mirror records and LiteLLM sessions. `XDG_STATE_HOME` counts only as an absolute path. |

Placeholders on this page:

| Name | Meaning |
| --- | --- |
| `<home>` | The home. |
| `<mdir>` | The machine directory. |
| `<ws>` | The workspace key: the workspace's absolute path, symbolic links resolved, with every character outside `[A-Za-z0-9]` replaced by `-`. `/home/alex/shop` becomes `-home-alex-shop`. |
| `<stamp>-<hex6>` | The name of an epic or a chat: its start in UTC as `YYYYMMDDTHHMMSS.mmmZ`, then six random hexadecimal digits. |
| `<machine>` | In the home: `/etc/machine-id` on Linux, the `IOPlatformUUID` on macOS, else the host name up to its first `.`. |

Timestamps inside files are UTC (`YYYY-MM-DDTHH:MM:SS.mmmZ`) unless a row says otherwise. A killed writer leaves a file named `.<name>.<16 hex digits>.new` beside its target. You can delete it.

If `.hmz` does not exist yet, Humanize renames `~/.humanize/` or `<workspace>/.humanize/` to `.hmz` on first access. It does not rename `~/.humanize/` while `HUMANIZE_HOME` is set.

See [Desktop app](/reference/desktop) for files specific to Humanize Desktop.

## The home

```text
<home>/
├── settings.toml
├── .settings.toml.lock
├── settings.yaml.migrated
├── history.jsonl
├── web-port
├── providers/<cli>/<name>/
├── flowverses/<verse>/
│   ├── index/
│   └── installed/[<owner>/]<flow>/
├── envs/
├── easytier/<version>/
├── identity/<machine>/
├── ai/<machine>/
├── chats/<ws>/<stamp>-<hex6>/
└── epics/<ws>/<stamp>-<hex6>/
```

| Path | Holds | Mode | If you delete it |
| --- | --- | --- | --- |
| `settings.toml` | Every setting. See [settings.toml](/reference/settings). | `0600` | Every setting takes its default. |
| `.settings.toml.lock` | An empty file each writer of `settings.toml` locks. | `0600` | Made again. |
| `settings.yaml.migrated` | The YAML settings file an earlier release kept, left after its conversion to `settings.toml`. Never read. | As it was | Nothing changes. |
| `history.jsonl` | Lines you submitted at the prompt of `hmz`. One JSON object a line: `at` (`YYYY-MM-DDTHH:MM:SS.ffffffZ`), `workdir`, `text`. Appended, never trimmed. | umask | Prompt history is empty. |
| `web-port` | The port the last `hmz web` listened on, as digits. | umask | `hmz web` has no remembered port. |
| `providers/<cli>/<name>/` | One account. See [The account directory](#account-directory). | `0700` | The account no longer exists. |
| `flowverses/<verse>/index/` | A depth-1 `git` clone of the flowverse's index. | umask | The flowverse is no longer known. |
| `flowverses/<verse>/installed/[<owner>/]<flow>/` | One installed flow: the release's files, the skills it names by URL under `skills/<skill>/`, and `.installed.json`. | umask | The flow is no longer installed. |
| `envs/` | Directories derived from a working directory. See [Environment state](#environment-state). | umask | Copies, scratch and worktrees are gone. |
| `easytier/<version>/` | EasyTier binaries Humanize downloaded. | umask | Downloaded again when needed. |
| `identity/<machine>/` | This machine's device identity and paired devices. See [Identity](#identity). | `0700` | The machine gets a new daemon id. Every client that pinned the old one refuses it. |
| `ai/<machine>/` | Ai-chan conversations. See [Ai-chan](#ai-chan). | `0700` | Every conversation is forgotten. Each one's chat stays, as an ordinary chat. |
| `chats/<ws>/<stamp>-<hex6>/` | One chat. See [A chat's directory](#chat-directory). | umask | The chat no longer exists. |
| `epics/<ws>/<stamp>-<hex6>/` | One epic. See [An epic's directory](#epic-directory). | umask | The epic no longer exists. |

Stop every `hmz` process and the daemon before deleting entries in `<home>`. You can delete `history.jsonl` and `web-port` at any time.

`.installed.json` is a JSON object with keys `verse`, `owner`, `name`, `version`, `commit`, `repo`, `ref`, `subdir`, `dependencies`, and `skills`. A directory is not an installed flow if `.installed.json` is missing or its `verse`, `owner`, or `name` does not match the path.

You can delete `local/` and `server.json` if present; Humanize ignores them.

### The account directory {#account-directory}

`<home>/providers/<cli>/<name>/` holds one [account](/user/accounts). `<name>` matches `[A-Za-z0-9][A-Za-z0-9._-]*`.

| Entry | Holds |
| --- | --- |
| `provider.json` | Mode `0600`. Keys: `cli`, `name`, `way` (the sign-in way, default `env`), `env` (variables every turn runs with), `args` (extra arguments), `made` (`YYYY-MM-DDTHH:MM:SSZ`). The directory names win over `cli` and `name`. |
| `home/<path>` | A credential file the CLI writes at `<path>` under its own home. |
| `user/<path>` | One it writes at `<path>` under `~`. |
| `config/<path>` | One it writes at `<path>` under `${XDG_CONFIG_HOME:-~/.config}`. |

Each CLI writes its own credential files when running under the account:

| CLI | Credential files |
| --- | --- |
| `claude` | `home/.credentials.json`, `home/.claude.json`, `user/.claude.json`, `config/anthropic` |
| `codex` | `home/auth.json` |
| `agy` | `home/antigravity-oauth-token` |
| `grok` | `home/auth.json`, `home/mcp_credentials.json` |
| `kimi` | `home/credentials`, `home/oauth` |
| `pi` | `home/auth.json`, `home/auth.json.lock` |
| `opencode`, `mimo` | `home/auth.json`, `home/mcp-auth.json` |
| `cursor-agent` | `home/cli-config.json`, `config/cursor/auth.json`, `user/.cursor/auth.json` |
| `mcode` | `home/config.yaml`, `home/auth` |
| `dsh`, `omp`, `qwen`, `litellm` | None |

Removing the account deletes its directory.

### Identity {#identity}

`<home>/identity/<machine>/` has mode `0700`. Every file inside it has mode `0600`.

| File | Holds |
| --- | --- |
| `key.pem` | The device's private key, PKCS #8 in PEM, unencrypted. Written once, never rewritten. |
| `cert.pem` | The device certificate, in PEM. |
| `devices.yaml` | A YAML list, one entry per device paired with this machine's daemon: `name`, `fingerprint`, `added`, `seen`. Deleting it unpairs every device. |

### Ai-chan {#ai-chan}

`<home>/ai/<machine>/` has mode `0700`. Only the daemon writes to it.

| Entry | Holds |
| --- | --- |
| `conversations.yaml` | A YAML list, one entry per conversation: `id`, `title`, `scope`, `workspace`, `epic`, `nous`, `preset`, `slot`, `record` (the name of the conversation's chat), `created`, `latest`, `updated`. Mode `0600`. |
| `forgotten.yaml` | A YAML list of the `record` of each forgotten conversation. Mode `0600`. |
| `<id>/` | The scratch directory of conversation `<id>`. Mode `0700`. Removed when the conversation is forgotten. |

### Environment state {#environment-state}

`<home>/envs/` holds data derived from an environment's working directory on this machine. `<name>` is the last component of the working directory, truncated to 32 characters.

| Path | Holds | Removed |
| --- | --- | --- |
| `envs/<name>-<digest>/` | Everything derived from one working directory. | Never |
| `…/clones/<id>-<digest>/` | A temporary copy a flow asked for. | When the flow destroys it or the call that made it ends. Kept while a resumable epic has not ended. |
| `…/clones/<id>-<digest>.lock` | A lock the process holding the copy keeps. | With the copy |
| `…/scratch/<id>-<digest>/` | A scratch directory a flow asked for. | As a temporary copy |
| `…/worktrees/<ref>-<hex8>/` | A `git` worktree a flow added without naming a directory. `<ref>` is the reference checked out, or `head`. | Never |
| `envs/mirrors/<unit>/<digest>/` | The local mirror of the working directory of an environment in a container, a swarm service or a Slurm job. `<unit>` is its name. | With the container, service or job |

A directory ending in `….part.<pid>` is a copy in progress; `….part.gone.<random>.<pid>` is a removal in progress. You can delete `envs/` when no epic is using it.

## An epic's directory {#epic-directory}

`<home>/epics/<ws>/<stamp>-<hex6>/` holds one epic. The directory name is the epic's name. A directory is an epic only if it contains `epic.jsonl`.

```text
<home>/epics/<ws>/<stamp>-<hex6>/
├── epic.jsonl
├── epic.<flow>_<hex6>.jsonl
├── resume.jsonl
├── profile.jsonl
├── flow-profile.jsonl
├── .held
├── host.log
├── sessions/<cli>/
└── traces/
```

| File | Present | Holds |
| --- | --- | --- |
| `epic.jsonl` | Always | The epic record: one JSON event a line, each with `event` and `at`. Appended as things happen, never rewritten. See [Events and records](/reference/events). |
| `epic.<flow>_<hex6>.jsonl` | One per call of a flow by a flow | The call record, in the same format. Its first event names the record it was called under. A flow called twice has two. |
| `resume.jsonl` | Resumable flows only | The resume journal: one compact JSON object a line, starting with `{"t":"journal","v":1}`. An epic that resumes another starts from a copy of that epic's journal. |
| `profile.jsonl` | When the environment was profiled | One JSON object a line for each process seen. |
| `flow-profile.jsonl` | When the flow was profiled | One JSON object a line: `t`, `dt`, `stack`. Written when the epic ends. |
| `.held` | Always | Empty, mode `0600`. The process running the epic holds a lock on it until the epic ends. A locked `.held` means the epic is running. |
| `host.log` | Epics a daemon holds | What the daemon's host process and the CLIs it started wrote to standard error. Mode `0600`. Appended, never rotated. |
| `sessions/<cli>/` | When sessions were kept | The sessions of that CLI, laid out as the CLI lays them out under its own home. This is the only copy. |
| `sessions/<cli>/.kept/<id>/` | When a flow stored a session in its state | A copy of that session. |
| `traces/<YYYYMMDDTHHMMSSZ>.trace.json` | After a trace was asked for with no output named | A Chrome trace of the epic. See [Trace formats](/reference/tracing). |
| `traces/export.trace.json` | After an export from the terminal interface | A Chrome trace, replaced by each export. |
| `manifest.json`, `transcript.md` | Imported epics only | Copies of those members of the `.hmzepic` archive. |

Humanize never deletes an epic's directory or its files. You can delete the directory when the epic is not running.

An exported epic is one file, `<epic name>.hmzepic` by default: a gzip-compressed tar archive of mode `0600`, written where you choose.

Importing an epic writes to `<home>/epics/<ws>/<epic name>/`, using `<ws>` from the recorded workspace. The import fails if that directory already exists. An archive of a chat goes to `<home>/chats/<ws>/` instead, with `chat.jsonl`. See [Export and import a run](/user/export).

## A chat's directory {#chat-directory}

`<home>/chats/<ws>/<stamp>-<hex6>/` holds one chat. The directory name is the chat's id. A directory is a chat only if it contains `chat.jsonl`. Chats and epics never share a name.

| File | Holds |
| --- | --- |
| `chat.jsonl` | The chat record: one JSON event a line, appended, never rewritten. |
| `.held` | As an epic's. Locked while the chat is going. |
| `sessions/<cli>/` | The conversation, laid out as the CLI lays it out. This is the only copy. |
| `host.log` | As an epic's. |
| `manifest.json` | Only in a chat downloaded from a backup target. |

Events in `chat.jsonl`:

| `event` | Written when | Keys |
| --- | --- | --- |
| `began` | The chat begins. Once, first. | `task` (the first message), `workspace`, `agents` (one entry, whose `agent` is `assistant`). Where they apply: `backup`, `prefer` (`native` or `flow`), `permission` (`read-only` or `danger-full-access`), `workdir` (the worktree it works in), `env` (the environment it began in, in place of `workdir`), `title`, `forked` (the chat it is a fork of), `adopted` (`<harness>:<id>`, the CLI session it was made from). |
| `set` | The preference, agent, permission, environment or title changes, or the chat is archived or put back. | Any of `prefer`, `agents`, `permission`, `env`, `title`, `archived`. |
| `opened` | A session's CLI gave it an id. | As in an epic record. |
| `reopened` | You send a message to a chat that had ended. | `task`, that message. |
| `usage` | The chat ends. | As in an epic record. What a chat spent is the sum of its `usage` events. |
| `backed` | A backup of the chat finished or failed. | As in an epic record. |
| `ended` | The chat ends. | `how`: `stopped` or `failed`. |
| `imported` | The chat was downloaded from a backup target. | `from`, `head`. |

Take `prefer`, `agents`, `permission`, `env`, `title`, and `archived` from the last event that sets them, including `began`. `permission` defaults to `workspace-write`, and `title` defaults to the first line of `task`. A chat is ended only when an `ended` event follows its last `reopened` event.

Forking a chat creates a new directory with a copy of `sessions/`. Adopting a CLI session copies its files into `sessions/<harness>/` in a new directory without modifying the CLI's original files.

Deleting a chat removes its directory, or you can delete the directory directly when the chat is not running. Deleting a chat never removes the worktree in `workdir`.

When the daemon starts, it moves every chat that an earlier release recorded under `<home>/epics/` to `<home>/chats/<ws>/`, renaming its `epic.jsonl` to `chat.jsonl`.

A chat started without a folder uses `<mdir>/nofolder/<random>/`, which is removed once no chat or epic that used it remains.

## The machine directory

`<mdir>` has mode `0700`. Humanize refuses to use it if you do not own it or if others can write to it. A cleaner of temporary files may empty it; Humanize recreates files as needed.

| Path | Holds | Removed |
| --- | --- | --- |
| `daemon.sock` | The socket the daemon accepts frontends on. Mode `0600`. | When the daemon closes |
| `daemon.json` | `pid`, `started`, `kind` (`daemon`), `protocol`. Mode `0600`. | When the daemon closes |
| `daemon.lock` | Empty, mode `0600`. The daemon holds a lock on it for its whole life. | Never |
| `daemon.log` | Standard output and standard error of the daemon, and of a host process that holds no epic. Mode `0600`. Appended, never rotated. | Never |
| `ai-<hex>.sock` | The socket of one Ai-chan conversation. Mode `0600`. | When that conversation's host goes |
| `prices.json` | The price list, fetched from the source `HUMANIZE_PRICES` names when older than 24 hours. | Never |
| `releases.json` | `{"latest": "<version>"}`, the newest release of `hmz`. | Never |
| `models/<cli>/<account>.json`, `models/<cli>/_local.json` | The model catalogue of one account, and of the CLI's own sign-in. | An account's, with the account |
| `pinned/<url-digest>/<commit>/` | A `git` checkout for a flow reference pinned to a commit, or for a release being installed. | Never |
| `skills/<owner>-<repo>-<digest>/` | A clone of a skill repository that a flow not installed names by URL. | Never |
| `backup/<target>/`, `backup/<target>.lock` | The `git` clone of one backup target, and its lock. | Never |
| `compiled/pi/`, `compiled/qwen/` | Node compile caches of those CLIs. | Never |
| `docker-ssh/<digest>/ssh` | A script that runs `ssh` with the options of a Docker runtime reached over ssh. Mode `0700`. | Never |
| `tokens/<digest>` | One secret, for a command line that names a secret by file. Mode `0600`. | With the Slurm job it belongs to; any other, never |
| `harness/` | An empty directory mounted as the working directory of a CLI placed in a container. | Never |
| `.<kind>.<runtime>.lock` | A lock for one runtime. `<kind>` is `docker`, `swarm`, `slurm` or `apple-container`. | Never |
| `nofolder/<random>/` | The working directory of an epic or a chat started in no folder. Mode `0700`. | With the last epic or chat that used it |
| `web-<port>.html` | A page that redirects to `hmz web`, with its key. Mode `0600`. | When `hmz web` stops |
| `tmp<random>/` | An archive being imported or exported, or a trace being computed. Mode `0700`. | When the request ends |
| `aside-<random>/` | The sessions of one side question. | When the side question closes |

Never delete `daemon.sock`, `daemon.json`, or `daemon.lock` while the daemon runs. Stop all `hmz` processes and the daemon before deleting other files in `<mdir>`, except `daemon.log`, which you can delete at any time.

`hmz` processes with different temporary directories connect to different daemons. See [Daemon and wire](/reference/daemon) and [Environment variables](/reference/environment).

### Other temporary files

| Path | Holds | Removed |
| --- | --- | --- |
| `<tmp>/hmz-fence-<random>/` | The temporary directory of one sandboxed agent process. Mode `0700`. | When the agent ends |
| `<tmp>/hmz-home-<random>/` | The configuration home one CLI process runs with in place of its own: copies of the CLI's configuration files, and links to the rest of its real home. Mode `0700`. | When that process exits |
| `<tmp>/humanize-hook-<random>/`, `humanize-tools-<random>/`, `humanize-preload-<random>/`, `humanize-clis-<random>/` | The sockets one CLI process reaches Humanize through. Mode `0700`. Under `/tmp` when the path would be too long for a socket. | When the agent or session ends |
| `<tmp>/hmz-dsh-<random>/`, `hmz-gateway-<random>/`, `hmz-homes-<random>/` | The configuration of one `dsh` process, of one LiteLLM gateway process (with its account's credentials, mode `0600`), and the homes of turns run on another machine. Mode `0700`. | When the agent or session ends |
| `<tmp>/hmz-sessions-<random>/` | Sessions a flow stored in its state, for an epic with no resume journal. | When the epic ends |
| `<tmp>/hmz-env-<random>/` | A copy of a file of an environment while your editor has it open from the terminal interface. | When the editor closes |
| `<tmp>/hmz-private-<random>/` | The home and the temporary directory of the private daemons of one Python process, with a copy of `settings.toml`. | When the last of them closes |
| `<tmp>/humanize-<random>/` | The container id and a mirror for one container, service or job of an environment. | With the container, service or job |
| `${XDG_RUNTIME_DIR:-<tmp>}/humanize-ssh-<uid>/` | Shared ssh connections. Mode `0700`. Under `/tmp` when the path would be too long for a socket. | Each socket, 120 seconds after its last use |
| `/dev/shm/hmz-<pid>-<16 hex digits>-<random>/` | Linux only. Copies of an account's credential files staged for one CLI process. Mode `0700`. | When that process ends |

## A workspace

Aside from files created by agents and flows, Humanize writes only these entries in a workspace:

| Path | Holds |
| --- | --- |
| `<workspace>/.hmz/flows/<flow>/__init__.py`, `<workspace>/.hmz/flows/<flow>.py` | Flows of the flowverse `local`. Humanize writes here only when you copy a flow into the workspace. It never removes anything here. |
| `refs/hmz/snapshots/<name>` in the repository | One snapshot of an environment: a commit by `humanize <humanize@localhost>`. The default `<name>` is `YYYYMMDDTHHMMSS.ffffffZ-<hex4>`. Never removed. |
| `<index>.hmz-snapshot.<pid>` beside the repository's index | A temporary index while a snapshot is taken. |
| `.<hex12>.hmz-tmp` beside a file | A file a flow is writing through its environment, before it is renamed into place. |

Humanize never adds `.hmz/` to `.gitignore`. Snapshots exclude `.hmz/` at the root of the working tree, and rewinds leave it untouched.

Humanize never writes CLI skills, hooks, commands, or instruction files into a workspace—including anything under `.claude/`, `.agents/`, `.cursor/`, `.codex/`, `.gemini/`, `.qwen/`, or `.grok/`, and any `AGENTS.md`, `CLAUDE.md`, or `.mcp.json`. It never writes epic records, sessions, traces, or archives there unless you specify that path as the destination.

## The state directory

| Path | Holds |
| --- | --- |
| `<state>/shadows/<sha16>.json` | `{"shadow": "<path>", "target": "<machine>"}`: one mirror on this machine and the machine it mirrors. `HUMANIZE_SHADOWS` names another directory. |
| `<state>/shadows/<sha16>.journal`, `<sha16>.live` | What the CLI processes using that mirror know of its files, and a marker that it is in use. Mode `0600`. |
| `<state>/litellm/sessions/<id>.jsonl` | A session of the `litellm` agent that is not kept in an epic. |

`<state>` is the state directory. Humanize never removes these files. You can delete them when no `hmz` process or daemon is running.

Earlier releases kept these under `~/.cache/humanize/`. The first process that looks for `shadows/` (unless `HUMANIZE_SHADOWS` is set), `litellm/` or `displaced/` in the state directory and finds none moves the old one there. It never merges into a directory that already exists, and leaves the old one where it is if it cannot be moved.

## A backup target

A backup target is a `git` repository that stores epics and chats from every machine and workspace as plain files. See [Back up to git](/user/backups).

```text
<machine>/<workspace>/<epic>/
├── epic.jsonl
├── epic.<flow>_<hex6>.jsonl
├── resume.jsonl
├── profile.jsonl
├── flow-profile.jsonl
├── traces/<name>
├── sessions/<session name>/<path>
└── manifest.json
```

| Part | Value |
| --- | --- |
| `<machine>` | The host name up to its first `.`, with every run of characters outside `[A-Za-z0-9._-]` replaced by one `-`. |
| `<workspace>` | The workspace key, `<ws>`. |
| `<epic>` | The epic's name, or the chat's id. |
| Files | The members of a `.hmzepic` archive of the epic, with every credential replaced by `[redacted]` and every `backed` event left out. A chat has `chat.jsonl` in place of `epic.jsonl`. |
| Commit | One per backup, with the message `Back up epic <epic> (<why>)`. `<why>` is `session`, `interval`, `end` or `manual`. |
| Author | Your `git` identity. `hmz <hmz@localhost>` where `git` has none. |
| Branch | The target's branch, `main` by default. Created when the remote has none. |

Humanize skips committing if only the manifest changed since the last backup. The local clone is at `<mdir>/backup/<target>/`.

`hmz backup --pull` writes epics to `<home>/epics/<ws>/<epic>/` and chats to `<home>/chats/<ws>/<chat>/`, failing if the destination directory already exists.

## On other machines

Humanize creates only the following files on remote machines running an environment or CLI:

| Path | Holds | Removed |
| --- | --- | --- |
| `${XDG_STATE_HOME:-$HOME/.local/state}/humanize/envs/` | As [Environment state](#environment-state), for environments on that machine. A relative `XDG_STATE_HOME` is ignored. | As there |
| `${XDG_CACHE_HOME:-$HOME/.cache}/humanize/coganchor-<digest16>` | The `coganchor` binary for that machine. Mode `0700`. `/tmp/humanize/coganchor-<digest16>` in a container. | By a later install, once unused for 14 days |
| `${XDG_CACHE_HOME:-$HOME/.cache}/humanize-mirrors/<sha16>/` | A CLI's mirror of the workspace, when the CLI runs on another machine than the environment. `/tmp/humanize-mirrors/<sha16>/` in a container. | Never |
| `/tmp/humanize-slurm-<job id>.out` | Output of a Slurm job reached over TCP, on its node. | Never |
| A `mktemp -d` directory | An account's credential files for one turn of a CLI running there. Mode `0700`, files `0600`. | When the turn ends |
| `<file>.humanize-<pid>-<n>.tmp` beside a file | A file being written, before it is renamed into place. | On rename |
| The directories of a CLI process, in that machine's temporary directory | As [Other temporary files](#other-temporary-files). | As there, except `hmz-fence-<random>/`, which is never removed |
| `shadows/` in that machine's state directory | The records of the mirrors on that machine, as [The state directory](#the-state-directory). | Never |

Each variable is read from the environment Humanize's commands run with on that machine. On a Slurm node that environment has only `HOME` and `USER`. When Humanize first reaches an SSH host, and when a Slurm job starts, it moves the `envs/` an earlier version kept on that machine into the state directory above: the one in `$HUMANIZE_HOME` or `~/.hmz`, else the one in `~/.humanize`. It moves nothing if the state directory already has `envs/` or is on another filesystem. After moving, it removes the old directory if that leaves it empty and runs `git worktree repair` in each worktree it moved.

Containers, swarm services, and Slurm jobs are named `humanize-<runtime>-<role>-<hex8>`, or `<name_prefix>-<role>-<hex8>` if the runtime sets `name_prefix`. Each has the labels `humanize=<uid>`, `humanize.provider`, `humanize.role`, `humanize.host`, and `humanize.pid`, and is removed when the environment closes. See [Environments and runtimes](/reference/environments).

## Never removed for you

Humanize never prunes these paths; delete them manually when you no longer need them:

- `<home>/epics/` and `<home>/chats/`
- `<home>/history.jsonl`
- worktrees under `<home>/envs/`
- `refs/hmz/snapshots/` in your repositories
- `<mdir>/daemon.log`, `<mdir>/pinned/`, `<mdir>/skills/` and `<mdir>/backup/`
- the state directory

Humanize reads `~/.ssh/config` and its included files, and never writes to them.

`hmz daemon install` writes one file outside these places: `~/Library/LaunchAgents/ai.humanfia.hmz.daemon.plist` on macOS, or `$XDG_CONFIG_HOME/systemd/user/hmz-daemon.service` on Linux, with the `XDG_CONFIG_HOME` of your systemd user manager (`~/.config/systemd/user/hmz-daemon.service` when it is unset or relative). `hmz daemon uninstall` removes it. See [Daemon and wire](/reference/daemon).
