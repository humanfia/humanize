---
pageClass: hmz-feature
---

# The moments of a turn

A coding agent has hooks of its own: a table of shell commands to run before a tool, after a
prompt, when a turn stops. They live in a settings file, written before anything starts and
read by the backend rather than by whatever is driving it.

humanize holds the same moments here instead. A hook is **an async function a weaver hangs on a
moment** — hung on an agent the flow holds, and taken down again, while it runs. A flow says what
to do at a moment in the language it is written in, and says it to the agent it is holding rather
than to a file somewhere under a home directory.

<HmzMoments />

## One method per moment

Each moment is a method of the agent, and hanging a hook is calling it:

```python
from hmz.flows import PreToolUseHookParams, PreToolUseHookResult


async def no_force_push(params: PreToolUseHookParams) -> PreToolUseHookResult:
    pushing = "push --force" in str(params.input.get("command", ""))
    return PreToolUseHookResult(block=pushing, reason="no force pushes")


agents["coder"].on_pre_tool_use(no_force_push)
```

Hanging another on the same moment replaces it; `None` takes it down. Each moment has a params
type and a result type of its own, so a hook hung on the wrong moment is a type error before it
is anything else.

Six moments every harness reaches, and every agent has a method for:
`on_session_start`, `on_user_prompt_submit`, `on_pre_tool_use`, `on_notification`, `on_stop` and
`on_session_end`. The rest only some harnesses reach, so a role asks for them with a mixin where
the flow declares it:

| Method | Mixin | Harnesses that reach it |
| --- | --- | --- |
| `on_permission_request` | `PermissionRequestHookAgentMixin` | Claude Code, Codex, Kimi Code, ZCode |
| `on_subagent_start` | `SubagentStartHookAgentMixin` | Claude Code, Codex, Cursor |
| `on_subagent_stop` | `SubagentStopHookAgentMixin` | Claude Code, Codex, Cursor |
| `on_ask_user` | `AskUserHookAgentMixin` | Claude Code, Codex, Kimi Code, ZCode, pi |

A role declared with the mixin is filled only by a harness that reaches that moment, and a
harness that cannot is refused before anything runs. A hook hung through a role that did not
declare it raises `CapabilityNotGranted` **where it is hung**, rather than hours into a loop — a
hook that quietly never runs is a flow that quietly does not do what it says.

The two about a **fleet** — the agents an agent starts of its own, Claude's `Task`, Codex's
collab agent, Cursor's task tool — are told rather than answered: no backend waits to be told
whether it may start one, so what their hooks answer changes nothing.

## What a hook is told, and what it says back

Every hook is told the flow's own context — `ctx`, the flow the agent belongs to — and the
`session` the moment arrived in, and then what its moment carries: the prompt about to go, the
tool reached for and with what, what the agent said last and how many times this turn has
already been sent on.

What it answers is its moment's result, and a result built with no arguments changes nothing, so
a hook that only watches returns one. Otherwise:

- **block** — what was about to happen may not: the prompt does not go, the tool does not run,
  the turn does not end. At the end of a turn the `reason` is what the agent is sent on to *do*,
  so blocking with nothing to say is not blocking.
- **allow** — the answer to a permission the harness asked for, which overrides the bypassed
  approvals every agent runs under.
- **context** — something to put in front of the agent: before its first prompt, beside a
  prompt, in front of a subagent.
- **answer** — the reply to a question the agent stopped to ask.

## Refusing a tool, and where the refusal lands

`on_pre_tool_use` is the moment a flow most wants to refuse, and it is the one that cannot be read
off the stream a turn is read from: a CLI says what it reached for and *then* reaches for it, so a
refusal read there would be describing a tool that had already run.

So on the CLIs that gate their tools with a hook table of their own — Claude Code and Qwen Code —
humanize puts the moment in that table, and the CLI stops and waits for the answer: a block means
the tool **does not run**. On the rest the moment is still told to the hook, and a block there is
a flow watching a tool rather than stopping one. The table is there only while a hook is, and a
hook hung while a turn is running is put in it from the next turn.

`on_permission_request` is the refusal every harness that asks can honour: a refused tool is not
run, and its reason is what the agent is told — on Codex, whose refusals carry none, as a steer
into the turn. While one is hung, Codex runs with its `untrusted` approvals, so that every command
but a known-safe read is asked about; Kimi Code and ZCode run at the rung where they ask about what
they deem risky, and humanize answers every request yes unless the hook says no. None of this is
ever put to a model to decide.

Nothing of your own configuration is read, written or replaced to do it — your own hooks stay
yours, and a flow that ends leaves the machine as it found it.

## Hung on the agent, not on the session

A hook hung on an agent is on every conversation that agent opens, and on those of every agent
[derived](/reference/flows#what-each-agent-may-do) from it — and hanging one is something a flow
does while it is **already running**, which is the whole point of these being functions rather
than a file.

It is on *this flow's* agent. The agent a flow hands a flow it calls is that flow's own, with no
hooks on it, and the called flow's hooks are not heard by the caller's sessions: each flow hears
the moments of the turns it took.

## A hook is a word in the turn, not a note about it

The CLI reaches a moment on a thread of its own, and waits there while the hook — a coroutine of
the flow's — runs on the flow's loop, as the flow. A hook that takes a while is a turn that takes
a while, which is what lets it decide something, and also what makes a slow one expensive. One
that keeps the CLI waiting fifteen minutes is answered for as if nothing were hung — except a
question the agent asked, which waits for as long as its answer takes.

A hook that raises fails the turn it arrived in: the turn stops, and `run` raises what the hook
raised, where the flow is waiting on it — as the flow's own code raising would.

## What this is enough to build

- a permission rule of your own, on top of the [permission](/user/permissions) the role
  declares
- a house rule added to every prompt, without touching anybody's settings file
- a [goal written by hand](/features/goals): a blocked stop, decided by code
- a question answered by the flow — by another agent, or by a flow it calls
- a watcher that writes down what the agent reached for, alongside the
  [trace](/features/tracing)

## Where the detail is

- [Hooks](/weaver/hooks) — hanging one, and each moment's fields
- [It decides when it is done](/features/goals) — the blocked stop, and what it costs
- [Flows reference](/reference/flows#hooks-in-a-flow)
