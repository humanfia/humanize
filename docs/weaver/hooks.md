# Hooks

A **hook** is an async function hung on a **moment**, one of the points a session passes
through. Reach for one when you want to get between an agent and its turn: refuse a command,
add to a prompt, or refuse to let a turn end. Claude Code, Codex and Kimi Code each take a
table of shell commands for the same moments; a hook is the same idea, hung on a live agent,
taken down again while it runs, and written in the language the flow is.

## Try it

The gentlest hook does nothing but look. This one says what its agent reached for:

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


async def seen(params: PreToolUseHookParams) -> PreToolUseHookResult:
    print(f"  → {params.tool}: {str(dict(params.input))[:60]}")
    return PreToolUseHookResult()          # built with nothing, a result changes nothing


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def watched(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    agent = agents["agent"]
    agent.on_pre_tool_use(seen)
    for _ in range(5):
        session = await agent.spawn(env=envs["workspace"])
        await agent.run(task, session=session)
```

```sh
hmz exec -f watched -a agent=claude/claude-opus-5:high -b cost=10 "$(cat TASK.md)"
```

Each time the agent reaches for a tool you get a line: an arrow, the tool's name, and the start
of what it was called with. The hook answers an empty `PreToolUseHookResult`, so the turn goes
on unchanged.

::: tip What a flow prints goes into the transcript
The interface captures everything printed under it, so a `print` is how a flow says something.
:::

## Hanging and taking down

There is one method per moment, `on_` and its name, and it takes the hook or `None`:

```python
agent.on_stop(keep_going)        # hung
agent.on_stop(other)             # replaces it: one hook per moment per agent
agent.on_stop(None)              # and down again
```

A hook is on the **agent**, so one covers every session the agent opens, including the fresh
one a Ralph loop makes each round. Hanging one mid-run is the point: it reaches every moment
that arrives after it is hung, in the turn under way too — except the few that decide how a
CLI is started, which [take hold from the next turn](#what-a-hook-changes-about-the-cli).

"The agent" here is the one your flow was handed. An agent [derived](/weaver/calling-flows#narrow-what-you-hand-on)
from it shares its hooks. A flow you call is handed an agent of its own even when you pass it
yours, so its hooks and yours never hear each other's sessions.

## The moments

Six moments are on every agent, because every CLI reaches them:

| Method | When | Told, beside `ctx` and `session` | What the result does |
| --- | --- | --- | --- |
| `on_session_start` | a session is about to take its first turn | — | `context` goes in front of the first prompt |
| `on_user_prompt_submit` | a prompt is about to go to the agent | `prompt` | `block` refuses it — `run` raises `SessionError` saying `reason`; `context` is added to it |
| `on_pre_tool_use` | the agent has reached for a tool, which has not run yet | `tool`, `input` | `block` refuses it, with `reason` told to the agent, [where the CLI waits](#refusing-a-tool) |
| `on_notification` | the agent has stopped to tell its user something | `message` | nothing: it is heard, not answered |
| `on_stop` | a turn is about to end | `said`, `again` | `block` keeps the agent going, with `reason` as its next prompt |
| `on_session_end` | a session is being closed | — | nothing |

The rest only some CLIs reach, so a role that hangs one declares the mixin for it:

| Method | Mixin | When | Told | What the result does |
| --- | --- | --- | --- | --- |
| `on_permission_request` | `PermissionRequestHookAgentMixin` | the CLI asks whether a tool may run | `tool`, `input` | `allow=False` refuses it, with `reason` told to the agent — over the bypassed approvals it runs under |
| `on_subagent_start` | `SubagentStartHookAgentMixin` | the agent has started a subagent of its own | `subagent`, `task` | `context` for the subagent — which no CLI waits for yet, so it is heard and changes nothing |
| `on_subagent_stop` | `SubagentStopHookAgentMixin` | one of those is about to finish | `subagent`, `said` | `block` and `reason` to keep it going — likewise heard, and changing nothing yet |
| `on_ask_user` | `AskUserHookAgentMixin` | the agent has stopped mid-turn to ask its user a question | `question`, `options` | `answer` is what it is told, or `None` to let it carry on without one |

And an [outworlder made with `Outworlder.new()`](/weaver/human-agent#stand-in-for-the-person)
has one of its own, `on_outworlder_run`, which answers for it.

Each moment has a params class and a result class of its own in `hmz.flows` —
`StopHookParams` and `StopHookResult`, `PreToolUseHookParams` and `PreToolUseHookResult`, and
so on — and a hook is typed `HookFn[StopHookParams, StopHookResult]`: hung on the wrong moment,
it is a type error. Every params carries `ctx`, the [context](/reference/flows#the-context) of
the flow the agent belongs to, and `session`, the session the moment arrived in. A result built
with no arguments changes nothing, so a hook that only watches returns one.

A hook can refuse a command:

```python
from hmz.flows import PermissionRequestHookParams, PermissionRequestHookResult


async def no_force_push(params: PermissionRequestHookParams) -> PermissionRequestHookResult:
    if "push --force" in str(params.input.get("command", "")):
        return PermissionRequestHookResult(allow=False, reason="not on this branch")
    return PermissionRequestHookResult()


builder.on_permission_request(no_force_push)
```

It can also add to a prompt:

```python
from hmz.flows import UserPromptSubmitHookParams, UserPromptSubmitHookResult


async def remind(params: UserPromptSubmitHookParams) -> UserPromptSubmitHookResult:
    return UserPromptSubmitHookResult(context="Run the tests before you say you are done.")


builder.on_user_prompt_submit(remind)
```

## A blocking `STOP` is a goal by hand

The turn is not over until the hook lets it be. `params.again` counts how many times this turn
has already been kept going, so a hook that keeps blocking can decide to stop:

```python
from hmz.flows import StopHookParams, StopHookResult


async def keep_going(params: StopHookParams) -> StopHookResult:
    if params.again < 3 and b"TODO" in await workspace.read("TASK.md"):
        return StopHookResult(block=True, reason="There is still a TODO in TASK.md.")
    return StopHookResult()
```

Blocking with nothing to say is not blocking: a `block` with an empty `reason` lets the turn end.

That is what [`humanize1:rlcr`](/flows/humanize1) was built on: a round *is* the builder
believing the plan is done and trying to stop, and what the reviewer says is what it hears
instead.

It is one of three ways to keep an agent going:

| | Decides it is done | Works on |
| --- | --- | --- |
| a `while` loop in the flow | your code, between turns | every CLI |
| a blocking `STOP` hook | your code, inside the turn | every CLI |
| a [`/goal`](/weaver/goals) | the **model**, against the objective | Claude Code, Codex, DeepSeek Harness, Kimi Code, ZCode |

## Refusing a tool

`PRE_TOOL_USE` is a moment every CLI reaches, but what a refusal *does* there is not the same
everywhere. Most CLIs say what they reached for and then reach for it, so a refusal read off
what a turn says would be describing a tool that had already run.

On the CLIs that take a hook table for one run — **Claude Code** and **Qwen Code** — humanize
puts the moment in that table instead. The CLI stops and waits for the answer, and a refusal
means the tool **does not run**:

```python
async def no_shell(params: PreToolUseHookParams) -> PreToolUseHookResult:
    return PreToolUseHookResult(block=params.tool == "Bash", reason="this flow does not shell out")
```

On every other CLI the hook is still told, and a refusal there is a flow watching a tool rather
than stopping one. Nothing of your own configuration is read, written or replaced to do it: the
table reaches the CLI on its own command line, or through a settings file this run alone is
pointed at, and goes when the run does.

`PERMISSION_REQUEST` is the one to stop a tool with anywhere it is served — Claude Code, Codex,
Kimi Code, ZCode: the CLI asks, and waits. A refusal there is the tool refused, and its reason
told to the agent; Codex's refusals carry no reason of their own, so on Codex it reaches the
agent as a word put into the turn. The two moments are different and both fire, and the table
gets the first word — a CLI runs its hooks before it decides whether a tool is permitted — so a
refusal at `PRE_TOOL_USE` means the permission is never asked.

`SUBAGENT_START` and `SUBAGENT_STOP` are told rather than asked: no CLI waits on either, so what
their hooks answer changes nothing yet.

## What a hook changes about the CLI

Every agent runs with nothing put to anybody for approval. A `PERMISSION_REQUEST` or an
`ASK_USER` hook is a flow asking to be put to, so while one is hung, three CLIs are started so
that they ask — and humanize answers every request yes unless the hook says no, never a model:

| CLI | While hung | What it runs at |
| --- | --- | --- |
| Codex | `on_permission_request` | approval policy `untrusted`, over the sandbox its permission puts it in: every command but a known-safe read is asked about |
| Codex | `on_ask_user` | its `default_mode_request_user_input` feature on, without which its agent cannot ask its user anything outside plan mode |
| Kimi Code, ZCode | either | their ask-and-approve rung — Kimi's `yolo`, ZCode's `build` — which asks about what the CLI deems risky |

That is how a CLI is **started**, so it takes hold from the next turn: a hook hung while a turn
is running reaches that turn's later moments where the CLI already asks, and changes how it is
started from the turn after. Take the hook down and the CLI goes back to asking nothing.
`PRE_TOOL_USE` on a CLI that gates its tools with a table is the same: the table is written as
the turn starts. See [Permissions](/user/permissions).

## Saying so in the flow

A flow that hangs a hook on a moment only some CLIs reach declares the mixin on the role's
type:

```python
from hmz.flows import Agent, AgentCollection, PermissionRequestHookAgentMixin


class Builder(Agent, PermissionRequestHookAgentMixin):
    """Gated: every command it asks to run is put to the flow first."""


class Agents(AgentCollection):
    builder: Builder
    reviewer: Agent
```

An agent handed to `builder` whose CLI does not reach the moment is refused before the first
turn:

```console
$ hmz exec -f gated -a builder=grok/grok-4.6:high -a reviewer=codex/gpt-5.6-sol:high \
    -b cost=10 "fix the build"
hmz exec: error: gated:gated: 'builder' needs PermissionRequestHookAgentMixin, which grok does not serve
```

And a role that did not declare it cannot hang one: `on_permission_request` on a plain `Agent`
raises `CapabilityNotGranted`, whatever the CLI underneath could have done — and is a type error
before it runs. Opening that flow in `/flow` offers only the CLIs that would work for that role.

| CLI | Permission request | Subagent start and stop | Ask user |
| --- | --- | --- | --- |
| Claude Code | yes | yes | yes |
| Codex | yes | yes | yes |
| cursor-agent | no | yes | no |
| Kimi Code | yes | no | yes |
| ZCode | yes | no | yes |
| pi | no | no | yes |
| Grok Build, opencode, MiMo Code, Qwen Code, Antigravity, DeepSeek Harness, an ACP CLI | no | no | no |

## Two rules

**A hook that raises fails the turn it arrived in.** The turn is interrupted, and the `run`
the flow is waiting on raises what the hook raised — exactly as an exception in the flow's own
code would, because a hook *is* the flow's own code. Catch inside the hook what it means to
survive.

**A hook runs as the flow the agent belongs to**, on the flow's own loop: `params.ctx` is that
flow's context, and a hook may take a turn of another agent, read the environment or call a
flow. The CLI waits while it runs. One that keeps a CLI waiting for fifteen minutes is answered
as though nothing were hung, so that a hook that hangs cannot hang the run with it — an
`ASK_USER` hook excepted, which is a question and waits for its answer as long as it takes. See
[The agent asking the flow](/weaver/tools).

## See also

- [Goals](/weaver/goals) — the same shape, decided by the model
- [The agent asking the flow](/weaver/tools)
- [Permissions](/user/permissions)
- [Agents › Hooks](/reference/agents#hooks)
- [Reference › Flows › Hooks in a flow](/reference/flows#hooks-in-a-flow)
