<script setup>
import ForkHistory from '../.vitepress/theme/components/weaver-compose/ForkHistory.vue'
</script>

# Branching a conversation

In this guide you branch one conversation into two. You build `twoways`: an agent reads the
code once, then the conversation is forked twice, and each fork tries the task a different way
in a worktree of its own, both at once, both knowing what the reading found.

Reach for `fork` when a conversation has got somewhere expensive, such as an hour of reading
the code, and you want to try more than one way on from it without paying for the reading
again.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- Several turns at once with `asyncio.gather`: [Many turns at once](/weaver/async-flows).
- A git repository with a commit, for the worktrees: [Worktrees, copies and
  scratch](/weaver/worktrees).
:::

## How it works

`agent.fork(session, env=…)` makes a second session that starts out knowing everything the
first one knows, and goes its own way from there:

- **Everything said after the fork belongs to one branch only.** The parent is untouched, and
  two forks never see each other's turns.
- **A fork is a session like any other.** It belongs to the same agent, with the same model,
  permission and [hooks](/weaver/hooks). It has its own `usage`, which starts at nothing, and
  is closed the way every session is.
- **A fork is cut at its own first turn**, not at the call to `fork`. The call itself costs
  nothing; the child's first turn is where the history is carried over.
- **`env` is where the child works**, and it need not be the parent's, on the CLIs that can
  carry a conversation into another directory.

Take turns below and watch who knows what:

<ForkHistory />

## Example: read once, try two ways {#fork-into-another-directory}

```python
# .hmz/flows/twoways/__init__.py
import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GitWorktreeEnvMixin,
    LocalEnv,
    Session,
    UnsupportedOperation,
    flow,
)

READ = "Read calc.py and check.py, and say in one sentence what they do. Change nothing."
WAYS = ("with a docstring and type hints", "as briefly as you can")


class Agents(AgentCollection):
    agent: Agent


class Workspace(LocalEnv, GitWorktreeEnvMixin): ...  # ①


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def twoways(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> list[str]:
    """Read once, then try the task two ways, each in a worktree of its own."""
    agent, workspace = agents["agent"], envs["workspace"]
    session = await agent.spawn(env=workspace)
    await agent.run(READ, session=session)  # ②

    async def attempt(way: str) -> str:
        tree = await workspace.derive_worktree()  # ③
        try:
            branch: Session = await agent.fork(session, env=tree)  # ④
        except UnsupportedOperation:  # ⑤
            branch = await agent.spawn(env=tree)
        print(f"{way}: {tree.workdir}")
        return await agent.run(f"{task}, {way}.", session=branch)  # ⑥

    return await asyncio.gather(*(attempt(way) for way in WAYS))  # ⑦
```

### What each part does

1. **`GitWorktreeEnvMixin`** lets the flow check out worktrees, so the two attempts do not
   write over each other's files.
2. **The expensive turn, taken once**, in the parent session. A fork needs a conversation to
   carry, so the parent must have taken at least one turn.
3. **`derive_worktree()`** checks out a new worktree at what the workdir has checked out: a
   clean copy of the committed code for each attempt.
4. **`fork(session, env=tree)`** makes a new session that carries the reading and works in the
   worktree. Nothing is sent yet.
5. **`UnsupportedOperation`** is what a CLI that cannot make this fork raises, at the call.
   Falling back to a fresh `spawn` keeps the flow running on any CLI, at the price of the
   history.
6. **The fork's first turn** is where the conversation is cut and carried over. From here on
   the two branches know only their own turns.
7. **`gather`** runs both attempts at once, and answers with both answers in the order of
   `WAYS`.

### Run it

```sh
hmz exec -f twoways -a agent=claude/claude-sonnet-5-5:high -p budget.cost=1 \
    "Add subtract(a, b) to calc.py"
```

A real run, abridged:

```text
● agent is working
● Read(/home/you/calc/calc.py)
● Read(/home/you/calc/check.py)
● `calc.py` defines an `add(a, b)` function that returns the sum of its arguments, and `check.py` imports it, asserts that `add(2, 3) == 5`, …
✻ input 4 · output 194 · cache_read 27.8k · cache_write 5.5k · $0.02 · claude-sonnet-5-5 · agent
…
✻ Worked for 5s · agent
● agent is working
● agent is working
● Read(/home/you/.hmz/envs/calc-c69b9824bb32/worktrees/head-88d122ae/calc.py)
● Read(/home/you/.hmz/envs/calc-c69b9824bb32/worktrees/head-278c0743/calc.py)
● Edit(/home/you/.hmz/envs/calc-c69b9824bb32/worktrees/head-88d122ae/calc.py)
● Edit(/home/you/.hmz/envs/calc-c69b9824bb32/worktrees/head-278c0743/calc.py)
● I added `subtract(a, b)` to `calc.py`, returning `a - b`. I didn't run anything, so it's untested.
✻ input 6 · output 378 · cache_read 51.4k · cache_write 926 · $0.02 · claude-sonnet-5-5 · agent
with a docstring and type hints: /home/you/.hmz/envs/calc-c69b9824bb32/worktrees/head-278c0743
as briefly as you can: /home/you/.hmz/envs/calc-c69b9824bb32/worktrees/head-88d122ae
…
● I added `subtract(a: float, b: float) -> float` to `calc.py` in the worktree. It has a one-line docstring and returns `a - b`. …
✻ input 6 · output 537 · cache_read 51.5k · cache_write 1.1k · $0.02 · claude-sonnet-5-5 · agent
…
```

- **The first turn is the reading**, in your own checkout.
- **Two `● agent is working` lines together** are the two forks' first turns, going at once,
  each in its own worktree.
- **`cache_read 51.4k` against the reading's `27.8k`** is the carried history: each fork
  starts from the whole conversation so far, and neither read `check.py` again.

## Check it worked

Each worktree holds one attempt, and your own checkout holds neither:

```sh
git -C ~/.hmz/envs/calc-c69b9824bb32/worktrees/head-278c0743 diff
git -C ~/.hmz/envs/calc-c69b9824bb32/worktrees/head-88d122ae diff
git status --short
```

```diff
@@ -1,2 +1,7 @@
 def add(a, b):
     return a + b
+
+
+def subtract(a: float, b: float) -> float:
+    """Return the difference of a and b (a - b)."""
+    return a - b
@@ -1,2 +1,6 @@
 def add(a, b):
     return a + b
+
+
+def subtract(a, b):
+    return a - b
```

`git status --short` in your checkout shows only `?? .hmz/`. Keep the attempt you like,
and `git worktree remove` the other.

A test checks the shape of the branching with a fake agent: who was forked from whom, and what
each branch was told:

```python
# tests/test_twoways.py
from hmz.sdk import fakes

READ = "Read calc.py and check.py, and say in one sentence what they do. Change nothing."


async def test_both_ways_carry_on_from_the_reading() -> None:
    agent = fakes.FakeAgentDriver()

    await fakes.run_fake("twoways", "Add subtract", agents={"agent": agent})

    reading, *branches = agent.sessions
    assert [branch.forked_from for branch in branches] == [reading, reading]  # ①
    assert sorted(branch.prompts[-1] for branch in branches) == [
        "Add subtract, as briefly as you can.",
        "Add subtract, with a docstring and type hints.",
    ]
    assert all(branch.prompts[0] == READ for branch in branches)  # ②
    assert reading.prompts == [READ]  # ③


async def test_a_cli_that_cannot_fork_starts_afresh() -> None:
    agent = fakes.FakeAgentDriver(forks=False)  # ④

    await fakes.run_fake("twoways", "Add subtract", agents={"agent": agent})

    assert [session.forked_from for session in agent.sessions] == [None, None, None]
    assert [len(session.prompts) for session in agent.sessions] == [1, 1, 1]  # ⑤
```

```text
..                                                                       [100%]
2 passed in 0.08s
```

1. **`forked_from`** is the session a fake session was forked from. Both branches come from the
   reading.
2. **A fork's `prompts` start with its parent's**, which is the history it carries.
3. **The parent is untouched**: its prompts are the reading alone.
4. **`forks=False`** makes a fake CLI that cannot fork, so `fork` raises
   `UnsupportedOperation`.
5. **The fallback ran**: three fresh sessions, each told one thing only.

## Which CLIs can fork

`fork` is on every agent and needs no mixin. A CLI that cannot make the fork you ask for raises
`UnsupportedOperation`, at the call.

| CLI, as `-a` names it | Forks | Into another directory |
| --- | --- | --- |
| `claude`, `codex`, `kimi` | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> |
| `grok`, `mimo`, `opencode`, `pi`, `qwen`, an ACP CLI | <Badge type="tip" text="yes" /> | <Badge type="warning" text="same directory only" /> |
| `agy`, `cursor-agent`, `dsh`, `mcode` | <Badge type="danger" text="no" /> | <Badge type="danger" text="no" /> |

No CLI forks onto another machine.

## Variations

**Fork in the same directory.** Where the branches only answer, rather than write, fork them
into the parent's own environment, which more CLIs can do:

```python
careful = await agent.fork(session, env=workspace)
quick = await agent.fork(session, env=workspace)
await asyncio.gather(
    agent.run("how would you fix the retry logic, carefully?", session=careful),
    agent.run("how would you fix the retry logic, quickly?", session=quick),
)
```

**Fork or derive?** They sound alike and do opposite things:

| | Gives you | Carries the history? |
| --- | --- | --- |
| `agent.fork(session, env=…)` | another **conversation** of the same agent | yes |
| `agent.derive(permission=…)` | the same **agent** under a narrower grant | no: it holds no conversation |

`derive` is covered in [A flow that calls a
flow](/weaver/calling-flows#narrow-what-you-hand-on).

## Pitfalls

- **Take the child's first turn before the parent moves on.** A fork is cut at its own first
  turn. If the parent takes a turn in between, the child's first turn is refused rather than
  quietly branching from a later point:

  ```python
  child = await agent.fork(session, env=workspace)
  await agent.run("carry on here", session=session)  # parent moves on
  await agent.run("and here", session=child)  # [!code error]
  ```

  ```text
  SessionError: claude: the conversation this one was forked from has taken a turn since; fork it again to branch from where it is now
  ```

  Fork again when you want the newer point. Turns on a child never move its parent, so
  `twoways`, which only ever turns the children, is safe.
- **A session with no turn has nothing to carry.** Forking one raises
  `SessionError: the session to fork has taken no turn to carry on from`. `spawn` a fresh one
  instead.
- **The fake kit does not hold you to these two rules.** A fake agent forks a fresh session and
  runs a stale child without complaint, so check the order of your turns on a real CLI before
  you rely on it.

## Next steps

- [Many turns at once](/weaver/async-flows), for driving the branches together
- [Worktrees, copies and scratch](/weaver/worktrees), for branching the files rather than the
  conversation
- [Many conversations at once](/user/conversations), for reading the branches at the prompt
- [Reference › `Agent.fork`](/reference/flows#fork) and [`Session`](/reference/flows#session)
