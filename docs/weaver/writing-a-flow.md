# Your first flow

In this guide you write `twice`: a flow that has one coding agent do a task, then read its own
work back and fix what is wrong. You run it on a real agent, then test it without spending a
token. It takes about five minutes.

Write a flow when you would otherwise type the same instructions to an agent again and again:
the flow types them for you, in the order you chose, and decides when to stop.

::: info Before you start
- humanize installed and one coding agent CLI signed in. See [Installation](/user/installation).
- A flow run behind you. The [User Guide](/user/) starts there.
- A git repository you don't mind an agent editing. To follow along exactly, make one:

  ```sh
  mkdir calc && cd calc && git init
  printf 'def add(a, b):\n    return a + b\n' > calc.py
  git add calc.py && git commit -m "add calc.py"
  ```

:::

## What a flow is

A **flow** is an `async` Python function with `@flow` on it. The decorator says three things the
function needs, and the runtime hands it exactly those when it runs:

| It declares | As | Filled by |
| --- | --- | --- |
| the **agents** it drives, one per **role** | an `AgentCollection` subclass | whoever runs it, with `-a ROLE=CLI/MODEL:EFFORT` |
| the **environments** they work in: a directory on a machine | an `EnvCollection` subclass | the runtime, for a `LocalEnv`; otherwise `-e` |
| its **params**: settings of its own | a `FlowParams` subclass | `-p KEY=VALUE`, or a form at the prompt |

The function never names a CLI or a model. It names a role, `builder`, and asks it for work in
two steps:

- **`spawn`** opens a **session**: one conversation of one agent, in one environment.
- **`run`** takes a **turn** in that session: sends one prompt and waits until the agent is done
  with it. It returns what the agent said.

A second `run` in the same session carries on the same conversation. That is all `twice` needs.

## Write the flow

A flow is a directory under `.humanize/flows/` in your project, named after the flow, with the
code in its `__init__.py`:

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


class Agents(AgentCollection):  # ①
    builder: Agent


class Envs(EnvCollection):  # ②
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)  # ③
async def twice(  # ④
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Do the work, then read it back and fix what is wrong."""  # ⑤
    builder = agents["builder"]  # ⑥
    session = await builder.spawn(env=envs["workspace"])  # ⑦
    await builder.run(task, session=session)  # ⑧
    await builder.run(  # ⑨
        "Now review what you just did, and fix anything that is wrong.",
        session=session,
    )
```

### What each part does

1. **`class Agents(AgentCollection)`** declares the roles. `builder: Agent` says the flow drives
   one agent, called `builder`, and asks nothing of it beyond taking turns. The role's type is
   where you would ask for more, such as a [hook](/weaver/hooks) or a [goal](/weaver/goals):
   the flow is then refused on a CLI that cannot do it.
2. **`class Envs(EnvCollection)`** declares where the agents work. `workspace: LocalEnv` is the
   directory the run was started in. The runtime fills a `LocalEnv` itself, so nobody names it
   on the command line.
3. **`@flow(agents=…, envs=…, params=…)`** makes the function a flow and says what it takes.
   All three keywords are required. `params=FlowParams` means no
   [params of its own](/weaver/flow-settings). The flow's name is the function's name.
4. **The signature is fixed.** A flow is `async`, takes the task as its one positional
   argument, and takes `agents`, `envs`, `params` and `ctx` as keyword-only arguments. `ctx`
   is the run's [context](/reference/flows#flowcontext): its budget, what it has spent, and
   state that survives a stop. `twice` does not use it, but still has to take it.
5. **The docstring's first line** is what `/flow` shows beside the flow's name.
6. **`agents["builder"]`** is the agent that fills the role, whichever CLI and model that is.
7. **`spawn(env=…)`** opens a session in the workspace. Nothing is sent to the agent yet.
8. **`run(task, session=…)`** sends the task as the first prompt and waits for the turn to
   end. It returns the agent's answer as a string, which `twice` ignores.
9. **The second `run`** is in the same session, so the agent remembers the first turn and can
   review its own change. A new `spawn` here would start a stranger with no memory of it.

The flow ends when the function returns. Every session it opened is closed then.

## Run it

::: code-group

```text [At the prompt]
$local/twice add a subtract function to calc.py
```

```sh [Claude Code]
hmz exec -f twice -a builder=claude/claude-sonnet-5-5:high -b cost=1 \
    "add a subtract function to calc.py"
```

```sh [Codex]
hmz exec -f twice -a builder=codex/gpt-5.6-sol:high -b cost=1 \
    "add a subtract function to calc.py"
```


:::

- **At the prompt**, your project's flows are offered as `local/<name>`. The first time, the
  flow's menu asks what `builder` runs and what the run may spend. After that, the line alone
  starts it.
- **On the command line**, `-a builder=…` fills the role by its name, as
  `CLI/MODEL:EFFORT`. Use a model your account can name: `/flow` lists them.
- **`-b cost=1`** is the run's [budget](/features/allowances), in US dollars. `hmz exec`
  refuses to start a flow without one.

This is a real run on Claude Code:

```text
● builder is working
● Read(/home/you/calc/calc.py)
● Edit(/home/you/calc/calc.py)
● I added `subtract(a, b)` to `calc.py`. It returns `a - b`. I haven't run it or added tests.
✻ input 6 · output 233 · cache_read 44.3k · cache_write 5.5k · $0.02 · claude-sonnet-5-5 · builder
I added `subtract(a, b)` to `calc.py`. It returns `a - b`. I haven't run it or added tests.
✻ Worked for 5s · builder
● builder is working
● Bash(cd /home/you/calc && cat calc.py && python3 -c "import calc; print(calc.subtract(5, 3), calc.subtract(1, 2.5))" && git s)
● Bash(cd /home/you/calc && rm -rf __pycache__ && git status --short)
● I found nothing wrong with the change.
  …
✻ input 6 · output 496 · cache_read 50.8k · cache_write 499 · $0.02 · claude-sonnet-5-5 · builder
I found nothing wrong with the change.
…
✻ Worked for 5s · builder
```

Read it turn by turn:

- **`● builder is working`** opens a turn, labelled with the role that is taking it.
- **`● Read(…)`, `● Edit(…)`, `● Bash(…)`** are the tools the agent reached for.
- **`✻ input … · $0.02 · …`** is what the turn spent, which counts against `-b`. The dollar
  figure appears where the model has a published price.
- **The line after it** is the turn's answer: the string `run` returned.
- **`✻ Worked for 5s`** closes the turn. The second turn follows in the same conversation, and
  the run ends when `twice` returns.

## Check it worked

The agent's change is in your working tree, for you to read and commit:

```sh
git diff
```

```diff
diff --git a/calc.py b/calc.py
index 4693ad3..3b474e9 100644
--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,6 @@
 def add(a, b):
     return a + b
+
+
+def subtract(a, b):
+    return a - b
```

The flow's own logic is worth a test too, and a test need not spend anything. The fake kit runs
`twice` exactly as `hmz exec` does, on an agent that answers from a script:

```python
# tests/test_twice.py
from hmz.sdk import fakes


async def test_twice_reads_its_own_work_back() -> None:
    builder = fakes.FakeAgentDriver()  # ①

    await fakes.run_fake(  # ②
        "twice", "add a --dry-run flag", agents={"builder": builder}
    )

    assert builder.prompts == [  # ③
        "add a --dry-run flag",
        "Now review what you just did, and fix anything that is wrong.",
    ]
```

```sh
uvx --with 'hmz @ git+https://github.com/humanfia/humanize.git' \
    --with pytest-asyncio pytest -q -o asyncio_mode=auto
```

```text
.                                                                        [100%]
1 passed in 0.09s
```

1. **`FakeAgentDriver()`** is a stand-in agent. With no script it answers `"ok"` to every
   turn, and it keeps every prompt it was sent.
2. **`run_fake("twice", …)`** finds the flow by the same name `-f` takes, from the directory
   pytest runs in, fills `builder` with the fake, and runs the flow to the end.
3. **`builder.prompts`** is what the flow said, in order. The assertion pins down that the
   task goes first and the review second, in the same session.

[Testing a flow](/weaver/testing-flows) scripts answers, workspaces, budgets and resuming.

## If it is refused

`hmz exec` checks the line and the flow before any agent starts, so a refusal costs nothing:

| `hmz exec: error: …` | Why, and the fix |
| --- | --- |
| `twice needs an agent for 'builder'; specify each with -a ROLE=CLI/MODEL:EFFORT` | No `-a builder=…` on the line. Add it. |
| `twice requires a budget: specify with -b duration=...,cost=...,output_tokens=...` | No `-b`. Add one, such as `-b cost=1`. |
| `twice: no flow is called 'twice', and it is not a path` | You are not in the project that holds `.humanize/flows/twice/`. `cd` into it, or pass `-f ./path/to/twice`. |
| ``twice: a flow takes `ctx` as a keyword argument`` | The signature is missing one of its keyword arguments. Take all four, even the ones you do not use. |
| `importing the flow at … failed: SyntaxError("'await' outside async function", …)` | `async` is missing from `def`. Write `async def`. |

## Where flows are found

A name is looked up nearest first, so a flow of yours can stand in for one of humanize's by
taking its name:

| Put it in | Run it with | At the prompt |
| --- | --- | --- |
| `.humanize/flows/twice/` in the project | `-f twice` | `$local/twice` |
| `~/.humanize/flows/twice/` | `-f twice`, when the project has none of that name | `$user/twice` |
| the flows humanize ships, and those you installed from a [flowverse](/weaver/flowverses) | `-f ralph_loop`, `-f theirs/review` | `$ralph_loop`, `$theirs/review` |
| anywhere else | `-f ./path/to/twice` | |

`-f local/twice` and `-f user/twice` say which one outright.

## Variations

**One file instead of a directory.** `.humanize/flows/twice.py` is a flow too. Use a directory
once the flow has files beside it, such as [skills](/user/skills) or helpers.

**Helpers the flow imports.** A file or directory whose name starts with `_` is not a flow. It
is somewhere to keep code the flows beside it import.

**The rest of `@flow`.**

| Keyword | Does |
| --- | --- |
| `name=` | Calls it this instead of the function's name. Letters, digits, `_`, `.` and `-`. |
| `description=` | Shows this beside it instead of the docstring's first line. |
| `hidden=True` | Leaves it out of the lists at the prompt. It still runs by name. |
| `resumable=True` | Lets a stopped run be picked up where it was, with `ctx.state`. See [Loops](/weaver/loops). |

One module can hold several flows, run as `<directory>:<name>`. See [A flow that calls a
flow](/weaver/calling-flows).

## Pitfalls

::: warning Agents run with approvals bypassed
Nobody is asked before an agent edits a file or runs a command. What it may touch is what its
role's `Permission` says, and unless you say otherwise that is writing the directory it works
in. See [Permissions](/user/permissions).
:::

- **A turn you do not `await` never runs.** `builder.run(…)` without `await` makes a coroutine
  and drops it. Python warns `coroutine 'AgentView.run' was never awaited`, and the agent is
  never asked. The test above fails on it: `builder.prompts` is one prompt short.
- **A new `spawn` forgets.** Each `spawn` is a new conversation. Keep the session in a variable
  for as long as the agent should remember.
- **The role's name is the contract.** `-a builder=…`, `agents["builder"]` and the test's
  `agents={"builder": …}` must agree. Renaming the role breaks every command line that runs
  the flow.

## Next steps

Everything else is added to a flow like this one, a piece at a time:

| To | Add | Read |
| --- | --- | --- |
| hold the agent to your test suite, and have a second agent review | a shell on the workspace, a reviewer role, a loop | [Build under test](/weaver/tutorials/build-under-test), the next page |
| start every round from nothing, or keep one conversation going | where `spawn` sits in the loop | [Loops](/weaver/loops) |
| take settings from `-p` and a form at the prompt | a `FlowParams` subclass | [Params of its own](/weaver/flow-settings) |
| get an answer your code can branch on | `output_schema=` a pydantic model | [Answers in a shape](/weaver/shapes) |
| keep an agent from writing | a `Permission` on its role | [Permissions](/user/permissions) |
| hand an agent skills | `_skills` on its role | [Skills](/user/skills) |
| use a CLI's own `/goal` | a mixin on the role | [Goals](/weaver/goals) |
| have several turns going at once | `asyncio.gather` | [Many turns at once](/weaver/async-flows) |
| build on a flow somebody else wrote | `load(…)` | [A flow that calls a flow](/weaver/calling-flows) |
| let whoever runs it say where the work lands, even another machine | a role typed `Env` instead of `LocalEnv`, given with `-e` | [Remote execution](/user/remote-execution) |

Every argument, refusal and return of the flow API is in [Reference › Flows](/reference/flows).
