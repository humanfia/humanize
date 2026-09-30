<script setup lang="ts">
// The capability matrix at the top of /reference/agents, with a filter over it.
//
// Every cell is read off the code, and has to go on matching it:
// - Goal, Loop, Steer, Permission, Subagent, AskUser: the mixins each harness protocol in
//   `HARNESS_AGENTS` (src/hmz/flows/agents.py) inherits -- what a flow role typed as that
//   harness may ask for
// - Schema, Tools: `shapes` and `takes_tools` on each session class in
//   src/hmz/coganchor/agents/*.py
// - Rungs, Fast: `rungs` and `service_tiers` on each agent class there
// - Fork, Web off: `forks` and `searches` on each Profile in src/hmz/coganchor/backends.py (an
//   added ACP CLI is `_speaks`); "+cwd" is `forks_elsewhere` on the session class
// - Trace: `_READERS` in src/hmz/runtime/tracing/collector.py
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

type Key =
  | 'goal'
  | 'loop'
  | 'steer'
  | 'perm'
  | 'sub'
  | 'ask'
  | 'schema'
  | 'fork'
  | 'web'
  | 'rungs'
  | 'fast'
  | 'tools'
  | 'trace'

interface Row {
  name: string
  product: string
  cells: Record<Key, Cell>
}

interface Column {
  key: Key
  head: string
  href: string
  filter: string
  group: 'flow' | 'driver'
}

// A cell with no text is a backend that cannot, drawn as a quiet dash so that what a backend
// can do is what the eye lands on.
const Y: Cell = { can: true, text: 'yes', tone: 'tip' }
const N: Cell = { can: false, text: '', tone: 'info' }
const ELSEWHERE: Cell = { can: true, text: '+cwd', tone: 'tip' }
const IF_SERVED: Cell = { can: true, text: 'if served', tone: 'warning' }
const ALL4: Cell = { can: true, text: 'all 4', tone: 'tip' }
const BYPASS: Cell = { can: false, text: 'bypass', tone: 'warning' }
const NO_RO: Cell = { can: false, text: 'no read-only', tone: 'warning' }

const COLUMNS: Column[] = [
  { key: 'goal', head: 'Goal', href: '#goals', filter: 'pursue a goal', group: 'flow' },
  { key: 'loop', head: 'Loop', href: '#loops', filter: 'run /loop', group: 'flow' },
  { key: 'steer', head: 'Steer', href: '#talking-to-a-turn-already-running', filter: 'be steered mid-turn', group: 'flow' },
  { key: 'perm', head: 'Permission', href: '#when-a-permissionrequest-refusal-reaches-the-agent', filter: 'answer permission requests', group: 'flow' },
  { key: 'sub', head: 'Subagent', href: '#not-every-backend-runs-every-moment', filter: 'report subagents', group: 'flow' },
  { key: 'ask', head: 'AskUser', href: '#questions', filter: 'ask the user', group: 'flow' },
  { key: 'schema', head: 'Schema held', href: '#answering-in-a-shape', filter: 'hold a schema', group: 'driver' },
  { key: 'fork', head: 'Fork', href: '#a-conversation-that-goes-two-ways', filter: 'fork', group: 'driver' },
  { key: 'web', head: 'Web off', href: '#whether-an-agent-may-search-the-web', filter: 'switch web search off', group: 'driver' },
  { key: 'rungs', head: 'Rungs', href: '#what-an-agent-may-do', filter: 'take all four rungs', group: 'driver' },
  { key: 'fast', head: 'Fast tier', href: '#the-service-tier', filter: 'take the fast tier', group: 'driver' },
  { key: 'tools', head: 'Tools', href: '#callbacks-as-tools', filter: 'be offered callbacks', group: 'driver' },
  { key: 'trace', head: 'Trace', href: '#state-and-logs', filter: 'be traced', group: 'driver' },
]

function row(
  name: string,
  product: string,
  said: Partial<Record<Key, Cell>>,
): Row {
  const cells = {} as Record<Key, Cell>
  for (const c of COLUMNS) cells[c.key] = said[c.key] ?? N
  return { name, product, cells }
}

const ROWS: Row[] = [
  row('agy', 'Antigravity', { schema: Y, web: Y, rungs: ALL4, trace: Y }),
  row('claude', 'Claude Code', {
    goal: Y, loop: Y, steer: Y, perm: Y, sub: Y, ask: Y,
    schema: Y, fork: ELSEWHERE, web: Y, rungs: ALL4, fast: Y, tools: Y, trace: Y,
  }),
  row('codex', 'Codex', {
    goal: Y, steer: Y, perm: Y, sub: Y, ask: Y,
    schema: Y, fork: ELSEWHERE, web: Y, rungs: ALL4, fast: Y, tools: Y, trace: Y,
  }),
  row('cursor-agent', 'Cursor Agent', { sub: Y, rungs: ALL4, fast: Y }),
  row('dsh', 'DeepSeek Harness', { goal: Y, web: Y, rungs: BYPASS, trace: Y }),
  row('grok', 'Grok Build', { schema: Y, fork: Y, web: Y, rungs: ALL4, trace: Y }),
  row('kimi', 'Kimi Code', {
    goal: Y, steer: Y, perm: Y, ask: Y,
    fork: ELSEWHERE, web: Y, rungs: ALL4, trace: Y,
  }),
  row('mcode', 'MiniMax Code', { sub: Y, schema: Y, rungs: NO_RO, trace: Y }),
  row('mimo', 'mimocode', { fork: Y, web: Y, rungs: ALL4, trace: Y }),
  row('opencode', 'opencode', { fork: Y, web: Y, rungs: ALL4, trace: Y }),
  row('pi', 'pi', { steer: Y, ask: Y, fork: Y, rungs: ALL4, trace: Y }),
  row('qwen', 'Qwen Code', { schema: Y, fork: Y, web: Y, rungs: ALL4, trace: Y }),
  row('an ACP CLI', 'added on this machine', { fork: IF_SERVED, rungs: BYPASS }),
]

const picked = ref<Set<Key>>(new Set())

function toggle(key: Key) {
  const next = new Set(picked.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  picked.value = next
}

const shown = computed(() =>
  ROWS.filter((r) => [...picked.value].every((key) => r.cells[key].can)),
)

const flowColumns = COLUMNS.filter((c) => c.group === 'flow')
const driverColumns = COLUMNS.filter((c) => c.group === 'driver')
</script>

<template>
  <div class="hmz-panel matrix">
    <div class="filter" role="group" aria-label="Show only the backends that can">
      <span class="lead">Show only backends that can</span>
      <button
        v-for="c in COLUMNS"
        :key="c.key"
        type="button"
        class="chip"
        :aria-pressed="picked.has(c.key)"
        @click="toggle(c.key)"
      >
        {{ c.filter }}
      </button>
      <button v-if="picked.size" type="button" class="clear" @click="picked = new Set()">
        clear
      </button>
    </div>
    <div class="scroll">
      <table>
        <caption>
          {{ shown.length }} of {{ ROWS.length }} backends. Read off what the harness protocols
          and the drivers declare; nothing runs.
        </caption>
        <thead>
          <tr class="groups">
            <th scope="col" class="name"></th>
            <th scope="colgroup" :colspan="flowColumns.length">Flow mixins served</th>
            <th scope="colgroup" :colspan="driverColumns.length" class="split">Driver</th>
          </tr>
          <tr>
            <th scope="col" class="name">Backend</th>
            <th
              v-for="(c, at) in COLUMNS"
              :key="c.key"
              scope="col"
              :class="{ split: at === flowColumns.length }"
            >
              <a :href="c.href">{{ c.head }}</a>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in shown" :key="r.name">
            <th scope="row" class="name">
              <code>{{ r.name }}</code>
              <span class="product">{{ r.product }}</span>
            </th>
            <td
              v-for="(c, at) in COLUMNS"
              :key="c.key"
              :class="{ split: at === flowColumns.length }"
            >
              <Badge v-if="r.cells[c.key].text" :type="r.cells[c.key].tone" :text="r.cells[c.key].text" />
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

.matrix thead .groups th {
  font-size: 10.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--vp-c-text-3);
  padding-bottom: 2px;
}

.matrix .split {
  border-left: 1px solid var(--vp-c-divider);
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
