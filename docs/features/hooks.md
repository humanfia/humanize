---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# The moments of a turn

A flow can hang its own code on the moments of an agent's turn: as a prompt goes out, as a
tool is about to run, as the turn is about to end. A **hook** there can change what happens.
It can add a line to the prompt, refuse a tool, answer the agent's question, or send the agent
back to work. Hooks are part of the flow and are hung on its agents while it runs, so your own
agent settings are never touched.

<HmzMoments />

Every moment is on the track above, top to bottom in the order a turn meets them, with what a
hook there can do. A hook that only watches changes nothing. A hook is also part of the turn it
runs in: a slow hook makes a slow turn, and a hook that fails fails the turn.

## Refusing a tool

When the CLI asks whether a tool may run, a refusal always holds. A CLI asks before the tools
it counts as changing something, though, not before every read.

Refusing a tool as the agent reaches for it stops the tool only on Claude Code and Qwen Code,
from the first turn that starts after the hook is hung, and only while the agent works on this
machine. Everywhere else the hook hears about the tool as it starts, so it can watch it but not
stop it.

## What this is enough to build

- a permission rule of your own, on top of the [permission](/user/permissions) the agent was
  given
- a house rule added to every prompt, without touching anybody's settings file
- a [goal written by hand](/features/goals): the end of the turn refused until a check passes
- a question answered by the flow, by another agent, or by a flow it calls
- a record of every tool the agent reached for, alongside the [trace](/features/tracing)

## Which CLIs reach which moments

Every CLI reaches six of the moments: a session starting and closing, a prompt going, a tool
reached for, a message to the user, and the turn ending. The rest only some CLIs reach. A flow
that needs one says so when it declares the agent, and humanize will not pair that agent with a
CLI that cannot serve it. A mismatch is refused before the run starts, not hours in.

| Moment | CLIs that reach it |
| --- | --- |
| the CLI asks whether a tool may run | <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="kimi" /> <Badge type="tip" text="zcode" /> |
| the agent stops to ask its user | <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="kimi" /> <Badge type="tip" text="pi" /> <Badge type="tip" text="zcode" /> |
| a subagent starts or finishes | <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="cursor-agent" /> |
| a tool refused as it is reached for does not run | <Badge type="tip" text="claude" /> <Badge type="tip" text="qwen" /> |

## Go further

<div class="hmz-paths by-three">
  <a :href="withBase('/weaver/hooks')">
    <strong>Hang one</strong>
    <span>Writing a hook in a flow, and what each moment tells it.</span>
  </a>
  <a :href="withBase('/features/goals')">
    <strong>Goals</strong>
    <span>The model deciding when it is done, beside a hook deciding it.</span>
  </a>
  <a :href="withBase('/reference/flows')">
    <strong>Flows reference</strong>
    <span>Every moment's fields and answers, and the declarations a flow makes.</span>
  </a>
</div>
