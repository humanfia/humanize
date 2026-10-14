# Agents

## 1. Scope

This specification governs how **hmz** drives a **harness** as an **agent**: which harnesses
exist and how an agent is named, which models and efforts an agent runs at, the configuration a
harness is launched with, what an agent is permitted to touch and how each harness is confined,
the turns, sessions, forks, steering, goals and schemas a harness serves, the hooks a flow hangs
on an agent, the tools and command lines a flow hands an agent, what happens when a turn fails,
the watchdog, token usage and cost, the LiteLLM gateway, harnesses added by the user over the
Agent Client Protocol, and the person at the prompt acting as an agent.

Out of scope:

- The accounts an agent runs as, their storage and their credentials: `features/accounts.md`.
- Where a harness runs relative to the env it works on, and the rule for configuration that
  crosses machines: `features/placements.md`.
- What an env is and how it is opened: `features/environments.md`.
- The flow-facing API through which a flow declares roles, permissions, hooks, tools and budgets:
  `api/flows.md`.
- The `-a` command-line option and exit statuses: `api/cli.md`.
- The `fallbacks` and `clis` keys of `settings.yaml`: `api/settings.md`.
- Where an epic keeps the sessions of its agents: `features/epics.md`.
- How usage and cost are displayed while an epic runs: `features/monitoring.md`.

## 2. Definitions

**2.1** **Harness kind**: the name by which hmz identifies one harness, as listed in §3.1.

**2.2** **Agent spec**: the text `<harness>[@<account>]/<model>[:<effort>]` that names an agent,
read as `api/cli.md` §7.4 states.

**2.3** **Place**: the text `<harness>[@<account>]/<model>`, identifying a harness kind, an
account and a model, without an effort.

**2.4** **Effort**: how hard the model is asked to think, in the words of the harness's effort
ladder (§4.3).

**2.5** **Effort ladder**: the ordered list of efforts a harness kind accepts.

**2.6** **Rung**: one of the four permission levels `read-only`, `workspace-write`, `auto` and
`bypass`, ordered from tightest to loosest.

**2.7** **Grant**: the four scopes `local`, `user`, `system` and `online` that a flow declares
for a role, each `NONE`, `READ` or `ALL`, as `api/flows.md` defines them.

**2.8** **Confinement**: the restriction hmz places around the harness process and every process
it starts, so that the agent touches no more than its grant allows.

**2.9** **Managed item**: an item hmz supplies to a harness at launch that the user did not
configure: a flow skill, a flow-declared subagent, a flow-declared command, the hmz tool server,
a hook hmz hangs, or a model declaration hmz adds for a flow or for an account.

**2.10** **System level**: the harness machine's system-wide configuration of a harness.

**2.11** **User level**: the harness machine's per-user configuration of a harness, together
with the managed items of the agent.

**2.12** **Project level**: the configuration of a harness found in the env's workspace.

**2.13** **Fault class**: the classification hmz assigns to a failed turn, one of `contended`,
`spent`, `throttled`, `refused`, `unlisted`, `retired`, `missing`, `sandboxed`, `unmirrored`,
`fenced`, `killed` and `dropped`, or unclassified.

**2.14** **Fallback chain**: the ordered list of places to which a turn is carried once its own
place has no retries left.

**2.15** **Stand-in**: an agent at the next place of a fallback chain that takes a turn its
original agent could not.

**2.16** **Fake tool**: a tool a flow declares whose calls run in the flow's process.

**2.17** **Fake command line**: a program a flow declares that appears on the agent's `PATH` and
whose runs are answered in the flow's process.

**2.18** **Gateway**: a LiteLLM proxy that hmz runs on this machine's loopback interface to
carry an account the harness has no way in for of its own.

**2.19** **ACP harness**: a harness the user adds by command line, driven over the Agent Client
Protocol.

**2.20** **Human agent**: the agent whose turns are answered by the user at the prompt.

**2.21** **Watchdog window**: the time a turn is permitted to pass without any output from its
harness before the watchdog acts (§12).

## 3. Harnesses

### 3.1 Harness kinds

**3.1.1** hmz MUST drive exactly the following built-in harness kinds, and MUST accept each under
every alias listed for it:

| Kind | Aliases | Product |
| --- | --- | --- |
| `agy` | `antigravity` | Antigravity CLI |
| `claude` | `claude-code` | Claude Code |
| `codex` | — | Codex |
| `cursor-agent` | `cursor-cli` | Cursor Agent |
| `dsh` | `deepseek-harness` | DeepSeek Harness (Python SDK, no CLI) |
| `grok` | `grok-build`, `grokbuild` | Grok Build |
| `kimi` | `kimi-code` | Kimi Code |
| `litellm` | — | a model called directly through LiteLLM (no CLI) |
| `mcode` | `minimax`, `minimax-code` | MiniMax Code |
| `mimo` | `mimocode`, `mimo-code` | mimocode |
| `omp` | `oh-my-pi` | Oh My Pi |
| `opencode` | — | opencode |
| `pi` | — | pi |
| `qwen` | `qwen-code` | Qwen Code |

**3.1.2** hmz MUST additionally drive, as an ACP harness, every command line the user has added
under its name (§14).

**3.1.3** hmz MUST record a harness kind by its kind name and MUST NOT record an alias.

**3.1.4** hmz MUST refuse a harness kind that is neither built in nor added, where the agent spec
naming it is read.

### 3.2 Installation

**3.2.1** Other than under the native placement, hmz MUST locate a harness's program on the
`PATH` of the harness machine, and, where it is not on the `PATH`, in `~/.local/bin`,
`/usr/local/bin`, `/opt/homebrew/bin`, `/usr/bin` and `/bin`, in that order.

**3.2.2** Under the native placement, hmz MUST locate a harness's program as
`features/placements.md` §3.2.3 states.

**3.2.3** A session whose harness is not installed on the harness machine MUST be refused before
its first turn with `HarnessNotInstalled`, whose message MUST name the harness and the command
that installs it.

**3.2.4** The install command named under §3.2.3 MUST be the following, and for a harness with
no install command the message MUST say `install <cli> and put it on PATH`:

| Kind | Install command |
| --- | --- |
| `claude` | `npm i -g @anthropic-ai/claude-code` |
| `codex` | `npm i -g @openai/codex` |
| `cursor-agent` | `curl https://cursor.com/install -fsS \| bash` |
| `dsh` | `pip install` of the DeepSeek Harness SDK and `python-dotenv` |
| `grok` | `npm i -g @xai-official/grok` |
| `kimi` | `npm i -g @moonshot-ai/kimi-code` |
| `litellm` | `pip install` of LiteLLM |
| `mcode` | `npm i -g @minimax-ai/code` |
| `mimo` | `npm i -g @mimo-ai/cli` |
| `omp` | `curl -fsSL https://omp.sh/install \| sh` |
| `opencode` | `npm i -g opencode-ai` |
| `pi` | `npm i -g @earendil-works/pi-coding-agent` |
| `qwen` | `npm i -g @qwen-code/qwen-code` |

**3.2.5** A turn whose harness program cannot be started MUST fail with the fault class
`missing`.

### 3.3 Capabilities served to flows

**3.3.1** Each harness kind MUST serve to a flow exactly the capabilities marked in the following
table, where Tools is fake tools (§10.1), Goal is `/goal` (§7.6), Loop is `/loop` (§7.7), Steer
is steering a running turn (§7.5), Perm is the permission-request hook, Sub is the subagent start
and stop hooks, and Ask is the ask-user hook (§9):

| Kind | Tools | Goal | Loop | Steer | Perm | Sub | Ask |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `claude` | yes | yes | yes | yes | yes | yes | yes |
| `codex` | yes | yes | — | yes | yes | yes | yes |
| `kimi` | — | yes | — | yes | yes | — | yes |
| `pi`, `omp` | yes | — | — | yes | — | — | yes |
| `dsh` | yes | yes | — | — | — | — | — |
| `cursor-agent`, `mcode` | — | — | — | — | — | yes | — |
| `agy`, `grok`, `mimo`, `opencode`, `qwen` | yes | — | — | — | — | — | — |
| `litellm`, an ACP harness | — | — | — | — | — | — | — |

**3.3.2** hmz MUST refuse, before its first turn, a role whose declared type requires a
capability that the harness filling it does not serve.

## 4. Agent specs, models and efforts

### 4.1 Agent specs

**4.1.1** hmz MUST read an agent spec, and an `-a` item, as `api/cli.md` §7.4 states.

**4.1.2** An absent `<account>` MUST mean the harness machine's own sign-in of that harness, as
`features/accounts.md` defines it.

**4.1.3** An absent `<effort>`, an empty `<effort>`, and the effort `auto` MUST each mean that no
effort is said to the harness.

**4.1.4** An agent spec naming an account that does not exist MUST be refused as
`features/accounts.md` §3.2.2 states.

**4.1.5** An effort not on the harness's ladder for that model MUST be refused before the epic
starts where the agent spec is given to start the epic (`api/cli.md` §7.7 for `-a`), and
otherwise before the agent's first turn with `HarnessUnrecoverable` naming the agent spec and the
reason.

**4.1.6** A setting the harness cannot express MUST be refused before the agent's first turn with
`HarnessUnrecoverable` naming the agent spec and the reason.

### 4.2 Models

**4.2.1** hmz MUST pass the model to the harness in the harness's own spelling and MUST NOT
translate it, except as §4.2.2, §13 and `features/accounts.md` state for gateway accounts.

**4.2.2** For `cursor-agent`, hmz MUST pass the model with the effort and the service tier
written into the model id as `<model>-<effort>[-fast]`, where that id appears in the account's
model catalogue; a model id that already carries an effort MUST be passed unchanged.

**4.2.3** For an ACP harness, the model MUST be `as configured`, and hmz MUST say no model to the
harness.

**4.2.4** hmz MUST keep, per harness kind and per account, a catalogue of the models the account
runs and the efforts each takes, as `features/accounts.md` states.

**4.2.5** Where Claude Code reports that it runs a model other than the one asked for, and the
model asked for is neither a Claude Code alias nor a dated form of the model reported, hmz MUST
emit one notice per session naming both models, and MUST let the turn continue.

### 4.3 Efforts

**4.3.1** Each harness kind MUST accept exactly the following effort ladder, hardest first, and
`auto`:

| Kind | Effort ladder |
| --- | --- |
| `agy` | `high`, `medium`, `low` |
| `claude` | `ultracode`, `max`, `xhigh`, `high`, `medium`, `low` |
| `codex` | `ultra`, `max`, `xhigh`, `high`, `medium`, `low` |
| `cursor-agent` | `max`, `xhigh`, `extra-high`, `high`, `medium`, `low`, `minimal`, `none` |
| `dsh` | `max`, `high`, `low`, `off` |
| `grok` | `xhigh`, `high`, `medium`, `low` |
| `kimi` | `max`, `high`, `medium`, `low`, and each prefixed with `swarm` |
| `litellm` | `high`, `medium`, `low`, `minimal`, `none` |
| `mcode` | `max`, `xhigh`, `high`, `medium`, `low` |
| `mimo`, `opencode` | `xhigh`, `high`, `medium`, `low`, `minimal` |
| `omp`, `pi` | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| `qwen` | `max`, `xhigh`, `high`, `medium`, `low`, `none` |
| an ACP harness | `as configured` |

**4.3.2** A model's ladder MUST be the harness's ladder narrowed to the efforts the account's
model catalogue lists for that model, in ladder order, and MUST be the whole ladder where the
catalogue lists none.

**4.3.3** The `claude` effort `ultracode` MUST be accepted and MUST NOT be listed in a model's
ladder; it MUST run as `xhigh` with Claude Code opted into orchestrating a fleet of subagents.

**4.3.4** The `omp` effort `off` MUST remain on every model's ladder whatever the catalogue
lists.

**4.3.5** A `kimi` effort prefixed with `swarm` MUST run at the unprefixed effort as a fleet of
subagents.

**4.3.6** An ACP harness MUST accept every effort and MUST be told none.

**4.3.7** A change of effort made while a turn runs MUST take effect from the session's next turn
and MUST NOT change the effort of the running turn.

**4.3.8** A changed effort MUST be checked against the model's ladder as a configured effort is.

### 4.4 Service tier

**4.4.1** An agent MUST be permitted the service tier `default` or `fast`.

**4.4.2** The tier `fast` MUST be served by `claude` (Claude Code's fast mode), `codex` (the
`priority` tier) and `cursor-agent` (the `-fast` model id the account lists), and MUST be refused
on every other harness kind and on `cursor-agent` where the account lists no `-fast` id.

## 5. Configuration levels

### 5.1 Levels

**5.1.1** hmz MUST launch every harness with its configuration drawn from three levels: the
system level, the user level and the project level.

**5.1.2** hmz MUST NOT replace, override, write or hide the system level of any harness.

**5.1.3** The user level MUST be the harness machine's user configuration of the harness, merged
at launch with the agent's managed items.

**5.1.4** Where a managed item and an item of the user's configuration have the same name, the
managed item MUST take effect for that launch.

**5.1.5** The project level MUST be the env's workspace, read by the harness as the harness reads
a workspace when the user runs it by hand.

**5.1.6** hmz MUST NOT place any managed item into the workspace.

**5.1.7** hmz MUST NOT switch on or off any skill, subagent, command, hook or tool server that the
user configured for the harness.

**5.1.8** Program-running configuration in the workspace MUST be honoured or refused as
`features/placements.md` §7 states.

**5.1.9** No permission field governs whether workspace configuration is honoured; a grant MUST
NOT be read as such a field.

### 5.2 Virtual config home

**5.2.1** The following harnesses rewrite their own configuration while running, and each MUST be
launched with a virtual config home (`api/files/harness-homes.md` §2.5): `claude` (which rewrites
`.claude.json`), `codex` (which records project trust in `config.toml`) and `qwen` (which migrates
its settings).

**5.2.2** The following harnesses offer no flag or environment variable through which hmz can add
user-level configuration, and each MUST be launched with a virtual config home wherever hmz adds
a managed item to it: `grok`, `pi`, `omp`, `mcode`, `agy`, `cursor-agent` and `kimi`.

**5.2.3** hmz MUST build a virtual config home on the harness machine, for one harness process,
from the user's configuration of that harness on that machine merged with the agent's managed
items, before that process starts.

**5.2.4** Two harness processes MUST NOT share one virtual config home.

**5.2.5** Every change the harness makes to a configuration file copied into its virtual config
home MUST be discarded when the process exits.

**5.2.6** Every other write the harness makes inside its virtual config home MUST reach the real
harness home (`api/files/harness-homes.md` §6.8), except the session records kept in an epic as
`api/files/harness-homes.md` §5 states.

**5.2.7** Where the harness replaces an entry that its virtual config home links to the real
harness home, other than a configuration file copied under §5.2.5, hmz MUST write the
replacement to the entry the link named, or to the account's file where the agent runs as an
account, when the process exits, unless that entry is at least as new as the replacement.

**5.2.8** hmz MUST NOT write any file of the user's real configuration of a harness, on any
machine, in building, using or discarding a virtual config home.

**5.2.9** Credential files read through a virtual config home MUST be the user's real credential
files, or the account's files where the agent runs as an account, and MUST NOT be copied into it,
so that a credential the harness refreshes during the process persists after it exits.

**5.2.10** A change the user makes to the real configuration while a harness process runs MUST
take effect no later than that harness's next launch.

### 5.3 Managed items through flags and environment

**5.3.1** The following harnesses neither rewrite their configuration nor need a virtual config
home, and each MUST receive its managed items through command-line flags or environment
variables at launch: `opencode`, `mimo`, `dsh` and every ACP harness.

**5.3.2** A harness listed in §5.3.1 MUST be launched with its configuration home as the user
left it.

**5.3.3** A managed item that a harness has no means of receiving at the user level MUST NOT be
delivered to it by any other means, and a flow skill that cannot be delivered MUST be omitted
from that harness's sessions without failing the turn.

**5.3.4** `litellm` MUST read no configuration home and MUST receive no managed item.

### 5.4 Flow skills

**5.4.1** A session MUST carry every skill the flow brings for its role unless the flow selects a
subset for that session, in which case it MUST carry exactly that subset.

**5.4.2** A skill name the flow selects that the flow does not bring MUST be ignored and MUST NOT
be refused.

**5.4.3** A change of the skills a session carries MUST take effect from the session's next turn.

**5.4.4** Where a skill the user configured and a flow skill have the same name, the workspace's
skill of that name MUST take precedence over both, and the flow skill MUST take precedence over
the user's.

### 5.5 Program-running configuration

**5.5.1** For each harness, program-running configuration MUST be exactly the entries
of the table below: a file, at the path given relative to the session directory or any directory
above it up to the workspace, holding a non-empty value at any of the key paths given, where `*`
stands for any one key of a table or any one item of a list; or a directory, written with a
trailing `/`, holding any entry.

**5.5.2** A file of the table that hmz cannot read or cannot parse MUST count as holding
program-running configuration.

**5.5.3** The harnesses `dsh` and `litellm` MUST have no program-running configuration.

| Harness | Path | Key paths |
| --- | --- | --- |
| `agy` | `.agents/mcp_config.json` | `mcpServers.*.command` |
| `agy` | `.agents/hooks.json` | `*.*.*.hooks.*.command` |
| `agy` | `.agents/plugins/` | any entry |
| `claude` | `.claude/settings.json` | `hooks.*.*.hooks.*.command`, `statusLine`, `subagentStatusLine`, `fileSuggestion`, `apiKeyHelper`, `awsAuthRefresh`, `awsCredentialExport`, `gcpAuthRefresh`, `otelHeadersHelper`, `enabledPlugins.*`, `extraKnownMarketplaces` |
| `claude` | `.claude/settings.local.json` | `hooks.*.*.hooks.*.command`, `statusLine`, `subagentStatusLine`, `fileSuggestion`, `apiKeyHelper`, `awsAuthRefresh`, `awsCredentialExport`, `gcpAuthRefresh`, `otelHeadersHelper`, `enabledPlugins.*`, `extraKnownMarketplaces` |
| `claude` | `.mcp.json` | `mcpServers.*.command`, `mcpServers.*.headersHelper` |
| `codex` | `.codex/config.toml` | `mcp_servers.*.command`, `mcp_servers.*.http_headers_helper`, `hooks` |
| `codex` | `.codex/hooks.json` | `hooks.*.*.hooks.*.command` |
| `cursor-agent` | `.cursor/hooks.json` | `hooks.*.*.command` |
| `cursor-agent` | `.cursor/mcp.json` | `mcpServers.*.command` |
| `grok` | `.grok/config.toml` | `mcp_servers.*.command`, `plugins` |
| `grok` | `.grok/hooks/` | any entry |
| `grok` | `.claude/settings.json` | `hooks.*.*.hooks.*.command` |
| `grok` | `.claude/settings.local.json` | `hooks.*.*.hooks.*.command` |
| `kimi` | `.kimi-code/mcp.json` | `mcpServers.*.command` |
| `mcode` | `.mcp.json` | `mcpServers.*.command`, `mcpServers.*.headersHelper` |
| `mimo` | `mimocode.json` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `mimo` | `mimocode.jsonc` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `mimo` | `.mimocode/mimocode.json` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `mimo` | `.mimocode/mimocode.jsonc` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `mimo` | `.mimocode/plugins/` | any entry |
| `mimo` | `.mimocode/plugin/` | any entry |
| `omp` | `.omp/settings.json` | `extensions` |
| `omp` | `.omp/config.yml` | `extensions` |
| `omp` | `.omp/mcp.json` | `mcpServers.*.command` |
| `omp` | `.omp/.mcp.json` | `mcpServers.*.command` |
| `omp` | `mcp.json` | `mcpServers.*.command` |
| `omp` | `.mcp.json` | `mcpServers.*.command`, `mcpServers.*.headersHelper` |
| `omp` | `.omp/hooks/` | any entry |
| `omp` | `.omp/tools/` | any entry |
| `omp` | `.claude/hooks/` | any entry |
| `omp` | `.claude/tools/` | any entry |
| `omp` | `.codex/hooks/` | any entry |
| `omp` | `.codex/tools/` | any entry |
| `omp` | `.gemini/hooks/` | any entry |
| `omp` | `.gemini/tools/` | any entry |
| `omp` | `.omp/extensions/` | any entry |
| `opencode` | `opencode.json` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `opencode` | `opencode.jsonc` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `opencode` | `.opencode/opencode.json` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `opencode` | `.opencode/opencode.jsonc` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `opencode` | `.opencode/plugins/` | any entry |
| `opencode` | `.opencode/plugin/` | any entry |
| `pi` | `.pi/settings.json` | `extensions`, `packages`, `npmCommand` |
| `pi` | `.pi/mcp.json` | `mcpServers.*.command` |
| `pi` | `.pi/extensions/` | any entry |
| `qwen` | `.qwen/settings.json` | `hooks.*.*.hooks.*.command`, `mcpServers.*.command`, `tools.discoveryCommand`, `tools.callCommand`, `ui.statusLine.command` |

## 6. Permissions and confinement

### 6.1 Approvals

**6.1.1** hmz MUST NOT put any action of an agent to any person or model for approval, except
where a flow hangs a permission-request hook (§9.3) or an ask-user hook (§9.4).

**6.1.2** What limits an agent MUST be its grant and the hooks its flow hangs.

### 6.2 Rungs

**6.2.1** hmz MUST derive a rung from a role's grant as follows: `local` of `NONE` or `READ` gives
`read-only`; `local` of `ALL` gives `bypass`.

**6.2.2** On `kimi`, a rung other than `read-only` MUST become `auto` while a permission-request
hook or an ask-user hook is hung on the agent.

**6.2.3** A rung a harness does not accept MUST become `bypass`; `dsh` and every ACP harness
accept only `bypass`, and `mcode` does not accept `read-only`.

**6.2.4** Each rung MUST launch each harness as the following table states:

| Kind | `read-only` | `workspace-write` | `auto` | `bypass` |
| --- | --- | --- | --- | --- |
| `agy` | plan mode, read tools only | accept-edits mode | skip permissions | skip permissions |
| `claude` | `plan` | `acceptEdits` | `auto` | `bypassPermissions` |
| `codex` | sandbox `read-only` | sandbox `workspace-write` | `on-request` | `danger-full-access` |
| `cursor-agent` | `--mode plan` | sandbox on | `--auto-review` | sandbox off |
| `grok` | read tools only | web search off | every tool | every tool |
| `kimi` | `manual`, plan mode | `auto` | `yolo` | `auto` |
| `mcode` | refused | `full` | `smart` | `full` |
| `mimo`, `opencode` | edit, bash denied | web tools denied | nothing denied | nothing denied |
| `omp` | every approval denied | `yolo` | `yolo` | `yolo` |
| `pi` | write tools withheld | nothing withheld | nothing withheld | nothing withheld |
| `qwen` | write tools withheld | `web_fetch` withheld | nothing withheld | nothing withheld |
| `dsh`, ACP | refused | refused | refused | every request granted |
| `litellm` | nothing said | nothing said | nothing said | nothing said |

**6.2.5** Where Claude Code refuses `bypassPermissions` for the account or because it runs as
root, hmz MUST run that agent at `acceptEdits` with every request granted, and MUST say so once
per agent.

**6.2.6** Where Codex refuses `danger-full-access` on the harness machine, hmz MUST run that agent
at `auto` with every request granted, and MUST say so once per agent.

**6.2.7** Codex's approval policy MUST be `never` at every rung but `auto`.

**6.2.8** hmz MUST NOT write a rung into any configuration file of the user.

### 6.3 Web search

**6.3.1** A grant whose `online` is `ALL` MUST switch the harness's own web search on, and one
whose `online` is `NONE` MUST switch it off, on every harness that can be told.

**6.3.2** `cursor-agent`, `mcode`, `omp`, `pi` and every ACP harness cannot be told, and on them
hmz MUST say nothing of web search.

**6.3.3** Switching web search off MUST NOT be read as cutting the network; only confinement
(§6.4) cuts it.

### 6.4 Confinement

**6.4.1** hmz MUST confine every harness except `litellm`, and every process the harness starts,
to the grant of its role.

**6.4.2** Confinement MUST permit reading what any program needs to start (system programs,
libraries, certificates and name-resolution files), and writing the device files, the harness's
own configuration and sign-in files, the agent's session records, and a temporary directory of
the agent's own.

**6.4.3** A `local` of `ALL` MUST also permit writing `/tmp`, `/var/tmp` and the directory
`TMPDIR` names.

**6.4.4** A `user` of `ALL` MUST permit writing whatever the user's file permissions permit, and
for the root user MUST permit writing the home directory, the temporary directories and
`/run/user/0`.

**6.4.5** A grant whose `online` is `NONE` MUST cut the network for the harness and its
processes, except connections to the hosts the harness and its account need to reach its model
and its sign-in, which MUST pass through a proxy on loopback.

**6.4.6** On Linux, confinement MUST require Landlock (kernel 5.13 or later, enabled), and
confinement that cuts the network MUST additionally require Landlock ABI 4 (kernel 6.7 or later)
and seccomp user notification; where either is absent, the session MUST be refused with
`HarnessSandboxed` naming the requirement.

**6.4.7** On macOS, confinement MUST use the Seatbelt sandbox, and where hmz itself runs inside a
sandbox that prevents applying one, the session MUST be refused with `HarnessSandboxed`.

**6.4.8** A grant whose `online` is `NONE` MUST be refused with `HarnessSandboxed` for
`cursor-agent` and for `mcode`, whose web search runs on their vendors' servers through the same
hosts as their models.

**6.4.9** A grant whose `online` is `NONE` MUST be refused with `HarnessSandboxed` for an ACP
harness that declares no hosts, and the message MUST name what to declare.

**6.4.10** A rung's own sandbox inside a harness MUST NOT be relied on to hold the grant;
confinement MUST hold the grant whatever the harness enforces.

**6.4.11** A turn kept off a host by confinement MUST fail with the fault class `fenced`.

## 7. Sessions and turns

### 7.1 Sessions

**7.1.1** A session MUST take one turn at a time; turns asked of one session concurrently MUST
run one after the other.

**7.1.2** A session MUST open its conversation with the harness on its first turn and MUST resume
that conversation by the harness's own session id on every later turn.

**7.1.3** A session whose first turn failed MUST remain unopened, and its next turn MUST open a
new conversation.

**7.1.4** Every turn MUST end in exactly one answer or exactly one failure.

**7.1.5** A session MUST run every turn in the directory it was opened in, and a directory that
does not exist MUST be refused before the turn.

**7.1.6** Where hmz restarts a harness process between turns of one session, the session MUST
continue the same conversation by its id, except on `dsh`, which cannot resume: a `dsh` session
that has taken a turn and would need a new process MUST refuse that turn with
`HarnessUnrecoverable`.

### 7.2 Schemas

**7.2.1** A turn asked for an answer in a schema MUST answer with an object of that schema or
fail with `OutputSchemaError`.

**7.2.2** `claude`, `agy`, `grok`, `qwen`, `mcode`, `codex` and `litellm` MUST be held to the
schema by the harness itself; every other harness MUST be asked for the schema in the prompt and
its answer validated afterwards.

**7.2.3** The schema MUST NOT appear in what hooks and watchers are shown of the prompt.

### 7.3 Forks

**7.3.1** The following harnesses MUST fork a conversation: `claude`, `codex`, `kimi`, `grok`,
`opencode`, `mimo`, `pi`, `omp`, `qwen`, and an ACP harness that advertises forking.

**7.3.2** `claude`, `codex` and `kimi` MUST additionally fork a conversation into another
directory of the same machine.

**7.3.3** Forking on `agy`, `cursor-agent`, `dsh`, `mcode`, `litellm` and an ACP harness that
does not advertise it MUST be refused with `UnsupportedOperation`.

**7.3.4** A fork MUST carry the conversation's history as of the fork, its effort, its skills and
its fake tools, and MUST have a session id of its own.

**7.3.5** Forking a session that has not taken a turn MUST be refused.

**7.3.6** A fork onto another machine MUST be refused with `UnsupportedOperation`.

### 7.4 Interrupting

**7.4.1** Interrupting a turn MUST end that turn and every process it started, and MUST leave the
conversation able to take the next turn.

**7.4.2** An interrupted turn MUST still end in exactly one answer, carrying what the agent had
said before the interruption.

**7.4.3** An interrupted turn MUST NOT be retried.

### 7.5 Steering

**7.5.1** Steering MUST put the user's or flow's words into the turn already running, and MUST NOT
queue them as another turn.

**7.5.2** `claude`, `codex`, `kimi`, `pi` and `omp` MUST serve steering; every other harness MUST
refuse it with `UnsupportedOperation`.

**7.5.3** Steering a session with no turn running MUST be refused with `SessionError`, except on
`claude`, `pi` and `omp` while their process is up.

**7.5.4** hmz MUST report when steered words reach the model.

### 7.6 Goals

**7.6.1** A turn whose prompt is `/goal <objective>` MUST run the harness's own goal feature,
continuing until the agent judges the objective met, and MUST answer with the last turn's answer.

**7.6.2** `claude`, `codex`, `kimi` and `dsh` MUST serve goals; every other harness MUST refuse
`/goal` and MUST NOT emulate a goal in the prompt.

**7.6.3** A per-turn budget and an interruption MUST NOT end a goal; stopping the agent MUST end
it.

### 7.7 Loops

**7.7.1** A prompt `/loop <interval> <task>` MUST be passed to `claude` unchanged, and `claude`
alone MUST serve it.

### 7.8 Per-turn budgets

**7.8.1** A per-turn budget MUST cap the output tokens and the wall-clock seconds of one turn,
and a cap of zero MUST cap nothing.

**7.8.2** A cap of seconds MUST take effect whether or not the harness is producing output.

**7.8.3** On `agy`, `grok`, `qwen` and every ACP harness, which report usage only when a turn
ends, a cap of output tokens MUST NOT take effect mid-turn.

**7.8.4** A turn ended by its budget MUST keep its changes and MUST NOT be retried.

**7.8.5** A budget's cut-off MUST prevail over a stop hook that would send the agent on.

## 8. Usage and cost

### 8.1 Token usage

**8.1.1** hmz MUST count the tokens of every turn in the kinds `input`, `output`, `cache_read`,
`cache_write` and `reasoning`, omitting a kind the harness does not report.

**8.1.2** An ACP harness reports no usage, and hmz MUST count none for it.

**8.1.3** hmz MUST count each model request once, including where the harness's log repeats one
request's usage across several records.

**8.1.4** Where hmz reads usage both from the harness's answers and from its logs, the figure
shown per model MUST be the higher of the two and MUST NOT be their sum.

**8.1.5** Usage of a conversation carried on from an earlier epic or forked from another session
MUST count only records made after the current epic opened that session.

### 8.2 Prices and cost

**8.2.1** hmz MUST price usage per model and per token kind from the price list at
`https://openllmprices.com/data/prices.json`, cached on this machine and refreshed when older than
24 hours.

**8.2.2** The environment variable `HUMANIZE_PRICES` MUST, where set to a URL or a path, replace
that source, and MUST, where set to `off`, `0`, `no`, `none` or the empty string, disable
fetching.

**8.2.3** Pricing MUST read only the cached list and MUST NOT wait on the network.

**8.2.4** A model the price list does not name exactly MUST be priced as unknown and MUST NOT be
priced at zero.

**8.2.5** A cost that includes any unpriced model MUST be shown as a lower bound.

**8.2.6** A failed fetch MUST leave the cached list unchanged.

## 9. Hooks

### 9.1 Moments

**9.1.1** Every harness except the human agent MUST serve the hooks session start, prompt
submit, pre-tool-use, notification, stop and session end.

**9.1.2** On `litellm`, which reaches for no tool, the pre-tool-use hook MUST never fire.

**9.1.3** The permission-request hook MUST be served by `claude`, `codex`, `kimi` and `grok`, and
by no other harness.

**9.1.4** The subagent start and subagent stop hooks MUST be served by `claude`, `codex`,
`cursor-agent` and `mcode`, and by no other harness.

**9.1.5** The ask-user hook MUST be served by `claude`, `codex`, `kimi`, `pi` and `omp`, and by no
other harness.

**9.1.6** The human agent MUST serve no hook.

**9.1.7** Hanging a hook on a moment the harness does not serve MUST be refused before the
agent's first turn.

### 9.2 Pre-tool-use

**9.2.1** On `claude` and `qwen`, a pre-tool-use hook that refuses MUST prevent the tool from
running.

**9.2.2** On every other harness, the pre-tool-use hook MUST be told of the tool after the
harness announced it, and its refusal MUST NOT prevent the tool from running.

**9.2.3** On `kimi`, `pi`, `qwen` and `mimo`, while a pre-tool-use hook is hung, hmz MUST also
report the programs the harness starts, the files it reads and writes, and the connections it
opens, as additional pre-tool-use occasions that cannot be refused.

**9.2.4** The reports of §9.2.3 MUST NOT be made for a harness running on a machine other than
this machine.

### 9.3 Permission requests

**9.3.1** A permission request that no hook refuses MUST be granted, except on `claude` at
`read-only`, on `codex` and `grok` with no rung said, and on `kimi` at `read-only` or with no
rung said, where it MUST be denied.

**9.3.2** A hook MUST be able to turn a grant into a denial and MUST NOT be able to turn a denial
into a grant.

**9.3.3** While a permission-request hook is hung, `claude` at `bypass` MUST run in its manual
permission mode, so that every tool that changes something reaches the hook, and `codex` MUST run
with the approval policy `untrusted`; each MUST take effect from the session's next turn.

### 9.4 Questions

**9.4.1** Where the agent stops mid-turn to ask its user a question, hmz MUST deliver the question
to the role's ask-user hook where one is hung.

**9.4.2** Where no ask-user hook is hung, hmz MUST tell the harness that nobody answered.

**9.4.3** While an ask-user hook is hung on `codex`, Codex MUST be launched able to ask its user
outside plan mode.

### 9.5 Timing

**9.5.1** A hook other than the ask-user hook MUST be waited for at most 900 seconds, after which
the moment MUST proceed as though no hook were hung.

**9.5.2** The ask-user hook MUST be waited for without limit.

**9.5.3** A hook that raises MUST be treated as having said nothing.

## 10. Fake tools and fake command lines

### 10.1 Fake tools

**10.1.1** Fake tools MUST be offered only to `claude`, `codex`, `qwen`, `opencode`, `mimo`,
`agy`, `grok`, `pi`, `omp`, `dsh` and ACP harnesses, and offering them to any other harness MUST
be refused.

**10.1.2** hmz MUST serve fake tools through the hmz tool server, a managed item at the user
level (§5), and MUST NOT require the flow to run a server.

**10.1.3** A fake tool's return value MUST reach the agent as text, and a fake tool that raises
MUST reach the agent as a failed tool call.

**10.1.4** On `grok`, a turn that `grok` can take only in print mode (a schema, the first turn of
a fork, web search off, or a rung that withholds tools) MUST be refused with
`HarnessUnrecoverable` while any fake tool is offered.

**10.1.5** Fake tools MUST be refused to a harness running on a machine other than this machine,
except `omp`.

### 10.2 Fake command lines

**10.2.1** Fake command lines MUST be put first on the `PATH` of every process of an agent whose
harness has a shell, which is every harness except `litellm` and the human agent, and MUST be
refused to those two.

**10.2.2** A fake command line MUST answer `--help` and `<command> --help` with its help on
standard output and exit status 0.

**10.2.3** A fake command line given arguments its command's options refuse MUST print the usage
and the error on standard error and exit with status 2.

**10.2.4** A fake command whose handler returns text MUST print it followed by a newline and exit
with status 0; one that returns nothing MUST print nothing and exit with status 0; one that
returns any other value MUST print it as indented JSON and exit with status 0.

**10.2.5** A fake command whose handler raises `SystemExit(n)` MUST exit with `n`; one whose
handler raises any other exception MUST print `NAME: <type>: <message>` on standard error and
exit with status 1.

**10.2.6** A fake command line run after the flow withdrew it MUST print
`NAME: command not found` on standard error and exit with status 127.

**10.2.7** Fake command lines MUST be refused to a harness running on a machine other than this
machine.

## 11. Failures, retries and fallbacks

### 11.1 Fault classes

**11.1.1** hmz MUST classify a failed turn by what the harness wrote on its output streams, and
for `agy` also by its log, reading the harness's own signs first and the shared signs after, in
the order of the following table, the first match deciding:

| Order | Fault class | Signs |
| --- | --- | --- |
| 1 | `unmirrored` | hmz could not keep this machine's copy of the work at its path |
| 2 | `fenced` | confinement kept the harness off a host |
| 3 | `contended` | a local store is locked; a refreshing sign-in is in use the other way |
| 4 | `spent` | a quota or balance is used up |
| 5 | `throttled` | status 429 or 529, rate limit, resource exhausted, overloaded, usage limit |
| 6 | `sandboxed` | the harness could not start its own sandbox |
| 7 | `unlisted` | the account is not entitled to the model |
| 8 | `refused` | status 401 or 403, an invalid, expired or revoked credential, not signed in |
| 9 | `retired` | status 404, model not found, unknown model |
| 10 | `killed` | a signal, out of memory, a segmentation fault |
| 11 | `dropped` | a connection reset or refused, a broken pipe, status 502, 503 or 504, a timeout |

**11.1.2** A harness program that exits with status 126 or 127 MUST be classified `missing`.

**11.1.3** On `codex`, a response stream that broke before completion, reported as `stream
disconnected before completion` or `responseStreamDisconnected`, MUST be classified `dropped`,
unless the same output carries a sign of a class earlier in §11.1.1, which MUST prevail.

**11.1.4** A Codex stream that disconnected because of a content filter MUST NOT be classified
`dropped`.

**11.1.5** A turn that no retry can change (a context window exceeded, a session id the harness
will not resume, a budget cut-off configured to fail) MUST fail with `HarnessUnrecoverable` and
MUST NOT be retried or carried to a stand-in.

### 11.2 What the flow sees

**11.2.1** A turn that fails after its retries and fallbacks are exhausted MUST raise in the flow
the error the following table names for its fault class:

| Fault class | Error |
| --- | --- |
| `contended` | `HarnessContended` |
| `spent`, `throttled` | `HarnessThrottled` |
| `refused` | `HarnessRefused` |
| `unlisted`, `retired` | `ModelUnavailable` |
| `missing` | `HarnessNotInstalled` for exit status 127, `HarnessMissing` otherwise |
| `sandboxed` | `HarnessSandboxed` |
| `killed` | `HarnessKilled` |
| `dropped` | `HarnessDropped` |
| `fenced`, `unmirrored`, unclassified | `HarnessUnrecoverable` |

**11.2.2** The error's message MUST carry what the harness said and, for a classified failure,
the fault class and what the user can do about it.

### 11.3 Retries at one place

**11.3.1** A failed turn MUST first be retried at its own place, in the same session, before it
is carried to a stand-in.

**11.3.2** The number of retries at a place MUST be the larger of the place's configured retries
and the floor the fault class sets in the following table, except that a fault class marked
"none" MUST receive no retry whatever the place configures:

| Fault class | Floor | Shortest wait | Harness process restarted |
| --- | --- | --- | --- |
| `throttled`, `spent` | 1 | 30 seconds | no |
| `contended` | 3 | 1 second, constant | no |
| `dropped` | 1 | the place's | yes |
| `killed` | 1 | 1 second, constant | yes |
| `refused`, `unlisted`, `retired` | none | — | — |
| `missing`, `sandboxed`, `unmirrored`, `fenced` | none | — | — |
| unclassified | 0 | the place's | no |

**11.3.3** A place with no configured retries MUST have zero configured retries.

**11.3.4** The wait before each retry MUST be the longest of the place's policy wait, the fault
class's own wait and the fault class's shortest wait, each policy wait capped at 60 seconds.

**11.3.5** A place's retry policy MUST be one of `none`, `constant`, `linear`, `exponential`,
`exponential-jitter` and `fibonacci`, with a base of 1 second, and MUST be `exponential-jitter`
where the place names none.

**11.3.6** Where a place configures a timeout, a retry whose wait would end after that timeout,
counted from the turn's first attempt, MUST NOT be taken.

**11.3.7** A retry of a fault class marked "restarted" MUST end the harness process and resume
the same conversation by its id in a new process.

**11.3.8** hmz MUST report each retry, with its fault class, wait and attempt number, as a notice
to the flow's watchers, and on standard error where nothing watches.

### 11.4 Fallback chains

**11.4.1** Once a place has no retries left, the turn MUST be taken at the next place of the
fallback chain configured for the original place, in a new session, by a stand-in configured as
the original agent was (effort, grant, skills, fake tools), and its answer MUST be returned
through the original session.

**11.4.2** A place with no configured chain MUST have none, and nothing MUST be carried to a
stand-in by default.

**11.4.3** A stand-in MUST be retried as its own place's retries state, and MUST carry on along
the chain it was reached by and MUST NOT read a chain of its own place.

**11.4.4** A chain MUST NOT contain its own place, and MUST NOT contain one place twice.

**11.4.5** An account MUST NOT name another account to carry on under; another account of the
same harness MUST be reached only as a place on a chain.

**11.4.6** A setting that measured the original model MUST be dropped when a stand-in runs another
model, and a setting the stand-in's harness cannot express MUST make that place no stand-in.

**11.4.7** A stopped agent MUST NOT be carried to a stand-in.

**11.4.8** Stand-ins MUST spend from the same epic budget as the original agent.

## 12. Watchdog

### 12.1 Silence

**12.1.1** hmz MUST watch every turn for silence, restarting the watchdog window whenever the
harness produces any output.

**12.1.2** The watchdog window MUST be 900 seconds, and 360 seconds for `dsh`.

**12.1.3** The environment variable `HUMANIZE_WATCHDOG` MUST, where set to a positive number of
seconds, replace the window, MUST, where set to zero or less, disable the watchdog, and MUST be
ignored where it is not a number.

**12.1.4** The watchdog MUST be paused while the turn waits on a person: a permission request, a
question, or a hook that pauses.

**12.1.5** When a window expires, hmz MUST grant a harness process or descendant visibly consuming
CPU up to 4 further windows, and MUST grant none to a process that is suspended or defunct.

**12.1.6** When the granted windows are exhausted, hmz MUST, in order: interrupt the turn; then end
the harness process and its descendants, saying first where that ends other turns sharing the
process; then kill what remains.

**12.1.7** hmz MUST report each step of §12.1.6 as a notice naming the harness.

**12.1.8** A turn ended by the watchdog MUST fail as a classified failure is, and MUST be retried as
§11.3 states, in the same conversation.

## 13. LiteLLM

### 13.1 The `litellm` harness

**13.1.1** A turn of `litellm` MUST be one streamed chat completion over the session's history and
the prompt, made from this machine, with no tool, file system access or hook of its own.

**13.1.2** A `litellm` turn MUST take no env, and a turn given one MUST be refused with
`UnsupportedOperation`.

**13.1.3** A `litellm` agent with no account MUST read its credentials from this process's
environment; one with an account MUST be given the account's credentials on the call.

**13.1.4** A parameter the provider does not accept, an effort among them, MUST be dropped from
the call and MUST NOT fail the turn.

**13.1.5** A context window exceeded MUST fail with `HarnessUnrecoverable`.

### 13.2 The gateway

**13.2.1** Where LiteLLM and its proxy are installed, hmz MUST offer every harness that supports
it the accounts `litellm` has a way in for, through a gateway, as `features/accounts.md` §6.4
states.

**13.2.2** hmz MUST start the gateway on this machine's loopback interface the first time a turn
needs it, one per agent, and MUST start another for another account or once it has exited.

**13.2.3** The harness MUST be given the gateway's URL and the gateway's own key, and MUST NOT be
given any of the account's variables.

**13.2.4** The gateway's configuration and key MUST be kept in a file only the user can read,
MUST NOT appear on any command line, and MUST be removed with the gateway.

**13.2.5** hmz MUST stop the gateway, and every process it started, when the agent stops.

**13.2.6** A harness running on a machine other than this machine MUST be refused an account a
gateway holds, where the agent is configured.

**13.2.7** A failure to start the gateway MUST report the proxy's last output with every secret
removed.

## 14. ACP harnesses

### 14.1 Adding and driving

**14.1.1** The user MUST be able to add as a harness any command that speaks the Agent Client
Protocol, under the name of the program it runs, and hmz MUST record it under `clis` in
`settings.yaml`, as `api/settings.md` states.

**14.1.2** hmz MUST refuse to add a command whose program is a built-in harness under any alias, a
command that is empty, and a name other than the program's own.

**14.1.3** An added harness MUST be available in every workspace from the next prompt.

**14.1.4** hmz MUST say no model, effort or mode to an ACP harness.

**14.1.5** hmz MUST grant every permission request an ACP harness makes, subject to confinement.

**14.1.6** An ACP harness MUST NOT be steered, MUST serve no goal, and MUST report no usage.

**14.1.7** An ACP harness MUST continue a conversation by whichever of resuming and loading it
advertises, and MUST fork only where it advertises forking.

**14.1.8** The hosts an ACP harness declares MUST be reachable under a grant whose `online` is
`NONE`, and the state paths it declares MUST be writable whatever the grant's `user` scope.

## 15. The human agent

### 15.1 Answers

**15.1.1** The human agent MUST answer each turn with what the user types at the prompt.

**15.1.2** The human agent MUST run no model, MUST spend nothing, and MUST be outside every budget.

**15.1.3** Where a turn of the human agent asks for a schema, hmz MUST ask the user one question per
field, offering a field's literal values or `yes` and `no` for a boolean as options, and offering
`-` to take a field's default.

**15.1.4** A value the schema refuses MUST be asked again a bounded number of times.

**15.1.5** Where nobody is at the prompt, the human agent MUST answer with nothing rather than
leave a flow waiting.
