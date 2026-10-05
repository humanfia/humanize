# Environment variables

Every environment variable humanize reads, and every one it sets in the environment of a
process it starts. Variables read only by a coding agent CLI itself are out of scope except
where humanize reads them too.

## Which process reads them

| Process | Reads its environment when |
| --- | --- |
| `hmz` (the TUI) | at start; terminal and theme variables |
| a workspace's runs host | forked from the first `hmz` in that workspace that starts it; **every variable read while a run executes is that first `hmz`'s environment**, not that of frontends attached later |
| the daemon | forked from the first `hmz` on the machine that starts it; reads none for a run. `TMPDIR` decides [where it is](/reference/daemon#files): two `hmz` with different ones reach different daemons |
| `hmz exec` | at start, and throughout its run |
| a Python program using `hmz.sdk` / `hmz.runtime` | throughout |
| `hmz internal …` | at start (flag defaults) |
| a remote machine's shell | `HUMANIZE_HOME` and `CUDA_VISIBLE_DEVICES`, read by the probe run over `ssh` |

Values are read with `os.environ`; `hmz` changes its own environment in one case only
(`TEXTUAL_DISABLE_KITTY_KEY`, below).

## humanize's own

| Variable | Values | Default | Effect |
| --- | --- | --- | --- |
| <code id="humanize-home">HUMANIZE_HOME</code> | a path; empty is unset | `~/.hmz` | Root of humanize's home, which holds what it keeps but your own flows (`~/.hmz/flows`), its cache and this machine's own directory: see [Files](/reference/files). A `~/.humanize` from before is [moved there](/reference/files#moved-from-humanize). On an `ssh` machine the remote login shell's `${HUMANIZE_HOME:-$HOME/.hmz}` decides the directory there; a relative value there is taken under the remote `$HOME`. |
| <code id="humanize-daemon">HUMANIZE_DAEMON</code> | `off`, `0`, `no` (trimmed, case-insensitive) mean off; anything else on | on | Off: plain `hmz` holds runs in its own process instead of the [runs host](/reference/daemon). Not read by `hmz exec`. |
| <code id="humanize-name">HUMANIZE_NAME</code> | any string; empty is unset | the login name (`getpass.getuser()`), else `somebody` | The name a frontend attaches under (`<name>@<kind>`, `#2`… on a clash). |
| <code id="humanize-sentry">HUMANIZE_SENTRY</code> | `on`, `1`, `true`, `yes` → on; `off`, `0`, `false`, `no` → off (trimmed, case-insensitive); anything else ignored | the `enable_sentry` [setting](/reference/settings#enable-sentry) | Answers the error-report question for this process only, without writing anything. `/settings` shows that the variable overrides the setting. |
| <code id="humanize-sessions">HUMANIZE_SESSIONS</code> | `off`, `0`, `no` (trimmed, case-insensitive) mean off | on | Off: a CLI's sessions stay in the CLI's own home instead of the epic's `sessions/<cli>/`. See [Tracing](/reference/tracing#sessions-dir). |
| <code id="humanize-watchdog">HUMANIZE_WATCHDOG</code> | a number of seconds (`float`); `<= 0` disables; a value that is not a number is ignored | per CLI: 900 s; `dsh` 360 s | Seconds a turn may be silent before the watchdog acts on it. Overrides every CLI's own value. |
| <code id="humanize-prices">HUMANIZE_PRICES</code> | a URL (contains `://`) or a file path; `""`, `off`, `0`, `no`, `none` (case-insensitive) disable fetching | `https://openllmprices.com/data/prices.json` | Where the price table used for [budgets](/reference/flows#budget) and the [tally](/user/tally) is refreshed from (at most once per 24 h, by the interface and by every run), into `$TMPDIR/humanize-<uid>/prices.json`. |
| <code id="humanize-shadows">HUMANIZE_SHADOWS</code> | a path (`~` expanded); empty is unset | `~/.cache/humanize/shadows` | Directory of mirror records (`<sha16>.json`) for this process and its children. |
| <code id="humanize-ssh-reuse">HUMANIZE_SSH_REUSE</code> | `off`, `0`, `no`, `false` (trimmed, case-insensitive) or set and empty turn it off; anything else on | on | On: every `ssh` humanize runs adds `-o ControlMaster=auto -o ControlPersist=120 -o ControlPath=<dir>/%C[-<digest>]`, `<dir>` being `$XDG_RUNTIME_DIR/humanize-ssh-<uid>` (or the temporary directory). Read once per process. |
| <code id="humanize-rendezvous">HUMANIZE_RENDEZVOUS</code> | a host or address; empty is unset | the address this machine uses to reach the outside (UDP route to `192.0.2.1`), else `127.0.0.1` | Default of `hmz internal anchor --broker`, and the address an in-process rendezvous broker advertises. |
| <code id="humanize-rendezvous-port">HUMANIZE_RENDEZVOUS_PORT</code> | an integer | `0` (any free port) | Port of the process's shared rendezvous broker (listening on `0.0.0.0`). A non-integer raises `ValueError`. |
| <code id="humanize-target">HUMANIZE_TARGET</code> | `ssh://HOST`, `docker://CONTAINER[@ENDPOINT]`, `apple-container://CONTAINER`, `tcp://HOST:PORT`, `peer://TICKET@HOST:PORT`, `local[:DIR]` | `local` | Default of `hmz internal anchor --target`. Also set by humanize inside an anchored agent (below). |
| <code id="humanize-harness">HUMANIZE_HARNESS</code> | `local`, `same`, or a target spelling | `local` | Default of `hmz internal anchor --harness`. |
| <code id="humanize-shadow">HUMANIZE_SHADOW</code> | a path | `--workspace` | Default of `hmz internal anchor --shadow`: the mirror directory on the machine the harness runs on. Set by humanize for a remote harness (below). |
| <code id="humanize-token">HUMANIZE_TOKEN</code> | a string | none | Default of `--token` for `hmz internal anchor` (the secret a `tcp://` target expects) and `hmz internal anchor serve` (the secret clients must present; a mismatch is refused with `invalid token`). `serve --listen` on a non-loopback address without a token fails: `hmz: cannot listen on a non-loopback address without --token`. |
| <code id="humanize-log">HUMANIZE_LOG</code> | `debug`, `info`, `warning`, `error` (trimmed, case-insensitive); empty is unset | `warning` for `anchor` and `anchor serve`; `info` for `anchor rendezvous` | Log level on stderr of those three commands, where `--log-level` is not given. Any other value is ignored: the command says `hmz: ignoring HUMANIZE_LOG='<value>', which is not one of debug, info, warning, error` on stderr and logs at its default. |

`hmz internal` flags: [CLI](/reference/cli#hmz-internal) and
[Remote execution](/reference/remote-execution).

## Terminal

| Variable | Values | Effect |
| --- | --- | --- |
| `NO_COLOR` | any non-empty value | No colour in `hmz exec` output. Checked first. |
| `TERM` | `dumb` | No colour, as `NO_COLOR`. |
| `FORCE_COLOR` | non-empty and not `0` | Colour even into a pipe. |
| `TEXTUAL_THEME` | a Textual theme name; unknown names ignored | The TUI's theme. Default: the `terminal` theme. |
| `TMUX`, `TERM_PROGRAM`, `LC_TERMINAL` | | Where `TMUX` is empty or unset and `TERM_PROGRAM` is `iTerm.app` or `LC_TERMINAL` is `iTerm2`, `hmz` sets `TEXTUAL_DISABLE_KITTY_KEY=1` in its own environment (if unset) before the TUI starts, so input-method text reaches the prompt. |

## System

| Variable | Read by | Effect |
| --- | --- | --- |
| `HOME` | everything (`~`) | Home directory. When a turn runs under an account, the backend home is resolved against that turn's `HOME`. |
| `PATH` | CLI discovery; fence | Where a CLI is found; every `PATH` directory is readable inside the fence for a script's `#!/usr/bin/env` interpreter. |
| `XDG_CONFIG_HOME` | backend profiles, Cursor Agent | Default `~/.config`. Locates CLI credentials kept there (Claude Code `anthropic`, Cursor `cursor/auth.json`), skills directories of opencode, MiMo Code and Cursor, and Cursor's fence write grant. |
| `XDG_RUNTIME_DIR` | ssh transport | Parent of the ssh control-socket directory `humanize-ssh-<uid>`; else the temporary directory. |
| `DOCKER_HOST` | docker transport | A docker target with no context of its own is "this machine" where `DOCKER_HOST` is unset, empty, or `unix://…`. |
| `CUDA_VISIBLE_DEVICES` | local and ssh environments | Comma list of indices or `GPU-` UUID prefixes, read up to the first entry that matches no GPU. Set but empty: 0 GPUs. Unset: every GPU `nvidia-smi` lists. Decides the GPUs an environment reports against [`GPUEnvMixin`](/reference/flows#what-a-machine-must-have). |
| `TMPDIR`, `TEMP`, `TMP` | Python's `tempfile` | Temporary directories (indirectly). |

## Backend homes

Where each CLI keeps its state and logs. Read to find sessions to [trace](/reference/tracing),
to fence the CLI, and to locate its credentials. `<var>` set: `<var>[/<sub>]`; unset:
`<HOME>/<default>`.

| CLI | Variable | Sub | Default |
| --- | --- | --- | --- |
| `claude` | `CLAUDE_CONFIG_DIR` | | `~/.claude` |
| `codex` | `CODEX_HOME` | | `~/.codex` |
| `dsh` | `DSH_HOME` | | `~/.dsh` |
| `grok` | `GROK_HOME` | | `~/.grok` |
| `kimi` | `KIMI_CODE_HOME` | | `~/.kimi-code` |
| `pi` | `PI_CODING_AGENT_DIR` | | `~/.pi/agent` |
| `qwen` | `QWEN_HOME` | | `~/.qwen` |
| `opencode` | `XDG_DATA_HOME` | `opencode` | `~/.local/share/opencode` |
| `mimo` | `XDG_DATA_HOME` | `mimocode` | `~/.local/share/mimocode` |
| `cursor-agent` | `CURSOR_CONFIG_DIR` | | `~/.cursor` |
| `mcode` | `MINIMAX_DATA_DIR` | | `~/.minimax` |
| `agy` | none (its `--app_data_dir`, in an account's arguments, moves it) | | `~/.gemini/antigravity-cli` |

The fence's grants for a CLI's own state use fixed `~/…` paths, not these variables.

`DSH_HOME` is also read directly for DeepSeek Harness's `settings.yaml`, `.credentials.yaml`
and `.env`. For a `dsh` turn with no account, the API key variable's name is
`llm-deepseek.apiKeyEnv` in `$DSH_HOME/settings.yaml` (default `DEEPSEEK_API_KEY`); the key is
taken from that variable, then `.credentials.yaml`, then the project's `.env`, then
`$DSH_HOME/.env`, and `DEEPSEEK_BASE_URL` likewise.

## Account variables

A CLI reads its credentials and endpoint from the environment. humanize reads the same
variables to decide which hosts a fenced session may reach, to list an account's models, and
to keep a shell's credentials from overriding an [account's](/reference/providers).

**Hushing.** A turn run under an account starts with every variable in its CLI's hushed set
removed, then the account's own `env` added: a key exported in a shell profile never outranks
the account. A turn with no account (`@local`) keeps the shell's.

**Endpoint.** Where the account (or, with no account, the shell) sets the CLI's endpoint
variable, the model list is read from `GET <endpoint>/models`.

| CLI | Endpoint variable |
| --- | --- |
| `claude` | `ANTHROPIC_BASE_URL` |
| `agy` | `GOOGLE_GEMINI_BASE_URL` |
| `codex` | `CODEX_PROVIDER_URL` |
| `dsh` | `DEEPSEEK_BASE_URL` |
| `grok` | `GROK_XAI_API_BASE_URL` |
| `kimi` | `KIMI_MODEL_BASE_URL` |
| `qwen` | `OPENAI_BASE_URL` |
| `mimo` | `MIMO_GATEWAY_URL` |
| `pi`, `opencode`, `cursor-agent`, `mcode`, `acp` | none |

**Reachable hosts under `online` `NONE`.** The hosts the CLI's model and sign-in are at, plus
the host (and port) of every variable in the turn's environment whose name ends in `_URL`,
`_BASE`, `_HOST`, `_ENDPOINT`, `_ORIGIN` or `_ISSUER`, plus, for Claude Code:

| Switch (non-empty) | Region/resource variable | Override |
| --- | --- | --- |
| `CLAUDE_CODE_USE_BEDROCK` | `AWS_REGION` (default `us-east-1`) | `ANTHROPIC_BEDROCK_BASE_URL` |
| `CLAUDE_CODE_USE_VERTEX` | `CLOUD_ML_REGION` (default `us-east5`) | `ANTHROPIC_VERTEX_BASE_URL` |
| `CLAUDE_CODE_USE_FOUNDRY` | `ANTHROPIC_FOUNDRY_RESOURCE` | `ANTHROPIC_FOUNDRY_BASE_URL` |

A region or resource must be a DNS label.

**Hushed sets.**

| CLI | Variables |
| --- | --- |
| `claude` | `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_CONFIG_DIR`, `ANTHROPIC_CUSTOM_HEADERS`, `ANTHROPIC_MODEL`, `ANTHROPIC_OAUTH_TOKEN`, `ANTHROPIC_VERTEX_PROJECT_ID`, `AWS_PROFILE`, `AWS_REGION`, `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR`, `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_FOUNDRY`, `CLAUDE_CODE_USE_GATEWAY`, `CLAUDE_CODE_USE_VERTEX`, `CLOUD_ML_REGION` |
| `agy` | `AGY_ADC_AUTH`, `CLOUD_CODE_URL`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_GEMINI_BASE_URL` |
| `codex` | `CODEX_ACCESS_TOKEN`, `CODEX_API_KEY`, `CODEX_AUTHAPI_BASE_URL`, `CODEX_PROVIDER_KEY`, `CODEX_PROVIDER_URL`, `OPENAI_API_BASE`, `OPENAI_API_KEY`, `OPENAI_BASE_URL` |
| `dsh` | `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_SEARCH_BASE_URL` |
| `grok` | `GROK_AUTH`, `GROK_AUTH_PATH`, `GROK_AUTH_PROVIDER_COMMAND`, `GROK_CLI_CHAT_PROXY_BASE_URL`, `GROK_CODE_XAI_API_KEY`, `GROK_DEFAULT_MODEL`, `GROK_MODELS_BASE_URL`, `GROK_MODELS_LIST_URL`, `GROK_OAUTH2_CLIENT_ID`, `GROK_OAUTH2_ISSUER`, `GROK_OIDC_CLIENT_ID`, `GROK_OIDC_ISSUER`, `GROK_XAI_API_BASE_URL`, `XAI_API_KEY` |
| `kimi` | `KIMI_API_KEY`, `KIMI_BASE_URL`, `KIMI_CODE_BASE_URL`, `KIMI_CODE_CUSTOM_HEADERS`, `KIMI_CODE_OAUTH_HOST`, `KIMI_MODEL_API_KEY`, `KIMI_MODEL_BASE_URL`, `KIMI_MODEL_NAME`, `KIMI_MODEL_PROVIDER_TYPE`, `KIMI_OAUTH_HOST`, `KIMI_REGISTRY_API_KEY`, `MOONSHOT_API_KEY` |
| `pi` | `AI_GATEWAY_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_OAUTH_TOKEN`, `ANT_LING_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_BEARER_TOKEN_BEDROCK`, `AWS_PROFILE`, `AWS_REGION`, `AWS_SECRET_ACCESS_KEY`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_DEPLOYMENT_NAME_MAP`, `AZURE_OPENAI_RESOURCE_NAME`, `BASETEN_API_KEY`, `CEREBRAS_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_KEY`, `CLOUDFLARE_GATEWAY_ID`, `DEEPSEEK_API_KEY`, `FIREWORKS_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GROK_CODE_XAI_API_KEY`, `GROQ_API_KEY`, `KIMI_API_KEY`, `MINIMAX_API_KEY`, `MISTRAL_API_KEY`, `MOONSHOT_API_KEY`, `NVIDIA_API_KEY`, `OPENAI_API_KEY`, `OPENCODE_API_KEY`, `OPENROUTER_API_KEY`, `QWEN_TOKEN_PLAN_API_KEY`, `QWEN_TOKEN_PLAN_CN_API_KEY`, `TOGETHER_API_KEY`, `XAI_API_KEY`, `XIAOMI_API_KEY`, `XIAOMI_TOKEN_PLAN_AMS_API_KEY`, `XIAOMI_TOKEN_PLAN_CN_API_KEY`, `XIAOMI_TOKEN_PLAN_SGP_API_KEY`, `ZAI_API_KEY`, `ZAI_CODING_CN_API_KEY` |
| `qwen` | `OPENAI_API_BASE`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_CODE_MODEL`, `QWEN_MODEL`, `QWEN_OAUTH_MODELS` |
| `opencode` | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `GITHUB_TOKEN`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `OPENCODE_API_KEY`, `OPENCODE_AUTH_CONTENT`, `OPENCODE_CONFIG_CONTENT`, `OPENCODE_WELLKNOWN`, `OPENROUTER_API_KEY` |
| `mimo` | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `AWS_BEARER_TOKEN_BEDROCK`, `AWS_PROFILE`, `AWS_REGION`, `AZURE_API_KEY`, `AZURE_RESOURCE_NAME`, `DEEPSEEK_API_KEY`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_GENERATIVE_AI_API_KEY`, `GOOGLE_VERTEX_LOCATION`, `GROK_CODE_XAI_API_KEY`, `MIMOCODE_AUTH_CONTENT`, `MIMOCODE_CONFIG_CONTENT`, `MIMO_API_KEY`, `MIMO_GATEWAY_API`, `MIMO_GATEWAY_KEY`, `MIMO_GATEWAY_MODEL`, `MIMO_GATEWAY_URL`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `XAI_API_KEY`, `XIAOMI_API_KEY` |
| `cursor-agent` | `CURSOR_API_BASE_URL`, `CURSOR_API_ENDPOINT`, `CURSOR_API_KEY`, `CURSOR_API_URL`, `CURSOR_AUTH_TOKEN`, `CURSOR_LOCAL_AGENT_API_KEY` |
| `mcode` | `MCODE_API_BASE_URL`, `MCODE_AUTH_BASE_URL`, `MCODE_AUTH_PROVIDER`, `MCODE_CLIENT_ID`, `MCODE_GATEWAY_FORMAT`, `MCODE_GATEWAY_MODEL`, `MCODE_GATEWAY_URL`, `MCODE_PROVIDER_API_KEY`, `MCODE_REGION`, `MINIMAX_API_KEY`, `MINIMAX_CN_API_KEY` |
| `acp` | none |

Aliases hushed together: `CLAUDE_CODE_OAUTH_TOKEN`/`ANTHROPIC_OAUTH_TOKEN`,
`GEMINI_API_KEY`/`GOOGLE_API_KEY`, `MOONSHOT_API_KEY`/`KIMI_API_KEY`,
`OPENAI_BASE_URL`/`OPENAI_API_BASE`, `XAI_API_KEY`/`GROK_CODE_XAI_API_KEY`.

**Other variables read for a CLI.** `NODE_COMPILE_CACHE` (pi, qwen) and `NODE_OPTIONS`
(appended to, never replaced) are respected if already set; `QWEN_CODE_SYSTEM_DEFAULTS_PATH`
is read from the turn's environment to know which files to watch.

## Set for processes humanize starts

| Variable | Set in | Value |
| --- | --- | --- |
| `HUMANIZE` | an anchored agent (supervised: its environment; native: an `env` prefix on the target command) | humanize's version |
| `HUMANIZE_TARGET` | the same | the target, as `--target` spells it |
| `HUMANIZE_WORKSPACE` | the same | the workspace as the target names it |
| `PWD` | an anchored agent; every command run on a target | the working directory |
| `TERM` | a command run on a target with a terminal | `xterm-256color` unless set |
| `HUMANIZE_SHADOW` | `hmz internal anchor` started for a harness on another machine | its mirror: `$HOME/.cache/humanize-mirrors/<sha16>` on an `ssh` machine, `/tmp/humanize-mirrors/<sha16>` in a container |
| `HUMANIZE_TOKEN` | a local `hmz internal anchor serve --stdio` child | the token |
| the account's `env` | every turn, sign-in and model listing under an account | from `providers/<cli>/<name>/provider.json` ([Files](/reference/files)); includes fixed values a sign-in way sets (e.g. `CLAUDE_CODE_USE_BEDROCK=1`, `AWS_REGION=us-east-1`) |
| a CLI's home variable and `XDG_CONFIG_HOME` | a native turn on another machine under an account whose credential files live in the CLI's home | a per-session `mktemp -d` directory on the target holding copies of those files, removed after the turn |
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` | every `claude` turn | `1` |
| `OPENCODE_PERMISSION`, `MIMOCODE_PERMISSION` | `opencode`/`mimo` turns with a rung, web switch or fence to express | a JSON permission table |
| `MIMOCODE_DISABLE_CLAUDE_CODE` | `mimo` turns whose fence does not allow reading `~/.claude.json` | `1` |
| `MIMO_GATEWAY_MODEL` | `mimo` turns under a gateway account | the turn's model, without a leading `humanize/` |
| `QWEN_CODE_SYSTEM_SETTINGS_PATH` | every `qwen` turn | a per-session settings file |
| `NODE_COMPILE_CACHE` | `pi`, `qwen` turns on this machine, unless already set | `$TMPDIR/humanize-<uid>/compiled/pi`, `…/compiled/qwen` |
| `NODE_OPTIONS`, `HMZ_PRELOAD_AT` | `kimi`, `pi`, `qwen`, `mimo` turns on this machine with an `on_pre_tool_use` hook hung | `--require <preload>` appended; the preload's report socket (the preload sets `HMZ_PRELOAD_IN` itself and removes all three from programs the CLI starts) |
| `HMZ_DSH_EFFORT` | `dsh` turns | the effort |
| `DEEPSEEK_SEARCH_BASE_URL` | `dsh` turns under an account that names an endpoint and not this | `DEEPSEEK_BASE_URL` |
| `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL` | `dsh` turns with no account | as resolved (see [Backend homes](#backend-homes)) |
| `PKG_NATIVE_CACHE_PATH` | fenced `dsh` turns | the fence's scratch directory |
| `TMPDIR`, `TMP`, `TEMP` | everything inside `hmz internal fence` | the fence's scratch directory |
| `XDG_CACHE_HOME`, `UV_CACHE_DIR`, `npm_config_cache`, `PIP_CACHE_DIR`, `GOCACHE` | inside the fence, where the current location is not writable under it | `<scratch>/cache/<name in lower case>` |
| `HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY` and lower-case forms; `NO_PROXY=`, `no_proxy=`; `NODE_USE_ENV_PROXY=1` | inside the fence, where `online` is `NONE` | `http://127.0.0.1:<proxy port>` |
| `DOCKER_HOST`, `DOCKER_CONTEXT`, `DOCKER_TLS`, `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH` (removed) | every `docker` command addressing a provider's own daemon | — |
| `PATH` | `docker` commands to an `ssh://` daemon with ssh options | `$TMPDIR/humanize-<uid>/docker-ssh/<sha16>:$PATH` (a shim that removes itself) |
| `SSH_ASKPASS_REQUIRE` | the `ssh` that checks a runtime | `never` (fail rather than prompt) |
| `HOME`, `NVIDIA_VISIBLE_DEVICES`, and the provider's `env` | containers of `docker` environments | `HOME=/tmp`; `NVIDIA_VISIBLE_DEVICES=void` unless GPUs are handed out |
| the variables an ACP agent asks for | commands an `acp` agent asks humanize to run | as asked |
| `TEXTUAL_DISABLE_KITTY_KEY` | `hmz`'s own environment, direct iTerm2 only | `1` if unset |

A variable humanize removes: every hushed account variable not set by the account (see
[Account variables](#account-variables)).

**What crosses to a target.** A command run on another machine gets the caller's environment
layered over the target's, less `DISPLAY`, `HOME`, `HOSTNAME`, `HOSTTYPE`, `LOGNAME`,
`MACHTYPE`, `MAIL`, `OLDPWD`, `OSTYPE`, `PATH`, `PWD`, `SECURITYSESSIONID`, `SHELL`, `SHLVL`,
`TEMP`, `TMP`, `TMPDIR`, `USER`, `WAYLAND_DISPLAY`, `_`, and every variable starting `Apple`,
`DYLD_`, `HUMANIZE_`, `LD_`, `SSH_`, `XDG_`, `XPC_` or `__CF`, and any named with
`--private`.
