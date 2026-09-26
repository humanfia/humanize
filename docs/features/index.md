---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Features

humanize runs **flows**: loops written in Python that drive the coding agents you already have
(Claude Code, Codex, Kimi and nine more) and keep a record of everything they did. Put a
different agent on every role, leave the run going for days, and read all of it back on one
timeline.

<HmzOrchestra />

<p class="hmz-note">
A simulation, not a recording. Each flow's roles and order of turns are its own; the calls are
invented. Pick a flow to see its shape, and hover a lane or a call.
</p>

## What you get

<HmzFeatures />

## Your agent here, its work there

Point a run at an ssh host or a container. The agent's edits, commands and tests happen there,
while the agent, its login and its link to the model stay on your machine. The agent needs no
plugin and no setting for it.

<HmzAnchor />

<p class="hmz-note">
Pick something the agent does to see where it lands. More in
<a :href="withBase('/features/anchor')">Work on another machine</a>; to set it up,
<a :href="withBase('/user/remote-execution')">Remote execution</a>.
</p>

## The flows you can run

`chat`, one agent talking with you, ships inside humanize. Every other flow comes from the
official **flowverse**, a git repository of flows, which humanize fetches in the background
each time you open it.

| Reach for | When you want |
| --- | --- |
| [`ralph_loop`](/flows/ralph-loop) | One agent on a long task, a fresh session every round |
| [`rlar`](/flows/rlar) | An actor, and a reviewer that reads its work and writes its next prompt |
| [`goal`](/flows/goal) | The model, not your loop, to decide when the work is done |
| [`parallel_flame_chase`](/flows/parallel-flame-chase) | Three streams of work at once |

Every flow, each with its loop played out: [Flows](/flows/).

## Everything, mapped

<HmzMap />

<p class="hmz-note">
Each item with a line on it, and the page that does it:
<a :href="withBase('/features/capabilities')">Everything it does</a>.
</p>

## Every feature page

### Run it your way

| Page | Reach for it when |
| --- | --- |
| [Every coding agent you have](/features/backends) | You want a different CLI, model or effort on each role. |
| [Two accounts of one CLI](/features/accounts) | Two agents of one CLI must run as two accounts at once. |
| [Prompt, script or Python](/features/surfaces) | You want to start the same flow from the prompt, a script or your own program. |

### While it runs

| Page | Reach for it when |
| --- | --- |
| [Talk into a running turn](/features/steering) | An agent is heading the wrong way and you do not want to stop it. |
| [When a flow asks you](/features/human) | A run needs a person's decision, or you are about to walk away. |
| [A budget on every run](/features/allowances) | A run should stop itself on time, money or tokens. |
| [Close the terminal, keep the run](/features/daemon) | A run will outlast the terminal you started it in. |

### Where the work lands

| Page | Reach for it when |
| --- | --- |
| [Work on another machine](/features/anchor) | The code has to build and run somewhere other than where the agent is signed in. |

### After a run

| Page | Reach for it when |
| --- | --- |
| [Every agent on one timeline](/features/tracing) | You want to see what every agent and program did, and when. |
| [Pick up where it stopped](/features/resuming) | A long run was stopped and should carry on rather than start again. |

### Writing a flow

| Page | Reach for it when |
| --- | --- |
| [A loop in plain Python](/features/flows) | The loop you want is not in the flowverse yet. |
| [Many conversations at once](/features/concurrency) | The work splits into pieces that can run side by side. |
| [Answers as typed data](/features/shapes) | Your loop has to read a verdict, not a paragraph. |
| [The agent decides it is done](/features/goals) | Only the model can judge when the work is finished. |
| [React to each moment of a turn](/features/hooks) | Your code has to step in before a tool runs or when a turn stops. |
| [Cap a single turn](/features/budgets) | One turn must not run away with the rest of the budget. |

::: warning Before you point a flow at a repository you care about
Nothing a flow's agents do is put to you for approval: they run with approvals bypassed. A flow
is Python, and loading one runs its code. Read [Security](/user/security).
:::
