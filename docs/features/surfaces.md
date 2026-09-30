---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# One system, three ways in

<p class="hmz-tagline">The terminal interface, the command line and Python: one set of flows, accounts and runs.</p>

<HmzSurfaces />

<div class="hmz-facts">

- **Nearest flow first.** A name means this project's flow, then yours, then a flowverse's,
  whichever way you ask.
- **Any run, anywhere.** However it started, it can be exported, traced and
  [picked up](/features/resuming).
- **Walk away.** [The terminal can leave](/features/daemon), and the run keeps going.
- **Settings become a form.** The terminal interface draws one from a flow's
  [settings](/weaver/flow-settings). Its author writes none of it.

</div>

<div class="hmz-paths by-three">
  <a :href="withBase('/user/')">
    <strong>The terminal interface</strong>
    <span>Watch a run, steer it, answer it, from a first run on.</span>
  </a>
  <a :href="withBase('/user/unattended')">
    <strong>The command line</strong>
    <span>A whole run on one line, for scripts, CI and cron.</span>
  </a>
  <a :href="withBase('/reference/sdk')">
    <strong>Python</strong>
    <span>Start runs, read them, and look after the ones left going.</span>
  </a>
</div>
