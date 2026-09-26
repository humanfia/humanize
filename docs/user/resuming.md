# Picking a run up

A flow that can be picked up carries on from where its last run stopped: after
<kbd>ctrl+c</kbd>, a spent budget, or a machine that went down. Most of the official loops can,
`ralph_loop` and `rlar` among them, and each flow's page says whether it can.

## Try it

::: code-group

```text [At the prompt]
/resume
```

```sh [hmz exec]
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b duration=2h \
    --resume "$(cat TASK.md)"
```

:::

At the prompt, `/resume` first says which run it carries on:

```console
carrying on from 20260910T021407.882Z-a3f19c: ralph_loop on what that run left behind
```

A Ralph loop picks up its count of rounds and goes on from the next one.

## At the prompt: `/resume`

`/resume` carries on the last run in this directory of a flow that can be picked up. It passes
over runs of flows that cannot, such as a `chat` you had in between. It runs that run's flow
again with that run's agents, environments, params, budget and task, whatever the prompt is set
up with now. It takes nothing after it.

When it cannot carry a run on, it says why:

| It says | Means |
| --- | --- |
| `no flow has been run here` | Nothing has run in this directory. |
| `no run here was of a flow that can be picked up` | Every run here was of a flow that cannot be. |
| `<flow> does not say it can be picked up` | The flow has been changed since that run and no longer can be. |
| `<run> left nothing behind` | The run was killed before it saved anything. Say what to do, and the flow starts from the top. |
| `<run> cannot be read back` | The run's record is damaged. |
| `no picking a run up while a flow is running` | [Stop](/user/stopping) the running flow first. |
| `no picking a run up while the flow is still stopping` | The flow is closing out its turn. Wait for it to finish. |

## An older run: `/epics`

To carry on a run other than the last, type `/epics`. Runs you can pick up are marked **can be
picked up**:

![The /epics list: two runs, newest first, the newer marked "can be picked
up"](/demo/epics.png)

Press <kbd>enter</kbd> on one and choose **resume this run**:

![Inside one run from /epics: when it ran and which flow, where it is kept, how it ended, and
two rows, resume this run and export it](/demo/epic-does.png)

The row is there only when the flow, as it is today, can be picked up. The same reasons as
above are given when it cannot.

## From a script: `--resume`

`--resume` carries on the newest run of that flow in this directory that can be picked up. The
line still says what to run it on, with its own `-a`, `-e`, `-p` and a fresh `-b`. Without
`--resume`, every run starts from the top.

When there is nothing to carry on, the line is refused with exit status 2:

```console
$ hmz exec -f goal … --resume "…"
hmz exec: error: goal does not say it can be picked up, so there is no run of it to resume
$ hmz exec -f ralph_loop … --resume "…"
hmz exec: error: ralph_loop has no run here to pick up: none got as far as writing anything down
```

## What carries over

| | Picked up? |
| --- | --- |
| What the flow kept, such as the round it had reached | Yes. The flow saves as it goes, so a run that was killed keeps it too. |
| Flows it called | Where they are called again the same way: the same flow, task, agents, environments and params. From the first call that differs, flows start afresh. |
| Temporary copies and scratch directories | Yes, where they were. |
| What the budget had spent | No. `--resume` runs under the new line's `-b`. `/resume` runs under the old run's budget, counted from zero. |

The flow at the top always picks up, so changing `-a` or `-p` on a `--resume` line does not
start it over. Leaving `--resume` off does.

Carrying on is a new run: [`/epics`](/user/tracing#what-a-run-writes-down) lists it separately,
with its own sessions and its own trace. A week of stops and starts reads as a run per stretch.

## Make a flow resumable

A flow can be picked up when its weaver says so with `resumable=True`. It then gets a
**state**, a mapping it keeps what the loop knows in, saved as each key is set:

```python{1,7}
@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def nightly(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
):
    fixer, state = agents["fixer"], ctx.state
    while True:
        state["round"] = (state["round"] if "round" in state else 0) + 1
        session = await fixer.spawn(env=envs["workspace"])
        await fixer.run(f"{task}\n\nRound {state['round']}.", session=session)
```

- Store only what JSON can hold. Anything else raises `StateNotSerializable` where it is set.
- Changing a value inside the state, such as appending to a list, is not saved. Set the key
  again: `state["seen"] = [*state["seen"], path]`.
- `ctx.resumed` says whether this call picked up an earlier one.

See [Loops](/weaver/loops) and the [flow API reference](/reference/flows).

## See also

- [Stopping](/user/stopping): what makes a run worth picking up
- [Tracing a run](/user/tracing): the runs `/epics` lists, and what each one did
- [Run it unattended](/user/unattended)
