---
title: Context, errors and cleanup
description: Read what a flow call knows about itself from ctx, catch the errors a turn or an environment raises, and clean up when a run is stopped.
---

# Context, errors and cleanup

Each flow receives `ctx`, which tracks what the call can spend and has spent. Failures arrive as standard Python exceptions and stops arrive as cancellations, so `try`, `except`, and `finally` work as they do in any coroutine.

![hmz exec runs the flow: the first conversation fails, the flow catches the error, and a second conversation edits the file and passes the tests](/shots/builder-context-caught.svg)

*A turn fails, the flow catches the error, and a second conversation finishes the task.*

## Read the flow context

Read `ctx` to inspect the current `FlowContext`. Each flow call gets its own context, and its fields update live each time you read them.

| Name | Type | What it is |
| --- | --- | --- |
| `ctx.budget` | `Budget` | The limits for this call, taking the tighter of its own limits and its caller's: `duration`, `cost`, `output_tokens`, and `graceful`. Unset limits are `None`; with no budget at all, `cost` is `inf`. |
| `ctx.usage` | `Usage` | Total usage for this call and its child calls so far: `duration` (a `timedelta`, the time agents spent in turns), `cost` (USD), and `output_tokens`. |
| `ctx.flow` | `Flow` | Metadata for the running flow: `description`, `resumable`, `expected_agents`, `expected_envs`, and `expected_params`. |
| `ctx.resumed` | `bool` | `True` if this call resumes an earlier run. |
| `ctx.state` | `FlowState` or `None` | State kept across runs for a resumable flow, or `None` if the flow is not resumable. |

`ctx.budget` holds the total limits, not the remaining budget. Subtract `ctx.usage` to find the cost or tokens that remain:

```python
left = ctx.budget.cost - ctx.usage.cost if ctx.budget.cost is not None else None
```

Hooks receive the same context at `params.ctx`. See [Budgets in a flow](/builder/budgets) for budgets and [Resumable flows](/builder/resumable) for `ctx.state`.

## Catch an error

Catch `FlowException` or one of its subclasses to handle errors from the flow API. The hierarchy splits into three branches based on where the failure happened.

![FlowException has three branches: FlowRuntimeError for what Humanize refused or ran out of, HarnessError for a coding agent that could not take a turn, and EnvError for an environment that could not do what it was asked](/diagrams/builder-context-1.svg)

Catch a leaf class for a specific failure, a branch for a category, or `FlowException` for everything. This flow gives the coder a second try in a new session when the harness fails:

```python
# .hmz/flows/second_try/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def second_try(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder does the task, and tries once more if its harness fails."""
    coder, workspace = agents["coder"], envs["workspace"]
    try:
        answer = await coder.run(task, session=await coder.spawn(), env=workspace)
    except HarnessError as error:
        again = f"The last try failed: {error}. Try again. {task}"
        answer = await coder.run(again, session=await coder.spawn(), env=workspace)
    return f"{answer} ({ctx.usage.output_tokens} output tokens)"
```

Here is the full exception tree, including the Python builtins that leaf classes inherit from:

```text
FlowException
├── FlowRuntimeError
│   ├── FlowNotFound
│   ├── FlowRefError (ValueError)
│   ├── FlowDefinitionError
│   ├── FlowLoadConflict
│   ├── RequirementError
│   │   ├── MissingRole
│   │   ├── CapabilityMissing
│   │   ├── PermissionTooNarrow
│   │   ├── ResourceUnmet
│   │   └── HarnessMismatch
│   ├── CapabilityNotGranted
│   ├── ParamsError (ValueError)
│   ├── FlowDepthExceeded (RecursionError)
│   ├── BudgetExceeded
│   │   ├── DurationExceeded (TimeoutError)
│   │   ├── CostExceeded
│   │   └── OutputTokensExceeded
│   ├── FlowCancelled
│   ├── StateNotSerializable (TypeError)
│   └── OutworlderAway
├── HarnessError
│   ├── HarnessNotInstalled
│   ├── HarnessContended
│   ├── HarnessThrottled
│   ├── HarnessRefused
│   ├── ModelUnavailable
│   ├── HarnessMissing
│   ├── HarnessSandboxed
│   ├── HarnessKilled
│   ├── HarnessDropped
│   ├── HarnessUnrecoverable
│   ├── OutputSchemaError (ValueError)
│   ├── SessionError
│   └── UnsupportedOperation
└── EnvError
    ├── EnvUnavailable
    ├── EnvConnectionError (ConnectionError)
    ├── EnvCommandTimeout (TimeoutError)
    ├── EnvFileNotFound (FileNotFoundError)
    ├── EnvPermissionDenied (PermissionError)
    ├── WorktreeError
    ├── TempCloneBusy
    ├── ScratchError
    └── RewindError
```

Python builtins catch matching leaf classes: `except TimeoutError` catches both `EnvCommandTimeout` and `DurationExceeded`. Child flows raise their exceptions directly into the calling flow without wrapping. Bugs in your own code keep their normal Python types, so a `KeyError` stays a `KeyError` rather than becoming a `FlowException`.

`BudgetExceeded` is sticky. Once a flow spends its budget, every later turn raises `BudgetExceeded` again. The flow can continue only when a single turn exceeds its own budget (`error.own` is `True`).

See the [Flow API](/reference/flows) reference for a description of each class.

## See how a flow ends

How the flow function exits determines the epic's final state and the exit code of `hmz exec`.

| The flow | The epic ends | `hmz exec` |
| --- | --- | --- |
| returns | **Done** | exits `0` |
| raises `BudgetExceeded` | **Budget spent** | writes `hmz exec: stopped -- <reason>`, exits `0` |
| is stopped from outside | **Stopped** | after <kbd>ctrl+c</kbd>, exits `128` plus the signal number |
| raises another `FlowException` | **Failed** | writes the exception, exits `1` |
| raises anything else | **Crashed** | writes the traceback, exits `1` |
| is refused before it starts | **Refused** | writes `hmz exec: error: <reason>`, exits `2` |

![hmz exec runs the same flow when both tries fail: it ends with the line HarnessUnrecoverable and what the harness said](/shots/builder-context-failed.svg)

*Both tries fail, so the second error leaves the flow and fails the epic.*

![The app's sidebar lists three epics of @local/second_try, marked Stopped, Failed and Done](/shots/builder-context-endings.svg)

*Three of these endings in the app.*

## Clean up when a run stops

Use a `try`/`finally` block to run cleanup code when someone stops an epic via **Stop** in the app, `/stop` in the terminal, <kbd>ctrl+c</kbd> in `hmz exec`, or `run.stop()` in the SDK.

![When an epic is stopped: turns are interrupted, the flow gets CancelledError at its await, its finally blocks run, and then Humanize closes sessions and removes temporary copies](/diagrams/builder-context-2.svg)

1. Humanize interrupts every active turn.
2. The flow receives `asyncio.CancelledError` at its current `await`.
3. Your `finally` blocks run while environments remain available.
4. Humanize closes all sessions and removes temporary clones and scratch directories created by the flow.

This flow writes a status file in the workspace and updates it on exit:

```python
# .hmz/flows/tidy/__init__.py
import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Workspace(LocalEnv, FilesEnvMixin):
    pass


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def tidy(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder works while a note says so; the note says how it ended."""
    coder, workspace = agents["coder"], envs["workspace"]
    await workspace.write("STATUS", b"working\n")
    status = b"failed\n"
    try:
        answer = await coder.run(task, session=await coder.spawn(), env=workspace)
        status = b"done\n"
        return answer
    except asyncio.CancelledError:
        status = b"stopped\n"
        raise
    finally:
        await workspace.write("STATUS", status)
```

Re-raise `CancelledError` if you catch it, or the flow will not stop. Keep cleanup fast because the user is waiting; Humanize gives its own session and directory cleanup 30 seconds before moving on. A resumable flow keeps its temporary clones and scratch directories for the next run (see [Worktrees, clones and scratch](/builder/worktrees)). Any file an agent was editing when interrupted stays as it was at that moment.

When a flow ends, Humanize cancels any background tasks the flow started and never awaited. Any later calls those tasks make to an agent, environment, or flow raise `FlowCancelled`. A non-graceful `duration` limit cancels the flow the same way when time runs out: the flow receives `CancelledError`, and its caller receives `DurationExceeded`.

See [Stop a run](/user/stopping) for how users stop and force-stop runs.

## Replace the board in flows

The board (covered in [Talk to a running flow](/user/steering)) is not part of `hmz.flows`, and flow epics do not display one. To show information to the user, pass context blocks to an `Outworlder` (see [The person as an agent](/builder/outworlder)). To persist values across runs, store them in `ctx.state` (see [Resumable flows](/builder/resumable)).

## Find Humanize directories

Call the path helpers on `hmz` to get a `pathlib.Path` for Humanize's directories, even outside a running flow.

| Call | Answers | Holds |
| --- | --- | --- |
| `hmz.home()` | `~/.hmz`, or the directory `HUMANIZE_HOME` names | Persistent data: settings, flowverses, epics, and chats. |
| `hmz.here()` | `.hmz`, relative to the current directory | Project data: its `flows/` directory and runs exported here. |
| `hmz.machine()` | `humanize-<uid>` in the system's temporary directory | Local runtime state, such as running processes. |

```python
import hmz

flows = hmz.here() / "flows"  # this project's own flows, the @local source
```

`hmz.home()` and `hmz.here()` do not create the directory on disk. If only a directory under the earlier name (`~/.humanize`, `.humanize`) exists, the first call renames it; a directory that `HUMANIZE_HOME` names is used as it is. `hmz.machine()` creates its directory with user-only permissions, and raises `PermissionError` if what already exists at that path is not a directory of yours that nobody else can write. Inside a `with hmz.working_in(workspace):` block, `hmz.here()` returns `<workspace>/.hmz` for the current thread.

These paths always point to the machine running the flow. An agent's working directory lives in its environment, which may be on another machine; access agent files through the environment instead. See [Files on disk](/reference/files) for the directory layout.

## Good to know

- `hmz exec` prints agent output, not the flow's return value.
- Humanize raises `RequirementError` and `ParamsError` for the top-level flow before the flow starts, so the flow cannot catch them itself and the epic ends **Refused**. A parent flow can catch them when calling a child flow.
- Humanize closes a session as soon as no variable references it, so keep the session in a variable while turns remain.
- To test error handling without a real agent, give a fake agent a `reply` function that raises one of these exceptions. See [Test a flow](/builder/testing).
