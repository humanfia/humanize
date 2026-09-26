# Providers

A provider is an **account**: one named set of credentials for one coding agent CLI, kept apart
from the CLI's own. Two agents driving the same CLI can run as two accounts at once. An agent
with no provider runs its CLI signed in the way you signed it in yourself.

| | |
| --- | --- |
| **Named** | `<cli>/<name>`, such as `claude/work`. `<cli>/` with no name is the account this machine is already signed into. |
| **Kept in** | `~/.humanize/providers/<cli>/<name>/`, or under `$HUMANIZE_HOME` where that is set |
| **Made at** | `/providers` and <kbd>a</kbd>, or [`Hmz().accounts`](/reference/sdk) from Python |
| **Chosen with** | `-a role=CLI@NAME/MODEL:EFFORT`, or `provider="NAME"` on an agent's config |
| **A turn under one** | Gets the provider's variables and loses the backend's other account variables. Its credential paths are answered out of the provider's directory. |

Two accounts of one CLI in one run: one signed into an Anthropic subscription, one pointed at a
DeepSeek endpoint, and [flame_chase](/flows/flame-chase) handing the task to each in turn.

```sh
hmz exec -f flame_chase \
    -a first_chaser=claude@anthropic/claude-opus-5:max \
    -a second_chaser=claude@deepseek/deepseek-chat:high \
    -b cost=20 "fix the build"
```

Both agents run the same `claude`. Neither can read the other's credential file, and neither
can read yours.

## Where the credentials are kept

```
~/.humanize/providers/claude/deepseek/
├── provider.json      its way in, its variables, its fallback
├── models.json        the models it was last found to offer
├── home/              credential files under the CLI's own home
│   ├── .credentials.json
│   └── .claude.json
├── user/              credential files under your home
│   └── .claude.json
└── config/            credential files under $XDG_CONFIG_HOME
    └── anthropic/
```

The CLI writes these files itself, so they keep the names it gave them. A login for a provider
is the CLI's own login, with those paths pointed here.

**Only credential files live here.** Sessions, settings and skills stay in the CLI's own home,
so a turn under a provider still shows up in a [trace](/reference/tracing), still counts
towards the cost readout, and still has the skills you installed.

### Per backend

A path is under the backend's home unless it starts `~/` (your home) or `config/`
(`$XDG_CONFIG_HOME`, else `~/.config`). A path ending `/` is a directory, and everything inside
it goes with it. The home is read from humanize's own environment.

| Backend | Home | Credential files |
| --- | --- | --- |
| `agy` | `~/.gemini/antigravity-cli` | `antigravity-oauth-token` |
| `claude` | `$CLAUDE_CONFIG_DIR`, else `~/.claude` | `.credentials.json`<br>`.claude.json`<br>`~/.claude.json`<br>`config/anthropic/` |
| `codex` | `$CODEX_HOME`, else `~/.codex` | `auth.json` |
| `cursor-agent` | `$CURSOR_CONFIG_DIR`, else `~/.cursor` | `cli-config.json`<br>`auth.json` |
| `dsh` | `$DSH_HOME`, else `~/.dsh` | none: its accounts are variables |
| `grok` | `$GROK_HOME`, else `~/.grok` | `auth.json`<br>`mcp_credentials.json` |
| `kimi` | `$KIMI_CODE_HOME`, else `~/.kimi-code` | `credentials/`<br>`oauth/` |
| `mimo` | `$XDG_DATA_HOME/mimocode`, else `~/.local/share/mimocode` | `auth.json`<br>`mcp-auth.json` |
| `opencode` | `$XDG_DATA_HOME/opencode`, else `~/.local/share/opencode` | `auth.json`<br>`mcp-auth.json` |
| `pi` | `$PI_CODING_AGENT_DIR`, else `~/.pi/agent` | `auth.json`<br>`auth.json.lock` |
| `qwen` | `$QWEN_HOME`, else `~/.qwen` | `oauth_creds.json`<br>`oauth_creds.lock` |
| `zcode` | `~/.zcode` | `v2/credentials.json` |

- For `agy` and `zcode`, humanize follows no variable of the backend's own: only `HOME`
  moves where it looks. `ZCODE_DATA_BASE_DIR`, which moves ZCode's `v2/`, is taken away from
  a turn under a provider.
- `agy`'s token file is what a sign-in leaves where there is no keyring to put it in.
- `codex`'s `auth.json` holds subscription tokens and an API key alike.
- `cursor-agent`'s `cli-config.json` also holds its settings, such as what the agent may
  reach for, so a provider of it keeps settings of its own.
- `grok`'s `mcp_credentials.json` holds the tokens its MCP servers handed back.
- `zcode`'s file is shared with the ZCode desktop app, and encrypted with a key derived from
  this machine and this user.
- An ACP CLI added at `/providers` has no credential files humanize knows of, so its accounts
  are variables.

## The ways in

A way is one kind of account: a subscription you sign into, a key, a gateway, an account on a
cloud. `/providers` offers a backend's ways once you pick the CLI, and
`Hmz().accounts.ways(cli)` returns the same list.

| Backend | `login` | `device` | `key` | `gateway` | Also | `env` |
| --- | :-: | :-: | :-: | :-: | --- | :-: |
| [`agy`](#antigravity-cli-agy) | ✓ | | ✓ | | `adc` | ✓ |
| [`claude`](#claude-code-claude) | ✓ | | ✓ | ✓ | `token`, `bedrock`, `vertex` | ✓ |
| [`codex`](#codex-codex) | ✓ | ✓ | ✓ | ✓ | `token` | ✓ |
| [`cursor-agent`](#cursor-agent-cursor-agent) | ✓ | | ✓ | ✓ | | ✓ |
| [`dsh`](#deepseek-harness-dsh) | | | ✓ | ✓ | | |
| [`grok`](#grok-build-grok) | ✓ | ✓ | ✓ | ✓ | `oidc` | ✓ |
| [`kimi`](#kimi-code-kimi) | ✓ | | | | `model` | ✓ |
| [`mimo`](#mimocode-mimo) | ✓ | | ✓ | | | ✓ |
| [`opencode`](#opencode-opencode) | ✓ | | | | `wellknown`, `zen` | ✓ |
| [`pi`](#pi-pi) | ✓ | | | | | ✓ |
| [`qwen`](#qwen-code-qwen) | ✓ | | ✓ | | | ✓ |
| [`zcode`](#zcode-zcode) | ✓ | ✓ | ✓ | ✓ | | ✓ |

A way that **runs** a command runs it on this terminal, under the provider's paths, and what
the command writes is the provider. A way that only **asks** keeps your answers as the
variables the backend reads them under. Every key and token is asked as a secret: drawn as
bullets and never shown back. A value in parentheses is what an unanswered question takes.

### Antigravity CLI (`agy`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | Sign in to a Google account. Runs `agy` and hands you the terminal. | — |
| `key` | A Gemini API key, from AI Studio. | `GEMINI_API_KEY` |
| `adc` | Google Application Default Credentials, for a service account. Also sets `AGY_ADC_AUTH=1`. | `GOOGLE_APPLICATION_CREDENTIALS`, the file's path |

### Claude Code (`claude`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | Sign in to an Anthropic account. Runs `claude auth login`. | — |
| `token` | A long-lived token, as `claude setup-token` prints one. | `CLAUDE_CODE_OAUTH_TOKEN` |
| `key` | An Anthropic API key, from the console. | `ANTHROPIC_API_KEY` |
| `gateway` | An endpoint speaking Claude Code's protocol: a proxy, a router, another vendor. | `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` |
| `bedrock` | Anthropic's models on your AWS account. Also sets `CLAUDE_CODE_USE_BEDROCK=1`. | `AWS_PROFILE`, `AWS_REGION` (`us-east-1`) |
| `vertex` | Anthropic's models on your Google Cloud project. Also sets `CLAUDE_CODE_USE_VERTEX=1`. | `ANTHROPIC_VERTEX_PROJECT_ID`, `CLOUD_ML_REGION` (`us-east5`) |

### Codex (`codex`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | Sign in to a ChatGPT account, in a browser. Runs `codex login`. | — |
| `device` | The same, from a machine with no browser. Runs `codex login --device-auth`. | — |
| `key` | An OpenAI API key. Runs `codex login --with-api-key` and writes the key to its stdin. | `OPENAI_API_KEY`, not kept |
| `token` | An access token, as an organisation hands one out. Runs `codex login --with-access-token` and writes it to its stdin. | `CODEX_ACCESS_TOKEN`, not kept |
| `gateway` | An endpoint speaking codex's protocol. | `CODEX_PROVIDER_URL`, `CODEX_PROVIDER_KEY` |

`key` and `token` are **not kept** as variables: `codex login` stores them in `auth.json`, and
a second copy would be a second place to leak them.

Codex takes a gateway as settings, not variables. A turn under `gateway` gets these arguments,
and nobody's `config.toml` is written:

```sh
-c model_provider=humanize
-c model_providers.humanize.name=humanize
-c model_providers.humanize.base_url=$CODEX_PROVIDER_URL
-c model_providers.humanize.env_key=CODEX_PROVIDER_KEY
-c model_providers.humanize.wire_api=responses   # the only one it runs
```

### Cursor Agent (`cursor-agent`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | Sign in to a Cursor account, in a browser. Runs `cursor-agent login`. | — |
| `key` | A Cursor API key, from the dashboard. | `CURSOR_API_KEY` |
| `gateway` | An endpoint speaking Cursor's protocol. | `CURSOR_API_ENDPOINT`, `CURSOR_API_KEY` |

### DeepSeek Harness (`dsh`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `key` | A DeepSeek API key, from the platform. | `DEEPSEEK_API_KEY` |
| `gateway` | An endpoint speaking DeepSeek's protocol. | `DEEPSEEK_BASE_URL`, `DEEPSEEK_API_KEY` |

`dsh` has no `env` way. humanize drives it through an SDK that reads this one key and this one
base URL and nothing else.

### Grok Build (`grok`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | Sign in to an xAI account, in a browser. Runs `grok login`. | — |
| `device` | The same, from a machine with no browser. Runs `grok login --device-auth`. | — |
| `key` | An xAI API key, from the console. | `XAI_API_KEY` |
| `gateway` | An endpoint speaking Grok Build's protocol, listing its models at `/models`. | `GROK_XAI_API_BASE_URL`, `XAI_API_KEY` |
| `oidc` | Your own identity provider, for an organisation that signs in through one. | `GROK_OIDC_ISSUER`, `GROK_OIDC_CLIENT_ID` |

### Kimi Code (`kimi`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | Sign in to a Kimi account, by the code it prints. Runs `kimi login`. | — |
| `model` | An endpoint of your own, made its default model. | `KIMI_MODEL_NAME`, `KIMI_MODEL_API_KEY`, `KIMI_MODEL_BASE_URL`, `KIMI_MODEL_PROVIDER_TYPE`: `anthropic`, `openai` or `kimi` (`openai`) |

### mimocode (`mimo`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | mimocode's own provider list, and whichever way that one takes. Runs `mimo auth login`. | — |
| `key` | A MiMo key, which its own models run on. | `XIAOMI_API_KEY` |

### opencode (`opencode`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | opencode's own provider list, and whichever way that one takes. Runs `opencode auth login`. | — |
| `wellknown` | A provider that hands out its own credential, by URL. Runs `opencode auth login <url>`. | `OPENCODE_WELLKNOWN`, the URL answering at `/.well-known/opencode`; not kept |
| `zen` | An OpenCode Zen key, which its own models run on. | `OPENCODE_API_KEY` |

### pi (`pi`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | pi's own `/login`. Runs `pi` and hands you the terminal: type `/login`, pick a provider, then `/exit`. | — |

### Qwen Code (`qwen`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | Sign in to a Qwen account. Runs `qwen` and hands you the terminal: type `/auth`, then `/quit`. | — |
| `key` | A key for the OpenAI-compatible endpoint it runs against. | `OPENAI_API_KEY`, `OPENAI_BASE_URL` (`https://dashscope.aliyuncs.com/compatible-mode/v1`) |

### ZCode (`zcode`)

| Way | What it is | Asks for |
| --- | --- | --- |
| `login` | Sign in to a Z.AI account, in a browser. Runs `zcode login`. | — |
| `device` | The same, from a machine with no browser. Runs `zcode login --no-browser`. | — |
| `key` | A Z.AI or BigModel coding plan key. Name the plan's own models, such as `zai/glm-5.1` or `bigmodel/glm-4.7`, and humanize hands ZCode that plan's endpoint per session. `~/.zcode/cli/config.json` is not written, so an existing `zcode login` is untouched. | `ZCODE_API_KEY` |
| `gateway` | An endpoint speaking ZCode's protocol. | `ZCODE_BASE_URL`, `ZCODE_API_KEY` |

### `env`, on every backend but `dsh`

| Way | What it is | Asks for |
| --- | --- | --- |
| `env` | Variables of your own: whatever name this CLI reads a key or an endpoint under. | `NAME=VALUE` lines |

You type the names, because the lists are too long to keep. pi reads a variable for each
provider it knows, and opencode one for each of about 180. Put one variable on each line.
<kbd>shift+enter</kbd> or <kbd>ctrl+j</kbd> starts a new line, and <kbd>enter</kbd> submits the
form. Blank lines and lines starting `#` are skipped.

## Making one

At the prompt, open `/providers`:

| Key | Does | When it lands |
| --- | --- | --- |
| <kbd>a</kbd> | Makes one. It asks which CLI, then which way in, then what that way asks, and hands the terminal to the CLI's own login where the way has one. | at once |
| <kbd>enter</kbd> → **correct what it holds** | Asks the way's questions again. What it holds is replaced, not merged, and credentials a login left are kept. Secrets start blank. | when the menu is saved |
| <kbd>enter</kbd> → **sign in again** | Runs the way's own command again, under this account's paths. Only for a way that runs one. | at once |
| <kbd>enter</kbd> → **falls back to** | Which account of this CLI a turn carries on under when this one fails. See [When an account goes down](#when-an-account-goes-down). | when the menu is saved |
| <kbd>enter</kbd> → **take it away** | Deletes the account and its credentials. An account already marked shows **keep it after all**. | when the menu is saved |

The same <kbd>a</kbd> works on the `provider` row of an agent's sheet, and comes back with the
new account chosen for that agent. The screens are in [TUI](/reference/tui).

**Names** are letters, digits, `.`, `-` and `_`, starting with a letter or a digit: a name is a
directory. **`<cli>/` with no name**, or `""` in Python, is the account this machine is already
signed into. Every backend has one. humanize keeps no credentials for it, and only its
**falls back to** can be set. Making it, signing it in or taking it away is refused.

From Python:

```python
from hmz.sdk import Hmz

accounts = Hmz().accounts

accounts.all()              # every account somebody made
accounts.all("claude")      # one backend's
accounts.ways("claude")     # how that backend can be signed into

way = accounts.way("claude", "gateway")
accounts.asks(way, {"ANTHROPIC_BASE_URL": url})   # still unanswered
one = accounts.make("claude", "deepseek", way, answers)
accounts.sign_in(one, way)  # the way's command, under its paths

accounts.write("claude", "work", "key", {"ANTHROPIC_API_KEY": key})
accounts.remove("claude", "deepseek")   # it and its credentials
```

`make` writes an account from a way's answers, filling unanswered questions from their
defaults. `write` writes one as given, and runs nothing. Either one, on an account that exists,
replaces what it holds and keeps its credentials and its fallback. `asks` lists the questions
with neither an answer nor a default. `sign_in` returns the command's exit status: `0` for a
way with no command, and `127` for a CLI that is not installed. See [SDK](/reference/sdk).

Reading one back from Python gives everything it holds. The `/providers` list shows only the
names of the variables it sets, never their values.

```python
one = accounts.find("claude", "deepseek")   # None if there is none

one.way        # the way it was made by
one.made       # when, as an ISO 8601 moment
one.at         # the directory its credentials are kept in
one.env        # the variables a turn under it is run with, values too
one.args       # what it adds to the backend's own command line
one.fallback   # the account it falls back to, or ""
one.swaps()    # (path the CLI names, path it gets), per credential
```

## Choosing one for an agent

The account goes after the CLI and an `@`. A CLI name never holds an `@`, so the account and
the model never get mixed up.

::: code-group

```sh [hmz exec]
hmz exec -f ralph_loop -a agent=claude@deepseek/claude-opus-5:max \
    -b cost=5 "fix the build"
```

```python [Python]
ClaudeCodeAgentConfig(
    model="claude-opus-5", effort="max", provider="deepseek"
)
```

```text [TUI]
the agent's sheet → provider → pick one, or a to make one there
```

:::

`provider=""`, the default, is the CLI as you already run it. A name the backend has no
account under raises `ValueError` the first time the agent needs it, naming the agent and the
account:

```text
coder: no claude provider called 'deepsek'
```

See [CLI › Writing an agent](/reference/cli#writing-an-agent) and [Agents](/reference/agents).

## What a turn under one runs with

| | |
| --- | --- |
| **Added** | The provider's variables, on top of the environment the turn inherits. |
| **Appended** | The provider's arguments, after the CLI's own. Only codex's `gateway` has any. |
| **Taken away** | Every variable the backend reads an account from, unless this provider sets it. |
| **Answered elsewhere** | Every credential path in the [table above](#per-backend), from the provider's directory. A refreshed token is written back there. |

All four apply whichever way the provider was made, so an agent on a gateway never reads the
account your CLI is signed into. An agent with **no** provider gets none of them: its
environment is left exactly as found.

### Variables taken away

A CLI prefers an account in a variable over the credentials it was signed in with. A key left
in your shell profile would outrank the provider, and nothing about the turn would look wrong:

```console
$ export ANTHROPIC_API_KEY=sk-mine    # what you use by hand
$ hmz exec -f ralph_loop -b cost=5 \
    -a agent=claude@work/claude-opus-5:high "..."
# the turn runs as `work`, not as that key
```

What is taken away is every variable the backend's ways ask for or set, and the other account
variables it reads, such as `ANTHROPIC_MODEL`, `CODEX_API_KEY`, `OPENCODE_AUTH_CONTENT` and
`CURSOR_AUTH_TOKEN`. It also covers every other name the same credential goes by:

| One credential | Also read as |
| --- | --- |
| `CLAUDE_CODE_OAUTH_TOKEN` | `ANTHROPIC_OAUTH_TOKEN` |
| `GEMINI_API_KEY` | `GOOGLE_API_KEY` |
| `MOONSHOT_API_KEY` | `KIMI_API_KEY` |
| `OPENAI_BASE_URL` | `OPENAI_API_BASE` |
| `XAI_API_KEY` | `GROK_CODE_XAI_API_KEY` |

The full list for each backend is its `ways` and `ambient` in `src/hmz/coganchor/backends.py`.

### How a credential path is answered

A turn under a provider of a backend with credential files is spawned under a supervisor:

```sh
python -m hmz internal cred --map=FROM=TO [--map=...] -- claude ...
```

[`hmz internal cred`](/reference/cli#hmz-internal-cred) runs the CLI under a seccomp-filtered
ptrace supervisor. Only syscalls that name a path stop. Everything else runs at native speed,
and the CLI is told nothing. Only a backend with no credential files, `dsh` or an ACP CLI,
skips the supervisor: a `key` provider of Claude Code is supervised as a `login` one is.

A `FROM` path is answered in three shapes:

| Shape | The CLI names | It gets, in the provider's directory |
| --- | --- | --- |
| the file itself | `~/.claude/.credentials.json` | `home/.credentials.json` |
| anything inside a directory | `~/.kimi-code/credentials/<file>` | `home/credentials/<file>` |
| the same name, another suffix | `~/.claude/.credentials.json.tmp` | `home/.credentials.json.tmp` |

The third shape is how a CLI rotates a token: it writes `.credentials.json.tmp`, then renames
it over the real name. A path is matched after `.`, `..` and doubled `/` are resolved, and
after `/proc/<pid>/fd/<n>`, `cwd`, `exe` and `root` links are followed. A home reached through
a symlink is matched under both spellings.

What the call is about to do decides which file it gets:

| The call | Gets |
| --- | --- |
| `stat`, `lstat`, `newfstatat`, `statx`, `access`, `faccessat`, `faccessat2`, `readlink`, `readlinkat`, and an `open` for reading | **A copy in memory.** Made once into `/dev/shm/hmz-<pid>-<random>/`, a `0700` directory holding `0600` files, and checked against the provider's file once a second, so another agent's refresh is seen. |
| Anything that creates, writes, truncates, renames, links, unlinks, changes a mode or touches a time, and an `open` that asks for anything but reading | **The provider's own file**, so a refreshed token is durable the moment the CLI writes it. The copy is dropped, and the next read makes a new one. |

A pi turn asks about its `auth.json` 600 to 800 times, over half of all the path syscalls it
makes. That is why reads get a copy. Directories, lock files, files over 1 MiB, and machines
with no usable `/dev/shm` get the provider's own path for reads too, and so does `chdir`.

The copies are deleted when the supervisor exits. A killed turn's copies are swept up by
whatever killed it, or else by the next redirected run on the machine.

An [anchored](/reference/remote-execution) turn uses none of this. A process has one tracer, so
the anchor is handed the same paths as `redirects` and its own supervisor answers them with the
provider's files.

## When an account goes down

Each account can name the account to carry on under when a turn under it fails: a subscription
that ran out, a key refused, a gateway answering 503. That one can name the next, which makes a
**chain**. A turn walks the chain inside the conversation it was in, with the same agent and
the same model.

Set it with **falls back to** in `/providers`, or from Python:

```python
accounts = Hmz().accounts

accounts.points("claude", "subscription", "key")
accounts.points("claude", "key", "gateway")
accounts.points("claude", "", "subscription")  # "": this machine's own

held = accounts.find("claude", "subscription")
accounts.chain(held)                   # [subscription, key, gateway]
```

| Rule | |
| --- | --- |
| A chain that loops | Ends at the second sight of an account. |
| A name that is not there | Ends the chain there. `points` refuses to write one. |
| Pointing at itself | Refused. |
| Falling back *to* the machine's own account | Not possible: `at=""` means the end of the line. An agent given no account already starts there. |
| The machine's own account | Can fall back to others. What it says is kept in `~/.humanize/local/<cli>.json`. |

An account's chain answers an account going down. A retired model, a CLI that will not start,
or a limit on the whole place is answered by [another agent](/user/fallback), which a turn
moves to only once this chain is spent. How many times a failed turn is retried first is set
per place on [`/fallback`](/user/fallback), not on the account.

## One account, several CLIs

An Anthropic key is an Anthropic key whether Claude Code, pi, opencode, mimocode or ZCode holds
it. So an account made for one backend can often be copied to others:

```python
one = accounts.write("claude", "work", "key", {"ANTHROPIC_API_KEY": k})
accounts.serves(one)          # ('pi', 'opencode', 'mimo', 'zcode')
for cli in accounts.serves(one):
    accounts.copies(one, cli) # pi/work, opencode/work, mimo/work, …
```

- A copy is written **under the same name**, spelled the way that backend reads it: a Claude
  subscription token lands on pi as `ANTHROPIC_OAUTH_TOKEN`.
- A copy **overwrites** one already there. That is how you rotate a key everywhere at once.
- It is recorded as that backend's own way where one asks for exactly these variables, and as
  `env` otherwise.
- `serves` lists where the account **could** go, whether or not a copy is already there.
- An account that is a login is the CLI's own store in its own format, so it copies nowhere.
  Neither does one holding a variable the other backend has no name for.

At the prompt, making or correcting an account that other backends could run asks which of them
to write it down for. The ones installed here are ticked to start with:

![/providers, a, claude, key: an account named and its key typed as bullets, then the question
of which other backends to write it down for](/demo/alike.gif)

Each copy is then an account of its own, listed under its own backend:

![the /providers list afterwards: shared under claude, opencode and pi, each saying which
variable it sets](/demo/alike-copied.png)

## Requirements and limits

- **Linux on x86-64 or aarch64**, for a provider of any backend with credential files: every
  backend but `dsh` and ACP CLIs, whichever way the provider was made.
- **Only the paths [listed](#per-backend) are answered.** A CLI that keeps a credential
  anywhere else keeps it where it always did.
- **A credential that is not a file is not covered.** A macOS keychain is not a path. An
  opencode or mimocode **console account** lives in that CLI's SQLite file, which also holds
  its sessions, so it is not answered. A provider of either is its `auth.json`.
- **A path that cannot be answered fails** with `EIO` rather than falling through to the real
  one, and a turn that cannot be supervised is refused. So is an `openat2` confined to a
  directory, which an answered path would leave.
- **A 32-bit process below the agent is not intercepted.** The filter lets another
  architecture's syscalls through. Every one of these CLIs is 64-bit.

## Security

::: warning A provider directory holds real credentials
Every directory humanize makes on the way to `~/.humanize/providers/<cli>/<name>/` is `0700`,
and `provider.json` is `0600` from the moment it exists. Taking an account away deletes the
directory, credentials and all.
:::

**The interface never draws a value.** The `/providers` list shows variable names, and a
secret answered at the prompt is drawn as bullets. From Python, `one.env` holds the values
themselves, and a value you pass to `make` or `write` from a script is only as private as
wherever that script got it.

::: warning Where the account goes when the work is elsewhere
- **Supervised, the default:** the agent runs here, so the provider's files never cross to the
  [target](/reference/remote-execution). Its variables are passed as `private`, so they do not
  reach the commands the agent runs there.
- **`native`:** the CLI runs on the target, so the provider's variables are sent there. Its
  credential files are written into a directory only the target's user can enter, and removed
  when the turn ends. Files under your home (`~/`) stay here, and an account kept only there
  is refused.
- **`harness` on another machine:** the agent process runs there, with that machine's state
  directory and connection. A provider is **not** carried there: its variables are not sent,
  and its credential paths are answered with this machine's paths, which that machine does not
  have.

A machine you would not trust with the account is a machine to reach supervised, with the
harness here. See [Remote execution](/reference/remote-execution#where-the-account-lives).
:::

## API summary

`Hmz().accounts` is the whole of this as one object, and it is what the interface uses. See
[SDK](/reference/sdk). Below it are two modules:

```python
from hmz.coganchor import providers
from hmz.coganchor.providers import login
```

| `providers.` | |
| --- | --- |
| `Provider` | One account: `cli`, `name`, `way`, `env`, `args`, `made`, `fallback`; `.at`, `.swaps()`, `.command(argv)`. |
| `LOCAL` | `""`, the name of the account this machine is already signed into. |
| `ENV` | The `env` way. |
| `providers(cli="")` | Every account, or one backend's. |
| `find(cli, name)` | One account, or `None`. |
| `add(cli, name, way="env", env=None, args=())` | Writes one down and makes its directory. |
| `ready(provider)` | Makes the directories its credentials land in. |
| `remove(cli, name)` | Takes one away, credentials and all. |
| `ways(cli)` | Every way one backend offers, `env` last where it has one. |
| `where(cli, name)` | The directory one is kept in. |
| `environ(provider)` | The variables a turn under it is run with. |
| `env_of(text)` | `NAME=VALUE` lines, read into variables. |
| `filled(text, answers)` | `{VARIABLE}` in a way's `argv` or `args`, filled from answers. |
| `serves(one)`, `copies(one, cli, name="")` | Where one could be copied; copying it there. |
| `points(cli, name, at)`, `chain(one)` | Setting what one falls back to; the chain, in order. |
| `alone(cli)` | The file what is said of this machine's own account is kept in. |

| `login.` | |
| --- | --- |
| `way_of(cli, name)` | The way one backend offers under a name, or `None`. |
| `asked(way, given)` | What a way still has to be told. |
| `make(cli, name, way, answers=None)` | An account out of what its way was answered with. |
| `sign_in(provider, way, answers=None)` | The way's own command, run under that account's paths. |

On the agent:

| `agent.` | |
| --- | --- |
| `provider` | `Provider \| None`: the account its turns run as. `None` is this machine's own. |
| `node()` | The same, never `None`: where its chain is walked from. |
| `walks()` | That account and everything it falls back to, in order. |
| `spec` | `CLI[@ACCOUNT]/MODEL`: how a fallback names this agent. |
| `stands_in()` | The agent that takes its turns once its chain is spent, or `None`. |
| `environment()` | The variables its turns are run with, on top of what they inherit. |
| `hushed()` | The variables its turns are run without. |
