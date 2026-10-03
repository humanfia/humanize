# The agent asking the flow

In this guide you let an agent, mid-turn, **ask the flow** for something, and answer with
the flow's own code. You build `delegating`: a builder that asks for a review whenever it
wants one, answered by a second agent whose turn happens inside the builder's.

A flow usually drives an agent by talking to it. Reach for this page when the traffic should go
the other way: the agent needs something only the flow has, such as another agent, another
flow, or a decision that is yours, and only the agent knows when it needs it.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- What a hook is: [Hooks](/weaver/hooks).
- A CLI that asks its user questions: Claude Code, Codex, Kimi Code or pi. See [Which CLIs
  ask](#which-clis-ask).
:::

## How it works

Most coding agent CLIs can stop in the middle of a turn and ask their user a question, and wait
for the answer. In a flow, that user is your flow:

1. The role declares **`AskUserHookAgentMixin`**, so only a CLI that asks can fill it.
2. The flow hangs an **`on_ask_user`** hook on the agent: an async function called with the
   question.
3. The hook answers with an **`AskUserHookResult`**. Its `answer` is what the agent is told, and
   the turn carries on from there.

The hook is the flow's own code, so it can take a turn of another agent, read the workspace, or
call a whole flow before it answers. The agent's turn is paused meanwhile. `hmz.flows` has no
other way to hand an agent a tool: the question is the tool.

The agent only knows when to ask, and how to phrase it, from its prompt, so the flow says both.
A fixed first word, like `review ` below, is the simplest way for the hook to tell one kind of
request from another.

## Example: a builder that asks for reviews

```python
# .humanize/flows/delegating/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    AskUserHookAgentMixin,
    AskUserHookParams,
    AskUserHookResult,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)

ASKING = (
    "When you want a file reviewed, ask your user `review <path>` and wait "
    "for the answer: it is the review. Ask for one before you say you are done."
)


class Builder(Agent, AskUserHookAgentMixin):  # ①
    """An agent that may stop mid-turn and ask."""


class Agents(AgentCollection):
    builder: Builder
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def delegating(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """Build, and let the builder ask for a review whenever it wants one."""
    builder, reviewer = agents["builder"], agents["reviewer"]
    workspace = envs["workspace"]

    async def asked(params: AskUserHookParams) -> AskUserHookResult:  # ②
        print(f"  asked: {params.question}")
        if not params.question.startswith("review "):  # ③
            return AskUserHookResult()
        reading = await reviewer.spawn(env=workspace)  # ④
        said = await reviewer.run(
            f"Review {params.question.removeprefix('review ')}. Be brief.",
            session=reading,
        )
        return AskUserHookResult(answer=said)  # ⑤

    builder.on_ask_user(asked)  # ⑥
    session = await builder.spawn(env=workspace)
    return await builder.run(f"{task}\n\n{ASKING}", session=session)  # ⑦
```

### What each part does

1. **`class Builder(Agent, AskUserHookAgentMixin)`** is a role type that asks for a CLI that
   asks its user. A CLI that cannot is refused before the first turn, and without the mixin
   `on_ask_user` cannot be hung at all.
2. **`asked`** is the hook. It is defined inside the flow so it can reach `reviewer` and
   `workspace`. It is called with an `AskUserHookParams` each time the builder asks, and
   answers with an `AskUserHookResult`.
3. **`params.question`** is what the agent asked, in its own words. A question that is not a
   review request gets an empty result: no answer, and the agent carries on without one.
4. **A fresh reviewer session per question.** The reviewer takes a whole turn of its own while
   the builder's turn waits.
5. **`AskUserHookResult(answer=said)`** hands the review back. The builder reads it as its
   user's answer and goes on with the same turn.
6. **`on_ask_user`** hangs the hook on every session of `builder`. Hang it before the turn it
   should cover: on Codex and Kimi Code, one hung mid-turn takes hold from the next turn.
7. **`ASKING` in the prompt** tells the builder when to ask and how to phrase it. The flow
   returns the builder's last answer.

### Run it

```sh
hmz exec -f delegating -a builder=claude/claude-sonnet-5-5:high \
    -a reviewer=claude/claude-sonnet-5-5:low -b cost=1 \
    "add a subtract function to calc.py"
```

A real run:

```text
● builder is working
● Read(/home/you/calc/calc.py)
● Edit(/home/you/calc/calc.py)
● Now I'll ask for a review before finishing.
● AskUserQuestion()
● review /home/you/calc/calc.py
● reviewer is working
● Read(/home/you/calc/calc.py)
● Bash(cd /home/you/calc && git diff calc.py)
● `calc.py` looks correct. The uncommitted change adds `subtract(a, b)`, which returns `a - b`.
  …
✻ input 4 · output 214 · cache_read 29.2k · cache_write 4.2k · $0.02 · claude-sonnet-5-5 · reviewer
  asked: review /home/you/calc/calc.py
…
✻ Worked for 4s · reviewer
● I added `subtract(a, b)` to `/home/you/calc/calc.py`. It returns `a - b`, in the same style as `add`. …
  The review said the code is correct and named two gaps, neither a bug: there are no docstrings or type hints, and there are no tests for `add` or `subtract`. …
✻ input 8 · output 494 · cache_read 61.3k · cache_write 5.9k · $0.03 · claude-sonnet-5-5 · builder
…
✻ Worked for 11s · builder
```

Read it in order:

- **`● AskUserQuestion()`** and **`● review …`** are the builder asking, with Claude Code's own
  question tool, in the words `ASKING` told it to use.
- **`● reviewer is working`** is the hook's reviewer turn, nested inside the builder's: the
  builder's turn has not ended.
- **`asked: review …`** is the hook's own `print`. It lands among the reviewer's lines, because
  a flow's output is not held back for a turn to finish.
- **The builder's last answer** quotes the review, which came back as its user's answer.

### Check it worked

The flow is tested on fake agents. A reply function reaches the question through the `session`
it is given, which fires the flow's `on_ask_user` hook exactly as a real question would:

```python
# tests/test_delegating.py
import pytest

from hmz.flows import CapabilityMissing
from hmz.sdk import fakes


async def asks_for_a_review(prompt: str, *, session: fakes.FakeSession, **_: object) -> str:
    review = await session.ask("review calc.py")  # ①
    return f"done; the review said: {review}"


async def test_the_reviewer_answers_the_question() -> None:
    builder = fakes.FakeAgentDriver(reply=asks_for_a_review)
    reviewer = fakes.FakeAgentDriver(reply="looks right")  # ②

    said = await fakes.run_fake(
        "delegating", "add subtract", agents={"builder": builder, "reviewer": reviewer}
    )

    assert said == "done; the review said: looks right"  # ③
    assert reviewer.prompts == ["Review calc.py. Be brief."]


async def test_a_question_that_is_not_ours_goes_unanswered() -> None:
    async def asks_something_else(
        prompt: str, *, session: fakes.FakeSession, **_: object
    ) -> str:
        return str(await session.ask("tabs or spaces?", ["tabs", "spaces"]))

    builder = fakes.FakeAgentDriver(reply=asks_something_else)
    reviewer = fakes.FakeAgentDriver()

    said = await fakes.run_fake(
        "delegating", "x", agents={"builder": builder, "reviewer": reviewer}
    )

    assert said == "None"  # ④
    assert reviewer.prompts == []


async def test_a_cli_that_cannot_ask_is_refused() -> None:
    with pytest.raises(CapabilityMissing):  # ⑤
        await fakes.run_fake(
            "delegating", "x", agents={"builder": fakes.FakeAgentDriver("opencode")}
        )
```

```text
...                                                                      [100%]
3 passed in 0.10s
```

1. **`session.ask(question, options)`** is the fake builder asking its user. It returns the
   hook's `answer`, or `None` where there is none.
2. **The reviewer answers from a script**, so the test knows what the review says.
3. **The review reached the builder**, and the flow returned the builder's answer.
4. **A question the hook does not handle** gets no answer, and no reviewer turn is spent on it.
5. **A fake opencode** does not ask its user, so the flow is refused before its first turn, as
   `hmz exec` refuses it.

## What a question carries

| | |
| --- | --- |
| `params.question` | what the agent asked, in its own words |
| `params.options` | the answers it offered, if any. Your answer need not be one of them |
| `params.ctx`, `params.session` | the flow's context, and the session the question arrived in |
| `AskUserHookResult(answer=…)` | what the agent is told |
| `AskUserHookResult()` | no answer: the agent carries on without one |

**A question waits.** Other hooks are answered as if nothing were hung once they keep a CLI
waiting 15 minutes. A question waits as long as its answer takes, whether that is a reviewer's
turn or a whole subflow. Whatever the hook spends counts against the run.

## Which CLIs ask

| CLI (`-a`) | Asks its user |
| --- | :---: |
| `claude`, `codex`, `kimi`, `pi` | <Badge type="tip" text="yes" /> |
| `agy`, `cursor-agent`, `dsh`, `grok`, `mcode`, `mimo`, `opencode`, `qwen`, an ACP CLI | <Badge type="info" text="no" /> |

A CLI that does not ask is refused before the first turn:

```text
hmz exec: error: delegating: 'builder' needs AskUserHookAgentMixin, which mcode does not support
```

See [Hooks › Declaring a mixin](/weaver/hooks#declaring-a-mixin).

## Variations

**An agent that starts a flow.** The hook can call another flow and wait for it. Here the agent
decides, mid-turn, that a piece of work needs a loop of its own, and gets
[`flame_chase`](/flows/flame-chase) under five dollars of the run's budget:

```python
from hmz.flows import Budget, BudgetExceeded, load

chase = load("flame_chase")


async def asked(params: AskUserHookParams) -> AskUserHookResult:
    if not params.question.startswith("chase "):
        return AskUserHookResult()
    try:
        await chase(
            params.question.removeprefix("chase "),
            agents={"first_chaser": reviewer, "second_chaser": reviewer},
            envs={},  # its workspace is the run's own
            params=chase.expected_params(),
            budget=Budget(cost=5.0),  # it never ends on its own
        )
    except BudgetExceeded:
        pass
    return AskUserHookResult(answer="done: read the working tree")
```

`flame_chase` loops until its budget is spent, so the `budget=` is what ends it, and the
`except` turns that into an answer. See [A flow that calls a flow](/weaver/calling-flows).

**The other ways in.** A question is the one moment that carries a request to the flow and
waits for what comes back. Other hooks reach the flow too, each for its own purpose:

| Hook | What the flow can do from it |
| --- | --- |
| `on_pre_tool_use` | see every tool the agent reaches for, and stop it on a CLI that waits |
| `on_permission_request` | decide whether a tool may run, on a CLI that asks |
| `on_stop` | refuse to let the turn end, and hand the agent its next prompt |
| `on_notification` | hear what the agent stopped to tell its user |

## Pitfalls

- **Whether to ask is the agent's decision.** The prompt can ask it to, and a model may still
  answer in prose instead of calling its question tool. In our runs Codex sometimes wrote
  `review calc.py` as its final answer rather than asking it. Where the review must happen,
  check for it in an [`on_stop` hook](/weaver/goals#when-your-code-should-decide-instead) and
  keep the turn going until it has.
- **A hook that raises fails the turn.** The builder's `run` raises what the hook raised, as if
  the flow's own code had raised it. Catch inside the hook whatever it should survive.
- **A nested flow needs a bound.** A loop called from a hook runs under the whole run's budget
  unless you give it a `budget=` of its own.

## Next steps

- [Hooks](/weaver/hooks): every moment a flow can hang one on
- [A flow that calls a flow](/weaver/calling-flows)
- [The person as an agent](/weaver/human-agent): questions the flow puts to a person
- [Questions](/user/questions): an agent's question, as whoever is at the prompt sees it
- [Reference › Hooks](/reference/flows#hooks-in-a-flow)
