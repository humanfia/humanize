---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# It decides when it is done

Give an agent a **goal** instead of a prompt, and it keeps working, turn after turn, until it
judges the objective met. This is the coding agent's own goal feature, the one its `/goal`
command reaches. humanize follows the goal across every turn and hands the flow the answer the
last one ended on.

<HmzGoal />

## The model decides, or your code does

A flow can keep an agent going without a goal, too: a [hook](/features/hooks) on the end of
the turn sends the agent back while some check still fails, and is told each time how often it
already has. The difference is who judges that the work is done.

| | A goal | A turn sent back |
| --- | --- | --- |
| **Who decides it is done** | the model, against the objective in its own words | your code, against anything it can read |
| **What it costs** | as many turns as the model takes | one more turn per refusal, and you choose when to give up |
| **Reach for it when "done" is** | a judgement: nothing was stubbed out, the design holds | a fact: the tests pass, no box in `TASK.md` is unticked |

A flow that loops over a goal starts a fresh goal each time round, rather than nudging an agent
that stopped early.

## Only on CLIs that have one

<Badge type="tip" text="claude" /> <Badge type="tip" text="codex" />
<Badge type="tip" text="dsh" /> <Badge type="tip" text="kimi" /> <Badge type="tip" text="zcode" />

A flow built on a goal says so when it declares the agent. At the prompt, only these CLIs are
offered for that agent, and a run started any other way with another CLI is refused before its
first turn rather than an hour into a loop.

Claude Code also has a recurring task, its `/loop` command, which a flow can reach the same
way. No other CLI has one.

## Go further

<div class="hmz-paths by-three">
  <a :href="withBase('/flows/goal')">
    <strong>Run one</strong>
    <span>The <code>goal</code> flow sets your task as the agent's goal, once.</span>
  </a>
  <a :href="withBase('/weaver/goals')">
    <strong>Ask for one</strong>
    <span>Giving an agent a goal from a flow, and declaring that it needs one.</span>
  </a>
  <a :href="withBase('/features/hooks')">
    <strong>Send a turn back</strong>
    <span>The hook on the end of a turn, and every other moment a flow can act at.</span>
  </a>
</div>
