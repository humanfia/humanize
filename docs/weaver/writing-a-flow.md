# Writing a flow

A **flow** is a directory whose `__init__.py` holds an `async` function marked `@flow`, and
that function drives the agents. A weaver writes one when the same agents should be run the
same way again and again, rather than typed out afresh each time.

## Write the flow

```sh
mkdir -p .humanize/flows/twice
```

```python
# .humanize/flows/twice/__init__.py
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

Three classes and a function. `Agents` says the flow drives one agent, which it calls
`builder`. `Envs` says that agent works in `workspace`, the directory the run was started in.
`FlowParams` says the flow takes no [params](/weaver/flow-settings). The function is what
happens.

## Run the flow

```sh
hmz exec -f twice -a builder=claude/claude-opus-5:high -b cost=5 \
    "add a --dry-run flag to calc.py"
```

`-a` names the agent **by its role**: `builder=` and then the CLI, the model and the effort,
with `@<account>` after the CLI where it should run as one of [your
accounts](/user/providers). `-b` is what the run may spend — `cost=` in dollars,
`duration=` on the clock, `output_tokens=` written — and **`hmz exec` will not start a flow
without one**. `workspace` has no `-e`: a role typed `LocalEnv` is the directory you are in,
and humanize fills it itself.

`/flow` offers it in the interface too, beside the flows humanize ships and everything in every
[**flowverse**](/weaver/flowverses) fetched here. A flowverse is a place flows live, and your
own two directories are places like any other: `.humanize/flows` here is `local`,
`~/.humanize/flows` is `user`. **←** and **→** step between the places, and opening a flow
asks what each of its roles runs, by the name the flow gave it.

## The contract, in four rules

**1. An `async def`, marked `@flow(agents=…, envs=…, params=…)`.** It is called with the task
and four keywords — `agents`, `envs`, `params` and `ctx`. A plain `def`, or a function that
cannot be called that way, is refused as the flow is defined, with `FlowDefinitionError`; so
is a name no ref could name — letters, digits, `_`, `.` and `-`.

**2. The agents are a `TypedDict` of roles.** Subclass `AgentCollection`, one key per agent,
each typed `Agent` or a class of your own that [asks for more](#ask-for-what-the-agent-must-do).
The environments are the same shape, subclassing `EnvCollection`.

```python
from typing import NotRequired


class Agents(AgentCollection):
    builder: Agent
    reviewer: NotRequired[Agent]     # may be left out; the flow asks `"reviewer" in agents`
```

A required role left unfilled is refused before anything starts:

```console
$ hmz exec -f twice -b cost=5 "add a --dry-run flag to calc.py"
hmz exec: error: twice:twice: no agent was given for 'builder'
```

**3. The params are a `FlowParams` subclass**, or `FlowParams` itself for a flow that takes
none. See [Params of its own](/weaver/flow-settings).

**4. The collections must resolve when the flow runs.** Their annotations are read the first
time the flow is called, against the module's own namespace — so `from __future__ import
annotations` is fine, and so is a collection declared inside a function. What is not is a type
imported only under `if TYPE_CHECKING`:

::: warning The most common first mistake
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:                     # [!code error]
    from hmz.flows import Agent       # [!code error]
```
```console
hmz exec: error: Agents.builder: 'Agent' cannot be resolved: name 'Agent' is not defined
```
Import what the collections name at runtime.
:::

The function's name is the flow's name, which is what a ref names it by after the colon:
`twice:twice`, or just `twice`, since it is the flow named after its directory. `@flow` takes
four more keywords, all optional:

| | |
| --- | --- |
| `name=` | what it is called instead of the function's name |
| `description=` | the line shown beside it where flows are listed, instead of the first line of its docstring |
| `hidden=True` | left out of the lists a person picks from, and still run and loaded by its ref |
| `resumable=True` | a run of it can be [picked up](/user/resuming) where it stopped, and it is handed a `ctx.state` to keep things in |

## Ask for what the agent must do

A role typed plain `Agent` can take turns and nothing more. Everything only some CLIs can do
is asked for by subclassing — mixing in what the role needs:

```python
from hmz.flows import Agent, GoalCommandAgentMixin, SteeringAgentMixin


class Worker(Agent, GoalCommandAgentMixin, SteeringAgentMixin):
    """An agent that can pursue a goal and be spoken to mid-turn."""


class Agents(AgentCollection):
    worker: Worker
```

That buys two things. An agent handed to `worker` that cannot do both is refused before the
flow starts, naming what it lacks. And the flow gets **exactly** what it declared: a `/goal`
prompt, a `steer`, a hook of a mixin it did not declare raise `CapabilityNotGranted`, whatever
the CLI underneath could have done. A type checker says the same thing before anything runs.
Which CLI serves which mixin is [on Flows](/reference/flows#what-each-harness-serves); a role
typed as one CLI's own protocol, `ClaudeCodeAgent` and the rest, asks for that CLI and
everything it can do.

## Say what each agent is allowed

Whoever runs your flow names a CLI, an account, a model and an effort. What the agent may
*touch* is yours, written on the role's class as a `Permission`, scope by scope:

```python
from hmz.flows import Agent, Permission, PermissionKind


class Reviewer(Agent):
    """Reads the change, and writes nothing."""

    _permission = Permission(local=PermissionKind.READ)
```

| Scope | What it covers | Unless you say |
| --- | --- | --- |
| `local` | the environment's workdir the session runs in | `ALL` |
| `user` | the rest of the home directory of the user the agent runs as | `READ` |
| `system` | everything else on the machine | `READ` |
| `online` | the CLI's own web tools — `NONE` or `ALL`, never `READ` | `NONE` |

Scopes nest, so a wider one may not be granted more than a narrower one: `local >= user >=
system`, and a `Permission` that says otherwise is refused as it is written. Nothing an agent
does is put to anybody for approval — every CLI runs in its nothing-asked mode — so what holds
an agent back is this and the [hooks](/weaver/hooks) the flow hangs on it. How each scope
reaches each CLI, including what it cannot fence, is [on
Flows](/reference/flows#what-each-agent-may-do).

`_skills` beside it names the skills the role's sessions carry: one in the flow's own `skills/`
by name, or one elsewhere as a git URL with `#<skill>`. See [Skills](/user/skills).

## Choose what the next turn remembers

A **session** is one conversation of one agent, in one environment. Every turn taken in it
remembers the turns before:

```python
session = await builder.spawn(env=workspace)
await builder.run("do the task", session=session)   # opens the conversation
await builder.run("keep going", session=session)    # the first turn still in context
```

A fresh `spawn` is a conversation that remembers nothing:

```python
for _ in range(3):
    fresh = await builder.spawn(env=workspace)
    await builder.run(task, session=fresh)          # reads the repository, not a history
```

The second shape arrives with no idea what the round before it did, and has to find out from
the repository. Sometimes that is exactly what you want, which is what a [Ralph
loop](/weaver/loops) is. A session holds one turn at a time; a second `run` on it while one is
under way raises `SessionError`, and [two at once](/weaver/async-flows) means two sessions.

## Make the loop survive a bad turn

A turn that fails raises the `HarnessError` it came to — `HarnessThrottled` for a provider
refusing for too many requests, `HarnessKilled` for a CLI that died mid-turn, and the rest of
[the tree](/reference/flows#when-something-goes-wrong). In a loop meant to run for hours, that
would end the run on the first hiccup, so catch it where the loop goes round:

```python
from hmz.flows import HarnessError

while True:
    fresh = await agent.spawn(env=workspace)
    try:
        await agent.run(task, session=fresh)
    except HarnessError:
        continue                                    # the loop goes round again
```

It catches a turn that failed and **nothing else**. A spent [budget](/features/budgets) raises
`BudgetExceeded`, and a run stopped from outside is a cancellation; neither is a
`HarnessError`, so neither is swallowed — otherwise the loop would carry on past them and never
end. Catch `FlowException` to catch everything the flow API can raise.

## Give the loop a finish line

A `while True` is only useful if something ends it. Ask the environment: a role whose type
carries `ShellEnvMixin` may run programs in it, and one with `FilesEnvMixin` may read and write
its files.

```python
from hmz.flows import FilesEnvMixin, LocalEnv, ShellEnvMixin


class Workspace(LocalEnv, ShellEnvMixin, FilesEnvMixin):
    """The directory the run was started in: programs run there, files read from it."""


class Envs(EnvCollection):
    workspace: Workspace


async def green(workspace: Workspace) -> bool:
    code, _, _ = await workspace.exec(["python", "-m", "pytest", "-q"])
    return code == 0


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def until_green(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    builder, workspace = agents["builder"], envs["workspace"]
    for _ in range(20):
        fresh = await builder.spawn(env=workspace)
        await builder.run(task, session=fresh)
        if await green(workspace) and b"- [ ]" not in await workspace.read("TASK.md"):
            return
```

`exec` answers with the exit status, stdout and stderr. It takes an argv; a string to hand to
`bash` needs `BashEnvMixin` instead. Going through the environment rather than `subprocess`
is what lets the same flow run against a directory on another machine, named with `-e`, with
no change to its code. A flow is still just Python, so it may branch, sleep, compute and give
up however it likes.

## Say what the flow is

The first line of the function's docstring is what is shown beside the flow's name where flows
are listed, unless `@flow(description=…)` says otherwise:

```python
    """Two passes: do the work, then read it back and fix what is wrong."""
```

## Where a flow lives, and what it is called

| Lives at | Called |
| --- | --- |
| `.humanize/flows/twice/__init__.py` | `twice` in this project, or `local/twice` |
| `~/.humanize/flows/twice/__init__.py` | `twice` in every project, or `user/twice` |
| a [flowverse](/weaver/flowverses) | `<flowverse>/twice` |
| anywhere else | its path: `-f ./flows/twice` |

A name is looked for **nearest first**, so a flow of yours may stand in for one of humanize's
by taking its name. A file whose name starts with `_` is not a flow.

A bare name means the flow **named after its directory** — `twice` above — else the one
visible flow the directory holds, else nothing: humanize will not choose between several, and
says which there are. One directory may [hold several
flows](/reference/flows#several-flows-in-one-file), each run as `<flow>:<name>`.

## Check your work

Run it on the fake kit before you run it on a model. `hmz.runtime.flowing.fakes` has agents
that answer from a script and environments that are a dictionary of files, and runs the flow
exactly as `hmz exec` would — granted what it declared, refused what it did not — in
milliseconds and for nothing:

```python
from hmz.runtime.flowing.fakes import FakeAgentDriver, run_fake


async def test_it_asks_twice() -> None:
    builder = FakeAgentDriver()
    await run_fake(".humanize/flows/twice", "add a flag", agents={"builder": builder})
    assert builder.prompts[0] == "add a flag"
    assert len(builder.prompts) == 2
```

See [Testing a flow](/weaver/testing-flows).

## See also

- [Loops](/weaver/loops)
- [Params of its own](/weaver/flow-settings)
- [Read the run back](/user/tracing)
- [Flowverses](/weaver/flowverses)
- [Stopping](/user/stopping)
- [Reference › Flows](/reference/flows)
- [Port a project](/user/tutorials/port-a-project)
