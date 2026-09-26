<script setup lang="ts">
// The readout above the editor, for a run of whichever agents are switched on. The figures are
// invented; the rules are the interface's own: every kind any agent reports is a column, a
// kind is marked `+` where some agent of the run does not report it (`Monitor.reckoning` in
// `src/hmz/tui/monitor.py`), the money is the priced models' sum and wears `+` where a model
// has no price (`HmzApp._draw` in `src/hmz/tui/app.py`), and the rate is output tokens a
// second. Which kinds each backend reports is its `counts`, plus what its own log names.
import { computed, ref } from 'vue'

const KINDS = ['input', 'output', 'cache_read', 'cache_write', 'reasoning'] as const
type Kind = (typeof KINDS)[number]

// How a kind is named in a sentence about a backend that does not report it.
const SAID: Record<Kind, string> = {
  input: 'input',
  output: 'output',
  cache_read: 'cached reads',
  cache_write: 'cache writes',
  reasoning: 'reasoning apart from output',
}

interface Runner {
  id: string
  role: string
  spec: string
  called: string
  model: string
  spent: Partial<Record<Kind, number>>
  dollars: number | null
  rate: number
}

const AGENTS: Runner[] = [
  {
    id: 'claude',
    role: 'builder',
    spec: 'claude/claude-opus-5:high',
    called: 'Claude Code',
    model: 'claude-opus-5',
    spent: { input: 8140, output: 1620, cache_read: 812400, cache_write: 38900 },
    dollars: 1.02,
    rate: 64,
  },
  {
    id: 'codex',
    role: 'reviewer',
    spec: 'codex/gpt-5.6-sol:high',
    called: 'Codex',
    model: 'gpt-5.6-sol',
    spent: { input: 4310, output: 540, cache_read: 207600 },
    dollars: 0.32,
    rate: 27,
  },
  {
    id: 'opencode',
    role: 'helper',
    spec: 'opencode/local/my-finetune:auto',
    called: 'opencode',
    model: 'my-finetune',
    spent: { input: 2200, output: 910, cache_read: 30100, cache_write: 0, reasoning: 380 },
    dollars: null,
    rate: 12,
  },
]

const on = ref<Record<string, boolean>>({ claude: true, codex: true, opencode: false })

function flip(id: string) {
  const left = AGENTS.filter((one) => on.value[one.id] && one.id !== id)
  if (on.value[id] && !left.length) return // a run has at least one agent
  on.value = { ...on.value, [id]: !on.value[id] }
}

const running = computed(() => AGENTS.filter((one) => on.value[one.id]))

function thousands(count: number): string {
  if (count < 1000) return count.toFixed(0)
  if (count < 1_000_000) return `${(count / 1000).toFixed(1)}k`
  return `${(count / 1_000_000).toFixed(2)}M`
}

interface Column {
  kind: Kind
  tokens: number
  whole: boolean
  missing: string[]
}

const columns = computed<Column[]>(() =>
  KINDS.filter((kind) => running.value.some((one) => kind in one.spent)).map((kind) => {
    const missing = running.value.filter((one) => !(kind in one.spent)).map((one) => one.called)
    return {
      kind,
      tokens: running.value.reduce((sum, one) => sum + (one.spent[kind] ?? 0), 0),
      whole: missing.length === 0,
      missing,
    }
  }),
)

const priced = computed(() => running.value.filter((one) => one.dollars !== null))
const unpriced = computed(() => running.value.filter((one) => one.dollars === null))
const bill = computed(() => priced.value.reduce((sum, one) => sum + (one.dollars ?? 0), 0))
const rate = computed(() => running.value.reduce((sum, one) => sum + one.rate, 0))

const moneyLine = computed(() => {
  const out = `${rate.value.toFixed(0)} out/s`
  if (!priced.value.length) return out
  const floor = unpriced.value.length ? '+' : ''
  return `$${bill.value.toFixed(2)}${floor} · ${out}`
})

function names(list: string[]): string {
  return list.length < 2 ? list.join('') : `${list.slice(0, -1).join(', ')} and ${list.at(-1)}`
}

const why = computed(() => {
  const said: string[] = []
  for (const one of columns.value) {
    if (!one.whole) {
      said.push(
        `${one.kind}+ — ${names(one.missing)} ${one.missing.length > 1 ? 'do' : 'does'} not report ${SAID[one.kind]}, so this is a floor.`,
      )
    }
  }
  const free = unpriced.value.map((one) => one.model)
  if (!priced.value.length) {
    said.push(`No $ — nobody lists a price for ${names(free)}, so there are tokens and no money.`)
  } else if (free.length) {
    said.push(`$…+ — nobody lists a price for ${names(free)}, so its tokens add nothing to the bill.`)
  }
  if (!said.length) {
    said.push(
      running.value.length === 1
        ? 'One agent: every figure is its own count, so nothing is marked.'
        : 'Every agent reports every kind here, and every model has a price: nothing is marked.',
    )
  }
  return said
})
</script>

<template>
  <div class="readout hmz-panel">
    <div class="pick" role="group" aria-label="agents in the run">
      <span>agents in the run</span>
      <button
        v-for="one in AGENTS"
        :key="one.id"
        type="button"
        :class="{ on: on[one.id] }"
        :aria-pressed="Boolean(on[one.id])"
        @click="flip(one.id)"
      >
        {{ one.called }}
      </button>
    </div>

    <div class="screen" aria-live="polite">
      <p v-for="one in running" :key="one.id" class="agent">
        {{ one.role }} · <span class="spec">{{ one.spec }}</span>
      </p>
      <p class="kinds">
        <template v-for="(one, at) in columns" :key="one.kind">
          <span v-if="at" class="dot"> · </span>
          <span :class="{ floor: !one.whole }">{{ one.kind }} {{ thousands(one.tokens) }}<b v-if="!one.whole">+</b></span>
        </template>
      </p>
      <p class="money">
        <span :class="{ floor: unpriced.length && priced.length }">{{ moneyLine }}</span>
      </p>
    </div>

    <ul class="why">
      <li v-for="one in why" :key="one">{{ one }}</li>
    </ul>

    <p class="caption">
      A simulation with made-up figures. Which columns appear, which wear a <code>+</code>, and
      whether there is money at all follow the rules the readout uses.
    </p>
  </div>
</template>

<style scoped>
.pick {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12.5px;
}

.pick span {
  margin-right: 4px;
  color: var(--vp-c-text-3);
}

.pick button {
  padding: 3px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-3);
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}

.pick button::before {
  content: '○ ';
}

.pick button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.pick button.on::before {
  content: '● ';
}

.screen {
  margin: 14px 16px 0;
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--vp-code-block-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  line-height: 1.7;
  text-align: right;
  overflow-wrap: anywhere;
}

.screen p {
  margin: 0;
  color: var(--vp-c-text-1);
}

.screen .agent {
  color: var(--vp-c-text-2);
}

.screen .spec {
  color: var(--hmz-accent);
}

.screen .dot {
  color: var(--vp-c-text-3);
}

.screen .floor {
  color: var(--hmz-warm);
}

.screen b {
  font-weight: 700;
}

.why {
  margin: 12px 16px 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.why li + li {
  margin-top: 4px;
}

.caption {
  margin: 10px 0 0;
  padding: 0 16px 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--vp-c-text-3);
}

@media (prefers-reduced-motion: reduce) {
  .pick button {
    transition: none;
  }
}
</style>
