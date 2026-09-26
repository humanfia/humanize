---
pageClass: hmz-feature
---

# A flow is Python

A flow is an `async` Python function that drives coding agents. Between two turns it runs
ordinary code: a loop, a check on what the last answer said, a test run, a file read. So a flow
can do whatever a function can. Whoever writes one is a **weaver**.

<HmzLoops />

<p class="hmz-note">
Each shape above is a flow you can run today. Pick one and see where each turn goes and what
the next turn starts from.
</p>

## What a flow declares

A flow says up front what it needs. That declaration is what you fill in when you run it.

| It declares | What you get |
| --- | --- |
| **An agent per role**, by name: `actor`, `reviewer` | You pick a CLI, model and effort for each role. A role left empty stops the run before the first turn. |
| **What it asks of each agent**: a goal loop, steering, a hook | A CLI that cannot do it is refused before anything starts. See the [capability map](/features/capabilities). |
| **What each agent may touch**: its working directory, your home, the machine, the network | Every session of that agent runs within it. |
| **Where each agent works**: this directory, or one on another machine | You choose at run time. The flow does not change. See [the anchor](/features/anchor). |
| **Settings of its own** | A form in the terminal interface, or values on the command line or in Python, all checked the same way. See [three ways in](/features/surfaces). |
| **Whether it can be picked up** | A stopped run carries on from where it stood. See [picked up where it stopped](/features/resuming). |

A flow gets exactly what it declared and nothing more. A role that did not ask for a goal loop
cannot start one, and an environment that asked only to run programs cannot run a script. So a
flow's declaration tells you everything it can do.

## A flow can call a flow

A good loop is one another loop can reach for. A flow can call another flow, whether it sits
beside it, elsewhere in the same flowverse, or in someone else's, and pass it agents and
environments it already holds.

- The called flow sees only what *it* declared, however much more the caller had.
- Its budget fits inside what the caller has left, and what it spends counts against both.
- Several calls can run at once. See [many turns at once](/features/concurrency).
- A run of flows calling flows reads back as the tree it ran as.

## A flow brings its own skills

Copy a flow and its skills come with it. A flow keeps the skills its agents work by in its own
directory, or names skills kept in a git repository. Those are fetched when a run needs them,
and the copy already on your machine is used when the network is down. A skill that cannot be
found stops the call before its first turn, not an hour into it.

## Where flows come from

A bare flow name means the nearest flow with that name:

1. **This project's flows.**
2. **Your own flows**, for every project on this machine.
3. **The official flowverse**: `chat`, plus humanize's repository of loops. It is always
   listed, whether or not it has been fetched.
4. **Flowverses you add.** A flowverse is a git repository of flows.

To change a flow, **fork** it. Forking copies the whole flow into this project under the same
name, so from then on that name means your copy. The original is still there under its full
name.

::: warning A flow is code
Running a flow runs its Python, and its agents run with approvals bypassed. Add a flowverse
only if you would install its code. See [Security](/user/security).
:::

## Where the detail is

- [Writing a flow](/weaver/writing-a-flow) · [Loops](/weaver/loops) ·
  [Testing a flow](/weaver/testing-flows)
- [Params of its own](/weaver/flow-settings) · [A flow that calls a
  flow](/weaver/calling-flows) · [Flowverses](/weaver/flowverses)
- [Flows reference](/reference/flows): the contract, in full
