---
title: Test a flow
description: Run a flow in pytest with scripted agents, an in-memory environment and a scripted person, then assert on what it did.
---

# Test a flow

Use `hmz.sdk.fakes` to run your flow with stand-ins: a scripted agent, an in-memory environment, and a scripted person. No coding agent starts, no machine is touched, and no token is spent.

![A test calls run_fake, which runs the flow in a private daemon with FakeAgentDriver, FakeEnvDriver and FakeOutworlder in place of the real agent, environment and person](/diagrams/builder-testing-1.svg)

## Write a test

Here is a flow where a coder works until the tests pass (at most `rounds` times), then asks a person whether to ship.

```python
# .hmz/flows/fix/__init__.py
from pydantic import BaseModel

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    ShellEnvMixin,
    flow,
)


class Verdict(BaseModel):
    ship: bool = False


class Agents(AgentCollection):
    coder: Agent
    human: Outworlder


class Workspace(LocalEnv, ShellEnvMixin, FilesEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


class Params(FlowParams):
    rounds: int = 3


@flow(agents=Agents, envs=Envs, params=Params)
async def fix(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> str:
    """A coder works until the tests pass, then a person decides whether to ship."""
    coder, human, workspace = agents["coder"], agents["human"], envs["workspace"]
    session = await coder.spawn()
    prompt = task
    for _ in range(params.rounds):
        await coder.run(prompt, session=session, env=workspace)
        status, out, _ = await workspace.exec(["pytest", "-q"])
        if status == 0:
            break
        prompt = f"The tests fail: {out}"
    else:
        return "gave up"
    await workspace.write("NOTES.md", f"{task}: tests pass\n".encode())
    verdict = await human.run(
        "Ship it?", session=await human.spawn(), output_schema=Verdict
    )
    return "shipped" if verdict.ship else "held"
```

Script all three roles, run the flow with `run_fake`, and assert on the return value and what each fake recorded.

```python
# tests/test_fix.py
import pytest

from hmz.flows import ParamsError
from hmz.sdk import fakes


async def test_it_ships_once_the_tests_pass() -> None:
    results = iter([(1, "1 failed", ""), (0, "5 passed", "")])
    coder = fakes.FakeAgentDriver(reply=["Added the code.", "Fixed the total."])
    workspace = fakes.FakeEnvDriver(
        {"shop/checkout.py": "TOTAL = 0\n"},
        run=lambda command, env: next(results) if command[0] == "pytest" else None,
    )
    human = fakes.FakeOutworlder(reply={"ship": True})

    result = await fakes.run_fake(
        "fix",
        "add a discount code to checkout",
        agents={"coder": coder},
        local=workspace,
        outworlder=human,
    )

    assert result == "shipped"
    assert coder.prompts == [
        "add a discount code to checkout",
        "The tests fail: 1 failed",
    ]
    assert workspace.commands == [("pytest", "-q"), ("pytest", "-q")]
    assert workspace.text("NOTES.md").endswith("tests pass\n")
    assert human.asked == ["Ship it?"]


async def test_it_gives_up_after_its_rounds() -> None:
    workspace = fakes.FakeEnvDriver(run={("pytest", "-q"): (1, "1 failed", "")})

    result = await fakes.run_fake("fix", "x", local=workspace, params={"rounds": 2})

    assert result == "gave up"
    assert len(workspace.commands) == 2


async def test_nobody_there_means_held() -> None:
    workspace = fakes.FakeEnvDriver(run={("pytest", "-q"): (0, "5 passed", "")})

    assert await fakes.run_fake("fix", "x", local=workspace) == "held"


async def test_wrong_params_are_refused_before_anything_runs() -> None:
    coder = fakes.FakeAgentDriver()

    with pytest.raises(ParamsError):
        await fakes.run_fake("fix", "x", agents={"coder": coder}, params={"rounds": "many"})

    assert coder.sessions == []
```

`run_fake` is a coroutine. Install pytest-asyncio to run `async def` tests:

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Without pytest-asyncio, wrap the call in `asyncio.run`:

```python
# tests/test_sync.py
import asyncio

from hmz.sdk import fakes


def test_nobody_there_means_held() -> None:
    workspace = fakes.FakeEnvDriver(run={("pytest", "-q"): (0, "5 passed", "")})

    assert asyncio.run(fakes.run_fake("fix", "x", local=workspace)) == "held"
```

Run pytest from the workspace root:

```sh
pytest --no-header -v tests/test_fix.py
```

![A terminal running pytest: the four tests of tests/test_fix.py pass in under a second](/shots/builder-testing-pytest.svg)

*Four runs of the flow, in under a second.*

## What `run_fake` takes

Call `run_fake(flow, task="", *, agents, envs, params, budget, outworlder, local, journal, resume)` to get the flow's return value or raise its exception.

| Argument | What you pass | If you leave it out |
| --- | --- | --- |
| `flow` | A flow's name or ref (looked up from the current directory as `hmz exec -f` does), a path to the flow's directory, or a `Flow` object from `load` | required |
| `task` | The task text | `""` |
| `agents` | By role: a `FakeAgentDriver`, or its reply. For an `Outworlder` role: a `FakeOutworlder`, or its reply | Each required role gets a fake of the requested harness (or `claude`) that answers `ok` |
| `envs` | By role: a `FakeEnvDriver`, or a dict of starting files | Each required role gets an empty fake at `/<role>`, sized as the role requires |
| `params` | A mapping, or an instance of the flow's params class | The defaults |
| `budget` | A `Budget` | Unlimited |
| `outworlder` | A `FakeOutworlder` for the `Outworlder` roles | The person is away |
| `local` | A `FakeEnvDriver` for the `LocalEnv` roles | An empty fake at `/here` |
| `journal`, `resume` | The journal file of a resumable flow, and whether to resume its run. See [Resumable flows](/builder/resumable) | No journal of your own |

Omitted optional roles (`NotRequired`) stay empty.

`run_fake` validates the flow before anything runs. It raises `RequirementError` if a fake in `agents` or `envs` does not meet what its role declares or if you name an undeclared role, and `ParamsError` if parameters fail validation. A `local` fake that lacks a mixin its role needs raises `hmz.sdk.Refused` instead.

## Script an agent

Pass `reply` to `FakeAgentDriver(harness="claude", *, reply=None, ...)` to control how the agent answers each turn:

- A list: one answer per turn, in order. Once exhausted, it returns the default answer.
- One answer: returned for every turn.
- A sync or async function `reply(prompt, *, session, output_schema)`: returns the answer, or `None` for the default.
- `None`: the default answer (`ok`, or the turn's `output_schema` built from its defaults). If the schema has a field without a default, the turn raises `OutputSchemaError`.

An answer can be text, a mapping, a pydantic model, or JSON text. Turns with an `output_schema` validate the answer against that schema. See [Typed answers](/builder/shapes).

| Option | Default | Meaning |
| --- | --- | --- |
| `harness` | `"claude"` | The harness to emulate, including its mixins, session forking, and moving |
| `model`, `effort`, `provider` | `"fake"`, `""`, `""` | Reported model, effort, and account |
| `capabilities` | the harness's | Custom mixins to serve |
| `cost`, `output_tokens`, `seconds` | `0.0`, `1`, `0.0` | Reported USD, tokens, and seconds spent per answer. Nothing waits. Budgets track cost and tokens. See [Budgets in a flow](/builder/budgets) |
| `forks` | the harness's | Whether it can fork a session. See [Branch a conversation](/builder/branching) |
| `names_late` | `False` | Delay assigning a session id until the first turn starts, matching real CLIs |
| `name` | a random codename | The agent's name |

A scripted agent fires the same hooks as a real one: session start on a session's first turn, prompt submit and stop on every turn, and session end on close. A blocking stop hook sends its reason as the next prompt in the same turn, up to 100 times.

### Reach for tools from a reply

Use the `FakeSession` passed to a reply function to act mid-turn like a real agent.

| Call | What it does | Returns |
| --- | --- | --- |
| `await session.tool(name, input)` | Fires the pre-tool-use hook, then the permission-request hook if supported | Whether the tool would run |
| `await session.use(name, input)` | Calls one of the flow's tools | Tool output |
| `await session.run_cli(argv)` | Runs one of the flow's command lines | `(status, stdout, stderr)` |
| `await session.ask(question, options)` | Fires the ask-user hook. Raises `UnsupportedOperation` if unsupported by the harness | The answer, or `None` |
| `await session.notify(message)` | Fires the notification hook | nothing |
| `await session.subagent(name, task="", said="")` | Fires subagent start and stop hooks if supported | `said`, or the blocking stop hook's reason |
| `await session.until_steered()` | Holds the turn open until the flow steers it. An interrupt raises `SessionError`, and the turn's hard deadline raises `DurationExceeded` | The steering text |

```python
# tests/test_reach.py
from hmz.sdk import fakes


async def careful(prompt: str, *, session: fakes.FakeSession, output_schema: object) -> str:
    await session.tool("Bash", {"command": "pytest -q"})
    return "Fixed the total." if prompt.startswith("The tests fail") else "Added the code."


async def test_one_session_takes_every_round() -> None:
    results = iter([(1, "1 failed", ""), (0, "5 passed", "")])
    coder = fakes.FakeAgentDriver("codex", reply=careful, output_tokens=400)
    workspace = fakes.FakeEnvDriver(run=lambda command, env: next(results))

    await fakes.run_fake("fix", "add a discount code", agents={"coder": coder}, local=workspace)

    (session,) = coder.sessions
    assert session.tools == [("Bash", {"command": "pytest -q"}, True)] * 2
    assert session.usage.output_tokens == 800
    assert session.closed
```

See [Hooks](/builder/hooks) and [Tools the agent can call](/builder/tools) for more examples.

## Fake an environment

`FakeEnvDriver(files=None, *, run=None, ...)` holds a working directory in a dictionary. Reads, writes, listings, worktrees, temporary clones, scratch directories, and snapshots operate on copies of that dictionary.

Pass `run` to script command execution:

- A dict mapping commands to `(status, stdout, stderr)`. A command is a tuple of words, or a string for a script.
- A sync or async function `run(command, env)`. Return `None` to fall back to the defaults.

By default, the environment handles `true`, `:`, `false`, `echo`, `cat`, `ls`, `sleep` (which really waits), and `git rev-parse --is-inside-work-tree`. Any other command or unscripted string exits with status 127.

| Option | Default | Meaning |
| --- | --- | --- |
| `files` | none | Starting files relative to the workdir. Text is stored as UTF-8 |
| `workdir` | `"/work"` | Path on the fake machine |
| `backend`, `provider` | `"local"`, `""` | Reported machine kind and provider |
| `capabilities` | every mixin | Environment mixins served |
| `cpu_count`, `memory` | `8`, 64 GiB | Reported CPUs and memory in bytes |
| `gpu_count`, `gpu_memory` | `0`, `0` | Reported GPUs and memory per GPU in bytes |
| `refs` | `("HEAD", "main")` | Git refs known to worktrees and rewinds |
| `repo` | `True` | Whether the workdir is a git repository |

Any terminal opened by the flow is a `FakePty` that echoes input. Typing <kbd>ctrl+d</kbd> ends it with status 0, and killing it ends it with status 137.

## Script the person

Use `FakeOutworlder(reply=None, *, away=False)` to answer questions sent to `Outworlder` roles. `reply` takes the same forms as `FakeAgentDriver`'s, where a mapping populates the requested schema. A function is called as `reply(prompt, *, output_schema)`: it gets no `session`, and `output_schema` is the question's JSON Schema as a dict, or `None` for a plain-text question.

Pass it to `outworlder=`, or pass the reply directly in `agents` (ignored when `outworlder=` is also given):

```python
result = await fakes.run_fake("fix", "x", local=workspace, agents={"human": {"ship": True}})
```

Use `FakeOutworlder(away=True)`, or leave `outworlder` out, to simulate an unavailable person: nothing is asked, and `asked` stays empty. See [The person as an agent](/builder/outworlder).

## Assert on what happened

Inspect your fakes after the run finishes.

| On | Read | It holds |
| --- | --- | --- |
| `FakeAgentDriver` | `prompts` | Every prompt across all sessions, in order |
| | `sessions` | Every `FakeSession` opened |
| | `live`, `peak`, `closed` | Currently open sessions, peak concurrent sessions, and close count |
| `FakeSession` | `prompts` | Every prompt received, including added hook context and stop hook reasons |
| | `requests` | Every turn requested, with limits and schema |
| | `tools` | Every `session.tool` call as `(name, input, allowed)` |
| | `steered` | Every steer as `(text, queued)` |
| | `placement`, `placements` | Current location, and history of where it was opened or moved |
| | `permission`, `skills`, `offered`, `shelved` | Permission, skills, tools, and command lines provided by the flow |
| | `forked_from`, `carried_on` | Parent session if forked, and prior conversation continued |
| | `turns`, `usage`, `closed` | Turn count, resource usage, and whether it is closed |
| | `id`, `named` | Session id (`None` until the first turn with `names_late`), and whether a turn has reached the agent |
| | `driver` | The `FakeAgentDriver` that opened it |
| `FakeEnvDriver` | `files`, `text(path)` | Workdir files as bytes, and a helper to read a file as text |
| | `commands` | Every command executed in the workdir |
| | `machine` | All files on the fake machine by absolute path, including copies and worktrees |
| | `clones`, `scratches` | IDs of remaining temporary clones and scratch directories |
| | `ptys`, `closed` | Opened terminals (`argv`, `typed`, `sizes`, `status`), and close count |
| `FakeOutworlder` | `asked` | Every question prompt |
| | `asks` | Full question records: schema, context, face, and session |
| | `shown` | Every context shown as `(session, context)` |
| | `faces` | Every face used to open a session |

## Good to know

- `run_fake` runs your flow in a private, in-process daemon with a temporary home directory, cleaning it up on return. It never touches your machine's daemon or epics.
- Flow names resolve from the current directory. Run pytest from the workspace root, or pass a path.
- Unscripted commands exit with status 127. If your flow loops on a command's status, script that command in `run`.
- `seconds` only affects reported usage. A `duration` budget measures wall-clock time, and scripted answers return instantly.
- Fakes test your flow's logic, not how a real model responds to your prompts. Run the flow with a real agent before shipping.
- Pass the same fakes to `Hmz.run` when you need to inspect run events. See [The Python SDK](/builder/sdk).
- `hmz.sdk.fakes` exports the type aliases `Answer`, `Reply`, `Command`, and `Handler` for typing your test helpers.
