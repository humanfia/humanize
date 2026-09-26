<script setup>
import RoleFit from '../.vitepress/theme/components/weaver-asking/RoleFit.vue'
</script>

# Hooks

A **hook** is an async function you hang on one **moment** of an agent's sessions, such as a
tool about to run, a prompt about to go, or a turn about to end. Reach for one to watch an
agent, refuse something it reaches for, add to what it is told, or keep it from stopping.

## Try it

The gentlest hook only looks. This Ralph loop prints every tool its agent reaches for:

```python
# .humanize/flows/watched/__init__.py
"""A Ralph loop that says what its agent reached for."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    PreToolUseHookParams,
    PreToolUseHookResult,
    flow,
)


class Agents(AgentCollection):
    agent: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


async def seen(params: PreToolUseHookParams) -> PreToolUseHookResult:  # [!code highlight]
    print(f"  → {params.tool}: {str(dict(params.input))[:60]}")  # [!code highlight]
    return PreToolUseHookResult()  # an empty result changes nothing [!code highlight]


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def watched(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    agent = agents["agent"]
    agent.on_pre_tool_use(seen)  # [!code highlight]
    for _ in range(5):
        session = await agent.spawn(env=envs["workspace"])
        await agent.run(task, session=session)
```

```sh
hmz exec -f watched -a agent=claude/claude-opus-5:high -b cost=10 \
    "$(cat TASK.md)"
```

Each tool call prints a line with the tool's name, as the CLI names it, and the start of what
it was called with:

```text
  → Read: {'file_path': '/work/app/TASK.md'}
  → Bash: {'command': 'pytest -q tests/test_parse.py', 'description':
  → Edit: {'file_path': '/work/app/src/parse.py', 'old_string': 'def p
```

A flow's `print` lands in the run's transcript, so this is also how a flow says something.

## Hang, replace, take down

Each moment has one method, named `on_` and the moment. It takes the hook, or `None`:

```python
agent.on_stop(keep_going)        # hung
agent.on_stop(other)             # replaced: one hook per moment per agent
agent.on_stop(None)              # taken down
```

A hook is hung on the **agent**, so it covers every session that agent opens, including the
fresh one a Ralph loop opens each round. An agent `derive`d from it shares its hooks. A flow
you call is handed an agent of its own, so its hooks and yours never hear each other's
sessions.

Hanging one mid-run is fine: it hears every moment after that, in the turn under way too.

## The moments

Six moments are on every agent, because every CLI reaches them:

| Method | When | Told | What the result does |
| --- | --- | --- | --- |
| `on_session_start` | a session is about to take its first turn | — | `context` goes in front of the first prompt |
| `on_user_prompt_submit` | a prompt is about to go to the agent | `prompt` | `context` is added to it; `block` refuses it, and `run` raises `SessionError` saying `reason` |
| `on_pre_tool_use` | the agent has reached for a tool that has not run yet | `tool`, `input` | `block` refuses it and tells the agent `reason`, [on the CLIs that wait](#stopping-a-tool) |
| `on_notification` | the agent has stopped to tell its user something | `message` | nothing: it is heard, not answered |
| `on_stop` | a turn is about to end | `said`, `again` | `block` keeps the agent going, with `reason` as its next prompt |
| `on_session_end` | a session is being closed | — | nothing |

Four more reach only some CLIs, so each is on a role that [declares the
mixin](#declaring-a-mixin) named after it: `PermissionRequestHookAgentMixin` for
`on_permission_request`, and so on.

| Method | When | Told | What the result does |
| --- | --- | --- | --- |
| `on_permission_request` | the CLI asks whether a tool may run | `tool`, `input` | `allow=False` refuses it and tells the agent `reason` |
| `on_subagent_start` | the agent has started a subagent of its own | `subagent`, `task` | nothing: no CLI waits on it |
| `on_subagent_stop` | one of those is about to finish | `subagent`, `said` | nothing: no CLI waits on it |
| `on_ask_user` | the agent has stopped mid-turn to ask its user a question | `question`, `options` | `answer` is what it is told; `None` lets it carry on without one |

An outworlder made with `Outworlder.new()` has one more, `on_outworlder_run`, which answers for
it. See [The person as an agent](/weaver/human-agent#stand-in-for-the-person).

Each moment has its own params and result class in `hmz.flows`, named after it:
`StopHookParams` and `StopHookResult`, `PreToolUseHookParams` and `PreToolUseHookResult`, and
so on. Every params also carries `ctx`, the [context](/reference/flows#the-context) of the flow
the agent belongs to, and `session`, the session the moment arrived in. A hook hung on the
wrong moment is a type error.

## Add to a prompt

```python
from hmz.flows import UserPromptSubmitHookParams, UserPromptSubmitHookResult


async def remind(
    params: UserPromptSubmitHookParams,
) -> UserPromptSubmitHookResult:
    return UserPromptSubmitHookResult(
        context="Run the tests before you say you are done."  # [!code highlight]
    )


builder.on_user_prompt_submit(remind)
```

## Keep a turn going

An `on_stop` hook that blocks keeps the turn open until it lets go. `params.again` counts how
many times it has already kept this turn going, so it can give up:

```python
from hmz.flows import StopHookParams, StopHookResult


async def keep_going(params: StopHookParams) -> StopHookResult:
    if params.again < 3 and b"TODO" in await workspace.read("TASK.md"):
        return StopHookResult(  # [!code highlight]
            block=True, reason="There is still a TODO in TASK.md."  # [!code highlight]
        )  # [!code highlight]
    return StopHookResult()
```

A `block` with an empty `reason` does not block. This is one of three ways to keep an agent
going:

| | Decides it is done | Works on |
| --- | --- | --- |
| a `while` loop in the flow | your code, between turns | every CLI |
| a blocking `on_stop` hook | your code, inside the turn | every CLI |
| a [`/goal`](/weaver/goals) | the **model**, against the objective | `claude`, `codex`, `dsh`, `kimi`, `zcode` |

## Stopping a tool

There are two moments to stop a tool at, and whether a refusal stops it depends on the CLI:

| Refuse in | Stops the tool on | Elsewhere |
| --- | --- | --- |
| `on_pre_tool_use` | `claude`, `qwen` | <Badge type="warning" text="watch only" /> the hook hears of the tool, which may already be running |
| `on_permission_request` | `claude`, `codex`, `kimi`, `zcode` | <Badge type="info" text="not served" /> a role that [declares it](#declaring-a-mixin) is never given these CLIs |

Each CLI decides which calls it asks permission for. A known-safe read may never be asked
about, and Kimi Code and ZCode ask only about what they deem risky. On Claude Code, where both
moments can stop a tool, `on_pre_tool_use` answers first, and a tool it refuses is never put to
`on_permission_request`.

```python
from hmz.flows import (
    PermissionRequestHookParams,
    PermissionRequestHookResult,
)


async def no_force_push(
    params: PermissionRequestHookParams,
) -> PermissionRequestHookResult:
    if "push --force" in str(params.input.get("command", "")):
        return PermissionRequestHookResult(  # [!code highlight]
            allow=False, reason="not on this branch"  # [!code highlight]
        )  # [!code highlight]
    return PermissionRequestHookResult()  # allowed


builder.on_permission_request(no_force_push)
```

Every flow's agents run with approvals bypassed. A permission hook puts the flow back in the
loop: a request is allowed unless the hook says no. [`humanize1`](/flows/humanize1) guards its
builder with both moments. See [Permissions](/user/permissions) for what a role may touch at
all.

::: tip Hang these before the turn they should cover
`on_pre_tool_use` on Claude Code and Qwen Code, and `on_permission_request` or `on_ask_user` on
Codex, Kimi Code and ZCode, change how the CLI is started. Hung mid-turn, they take hold from
the next turn.
:::

## Declaring a mixin

A role that hangs a hook on a moment only some CLIs reach says so on its type:

```python
from hmz.flows import (
    Agent,
    AgentCollection,
    PermissionRequestHookAgentMixin,
)


class Builder(Agent, PermissionRequestHookAgentMixin):  # [!code highlight]
    """Every command it asks to run is put to the flow first."""


class Agents(AgentCollection):
    builder: Builder
    reviewer: Agent
```

A CLI that does not reach the moment is refused before the first turn, and `/flow` does not
offer it for that role:

```console
$ hmz exec -f gated -a builder=grok/grok-4.6:high \
    -a reviewer=codex/gpt-5.6-sol:high -b cost=10 "fix the build"
hmz exec: error: gated: 'builder' needs PermissionRequestHookAgentMixin, which grok does not do
```

A role that did not declare it cannot hang one: `on_permission_request` on a plain `Agent` is a
type error, and raises `CapabilityNotGranted` if it runs anyway, whatever the CLI underneath
could do.

| CLI (`-a`) | `on_permission_request` | `on_subagent_start`, `_stop` | `on_ask_user` |
| --- | :---: | :---: | :---: |
| `claude`, `codex` | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> |
| `kimi`, `zcode` | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> | <Badge type="tip" text="yes" /> |
| `cursor-agent` | <Badge type="info" text="no" /> | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> |
| `pi` | <Badge type="info" text="no" /> | <Badge type="info" text="no" /> | <Badge type="tip" text="yes" /> |
| `agy`, `dsh`, `grok`, `mimo`, `opencode`, `qwen`, an ACP CLI | <Badge type="info" text="no" /> | <Badge type="info" text="no" /> | <Badge type="info" text="no" /> |

Every mixin a role declares narrows the CLIs that can fill it, goals and steering included.
Combine them here:

<RoleFit />

## Two rules

**A hook that raises fails the turn it arrived in.** The turn is interrupted, and the `run` the
flow is waiting on raises what the hook raised, as if the flow's own code had raised it. Catch
inside the hook whatever it should survive.

**A hook runs as the flow the agent belongs to.** `params.ctx` is that flow's context, and the
hook may take a turn of another agent, read the environment or call a flow. The CLI waits
meanwhile. A hook that keeps it waiting for 15 minutes is answered as if nothing were hung, so
a stuck hook cannot stall the run. `on_ask_user` is the exception: a question waits for its
answer. See [The agent asking the flow](/weaver/tools).

## See also

- [Goals](/weaver/goals): the same shape as a blocking `on_stop`, decided by the model
- [The agent asking the flow](/weaver/tools)
- [Permissions](/user/permissions)
- [The moments of a turn](/features/hooks): a hook hung and a turn run, drawn
- [Flows › Hooks in a flow](/reference/flows#hooks-in-a-flow)
