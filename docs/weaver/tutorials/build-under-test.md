# Build under test

**Thirty minutes.** You will grow [your first flow](/weaver/writing-a-flow) into one worth
keeping. One agent writes code, the flow runs `pytest` after every turn, and a second agent
reviews whatever passed. The loop ends when the reviewer is satisfied, not when the writer says
it is finished.

```text
          ┌──────────── review notes ────────────┐
          ▼                                      │
   builder's turn ──▶ pytest ──green──▶ reviewer's turn ──good──▶ done
          ▲             │
          └──── red ────┘
```

::: tip Before you start
You have run `twice` from [Your first flow](/weaver/writing-a-flow), one backend is signed in,
and `python -m pytest` works on your machine.
:::

## Step 1 — make a project to work in

```sh
mkdir -p ~/tmp/flowlab && cd ~/tmp/flowlab
git init -q
```

Something for the agent to extend — Roman numerals, one direction only:

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
..........                                   [100%]
10 passed in 0.29s
```

Ten green tests — the baseline the flow will hold the agent to.

```sh
git add -A && git commit -qm "roman numerals, one way"
```

## Step 2 — a builder and a reviewer

Start from the shape of `twice`, with two roles instead of one:

```sh
mkdir -p .humanize/flows/build_under_test
```

```python
# .humanize/flows/build_under_test/__init__.py
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
    working = await builder.spawn(env=workspace)
    await builder.run(task, session=working)
    reading = await reviewer.spawn(env=workspace)  # [!code highlight]
    print(await reviewer.run(REVIEW + task, session=reading))
```

This already runs: the builder takes a turn, then the reviewer reads the result. The reviewer
gets a session of its own, so it reads the repository rather than the builder's account of it.
The flow is named after its directory, which is what makes `-f build_under_test` mean this one.

## Step 3 — keep the reviewer from writing

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

`local=PermissionKind.READ` means it may read the directory it works in and write none of it,
whichever CLI fills the role. [Permissions](/user/permissions) has the other scopes.

## Step 4 — run the tests yourself

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

## Step 5 — ask the reviewer for a verdict

A review in prose leaves your code hunting paragraphs for "looks good to me". Give the turn an
`output_schema` — a pydantic model — and it answers with an instance of it instead:

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

The `description` strings are handed to the CLI as part of the shape it must answer in, so
they are the instruction. Edit them when you want stricter reviews. See [Answers in a
shape](/weaver/shapes).

## Step 6 — loop until the reviewer is satisfied

Now the function itself:

```python
@flow(agents=Agents, envs=Envs, params=FlowParams)
async def build_under_test(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:  # [!code --]
) -> str:  # [!code ++]
    """One agent writes, pytest judges, a reviewer reads what passed."""
    builder, reviewer, workspace = agents["builder"], agents["reviewer"], envs["workspace"]
    working = await builder.spawn(env=workspace)
    await builder.run(task, session=working)  # [!code --]
    reading = await reviewer.spawn(env=workspace)  # [!code --]
    print(await reviewer.run(REVIEW + task, session=reading))  # [!code --]
    prompt = task  # [!code ++]
    while True:  # [!code ++]
        await builder.run(prompt, session=working)  # [!code ++]
        passed, said = await suite(workspace)  # [!code ++]
        if not passed:  # [!code ++]
            prompt = f"`python -m pytest -q` fails. Read this and fix it.\n\n{said}"  # [!code ++]
            continue  # [!code ++]
        reading = await reviewer.spawn(env=workspace)  # [!code ++]
        review = await reviewer.run(REVIEW + task, session=reading, output_schema=Review)  # [!code ++]
        if review.good:  # [!code ++]
            print(review.notes)  # [!code ++]
            return review.notes  # [!code ++]
        prompt = review.notes  # [!code ++]
```

Four decisions are in those lines:

- **The builder's `spawn` is outside the loop,** so it keeps one conversation and remembers
  every round. **The reviewer's is inside,** so every review starts fresh.
- **A red suite never reaches the reviewer.** pytest's own words become the builder's next
  prompt.
- **The loop ends on `review.good`,** a field the reviewer filled in, not a phrase in a
  paragraph. The flow prints the review it ended on and returns it.
- **If the reviewer is never satisfied, the budget ends the run.** Every run is given one, and
  the turn that finds it spent stops the flow.

::: details The whole file
```python
# .humanize/flows/build_under_test/__init__.py
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


class Reviewer(Agent):
    """Reads what the builder wrote, and writes nothing."""

    _permission = Permission(local=PermissionKind.READ)


class Agents(AgentCollection):
    builder: Agent
    reviewer: Reviewer


class Workspace(LocalEnv, ShellEnvMixin):
    """The project the run was started in, where the flow runs the tests."""


class Envs(EnvCollection):
    workspace: Workspace


class Review(BaseModel):
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


async def suite(workspace: Workspace) -> tuple[bool, str]:
    """Runs the tests: whether they passed, and the end of what they said."""
    code, out, err = await workspace.exec(["python", "-m", "pytest", "-q"])
    return code == 0, (out + err)[-TAIL:]


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def build_under_test(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """One agent writes, pytest judges, a reviewer reads what passed."""
    builder, reviewer, workspace = agents["builder"], agents["reviewer"], envs["workspace"]
    working = await builder.spawn(env=workspace)
    prompt = task
    while True:
        await builder.run(prompt, session=working)
        passed, said = await suite(workspace)
        if not passed:
            prompt = f"`python -m pytest -q` fails. Read this and fix it.\n\n{said}"
            continue
        reading = await reviewer.spawn(env=workspace)
        review = await reviewer.run(REVIEW + task, session=reading, output_schema=Review)
        if review.good:
            print(review.notes)
            return review.notes
        prompt = review.notes
```
:::

## Step 7 — run it

```sh
task="Add from_roman(s: str) -> int to roman.py, the exact inverse of \
to_roman, refusing anything that is not a canonical numeral. Add tests \
for it in test_roman.py, including a round-trip over 1..3999."
```

Each role takes its own agent, so the reviewer can think harder than the builder, or be
another CLI altogether:

::: code-group

```sh [Claude Code]
hmz exec -f build_under_test \
    -a builder=claude/claude-opus-5:high \
    -a reviewer=claude/claude-opus-5:max \
    -b cost=5,duration=1h "$task"
```

```sh [Codex]
hmz exec -f build_under_test \
    -a builder=codex/gpt-5.6-sol:high \
    -a reviewer=codex/gpt-5.6-sol:xhigh \
    -b cost=5,duration=1h "$task"
```

```sh [DeepSeek Harness]
hmz exec -f build_under_test \
    -a builder=dsh/deepseek-v4-flash:high \
    -a reviewer=dsh/deepseek-v4-pro:high \
    -b cost=5,duration=1h "$task"
```

```sh [Two CLIs]
hmz exec -f build_under_test \
    -a builder=codex/gpt-5.6-sol:high \
    -a reviewer=claude/claude-opus-5:max \
    -b cost=5,duration=1h "$task"
```

```text [At the prompt]
$local/build_under_test Add from_roman(s: str) -> int to roman.py, the exact inverse of to_roman, refusing anything that is not a canonical numeral. Add tests for it in test_roman.py, including a round-trip over 1..3999.
```

:::

`-b cost=5,duration=1h` lets the run spend five dollars or an hour, whichever comes first. It
ends by itself, printing the review it ended on. Abridged, a run that passes on its first round
reads:

```text
● builder is working
● Read(roman.py)
● Edit(roman.py)
● Edit(test_roman.py)
● Added from_roman, a round-trip test over 1..3999, and cases it refuses.
✻ Worked for 96s · builder
● reviewer is working
● Read(roman.py)
● Read(test_roman.py)
✻ Worked for 38s · reviewer
Done and worth keeping. from_roman is a genuine inverse: greedy descent
over VALUES, then `to_roman(n) != s`, accepts exactly the canonical
numerals. The round-trip over 1..3999 and the refusal cases cover the
contract. No existing test was weakened, and nothing is left to tidy.
```

## Step 8 — check the work

```sh
python -m pytest -q
```

```text
..............................               [100%]
30 passed in 0.23s
```

Ten tests became thirty. Look at what it actually wrote:

```sh
git diff
```

```python
def from_roman(s: str) -> int:
    """The exact inverse of to_roman: the int for canonical numeral s."""
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = 0
    rest = s
    for value, sign in VALUES:
        while rest.startswith(sign):
            n += value
            rest = rest[len(sign):]

    if rest or not 1 <= n <= 3999 or to_roman(n) != s:  # [!code highlight]
        raise ValueError(f"not a canonical Roman numeral: {s!r}")
    return n
```

Note `to_roman(n) != s`. Greedy descent alone would accept `IIII` and `VV`; checking the round
trip is what makes "canonical" mean something — the kind of thing the reviewer is there for.

## What to change

**Swap `pytest` for what your project uses.** `suite()` is one `exec`. Point it at `npm test`,
`cargo test` or `go test ./...`. To hand it a shell line as a string instead, put
`BashEnvMixin` on the workspace in place of `ShellEnvMixin`.

**Gate on more than tests.** Add a linter to `suite()` and hand the builder both outputs.

**Give it a round limit.** A `rounds: int = 12` param is two lines, and whoever runs the flow
sets it with `-p rounds=20`. See [Params of its own](/weaver/flow-settings).

**Survive a turn that fails.** A failed turn raises, and ends the run. [Loops](/weaver/loops)
shows how the flowverse's own loops catch it and carry on.

**Next:** [test it without spending tokens](/weaver/testing-flows).
