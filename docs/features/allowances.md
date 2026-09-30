---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
import Allowances from '../.vitepress/theme/components/features/Allowances.vue'
</script>

# Every run has a budget

<p class="hmz-tagline">Time, money and output tokens. The first limit reached stops the run.</p>

<Allowances />

<div class="hmz-facts">

- **Graceful by default.** The turn under way ends and answers. Not graceful cuts it off where
  it stands.
- **Nested.** Cost and tokens roll up through every flow a run calls. Duration is a deadline,
  not a sum.
- **humanize holds it.** No flow and no hook can talk a spent budget into another turn.
- **One per run.** A [picked-up](/features/resuming) run brings its own. Only
  [`chat`](/flows/chat) runs without one.
- **Unpriced is free.** A model with no listed price costs $0, so pair cost with a time or
  token limit.

</div>

<div class="hmz-paths by-three">
  <a :href="withBase('/user/unattended')">
    <strong>Set one</strong>
    <span>Giving a run its budget, at the prompt or on the command line.</span>
  </a>
  <a :href="withBase('/features/budgets')">
    <strong>Cap one turn</strong>
    <span>A budget of a turn's own, inside the run's.</span>
  </a>
  <a :href="withBase('/user/tally')">
    <strong>Read the spend</strong>
    <span>What the readings of time, tokens and cost are made of.</span>
  </a>
</div>
