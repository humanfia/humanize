# Settings

Every setting Humanize persists: its key, scope, type, default, the file it is stored in, who
writes and reads it, and when a change takes effect. The screen that edits them is
[`/settings`](/reference/tui#menus); the Python object is `Hmz().settings`
(`hmz.runtime.settings.Settings`, internal).

## Stores

| Store | File | Scope | Edited on `/settings` page | Reference |
| --- | --- | --- | --- | --- |
| settings | `H/settings.yaml` | this machine, and per workspace | General, Workspace (and `/flow`) | this page |
| accounts | `H/providers/<cli>/<name>/provider.json`; CLIs added by hand under [`clis`](#clis) in `H/settings.yaml` | this machine | Accounts | [Providers](/reference/providers), [Files](/reference/files#h-providers-cli-name) |
| runtimes | [`runtimes`](#runtimes) in `H/settings.yaml` | this machine | Runtimes | [Machines](/reference/machines#runtimes) |
| nous | [`nous`](#nous) in `H/settings.yaml` | this machine | Nous | this page |
| backups | [`backup`](#backup) in `H/settings.yaml`; clones cached under `hmz.machine()/backup/<name>/` | this machine | none yet: `settings.yaml` | this page |
| flowverses | `H/flowverses/<name>/index/` (index clones), `H/flowverses/<name>/installed/[<user>/]<flow>/` (installed flows) | this machine | none: `/flow` › Flowverses | [Flows](/reference/flows#flowverses) |

`H` is `$HUMANIZE_HOME`, else `~/.hmz`. A workspace is identified by its absolute,
symlink-resolved path.

## `settings.yaml`

```yaml
workspaces:
  /home/you/code:                  # one entry per workspace
    flow: rlar                     # the flow last set up here
    chat:
      agent: claude/claude-opus-5:high  # the agent a new chat here starts with
    flows:
      rlar:                        # one entry per flow set up here, by listed name
        agents:
          actor: claude/claude-opus-5:high
          reviewer: codex@work/gpt-5.6-sol:high
        envs:
          box: ssh@gpu-box/home/you/code
        params:
          rounds: 5
        budget:
          duration: PT6H
          cost: 20.0
          output_tokens: null
          graceful: true
        profile_flow: true         # profile the flow's Python in a run started from the TUI
        profile_environment: true  # and the programs its agents start
        backup: [lab]              # the targets an epic of it goes to; [] for none
        harness: local
enable_sentry: false               # this machine
details: true                      # this machine
ai_chan: claude/claude-opus-5:high # this machine: the nous Ai-chan was last made with
every_epic: true                   # this machine
harness_sessions: true             # this machine
chat:                              # this machine
  prefer: native                   # native or flow: what `$<name>` is in a chat where both
sandbox:                           # this machine; written by hand
  backend: auto                    # auto, landlock or bwrap: what holds a grant on Linux
  native: [codex]                  # CLIs whose own sandbox holds their grant instead
daemons:                           # this machine; /settings daemons
- name: gpu
  id: ""                           # pinned the first time it answers over a trusted route
  routes: ["stdio:ssh://me@gpu.example:22?identity=~%2F.ssh%2Fid_ed25519"]
- name: lab                        # an ssh config host, resolved each time
  id: ""
  routes: ["stdio:ssh://lab"]
- name: home                       # paired from its code: `hmz daemon pair` there
  id: j2quawebkb3tzy5kzz4gv3xx6qcjzyia7jsjzfh3xxnzmdy5vfba
  routes: ["tcp://home.example:41817", "easytier:home"]
notifications:                     # this machine; /settings notifications
  kinds: {done: true, failed: true, stopped: true, asked: true, listening: true}
  system: true
spelling: 2                        # how envs are spelled; written with every change
nous:                              # this machine; the Nous page
  claude@work/claude-opus-5:
    tries: 3
    policy: exponential
    timeout: 600.0
    then: [codex/gpt-5.6-sol, dsh/deepseek-v4-flash]
  smart:
    tries: 0
    policy: exponential-jitter
    timeout: 0.0
    graph:
      start: pool
      nodes:
        pool: {balance: least-busy, among: {claude@work/claude-opus-5: 1, claude@team/claude-opus-5: 2}, next: cheap}
        cheap: {use: dsh/deepseek-v4-flash}
clis:                              # this machine; added on the Accounts page
  my-agent: [my-agent, --acp]
runtimes:                          # this machine; the Runtimes page
  ssh:
    gpu-box: {host: 10.0.0.2, user: you, port: 0, ...}
backup:                            # this machine
  targets:
  - name: lab
    url: git@github.com:you/epics.git
    branch: main
    policies: [session, interval, end]
    every: 30
  defaults: [lab]
```

### Machine settings

| Key | Type | Default (absent) | Written by | Read by | Takes effect |
| --- | --- | --- | --- | --- | --- |
| <span id="enable-sentry"></span>`enable_sentry` | `bool` | absent: *nobody has been asked*; the TUI asks at its first start; everything else reports nothing | the first-start question; `/settings` › General › **Error reports** | every process that could report (read once per process) | immediately in the process that changed it; at start elsewhere. [`HUMANIZE_SENTRY`](/reference/environment#humanize-sentry) overrides it for one process without writing it. Reading never writes it. |
| `details` | `bool` (only `true` is on) | `false` | `/settings` › General › **Details** | the TUI | immediately: turns show every tool call and all thinking instead of responses only |
| <span id="ai-chan"></span>`ai_chan` | `str`: a nous's name, or `cli[@account]/model:effort` | `""`: no conversation was made yet, and `/ai` and the page ask for one | nothing you set: the daemon, as [`aichan.create`](/reference/daemon#aichan-methods) makes a conversation, writes the nous it was made with | the TUI and the web page, as their forms' default; the daemon, as `aichan.create` is given no `nous` | the next Ai-chan conversation made; one made keeps its nous |
| `every_epic` | `bool` (only `true` is on) | `false`: this directory's | `ctrl+t` on [`/epics`](/reference/tui#the-runs-that-have-already-happened) | the TUI | the next time `/epics` is opened |
| <span id="harness-sessions"></span>`harness_sessions` | `bool` (only `true` is on) | `false`: only what Humanize ran is listed | `/settings` › General › **Harness sessions**; web **Settings › General › Harness sessions**; `settings.set` `harness_sessions` | the web page's sidebar and the TUI's `/resume` in a chat | the web sidebar at once; the TUI the next time `/resume` is typed. It governs what the interfaces list: [`chat.harness.list`](/reference/daemon#harness-sessions) answers either way |
| <span id="chat-prefer"></span>`chat.prefer` | `str`: `native` or `flow` (any other value reads as `native`) | `native` | `/settings` › General › **Chat prefers for `$`**; `settings.set` `prefer` | every chat, through its host | the next `$` line of every [chat](/user/chat#a-name-that-is-both) that has no preference of its own (`/prefer`, the web's **Skill or flow** menu, `chat.set`), which is kept in that chat's record |
| `daemons` | list of `{name, id, routes}`: `id` the daemon id pinned, 52 base32 characters, or `""` until it first answers over a trusted route, which pins it; `routes` the routes it is reached by (Section 3.3 of `protocol/wire.md`), in the order they are raced, the first a trusted one (`stdio:ssh://…`, `stdio:local`, `stdio:wsl`) where `id` is `""`. An entry an earlier release wrote, `{via, host, user, port, identity_file, proxy_jump, options, alias}` or `{via: easytier, secret, peers}`, is read as the `stdio:ssh` or `easytier:<name>` route it reached, and written so at the next write, an EasyTier one's secret and nodes moving to `easytier` | `[]`: Local alone | `Remotes.pair` from a pairing code, the terminal interface's [Daemons](/user/settings#daemons) page and its **Import…** | the terminal interface, `hmz exec`, the SDK; never the web page, which keeps [its own](/reference/web#kept) | at once: a daemon added is reached the first time it is asked for, one removed is let go of |
| `notifications` | `{kinds: {done, failed, stopped, asked, listening}: bool, system: bool}` | every kind told, and shown by the system too; only `false` turns one off | [`/settings notifications`](/reference/tui#notifications-page) | `hmz`; never the web page, which keeps [its own](/reference/web#kept) | immediately: the next notice of a kind is told or not |
| <span id="sandbox"></span>`sandbox` | `{backend: str, native: [str]}` | `backend`: `auto` (any value but `landlock` and `bwrap` reads as it); `native`: `[]` (an entry that is not a string is ignored) | nobody: written by hand | every process that fences an agent: `backend` where the fence is put up, on that machine; `native` by the Codex driver | at the next turn fenced. `backend` picks Landlock or bubblewrap on Linux, `auto` being Landlock where it can hold the grant and bubblewrap otherwise; `native` names CLIs whose own sandbox holds their grant around the commands they run alone, of which only `codex` is honoured. See [Permissions](/user/permissions#choose-how-this-machine-holds-a-grant) |
| <span id="envs"></span>`envs` | `{paired_terminals: bool}` | `paired_terminals`: `false` (only `true` is on) | nobody: written by hand | the daemon, at each call that opens or types into a terminal | at the next such call. `true` lets a paired device, or a session over EasyTier, open a shell in an epic's environments; a session on this machine or over SSH always may. See [Into its environments](/features/environments#from-another-device) |
| <span id="spelling"></span>`spelling` | `int` | absent: written before `-e` wrote `@` only before a provider | every write of the file, as `2` | every process, as it reads the file | absent, `envs` are read as their old spelling meant and rewritten once; `2`, as written |

What error reports contain and exclude is listed on `/settings` › General › **What is sent**.

### Workspace settings

Under `workspaces.<path>`.

| Key | Type | Default | Written by | Read by | Takes effect |
| --- | --- | --- | --- | --- | --- |
| `flow` | `str`, a listed flow name | absent (`Settings.flow` is `""`): no flow set up here | `/flow` when saved | the TUI at start, as the flow `/flow` and `$` lines start from; the TUI always opens on a new [chat](/user/chat) | next launch |
| <span id="chat-agent"></span>`chat.agent` | `str`, an agent as `-a` spells one after `<role>=` | absent (`Settings.chat_agent` is `None`; one an earlier Humanize wrote as the `assistant` of `flows.chat.agents` is read in its place); the TUI then [fills it by default](/reference/tui#default-fill) | starting a chat from the TUI or the web, `/model` or `/effort` in one, `/settings` › Workspace › **Chat agent**, `settings.set` `chat`; never `flow` or a flow's entry | the TUI, the web's **New epic › Chat**, and `hmz chat` given no `-a` | the next chat started here |
| `flows.<flow>` | mapping | absent | `/flow` when saved | the TUI | see below |

`/settings` › Workspace also shows **Default flow** (read-only), **Chat agent**, and **Forget**: on save it
deletes this workspace's entry; the TUI already open keeps what it loaded, and the next launch
starts without it.

### Per flow

Under `workspaces.<path>.flows.<flow>`, keyed by the flow's listed name (`rlar`,
`alice/kernel`, `@local/twice`, `@theirs/review`, `humanize1:gen-plan`), so a local flow never
inherits the setup of the installed flow it shadows.

| Key | Type | Meaning | Read back |
| --- | --- | --- | --- |
| `agents` | `{role: str}` | each agent role's `cli[@account]/model:effort` (the [`-a`](/reference/flows#a-agents) spec after `<role>=`) | an entry that does not read as `cli[@account]/model:effort` (split at the first `/` and the last `:`) makes the whole `agents` mapping read as absent |
| `envs` | `{role: str}` | each environment role's [`-e`](/reference/flows#e-environments) spec after `<role>=` | any non-string value makes the mapping read as absent; in a file with no [`spelling`](#spelling), a spec in the spelling `-e` refuses with a hint (`local@/x`, `docker@local/x`, `swarm@local/x`, `apple-container@local/x`, `slurm@local/x`, an unsaved ssh host out of brackets) is rewritten in the one the hint gives, in every workspace, when the file is first read |
| `params` | mapping | the params, as JSON | validated through the flow's current params model; a failure reads as not set up |
| `budget` | `{duration, cost, output_tokens, graceful}` | the budget as `Budget.model_dump_json` writes it (`duration` ISO 8601, `cost` `"Infinity"` for unlimited, `graceful` a `bool` or `{duration, cost, output_tokens}` of `bool`s) | validated as a `Budget`; a failure reads as absent |
| `profile_flow` | `bool`, written only as `true` | whether a run of the flow started from the TUI or the web profiles the flow's own Python, set on the `/flow` menu's **profile flow** row | anything but `true` reads as off |
| `profile_environment` | `bool`, written only as `true` | whether a run of the flow started from the TUI or the web [profiles](/reference/tracing#profiling-a-run) the programs its agents start, set on the `/flow` menu's **profile environment** row | anything but `true` reads as off |
| `backup` | `[str]` | the [backup targets](#backup) an epic of the flow goes to, by name, as **Backup** on the **New epic** form of `hmz web` was started with; `[]` is none | anything but a list reads as absent, which is the defaults; a name settings has no target of is dropped by whoever starts the epic |

**Writing.** Saving `/flow` replaces the flow's whole entry and sets `flow`. `agents` is always
written; `envs`, `params`, `budget`, `profile_flow`, `profile_environment` and `backup` are
written as given, carried over from the file where the caller passes none, and an empty value
(or a profiling switch off) erases the
key -- but an empty `backup`, which is kept as none. A `harness` key an older
Humanize wrote is dropped at the next save.

**Reading.** When the TUI starts a flow without opening `/flow` (a `$flow` line, or
`/flow <flow> <task>`), it uses the remembered setup only if it is complete: the remembered
agent roles equal the flow's declared agent roles; every required environment role is
remembered; the params still validate; a budget is remembered. Otherwise `/flow` opens to ask. `profile_flow` and `profile_environment` go with the rest. `hmz exec` and `Hmz().run` never read `flows`; they
use only their own arguments (`--profile-flow`, `--profile-environment`, `profile_flow=True`,
`profile_environment=True`).

### `nous`

[Nous](/user/settings#nous), written by `/settings` › Nous and `Hmz().nous`. A mapping from
each nous's name -- a concrete nous `CLI[@ACCOUNT]/MODEL[:EFFORT]`, or a virtual nous's name,
`[A-Za-z][A-Za-z0-9_.-]*` and no CLI's -- to:

| Field | Type | |
| --- | --- | --- |
| `tries` | `int` | retries before `then` |
| `policy` | `str` | `none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci` |
| `timeout` | `float` | seconds, `0` for no limit |
| `graph` | graph | a virtual nous's graph; never on a concrete one |
| `then` | graph | where a turn goes once the tries are spent |

A graph is one nous, a list of nous tried in turn, or `{start, nodes}`, `nodes` mapping each
node's id to `{use: <nous>}` or `{balance: <strategy>, among: {<nous>: <weight>}, spread: <n>}`,
with `on: {<fault class or *>: <node id>}` or `next: <node id>` (the same as `on: {'*': …}`).
A chain is written back as a list. Invalid entries are dropped on read, as is one that names those
before it round; a write that would name a virtual nous nobody wrote, or let nous name one another
round, is refused. A `fallbacks` list an
older Humanize wrote is read as each `spec`'s `then: <to>`, and dropped at the next write.

### `clis`

CLIs added on the Accounts page, driven over ACP. A mapping from name to either an argv list
or `{command: [...], hosts: [...], state: [...]}` (`hosts`, `state` are set by hand: the hosts
it may reach with `network=False`, and extra paths it may write). A host is `name`,
`name:port`, `*.suffix` or an IP address; one written as a URL is read as its host and port
(`https://api.example.com/v1` is `api.example.com`), and one that names no host is dropped
with a warning, so a list of nothing else counts as no hosts. Removing the key forgets every
added CLI.

### `runtimes`

[Runtimes](/reference/machines#runtimes), written by `/settings` › Runtimes and
`Hmz().runtimes`: `runtimes.<backend>.<name>`, `<backend>` `ssh`, `docker`, `swarm`,
`apple-container` or `slurm`. The backend and the name are where the entry is, whatever it says; an
entry that does not validate is skipped. A runtime an earlier Humanize wrote with an ordered
`affinity` list is read as though its `harness` were the list's first entry (`self` read as
`env`), and as having none where the list is empty; the next write of it drops `affinity`.

`ssh`:

| Field | Type |
| --- | --- |
| `host`, `user`, `identity_file`, `proxy_jump`, `alias`, `config`, `workdir` | `str` |
| `port` | `int` |
| `options` | `{str: str}` |
| `fallback` | `[str]`, each `<backend>:<name>` |
| `harness` | `str`: `env` (default), `local` or `<backend>:<name>`, not the runtime itself |
| `made` | `"typed"` or `"imported"` |

`docker`:

| Field | Type |
| --- | --- |
| `tls_dir`, `image`, `runtime`, `name_prefix`, `workdir` | `str` |
| `endpoint` | `local`, `unix://…`, `tcp://…`, `ssh://…`, `ssh:<ssh runtime>`, `context:<name>` |
| `container` | `str`: a running container every environment works in ([A running container](/reference/machines#a-running-container)) |
| `exec_user` | `str`: `UID[:GID]` |
| `exec_env`, `exec_wrapper` | `[str]`: `NAME=VALUE` each; the wrapper's words |
| `run_args`, `gpus`, `fallback` | `[str]` |
| `harness` | `str`, as for `ssh` |
| `cpus` | `float` |
| `memory`, `gpu_memory`, `max_containers` | `int` |
| `made` | `"typed"` |

`swarm`:

| Field | Type |
| --- | --- |
| `tls_dir`, `image`, `name_prefix`, `gpu_resource`, `workdir` | `str` |
| `endpoint` | a swarm manager, as a docker runtime's `endpoint` |
| `run_args`, `constraints`, `fallback` | `[str]` |
| `harness` | `str`, as for `ssh` |
| `cpus` | `float` |
| `memory`, `max_tasks` | `int` |
| `nodes` | `{str: str}`: a node's host name to a saved ssh runtime's name or `[user@]host[:port]` |
| `made` | `"typed"` |

`apple-container`: `image`, `workdir`, `harness` (`str`), `run_args`, `fallback` (`[str]`),
`cpus` (`float`), `memory`, `max_containers` (`int`), `made` (`"typed"`).

`slurm`:

| Field | Type |
| --- | --- |
| `partition`, `account`, `qos`, `constraint`, `workdir` | `str` |
| `time` | `str`: minutes, `MM:SS`, `HH:MM:SS`, `D-HH[:MM[:SS]]`, `UNLIMITED` or `INFINITE` |
| `python` | `str`: absolute, or under `~/`; accepted and not used |
| `via` | `"srun"` or `"tcp"` |
| `run_args`, `fallback` | `[str]` |
| `harness` | `str`, as for `ssh` |
| `cpus` | `float` |
| `memory`, `max_jobs`, `max_wait` | `int` |
| `made` | `"typed"` |

```yaml
runtimes:
  slurm:
    hpc:
      partition: batch
      account: myteam
      time: '04:00:00'
      via: tcp
      max_jobs: 8
      max_wait: 600
      workdir: /lustre/me/project
```

### `backup`

The git repositories [epics are backed up to](/user/backups), written by
`Hmz().settings.back_up_to(targets, defaults)` -- which the [Backup page](/user/settings#backup) of
`/settings` saves through -- and read by every process that runs an epic, as
the epic starts.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `targets[].name` | `str`: a letter or digit, then letters, digits, `-` and `_`, 32 at most | **required** | What `--backup`, `--to` and `defaults` name it. Unique. |
| `targets[].url` | `str` | **required** | Where git pushes to, with this machine's own ssh key or credential helper. |
| `targets[].branch` | `str` | `main` | The branch epics are committed to; made where the repository has none. |
| `targets[].policies` | list of `session`, `interval`, `end` | `[]`: by hand only | When an epic is backed up there unasked. |
| `targets[].every` | `int` ≥ 1 | `30` | Minutes between `interval` backups of a running epic. |
| `defaults` | list of target names | `[]` | The targets an epic goes to when it is started without saying. |

A target that does not validate is skipped as the file is read, and a default naming no target
is dropped; `back_up_to` refuses both with `ValueError` and writes nothing. Each backup's
outcome is a `backed` line in the epic's `epic.jsonl` (`to`, `ok`, `error`, `why`).

## File behaviour

| Behaviour | Rule |
| --- | --- |
| Missing, unreadable, invalid YAML, not a mapping | read as empty; never prevents a start |
| Unknown keys | kept at the top level and in a workspace entry; a flow's entry is replaced whole when `/flow` is saved |
| Write | each change is written at once: take `flock(LOCK_EX)` on `.settings.yaml.lock` beside the file; re-read the file; make this one change to what it holds now (one machine key, one workspace's `flow` and one flow's entry, one workspace removed, or the whole of `nous`, `clis`, `backup` or one runtime); write `.settings.yaml.<random>.new` (mode `0600` for a new file, the existing file's otherwise), fsync, rename over; release the lock. The writer then holds what it wrote. A file that exists but does not read as a mapping is never written over: it is left for whoever is editing it to correct. |
| Concurrent writers | serialized by the lock. A write changes only what it is about: every machine key, workspace, workspace key and flow entry another writer wrote survives it, whenever this writer read the file. `envs`, `params`, `budget`, `profile_flow`, `profile_environment` and `backup` not handed to a `/flow` save are carried over from the file as it is at the write. Two writes to the same key or the same flow's entry: the later wins. A writer that cannot open the lock file, gets an error from `flock`, or has waited 30 s for it writes without it. |
| Write failure, or a file that does not read as a mapping | a `Settings` holds the change in memory and writes nothing; a nous, added CLI or runtime is refused with `OSError` |

## `/settings` rows

| Page | Row | Key | Kind |
| --- | --- | --- | --- |
| General | Details | `details` | switch |
| General | Chat prefers for $ | `chat.prefer` | pick: `native`, `flow` |
| General | Harness sessions | `harness_sessions` | switch |
| General | Error reports | `enable_sentry` | switch |
| General | What is sent | — | shows the lists |
| Workspace | Default flow | `workspaces.<path>.flow` | read-only |
| Workspace | Chat agent | `workspaces.<path>.chat.agent` | agent sheet |
| Workspace | Forget | deletes `workspaces.<path>` | switch |

Changes are held until saved (the save button, or the question asked on leaving). The pages
Accounts, Runtimes and Fallback edit the other [stores](#stores); the flowverses are edited
on `/flow`. `/settings <page>` opens a page by name: `general`, `accounts`, `nous`,
`runtimes`, `workspace` (also `settings` and `everywhere` for `general`, `directory` for
`workspace`, `environments` for `runtimes`; `flowverses` opens `/flow` on its Flowverses
page). The Workspace page names its directory across its top rather than as a row.
