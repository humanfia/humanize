---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# One timeline

<p class="hmz-tagline">Every agent and tool call of a run, on one clock, whichever CLIs did the work.</p>

<HmzTimeline />

<div class="hmz-facts">

- **Only that run.** A directory run in fifty times holds fifty runs; no trace holds another's
  work.
- **As much as the CLI wrote.** A slice carries the prompt, the reasoning, the tool's input and
  output.
- **Profiling watches from the side.** It never gets between an agent and its programs, and
  cannot stop a run.
- **Nothing is uploaded.** Perfetto reads the file in your browser.
  [Reporting](/user/reporting) is separate, and off until you say yes.

</div>

The trace is drawn by **Exomyth**, humanize's visualizer: it reads each CLI's own session logs,
and the profile of the programs a run started, into one Chrome JSON trace
(`hmz.runtime.tracing`), so a tool call and the programs it started sit on one timeline.

Read back from: <Badge type="tip" text="agy" /> <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="dsh" /> <Badge type="tip" text="grok" /> <Badge type="tip" text="kimi" /> <Badge type="tip" text="mcode" /> <Badge type="tip" text="mimo" /> <Badge type="tip" text="opencode" /> <Badge type="tip" text="pi" /> <Badge type="tip" text="qwen" /> <Badge type="warning" text="cursor-agent: nothing to read" /> <Badge type="warning" text="an ACP CLI you add: nothing to read" />

<div class="hmz-paths by-three">
  <a :href="withBase('/user/tracing')">
    <strong>Make one</strong>
    <span>Tracing a run, and what to look for in your first.</span>
  </a>
  <a :href="withBase('/user/export')">
    <strong>Send one</strong>
    <span>The run as one archive, with its trace in it.</span>
  </a>
  <a :href="withBase('/reference/tracing')">
    <strong>Every field</strong>
    <span>What a run writes down, and every field of a slice.</span>
  </a>
</div>
