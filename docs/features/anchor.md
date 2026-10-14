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
- **The agent can move too.** Onto its work's own machine, taking its
  [account](/features/accounts) with it, or onto a third machine: one setting of the runtime,
  its harness, says where.

</div>

::: danger Serving is not a sandbox
Serving a target limits which files a request names, not what its commands do: **a listening
port is as good as a shell on that machine.** Prefer SSH or Docker targets, which open no port.
:::

This is **CogAnchor**, humanize's remote-execution layer (`hmz.coganchor`). It sits between a
coding agent CLI and the machine its work is on: it takes each action the CLI makes, maps it
to the target environment and workspace, and hands the result back to the CLI as if the work
were local. How it is built, from the system calls up, is on
[Deep Tech](https://humanfia.ai/research/deep-tech#coganchor) on humanfia.ai.

The name comes from the **Chronocognitive Anchor** (识刻锚) of *Honkai: Star Rail*. Screwllum
builds it into the Emperor's Scepter that runs Amphoreus. It keeps one person whole inside that
other world and lets them still reach the rest of the cosmos. CogAnchor does the same for an
agent whose work is on another machine: the work happens there, and the agent stays itself,
at home, on its own account.

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
