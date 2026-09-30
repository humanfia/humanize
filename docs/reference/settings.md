# Settings

Every setting humanize persists: its key, scope, type, default, the file it is stored in, who
writes and reads it, and when a change takes effect. The screen that edits them is
[`/settings`](/reference/tui#menus); the Python object is `Hmz().settings`
(`hmz.runtime.settings.Settings`, internal).

## Stores

| Store | File | Scope | Edited on `/settings` page | Reference |
| --- | --- | --- | --- | --- |
| settings | `H/settings.yaml` | this machine, and per workspace | Settings, Workspace (and `/flow`) | this page |
| accounts | `H/providers/<cli>/<name>/provider.json`, `H/local/<cli>.json`, `H/acp.json` | this machine | Accounts | [Providers](/reference/providers), [Files](/reference/files#h-providers-cli-name) |
| environment providers | `H/env-providers/{ssh,docker}/<name>/provider.json` | this machine | Environments | [Machines](/reference/machines#environment-providers) |
| fallbacks | `H/fallbacks.json` | this machine | Fallback | [Files](/reference/files#h-fallbacks-json) |
| flowverses | `H/flowverses/<name>/` (git clones) | this machine | Flowverses | [Flows](/reference/flows#flowverses) |

`H` is `$HUMANIZE_HOME`, else `~/.humanize`. A workspace is identified by its absolute,
symlink-resolved path.

## `settings.yaml`

```yaml
workspaces:
  /home/you/code:                  # one entry per workspace
    flow: rlar                     # the flow the TUI opens on here
    profile: true                  # profile runs started here
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
        harness: local
enable_sentry: false               # this machine
details: true                      # this machine
btw: claude/claude-opus-5:high     # this machine
```

### Machine settings

| Key | Type | Default (absent) | Written by | Read by | Takes effect |
| --- | --- | --- | --- | --- | --- |
| <span id="enable-sentry"></span>`enable_sentry` | `bool` | absent: *nobody has been asked*; the TUI asks at its first start; everything else reports nothing | the first-start question; `/settings` › Settings › **Error reports** | every process that could report (read once per process) | immediately in the process that changed it; at start elsewhere. [`HUMANIZE_SENTRY`](/reference/environment#humanize-sentry) overrides it for one process without writing it. Reading never writes it. |
| `details` | `bool` (only `true` is on) | `false` | `/settings` › Settings › **Details** | the TUI | immediately: turns show every tool call and all thinking instead of responses only |
| `btw` | `str`: `cli[@account]/model:effort` | `""`: the running flow's first agent | `/settings` › Settings › **/btw agent** | the TUI | the next time `/btw` is entered |

What error reports contain and exclude is listed on `/settings` › Settings › **What is sent**.

### Workspace settings

Under `workspaces.<path>`.

| Key | Type | Default | Written by | Read by | Takes effect |
| --- | --- | --- | --- | --- | --- |
| `flow` | `str`, a listed flow name | absent (`Settings.flow` is `""`); the TUI then opens on `chat` | `/flow` when saved | the TUI at start | next launch |
| `profile` | `bool` | `false` | `/settings` › Workspace › **Profiling** | every run's start (TUI, `hmz exec`, SDK) | the next run; a running run keeps what it started with. See [Profiling](/reference/tracing#profiling-a-run). |
| `flows.<flow>` | mapping | absent | `/flow` when saved | the TUI | see below |

`/settings` › Workspace also shows **Directory** and **Default flow** (read-only), and
**Forget**: on save it deletes this workspace's entry; the TUI already open keeps what it
loaded, and the next launch starts without it.

### Per flow

Under `workspaces.<path>.flows.<flow>`, keyed by the flow's listed name (`rlar`,
`local/twice`, `theirs/rlar`, `humanize1:gen-plan`), so a local flow never inherits the setup
of the flowverse flow it shadows.

| Key | Type | Meaning | Read back |
| --- | --- | --- | --- |
| `agents` | `{role: str}` | each agent role's `cli[@account]/model:effort` (the [`-a`](/reference/flows#a-agents) spec after `<role>=`) | an entry that does not read as `cli[@account]/model:effort` (split at the first `/` and the last `:`) makes the whole `agents` mapping read as absent |
| `envs` | `{role: str}` | each environment role's [`-e`](/reference/flows#e-environments) spec after `<role>=` | any non-string value makes the mapping read as absent |
| `params` | mapping | the params, as JSON | validated through the flow's current params model; a failure reads as not set up |
| `budget` | `{duration, cost, output_tokens, graceful}` | the budget as `Budget.model_dump_json` writes it (`duration` ISO 8601, `cost` `"Infinity"` for unlimited) | validated as a `Budget`; a failure reads as absent |
| `harness` | `str` | the [`-H`](/reference/flows#harness-placement) value; not written for `adaptive` | a non-string reads as `adaptive` |

**Writing.** Saving `/flow` replaces the flow's whole entry and sets `flow`. `agents` is always
written; `envs`, `params`, `budget` and `harness` are written as given, carried over from the
file where the caller passes none, and an empty value erases the key (`harness: ""` → absent).

**Reading.** When the TUI starts a flow without opening `/flow` (a `$flow` line, the default
flow), it uses the remembered setup only if it is complete: the remembered agent roles equal
the flow's declared agent roles; every required environment role is remembered; the params
still validate; a budget is remembered unless the flow runs without one. Otherwise `/flow`
opens to ask. `hmz exec` and `Hmz().run` never read `flows`; they use only their own
arguments.

## File behaviour

| Behaviour | Rule |
| --- | --- |
| Missing, unreadable, invalid YAML, not a mapping | read as empty; never prevents a start |
| Unknown keys | kept at the top level and in a workspace entry; a flow's entry is replaced whole when `/flow` is saved |
| Write | re-read the file; take from it every machine key this writer did not change and every workspace this writer did not read; take from this writer every workspace entry it holds (as it read them, plus its own changes) and every machine key it changed; drop workspaces it forgot; write `.settings.yaml.<random>.new` (mode `0600`); rename over |
| Concurrent writers | no lock. Machine keys and workspaces added since a writer read the file survive its write; a change another writer made since to a workspace entry this writer holds is overwritten by this writer's copy. |
| Write failure | ignored: the setting is not remembered |

## `/settings` rows

| Page | Row | Key | Kind |
| --- | --- | --- | --- |
| Settings | Error reports | `enable_sentry` | switch |
| Settings | What is sent | — | shows the lists |
| Settings | Details | `details` | switch |
| Settings | /btw agent | `btw` | pick |
| Workspace | Directory | — (the workspace path) | read-only |
| Workspace | Default flow | `workspaces.<path>.flow` | read-only |
| Workspace | Profiling | `workspaces.<path>.profile` | switch |
| Workspace | Forget | deletes `workspaces.<path>` | switch |

Changes are held until saved (the save button, or the question asked on leaving). The pages
Accounts, Environments, Fallback and Flowverses edit the other [stores](#stores).
`/settings <page>` opens a page by name: `settings`, `workspace`, `accounts`, `environments`,
`fallback`, `flowverses` (also `everywhere` for `settings`, `directory` for `workspace`).
