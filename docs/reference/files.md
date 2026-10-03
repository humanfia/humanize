# Files

Every file and directory humanize reads or writes: under its home, under a workspace's
`.hmz/`, and elsewhere on this machine and on the machines environments run on.

## Roots

| Root | Path | Notes |
| --- | --- | --- |
| **home** (`H` below) | `$HUMANIZE_HOME`, else `~/.hmz` | Not created in advance; the first writer creates it. The provider stores create every missing level with mode `0700`; other writers leave it at the umask. A `~/.humanize` is [moved here](#moved-from-humanize). |
| **user flows** | `~/.hmz/flows` | Always the literal `~`; does **not** follow `HUMANIZE_HOME`. |
| **workspace** | `<workspace>/.hmz/` | `<workspace>` is the directory `hmz` runs in. Not added to `.gitignore`. A `<workspace>/.humanize/` is [moved here](#moved-from-humanize). |
| **cache** | `~/.cache/humanize/` | Does not follow `HUMANIZE_HOME`. |
| **a remote machine's home** | `${HUMANIZE_HOME:-$HOME/.hmz}` in the login shell there | Holds `envs/` for `ssh` environments. A `$HOME/.humanize` there is [moved here](#moved-from-humanize). |

### Moved from `.humanize`

These directories were called `.humanize` before. Each old one is renamed to its new name
the first time humanize looks for it, with no message:

| Old | New | When |
| --- | --- | --- |
| `~/.humanize` | `~/.hmz` | first look at the home in a process; not when `HUMANIZE_HOME` is set |
| `<workspace>/.humanize` | `<workspace>/.hmz` | first look at the workspace's flows, or first bundle written there; not when it is `~/.humanize` (moved as the home is) or the directory `HUMANIZE_HOME` names |
| `$HOME/.humanize` on an `ssh` machine | `$HOME/.hmz` | when the machine is probed; not when `HUMANIZE_HOME` is set there |

The rename happens only while the new directory does not exist. When both exist, the new one
is used and the old one is left as it is; nothing is merged. A rename that fails (a parent
that cannot be written, a mount point) is not an error: the old directory is just not used.
Snapshots and rewinds leave a workspace's `.humanize/` alone, as they leave its `.hmz/`.

With `HUMANIZE_HOME` set, `~/.humanize` is not moved, so flows of your own still in
`~/.humanize/flows` are not found until you move them to `~/.hmz/flows`.

`<ws>` below is a workspace's absolute resolved path with every character outside
`[A-Za-z0-9]` replaced by `-` (`/home/you/code` → `-home-you-code`; distinct paths can
collide, e.g. `/a/b.c` and `/a/b-c`). Timestamps written into files are UTC,
`%Y-%m-%dT%H:%M:%S.mmmZ`, unless stated.

## Layout

```
H/
├── settings.yaml                       what each workspace was set up to run; machine settings
├── .settings.yaml.lock                 held by each writer of settings.yaml
├── history.jsonl                       lines typed at the TUI prompt
├── fallbacks.json                      where a failed turn goes next
├── acp.json                            CLIs added by hand (ACP)
├── prices.json                         the price table
├── models/<cli>.json                   model catalogue of the CLI's own sign-in
├── providers/<cli>/<name>/             accounts
│   ├── provider.json
│   ├── models.json
│   └── home/ user/ config/             credential files the CLI writes
├── runtimes/                           was env-providers/; moved on first use
│   ├── ssh/<name>/runtime.json
│   ├── docker/<name>/runtime.json, docker/.<name>.lock
│   └── swarm/<name>/runtime.json, swarm/.<name>.lock
├── flowverses/
│   ├── official/  <name>/              git clones
│   └── .pinned/<blake2b-8(url)>/<sha>/ checkouts of git+ refs
├── skills/<owner>-<repo>-<sha256[:12]>/  skill repositories
├── envs/
│   ├── <workdir-name>-<digest>/{clones,scratch,worktrees}/
│   └── mirrors/<container or service>/<digest>/
├── harness/                            workdir of a harness an affinity puts on a docker daemon here
├── epics/<ws>/<stamp>-<hex6>/          one run
├── sessions/<cli>/                     sessions of agents no run drives
├── daemons/<name>-<sha256[:12]>/       the runs host of one workspace
├── compiled/{pi,qwen}/                 Node compile caches
├── docker-ssh/<sha256[:16]>/ssh        ssh shim for docker over ssh
└── patched/<cli>-<pid>-<rand>/         patched CLI copies (unused in production)

~/.hmz/flows/                      your flows (flowverse `user`)
<workspace>/.hmz/
├── flows/                              this project's flows (flowverse `local`)
├── .gitignore                          `*.epic.tar.gz`, written by the first export if absent
└── <epic>.epic.tar.gz                  exported runs
```

## Settings and state

### `H/settings.yaml`

[Settings](/reference/settings) is the schema. Written by `hmz.runtime.settings.Settings`.

| Property | Value |
| --- | --- |
| Format | YAML (`yaml.safe_dump`, key order kept); read with `yaml.safe_load` |
| Write | under the lock: re-read, this writer's one change made to it ([rules](/reference/settings#file-behaviour)), written to `.settings.yaml.<random>.new` (`mkstemp`; mode `0600` for a new file, the existing file's otherwise), fsynced, renamed over |
| Lock | `flock(LOCK_EX)` on `H/.settings.yaml.lock` (`0600`, opened read-only, kept) for each write, waited for up to 30 s and then gone without; released by the kernel if the writer dies. Readers take no lock. |
| Unreadable, missing, not a mapping | read as empty; never an error |
| Write failure | ignored |
| Removed | never; `forget` removes one workspace's entry |

### `H/history.jsonl`

| Property | Value |
| --- | --- |
| Writer | the TUI, on every submitted prompt line |
| Line | `{"at": "%Y-%m-%dT%H:%M:%S.%fZ", "workdir": "<abs path>", "text": "<line>"}` |
| Rules | appended; blank lines and a repeat of the previous line are not written; no size limit |
| Read | at TUI start: this workdir's lines, or every line if it has none |
| Safe to delete | yes |

### `H/fallbacks.json`

[Fallback](/user/settings#fallback) chains. JSON array:

```json
[{"spec": "claude@work/claude-opus-5", "to": ["codex/gpt-5.6-sol", "dsh/deepseek-v4-flash"],
  "tries": 3, "policy": "exponential", "timeout": 600.0}]
```

| Field | Type | |
| --- | --- | --- |
| `spec` | `str` | `CLI[@ACCOUNT]/MODEL` the entry applies to |
| `to` | `[str]` | the chain: where the turn goes next, in order. A plain string, as older versions wrote, reads as that place followed by each place the older rows went on to from it, and is written back as a list |
| `tries` | `int` | retries before falling |
| `policy` | `str` | `none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci` |
| `timeout` | `float` | seconds |

Written to `.fallbacks.json.<random>.new` (`0600`), fsynced and renamed; invalid entries are
dropped on read, and so are places in `to` that cannot be read, name the entry's own `spec`, or
repeat an earlier one.

### `H/acp.json`

CLIs added on the Accounts page, driven over ACP. A JSON object from name to either an argv
list or `{"command": [...], "hosts": [...], "state": [...]}` (`hosts`, `state` are set by
hand: the hosts it may reach with `online` `NONE`, and extra paths it may write). Written to
`.acp.json.<random>.new`, fsynced and renamed; a new file gets the umask's mode, an existing
one keeps its own. Deleting it forgets every added CLI.

### `H/prices.json`

```json
{"source": "https://openllmprices.com/data/prices.json", "etag": "…", "fetched": 1790000000.0,
 "date": "…", "models": {"<id>": {"provider": "…", "name": "…",
   "per_million": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75}}}}
```

Refreshed when older than 24 h, with a conditional GET (a `304` only touches the mtime), from
[`HUMANIZE_PRICES`](/reference/environment#humanize-prices), at most one attempt an hour per
process, 20 s timeout: by the TUI as it opens, in the background; and by every run as it starts
(`hmz exec`, the SDK, the TUI's), in the background unless the run has a finite `cost` limit,
which waits for it before its first turn. Written to `.prices.json.<random>.new`, fsynced and
renamed. Each fetch first deletes any `.prices.json.*.new` or `prices.json.*` (the older
naming) more than 10 min old, left by a process that exited mid-write.

### Model catalogues

`H/models/<cli>.json` (the CLI's own sign-in) and `H/providers/<cli>/<name>/models.json` (an
account):

```json
{"asked": "2026-09-30T05:33:55Z", "models": [{"name": "…", "efforts": ["low", "high"], "swarms": false}]}
```

Asked again after 7 days. Written to `.<file>.<random>.new`, fsynced and renamed; a new file
gets the umask's mode, an existing one keeps its own.

### `H/providers/<cli>/<name>/`

An [account](/reference/providers). `<name>` matches `[A-Za-z0-9][A-Za-z0-9._-]*`.
Directories `0700`.

`provider.json` (`0600` from creation, written to `.provider.json.<random>.new`, fsynced and
renamed):

| Field | Type | |
| --- | --- | --- |
| `cli` | `str` | the CLI (the directory name wins on read) |
| `name` | `str` | the account name (the directory name wins) |
| `way` | `str` | the sign-in way; default `env` |
| `env` | `{str: str}` | variables every turn under it runs with ([Environment](/reference/environment#account-variables)) |
| `args` | `[str]` | extra CLI arguments |
| `made` | `str` | `%Y-%m-%dT%H:%M:%SZ` |

A `fallback` key written by an older version is ignored, and dropped the next time the account
is written.

`home/`, `user/`, `config/` hold the credential files **the CLI itself writes** when it signs
in, redirected from where it would write them at home:

| CLI | Files |
| --- | --- |
| `claude` | `home/.credentials.json`, `home/.claude.json`, `user/.claude.json`, `config/anthropic` |
| `codex` | `home/auth.json` |
| `agy` | `home/antigravity-oauth-token` |
| `grok` | `home/auth.json`, `home/mcp_credentials.json` |
| `kimi` | `home/credentials`, `home/oauth` |
| `pi` | `home/auth.json`, `home/auth.json.lock` |
| `qwen` | `home/oauth_creds.json`, `home/oauth_creds.lock` |
| `opencode`, `mimo` | `home/auth.json`, `home/mcp-auth.json` |
| `cursor-agent` | `home/cli-config.json`, `config/cursor/auth.json`, `user/.cursor/auth.json` |
| `mcode` | `home/config.yaml`, `home/auth` |
| `dsh` | none |

Removing an account deletes its directory.

### `H/local/<cli>.json`

Written by older versions to hold the CLI's own sign-in's account fallback. No longer read;
safe to delete.

### `H/runtimes/`

[Runtimes](/reference/machines#runtimes). Directories `0700`; each
`runtime.json` written to `.runtime.json.<random>.new` (`0600` from creation), fsynced and
renamed. A file that does not validate is skipped.

Formerly `H/env-providers/`, each file `provider.json`. When `H/runtimes/` does not exist, the
first look for it renames `H/env-providers/` to it in one step, locks and all; a
`provider.json` left in a runtime's directory is read where there is no `runtime.json`, and
removed when that runtime is next written. Where both directories exist, `H/env-providers/` is
left alone and not read.

`ssh/<name>/runtime.json`:

| Field | Type |
| --- | --- |
| `backend` | `"ssh"` |
| `name`, `host`, `user`, `identity_file`, `proxy_jump`, `alias`, `config`, `workdir` | `str` |
| `port` | `int` |
| `options` | `{str: str}` |
| `fallback` | `[str]`, each `<backend>:<name>` |
| `made` | `"typed"` or `"imported"` |

`docker/<name>/runtime.json`:

| Field | Type |
| --- | --- |
| `backend` | `"docker"` |
| `name`, `tls_dir`, `image`, `runtime`, `workdir` | `str` |
| `endpoint` | `local`, `unix://…`, `tcp://…`, `ssh://…`, `ssh:<ssh runtime>`, `context:<name>` |
| `run_args`, `gpus`, `fallback` | `[str]` |
| `cpus` | `float` |
| `memory`, `gpu_memory`, `max_containers` | `int` |
| `made` | `"typed"` |

`docker/.<name>.lock`: empty; held with `flock(LOCK_EX)` while containers of that runtime are
sized and started, so two runs never allocate from one runtime at once. Never deleted.

`swarm/<name>/runtime.json`:

| Field | Type |
| --- | --- |
| `backend` | `"swarm"` |
| `name`, `tls_dir`, `image`, `gpu_resource`, `workdir` | `str` |
| `endpoint` | a swarm manager, as a docker runtime's `endpoint` |
| `run_args`, `constraints`, `fallback` | `[str]` |
| `cpus` | `float` |
| `memory`, `max_tasks` | `int` |
| `nodes` | `{str: str}`: a node's host name to a saved ssh runtime's name or `[user@]host[:port]` |
| `made` | `"typed"` |

`swarm/.<name>.lock`: as `docker/.<name>.lock`, held while services of that runtime are
counted, created and waited for until their task runs.

## Flows

### `H/flowverses/<name>/`

A `git clone --depth 1` of a [flowverse](/reference/flows#flowverses). Cloned into
`.<name>.XXXXXXXX` beside it and renamed into place; a leftover `.<name>.*` older than 60 s is
removed before the next clone of that name. Fetch is `git fetch --depth 1 origin HEAD` then
`git reset --hard FETCH_HEAD`. The origin URL is read from `.git/config`. Deleted by *remove*
(not `official`).

### `H/flowverses/.pinned/<blake2b-8(url)>/<sha>/`

Checkouts of [`git+` refs](/reference/flows#refs): a full clone with `--no-checkout` into
`.<uuid>`, checked out detached at `<sha>`, renamed into place. One per commit; never
removed.

### `H/skills/<owner>-<repo>-<sha256(url)[:12]>/`

Clones of skill repositories a role names by URL
([Skills](/reference/flows#the-skills-a-flow-brings)), cloned and refreshed as flowverses are,
each run that names them. Never removed. Mounted skills are copied into the session's
workdir (`.claude/skills`, `.cursor/skills` or `.agents/skills`) for the session's life.

### `~/.hmz/flows/` and `<workspace>/.hmz/flows/`

Flowverses `user` and `local`: `<name>/__init__.py` or `<name>.py`
([Where flows live](/reference/flows#where-flows-live)). humanize writes here only when a flow
is forked (copied to `.<name>.*`, then renamed). Never deleted by humanize.

## Environments

### `<state>/envs/`

On the machine an environment is on; `<state>` is `H` here and
`${HUMANIZE_HOME:-$HOME/.hmz}` over ssh.

| Path | Is | Lifetime |
| --- | --- | --- |
| `envs/<name≤32>-<blake2b(workdir)>/` | everything derived from one workdir | kept |
| `…/clones/<id≤40>-<blake2b(id)>/` | a temporary copy (`cp -a --reflink=auto`) | removed when its call ends, or kept for a resumable run |
| `…/clones/<…>.lock` | `flock(LOCK_EX\|LOCK_NB)` held by the process holding the copy (this machine only) | unlinked on destroy |
| `…/clones/<…>.part.<pid>/`, `….part.gone….<pid>/` | a copy being made; one being removed | transient |
| `…/scratch/<id>-<blake2b(id)>/` | a scratch directory | as copies |
| `…/worktrees/<ref\|head>-<hex8>/` | a `derive_worktree` with no `dir` | **never removed** |
| `envs/mirrors/<container>/<digest>/` | the local mirror of a `docker` environment's workdir | removed with the container |
| `envs/mirrors/<service>/<digest>/` | the local mirror of a `swarm` environment's workdir | removed with the service |

Names are deterministic, so a resumed run finds the same copy. `envs/` may be deleted while
no run uses it. `write` on a local environment goes through `.<hex12>.hmz-tmp` beside the
file, then rename.

**In your repository.** `snapshot` writes refs `refs/hmz/snapshots/<name>` (commits authored
`humanize <humanize@localhost>`) using a temporary index `<index>.hmz-snapshot.<pid>`. Refs are
never removed by humanize.

**Containers.** A `docker` environment's container is named
`humanize-<provider>-<role>-<hex8>` and labelled `humanize=<uid>`, `humanize.provider`,
`humanize.role`, `humanize.host`, `humanize.pid`, and `humanize.cpus`, `humanize.memory`,
`humanize.gpus` where set. Only the workdir is bind-mounted. A `swarm` environment's service is
named and labelled the same way, on the swarm its runtime's manager manages.

### `H/harness/`

The workdir of a harness an affinity puts on a docker runtime whose daemon is on this machine
and that was saved without a workdir ([Harness placement](/reference/flows#harness-placement));
created by the run.

## Runs

### `H/epics/<ws>/<stamp>-<hex6>/`

One run ([Tracing › Epics](/reference/tracing#epics) has every schema). `<stamp>` is
`%Y%m%dT%H%M%S.mmmZ` (UTC), `<hex6>` random. A directory without `epic.jsonl` is not listed.

| File | Written | Format |
| --- | --- | --- |
| `epic.jsonl` | appended per event, open/write/close under a thread lock; no fsync | [events](/reference/tracing#epic-jsonl) |
| `epic.<flow>_<hex6>.jsonl` | one per flow call | [records](/reference/tracing#records-of-called-flows) |
| `resume.jsonl` | resumable runs only; compacted via `.resume.jsonl.<random>.new` + fsync + rename, then appended `O_APPEND` | [journal](/reference/flows#journal) |
| `profile.jsonl` | profiled runs only | [profile](/reference/tracing#profile-jsonl) |
| `.held` | empty, `0600`; `flock`ed exclusively by the process running the run until `ended` is written | a run whose `.held` is locked is still going, and is not [picked up](/reference/cli#picking-a-run-up) |
| `sessions/<cli>/…` | by the CLI itself, redirected | the CLI's own layout |
| `traces/*.trace.json` | on demand; plain write | [Chrome trace](/reference/tracing#document) |

Epics are never deleted by humanize.

### `H/sessions/<cli>/`

Sessions of agents driven with no run (the agent API, `/btw`), laid out as the CLI's home.
Like an epic's `sessions/`, it is the only copy of those conversations. Not used under
[`HUMANIZE_SESSIONS=off`](/reference/environment#humanize-sessions).

### `<workspace>/.hmz/<epic>.epic.tar.gz`

An [exported run](/reference/tracing#export). Written with `mkstemp` (mode `0600`) and renamed;
exporting the same run again replaces it. Nothing in humanize imports one. Exporting here
also writes `<workspace>/.hmz/.gitignore` (`*.epic.tar.gz`) where there is none, so a
`git add -A` in the workspace, an agent's included, does not commit the archive; one already
there is left as it is.

### `H/daemons/<name≤24>-<sha256(workspace)[:12]>/`

The [runs host](/reference/daemon) of one workspace. `<name>` is the workspace directory's
name with each run of characters outside `[A-Za-z0-9]` replaced by `-`, leading and trailing
`-` stripped, cut to 24 characters, and `workspace` where nothing is left.

| File | Mode | Lifetime | Content |
| --- | --- | --- | --- |
| `daemon.sock` | `0600` | removed on stop | Unix socket (reached via `chdir` if the path exceeds 100 bytes) |
| `daemon.json` | `0600` | removed on stop | `{"pid": int, "workspace": str, "started": "%Y-%m-%dT%H:%M:%SZ", "kind": "host", "protocol": int}`, via `.daemon.json.<random>.new` (`mkstemp`), fsync and rename |
| `daemon.lock` | `0600` | kept | `flock(LOCK_EX\|LOCK_NB)` for the daemon's life; released by the kernel on exit |
| `daemon.log` | `0600` | kept, never rotated | the daemon's stdout and stderr |

Deleting `daemon.lock` under a running daemon allows a second daemon for the workspace.

## Caches

| Path | Is |
| --- | --- |
| `H/compiled/pi/`, `H/compiled/qwen/` | `NODE_COMPILE_CACHE` for pi and Qwen Code; written by Node |
| `H/docker-ssh/<sha256[:16]>/ssh` | shim for `docker` over `ssh://` with options; directory and file `0700` |
| `H/patched/<cli>-<pid>-<rand>/` | `0700`; directories of dead processes are removed |
| `~/.cache/humanize/shadows/<sha256(path)[:16]>.json` | `{"shadow": "<abs path>", "target": "<target>"}` per mirror; moved by [`HUMANIZE_SHADOWS`](/reference/environment#humanize-shadows); never removed |

Every path in this section is safe to delete while humanize is not running.

## Temporary

| Path | Is | Removed |
| --- | --- | --- |
| `$TMPDIR/hmz-fence-XXXXXXXX/` (`0700`) | a fenced process's `TMPDIR`; `cache/<var>` inside for redirected caches | when the process ends (left on `SIGKILL`) |
| the same path, on a machine a supervised agent's commands run on | that agent's commands' `TMPDIR` there | kept |
| `$TMPDIR/humanize-hook-*/hook.sock`, `humanize-tools-*/tools.sock`, `humanize-preload-*/said.sock` | sockets a CLI reports hooks, tool calls and preload events on | with the session |
| `$TMPDIR/hmz-dsh-*/cordis.yml`, `hmz-qwen-*/` | per-session CLI configuration | with the session |
| `$TMPDIR/humanize-<uid>/` (`0700`, refused if anyone else can write it): `humanize-<digest>.pyz` (`0700`), `<stamp>.digest` (`0600`) | the humanize bundle copied to other machines, one per source tree it was built from, and which tree built which | anything in it untouched for 14 days, when another bundle is built; a run touches the one it uses at least hourly |
| `$TMPDIR/humanize-*` | a docker environment's cid file and machine shadow | with the container |
| `${XDG_RUNTIME_DIR:-$TMPDIR}/humanize-ssh-<uid>/%C[-<hex8>]` (`0700`) | ssh control sockets ([`HUMANIZE_SSH_REUSE`](/reference/environment#humanize-ssh-reuse)) | 120 s after last use |
| `/dev/shm/hmz-<pid>-<hex16>-*/<n>.<file>` (`0700`/`0600`) | credential copies staged for a turn (≤ 1 MiB each) | on close; dead-pid directories swept |

## On other machines

| Path | Is |
| --- | --- |
| `$HOME/.cache/humanize/humanize-<digest>.pyz` | the humanize bundle on an `ssh` machine (`/tmp/humanize/…` in a container); checked against `<digest>` on arrival and when already there, written to `f.<pid>` and moved into place; every run line touches the one it runs; other `humanize-*.pyz*` untouched for 14 days are removed by the next install |
| `$HOME/.cache/humanize-mirrors/<sha256[:16]>/` on an `ssh` machine; `/tmp/humanize-mirrors/<sha256[:16]>/` in a container | a remote harness's mirror of the workspace |
| `${HUMANIZE_HOME:-$HOME/.hmz}/envs/` | as [above](#state-envs) |
| a `mktemp -d` directory (umask `077`) | per-session files of a native turn, including projected credentials (`0600`); removed after the turn |
| `.humanize-carried/<uuid>` | claim file inside a directory carried to the target |

## Read, never written

| Path | Read for |
| --- | --- |
| `~/.ssh/config` and its `Include`s | importing ssh hosts |
| each CLI's home ([Backend homes](/reference/environment#backend-homes)) | sessions to trace; credentials of `@local`; tally |
| `$DSH_HOME` (`~/.dsh`): `settings.yaml`, `.credentials.yaml`, `.env` | DeepSeek Harness key and endpoint |

Antigravity's permission profiles `hmz-read-only.md`, `hmz-read-only-web.md` and
`hmz-offline.md` are written into Antigravity's own home, `~/.gemini/antigravity-cli/agents/`,
when their content changes.

## Retention

Nothing prunes `epics/`, `sessions/`, `flowverses/.pinned/`, `skills/`, worktrees under
`envs/`, snapshot refs, `compiled/`, `docker-ssh/` or `history.jsonl`.
Delete them by hand; an epic's `sessions/` is the only copy of that run's conversations.
Bundles, here and on other machines, go once nothing has used them for 14 days, and so do the
`$TMPDIR/humanize-<uid>.pyz` and `.stamp` an earlier humanize shared between checkouts.
