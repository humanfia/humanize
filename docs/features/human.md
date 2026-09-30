---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# You, as one of the agents

<p class="hmz-tagline">A flow can ask you, the way it asks a model, and read your answers as fields.</p>

<HmzPerson />

<div class="hmz-facts">

- **Any question too.** Asked for text rather than a [shape](/features/shapes), you type a line
  and the flow gets it.
- **Away means answered.** Run unattended, or [marked away](/user/afk), a text question gets an
  empty answer.
- **Give defaults to run unattended.** Away, a shape with a default in every field gets those,
  and any other fails the flow.
- **You fill your own role.** You never pick an agent for the person: humanize puts you there.
- **A flow can stand in.** A calling flow can answer a called flow's questions itself.

</div>

<div class="hmz-paths by-three">
  <a :href="withBase('/user/questions')">
    <strong>Answer one</strong>
    <span>What a question looks like at the prompt, and how to answer it.</span>
  </a>
  <a :href="withBase('/weaver/human-agent')">
    <strong>Ask one</strong>
    <span>Driving the person from a flow, and standing in for them.</span>
  </a>
  <a :href="withBase('/user/afk')">
    <strong>Step away</strong>
    <span>What <code>/afk</code> does to questions while a run goes on.</span>
  </a>
</div>
