---
pageClass: hmz-feature
---

# A turn can be cut off

A turn can be given a **budget** of its own — how long it may run for, how much it may cost, how
many output tokens it may write — and when it is spent, the turn stops. Not the next turn: this
one, the one that is running now.

```python
from datetime import timedelta

from hmz.flows import Budget, BudgetExceeded

try:
    said = await agent.run(
        prompt,
        session=session,
        budget=Budget(output_tokens=4_000, duration=timedelta(minutes=5), graceful=False),
    )
except BudgetExceeded:
    said = None  # cut off: what it did is on disk, and the session is still open
```

::: tip One type, two places
This page is the **per-turn** budget. It shortens an answer, it can be reached a thousand times
in an afternoon, and it is given to one `run`.

What a whole **run** may spend — and each flow called inside it — is the
[run's budget](/features/allowances): `-b` on a command line, `budget=` on a flow call. It is the
same `Budget`, and a turn is held to the tighter of the two: a turn's own budget never lets it
spend what the run no longer has.
:::

Without it there is nothing to do about a turn that has gone wrong. Refusing an agent its *next*
turn does nothing for this one: an agent six minutes into an answer nobody wants goes on
writing it for as long as it takes, and the flow finds out when it is over.

## Per turn, not per session

Every turn starts with the whole of it. A cap over the whole conversation would cut a tenth
round off for what the first round wrote, which is a budget nobody can reason about — so what is
measured is what the turn now running spends, and the round after a cut-off round gets the same
room the first one did.

## Read while the turn is still running

This is the whole reason it works. Most backends here say what each request to the model cost
as that request lands, and the driver's meter moves then rather than when the turn ends. So a
turn that has written its four thousand tokens is stopped in the middle of the turn, not
congratulated after it.

The three that state a whole turn's cost only at the end — Antigravity, Grok Build and Qwen
Code — can only be held to a token or cost limit at the end of a turn, which is the same thing
their [rate](/reference/agents#what-it-has-cost-and-how-fast) already reads as.

A cap on the clock has no such gap: it bites whether or not anything is arriving, which is what
makes it the one that catches a turn that has gone quiet, and the one to reach for on a backend
that does not count as it goes.

## Graceful, or not

| `graceful` | What happens when a limit is reached mid-turn |
| --- | --- |
| `True` (the default) | The turn runs to its end and answers with what it said. The *next* turn under that budget is refused. |
| `False` | The turn is cut off where it stands — the CLI stops spending — and `run` raises `DurationExceeded`, `CostExceeded` or `OutputTokensExceeded` instead of answering. |

A graceful per-turn budget is a budget for the run's accounting rather than a way to shorten an
answer, so a turn meant to be cut off says `graceful=False`. Where several budgets are over one
turn — its own, its flow's, the run's — each limit is the least any of them leaves, and it is
hard wherever the budget that sets it is. A hard deadline holds under a sooner graceful one too:
the turn runs on past the graceful deadline, and is cut off at the hard one.

**A turn cut off did what it did.** Its edits are on disk and its conversation is open to the
next turn, so the round after a short round carries the same session on rather than starting
another — which is the whole difference between a cap and a kill.

## Cutting one off by hand

Cancelling the task a turn is awaited in cuts that turn off: `asyncio.timeout`, a `TaskGroup`
whose sibling failed, a gather that was cancelled. The turn stops spending, and the session is
left usable — the next turn is an ordinary turn.

```python
async with asyncio.timeout(300):
    said = await agent.run(prompt, session=session)
```

A [steer](/features/steering) with `queued=False` is the other way: it interrupts the turn and
carries on from the words it put in.

## What is actually ended

Whichever process is holding the turn, and everything it started — a CLI that was in the middle
of a test run does not leave the test run behind. Every session a flow opens is a conversation
of an agent of its own, so cutting one turn off never reaches another flow's.

| How the backend is driven | What a cut-off reaches |
| --- | --- |
| One command per turn — Cursor, Grok Build, opencode, MiMo, and the shaped turns of Antigravity and Qwen Code | The command the turn is running in. Ended, with everything it started. |
| One process held open across its turns — Claude Code, pi, Antigravity, Qwen Code | The process the session is spoken to. Ended; the next turn starts another and resumes the conversation. |
| An app server or daemon — Codex, Kimi Code, ZCode, DeepSeek Harness | The turn is interrupted, and the server the session is held by is put down, which is what ends the turn now rather than at its next answer. The next turn starts it again and resumes the conversation by its id. |

A [goal](/features/goals) is a turn like any other here: `/goal` is taken as one `run`, and its
budget and the run's are held to while the backend keeps going.

## Where the moments of a turn stop being enough

A `STOP` [hook](/features/hooks) fires *between* completed turns of the model and can send the
agent on again. That is the right shape for deciding whether a turn is finished and the wrong
shape for stopping one: it never runs while the model is writing. A spent budget also wins over a
hook that would have sent the agent on — a spent budget is not a question.

See [What it has cost, and how fast](/reference/agents#what-it-has-cost-and-how-fast) for the
readings a budget is held to, [Every run has a budget](/features/allowances) for the budget of the
run rather than the turn, and [Stopping](/user/stopping) for ending a run by hand.
