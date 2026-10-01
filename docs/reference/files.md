# Files

Every file and directory humanize reads or writes: under its home, under a workspace's
`.humanize/`, and elsewhere on this machine and on the machines environments run on.

## Roots

| Root | Path | Notes |
| --- | --- | --- |
| **home** (`H` below) | `$HUMANIZE_HOME`, else `~/.humanize` | Not created in advance; the first writer creates it. The provider stores create every missing level with mode `0700`; other writers leave it at the umask. |
| **user flows** | `~/.humanize/flows` | Always the literal `~`; does **not** follow `HUMANIZE_HOME`. |
| **workspace** | `<workspace>/.humanize/` | `<workspace>` is the directory `hmz` runs in. Not added to `.gitignore`. |
| **cache** | `~/.cache/humanize/` | Does not follow `HUMANIZE_HOME`. |
| **a remote machine's home** | `${HUMANIZE_HOME:-$HOME/.humanize}` in the login shell there | Holds `envs/` for `ssh` environments. |

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
├── local/<cli>.json                    fallback of the CLI's own sign-in
├── providers/<cli>/<name>/             accounts
│   ├── provider.json
│   ├── models.json
│   └── home/ user/ config/             credential files the CLI writes
├── env-providers/
│   ├── ssh/<name>/provider.json
│   └── docker/<name>/provider.json, docker/.<name>.lock
├── flowverses/
│   ├── official/  <name>/              git clones
│   └── .pinned/<blake2b-8(url)>/<sha>/ checkouts of git+ refs
├── skills/<owner>-<repo>-<sha256[:12]>/  skill repositories
├── envs/
│   ├── <workdir-name>-<digest>/{clones,scratch,worktrees}/
│   └── mirrors/<container>/<digest>/
├── harness/                            workdir of a standalone harness on docker's default here
├── epics/<ws>/<stamp>-<hex6>/          one run
├── sessions/<cli>/                     sessions of agents no run drives
├── daemons/<name>-<sha256[:12]>/       the runs host of one workspace
├── compiled/{pi,qwen}/                 Node compile caches
├── docker-ssh/<sha256[:16]>/ssh        ssh shim for docker over ssh
└── patched/<cli>-<pid>-<rand>/         patched CLI copies (unused in production)

~/.humanize/flows/                      your flows (flowverse `user`)
<workspace>/.humanize/
├── flows/                              this project's flows (flowverse `local`)
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
[{"spec": "claude@work/claude-opus-5", "to": "codex/gpt-5.6-sol",
  "tries": 3, "policy": "exponential", "timeout": 600.0}]
```

| Field | Type | |
| --- | --- | --- |
| `spec` | `str` | `CLI[@ACCOUNT]/MODEL` the entry applies to |
| `to` | `str` | where the turn goes next |
| `tries` | `int` | retries before falling |
| `policy` | `str` | `none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci` |
| `timeout` | `float` | seconds |

Written to `.fallbacks.json.<random>.new` (`0600`), fsynced and renamed; invalid entries are
dropped on read.

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

Refreshed by the TUI when older than 24 h, with a conditional GET (a `304` only touches the
mtime), from [`HUMANIZE_PRICES`](/reference/environment#humanize-prices). Written to
`prices.json.<pid>` and renamed. `hmz exec` reads it and never fetches.

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
| `fallback` | `str` | the account to fall back to |

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

`{"fallback": "<account>"}` for the CLI's own sign-in (`@local`). `0600`, directory `0700`.

### `H/env-providers/`

[Environment providers](/reference/machines#environment-providers). Directories `0700`; each
`provider.json` written to `.provider.json.<random>.new` (`0600` from creation), fsynced and
renamed. A file that does not validate is skipped.

`ssh/<name>/provider.json`:

| Field | Type |
| --- | --- |
| `backend` | `"ssh"` |
| `name`, `host`, `user`, `identity_file`, `proxy_jump`, `alias`, `config`, `workdir` | `str` |
| `port` | `int` |
| `options` | `{str: str}` |
| `made` | `"typed"` or `"imported"` |

`docker/<name>/provider.json`:

| Field | Type |
| --- | --- |
| `backend` | `"docker"` |
| `name`, `tls_dir`, `image`, `runtime`, `workdir` | `str` |
| `endpoint` | `local`, `unix://…`, `tcp://…`, `ssh://…`, `ssh:<provider>`, `context:<name>` |
| `run_args`, `gpus` | `[str]` |
| `cpus` | `float` |
| `memory`, `gpu_memory`, `max_containers` | `int` |
| `made` | `"typed"` |

`docker/.<name>.lock`: empty; held with `flock(LOCK_EX)` while containers of that provider are
sized and started, so two runs never allocate from one provider at once. Never deleted.

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

### `~/.humanize/flows/` and `<workspace>/.humanize/flows/`

Flowverses `user` and `local`: `<name>/__init__.py` or `<name>.py`
([Where flows live](/reference/flows#where-flows-live)). humanize writes here only when a flow
is forked (copied to `.<name>.*`, then renamed). Never deleted by humanize.

## Environments

### `<state>/envs/`

On the machine an environment is on; `<state>` is `H` here and
`${HUMANIZE_HOME:-$HOME/.humanize}` over ssh.

| Path | Is | Lifetime |
| --- | --- | --- |
| `envs/<name≤32>-<blake2b(workdir)>/` | everything derived from one workdir | kept |
| `…/clones/<id≤40>-<blake2b(id)>/` | a temporary copy (`cp -a --reflink=auto`) | removed when its call ends, or kept for a resumable run |
| `…/clones/<…>.lock` | `flock(LOCK_EX\|LOCK_NB)` held by the process holding the copy (this machine only) | unlinked on destroy |
| `…/clones/<…>.part.<pid>/`, `….part.gone….<pid>/` | a copy being made; one being removed | transient |
| `…/scratch/<id>-<blake2b(id)>/` | a scratch directory | as copies |
| `…/worktrees/<ref\|head>-<hex8>/` | a `derive_worktree` with no `dir` | **never removed** |
| `envs/mirrors/<container>/<digest>/` | the local mirror of a `docker` environment's workdir | removed with the container |

Names are deterministic, so a resumed run finds the same copy. `envs/` may be deleted while
no run uses it. `write` on a local environment goes through `.<hex12>.hmz-tmp` beside the
file, then rename.

**In your repository.** `snapshot` writes refs `refs/hmz/snapshots/<name>` (commits authored
`humanize <humanize@localhost>`) using a temporary index `<index>.hmz-snapshot.<pid>`. Refs are
never removed by humanize.

**Containers.** A `docker` environment's container is named
`humanize-<provider>-<role>-<hex8>` and labelled `humanize=<uid>`, `humanize.provider`,
`humanize.role`, `humanize.host`, `humanize.pid`, and `humanize.cpus`, `humanize.memory`,
`humanize.gpus` where set. Only the workdir is bind-mounted.

### `H/harness/`

The default workdir of `-H standalone:docker@local`
([Harness placement](/reference/flows#harness-placement)); created by the run.

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
| `sessions/<cli>/…` | by the CLI itself, redirected | the CLI's own layout |
| `traces/*.trace.json` | on demand; plain write | [Chrome trace](/reference/tracing#document) |

Epics are never deleted by humanize.

### `H/sessions/<cli>/`

Sessions of agents driven with no run (the agent API, `/btw`), laid out as the CLI's home.
Like an epic's `sessions/`, it is the only copy of those conversations. Not used under
[`HUMANIZE_SESSIONS=off`](/reference/environment#humanize-sessions).

### `<workspace>/.humanize/<epic>.epic.tar.gz`

An [exported run](/reference/tracing#export). Written with `mkstemp` (mode `0600`) and renamed;
exporting the same run again replaces it. Nothing in humanize imports one.

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
| `${HUMANIZE_HOME:-$HOME/.humanize}/envs/` | as [above](#state-envs) |
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
