---
pageClass: hmz-feature
---

# chat

One agent, one session, and every line typed between turns is a turn of it — a coding agent
with no loop around it, doing what it is told and then waiting to be told again. It is what the
terminal interface opens on, so that saying something is all it takes to start.

```sh
hmz exec -f chat -a assistant=claude/claude-opus-5:high "what does this repository do?"
```

The one flow `hmz exec` runs without a `-b`: a conversation ends when you stop talking, so it
runs under `Budget(cost=inf)`.

<HmzFlowShape flow="chat" />

## Two agents, and the second is you

`chat` drives an `assistant` and a `human` — the [outworlder](/features/human), whoever is outside
the run, filled in by the runtime and never by `-a`. Saying something to the person is asking
what to say next, and what they answer with is what they typed:

```python
conversation = await assistant.spawn(env=workspace)
person = await human.spawn(env=workspace)
said = task
while said:
    answered = await assistant.run(said, session=conversation)
    said = await human.run(answered, session=person)
```

Which is why the same flow works with nobody at a prompt: an outworlder that is away answers
`""`, the loop ends, and `chat` has done the one thing it was given. `/afk` and a shell script are
the same thing to it, and that is deliberate.

**The first turn is the one that fails out loud.** A conversation that could not be started at
all — an account the backend refused, a model it will not run for that account — ends the run
with what the backend said about it. Every turn after the first is forgiving: a turn that fails
is said to you, and by then there is a conversation to carry on.

## Every capability the harness has

`chat` declares a plain `Agent`, because it talks to whichever harness it is given — and it is
the one flow the runtime hands the harness's **full** view, so everything that harness can do is
there: a `/goal` typed at it on a harness with one, a question the agent stops to ask put to you
on a harness that asks. Every other flow gets exactly what it declared.

A line typed **while a turn is running** goes into that turn rather than becoming another one —
true under any flow, and [Steering](/features/steering) is how.

## What it keeps

Nothing. What was said is the conversation, logged turn by turn by the backend that ran it, and
a session is spawned rather than reopened — so starting this again is another conversation
rather than the last one carried on. To read one back, [export the run](/user/export) from
`/epics` and open the [trace](/user/tracing) inside it.

## See also

- [Many conversations at once](/user/conversations) — the interface holds several of these
- [The person as an agent](/weaver/human-agent) — what the outworlder is, and what it does
  unattended
- [ralph_loop](/flows/ralph-loop) — the same one agent, with a loop around it
