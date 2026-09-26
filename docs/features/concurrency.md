---
pageClass: hmz-feature
---

# Many turns at once

Turns wait for each other only inside one conversation. Give an agent more conversations and it
works on all of them at once: two hundred files, two hundred conversations, one agent.

<HmzTurns />

<p class="hmz-note">
Drag the slider to spread twelve prompts over more conversations, then put them all on one
session.
</p>

## One conversation, one turn at a time

Turns in one conversation run one after another. Asking a conversation for a second turn while
its first is still going is an error, not a queue. For two turns at once, open two sessions.

Sessions are cheap to hold. Opening one starts nothing until its first turn, so ten thousand
opened up front are a list, not a bill.

## Where each one works

A session works in one directory for its whole life. So one agent working in several places at
once holds a session per place:

| Aim the fan-out at | Each session works in |
| --- | --- |
| **this directory** | the directory the run started in |
| **a worktree each** | a git worktree of its own: one agent, several checkouts |
| **a copy each** | a throwaway copy of the directory, removed when the flow that made it ends, unless the run can be [picked up](/features/resuming) |
| **another machine** | a directory on an ssh host. The agent stays here and its commands land there. See [the anchor](/features/anchor). |

## Whole flows at once

A flow can run whole flows side by side, the same way it runs turns side by side. Each one:

- opens its own sessions, which its siblings never see;
- has its own budget, inside what its caller has left, and what it spends counts against every
  flow above it;
- stops when a limit above it is reached.

## How wide you can go

humanize puts no cap on a fan-out. What limits it is the coding agent CLI underneath and the
machine it runs on, because every turn is real work: files changed, commands run. How many
conversations keep their pace depends on the backend, so widen a fan-out while its turns stay
quick.

::: details opencode keeps one database for every project
When several opencode turns write at the same moment, one of them can find that database busy.
humanize waits a moment and tries that turn again.
:::

## Reading many conversations

In the terminal interface, one agent is one screen, however many conversations it holds, and
each turn says which conversation it is in. A [trace](/features/tracing) lays every one of them
out on one timeline.

## Where the detail is

- [Many turns at once](/weaver/async-flows): writing the fan-out
- [Worktrees, copies and scratch](/weaver/worktrees) · [Remote
  execution](/user/remote-execution)
- [Many conversations at once](/user/conversations): reading them at the prompt
