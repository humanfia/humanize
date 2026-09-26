# Your first flow

A **flow** is a Python function that drives coding agents: which agents, what each is asked,
in what order, and when to stop. Write one when you would otherwise type the same instructions
to an agent again and again. In five minutes you will have one of your own running.

You need a flow run behind you — the [User Guide](/user/) starts there — and a git repository
you don't mind an agent editing.

## Write it

A flow is a directory under `.humanize/flows/` in your project, named after the flow:

```sh
mkdir -p .humanize/flows/twice
```

```python
# .humanize/flows/twice/__init__.py
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
    builder: Agent  # [!code highlight]


class Envs(EnvCollection):
    workspace: LocalEnv  # [!code highlight]


@flow(agents=Agents, envs=Envs, params=FlowParams)  # [!code highlight]
async def twice(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Do the work, then read it back and fix what is wrong."""
    builder = agents["builder"]
    session = await builder.spawn(env=envs["workspace"])  # [!code highlight]
    await builder.run(task, session=session)  # [!code highlight]
    await builder.run(  # [!code highlight]
        "Now review what you just did, and fix anything that is wrong.",
        session=session,
    )
```

| Line | What it says |
| --- | --- |
| `builder: Agent` | The flow drives one agent, in the **role** `builder`. Whoever runs it says which CLI and model fill that role. |
| `workspace: LocalEnv` | The agent works in the directory the run starts in. Nobody has to name it. |
| `@flow(…)` | This `async def` is a flow, and these are what it takes. `params=FlowParams` means no [params](/weaver/flow-settings) of its own. |
| `builder.spawn(…)` | Opens a **session**: one conversation of one agent, in one place. |
| `builder.run(…)` | Takes a **turn** in that session and waits for it to end. The second turn remembers the first, because it is the same session. |

The docstring's first line is what `/flow` shows beside the flow's name.

## Run it

::: code-group

```text [At the prompt]
$local/twice add a subtract function to calc.py
```

```sh [Claude Code]
hmz exec -f twice -a builder=claude/claude-opus-5:high -b cost=5 \
    "add a subtract function to calc.py"
```

```sh [Codex]
hmz exec -f twice -a builder=codex/gpt-5.6-sol:high -b cost=5 \
    "add a subtract function to calc.py"
```

```sh [Kimi Code]
hmz exec -f twice -a builder=kimi/kimi-code/k3:high -b cost=5 \
    "add a subtract function to calc.py"
```

```sh [DeepSeek Harness]
hmz exec -f twice -a builder=dsh/deepseek-v4-flash:high -b cost=5 \
    "add a subtract function to calc.py"
```

:::

At the prompt your project's flows are offered as `local/<name>`. The first time, the flow's
menu opens and asks what `builder` runs and what the run may spend; after that, the line alone
starts it. On the command line, `-a` fills the role by its name, and `-b` is the run's
[budget](/features/allowances), which `hmz exec` will not start without. Use a model your
account can name — `/flow` lists them.

The agent takes two turns in one conversation, and the run ends when the function returns:

```text
● builder is working
● Read(calc.py)
● Edit(calc.py)
● Added subtract(a, b) beside add(a, b).
✻ Worked for 31s · builder
● builder is working
● Read(calc.py)
● Edit(calc.py)
● Reviewed it: subtract is right, but add subtracted too, so I fixed add.
✻ Worked for 14s · builder
```

::: details If it is refused
| `hmz exec: error: …` | Why |
| --- | --- |
| `twice needs an agent for 'builder'; give each with -a ROLE=CLI/MODEL:EFFORT` | No `-a builder=…` on the line. |
| `twice: a run is given a budget -- -b duration=...,cost=...,output_tokens=... -- and this one was given none` | No `-b`. |
| `twice: no flow is called 'twice', and it is not a path` | You are not in the project that holds `.humanize/flows/twice/`. |
| `importing the flow at … failed: …` | Python could not import the file: a typo, or a name used and never imported. |
:::

## Grow it

Everything else is added to a flow like this one, a piece at a time:

| To | Add | Read |
| --- | --- | --- |
| hold the agent to your test suite, and have a second agent review | a shell on the workspace, a reviewer role, a loop | [Build under test](/weaver/tutorials/build-under-test) — the next page |
| start every round from nothing, or keep one conversation going | where `spawn` sits in the loop | [Loops](/weaver/loops) |
| take settings from `-p` and a form at the prompt | a `FlowParams` subclass | [Params of its own](/weaver/flow-settings) |
| get an answer your code can branch on | `output_schema=` a pydantic model | [Answers in a shape](/weaver/shapes) |
| keep an agent from writing | a `Permission` on its role | [Permissions](/user/permissions) |
| hand an agent skills | `_skills` on its role | [Skills](/user/skills) |
| use a CLI's own `/goal`, or speak into a turn | a mixin on the role | [Goals](/weaver/goals) |
| have several turns going at once | `asyncio.gather` | [Many turns at once](/weaver/async-flows) |
| build on a flow somebody else wrote | `load(…)` | [A flow that calls a flow](/weaver/calling-flows) |
| let whoever runs it say where the work lands, even another machine | a role typed `Env` instead of `LocalEnv`, given with `-e` | [Remote execution](/user/remote-execution) |

::: warning Agents run with approvals bypassed
Nobody is asked before an agent edits a file or runs a command. What it may touch is what its
role's `Permission` says, and unless you say otherwise that is writing the directory it works
in.
:::

## Where flows are found

A name is looked for nearest first, so a flow of yours can stand in for one of humanize's by
taking its name:

| Put it in | Run it with | At the prompt |
| --- | --- | --- |
| `.humanize/flows/twice/` in the project | `-f twice` | `$local/twice` |
| `~/.humanize/flows/twice/` | `-f twice`, when the project has none of that name | `$user/twice` |
| the flows humanize ships, and the [flowverses](/weaver/flowverses) you have added | `-f ralph_loop`, `-f theirs/review` | `$ralph_loop`, `$theirs/review` |
| anywhere else | `-f ./path/to/twice` | |

`-f local/twice` and `-f user/twice` say which one outright. A flow can also be a single file,
`.humanize/flows/twice.py`. A file or directory whose name starts with `_` is not a flow: it is
somewhere to keep code the flows beside it import.

::: details The rest of `@flow`
| Keyword | |
| --- | --- |
| `name=` | Call it this instead of the function's name. |
| `description=` | Show this beside it instead of the docstring's first line. |
| `hidden=True` | Leave it out of the lists at the prompt. It still runs by name. |
| `resumable=True` | A stopped run can be picked up where it was. See [Loops](/weaver/loops). |

A flow's name is letters, digits, `_`, `.` and `-`. One directory can hold several flows, run
as `<directory>:<name>` — see [A flow that calls a flow](/weaver/calling-flows).
:::

**Next:** [test it without spending tokens](/weaver/testing-flows).
