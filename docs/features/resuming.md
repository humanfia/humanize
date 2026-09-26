---
pageClass: hmz-feature
---

# Picked up where it stopped

A loop meant to run for a week will be stopped: you stop it, the machine restarts, the budget
runs out. A flow that can be picked up carries on from where it stood instead of starting over,
so round 41 follows round 40.

<HmzResume />

<p class="hmz-note">
Run it, pull the plug, then pick it up. The round comes back. The conversation does not.
</p>

## What comes back

| What | After a stop |
| --- | --- |
| **What the flow kept**: which round, which files are done, what it has decided | <Badge type="tip" text="comes back" /> Saved the moment the flow writes it, so a run killed a second later still has it. |
| **Copies and scratch directories the run made** | <Badge type="tip" text="comes back" /> Kept when the run stops, so the next run finds them where they were. |
| **The flow's code** | <Badge type="tip" text="the latest" /> A picked-up run starts the flow from the top with what it kept, so a fix you made in between is the code that runs. |
| **The conversation** | <Badge type="danger" text="gone" /> A picked-up run opens new sessions. The agents remember only what the flow wrote down. |
| **What the run spent** | <Badge type="info" text="starts again" /> A picked-up run is a new run, with a budget of its own. |

A flow keeps little on purpose. The repository is the memory, and the handful of things a loop
tracks is all that has to survive.

## Which flows can be picked up

A flow has to say that it can be picked up. Most of the official loops do, and
[each flow's page](/flows/) says whether it does. A flow that cannot be picked up starts from
the top every time.

## Picking one up

Nothing carries on by itself: running a flow again starts it fresh unless you ask to pick it
up.

| From | Picks up | Runs it on |
| --- | --- | --- |
| **the terminal interface** | the last run here of a flow that can be picked up, or any run you choose from this directory's list | the agents, settings and task that run had |
| **the command line** | the newest run of that flow in this directory | the agents and settings you give it |

Each pickup is a run of its own that says which run it carried on. The stopped run is never
reopened, so a week of stops and starts reads as one run per stretch.

::: details For weavers: flows that a flow calls
When a picked-up flow calls another flow again with the same task, agents, environments and
settings, that call picks up too. A call that differs starts fresh, because what it kept
answered a different question.
:::

## Where the detail is

- [Picking a run up](/user/resuming): doing it, from the prompt or the command line
- [Flows reference › A flow that can be picked
  up](/reference/flows#a-flow-that-can-be-picked-up): making a flow resumable
- [Stopping](/user/stopping): what a stop does to the turn under way
- [The terminal can leave](/features/daemon): closing the terminal without stopping the run
