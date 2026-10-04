# Many turns at once

In this guide you have one flow take many turns at the same time. You build `fanout`, which
gives every Python file in the repository a session of its own, runs two of them at a time,
and carries on past a turn that fails. Then you gather different agents, and whole flows, the
same way.

Reach for this when the work splits into pieces that do not need each other: a change to
every module, an actor and a reviewer side by side, or one flow run on several parts at once.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- Python's `asyncio`:
  [`gather`](https://docs.python.org/3/library/asyncio-task.html#asyncio.gather),
  [`Semaphore`](https://docs.python.org/3/library/asyncio-sync.html#asyncio.Semaphore) and
  [`TaskGroup`](https://docs.python.org/3/library/asyncio-task.html#task-groups).
:::

## How it works

A flow is an `async def`, and `agent.run` is a coroutine, so turns you start together run
together. Nothing new is needed from humanize: `asyncio.gather` and its relatives do the
waiting.

The one rule is that **two turns at once need two sessions**. A session is one conversation,
and a conversation takes one turn at a time: a second `run` on a session whose turn is still
going raises `SessionError`. It is not queued, and not interleaved.

```python
# One session: the second run raises SessionError.
await asyncio.gather(agent.run(a, session=s), agent.run(b, session=s))  # [!code error]

# Two sessions: both go at once.
await asyncio.gather(agent.run(a, session=s1), agent.run(b, session=s2))
```

Sessions of one agent are still one agent: one CLI, one model, and one role in the
[trace](/user/tracing), with several conversations going.

## Example: one session per file

```python
# .hmz/flows/fanout/__init__.py
import asyncio

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

AT_ONCE = 2


class Agents(AgentCollection):
    agent: Agent


class Workspace(LocalEnv, ShellEnvMixin): ...  # ①


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def fanout(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> dict[str, str]:
    """The task once per Python file, a session apiece, two at a time."""
    agent, workspace = agents["agent"], envs["workspace"]
    _, listed, _ = await workspace.exec(["git", "ls-files", "*.py"])  # ②
    paths = listed.split()
    gate = asyncio.Semaphore(AT_ONCE)  # ③

    async def one(path: str) -> str:  # ④
        async with gate:
            session = await agent.spawn(env=workspace)  # ⑤
            return await agent.run(f"{task}\n\nThe file is {path}.", session=session)

    said = await asyncio.gather(*(one(path) for path in paths), return_exceptions=True)  # ⑥
    answers: dict[str, str] = {}
    for path, answer in zip(paths, said, strict=True):
        if isinstance(answer, HarnessError):  # ⑦
            print(f"{path}: failed, {answer}")
        elif isinstance(answer, BaseException):
            raise answer  # ⑧
        else:
            answers[path] = answer
    return answers
```

### What each part does

1. **`ShellEnvMixin`** lets the flow run programs in the workspace, which it needs to list the
   files.
2. **`exec(["git", "ls-files", "*.py"])`** answers with the exit status, stdout and stderr. The
   files are the lines of stdout.
3. **`asyncio.Semaphore(AT_ONCE)`** caps how many turns go at once. Nothing in humanize caps
   it, so without the semaphore every file starts at the same moment. How wide is worth going
   depends on the CLI, your account's rate limits and the machine: see [Running
   together](/features/concurrency).
4. **`one(path)`** is everything one file needs, written once, as a coroutine.
5. **A session per file**, spawned inside the semaphore, so no more sessions are open than
   turns are going. Each session is closed as soon as nothing holds it, here when `one`
   returns.
6. **`gather(…, return_exceptions=True)`** runs them all and waits for every one. The answers
   come back in the order of `paths`, whatever order the turns finish in, and a turn that
   raised has its exception in its place rather than cancelling the rest.
7. **`HarnessError`** is a turn the CLI could not take: it died, it was throttled, the
   connection broke. The flow reports it and keeps the other answers.
8. **Anything else is re-raised.** A spent [budget](/features/allowances) or a bug in your own
   flow lands in the list too, and must not be read past.

### Run it

```sh
hmz exec -f fanout -a agent=claude/claude-sonnet-5-5:high -p budget.cost=1 \
    "Add a one-line module docstring to this file. Change nothing else."
```

On a repository with two Python files, both turns start at once and finish in their own time:

```text
● agent is working
● agent is working
● Read(/home/you/calc/check.py)
● Read(/home/you/calc/calc.py)
● Edit(/home/you/calc/calc.py)
● I added the one-line docstring `"""Simple calculator functions."""` at the top of `calc.py`, …
✻ input 6 · output 266 · cache_read 45.8k · cache_write 4.1k · $0.02 · claude-sonnet-5-5 · agent
…
✻ Worked for 6s · agent
● Edit(/home/you/calc/check.py)
● I added the one-line module docstring at the top of `check.py`: …
✻ input 6 · output 262 · cache_read 44.4k · cache_write 5.6k · $0.03 · claude-sonnet-5-5 · agent
…
✻ Worked for 13s · agent
```

- **Two `● agent is working` lines together** are two turns starting at once, in two sessions.
- **The lines of both turns interleave**, each labelled with the role. At the prompt, the agent
  shows a count of its working conversations: see [Many conversations at
  once](/user/conversations).
- **Each turn has its own `✻ input …` line**, and both count against the one budget.

## Check it worked

`git diff --stat` shows one change per file:

```text
 calc.py  | 3 +++
 check.py | 2 ++
 2 files changed, 5 insertions(+)
```

A test proves the cap and the failure handling, which no single real run can. Fake turns take
no time unless the reply makes them, so the reply waits a moment to let turns overlap:

```python
# tests/test_fanout.py
import asyncio

from hmz.flows import HarnessError
from hmz.sdk import fakes

FILES = {("git", "ls-files", "*.py"): (0, "a.py\nb.py\nc.py\nd.py\n", "")}  # ①


async def last_word(prompt: str, **_: object) -> str:
    await asyncio.sleep(0.01)  # ②
    return prompt.split()[-1]


async def test_every_file_gets_a_session_two_at_a_time() -> None:
    agent = fakes.FakeAgentDriver(reply=last_word)

    said = await fakes.run_fake(
        "fanout", "annotate", agents={"agent": agent}, local=fakes.FakeEnvDriver(run=FILES)
    )

    assert said == {"a.py": "a.py.", "b.py": "b.py.", "c.py": "c.py.", "d.py": "d.py."}
    assert len(agent.sessions) == 4
    assert agent.peak == 2  # ③


async def test_a_failed_turn_is_reported_and_the_rest_carry_on() -> None:
    def fails_on_b(prompt: str, **_: object) -> str:  # ④
        if prompt.endswith("b.py."):
            raise HarnessError("the CLI died mid-turn")
        return "done"

    said = await fakes.run_fake(
        "fanout",
        "annotate",
        agents={"agent": fakes.FakeAgentDriver(reply=fails_on_b)},
        local=fakes.FakeEnvDriver(run=FILES),
    )

    assert sorted(said) == ["a.py", "c.py", "d.py"]  # ⑤
```

```text
..                                                                       [100%]
2 passed in 0.13s
```

1. **`FILES`** answers the one command the flow runs with four files. Any other command would
   exit 127, so a flow that runs something unscripted says so.
2. **The reply sleeps** so each turn takes a moment and the turns overlap, as real ones do.
3. **`agent.peak`** is the most sessions that were open at once. Exactly two proves both that
   the turns ran together and that the semaphore held them to two. Set `AT_ONCE = 4` and this
   assertion fails with `4 == 2`.
4. **A reply that raises** fails that one turn with the `HarnessError` it raised.
5. **The other three answers** are still returned, and the flow printed `b.py: failed, the CLI
   died mid-turn`.

## Different turns at once

Two agents, or one agent with different prompts, gather the same way. Each has its own session:

```python
acting = await agents["actor"].spawn(env=workspace)
reviewing = await agents["reviewer"].spawn(env=workspace)
acted, reviewed = await asyncio.gather(
    agents["actor"].run(task, session=acting),
    agents["reviewer"].run(REVIEW + task, session=reviewing),
)
```

## Whole flows at once

`load` finds a flow by its ref and hands it back ready to await, and whole flows gather the
same way turns do. From another flow in the same project, `"fanout"` is the flow above:

```python
from hmz.flows import load

part = load("fanout")
await asyncio.gather(
    part("the parser", agents=agents, envs=envs, params=FlowParams()),
    part("the printer", agents=agents, envs=envs, params=FlowParams()),
)
```

Each call is a **branch of the run**, with its own `ctx`, its own budget under what is left of
yours, and its own line in the running tree. Both may be handed the same agent: the sessions
one branch opens and the [hooks](/weaver/hooks) it hangs are its own, and the other never sees
them. See [A flow that calls a flow](/weaver/calling-flows).

## Variations

**Stop at the first failure.** When one failed turn makes the rest pointless,
`asyncio.TaskGroup` cancels the others at once, and each cancelled CLI stops:

```python
said: list[str] = []
try:
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(one(path)) for path in paths]
    said = [task.result() for task in tasks]
except* HarnessError as failed:
    print(f"{len(failed.exceptions)} turns failed")
```

| Shape | The other turns | What you get back |
| --- | --- | --- |
| `gather(...)` | keep running, unwatched | the first failure, raised |
| `gather(..., return_exceptions=True)` | run to the end | every answer, with failures in place |
| `asyncio.TaskGroup` | cancelled at once, and each CLI stops | an `ExceptionGroup` of the failures |

**A checkout per session.** Sessions that all write to one directory can trip over each other.
Give each a [worktree](/weaver/worktrees) of its own with `derive_worktree`, and spawn the
session there.

**A word into a running turn.** To add to a turn that is already going, rather than start a
second one, `steer` it. That needs a role that declared `SteeringAgentMixin`, which Claude
Code, Codex, Kimi Code and pi serve. See [Steering](/user/steering).

## Pitfalls

- **Plain `gather` leaves orphans.** Without `return_exceptions=True`, the first failure is
  raised at once and the other turns keep running with nobody waiting for them. Collect the
  failures, or use a `TaskGroup`.
- **`except Exception` over a gather** swallows a spent budget along with failed turns. Catch
  `HarnessError`, and re-raise the rest, as `fanout` does.
- **Spawn inside the semaphore.** Spawning every session up front holds them all open while
  they wait their turn.
- **One budget for everything.** Every turn going at once spends from the same budget, so a wide
  fan-out reaches it quickly.

## Next steps

- [Worktrees, copies and scratch](/weaver/worktrees), for a directory per conversation
- [Branching a conversation](/weaver/branching), for two sessions that share a history
- [A flow that calls a flow](/weaver/calling-flows)
- [Reference › Waiting for more than one
  thing](/reference/flows#a-flow-that-waits-for-more-than-one-thing) and
  [Sessions and turns](/reference/flows#sessions-and-turns)
