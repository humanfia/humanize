---
pageClass: hmz-feature
---

# continue_loop

Sends the task once, then keeps nudging `continue` at the session that heard it. The same one
session as [`stateful_ralph`](/flows/stateful-ralph), told to carry on rather than told what to
do again — which is what a person at a prompt actually types, and is a different prompt from
the task however similar it looks.

```sh
hmz exec -f continue_loop -a agent=kimi/kimi-code/k3:high -b duration=6h "$(cat TASK.md)"
```

<HmzFlowShape flow="continue_loop" />

## Until a turn lands, the task is sent again

`continue` means something only to a session that heard what it is continuing. So the flow
sends the task, and only once a turn has actually landed does the prompt become `continue`:

```python
try:
    answered = await agent.run(prompt, session=session)
except HarnessError:
    failed += 1
    if failed >= 3:
        raise
    answered = ""
else:
    failed = 0
if answered:
    prompt = "continue"
```

A turn that failed or answered nothing — a backend that fell over before it said anything — is
sent again: the task until a turn has answered, `continue` after. Three failed turns in a row
end the run with the last failure.

## What ends it

The run's [budget](/features/allowances) — `-b duration=…,cost=…,output_tokens=…` — held to at
every turn of the session rather than implemented here. The flow itself takes no params and
declares no budget of its own, so `hmz exec` refuses to start it without a `-b`. The turn that
finds it spent raises `BudgetExceeded`, which is how the run ends, and `--resume` carries on
counting rounds under a fresh `-b`. Three failed turns in a row end it sooner, with the last
failure.

## What it keeps

`rounds`. That the task has been sent is **not** kept: a run picked up with `--resume` spawns a
session that has heard nothing, and starts it on the task exactly as the first run did. What the
agent went on to say is the backend's own log to keep, not this flow's.

## See also

- [stateful_ralph](/flows/stateful-ralph) — the same session, re-sent the task rather than nudged
- [goal](/flows/goal) — the backend's own way of not stopping
