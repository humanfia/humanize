# Params of its own

In this guide you give a flow settings of its own, called **params**: how many review passes to
take, what each looks for, whether to commit at the end. You declare them once, as a pydantic
model, and the flow grows a `-p` on the command line, a form at the prompt, and refusals in
your own words, with no interface code of your own.

Reach for params when a flow has a knob whoever runs it should turn: a round limit, a mode, a
file to write to. Anything the flow always does the same way stays a constant in the code.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- A little [pydantic](https://docs.pydantic.dev/): `Field`, `Literal`, and a validator.
:::

## How params work

`FlowParams` is a pydantic model. You subclass it, one field per param, and hand the class to
`@flow(params=…)`. From then on:

| Where | What your model does there |
| --- | --- |
| `hmz exec -p key=value` | Each value is read as its field's type, then the whole model is validated. A refusal stops the run before any agent starts. |
| `/flow` at the prompt | The fields become a form. The type decides how each row is answered, `description` is the line beside it. |
| another flow calling yours | It passes an instance of your class, or a mapping validated into one. |
| inside your flow | `params` is always a validated instance: the defaults where nothing was set, never `None`. |

A key your model has no field for is refused rather than ignored, so a typo on the command line
never silently does nothing.

## Example: `polish`

`polish` has one agent do the task, then review its own work a number of times for one thing,
and optionally commit. Four params steer it:

```python
# .humanize/flows/polish/__init__.py
from typing import Literal

from pydantic import Field, model_validator

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)

PASSES = {"section": "passes  ·  what the agent does"}  # ①
AFTER = {"section": "after  ·  what happens at the end"}


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):  # ②
    """What polish takes."""

    passes: int = Field(  # ③
        default=1, ge=1, le=5, description="review passes after the work",
        json_schema_extra=PASSES,
    )
    focus: Literal["correctness", "style", "tests"] = Field(  # ④
        default="correctness", description="what each pass looks for",
        json_schema_extra=PASSES,
    )
    commit: bool = Field(  # ⑤
        default=False, description="commit when done", json_schema_extra=AFTER
    )
    message: str = Field(
        default="", description="the commit message; empty for the agent's own",
        json_schema_extra=AFTER,
    )

    @model_validator(mode="after")  # ⑥
    def _settles(self) -> "Params":
        if self.message and not self.commit:
            raise ValueError("a message needs commit=true")
        return self


@flow(agents=Agents, envs=Envs, params=Params)  # ⑦
async def polish(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext  # ⑧
) -> None:
    """Do the work, then review it for one thing, as many times as asked."""
    builder = agents["builder"]
    session = await builder.spawn(env=envs["workspace"])
    await builder.run(task, session=session)
    for _ in range(params.passes):  # ⑨
        await builder.run(
            f"Review what you just did for {params.focus} only, and fix what you find.",
            session=session,
        )
    if params.commit:
        said = f"the message {params.message!r}" if params.message else "a message of yours"
        await builder.run(f"Commit your work with git, with {said}.", session=session)
```

### What each part does

1. **`{"section": …}`** is a heading for the form at the prompt. Fields that carry the same
   section are drawn under it, in the order you declare them. A flow with three params needs
   none; one with twenty needs them.
2. **`class Params(FlowParams)`** declares the params. Its docstring is for you: the form shows
   each field's `description`, not the class's.
3. **`passes: int = Field(default=1, ge=1, le=5, …)`**: the type says `-p passes=3` is read as
   an `int`; `ge` and `le` are pydantic's bounds, so `-p passes=9` is refused before anything
   runs; `description` is the line shown under it on the form.
4. **`Literal["correctness", "style", "tests"]`** is a choice. The command line accepts exactly
   those words, and the form drops them under the row in the order written.
5. **`commit: bool`** is a switch: `-p commit=true` on the command line, `on` or `off` on the
   form.
6. **`@model_validator(mode="after")`** refuses a combination the flow cannot run, where it is
   typed rather than an hour into the run. Its `ValueError` message is what the person sees.
7. **`@flow(…, params=Params)`** hands the class to the runtime in place of `FlowParams`.
8. **`params: Params`** types the argument as your class, so `params.passes` and
   `params.focus` are checked by your type checker too.
9. **`params.passes`** is read like any attribute. Every field has a default, so a run nobody
   configured is `Params()` and takes one pass for correctness.

## Run it

::: code-group

```sh [Claude Code]
hmz exec -f polish -a builder=claude/claude-sonnet-5-5:high -b cost=1 \
    -p passes=1,focus=tests,commit=true "add a subtract function to calc.py"
```

```text [At the prompt]
$local/polish add a subtract function to calc.py
```

:::

**On the command line**, `-p` takes `key=value`, several in one separated by commas, or the
option repeated. A comma splits two params only where a `key=` follows it, so
`-p message=fix a, b and c` is one param. A value is read as its field's type (`1` is an `int`
for `passes`, `true` a `bool`) and otherwise as JSON, so a list is written the way JSON writes
one: `-p 'tags=["parser","printer"]'`.

A real run, abridged:

```text
● builder is working
● Bash(cd /home/you/calc && ls && cat calc.py)
● Edit(/home/you/calc/calc.py)
● I added `subtract(a, b)` to `calc.py`. It returns `a - b` and follows the style of `add`. I haven't run it or added tests.
✻ input 6 · output 316 · cache_read 44.4k · cache_write 5.5k · $0.03 · claude-sonnet-5-5 · builder
…
✻ Worked for 6s · builder
● builder is working
● Bash(cd /home/you/calc && ls -a && python3 -m pytest --version 2>&1 | head -1)
● The repo has no tests, so neither `add` nor `subtract` is covered. pytest is available, so I'll add a test file covering both functions.
● Write(/home/you/calc/test_calc.py)
● Bash(cd /home/you/calc && python3 -m pytest -q 2>&1 | tail -5)
● The review found one problem: `subtract` had no tests, and neither did `add`. I added `test_calc.py` with parametrized cases for both functions. …
✻ input 6 · output 771 · cache_read 50.9k · cache_write 1.1k · $0.02 · claude-sonnet-5-5 · builder
…
✻ Worked for 7s · builder
● builder is working
● Bash(cd /home/you/calc && git add calc.py test_calc.py && git commit -m "$(cat <<'EOF'
Add subtract function and tests for)
● I committed `calc.py` and `test_calc.py` to `main` as `abb21ec`, with the message "Add subtract function and tests for calc".
  …
✻ input 4 · output 292 · cache_read 35.9k · cache_write 420 · $0.01 · claude-sonnet-5-5 · builder
…
✻ Worked for 3s · builder
```

The three turns are the three things the params asked for: the task, one pass (`passes=1`) that
looked at tests (`focus=tests`), and a commit (`commit=true`).

**At the prompt**, choosing the flow in `/flow` puts its params up as a form before its agents:

```text
  hmz › Flow › Set up polish
  Configure how this flow runs. Options and validation are defined by the flow
  itself.

  ╭──────────────────────────────────────────────────────────────────────────╮
  │ passes  ·  what the agent does                                           │
  │ passes                                                                 1 │
  │   review passes after the work                                           │
  │──────────────────────────────────────────────────────────────────────────│
  │ focus                                                      correctness ▾ │
  │   what each pass looks for                                               │
  │                                                                          │
  │ after  ·  what happens at the end                                        │
  │ commit                                                           ○ off ▾ │
  │   commit when done                                                       │
  │──────────────────────────────────────────────────────────────────────────│
  │ message                                                                — │
  │   the commit message; empty for the agent's own                          │
  ╰──────────────────────────────────────────────────────────────────────────╯

                                                                           Set

  enter change   tab actions   esc back
```

The two headings are the `section`s, each row is a field with its value at the far end and its
`description` under it, and `▾` marks a row whose values <kbd>enter</kbd> or a click drops
under it to be picked from. **Set**, the button under them, takes the form and goes on to the
flow's agents.

| Field type | On the form |
| --- | --- |
| `bool` | a switch, `on` or `off`, picked from the two |
| `Literal[…]` | picked from its values, in the order you wrote them |
| `int`, `float` | written |
| anything else | written |

The arrows walk the params and step over the headings. What is set there is
[remembered per flow](/user/settings), with the agents and the budget, so twenty params are not
twenty questions every morning.

## Check it worked

Every refusal happens before any agent starts, and costs nothing. Try one of each:

```sh
hmz exec -f polish -a builder=claude/claude-sonnet-5-5:high -b cost=1 -p passes=9 "x"
hmz exec -f polish -a builder=claude/claude-sonnet-5-5:high -b cost=1 -p message=hi "x"
hmz exec -f polish -a builder=claude/claude-sonnet-5-5:high -b cost=1 -p colour=red "x"
```

```text
hmz exec: error: polish:polish: 1 validation error for Params
passes
  Input should be less than or equal to 5 [type=less_than_equal, input_value=9, input_type=int]
    For further information visit https://errors.pydantic.dev/2.13/v/less_than_equal
hmz exec: error: polish:polish: 1 validation error for Params
  Value error, a message needs commit=true [type=value_error, input_value={'message': 'hi'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/value_error
hmz exec: error: polish:polish: 1 validation error for Params
colour
  Extra inputs are not permitted [type=extra_forbidden, input_value='red', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/extra_forbidden
```

The first is `le=5`, the second is your validator's own words, and the third is a key the model
does not declare.

In a test, `run_fake` takes the params as a mapping and validates it the same way:

```python
# tests/test_polish.py
import pytest

from hmz.flows import ParamsError
from hmz.sdk import fakes


async def test_passes_and_focus_shape_the_prompts() -> None:
    builder = fakes.FakeAgentDriver()
    await fakes.run_fake(
        "polish", "add subtract", agents={"builder": builder},
        params={"passes": 2, "focus": "tests"},  # ①
    )
    assert builder.prompts == [  # ②
        "add subtract",
        "Review what you just did for tests only, and fix what you find.",
        "Review what you just did for tests only, and fix what you find.",
    ]


async def test_the_defaults_take_one_pass_and_do_not_commit() -> None:
    builder = fakes.FakeAgentDriver()
    await fakes.run_fake("polish", "add subtract", agents={"builder": builder})  # ③
    assert len(builder.prompts) == 2


async def test_a_message_without_a_commit_is_refused() -> None:
    builder = fakes.FakeAgentDriver()
    with pytest.raises(ParamsError, match="a message needs commit=true"):  # ④
        await fakes.run_fake(
            "polish", "x", agents={"builder": builder}, params={"message": "hi"}
        )
    assert builder.prompts == []  # ⑤
```

```sh
uvx --with 'hmz @ git+https://github.com/humanfia/humanize.git' \
    --with pytest-asyncio pytest -q -o asyncio_mode=auto
```

```text
...                                                                      [100%]
3 passed in 0.09s
```

1. **`params={…}`** is what `-p` would be: a mapping, validated into `Params`.
2. **The prompts** show both params reached the flow: two passes, each about tests.
3. **No `params=`** is a run nobody configured, which is `Params()`.
4. **`ParamsError`** is what a mapping that does not validate raises, carrying pydantic's
   message, your validator's words included.
5. **No prompts** proves the refusal came before the first turn.

## Variations

**Another flow passes them.** A flow that [calls yours](/weaver/calling-flows) passes an
instance of your class, which is taken as it is. Anything else, such as a mapping of fields, is
validated into your class at the call, and refused with `ParamsError` where it does not
validate, before your flow has run a line:

```python
polish = load("polish")
await polish(task, agents=agents, envs=envs, params={"passes": 3})
```

**Big flows.** `humanize1:rlcr` in the official flowverse takes over a dozen params, one per
flag of the tool it ports. Open it to see a large one:

```text
/flow humanize1:rlcr
```

## Pitfalls

- **The budget is not a param.** What a run may spend is the run's: `-b` on the command line,
  the budget row at the prompt. A flow that wants to know reads `ctx.budget`; one that wants
  part of its work held to less gives that turn a `Budget` of its own. See [Every run has a
  budget](/features/allowances).
- **Give every field a default** unless the flow truly cannot run without it. A field with no
  default must be given on every `-p` line, and every flow that calls yours must pass it.
- **Keep combinations in the model, not in the flow.** A check in the flow body runs after
  the agents have started; the same check in a validator refuses the line before a token is
  spent.
- **Renaming a field breaks command lines.** `-p passes=…` in somebody's script is refused as
  an unknown key once the field is `rounds`.

## Next steps

- [A flow that calls a flow](/weaver/calling-flows): pass params from one flow to another.
- [Testing a flow](/weaver/testing-flows): the fake kit, and testing validators.
- [Settings](/user/settings): how the person running the flow keeps what they set.
- Reference: [`FlowParams`](/reference/flows#flowparams), [`hmz exec -p`](/reference/cli), and
  [errors](/reference/flows#when-something-goes-wrong).
