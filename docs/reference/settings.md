# Settings

Every setting humanize persists: its key, scope, type, default, the file it is stored in, who
writes and reads it, and when a change takes effect. The screen that edits them is
[`/settings`](/reference/tui#menus); the Python object is `Hmz().settings`
(`hmz.runtime.settings.Settings`, internal).

## Stores

| Store | File | Scope | Edited on `/settings` page | Reference |
| --- | --- | --- | --- | --- |
| settings | `H/settings.yaml` | this machine, and per workspace | Settings, Workspace (and `/flow`) | this page |
| accounts | `H/providers/<cli>/<name>/provider.json`; CLIs added by hand under [`clis`](#clis) in `H/settings.yaml` | this machine | Accounts | [Providers](/reference/providers), [Files](/reference/files#h-providers-cli-name) |
| runtimes | [`runtimes`](#runtimes) in `H/settings.yaml` | this machine | Runtimes | [Machines](/reference/machines#runtimes) |
| fallbacks | [`fallbacks`](#fallbacks) in `H/settings.yaml` | this machine | Fallback | this page |
| flowverses | `H/flowverses/<name>/index/` (index clones), `H/flowverses/<name>/installed/[<user>/]<flow>/` (installed flows) | this machine | none: `/flow` › Flowverses | [Flows](/reference/flows#flowverses) |

`H` is `$HUMANIZE_HOME`, else `~/.hmz`. A workspace is identified by its absolute,
symlink-resolved path.

## `settings.yaml`

```yaml
workspaces:
  /home/you/code:                  # one entry per workspace
    flow: rlar                     # the flow the TUI opens on here
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
        profile: true              # profile a run of it started from the TUI
        harness: local
enable_sentry: false               # this machine
details: true                      # this machine
btw: claude/claude-opus-5:high     # this machine
spelling: 2                        # how envs are spelled; written with every change
naming: 2                          # how flows are named; written with every change
fallbacks:                         # this machine; the Fallback page
- spec: claude@work/claude-opus-5
  to: [codex/gpt-5.6-sol, dsh/deepseek-v4-flash]
  tries: 3
  policy: exponential
  timeout: 600.0
clis:                              # this machine; added on the Accounts page
  my-agent: [my-agent, --acp]
runtimes:                          # this machine; the Runtimes page
  ssh:
    gpu-box: {host: 10.0.0.2, user: you, port: 0, ...}
```

### Machine settings

| Key | Type | Default (absent) | Written by | Read by | Takes effect |
| --- | --- | --- | --- | --- | --- |
| <span id="enable-sentry"></span>`enable_sentry` | `bool` | absent: *nobody has been asked*; the TUI asks at its first start; everything else reports nothing | the first-start question; `/settings` › Settings › **Error reports** | every process that could report (read once per process) | immediately in the process that changed it; at start elsewhere. [`HUMANIZE_SENTRY`](/reference/environment#humanize-sentry) overrides it for one process without writing it. Reading never writes it. |
| `details` | `bool` (only `true` is on) | `false` | `/settings` › Settings › **Details** | the TUI | immediately: turns show every tool call and all thinking instead of responses only |
| `btw` | `str`: `cli[@account]/model:effort` | `""`: the running flow's first agent | `/settings` › Settings › **/btw agent** | the TUI | the next time `/btw` is entered |
| <span id="spelling"></span>`spelling` | `int` | absent: written before `-e` wrote `@` only before a provider | every write of the file, as `2` | every process, as it reads the file | absent, `envs` are read as their old spelling meant and rewritten once; `2`, as written |
| <span id="naming"></span>`naming` | `int` | absent: written before flows of other places than `official` were named after an `@` | every write of the file, as `2` | every process, as it reads the file | absent, every workspace's `flow` and `flows` keys said as before (`local/x`, `user/x`, `<flowverse>/x` for a flowverse there is, `official/x`) are renamed once (`@local/x`, `@user/x`, `@<flowverse>/x`, `x`); `2`, as written |

What error reports contain and exclude is listed on `/settings` › Settings › **What is sent**.

### Workspace settings

Under `workspaces.<path>`.

| Key | Type | Default | Written by | Read by | Takes effect |
| --- | --- | --- | --- | --- | --- |
| `flow` | `str`, a listed flow name | absent (`Settings.flow` is `""`); the TUI then opens on `chat` | `/flow` when saved | the TUI at start | next launch |
| `flows.<flow>` | mapping | absent | `/flow` when saved | the TUI | see below |

`/settings` › Workspace also shows **Directory** and **Default flow** (read-only), and
**Forget**: on save it deletes this workspace's entry; the TUI already open keeps what it
loaded, and the next launch starts without it.

### Per flow

Under `workspaces.<path>.flows.<flow>`, keyed by the flow's listed name (`rlar`,
`alice/kernel`, `@local/twice`, `@theirs/review`, `humanize1:gen-plan`), so a local flow never
inherits the setup of the built-in or installed flow it shadows. One kept under a name from
before the `@` is renamed once: see [`naming`](#naming).

| Key | Type | Meaning | Read back |
| --- | --- | --- | --- |
| `agents` | `{role: str}` | each agent role's `cli[@account]/model:effort` (the [`-a`](/reference/flows#a-agents) spec after `<role>=`) | an entry that does not read as `cli[@account]/model:effort` (split at the first `/` and the last `:`) makes the whole `agents` mapping read as absent |
| `envs` | `{role: str}` | each environment role's [`-e`](/reference/flows#e-environments) spec after `<role>=` | any non-string value makes the mapping read as absent; in a file with no [`spelling`](#spelling), a spec in the spelling `-e` refuses with a hint (`local@/x`, `docker@local/x`, `swarm@local/x`, `apple-container@local/x`, an unsaved ssh host out of brackets) is rewritten in the one the hint gives, in every workspace, when the file is first read |
| `params` | mapping | the params, as JSON | validated through the flow's current params model; a failure reads as not set up |
| `budget` | `{duration, cost, output_tokens, graceful}` | the budget as `Budget.model_dump_json` writes it (`duration` ISO 8601, `cost` `"Infinity"` for unlimited) | validated as a `Budget`; a failure reads as absent |
| `profile` | `bool`, written only as `true` | whether a run of the flow started from the TUI is [profiled](/reference/tracing#profiling-a-run), set on the `/flow` menu's **profiling** row | anything but `true` reads as off |

**Writing.** Saving `/flow` replaces the flow's whole entry and sets `flow`. `agents` is always
written; `envs`, `params`, `budget` and `profile` are written as given, carried over from
the file where the caller passes none, and an empty value (or `profile` off) erases the key. A `harness` key an older
humanize wrote is dropped at the next save.

**Reading.** When the TUI starts a flow without opening `/flow` (a `$flow` line, the default
flow), it uses the remembered setup only if it is complete: the remembered agent roles equal
the flow's declared agent roles; every required environment role is remembered; the params
still validate; a budget is remembered unless the flow runs without one. Otherwise `/flow`
opens to ask. `profile` goes with the rest. `hmz exec` and `Hmz().run` never read `flows`; they
use only their own arguments (`--profile`, `profile=True`).

### `fallbacks`

[Fallback](/user/settings#fallback) chains, written by `/settings` › Fallback and
`Hmz().fallbacks`. A list, one entry per place:

| Field | Type | |
| --- | --- | --- |
| `spec` | `str` | `CLI[@ACCOUNT]/MODEL` the entry applies to |
| `to` | `[str]` | the chain: where the turn goes next, in order |
| `tries` | `int` | retries before falling |
| `policy` | `str` | `none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci` |
| `timeout` | `float` | seconds |

Invalid entries are dropped on read, and so are places in `to` that cannot be read, name the
entry's own `spec`, or repeat an earlier one.

### `clis`

CLIs added on the Accounts page, driven over ACP. A mapping from name to either an argv list
or `{command: [...], hosts: [...], state: [...]}` (`hosts`, `state` are set by hand: the hosts
it may reach with `online` `NONE`, and extra paths it may write). Removing the key forgets
every added CLI.

### `runtimes`

[Runtimes](/reference/machines#runtimes), written by `/settings` › Runtimes and
`Hmz().runtimes`: `runtimes.<backend>.<name>`, `<backend>` `ssh`, `docker`, `swarm` or
`apple-container`. The backend and the name are where the entry is, whatever it says; an
entry that does not validate is skipped.

`ssh`:

| Field | Type |
| --- | --- |
| `host`, `user`, `identity_file`, `proxy_jump`, `alias`, `config`, `workdir` | `str` |
| `port` | `int` |
| `options` | `{str: str}` |
| `fallback`, `affinity` | `[str]`, each `<backend>:<name>` (`affinity` also `self`, `local`) |
| `made` | `"typed"` or `"imported"` |

`docker`:

| Field | Type |
| --- | --- |
| `tls_dir`, `image`, `runtime`, `workdir` | `str` |
| `endpoint` | `local`, `unix://…`, `tcp://…`, `ssh://…`, `ssh:<ssh runtime>`, `context:<name>` |
| `run_args`, `gpus`, `fallback`, `affinity` | `[str]` |
| `cpus` | `float` |
| `memory`, `gpu_memory`, `max_containers` | `int` |
| `made` | `"typed"` |

`swarm`:

| Field | Type |
| --- | --- |
| `tls_dir`, `image`, `gpu_resource`, `workdir` | `str` |
| `endpoint` | a swarm manager, as a docker runtime's `endpoint` |
| `run_args`, `constraints`, `fallback`, `affinity` | `[str]` |
| `cpus` | `float` |
| `memory`, `max_tasks` | `int` |
| `nodes` | `{str: str}`: a node's host name to a saved ssh runtime's name or `[user@]host[:port]` |
| `made` | `"typed"` |

`apple-container`: `image`, `workdir` (`str`), `run_args`, `fallback`, `affinity` (`[str]`),
`cpus` (`float`), `memory`, `max_containers` (`int`), `made` (`"typed"`).

## File behaviour

| Behaviour | Rule |
| --- | --- |
| Missing, unreadable, invalid YAML, not a mapping | read as empty; never prevents a start |
| Unknown keys | kept at the top level and in a workspace entry; a flow's entry is replaced whole when `/flow` is saved |
| Write | each change is written at once: take `flock(LOCK_EX)` on `.settings.yaml.lock` beside the file; re-read the file; make this one change to what it holds now (one machine key, one workspace's `flow` and one flow's entry, one workspace removed, or the whole of `fallbacks`, `clis` or one runtime); write `.settings.yaml.<random>.new` (mode `0600` for a new file, the existing file's otherwise), fsync, rename over; release the lock. The writer then holds what it wrote. A file that exists but does not read as a mapping is never written over: it is left for whoever is editing it to correct. |
| Concurrent writers | serialized by the lock. A write changes only what it is about: every machine key, workspace, workspace key and flow entry another writer wrote survives it, whenever this writer read the file. `envs`, `params`, `budget` and `profile` not handed to a `/flow` save are carried over from the file as it is at the write. Two writes to the same key or the same flow's entry: the later wins. A writer that cannot open the lock file, gets an error from `flock`, or has waited 30 s for it writes without it. |
| Write failure, or a file that does not read as a mapping | a `Settings` holds the change in memory and writes nothing; a fallback, added CLI or runtime is refused with `OSError` |

## `/settings` rows

| Page | Row | Key | Kind |
| --- | --- | --- | --- |
| General | Details | `details` | switch |
| General | /btw agent | `btw` | pick |
| General | Error reports | `enable_sentry` | switch |
| General | What is sent | — | shows the lists |
| Workspace | Default flow | `workspaces.<path>.flow` | read-only |
| Workspace | Forget | deletes `workspaces.<path>` | switch |

Changes are held until saved (the save button, or the question asked on leaving). The pages
Accounts, Runtimes and Fallback edit the other [stores](#stores); the flowverses are edited
on `/flow`. `/settings <page>` opens a page by name: `general`, `accounts`, `fallback`,
`runtimes`, `workspace` (also `settings` and `everywhere` for `general`, `directory` for
`workspace`, `environments` for `runtimes`; `flowverses` opens `/flow` on its Flowverses
page). The Workspace page names its directory across its top rather than as a row.
