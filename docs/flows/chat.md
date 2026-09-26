---
pageClass: hmz-feature
---

# chat

Talk to one coding agent, with no loop around it: it answers, and what you type back is its
next turn. It is the one flow that needs no budget, and the one `hmz` opens on in a new
project, so there typing a line is all it takes to start. Once you have run another flow,
`$chat` brings you back.

::: code-group

```text [at the prompt]
❯ $chat what does this repository do?
```

```sh [hmz exec]
hmz exec -f chat -a assistant=claude/claude-opus-5:high "what does this repository do?"
```

:::

<HmzFlowShape flow="chat" />

Under `hmz exec` nobody is at the prompt to answer, so a run is a single turn: one question
answered, or one task done.

## Roles and params

| Role | |
| --- | --- |
| `assistant` | The agent you talk to. It may also search and read the web. |
| `human` | You. humanize fills this role; it takes no `-a`. |

No params.

## While you talk

- **Type while it works.** The line goes to the agent, into the turn under way where its
  backend allows. See [Talking to a running turn](/user/steering).
- **Answer its questions.** When the agent stops to ask you something, the question comes to
  your prompt. This works on `claude`, `codex`, `kimi`, `pi` and `zcode`.
- **Keep several going.** See [Many conversations at once](/user/conversations).

## What ends it

- **Nothing comes back from you.** At the prompt, that is `/stop`, or [`/afk`](/user/afk),
  which answers for you with nothing. Under `hmz exec`, it is the end of the first turn.
- **The first turn fails.** If the conversation cannot start at all, say because the backend
  refused the account or will not run the model, the run ends with what the backend said. After
  the first turn, a failed turn is reported to you and the conversation goes on.

## Picking it up

`chat` keeps nothing for `--resume`: running it again starts a new conversation. To read an old
one, [export the run](/user/export) from `/epics` and open its [trace](/user/tracing).

::: details The whole loop, for the curious
This is the heart of the flow, as humanize ships it:

```python
conversation = await assistant.spawn(env=workspace)
person = await human.spawn(env=workspace)
said = task
while said:
    answered = await assistant.run(said, session=conversation)
    said = await human.run(answered, session=person)
```

[Writing a flow](/weaver/writing-a-flow) starts from a loop like this one.
:::

## See also

- [ralph_loop](/flows/ralph-loop): one agent, with a loop around it
- [goal](/flows/goal): one agent that keeps going until it says it is done
