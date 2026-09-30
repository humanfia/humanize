---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Answers in a shape

<p class="hmz-tagline">Named, typed fields instead of a paragraph. The flow decides on a field.</p>

<HmzShape />

<div class="hmz-facts">

- **Each kind of field has a job.** Yes or no decides, a few words pick a branch, text carries,
  a number bounds.
- **Two or three fields.** A shape with thirty is a form, and filling in forms is not the work.
- **Never half an answer.** An answer out of shape fails the turn; the usual response is another
  round.
- **Asked is freer to miss.** On a CLI that is only asked, a loop's retry does more of the work.

</div>

| | CLIs |
| --- | --- |
| **Held by the CLI** | <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="agy" /> <Badge type="tip" text="grok" /> <Badge type="tip" text="mcode" /> <Badge type="tip" text="qwen" /> |
| **Asked in the prompt** | <Badge type="info" text="cursor-agent" /> <Badge type="info" text="dsh" /> <Badge type="info" text="kimi" /> <Badge type="info" text="mimo" /> <Badge type="info" text="opencode" /> <Badge type="info" text="pi" />, and any CLI you [add](/user/settings#accounts) |

<div class="hmz-paths by-three">
  <a :href="withBase('/weaver/shapes')">
    <strong>Ask for one</strong>
    <span>Writing the shape in a flow, and the branch for a turn that misses it.</span>
  </a>
  <a :href="withBase('/features/human')">
    <strong>Put it to a person</strong>
    <span>The same shape as a short questionnaire at the prompt.</span>
  </a>
  <a :href="withBase('/reference/flows')">
    <strong>Flows reference</strong>
    <span>Every argument of a turn, and every error it can raise.</span>
  </a>
</div>
