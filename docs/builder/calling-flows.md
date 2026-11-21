---
title: Call another flow
description: Load a flow by its ref and run it inside your own flow, with the agents, environments, params and budget you choose.
---

# Call another flow

Use `load(ref)` to find another flow, then await it to run it as a step inside your epic and get its return value.

![Your flow loads a flow and awaits it; what you pass is checked first, the called flow runs with its own ctx, sessions and hooks, and its return value or exception comes back](/diagrams/builder-calling-flows-1.svg)

## Load a flow and call it

Save this flow as `.hmz/flows/shipped/__init__.py`. It calls `goal` from the official flowverse (see [Find and install flows](/user/flows)) and `review`, a hidden flow in the same file:

```python
from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    EnvCollection,
    FlowContext,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    flow,
    load,
)


class Coder(Agent, GoalCommandAgentMixin): ...


class Agents(AgentCollection):
    coder: Coder


class Reviewers(AgentCollection):
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Focus(FlowParams):
    focus: str = "bugs"


@flow(agents=Reviewers, envs=Envs, params=Focus, name="review", hidden=True)
async def review(
    task: str, *, agents: Reviewers, envs: Envs, params: Focus, ctx: FlowContext
) -> str:
    """Read the change and say what is wrong with it."""
    reviewer = agents["reviewer"]
    session = await reviewer.spawn()
    return await reviewer.run(
        f"Review the change for {params.focus}: {task}",
        session=session,
        env=envs["workspace"],
    )


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def shipped(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """The task as a goal, then a review of the change."""
    goal = load("goal")
    await goal(
        task,
        agents={"worker": agents["coder"]},
        envs={},
        params=goal.expected_params(),
    )
    review = load(":review")
    return await review(
        task,
        agents={"reviewer": agents["coder"]},
        envs=envs,
        params=review.expected_params(focus="security"),
        budget=Budget(output_tokens=2000),
    )
```

Run it from the command line:

```sh
hmz exec -f @local/shipped -a coder=claude/claude-haiku-4-5 -p budget.output_tokens=20000 "Add a discount code to checkout"
```

![The output of hmz exec for the shipped flow: one turn taken inside goal, then a second conversation taken inside review](/shots/builder-calling-flows-exec.svg)

*The first turn runs inside `goal`, the second inside `review`.*

Pass these arguments when calling a flow:

| Argument | What to pass |
| --- | --- |
| `task` | The task text for the called flow. |
| `agents` | A mapping from the called flow's role names to your agents. |
| `envs` | A mapping from the called flow's role names to your environments. |
| `params` | An instance of the called flow's params class, or a mapping of values. |
| `budget` | Optional. A `Budget` for this call alone. |

The called flow runs with its own `ctx`, sessions, and hooks, and cannot use a session you opened. If it raises an exception, you receive that exception unwrapped with its original class.

Read a flow object's attributes to inspect its declaration: `description`, `expected_agents`, `expected_envs`, `expected_params`, and `resumable`.

If a flow is defined in the same file, it is already a flow object. You can await `review(...)` directly without calling `load`.

## Name the flow

Pass a flow ref to `load`. `hmz exec -f` accepts the same forms, except `:review`.

| Ref | What it names |
| --- | --- |
| `:review` | The flow called `review` in the same module as the code calling `load`. |
| `goal` | A flow by name. |
| `humanize1:gen-plan` | The flow called `gen-plan` in the `humanize1` module. |
| `alice/kernel` | A flow the official flowverse lists under a user. |
| `@local/shipped` | A flow of one flowverse only: `@local`, `@user` or `@<flowverse>`. |
| `./flows/mine`, `/abs/path`, `~/flows/mine` | A path. The first that exists of `<path>/__init__.py`, `<path>` and `<path>.py` is used. |
| `git+https://github.com/humanfia/humanize1-flow@v0.1.0#humanize1:rlcr` | A repository, at the revision after `@`, in the directory after `#`. |

Humanize resolves a flow name beside the calling flow first: among the flows in the same directory as the calling flow, or among flows from the same flowverse if it was installed from one. Next, it checks `@local`, `@user`, official, and other flowverses alphabetically.

A ref without `:<name>` selects the flow named after the directory or file, or else the only non-hidden flow.

Use a `git+` ref to run a flow without installing it. Supported URL schemes are `https`, `http`, `ssh`, `file`, and `git`. Omitting `@<rev>` uses the default branch. `load` does not fetch the repository; Humanize clones it when you first call the flow or read a property like `expected_params`.

`load` raises these exceptions:

| Exception | When |
| --- | --- |
| `FlowRefError` | The text is not a ref, or `:<name>` is used where no flow is asking. |
| `FlowNotFound` | The ref names no flow. For a `git+` ref, this is raised at the first call if the repository cannot be fetched. |
| `FlowLoadConflict` | Two flow directories that import under the same module name are loaded in one epic. |
| `FlowDefinitionError` | The named flow is written wrong, or importing it fails. |

## Pass agents and environments

Map the called flow's role names to your agents and environments. In the example above, your `coder` fills the `worker` role in `goal` and the `reviewer` role in `review`.

Every agent or environment you pass must meet the called role's declarations. Humanize checks requirements before the called flow starts, so a failed check runs and spends nothing.

| The called role declares | Raised if what you pass falls short |
| --- | --- |
| A required role | `MissingRole` |
| A mixin, such as `GoalCommandAgentMixin` | `CapabilityMissing` |
| A permission | `PermissionTooNarrow` |
| One harness, such as `ClaudeCodeAgent` | `HarnessMismatch` |
| CPUs, memory or GPUs | `ResourceUnmet` |

All five exceptions inherit from `RequirementError`. Passing an object that is not an agent or environment of the current epic raises `RequirementError` directly.

Your agent can only pass on capabilities that your own role declares. Because `goal` requires `GoalCommandAgentMixin`, `Coder` must declare it too. If `coder` is a plain `Agent`, Humanize refuses the call:

![The output of hmz exec when the coder role is a plain Agent: CapabilityMissing, goal's worker needs GoalCommandAgentMixin](/shots/builder-calling-flows-refused.svg)

The called flow receives only what its own role declares: its mixins, permission, skills, tools, and command lines. It never receives extra capabilities held by your flow.

Names in a mapping that the called flow does not declare are ignored. You can omit roles that the run provides automatically. An omitted `LocalEnv` role receives the epic's directory, which lets `envs={}` work for `goal`. An omitted `Outworlder` role receives the epic's person. To answer for the person from your flow instead, see [The person as an agent](/builder/outworlder).

## Pass params

Call `expected_params` on the loaded flow to build its params instance:

```python
params=review.expected_params(focus="security")
```

Calling `review.expected_params()` with no arguments uses the defaults. You can also pass a plain mapping like `{"focus": "security"}`, which Humanize validates against the params class. Invalid values raise `ParamsError` before the called flow starts. See [Params](/builder/params).

## Give the call a budget

Pass `budget=Budget(...)` to cap what a single call can spend. Without `budget=`, the called flow uses your remaining budget. With `budget=`, both limits apply, and everything the called flow spends counts against your flow and the epic.

If the call exhausts its own budget, it raises `BudgetExceeded`, which you can catch to continue your flow. The `budget` argument must be a `Budget` or `None`, or the call raises `TypeError`. See [Budgets in a flow](/builder/budgets).

## In the app

Open the epic and look under **Called flows** in the **Epic** panel to see each call's task and state. On the graph, a box labelled `Called` groups agents that ran inside a called flow.

![The epic page in Humanize Desktop: the graph shows a box for the flow and one for the called goal flow, and the panel lists goal:goal and shipped:review under Called flows](/shots/builder-calling-flows-called.svg)

## Good to know

- Run several flow calls at once with `asyncio.gather` (see [Concurrent turns](/builder/async)).
- A flow can call itself. Calls nest at most 64 flows deep, counting the flow the epic started with; one level deeper raises `FlowDepthExceeded`, which is a subclass of `RecursionError`.
- Awaiting a flow outside an epic raises `FlowRuntimeError`. Calling a flow after your own call or the epic has finished raises `FlowCancelled`.
- Within one epic, loading the same ref from the same module returns the same flow object, and a `git+` URL at a given revision is fetched at most once.
- When you resume an epic, a called flow resumes if called with the same task, agents, environments, and params (see [Resumable flows](/builder/resumable)).
- In tests, called flows run against the same fakes as the caller (see [Test a flow](/builder/testing)).
