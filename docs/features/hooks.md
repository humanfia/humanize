---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# The moments of a turn

<p class="hmz-tagline">Hang your own code on each moment of a turn, and change what happens.</p>

<HmzMoments />

<div class="hmz-facts">

- **Six moments everywhere.** Session start and close, prompt, tool, message and turn end reach
  every CLI.
- **Refused up front.** A flow that needs a moment its CLI lacks is refused before the run starts.
- **Part of the turn.** A slow hook makes a slow turn; a hook that fails fails the turn.
- **Your settings untouched.** Hooks belong to the flow, and hang on its agents only while it
  runs.
- **Stopping a tool in time.** Holds from the next turn after hanging, and only while the agent
  works on this machine.

</div>

| Moment | CLIs that reach it |
| --- | --- |
| the CLI asks whether a tool may run | <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="kimi" /> |
| the agent asks its user | <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="kimi" /> <Badge type="tip" text="pi" /> |
| a subagent starts or finishes | <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="cursor-agent" /> <Badge type="tip" text="mcode" /> |
| a tool refused as it is reached for never runs | <Badge type="tip" text="claude" /> <Badge type="tip" text="qwen" /> |

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
