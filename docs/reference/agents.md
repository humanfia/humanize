---
pageClass: hmz-feature
---

# Agents

<script setup>
import AgentMatrix from '../.vitepress/theme/components/ref-agents/AgentMatrix.vue'
</script>

Reference for the agent layer, `hmz.coganchor.agents`, and for every coding agent CLI it
drives: what each backend is, how a turn of it is run, and what each setting becomes on its
command line. A flow never imports this module; the `Agent` and `Session` a flow is handed are
views the flow runtime makes over it (`hmz.runtime.flowing.harnesses.HarnessDriver`), and
[Flows](/reference/flows) is the flow-level contract.

## Terms

| Term | Definition |
| --- | --- |
| **Backend** | One coding agent CLI, named by the command it is installed as (`claude`, `codex`, …), or an [ACP CLI](#a-cli-of-your-own) added on this machine. |
| **Profile** | `hmz.coganchor.backends.Profile`: the facts about one backend that are not code (home, logs, ladders, hosts, ways in). `backends.PROFILES` holds the built-in ones. |
| **Agent** | An instance of a backend's `AgentBase` subclass: a backend at one config. Holds sessions. |
| **Config** | A frozen `AgentConfig` subclass: model, effort, rung, account, machine, fence, budget, and backend fields. |
| **Session** | One conversation with the backend, identified by the backend's own id once its first turn lands. |
| **Turn** | One prompt and everything the CLI does until it answers, ending on exactly one `result` event. |
| **Rung** | One of the four [permission](#what-an-agent-may-do) levels: `read-only`, `workspace-write`, `auto`, `bypass`. |
| **Effort** | How hard the model is asked to think, in the backend's own words ([Efforts](#efforts)). |
| **Moment** | A point of a turn a [hook](#hooks) may be hung on. |
| **Fence** | What the agent's processes may reach ([The fence](#the-fence)). |
| **Harness** | A backend as the flow runtime drives it: `HarnessKind` names it, `HARNESS_AGENTS` gives its flow protocol. |

## Backends {#backends}

`hmz.coganchor.agents.DRIVEN` maps each built-in backend to its agent and config class.

| Backend | Accepted as | Product | Transport |
| --- | --- | --- | --- |
| `agy` | `agy`, `antigravity` | Antigravity CLI | one process held open (`--input-format stream-json`); a print command per shaped or slash-command turn |
| `claude` | `claude`, `claude-code` | Claude Code | one `claude --print` held open per session (stream-json) |
| `codex` | `codex` | Codex | one `codex app-server --stdio` per agent, shared by its sessions |
| `cursor-agent` | `cursor-agent`, `cursor-cli` | Cursor Agent | one `cursor-agent --print` per turn |
| `dsh` | `dsh`, `deepseek-harness` | DeepSeek Harness | the Python SDK in this process, one runtime per agent |
| `grok` | `grok`, `grok-build`, `grokbuild` | Grok Build | one `grok agent stdio` held open; `grok -p` for turns it cannot express |
| `kimi` | `kimi`, `kimi-code` | Kimi Code | one `kimi web` daemon per agent, shared by its sessions |
| `mcode` | `mcode`, `minimax`, `minimax-code` | MiniMax Code | one `mcode exec` per turn |
| `mimo` | `mimo`, `mimocode`, `mimo-code` | mimocode | one `mimo run` per turn |
| `opencode` | `opencode` | opencode | one `opencode run` per turn |
| `pi` | `pi` | pi | one `pi --mode rpc` held open per session |
| `qwen` | `qwen`, `qwen-code` | Qwen Code | one process held open (stream-json); a command per shaped turn |
| an ACP CLI | its name | any Agent Client Protocol agent | one process held open, JSON-RPC over stdio |
| the person | — | — | the interface |

| Backend | Agent class | Config class | Session class | Session base |
| --- | --- | --- | --- | --- |
| `agy` | `AntigravityCLIAgent` | `AntigravityCLIAgentConfig` | `AntigravityCLISession` | `StreamSessionBase` |
| `claude` | `ClaudeCodeAgent` | `ClaudeCodeAgentConfig` | `ClaudeCodeSession` | `StreamSessionBase` |
| `codex` | `CodexAgent` | `CodexAgentConfig` | `CodexSession` | `SessionBase` |
| `cursor-agent` | `CursorAgent` | `CursorAgentConfig` | `CursorSession` | `CommandSessionBase` |
| `dsh` | `DshAgent` | `DshAgentConfig` | `DshSession` | `SessionBase` |
| `grok` | `GrokBuildAgent` | `GrokBuildAgentConfig` | `GrokBuildSession` | `StreamSessionBase` |
| `kimi` | `KimiCodeCLIAgent` | `KimiCodeCLIAgentConfig` | `KimiCodeCLISession` | `SessionBase` |
| `mcode` | `MiniMaxCodeAgent` | `MiniMaxCodeAgentConfig` | `MiniMaxCodeSession` | `CommandSessionBase` |
| `mimo` | `MimoCodeAgent` | `MimoCodeAgentConfig` | `MimoCodeSession` | `CommandSessionBase` |
| `opencode` | `OpencodeAgent` | `OpencodeAgentConfig` | `OpencodeSession` | `CommandSessionBase` |
| `pi` | `PiAgent` | `PiAgentConfig` | `PiSession` | `StreamSessionBase` |
| `qwen` | `QwenCodeAgent` | `QwenCodeAgentConfig` | `QwenCodeSession` | `StreamSessionBase` |
| an ACP CLI | `AcpAgent` | `AcpAgentConfig` | `AcpSession` | `SessionBase` |
| the person | `HumanAgent` | none (`name=` only) | `HumanSession` | `SessionBase` |

All classes are importable from `hmz.coganchor.agents`.

### Installation and versions

| Backend | Install line (`Profile.installs`) | Driver written against |
| --- | --- | --- |
| `agy` | none recorded | 1.1.28 – 1.2.12 |
| `claude` | `npm i -g @anthropic-ai/claude-code` | 2.1.272 – 2.1.284 |
| `codex` | `npm i -g @openai/codex` | 0.153.4 |
| `cursor-agent` | `curl https://cursor.com/install -fsS \| bash` | not recorded |
| `dsh` | `pip install 'deepseek-harness-sdk>=0.1.1rc1,<0.1.2' 'python-dotenv>=1.2.3'` (the `[dsh]` extra) | SDK `>=0.1.1rc1,<0.1.2` (`backends.DSH_SDK`) |
| `grok` | `npm i -g @xai-official/grok` | 1.0.24 |
| `kimi` | `npm i -g @moonshot-ai/kimi-code` (plus the `[kimi]` extra) | 0.42.0 |
| `mcode` | `npm i -g @minimax-ai/code` | 0.5.9 |
| `mimo` | `npm i -g @mimo-ai/cli` | not recorded |
| `opencode` | `npm i -g opencode-ai` | not recorded |
| `pi` | `npm i -g @earendil-works/pi-coding-agent` | 0.84.0 – 0.85.1 |
| `qwen` | `npm i -g @qwen-code/qwen-code` | not recorded |

- A backend's program is found on `PATH`, else in `~/.local/bin`, `/usr/local/bin`,
  `/opt/homebrew/bin`, `/usr/bin`, `/bin` (`backends.program`).
- A turn whose CLI cannot be spawned exits 127 and fails with fault `missing`. Under a flow the
  session is refused first with `HarnessNotInstalled: <cli> is not installed here: <install
  line>`; a backend with no recorded line says `install <cli> and put it on PATH`.

<small>Defined in [`src/hmz/coganchor/backends.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/backends.py) (`PROFILES`, `installing`, `program`), [`src/hmz/coganchor/agents/__init__.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/__init__.py) (`DRIVEN`).</small>

## Capability matrix {#capability-matrix}

<AgentMatrix />

| Column | Source | Meaning |
| --- | --- | --- |
| Goal | `GoalCommandAgentMixin` in `HARNESS_AGENTS` | a flow may send `/goal <objective>`: the CLI's own goal feature ([Goals](#goals)) |
| Loop | `LoopCommandAgentMixin` | a flow may send `/loop <interval> <task>`: the CLI's own recurring task ([Loops](#loops)) |
| Steer | `SteeringAgentMixin` | a flow may put words into a running turn |
| Permission | `PermissionRequestHookAgentMixin` | a flow may answer the CLI's permission requests |
| Subagent | `SubagentStartHookAgentMixin`, `SubagentStopHookAgentMixin` | a flow is told when the CLI starts and ends agents of its own |
| AskUser | `AskUserHookAgentMixin` | the CLI's questions to its user reach the flow |
| Schema held | `SessionBase.shapes` | the CLI validates the answer against the schema; elsewhere it is asked for in the prompt and validated after |
| Fork | `Profile.forks`; `+cwd` is `SessionBase.forks_elsewhere` | the CLI can branch a conversation; `+cwd` into another directory |
| Web off | `Profile.searches` | `web_search=False` can be said |
| Rungs | `AgentBase.rungs` | which [rungs](#what-an-agent-may-do) the backend takes |
| Fast tier | `AgentBase.service_tiers` | `service_tier="fast"` is served |
| Tools | `SessionBase.takes_tools` | Python callbacks can be offered as tools |
| Trace | `_READERS` in `hmz.runtime.tracing.collector` | `Hmz().epics.trace()` reads its logs |

The flow mixins are what a role typed as that harness may declare; the driver columns are what
`hmz.coganchor.agents` does. One moment is reachable from Python and from no flow mixin: `grok`
runs `PERMISSION_REQUEST`. `HumanAgent` runs no moment at all.

## Agent specs (`-a`) {#agent-specs}

An agent is written `[ROLE=]CLI[@ACCOUNT]/MODEL[:EFFORT]` wherever one is named: `-a`, a settings
file, `Runs`, the TUI. `backends.read` parses one item; `-a` splits a value on `,` followed by
`KEY=`.

| Part | Rule |
| --- | --- |
| `ROLE` | Required for `-a`. A Python identifier: a field of the flow's agent collection. |
| `CLI` | Any alias in [Backends](#backends), or an added ACP CLI's name. Never contains `@`. |
| `ACCOUNT` | After `@`: a [provider](/reference/providers) name. Omitted: the CLI as already signed in. `@` with nothing after it is refused. |
| `MODEL` | Everything after the first `/`, less a trailing `:EFFORT`. May contain `/` (`kimi-code/k3`, `opencode/big-pickle`) and `:` (`custom_provider:gateway/m`). Must be non-empty. |
| `EFFORT` | After the last `:`, where what follows it is spelled as an effort: words of letters joined by `-`, `_` or a space (`high`, `extra-high`, `as configured`), or nothing. Otherwise -- `custom_provider:gateway/m`, `qwen3:8b` -- the `:` is the model's, and so is everything after it. Left off, or `auto`, or empty: no rung, stored as `""`. A model whose own name ends in `:<word>` is written with its effort after it: `qwen3:latest:auto`. Checked against the backend's ladder when the agent is built. |

| Input | `AgentSpecError` (exit 2 from `hmz exec`) |
| --- | --- |
| no `ROLE=` | `-a 'claude/m:high': expected <role>=<harness>[@<provider>]/<model>[:<effort>]` |
| a role that is not an identifier | `` -a '9x=claude/m:high': '9x' is not a place a flow could declare: what is written before `=` is a field of the tuple of agents the flow declares, so it is a Python identifier `` |
| unknown CLI, no `/`, empty model | `-a 'agent=claude': expected [NAME=]CLI[@PROVIDER]/MODEL[:EFFORT]` |
| `@` with no account | `-a 'agent=claude@/m:high': expected an account after @, as in claude@deepseek/MODEL:EFFORT` |
| a role given twice | `-a: the role 'agent' is given twice` |
| an empty item | `-a '<value>': an item is empty` |

An effort off the ladder, an account that does not exist, or a setting the backend cannot carry
is refused when the run builds the role's driver, as `HarnessUnrecoverable: <spec>: <reason>`,
the reason being the [`AgentConfig` refusal](#agentconfig).

<small>Defined in [`src/hmz/coganchor/backends.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/backends.py) (`read`, `named`), [`src/hmz/runtime/flowing/specs.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/specs.py) (`parse_agents`), [`src/hmz/runtime/flowing/harnesses.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/harnesses.py) (`open_agent`).</small>

## `AgentConfig` {#agentconfig}

`hmz.coganchor.agents.AgentConfig` is a frozen, keyword-only dataclass. Every backend config
subclasses it; [Backend notes](#backend-notes) lists each subclass's own fields.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `model` | `str` | required | The model, in the backend's spelling ([Models](#models)). |
| `effort` | `str` | required | A rung of the backend's [ladder](#efforts); `""` or `"auto"` for none. |
| `service_tier` | `str` | `"default"` | `"default"` or `"fast"` ([Service tier](#the-service-tier)). |
| `machine` | `MachineConfig \| None` | `None` | Where turns land ([Machines](/reference/machines)). |
| `permission` | `str` | `""` | A [rung](#what-an-agent-may-do), or `""` for none said. |
| `provider` | `str` | `""` | The [account](/reference/providers); `""` for the CLI as signed in. |
| `goals` | `bool` | `True` | Whether [goals](#goals) and work-past-the-turn tools are available. |
| `web_search` | `bool \| None` | `None` | [Web search](#whether-an-agent-may-search-the-web): on, off, or unsaid. |
| `fence` | `Fence \| None` | `None` | What the agent's processes may reach ([The fence](#the-fence)). |
| `budget` | `Budget \| None` | `None` | What each turn may spend ([Budgets](#cutting-a-turn-off-and-what-one-turn-may-spend)). |

The config is checked twice: by `__post_init__` when it is built (`ValueError`), and by the
agent when it is made, reconfigured, or has its effort moved (`Unserved`, a `ValueError`;
`Unfenced`, a kind of `Unserved`).

| Refused | Error and message |
| --- | --- |
| a tier other than `default`/`fast` | `ValueError: service_tier must be one of default, fast, not 'slow'` |
| a rung that is not one of the four | `ValueError: permission must be one of read-only, workspace-write, auto, bypass, not 'all'` |
| an effort off the ladder | `Unserved: claude cannot be asked to think at 'warp'; expected one of ultracode, max, xhigh, high, medium, low` |
| a tier the backend does not serve | `Unserved: PiAgent does not support service tier 'fast'; expected default` |
| a rung the backend does not take | `Unserved: DshAgent cannot be held to 'read-only'; expected bypass, or left unsaid for the agent as whoever installed the CLI configured it` |
| `web_search=False` on a backend that cannot be told | `Unserved: PiAgent has no way of being told not to search the web; web_search must be on for it` |
| a fence that cannot be held | `Unfenced: …` ([conditions](#when-a-fence-is-refused)) |
| backend-specific combinations | listed under each backend in [Backend notes](#backend-notes) |

`Budget` refuses `when` other than `next-response`/`immediately`
(`when must be one of next-response, immediately, not 'later'`), `then` other than `end`/`fail`,
and a negative cap (`a budget cannot be less than nothing`).

<small>Defined in [`src/hmz/coganchor/agents/config.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/config.py), [`src/hmz/coganchor/agents/base.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/base.py).</small>

## Models {#models}

`model` is passed in the CLI's own spelling.

| Backend | A model is | Example |
| --- | --- | --- |
| `agy`, `claude`, `codex`, `dsh`, `grok`, `qwen` | the id the CLI or its endpoint serves | `claude-opus-5`, `gpt-5.6-sol`, `deepseek-v4-flash` |
| `kimi` | Kimi Code's `provider/id` | `kimi-code/k3` |
| `pi`, `opencode`, `mimo` | `provider/id` | `openai-codex/gpt-5.5`, `opencode/big-pickle` |
| `cursor-agent` | an id from the account's list, the rung and tier written into it | `composer-2.5-high-fast` |
| `mcode` | `minimax/<id>`, or `custom_provider:<name>/<id>` for an added provider; `""` for its configured default | `minimax/MiniMax-M3` |
| an ACP CLI | `as configured` | |

`pi`'s `--provider` defaults to `google`; a bare id is looked up among Gemini models.

### Catalogues

`hmz.coganchor.models` keeps what each account runs in `models.json`
([Providers › `models.json`](/reference/providers#models-json)). It is asked when an account is
made, when refreshed from the TUI's models sheet, and by the TUI at start-up, in the background,
for each installed backend whose machine's-own catalogue is missing or older than 7 days. It
is asked as a turn of that account is taken: under its paths, with its variables and without
hushed ones.

| Backend | Asked with | Efforts per model |
| --- | --- | --- |
| `claude` | `claude -p --input-format stream-json --output-format stream-json --verbose`, sent a `control_request` `list_models` | the model's `supportedEffortLevels` |
| `codex` | `codex debug models` (models marked for listing) | per model |
| `kimi` | `kimi provider list --json` | per model; swarm |
| `agy` | `agy models` | the ladder |
| `grok` | `grok models` | the ladder |
| `cursor-agent` | `cursor-agent --list-models` | the rungs its listed variants carry (`gpt-5.2` at those `gpt-5.2-low` … are listed for); none for a model with no variants |
| `pi` | `pi --list-models` | the ladder |
| `opencode`, `mimo` | `<cli> models` (lines with a `/`) | the ladder |
| `mcode` | `mcode provider list --json`, then MiniMax's own four (`minimax/MiniMax-M3`, `minimax/MiniMax-M3.1-Flash-Preview`, `minimax/MiniMax-M2.7`, `minimax/MiniMax-M2.7-highspeed`) | only `MiniMax-M3.1-Flash-Preview` takes rungs |
| `dsh` | nothing: `deepseek-v4-flash`, `deepseek-v4-pro` | the ladder |
| `qwen` | nothing: `qwen3-coder-plus`, `qwen3-coder-flash` | the ladder |
| an ACP CLI | nothing: one row, `as configured` | `as configured` |

Where the account sets the backend's endpoint variable, the endpoint is asked first:

| Backend | Endpoint variable |
| --- | --- |
| `agy` | `GOOGLE_GEMINI_BASE_URL` |
| `claude` | `ANTHROPIC_BASE_URL` |
| `codex` | `CODEX_PROVIDER_URL` |
| `dsh` | `DEEPSEEK_BASE_URL` |
| `grok` | `GROK_XAI_API_BASE_URL` |
| `kimi` | `KIMI_MODEL_BASE_URL` |
| `qwen` | `OPENAI_BASE_URL` |

The request is `GET {base}/v1/models` (`{base}/models` when the base ends in a version);
every listed id is offered at the backend's whole ladder. See
[Providers › Gateways](/reference/providers#gateways).

A Claude Code session whose `system/init` names a model other than the one asked for (not
the model, the model dated, an alias `opus`, `sonnet`, `haiku`, `default`, `best`, `opusplan`
with or without `[1m]`, nor a catalogue name) emits one `notice` per session:
`Claude Code does not know the model '<asked>' and is running <actual>, its own default, in
its place`. The turn continues.

<small>Defined in [`src/hmz/coganchor/models.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/models.py).</small>

## Efforts {#efforts}

The effort is checked against `Profile.efforts` (plus `Profile.beyond`) where the agent is made
and wherever it is moved. `auto` is no rung: every backend takes it, and nothing is said to the
CLI. An ACP CLI's ladder is the single word `as configured` and any effort is accepted.

| Backend | Ladder, hardest first | How it is sent |
| --- | --- | --- |
| `agy` | `high`, `medium`, `low` | `--effort`, only where the model name carries no rung (`gemini-3.7-flash-high` runs at its own rung) |
| `claude` | `ultracode`, `max`, `xhigh`, `high`, `medium`, `low` | `--effort`. `ultracode` (in `beyond`: taken, never listed) is `xhigh` with the turn opted into orchestrating a fleet. |
| `codex` | `ultra`, `max`, `xhigh`, `high`, `medium`, `low` | per turn on the app server; `ultra`/`max` only on models that list them |
| `cursor-agent` | `max`, `xhigh`, `extra-high`, `high`, `medium`, `low`, `minimal`, `none` | written into the model id: `<model>-<rung>`, where the account lists that id |
| `dsh` | `max`, `high`, `low`, `off` | written onto the SDK composition |
| `grok` | `xhigh`, `high`, `medium`, `low` | `--effort` |
| `kimi` | `max`, `high`, `medium`, `low`, each also `swarm`-prefixed | per turn on the daemon; `swarmmax` is `max` run as a fleet of subagents (`agents.SWARM == "swarm"`) |
| `mcode` | `max`, `xhigh`, `high`, `medium`, `low` | `--effort`, only where there is a rung; a rung the account's catalogue does not list for the model is `Unserved` |
| `mimo`, `opencode` | `xhigh`, `high`, `medium`, `low`, `minimal` | `--variant` |
| `pi` | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` | `--thinking`; pi clamps a rung the model lacks to the nearest it has |
| `qwen` | `max`, `xhigh`, `high`, `medium`, `low`, `none` | a settings file named by `QWEN_CODE_SYSTEM_SETTINGS_PATH`, one per effort |

### Moving the effort while it runs {#moving-the-effort-while-it-runs}

`agent.effort = "low"` moves every session of the agent; `session.effort = "max"` moves one;
`session.effort = ""` returns it to the agent's. `agent.config.effort` stays as configured. The
change takes hold on the next turn; the running turn keeps its effort. The new effort is
checked as a configured one is.

| Backend | How a moved effort takes hold |
| --- | --- |
| `codex`, `kimi`, `opencode`, `mimo`, `cursor-agent`, `mcode` | sent with the next turn |
| `claude`, `dsh`, `agy`, `grok`, `qwen` | the process or runtime is restarted and resumes the same conversation |
| `pi` | a command to the held process, between turns |

<small>Defined in [`src/hmz/coganchor/backends.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/backends.py) (`Profile.efforts`, `Profile.beyond`, `Profile.takes`, `AUTO`, `SWARM`).</small>

## Service tier {#the-service-tier}

| Backend | `service_tier="fast"` |
| --- | --- |
| `claude` | `fastMode: true` in the `--settings` literal; at `default` nothing is sent |
| `codex` | the `priority` service tier |
| `cursor-agent` | the `-fast` id the account lists for the model (`composer-2.5-fast`); `Unserved` where none is listed |
| every other backend | `Unserved` |

The field records the tier asked for; the provider decides the tier served.

## Permission rungs {#what-an-agent-may-do}

`AgentConfig.permission` is one of four rungs, loosest last, or `""`:

| Rung | Meaning |
| --- | --- |
| `read-only` | may read anything and change nothing |
| `workspace-write` | may change the workspace it was given |
| `auto` | may reach for anything; what it asks for is granted |
| `bypass` | nothing is asked and nothing is checked |
| `""` | nothing is said to the CLI: no mode, sandbox or approval flag |

What each rung becomes, in the CLI's own terms (`—`: the same as the rung to its left;
refused: `Unserved`):

| Backend | `read-only` | `workspace-write` | `auto` | `bypass` |
| --- | --- | --- | --- | --- |
| `agy` | plan mode, four read tools | accept-edits mode | skip permissions | — |
| `claude` | `plan` | `acceptEdits` | `auto` | `bypassPermissions`; `acceptEdits` where the account or root forbids it; `manual` with `asks` |
| `codex` | sandbox `read-only` | sandbox `workspace-write` | sandbox `workspace-write`, approval `on-request` | sandbox `danger-full-access` |
| `cursor-agent` | `plan` | sandbox on | auto-review | sandbox off |
| `dsh` | refused | refused | refused | nothing sent |
| `grok` | three read tools | web search off | every tool | — |
| `kimi` | `manual` and plan mode | `auto` | `yolo` | `auto` |
| `mcode` | refused | `full` | `smart` | `full` |
| `mimo`, `opencode` | `edit`, `bash` denied | web tools denied | nothing denied | — |
| `pi` | four tools withheld | nothing withheld | — | — |
| `qwen` | five tools withheld | `web_fetch` withheld | nothing withheld | — |
| an ACP CLI | refused | refused | refused | every request granted |

How it is sent:

| Backend | Flags or protocol |
| --- | --- |
| `agy` | `--mode plan --agent hmz-read-only`; `--mode accept-edits`; `--dangerously-skip-permissions` |
| `claude` | `--permission-mode <mode>`; at `bypass` also `--permission-prompt-tool stdio`, each request answered `allow` unless a `PERMISSION_REQUEST` hook refuses |
| `codex` | `sandbox` and `approvalPolicy` on `thread/start`, `thread/resume` and `turn/start`; approval `never` at every rung but `auto` |
| `cursor-agent` | `--mode plan`; `--force --sandbox enabled`; `--auto-review`; `--force --sandbox disabled` |
| `grok` | `--always-approve`, plus `--tools read_file,grep,list_dir` at `read-only` and `--disable-web-search` at `workspace-write` |
| `kimi` | the session's permission mode on the daemon, and plan mode at `read-only` |
| `mcode` | `--permission full`, `--permission smart` |
| `mimo`, `opencode` | the `MIMOCODE_PERMISSION` / `OPENCODE_PERMISSION` table, plus `--dangerously-skip-permissions` / `--auto` |
| `pi` | `--exclude-tools bash,edit,write,powershell` at `read-only` |
| `qwen` | `--approval-mode yolo`, plus `--exclude-tools edit,monitor,notebook_edit,run_shell_command,write_file` at `read-only` or `--exclude-tools web_fetch` at `workspace-write` |

Per-backend rules:

- **agy**: `--mode plan` alone does not stop writes (agy 1.2 writes in it), so `read-only`
  also starts the turn as `--agent hmz-read-only`, an agent file humanize writes under
  `~/.gemini/antigravity-cli/agents/` whose only tools are `view_file`, `grep_search`,
  `find_by_name` and `list_dir`. That file exists only on this machine, so `read-only` or
  `web_search=False` on another machine is `Unserved: agy cannot run at read-only or off the
  web on another machine: what holds it there is an agent of humanize's that is a file on this
  one`. At `workspace-write` edits pass and commands are soft-denied (named in
  `denied_actions`).
- **claude**: `bypass` is `bypassPermissions`. An account whose managed settings carry
  `"disableBypassPermissionsMode": "disable"` starts that turn at `default` and says so in
  its `system/init`; the driver then moves the process to `acceptEdits` with a
  `set_permission_mode` control request, starts every later process of the agent on that
  account at `acceptEdits`, and says once: `claude: this account will not run an agent at
  bypass, so it runs at acceptEdits, where what it asks for is granted`. The same holds where
  Claude runs as root without `IS_SANDBOX=1`: it exits before the turn with
  `--dangerously-skip-permissions cannot be used with root/sudo privileges for security
  reasons`, and the turn is taken again at `acceptEdits`. With `ClaudeCodeAgentConfig.asks`,
  `bypass` runs at `manual` instead, so that every tool that would change something reaches a
  `PERMISSION_REQUEST` hook. Whatever is asked at `bypass` is
  answered `allow` unless such a hook refuses. The CLI still enforces an organisation's `deny`
  list.
- **codex**: the approval policy is `never` at every rung but `auto`. On a machine whose
  requirements forbid `danger-full-access`, `bypass` runs at `auto` and says once:
  `codex: this machine will not run an agent at bypass, so it runs at auto, where what it asks
  for is granted`. `CodexAgentConfig.approvals` replaces the rung's approval policy.
- **kimi**: Kimi's modes are, loosest last, `manual`, `yolo`, `auto`. At `read-only` plan mode
  vetoes `Write`, `Edit`, `TaskStop` and the cron tools, and `manual` turns everything else,
  `Bash` included, into an approval the driver answers no; `ExitPlanMode` is an approval too.
  Kimi `auto` denies `AskUserQuestion`, so at `workspace-write` and `bypass` no question and
  no `NOTIFICATION` occur.
- **mcode**: has no rung that changes nothing and no sandbox. `smart` is its own reviewer,
  which fails the turn where it would have asked. `read-only` is refused; a flow holds it
  read-only with a fence that writes nothing.
- **mimo**, **opencode**: the rung goes in a permission table (`OPENCODE_PERMISSION` /
  `MIMOCODE_PERMISSION`); any rung also adds `--auto` (opencode) or
  `--dangerously-skip-permissions` (mimo), unless `unattended` says otherwise.
- **pi**: no permission gate and no sandbox; `workspace-write`, `auto` and `bypass` are one
  agent.
- **qwen**: always `--approval-mode yolo`; its asking modes would leave a held-open session
  waiting on an approval nothing can answer. Nothing confines an edit to the workspace.
- **dsh**, **ACP**: the SDK exposes no per-session sandbox or approval control; an ACP CLI's
  only permission word is a per-call question, which is granted.

### Flow permission to rung {#the-flow-api-s-permission-on-each-cli}

Under a flow the rung is derived from the role's `Permission` by
`hmz.runtime.flowing.harnessing.rung()`, and nothing is put to anybody for approval:

1. `local` of `READ` or `NONE` gives `read-only`; `local` of `ALL` gives `bypass`.
2. If that is not `read-only` and the harness is in `ASKS` and a hook in its `ASKS` set is
   hung, it becomes `auto`. `ASKS` is `{kimi: {PERMISSION_REQUEST, ASK_USER}}`.
3. A rung the backend does not take becomes `bypass` (`dsh`, `mcode`, ACP CLIs).

| `local` | every harness but `dsh`, `mcode`, ACP | `dsh`, `mcode`, ACP |
| --- | --- | --- |
| `NONE`, `READ` | `read-only` | `bypass` |
| `ALL` | `bypass` (`auto` for `kimi` with a `PermissionRequest` or `AskUser` hook hung) | `bypass` |

- `user`, `system` and `online` are held by the [fence](#the-fence), not the rung; so is `local`
  on `dsh`, `mcode` and ACP CLIs.
- **Claude Code** with a `PermissionRequest` hook hung is given `asks=True`
  (`harnessing.prompting`), so `bypass` runs at `manual` and every tool that would change
  something reaches the hook. It takes hold from the session's next turn (the process is
  restarted).
- **Codex** with a `PermissionRequest` hook hung runs approval policy `untrusted` over its
  rung's sandbox (`harnessing.approvals`). With an `AskUser` hook hung it is started with the
  feature `default_mode_request_user_input` (`harnessing.ASKING_FEATURE`). Both take hold from
  the session's next turn (the app server is restarted).
- **Codex `read-only`** under a fence, or where bubblewrap cannot get a user namespace, starts
  the app server with `--enable use_legacy_landlock` (asked once per process by running
  `codex sandbox … -- true`). Where the fence leaves the network on, each `read-only` turn is
  sent `sandboxPolicy: {"type": "readOnly", "networkAccess": true}`. On macOS, where Codex's
  own Seatbelt sandbox cannot start inside the fence's, each `read-only` or `workspace-write`
  turn under a fence is sent `sandboxPolicy: {"type": "externalSandbox", "networkAccess":
  "enabled"|"restricted"}` instead, the fence holding the rung.
- `online` also decides the CLI's own web tools ([Web search](#whether-an-agent-may-search-the-web)).

<small>Defined in [`src/hmz/runtime/flowing/harnessing.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/harnessing.py) (`rung`, `ASKS`, `approvals`, `prompting`, `searching`, `fenced`), and each driver's `_PERMITTED` table.</small>

## Web search {#whether-an-agent-may-search-the-web}

| `web_search` | Meaning |
| --- | --- |
| `None` (default) | nothing said; the CLI searches as it would when run by hand |
| `True` | on, said even to a CLI that ships with search off |
| `False` | off; `Unserved` on a backend with `Profile.searches == False` |

| Backend | How it is said |
| --- | --- |
| `claude` | `--disallowedTools WebSearch,WebFetch` when off, or when the fence cuts the network |
| `codex` | `-c web_search="live"` or `"disabled"`; `disabled` whenever the fence cuts the network |
| `dsh` | the `dsh-web` plugin, its providers and `dsh-tool-web` mounted when on |
| `grok` | `--disable-web-search` when off, or when the fence cuts the network |
| `kimi` | `disabled_tools` on each prompt: `WebSearch`, `FetchURL` when off, or when the fence cuts the network |
| `qwen` | `--exclude-tools web_search,web_fetch` when off, or when the fence cuts the network |
| `opencode` | `webfetch: deny`, `websearch: deny` in the permission table |
| `mimo` | the same, and `codesearch: deny` |
| `agy` | `--agent hmz-offline` (default tools less `read_url_content`, `search_web` and the subagent tools) when off or when the fence cuts the network; at `read-only`, `hmz-read-only-web` when on |
| `cursor-agent`, `mcode`, `pi`, an ACP CLI | cannot be told: `False` is refused |

Under a flow, `online` of `ALL` (the default) is `True` and `NONE` is `False`, on a backend that
can be told; elsewhere `None`. A command the agent runs reaches the network regardless of this
setting; only the [fence](#the-fence) stops that.

## The fence {#the-fence}

`AgentConfig.fence` is what the agent's processes may reach: the CLI's own process and every
command it runs. A flow sets one on every session from the role's `Permission`
(`harnessing.fenced`).

`hmz.coganchor.fence.Fence` (frozen):

| Field | Type | Meaning |
| --- | --- | --- |
| `read` | `tuple[str, ...]` | absolute paths that may be read, listed and executed |
| `write` | `tuple[str, ...]` | absolute paths that may be read and changed; a path in both is written |
| `online` | `bool` | `True`: the network is unrestricted. `False`: cut, except through a proxy to `hosts` |
| `hosts` | `tuple[str, ...]` | what the proxy passes while `online` is False: `host`, `*.suffix`, or `host:port` |
| `tmp` | `str` | the scratch directory, exported as `TMPDIR`, `TMP`, `TEMP`; `""` for one made per run |
| `scopes` | `tuple[str, ...]` | `(local, user, system)` levels it was drawn from, or `()` for one drawn path by path |
| `listen` | `tuple[int, ...]` | TCP ports that may be bound while `online` is False, on loopback |

`Fence.open` is true when `/` is in `write` and `online` is true: nothing is put around the CLI.

`Fence.of(*, local, user, system, online, workdir, home, cwd="", hosts=(), read=(), write=())`:

- Each scope is a root (`system` is `/`, `user` is `home`, `local` is `workdir` and `cwd`) and
  a level: `read` puts the root in `read`, `all` in `write`, `none` leaves it out.
- The levels must nest, `local >= user >= system`: `ValueError: scopes must nest, local >= user
  >= system; got local=read, user=all, system=none`. A level outside `none`/`read`/`all`:
  `ValueError: a scope is one of none, read, all, not 'x'`.
- Always added to `read`: `/usr`, `/bin`, `/sbin`, `/lib`, `/lib32`, `/lib64`, `/libx32`,
  `/etc/ssl`, `/etc/ca-certificates`, `/etc/pki`, `/etc/resolv.conf`, `/etc/hosts`,
  `/etc/host.conf`, `/etc/gai.conf`, `/etc/nsswitch.conf`, `/etc/passwd`, `/etc/group`,
  `/etc/localtime`, `/etc/timezone`, `/etc/os-release`, `/etc/ld.so.cache`, `/etc/ld.so.conf`,
  `/etc/ld.so.conf.d`, `/etc/alternatives`, `/proc`, `/sys`, and the Python running humanize.
- Always added to `write`: `/dev/null`, `/dev/zero`, `/dev/full`, `/dev/random`,
  `/dev/urandom`, `/dev/tty`, `/dev/pts`, `/dev/ptmx`, `/dev/shm`, every `/dev/nvidia*`,
  `/dev/dri`, `/dev/kfd`.

The agent widens the fence where it spawns a turn (`agent.fenced()`): its CLI's state and
sign-in directories and its session directory to write, and on macOS `~/Library/Keychains`,
where Claude Code keeps its sign-in and rewrites it as it refreshes; the account's directory;
the hosts its model and sign-in are at under the account ([Network hosts](#network-hosts)); the
skills it carries; its programs and their install trees to read.

Both a flow's fence and the agent's widening read the hosts from the same environment,
`providers.composed(provider, profile)`: this process's own, less the variables the account
hushes, plus the ones it sets. A variable the turn runs without, such as an
`ANTHROPIC_BASE_URL` left in the shell under an account that does not set one, opens no
host.

### Enforcement

`agent.natively(fence)` returns what the CLI does not enforce itself. That remainder is held
from outside by putting `python -Pm hmz internal fence --policy=<Fence JSON> --` outermost around
the turn:

| Mechanism | Holds |
| --- | --- |
| Landlock (Linux) | paths, and TCP `connect`/`bind` by port (ABI >= 4 where the network is cut) |
| seccomp filter (Linux) | every non-TCP socket family refused |
| seccomp user notification + `pidfd_getfd` (Linux) | with `online=False`, every `bind` and `listen` stops for the wrapper, which allows loopback only (`EACCES` otherwise) |
| Seatbelt (macOS) | paths (as given and as resolved, `/tmp` being `/private/tmp`); with `online=False`, outgoing TCP to the proxy's port on `localhost` only, every other outgoing connection and the system resolver's socket refused, and listening allowed on `localhost`, which Seatbelt also matches for every address and every port |
| proxy on loopback | with `online=False`, the only way out: handed to the CLI as `HTTPS_PROXY` and related variables, passing only `hosts` (ports 443 and 80 for a host without a port) |

The minimum granted whatever the scopes is `LINUX_SYSTEM` and `LINUX_DEVICES` on Linux, and
`DARWIN_SYSTEM` (`/usr`, `/bin`, `/sbin`, `/System`, `/private/var/select`,
`/private/var/db/timezone` and the handful of files under `/etc` a program reads to start) and
`DARWIN_DEVICES` on macOS, where the root directory itself is also readable and the
pseudo-terminals `/dev/ttys*` writable.

No built-in backend enforces any part natively: every driver's `natively` returns the whole
fence, for these reasons:

| Backend | Why its own confinement is not used |
| --- | --- |
| `agy` | `--sandbox` confines commands only (its file tools run outside it), cannot start without unprivileged user namespaces, and its network lists are desktop-app settings |
| `codex` | its sandbox holds the commands its agent runs, not Codex's own process, MCP servers or hooks; `online=False` also sends `-c web_search="disabled"`, `--disable apps`, and `--disable respect_system_proxy` where `codex features list` names it |
| `cursor-agent` | `cursorsandbox` wraps shell commands only and needs a user namespace; `$XDG_CONFIG_HOME/cursor` (else `~/.config/cursor`) is granted to write |
| `dsh` | the bundle has no confining shell executor; the runtime the SDK launches is wrapped, its composition file and native module cache (`PKG_NATIVE_CACHE_PATH`) put in the fence's `tmp` |
| `grok` | its sandbox profiles write `/tmp` and `/var/tmp`, block only commands' network, and fail without user namespaces on 1.0.24 |
| `kimi` | 0.42 has no sandbox; the daemon is fenced once, when it starts |
| `mimo`, `opencode` | neither confines its shell; the permission table additionally denies `edit` outside writable paths, `read`/`external_directory` outside readable ones (only where `system` is `NONE`), and web tools where `online` is `NONE` |
| `pi` | no gate and no sandbox; `--offline` under `online` `NONE` |
| `qwen` | `--sandbox` is a container or Seatbelt; its rules hold its own tools only; generated settings live under one `hmz-qwen-*` temporary directory granted read-only |
| an ACP CLI | nothing is known of it; declared `hosts` and `state` under `clis` in `settings.yaml` are granted |

### When a fence is refused {#when-a-fence-is-refused}

`Unfenced` is raised where the config arrives (construction, reconfiguration) when:

| Condition | Message |
| --- | --- |
| this machine has no Landlock (Linux < 5.13, or not in the `lsm=` list) | `<Agent> cannot be held to its permission on this machine: it does not enforce it natively, and fencing it from outside needs Landlock (Linux 5.13 or later, with landlock in its lsm= list)` |
| macOS, where `sandbox-exec` cannot apply a profile (humanize itself already runs inside a sandbox) | `… needs Seatbelt, which a process already inside a sandbox cannot apply` |
| `online=False` and no Landlock ABI 4, no seccomp notification, or `pidfd_getfd` refused (a container's default seccomp profile, Yama `ptrace_scope` >= 2) | `… needs Landlock ABI 4 (Linux 6.7 or later) and seccomp to cut the network` |
| a fence drawn path by path on an agent whose `machine` is set | `<Agent>: a fence drawn path by path cannot be held on another machine` |
| a harness on another machine | `<Agent>: a fence cannot hold a harness that runs on another machine` |
| `online=False` with the anchor's `net="remote"` | `<Agent>: an agent whose own connections are sent to the target cannot have its network cut here` |
| `cursor-agent` with `online=False` | `cursor-agent: this permission cuts the network, and cursor-agent's web search and web fetch run on Cursor's own servers, through the same hosts as its model, where nothing here can tell them apart or switch them off; grant it online ALL to use cursor-agent` |
| `mcode` with `online=False` | `mcode: this permission cuts the network, and mcode's web search runs on MiniMax's own service, through the same hosts as its model, where nothing here can take it away; grant it online ALL to use mcode` |
| `grok` with `leader=True` and a non-open fence | `GrokBuildAgent: a fenced conversation cannot join the leader, which runs its tools outside the fence; set leader to False or None` |

Under a flow, `Unfenced` becomes `HarnessSandboxed`. An ACP CLI with `online` `NONE` and no
declared hosts is refused `HarnessSandboxed`, naming what to declare. For anchored agents, what
each machine holds is in [Remote execution › A fence on both machines](/reference/remote-execution#a-fence-on-both-machines).

Gaps are the kernel's: neither Landlock nor Seatbelt governs connecting to a Unix socket (on
macOS, nor asking a system service over Mach); on Linux with the network cut the proxy's port
is reachable on any address, by number; and on macOS with the network cut a program may listen
on any address and port, Seatbelt telling neither apart.

### Network hosts {#network-hosts}

`Profile.hosts`: what a fenced turn with `online=False` still reaches. The account adds its
endpoint's host and cloud hosts ([Providers › Hosts reachable under a cut
network](/reference/providers#hosts-reachable-under-a-cut-network)).

| Backend | Hosts |
| --- | --- |
| `agy` | `cloudcode-pa.googleapis.com`, `daily-cloudcode-pa.googleapis.com`, `oauth2.googleapis.com`, `www.googleapis.com`, `generativelanguage.googleapis.com`, `lh3.googleusercontent.com` |
| `claude` | `api.anthropic.com`, `platform.claude.com`, `claude.ai` |
| `codex` | `chatgpt.com`, `auth.openai.com`, `api.openai.com` |
| `cursor-agent` | `*.cursor.sh` (a cut network is refused anyway) |
| `dsh` | `api.deepseek.com` |
| `grok` | `cli-chat-proxy.grok.com`, `auth.x.ai`, `api.x.ai` |
| `kimi` | `api.kimi.com`, `auth.kimi.com`, `api.kimi.ai`, `auth.kimi.ai`, `api.moonshot.ai`, `api.moonshot.cn` |
| `mcode` | `agent.minimax.io`, `agent.minimaxi.com`, `agent.minimax.cn`, `api.minimax.io`, `api.minimaxi.com`, `account.minimax.io`, `account.minimax.cn` (a cut network is refused anyway) |
| `mimo` | `api.xiaomimimo.com`, `token-plan-cn.xiaomimimo.com`, `token-plan-sgp.xiaomimimo.com`, `token-plan-ams.xiaomimimo.com`; plus the `options.baseURL` of the provider `mimocode/mimocode.json` (under `$XDG_CONFIG_HOME`) declares for the model |
| `opencode` | `opencode.ai`, `chatgpt.com`, `auth.openai.com`, `api.githubcopilot.com`; plus the `options.baseURL` of the provider `opencode/opencode.json` (under `$XDG_CONFIG_HOME`) declares for the model |
| `pi` | `api.anthropic.com`, `platform.claude.com`, `chatgpt.com`, `auth.openai.com`, `api.github.com`, `api.individual.githubcopilot.com`, `api.x.ai`, `auth.x.ai`, `api.kimi.com`, `auth.kimi.com`, `openrouter.ai`; plus the `baseUrl` of each provider pi's own `models.json` declares for the model |
| `qwen` | `chat.qwen.ai`, `portal.qwen.ai`, `dashscope.aliyuncs.com`, `dashscope-intl.aliyuncs.com` |
| an ACP CLI | its declared `hosts` |

<small>Defined in [`src/hmz/coganchor/fence/`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/fence) (`Fence`, `enforceable`, `wrapper`, `proxy`, `loopback`), [`src/hmz/coganchor/agents/base.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/base.py) (`fenced`, `natively`, `_abroad`), [`src/hmz/coganchor/backends.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/backends.py) (`Profile.hosts`, `reachable`).</small>

## Sessions and turns {#turns}

```python
agent(prompt)                       # a turn in a session nobody keeps
session = agent.new(cwd=None)       # nothing is opened with the backend yet
session(prompt)                     # opens the conversation, then resumes it
```

- Both calls return the answer, stripped (or the schema model, with `schema=`).
- `session.id` raises `RuntimeError: session has not run a turn yet` until a turn has landed;
  `session.named` is `None` instead. On `claude`, `codex`, `dsh`, `kimi` and `pi` it is set as
  soon as the backend names the session, during the first turn; elsewhere when that turn lands.
- A session runs one turn at a time; concurrent callers of one session are serialised.
- An agent holds its sessions weakly; dropping a session closes it.
- `session.close()` ends whatever holds the conversation open.

### Failures {#failures}

A failed turn raises `Failed` (a `subprocess.CalledProcessError`) and leaves the session
unopened, so the next call retries rather than resuming something that may not exist. The
message ends with what the CLI said and, where classified, `(<fault>: <fix>)`.

| Attribute | Meaning |
| --- | --- |
| `Failed.fault` | one of `backends.FAULTS`, or `""` |
| `Failed.fix` | what to do about it, or `""` |

| Fault | Meaning |
| --- | --- |
| `contended` | two turns at one local store (`database is locked`, `SQLITE_BUSY`), or at one [sign-in that refreshes itself](/reference/providers#a-sign-in-that-refreshes-itself) the other way round (`signs in with a token that refreshes itself`) |
| `spent` | a quota or balance used up, said in so many words (`quota`, `insufficient balance`, `credit balance is too low`, `billing`); read ahead of `throttled`, since it comes as the same `429` |
| `throttled` | too many requests (`429`, `529`, `rate limit`, `resource exhausted`, `overloaded`, `usage limit`, …) |
| `refused` | the credential (`401`, `403`, `unauthorized`, `invalid api key`, `not logged in`, `token expired`, `token was revoked`, `forbidden`, …) |
| `unlisted` | the model is not this account's (`not allowed to access model`, `can only access models`, `is not supported when using`, …) |
| `retired` | the model is gone (`404`, `model not found`, `unknown model`, …) |
| `missing` | nothing to run: exit 126 or 127 |
| `sandboxed` | the CLI could not start its own sandbox (`bwrap: `, `cannot create … namespace`, …) |
| `unmirrored` | the copy of another machine's work a harness here keeps could not be made at its path (`cannot keep the local copy of the work at`); read first of all, ahead of the `Permission denied` it usually carries |
| `fenced` | the run's network fence kept it off a host (`is not a host this run may reach`, the fence proxy's `403`); read ahead of the credentials |
| `killed` | a signal, or exit 129–192, or `out of memory`, `SIGKILL`, `segmentation fault`, … |
| `dropped` | the wire (`ECONNRESET`, `broken pipe`, `fetch failed`, `502`/`503`/`504`, `timed out`, …) |

Classification (`backends.trouble`) reads the last 4096 characters of each stream, the
backend's own `Profile.signs` first, then the shared `backends.SIGNS` in order; the first match
wins. Backend-specific signs: `dsh` `needs a DeepSeek API key` → `refused`; `grok`
`couldn't set model.*unknown model id` → `throttled`; `mcode` `sign in to minimax` and `oauth
bearer is not synced` → `refused`. For `agy`, whose streams say nothing useful, the newest of
`cli.log` / `log/cli-*.log` written within the turn's duration (at most 300 s, last 64 KiB) is
read last (`Profile.journal`).

| Also raised | When |
| --- | --- |
| `Unrecoverable` (a `Failed`) | no retry could change it: a context-window overflow, a session id the backend will not resume, a budget spent with `then="fail"`. Never retried, never carried to another account. |
| `Stopped` | the agent was [stopped](#stopping). Not a `CalledProcessError`. |
| `NotImplementedError` | the backend lacks the feature (`pursue` without goals, `interject` without steering, `fork` without forks, `offers` without tools) |

`suppress=True` returns `""` (or `None` with a schema) for a `Failed` or a schema mismatch, and
nothing else.

### Forks {#a-conversation-that-goes-two-ways}

`session.fork(*, into=None, cwd=None)` returns an unopened child that carries the session's
history; its first turn performs the fork.

| Backend | Fork mechanism | Into another `cwd` |
| --- | --- | --- |
| `claude` | `--resume <parent> --fork-session` | yes: the transcript is copied to where `--resume` looks |
| `codex` | `thread/fork` | yes |
| `kimi` | `kimi fork` | yes |
| `grok` | `grok -p --resume <parent> --fork-session` | no |
| `opencode`, `mimo` | `run --session <parent> --fork` | no |
| `pi` | `--fork <parent>` | no |
| `qwen` | `--resume <parent> --fork-session` | no |
| an ACP CLI | `session/fork`, where the agent serves it | no |
| `agy`, `cursor-agent`, `dsh`, `mcode` | none | — |

- Forking a session that has not landed a turn: `RuntimeError: session has not run a turn yet`.
- A backend with no fork: `NotImplementedError: <cli> has no way of carrying a conversation
  into a second one`. `cwd=` elsewhere where unsupported: `NotImplementedError`.
- `into=` another agent of the same backend, account and machine; anything else is `ValueError`.
- The child carries the session's effort, budget, skills and callbacks.
- A child driven after its parent has taken another turn raises `RuntimeError`.
- `session.forks` says whether this backend forks. Under a flow, `agent.fork(session, env=…)`;
  a fork onto another machine is `UnsupportedOperation: <cli> cannot fork a session onto
  another machine`.

### Working directory {#the-directory-a-session-works-in}

`agent.new(cwd)`, `agent(prompt, cwd=…)`, `agent.pursue(…, cwd=…)`, `agent.batch(…, cwd=…)` and
`agent.batch_new(n, cwd)` open sessions at a directory; `None` is the directory the process (or
flow) is in. `session.cwd` is the absolute path as the machine it lands on names it. For an
anchored agent it is that machine's path and must be inside the anchor's workspace. Before the
first turn:

```text
/srv/nowhere: no directory to open a session in
/tmp/elsewhere is not inside /srv/project, which is the workspace this agent's turns land in
```

### Async and batches {#awaiting-a-turn}

`aturn`, `apursue` and `abatch` are awaitable twins with the same arguments; each turn runs on
a thread of its own. Two awaited turns on one session run one after the other; on two sessions,
concurrently.

<a id="many-at-once"></a>

`agent.batch(prompts, *, suppress=False, schema=…, at_once=0, cwd=None)` runs one fresh session
per prompt, `at_once` at a time (`0`: all at once), answers in order. Without `suppress` it
raises the first failure after every turn has landed. `batch_new(count, cwd=None)` opens
sessions without running a turn.

### Schemas {#answering-in-a-shape}

`schema=Model` (a pydantic model) makes the turn answer with an instance.

| Backend | How the shape is held |
| --- | --- |
| `claude`, `agy`, `grok`, `qwen` | `--json-schema` (a separate print/command turn on `agy`, `grok`, `qwen`; a process restart on `claude`) |
| `mcode` | `--output-schema` |
| `codex` | `outputSchema` on the turn |
| every other | the schema is put in the prompt; the answer is validated after |

`grok` and `mcode` close every object (`additionalProperties: false`, every property required,
no defaults), as Codex requires. An answer that does not validate raises `ValueError`;
`suppress=True` returns `None`.

### Events {#watching-a-turn-as-it-happens}

`session.stream(prompt, *, schema=None)` yields `Event(kind, text, whose="", tokens={},
spent=Usage())`.

| `kind` | Meaning |
| --- | --- |
| `text` | the agent talking; one whole utterance |
| `reasoning` | the agent thinking aloud, where the backend reports it (opencode and mimo with `thinking=True`) |
| `tool` | a tool reached for; where arguments stream, sent at the first fragment naming the path or command |
| `subagent`, `subagent-ends` | bracket an agent this one started; `whose` pairs them |
| `took` | an interjected word is now in front of the model |
| `result` | the answer; exactly one closes each turn; carries `tokens` (per model) and `spent` |
| `failed` | the turn closed the other way |

`agent.watch(listener)` registers `listener(agent, session | None, event)` for every session,
which also sees `begins`, `ends` (bracketing a turn), `asks` (a [question](#questions)) and
`notice` (humanize itself: a rate limit waited out, an account moved, a turn cut off, a wedged
backend ended). With no watcher, a `notice` is written to stderr. A watcher that raises is
reported as a snag and does not fail the flow.

`claude` alone announces a tool while its arguments are still being written
(`session.narrates`, `--include-partial-messages`, `ClaudeCodeAgentConfig.partial_messages`).

<small>Defined in [`src/hmz/coganchor/agents/base.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/base.py), [`src/hmz/coganchor/agents/event.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/event.py), [`src/hmz/coganchor/backends.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/backends.py) (`FAULTS`, `SIGNS`, `trouble`, `journalled`).</small>

## Steering {#talking-to-a-turn-already-running}

`session.interject(text)` puts words into the running turn; a `took` event follows once they
are in front of the model. `session.steers` says whether the backend can.

| Backend | Mechanism | Between turns |
| --- | --- | --- |
| `claude` | a user message written on the held stream | accepted while the process is up; `RuntimeError: no turn is running to be talked to` before the first turn |
| `codex` | `turn/steer` | `RuntimeError` |
| `kimi` | queued on the daemon, then steered in | `RuntimeError` |
| `pi` | an RPC `steer` command | accepted while the process is up |
| every other | none: `NotImplementedError: <Session> cannot be talked to mid-turn` | |

An anchored session's process ends with each turn, so an anchored `claude` or `pi` hears words
only during a turn. Under a flow, `SteeringAgentMixin.steer(prompt, session=…, queued=True)`;
`queued=False` interrupts the turn and continues from the prompt.

## Goals {#goals}

`agent.pursue(objective, *, suppress=False, cwd=None)` runs the backend's own goal feature:
the agent decides when the objective is met; until then each turn that would end starts
another, and `pursue` answers with the last.

| Backend | Goal feature |
| --- | --- |
| `claude` | `/goal` |
| `codex` | `thread/goal/set` |
| `kimi` | the daemon's goal, set each time it is asked |
| `dsh` | the goal service, `create_goal` tool and round driver mounted into the composition |
| every other | `NotImplementedError: <Session> has no goal feature`, even under `suppress` |

- `type(agent).pursues` says whether the backend has one.
- `goals=False` makes `pursue` raise `RuntimeError` and removes work-past-the-turn tools:
  `codex` starts with `--disable goals`; `claude` gets `--disallowedTools Agent,ScheduleWakeup,
  CronCreate,CronDelete,CronList,Workflow`; `dsh` mounts no goal service.
- A budget and `interrupt` do not end a goal; `agent.stop()` does, and so does `cut` on a
  backend whose transport it puts down.
- A goal is watched as a turn is: what each of its turns says and reaches for reaches the
  agent's watchers as it happens (on `codex`, bracketed by one `begins` and one `ends` for the
  whole goal), and on stderr where nothing is watching.
- Under a flow, `/goal <objective>` as the prompt of a role typed with `GoalCommandAgentMixin`.

### Loops {#loops}

`LoopCommandAgentMixin` is served by `claude` only. A flow prompt `/loop <interval> <task>` is
passed to the CLI unchanged; no other prompt is interpreted, and no Python API corresponds.

## Hooks {#hooks}

A hook is a Python callable hung on a moment of a turn:

```python
hung = agent.hooks.on(Moment.PERMISSION_REQUEST, hook, tool="Bash")  # a context manager too
hung.off()                                                           # idempotent
```

`hook(occasion: Occasion) -> Verdict | None`. Hooks are on the agent and apply to every session;
they may be hung and taken down mid-run.

| `Moment` | When | What a refusing `Verdict` does |
| --- | --- | --- |
| `SESSION_START` | before a session's first turn | nothing |
| `USER_PROMPT_SUBMIT` | before each prompt is sent | skips the turn; `adds` is appended to the prompt |
| `PRE_TOOL_USE` | the agent reached for a tool | stops the tool on a backend with a hook seam ([below](#refusing-a-tool)); nothing elsewhere |
| `SUBAGENT_START`, `SUBAGENT_STOP` | an agent of its own started / came back | nothing |
| `PERMISSION_REQUEST` | the backend asks whether a tool may run | denies it, `because` as the reason |
| `NOTIFICATION` | the agent stopped to ask its user something | nothing |
| `STOP` | a turn ended | sends the agent on, `because` as the next prompt |
| `SESSION_END` | a session closed | nothing |

| `Occasion` field | Type | Meaning |
| --- | --- | --- |
| `moment` | `Moment` | |
| `agent` | `str` | the agent's id |
| `session` | `str` | the session id, or `""` |
| `prompt` | `str` | the prompt (`USER_PROMPT_SUBMIT`) |
| `tool` | `str` | the tool, or the subagent's name |
| `about` | `str` | the command or path, or the subagent's task |
| `under` | `str` | the backend's id for a subagent, pairing start and stop |
| `input` | `Mapping[str, Any]` | the tool's input where known |
| `said` | `str` | what was said (`NOTIFICATION`, `SUBAGENT_STOP`) |
| `again` | `int` | how many times this turn has been sent on by `STOP` |

`Verdict(refused=False, because="", adds="")`. Two hooks on one moment combine: refused if
either refused, every `adds` added. A hook that raises has said nothing, except `Stopped`, which
propagates.

### Moments per backend {#not-every-backend-runs-every-moment}

`agent.moments` is what the backend runs; `hooks.on` for any other raises
`Unhooked: <agent id> does not run <Moment>`.

| Backend | the six common moments | `PERMISSION_REQUEST` | `SUBAGENT_START`, `SUBAGENT_STOP` |
| --- | :-: | :-: | :-: |
| `claude`, `codex` | yes | yes | yes |
| `cursor-agent`, `mcode` | yes | — | yes |
| `grok`, `kimi` | yes | yes | — |
| `agy`, `dsh`, `mimo`, `opencode`, `pi`, `qwen`, an ACP CLI | yes | — | — |
| `HumanAgent` | — | — | — |

The six common moments are `SESSION_START`, `USER_PROMPT_SUBMIT`, `PRE_TOOL_USE`,
`NOTIFICATION`, `STOP`, `SESSION_END`.

### Permission requests {#when-a-permissionrequest-refusal-reaches-the-agent}

A refusal reaches the agent only on a backend that waits for the answer:

| Backend | When it asks | Default answer with no refusing hook |
| --- | --- | --- |
| `claude` | at `bypass`: `--permission-prompt-tool stdio` routes every request over the stream | yes; a request at `read-only` is answered no; with no rung nothing is routed |
| `codex` | through the app server, at `auto` (`on-request`) and at any rung given `approvals` | yes at every rung; no with no rung |
| `grok` | `session/request_permission`, on the held-open transport only | yes at every rung; no with no rung |
| `kimi` | each approval on the daemon's `/approvals`: at `auto`, and at `read-only` or no rung | yes at `auto`; no at `read-only` and with no rung |

A hook can turn a yes into a no, never a no into a yes. Under a flow, Codex's refusal carries
no reason, so the reason is steered into the turn instead.

### Refusing a tool {#refusing-a-tool}

`PRE_TOOL_USE` stops a tool only on a backend that takes a hook table for one run
(`Profile.hooks`):

| Backend | Seam |
| --- | --- |
| `claude` | `--settings`, the settings literal on the command line, carrying a `PreToolUse` hook |
| `qwen` | a settings file of humanize's named by `QWEN_CODE_SYSTEM_SETTINGS_PATH` |

- The table runs `hmz internal hook --at <socket>`, which relays the call to this process and
  the verdict back; a refusal means the tool does not run and `PERMISSION_REQUEST` is not asked.
- The table is present only while a `PRE_TOOL_USE` hook is hung. A hook hung or removed between
  turns takes effect next turn; one hung mid-turn is read off the stream for that turn.
- An anchored turn gets no table; there, and on every other backend, `PRE_TOOL_USE` is read off
  the stream after the tool was announced, and cannot stop it.
- Nothing of the user's configuration is read, written or replaced.

### Runtime reports {#what-the-runtime-says-the-turn-did}

On backends whose CLI is a Node program (`Profile.preloads == "NODE_OPTIONS"`: `kimi`, `pi`,
`qwen`, `mimo`), hanging a `PRE_TOOL_USE` hook also preloads a script via `NODE_OPTIONS` that
reports what the runtime did as additional `PRE_TOOL_USE` occasions:

| `occasion.tool` | `occasion.about` |
| --- | --- |
| `spawn` | the command line |
| `read`, `write` | the path |
| `connect` | `host:port` |
| `quiet` | the process stopped reporting (100,000 reports, or reports dropped) |

| | `kimi` | `qwen` | `pi` | `mimo` |
| --- | --- | --- | --- | --- |
| Watched | the daemon (every session of the agent) | the launcher and the bundle it re-execs | the held process | its launcher only |

- Reports arrive after the call, on the socket-reading thread; a verdict does nothing.
- Hang before the first turn: `qwen`, `pi`, `mimo` pick up later hooks on their next turn;
  `kimi`'s daemon, started once, never does.
- The CLI's reads of its own install and calls on descriptors are not reported; a Node program
  the agent runs reports nothing beyond its `spawn`. The preload fails open.
- Not installed for an anchored turn. The socket is named by `HMZ_PRELOAD_AT` and
  `HMZ_PRELOAD_IN`.

### Flow hooks {#flow-hooks}

Under a flow, hooks are async functions on the flow agent (`agent.on_stop(fn)`,
`agent.on_permission_request(fn)`, …). The harness driver fires `SESSION_START`,
`USER_PROMPT_SUBMIT`, `STOP` and `SESSION_END` itself around each turn, and carries
`PreToolUse`, `PermissionRequest`, `Notification`, `SubagentStart` and `SubagentStop` from the
CLI's threads. A moment waits at most `HOOK_TIMEOUT` (900 s) for the flow's hook before it is
answered as if nothing were hung; a question to the user waits indefinitely. A flow declaring a
hook mixin its harness does not serve is refused before its first turn.

<small>Defined in [`src/hmz/coganchor/agents/hooks.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/hooks.py), [`src/hmz/coganchor/agents/preload/`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/preload), [`src/hmz/runtime/flowing/harnesses.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/harnesses.py).</small>

## Questions {#questions}

An agent may stop mid-turn to ask its user; `Question(text, options=(), asker="")`.

| Callback | Called | Returns |
| --- | --- | --- |
| `agent.ask` | when the agent asks | the answer, or `None`; unset: the backend is told nobody answered |
| `agent.waiting` | as each turn starts | `list[str]` said while no turn was open, prepended to the turn |
| `agent.prompting` | between turns, by `agent.prompted()` | the next prompt, or `None` when there is none; `prompted()` raises `Stopped` for a stopped agent |

A watcher sees each question as an `asks` event. Under a flow, questions go to the role's
`on_ask_user` hook where the role declares `AskUserHookAgentMixin` (served by `claude`,
`codex`, `kimi`, `pi`); otherwise the backend is told nobody answered.

## Stopping and budgets {#stopping}

`agent.stop()` ends the running turn of every session, closes them, and makes every later call
raise `Stopped`. `agent.stopped` says whether it has happened. What the turn changed stays.

### Budgets {#cutting-a-turn-off-and-what-one-turn-may-spend}

`hmz.coganchor.agents.Budget` (frozen):

| Field | Default | Meaning |
| --- | --- | --- |
| `output` | `0.0` | output tokens one turn may write; `0` is no cap |
| `seconds` | `0.0` | wall-clock seconds one turn may run (tool time counts); `0` is no cap |
| `when` | `"next-response"` | `next-response`: let the answer in progress land; `immediately`: end the turn where it stands |
| `then` | `"end"` | `end`: answer with what was said; `fail`: raise `Unrecoverable` |

- Per turn: every turn starts with the whole budget. `Budget()` caps nothing.
- `AgentConfig.budget` is the agent's; `session.budget = …` overrides it for one conversation
  from its next turn.
- Held off the live meter ([Usage](#what-it-has-cost-and-how-fast)); `seconds` bites with no
  output arriving. On `agy`, `grok`, `qwen` and ACP CLIs, whose drivers do not feed the meter,
  `output` never bites.
- A turn ended by its budget has landed: its edits stay and the next turn resumes the session.
  It is never retried.
- A budget's cut-off wins over a `STOP` hook that would send the agent on.

### Interrupting {#interrupting-by-hand}

`session.interrupt(*, why)` ends the running turn and leaves the session usable (no-op with no
turn). `session.cut(*, why)` does the same and, on a backend with `cuts_transport`, puts the
shared transport down, ending every turn on it and any goal; the next turn restarts it and
resumes by id.

| How the backend holds a turn | `interrupt` reaches | `cut` reaches |
| --- | --- | --- |
| a command per turn: `cursor-agent`, `mcode`, `opencode`, `mimo`, and the command turns of `agy`, `grok`, `qwen` | the command and its children | the same |
| a held process: `claude`, `pi`, the ordinary turns of `agy`, `grok`, `qwen` | that process; `pi` is first sent `abort` and given 5 s | the same |
| a shared transport: `codex` (app server), `dsh` (SDK runtime) | nothing is taken down; the turn stops at the transport's next message | the transport and every turn on it |
| `kimi` (daemon) | the prompt is aborted (`POST …/prompts/<id>:abort`) | that, then the daemon's whole process tree |
| an ACP CLI | `session/cancel` | the same |

A cut turn still ends on exactly one `result`, carrying what had been said; a CLI that sends
whole messages only answers `""` if cut during its first.

### Allowances {#what-a-whole-run-may-spend}

A flow run's budget (`-p budget.<limit>=`) is held by the flow runtime, which hands each turn
what remains. For agents driven directly, `Ledger(Allowance(hours=0, tokens=0, dollars=0),
agents)` assigned to `agent.allowance` stops every agent of the set when any cap is reached.

| `Allowance` field | Unit | `0` |
| --- | --- | --- |
| `hours` | wall-clock hours | no cap |
| `tokens` | **millions** of output tokens | no cap |
| `dollars` | US dollars (an unpriced model counts as nothing) | no cap |

Checked by `SessionBase` at both edges of every turn and as each session closes; a turn asked
for under a spent allowance raises `Stopped`. Clones and stand-ins spend the same allowance.
`ledger.reads()` has `seconds`, `output`, `dollars` (`None` where nothing is priced), `floor`
(money is a lower bound), `blind` (caps nothing can read); `ledger.over()` says why, or `""`;
`ledger.spent` says whether it has been found over.

## Usage and cost {#what-it-has-cost-and-how-fast}

`session.spent()` and `agent.spent()` return a `Usage`: a mapping of kind to tokens, with
`input`, `output` and `total` attributes. `agents.KINDS` is `("input", "output", "cache_read",
"cache_write", "reasoning")`. A kind a backend does not report is absent.

| Backend | `counts` | The meter moves |
| --- | --- | --- |
| `claude` | input, output, cache_read, cache_write | on each message |
| `codex` | input, output (cached reads inside input) | on `thread/tokenUsage/updated` |
| `dsh` | input, output, cache_read, cache_write | on each finalised assistant message |
| `pi` | input, output, cache_read, cache_write | on each finalised assistant message |
| `opencode`, `mimo` | all five | on each step |
| `kimi` | input, output, cache_read, cache_write | on each `turn.step.completed` notification |
| `cursor-agent`, `mcode` | input, output, cache_read, cache_write | once, on the closing `result` |
| `agy` | input, output, cache_read, reasoning | never: usage is on the `result` event only |
| `grok`, `qwen` | input, output, cache_read, cache_write | never: usage is on the `result` event only |
| an ACP CLI | none | never |

- `rate(over=WINDOW)`: tokens per second by kind, over the last `over` seconds of wall clock
  (`agents.WINDOW == 300`); a younger run is measured over its life.
- `juice(over=WINDOW)`: output tokens per model request; `0.0` for a window with none.
- The `result` event's `spent` is the turn's usage and `tokens` its per-model totals.
- `hmz.coganchor.prices.cost(usage, model)` prices a `Usage` kind by kind; `price(model)`
  returns the `Price`. Both read `$HUMANIZE_HOME/prices.json` (fetched from
  `https://openllmprices.com/data/prices.json`, refreshed after 24 h; `HUMANIZE_PRICES`
  points elsewhere or turns fetching off with `off`) and return `None` for an unlisted model.
- The TUI's running cost reads the CLIs' own logs as they are written, for `claude`, `codex`,
  `dsh`, `kimi` and `mcode`; for the rest it moves as each turn lands. Each model request is
  counted once: Claude's rows sharing a message id (one per content block, each with the whole
  usage) and Codex's `token_count` rows with an unmoved `total_token_usage` are one request.
  Only rows the log timestamps at or after the moment the run opened that session count: a
  conversation carried on from an earlier run, or forked from another, keeps that one's rows,
  and a row with no timestamp is counted.
  What is shown per model is the higher of what the logs and the backends say, never the sum.

<small>Defined in [`src/hmz/coganchor/agents/event.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/event.py) (`Usage`, `KINDS`), [`src/hmz/coganchor/agents/allowance.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/allowance.py), [`src/hmz/coganchor/prices.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/prices.py), [`src/hmz/tui/tally.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/tui/tally.py).</small>

## Skills {#the-skills-an-agent-carries}

Skills installed for a CLI are the CLI's own; humanize does not disable them or write its
settings. `hmz.coganchor.agents.skills.skills(cli)` lists what the CLI would load here.

`agent.loaded` / `agent.loads(loaded)` are the skills whoever drives the agent brings (under a
flow, the role's `_skills`). `session.skills` / `session.loads(names | None)` select which of
those one conversation carries, from its next turn; a name not brought is ignored.

Brought skills are copied, for the session's life, where the backend reads a project's skills
(`Profile.mounts`), and removed after. A project's own skill of the same name wins.

| Backend | Mounted at | Skill directories read (`Profile.works`, relative to the workspace) |
| --- | --- | --- |
| `claude` | `.claude/skills/` | `.claude/skills` |
| `cursor-agent` | `.cursor/skills/` | `.cursor/skills` |
| `agy`, `codex`, `grok`, `kimi`, `mcode`, `mimo`, `opencode`, `qwen` | `.agents/skills/` | `.agents/skills` and each CLI's own (`.codex/skills`, `.grok/skills`, `.kimi-code/skills`, `.minimax/skills`, `.mimocode/skill[s]`, `.opencode/skill[s]`, `.qwen/skills`, and on some `.claude/skills`, `.cursor/skills`) |
| `dsh`, `pi` | none | none |

- `pi` reads workspace skills only for a trusted project; pass paths with
  `PiAgentConfig.skill_paths` (`--skill`).
- Under a native anchor, skills are [carried](/reference/remote-execution#native-the-target-s-own-cli)
  into the target's workspace; under a supervised anchor they reach the target only where it
  reads this workspace.

## Callback tools {#callbacks-as-tools}

`session.offers([Tool(name, about, call, takes=None)])` gives the agent a tool whose call runs
`call` in this process; `offers(None)` withdraws them. Not available to flows.

| `Tool` field | Meaning |
| --- | --- |
| `name` | what the agent calls it |
| `about` | what it is for, said to the model |
| `takes` | a pydantic model of its arguments, or `None` for none |
| `call` | called with the model (or nothing); its return value goes back as text; raising is the tool failing |

- Served by `claude` (`--mcp-config`) and `codex` (`-c mcp_servers.humanize.…`)
  (`session.takes_tools`); elsewhere `NotImplementedError: <cli> has no way of being given a
  tool of a flow's own`.
- The road is MCP: the CLI is given `hmz internal tools --at <socket>`. Tools are per agent.
- A native anchored turn on a non-`local` target cannot be offered tools (refused).

## Machine and account

<a id="where-the-turns-land"></a>

`AgentConfig.machine` decides where turns land; `agent.anchor` brings the machine up on first
read ([Machines](/reference/machines)). Under a flow, the session's environment decides.

<a id="which-account-it-runs-as"></a>

`AgentConfig.provider` names the account ([Providers](/reference/providers)). `agent.provider`
raises `ValueError: <id>: no <cli> provider called '<name>'` the first time a turn needs a
missing account; it never falls back to the machine's own.

## When a turn fails {#retries}

Before a failure reaches the caller, two things are tried in order: retries at the same
place, in the same conversation, and then each place of the fallback chain, in order.

### Retries

A place is `CLI[@ACCOUNT]/MODEL` (`agent.spec`). Retries are set per place in
`fallbacks` in `$HUMANIZE_HOME/settings.yaml`, by `Hmz().fallbacks.retrying(place, tries, policy, timeout)` or
the Fallback page of `/settings`. Nothing is retried by default.

| Policy | Waits (base 1 s, each capped at 60 s) |
| --- | --- |
| `none` | 0 |
| `constant` | 1, 1, 1, … |
| `linear` | 1, 2, 3, … |
| `exponential` | 1, 2, 4, 8, … |
| `exponential-jitter` (default) | uniformly random up to the exponential wait |
| `fibonacci` | 1, 1, 2, 3, 5, … |

Each fault adjusts the place's retries (`fallbacks.ANSWERS`):

| Fault | Tries (floor) | Wait | Transport reopened | Fix |
| --- | --- | --- | --- | --- |
| `throttled` | 1 | at least 30 s | no | the service asks it to slow down, with no quota spent; a wait is what answers it |
| `spent` | 1 | at least 30 s | no | this account has spent its quota; another one, or a wait, is what answers it |
| `refused` | none | — | no | that account needs signing in again |
| `unlisted` | none | — | no | that model is not this account's to name; ask it what it runs and name one of those |
| `retired` | none | — | no | the model is gone or was never this account's; another place is what answers it |
| `contended` | 3 | constant | no | two turns of it are sharing one database |
| `dropped` | 1 | the place's | yes | |
| `fenced` | none | — | no | the run's network fence keeps it off that host, which no sign-in answers; give the role online of ALL to let it through |
| `killed` | 1 | constant | yes | the machine it runs on may be out of memory |
| `missing` | none | — | no | |
| `sandboxed` | none | — | no | this machine will not let it sandbox itself; run it without one, or somewhere it can |
| `unmirrored` | none | — | no | that path cannot be made here; use a workdir whose path you can create here, or put self in the affinity of the runtime the work is on |
| unclassified | the place's | the place's | no | |

`Unrecoverable` is never retried or carried.

| Refused by `fallbacks` | `ValueError` |
| --- | --- |
| a place that does not parse | `'<text>' is not a place: expected CLI[@ACCOUNT]/MODEL` |
| an unknown policy | `'<p>' is not a retry policy: none, constant, linear, exponential, exponential-jitter, fibonacci` |
| negative or infinite numbers | `tries and seconds are counts, not debts or infinities` |
| a place falling back to itself | `<place> cannot fall back to itself` |
| a place named twice on one chain | `<place> is already one of the places <spec> falls back to` |

### Fallback chain {#when-the-place-has-nowhere-left-to-run}

`Hmz().fallbacks.points(place, [other, another])` writes the places a place's turns go to once
its retries are spent, in order. `fallbacks.chain(place)` is `[place, *to]` for a place a rule is
written against, and `[place]` for any other, including one that is only on somebody else's
chain. `agent.stands_in()` returns the stand-in at the next place, built once and kept; a
stand-in holds the rest of the chain it was reached by and carries on along it, never along a
rule of its own place. Each stand-in is retried as its own place's rule says. The turn is taken
in a new session at the other place, by an agent configured as this one (effort, rung, skills);
settings that were measurements of the old model (`of_model` fields, e.g. Codex `overrides`) are
dropped when the model changes. An account names no fallback of its own: another account of the
same CLI is a place on the chain.

<small>Defined in [`src/hmz/coganchor/fallbacks.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/fallbacks.py), [`src/hmz/coganchor/standin.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/standin.py).</small>

## Watchdog {#when-a-cli-stops-answering}

Every blocking read of a turn runs under a clock that restarts whenever the backend says
anything.

| Setting | Value |
| --- | --- |
| Silence allowed | `Profile.silence`: 900 s; 360 s for `dsh` |
| Override | `HUMANIZE_WATCHDOG=<seconds>`; `0` or less disables it |
| Paused | while the turn waits on a person: a permission prompt, a question, a pausing hook |

When the clock runs out, in order:

1. **Look.** A process (or a descendant) burning CPU gets up to 4 more windows; a suspended
   or defunct one gets none.
2. **Interrupt** the turn; the conversation is untouched.
3. **Drop the transport**, signalling the process tree; on `codex` and `kimi` the shared server
   goes, ending the agent's other turns too, and that is said first.
4. **Kill** what is left and wait.

Each step emits a `notice`, `<backend> …`: `has said nothing for <n>s but is still working`,
`has said nothing for <n>s`, `was asked to stop: …`, `is not answering; ending it[; <id> is
picked back up on the next try]`, `did not go when it was asked; killing it and everything
under it`. The turn then fails as an ordinary `Failed`, which retries take against the same
conversation.

<small>Defined in [`src/hmz/coganchor/agents/watchdog.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/watchdog.py).</small>

## State, logs and traces {#state-and-logs}

| Backend | Home (`home_var`, else default) | Session log (`logs`, `{ident}` the session id) | Trace | Subagents in trace |
| --- | --- | --- | --- | --- |
| `agy` | `~/.gemini/antigravity-cli` | `conversations/{ident}.db` | yes | yes |
| `claude` | `$CLAUDE_CONFIG_DIR`, `~/.claude` | `projects/*/{ident}.jsonl`, `projects/*/{ident}/subagents/**/*.jsonl` | yes | yes |
| `codex` | `$CODEX_HOME`, `~/.codex` | `sessions/**/rollout-*{ident}.jsonl` | yes | yes |
| `cursor-agent` | `$CURSOR_CONFIG_DIR`, `~/.cursor` | none | no | — |
| `dsh` | `$DSH_HOME`, `~/.dsh` | `sessions/*/{ident}/session.jsonl` | yes | yes |
| `grok` | `$GROK_HOME`, `~/.grok` | `sessions/*/{ident}/updates.jsonl` | yes | yes |
| `kimi` | `$KIMI_CODE_HOME`, `~/.kimi-code` | `server/events/{ident}.jsonl` | yes | yes |
| `mcode` | `$MINIMAX_DATA_DIR`, `~/.minimax` | `v2/sessions/*/*/*/*-session_{ident}/messages.jsonl`, `{ident}` URL-safe base64 without padding (`Profile.encodes`) | yes | no |
| `mimo` | `$XDG_DATA_HOME/mimocode`, `~/.local/share/mimocode` | SQLite `mimocode.db` | yes | yes |
| `opencode` | `$XDG_DATA_HOME/opencode`, `~/.local/share/opencode` | SQLite `opencode.db` | yes | yes |
| `pi` | `$PI_CODING_AGENT_DIR`, `~/.pi/agent` | `sessions/*/*{ident}.jsonl` | yes | no |
| `qwen` | `$QWEN_HOME`, `~/.qwen` | `projects/*/chats/{ident}.jsonl` | yes | no |
| an ACP CLI | none | none | no | — |

- A turn keeps its sessions in the run's directory, laid out as the CLI's home, rather than in
  the home ([Providers › Where sessions are kept](/reference/providers#where-sessions-are-kept)).
  A trace reads both.
- `agent.opened` is the backend's id for every session the agent opened, oldest first;
  `hmz.runtime.tracing.collect(agents={id: agent.opened, …})` gathers them. See
  [Tracing](/reference/tracing).
- Paths kept on this machine under a supervised anchor are in
  [Remote execution › What stays on this machine](/reference/remote-execution#what-stays-on-this-machine).

## Backend notes {#backend-notes}

### Antigravity {#antigravity}

`agy`. Ordinary turns are lines on one held process started with `--input-format stream-json`;
a slash command (a whole first word such as `/help`) and a shaped turn run as separate
`--print` commands and resume with `--conversation <id>`. Changed configuration, customisations
or flow resources restart the process; an anchored turn always ends it.

| Field | Default | Meaning |
| --- | --- | --- |
| `add_workspace` | `True` | `--add-dir <session dir>`, pinning the session's directory |
| `print_timeout` | `86400.0` | `--print-timeout` seconds (raised from the CLI's 300; since 1.1.28 a timed-out turn exits successfully with a partial answer) |
| `disable_slash_commands` | `False` | `--disable-slash-commands`; with `read-only`: `Unserved: agy cannot run at read-only with disable_slash_commands: its plan mode has no effect while expansion is off` |
| `sandbox` | `False` | `--sandbox`, the CLI's terminal restrictions; not how a fence is held |

- Usage is cumulative per conversation; each result reports its own increment. Shaped answers
  validate the final `structured_output`.
- A fence is held from outside in full. With `online` cut it still reaches its eligibility
  hosts (including `lh3.googleusercontent.com`) and starts a loopback language server on a
  kernel-chosen port; the turn is started as `hmz-offline` regardless of `web_search`.
- Credential: `antigravity-oauth-token` under its home (only `HOME` moves it).

### Claude Code {#claude-code}

`claude`. One process per session:

```text
claude --print --input-format stream-json --output-format stream-json --verbose
  [--include-partial-messages]
  (--session-id <new uuid> | --resume <id> | --resume <parent> --fork-session)
  [--permission-mode plan|acceptEdits|auto|bypassPermissions|manual]
  [--permission-prompt-tool stdio]
  --settings '<json>' --model <model> [--effort <rung>] [--json-schema '<json>']
  [--disallowedTools <list>] [--allowedTools <list>] [--mcp-config '<json>']
```

| Field | Default | Meaning |
| --- | --- | --- |
| `allowed_tools` | `()` | `--allowedTools` rules; at most 32, sorted, unique, no `,`, each at most 4096 characters (`ValueError: allowed_tools must be unique sorted Claude tool rules`) |
| `partial_messages` | `True` | `--include-partial-messages` |
| `asks` | `None` | at `bypass`, `--permission-mode manual` instead of `bypassPermissions`, so every tool that would change something is asked about. `None`: while a `PERMISSION_REQUEST` hook is hung on the agent. A flow sets it `True` while its own `PERMISSION_REQUEST` hook is hung and `False` otherwise |

- Every turn runs with `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, so background subagents and
  commands finish inside the turn.
- `--settings` carries `fastMode` (fast tier) and the `PreToolUse` hook table only when needed.
- `--json-schema`, a hook table change, an effort change, a change of `asks`, or a change of
  offered tools restarts the process and resumes the conversation.
- A result with `is_error`, a non-`success` subtype, a `terminal_reason` other than
  `completed`, or a `stop_reason` of `max_tokens`, `model_context_window_exceeded`,
  `pause_turn`, `tool_deferred` or `tool_use` (without structured output) fails the turn.
- An anchored session's process ends with each turn.

### Codex {#codex}

`codex`. One app server per agent, shared by its sessions:

```text
codex app-server [--strict-config] [--disable goals] [--enable|--disable <feature>]...
  [--disable apps] [--disable respect_system_proxy] [--enable use_legacy_landlock]
  [--disable shell_snapshot]
  [-c web_search="live"|"disabled"] --stdio
  [-c <override>]... [-c mcp_servers.humanize.command=… -c mcp_servers.humanize.args=…]
```

Threads are `thread/start`, `thread/resume` and `thread/fork`; turns are `turn/start` (model,
effort, rung, approval, service tier, `outputSchema`); steering is `turn/steer`.

| Field | Default | Meaning |
| --- | --- | --- |
| `overrides` | `()` | `-c` pairs; only `model_context_window` and `model_auto_compact_token_limit`, positive integers, the second below the first. Dropped when a fallback changes the model. |
| `features` | `()` | `--enable`/`--disable` pairs by `codex features list` names; `goals` and names beginning `browser_use`, `computer_use`, `standalone_web_search`, `web_search` are refused |
| `strict_config` | `False` | `--strict-config` |
| `approvals` | `""` | approval policy replacing the rung's: `untrusted`, `on-request`, `on-failure`, `never` |

| Refusal | `ValueError` message |
| --- | --- |
| another override key | `model is not a Codex override; expected model_auto_compact_token_limit, model_context_window` |
| a non-positive value | `model_context_window must be a positive integer, not '-1'` |
| wrong order | `model_auto_compact_token_limit must be below model_context_window` |
| `goals` as a feature | `goals is the flow's to say, as AgentConfig(goals=...) -- a second place for it would be two answers` |
| a web or browser feature | `web_search_request is what the agent may reach for, which the flow says as AgentConfig(web_search=...) and AgentConfig(permission=...) where it declares the place -- a feature is not a second place for it` |
| bad `approvals` | `approvals must be one of '', 'untrusted', 'on-failure', 'on-request', 'never', not 'sometimes'` |

- The server reads `overrides`, `features`, `strict_config`, `web_search`, the account and the
  fence once at start; a change starts a new server for the next turn and each conversation is
  resumed there by id. Model, effort, rung and `approvals` are per call.
- `-p/--profile` and `--add-dir` are not offered; `codex app-server` does not take them.
- No hook table: Codex runs hooks only once trusted in the user's `config.toml`.
- On another machine, a sandboxed rung whose fence is at least as narrow is sent
  `sandboxPolicy: externalSandbox` ([Remote execution](/reference/remote-execution#a-fence-on-both-machines)).
- Supervised with its commands on another machine (any anchor but `native`), the server starts
  with `--disable shell_snapshot` unless `features` names it: Codex writes its shell capture
  into its own home and sources it from each command, which runs on the target, where that
  home is not. Each command is a login shell on the target instead.
- A `gateway` account appends `-c model_provider=humanize …` ([Providers › Gateways](/reference/providers#gateways)).

### Cursor Agent {#cursor-agent}

`cursor-agent`. One command per turn:

```text
cursor-agent --print --output-format stream-json --workspace <dir> --model <id>
  [--resume=<chat id>] [<rung flags>] [--trust] [--stream-partial-output] [--approve-mcps]
  [--add-dir <dir>]... -- <prompt>
```

| Field | Default | Meaning |
| --- | --- | --- |
| `trust` | `True` | `--trust`: the workspace is trusted without asking |
| `partial_output` | `False` | `--stream-partial-output`; the gathered duplicate message is dropped |
| `approve_mcps` | `False` | `--approve-mcps` |
| `add_dirs` | `()` | `--add-dir` per entry |

- `--workspace` is the directory on the machine `cursor-agent` runs on: for work on another
  machine with `cursor-agent` here, the copy of the work kept here, never the far path.
- The effort and tier are written into the id: `composer-2.5` at `high` is
  `composer-2.5-high`, at the fast tier `composer-2.5-high-fast`. A name already carrying a rung
  is used as is. Bracket syntax (`gpt-5.2[effort=low]`) is not built.
- The id is checked against the account's last catalogue: an unlisted rung is `Unserved`,
  naming those listed. An account never asked refuses nothing.
- On another machine, `workspace-write` runs `--force --sandbox disabled` where the fence writes
  nothing of the home or system.
- `cursor-agent-local`, pointed at an OpenAI-compatible endpoint with
  `CURSOR_LOCAL_AGENT_BASE_URL`, `CURSOR_LOCAL_AGENT_API_KEY` and `CURSOR_ENABLE_AUTHLESS=1`,
  takes the id it serves; under a provider, `CURSOR_LOCAL_AGENT_API_KEY` is hushed unless set.

### DeepSeek Harness {#deepseek-harness}

`dsh`. Driven through `deepseek-harness-sdk` (`>=0.1.1rc1,<0.1.2`) in this process; no CLI.
Models: `deepseek-v4-flash`, `deepseek-v4-pro`. Each session starts from the SDK's default
composition (`runtime/cordis.yml`) with the effort written onto it.

| Field | Default | Meaning |
| --- | --- | --- |
| `compaction` | `True` | mounts `dsh-token-meter` and `dsh-compaction-basic`, compacting at 0.8 of the context window |
| `session_compression` | `"none"` | the session log's compression, `none` or `zstd` (the tally cannot read `zstd`) |

- `goals` mounts the goal service, `create_goal` and the round driver; re-read every turn, so a
  reconfigured agent gets a rebuilt runtime and keeps its conversation.
- `Unrecoverable`: the length refusal, and a session id the runtime will not resume.
- Sessions are placed by the driver (`Profile.told`) under the kept session directory.
- `interject` is unsupported: `session/prompt` queues and `steer` is not on the SDK surface.
- Without an account, the SDK's saved credentials or `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`.

### Grok Build {#grok-build}

`grok`. Ordinary turns are `session/prompt` on a held `grok agent stdio`, which takes only a
model, an effort, an approval, an agent profile, a plugin directory and the leader. A
tool-withholding rung, `web_search=False`, a network-cutting fence, a shape, a fork, or any field
below but `leader` set away from default sends the turn to
`grok -p --output-format streaming-json --resume <id> …` instead.

| Field | Default | Meaning |
| --- | --- | --- |
| `leader` | `False` | `False`: a process per conversation; `True`: join the shared leader; `None`: `[cli] use_leader` in `config.toml` (sent as `--no-leader` when fenced) |
| `sandbox` | `""` | `--sandbox <profile>` |
| `max_turns` | `0` | `--max-turns`; `0` uncapped |
| `subagents` | `True` | `False` is `--no-subagents` |
| `rules` | `""` | `--rules`, appended to its system prompt |

- The `-p` prompt is one argument (`--single=…`); Linux caps an argument at 32 pages, so a
  prompt over 131062 bytes raises before the process starts.
- `--include-partial-messages`, `--agent-profile` and `--plugin-dir` are not fields.
- Every turn is run with `GROK_FOLDER_TRUST=0`: Grok Build reads a project's skills, the ones a
  flow mounts under `.agents/skills` included, only from a folder it trusts.

### Kimi Code {#the-daemon-kimi-is-driven-through}

`kimi`. A `kimi web` daemon per agent (needs the `[kimi]` extra), driven over REST and its
WebSocket notifications: the daemon has a route into a running turn, a per-turn body for the
rung, thinking level and swarm width, and question ids.

| Field | Default here | `kimi web`'s own | Meaning |
| --- | --- | --- | --- |
| `port` | `0` (free port) | `58627` | |
| `open_browser` | `False` | opens one | |
| `log_level` | `error` | `silent` | one of `fatal`, `error`, `warn`, `info`, `debug`, `trace`; `silent` is refused (the driver reads `Kimi server: <url>/#token=<token>`) |
| `web_title` | `None` | `<dir> \| Kimi Code` | the web UI title |

- Notifications wake the driver's REST polling (1 s without them); heartbeats are answered.
- Usage comes from `turn.step.completed` (`inputOther`, `output`, `inputCacheRead`,
  `inputCacheCreation`); the larger of the steps' sum and the session aggregate wins per kind.
- A turn is over when the session is seen stopped twice, a wait apart, after it was seen to
  start. One whose `turn.ended` notification says `reason: failed` fails, with the daemon's
  `error` message, rather than answering with nothing.
- The fence goes up once, when the daemon starts; another fence or account starts a new daemon.
  With `online=False`, the port is chosen before start and is the only one in `listen`, and
  `WebSearch`/`FetchURL` are in `disabled_tools` regardless of `web_search`.
- `--add-dir`, `--skills-dir`, `--agent`, `--agent-file` are ignored by `kimi web` and not
  offered.

### MiniMax Code {#minimax-code}

`mcode`. One command per turn, the prompt on stdin:

```text
mcode exec --output-format stream-json --input - --cwd <dir> [--model <model>]
  [--session <id>] [--effort <rung>] [--permission full|smart] [--output-schema '<json>']
```

No fields of its own.

- `--cwd` is the directory on the machine `mcode` runs on: for work on another machine with
  `mcode` here, the copy of the work kept here, never the far path.
- The session is continued with `--session` and the id its first turn's lines carry.
- `--effort` is sent only where the account's catalogue lists the rung for the model (only
  `minimax/MiniMax-M3.1-Flash-Preview` takes rungs).
- `read-only` is refused; `web_search=False` and a network-cutting fence are refused.
- The stream reports its `task` tool as `SUBAGENT_START`/`SUBAGENT_STOP`; usage arrives on the
  closing result, and the running cost reads its session log.
- Each start creates `~/.minimax.lock` beside its data directory, which a fence that reads but
  does not write the home cannot grant. A fenced turn's supervisor answers that path from the
  kept session directory (`sessions/mcode/minimax.lock`), shared by every agent of the run.
  With `HUMANIZE_SESSIONS=off` the directory is still made and holds only that lock. On a
  machine that cannot supervise a turn the path is not answered, and only a fence that
  writes the home lets `mcode` start.
- `config.yaml` and `auth/` are credential files, so an account holds its own settings.

### opencode and mimocode {#what-opencode-and-mimocode-add-to-a-bare-run}

`opencode` and `mimo` (one program under two names). One command per turn:

```text
opencode run --format json --dir <dir> --model <provider/id> [--variant <effort>]
  [--session <id> | --session <parent> --fork] [--agent <name>] [--thinking] [--pure]
  [--auto | --dangerously-skip-permissions] <prompt>
```

| Field | Default | Meaning |
| --- | --- | --- |
| `cli_agent` | `""` | `--agent NAME` |
| `thinking` | `False` | `--thinking`: reasoning streamed as `reasoning` events |
| `pure` | `False` | `--pure`: no plugins |
| `unattended` | `None` | `--auto` (opencode) / `--dangerously-skip-permissions` (mimo); `None`: on where a rung is named |
| `permission_table` | `None` | `OPENCODE_PERMISSION` / `MIMOCODE_PERMISSION` carrying the rung and web answer; `None`: written where either is said; `False` refused beside a withholding rung or `web_search=False` (`Unserved: permission_table=False withholds the only table this backend hears permission='read-only' in`) |

- The table is written for the turn, never to a settings file. Its `read` and `edit` rules are
  relative to the top of the git checkout the session is in, or `/`.
- mimocode reads `~/.claude.json` at start; where the fence does not let it,
  `MIMOCODE_DISABLE_CLAUDE_CODE=1` is set.
- Both keep sessions in SQLite; traces read it with a query.

### pi {#pi}

`pi`. One `pi --mode rpc` per session:

```text
pi --mode rpc --model <model> --session-id <id> [--fork <parent>] [--thinking <rung>]
  [--exclude-tools bash,edit,write,powershell] [--no-context-files] [--no-extensions]
  [--offline] [--append-system-prompt <s>]... [--skill <path>]...
```

| Field | Default | Meaning |
| --- | --- | --- |
| `compiled` | `True` | `NODE_COMPILE_CACHE` at `$HUMANIZE_HOME/compiled/pi` unless already set; not for anchored turns |
| `context_files` | `True` | `False` is `--no-context-files` |
| `extensions` | `True` | `False` is `--no-extensions` |
| `offline` | `False` | `--offline`; forced under `online` `NONE` |
| `append_system_prompt` | `()` | `--append-system-prompt` per entry (text or path) |
| `skill_paths` | `()` | `--skill` per entry |

`--session-id` rather than `--continue`, which resumes the newest session in the directory.
pi 0.85.1 has no web tools of its own.

### Qwen Code {#qwen-code}

`qwen`. Ordinary turns are lines on a held process (`--input-format stream-json`); a shaped
turn runs as a separate command (`--json-schema` is refused with stream-json input). The
opening turn is `--session-id <new uuid>`; later ones `--resume <id>`; a fork
`--resume <parent> --fork-session`. An id already used in the project is retried under a new
one.

| Field | Default | Meaning |
| --- | --- | --- |
| `headless_defaults` | `True` | writes Qwen's system-defaults layer with `general.preventSystemSleep: false` and `general.enableAutoUpdate: false` |
| `compile_cache` | `True` | `NODE_COMPILE_CACHE` at `$HUMANIZE_HOME/compiled/qwen` unless set; not for anchored turns |
| `partial_messages` | `False` | `--include-partial-messages` |

- The effort is a settings file named by `QWEN_CODE_SYSTEM_SETTINGS_PATH`, one per effort,
  shared by concurrent sessions at that effort, under one `hmz-qwen-*` temporary directory.
  A `QWEN_CODE_SYSTEM_DEFAULTS_PATH` of the user's is watched for changes; settings the driver
  cannot parse keep a fresh process per turn.
- Usage counts each assistant message once; the terminal summary fills only missing fields.

## A CLI of your own {#a-cli-of-your-own}

Any agent speaking the [Agent Client Protocol](https://agentclientprotocol.com) can be added as
a backend, from the TUI (`/settings accounts` → `add a custom CLI`) or with
`backends.remember(name, command)`. It is written under `clis` in
`$HUMANIZE_HOME/settings.yaml` and is a backend in every workspace from the next prompt.

`clis` is a mapping keyed by name; each value is the command (a list of strings), or a
mapping:

```yaml
clis:
  my-agent:
    command: [my-agent, --acp]
    hosts: [api.my-agent.example]
    state: [~/.my-agent]
```

| Key | Meaning |
| --- | --- |
| `command` | argv that starts it |
| `hosts` | hosts reachable under `online` `NONE`, spelled as `Profile.hosts` spells them; none: a network-cutting permission is refused (`HarnessSandboxed`) naming what to declare |
| `state` | paths it writes its state to, granted whatever `user` says; none: nothing of the home is writable |

`backends.declared(name)` returns `(hosts, state)`; `backends.forget(name)` removes one. An
unreadable settings file reads as no added CLIs.

| `remember` refusal | `ValueError` message |
| --- | --- |
| no command | `an added CLI needs a command to start it with` |
| the command is a built-in backend (any alias, by its last path component) | `claude is already a backend humanize drives` |
| a name other than the command's own | `an added CLI is called what it runs, so my-agent is added as my-agent rather than as foo` |

Protocol use: `initialize`; `session/new`; `session/prompt` per turn; `session/update`
notifications for output; `session/resume` or `session/load` (whichever the agent advertises)
to continue; `session/fork`; `session/cancel`. No model, effort or mode is sent
(`session/set_model`, `session/set_config_option`, `session/set_mode` are unused): model and
effort read `as configured`. Every permission request is granted, by the option's kind. It
cannot be steered, has no goal, reports no usage and has no trace.

`AcpAgentConfig` fields, off by default:

| Field | Type | Meaning |
| --- | --- | --- |
| `cli` | `str` | the name it was added under |
| `command` | `tuple[str, ...]` | overrides the recorded command |
| `reads_files` | `bool` | serve `fs/read_text_file` from this machine |
| `writes_files` | `bool` | serve `fs/write_text_file` |
| `terminals` | `bool` | serve `terminal/*` (start, read, wait, kill) |
| `mcp_servers` | `tuple[McpServer, ...]` | MCP servers added to the agent's own |

The first three are refused for an agent under a native anchor. Under a fence, what this
client does for the agent is held to the same fence: a refused file or path is answered with
`reject_once`, and a terminal command runs inside the fence.

<small>Defined in [`src/hmz/coganchor/backends.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/backends.py) (`speaking`, `declared`, `remember`, `forget`, `_speaks`), [`src/hmz/coganchor/agents/acp.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/acp.py).</small>

## Bundle patching {#reaching-into-a-bundled-cli}

`hmz.coganchor.agents.patching` rewrites a copy of a Bun standalone executable (`claude`,
`opencode`) where no shallower route reaches a behaviour. `patched(profile, path, patches)`
returns the copy's path, or `None`.

- Never the installed binary: the copy lives in a directory of humanize's own for one session.
- Fingerprinted against `Profile.bundles` (a path glob, a regular expression one module must
  match, an optional SHA-256); `tests/system/agents/test_patching.py` checks them.
- Any mismatch or failure returns `None`, is logged, and the shallower route is used.
- Every rewrite is the same length as what it replaces; the module's precompiled bytecode is
  cleared.

## Names, clones and the person

<a id="names-and-what-a-run-left-behind"></a>

| Attribute | Meaning |
| --- | --- |
| `agent.id` | the given `name=`, the flow's role name, or a codename |
| `agent.backend` | the backend's name, or an ACP CLI's |
| `agent.opened` | every session id it opened, oldest first |
| `agent.sessions` | the sessions still held |
| `agent.config` | its config |
| `agent.spec` | `CLI[@ACCOUNT]/MODEL` |

An unnamed agent gets a codename from Amphoreus (*Honkai: Star Rail*): 29 designations used
verbatim while any is free (half the time), otherwise morphemes joined at a capital plus digits.
No codename repeats in one process.

<a id="an-agent-that-is-not-quite-the-one-you-were-handed"></a>

`agent.clone(*, config=None, name=None, skills=None)` makes a fresh agent: same settings unless
given, no conversations, spending, watchers or hooks, a new codename unless named; it spends the
same allowance. `reconfigure(config)`, `runs_on(machine)`, `loads(skills)`, `rename(name)` and
`disable_goals()` change an agent in place; flows have none of them, only `derive`.

### The person as an agent {#the-person-as-an-agent}

`HumanAgent(name="human")` asks the person and answers with what they typed. It runs no model,
spends nothing, runs no moment, and emits no `begins`/`ends`.

<a id="asking-them-for-a-shape-which-is-a-questionnaire"></a>

With `schema=`, the person is asked one question per field:

| In the model | Asked as |
| --- | --- |
| `description=` | the question (the field name where none) |
| `Literal[…]` | those words as options |
| `bool` | `yes` / `no` |
| a default | `or - for <default>`; `-` takes it |
| `list[str]` | one comma-separated line |

A refused value is asked again a bounded number of times. Under `suppress`, an unfinished
questionnaire answers `None`. In a flow the person is an `Outworlder` role; an away outworlder
answers with the model built from its defaults, or raises `OutworlderAway` for a field without
one.

## Environment variables {#environment-variables}

The variables the agent layer reads or sets. Every variable humanize reads is listed in
[Environment variables](/reference/environment).

| Variable | Read by | Effect |
| --- | --- | --- |
| `HUMANIZE_HOME` | everything | humanize's home (default `~/.hmz`): `settings.yaml`, `providers/`, `sessions/`, `prices.json`, `compiled/` |
| `HUMANIZE_WATCHDOG` | the watchdog | seconds of silence allowed; `0` or less disables it |
| `HUMANIZE_SESSIONS` | session keeping | `off`, `0` or `no`: sessions stay in the CLI's home |
| `HUMANIZE_PRICES` | `prices` | the price list's URL or path; `off`, `0`, `no`, `none` or empty disables fetching |
| each backend's home variable | the drivers, traces, providers | see [State, logs and traces](#state-and-logs) |
| `XDG_CONFIG_HOME` | credential and skill paths | the `config/` root |

Set by drivers on a turn:

| Variable | Backend | Value |
| --- | --- | --- |
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` | `claude` | `1` |
| `NODE_OPTIONS`, `HMZ_PRELOAD_AT`, `HMZ_PRELOAD_IN` | `kimi`, `pi`, `qwen`, `mimo` | the runtime-report preload, only while a `PRE_TOOL_USE` hook is hung |
| `NODE_COMPILE_CACHE` | `pi`, `qwen` | `$HUMANIZE_HOME/compiled/<cli>`, unless already set |
| `QWEN_CODE_SYSTEM_SETTINGS_PATH` | `qwen` | the per-effort settings file |
| `OPENCODE_PERMISSION`, `MIMOCODE_PERMISSION` | `opencode`, `mimo` | the permission table |
| `MIMOCODE_DISABLE_CLAUDE_CODE` | `mimo` | `1` where the fence hides `~/.claude.json` |
| `PKG_NATIVE_CACHE_PATH` | `dsh` | inside the fence's `tmp`, when fenced |
| `TMPDIR`, `TMP`, `TEMP`, `HTTPS_PROXY` and related | fenced turns | the fence's scratch directory and proxy |
| `HUMANIZE`, `HUMANIZE_TARGET`, `HUMANIZE_WORKSPACE` | anchored turns | see [Remote execution](/reference/remote-execution#variables-the-agent-is-given) |

## API summary {#api-summary}

```python
type Where = str | os.PathLike[str] | None

class AgentBase:
    moments: ClassVar[frozenset[Moment]]
    pursues: ClassVar[bool]
    service_tiers: ClassVar[tuple[str, ...]]
    rungs: ClassVar[tuple[str, ...]]
    counts: ClassVar[frozenset[str]]

    id: str; backend: str; config: AgentConfig; effort: str  # settable
    spec: str; opened: list[str]; sessions: list[SessionBase]; stopped: bool
    anchor: AnchorConfig | None; provider: Provider | None
    hooks: Hooks; loaded: tuple[Loaded, ...]; allowance: Ledger | None
    ask: Callable[[Question], str | None] | None
    waiting: Callable[[], list[str]] | None
    prompting: Callable[[], str | None] | None

    def __call__(prompt, *, suppress=False, schema=…, cwd: Where = None) -> str | T | None
    def pursue(objective, *, suppress=False, cwd: Where = None) -> str
    def new(cwd: Where = None) -> SessionBase
    async def aturn(...); async def apursue(...)
    def batch(prompts, *, suppress=False, schema=…, at_once=0, cwd: Where = None) -> list
    async def abatch(...)
    def batch_new(count, cwd: Where = None) -> list[SessionBase]
    def spent() -> Usage; def rate(over=WINDOW) -> Usage; def juice(over=WINDOW) -> float
    def clone(*, config=None, name=None, skills=None) -> Self
    def reconfigure(config); def runs_on(machine); def loads(skills); def rename(name)
    def disable_goals(); def stop()
    def watch(listener: Callable[[AgentBase, SessionBase | None, Event], None])
    def asked(question) -> str | None; def prompted() -> str | None
    def stands_in() -> AgentBase | None
    def node() -> Provider
    def environment() -> Mapping[str, str]; def hushed() -> frozenset[str]
    def fenced() -> Fence | None; def natively(fence: Fence) -> Fence

class SessionBase:
    shapes: ClassVar[bool]; steers: ClassVar[bool]; takes_tools: ClassVar[bool]
    narrates: ClassVar[bool]; forks_elsewhere: ClassVar[bool]; cuts_transport: ClassVar[bool]

    id: str; named: str | None; cwd: str; forks: bool
    effort: str; budget: Budget | None  # settable
    skills: tuple[str, ...]; tools: tuple[Tool, ...]

    def __call__(prompt, *, suppress=False, schema=…) -> str | T | None
    def stream(prompt, *, schema=None) -> Iterator[Event]
    def pursue(objective, *, suppress=False) -> str
    def fork(*, into=None, cwd: Where = None) -> SessionBase
    async def aturn(...); async def apursue(...)
    def interject(text); def interrupt(*, why); def cut(*, why)
    def loads(skills | None); def offers(tools | None)
    def spent() -> Usage; def rate(over=WINDOW) -> Usage; def juice(over=WINDOW) -> float
    def close()

class Failed(subprocess.CalledProcessError): fault: str; fix: str
class Unrecoverable(Failed): ...
class Stopped(Exception): ...
class Unserved(ValueError): ...
class Unfenced(Unserved): ...
class Unhooked(ValueError): ...
```

`CommandSessionBase` (one command per turn) and `StreamSessionBase` (one long-lived process fed
a line at a time) are the two shapes a driver subclasses; the contract is
[`specs/coganchor/agents.md`](https://github.com/humanfia/humanize/blob/main/specs/coganchor/agents.md).
