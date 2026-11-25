---
title: Params
description: Declare a flow's typed params once and have them asked in the app, in the terminal and with -p, validated before any agent starts.
---

# Params

Params are the settings the caller can change when running a flow, such as the number of rounds, the mode, or whether to commit. Declare them once as a pydantic model. Humanize prompts for them on every interface and passes a validated instance to your flow.

![One params class becomes the -p flag, the form in the app, the sheet in the terminal and a mapping from Python; each is validated into the params your flow reads, or refused before the run](/diagrams/builder-params-1.svg)

## Declare the params

Subclass `FlowParams`, add one field per param, and pass the class to `@flow(params=...)`. If a flow takes no params, pass `FlowParams` itself.

```python
# .hmz/flows/polish/__init__.py
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

REVIEW = {"section": "Review"}
AFTER = {"section": "After"}


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    rounds: int = Field(
        2, ge=1, le=5, description="Review rounds after the work.",
        json_schema_extra=REVIEW,
    )
    focus: Literal["correctness", "style", "tests"] = Field(
        "correctness", description="What each round looks for.",
        json_schema_extra=REVIEW,
    )
    commit: bool = Field(
        False, description="Commit when done", json_schema_extra=AFTER
    )
    message: str = Field(
        "", title="Commit message", description="Empty for the agent's own.",
        json_schema_extra=AFTER,
    )

    @model_validator(mode="after")
    def _message_needs_commit(self) -> "Params":
        if self.message and not self.commit:
            raise ValueError("a message needs commit=true")
        return self


@flow(agents=Agents, envs=Envs, params=Params)
async def polish(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> None:
    """Do the task, then review it for one thing."""
    coder, workspace = agents["coder"], envs["workspace"]
    session = await coder.spawn()
    await coder.run(task, session=session, env=workspace)
    for _ in range(params.rounds):
        await coder.run(
            f"Review your change for {params.focus} only. Fix what you find.",
            session=session,
            env=workspace,
        )
    if params.commit:
        how = f"the message {params.message!r}" if params.message else "your own message"
        await coder.run(f"Commit your work with {how}.", session=session, env=workspace)
```

Inside the flow, `params` is an instance of your class, never `None`. Unset fields hold their defaults.

All standard pydantic field features work. The interfaces also read these attributes:

| In the model | What it does |
| --- | --- |
| The field's type | How `-p` parses text, and which control the form draws. |
| The default | The value used when unset. A field with no default is required on every run. |
| `description` | Help text shown with the param. |
| `title` | Display name on the form and sheet. `-p` still uses the field key. |
| `ge`, `le` and other bounds | Rejects out-of-range values. |
| `Literal[...]` | Restricts input to fixed choices. |
| `@model_validator` | Rejects invalid combinations and shows the `ValueError` message to the user. |
| `json_schema_extra={"section": "..."}` | Groups params under a heading on the terminal sheet. |

Unknown keys are rejected. You cannot name a param `budget`; `@flow` raises `FlowDefinitionError`.

## In the app

Pick a flow on the **New epic** page. Its params appear under **Parameters**, pre-filled with their defaults.

![The New epic page in Humanize Desktop: polish is picked, its four params appear under Parameters, rounds is set to 9, and starting the epic shows the model's refusal above the task box](/shots/builder-params-app.svg)

*Picking the flow shows its params. If the model rejects a value when you start the epic, the error appears above the task box and nothing runs.*

![The Parameters section alone: a number box for rounds, three buttons for focus, Yes and No buttons for commit, a text box for Commit message](/shots/builder-params-form.svg)

Params use the same controls as [Typed answers](/builder/shapes): `int` renders a number box, `Literal` a button row (a list when it has more than five choices), `bool` two buttons with the affirmative label drawn from a short `description`, and `str` a text box. Required params appear first. A param still at a non-empty default is tagged **Suggested**, and a dot marks the default choice.

The flow's page under **Flows** lists each param by its `title`, or its key when it has none, with its `description`.

## In the terminal

Select the flow in the `/flow` menu. If the flow has params, the **Set up polish** sheet opens before role assignment. You can reopen it from the `Parameters` row on the flow's page.

![The terminal's Set up polish sheet: rounds and focus under the heading Review, commit and Commit message under After, each with its value at the right and its description below, and a Set button](/shots/builder-params-terminal.svg)

| Field type | On the sheet |
| --- | --- |
| `bool` | A switch: press <kbd>enter</kbd> to pick `on` or `off`. |
| `Literal[...]` | Press <kbd>enter</kbd> to open a list of choices. |
| Anything else | Press <kbd>enter</kbd> and type the value. Parsed as the field type, then as JSON. |

Choose **Set** to validate the model. If validation fails, the error appears in red below the list and the sheet stays open.

![The sheet in use: enter on focus drops correctness, style and tests, tests is picked, a commit message is typed, and Set is refused with "Value error, a message needs commit=true"](/shots/builder-params-terminal-set.svg)

## From the command line

Pass `-p key=value` to `hmz exec`.

```sh
hmz exec -f polish -a coder=claude/claude-haiku-4-5 -p budget.duration=10m \
    -p rounds=1,focus=tests -p commit=true "Add a discount code to checkout"
```

![hmz exec running polish with rounds=1, focus=tests and commit=true: three turns, the task, one review that runs the tests, and a commit](/shots/builder-params-exec.svg)

You can repeat `-p` or separate multiple pairs with commas. A comma starts a new param only when followed by `key=`, so `-p message=fix a, b and c` stays a single param. Humanize parses each value as the field's type (such as `1` as `int` for `rounds` and `true` as `bool` for `commit`), falling back to JSON for values like `-p 'tags=["cart","checkout"]'`. Duplicate keys are rejected. `-p budget.<limit>=` sets the run's budget, not a flow param; see [Budgets in a flow](/builder/budgets).

If validation fails, `hmz exec` prints the pydantic error and exits before starting any agent.

![hmz exec with -p rounds=9 refused: 1 validation error for Params, rounds, Input should be less than or equal to 5](/shots/builder-params-refused.svg)

![hmz exec with a message and no commit refused in the validator's own words: Value error, a message needs commit=true](/shots/builder-params-validator.svg)

## From Python

Pass a mapping (parsed like `-p`) or a model instance to the [SDK](/builder/sdk). Invalid params raise `Refused`.

```python
from hmz.sdk import Hmz

Hmz().run(
    "polish",
    "Add a discount code to checkout",
    agents={"coder": "claude/claude-haiku-4-5"},
    params={"rounds": 3, "focus": "tests"},
    budget={"cost": 1},
).run()
```

When a flow [calls another flow](/builder/calling-flows), construct the callee's params with `expected_params`:

```python
polish = load("polish")
await polish(task, agents=agents, envs=envs, params=polish.expected_params(rounds=3))
```

In tests, pass the same mapping to `run_fake`. Invalid params raise `ParamsError`. See [Test a flow](/builder/testing).

```python
# .hmz/tests/test_polish.py
import pytest

from hmz.flows import ParamsError
from hmz.sdk import fakes


async def test_rounds_and_focus_reach_the_prompts() -> None:
    coder = fakes.FakeAgentDriver()
    await fakes.run_fake(
        "polish", "add a discount code", agents={"coder": coder},
        params={"rounds": 1, "focus": "tests"},
    )
    assert coder.prompts == [
        "add a discount code",
        "Review your change for tests only. Fix what you find.",
    ]


async def test_a_message_without_commit_is_refused() -> None:
    coder = fakes.FakeAgentDriver()
    with pytest.raises(ParamsError, match="a message needs commit=true"):
        await fakes.run_fake(
            "polish", "x", agents={"coder": coder}, params={"message": "hi"}
        )
    assert coder.prompts == []
```

## Good to know

- Validation runs before the flow starts, so a rejected run spawns no agents.
- Check multi-field rules in a validator rather than the flow body so failures happen before agents start.
- `ParamsError` is a subclass of `ValueError`.
- Give every field a default unless the flow cannot run without it.
- Renaming a field breaks existing command lines because the old name is rejected as an unknown key.
- The app and terminal remember the last values set for each flow; see [Start an epic](/user/epics).
- When serialised, infinite or NaN `float` values become `"Infinity"`, `"-Infinity"`, or `"NaN"`.
