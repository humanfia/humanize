<script setup>
import FakeRun from '../.vitepress/theme/components/weaver-testing/FakeRun.vue'
</script>

# Testing a flow

In this guide you write pytest tests for your flows that run in milliseconds, need no coding
agent CLI and spend nothing. You test `twice` from [Your first flow](/weaver/writing-a-flow)
first, then a flow with two roles, a shell, a hook, a budget and a resumable state, and
finally set the tests up to run in CI.

Test a flow whenever its logic is worth more than one line: when it loops, branches on an
answer, refuses something, or keeps state across a stop. A test proves what the flow does with
each answer. It does not prove what a model answers, so run the flow for real once, with a
small budget, before you rely on it.

::: info Before you start
- A flow of your own: [Your first flow](/weaver/writing-a-flow).
- [pytest](https://docs.pytest.org/) and [`uv`](https://docs.astral.sh/uv/). The commands
  below bring pytest, humanize and
  [pytest-asyncio](https://pytest-asyncio.readthedocs.io/) along, and add nothing to your
  project.
:::

## How it works

<FakeRun />

The **fake kit**, `hmz.sdk.fakes`, runs your flow exactly as `hmz exec` runs it: the same
lookup by name, the same checks of what each role declares, the same budget, the same hooks.
Only what is on the far side is replaced:

| Real | Fake | What the fake does |
| --- | --- | --- |
| a coding agent CLI | `FakeAgentDriver` | answers each turn from a script, at once, and keeps every prompt |
| a working directory | `FakeEnvDriver` | files in a dictionary, and `exec` answered from a table |
| the person at the prompt | `FakeOutworlder` | answers from a script, or is away |

`fakes.run_fake(flow, task, …)` is `hmz exec` for a test. It takes the flow by the name `-f`
takes, fills every role you name with your fake and every role you leave out with a default
one, runs the flow to the end, and returns what the flow returned.

| Role | Left out, it gets |
| --- | --- |
| an agent role | a fake Claude Code replying `"ok"`, or a fake of the CLI the role is typed as, such as `CodexAgent` |
| an environment role | an empty `FakeEnvDriver` |
| a `LocalEnv` role | `local=`, or an empty `FakeEnvDriver` |
| an `Outworlder` role | a person who is away |
| a `NotRequired` role | nothing: the role is left out, as it would be on a command line |

## Example: test `twice`

From the root of the project that holds `.hmz/flows/twice/`:

::: code-group

```python [tests/test_twice.py]
from hmz.sdk import fakes


async def test_twice_reads_its_own_work_back() -> None:  # ①
    builder = fakes.FakeAgentDriver()  # ②

    await fakes.run_fake(  # ③
        "twice", "add a --dry-run flag", agents={"builder": builder}
    )

    assert builder.prompts == [  # ④
        "add a --dry-run flag",
        "Now review what you just did, and fix anything that is wrong.",
    ]
```

```python [.hmz/flows/twice/__init__.py]
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
    """Do the work, then read it back and fix what is wrong."""
    builder = agents["builder"]
    session = await builder.spawn()
    await builder.run(task, session=session, env=envs["workspace"])
    await builder.run(
        "Now review what you just did, and fix anything that is wrong.",
        session=session,
        env=envs["workspace"],
    )
```

:::

```sh
uvx --with 'hmz @ git+https://github.com/humanfia/humanize.git' \
    --with pytest-asyncio pytest -q -o asyncio_mode=auto
```

```text
.                                                                        [100%]
1 passed in 0.36s
```

### What each part does

1. **An `async def` test.** A flow is async, so its test is too. `-o asyncio_mode=auto` has
   pytest-asyncio run every async test without a marker on each.
2. **`FakeAgentDriver()`** is a fake Claude Code with no script: it answers `"ok"` to every
   turn and keeps every prompt it is sent.
3. **`run_fake("twice", …)`** looks `twice` up from the directory pytest runs in, the way `-f`
   looks one up from where `hmz exec` runs, gives its `builder` role your fake, and runs it to
   the end.
4. **`builder.prompts`** is every prompt the flow sent, in order. The assertion is the flow's
   whole contract: the task first, the review second.

`uvx` runs pytest in a throwaway environment with humanize beside it. To keep the setup in the
repository instead, see [Run the tests in CI](#run-the-tests-in-ci).

## Example: test a flow with two roles

`reviewed` is the flow from [Answers in a shape](/weaver/shapes), grown: an actor keeps one
session and runs `pytest` between its turns, a fresh reviewer's `Review` decides when to stop,
a hook refuses a force push, a `rounds` param bounds it, and the review it owes survives a
stop.

::: details The flow under test: `.hmz/flows/reviewed/__init__.py`

```python
# .hmz/flows/reviewed/__init__.py
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
    working = await actor.spawn()
    prompt = state["owed"] if "owed" in state else task
    for _ in range(params.rounds):
        await actor.run(prompt, session=working, env=workspace)
        code, out, _ = await workspace.exec(["python", "-m", "pytest", "-q"])
        if code != 0:
            prompt = f"The tests fail:\n\n{out}"
            continue
        reading = await reviewer.spawn()
        try:
            review = await reviewer.run(
                REVIEW, session=reading, env=workspace, output_schema=Review
            )
        except HarnessError:
            continue
        if review.done:
            return True
        prompt = state["owed"] = review.notes
    return False
```

:::

The first test scripts the reviewer and the workspace, and leaves the actor to answer
`"ok"`. It lives in `.hmz/tests/` rather than `tests/`, for a reason
[below](#where-to-keep-the-tests):

```python
# .hmz/tests/test_reviewed.py
from pathlib import Path

import pytest

from hmz.flows import Budget, CapabilityMissing, CostExceeded
from hmz.sdk import fakes

GREEN = {("python", "-m", "pytest", "-q"): (0, "3 passed", "")}  # ①
DONE = {"done": True, "notes": ""}  # ②
PUSH = {"command": "git push --force"}


async def test_it_stops_when_the_reviewer_says_done() -> None:
    actor = fakes.FakeAgentDriver()  # ③
    reviewer = fakes.FakeAgentDriver(
        reply=[{"done": False, "notes": "fix the imports"}, DONE]  # ④
    )

    done = await fakes.run_fake(  # ⑤
        "reviewed",
        "write the parser",
        agents={"actor": actor, "reviewer": reviewer},
        local=fakes.FakeEnvDriver(run=GREEN),  # ⑥
    )

    assert done is True  # ⑦
    assert actor.prompts == ["write the parser", "fix the imports"]  # ⑧
```

```sh
uvx --with 'hmz @ git+https://github.com/humanfia/humanize.git' \
    --with pytest-asyncio pytest -q -o asyncio_mode=auto .hmz/tests/test_reviewed.py
```

With every `reviewed` test on this page in the file:

```text
........                                                                 [100%]
8 passed in 0.16s
```

### What each part does

1. **`GREEN`** scripts the workspace: `exec` of exactly that argv answers exit status `0`,
   stdout `"3 passed"` and no stderr. A command is an argv as a tuple, or a script as a
   string.
2. **`DONE`** is a review, written as a mapping. A turn that asks for an `output_schema` reads
   the answer into it, exactly as it reads a real CLI's JSON.
3. **An actor with no script** answers `"ok"`. Its prompts are still recorded.
4. **A list of replies** answers turn by turn: a review that is not done, then one that is.
5. **`run_fake` returns what the flow returned**, here a `bool`.
6. **`local=`** fills every `LocalEnv` role. `reviewed`'s `workspace` is one.
7. **The return value** is the flow's verdict.
8. **The actor's prompts** show the review's `notes` went to it word for word, in the same
   session as the task.

Everything `run_fake` takes after the task is optional:

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

The sections below add one test each to `.hmz/tests/test_reviewed.py`.

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

**An answer out of shape raises `OutputSchemaError`**, a `HarnessError`, so the path your flow
takes on a bad answer is testable too. `{"done": "maybe"}` is not a `bool`:

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
session (`forks=True` one that can). A fake forks as its CLI would: only a session that has
taken a turn, and its first turn is refused if the parent has taken another since the fork,
so run the parent once before forking it and take the fork's first turn before the parent's
next. `model=`, `effort=` and `provider=` set what it reports about itself.

**The driver keeps what happened**, for the test to read afterwards:

| | |
| --- | --- |
| `.prompts` | every prompt its sessions were given, session by session, with what hooks added |
| `.sessions` | every session it opened, each a `FakeSession` |
| `.live`, `.peak` | how many sessions are open now, and the most that were open at once. This is how a test sees a loop let go of sessions it is done with |
| `session.prompts` | one session's prompts |
| `session.requests` | each turn it was asked for, with its limits |
| `session.steered` | what it was steered with, and whether it was queued |
| `session.tools` | each tool its replies reached for, with the input, and whether it was allowed |
| `session.placement.workdir` | where it worked |
| `session.closed`, `session.forked_from` | whether it is over, and the session it was forked from |

## Script the workspace

`FakeEnvDriver(files)` is a working directory held in a dictionary. `files` is what it starts
with, by path, as text or bytes. The flow's reads and writes land in it, and so do the
worktrees, temporary copies, scratch directories and snapshots it derives.

`run=` answers `exec`. Give it a table from command to `(exit status, stdout, stderr)`, as
`GREEN` is, or a function of the command and the environment that returns `None` for commands
it leaves alone. A few argvs work without scripting: `true`, `false`, `echo`, `cat`, `ls`,
`git rev-parse --is-inside-work-tree`, and `sleep`, which really waits. Anything else exits
127, scripts included, so a flow that runs something you did not script says so.

```python
async def test_a_red_suite_never_reaches_the_reviewer() -> None:
    runs = iter([(1, "1 failed", ""), (0, "3 passed", "")])
    reviewer = fakes.FakeAgentDriver(reply=DONE)
    here = fakes.FakeEnvDriver(run=lambda command, env: next(runs))

    await fakes.run_fake("reviewed", "x", agents={"reviewer": reviewer}, local=here)

    assert len(reviewer.prompts) == 1
    assert here.commands == [("python", "-m", "pytest", "-q")] * 2
```

Afterwards:

| | |
| --- | --- |
| `.files` | what is under the working directory, by relative path |
| `.text(path)` | one file, as text |
| `.commands` | every command run there, in order |
| `.machine` | every file on the fake machine, copies and worktrees included |
| `.clones`, `.scratches` | the temporary copies and scratch directories still there, which is how a test checks that a flow [cleans up](/weaver/worktrees#how-long-they-last) after itself |

`refs=` sets the git refs `derive_worktree` and `rewind` know, and `repo=False` makes a
working directory that is not a git repository. [Worktrees, copies and
scratch](/weaver/worktrees) tests a snapshot and a rewind this way.

## Set the params

`params=` takes a mapping, validated into the flow's params exactly as `-p` is. A value of the
wrong type is refused before anything runs:

```python
async def test_it_gives_up_after_its_rounds() -> None:
    reviewer = fakes.FakeAgentDriver(reply={"done": False, "notes": "again"})

    done = await fakes.run_fake(
        "reviewed",
        "x",
        agents={"reviewer": reviewer},
        params={"rounds": 3},
        local=fakes.FakeEnvDriver(run=GREEN),
    )

    assert done is False
    assert len(reviewer.prompts) == 3
```

`params={"rounds": "many"}` raises `ParamsError`. A [params model](/weaver/flow-settings) is a
pydantic model, so its validators are tested the same way.

## Script the person

`FakeOutworlder(reply)` is somebody at the prompt answering from a script, and `.asked` is
every prompt put to them. `reply=` takes the same forms as an agent's, except that a function
is called with the prompt and `output_schema=` only: a person has no session.
`FakeOutworlder(away=True)` is nobody there, and so is leaving it out.

::: details The flow under test: `.hmz/flows/talk/__init__.py`, from [The person as an agent](/weaver/human-agent)

```python
# .hmz/flows/talk/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    flow,
)


class Agents(AgentCollection):
    assistant: Agent
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def talk(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """One conversation, and every line the person types is a turn of it."""
    assistant, human = agents["assistant"], agents["human"]
    conversation = await assistant.spawn()
    listening = await human.spawn()
    said = task
    while said:
        answered = await assistant.run(said, session=conversation, env=envs["workspace"])
        said = await human.run(answered, session=listening)
```

:::

```python
# .hmz/tests/test_talk.py
from hmz.sdk import fakes


async def test_the_person_ends_it_with_an_empty_line() -> None:
    assistant = fakes.FakeAgentDriver(reply=lambda prompt, **_: f"re: {prompt}")
    person = fakes.FakeOutworlder(["more", "done", ""])  # ①

    await fakes.run_fake(
        "talk", "hello", agents={"assistant": assistant}, outworlder=person
    )

    assert assistant.prompts == ["hello", "more", "done"]  # ②
    assert person.asked == ["re: hello", "re: more", "re: done"]  # ③


async def test_nobody_there_ends_it_after_one_turn() -> None:
    assistant = fakes.FakeAgentDriver()

    await fakes.run_fake("talk", "hello", agents={"assistant": assistant})  # ④

    assert assistant.prompts == ["hello"]
```

1. **Three lines typed, the last empty.** The `""` is what ends `talk`'s loop. Without it,
   the person would answer `"ok"` from then on, and the loop would never end.
2. **Each line became a turn** of the assistant, after the task.
3. **`.asked`** is what the person was shown: each of the assistant's answers.
4. **Left out, the person is away**, as under `hmz exec`, and an away person answers `""` at
   once.

Giving the `Outworlder` role a reply, as though it were an agent, does the same:
`agents={"human": ["more", "done", ""]}`.

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
async def test_a_force_push_is_refused() -> None:
    async def pushes(prompt: str, *, session: fakes.FakeSession, **_: object) -> str:
        allowed = await session.tool("Bash", PUSH)  # [!code focus]
        return "pushed" if allowed else "refused"

    actor = fakes.FakeAgentDriver(reply=pushes)
    await fakes.run_fake(
        "reviewed",
        "x",
        agents={"actor": actor, "reviewer": DONE},
        local=fakes.FakeEnvDriver(run=GREEN),
    )

    assert actor.sessions[0].tools == [("Bash", PUSH, False)]  # [!code focus]
```

The hook that refused it is the flow's own `no_force_push`, called exactly as it would be on a
real turn. `agents={"reviewer": DONE}` is the short form: a reply instead of a driver.

## Spend a budget

A fake turn takes no time and costs what you tell it to: `cost=` dollars, `output_tokens=` and
`seconds=` per answer, reported the way a real turn's are. So a budget stops a fake run where
it would stop a real one, and `ctx.usage` adds up:

```python
async def test_the_budget_stops_it() -> None:
    reviewer = fakes.FakeAgentDriver(reply={"done": False, "notes": "again"}, cost=0.5)

    with pytest.raises(CostExceeded):
        await fakes.run_fake(
            "reviewed",
            "x",
            agents={"reviewer": reviewer},
            budget=Budget(cost=2),
            local=fakes.FakeEnvDriver(run=GREEN),
        )
```

## Pick a run up

A resumable flow keeps what it writes to `ctx.state` in a journal. Give `run_fake` a
`journal=`, stop the run, and run it again with `resume=True`:

```python
async def test_it_picks_up_what_it_owed(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    owes = {"done": False, "notes": "fix the imports"}
    with pytest.raises(CostExceeded):
        await fakes.run_fake(
            "reviewed",
            "x",
            agents={"reviewer": fakes.FakeAgentDriver(reply=owes, cost=1.0)},
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

The first run is stopped by its budget right after the review, with `owed` saved. The second
picks it up and hands the owed notes to a fresh actor first. The flows it
[calls](/weaver/calling-flows) are picked up the same way.

## Test the parts that are not turns

Most of what goes wrong in a flow is not the model. Pull those parts out as plain functions,
in the flow's own helper package, and test them as you would any other code. In a flow's own
repository, where `review`'s helpers are in `review/_review/`:

```python
# review/_review/checks.py
def unfinished(text: str) -> bool:
    return "- [ ]" in text
```

```python
# tests/test_checks.py
from _review.checks import unfinished


def test_unfinished() -> None:
    assert unfinished("- [ ] a\n- [x] b")
    assert not unfinished("- [x] a")
```

```sh
uvx --with 'hmz @ git+https://github.com/humanfia/humanize.git' \
    --with pytest-asyncio pytest -q -o asyncio_mode=auto -o pythonpath=review
```

`-o pythonpath=review` lets the test import what the flow imports, from beside the flow.
The flow is then a few lines of glue around code that is already tested. That is the shape to
aim for.

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
testpaths = ["tests", ".hmz/tests"]
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

- **`[dependency-groups] dev`** is what `uv run` installs before it runs anything: humanize,
  pytest and pytest-asyncio. Nothing is published, and nothing is added to a package.
- **`asyncio_mode = "auto"`** is the `-o asyncio_mode=auto` from the commands above.
- **`testpaths`** names both places tests are kept, since pytest does not look inside a
  directory whose name starts with `.` by itself. A flow's own repository, with the flow in a
  directory of its own, needs only `tests`.

```sh
uv run pytest -q
```

```text
...........                                                              [100%]
11 passed in 0.43s
```

That is `twice`'s test, the eight of `reviewed` and the two of `talk`.

## Where to keep the tests

Keep them in `tests/` unless the flow runs your project's own suite. A flow that does, as
`reviewed` runs `python -m pytest -q`, would also collect any flow tests kept there, and
they fail in that run on `import hmz`. Keep such a flow's tests in `.hmz/tests/`
instead, beside the flows: pytest does not look inside a directory whose name starts with `.`
unless it is named, so your suite never sees them, and `pytest .hmz/tests` or the
`testpaths` above runs them. The [tutorial](/weaver/tutorials/build-under-test) does the same.

## Variations

**Test a flow by path.** `run_fake("./review", …)` runs the flow at that path, which is how a
flow's own repository tests it without [installing](/weaver/flowverses) it.

**Test the flow object.** `run_fake` also takes what `load(…)` returns, for a flow you only
reach by ref.

**Test the rest in the same file.** A flow's pure helpers, its params model and its `Review`
model are ordinary Python, and belong beside the flow's own tests.

## Pitfalls

- **Run pytest from the project root.** A name is looked up from the directory pytest runs in.
  From anywhere else, `run_fake("twice", …)` raises `FlowNotFound`. A path starts with `.`, `/`
  or `~`, and a relative one, such as `run_fake("./flows/review", …)`, is relative to that
  directory too. Without the `./`, `flows/review` is a name, the flow `review` of a user
  `flows`, and not a path.
- **A command you did not script exits 127.** Leave `local=` out of a test of `reviewed`, and
  every `pytest` it runs fails, so the reviewer is never asked.
- **A reply that waits needs a hard deadline.** A turn its reply holds open, such as one
  waiting on `until_steered()` that nobody steers, ends at
  `Budget(duration=…, graceful=False)` with `DurationExceeded`. Under a graceful budget, the
  default, it waits for ever, and so does the test.
- **Fakes prove the flow, not the model.** Before you [publish a flow](/weaver/flowverses),
  run it once for real with a small budget.

## Next steps

- [Answers in a shape](/weaver/shapes), [Params of its own](/weaver/flow-settings) and
  [Hooks](/weaver/hooks): what the tests above script
- [Flowverses](/weaver/flowverses), to publish what you tested
- [Reference › Testing a flow](/reference/flows#testing-a-flow):
  [`run_fake`](/reference/flows#run-fake),
  [`FakeAgentDriver`](/reference/flows#fakeagentdriver),
  [`FakeSession`](/reference/flows#fakesession),
  [`FakeEnvDriver`](/reference/flows#fakeenvdriver) and
  [`FakeOutworlder`](/reference/flows#fakeoutworlder)
