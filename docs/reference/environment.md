---
title: Environment variables
description: Look up every environment variable Humanize reads, what values it takes, and what Humanize sets for the programs it starts.
---

# Environment variables

This page lists every environment variable Humanize reads, and the ones it sets for the programs it starts. Variables read only by a harness for itself are omitted.

## Whose environment counts

Set run-related variables in the daemon's environment. Flows and agents run inside the daemon, not inside your window or terminal. Changes take effect the next time the daemon starts.

| Process | Environment it has |
| --- | --- |
| `hmz`, `hmz exec`, `hmz chat`, `hmz web` | The shell you ran it from. |
| The daemon | The environment of the first `hmz` that started it. A daemon run by `hmz daemon serve` with no terminal (the service `hmz daemon install` sets up) takes your login shell's environment instead. |
| A run and its harnesses | The daemon's, with the changes listed under [Set by Humanize](#set-by-humanize). |
| Humanize Desktop | Your login shell's (`$SHELL -ilc`), not the one the app was opened with. |
| A harness on another machine | That machine's, with yours laid over it. See [What crosses to another machine](#what-crosses-to-another-machine). |

See [The daemon](/user/daemon).

## Humanize's own

An empty value counts as unset unless the table says otherwise. Switch values are trimmed and case-insensitive.

| Variable | Values | Default | Effect |
| --- | --- | --- | --- |
| `HUMANIZE_HOME` | a path | `~/.hmz` | The directory for settings, accounts, and epics. See [Files on disk](/reference/files). |
| `HUMANIZE_NAME` | any text | your login name, else `somebody` | The name an interface attaches to the daemon under, as `<name>@<kind>`. |
| `HUMANIZE_SENTRY` | `on`, `1`, `true`, `yes` or `off`, `0`, `false`, `no` | the `enable_sentry` setting | Turns error reports on or off for this process only. Writes nothing to settings. Ignores any other value. See [Report a problem](/user/reporting). |
| `HUMANIZE_SESSIONS` | `off`, `0`, `no` | on | Off: each harness keeps its sessions in its own home, and Humanize keeps none inside the epic. |
| `HUMANIZE_WATCHDOG` | seconds, as a number | `900`; `360` for `dsh` | How long a turn may stay silent before the watchdog acts. Applies to every harness. `0` or less turns the watchdog off. Ignores non-numeric values. |
| `HUMANIZE_PRICES` | a URL or a file path; `off`, `0`, `no`, `none` or empty | `https://openllmprices.com/data/prices.json` | Source for the price list behind [cost](/user/usage) and money [budgets](/user/budgets), fetched at most once every 24 hours. An off value stops fetching. |
| `HUMANIZE_RELEASES` | a URL or a file path; `off`, `0`, `no`, `none` or empty | `https://pypi.org/pypi/hmz/json` | Source for checking the newest release of `hmz`, at most once every 24 hours. An off value stops the lookup. |
| `HUMANIZE_SCAN` | `off`, `0`, `no`, `none` or empty | on | Off: the daemon does not ask installed harnesses for their models at startup. Models appear only when you scan. |
| `HUMANIZE_SSH_REUSE` | `off`, `0`, `no`, `false` or empty | on | On: every `ssh` Humanize runs to one host shares one connection (`ControlMaster=auto`, `ControlPersist=120`). Read once per process. |
| `HUMANIZE_EASYTIER` | path to an `easytier-core` binary | EasyTier `2.6.4`, downloaded into the home on first use | The EasyTier binary used to reach or serve a daemon over EasyTier. Ignores paths that are not files. |
| `HUMANIZE_EASYTIER_NODES` | URL of an Uptime Kuma server | `https://easytier.gd.nkbpal.cn` | Source for the list of shared community EasyTier nodes. |
| `HUMANIZE_COGANCHOR` | path to a `coganchor` binary | the build shipped in the package | The `coganchor` run on this machine. Other machines still get the packaged builds. Ignores paths that are not files. |
| `HUMANIZE_SHADOWS` | a path, `~` allowed | `$XDG_STATE_HOME/humanize/shadows`, else `~/.local/state/humanize/shadows` | Directory for records of local mirrors of remote workspaces. |
| `HUMANIZE_RENDEZVOUS` | a host or address | this machine's outward-facing address | The address the two halves of a remote turn dial to meet. Also the default of `hmz internal anchor --broker`. |
| `HUMANIZE_RENDEZVOUS_PORT` | an integer | `0`, any free port | The port of that meeting point. Listens on every interface. An empty or non-numeric value is an error. |

## Internal commands

These variables give defaults to flags of `hmz internal anchor`, which Humanize runs for itself. You do not normally set them. See [CLI](/reference/cli).

| Variable | Flag | Default | Values |
| --- | --- | --- | --- |
| `HUMANIZE_TARGET` | `--target` | `local` | `ssh://[USER@]HOST[:PORT]`, `docker://CONTAINER[@ENDPOINT]`, `apple-container://NAME`, `slurm://JOBID`, `tcp://HOST:PORT`, `peer://TICKET@HOST:PORT`, `local[:DIR]` |
| `HUMANIZE_HARNESS` | `--harness` | `local` | `local`, or a target URL |
| `HUMANIZE_SHADOW` | `--shadow` | the workspace | a path: the mirror directory on the harness's machine |
| `HUMANIZE_TOKEN` | `--token` | none | the shared secret of a `tcp://` target. `hmz internal anchor serve` reads it too, except with `--peer`. Empty counts as none. |
| `HUMANIZE_LOG` | `--log-level` | `warning`; `info` for `hmz internal anchor rendezvous` | `debug`, `info`, `warning`, `error`. Any other value is reported on standard error and ignored. |

## Desktop

| Variable | Effect |
| --- | --- |
| `HUMANIZE_HMZ` | The `hmz` the app runs for this machine. When set, the app looks for no other `hmz` and installs none. On Windows, give a path inside WSL. |
| `SHELL` | The login shell the app queries for its environment. Default `/bin/zsh`; on Windows, the shell of your WSL account. If the shell does not answer within 5 seconds, the app uses its own environment. |
| `PATH` | On macOS, where the app finds `hmz` when `HUMANIZE_HMZ` is unset. The app adds `~/.local/bin`, `UV_TOOL_BIN_DIR`, `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`, and `/bin` to it. On Windows, the app runs the `hmz` it installs in WSL instead. |

See [Desktop app](/reference/desktop).

## Terminal and display

| Variable | Values | Effect |
| --- | --- | --- |
| `NO_COLOR` | any non-empty value | Disables colour in command-line output. Checked first. |
| `TERM` | `dumb` | Disables colour, as with `NO_COLOR`. |
| `FORCE_COLOR` | non-empty and not `0` | Enables colour even when output is not a terminal. |
| `TEXTUAL_THEME` | a Textual theme name | The theme of the terminal interface. Default `terminal`, which uses your terminal's own colours. Ignores unknown names. |
| `TMUX`, `TERM_PROGRAM`, `LC_TERMINAL` | | In iTerm2 outside tmux (`TERM_PROGRAM` is `iTerm.app` or `LC_TERMINAL` is `iTerm2`, and `TMUX` is empty), `hmz` sets `TEXTUAL_DISABLE_KITTY_KEY=1` unless you set it, so input method text reaches the prompt. |
| `VISUAL`, `EDITOR` | a command | The editor the terminal interface uses to edit a file of an environment. `VISUAL` takes precedence. Default `vi`. |
| `DISPLAY`, `WAYLAND_DISPLAY` | | On Linux, `hmz web` opens a browser only when one of these is set. Otherwise it prints the address. |

## System

| Variable | Effect |
| --- | --- |
| `HOME` | Your home directory, used for every `~` on this page. |
| `PATH` | Where Humanize finds harnesses. |
| `SHELL` | The login shell a daemon started with no terminal queries for its environment. Default: your account's shell, else `/bin/sh`. |
| `UV_TOOL_BIN_DIR` | Added to the `PATH` of a daemon started with no terminal, along with `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`, and `/bin`. |
| `TMPDIR` | The temporary directory. Holds the daemon's socket and lock, so two `hmz` processes with different `TMPDIR` values reach different daemons. |
| `XDG_CONFIG_HOME` | Default `~/.config`. Where Humanize looks for harness configuration and credentials. |
| `XDG_RUNTIME_DIR` | Parent directory for shared `ssh` connection sockets. Falls back to the temporary directory if unset. |
| `DOCKER_HOST` | The Docker daemon for a container target with no endpoint of its own. For a target with an endpoint, `docker` runs without `DOCKER_HOST`, `DOCKER_CONTEXT`, `DOCKER_TLS`, `DOCKER_TLS_VERIFY`, and `DOCKER_CERT_PATH`. |
| `GIT_SSH_COMMAND`, `GIT_SSH` | When neither is set, the `git` that backs up epics runs `ssh` with `BatchMode=yes` and `ConnectTimeout=20`. |
| `CUDA_VISIBLE_DEVICES` | Narrows the GPUs a local or `ssh` environment reports, read on the machine the environment is on: a comma-separated list of indices or `GPU-` UUID prefixes. Set but empty means no GPU. Unset means every GPU `nvidia-smi` lists. |
| `WSL_DISTRO_NAME` | Set by WSL. When present, the daemon reports itself as running in that distribution, and translates a Windows path given for a `.hmzepic` file to [import](/user/export) with `wslpath -u`. No other path is translated. |
| `NO_PROXY`, `no_proxy` | Preserved, with `127.0.0.1` and `localhost` added, for turns that go through a local gateway. |

## Harness homes

Humanize reads each harness's home variable to find its sessions, state, and credentials. When set, the home is the variable's value plus any listed subdirectory. When unset, Humanize uses the default.

| Harness | Variable | Subdirectory | Default |
| --- | --- | --- | --- |
| `claude` | `CLAUDE_CONFIG_DIR` | | `~/.claude` |
| `codex` | `CODEX_HOME` | | `~/.codex` |
| `agy` | none | | `~/.gemini/antigravity-cli` |
| `dsh` | `DSH_HOME` | | `~/.dsh` |
| `grok` | `GROK_HOME` | | `~/.grok` |
| `kimi` | `KIMI_CODE_HOME` | | `~/.kimi-code` |
| `pi` | `PI_CODING_AGENT_DIR` | | `~/.pi/agent` |
| `omp` | `PI_CODING_AGENT_DIR` | | `~/.omp/agent` |
| `qwen` | `QWEN_HOME` | | `~/.qwen` |
| `opencode` | `XDG_DATA_HOME` | `opencode` | `~/.local/share/opencode` |
| `mimo` | `XDG_DATA_HOME` | `mimocode` | `~/.local/share/mimocode` |
| `cursor-agent` | `CURSOR_CONFIG_DIR` | | `~/.cursor` |
| `mcode` | `MINIMAX_DATA_DIR` | | `~/.minimax` |

For `qwen`, Humanize also watches the settings files `QWEN_CODE_SYSTEM_SETTINGS_PATH` and `QWEN_CODE_SYSTEM_DEFAULTS_PATH` name, so a change to them reaches the next turn.

See [Agents and harnesses](/reference/agents) for harness names.

## Account variables

Harnesses read their keys and endpoints from the environment. Humanize uses these same variables in three ways.

### Endpoint

When set by an account (or by your shell when running without an account), Humanize reads the model list from this endpoint.

| Harness | Endpoint variable |
| --- | --- |
| `claude` | `ANTHROPIC_BASE_URL` |
| `codex` | `CODEX_PROVIDER_URL` |
| `agy` | `GOOGLE_GEMINI_BASE_URL` |
| `dsh` | `DEEPSEEK_BASE_URL` |
| `grok` | `GROK_XAI_API_BASE_URL` |
| `kimi` | `KIMI_MODEL_BASE_URL` |
| `pi` | `PI_GATEWAY_URL` |
| `qwen` | `OPENAI_BASE_URL` |
| `opencode` | `OPENCODE_GATEWAY_URL` |
| `mimo` | `MIMO_GATEWAY_URL` |
| `omp`, `cursor-agent`, `mcode` | none |
| `litellm` | `LITELLM_GATEWAY_URL` |

### Hosts a sandboxed turn may reach

When the network is closed, a turn can still reach its harness's model and sign-in hosts. Humanize allows the host from the endpoint variable, plus the host from any variable in the list below ending in `_URL`, `_BASE`, `_HOST`, `_ENDPOINT`, `_ORIGIN`, or `_ISSUER`. Three are exceptions: `ANTHROPIC_BEDROCK_BASE_URL` counts only with its switch, and `OPENAI_API_BASE` for `codex` and `AZURE_API_BASE` for `litellm` do not count. For `claude`, setting a cloud switch also allows that cloud's hosts:

| Switch | Region or resource | Override |
| --- | --- | --- |
| `CLAUDE_CODE_USE_BEDROCK` | `AWS_REGION`, default `us-east-1` | `ANTHROPIC_BEDROCK_BASE_URL` |
| `CLAUDE_CODE_USE_MANTLE` | `AWS_REGION`, default `us-east-1` | `ANTHROPIC_BEDROCK_MANTLE_BASE_URL` |
| `CLAUDE_CODE_USE_ANTHROPIC_AWS` | `AWS_REGION`, default `us-east-1` | `ANTHROPIC_AWS_BASE_URL` |
| `CLAUDE_CODE_USE_VERTEX` | `CLOUD_ML_REGION`, default `us-east5` | `ANTHROPIC_VERTEX_BASE_URL` |
| `CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD` | none | `ANTHROPIC_GOOGLE_CLOUD_BASE_URL` |
| `CLAUDE_CODE_USE_FOUNDRY` | `ANTHROPIC_FOUNDRY_RESOURCE` | `ANTHROPIC_FOUNDRY_BASE_URL` |

`CLAUDE_CODE_USE_FOUNDRY` also applies to `omp`. A region or resource must be a single DNS label.

For `opencode` and `mimo`, Humanize also allows the `baseURL` of the model's provider in the CLI's own configuration: the files under `XDG_CONFIG_HOME`, the file `OPENCODE_CONFIG` or `MIMOCODE_CONFIG` names, and the text in `OPENCODE_CONFIG_CONTENT` or `MIMOCODE_CONFIG_CONTENT`.

See [The sandbox](/user/sandbox).

### Removed under an account

When a turn runs under an [account](/user/accounts), Humanize strips the variables below before applying the account's own variables. A key exported in your shell profile never overrides the account. A turn without an account keeps your shell's variables.

```text
claude
  ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_AWS_API_KEY ANTHROPIC_AWS_BASE_URL
  ANTHROPIC_AWS_WORKSPACE_ID ANTHROPIC_BASE_URL ANTHROPIC_BEDROCK_BASE_URL
  ANTHROPIC_BEDROCK_MANTLE_BASE_URL ANTHROPIC_CONFIG_DIR ANTHROPIC_CUSTOM_HEADERS
  ANTHROPIC_FEDERATION_RULE_ID ANTHROPIC_FOUNDRY_API_KEY ANTHROPIC_FOUNDRY_AUTH_TOKEN
  ANTHROPIC_FOUNDRY_BASE_URL ANTHROPIC_FOUNDRY_RESOURCE ANTHROPIC_GOOGLE_CLOUD_BASE_URL
  ANTHROPIC_GOOGLE_CLOUD_LOCATION ANTHROPIC_GOOGLE_CLOUD_PROJECT
  ANTHROPIC_GOOGLE_CLOUD_WORKSPACE_ID ANTHROPIC_IDENTITY_TOKEN ANTHROPIC_IDENTITY_TOKEN_FILE
  ANTHROPIC_MODEL ANTHROPIC_OAUTH_TOKEN ANTHROPIC_ORGANIZATION_ID ANTHROPIC_PROFILE
  ANTHROPIC_SCOPE ANTHROPIC_SERVICE_ACCOUNT_ID ANTHROPIC_VERTEX_BASE_URL
  ANTHROPIC_VERTEX_PROJECT_ID ANTHROPIC_WORKSPACE_ID AWS_BEARER_TOKEN_BEDROCK AWS_PROFILE
  AWS_REGION CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR CLAUDE_CODE_OAUTH_REFRESH_TOKEN
  CLAUDE_CODE_OAUTH_TOKEN CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR
  CLAUDE_CODE_SKIP_ANTHROPIC_AWS_AUTH CLAUDE_CODE_SKIP_ANTHROPIC_GOOGLE_CLOUD_AUTH
  CLAUDE_CODE_SKIP_BEDROCK_AUTH CLAUDE_CODE_SKIP_FOUNDRY_AUTH CLAUDE_CODE_SKIP_MANTLE_AUTH
  CLAUDE_CODE_SKIP_VERTEX_AUTH CLAUDE_CODE_USE_ANTHROPIC_AWS
  CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_FOUNDRY
  CLAUDE_CODE_USE_GATEWAY CLAUDE_CODE_USE_MANTLE CLAUDE_CODE_USE_VERTEX CLOUD_ML_REGION

agy
  AGY_ADC_AUTH AGY_LLM_GATEWAY_API_KEY AGY_LLM_GATEWAY_CA_CERT AGY_LLM_GATEWAY_HEADERS
  AGY_LLM_GATEWAY_MODELS AGY_LLM_GATEWAY_PROXY_URL AGY_LLM_GATEWAY_URL
  AGY_LLM_GATEWAY_WIRE_PROTOCOL CLOUD_CODE_URL GEMINI_API_KEY GOOGLE_API_KEY
  GOOGLE_APPLICATION_CREDENTIALS GOOGLE_GEMINI_BASE_URL

codex
  AWS_BEARER_TOKEN_BEDROCK AWS_PROFILE AWS_REGION AZURE_OPENAI_API_KEY
  AZURE_OPENAI_API_VERSION AZURE_OPENAI_BASE_URL CODEX_ACCESS_TOKEN CODEX_API_KEY
  CODEX_AUTHAPI_BASE_URL CODEX_OSS_BASE_URL CODEX_PROVIDER_KEY CODEX_PROVIDER_URL
  OPENAI_API_BASE OPENAI_API_KEY OPENAI_BASE_URL OPENAI_FEDERATION_RULE_ID
  OPENAI_IDENTITY_TOKEN_FILE

dsh
  DEEPSEEK_API_KEY DEEPSEEK_BASE_URL DEEPSEEK_SEARCH_BASE_URL DSH_GATEWAY_API

grok
  GROK_AUTH GROK_AUTH_PATH GROK_AUTH_PROVIDER_COMMAND GROK_AUTH_PROVIDER_LABEL
  GROK_AUTH_TOKEN_TTL GROK_CLI_CHAT_PROXY_BASE_URL GROK_CODE_XAI_API_KEY GROK_CONFIG
  GROK_CONFIG_PATH GROK_DEFAULT_MODEL GROK_GATEWAY_API_BACKEND GROK_MODELS_BASE_URL
  GROK_MODELS_LIST_URL GROK_OAUTH2_CLIENT_ID GROK_OAUTH2_ISSUER GROK_OIDC_AUDIENCE
  GROK_OIDC_CLIENT_ID GROK_OIDC_ISSUER GROK_OIDC_SCOPES GROK_XAI_API_BASE_URL XAI_API_KEY

kimi
  KIMI_API_KEY KIMI_BASE_URL KIMI_CODE_BASE_URL KIMI_CODE_CUSTOM_HEADERS
  KIMI_CODE_OAUTH_HOST KIMI_MODEL_ADAPTIVE_THINKING KIMI_MODEL_API_KEY KIMI_MODEL_BASE_URL
  KIMI_MODEL_CAPABILITIES KIMI_MODEL_DISPLAY_NAME KIMI_MODEL_MAX_COMPLETION_TOKENS
  KIMI_MODEL_MAX_CONTEXT_SIZE KIMI_MODEL_MAX_OUTPUT_SIZE KIMI_MODEL_MAX_TOKENS
  KIMI_MODEL_NAME KIMI_MODEL_PROVIDER_TYPE KIMI_MODEL_REASONING_KEY KIMI_MODEL_TEMPERATURE
  KIMI_MODEL_THINKING_EFFORT KIMI_MODEL_THINKING_KEEP KIMI_MODEL_TOP_P KIMI_OAUTH_HOST
  KIMI_REGION KIMI_REGISTRY_API_KEY MOONSHOT_API_KEY

pi
  AI_GATEWAY_API_KEY ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_OAUTH_TOKEN
  ANT_LING_API_KEY AWS_ACCESS_KEY_ID AWS_BEARER_TOKEN_BEDROCK AWS_PROFILE AWS_REGION
  AWS_SECRET_ACCESS_KEY AZURE_OPENAI_API_KEY AZURE_OPENAI_API_VERSION AZURE_OPENAI_BASE_URL
  AZURE_OPENAI_DEPLOYMENT_NAME_MAP AZURE_OPENAI_RESOURCE_NAME BASETEN_API_KEY
  CEREBRAS_API_KEY CLAUDE_CODE_OAUTH_TOKEN CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_API_KEY
  CLOUDFLARE_GATEWAY_ID COPILOT_GITHUB_TOKEN DEEPSEEK_API_KEY FIREWORKS_API_KEY
  GCLOUD_PROJECT GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_CLOUD_API_KEY GOOGLE_CLOUD_LOCATION
  GOOGLE_CLOUD_PROJECT GROK_CODE_XAI_API_KEY GROQ_API_KEY HF_TOKEN KIMI_API_KEY META_API_KEY
  MINIMAX_API_KEY MINIMAX_CN_API_KEY MISTRAL_API_KEY MOONSHOT_API_KEY NVIDIA_API_KEY
  OPENAI_API_KEY OPENCODE_API_KEY OPENROUTER_API_KEY PI_GATEWAY_API PI_GATEWAY_KEY
  PI_GATEWAY_MODEL PI_GATEWAY_URL QWEN_TOKEN_PLAN_API_KEY QWEN_TOKEN_PLAN_CN_API_KEY
  RADIUS_API_KEY TOGETHER_API_KEY TYPESAFE_API_KEY XAI_API_KEY XIAOMI_API_KEY
  XIAOMI_TOKEN_PLAN_AMS_API_KEY XIAOMI_TOKEN_PLAN_CN_API_KEY XIAOMI_TOKEN_PLAN_SGP_API_KEY
  ZAI_API_KEY ZAI_CODING_CN_API_KEY

omp
  ABLITERATION_API_KEY AIAND_API_KEY AIMLAPI_API_KEY AI_GATEWAY_API_KEY
  ALIBABA_CODING_PLAN_API_KEY ALIBABA_TOKEN_PLAN_API_KEY ANTHROPIC_API_KEY
  ANTHROPIC_FOUNDRY_API_KEY ANTHROPIC_OAUTH_TOKEN AWS_ACCESS_KEY_ID AWS_BEARER_TOKEN_BEDROCK
  AWS_PROFILE AWS_REGION AWS_SECRET_ACCESS_KEY AZURE_OPENAI_API_KEY
  BAILIAN_TOKEN_PLAN_API_KEY BASETEN_API_KEY BIGMODEL_API_KEY CEREBRAS_API_KEY
  CHARM_HYPER_API_KEY CLAUDE_CODE_OAUTH_TOKEN CLAUDE_CODE_USE_FOUNDRY CLINE_API_KEY
  CLOUDFLARE_AI_GATEWAY_API_KEY COMMAND_CODE_API_KEY COPILOT_GITHUB_TOKEN COREWEAVE_API_KEY
  COREWEAVE_PROJECT CURSOR_ACCESS_TOKEN DEEPINFRA_API_KEY DEEPSEEK_API_KEY DEVIN_API_KEY
  FIREPASS_API_KEY FIREWORKS_API_KEY FOUNDRY_BASE_URL FUGU_API_KEY GEMINI_API_KEY
  GITLAB_TOKEN GMI_API_KEY GOOGLE_API_KEY GOOGLE_APPLICATION_CREDENTIALS
  GOOGLE_CLOUD_API_KEY GOOGLE_CLOUD_LOCATION GOOGLE_CLOUD_PROJECT GROK_CODE_XAI_API_KEY
  GROQ_API_KEY HF_TOKEN HUGGINGFACE_HUB_TOKEN HYPER_API_KEY KILO_API_KEY KIMI_API_KEY
  LITELLM_API_KEY LLAMA_CPP_API_KEY LM_STUDIO_API_KEY META_API_KEY MINIMAX_API_KEY
  MINIMAX_CODE_API_KEY MINIMAX_CODE_CN_API_KEY MISTRAL_API_KEY MODEL_API_KEY
  MOONSHOT_API_KEY NANO_GPT_API_KEY NOVITA_API_KEY NVIDIA_API_KEY OLLAMA_API_KEY
  OLLAMA_CLOUD_API_KEY OMP_AUTH_BROKER_TOKEN OMP_AUTH_BROKER_URL OPENAI_API_KEY
  OPENAI_CODEX_OAUTH_TOKEN OPENCODE_API_KEY OPENROUTER_API_KEY QIANFAN_API_KEY
  QWEN_OAUTH_TOKEN QWEN_PORTAL_API_KEY SAKANA_API_KEY SILICONFLOW_API_KEY
  SILICONFLOW_CN_API_KEY SYNTHETIC_API_KEY TOGETHER_API_KEY UMANS_AI_CODING_PLAN_API_KEY
  VENICE_API_KEY VERCEL_AI_GATEWAY_API_KEY VLLM_API_KEY WAFER_SERVERLESS_API_KEY
  WANDB_API_KEY XAI_API_KEY XAI_OAUTH_TOKEN XIAOMI_API_KEY XIAOMI_TOKEN_PLAN_AMS_API_KEY
  XIAOMI_TOKEN_PLAN_CN_API_KEY XIAOMI_TOKEN_PLAN_SGP_API_KEY YOLO_AUTO_API_KEY ZAI_API_KEY
  ZENMUX_API_KEY ZHIPU_API_KEY

qwen
  ANTHROPIC_API_KEY ANTHROPIC_BASE_URL ANTHROPIC_MODEL BAILIAN_CODING_PLAN_API_KEY
  BAILIAN_TOKEN_PLAN_API_KEY GEMINI_API_KEY GEMINI_MODEL GOOGLE_API_KEY
  GOOGLE_CLOUD_LOCATION GOOGLE_CLOUD_PROJECT GOOGLE_GEMINI_BASE_URL
  GOOGLE_GENAI_USE_VERTEXAI GOOGLE_MODEL GOOGLE_VERTEX_BASE_URL OPENAI_API_BASE
  OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL QWEN_API_KEY QWEN_BASE_URL QWEN_CODE_MODEL
  QWEN_DEFAULT_AUTH_TYPE QWEN_MODEL QWEN_OAUTH_MODELS

opencode
  ANTHROPIC_API_KEY ANTHROPIC_BASE_URL AWS_BEARER_TOKEN_BEDROCK AWS_PROFILE AWS_REGION
  AZURE_API_KEY AZURE_RESOURCE_NAME DEEPSEEK_API_KEY GEMINI_API_KEY GITHUB_TOKEN
  GOOGLE_API_KEY GOOGLE_CLOUD_LOCATION GOOGLE_CLOUD_PROJECT GOOGLE_GENERATIVE_AI_API_KEY
  GOOGLE_VERTEX_LOCATION GOOGLE_VERTEX_PROJECT GROK_CODE_XAI_API_KEY MISTRAL_API_KEY
  OPENAI_API_KEY OPENCODE_API_KEY OPENCODE_AUTH_CONTENT OPENCODE_CONFIG_CONTENT
  OPENCODE_GATEWAY_KEY OPENCODE_GATEWAY_MODEL OPENCODE_GATEWAY_NPM OPENCODE_GATEWAY_URL
  OPENCODE_WELLKNOWN OPENROUTER_API_KEY XAI_API_KEY

mimo
  ANTHROPIC_API_KEY ANTHROPIC_BASE_URL AWS_BEARER_TOKEN_BEDROCK AWS_PROFILE AWS_REGION
  AZURE_API_KEY AZURE_RESOURCE_NAME DEEPSEEK_API_KEY GOOGLE_CLOUD_PROJECT
  GOOGLE_GENERATIVE_AI_API_KEY GOOGLE_VERTEX_LOCATION GROK_CODE_XAI_API_KEY
  MIMOCODE_AUTH_CONTENT MIMOCODE_CONFIG_CONTENT MIMO_API_KEY MIMO_GATEWAY_API
  MIMO_GATEWAY_KEY MIMO_GATEWAY_MODEL MIMO_GATEWAY_URL OPENAI_API_KEY OPENROUTER_API_KEY
  XAI_API_KEY XIAOMI_API_KEY

cursor-agent
  CURSOR_API_BASE_URL CURSOR_API_ENDPOINT CURSOR_API_KEY CURSOR_API_URL CURSOR_AUTH_TOKEN
  CURSOR_LOCAL_AGENT_API_KEY

mcode
  MAVIS_REGION MCODE_API_BASE_URL MCODE_AUTH_BASE_URL MCODE_AUTH_PROVIDER MCODE_CLIENT_ID
  MCODE_GATEWAY_FORMAT MCODE_GATEWAY_MODEL MCODE_GATEWAY_URL MCODE_PROVIDER_API_KEY
  MCODE_REGION MINIMAX_API_KEY MINIMAX_CN_API_KEY

litellm
  ANTHROPIC_API_KEY AWS_PROFILE AWS_REGION_NAME AZURE_API_BASE AZURE_API_KEY
  AZURE_API_VERSION DEEPSEEK_API_KEY GEMINI_API_KEY GOOGLE_API_KEY GROK_CODE_XAI_API_KEY
  GROQ_API_KEY LITELLM_GATEWAY_API LITELLM_GATEWAY_KEY LITELLM_GATEWAY_URL MISTRAL_API_KEY
  OPENAI_API_KEY OPENROUTER_API_KEY VERTEXAI_LOCATION VERTEXAI_PROJECT XAI_API_KEY
```

`litellm` is the local gateway, not a harness.

## Set by Humanize

Humanize sets these variables for the programs it starts.

| Variable | Set for | Value |
| --- | --- | --- |
| `HUMANIZE` | a harness started through `hmz internal anchor` | Humanize's version |
| `HUMANIZE_TARGET` | the same | the target |
| `HUMANIZE_WORKSPACE` | the same | the workspace as the target names it |
| `HUMANIZE_SHADOW` | a harness placed on another machine | its mirror directory there |
| `HUMANIZE_TOKEN` | a local `coganchor` serving one session, and the one a Slurm job serves over TCP | the session's token; removed locally when there is none |
| `HUMANIZE_AICHAN_LINK` | [Ai-chan](/user/ai-chan)'s conversation, which refuses to start without it | the path of her scoped link to the daemon |
| `COGANCHOR_BINARIES` | every `coganchor` | the directory of packaged builds copied to other machines |
| the account's variables | every turn, sign-in, and model listing under an account | as the account holds them |
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, `CLAUDE_CODE_NO_MODEL_FALLBACK` | every `claude` turn | `1` |
| `GROK_FOLDER_TRUST` | every `grok` turn | `0` |
| `DSH_PERMISSION_MODE`, `DSH_HOME` | every `dsh` turn | `danger-full-access`; the home Humanize keeps for the agent |
| `PKG_NATIVE_CACHE_PATH` | `dsh` turns inside the sandbox | the sandbox's scratch directory |
| `OPENCODE_PERMISSION`, `MIMOCODE_PERMISSION` | `opencode` and `mimo` turns with a sandbox or a web search setting | the tool permissions that follow from them, as JSON |
| `MIMOCODE_DISABLE_CLAUDE_CODE` | `mimo` turns whose sandbox cannot read `~/.claude.json` | `1` |
| `NODE_COMPILE_CACHE` | `pi` and `qwen` turns on this machine, unless already set | a cache directory of Humanize's |
| `NODE_OPTIONS`, `HMZ_PRELOAD_AT` | `kimi`, `pi`, `qwen`, and `mimo` turns on this machine that a flow hooks into | a `--require` added to `NODE_OPTIONS`; the address the preload reports to. The preload sets `HMZ_PRELOAD_IN` for the processes that turn starts. |
| `PATH` | turns of an agent a flow gives command lines | a directory holding those commands, put first |
| `HMZ_PI_TOOLS` | `pi` turns given tools by a flow | the command of the tool bridge, as JSON |
| `TMPDIR`, `TMP`, `TEMP` | everything inside the sandbox | the sandbox's scratch directory |
| `XDG_CACHE_HOME`, `UV_CACHE_DIR`, `npm_config_cache`, `PIP_CACHE_DIR`, `GOCACHE` | inside the sandbox, where the usual location is not writable | a directory under the scratch directory |
| `HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY`, `https_proxy`, `http_proxy`, `all_proxy` | inside the sandbox with the network closed | the sandbox's proxy on `127.0.0.1`. Empties `NO_PROXY` and `no_proxy` and sets `NODE_USE_ENV_PROXY` to `1`. |
| `NVIDIA_VISIBLE_DEVICES` | containers of Docker environments | `void`, except when Docker's `--gpus` hands out the GPUs |
| `HOME` | containers of Docker and Apple container environments | `/tmp`, unless the environment's own variables set it |
| `TERM` | a terminal opened in an environment | `xterm-256color` |
| `ET_NETWORK_SECRET` | `easytier-core` | the network's secret. Every other `ET_` variable is removed. |
| `LITELLM_LOCAL_MODEL_COST_MAP` | the local LiteLLM gateway | `True`. `DATABASE_URL`, `LITELLM_MASTER_KEY`, and `CONFIG_FILE_PATH` are removed. |
| `GIT_TERMINAL_PROMPT` | the `git` that backs up epics | `0` |
| `SSH_ASKPASS_REQUIRE` | the `ssh` that checks a runtime | `never`: fails rather than prompts |

## What crosses to another machine

Commands run on another machine receive your environment laid over that machine's, except for:

- `DISPLAY`, `HOME`, `HOSTNAME`, `HOSTTYPE`, `LOGNAME`, `MACHTYPE`, `MAIL`, `OLDPWD`, `OSTYPE`, `PATH`, `PWD`, `SECURITYSESSIONID`, `SHELL`, `SHLVL`, `TEMP`, `TMP`, `TMPDIR`, `USER`, `WAYLAND_DISPLAY`, `_`
- variables starting with `Apple`, `DYLD_`, `HUMANIZE_`, `LD_`, `SSH_`, `XDG_`, `XPC_`, or `__CF`
- variables named with `--private`

See [Runtimes: servers, containers and clusters](/user/runtimes).
