---
title: Agents and harnesses
description: Look up how an agent is written, which harnesses Humanize drives, what each one can do, its effort ladder, its sign-in ways, the fault classes of a failed turn and the agent layer's config in Python.
---

# Agents and harnesses

Look up agent spec syntax, harness capabilities, effort ladders, sign-in ways, fault classes, and the `AgentConfig` options of the agent layer. For usage guides, see [Coding agents](/user/agents), [Accounts](/user/accounts), and [Agent roles](/builder/agents).

## Agent spec

![An agent spec is a role, a harness, an optional account, a model and an optional effort; or a role and the name of a virtual nous](/diagrams/reference-agents-1.svg)

```text
hmz exec   -a ROLE=CLI[@ACCOUNT]/MODEL[:EFFORT][,...]
hmz exec   -a ROLE=NOUS[,...]
hmz chat start -a CLI[@ACCOUNT]/MODEL[:EFFORT]
```

Use the same string in `settings.toml` and the SDK. Omit the role to write a concrete nous.

| Part | Rule |
| --- | --- |
| `ROLE` | A Python identifier matching an agent field declared by the flow. Required on `hmz exec`, omitted on `hmz chat`. Giving a role twice is an error. |
| `CLI` | A harness name or alias from the table below, or an added ACP CLI name. |
| `@ACCOUNT` | The account that runs the turns. If omitted, the agent uses this machine's sign-in. Matches `[A-Za-z0-9][A-Za-z0-9._-]*`. |
| `MODEL` | The model ID listed by the harness. May contain `/` and `:`. |
| `:EFFORT` | A rung on the harness's ladder, optionally prefixed with `swarm`. If omitted, empty, or `auto`, the harness uses its default. |
| `NOUS` | A virtual nous name: a word matching `[A-Za-z][A-Za-z0-9_.-]*` that is not a harness name and contains no `/`. See [Nous](/user/nous). |

Humanize parses the spec from both ends. Text after the last `:` is parsed as an effort only if it consists of letter words joined by `-`, `_`, or a space. Unknown efforts are rejected when creating the agent, before the first turn.

| Spec | Harness | Account | Model | Effort |
| --- | --- | --- | --- | --- |
| `claude/claude-haiku-4-5:low` | `claude` | this machine's | `claude-haiku-4-5` | `low` |
| `codex@work/gpt-5:high` | `codex` | `work` | `gpt-5` | `high` |
| `opencode/anthropic/claude-x:high` | `opencode` | this machine's | `anthropic/claude-x` | `high` |
| `mcode/custom_provider:gateway/m` | `mcode` | this machine's | `custom_provider:gateway/m` | default |
| `qwen/qwen3:latest:auto` | `qwen` | this machine's | `qwen3:latest` | default |
| `qwen/qwen3:latest` | `qwen` | this machine's | `qwen3` | `latest`, which is refused |
| `kimi/kimi-for-coding:swarmmax` | `kimi` | this machine's | `kimi-for-coding` | `max`, as a swarm |

Append `:auto` if a model name ends with `:` followed by a word, as in the fifth row.

| Mistake | Message |
| --- | --- |
| Unknown harness | `unknown CLI 'NAME'; see the CLI reference for supported names` |
| No model | `missing model; expected [NAME=]CLI[@PROVIDER]/MODEL[:EFFORT]` |
| `@` with nothing after it | `expected an account after @, as in claude@deepseek/MODEL:EFFORT` |
| A role that is no identifier | `'NAME' is not a place a flow could declare` |
| No role on `hmz exec` | `expected <role>=<harness>[@<provider>]/<model>[:<effort>] or <role>=<nous>` |
| A role given twice | `the role 'NAME' is given twice` |
| Several specs where `settings.toml` or the SDK takes one | ``expected one agent: a `,` separates several, each read on its own`` |
| A nous name that is not saved | `'NAME' is no nous written down` |

## Harnesses

Each harness name matches its installed command; `dsh` and `litellm` are Python packages with no command. Restrict a flow role to one harness using its role type. See the [CLI reference](/reference/cli) for flags.

| Harness | Product | Aliases | Role type | Install |
| --- | --- | --- | --- | --- |
| `claude` | Claude Code | `claude-code` | `ClaudeCodeAgent` | `npm i -g @anthropic-ai/claude-code` |
| `agy` | Antigravity | `antigravity` | `AntigravityAgent` |  |
| `codex` | Codex |  | `CodexAgent` | `npm i -g @openai/codex` |
| `dsh` | DeepSeek Harness | `deepseek-harness` | `DeepSeekHarnessAgent` | `pip install 'deepseek-harness-sdk>=0.1.5rc1,<0.1.6' 'python-dotenv>=1.2.3'` |
| `grok` | Grok Build | `grok-build`, `grokbuild` | `GrokBuildAgent` | `npm i -g @xai-official/grok` |
| `kimi` | Kimi Code | `kimi-code` | `KimiCodeAgent` | `npm i -g @moonshot-ai/kimi-code` |
| `pi` | Pi |  | `PiAgent` | `npm i -g @earendil-works/pi-coding-agent` |
| `omp` | Oh My Pi | `oh-my-pi` | `OhMyPiAgent` | `curl -fsSL https://omp.sh/install \| sh` |
| `qwen` | Qwen Code | `qwen-code` | `QwenCodeAgent` | `npm i -g @qwen-code/qwen-code` |
| `opencode` | OpenCode |  | `OpenCodeAgent` | `npm i -g opencode-ai` |
| `mimo` | MiMo Code | `mimocode`, `mimo-code` | `MiMoCodeAgent` | `npm i -g @mimo-ai/cli` |
| `cursor-agent` | Cursor CLI | `cursor-cli` | `CursorAgent` | `curl https://cursor.com/install -fsS \| bash` |
| `mcode` | MiniMax Code | `minimax`, `minimax-code` | `MiniMaxCodeAgent` | `npm i -g @minimax-ai/code` |
| `litellm` | LiteLLM |  | `LiteLLMAgent` | `pip install 'litellm>=1.105'` |
| any name | A CLI added over ACP | | `Agent` | Added by its command. See [Gateways, LiteLLM and custom CLIs](/user/gateways). |

Install the matching Humanize extra for `dsh` (`hmz[dsh]`), `kimi` (`hmz[kimi]`), and `litellm` (`hmz[litellm]`). `litellm` is a bare model rather than a coding agent: it runs one chat completion per turn with no tools or files.

## Capabilities

A role with capability mixins requires a harness that supports all of them. Append `AgentMixin` to any column name to get the mixin class, such as `SteeringAgentMixin`. See [Agent roles](/builder/agents).

| Harness | FakeTool | GoalCommand | LoopCommand | Steering | PermissionRequestHook | SubagentStartHook | SubagentStopHook | AskUserHook |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `claude` | yes | yes | yes | yes | yes | yes | yes | yes |
| `agy` | yes |  |  |  |  |  |  |  |
| `codex` | yes | yes |  | yes | yes | yes | yes | yes |
| `dsh` | yes | yes |  |  |  |  |  |  |
| `grok` | yes |  |  |  |  |  |  |  |
| `kimi` |  | yes |  | yes | yes |  |  | yes |
| `pi` | yes |  |  | yes |  |  |  | yes |
| `omp` | yes |  |  | yes |  |  |  | yes |
| `qwen` | yes |  |  |  |  |  |  |  |
| `opencode` | yes |  |  |  |  |  |  |  |
| `mimo` | yes |  |  |  |  |  |  |  |
| `cursor-agent` |  |  |  |  |  | yes | yes |  |
| `mcode` |  |  |  |  |  | yes | yes |  |
| `litellm` |  |  |  |  |  |  |  |  |
| ACP CLI |  |  |  |  |  |  |  |  |

## Other harness facts

| Harness | Web search can be switched | Forks a session | One server for all conversations | Swarm | Local LiteLLM gateway | Silent before the watchdog acts |
| --- | --- | --- | --- | --- | --- | --- |
| `claude` | yes | yes | no | no | yes | 900 s |
| `agy` | yes | no | no | no | yes | 900 s |
| `codex` | yes | yes | yes | no | yes | 900 s |
| `dsh` | yes | no | no | no | yes | 360 s |
| `grok` | yes | yes | no | no | yes | 900 s |
| `kimi` | yes | yes | yes | yes | yes | 900 s |
| `pi` | no | yes | no | no | yes | 900 s |
| `omp` | no | yes | no | no | no | 900 s |
| `qwen` | yes | yes | no | no | yes | 900 s |
| `opencode` | yes | yes | no | no | yes | 900 s |
| `mimo` | yes | yes | no | no | yes | 900 s |
| `cursor-agent` | no | no | no | no | no | 900 s |
| `mcode` | no | no | no | no | yes | 900 s |
| `litellm` | no | yes | no | no | no | 900 s |
| ACP CLI | no | yes | no | no | no | 900 s |

- Web search: if no, a flow cannot toggle the harness's built-in web search.
- One server: all conversations on an agent share one server process; restarting it ends the agent's other active turns.
- Local LiteLLM gateway: the harness supports the `litellm-` sign-in ways below.
- An ACP CLI forks only if it implements `session/fork`.

## Effort ladders

Rungs are listed hardest first, using each harness's own names. Each model supports a subset of its harness's ladder. See [Effort and swarm mode](/user/efforts).

| Harness | Rungs |
| --- | --- |
| `claude` | `ultracode`, `max`, `xhigh`, `high`, `medium`, `low` |
| `agy` | `high`, `medium`, `low` |
| `codex` | `ultra`, `max`, `xhigh`, `high`, `medium`, `low` |
| `dsh` | `max`, `high`, `low`, `off` |
| `grok` | `xhigh`, `high`, `medium`, `low` |
| `kimi` | `max`, `high`, `medium`, `low` |
| `pi` | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| `omp` | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| `qwen` | `max`, `xhigh`, `high`, `medium`, `low`, `none` |
| `opencode` | `xhigh`, `high`, `medium`, `low`, `minimal` |
| `mimo` | `xhigh`, `high`, `medium`, `low`, `minimal` |
| `cursor-agent` | `max`, `xhigh`, `extra-high`, `high`, `medium`, `low`, `minimal`, `none` |
| `mcode` | `max`, `xhigh`, `high`, `medium`, `low` |
| `litellm` | `high`, `medium`, `low`, `minimal`, `none` |
| ACP CLI | `as configured`; any word is accepted and none is sent |

- Every harness accepts `auto` or an omitted effort.
- Prefix a rung with `swarm` (for example, `swarmmax` for `max`) to run the turn as a fleet of subagents; `swarm` alone is a swarm at the default effort. Supported only on `kimi`.
- `ultracode` on `claude` runs at `xhigh` and lets the turn orchestrate its own fleet.

The UI displays each rung with a label:

| Rung | Shown as |
| --- | --- |
| `ultracode` | Ultracode |
| `ultra` | Ultra |
| `max` | Max |
| `xhigh`, `extra-high` | Extra high |
| `high` | High |
| `medium` | Medium |
| `low` | Low |
| `minimal` | Minimal |
| `none` | None |
| `off` | Off |
| `as configured` | As configured |

## Sign-in ways

An account stores the credentials for one sign-in way of one CLI. Ways that run a command require the terminal interface; ways that only prompt for values also work in the app. See [Accounts](/user/accounts) and [Gateways, LiteLLM and custom CLIs](/user/gateways).

Two shared groups of sign-in ways apply across harnesses:

| Way | Offered to | What it is |
| --- | --- | --- |
| `env` | Every CLI except `dsh` and `litellm` | Custom environment variables, entered as `NAME=VALUE` lines. |
| `litellm-openai-key`, `litellm-anthropic-key`, `litellm-gemini-key`, `litellm-xai-key`, `litellm-openrouter-key`, `litellm-deepseek-key`, `litellm-groq-key`, `litellm-mistral-key`, `litellm-openai-gateway`, `litellm-anthropic-gateway`, `litellm-bedrock`, `litellm-vertex`, `litellm-azure` | `claude`, `agy`, `codex`, `dsh`, `grok`, `kimi`, `pi`, `qwen`, `opencode`, `mimo`, `mcode`, when the `hmz[litellm]` extra is installed | The matching `litellm` way, routed through a local LiteLLM gateway. Prompts for the same values. |

### claude

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `login` | sign in to a Claude subscription, as `claude auth login` does | `claude auth login` |  |
| `console` | sign in to an Anthropic Console account, billed per token, as `claude auth login --console` does | `claude auth login --console` |  |
| `token` | a long-lived token, as `claude setup-token` prints one |  | `CLAUDE_CODE_OAUTH_TOKEN` |
| `key` | an Anthropic API key, from the console |  | `ANTHROPIC_API_KEY` |
| `wif` | Workload Identity Federation: a token another identity provider issues, traded for Anthropic's |  | `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID`, `ANTHROPIC_IDENTITY_TOKEN_FILE` |
| `anthropic-gateway` | an endpoint speaking Anthropic's Messages API: a proxy, a router, another vendor |  | `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` |
| `bedrock-gateway` | an endpoint speaking Amazon Bedrock's API, which holds the AWS credentials itself |  | `ANTHROPIC_BEDROCK_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` |
| `vertex-gateway` | an endpoint speaking Vertex AI's API, which holds the Google Cloud credentials itself |  | `ANTHROPIC_VERTEX_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_VERTEX_PROJECT_ID`, `CLOUD_ML_REGION` |
| `bedrock` | Anthropic's models on an AWS account of yours |  | `AWS_PROFILE`, `AWS_REGION` |
| `bedrock-key` | Anthropic's models on Amazon Bedrock, by a Bedrock API key |  | `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION` |
| `mantle` | Anthropic's models on Amazon Bedrock's Mantle endpoint, on an AWS account of yours |  | `AWS_PROFILE`, `AWS_REGION` |
| `vertex` | Anthropic's models on a Google Cloud project of yours |  | `ANTHROPIC_VERTEX_PROJECT_ID`, `CLOUD_ML_REGION` |
| `foundry` | Anthropic's models on a Microsoft Foundry resource of yours |  | `ANTHROPIC_FOUNDRY_RESOURCE`, `ANTHROPIC_FOUNDRY_API_KEY` |
| `aws` | Claude Platform on AWS: Anthropic's API, billed through AWS |  | `ANTHROPIC_AWS_WORKSPACE_ID`, `AWS_REGION`, `ANTHROPIC_AWS_API_KEY` |
| `google-cloud` | Claude Platform on Google Cloud: Anthropic's API, billed through Google Cloud |  | `ANTHROPIC_GOOGLE_CLOUD_PROJECT`, `ANTHROPIC_GOOGLE_CLOUD_LOCATION`, `ANTHROPIC_GOOGLE_CLOUD_WORKSPACE_ID` |

### agy

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `login` | sign in to a Google account, in a session opened for it | `agy` |  |
| `key` | a Gemini API key, from AI Studio |  | `GEMINI_API_KEY` |
| `gemini-gateway` | an endpoint speaking Gemini's API: a proxy, a router, another vendor |  | `AGY_LLM_GATEWAY_URL`, `AGY_LLM_GATEWAY_API_KEY` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor |  | `AGY_LLM_GATEWAY_URL`, `AGY_LLM_GATEWAY_API_KEY`, `AGY_LLM_GATEWAY_MODELS` |
| `adc` | Google Application Default Credentials, for a service account |  | `GOOGLE_APPLICATION_CREDENTIALS` |

### codex

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `login` | sign in to a ChatGPT account, in a browser | `codex login` |  |
| `device` | the same, from a machine with no browser on it | `codex login --device-auth` |  |
| `key` | an OpenAI API key, which codex keeps in its own store | `codex login --with-api-key` | `OPENAI_API_KEY` |
| `token` | an access token, which is how an organisation hands one out | `codex login --with-access-token` | `CODEX_ACCESS_TOKEN` |
| `workload` | a ChatGPT workspace's workload identity, where nobody signs in |  | `OPENAI_FEDERATION_RULE_ID`, `OPENAI_IDENTITY_TOKEN_FILE` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor |  | `CODEX_PROVIDER_URL`, `CODEX_PROVIDER_KEY` |
| `azure` | OpenAI's models on an Azure OpenAI resource of yours |  | `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION` |
| `bedrock` | OpenAI's models on an AWS account of yours |  | `AWS_PROFILE`, `AWS_REGION` |
| `bedrock-key` | the same, with a Bedrock API key |  | `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION` |
| `ollama` | open models served by Ollama |  | `CODEX_OSS_BASE_URL` |
| `lmstudio` | open models served by LM Studio |  | `CODEX_OSS_BASE_URL` |

### dsh

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `key` | a DeepSeek API key, from the platform |  | `DEEPSEEK_API_KEY` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor |  | `DEEPSEEK_BASE_URL`, `DEEPSEEK_API_KEY`, `DSH_GATEWAY_API` |
| `anthropic-gateway` | an endpoint speaking Anthropic's Messages API: a proxy, a router, another vendor |  | `DEEPSEEK_BASE_URL`, `DEEPSEEK_API_KEY` |
| `gemini-gateway` | an endpoint speaking Gemini's API: a proxy, a router, another vendor |  | `DEEPSEEK_BASE_URL`, `DEEPSEEK_API_KEY` |

### grok

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `login` | sign in to an xAI account, in a browser | `grok login` |  |
| `device` | the same, from a machine with no browser on it | `grok login --device-auth` |  |
| `oidc` | your own identity provider, for an organisation that signs in through one | `grok login` | `GROK_OIDC_ISSUER`, `GROK_OIDC_CLIENT_ID` |
| `provider-command` | a command of your organisation's that prints a token | `grok login` | `GROK_AUTH_PROVIDER_COMMAND` |
| `key` | an xAI API key, from the console |  | `XAI_API_KEY` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor |  | `GROK_XAI_API_BASE_URL`, `XAI_API_KEY`, `GROK_GATEWAY_API_BACKEND` |
| `anthropic-gateway` | an endpoint speaking Anthropic's Messages API: a proxy, a router, another vendor |  | `GROK_XAI_API_BASE_URL`, `XAI_API_KEY` |

### kimi

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `login` | sign in to a Kimi account, by the code it prints | `kimi login --region {KIMI_REGION}` | `KIMI_REGION` |
| `kimi-key` | a Moonshot platform key, or a Kimi for Coding one at https://api.kimi.com/coding/v1 |  | `KIMI_MODEL_API_KEY`, `KIMI_MODEL_BASE_URL`, `KIMI_MODEL_NAME` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor |  | `KIMI_MODEL_BASE_URL`, `KIMI_MODEL_API_KEY`, `KIMI_MODEL_NAME`, `KIMI_MODEL_PROVIDER_TYPE` |
| `anthropic-gateway` | an endpoint speaking Anthropic's Messages API: a proxy, a router, another vendor |  | `KIMI_MODEL_BASE_URL`, `KIMI_MODEL_API_KEY`, `KIMI_MODEL_NAME` |
| `gemini-gateway` | an endpoint speaking Gemini's API: a proxy, a router, another vendor |  | `KIMI_MODEL_BASE_URL`, `KIMI_MODEL_API_KEY`, `KIMI_MODEL_NAME` |

### pi

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `login` | pi's own /login, in a session opened for it | `pi` |  |
| `anthropic-key` | an Anthropic API key, from the console |  | `ANTHROPIC_API_KEY` |
| `anthropic-token` | a long-lived Anthropic token, as `claude setup-token` prints one |  | `ANTHROPIC_OAUTH_TOKEN` |
| `openai-key` | an OpenAI API key, from the platform |  | `OPENAI_API_KEY` |
| `gemini-key` | a Gemini API key, from Google AI Studio |  | `GEMINI_API_KEY` |
| `xai-key` | an xAI API key, from the console |  | `XAI_API_KEY` |
| `openrouter-key` | an OpenRouter API key |  | `OPENROUTER_API_KEY` |
| `deepseek-key` | a DeepSeek API key, from the platform |  | `DEEPSEEK_API_KEY` |
| `groq-key` | a Groq API key, from the console |  | `GROQ_API_KEY` |
| `mistral-key` | a Mistral API key, from La Plateforme |  | `MISTRAL_API_KEY` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor |  | `PI_GATEWAY_URL`, `PI_GATEWAY_KEY`, `PI_GATEWAY_MODEL`, `PI_GATEWAY_API` |
| `anthropic-gateway` | an endpoint speaking Anthropic's Messages API: a proxy, a router, another vendor |  | `PI_GATEWAY_URL`, `PI_GATEWAY_KEY`, `PI_GATEWAY_MODEL` |
| `gemini-gateway` | an endpoint speaking Gemini's API: a proxy, a router, another vendor |  | `PI_GATEWAY_URL`, `PI_GATEWAY_KEY`, `PI_GATEWAY_MODEL` |
| `bedrock` | models on Amazon Bedrock, under an AWS account of yours |  | `AWS_PROFILE`, `AWS_REGION` |
| `vertex` | models on Vertex AI, under a Google Cloud project of yours |  | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` |
| `azure` | OpenAI's models on an Azure OpenAI resource of yours |  | `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY` |

### omp

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `anthropic-key` | an Anthropic API key, from the console |  | `ANTHROPIC_API_KEY` |
| `anthropic-token` | a long-lived Anthropic token, as `claude setup-token` prints one |  | `ANTHROPIC_OAUTH_TOKEN` |
| `openai-key` | an OpenAI API key, from the platform |  | `OPENAI_API_KEY` |
| `gemini-key` | a Gemini API key, from Google AI Studio |  | `GEMINI_API_KEY` |
| `xai-key` | an xAI API key, from the console |  | `XAI_API_KEY` |
| `openrouter-key` | an OpenRouter API key |  | `OPENROUTER_API_KEY` |
| `deepseek-key` | a DeepSeek API key, from the platform |  | `DEEPSEEK_API_KEY` |
| `groq-key` | a Groq API key, from the console |  | `GROQ_API_KEY` |
| `mistral-key` | a Mistral API key, from La Plateforme |  | `MISTRAL_API_KEY` |
| `bedrock` | models on Amazon Bedrock, under an AWS account of yours |  | `AWS_PROFILE`, `AWS_REGION` |
| `vertex` | models on Vertex AI, under a Google Cloud project of yours |  | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` |

### qwen

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `coding-plan` | an Alibaba Cloud Model Studio Coding Plan |  | `OPENAI_BASE_URL`, `OPENAI_API_KEY` |
| `token-plan` | an Alibaba Cloud Model Studio Token Plan |  | `OPENAI_BASE_URL`, `OPENAI_API_KEY` |
| `gemini-key` | a Gemini API key, from AI Studio |  | `GEMINI_API_KEY` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor |  | `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `QWEN_DEFAULT_AUTH_TYPE` |
| `anthropic-gateway` | an endpoint speaking Anthropic's Messages API: a proxy, a router, another vendor |  | `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY` |
| `gemini-gateway` | an endpoint speaking Gemini's API: a proxy, a router, another vendor |  | `GOOGLE_GEMINI_BASE_URL`, `GEMINI_API_KEY` |
| `vertex` | Google's models on a Google Cloud project of yours |  | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` |
| `vertex-key` | a Vertex AI API key, for its express mode |  | `GOOGLE_API_KEY` |

### opencode

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `login` | opencode's own provider list, and whichever way that one takes | `opencode auth login` |  |
| `wellknown` | a provider that hands out its own credential, by URL | `opencode auth login {OPENCODE_WELLKNOWN}` | `OPENCODE_WELLKNOWN` |
| `zen` | an OpenCode Zen key, which its own models run on |  | `OPENCODE_API_KEY` |
| `anthropic-key` | an Anthropic API key, from the console |  | `ANTHROPIC_API_KEY` |
| `openai-key` | an OpenAI API key, from the platform |  | `OPENAI_API_KEY` |
| `gemini-key` | a Gemini API key, from AI Studio |  | `GOOGLE_GENERATIVE_AI_API_KEY` |
| `xai-key` | an xAI API key, from its console |  | `XAI_API_KEY` |
| `openrouter-key` | an OpenRouter key, for every model it routes to |  | `OPENROUTER_API_KEY` |
| `deepseek-key` | a DeepSeek API key, from its platform |  | `DEEPSEEK_API_KEY` |
| `mistral-key` | a Mistral API key, from its console |  | `MISTRAL_API_KEY` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor |  | `OPENCODE_GATEWAY_URL`, `OPENCODE_GATEWAY_KEY`, `OPENCODE_GATEWAY_MODEL`, `OPENCODE_GATEWAY_NPM` |
| `anthropic-gateway` | an endpoint speaking Anthropic's Messages API: a proxy, a router, another vendor |  | `OPENCODE_GATEWAY_URL`, `OPENCODE_GATEWAY_KEY`, `OPENCODE_GATEWAY_MODEL` |
| `gemini-gateway` | an endpoint speaking Gemini's API: a proxy, a router, another vendor |  | `OPENCODE_GATEWAY_URL`, `OPENCODE_GATEWAY_KEY`, `OPENCODE_GATEWAY_MODEL` |
| `bedrock` | the models on an AWS account of yours |  | `AWS_PROFILE`, `AWS_REGION` |
| `vertex` | the models on a Google Cloud project of yours |  | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` |
| `azure` | the models deployed on an Azure OpenAI resource of yours |  | `AZURE_RESOURCE_NAME`, `AZURE_API_KEY` |

### mimo

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `login` | mimocode's own provider list, and whichever way that one takes | `mimo auth login` |  |
| `key` | a MiMo key, which its own models run on |  | `XIAOMI_API_KEY` |
| `anthropic-key` | an Anthropic API key, from the console |  | `ANTHROPIC_API_KEY` |
| `openai-key` | an OpenAI API key, from the platform |  | `OPENAI_API_KEY` |
| `gemini-key` | a Gemini API key, from Google AI Studio |  | `GOOGLE_GENERATIVE_AI_API_KEY` |
| `xai-key` | an xAI API key, from its console |  | `XAI_API_KEY` |
| `openrouter-key` | an OpenRouter key, which every model it routes to runs on |  | `OPENROUTER_API_KEY` |
| `deepseek-key` | a DeepSeek API key, from its platform |  | `DEEPSEEK_API_KEY` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor |  | `MIMO_GATEWAY_URL`, `MIMO_GATEWAY_KEY`, `MIMO_GATEWAY_MODEL`, `MIMO_GATEWAY_API` |
| `anthropic-gateway` | an endpoint speaking Anthropic's Messages API: a proxy, a router, another vendor |  | `MIMO_GATEWAY_URL`, `MIMO_GATEWAY_KEY`, `MIMO_GATEWAY_MODEL` |
| `gemini-gateway` | an endpoint speaking Gemini's API: a proxy, a router, another vendor |  | `MIMO_GATEWAY_URL`, `MIMO_GATEWAY_KEY`, `MIMO_GATEWAY_MODEL` |
| `vertex` | Gemini and Anthropic's models on a Google Cloud project of yours |  | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_VERTEX_LOCATION` |
| `bedrock` | the models on Amazon Bedrock, on an AWS account of yours |  | `AWS_PROFILE`, `AWS_REGION` |
| `azure` | the models on an Azure OpenAI resource of yours |  | `AZURE_RESOURCE_NAME`, `AZURE_API_KEY` |

### cursor-agent

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `login` | sign in to a Cursor account, in a browser | `cursor-agent login` |  |
| `key` | a Cursor API key, from the dashboard |  | `CURSOR_API_KEY` |
| `cursor-gateway` | an endpoint speaking this CLI's own protocol: a proxy, a router, another vendor |  | `CURSOR_API_ENDPOINT`, `CURSOR_API_KEY` |

### mcode

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `login` | sign in to a MiniMax account, in a browser | `mcode login --region {MCODE_REGION}` | `MCODE_REGION` |
| `key` | a MiniMax API key, from the platform | `mcode provider set-minimax-key` | `MCODE_PROVIDER_API_KEY`, `MAVIS_REGION` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor | `mcode provider add --name gateway --base-url {MCODE_GATEWAY_URL} --api-format {MCODE_GATEWAY_FORMAT} --model {MCODE_GATEWAY_MODEL} --api-key-env MCODE_PROVIDER_API_KEY --use` | `MCODE_GATEWAY_URL`, `MCODE_PROVIDER_API_KEY`, `MCODE_GATEWAY_MODEL`, `MCODE_GATEWAY_FORMAT` |
| `anthropic-gateway` | an endpoint speaking Anthropic's Messages API: a proxy, a router, another vendor | `mcode provider add --name gateway --base-url {MCODE_GATEWAY_URL} --api-format anthropic-messages --model {MCODE_GATEWAY_MODEL} --api-key-env MCODE_PROVIDER_API_KEY --use` | `MCODE_GATEWAY_URL`, `MCODE_PROVIDER_API_KEY`, `MCODE_GATEWAY_MODEL` |

### litellm

| Way | What it is | Runs | Asks for |
| --- | --- | --- | --- |
| `openai-key` | an OpenAI API key, from the platform |  | `OPENAI_API_KEY` |
| `anthropic-key` | an Anthropic API key, from the console |  | `ANTHROPIC_API_KEY` |
| `gemini-key` | a Gemini API key, from Google AI Studio |  | `GEMINI_API_KEY` |
| `xai-key` | an xAI API key, from the console |  | `XAI_API_KEY` |
| `openrouter-key` | an OpenRouter API key |  | `OPENROUTER_API_KEY` |
| `deepseek-key` | a DeepSeek API key, from the platform |  | `DEEPSEEK_API_KEY` |
| `groq-key` | a Groq API key, from the console |  | `GROQ_API_KEY` |
| `mistral-key` | a Mistral API key, from La Plateforme |  | `MISTRAL_API_KEY` |
| `openai-gateway` | an endpoint speaking OpenAI's API: a proxy, a router, another vendor |  | `LITELLM_GATEWAY_URL`, `LITELLM_GATEWAY_KEY` |
| `anthropic-gateway` | an endpoint speaking Anthropic's Messages API: a proxy, a router, another vendor |  | `LITELLM_GATEWAY_URL`, `LITELLM_GATEWAY_KEY` |
| `bedrock` | models on Amazon Bedrock, under an AWS account of yours |  | `AWS_PROFILE`, `AWS_REGION_NAME` |
| `vertex` | models on Vertex AI, under a Google Cloud project of yours |  | `VERTEXAI_PROJECT`, `VERTEXAI_LOCATION` |
| `azure` | OpenAI's models on an Azure OpenAI resource of yours |  | `AZURE_API_BASE`, `AZURE_API_KEY`, `AZURE_API_VERSION` |

## Fault classes

When a turn fails, Humanize reads the exit status, then matches the CLI output against an ordered list of signatures, the harness's own first. The first match determines the fault class, retry behavior at the current nous, fallback graph edge, and flow exception. The table lists the classes, not the order in which signatures are tried. See [Nous](/user/nous) and the [Flow API](/reference/flows).

| Fault | What happened | At the same nous | Error in a flow |
| --- | --- | --- | --- |
| `contended` | Two turns reached one local store of the CLI at once. | Retried at least 3 times, at a constant wait. | `HarnessContended` |
| `spent` | The account's quota or balance is used up. | Retried at least once, after at least 30 s. | `HarnessThrottled` |
| `throttled` | Too many requests. | Retried at least once, after at least 30 s. | `HarnessThrottled` |
| `refused` | The credential was refused: expired, revoked, or not signed in. | Never retried. | `HarnessRefused` |
| `unlisted` | The model is not served to this account. | Never retried. | `ModelUnavailable` |
| `retired` | The model is gone, or never existed. | Never retried. | `ModelUnavailable` |
| `missing` | The CLI is not installed, or will not start. | Never retried. | `HarnessMissing`, or `HarnessNotInstalled` when there was nothing to run |
| `sandboxed` | The CLI could not set up its own sandbox on this machine. | Never retried. | `HarnessSandboxed` |
| `unmirrored` | The local copy of another machine's workspace could not be made at its path. | Never retried. | `HarnessUnrecoverable` |
| `fenced` | The run's network fence kept the CLI off a host. | Never retried. | `HarnessUnrecoverable` |
| `killed` | The process died instead of answering: a signal, or out of memory. | Retried at least once, at a constant wait, in a new process. | `HarnessKilled` |
| `dropped` | The connection broke. | Retried at least once, in a new process. | `HarnessDropped` |

- Unmatched failures use the retry count and wait configured on the nous, and raise `HarnessUnrecoverable` in a flow.
- Faults never retried at the same nous still follow their matching edge in a fallback graph. Edges are named after a fault, or `*` for all others.
- No single wait exceeds 60 s.
- Every error above subclasses `HarnessError`.

## Agent layer

Use `hmz.coganchor.agents` to drive a harness directly from Python with no flow and no daemon. Build every agent from an `AgentConfig` subclass for that harness.

```python
from hmz.coganchor.agents import Allowance, Budget, ClaudeCodeSession, Ledger, driver

Agent, Config = driver("claude")
agent = Agent(Config(model="claude-haiku-4-5", effort="low", service_tier="fast"))
agent.allowance = Ledger(Allowance(hours=6, dollars=50), [agent])

session = ClaudeCodeSession(agent, ".")
session.budget = Budget(seconds=90, when="immediately", then="fail")
print(session("Summarise the README."))
```

| Name | What it is |
| --- | --- |
| `driver(name)` | Returns the agent class and config class for a harness name. Returns `AcpAgent` and `AcpAgentConfig` for an added ACP CLI. Raises `KeyError` for an unknown name or an alias such as `claude-code`. |
| `DRIVEN` | Dict mapping built-in harness names to their agent and config class pair. |
| `Unserved` | `ValueError` raised when you build an agent with a setting its harness does not support. |

### AgentConfig

| Field | Default | Meaning |
| --- | --- | --- |
| `model` | required | Model ID. |
| `effort` | required | Rung on the harness's ladder. `""` or `"auto"` sends none. |
| `service_tier` | `"default"` | `"default"` or `"fast"`. `"fast"` requests lower latency at the same reasoning from `claude`, `codex` or `cursor-agent`; any other harness raises `Unserved`. |
| `machine` | `None` | Where turns run. `None` is this machine. See [Machines and moving sessions](/builder/machines). |
| `provider` | `""` | Account name. `""` uses this machine's sign-in. |
| `goals` | `True` | `False` disables the harness's goal feature for the agent: a goal turn raises `RuntimeError`. |
| `web_search` | `None` | `True` turns the CLI's web search on, `False` turns it off, and `None` leaves the CLI's installed default. On a harness that cannot switch web search, `False` raises `Unserved` and `True` changes nothing. |
| `fence` | `None` | Sandbox for the agent: the paths it may read and write, and whether it may go online. `None` applies no sandbox and tells the CLI nothing about what it may do. |
| `budget` | `None` | `Budget` for each turn. `None` sets no cap. |
| `nous` | `""` | Name of a virtual nous whose fallback the turns walk. `""` uses the concrete nous defined by the other fields. |

An `-a` spec sets only the harness, `provider`, `model` and `effort`, or `nous` when it names a virtual nous. A flow run fills `machine`, `web_search` and `fence` from the role's environment and permission. You cannot set `service_tier` from a spec or a flow.

Assign `agent.effort = "low"` or `session.effort = "max"` between turns to change effort for subsequent turns. Set `""` on an agent to revert to its configured effort, or on a session to revert to the agent's effort. An unknown rung raises `Unserved`.

### Budget and Allowance

| Class | Caps | Fields |
| --- | --- | --- |
| `Budget` | One turn | `output` (output tokens), `seconds` (wall clock), `when` (`"next-response"` or `"immediately"`), `then` (`"end"` or `"fail"`) |
| `Allowance` | A whole run | `hours`, `dollars`, `tokens` (millions of output tokens) |

All numeric fields default to `0`, which means no cap. `when="next-response"`, the default, lets the current answer finish before stopping; `"immediately"` stops the turn at once. `then="end"`, the default, returns the output so far; `"fail"` raises `Unrecoverable`.

Set `budget` on the config to cap every session of the agent, or set `session.budget` for a single conversation. Assign `session.budget = Budget()` to opt that session out of the agent's budget.

Attach an `Allowance` through a `Ledger` by assigning `agent.allowance = Ledger(Allowance(...), [agent, ...])` to every agent in the run. When the allowance is spent, every session in the run stops.

### AcpAgentConfig

Configure a CLI added over ACP with `AcpAgentConfig`. `cli` and `command` identify the CLI; the other extra fields control what Humanize offers it as the ACP client, and all default to off.

| Field | Default | Meaning |
| --- | --- | --- |
| `cli` | `""` | The name the CLI was added under. |
| `command` | `()` | The command that starts the CLI, as a tuple of words. `()` uses the command saved when the CLI named by `cli` was added. |
| `reads_files` | `False` | The agent can ask Humanize to read a file. |
| `writes_files` | `False` | The agent can ask Humanize to write a file. |
| `terminals` | `False` | The agent can ask Humanize to run and hold a command on the machine where Humanize runs. |
| `mcp_servers` | `()` | `McpServer(name=, command=, args=, env=)` entries, with `env` as `(name, value)` pairs, started over stdio and added to every conversation alongside the CLI's own servers. |

Humanize refuses `reads_files`, `writes_files` and `terminals` when a turn runs on another machine through that machine's CLI, because the files and commands would be this machine's.
