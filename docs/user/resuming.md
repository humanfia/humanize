# Picking a run up

A loop that runs for a week will be stopped and started: a machine goes down, somebody presses
by hand, or a turn takes the process with it. A **flow** is a file on disk, and the weaver who
wrote it may say it can be picked up where its last run left off.

## Try it

Run a resumable flow, stop it, and run it again with `--resume`:

```sh
hmz exec -f nightly -a fixer=claude/claude-opus-5:high -b duration=2h "keep the tests green"
# ctrl+c, a reboot, a spent budget …
hmz exec -f nightly -a fixer=claude/claude-opus-5:high -b duration=2h --resume "keep the tests green"
```

The second run finds what the first kept, and carries on from the round it had reached. Without
`--resume` every run starts afresh, whatever an earlier one left behind. In the interface,
[`/resume`](#picking-one-up-from-the-interface) is that second line typed at the prompt.

## Saying so

**For the weaver.** To make a flow resumable, mark it `resumable=True`. Its context then has a
**state**: a mapping the flow keeps what the loop itself knows in — which round it is on, which
files it has been through, what it has decided so far. It is not a second copy of the
transcript — the backends keep that, and the run's **[epic](/user/tracing#what-a-run-writes-down)**
already says which sessions it opened.

```python
"""A Ralph loop that knows which round it is on."""

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
    fixer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def nightly(task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    fixer, state = agents["fixer"], ctx.state
    assert state is not None  # a resumable flow always has one
    while True:
        state["round"] = (state["round"] if "round" in state else 0) + 1   # saved as it is set
        session = await fixer.spawn(env=envs["workspace"])
        await fixer.run(f"{task}\n\nRound {state['round']}.", session=session)
```

`ctx.state` is `None` for a flow that is not resumable, and `ctx.resumed` says whether this call
picked an earlier one up. A flow that says nothing runs from the top every time. See
[Writing a flow](/weaver/writing-a-flow).

## Where it lives

A resumable run keeps a **journal** beside its epic: one JSON line per thing a run picking it up
needs — each flow call and how it ended, each write to a flow's state, each session opened, each
temporary copy and scratch directory kept. It is appended to as the run goes, so a run that was
killed rather than stopped still says what it got to.

State is kept **per call**, so a flow that calls [another
one](/reference/flows#a-flow-that-calls-another-flow) is two flows, each keeping its own state
and neither writing the other's.

## When it is saved

**As the flow writes it.** Setting a key or deleting one is written down there and then. A run
worth picking up is one that was stopped or killed, and state written only at the end is state
such a run has none of.

Writing *inside* a value the state holds is a change no mapping can see: appending to a list it
holds changes nothing kept. Set the key again — `state["seen"] = [*state["seen"], path]`.

Keep to what JSON holds. A value it cannot hold is refused where it is written, with
`StateNotSerializable`, and what is read back is what JSON gives back — a tuple comes back a
list — so that a fresh run and one picked up read the same.

## What is picked up

The flow at the top **picks up unconditionally**: it is the run you asked for, with the state it
kept. Under it, each flow it calls picks up **only where it is called again the same way** —
the same flow, the same task, the same agents, environments and params. The first such call
picks up the first one of the earlier run, the second the second, and so on; a call that differs
starts afresh from there down. So a loop whose rounds each called a review flow picks up the
reviews of the rounds it had done, and a round with a different task is a new round.

Temporary copies and scratch directories a resumable run made are kept rather than removed as
the flow that made them ends, so the run picking it up finds them where they were.

The budget is not picked up: a run picked up is held to the `-b` of the line that picked it up.

## Running it again

`--resume` carries on **the newest run of that flow in this directory that can be picked up**.
Runs are kept under the workspace they ran in, so another checkout carries on from its own last
run there. The line still says what to run it on — its own `-a`, `-e`, `-p` and `-b`. The flow
at the top picks up whatever the line says, its state and all; it is the flows it calls that
must match — a call whose agents, environments, params or task changed is started afresh. So
changing `-p` on a `--resume` line does not start the run over; leaving `--resume` off does.

## Picking one up from the interface

**`/resume`** picks up the newest run of the flow in force here that can be picked up: that
run's own flow, on its own agents and environments, with its params and what it was asked to do.
Which one that was comes back on the line that starts it —

```
carrying on from 20260910T021407.882Z-a3f19c: nightly on what that run left behind
```

— because the person typing it has usually been away, and which day's work resumed is the thing
they need to know first. Where there is nothing to pick up it says which reason that is:

| | |
| --- | --- |
| `no run of <flow> here can be picked up` | Nothing has run that flow in this directory, or nothing that ran it kept a journal. |
| `<run> cannot be read back` | Its record is not one: a run that died mid-line left a line rather than an epic. |
| `<flow> does not say it can be picked up` | Asked of the flow as it stands today, not of what the run recorded. |
| `no picking a run up while a flow is running` | A run picked up is a flow started, and one is going. [ctrl+c twice or `/stop`](/user/stopping) stops it first. |
| `no picking a run up while the flow is still stopping` | ctrl+c twice was pressed and the flow has not gone yet — it is closing out the turn it was in, and its journal is still being written. |

`/resume` takes nothing after it: a line that names a run is said back rather than dropped.
To carry on a run that is **not** the newest, open the list and go into that run — which is the
next section.

## Carrying an older one on

`/epics` is every run of a flow in this directory, newest first: when it happened, which flow
it was, what it was asked to do, how many sessions it opened, and a mark on the runs whose flow
says it can be picked up. Enter goes **into** the run under the cursor — which says where that
run is written down, and offers what there is to do with it:

![the /epics list with the run that can be picked up marked, and what opens inside one run:
its directory, over resuming it and exporting it](/demo/epics.gif)

| | |
| --- | --- |
| **resume this run** | Pick this run up, from where its journal says it got to |
| **export it** | The whole run as one archive, its [trace](/user/tracing) and its session logs in it — see [Exporting a run](/user/export) |

**It is `/resume` with the run already named.** The reasons a run cannot be picked up are said
here in the same words, so the table above holds inside a run as well as at the prompt.

The mark in the list and that first row are one question, asked of the **flow** rather than of
the run. The weaver may have rewritten it since, so what can happen next is what it says today:

- A flow that has since dropped `resumable=True` has neither the mark nor the row, whatever the
  run wrote down at the time; where the row is gone, the reason stands under the list.
- A flow that will not load at all reads as one that says no — a flow that cannot be read
  cannot be run.

Exporting is offered for every run, whatever its flow says. Carrying one on is refused while a
flow is running, on the sheet rather than on the way out; [stopping](/user/stopping) is what
stops a flow.

## What carrying on runs

The flow, its agents, its environments, its params and what it was asked to do all come off the
run rather than off whatever the interface happens to be set up on — an agent swapped under it
would be a different run wearing its name. The person at the prompt is not an agent anybody
chose, so a flow that talks to one talks to whoever is there now.

## An epic is never reopened

What carries on is written into an epic of its own, and its `began` line says which run it was
`picked_up` from. A week of stops and starts therefore reads as a run per stretch — its own
sessions, its own trace, its own end — rather than one enormous epic claiming to have begun on
Monday.

## See also

- [Tracing](/user/tracing) — what else a run writes down, and reading one back
- [Stopping](/user/stopping) — what makes a run worth picking up
- [Flows › A flow that can be picked up](/reference/flows#a-flow-that-can-be-picked-up)
- [TUI › Commands](/reference/tui#commands)
