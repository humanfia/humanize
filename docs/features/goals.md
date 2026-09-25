---
pageClass: hmz-feature
---

# It decides when it is done

A session can be given a **goal** instead of a prompt. The agent decides for itself whether the
objective has been met, and until it decides that it has, a turn that would have ended starts
another.

This is the backend's own goal feature — the one its own goal command reaches — not a prompt
that asks for one. The extra turns are started by the backend, and humanize follows the goal
across all of them.

<HmzGoal />

## What "until it says so" means

A goal takes as many turns of the model as the objective takes, and what comes back is the last
of them. A session that has gone quiet is not a goal that has stopped: the goal has stopped
only once the goal itself says so. That is why a flow looping over a goal runs the objective
again rather than nudging an agent that stopped early — it is starting a new goal, not
continuing one.

## Asked for before the first turn, not an hour in

A goal is a prompt: `/goal <objective>`, handed to `run` like any other. What makes it a goal is
the role it is sent through, which has to be declared with `GoalCommandAgentMixin`:

```python
class Worker(Agent, GoalCommandAgentMixin): ...

said = await agents["worker"].run(f"/goal {task}", session=session)
```

A role declared that way is filled only by a harness that has a goal feature — Claude Code,
Codex, DeepSeek Harness, Kimi Code, ZCode — and one that has none is refused before anything
runs. A `/goal` prompt through a role that did not declare the mixin raises
`CapabilityNotGranted`, whatever the harness underneath could do: a missing declaration is a flow
to correct, not a turn to retry. Where agents are chosen at the prompt, only the CLIs that have
one are offered for such a role.

`/loop <interval> <task>` is the same bargain with another mixin, `LoopCommandAgentMixin`, and
only Claude Code serves it.

## The same shape, written by hand

A goal written by hand is a blocking `on_stop` [hook](/features/hooks): the turn is not over until
the hook lets it be, and the hook is told how many times it has already sent this turn on
(`again`), so one that keeps blocking can decide to stop.

The difference is who judges, and what it costs:

| | Decides it is done | Costs |
| --- | --- | --- |
| a goal | the **model**, against the objective in its own words | turns you did not ask for, until it says so |
| a blocked stop | **your code**, against whatever it can read | one extra turn per refusal, bounded by the count it is given |

Reach for the goal when the stopping condition is one the model should judge, and the blocked
stop when a Python function can check it — an unticked box in a file, a test that still fails,
a diff that still touches the wrong directory.

## Where the detail is

- [Goals](/weaver/goals) — the prompt, the mixin, and which backends have one
- [The moments of a turn](/features/hooks) — the blocked stop, in full
- [Flows reference](/reference/flows#sessions-and-turns) · [Agents reference](/reference/agents#goals)
