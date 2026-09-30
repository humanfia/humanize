---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Many turns at once

<p class="hmz-tagline">Turns wait for each other only inside one session. Open more, and one agent works on all of them.</p>

<HmzTurns />

<div class="hmz-facts">

- **Sessions are cheap.** Opening one starts nothing until its first turn.
- **A place per session.** This directory, a worktree, a throwaway copy, or
  [another machine](/user/remote-execution).
- **Whole flows too.** Flows run side by side, each with its own sessions and a
  [budget](/features/allowances) inside its caller's.
- **No cap from humanize.** The CLI and the machine set the pace; widen while turns stay quick.
- **Read as one.** One agent is one screen; a [trace](/features/tracing) lays every
  conversation on one timeline.

</div>

<div class="hmz-paths by-three">
  <a :href="withBase('/weaver/async-flows')">
    <strong>Fan out</strong>
    <span>Writing turns and flows that run at once.</span>
  </a>
  <a :href="withBase('/weaver/worktrees')">
    <strong>Give each a place</strong>
    <span>Worktrees, copies and scratch, and where each one lives.</span>
  </a>
  <a :href="withBase('/user/conversations')">
    <strong>Read them</strong>
    <span>Many conversations at once, at the prompt.</span>
  </a>
</div>
