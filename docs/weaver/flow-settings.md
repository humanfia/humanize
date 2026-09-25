# Params of its own

Declare a `FlowParams` subclass and the flow grows a form at the prompt, a `-p` on the command
line and a set of refusals, with no interface code of your own. Reach for this when a flow
needs knobs you want remembered between runs rather than typed every morning.

## Declare the params

`FlowParams` is a [pydantic](https://docs.pydantic.dev/) model. Subclass it, one field per
param, and hand the class to `@flow`:

```python
# .humanize/flows/pair/__init__.py
from typing import Literal

from pydantic import Field

from hmz.flows import FlowContext, FlowParams, flow


class Params(FlowParams):
    """What this flow takes."""

    rounds: int = Field(default=3, ge=1, le=9, description="how many times round")
    mode: Literal["fast", "slow"] = Field(default="fast", description="which way")


@flow(agents=Agents, envs=Envs, params=Params)
async def pair(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> None:
    for _ in range(params.rounds):
        ...
```

That is the whole of it. **The model is what asks.** The fields are the questions. Their types
say how each one is answered. `description` is the line shown beside a field. Whatever the
model refuses is what the flow will not run.

`params` is always an instance of your class. Nobody having set anything is `Params()` — the
defaults — so there is no `None` to fall back from. A flow that takes nothing says
`params=FlowParams`, and is handed an empty one.

`FlowParams` forbids what it does not declare: a key your model has no field for is refused
rather than quietly ignored, because a param typed wrong is a param somebody thinks they set.

## Set them from the command line

```sh
hmz exec -f pair -a agent=claude/claude-opus-5:max -b cost=10 \
    -p rounds=9 -p mode=slow "$(cat TASK.md)"
```

`-p key=value`, as many as you like, or several in one: `-p rounds=9,mode=slow`. A value is
read as its field's type — `9` is an `int` for `rounds`, `true` a `bool` — and, where that does
not read it, as JSON, so a list or a mapping is written the way JSON writes one:

```sh
-p 'tags=["parser","printer"]'
```

A comma separates two params only where a `key=` follows it, so `-p note=a, b, c` is one param
whose value has commas in it. What the model refuses stops the run before any agent starts,
with pydantic's own account of why:

```console
$ hmz exec -f pair -a agent=claude/claude-opus-5:max -b cost=10 -p rounds=12 "…"
hmz exec: error: pair:pair: 1 validation error for Params
rounds
  Input should be less than or equal to 9 [type=less_than_equal, input_value=12, input_type=int]
```

## Set them at the prompt

Choosing the flow in `/flow` puts its params up as a form: the model with a cursor on it. Each
row is one param — its name, what it is set to, and the line the flow declared it with.

```
   ❯ 1. rounds                       3            how many times round
     2. mode                         fast         which way
```

| Key | |
| --- | --- |
| **↑ ↓** | move between params |
| **← →** | move the one under the cursor along: a switch flips, a choice steps, a number goes up or down by one |
| letters | write the one under the cursor, for the ones that are written rather than stepped |
| **enter** | take the lot, and go on |
| **esc** | back, changing nothing |

What you set is [remembered per flow](/user/settings), with the agents and the environments
each role was given and the budget, so a flow of twenty params is not twenty questions every
morning. See [TUI › Setting a flow up](/reference/tui#setting-a-flow-up).

## What a run may spend is not a param

A budget is the run's, not the flow's: `-b` on a command line and the budget row of `/flow` at
the prompt. A flow declares none, and has no default of its own to fall back on — whoever runs
it says what it may spend, and `hmz exec` will not start one without being told. A flow that
wants to know reads `ctx.budget`; one that wants a part of its work held to less says so where
it [calls a flow](/weaver/calling-flows) or takes a turn, with a `Budget` of its own. See
[Budgets](/features/budgets).

## Refuse the combinations you cannot run

Put refusals in the **model**, not in the flow:

```python
from pydantic import model_validator


class Params(FlowParams):
    fast: bool = Field(default=False, description="skip the review round")
    careful: bool = Field(default=False, description="review twice")

    @model_validator(mode="after")
    def _settles(self) -> "Params":
        if self.fast and self.careful:
            raise ValueError("fast and careful do not go together")
        return self
```

The flow now refuses a bad combination where it was typed, on the form or on the command line,
rather than an hour into the run. Nothing in the interface knows what any of your params mean.
The types say how a value moves, and your model says which combinations it will not take.

## Group the params

A flow with twenty params is a wall. Each field says which part of the form it belongs under,
and the form draws a heading above each group:

```python
    gen_idea: bool = Field(
        default=True,
        description="open the idea into a repo-grounded draft",
        json_schema_extra={"section": "gen-idea  ·  open the idea into a draft"},
    )
```

```
   gen-idea  ·  open the idea into a draft
     1. gen_idea                     on           open the idea into a repo-grounded draft
     2. n                            6            --n: how many directions explore the idea
   ❯ 3. idea_output                  docs/d.md▏   --output: where the draft goes

   gen-plan  ·  turn the draft into a plan
     4. gen_plan                     on           turn the draft into a plan, against review
```

The arrows walk the params and step over the headings.

## When another flow passes them

A flow that [calls yours](/weaver/calling-flows) passes an instance of your class:

```python
await load("pair")(task, agents=..., envs=..., params=Params(rounds=9))
```

That instance is taken as it is. Anything else — an instance of another `FlowParams`, a mapping
of fields — is validated into your class at the call, and refused with `ParamsError` where it
does not validate, before your flow has run a line.

## What you get for free

- A form, with the right widget per type.
- `-p` on `hmz exec`, and the same answers on the form at the prompt.
- Validation, in your own words, at the moment somebody types it.
- [Remembered per flow](/user/settings), so twenty params are not twenty questions every
  morning.
- A typed `params` in your own code, which a type checker reads.

## Try this

`humanize1` takes a couple of dozen params, grouped into its phases. Fetch the official
flowverse, `/flow` it, choose it, and look at what a large one of these is:

```
/flow humanize1:gen-idea
```

## See also

- [Port a project](/user/tutorials/port-a-project)
- [Remembered per flow](/user/settings)
- [A flow that calls a flow](/weaver/calling-flows)
- [Reference › Flows › Settings of the flow's own](/reference/flows#settings-of-the-flow-s-own)
