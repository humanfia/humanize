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
| **machine** (`M` below) | `<tmp>/humanize-<uid>/` | Python's `tempfile.gettempdir()` (`$TMPDIR`, else `/tmp`) and the user's id: what is this machine's alone, which a home directory several machines share must not hold: caches, scratch copies, sockets. Made `0700` by the first look at it; refused if anyone else can write it. A cleaner of temporary files may empty it; everything in it is made again when next needed. See [Temporary](#temporary). |
| **a remote machine's home** | `${HUMANIZE_HOME:-$HOME/.hmz}` in the login shell there | Holds `envs/` for `ssh` environments. A `$HOME/.humanize` there is [moved here](#moved-from-humanize). |

### Moved from `.humanize`

These directories were called `.humanize` before. Each old one is renamed to its new name
the first time humanize looks for it, with no message:

| Old | New | When |
| --- | --- | --- |
| `~/.humanize` | `~/.hmz` | first look at the home in a process; not when `HUMANIZE_HOME` is set |
| `<workspace>/.humanize` | `<workspace>/.hmz` | first look at the workspace's flows, first flow forked into them, or first bundle written there; not when it is `~/.humanize` (moved as the home is) or the directory `HUMANIZE_HOME` names |
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
├── settings.yaml                       everything /settings sets: workspaces, machine settings, fallbacks, added CLIs, runtimes
├── .settings.yaml.lock                 held by each writer of settings.yaml
├── history.jsonl                       lines typed at the TUI prompt
├── providers/<cli>/<name>/             accounts
│   ├── provider.json
│   └── home/ user/ config/             credential files the CLI writes
├── flowverses/<name>/                  one per flowverse, official included
│   ├── index/                          the index clone
│   └── installed/<flow>/               installed flows, each with its .installed.json
├── envs/
│   ├── <workdir-name>-<digest>/{clones,scratch,worktrees}/
│   └── mirrors/<container or service>/<digest>/
└── epics/<ws>/<stamp>-<hex6>/          one run

M/
├── prices.json                         the price table
├── models/<cli>/<account>.json         model catalogues, `_local` for the CLI's own sign-in
├── harness/                            workdir of a harness an affinity puts on a docker daemon here
├── compiled/{pi,qwen}/                 Node compile caches
├── docker-ssh/<sha256[:16]>/ssh        ssh shim for docker over ssh
└── patched/<cli>-<pid>-<rand>/         patched CLI copies (unused in production)

~/.hmz/flows/                      your flows (flowverse `user`)
<workspace>/.hmz/
└── flows/                              this project's flows (flowverse `local`)
```

## Settings and state

### `H/settings.yaml`

[Settings](/reference/settings) is the schema. Written through `hmz.coganchor.settings`: by
`hmz.runtime.settings.Settings`, and by the fallbacks, added CLIs and runtimes.

| Property | Value |
| --- | --- |
| Format | YAML (`yaml.safe_dump`, key order kept); read with `yaml.safe_load` |
| Write | under the lock: re-read, this writer's one change made to it ([rules](/reference/settings#file-behaviour)), written to `.settings.yaml.<random>.new` (mode `0600` for a new file, the existing file's otherwise), fsynced, renamed over |
| Lock | `flock(LOCK_EX)` on `H/.settings.yaml.lock` (`0600`, opened read-only, kept) for each write, waited for up to 30 s and then gone without; released by the kernel if the writer dies. Readers take no lock. |
| Unreadable, missing, not a mapping | read as empty; never an error |
| Write failure, or unreadable at a write | not written over; ignored by `Settings`, `OSError` for a fallback, added CLI or runtime |
| Removed | never; `forget` removes one workspace's entry |

### `H/history.jsonl`

| Property | Value |
| --- | --- |
| Writer | the TUI, on every submitted prompt line |
| Line | `{"at": "%Y-%m-%dT%H:%M:%S.%fZ", "workdir": "<abs path>", "text": "<line>"}` |
| Rules | appended; blank lines and a repeat of the previous line are not written; no size limit |
| Read | at TUI start: this workdir's lines, or every line if it has none |
| Safe to delete | yes |

### `M/prices.json` {#h-prices-json}

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

A cache, so on this machine rather than in `H`:
`$TMPDIR/humanize-<uid>/models/<cli>/<name>.json` for an account, and
`$TMPDIR/humanize-<uid>/models/<cli>/_local.json` for the CLI's own sign-in (no account name
starts with `_`). An account's is deleted when the account is removed:

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

## Flows

### `H/flowverses/<name>/`

One [flowverse](/reference/flows#flowverses): its index clone and the flows installed from it,
side by side. Deleted whole, in one rename, by *remove* (not `official`). A directory here
without `index/` is still listed, as a flowverse with nowhere to fetch from.

### `H/flowverses/<name>/index/`

A `git clone --depth 1` of the flowverse's index: `flows/<flow>/<version>/flow.yaml`. Cloned
into `.index.XXXXXXXX` beside it and renamed into place; a leftover `.index.*` older than 60 s
is removed before the next clone. Fetch is `git fetch --depth 1 origin HEAD` then
`git reset --hard FETCH_HEAD`. The origin URL is read from `.git/config`. Read as YAML, never
imported.

### `H/flowverses/<name>/installed/<flow>/`

A flow installed from that flowverse's index: the release's `subdir` at its commit, without
`.git` and `__pycache__` (a single `<flow>.py` as `__init__.py`), every skill its roles name by
URL fetched into its `skills/<name>/`, and `.installed.json`.
Written into `.<flow>.XXXXXXXX` beside it and renamed into place, the release it replaces moved
aside into that directory first and deleted with it; a leftover `.<flow>.*` older than 600 s is
removed before the next install of that name. Replaced by an update, deleted by uninstall and
by removing the flowverse. Imported where flows are listed and run.

`.installed.json`, written with the copy before the rename, JSON (indented 2):

| Key | Value |
| --- | --- |
| `verse`, `name` | the flowverse and the flow; must match the directories, or it is not read as installed |
| `version`, `commit` | the release, and the commit it was copied from |
| `repo`, `ref`, `subdir` | as the manifest said |
| `dependencies` | `{flow: range}`, as the manifest said; checked by later installs and uninstalls |
| `skills` | `{url: [skill, …]}`: each URL its roles name, to the skills install fetched into its `skills/` for it |

### `~/.hmz/flows/` and `<workspace>/.hmz/flows/`

Flowverses `user` and `local`: `<name>/__init__.py` or `<name>.py`
([Where flows live](/reference/flows#where-flows-live)). humanize writes here only when a flow
is copied here (to `.<name>.*`, then renamed). Never deleted by humanize.

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

### `M/harness/`

An empty directory mounted as the workdir of a harness an affinity puts on a docker runtime
whose daemon is on this machine, or on an Apple container, saved without a workdir
([Harness placement](/reference/flows#harness-placement)): a container needs a directory of
this user's on the host to mount. Created by the run; nothing is written into it by humanize.

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
| `host.log` | runs held by a [host process](/reference/daemon#files) only; appended (`0600`), never rotated | that process's descriptors 1 and 2 while the run is the one it holds: output of the CLIs the run started, and the carrier's failures |
| `.held` | empty, `0600`; `flock`ed exclusively by the process running the run until `ended` is written | a run whose `.held` is locked is still going, and is not [picked up](/reference/cli#picking-a-run-up) |
| `sessions/<cli>/…` | by the CLI itself, redirected | the CLI's own layout |
| `traces/*.trace.json` | on demand; plain write | [Chrome trace](/reference/tracing#document) |

Epics are never deleted by humanize.

## Caches

| Path | Is |
| --- | --- |
| `M/compiled/pi/`, `M/compiled/qwen/` | `NODE_COMPILE_CACHE` for pi and Qwen Code; written by Node |
| `M/docker-ssh/<sha256[:16]>/ssh` | shim for `docker` over `ssh://` with options; directory and file `0700`; touched on each use, written again if gone |
| `M/patched/<cli>-<pid>-<rand>/` | `0700`; directories of dead processes are removed |
| `~/.cache/humanize/shadows/<sha256(path)[:16]>.json` | `{"shadow": "<abs path>", "target": "<target>"}` per mirror; moved by [`HUMANIZE_SHADOWS`](/reference/environment#humanize-shadows); never removed |

Every path in this section is safe to delete while humanize is not running.

## Temporary

| Path | Is | Removed |
| --- | --- | --- |
| `$TMPDIR/hmz-fence-XXXXXXXX/` (`0700`) | a fenced process's `TMPDIR`; `cache/<var>` inside for redirected caches | when the process ends (left on `SIGKILL`) |
| the same path, on a machine a supervised agent's commands run on | that agent's commands' `TMPDIR` there | kept |
| `$TMPDIR/humanize-hook-*/hook.sock`, `humanize-tools-*/tools.sock`, `humanize-preload-*/said.sock` | sockets a CLI reports hooks, tool calls and preload events on | with the session |
| `$TMPDIR/hmz-dsh-*/cordis.yml`, `hmz-qwen-*/` | per-session CLI configuration | with the session |
| `$TMPDIR/humanize-<uid>/pinned/<blake2b-8(url)>/<sha>/` | checkouts of [`git+` refs](/reference/flows#refs), and of the releases [installed](/reference/flows#installing): a full clone with `--no-checkout` into `.<uuid>`, checked out detached at `<sha>`, renamed into place; one per commit | never; cloned again when missing |
| `$TMPDIR/humanize-<uid>/` (`0700`, refused if anyone else can write it): `humanize-<digest>.pyz` (`0700`), `<stamp>.digest` (`0600`) | the humanize bundle copied to other machines, one per source tree it was built from, and which tree built which | any `humanize-*` or `*.digest` in it untouched for 14 days, when another bundle is built; a run touches the one it uses at least hourly |
| `$TMPDIR/humanize-<uid>/skills/<owner>-<repo>-<sha256(url)[:12]>/` | clones of skill repositories a role of a flow that was never installed names by URL ([Skills](/reference/flows#the-skills-a-flow-brings)), fetched again each run that names them | kept |
| `$TMPDIR/humanize-<uid>/daemon.sock`, `daemon.json` (`0600`) | the [daemon](/reference/daemon#files) of this machine and user, which every workspace's runs are reached through: its socket, and `{"pid": int, "started": "%Y-%m-%dT%H:%M:%SZ", "kind": "daemon", "protocol": int}` via `.daemon.json.<random>.new` (`mkstemp`), fsync and rename | when the daemon closes |
| `$TMPDIR/humanize-<uid>/daemon.lock` (`0600`) | `flock(LOCK_EX\|LOCK_NB)` for the daemon's life; released by the kernel on exit. Deleting it under a running daemon allows a second daemon | kept |
| `$TMPDIR/humanize-<uid>/daemon.log` (`0600`) | what belongs to no run: the daemon's stdout and stderr, and a host process's before it holds a run; what belongs to a run is the epic's [`host.log`](#h-epics-ws-stamp-hex6) | kept, never rotated |
| `$TMPDIR/humanize-<uid>/models/<cli>/<name>.json`, `_local.json` | [model catalogues](#model-catalogues) of each account and of the CLI's own sign-in | an account's when it is removed; the rest kept |
| `$TMPDIR/humanize-*` | a docker environment's cid file and machine shadow | with the container |
| `$TMPDIR/humanize-<uid>/.<backend>.<name>.lock` | empty; held with `flock(LOCK_EX)` while containers of a docker or Apple container runtime are sized and started, or services of a swarm counted, created and waited for, so two runs on this machine never allocate from one runtime at once | kept |
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

Nothing prunes `epics/`, worktrees under
`envs/`, snapshot refs, `M/compiled/`, `M/docker-ssh/` or `history.jsonl`.
Delete them by hand; an epic's `sessions/` is the only copy of that run's conversations.
Bundles, here and on other machines, go once nothing has used them for 14 days, and so do the
`$TMPDIR/humanize-<uid>.pyz` and `.stamp` an earlier humanize shared between checkouts.
