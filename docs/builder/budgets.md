---
title: Budgets in a flow
description: Read the epic's budget from a flow, give one turn or one called flow a tighter budget, and end cleanly when a budget is spent.
---

# Budgets in a flow

Every epic runs under a budget set by the person who starts it. A flow can read that budget, read what has been spent, and put a tighter budget around one turn or one called flow. A flow can never raise a limit.

![Three budgets, one inside the other: the epic's, a called flow's and one turn's. A turn is held to the tightest limit of the three, and what it spends counts against all of them](/diagrams/builder-budgets-1.svg)

## Read the budget and the spending

Read `ctx` at any time to see the current budget and spending.

| Name | What it is |
| --- | --- |
| `ctx.budget` | A `Budget`: the most this flow call may spend in all, the tightest of every budget around it. |
| `ctx.usage` | A `Usage`: what this flow call and every flow it called have spent so far. |
| `session.usage` | A `Usage`: what the turns of one session have spent so far. |

`Budget` and `Usage` have the same three fields.

| Field | In a `Budget` | In a `Usage` |
| --- | --- | --- |
| `duration` | A `datetime.timedelta`: time on the clock from the start of the call to its deadline. | The time agents spent in turns, added up. Two turns at once count twice. |
| `cost` | US dollars. | US dollars spent. |
| `output_tokens` | Tokens the agents may write. | Tokens the agents wrote. |

An unset limit is `None`. An unlimited budget has a `cost` of `math.inf`.

`ctx.budget` is the total allowance, not what remains. Subtract `ctx.usage` to find the remaining cost or tokens. Track elapsed wall time yourself, because `Usage.duration` only sums agent turn time.

## Limit one turn

Pass a `Budget` to `run` to cap that turn alone on top of any outer budgets. The next turn starts fresh. Set at least one of `duration`, `cost`, or `output_tokens`.

Set `graceful=False` on a turn's budget. A graceful limit lets the current turn finish, which does nothing on a single turn.

This flow sets a time limit on each turn and stops early when few tokens remain:

```python
# .hmz/flows/capped/__init__.py
import datetime

from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    BudgetExceeded,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    seconds: float = 600
    """The most one turn may take."""


@flow(agents=Agents, envs=Envs, params=Params)
async def capped(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> str:
    """Up to four rounds on a task, each turn held to a time limit of its own."""
    coder, workspace = agents["coder"], envs["workspace"]
    session = await coder.spawn()
    turn = Budget(duration=datetime.timedelta(seconds=params.seconds), graceful=False)
    cut = 0
    for round in range(4):
        allowed = ctx.budget.output_tokens  # None when no token limit is set
        if allowed is not None and allowed - ctx.usage.output_tokens < 500:
            break  # too little left for a useful round: end normally
        try:
            await coder.run(
                task if round == 0 else "Carry on.",
                session=session,
                env=workspace,
                budget=turn,
            )
        except BudgetExceeded as spent:
            if not spent.own:
                raise  # the epic's budget is spent: let it end the epic
            cut += 1  # only this turn's limit: the flow goes on
    return f"{cut} turns cut off, {ctx.usage.output_tokens} output tokens written"
```

When a turn passes its own limit, it stops at once and `run` raises `BudgetExceeded` with `own` set to `True`. File changes remain in place, and the session can take another turn. When `own` is `False`, an outer flow or epic budget is spent, and any later turn will raise too.

Run the flow with a two-second turn limit to see a turn cut off:

```sh
hmz exec -f @local/capped -a coder=claude/claude-haiku-4-5 \
    -p budget.output_tokens=20000 -p seconds=2 "Add a discount code to checkout"
```

![The command's output: the first turn is cut off after two seconds because its budget is spent, then the same agent takes three more turns](/shots/builder-budgets-exec.svg)

*The first turn is cut off. The flow goes on in the same session.*

## Limit a called flow

Pass `budget=` when you call a flow. The called flow runs under the tighter of that budget and your remaining budget. Its `duration` is a deadline counted from the start of the call. Its cost and token spending also count against your flow and the epic.

```python
# .hmz/flows/drafted/__init__.py
@flow(agents=Agents, envs=Envs, params=FlowParams, hidden=True)
async def polish(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Round after round on one task, until its budget ends it."""
    coder = agents["coder"]
    session = await coder.spawn()
    while True:
        await coder.run(f"Polish: {task}", session=session, env=envs["workspace"])


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def drafted(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A draft, some polish under a budget of its own, then a summary."""
    coder, workspace = agents["coder"], envs["workspace"]
    session = await coder.spawn()
    await coder.run(task, session=session, env=workspace)
    try:
        await polish(
            task,
            agents=agents,
            envs=envs,
            params=params,
            budget=Budget(output_tokens=300),
        )
    except BudgetExceeded:
        pass  # the polish spent its share; the next turn raises if the epic's is spent too
    return await coder.run("Summarise the change.", session=session, env=workspace)
```

`drafted` uses the same imports, `Agents`, and `Envs` as `capped`. `polish` loops until it spends its 300 tokens. Its next turn raises `OutputTokensExceeded`, which exits `polish` and reaches `drafted` at the `await`. `drafted` catches it and continues. An exception raised for a called flow's budget always has `own` set to `False`.

In the app, the **Epic** tab lists the call under **Called flows** as `stopped`, while the epic itself finishes as done.

![Humanize Desktop with the finished epic: the Epic tab lists the called flow drafted:polish as stopped, and the epic is done](/shots/builder-budgets-called.svg)

*The call was ended by its own budget. The epic went on and finished.*

See [Call another flow](/builder/calling-flows) for more on calling flows.

## Choose what happens at a limit

Set `graceful` to control what happens to a running turn when it hits a limit.

| `graceful` | At the limit |
| --- | --- |
| `True` (the default) | The turn under way finishes and returns. The next turn raises. |
| `False` | The turn under way is stopped at once and `run` raises. |
| `Graceful(duration=False)` | One answer for each limit. A field you leave out is `True`. |

```python
import datetime

from hmz.flows import Budget, Graceful

budget = Budget(
    duration=datetime.timedelta(minutes=30),
    cost=2,
    graceful=Graceful(duration=False),  # time cuts the turn off; cost lets it finish
)
```

When budgets around a turn disagree, each limit follows the budget with the least remaining allowance. `budget.graces` is always a `Graceful` instance, regardless of how you pass `graceful`.

## End when a budget is spent

A spent budget raises one of three `BudgetExceeded` subclasses.

| Exception | The spent limit |
| --- | --- |
| `DurationExceeded` | `duration`. It is also a `TimeoutError`. |
| `CostExceeded` | `cost` |
| `OutputTokensExceeded` | `output_tokens` |

A spent budget stays spent. Every later turn under it raises immediately before contacting the agent.

Let the exception leave your flow to end the epic. Humanize records the epic as stopped rather than failed, and `hmz exec` prints a line starting with `hmz exec: stopped --` and exits with status `0`. To finish as done instead, check `ctx.budget` and `ctx.usage` before a turn and return early, as `capped` does.

Deadlines behave differently inside the timed flow. When a flow call's `duration` expires, Humanize cancels the call (after any running turns finish, if graceful). Inside that flow, you receive `asyncio.CancelledError`; its caller receives `DurationExceeded`. Put cleanup in `finally`, not only in `except BudgetExceeded`. See [Context, errors and cleanup](/builder/context).

## Test budgets

Set `cost` and `output_tokens` on `FakeAgentDriver` to control what a scripted agent spends per turn. Pass `budget=` to `run_fake` to set the epic's budget; without it, the budget is unlimited.

```python
# tests/test_capped.py
import pytest

from hmz.flows import Budget, OutputTokensExceeded
from hmz.sdk import fakes


async def test_it_stops_before_the_tokens_run_out() -> None:
    coder = fakes.FakeAgentDriver(output_tokens=400)

    said = await fakes.run_fake(
        "capped", "add a coupon", agents={"coder": coder}, budget=Budget(output_tokens=1000)
    )

    assert said == "0 turns cut off, 800 output tokens written"


async def test_a_spent_epic_budget_ends_the_flow() -> None:
    coder = fakes.FakeAgentDriver(output_tokens=1200)

    with pytest.raises(OutputTokensExceeded):
        await fakes.run_fake(
            "capped",
            "add a coupon",
            agents={"coder": coder},
            budget=Budget(output_tokens=1000, graceful=False),
        )
```

See [Test a flow](/builder/testing).

## Good to know

- The person starting the epic sets its budget, not the flow. See [Budgets](/user/budgets). A flow cannot declare a param named `budget`.
- A `Budget` with no limits or with a negative limit raises `pydantic.ValidationError`. `Budget(cost=math.inf)` creates an unlimited budget.
- `budget=` on a flow call must be a `Budget` or `None`. Any other type raises `TypeError`.
- A model with no listed price costs $0, so a cost limit never stops it. Pair cost with time or tokens.
- The final turn under a graceful limit can spend past the limit before finishing.
- Concurrent turns spend from the same budgets. See [Concurrent turns](/builder/async).
- `except Exception` around a turn catches spent budgets too. Catch `HarnessError` for failed turns, and let `BudgetExceeded` pass through.
- A resumed epic counts its budget from zero. See [Resumable flows](/builder/resumable).
