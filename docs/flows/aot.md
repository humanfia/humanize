---
pageClass: hmz-feature
---

# aot

The flow that writes a flow: a description in, and out a flow that has been loaded through
humanize's own engine, run on fakes, and read by a critic. It lands in `.humanize/flows/`
under its name, ready for `hmz exec -f`.

```sh
hmz exec -f aot -a writer=claude/claude-opus-5:high -a critic=codex/gpt-5.6-sol:high \
    -b cost=10 "two agents take turns until a reviewer says it is done"
```

## Three roles

| | |
| --- | --- |
| `writer` | Draws a spec from the description, then drafts the flow in a scratch directory and repairs it |
| `critic` | Reads each draft that passed the gates, in a fresh session; declared `Permission(local=READ)`, so it reads and never writes |
| `human` | You — the [outworlder](/features/human), filled in by the runtime and never by `-a` |

Both agents carry the flow's own [skill](/user/skills), `writing-flows`: the flow API, as a
flow is written against it. Any harness can fill either.

## A draft is run before it lands

The writer draws a spec first: the roles the flow drives, what each must be able to do, its
params and what ends it. A capability nothing here serves is sent back for the writer to
restate, and then put to you to narrow. The name is settled before anything is drafted: one
already taken in the place it lands is put to you, twice at most.

Each draft then goes through two gates, in a process of its own:

1. It is **loaded** through the engine, and what it declares is read back.
2. It is **run on the fake kit** in three worlds — an agent that never says done, one that says
   done at once, one that answers nothing — and must end on its own in every one, within
   `seconds` apiece.

A draft that passes is read by the critic. A refusal from either goes back to the writer word
for word, for up to `repairs` rounds.

## What it takes

| | |
| --- | --- |
| `name` | What to call the flow that lands; `""` takes the name the spec derives from the description |
| `into` | `local`, this project's `.humanize/flows/`, or `user`, the one in your home directory |
| `repairs` | Rounds of repair after the first draft; `3`, from `0` to `6` |
| `strict` | Whether every warning sends a draft back rather than only what blocks; `false` |
| `seconds` | The clock each smoke run is held to; `60` |

## What ends it

The flow that lands, or none. What passes is moved into place whole, and never over a flow that
is already there. Under `hmz exec` nobody is at the prompt, so every question put to you is
answered no, and a draft that runs out of repairs is not landed. It prints the line that runs
what it wrote.

It keeps nothing: a run of it is one description, and running it again writes another flow.

## See also

- [Writing a flow](/weaver/writing-a-flow) — the same thing, by hand
- [Testing a flow](/weaver/testing-flows) — the fake kit the gates run a draft on
