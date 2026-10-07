# Build under test

**Thirty minutes.** In this tutorial you grow [your first flow](/weaver/writing-a-flow) into
one worth keeping. One agent writes code, the flow runs `pytest` after every turn, and a second
agent reviews whatever passed. The loop ends when the reviewer is satisfied, not when the
writer says it is finished.

```text
          ┌──────────── review notes ────────────┐
          ▼                                      │
   builder's turn ──▶ pytest ──green──▶ reviewer's turn ──good──▶ done
          ▲             │
          └──── red ────┘
```

By the end you will have used, once each, the pieces most flows are made of: two roles, a
permission, a shell on the workspace, an answer in a shape, and a loop. Every step is written
out; type it as it is.

::: info Before you start
- You have run `twice` from [Your first flow](/weaver/writing-a-flow).
- One coding agent CLI is signed in. This page runs Claude Code.
- `python -m pytest` works on your machine.
:::

## Step 1: make a project to work in

```sh
mkdir -p ~/tmp/flowlab && cd ~/tmp/flowlab
git init -q
```

Give the agent something to extend: Roman numerals, one direction only.

```sh
cat > roman.py <<'PY'
"""Roman numerals."""

VALUES = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def to_roman(n: int) -> str:
    """The Roman numeral for 1 <= n <= 3999."""
    if not 1 <= n <= 3999:
        raise ValueError(f"out of range: {n}")
    out = []
    for value, sign in VALUES:
        while n >= value:
            out.append(sign)
            n -= value
    return "".join(out)
PY
cat > test_roman.py <<'PY'
import pytest

from roman import to_roman


@pytest.mark.parametrize(
    ("n", "sign"),
    [(1, "I"), (4, "IV"), (9, "IX"), (14, "XIV"), (40, "XL"), (1990, "MCMXC"), (3999, "MMMCMXCIX")],
)
def test_to_roman(n, sign):
    assert to_roman(n) == sign


@pytest.mark.parametrize("n", [0, -1, 4000])
def test_to_roman_refuses(n):
    with pytest.raises(ValueError):
        to_roman(n)
PY
python -m pytest -q
```

```text
..........                                                               [100%]
10 passed in 0.01s
```

Ten green tests: the baseline the flow will hold the agent to. Commit them, less what running
them left behind, so that `git diff` shows exactly what the agent changes later:

```sh
printf '__pycache__/\n.pytest_cache/\n' > .gitignore
git add -A && git commit -qm "roman numerals, one way"
```

## Step 2: a builder and a reviewer

Start from the shape of `twice`, with two roles instead of one:

```sh
mkdir -p .hmz/flows/build_under_test
```

```python
# .hmz/flows/build_under_test/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)

REVIEW = """You are reviewing a coding agent's work in the directory you are running in. \
Read what it actually wrote, with `git diff`, `git status` and the files themselves, and \
judge whether the task below is done and the code is worth keeping. Be sceptical: a test \
weakened, a case special-cased, or a function stubbed to make the suite pass is the thing \
you are most here to catch.

Task:
"""


class Agents(AgentCollection):
    builder: Agent  # [!code highlight]
    reviewer: Agent  # [!code highlight]


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def build_under_test(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """One agent writes, pytest judges, a reviewer reads what passed."""
    builder, reviewer, workspace = agents["builder"], agents["reviewer"], envs["workspace"]
    working = await builder.spawn()
    await builder.run(task, session=working, env=workspace)
    reading = await reviewer.spawn()  # [!code highlight]
    print(await reviewer.run(REVIEW + task, session=reading, env=workspace))
```

This already runs: the builder takes a turn, then the reviewer reads the result. Two things to
notice:

- **Each role is filled separately** on the command line, so the reviewer can be a stronger
  model than the builder, or another CLI altogether.
- **The reviewer gets a session of its own**, so it reads the repository rather than the
  builder's account of it.

The flow is named after its function, and found by its directory, which is what makes
`-f build_under_test` mean this one.

## Step 3: keep the reviewer from writing

A reviewer that fixes what it finds has stopped reviewing. What a role may touch is the flow's
to declare, as a `Permission` on the role's class:

```python
from hmz.flows import (
    ...
    LocalEnv,
    Permission,  # [!code ++]
    PermissionKind,  # [!code ++]
    flow,
)


class Reviewer(Agent):  # [!code ++]
    """Reads what the builder wrote, and writes nothing."""  # [!code ++]

    _permission = Permission(local=PermissionKind.READ)  # [!code ++]


class Agents(AgentCollection):
    builder: Agent
    reviewer: Agent  # [!code --]
    reviewer: Reviewer  # [!code ++]
```

`local=PermissionKind.READ` means the reviewer may read the directory it works in and write
none of it, whichever CLI fills the role. [Permissions](/user/permissions) has the other
scopes.

## Step 4: run the tests yourself

Asking the agent whether the tests pass gets you its opinion. Running them gets you an exit
code. A flow may run programs in a workspace whose type carries `ShellEnvMixin`:

```python
from hmz.flows import (
    ...
    PermissionKind,
    ShellEnvMixin,  # [!code ++]
    flow,
)


class Workspace(LocalEnv, ShellEnvMixin):  # [!code ++]
    """The project the run was started in, where the flow runs the tests."""  # [!code ++]


class Envs(EnvCollection):
    workspace: LocalEnv  # [!code --]
    workspace: Workspace  # [!code ++]


TAIL = 4000  # [!code ++]


async def suite(workspace: Workspace) -> tuple[bool, str]:  # [!code ++]
    """Runs the tests: whether they passed, and the end of what they said."""  # [!code ++]
    code, out, err = await workspace.exec(["python", "-m", "pytest", "-q"])  # [!code ++]
    return code == 0, (out + err)[-TAIL:]  # [!code ++]
```

`exec` runs one program in the workspace and answers with its exit status, stdout and stderr.
`TAIL` keeps the end of pytest's output, which is the part that says what failed.

## Step 5: ask the reviewer for a verdict

A review in prose leaves your code hunting paragraphs for "looks good to me". Give the turn an
`output_schema`, a pydantic model, and it answers with an instance of it instead:

```python
from pydantic import BaseModel, ConfigDict, Field  # [!code ++]

from hmz.flows import (
    ...
)


class Review(BaseModel):  # [!code ++]
    """What one round's review comes to."""  # [!code ++]

    model_config = ConfigDict(extra="forbid")  # [!code ++]

    good: bool = Field(  # [!code ++]
        description="True only if the task is done and the code is worth keeping: no "  # [!code ++]
        "duplication left behind, no dead code, names that say what they hold, and no test "  # [!code ++]
        "weakened or special-cased to pass. False if anything is left to do or to tidy."  # [!code ++]
    )  # [!code ++]
    notes: str = Field(  # [!code ++]
        description="The review, written as a message to the coding agent: what is done, "  # [!code ++]
        "what to change, and where. It is passed on word for word."  # [!code ++]
    )  # [!code ++]
```

The `description` strings are handed to the CLI as part of the shape it must answer in, so they
are the instruction. Edit them when you want stricter reviews. See [Answers in a
shape](/weaver/shapes).

## Step 6: loop until the reviewer is satisfied

Now replace the body of the function with a loop. This is the whole file, as it should read
when you are done:

```python
# .hmz/flows/build_under_test/__init__.py
from pydantic import BaseModel, ConfigDict, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Permission,
    PermissionKind,
    ShellEnvMixin,
    flow,
)

REVIEW = """You are reviewing a coding agent's work in the directory you are running in. \
Read what it actually wrote, with `git diff`, `git status` and the files themselves, and \
judge whether the task below is done and the code is worth keeping. Be sceptical: a test \
weakened, a case special-cased, or a function stubbed to make the suite pass is the thing \
you are most here to catch.

Task:
"""

TAIL = 4000


class Reviewer(Agent):  # ①
    """Reads what the builder wrote, and writes nothing."""

    _permission = Permission(local=PermissionKind.READ)


class Agents(AgentCollection):
    builder: Agent
    reviewer: Reviewer


class Workspace(LocalEnv, ShellEnvMixin):  # ②
    """The project the run was started in, where the flow runs the tests."""


class Envs(EnvCollection):
    workspace: Workspace


class Review(BaseModel):  # ③
    """What one round's review comes to."""

    model_config = ConfigDict(extra="forbid")

    good: bool = Field(
        description="True only if the task is done and the code is worth keeping: no "
        "duplication left behind, no dead code, names that say what they hold, and no test "
        "weakened or special-cased to pass. False if anything is left to do or to tidy."
    )
    notes: str = Field(
        description="The review, written as a message to the coding agent: what is done, "
        "what to change, and where. It is passed on word for word."
    )


async def suite(workspace: Workspace) -> tuple[bool, str]:  # ④
    """Runs the tests: whether they passed, and the end of what they said."""
    code, out, err = await workspace.exec(["python", "-m", "pytest", "-q"])
    return code == 0, (out + err)[-TAIL:]


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def build_under_test(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:  # ⑤
    """One agent writes, pytest judges, a reviewer reads what passed."""
    builder, reviewer, workspace = agents["builder"], agents["reviewer"], envs["workspace"]
    working = await builder.spawn()  # ⑥
    prompt = task
    while True:  # ⑦
        await builder.run(prompt, session=working, env=workspace)
        passed, said = await suite(workspace)
        if not passed:  # ⑧
            prompt = f"`python -m pytest -q` fails. Read this and fix it.\n\n{said}"
            continue
        reading = await reviewer.spawn()  # ⑨
        review = await reviewer.run(  # ⑩
            REVIEW + task, session=reading, env=workspace, output_schema=Review
        )
        if review.good:  # ⑪
            print(review.notes)
            return review.notes
        prompt = review.notes  # ⑫
```

### What each part does

1. **`Reviewer(Agent)` with `_permission`** narrows the role. An agent given for it runs every
   session under exactly this grant: reading the workdir, writing none of it.
2. **`Workspace(LocalEnv, ShellEnvMixin)`** is the directory the run started in, plus the right
   for the flow to run programs there. Without the mixin, `exec` raises `CapabilityNotGranted`.
3. **`Review`** is the shape the reviewer answers in. `extra="forbid"` refuses an answer with
   fields you did not ask for; the `description`s are the reviewer's instructions.
4. **`suite`** is the check, as a plain function: easy to read, easy to swap for another
   test command.
5. **`-> str`**: the flow returns the review it ended on, for a
   [calling flow](/weaver/calling-flows) to read, and for a test to assert on in Step 9.
6. **The builder's `spawn` is outside the loop**, so it keeps one conversation and remembers
   every round: what it tried, and what it was told.
7. **`while True`** has no round limit of its own. If the reviewer is never satisfied, the
   run's budget ends it: the turn that finds it spent raises `BudgetExceeded`.
8. **A red suite never reaches the reviewer.** pytest's own words become the builder's next
   prompt, and the loop goes round again.
9. **The reviewer's `spawn` is inside the loop**, so every review starts fresh, with no memory
   of having passed or failed this work before.
10. **`output_schema=Review`** makes `run` return a `Review` instance, not a string. An answer
    that does not fit raises `OutputSchemaError`.
11. **`review.good`** ends the loop on a field the reviewer filled in, not a phrase in a
    paragraph. The flow prints the notes and returns them.
12. **`review.notes`** is otherwise passed to the builder word for word, as its next prompt.

## Step 7: run it

Put the task in a shell variable, so the command stays readable:

```sh
task="Add from_roman(s: str) -> int to roman.py, the exact inverse of \
to_roman, refusing anything that is not a canonical numeral. Add tests \
for it in test_roman.py, including a round-trip over 1..3999."
```

Each role takes its own agent. Here the reviewer thinks harder than the builder:

::: code-group

```sh [Claude Code]
hmz exec -f build_under_test \
    -a builder=claude/claude-sonnet-5-5:medium \
    -a reviewer=claude/claude-sonnet-5-5:high \
    -p budget.cost=2,budget.duration=30m "$task"
```

```text [At the prompt]
$@local/build_under_test Add from_roman(s: str) -> int to roman.py, the exact inverse of to_roman, refusing anything that is not a canonical numeral. Add tests for it in test_roman.py, including a round-trip over 1..3999.
```

:::

`-p budget.cost=2,budget.duration=30m` lets the run spend two dollars or half an hour, whichever
comes first.
It ends by itself, printing the review it ended on. A real run, abridged:

```text
● builder is working
● Read(~/tmp/flowlab/roman.py)
● Read(~/tmp/flowlab/test_roman.py)
● Edit(~/tmp/flowlab/roman.py)
● Edit(~/tmp/flowlab/test_roman.py)
● Edit(~/tmp/flowlab/test_roman.py)
● Bash(cd ~/tmp/flowlab && python -m pytest -q test_roman.py 2>&1 | tail -15)
● I added `from_roman` to `roman.py`, and all 43 tests in `test_roman.py` pass.
  …
✻ input 8 · output 1.8k · cache_read 64.0k · cache_write 8.0k · $0.05 · claude-sonnet-5-5 · builder
…
✻ Worked for 16s · builder
● reviewer is working
● Bash(cd ~/tmp/flowlab && git diff -- roman.py test_roman.py && cat roman.py && python -m pytest -q 2>&1 | tail -5)
● StructuredOutput(The task is done and the code is worth keeping. I read the diff and ran the suite: 43 tests pass. …)
✻ input 4 · output 990 · cache_read 17.1k · cache_write 19.0k · $0.06 · claude-sonnet-5-5 · reviewer
{"good":true,"notes":"The task is done and the code is worth keeping. I read the diff and ran the suite: 43 tests pass.\n\n**`from_roman` in `roman.py`:** …"}
✻ Worked for 12s · reviewer
The task is done and the code is worth keeping. I read the diff and ran the suite: 43 tests pass.

**`from_roman` in `roman.py`:**
- It greedily parses the string using the same `VALUES` table that `to_roman` uses.
- It then requires that the whole string was consumed, that the value is in 1..3999, and that `to_roman(n) == s`.
- That last check makes it the exact inverse of `to_roman`. Anything non-canonical is rejected (`IIII`, `IC`, `VX`, `IVI`, lowercase, whitespace, non-ASCII, empty string, `MMMM`).
…
- The existing `to_roman` tests are untouched, so nothing was weakened.
…
```

Read it against the code:

- **The builder's turn** ran the tests itself, but the flow did not take its word for it: it
  ran `python -m pytest -q` between the turns, with nothing on screen, and found it green.
- **The reviewer's turn** answered through `StructuredOutput`, which is how Claude Code
  answers in a shape. The JSON line after the usage is that answer, which `run` read into a
  `Review`.
- **The last block** is `print(review.notes)`: the review the flow ended on, and what it
  returned. `good` was true on the first round, so there was no second.

Your run will read differently, and may take more rounds: a builder that leaves a test red
gets pytest's output back, and a reviewer that answers `good: false` sends its notes.

## Step 8: check the work

Run the tests yourself:

```sh
python -m pytest -q
```

```text
...........................................                              [100%]
43 passed in 0.03s
```

Then look at what the agent actually wrote:

```sh
git diff roman.py
```

```diff
@@ -17,3 +17,18 @@ def to_roman(n: int) -> str:
             out.append(sign)
             n -= value
     return "".join(out)
+
+
+def from_roman(s: str) -> int:
+    """The inverse of to_roman; refuses anything to_roman would not produce."""
+    if not isinstance(s, str):
+        raise TypeError(f"expected str, not {type(s).__name__}")
+    n = 0
+    i = 0
+    for value, sign in VALUES:
+        while s.startswith(sign, i):
+            n += value
+            i += len(sign)
+    if i != len(s) or not 1 <= n <= 3999 or to_roman(n) != s:
+        raise ValueError(f"not a canonical Roman numeral: {s!r}")
+    return n
```

Ten tests became forty-three. Note `to_roman(n) != s`: greedy parsing alone would accept `IIII`
and `VV`, and checking the round trip is what makes "canonical" mean something. That is the
kind of thing the reviewer is there to look for, and the kind of thing to look for yourself
before you commit.

## Step 9: test the flow without spending

The run above cost real money and took minutes. The flow's own decisions (red goes back to the
builder, green goes to a fresh reviewer, notes are passed on word for word) can be tested in
milliseconds on fakes. Save this under `.hmz/tests/`:

```python
# .hmz/tests/test_build_under_test.py
from hmz.flows import PermissionKind
from hmz.sdk import fakes

SUITE = ("python", "-m", "pytest", "-q")
GOOD = {"good": True, "notes": "done and worth keeping"}


async def test_a_red_suite_goes_back_to_the_builder() -> None:
    runs = iter([(1, "1 failed", ""), (0, "30 passed", "")])  # ①
    here = fakes.FakeEnvDriver(run=lambda command, env: next(runs))
    builder = fakes.FakeAgentDriver()
    reviewer = fakes.FakeAgentDriver(reply=GOOD)  # ②
    said = await fakes.run_fake(
        "build_under_test",
        "add from_roman",
        agents={"builder": builder, "reviewer": reviewer},
        local=here,
    )
    assert said == "done and worth keeping"  # ③
    assert builder.prompts[1].startswith("`python -m pytest -q` fails.")  # ④
    assert len(reviewer.sessions) == 1


async def test_the_notes_are_the_next_prompt() -> None:
    reviewer = fakes.FakeAgentDriver(
        reply=[{"good": False, "notes": "IIII is accepted"}, GOOD]  # ⑤
    )
    builder = fakes.FakeAgentDriver()
    await fakes.run_fake(
        "build_under_test",
        "add from_roman",
        agents={"builder": builder, "reviewer": reviewer},
        local=fakes.FakeEnvDriver(run={SUITE: (0, "30 passed", "")}),
    )
    assert builder.prompts == ["add from_roman", "IIII is accepted"]
    assert (len(builder.sessions), len(reviewer.sessions)) == (1, 2)  # ⑥
    assert reviewer.sessions[0].permission.local == PermissionKind.READ  # ⑦
```

```sh
uvx --with 'hmz>=0.1.0b1' \
    --with pytest-asyncio pytest -q -o asyncio_mode=auto .hmz/tests
```

```text
..                                                                       [100%]
2 passed in 0.09s
```

1. **A scripted workspace.** The function answers `exec`: red the first time, green the
   second.
2. **A scripted reviewer.** A mapping is read into `Review`, as a real answer would be.
3. **`run_fake` returns what the flow returned**: the notes it ended on.
4. **Red went back to the builder**, with pytest's words, and the reviewer was asked once.
5. **A list replies turn by turn**: first "not yet", then "good".
6. **One builder session, two reviewer sessions**: the builder remembered, each review was
   fresh.
7. **The reviewer's grant** is what `_permission` declared, whatever CLI fills the role.

**Why `.hmz/tests/`:** pytest skips directories whose names start with `.`, so the
`python -m pytest -q` the flow runs never collects the flow's own tests. Put them in `tests/`
and every round would try to import `hmz` in the project's Python, and fail.
[Testing a flow](/weaver/testing-flows) has the rest of the kit.

## What to change

**Swap `pytest` for what your project uses.** `suite()` is one `exec`. Point it at `npm test`,
`cargo test` or `go test ./...`. To hand it a shell line as a string instead, put
`BashEnvMixin` on the workspace in place of `ShellEnvMixin`.

**Gate on more than tests.** Add a linter to `suite()` and hand the builder both outputs.

**Give it a round limit.** A `rounds: int = 12` param is two lines, and whoever runs the flow
sets it with `-p rounds=20`. See [Params of its own](/weaver/flow-settings).

**Survive a turn that fails.** A failed turn raises `HarnessError`, and ends the run.
[Loops](/weaver/loops) shows how to catch it and carry on.

**Put another CLI on review.** `-a reviewer=codex/gpt-5.6-sol:high` changes nothing in the
flow: the role asks for no more than any CLI can do.

## Pitfalls

- **A reviewer that can write will fix instead of judging.** Keep `_permission` on it.
- **A suite that cannot run is red for ever.** If `python -m pytest` is not installed where the
  run starts, every round is "the tests fail" until the budget is spent. Run Step 1's check
  first.
- **The budget is the only brake on `while True`.** Give every run a budget you would be
  content to spend in full, or add a round limit.

## Next steps

- [Loops](/weaver/loops): what the next turn remembers, and what ends a loop.
- [Answers in a shape](/weaver/shapes): more on `output_schema`.
- [Testing a flow](/weaver/testing-flows): the whole fake kit.
- Reference: [`Permission`](/reference/flows#permission),
  [`ShellEnvMixin`](/reference/flows#what-an-environment-can-do),
  [`Agent.run`](/reference/flows#run).
