# Picking a run up

Carry a loop on from where its last run stopped, instead of starting it over. Use this after
<kbd>ctrl+c</kbd>, after a budget ran out before the work was done, or after the machine went
down mid-run. By the end of this page you will have stopped a loop, picked it up both at the
prompt and from a script, and checked that it went on counting where it left off.

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

At the prompt, `/resume` first says which run it carries on, then the flow starts again:

```text
resuming 20260930T053826.667Z-55bb87: running ralph_loop from saved state
```

## Before you start

- A flow that can be picked up. Most of the official loops can,
  [`ralph_loop`](/flows/ralph-loop) and [`rlar`](/flows/rlar) among them; each flow's page says
  whether it can. [`chat`](/flows/chat) cannot.
- An earlier run of that flow, **in this directory**, that got far enough to save something.
  Runs are kept per directory, so start `hmz` or `hmz exec` where the first run started.
- Nothing running here now. [Stop](/user/stopping) a running flow first.

## What picking up means

A flow that can be picked up keeps a small record of where its loop has got to, such as the
number of the round it is on, and saves it every time it changes. A run that stops for any
reason — <kbd>ctrl+c</kbd>, a spent budget, a crash, a machine switched off — leaves that
record behind. Picking the run up starts the flow again **with that record**, so the loop
carries on counting instead of starting from nothing.

Three things are worth knowing before you rely on it:

- **It is a new run.** The run that stopped is never reopened. The one that carries it on is a
  run of its own, with its own sessions, its own trace and its own row in
  [`/epics`](/user/tracing#what-a-run-writes-down). A week of stops and starts reads as one run
  per stretch.
- **The agents start fresh conversations.** What carries over is what the flow chose to keep,
  and the files the agents already changed in your project. An agent's conversation is not
  continued.
- **Budgets do not carry over.** What the earlier run spent is not counted against the new one.

There are three ways in:

| Way in | Picks up | Runs it with |
| --- | --- | --- |
| `/resume` at the prompt | the last run here of a flow that can be picked up | that run's own agents, environments, params, budget and task |
| `/epics`, then **resume run** | any run you choose | the same: that run's own setup |
| `hmz exec --resume` | the newest run of the `-f` flow here that saved something | the line's own `-a`, `-e`, `-p` and `-b` |

## Example: stop a Ralph loop on its budget, then carry it on

A tiny project with two failing tests, and a [Ralph loop](/flows/ralph-loop) that tries the
task again in a fresh session every round. The budget is deliberately small so the run stops
by itself.

```sh
hmz exec -f ralph_loop \
    -a agent=claude/claude-haiku-4-5-20251001:low \
    -b output_tokens=1500 \
    "$(cat TASK.md)"
```

The run, as it appeared at the terminal (the agents' thinking trimmed):

```text
round 1                                                                ①
● agent is working
● Read(…/app2/test_slug.py)
● Read(…/app2/slug.py)
● Edit(…/app2/slug.py)
● Bash(cd …/app2 && python -m pytest test_slug.py -v)
● Done! Both tests now pass. …
✻ input 50 · output 1.0k · cache_read 127.5k · cache_write 1.8k · $0.02 · claude-haiku-4-5-20251001 · agent
✻ Worked for 14s · agent
round 2
● agent is working
…
✻ input 26 · output 810 · cache_read 62.8k · cache_write 1.2k · $0.01 · claude-haiku-4-5-20251001 · agent
✻ Worked for 11s · agent
round 3                                                                ②
hmz exec: stopped -- ralph_loop:ralph_loop: its budget's output tokens are spent   ③
```

`echo $?` prints `0`. Now run the same line again with `--resume` and a fresh budget:

```sh
hmz exec -f ralph_loop \
    -a agent=claude/claude-haiku-4-5-20251001:low \
    -b output_tokens=800 \
    --resume "$(cat TASK.md)"                                          # ④
```

```text
round 4                                                                ⑤
● agent is working
● Read(…/app2/test_slug.py)
● Read(…/app2/slug.py)
● Bash(cd …/app2 && python -m pytest test_slug.py -v)
✻ input 34 · output 1.0k · cache_read 84.2k · cache_write 1.5k · $0.02 · claude-haiku-4-5-20251001 · agent
✻ Worked for 13s · agent
round 5
hmz exec: stopped -- ralph_loop:ralph_loop: its budget's output tokens are spent
```

### What each part means

1. **`round 1`** is printed by the flow itself, and the number is what the flow saves. Every
   round opens a fresh session, which is what a Ralph loop is.
2. **`round 3` with no turn after it.** The flow had counted round 3 and saved it when the
   budget stopped the run, before the agent started working. The count is saved the moment it
   is set, so it survives however the run ends.
3. **`hmz exec: stopped -- …`** names the limit that was reached, on stderr. A budget stopping
   a loop is the ordinary way for a loop to end, so the exit status is still `0`.
4. **`--resume`** asks for the newest run of `ralph_loop` in this directory that saved
   something. The rest of the line is read as usual: the `-a` and `-b` here are what the
   carried-on run uses, so this is where you change the model or give it more room.
5. **`round 4`**: the loop carried on from the count it had saved, not from 1. The agent
   found the tests already passing, because the files it fixed in round 1 are still in your
   project.

## Example: pick it up at the prompt

Open `hmz` in the same directory and type `/resume`. The command is offered in the `/` list
only while there is a run here to carry on and nothing is running:

```text
❯ /resume
resuming 20260930T053826.667Z-55bb87: running ralph_loop from saved state      ①
── agent
● agent is working
                                          agent · claude/claude-haiku-4-5-20251001:low · ● 1   ②
```

1. **`resuming <run>: running <flow> from saved state`** names the run being carried on, by
   the name `/epics` lists it under, and the flow it runs.
2. **The agent line** shows the agent **that run** was set up with, here Claude Haiku at `low`,
   even though the prompt itself is set up for another flow. `/resume` runs what ran: the
   flow, its agents, environments, params, budget and task all come from the run. The budget
   is counted from zero again.

To carry on an **older** run than the last, open `/epics`. Runs you can pick up end with
`resumable`:

![The /epics list: two runs, newest first, the newer marked
"resumable"](/demo/epics.png)

Press <kbd>enter</kbd> on one and choose **resume run**:

```text
   2026-09-30 05:38 · ralph_loop
   …/epics/-tmp-hmzdocs-C-app/20260930T053826.667Z-55bb87
   It stopped with 1 agent in 1 session.

   ❯ 1. resume run                resume the flow from this run
     2. export run                the entire run as an archive, with its trace

   enter choose · esc back
```

The **resume run** row is there only when the flow, as it is today, can be picked up. The
same reasons as `/resume` are given when it cannot.

## Check that it worked

- **The count went on.** A Ralph loop's first line after `--resume` or `/resume` is the round
  after the one it had reached, as `round 4` above.
- **A new row in `/epics`.** The carried-on run is listed above the one it came from, with its
  own session count:

  ```text
     ❯ 1. 2026-09-30 05:40 · ralph_loop Make the tests in test_slug.py pass. … · 1 session · stopped ·…
       2. 2026-09-30 05:38 · ralph_loop Make the tests in test_slug.py pass. … · 1 session · stopped ·…
       3. 2026-09-30 05:37 · ralph_loop Make the tests in test_slug.py pass. … · 3 sessions · stopped
  ```

- **The work is where it was.** Your files are as the earlier run left them. Temporary copies
  and scratch directories the flow made are where they were too.

## What carries over

| | Picked up? |
| --- | --- |
| What the flow kept, such as the round it had reached | Yes. The flow saves as it goes, so a run that was killed keeps it too. |
| Flows it called | Where they are called again the same way: the same flow, task, agents, environments and params. From the first call that differs, flows start afresh. |
| Temporary copies and scratch directories | Yes, where they were. |
| The agents' conversations | No. Each carried-on turn opens a fresh session. |
| What the budget had spent | No. `--resume` runs under the new line's `-b`. `/resume` runs under the old run's budget, counted from zero. |

## Variations

- **Change the agents while you carry on.** On a `--resume` line, `-a`, `-e` and `-p` may all
  differ from the first run. The flow at the top always picks up, so changing them does not
  start it over; leaving `--resume` off does.
- **Give a longer leash.** Pick up an overnight loop that ran out of money with
  `-b duration=8h,cost=40 --resume`.
- **Start over on purpose.** Run the line without `--resume`. At the prompt, choose the flow
  and type the task as usual.

## If it goes wrong

At the prompt, `/resume` typed when it cannot carry a run on says why:

| It says | Means | Do |
| --- | --- | --- |
| `no flow has been run here, so there is nothing to resume` | Nothing has run in this directory. | Start `hmz` where the run started. |
| `no run here was of a flow that can be resumed, so there is nothing to resume` | Every run here was of a flow that cannot be. | Start the flow afresh. |
| `<flow> does not support resuming, so <run> cannot be resumed` | The flow has been changed since that run and no longer can be. | Start it afresh. |
| `<run> has no saved state to resume: enter a task to start the flow from the beginning` | The run was killed before it saved anything. | Type the task: the flow starts from the top. |
| `<run> cannot be read, so there is nothing to resume` | The run's record is damaged. | Pick another run from `/epics`. |
| `cannot resume a run while a flow is running: press ctrl+c twice to stop it first` | A flow is running. | [Stop](/user/stopping) it first. |
| `cannot resume a run while the flow is still stopping: it is finishing the turn it was in` | The flow is closing out its turn. | Wait for it to finish. |
| `/resume takes no arguments: it resumes the last run here; use /epics to choose another run` | Something was typed after it. | Use `/epics` to choose a run. |

From a script, `--resume` with nothing to carry on is refused before any agent starts, with
exit status 2:

```console
$ hmz exec -f chat -a assistant=claude/claude-haiku-4-5-20251001:low --resume "hi"
hmz exec: error: chat does not support resuming, so there is no run to resume
$ hmz exec -f ralph_loop -a agent=claude/claude-haiku-4-5-20251001:low -b cost=1 --resume "…"
hmz exec: error: ralph_loop has no run to resume here: none saved any progress
```

The second one also appears in a directory where the flow never ran: check that you are in
the directory the first run started in. On a fresh CI runner there is never anything to pick
up; see [humanize in CI](/user/ci). More in [Troubleshooting](/user/troubleshooting).

## Make a flow resumable

::: details For whoever writes the flow
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
:::

## Next steps

- [Stopping](/user/stopping): the ways a run ends, and what each leaves to pick up
- [Tracing a run](/user/tracing): the runs `/epics` lists, and what each one did
- [Run it unattended](/user/unattended): `--resume` in a scheduled script
- [CLI reference › Picking a run up](/reference/cli#picking-a-run-up): the exact rules
