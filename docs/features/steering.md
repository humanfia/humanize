---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# A line typed mid-turn

<p class="hmz-tagline">Type while an agent works. It takes your words and carries on, without starting over.</p>

<HmzSteer />

| Your line goes | Backends |
| --- | --- |
| into this turn | <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="kimi" /> <Badge type="tip" text="pi" /> |
| into the next turn | <Badge type="warning" text="every other backend" /> |

<div class="hmz-facts">

- **To the agent on your screen.** Reading every agent at once, it goes to whichever has a turn
  open. See [conversations](/user/conversations).
- **Never dropped.** A line typed between turns waits on the pin for the next turn to start.
- **Shared.** Everybody [reading the run](/features/daemon#several-people-on-one-run) sees each
  line waiting, marked with who said it.
- **From a flow too.** A flow can say something into its own agents' running turns.
- **On another machine too.** An [anchored](/features/anchor) agent takes a line the same way.

</div>

<div class="hmz-paths by-three">
  <a :href="withBase('/user/steering')">
    <strong>Talk to a turn</strong>
    <span>The pin, and what each backend does with your line.</span>
  </a>
  <a :href="withBase('/user/conversations')">
    <strong>Pick who hears it</strong>
    <span>Which agent a line reaches when a flow runs several.</span>
  </a>
  <a :href="withBase('/reference/flows#sessions-and-turns')">
    <strong>Steer from a flow</strong>
    <span>Saying something into a running turn from a flow's own code.</span>
  </a>
</div>
