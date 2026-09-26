# Testing a flow

The fake kit runs your flow exactly as `hmz exec` runs it, but on agents that answer from a
script and a workspace held in memory. A test takes milliseconds, needs no coding agent CLI,
and spends nothing.

## Try it

Test `twice`, the flow from [Writing a flow](/weaver/writing-a-flow), from the root of the
project it lives in:

::: code-group

```python [tests/test_twice.py]
from hmz.sdk import fakes


async def test_twice_reads_its_own_work_back() -> None:
    builder = fakes.FakeAgentDriver()

    await fakes.run_fake(
        "twice", "add a --dry-run flag", agents={"builder": builder}
    )

    assert builder.prompts == [
        "add a --dry-run flag",
        "Now review what you just did, and fix anything that is wrong.",
    ]
```

```python [.humanize/flows/twice/__init__.py]
"""Two passes: do the work, then read it back and fix what is wrong."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def twice(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Two passes: do the work, then read it back and fix what is wrong."""
    builder = agents["builder"]
    session = await builder.spawn(env=envs["workspace"])
    await builder.run(task, session=session)
    await builder.run(
        "Now review what you just did, and fix anything that is wrong.",
        session=session,
    )
```

:::

```sh
uvx --with 'hmz @ git+https://github.com/humanfia/humanize.git' \
    --with pytest-asyncio pytest -q -o asyncio_mode=auto
```

```console
.                                                                        [100%]
1 passed in 0.12s
```

`run_fake` found `twice` by the name `-f` takes, gave its `builder` role your fake, and ran
the flow to the end. The fake answered `"ok"` to each turn and kept every prompt it was sent,
so the test asserts on what the flow said.

`uvx` runs pytest with humanize and [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
beside it, and adds nothing to your project. To keep that setup in the repository instead, see
[Run the tests in CI](#run-the-tests-in-ci).

## What `run_fake` takes

The rest of this page tests a bigger flow: `reviewed`, from [Answers in a
shape](/weaver/shapes), with a few additions. An actor keeps one session, `pytest` runs
between its turns, and a fresh reviewer's `Review` decides when to stop. It also has a
`rounds` param, a hook that refuses a force push, and a review it keeps owing across a stop.

::: details The flow under test: `.humanize/flows/reviewed/__init__.py`

```python
"""Build under review, and stop when the reviewer says there is nothing left."""

from pydantic import BaseModel, ConfigDict, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    LocalEnv,
    PermissionRequestHookAgentMixin,
    PermissionRequestHookParams,
    PermissionRequestHookResult,
    ShellEnvMixin,
    flow,
)

REVIEW = "Read the repository and the current diff. Is anything left to do or to fix?"


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, passed on word for word.")


class Builder(Agent, PermissionRequestHookAgentMixin): ...


class Agents(AgentCollection):
    actor: Builder
    reviewer: Agent


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


class Params(FlowParams):
    rounds: int = 12


async def no_force_push(params: PermissionRequestHookParams) -> PermissionRequestHookResult:
    if "push --force" in str(params.input.get("command", "")):
        return PermissionRequestHookResult(allow=False, reason="not on this branch")
    return PermissionRequestHookResult()


@flow(agents=Agents, envs=Envs, params=Params, resumable=True)
async def reviewed(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> bool:
    """Build under review, and stop when the reviewer says there is nothing left."""
    actor, reviewer, workspace = agents["actor"], agents["reviewer"], envs["workspace"]
    state = ctx.state
    assert state is not None
    actor.on_permission_request(no_force_push)
    working = await actor.spawn(env=workspace)
    prompt = state["owed"] if "owed" in state else task
    for _ in range(params.rounds):
        await actor.run(prompt, session=working)
        code, out, _ = await workspace.exec(["python", "-m", "pytest", "-q"])
        if code != 0:
            prompt = f"The tests fail:\n\n{out}"
            continue
        reading = await reviewer.spawn(env=workspace)
        try:
            review = await reviewer.run(REVIEW, session=reading, output_schema=Review)
        except HarnessError:
            continue
        if review.done:
            return True
        prompt = state["owed"] = review.notes
    return False
```

:::

Its first test scripts the reviewer and the workspace, and leaves the actor to answer `"ok"`:

```python
# tests/test_reviewed.py
from pathlib import Path

import pytest

from hmz.flows import Budget, CapabilityMissing, CostExceeded
from hmz.sdk import fakes

#: What the workspace answers: the suite is green.
GREEN = {("python", "-m", "pytest", "-q"): (0, "3 passed", "")}
#: What the reviewer answers when there is nothing left.
DONE = {"done": True, "notes": ""}


async def test_it_stops_when_the_reviewer_says_done() -> None:
    actor = fakes.FakeAgentDriver()
    reviewer = fakes.FakeAgentDriver(
        reply=[{"done": False, "notes": "fix the imports"}, DONE]
    )
    done = await fakes.run_fake(
        "reviewed",
        "write the parser",
        agents={"actor": actor, "reviewer": reviewer},
        local=fakes.FakeEnvDriver(run=GREEN),
    )
    assert done is True  # [!code highlight]
    assert actor.prompts == ["write the parser", "fix the imports"]  # [!code highlight]
```

`run_fake` returns what the flow returned. Everything it takes after the task is optional:

```python
await fakes.run_fake(
    "reviewed",               # the name -f takes, or a path
    "write the parser",       # the task
    agents={...},             # per role: a driver, or what it replies
    envs={...},               # per role: a driver, or its files
    local=...,                # where every LocalEnv role works
    params={"rounds": 3},     # the defaults where left out
    budget=Budget(cost=2),    # unlimited where left out
    outworlder=...,           # the person; away where left out
    journal=..., resume=...,  # stop a run, then pick it up
)
```

Run pytest from the project root: a name is looked up from the directory pytest runs in, the
way `-f` looks one up from where `hmz exec` runs.

The flow is held to what it declares, as `hmz exec` holds it: a role that asks for more than
its fake serves is refused, and a budget stops the run where it would stop a real one.

**What you leave out is faked for you**, so a test names only the roles it cares about:

| Role | Left out, it gets |
| --- | --- |
| an agent role | a fake Claude Code replying `"ok"`, or a fake of the CLI the role is typed as, such as `CodexAgent` |
| an environment role | an empty `FakeEnvDriver` |
| a `LocalEnv` role | `local=`, or an empty `FakeEnvDriver` |
| an `Outworlder` role | a person who is away |
| a `NotRequired` role | nothing: the role is left out, as it would be on a command line |

## Script an agent

`FakeAgentDriver(reply=…)` answers every turn from a script:

| `reply=` | Each turn answers |
| --- | --- |
| a string, a pydantic model or a mapping | that, every turn |
| a list | the next item, turn by turn. Once the list runs out, what nothing answers |
| a function | what it returns. It is called with the prompt, and with `output_schema=` and `session=` as keywords, and may be sync or async |
| nothing | `"ok"`, or the schema built from its defaults |

A function answers one prompt one way and another prompt another:

```python
def reply(prompt: str, *, output_schema=None, **_) -> object:
    if output_schema is not None:
        return {"done": True, "notes": ""}
    return f"did {prompt}"
```

**A turn that asks for an `output_schema` reads the answer into it.** A mapping or JSON text is
validated, and one that does not fit raises `OutputSchemaError`, a `HarnessError`. So the path
your flow takes on a bad answer is testable too:

```python
async def test_a_malformed_review_is_skipped() -> None:
    reviewer = fakes.FakeAgentDriver(reply=[{"done": "maybe"}, DONE])
    done = await fakes.run_fake(
        "reviewed",
        "x",
        agents={"reviewer": reviewer},
        local=fakes.FakeEnvDriver(run=GREEN),
    )
    assert done is True
    assert len(reviewer.prompts) == 2
```

**The driver keeps what happened**, for the test to read afterwards:

| | |
| --- | --- |
| `.prompts` | every prompt its sessions were given, session by session, with what hooks added |
| `.sessions` | every session it opened, each a `FakeSession` |
| `.live`, `.peak` | how many sessions are open now, and the most that were open at once. This is how a test sees a loop let go of sessions it is done with |
| `session.prompts` | one session's prompts |
| `session.requests` | each turn it was asked for, with its limits |
| `session.steered` | what it was steered with |
| `session.tools` | each tool its replies reached for, with the input, and whether it was allowed |
| `session.closed`, `session.forked_from` | whether it is over, and the session it was forked from |

**A fake is one CLI, Claude Code unless you name another.** It serves exactly what that CLI
serves, so a flow that asks for more is refused before its first turn, as it would be for
real. `reviewed`'s actor needs a permission hook, which pi does not serve:

```python
async def test_a_cli_without_the_hook_is_refused() -> None:
    pi = fakes.FakeAgentDriver("pi")
    with pytest.raises(CapabilityMissing):
        await fakes.run_fake("reviewed", "x", agents={"actor": pi})
```

`capabilities=` overrides what it serves, and `forks=False` makes a CLI that cannot fork a
session. `model=`, `effort=` and `provider=` set what it reports about itself.

## Script the workspace

`FakeEnvDriver(files)` is a working directory held in a dictionary. `files` is what it starts
with, by path, as text or bytes. The flow's reads and writes land in it, and so do the
worktrees, temporary copies and scratch directories it derives.

`run=` answers `exec`. Give it a table from command to `(exit status, stdout, stderr)`, as
`GREEN` is, or a function of the command and the environment that returns `None` for commands
it leaves alone. A command is an argv as a tuple, or a script as a string. A few argvs work
without scripting: `true`, `false`, `echo`, `cat`, `ls`, `git rev-parse --is-inside-work-tree`,
and `sleep`, which really waits. Anything else exits 127, scripts included, so a flow that runs
something you did not script says so.

```python
async def test_a_red_suite_never_reaches_the_reviewer() -> None:
    runs = iter([(1, "1 failed", ""), (0, "3 passed", "")])
    reviewer = fakes.FakeAgentDriver(reply=DONE)
    here = fakes.FakeEnvDriver(run=lambda command, env: next(runs))
    await fakes.run_fake(
        "reviewed", "x", agents={"reviewer": reviewer}, local=here
    )
    assert len(reviewer.prompts) == 1
    assert here.commands == [("python", "-m", "pytest", "-q")] * 2
```

Afterwards, `.files` is what is under the working directory, `.text(path)` is one file as
text, and `.commands` is every command run there. `.machine` is every file on the fake
machine, copies and worktrees included. `.clones` and `.scratches` are the temporary copies and
scratch directories still there, which is how a test checks that a flow [cleans
up](/weaver/worktrees) after itself. `refs=` sets the git refs `derive_worktree` knows, and
`repo=False` makes a working directory that is not a git repository.

## Script the person

`FakeOutworlder(reply)` is somebody at the prompt answering from a script, and `.asked` is
every prompt put to them. `reply=` takes the same forms as an agent's, except that a function
is called with the prompt and `output_schema=` only: a person has no session.
`FakeOutworlder(away=True)` is nobody there.

Hand one to `run_fake` as `outworlder=`, or give the `Outworlder` role a reply as though it
were an agent. For `talk`, from [The person as an agent](/weaver/human-agent), saved as
`.humanize/flows/talk/__init__.py`:

```python
await fakes.run_fake(
    "talk", "hello", agents={"human": ["more", "done", ""]}
)
```

The `""` at the end is what ends `talk`'s loop. Without it, the person would answer `"ok"`
from then on.

## Reach the hooks

A fake session fires the hooks a real one fires on every turn: `SESSION_START`,
`USER_PROMPT_SUBMIT` and `STOP`, and `SESSION_END` as it closes. A `STOP` hook that blocks
keeps the turn going, with its reason as the next prompt.

The hooks that fire from inside a turn are reached by a reply function, through the `session`
it is given:

| In a reply | Fires |
| --- | --- |
| `await session.tool(name, input)` | `PRE_TOOL_USE`, then `PERMISSION_REQUEST` where the CLI serves it. Returns whether the tool would run |
| `await session.ask(question, options)` | `ASK_USER`. Returns the answer, or `None`. Raises `UnsupportedOperation` on a CLI that cannot ask |
| `await session.notify(message)` | `NOTIFICATION` |
| `await session.subagent(name, task, said)` | `SUBAGENT_START` and `SUBAGENT_STOP`, where the CLI serves them |
| `await session.until_steered()` | nothing. Waits for a `steer`, and returns what it said |

```python
PUSH = {"command": "git push --force"}


async def test_a_force_push_is_refused() -> None:
    async def pushes(
        prompt: str, *, session: fakes.FakeSession, **_: object
    ) -> str:
        allowed = await session.tool("Bash", PUSH)  # [!code focus]
        return "pushed" if allowed else "refused"

    actor = fakes.FakeAgentDriver(reply=pushes)
    reviewer = fakes.FakeAgentDriver(reply=DONE)
    await fakes.run_fake(
        "reviewed",
        "x",
        agents={"actor": actor, "reviewer": reviewer},
        local=fakes.FakeEnvDriver(run=GREEN),
    )
    assert actor.sessions[0].tools == [("Bash", PUSH, False)]  # [!code focus]
```

The hook that refused it is the flow's own `no_force_push`, called exactly as it would be on a
real turn.

## Spend a budget

A fake turn takes no time and costs what you tell it to: `cost=` dollars, `output_tokens=` and
`seconds=` per answer, reported the way a real turn's are. So a budget stops a fake run where
it would stop a real one, and `ctx.usage` adds up:

```python
async def test_the_budget_stops_it() -> None:
    reviewer = fakes.FakeAgentDriver(
        reply={"done": False, "notes": "again"}, cost=0.5
    )
    with pytest.raises(CostExceeded):
        await fakes.run_fake(
            "reviewed",
            "x",
            agents={"reviewer": reviewer},
            budget=Budget(cost=2),
            local=fakes.FakeEnvDriver(run=GREEN),
        )
```

::: warning A reply that waits needs a hard deadline
A turn its reply holds open, such as one waiting on `until_steered()` that nobody steers, ends
at `Budget(duration=…, graceful=False)` with `DurationExceeded`. Under a graceful budget, the
default, it waits for ever, and so does the test.
:::

## Pick a run up

A resumable flow keeps what it writes to `ctx.state` in a journal. Give `run_fake` a
`journal=`, stop the run, and run it again with `resume=True`:

```python
async def test_it_picks_up_what_it_owed(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    owes = {"done": False, "notes": "fix the imports"}
    reviewer = fakes.FakeAgentDriver(reply=owes, cost=1.0)
    with pytest.raises(CostExceeded):
        await fakes.run_fake(
            "reviewed",
            "x",
            agents={"reviewer": reviewer},
            budget=Budget(cost=0.5),
            journal=journal,
            local=fakes.FakeEnvDriver(run=GREEN),
        )

    actor = fakes.FakeAgentDriver()
    await fakes.run_fake(
        "reviewed",
        "x",
        agents={"actor": actor, "reviewer": DONE},
        journal=journal,
        resume=True,
        local=fakes.FakeEnvDriver(run=GREEN),
    )
    assert actor.prompts[0] == "fix the imports"
```

The flows it [calls](/weaver/calling-flows) are picked up the same way.

## Test the parts that are not turns

Most of what goes wrong in a flow is not the model. Pull those parts out as plain functions
and test them as you would any other code:

```python
def unfinished(text: str) -> bool:
    return "- [ ]" in text


def test_unfinished() -> None:
    assert unfinished("- [ ] a\n- [x] b")
    assert not unfinished("- [x] a")
```

The flow is then a few lines of glue around code that is already tested. That is the shape to
aim for.

A [params model](/weaver/flow-settings) is a pydantic model, so test its validators the same
way:

```python
import pytest
from pydantic import ValidationError


def test_fast_and_careful_do_not_go_together() -> None:
    with pytest.raises(ValidationError):
        Params(fast=True, careful=True)
```

## Run the tests in CI

Keep the setup in the repository, and every checkout runs the tests with `uv run pytest`:

::: code-group

```toml [pyproject.toml]
[project]
name = "my-flows"
version = "0"
requires-python = ">=3.12"

[dependency-groups]
dev = [
    "hmz @ git+https://github.com/humanfia/humanize.git",
    "pytest",
    "pytest-asyncio",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

```yaml [.github/workflows/test.yml]
name: test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.0.1
      - run: uv run pytest
```

:::

A test on fakes proves what the flow does with each answer, not what a model answers. Before
you [publish a flow](/weaver/flowverses), run it once for real with a small `-b`.

## See also

- [Answers in a shape](/weaver/shapes)
- [Params of its own](/weaver/flow-settings)
- [Hooks](/weaver/hooks)
- [Flowverses](/weaver/flowverses), to publish what you tested
- [Reference › Flows › Testing a flow](/reference/flows#testing-a-flow)
