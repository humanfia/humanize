---
pageClass: hmz-feature
---

# Providers

Reference for accounts: `hmz.coganchor.providers`. A provider is one named set of credentials
for one coding agent CLI, kept apart from the CLI's own. An agent configured with a provider
runs every turn with that provider's variables and reads and writes its credential files in the
provider's directory. Two agents of one CLI can therefore run as two accounts at once.

## Identity

| Aspect | Rule |
| --- | --- |
| Name | `<cli>/<name>`, e.g. `claude/work`. `<cli>` is the backend's name (any [alias](/reference/agents#backends) is accepted and normalised). |
| `<name>` | `[A-Za-z0-9][A-Za-z0-9._-]*` |
| The machine's own account | `<cli>/` with the empty name, `providers.LOCAL == ""`. Exists for every backend; humanize keeps no credentials for it, and turns under it are the CLI as already signed in. Nothing about it can be set. |
| Chosen with | `-a ROLE=CLI@NAME/MODEL:EFFORT`; `AgentConfig.provider="NAME"`; an agent's sheet in the TUI ([TUI](/reference/tui)) |
| Which CLIs | every built-in backend, and every [ACP CLI](/reference/agents#a-cli-of-your-own) added on this machine (which has only the `env` way) |

| Input | `ValueError` |
| --- | --- |
| a backend no profile answers to | `nosuch: unknown agent` |
| a bad name | `'a/b' is not a valid account name: letters, digits, dot, dash and underscore, starting with a letter or a digit` |
| an agent whose `provider` names no account (raised the first time a turn needs it; a run given one in an `-a` spec is [refused](/reference/cli#what-is-refused-before-anything-runs) before it starts instead) | `<agent id>: no <cli> provider called '<name>'` |

<small>Defined in [`src/hmz/coganchor/providers/store.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/providers/store.py), [`specs/coganchor/providers.md`](https://github.com/humanfia/humanize/blob/main/specs/coganchor/providers.md).</small>

## Storage

The rest of humanize's home is in [Files](/reference/files).

```text
$HUMANIZE_HOME/                         default ~/.hmz
├── providers/<cli>/<name>/             one account
│   ├── provider.json                   what it is
│   ├── models.json                     what it was last found to run
│   ├── home/…                          credential files under the CLI's home
│   ├── user/…                          credential files under the user's home (~/…)
│   └── config/…                        credential files under $XDG_CONFIG_HOME
└── models/<cli>.json                   the machine's own account's catalogue
```

| Rule | |
| --- | --- |
| Modes | Every directory humanize creates on the way to `providers/<cli>/<name>/` and to each credential's parent is `0700`. Every file is written to a file of its own beside it (`.<file>.<random>.new`, mode `0600` from creation), fsynced and renamed into place. |
| Directory name | The backend's canonical name and the account's name. The directory, not the file, decides which backend and name an account has. |
| Unreadable entries | A directory whose `provider.json` is missing or not a JSON object is not listed. |
| Removal | `remove(cli, name)` deletes the whole directory, credentials included. |

### `provider.json`

| Key | Type | Meaning |
| --- | --- | --- |
| `cli` | string | the backend, as named here |
| `name` | string | the account's name |
| `way` | string | the [way](#the-ways-in) it was made by; `env` if missing |
| `env` | object of strings | variables a turn under it is given |
| `args` | array of strings | arguments appended to the backend's command line |
| `made` | string | UTC time made, `YYYY-MM-DDTHH:MM:SSZ` |

```json
{
  "cli": "claude",
  "name": "work",
  "way": "key",
  "env": {"ANTHROPIC_API_KEY": "sk-ant-…"},
  "args": [],
  "made": "2026-09-30T05:49:08Z"
}
```

A `fallback` key written by an older version is ignored, and dropped the next time the account
is written. So is `local/<cli>.json`, which held only that.

### `models.json`

The account's model catalogue, written by `hmz.coganchor.models.ask` when the account is made
and when it is asked again (the `check again` row of the TUI's models sheet). Read by every
prompt. Older than 7 days (`models.STALE`) counts as stale; at start-up the TUI asks again, in
the background, for each installed backend whose machine's-own catalogue is missing or stale.

```json
{"asked": "2026-09-30T05:49:08Z", "models": [{"name": "claude-opus-5", "efforts": ["max", "high"], "swarms": false}]}
```

Where the backend has an [endpoint variable](#gateways) and the account sets it, the catalogue
is the endpoint's `GET {base}/v1/models` (`{base}/models` when the base already ends in a
version such as `/v1`), sent with the account's secret as both `Authorization: Bearer` and
`x-api-key` and `anthropic-version: 2023-06-01`, 20 s timeout, 8 MiB limit, redirects followed
only on the same host and never from `https` down to `http`. An endpoint that does not answer
leaves an endpoint-sourced catalogue in place. Otherwise the CLI is asked (see
[Agents › Models](/reference/agents#models)).

<small>Defined in [`src/hmz/coganchor/providers/store.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/providers/store.py), [`src/hmz/coganchor/models.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/models.py).</small>

## The ways in {#the-ways-in}

A way is one kind of account a backend offers. `ways(cli)` returns the backend's own ways in
order, then `env` for every backend but `dsh`.

`hmz.coganchor.backends.Way`:

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | `str` | what the way is called; recorded as the provider's `way` |
| `about` | `str` | one line describing it |
| `argv` | `tuple[str, ...]` | the backend's own command to run, under the provider's paths, with the terminal handed over; `()` for a way that is only answers. `{VARIABLE}` is filled from the answers. |
| `asks` | `tuple[Asked, ...]` | questions, in order |
| `sets` | `tuple[(str, str), ...]` | variables always set, whatever the answers |
| `args` | `tuple[str, ...]` | arguments appended to every turn's command line, `{VARIABLE}` filled |
| `stdin` | `str` | the variable whose answer is written to `argv`'s stdin |

`hmz.coganchor.backends.Asked`:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `env` | `str` | required | the variable the answer becomes |
| `about` | `str` | required | the question |
| `secret` | `bool` | `False` | drawn as bullets, never shown back |
| `keep` | `bool` | `True` | kept in `env`; `False` for an answer only handed to `argv` |
| `fixed` | `str` | `""` | the answer when none is given |

### Ways by backend

| Backend | Way | Runs | Asks (secret •, not kept ◦, default in parentheses) | Sets |
| --- | --- | --- | --- | --- |
| `claude` | `login` | `claude auth login` | — | |
| | `token` | — | `CLAUDE_CODE_OAUTH_TOKEN` • | |
| | `key` | — | `ANTHROPIC_API_KEY` • | |
| | `gateway` | — | `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` • | |
| | `bedrock` | — | `AWS_PROFILE`, `AWS_REGION` (`us-east-1`) | `CLAUDE_CODE_USE_BEDROCK=1` |
| | `vertex` | — | `ANTHROPIC_VERTEX_PROJECT_ID`, `CLOUD_ML_REGION` (`us-east5`) | `CLAUDE_CODE_USE_VERTEX=1` |
| `agy` | `login` | `agy` (interactive) | — | |
| | `key` | — | `GEMINI_API_KEY` • | |
| | `adc` | — | `GOOGLE_APPLICATION_CREDENTIALS` (a file path) | `AGY_ADC_AUTH=1` |
| `codex` | `login` | `codex login` | — | |
| | `device` | `codex login --device-auth` | — | |
| | `key` | `codex login --with-api-key`, key on stdin | `OPENAI_API_KEY` • ◦ | |
| | `token` | `codex login --with-access-token`, token on stdin | `CODEX_ACCESS_TOKEN` • ◦ | |
| | `gateway` | — | `CODEX_PROVIDER_URL`, `CODEX_PROVIDER_KEY` • | appends `-c` arguments ([below](#gateways)) |
| `cursor-agent` | `login` | `cursor-agent login` | — | |
| | `key` | — | `CURSOR_API_KEY` • | |
| | `gateway` | — | `CURSOR_API_ENDPOINT`, `CURSOR_API_KEY` • | |
| `dsh` | `key` | — | `DEEPSEEK_API_KEY` • | |
| | `gateway` | — | `DEEPSEEK_BASE_URL`, `DEEPSEEK_API_KEY` • | |
| `grok` | `login` | `grok login` | — | |
| | `device` | `grok login --device-auth` | — | |
| | `key` | — | `XAI_API_KEY` • | |
| | `gateway` | — | `GROK_XAI_API_BASE_URL` (models listed at `/models`), `XAI_API_KEY` • | |
| | `oidc` | — | `GROK_OIDC_ISSUER`, `GROK_OIDC_CLIENT_ID` | |
| `kimi` | `login` | `kimi login` | — | |
| | `model` | — | `KIMI_MODEL_NAME`, `KIMI_MODEL_API_KEY` •, `KIMI_MODEL_BASE_URL`, `KIMI_MODEL_PROVIDER_TYPE` (`openai`; `anthropic`, `openai` or `kimi`) | |
| `mcode` | `login` | `mcode login` | — | |
| | `key` | `mcode provider set-minimax-key` | `MCODE_PROVIDER_API_KEY` • | |
| | `gateway` | `mcode provider add --name gateway --base-url {MCODE_GATEWAY_URL} --api-format {MCODE_GATEWAY_FORMAT} --model {MCODE_GATEWAY_MODEL} --api-key-env MCODE_PROVIDER_API_KEY --use` | `MCODE_GATEWAY_URL`, `MCODE_PROVIDER_API_KEY` •, `MCODE_GATEWAY_MODEL` ◦, `MCODE_GATEWAY_FORMAT` ◦ (`openai-completions`; `anthropic-messages`, `openai-completions` or `openai-responses`) | |
| `mimo` | `login` | `mimo auth login` | — | |
| | `key` | — | `XIAOMI_API_KEY` • | |
| `opencode` | `login` | `opencode auth login` | — | |
| | `wellknown` | `opencode auth login {OPENCODE_WELLKNOWN}` | `OPENCODE_WELLKNOWN` ◦ (URL answering at `/.well-known/opencode`) | |
| | `zen` | — | `OPENCODE_API_KEY` • | |
| `pi` | `login` | `pi` (interactive: `/login`, then `/exit`) | — | |
| `qwen` | `login` | `qwen` (interactive: `/auth`, then `/quit`) | — | |
| | `key` | — | `OPENAI_API_KEY` •, `OPENAI_BASE_URL` (`https://dashscope.aliyuncs.com/compatible-mode/v1`) | appends `--auth-type openai` |
| every backend but `dsh`; ACP CLIs | `env` | — | `NAME=VALUE` lines | |

- A model on an `mcode` `gateway` account is named `custom_provider:gateway/<id>`.
- `mcode`'s `config.yaml` is a credential file, so a provider of it holds settings of its own.
- `cursor-agent`'s `cli-config.json` is a credential file and also its settings.

### The `env` way

- `env_of(text)` reads `NAME=VALUE` lines: surrounding whitespace is stripped, blank lines and
  lines starting `#` are skipped, a value may contain `=`. A non-empty line without `=` (or
  with an empty name) raises `ValueError: '<line>' is not NAME=VALUE`.
- Every variable given is kept, whatever its name.

### Making, signing in, rewriting

| Call | Behaviour |
| --- | --- |
| `login.make(cli, name, way, answers=None)` | Fills unanswered questions from `fixed`; keeps answers whose `Asked.keep` is true (all of them for `env`) and are non-empty; adds `sets`; fills `args`; writes the account with `add`. |
| `login.asked(way, given)` | The variables still to be answered: neither given nor `fixed`. |
| `login.sign_in(provider, way, answers=None)` | Runs `argv` (filled) under the provider's credential paths (`hmz internal cred`), environment `os.environ` plus the provider's `env`, writing `answers[way.stdin] + "\n"` to stdin where `stdin` is set. Returns the exit status: `0` for a way with no `argv`, `127` for a CLI not installed. |
| `add(cli, name, way="env", env=None, args=())` | Writes `provider.json`, replacing `way`, `env`, `args` and `made`; leaves credential files in place; makes every credential parent directory. |
| `ready(provider)` | Makes every credential parent directory (`0700`). |
| `remove(cli, name) -> bool` | Deletes the account directory. |

The machine's own account cannot be made, signed in or removed.

<small>Defined in [`src/hmz/coganchor/backends.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/backends.py) (`Way`, `Asked`, `PROFILES`), [`src/hmz/coganchor/providers/login.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/providers/login.py).</small>

## Credential files

`Profile.creds` lists the files a backend's login leaves. An entry is under the backend's home
unless it starts `~/` (the user's home) or `config/` (`$XDG_CONFIG_HOME`, else `~/.config`). A
directory entry covers everything inside it. In the provider's directory the three roots are
`home/`, `user/` and `config/`.

| Backend | Home | Credential files |
| --- | --- | --- |
| `agy` | `~/.gemini/antigravity-cli` (only `HOME` moves it) | `antigravity-oauth-token` |
| `claude` | `$CLAUDE_CONFIG_DIR`, else `~/.claude` | `.credentials.json`, `.claude.json`, `~/.claude.json`, `config/anthropic/` |
| `codex` | `$CODEX_HOME`, else `~/.codex` | `auth.json` |
| `cursor-agent` | `$CURSOR_CONFIG_DIR`, else `~/.cursor` | `cli-config.json`, `config/cursor/auth.json`, `~/.cursor/auth.json` |
| `dsh` | `$DSH_HOME`, else `~/.dsh` | none |
| `grok` | `$GROK_HOME`, else `~/.grok` | `auth.json`, `mcp_credentials.json` |
| `kimi` | `$KIMI_CODE_HOME`, else `~/.kimi-code` | `credentials/`, `oauth/` |
| `mcode` | `$MINIMAX_DATA_DIR`, else `~/.minimax` | `config.yaml`, `auth/` |
| `mimo` | `$XDG_DATA_HOME/mimocode`, else `~/.local/share/mimocode` | `auth.json`, `mcp-auth.json` |
| `opencode` | `$XDG_DATA_HOME/opencode`, else `~/.local/share/opencode` | `auth.json`, `mcp-auth.json` |
| `pi` | `$PI_CODING_AGENT_DIR`, else `~/.pi/agent` | `auth.json`, `auth.json.lock` |
| `qwen` | `$QWEN_HOME`, else `~/.qwen` | `oauth_creds.json`, `oauth_creds.lock` |
| an ACP CLI | none known | none |

`Provider.swaps()` is one `(path the CLI names, path in the provider's directory)` pair per
entry, plus the same pair with symlinks resolved where the resolved path differs. It is empty
for the machine's own account and for a backend with no credential files.

Not covered: a credential that is not a file (a macOS keychain); an opencode or mimocode
console account, which lives in the same SQLite database as its sessions; any path not listed.

### How a credential path is answered

A turn under a provider whose `swaps()` is non-empty is spawned as:

```text
python -Pm hmz internal cred --map=FROM=TO [--map=…] [--keep=FROM=TO …] -- CLI ARGS…
```

`hmz internal cred` runs the CLI under a seccomp-filtered ptrace supervisor that stops only
path-naming syscalls: the same set an anchored supervisor stops, less `execve`, `execveat` and
`connect` ([Remote execution › Interception](/reference/remote-execution#interception)). A
path is matched after `.`, `..` and doubled `/` are resolved and `/proc/<pid>/fd/<n>`, `cwd`,
`exe` and `root` links are followed, as the file itself, as
anything inside a directory entry, or as the same name with a suffix (`.credentials.json.tmp`,
which is how a token is rotated by rename).

| Syscall | Answered with |
| --- | --- |
| `stat`, `lstat`, `newfstatat`, `statx`, `access`, `faccessat`, `faccessat2`, `readlink`, `readlinkat`, and `open`/`openat`/`openat2` without `O_WRONLY`, `O_RDWR`, `O_CREAT`, `O_TRUNC` or `O_APPEND` | a copy in `/dev/shm/hmz-<pid>-<random>/` (directory `0700`, files `0600`), made on first read and re-checked against the provider's file once a second |
| everything else (create, write, truncate, rename, link, unlink, `mknod`, chmod, chown, utime, `setxattr`/`removexattr`, open for writing) | the provider's own file; the copy is dropped |
| `statfs`, `getxattr`/`listxattr` (and their `l` forms), `name_to_handle_at`, `open_tree`, `inotify_add_watch`, `fanotify_mark` | the provider's own file; the copy is kept |
| `chdir`, and reads of directories, lock files, files over 1 MiB, or anything when `/dev/shm` is unusable | the provider's own path |

- A path that cannot be answered fails with `EIO` rather than falling through to the real one;
  an `openat2` with `RESOLVE_BENEATH` or `RESOLVE_IN_ROOT` naming an answered path is refused.
- The copies are removed when the supervisor exits; a killed supervisor's copies are removed
  by whatever killed it, or by the next redirected run on the machine.
- The filter lets other architectures' syscalls through: a 32-bit process below the CLI is not
  intercepted.
- Requires Linux on x86-64 or aarch64 with ptrace permitted. A backend with no credential
  files (`dsh`, ACP CLIs), and a provider whose credentials are only variables on such a
  backend, needs no supervisor for credentials.
- An anchored turn is not wrapped: a process has one tracer, so the anchor is given the same
  pairs as `redirects` and its own supervisor answers them
  ([Remote execution › Where the account lives](/reference/remote-execution#where-the-account-lives)).

<small>Defined in [`src/hmz/coganchor/providers/redirect.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/providers/redirect.py), [`_trace.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/providers/_trace.py), [`_staging.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/providers/_staging.py), [`src/hmz/coganchor/pathcalls.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/pathcalls.py).</small>

### A sign-in that refreshes itself {#a-sign-in-that-refreshes-itself}

Some logins keep a refresh token in their credential file, and each refresh writes a new one and
spends the old one: Codex signed in with ChatGPT (`auth.json`), Claude Code with a subscription
(`.credentials.json`), and the OAuth logins of `cursor-agent`, `kimi`, `opencode`, `mimo`, `pi`
and `qwen`. A spent refresh token presented again is read by the vendor as a stolen one, and the
whole sign-in is revoked, every copy of it included. API keys, gateway tokens and
`CLAUDE_CODE_OAUTH_TOKEN` do not rotate.

So such a file is never copied somewhere it could refresh on its own:

| Where the turn runs | What it refreshes |
| --- | --- |
| This machine, or a supervised anchor | the account's own file: a write is always answered with it, never with a copy |
| A native anchor (`self` in an affinity, or the default where the CLI is there) | a copy on the target, sent only while **no other turn is using the file**, and no other turn may until it is back; when the turn ends, the refreshed copy is written back over the account's file, unless that file changed meanwhile |
| The machine's own sign-in (no `@account`) | never sent anywhere: a CLI on another machine uses that machine's own sign-in |

A file holding `refresh_token`, `refreshToken` or a `"refresh":` key counts as one. Each turn
holds the directory it is in with `flock` for its length: shared by turns using it in place,
exclusive for a native turn sending a copy. Neither waits for the other, since the holder may be
a session open until the run ends; the turn that finds it held the other way is refused with
`… this account signs in with a token that refreshes itself, and another turn is using it …`
(native) or `… and a copy of it is out on another machine for a turn there …` (here), which
is the `contended` fault, tried three times a second apart. Run every role of that account with
its harness here (`local` first in the runtime's affinity), give the native one an account signed in with a key, or sign the CLI in on the host
and use no `@account` there. A filesystem that cannot lock a directory (some NFS) logs
`cannot hold … for this turn` and runs the turn unheld.

If a login was revoked anyway (`refresh token was revoked`, `(refused: that account needs signing
in again)`), sign it in again: `codex login` or `claude auth login` for this machine's own, or
**sign in again** on the account under `/settings accounts`. Nothing else restores it.

<small>Defined in [`src/hmz/coganchor/anchor.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/anchor.py) (`_lending`, `_brought_back`), [`src/hmz/coganchor/_lending.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/_lending.py).</small>

## Where sessions are kept {#where-sessions-are-kept}

The same supervisor keeps each turn's sessions out of the CLI's home, under whatever account
it runs, the machine's own included. Each `Profile.sessions` entry under the CLI's home is
passed as `--keep=FROM=TO`, `TO` being the same relative path under the agent's session
directory:

| Agent | Session directory |
| --- | --- |
| driven by a flow run | the run's epic: `<epic>/sessions/<cli>/…` ([Tracing](/reference/tracing)) |
| driven by hand | `$HUMANIZE_HOME/sessions/<cli>/…` |

A kept path is always answered with the file itself (never a copy), its directories are made
as the CLI writes into them, and an entry may be a glob of one path component.

| CLI | Kept, relative to its home |
| --- | --- |
| `claude` | `projects`, `sessions`, `file-history`, `session-env`, `tasks`, `todos`, `plans` |
| `agy` | `conversations`, `brain`, `annotations`, `implicit`, `presence`, `conversation_summaries.db*`, `jetbox_summaries_proto.pb`, `cache/last_conversations.json` |
| `codex` | `sessions`, `archived_sessions`, `session_index.jsonl`, `state_*.sqlite*`, `thread_history_*.sqlite*`, `goals_*.sqlite*`, `queue_*.sqlite*`, `memories_*.sqlite*`, `thread-writer-locks`, `shell_snapshots` |
| `cursor-agent` | `chats`, `projects/*/agent-transcripts` |
| `dsh` | `sessions`, named to the SDK as its session root (`Profile.told`) rather than supervised |
| `grok` | `sessions`, `active_sessions.*` |
| `kimi` | `sessions`, `session_index.jsonl`, `workspaces.json`, `server/events`, `search-index`, `file-history` |
| `mcode` | `v2/sqlite`, `v2/sessions`, `background-tasks` |
| `mimo` | `mimocode.db*`, `storage` |
| `opencode` | `opencode.db*`, `storage` |
| `pi` | `sessions` |
| `qwen` | `projects`, `tmp`, `file-history` |

Sessions stay where the CLI keeps them, and nothing is supervised for them, when any of these
holds:

- `HUMANIZE_SESSIONS` is `off`, `0` or `no` (credentials are still supervised);
- this machine cannot supervise a turn: not Linux on x86-64/aarch64, or starting a traced
  no-op program fails (the answer is cached; a failure is asked again after a minute);
- the turn is native on a target, or its harness runs on another machine.

MiniMax Code needs its sessions kept to run fenced: see
[Agents › MiniMax Code](/reference/agents#minimax-code).

<small>Defined in [`src/hmz/coganchor/backends.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/backends.py) (`Profile.sessions`, `Profile.kept`), [`src/hmz/coganchor/agents/base.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/base.py) (`KEEPING`, `keeps`, `_keeping`), [`src/hmz/coganchor/providers/redirect.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/providers/redirect.py) (`supervises`).</small>

## A turn under a provider

| Effect | Rule |
| --- | --- |
| Added | `provider.env`, on top of the inherited environment (`agent.environment()`). |
| Appended | `provider.args`, after the CLI's own arguments. Only `codex`'s `gateway` way and `qwen`'s `key` way (`--auth-type openai`) have any. |
| Removed | `agent.hushed()`: every variable the backend would read an account from ([below](#variables-taken-away)), except those `provider.env` sets. |
| Redirected | `provider.swaps()`, as [above](#how-a-credential-path-is-answered). |

An agent with no provider (or the machine's own account) gets none of these: its environment
is left exactly as found. All four apply whichever way the account was made.

### Variables taken away {#variables-taken-away}

`Profile.accounts()` is every variable a way of the backend asks for or sets, plus
`Profile.ambient`. `Profile.hushes()` adds every other name the same credential goes by, from
`backends.ALIKE`:

| One credential | Every name |
| --- | --- |
| Anthropic subscription token | `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_OAUTH_TOKEN` |
| Gemini key | `GEMINI_API_KEY`, `GOOGLE_API_KEY` |
| Moonshot key | `MOONSHOT_API_KEY`, `KIMI_API_KEY` |
| OpenAI base URL | `OPENAI_BASE_URL`, `OPENAI_API_BASE` |
| xAI key | `XAI_API_KEY`, `GROK_CODE_XAI_API_KEY` |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `OPENAI_API_KEY` | one name each |

| Backend | `hushes()` |
| --- | --- |
| `agy` | `AGY_ADC_AUTH`, `CLOUD_CODE_URL`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_GEMINI_BASE_URL` |
| `claude` | `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_CONFIG_DIR`, `ANTHROPIC_CUSTOM_HEADERS`, `ANTHROPIC_MODEL`, `ANTHROPIC_OAUTH_TOKEN`, `ANTHROPIC_VERTEX_PROJECT_ID`, `AWS_PROFILE`, `AWS_REGION`, `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR`, `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_FOUNDRY`, `CLAUDE_CODE_USE_GATEWAY`, `CLAUDE_CODE_USE_VERTEX`, `CLOUD_ML_REGION` |
| `codex` | `CODEX_ACCESS_TOKEN`, `CODEX_API_KEY`, `CODEX_AUTHAPI_BASE_URL`, `CODEX_PROVIDER_KEY`, `CODEX_PROVIDER_URL`, `OPENAI_API_BASE`, `OPENAI_API_KEY`, `OPENAI_BASE_URL` |
| `cursor-agent` | `CURSOR_API_BASE_URL`, `CURSOR_API_ENDPOINT`, `CURSOR_API_KEY`, `CURSOR_API_URL`, `CURSOR_AUTH_TOKEN`, `CURSOR_LOCAL_AGENT_API_KEY` |
| `dsh` | `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_SEARCH_BASE_URL` |
| `grok` | `GROK_AUTH`, `GROK_AUTH_PATH`, `GROK_AUTH_PROVIDER_COMMAND`, `GROK_CLI_CHAT_PROXY_BASE_URL`, `GROK_CODE_XAI_API_KEY`, `GROK_DEFAULT_MODEL`, `GROK_MODELS_BASE_URL`, `GROK_MODELS_LIST_URL`, `GROK_OAUTH2_CLIENT_ID`, `GROK_OAUTH2_ISSUER`, `GROK_OIDC_CLIENT_ID`, `GROK_OIDC_ISSUER`, `GROK_XAI_API_BASE_URL`, `XAI_API_KEY` |
| `kimi` | `KIMI_API_KEY`, `KIMI_BASE_URL`, `KIMI_CODE_BASE_URL`, `KIMI_CODE_CUSTOM_HEADERS`, `KIMI_CODE_OAUTH_HOST`, `KIMI_MODEL_API_KEY`, `KIMI_MODEL_BASE_URL`, `KIMI_MODEL_NAME`, `KIMI_MODEL_PROVIDER_TYPE`, `KIMI_OAUTH_HOST`, `KIMI_REGISTRY_API_KEY`, `MOONSHOT_API_KEY` |
| `mcode` | `MCODE_API_BASE_URL`, `MCODE_AUTH_BASE_URL`, `MCODE_AUTH_PROVIDER`, `MCODE_CLIENT_ID`, `MCODE_GATEWAY_FORMAT`, `MCODE_GATEWAY_MODEL`, `MCODE_GATEWAY_URL`, `MCODE_PROVIDER_API_KEY`, `MCODE_REGION`, `MINIMAX_API_KEY`, `MINIMAX_CN_API_KEY` |
| `mimo` | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `MIMOCODE_AUTH_CONTENT`, `MIMOCODE_CONFIG_CONTENT`, `MIMO_API_KEY`, `OPENAI_API_KEY`, `XIAOMI_API_KEY` |
| `opencode` | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `GITHUB_TOKEN`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `OPENCODE_API_KEY`, `OPENCODE_AUTH_CONTENT`, `OPENCODE_CONFIG_CONTENT`, `OPENCODE_WELLKNOWN`, `OPENROUTER_API_KEY` |
| `pi` | `AI_GATEWAY_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_OAUTH_TOKEN`, `ANT_LING_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_BEARER_TOKEN_BEDROCK`, `AWS_PROFILE`, `AWS_REGION`, `AWS_SECRET_ACCESS_KEY`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_DEPLOYMENT_NAME_MAP`, `AZURE_OPENAI_RESOURCE_NAME`, `BASETEN_API_KEY`, `CEREBRAS_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_KEY`, `CLOUDFLARE_GATEWAY_ID`, `DEEPSEEK_API_KEY`, `FIREWORKS_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GROK_CODE_XAI_API_KEY`, `GROQ_API_KEY`, `KIMI_API_KEY`, `MINIMAX_API_KEY`, `MISTRAL_API_KEY`, `MOONSHOT_API_KEY`, `NVIDIA_API_KEY`, `OPENAI_API_KEY`, `OPENCODE_API_KEY`, `OPENROUTER_API_KEY`, `QWEN_TOKEN_PLAN_API_KEY`, `QWEN_TOKEN_PLAN_CN_API_KEY`, `TOGETHER_API_KEY`, `XAI_API_KEY`, `XIAOMI_API_KEY`, `XIAOMI_TOKEN_PLAN_AMS_API_KEY`, `XIAOMI_TOKEN_PLAN_CN_API_KEY`, `XIAOMI_TOKEN_PLAN_SGP_API_KEY`, `ZAI_API_KEY`, `ZAI_CODING_CN_API_KEY` |
| `qwen` | `OPENAI_API_BASE`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_CODE_MODEL`, `QWEN_MODEL`, `QWEN_OAUTH_MODELS` |
| an ACP CLI | none |

<small>Defined in [`src/hmz/coganchor/backends.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/backends.py) (`Profile.accounts`, `Profile.hushes`, `ALIKE`), [`src/hmz/coganchor/agents/base.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/base.py) (`environment`, `hushed`).</small>

## Gateways {#gateways}

A gateway account points the CLI at an endpoint speaking that CLI's protocol.

| Backend | Gateway way | Endpoint variable (`Profile.endpoint`) |
| --- | --- | --- |
| `claude` | `gateway` | `ANTHROPIC_BASE_URL` |
| `codex` | `gateway` | `CODEX_PROVIDER_URL` |
| `cursor-agent` | `gateway` | none |
| `dsh` | `gateway` | `DEEPSEEK_BASE_URL` |
| `grok` | `gateway` | `GROK_XAI_API_BASE_URL` |
| `kimi` | `model` | `KIMI_MODEL_BASE_URL` |
| `mcode` | `gateway` | none (`mcode provider list --json` is the catalogue) |
| `qwen` | `key` | `OPENAI_BASE_URL` |
| `agy` | `env` with `GOOGLE_GEMINI_BASE_URL` | `GOOGLE_GEMINI_BASE_URL` |

A backend with an endpoint variable has its catalogue read from the endpoint when the account
sets it ([`models.json`](#models-json)). `pi`, `opencode` and `mimo` have none: their models are
named `provider/id`, which an endpoint's ids do not carry.

Codex reads a gateway from configuration, not variables. A turn under a codex `gateway`
account appends, and no `config.toml` is written:

```text
-c model_provider=humanize
-c model_providers.humanize.name=humanize
-c model_providers.humanize.base_url=<CODEX_PROVIDER_URL>
-c model_providers.humanize.env_key=CODEX_PROVIDER_KEY
-c model_providers.humanize.wire_api=responses
```

### Hosts reachable under a cut network

A flow role whose `online` is `NONE` is fenced to the hosts `backends.reachable(profile,
environ)` returns, `environ` being the environment a turn under the account runs with,
`providers.composed(provider, profile)`: this process's own, less every variable the account
hushes and plus the ones it sets. The flow's fence and the agent's own widening of it both read
it there, so a hushed variable opens no host:

1. `Profile.hosts` (see [Agents › Network hosts](/reference/agents#network-hosts));
2. the host (and `:port`, where one is written) of the endpoint variable and of every
   `ambient` variable ending `_URL`, `_BASE`, `_HOST`, `_ENDPOINT`, `_ORIGIN` or `_ISSUER`;
3. for `claude` with `CLAUDE_CODE_USE_BEDROCK`, `…_VERTEX` or `…_FOUNDRY` set, the cloud's
   hosts (below) and the host of `ANTHROPIC_BEDROCK_BASE_URL`, `ANTHROPIC_VERTEX_BASE_URL` or
   `ANTHROPIC_FOUNDRY_BASE_URL`.

| Switch | Hosts | Region variable (default) |
| --- | --- | --- |
| `CLAUDE_CODE_USE_BEDROCK` | `bedrock-runtime.{r}.amazonaws.com`, `bedrock.{r}.amazonaws.com`, `sts.{r}.amazonaws.com` | `AWS_REGION` (`us-east-1`) |
| `CLAUDE_CODE_USE_VERTEX` | `{r}-aiplatform.googleapis.com`, `aiplatform.googleapis.com`, `oauth2.googleapis.com` | `CLOUD_ML_REGION` (`us-east5`) |
| `CLAUDE_CODE_USE_FOUNDRY` | `{r}.services.ai.azure.com` | `ANTHROPIC_FOUNDRY_RESOURCE` (none) |

A region value that is not one DNS label adds no cloud host. Example: a `claude` account with
`ANTHROPIC_BASE_URL=https://gw.example:8443/v1` reaches `api.anthropic.com`,
`platform.claude.com`, `claude.ai` and `gw.example:8443` (that port only).

<small>Defined in [`src/hmz/coganchor/backends.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/backends.py) (`reachable`, `_CLOUDS`), [`src/hmz/coganchor/providers/store.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/providers/store.py) (`composed`, `hushed`), [`src/hmz/coganchor/models.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/models.py) (`_served`, `_listing`).</small>

## One account, several CLIs

A credential is the vendor's, so an account made for one backend can often run another.

| Call | Behaviour |
| --- | --- |
| `serves(one) -> tuple[str, ...]` | The other backends `one` could be copied to: those for which `backends.serves(one.env, backend)` is not `None`, whether or not a copy exists. |
| `backends.serves(env, backend)` | `env` renamed to what `backend` reads, each variable matched by any [alike](#variables-taken-away) name in `backend`'s `accounts()`; `None` if `env` is empty or any variable has no name there. |
| `copies(one, cli, name="")` | Writes the renamed `env` as an account of `cli` under `name` (default `one.name`), overwriting one there. Its `way` is the first `cli` way with no `argv` whose kept asks and sets are exactly those variables, else `env`. |

- A login account holds files, not variables, so it copies nowhere.
- `copies` of an account `cli` cannot run raises `ValueError: claude/work cannot be used with codex`.
- Example: a `claude` `key` account (`ANTHROPIC_API_KEY`) serves `pi`, `opencode` and `mimo`;
  each copy is recorded with way `env`.

The TUI's account form offers an `also for <cli>` row per backend in `serves()`.

## When an account fails

An account does not name another to carry on under. Where a failed turn goes is a
[fallback chain](/user/settings#fallback) written against a *place* (`CLI[@ACCOUNT]/MODEL`), so
moving to another account of the same CLI is a place on that chain, taken in a new
conversation. See [Agents › When a turn fails](/reference/agents#retries).

## Placement of the account

| Arrangement | Where the account is used | Provider variables | Provider credential files |
| --- | --- | --- | --- |
| No anchor | this machine | set on the turn | answered here by `hmz internal cred` |
| Supervised anchor | this machine | set on the agent; `private`, so commands on the target never get them | answered here by the anchor's supervisor |
| Native anchor | the target | sent; `hushes()` removed there with `env -u` | written to a private directory on the target for the turn, where a variable of the backend moves their root; otherwise the turn is refused. A [sign-in that refreshes itself](#a-sign-in-that-refreshes-itself) goes to one turn at a time and comes back refreshed |
| Harness on another machine | the harness machine | not sent | redirected to this machine's paths, which that machine lacks |

See [Remote execution › Where the account lives](/reference/remote-execution#where-the-account-lives).

## Security properties

| Property | Holds |
| --- | --- |
| `provider.json` and credential files readable by others | never: `0600` files in `0700` directories from creation |
| A secret shown by the TUI | never: the Accounts page shows variable names; secret answers are drawn as bullets |
| Another agent's credentials readable by a turn | never through the redirected paths: each turn is answered from its own account's directory |
| A shell-profile key overriding the account | never: `hushes()` is removed from the turn |
| A key passed as argv | never: `stdin` ways write it to the command's stdin |
| A sign-in that refreshes itself held in two places that refresh apart | never, where its directory can be locked: it is used in place by every turn here, or lent to one native turn at a time while no other turn uses it, and written back |
| `Provider.env` values from Python | returned in full to the caller |

## API summary

```python
from hmz.coganchor import providers
from hmz.coganchor.providers import login
```

| `providers.` | |
| --- | --- |
| `Provider(cli, name, way="env", env={}, args=(), made="")` | one account; `.at`, `.swaps()`, `.command(argv)`, `.held()` |
| `LOCAL` | `""` |
| `ENV` | the `env` way |
| `ways(cli)` | the backend's ways, `env` last (not for `dsh`) |
| `providers(cli="")` | every account, or one backend's, by backend then name |
| `find(cli, name)` | one account or `None`; never `None` for `LOCAL` of a known backend |
| `where(cli, name)` | the account's directory |
| `add(cli, name, way="env", env=None, args=())` | write one |
| `ready(provider)` | make its credential directories |
| `remove(cli, name)` | delete one |
| `environ(provider)` | its variables, `{}` for `None` |
| `env_of(text)` | parse `NAME=VALUE` lines |
| `filled(text, answers)` | substitute `{VARIABLE}` |
| `serves(one)`, `copies(one, cli, name="")` | alike accounts |

| `login.` | |
| --- | --- |
| `way_of(cli, name)` | a way by name, or `None` |
| `asked(way, given)` | variables still unanswered |
| `make(cli, name, way, answers=None)` | an account from answers |
| `sign_in(provider, way, answers=None) -> int` | run the way's command under the account's paths |

| On an agent | |
| --- | --- |
| `agent.provider` | `Provider \| None`; `None` for the machine's own account |
| `agent.node()` | the account it is on now, never `None` |
| `agent.environment()` | `provider.env` |
| `agent.hushed()` | `hushes() - provider.env` |

`Hmz().accounts` (`hmz.runtime.doing.accounts.Accounts`) is the same surface as one object,
used by the TUI; see [SDK](/reference/sdk):

| `Hmz().accounts.` | |
| --- | --- |
| `all(cli="")`, `find(cli, name)`, `where(cli, name)` | listing and locating |
| `ways(cli)`, `way(cli, name)`, `asks(way, given)` | the ways in |
| `write(cli, name, way="", env=None, args=())` | write an account as given, running nothing |
| `make(cli, name, way, answers=None)`, `sign_in(provider, way, answers=None)` | make from answers; run the way's command |
| `serves(one)`, `copies(one, cli, name="")` | alike accounts |
| `remove(cli, name)` | delete |
| `env(text)`, `environ(provider)` | `env_of`, `environ` |
| `models(cli, provider="")`, `asked(cli, provider="")`, `stale(cli, provider="")`, `ask(cli, provider="", seconds=None)` | the account's model catalogue |
