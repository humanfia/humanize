# Build under test

**Thirty minutes.** You will write a flow of about seventy lines. One agent writes code, the
flow runs `pytest` between its turns, and a second agent reviews whatever passed. The loop ends
when the reviewer is satisfied, not when the writer says it is finished. Then you will test the
flow without spending a token.

It is a [weaver's](/weaver/) first flow, and it uses the things every flow is made of: roles,
an environment, a session, a schema, and a loop.

::: tip Before you start
Finish the [quickstart](/#run-a-flow) on the home page: humanize installed, one backend
working, one flow run. [Weave a flow](/#weave-a-flow) beside it is the short version of what
this tutorial builds in full. The backend here is DeepSeek Harness, which needs only an API
key.
:::

## What a flow actually is

A flow is a directory with an `__init__.py` in it, and that file has an `async` function marked
`@flow`, which says what it needs:

```python
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
    agent: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def once(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    session = await agents["agent"].spawn(env=envs["workspace"])
    await agents["agent"].run(task, session=session)
```

That is a complete flow. `agents` is what the person running it named on the command line,
one `-a role=…` per role; `envs` is where they work — `workspace`, typed `LocalEnv`, is the
directory the run was started in, which nobody has to name; `task` is the last argument they
typed.

Flows are looked for nearest first: `.humanize/flows/` in the project you are in,
`~/.humanize/flows/` for your own, then the ones humanize ships and every
[flowverse](/weaver/flowverses) you have added. This one goes in the project.

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

```console
..........                                                               [100%]
10 passed in 0.29s
```

Ten green tests — the baseline the flow will hold the agent to.

```sh
git add -A && git commit -qm "roman numerals, one way"
```

## Step 2 — say who the agents are, and where they work

```sh
mkdir -p .humanize/flows/build_under_test
```

Open `.humanize/flows/build_under_test/__init__.py` and start with the two roles and the one
environment:

```python
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    LocalEnv,
    Permission,
    PermissionKind,
    ShellEnvMixin,
)


class Reviewer(Agent):
    """Reads what the builder wrote, and writes nothing."""

    _permission = Permission(local=PermissionKind.READ)


class Agents(AgentCollection):
    """The two this drives: one that writes, and one that reads what it wrote."""

    builder: Agent
    reviewer: Reviewer


class Workspace(LocalEnv, ShellEnvMixin):
    """The project the run was started in, where the flow runs the tests."""


class Envs(EnvCollection):
    workspace: Workspace
```

The role names are what everything else uses: `-a builder=…` on the command line, `/flow`
asking what *the reviewer* runs, a [trace](/user/tracing) grouping that agent's sessions under
`reviewer`.

The two classes of your own say what each role needs. `Reviewer` is an agent that may read the
project and not write it — the CLI's own read-only mode, whichever CLI fills the role.
`Workspace` is the project directory with `ShellEnvMixin`, which is what lets the flow run
programs in it; without it, `exec` would raise `CapabilityNotGranted`. A flow gets exactly what
it declares.

## Step 3 — say what the reviewer has to answer

A reviewer that replies in prose leaves the flow reading paragraphs for a phrase like "looks
good to me". Ask for a shape instead:

```python
from pydantic import BaseModel, ConfigDict, Field


class Review(BaseModel):
    """What one round's review comes to: whether it is over, and what the builder is told."""

    model_config = ConfigDict(extra="forbid")

    good: bool = Field(
        description="True only if the task is done and the code is worth keeping: no "
        "duplication left behind, no dead code, names that say what they hold, and no test "
        "weakened or special-cased to pass. False if anything is left to do or to tidy."
    )
    notes: str = Field(
        description="The review, written as a message to the coding agent: what is done, "
        "what to change, and where. It is passed on word for word and is all the agent will "
        "hear from you."
    )
```

Those `description` strings are not comments. They are handed to the CLI as the shape it must
answer in, so they *are* the instruction — edit them when you want stricter reviews. See
[Answers in a shape](/weaver/shapes).

## Step 4 — run the tests yourself

The flow can run anything in its workspace between turns:

```python
#: How much of a failing suite the builder is shown. The end of pytest's output is the part
#: that says what failed; the front of it is a list of dots.
TAIL = 4000


async def suite(workspace: Workspace) -> tuple[bool, str]:
    """Runs the tests. Answers with whether they passed and the end of what they said."""
    code, out, err = await workspace.exec(["python", "-m", "pytest", "-q"])
    return code == 0, (out + err)[-TAIL:]
```

You could ask the agent to run the tests and tell you how it went. Running them yourself rests
the flow's decisions on an exit code, and an exit code cannot be optimistic. Running them
through the workspace rather than `subprocess` is what lets the same flow run against a project
on another machine, unchanged.

## Step 5 — write the loop

```python
from hmz.flows import FlowContext, FlowParams, HarnessError, flow

REVIEW = """You are reviewing a coding agent's work in the directory you are running in. \
`python -m pytest -q` passes -- that is not in question. Read what it actually wrote, with \
`git diff`, `git status` and the files themselves, and judge whether the task below is done \
and the code is worth keeping. Be sceptical: a test weakened, a case special-cased, or a \
function stubbed to make the suite green is the thing you are most here to catch.

Task:
"""


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def build_under_test(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """Build under test: one agent writes, pytest judges, a reviewer reads what passed."""
    builder, reviewer, workspace = agents["builder"], agents["reviewer"], envs["workspace"]
    working = await builder.spawn(env=workspace)
    prompt = task
    while True:
        # A turn that failed: take the round again rather than test a working tree the
        # builder never got to write to.
        try:
            await builder.run(prompt, session=working)
        except HarnessError:
            continue
        passed, said = await suite(workspace)
        if not passed:
            prompt = f"`python -m pytest -q` fails. Read this and fix it.\n\n{said}"
            continue
        reading = await reviewer.spawn(env=workspace)
        try:
            review = await reviewer.run(REVIEW + task, session=reading, output_schema=Review)
        except HarnessError:
            continue
        if review.good:
            print(review.notes)
            return review.notes
        prompt = review.notes or prompt
```

Five decisions are packed into those lines.

**`builder.spawn` sits outside the loop,** so the builder keeps one session and remembers every
round. **`reviewer.spawn` sits inside it,** which opens a fresh conversation each time: the
reviewer reads the repository, never the builder's account of it.

**A red suite never reaches the reviewer.** It becomes the builder's next prompt instead.

**A failed turn is caught and the round taken again,** so one rate limit does not end a loop
meant to run for hours. `except HarnessError` catches a turn that failed and nothing else: a
spent budget or a stop goes straight through it, which is what ends the loop when nothing else
does.

**The loop ends on `review.good`,** a boolean the reviewer filled in — not on a phrase in a
paragraph. It prints the review it ended on, and returns it for whatever called the flow.

**It is named after its directory,** `build_under_test` in `build_under_test/`, which is what
makes `-f build_under_test` mean this flow.

::: details The whole file
Everything above, in order: the imports, `Reviewer`, `Agents`, `Workspace`, `Envs`, `Review`,
`TAIL`, `suite`, `REVIEW` and the flow. Put a module docstring at the top.

```python
"""Build under test: one agent writes, pytest judges, a reviewer reads what passed."""

from pydantic import BaseModel, ConfigDict, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    LocalEnv,
    Permission,
    PermissionKind,
    ShellEnvMixin,
    flow,
)
```
:::

## Step 6 — run it

```sh
export DEEPSEEK_API_KEY=sk-…
hmz exec -f build_under_test \
    -a builder=dsh/deepseek-v4-flash:high \
    -a reviewer=dsh/deepseek-v4-pro:high \
    -b cost=5,duration=1h \
    "Add from_roman(s: str) -> int to roman.py, the exact inverse of to_roman, refusing anything that is not a canonical numeral. Add tests for it in test_roman.py, including a round-trip over 1..3999."
```

`-f build_under_test` finds the flow by name, because `.humanize/flows/` is the first place
humanize looks. A cheap fast model builds and a stronger one reviews, which is the right way
round: reviewing is the harder judgement, and it is one turn per round. `-b` is what the run may
spend — five dollars or an hour, whichever comes first — and is not optional: a loop with no
exit of its own needs something that stops it.

The run ends by itself, printing the review it ended on:

```console
Done and worth keeping. from_roman is a genuine inverse: greedy descent over VALUES
followed by `to_roman(n) != s` rejection accepts exactly the canonical numerals, and
the round-trip over 1..3999 plus the non-canonical refusal cases in test_roman.py
cover the contract. No existing test was weakened, no special-casing, and no dead
code or duplication. Nothing to change.
```

## Step 7 — check the work

```sh
python -m pytest -q
```

```console
..............................                                           [100%]
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

    if rest or not 1 <= n <= 3999 or to_roman(n) != s:
        raise ValueError(f"not a canonical Roman numeral: {s!r}")
    return n
```

Note `to_roman(n) != s` on the last line. Greedy descent alone would accept `IIII` and `VV`;
round-tripping through the existing function is what makes "canonical" mean something — the
kind of thing the reviewer's turn is for.

## Step 8 — test the flow without a model

That run cost real money, and the next change to the flow should not have to. The [fake
kit](/weaver/testing-flows) runs the same flow on agents that answer from a script and a
workspace that answers `pytest` from a table:

```python
# tests/test_build_under_test.py
from pathlib import Path

from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeEnvDriver, run_fake

FLOW = str(Path(__file__).parent.parent / ".humanize" / "flows" / "build_under_test")


async def test_a_red_suite_goes_back_to_the_builder() -> None:
    suites = iter([(1, "", "FAILED test_roman.py::test_from_roman"), (0, "30 passed", "")])
    workspace = FakeEnvDriver(run=lambda command, env: next(suites))
    builder = FakeAgentDriver()
    reviewer = FakeAgentDriver(reply={"good": True, "notes": "Done and worth keeping."})

    said = await run_fake(
        FLOW,
        "add from_roman",
        agents={"builder": builder, "reviewer": reviewer},
        local=workspace,
    )

    assert said == "Done and worth keeping."
    assert builder.prompts[0] == "add from_roman"
    assert "FAILED test_roman.py::test_from_roman" in builder.prompts[1]
    assert len(reviewer.prompts) == 1
```

```sh
uv add --dev pytest pytest-asyncio
uv run pytest -q -o asyncio_mode=auto
```

```console
.                                                                        [100%]
1 passed in 0.09s
```

A red suite went back to the builder with pytest's own words, a green one went to the
reviewer, and the reviewer's `good` ended the run — every decision the flow makes, checked in a
tenth of a second.

## What to change

**Swap `pytest` for what your project uses.** `suite()` is one `exec`. Point it at `npm test`,
`cargo test`, `go test ./...`, or a script that runs all three — as a string, with
`BashEnvMixin` on the workspace in place of `ShellEnvMixin`.

**Gate on more than tests.** Add a linter to `suite()` and hand the agent both outputs. Holding
an agent to a command is stronger than asking it in a prompt.

**Give the flow params of its own.** A `FlowParams` subclass turns into `-p` on the command
line and a form at the prompt — a `rounds: int = 12` is a round limit in two lines. See
[Params of its own](/weaver/flow-settings).

**Make it one you can pick up.** `resumable=True`, and the review the builder is owed kept in
`ctx.state`, is a loop a stopped machine does not throw away. See [Picking a run
up](/user/resuming).

## Next

The flow drives two agents one turn at a time. [Many turns at once](/weaver/async-flows) has
several going together, and [A flow that calls a flow](/weaver/calling-flows) builds this one
into something larger.
