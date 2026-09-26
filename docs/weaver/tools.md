# The agent asking the flow

A flow drives an agent by talking to it. This is the other direction: **the agent, mid-turn,
asking the flow**, and the flow's own code answering with its own agents and environments.
Reach for it when the agent needs something only the flow has: another agent, another flow, or
a decision that is yours.

The way in is the agent's own question to its user. Declare `AskUserHookAgentMixin` on the
role, hang an `on_ask_user` [hook](/weaver/hooks), and the user it asks is your flow.
`hmz.flows` has no other way to hand an agent a tool.

## Try it

A builder that asks for a review whenever it wants one, answered by a second agent:

```python
# .humanize/flows/delegating/__init__.py
"""Build, and let the builder ask for a review whenever it wants one."""

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

ASKING = (
    "When you want a file reviewed, ask your user `review <path>` and wait "
    "for the answer: it is the review. Ask for one before you say you are done."
)


class Builder(Agent, AskUserHookAgentMixin):  # [!code highlight]
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
    builder, reviewer = agents["builder"], agents["reviewer"]
    workspace = envs["workspace"]

    async def asked(params: AskUserHookParams) -> AskUserHookResult:  # [!code highlight]
        if not params.question.startswith("review "):
            return AskUserHookResult()  # not ours: no answer
        reading = await reviewer.spawn(env=workspace)
        said = await reviewer.run(
            f"Review {params.question.removeprefix('review ')}. Be brief.",
            session=reading,
        )
        return AskUserHookResult(answer=said)  # [!code highlight]

    builder.on_ask_user(asked)  # [!code highlight]
    session = await builder.spawn(env=workspace)
    return await builder.run(f"{task}\n\n{ASKING}", session=session)
```

```sh
hmz exec -f delegating -a builder=claude/claude-opus-5:max \
    -a reviewer=codex/gpt-5.6-sol:high -b cost=20 "write the parser"
```

The builder decides when it wants a review, and the reviewer's turn happens inside the
builder's. No prompt can arrange that.

The prompt is all the agent knows about when to ask and how to phrase it, so the flow says
both. A fixed first word, like `review ` above, is the simplest way for the hook to tell one
request from another.

## What a question carries

| | |
| --- | --- |
| `params.question` | what the agent asked, in its own words |
| `params.options` | the answers it offered, if any; your answer need not be one of them |
| `params.ctx`, `params.session` | the flow's context, and the session the question arrived in |
| `AskUserHookResult(answer=…)` | what the agent is told |
| `AskUserHookResult()` | no answer: the agent carries on without one |

**A question waits.** Other hooks are answered as if nothing were hung once they keep a CLI
waiting 15 minutes. A question waits as long as its answer takes, whether that is a reviewer's
turn or a whole subflow. The turn it arrived in is paused meanwhile, and whatever the hook
spends counts against the run.

**A hook that raises fails the turn.** The builder's `run` raises what the hook raised, as if
the flow's own code had raised it. Catch inside the hook whatever it should survive.

## An agent that starts a flow

The hook is the flow's own code, so it can do anything the flow can, including call another
flow and wait for it:

```python
from hmz.flows import Budget, BudgetExceeded, load

chase = load("git+https://github.com/humanfia/flowverse@main#flame_chase")


async def asked(params: AskUserHookParams) -> AskUserHookResult:
    if not params.question.startswith("chase "):
        return AskUserHookResult()
    try:
        await chase(
            params.question.removeprefix("chase "),
            agents={"first_chaser": reviewer, "second_chaser": reviewer},
            envs={},                  # its workspace is the run's own
            params=chase.expected_params(),
            budget=Budget(cost=5.0),  # it never ends on its own [!code highlight]
        )
    except BudgetExceeded:
        pass
    return AskUserHookResult(answer="done: read the working tree")
```

The agent decides, mid-turn, that a piece of work needs a loop of its own, and gets one:
[`flame_chase`](/flows/flame-chase), under five dollars of the run's budget.

## Which CLIs ask

| CLI (`-a`) | Asks its user |
| --- | :---: |
| `claude`, `codex`, `kimi`, `pi`, `zcode` | <Badge type="tip" text="yes" /> |
| `agy`, `cursor-agent`, `dsh`, `grok`, `mimo`, `opencode`, `qwen`, an ACP CLI | <Badge type="info" text="no" /> |

For a role that declares `AskUserHookAgentMixin`, a CLI that does not ask is refused before the
first turn. A role that does not declare it cannot hang the hook: `on_ask_user` raises
`CapabilityNotGranted`. On Codex, Kimi Code and ZCode, hang it before the turn it should cover:
hung mid-turn, it takes hold from the next one. See [Hooks](/weaver/hooks#declaring-a-mixin).

## The other ways in

A question is the one moment that carries a request to the flow and waits for what comes back.
Other hooks reach the flow too, each for its own purpose:

| Hook | What the flow can do from it |
| --- | --- |
| `on_pre_tool_use` | see every tool the agent reaches for, and stop it on a CLI that waits |
| `on_permission_request` | decide whether a tool may run, on a CLI that asks |
| `on_stop` | refuse to let the turn end, and hand the agent its next prompt |
| `on_notification` | hear what the agent stopped to tell its user |

## See also

- [Hooks](/weaver/hooks): every moment a flow can hang one on
- [A flow that calls a flow](/weaver/calling-flows)
- [The person as an agent](/weaver/human-agent): questions the flow puts to a person
- [Questions](/user/questions): an agent's question, as whoever is at the prompt sees it
