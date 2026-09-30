---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# A flow is Python

<p class="hmz-tagline">An async function that drives coding agents. Between two turns, any code at all.</p>

<HmzLoops />

<div class="hmz-facts">

- **Whoever writes one is a weaver.** Every loop above is a flow you can run today.
- **Declared up front.** A role left empty, or a CLI short of a [capability](/features/capabilities)
  it needs, stops the run before its first turn.
- **Where agents work is yours.** Here or on [another machine](/features/anchor), chosen at run time.
- **Calls nest.** A called flow's budget fits inside what its caller has left, and runs
  [side by side](/features/concurrency).
- **Skills travel with it.** Copy a flow and its skills come along; fork one to make it yours.

</div>

::: warning A flow is code
Running a flow runs its Python, with its agents' approvals bypassed. Add a flowverse only if you
would install its code. See [Security](/user/security).
:::

<div class="hmz-paths by-three">
  <a :href="withBase('/weaver/writing-a-flow')">
    <strong>Write one</strong>
    <span>A flow from nothing: its roles, its loop, and testing it.</span>
  </a>
  <a :href="withBase('/weaver/calling-flows')">
    <strong>Call one</strong>
    <span>A flow that calls a flow, and what it hands down.</span>
  </a>
  <a :href="withBase('/reference/flows')">
    <strong>Flows reference</strong>
    <span>The contract, in full.</span>
  </a>
</div>
