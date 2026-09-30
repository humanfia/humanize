---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# The anchor

<p class="hmz-tagline">The agent here, its work over there. The account never leaves home.</p>

<HmzSyscalls />

<div class="hmz-facts">

- **Nothing to tell the agent.** No plugin, flag or setting of its own says where its work is.
- **One writer.** Nobody else may edit the target's workspace while an agent works on it.
- **A lost link does not stop it.** Work that needs the target fails; the agent exits with its
  own status.
- **Nothing to install over there.** Any POSIX machine with Python 3.12 or newer, no root. The
  agent side needs Linux.
- **The agent can move too.** Beside its work, or on a third machine, taking its
  [account](/features/accounts) with it.

</div>

::: danger Serving is not a sandbox
Serving a target limits which files a request names, not what its commands do: **a listening
port is as good as a shell on that machine.** Prefer SSH or Docker targets, which open no port.
:::

<div class="hmz-paths by-three">
  <a :href="withBase('/user/remote-execution')">
    <strong>Point an agent elsewhere</strong>
    <span>Picking a target, and running an agent against it.</span>
  </a>
  <a :href="withBase('/user/security')">
    <strong>Read this first</strong>
    <span>What an agent, a target and a listening port can reach.</span>
  </a>
  <a :href="withBase('/reference/remote-execution')">
    <strong>Exactly what holds</strong>
    <span>Files, commands, signals and failures, as you can rely on them.</span>
  </a>
</div>
