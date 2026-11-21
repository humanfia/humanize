---
title: Agent roles
description: Declare the agents a flow drives, ask for what each must be able to do, pin a role to one harness or a bare model, and narrow an agent for one job.
---

# Agent roles

A flow declares roles instead of naming coding agents or models. The person who runs the flow assigns an agent to each role. A role's type defines what the flow can do with that agent and which harnesses can fill it.

![A role type is checked against the agent given for it; the flow is handed an agent granted what the type declares, and derive narrows it](/diagrams/builder-agents-1.svg)

## Declare the roles

Subclass `AgentCollection` with one key per role. Type each role as `Agent` or a subclass that requests extra capabilities.

```python
# .hmz/flows/careful/__init__.py
from typing import NotRequired

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    Permission,
    flow,
)


class Coder(Agent, GoalCommandAgentMixin):
    """Pursues the task as a goal of its harness."""


class Agents(AgentCollection):
    coder: Coder
    reviewer: NotRequired[Agent]


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def careful(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder pursues the task; a reviewer, if given, reads the change."""
    coder, workspace = agents["coder"], envs["workspace"]
    said = await coder.run(f"/goal {task}", session=await coder.spawn(), env=workspace)
    reviewer = agents.get("reviewer")
    if reviewer is None:
        return said
    reader = reviewer.derive(permission=Permission(preset="read-only"))
    return await reader.run(
        "Review the change in this repository.",
        session=await reader.spawn(),
        env=workspace,
    )
```

`coder` is required; a run without an agent for it is refused before starting. `reviewer` is wrapped in `NotRequired[...]`, so you can omit it. When omitted, its key is missing from `agents`, so read it with `agents.get`. A role typed `Outworlder` represents the person; Humanize fills it automatically, and nobody can assign an agent to it (see [The person as an agent](/builder/outworlder)).

Run the flow with one `-a` flag per role:

```sh
hmz exec -f @local/careful -a coder=claude/claude-haiku-4-5 \
    -a reviewer=claude/claude-opus-4-1 -p budget.output_tokens=20000 \
    "Add a discount code to checkout"
```

![The command's output: the coder edits and tests and says the goal is met, then the reviewer reads the diff and answers](/shots/builder-agents-exec.svg)

*Each role takes its turn as the agent given for it.*

## Ask for a capability

Add a mixin to a role type for anything the flow does beyond `spawn`, `run`, `fork`, `derive` and the universal hooks.

| Mixin | Lets the flow |
| --- | --- |
| `GoalCommandAgentMixin` | `run` a prompt that starts with `/goal`. See [Goals](/builder/goals) |
| `LoopCommandAgentMixin` | `run` a prompt that starts with `/loop`. See [Goals](/builder/goals) |
| `SteeringAgentMixin` | call `steer` to say something into a running turn. See [Sessions and turns](/builder/turns) |
| `PermissionRequestHookAgentMixin` | call `on_permission_request`. See [Hooks](/builder/hooks) |
| `SubagentStartHookAgentMixin` | call `on_subagent_start` |
| `SubagentStopHookAgentMixin` | call `on_subagent_stop` |
| `AskUserHookAgentMixin` | call `on_ask_user` |
| `FakeToolAgentMixin` | set `_tools` on the role. See [Tools the agent can call](/builder/tools) |

Mixins enforce a contract on both sides. Only a harness that supports every mixin on a role can fill it; any other is refused before the run starts:

![The command refused: coder needs GoalCommandAgentMixin, which cursor-agent does not support](/shots/builder-agents-refused.svg)

The flow receives only the capabilities its role declares. Calling an undeclared capability raises `CapabilityNotGranted`, even if the underlying harness supports it. Here `Coder` is declared as `class Coder(Agent)` and still runs `/goal`:

![The command's output: CapabilityNotGranted, coder: /goal needs GoalCommandAgentMixin on the role](/shots/builder-agents-not-granted.svg)

## Check harness support

Each harness has its own role type and supports specific mixins. The first column shows the harness name passed to `-a`.

| Harness | Role type | Goal | Loop | Steering | Permission request | Subagent start and stop | Ask user | Fake tools |
| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `claude` | `ClaudeCodeAgent` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `codex` | `CodexAgent` | ✓ | | ✓ | ✓ | ✓ | ✓ | ✓ |
| `kimi` | `KimiCodeAgent` | ✓ | | ✓ | ✓ | | ✓ | |
| `pi` | `PiAgent` | | | ✓ | | | ✓ | ✓ |
| `omp` | `OhMyPiAgent` | | | ✓ | | | ✓ | ✓ |
| `dsh` | `DeepSeekHarnessAgent` | ✓ | | | | | | ✓ |
| `opencode` | `OpenCodeAgent` | | | | | | | ✓ |
| `mimo` | `MiMoCodeAgent` | | | | | | | ✓ |
| `qwen` | `QwenCodeAgent` | | | | | | | ✓ |
| `grok` | `GrokBuildAgent` | | | | | | | ✓ |
| `agy` | `AntigravityAgent` | | | | | | | ✓ |
| `cursor-agent` | `CursorAgent` | | | | | ✓ | | |
| `mcode` | `MiniMaxCodeAgent` | | | | | ✓ | | |
| `litellm` | `LiteLLMAgent` | | | | | | | |
| `acp` | `Agent` | | | | | | | |

`acp` represents any custom CLI added by a user; give it to `-a` by the name it was added under, not as `acp`. It supports no mixins and fills only plain `Agent` roles. See [Coding agents](/user/agents) for the products behind these names, and [Agents and harnesses](/reference/agents) for the full matrix.

## Pin a role to one harness

Type a role with a specific harness class to require that harness and grant all its mixins:

```python
from hmz.flows import ClaudeCodeAgent, Permission


class Coder(ClaudeCodeAgent):
    _permission = Permission(network=False)
```

Passing any other harness for this role is refused before the run starts. In a subflow, a mismatch raises `HarnessMismatch` (see [Call another flow](/builder/calling-flows)).

Prefer `Agent` with mixins so any compatible harness can fill the role. `HARNESS_AGENTS` maps each `HarnessKind` to its role type.

## Configure role defaults

Set four class variables on a role type to configure its sessions.

| Class variable | Default | Sets |
| --- | --- | --- |
| `_permission` | `Permission()`: change the working directory, read the rest of the machine, use the network | What the agent may touch. See [Skills and permissions](/builder/skills) |
| `_skills` | `()` | The skills its sessions are given. See [Skills and permissions](/builder/skills) |
| `_tools` | `()` | Functions of the flow offered as tools. Needs `FakeToolAgentMixin` |
| `_clis` | `()` | Command lines of the flow put on the agent's `PATH`. Needs no mixin. Not for `litellm` |

## Inspect the assigned agent

Read these properties on an agent to see what fills its role:

| Property | Value |
| --- | --- |
| `role` | The role's key in the `AgentCollection` |
| `harness` | A `HarnessKind`, such as `HarnessKind.CLAUDE`. Its value is the `-a` name |
| `model` | The model, as it was given |
| `effort` | The effort in the harness's own words. `""` when none was given or it was `auto` |
| `provider` | The account its turns run as. `""` for the sign-in the CLI already has |

## Use a bare model

Type a role as `LiteLLMAgent`, or pass `-a judge=litellm/MODEL` to a plain `Agent` role, to call a model directly. Each turn runs one chat completion over the session history without a CLI, tools, shell, or files. Use this for roles that only judge text.

```python
class Agents(AgentCollection):
    coder: Agent
    judge: LiteLLMAgent


# In the flow function:
judge = agents["judge"]
verdict = await judge.run(
    f"Does this summary say the task is done?\n\n{said}",
    session=await judge.spawn(),
)
```

Omit `env` on its turns; passing an environment raises `UnsupportedOperation`. The person running the flow must install the LiteLLM extra (see [Gateways, LiteLLM and custom CLIs](/user/gateways)).

## Narrow an agent

Call `derive` to return a copy of the agent with narrower permissions, fewer skills, or both. The original agent is unchanged.

```python
reader = coder.derive(permission=Permission(preset="read-only"), skills=())
```

Pass `permission=None` to keep the current permission, and `skills=None` to keep all current skills. Requesting more than the agent was granted raises `CapabilityNotGranted`, because `derive` never widens access. Passing a `permission` that is not a `Permission` instance raises `TypeError`.

The derived agent shares sessions and hooks with the original, and retains the role's tools and command lines. A session spawned by one can take turns with the other.

## Assign roles when running a flow

### In the app

Open **New epic** to see one row per role under **Agents**. Optional roles are marked **Optional**. Each row lists only the harnesses that can fill the role. See [Start an epic](/user/epics).

![Humanize Desktop's New epic page for @local/careful: under Agents, a row for coder and a row for reviewer marked Optional](/shots/builder-agents-app.svg)

### In the terminal

Run `/flow careful` to open the flow setup with one row per role.

![The terminal interface's setup of careful: rows for coder and reviewer, each an agent, then budget and the rest](/shots/builder-agents-tui.svg)

### From the command line

Pass one `-a ROLE=CLI/MODEL:EFFORT` flag per role. Omitting a required role refuses the run: `@local/careful needs an agent for 'coder'`.

## Good to know

- A role type cannot inherit from two harnesses, `Outworlder` accepts no harness or mixin, and setting `_tools` requires `FakeToolAgentMixin`. Violating any of these raises `FlowDefinitionError` when Humanize loads the flow.
- A `grok` agent on a role with `_tools` raises `HarnessUnrecoverable` on turns with `output_schema`, on the first turn of a fork, when `network=False`, or when its permission lets it write nowhere.
- A `litellm` agent is refused for any role that sets `_clis` because it has no shell.
- In tests, `run_fake` fills any unassigned required role with a scripted agent matching the requested harness, defaulting to Claude Code. Unassigned optional roles remain omitted. See [Test a flow](/builder/testing).
