# Testing a flow

Test a flow without a coding agent, so each test runs in milliseconds and costs nothing:
`hmz.runtime.flowing.fakes` has an agent that answers from a script, an environment that is a
dictionary of files, and a person who answers from a list or is away — and runs the flow on
them exactly as `hmz exec` runs it on the real ones.

## Run the flow on fakes

Take the flow from [Answers in a shape](/weaver/shapes), grown a little: an actor that keeps a
session, `pytest` between its turns, a reviewer whose `Review` ends the loop, a `rounds` param,
a hook that refuses a force push, and a review it keeps owing across a stop.

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

Its test:

```python
# tests/test_reviewed.py
from pathlib import Path

import pytest

from hmz.flows import Budget, CapabilityMissing, CostExceeded
from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeEnvDriver, FakeSession, run_fake

FLOW = str(Path(__file__).parent.parent / ".humanize" / "flows" / "reviewed")

#: What the workspace answers: the suite is green.
GREEN = {("python", "-m", "pytest", "-q"): (0, "3 passed", "")}


async def test_it_stops_when_the_reviewer_says_done() -> None:
    actor = FakeAgentDriver()
    reviewer = FakeAgentDriver(
        reply=[{"done": False, "notes": "fix the imports"}, {"done": True, "notes": ""}]
    )
    done = await run_fake(
        FLOW,
        "write the parser",
        agents={"actor": actor, "reviewer": reviewer},
        local=FakeEnvDriver(run=GREEN),
    )
    assert done is True
    assert actor.prompts == ["write the parser", "fix the imports"]
```

`run_fake` takes the flow — or a ref, loaded from where it is called, as `FLOW` is here — the
task, and whatever you want to say about the run: a driver per role, a driver per environment,
the params, a budget. It runs the flow through the engine every way in uses, so the flow is
checked against what it declared, handed views granted exactly that, and held to its budget.
What it returns is what the flow returned.

**What you leave out is faked for you.** A required agent role nobody gave a driver for is a
fake of the CLI it asks for — Claude Code, which serves every mixin, where it asks for none —
replying `"ok"`. A required environment role gets an empty `FakeEnvDriver`; a `LocalEnv` role
gets `local=`, an empty one where that is not given either. An `Outworlder` role is a person who
is away. A `NotRequired` role nobody gave is left out, as it would be on a command line, so a
test of the branch that uses one gives it a driver. The budget is unlimited, the params are the
defaults.

Tests are `async def`: run them with [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
and `asyncio_mode = "auto"` in your pytest configuration, or mark each one.

## Script an agent

`FakeAgentDriver(reply=…)` answers every turn from a script:

| `reply=` | Each turn answers |
| --- | --- |
| a string, a model, a mapping | that, every turn |
| a list | the next item, and what nothing answers once it runs out |
| a function of the prompt | what it returns — sync or async, given `output_schema=` and `session=` as keywords |
| nothing | `"ok"`, or the schema built from its defaults |

Asked for an `output_schema`, an answer is read as that schema: a mapping or JSON text is
validated into it, and one that does not validate raises `OutputSchemaError` as a real CLI's
would. A function is how a test answers one prompt one way and another another:

```python
def reply(prompt: str, *, output_schema=None, **_) -> object:
    if output_schema is not None:
        return {"done": True, "notes": ""}
    return f"did {prompt}"
```

Afterwards the driver says what happened: `.prompts` is every prompt any of its sessions was
given, hooks' additions included, in order; `.sessions` is every session it opened, each a
`FakeSession` with its own `.prompts`, the `.requests` it was asked for with their limits,
what it was `.steered` with, the `.tools` its answers reached for, whether it is `.closed`, and
the session it was `.forked_from`. `.live` is how many of its sessions are open now and `.peak`
the most that were open at once, which is how a test sees a loop let go of the sessions it is
done with.

`FakeAgentDriver("codex")` is Codex: it serves exactly what Codex serves, so a flow that asks
for more is refused the way it would be with the real one:

```python
async def test_a_cli_without_the_hook_is_refused() -> None:
    with pytest.raises(CapabilityMissing):
        await run_fake(FLOW, "x", agents={"actor": FakeAgentDriver("pi")})
```

`capabilities=` says otherwise, `forks=False` is a CLI that cannot fork, and `model=`,
`effort=` and `provider=` are what it says it is.

## Spend, and budgets

A fake turn takes no time and costs what it is told to: `cost=` dollars, `output_tokens=` and
`seconds=` apiece, reported the way a real turn's are. So a budget stops a fake run exactly
where it would stop a real one, and `ctx.usage` adds up:

```python
async def test_the_budget_stops_it() -> None:
    reviewer = FakeAgentDriver(reply={"done": False, "notes": "again"}, cost=0.5)
    with pytest.raises(CostExceeded):
        await run_fake(FLOW, "x", agents={"reviewer": reviewer}, budget=Budget(cost=2),
                       local=FakeEnvDriver(run=GREEN))
```

A turn held open by its reply — one waiting on `until_steered()` — is cut off at a hard
deadline, as a real one is, and raises `DurationExceeded`.

## Script an environment

`FakeEnvDriver(files)` is a working directory held in a dictionary: what is in it to start
with, by path, text or bytes. `read` and `write` read and write it; worktrees, temporary copies
and scratch directories are copies of it in the same dictionary, with the ids they were made
under.

`exec` is answered by `run=` — a table from a command to `(exit status, stdout, stderr)`, as
`GREEN` above, or a function of the command and the environment, answering `None` for the ones
it leaves alone. A command is an argv as a tuple, or a script as a string. What `run=` leaves
is answered by a handful of defaults — `true`, `false`, `echo`, `cat`, `ls`, `sleep` and `git
rev-parse --is-inside-work-tree` — and anything else exits 127, so a flow that runs something
nobody scripted says so.

```python
async def test_a_red_suite_never_reaches_the_reviewer() -> None:
    runs = iter([(1, "1 failed", ""), (0, "3 passed", "")])
    reviewer = FakeAgentDriver(reply={"done": True, "notes": ""})
    here = FakeEnvDriver(run=lambda command, env: next(runs))
    await run_fake(FLOW, "x", agents={"reviewer": reviewer}, local=here)
    assert len(reviewer.prompts) == 1
    assert here.commands == [("python", "-m", "pytest", "-q")] * 2
```

Afterwards it says what happened: `.files` is what is under the workdir now, `.text(path)` one
file as text, `.commands` every command run there, `.machine` every file on the fake machine —
copies and worktrees included — and `.clones` and `.scratches` the temporary copies and scratch
directories still there, which is how a test sees them [cleaned
up](/weaver/worktrees#how-long-they-last). A temporary copy is held by whoever made it until
the run that made it is over, and a run resumed on the same fake takes it again as it was left.
`refs=` is the git refs `derive_worktree` knows, and `repo=False` a workdir that is not a
repository.

## Script the person

`FakeOutworlder(reply)` is somebody at the prompt answering from a script, with the same
`reply=` forms an agent takes; `.asked` is every prompt put to them. `away=True` is nobody
there. Hand it to `run_fake` as `outworlder=`, or give the `Outworlder` role a reply as though
it were an agent:

```python
await run_fake(talk, "hello", agents={"human": ["more", "done", ""]})
```

## Exercise the hooks

A fake session fires what a real one does on every turn — `SESSION_START`,
`USER_PROMPT_SUBMIT`, `STOP` — and `SESSION_END` as it closes, and a `STOP` hook that blocks
keeps the turn going with its reason as the next prompt. The moments that come from inside a
turn are reached by a scripted reply, through the `session` it is given:

| From a reply | Fires |
| --- | --- |
| `await session.tool(name, input)` | `PRE_TOOL_USE`, then `PERMISSION_REQUEST` where the CLI serves it; answers whether the tool would run |
| `await session.ask(question, options)` | `ASK_USER`; answers the answer, or `None` |
| `await session.notify(message)` | `NOTIFICATION` |
| `await session.subagent(name, task, said)` | `SUBAGENT_START` and `SUBAGENT_STOP`, where served |
| `await session.until_steered()` | nothing: waits for a `steer`, and answers what it said |

```python
async def test_a_force_push_is_refused() -> None:
    async def pushes(prompt: str, *, session: FakeSession, **_: object) -> str:
        allowed = await session.tool("Bash", {"command": "git push --force"})
        return "pushed" if allowed else "refused"

    actor = FakeAgentDriver(reply=pushes)
    reviewer = FakeAgentDriver(reply={"done": True, "notes": ""})
    await run_fake(FLOW, "x", agents={"actor": actor, "reviewer": reviewer},
                   local=FakeEnvDriver(run=GREEN))
    assert actor.sessions[0].tools == [("Bash", {"command": "git push --force"}, False)]
```

The hook is the flow's own, hung by the flow, and heard exactly as it would be on a real turn.

## Pick a run up

A resumable flow keeps what it wrote to `ctx.state` in a journal. Give `run_fake` one, stop the
run, and run it again with `resume=True`:

```python
async def test_it_picks_up_the_review_it_owed(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    reviewer = FakeAgentDriver(reply={"done": False, "notes": "fix the imports"}, cost=1.0)
    with pytest.raises(CostExceeded):
        await run_fake(FLOW, "x", agents={"reviewer": reviewer}, budget=Budget(cost=0.5),
                       journal=journal, local=FakeEnvDriver(run=GREEN))
    actor = FakeAgentDriver()
    await run_fake(FLOW, "x", agents={"actor": actor, "reviewer": {"done": True, "notes": ""}},
                   journal=journal, resume=True, local=FakeEnvDriver(run=GREEN))
    assert actor.prompts[0] == "fix the imports"
```

The flows it calls are picked up too, where they are called as they were — which is the same
test, a level down.

## Test the parts that are not turns

Most of what goes wrong in a flow is not the model. Pull those parts out as plain functions and
test them normally:

```python
def unfinished(text: str) -> bool:
    return "- [ ]" in text


def test_unfinished() -> None:
    assert unfinished("- [ ] a\n- [x] b")
    assert not unfinished("- [x] a")
```

Then the flow is a few lines of glue around things that are already tested. That is the shape
to aim for.

A [params model](/weaver/flow-settings) is a pydantic model, so test its validators the same
way:

```python
import pytest
from pydantic import ValidationError


def test_fast_and_careful_do_not_go_together() -> None:
    with pytest.raises(ValidationError):
        Params(fast=True, careful=True)
```

## Run the real thing deliberately

Sort your tests by what is on the other side of them, which is what humanize itself does. It
keeps three directories:

| | |
| --- | --- |
| `tests/unit/` | Calls the code and asserts. A flow on the fake kit, a params model, a function. No agent, no process |
| `tests/integration/` | Everything on the far side is something you wrote: a stand-in CLI, a fake server, a mock LLM service |
| `tests/system/` | The real thing — a coding agent CLI signed in as you signed it in — and real tokens |

The first two are the gate: they want a checkout and nothing else, so they run everywhere and on
every change. The third is a run somebody makes on purpose.

```sh
uv run pytest tests/unit            # the fast loop
uv run pytest                       # the gate: unit and integration
uv run pytest --run-agents          # also the system tier, which spends real tokens
```

`--run-agents` is not a pytest option — it is one humanize registers, and your project has to
register its own. In the root `conftest.py`:

```python
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "agent: drives a real coding agent CLI")


def pytest_addoption(parser):
    parser.addoption("--run-agents", action="store_true", default=False)


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-agents"):
        return
    skip = pytest.mark.skip(reason="needs --run-agents (drives real agents, costs tokens)")
    for item in items:
        if "agent" in item.keywords:
            item.add_marker(skip)
```

The root `conftest.py` and no other — `pytest_addoption` is read there alone. Then put
`pytest.mark.agent` on the tests, keep `--strict-markers` on so a typo in the name is an error
rather than a selection of nothing, and set `-ra` in your `addopts`: the summary of an ordinary
run then names every agent test that sat out and why, and a test that quietly stops running
says so.

Keep the tier out of your CI the way humanize keeps it out of its own — with
`--ignore=tests/system` rather than a marker expression that deselects it. Deselecting still
collects, and collecting is importing: a module that reaches for a CLI your runner has not got
is a collection error, which fails a job about tests it was never going to run. Locally you want
the opposite, which is what `-ra` and the skip above are for.

## See also

- [Answers in a shape](/weaver/shapes)
- [Params of its own](/weaver/flow-settings)
- [Hooks](/weaver/hooks)
- [Flowverses](/weaver/flowverses) — publishing what you tested
- [Reference › Flows › Testing a flow](/reference/flows#testing-a-flow)
