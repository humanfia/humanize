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

- **One form, every field at once.** Asked for a [shape](/features/shapes), you get one form
  of all of it, at the prompt or in the browser, with what the flow suggests already picked; an
  answer the shape refuses is said beside the field it is about.
- **Any question too.** Asked for text rather than a shape, you type a line and the flow gets
  it.
- **Something to read with it.** A question can carry a diff, a table or a chart, and a flow
  can bring a [page of its own](/weaver/faces) to ask it in, the form always a click away.
- **Away means answered.** Run unattended, or [marked away](/user/afk), a text question gets an
  empty answer.
- **Give defaults to run unattended.** Away, a shape with a default in every field gets those,
  and any other fails the flow.
- **You fill your own role.** You never pick an agent for the person: Humanize puts you there.
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
