---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Picked up where it stopped

<p class="hmz-tagline">Stop a week-long loop, pick it up, and round 41 follows round 40.</p>

<HmzResume />

<div class="hmz-facts">

- **Nothing carries on by itself.** Running a flow again starts it fresh unless you ask to pick
  it up.
- **The flow has to say so.** [Each flow's page](https://humanfia.ai/flows/) says whether it can be picked up.
- **Never reopened.** Each pickup is a run of its own, so a week of stops reads as one run per
  stretch.
- **From the terminal or the command line.** Pick any run from this directory's list, or the
  newest.
- **Called flows pick up too,** when called again with the same task, agents, environments and
  settings.

</div>

<div class="hmz-paths by-three">
  <a :href="withBase('/user/resuming')">
    <strong>Pick a run up</strong>
    <span>Doing it, from the prompt or the command line.</span>
  </a>
  <a :href="withBase('/reference/flows#a-flow-that-can-be-picked-up')">
    <strong>Make a flow resumable</strong>
    <span>What a flow keeps, and how it says it can be picked up.</span>
  </a>
  <a :href="withBase('/user/stopping')">
    <strong>Stop one</strong>
    <span>What a stop does to the turn under way.</span>
  </a>
</div>
