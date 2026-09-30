---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# The terminal can leave

<p class="hmz-tagline">Close the terminal and the run keeps going. Come back, and it is read from the top.</p>

<HmzDaemon />

<div class="hmz-facts">

- **One run per directory.** Another checkout of the same project is another directory, with a
  run of its own.
- **Leaving is not stopping.** Exiting with a flow running asks: leave it going, or stop it for
  everybody.
- **A reboot ends it.** The run lives on its machine. A flow that can be
  [picked up](/features/resuming) carries on from where it stood.
- **Only from a real terminal.** Piped, redirected or [unattended](/user/unattended) runs end with
  their process.

</div>

## Several people on one run

<div class="hmz-facts">

- **Everyone is named.** A frontend is a name and a kind, alice@tui or bob@sdk, and every
  answer, line and stop says who.
- **Claims are about questions.** Anybody may still say anything to any agent.
- **Leaving hands your part back.** A frontend that goes gives its roles back to anybody.
- **Programs too.** A program on the [SDK](/reference/sdk#link) is a frontend like any interface.

</div>

<div class="hmz-paths by-three">
  <a :href="withBase('/user/stopping')">
    <strong>Stop it</strong>
    <span>Stopping a flow, and what it leaves behind.</span>
  </a>
  <a :href="withBase('/user/resuming')">
    <strong>Pick it up</strong>
    <span>Carrying on after the run itself has gone.</span>
  </a>
  <a :href="withBase('/reference/daemon')">
    <strong>How it is held</strong>
    <span>The host, its frontends, claims, and doing it all from Python.</span>
  </a>
</div>
