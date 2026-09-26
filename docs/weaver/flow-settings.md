# Params of its own

Declare a `FlowParams` subclass and the flow grows a `-p` on the command line, a form at the
prompt, and refusals in your own words, with no interface code of your own. Reach for it when a
flow needs knobs: a round limit, a mode, a file to write to.

## Declare them

`FlowParams` is a [pydantic](https://docs.pydantic.dev/) model. Subclass it, one field per
param, and hand the class to `@flow` in place of `FlowParams`:

```python
# .humanize/flows/pair/__init__.py
from typing import Literal

from pydantic import Field

from hmz.flows import FlowContext, FlowParams, flow


class Params(FlowParams):  # [!code ++]
    """What this flow takes."""  # [!code ++]

    rounds: int = Field(default=3, ge=1, le=9, description="how many times round")  # [!code ++]
    mode: Literal["fast", "slow"] = Field(default="fast", description="which way")  # [!code ++]


@flow(agents=Agents, envs=Envs, params=FlowParams)  # [!code --]
@flow(agents=Agents, envs=Envs, params=Params)  # [!code ++]
async def pair(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext  # [!code --]
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext  # [!code ++]
) -> None:
    for _ in range(params.rounds):  # [!code highlight]
        ...
```

The fields are the questions, their types say how each is answered, and `description` is the
line shown beside it. `params` is always an instance of your class: nobody having set anything
is `Params()`, the defaults, so there is no `None` to fall back from. A key your model has no
field for is refused rather than ignored.

## Set them

::: code-group

```sh [hmz exec]
hmz exec -f pair -a agent=claude/claude-opus-5:max -b cost=10 \
    -p rounds=9 -p mode=slow "$(cat TASK.md)"
```

```text [At the prompt]
   ❯ 1. rounds                       3            how many times round
     2. mode                         fast         which way
```

:::

On the command line, `-p key=value` as many times as you like, or several in one:
`-p rounds=9,mode=slow`. A comma splits two params only where a `key=` follows it, so
`-p note=a, b, c` is one param. A value is read as its field's type — `9` is an `int` for
`rounds`, `true` a `bool` — and otherwise as JSON, so a list is written the way JSON writes
one:

```sh
-p 'tags=["parser","printer"]'
```

At the prompt, choosing the flow in `/flow` puts its params up as a form, and your types decide
how each row is answered:

| Field type | On the form |
| --- | --- |
| `bool` | a switch, `on` or `off` |
| `Literal[…]` | stepped through its values, in the order you wrote them |
| `int`, `float` | written, or stepped up and down by one |
| anything else | written |

What is set there is [remembered per flow](/user/settings), with the agents and the budget, so
twenty params are not twenty questions every morning.

## Refuse what cannot run

What the model refuses stops the run before any agent starts, with pydantic's own account of
why:

```console
$ hmz exec -f pair -a agent=claude/claude-opus-5:max -b cost=10 -p rounds=12 "…"
hmz exec: error: pair:pair: 1 validation error for Params
rounds
  Input should be less than or equal to 9 [type=less_than_equal, input_value=12, input_type=int]
    For further information visit https://errors.pydantic.dev/…/v/less_than_equal
```

So put the combinations you cannot run in the **model**, not in the flow:

```python
from pydantic import model_validator


class Params(FlowParams):
    fast: bool = Field(default=False, description="skip the review round")
    careful: bool = Field(default=False, description="review twice")

    @model_validator(mode="after")  # [!code focus]
    def _settles(self) -> "Params":  # [!code focus]
        if self.fast and self.careful:  # [!code focus]
            raise ValueError("fast and careful do not go together")  # [!code focus]
        return self  # [!code focus]
```

A bad combination is now refused where it is typed, on the form or on the command line, rather
than an hour into the run.

## Group them

A flow with twenty params is a wall. Give each field a section, and the form draws a heading
above each group:

```python
    reviews: int = Field(
        default=1,
        description="how many reviewers read each round",
        json_schema_extra={"section": "review  ·  how the work is read"},  # [!code highlight]
    )
```

```text
   review  ·  how the work is read
   ❯ 1. reviews                      1            how many reviewers read each round
     2. strict                       off          refuse on style as well as substance
```

The arrows walk the params and step over the headings.

## When another flow passes them

A flow that [calls yours](/weaver/calling-flows) passes an instance of your class:

```python
await load("pair")(task, agents=..., envs=..., params=Params(rounds=9))
```

That instance is taken as it is. Anything else — another `FlowParams`, a mapping of fields — is
validated into your class at the call, and refused with `ParamsError` where it does not
validate, before your flow has run a line.

## The budget is not a param

What a run may spend is the run's: `-b` on the command line, the budget row at the prompt. A
flow declares none. One that wants to know reads `ctx.budget`; one that wants part of its work
held to less gives that turn or that call a `Budget` of its own. See [Every run has a
budget](/features/allowances).

## Try this

`humanize1:rlcr` in the official flowverse takes over a dozen params, one per flag of the tool
it ports. Open it and look at what a large one of these is:

```text
/flow humanize1:rlcr
```
