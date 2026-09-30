---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
import TurnBudget from '../.vitepress/theme/components/features-agents/TurnBudget.vue'
</script>

# A turn can be cut off

<p class="hmz-tagline">Give one turn its own time, cost or token limit, and stop it mid-answer.</p>

<TurnBudget />

<div class="hmz-facts">

- **Every turn starts fresh.** The tenth round of a loop gets the same room as the first.
- **Cut off, not killed.** Its edits stay on disk and the next turn carries on the same session.
- **The tighter one wins.** A turn is held to its own budget or the
  [run's](/features/allowances), whichever is tighter.
- **Unpriced is free.** A model with no listed price costs $0, so its cost limit never bites.
- **Nothing outlasts it.** A [goal](/features/goals) is held to it, and it beats a
  [hook](/features/hooks) that would send the agent on.

</div>

Tokens and cost counted only at the turn's end: <Badge type="warning" text="agy" /> <Badge type="warning" text="cursor-agent" /> <Badge type="warning" text="grok" /> <Badge type="warning" text="qwen" />

A CLI you add yourself never reports them. Give those turns a time limit too.

<div class="hmz-paths by-three">
  <a :href="withBase('/reference/flows')">
    <strong>Give one</strong>
    <span>A turn's budget in a flow, and what a cut-off raises.</span>
  </a>
  <a :href="withBase('/user/tally')">
    <strong>Read the spend</strong>
    <span>What the readings of time, tokens and cost are made of.</span>
  </a>
  <a :href="withBase('/user/stopping')">
    <strong>Stop by hand</strong>
    <span>Ending a turn or a run yourself, from the keyboard.</span>
  </a>
</div>
