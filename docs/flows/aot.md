---
pageClass: hmz-feature
---

# aot

Describe a flow, and get one you can run. A writer drafts it; humanize loads the draft and runs
it on fake agents; a critic reads it fresh. Only a draft that passes all three lands in this
project's `.humanize/flows/`.

::: code-group

```text [at the prompt]
❯ $aot two agents take turns until a reviewer says it is done
```

```sh [hmz exec]
hmz exec -f aot -a writer=claude/claude-opus-5:high -a critic=codex/gpt-5.6-sol:high \
    -b cost=10 "two agents take turns until a reviewer says it is done"
```

:::

<HmzFlowShape flow="aot" />

When it lands, it prints what the new flow drives, takes and ends on, and the line that runs
it:

```text
compiled: turn_taking_review -- two agents take turns until a reviewer approves
landed:   .humanize/flows/turn_taking_review
drives:   worker -- an agent
drives:   reviewer -- an agent
ends:     by verdict -- reviewer says done, within 6 rounds

hmz exec -f local/turn_taking_review -a worker=CLI/MODEL:EFFORT -a reviewer=CLI/MODEL:EFFORT -b cost=USD "the task"
```

At the prompt, the new flow is `$local/turn_taking_review`.

## How a draft is checked

1. **A spec first.** The writer draws up the roles the flow drives, what each must be able to
   do, its params and what ends it. A capability no backend serves is sent back to be restated,
   then put to you. A name that is already taken is put to you too.
2. **It loads.** humanize loads the draft and reads back what it declares.
3. **It ends on its own.** The draft runs on fake agents in three worlds: an agent that never
   says it is done, one that says so at once, and one that answers nothing. It must end in
   every one within `seconds`.
4. **A critic approves it.** A fresh session that may only read, and never saw it written.

A refusal at any step goes back to the writer word for word, for up to `repairs` rounds.

## Roles and params

| Role | |
| --- | --- |
| `writer` | Draws the spec, then drafts and repairs the flow, in one session. |
| `critic` | Reads each draft that passed the gates, in a fresh session. It may only read. |
| `human` | You, filled in by humanize. Asked about names, capabilities, and a draft whose repairs ran out. |

Both agents carry the flow's own [skill](/user/skills), `writing-flows`: how a flow is written
against humanize. Any backend can fill either role.

| Param | Default | |
| --- | --- | --- |
| `name` | blank | What to call the new flow. Blank takes the name the spec gives it. |
| `into` | `local` | `local` lands it in this project's `.humanize/flows/`; `user` in `~/.humanize/flows/`. |
| `repairs` | `3` | Rounds of repair after the first draft, 0 to 6. |
| `strict` | `false` | Send a draft back for every warning, not only for what blocks it. |
| `seconds` | `60` | How long each run on fakes may take. |

## What ends it

- **The flow lands.** It is moved into place whole, and never over a flow that is already
  there.
- **Nothing lands.** No spec could be drawn, you declined a name or a capability, or the
  repairs ran out and you did not take the draft as it stands. Under `hmz exec` nobody is there
  to say yes, so every such question is a no.
- **The [budget](/features/allowances).**

## Picking it up

`aot` keeps nothing for `--resume`: each run is one description, and running it again writes
another flow.

## See also

- [Writing a flow](/weaver/writing-a-flow): the same thing, by hand
- [Testing a flow](/weaver/testing-flows): the fake agents the draft is run on
