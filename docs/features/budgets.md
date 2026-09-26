---
pageClass: hmz-feature
---

<script setup>
import TurnBudget from '../.vitepress/theme/components/features-agents/TurnBudget.vue'
</script>

# A turn can be cut off

A flow can give one turn a **budget** of its own: how long it may run, how much it may cost,
how many output tokens it may write. When a limit is reached, *this* turn stops, while it is
still running. Without it, an agent six minutes into an answer nobody wants writes it to the
end.

<TurnBudget />

::: tip A turn's budget, or the run's
This page is about one turn. What a whole run may spend is the
[run's budget](/features/allowances), and a turn is held to whichever of the two is tighter.
:::

## Every turn starts fresh

The budget measures the turn now running, not the conversation so far. The tenth round of a loop
gets the same room as the first, rather than being cut off for what the first one wrote.

## When a limit bites

Only a budget that is **not graceful** cuts a turn off. A graceful one, which is the default,
lets the turn run to its end and answer: it never shortens a turn.

When a limit bites depends on the limit:

| Limit | Cut off |
| --- | --- |
| Time | the moment it runs out, on every backend. It is the only limit that catches a turn that has gone quiet. |
| Tokens or cost, on most backends | as the response that crosses the limit lands, since they report what they spend as they go |
| Tokens or cost, on <Badge type="warning" text="Antigravity" /> <Badge type="warning" text="Cursor Agent" /> <Badge type="warning" text="Grok Build" /> <Badge type="warning" text="Qwen Code" /> | only when the turn ends, since that is the first time they say what it spent |
| Tokens or cost, on a CLI of your own | never, since it does not say what it spent |

On a backend that reports late, give the turn a time limit too.

Cost is priced from what each turn's CLI reports. A model nobody lists a price for counts as
free, so a cost limit on it never bites.

## A turn that is cut off did what it did

Its edits are on disk and its conversation stays open. Whatever the CLI was running for that
turn stops with it, such as a test run it had started. The next turn carries on in the same
session rather than starting over. That is the difference between a limit and a kill.

The flow gets an error instead of an answer, and decides what to do next. A flow that cancels a
turn it is waiting on cuts it off the same way.

A [goal](/features/goals) is held to a budget like any other turn. A spent budget also wins over
a [hook](/features/hooks) that would send the agent on for another round.

## Where the detail is

- [Every run has a budget](/features/allowances): the budget of the whole run
- [Flows reference](/reference/flows): giving a turn a budget, and what a cut-off raises
- [Cost and rate](/user/tally): what the readings are made of
- [Stopping](/user/stopping): ending a run by hand
