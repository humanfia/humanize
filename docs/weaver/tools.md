# The agent asking the flow

A flow drives an agent by saying things to it. This is the other direction: **the agent,
mid-turn, reaching the flow** — and the flow's own code running, with the flow's own agents and
environments, to answer it.

Reach for it when the agent needs something only the flow has: another agent, another flow, a
decision that is yours to make.

::: warning Callbacks as tools are gone
Earlier versions of the flow API let a flow put its own functions in front of an agent as tools
— `session.offers([Tool(...)])`, served over MCP. The flow API has no such thing any more: a
flow cannot add a tool to an agent. What reaches the flow from inside a turn is a
[hook](/weaver/hooks), and the one that carries a request and waits for an answer is the
agent's question to its user.
:::

## Try it

An agent whose role declares `AskUserHookAgentMixin` may stop mid-turn and ask its user
something. Hang a hook on that, and the user it asks is your flow:

```python
# .humanize/flows/delegating/__init__.py
"""Build here, and let the builder ask for a review whenever it wants one."""

from hmz.flows import (
    Agent,
    AgentCollection,
    AskUserHookAgentMixin,
    AskUserHookParams,
    AskUserHookResult,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)

ASKING = """When you want a file reviewed, ask your user `review <path>` and wait for the \
answer: it is the review. Ask for one before you say you are done."""


class Builder(Agent, AskUserHookAgentMixin):
    """An agent that may stop mid-turn and ask."""


class Agents(AgentCollection):
    builder: Builder
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def delegating(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """Build here, and let the builder ask for a review whenever it wants one."""
    builder, reviewer, workspace = agents["builder"], agents["reviewer"], envs["workspace"]

    async def asked(params: AskUserHookParams) -> AskUserHookResult:
        if not params.question.startswith("review "):
            return AskUserHookResult()             # not ours: let it carry on unanswered
        reading = await reviewer.spawn(env=workspace)
        said = await reviewer.run(
            f"Review {params.question.removeprefix('review ')}. Be brief.", session=reading
        )
        return AskUserHookResult(answer=said)

    builder.on_ask_user(asked)
    session = await builder.spawn(env=workspace)
    return await builder.run(f"{task}\n\n{ASKING}", session=session)
```

```sh
hmz exec -f delegating -a builder=claude/claude-opus-5:max \
    -a reviewer=codex/gpt-5.6-sol:high -b cost=20 "write the parser"
```

The builder decides when it wants a review, and the reviewer's turn happens inside the
builder's — which is a thing no prompt can arrange.

## An agent that calls a flow

The hook is the flow's own code, run as the flow, so it may do whatever the flow may do,
including start another flow and wait for it:

```python
from hmz.flows import Budget, BudgetExceeded, load

chase = load("flame_chase")


async def asked(params: AskUserHookParams) -> AskUserHookResult:
    if not params.question.startswith("chase "):
        return AskUserHookResult()
    try:
        await chase(
            params.question.removeprefix("chase "),
            agents={"first_chaser": reviewer, "second_chaser": reviewer},
            envs={},                      # its workspace is the run's own
            params=chase.expected_params(),
            budget=Budget(cost=5.0),      # a loop with no end of its own gets one here
        )
    except BudgetExceeded:
        pass
    return AskUserHookResult(answer="done: read the working tree for what it came to")
```

That is an agent deciding, mid-turn, that a piece of work wants a loop of its own — and getting
one, under five dollars of the run's budget. Nothing about it is written into any CLI.

## What a question is

| | |
| --- | --- |
| `params.question` | what the agent asked, in its own words |
| `params.options` | the answers it offered, if it offered any — an answer need not be one of them |
| `params.ctx`, `params.session` | the flow's context, and the session the question arrived in |
| `AskUserHookResult(answer=…)` | what the agent is told |
| `AskUserHookResult()` | no answer: the agent carries on without one |

The prompt is the whole of what the agent knows about when to ask and how to phrase it, so the
flow says both — a word to start the question with, as `review ` above, is the simplest way for
the hook to tell one request from another.

**A question waits.** Every other hook that keeps a CLI waiting for fifteen minutes is answered
as though nothing were hung; a question is exempt, and waits for its answer as long as the
answer takes — a reviewer's turn, a whole subflow. The turn it arrived in is paused meanwhile,
and what the hook spends counts against the run like anything else.

**A hook that raises fails the turn.** The builder's `run` raises what the hook raised, as
though the flow's own code had — which it had. Catch inside the hook what it means to survive.

## Which CLIs ask

| CLI | Asks its user |
| --- | --- |
| Claude Code | yes |
| Codex | yes — with its `default_mode_request_user_input` feature switched on while the hook is hung, from the next turn |
| Kimi Code, ZCode | yes — run at their ask-and-approve rung while the hook is hung, from the next turn |
| pi | yes |
| every other | no |

A role that declares `AskUserHookAgentMixin` is refused, before the first turn, an agent whose
CLI does not ask; and a role that does not declare it cannot hang the hook at all —
`on_ask_user` raises `CapabilityNotGranted`. See [Hooks](/weaver/hooks#saying-so-in-the-flow).

## The other ways in

A question is the one moment that carries a request *to* the flow and waits for what comes
back. The others reach the flow too, each for its own purpose:

| Hook | What the flow can do from it |
| --- | --- |
| `on_pre_tool_use` | see every tool the agent reaches for, and refuse it on a CLI that waits |
| `on_permission_request` | answer whether a tool may run — the gate, on a CLI that asks |
| `on_stop` | refuse to let the turn end, and hand the agent its next prompt |
| `on_notification` | hear what the agent stopped to tell its user |

See [Hooks](/weaver/hooks) for each of them.

## See also

- [Hooks](/weaver/hooks) — every moment a flow can hang one on
- [A flow that calls a flow](/weaver/calling-flows)
- [The person as an agent](/weaver/human-agent) — questions the flow puts to a person
- [Questions](/user/questions) — an agent's question, as whoever is at the prompt sees it
