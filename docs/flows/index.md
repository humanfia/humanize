---
pageClass: hmz-feature
---

# Flows

A **flow** is a directory of Python that drives one or more coding agents: which agents, what
each is asked, in what order, and when to stop. humanize runs flows and has no opinion about
what a good one is — so a flow is content rather than product, whoever writes one is a
**weaver**, and the list below is something to read, fork, publish and beat.

Fourteen are listed here — sixteen by name, since [`humanize1`](/flows/humanize1) is three
phases. Between them they are most of the loop shapes the field has converged on.

<HmzFlowShape pick="ralph_loop,stateful_ralph,flame_chase,rlar,goal,parallel_flame_chase" />

## Every flow there is

<HmzFlows />

## Picking one

What a flow decides is *what the agent sees at the start of a round*, and there are only a few
honest answers.

| If you want | Reach for |
| --- | --- |
| To talk to an agent, with no loop at all | [`chat`](/flows/chat) |
| A long unattended run that cannot poison itself with its own context | [`ralph_loop`](/flows/ralph-loop) |
| A long run where the agent has to remember what it tried | [`stateful_ralph`](/flows/stateful-ralph), [`continue_loop`](/flows/continue-loop) |
| The model, rather than your loop, to decide a turn is not over | [`goal`](/flows/goal) |
| Two agents to check each other by working on the same tree | [`flame_chase`](/flows/flame-chase) |
| A reviewer that reads the work and writes the next prompt | [`rlar`](/flows/rlar) |
| A plan agreed first, then built under review | [`humanize1`](/flows/humanize1) |
| Three streams of work at once, only one of them touching your tree | [`parallel_flame_chase`](/flows/parallel-flame-chase) |
| Three lanes, each with a clone, merged into `main` only by a measurement | [`parallel_flame_chase_git_pr`](/flows/parallel-flame-chase-git-pr) |
| A long loop whose workspace is distilled every few turns | [`ralph_loop_agent_cleanup`, `flame_chase_agent_cleanup`](/flows/agent-cleanup) |
| A Lean theorem proved by recursive decomposition | [`recursive_lean_prover`](/flows/recursive-lean-prover) |
| A flow written for you from a description | [`aot`](/flows/aot) |

Six name a [FlowBench](https://humanfia.ai/projects/flowbench) loop in their own docstring,
so that comparing one method against another is a flag rather than a reimplementation.

## Running one

`-f` takes the flow, `-a` one agent per role it declares — named, so the order is yours — and
`-b` what the run may spend:

```sh
hmz exec -f rlar \
    -a actor=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high \
    -b duration=6h,cost=60 "$(cat TASK.md)"
```

A role the runtime fills itself is never named: `human`, the person at the prompt, and
`workspace`, the directory the run was started in. A flow that takes params takes them as `-p`:

```sh
hmz exec -f humanize1:rlcr -a builder=claude/claude-opus-5:max \
    -a reviewer=codex/gpt-5.6-sol:max -b duration=2d -p max=20,base_branch=main "build it"
```

Without `-f` the terminal interface opens on [`chat`](/flows/chat), and `/flow` changes it —
asking for each role by name, then the params, then the budget. Every flag is in the
[CLI reference](/reference/cli).

## What ends a loop

A loop with nothing to stop it runs until somebody stops it, which is a bill nobody agreed to
and a week of rounds nobody read. So every run is held to a **[budget](/features/allowances)** —
a duration, a cost, a count of output tokens — and whichever it reaches first is the one that
stops it. `hmz exec` refuses to start a run without one:

```sh
-b duration=6h,cost=50,output_tokens=10m
```

The budget is humanize's rather than any flow's, and no flow declares a default. It is
held to at every turn of every session of every agent, whatever backend, so a loop needs no
stopping condition of its own and none of them can opt out of one somebody set. It is also
**per run**: a run picked up with `--resume` gets the budget its own command line gives it, which
is what makes a run stopped by its budget a run to pick up rather than one that is over.

Some reach an end of their own first: [`chat`](/flows/chat) when you stop typing — the one flow
that runs without a `-b` — [`rlar`](/flows/rlar) when its reviewer agrees the work is done,
[`goal`](/flows/goal) when the model says the objective is met, and
[`humanize1`](/flows/humanize1)'s loop when its reviewer says the plan is complete, or on its
`max` rounds. The loops of one agent stop after three rounds in a row that came to nothing, and
several end with the error after three failed turns in a row. For the two
[lane flows](/flows/parallel-flame-chase) the budget is the only end there is: their lanes are
scheduled again for as long as they run, so give them a duration.

A run its budget stopped ends with `BudgetExceeded` — `hmz exec` says which limit and exits 0 —
and one that can be picked up carries on from there with `--resume` and a fresh `-b`.

## Where they come from

| | |
| --- | --- |
| `official` | humanize's own, which is [`chat`](/flows/chat) in the package and [humanfia/flowverse](https://github.com/humanfia/flowverse) for everything else, fetched as `/flow` first opens or with `r` at `/flowverses` — until then `hmz exec` naming one of its flows says so |
| `local` · `user` | `.humanize/flows/` here, and `~/.humanize/flows/` everywhere |

Which of humanize's two places a flow is kept in is humanize's business, so all of them are
said the same way: a bare name. `chat` and `rlar` are both just that, `official/rlar` is the
spelling that pins one to the place it came from, and a flow that moves from the package into
the flowverse goes on answering to the name it always had. Only the flows of your own and of
anybody else's flowverse carry a prefix: `local/scheduler`, `theirs/rlar`.

Any git repository with a `flows/` directory in it is a **flowverse**, and adding one offers
its flows by name on every machine you add it to. To put one of your own on that list:
[Writing a flow](/weaver/writing-a-flow) is the first flow a weaver writes, and
[Flowverses](/weaver/flowverses) is how it gets published.

::: danger Adding a flowverse is trusting that repository with this machine
A flow is Python, and reading one means **running** it: listing what a flowverse holds imports
every file in its `flows/`. Add the ones you would clone and run. Every flow here also runs its
agents at whatever rung it declares, up to the one where nothing is asked at all — read
[Security](/user/security) first.
:::
