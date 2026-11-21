---
title: Loops
description: Write a loop in a flow, choose what each round remembers, decide what ends it, and keep it going when a turn fails or stalls.
---

# Loops

Write a `for` or `while` loop around `run`. Flows are async Python, so there is no separate loop API. You choose what a round remembers, what ends the loop, and what happens when a turn fails.

![Two rows. Fresh sessions per round: three separate sessions that share only the repository. One long session: three turns in a row inside one session, which also reads and writes the repository](/diagrams/builder-loops-1.svg)

## Write a loop

Run an agent in a loop until your check passes. In this flow, each round spawns a fresh session, runs the coder, and then runs the project's tests to check the exit status.

```python
# .hmz/flows/until_green/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    LocalEnv,
    ShellEnvMixin,
    flow,
)

TESTS = ["python", "-m", "pytest", "-q"]


class Agents(AgentCollection):
    coder: Agent


class Workspace(LocalEnv, ShellEnvMixin):
    """The project, and a shell in it."""


class Envs(EnvCollection):
    workspace: Workspace


class Params(FlowParams):
    rounds: int = 5


@flow(agents=Agents, envs=Envs, params=Params)
async def until_green(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> bool:
    """Work on the task, round after round, until the tests pass."""
    coder, workspace = agents["coder"], envs["workspace"]
    prompt = task
    for _ in range(params.rounds):
        session = await coder.spawn()  # a fresh conversation every round
        try:
            await coder.run(prompt, session=session, env=workspace)
        except HarnessError:
            prompt = f"{task}\n\nThe last turn failed. Check what is already there."
            continue
        status, out, _ = await workspace.exec(TESTS)
        if status == 0:
            return True
        prompt = f"{task}\n\nThe tests still fail:\n{out[-2000:]}"
    return False
```

Pass a budget when you run it. `hmz exec` requires one.

```sh
hmz exec -f @local/until_green -a coder=claude/claude-haiku-4-5 \
    -p budget.output_tokens=20000 "Add a discount code to checkout"
```

![The command's output: the agent edits checkout.py, then works again as conversation 2 of 2, edits again, and the command ends](/shots/builder-loops-exec.svg)

*Two rounds. The tests failed after the first and passed after the second.*

## Choose what a round remembers

Place `spawn` inside or outside the loop to control memory.

```python
# Fresh session per round: the agent starts from the prompt and the repository.
for _ in range(params.rounds):
    session = await coder.spawn()
    await coder.run(prompt, session=session, env=workspace)

# One long session: every round is one more turn of the same conversation.
session = await coder.spawn()
for _ in range(params.rounds):
    await coder.run(prompt, session=session, env=workspace)
```

| | Fresh session per round | One long session |
| --- | --- | --- |
| Each round starts from | the prompt and the repository | everything said and done so far |
| Use it when | earlier attempts would mislead the next one | each round builds on what the last one learned |
| Cost | every round reads the project again | the conversation grows with every round |
| In the official flowverse | `ralph_loop` | `stateful_ralph`, `continue_loop` |

In Humanize Desktop, a fresh-session loop shows one session per round:

![Humanize Desktop on the finished epic: the coder's card lists sessions 1 and 2, each with one turn on its timeline, and the sidebar lists both sessions under the agent](/shots/builder-loops-fresh.svg)

Moving `spawn` above the loop shows one session with two turns:

![Humanize Desktop on the finished epic: the coder's card lists one session with two turns on its timeline, and the sidebar lists one session under the agent](/shots/builder-loops-one.svg)

Sessions close automatically when nothing references them, so a fresh-session loop keeps only the current session open.

Pass context between fresh sessions in one of four ways:

| Memory | How |
| --- | --- |
| The repository | The agent's files and commits stay on disk for the next round. |
| The prompt | Put output from the last round into the next prompt, as `until_green` does with test results. |
| A notes file | Tell the agent to maintain and read a file such as `NOTES.md`. |
| `ctx.state` | In a resumable flow, store values here to survive stops and resumes. See [Resumable flows](/builder/resumable). |

A counter in a local variable starts again from zero when a run resumes. Keep state that must survive a stop in `ctx.state`.

## Decide when to stop

Give your loop more than one exit condition.

| What ends it | How |
| --- | --- |
| A check of your own | `return` or `break` on a command's exit status: `status, out, err = await workspace.exec(TESTS)`. See [Environment roles](/builder/environments). |
| A round limit | `for _ in range(params.rounds)`. Let the user override it with `-p rounds=3`. See [Params](/builder/params). |
| A verdict | Ask an agent for a typed answer and branch on a field. See [Typed answers](/builder/shapes). |
| The budget | Always active. Reaching a limit makes the next `run` raise `BudgetExceeded`, ending the flow and marking the epic stopped rather than failed. Check `ctx.usage` and `ctx.budget` to exit early. See [Budgets in a flow](/builder/budgets). |
| A failed turn | `run` raises `HarnessError`. If uncaught, the flow ends and the epic fails. |
| The person | Stopping the epic cancels the flow at its current `await`. |
| The agent | Delegate the loop to the harness's goal command so the agent decides when it is done. See [Goals](/builder/goals). |

A `while True` loop such as `ralph_loop` relies entirely on the budget to stop. Give it a budget you are willing to spend in full.

To extend a single turn instead of starting a new one, use a stop hook. See [Hooks](/builder/hooks).

## Keep going after a failed turn

Catch `HarnessError` around `run` to lose only the current round when a turn fails, as `until_green` does.

`run` raises `HarnessError` if the harness dies, hits rate limits, or loses its connection, after Humanize has already exhausted automatic retries and the fallbacks in the agent's [nous](/user/nous).

::: warning Catch `HarnessError`, not `Exception`
`BudgetExceeded` is not a `HarnessError`, so it passes through and ends the loop. `except Exception` catches it too. A spent budget raises again on every later turn, so a `while True` loop written that way spins without end.
:::

See [Sessions and turns](/builder/turns) for every error a turn can raise.

## Handle a stalled turn

Humanize automatically stops silent turns so your loop never hangs forever.

![The command's output: after the agent starts pytest, yellow notices say claude is idle and has said nothing, that the turn is being cut off, and that claude was asked to stop; then the agent works again as conversation 2 of 2 and finishes](/shots/builder-loops-watchdog.svg)

*A stalled turn ended by the watchdog, and the loop taking its next round. The window was set to 5 seconds for this picture.*

1. Output from the harness resets the watchdog window (900 seconds by default, or 360 seconds for the `dsh` harness).
2. When the window expires, Humanize checks CPU usage. If the harness or a child process is using the CPU, it gets up to 4 more windows, leaving long test suites alone.
3. Otherwise, or once those windows are used up, Humanize posts a notice and then takes one step per window until the turn ends: it interrupts the turn, terminates the harness process tree, and finally kills anything left.
4. Each step posts a notice naming the harness wherever you watch the epic.
5. The turn fails and `run` raises `HarnessUnrecoverable` (a `HarnessError` subclass) whose message contains `the watchdog stopped this turn`. A loop catching `HarnessError` moves to the next round.

The watchdog pauses while a turn waits on a person for a permission request, a question, or a pausing hook.

| Setting | Effect |
| --- | --- |
| `HUMANIZE_WATCHDOG=120` | Sets the window to 120 seconds for every harness. |
| `HUMANIZE_WATCHDOG=0` | Disables the watchdog (0 or negative). |

Set this variable in the environment of the daemon holding the epic. A daemon that is already running does not pick it up from the `hmz exec` command line. See [The daemon](/user/daemon).

## Test a loop

Test your loop with a scripted agent and a fake workspace without spending tokens.

```python
# tests/test_until_green.py
from hmz.sdk import fakes


async def test_it_stops_at_the_first_green_run() -> None:
    results = iter([(1, "1 failed", ""), (0, "2 passed", "")])
    coder = fakes.FakeAgentDriver()
    workspace = fakes.FakeEnvDriver(run=lambda argv, env: next(results))

    done = await fakes.run_fake(
        "until_green", "add a coupon", agents={"coder": coder}, local=workspace
    )

    assert done is True
    assert len(coder.sessions) == 2  # a fresh session each round
    assert coder.prompts[1].endswith("1 failed")
```

See [Test a flow](/builder/testing).

## Good to know

- Trust your own check, such as a command's exit status, rather than the agent's claim that it is done.
- A single long session grows each round; exceeding the model's context window raises `HarnessUnrecoverable`, which retries cannot fix.
- A session runs one turn at a time. To run rounds in parallel, see [Concurrent turns](/builder/async).
- A fresh-session loop needs no saved state to resume; running it again continues from the repository.
- Find ready-made loops in the [catalogue of official flows](https://humanfia.ai/flows/). Humanize ships none built in.
- To watch rounds live, see [Watch a run](/user/watch-a-run).
