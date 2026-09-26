<script setup lang="ts">
// The capability matrix at the top of /reference/agents, with a filter over it.
//
// Every cell is read off the code, and has to go on matching it:
// - steers, schema held: `steers` and `shapes` on each session class in
//   src/hmz/coganchor/agents/*.py
// - goal, fast tier, rungs, moments: `pursues`, `service_tiers`, `rungs` and `moments` on each
//   agent class there
// - fork, web-search switch: `forks` and `searches` on each Profile in
//   src/hmz/coganchor/backends.py (an added ACP CLI is `_speaks`)
// - trace reader: `_READERS` in src/hmz/runtime/tracing/collector.py
//
// Nothing here touches `window` or `document`, so it renders the same on the server as in the
// browser: every row is in the HTML, and the filter only hides rows once somebody clicks.
import { computed, ref } from 'vue'

type Tone = 'tip' | 'warning' | 'info'

interface Cell {
  can: boolean
  text: string
  tone: Tone
}

interface Row {
  name: string
  product: string
  steers: Cell
  goal: Cell
  schema: Cell
  fork: Cell
  web: Cell
  rungs: Cell
  moments: string[]
  fast: Cell
  trace: Cell
}

// A cell with no text is a backend that cannot, drawn as a quiet dash so that what a backend
// can do is what the eye lands on.
const yes: Cell = { can: true, text: 'yes', tone: 'tip' }
const no: Cell = { can: false, text: '', tone: 'info' }
const held: Cell = { can: true, text: 'held', tone: 'tip' }
const prompt: Cell = { can: false, text: 'prompt', tone: 'warning' }
const four: Cell = { can: true, text: 'all 4', tone: 'tip' }
const bypass: Cell = { can: false, text: 'bypass', tone: 'warning' }

const PERM = 'Permission'
const SUB = 'Subagent'

const ROWS: Row[] = [
  { name: 'agy', product: 'Antigravity', steers: no, goal: no, schema: held, fork: no, web: no, rungs: four, moments: [], fast: no, trace: yes },
  { name: 'claude', product: 'Claude Code', steers: yes, goal: yes, schema: held, fork: yes, web: yes, rungs: four, moments: [PERM, SUB], fast: yes, trace: yes },
  { name: 'codex', product: 'Codex', steers: yes, goal: yes, schema: held, fork: yes, web: yes, rungs: four, moments: [PERM, SUB], fast: yes, trace: yes },
  { name: 'cursor-agent', product: 'Cursor Agent', steers: no, goal: no, schema: prompt, fork: no, web: no, rungs: four, moments: [SUB], fast: yes, trace: no },
  { name: 'dsh', product: 'DeepSeek Harness', steers: no, goal: yes, schema: prompt, fork: no, web: yes, rungs: bypass, moments: [], fast: no, trace: yes },
  { name: 'grok', product: 'Grok Build', steers: no, goal: no, schema: held, fork: yes, web: yes, rungs: four, moments: [PERM], fast: no, trace: yes },
  { name: 'kimi', product: 'Kimi Code', steers: yes, goal: yes, schema: prompt, fork: yes, web: yes, rungs: four, moments: [PERM], fast: no, trace: yes },
  { name: 'mimo', product: 'MiMo Code', steers: no, goal: no, schema: prompt, fork: yes, web: yes, rungs: four, moments: [], fast: no, trace: yes },
  { name: 'opencode', product: 'opencode', steers: no, goal: no, schema: prompt, fork: yes, web: yes, rungs: four, moments: [], fast: no, trace: yes },
  { name: 'pi', product: 'pi', steers: yes, goal: no, schema: prompt, fork: yes, web: no, rungs: four, moments: [], fast: no, trace: yes },
  { name: 'qwen', product: 'Qwen Code', steers: no, goal: no, schema: held, fork: yes, web: yes, rungs: four, moments: [], fast: no, trace: yes },
  { name: 'zcode', product: 'ZCode', steers: no, goal: yes, schema: prompt, fork: yes, web: yes, rungs: four, moments: [PERM], fast: no, trace: yes },
  {
    name: 'an ACP CLI',
    product: 'added at /providers',
    steers: no,
    goal: no,
    schema: prompt,
    fork: { can: true, text: 'yes', tone: 'warning' },
    web: no,
    rungs: bypass,
    moments: [],
    fast: no,
    trace: no,
  },
]

type Key = 'steers' | 'goal' | 'schema' | 'fork' | 'web' | 'rungs' | 'perm' | 'sub' | 'fast' | 'trace'

interface Filter {
  key: Key
  label: string
  test: (row: Row) => boolean
}

const FILTERS: Filter[] = [
  { key: 'steers', label: 'steer a running turn', test: (r) => r.steers.can },
  { key: 'goal', label: 'pursue a goal', test: (r) => r.goal.can },
  { key: 'schema', label: 'hold a schema', test: (r) => r.schema.can },
  { key: 'fork', label: 'fork', test: (r) => r.fork.can },
  { key: 'web', label: 'switch web search off', test: (r) => r.web.can },
  { key: 'rungs', label: 'take all four rungs', test: (r) => r.rungs.can },
  { key: 'perm', label: 'run PermissionRequest', test: (r) => r.moments.includes(PERM) },
  { key: 'sub', label: 'run Subagent moments', test: (r) => r.moments.includes(SUB) },
  { key: 'fast', label: 'take the fast tier', test: (r) => r.fast.can },
  { key: 'trace', label: 'be traced', test: (r) => r.trace.can },
]

const COLUMNS: { head: string; href: string }[] = [
  { head: 'Steers', href: '#talking-to-a-turn-already-running' },
  { head: 'Goal', href: '#goals' },
  { head: 'Schema', href: '#answering-in-a-shape' },
  { head: 'Fork', href: '#a-conversation-that-goes-two-ways' },
  { head: 'Web search', href: '#whether-an-agent-may-search-the-web' },
  { head: 'Rungs', href: '#what-an-agent-may-do' },
  { head: 'Moments', href: '#not-every-backend-runs-every-moment' },
  { head: 'Fast tier', href: '#the-service-tier' },
  { head: 'Trace', href: '#how-each-backend-is-driven' },
]

const picked = ref<Set<Key>>(new Set())

function toggle(key: Key) {
  const next = new Set(picked.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  picked.value = next
}

const shown = computed(() =>
  ROWS.filter((row) => FILTERS.every((f) => !picked.value.has(f.key) || f.test(row))),
)

const before = (row: Row): Cell[] => [
  row.steers,
  row.goal,
  row.schema,
  row.fork,
  row.web,
  row.rungs,
]

const after = (row: Row): Cell[] => [row.fast, row.trace]
</script>

<template>
  <div class="hmz-panel matrix">
    <div class="filter" role="group" aria-label="Show only the backends that can">
      <span class="lead">Show only backends that can</span>
      <button
        v-for="f in FILTERS"
        :key="f.key"
        type="button"
        class="chip"
        :aria-pressed="picked.has(f.key)"
        @click="toggle(f.key)"
      >
        {{ f.label }}
      </button>
      <button v-if="picked.size" type="button" class="clear" @click="picked = new Set()">
        clear
      </button>
    </div>
    <div class="scroll">
      <table>
        <caption>
          {{ shown.length }} of {{ ROWS.length }} backends. A filter over what the drivers
          declare; nothing runs.
        </caption>
        <thead>
          <tr>
            <th scope="col" class="name">Backend</th>
            <th v-for="c in COLUMNS" :key="c.head" scope="col">
              <a :href="c.href">{{ c.head }}</a>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in shown" :key="row.name">
            <th scope="row" class="name">
              <code>{{ row.name }}</code>
              <span class="product">{{ row.product }}</span>
            </th>
            <td v-for="(cell, at) in before(row)" :key="at">
              <Badge v-if="cell.text" :type="cell.tone" :text="cell.text" />
              <template v-else><span class="dash" aria-hidden="true">—</span><span class="sr">no</span></template>
            </td>
            <td class="moments">
              <Badge v-for="m in row.moments" :key="m" type="tip" :text="m" />
              <template v-if="!row.moments.length"><span class="dash" aria-hidden="true">—</span><span class="sr">the base six only</span></template>
            </td>
            <td v-for="(cell, at) in after(row)" :key="'after' + at">
              <Badge v-if="cell.text" :type="cell.tone" :text="cell.text" />
              <template v-else><span class="dash" aria-hidden="true">—</span><span class="sr">no</span></template>
            </td>
          </tr>
          <tr v-if="!shown.length">
            <td :colspan="COLUMNS.length + 1" class="none">No backend does all of these.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.matrix {
  padding: 14px 0 6px;
}

.filter {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 0 16px 12px;
  border-bottom: 1px solid var(--hmz-panel-border);
}

.lead {
  font-size: 13px;
  color: var(--vp-c-text-2);
  margin-right: 4px;
}

.chip,
.clear {
  font-size: 12.5px;
  line-height: 1;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  cursor: pointer;
  transition:
    background-color 0.15s,
    border-color 0.15s;
}

.chip:hover,
.clear:hover {
  border-color: var(--vp-c-brand-1);
}

.chip[aria-pressed='true'] {
  background: var(--vp-c-brand-soft);
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.clear {
  border-style: dashed;
  color: var(--vp-c-text-2);
}

.chip:focus-visible,
.clear:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.scroll {
  position: relative;
  overflow-x: auto;
}

.matrix table {
  display: table;
  width: 100%;
  margin: 0;
  border-collapse: collapse;
  font-size: 13px;
}

.matrix caption {
  caption-side: bottom;
  text-align: left;
  padding: 10px 16px 6px;
  font-size: 12.5px;
  color: var(--vp-c-text-2);
}

.matrix th,
.matrix td {
  border: none;
  border-top: 1px solid var(--vp-c-divider);
  padding: 5px 3px;
  text-align: center;
  vertical-align: middle;
  white-space: nowrap;
  background: transparent;
}

.matrix thead th {
  border-top: none;
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1.3;
  white-space: normal;
  color: var(--vp-c-text-2);
  vertical-align: bottom;
}

.matrix thead a {
  color: inherit;
  text-decoration: none;
  border-bottom: 1px dotted var(--vp-c-text-3);
}

.matrix thead a:hover {
  color: var(--vp-c-brand-1);
}

.matrix tr {
  background: transparent;
}

.matrix .name {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--hmz-panel-bg);
  padding-left: 12px;
  padding-right: 6px;
  text-align: left;
}

.matrix tbody .name code {
  font-size: 12px;
}

.matrix tbody .name {
  font-weight: 400;
}

.product {
  display: block;
  max-width: 7.5rem;
  font-size: 11px;
  line-height: 1.3;
  white-space: normal;
  color: var(--vp-c-text-2);
}

.dash {
  color: var(--vp-c-text-3);
}

.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.matrix :deep(.VPBadge) {
  padding: 0 6px;
  margin-left: 0;
  transform: none;
}

.moments :deep(.VPBadge) {
  display: block;
  width: fit-content;
  margin: 2px auto;
}

.none {
  color: var(--vp-c-text-2);
  font-style: italic;
  padding: 14px 16px;
}

@media (prefers-reduced-motion: reduce) {
  .chip,
  .clear {
    transition: none;
  }
}
</style>
