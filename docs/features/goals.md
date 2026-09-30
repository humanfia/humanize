---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# It decides when it is done

<p class="hmz-tagline">Give an agent a goal, and it keeps working until it judges the goal met.</p>

<HmzGoal />

<div class="hmz-facts">

- **The CLI's own feature.** humanize follows the goal across every turn and hands the flow the
  last answer.
- **Refused up front.** A flow that needs a goal will not run on a CLI without one, not even
  its first turn.
- **A fresh goal each round.** A flow that loops over a goal starts a new one, rather than
  nudging an agent that stopped.
- **Or your own check.** A [hook](/features/hooks) on the end of the turn works on every CLI,
  one turn per refusal.
- **Still on a budget.** A goal is held to a [turn's budget](/features/budgets) like any other
  turn.

</div>

Has a goal: <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="dsh" /> <Badge type="tip" text="kimi" />

<div class="hmz-paths by-three">
  <a :href="withBase('/flows/goal')">
    <strong>Run one</strong>
    <span>The goal flow sets your task as the agent's goal, once.</span>
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
