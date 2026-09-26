<script setup lang="ts">
// Every backend against what a flow may ask of it. Each column is read off the code:
//   steer   `steers` on the session class in `src/hmz/coganchor/agents/<cli>.py`
//   goal    a `_pursue` of the session's own
//   shape   `shapes` on the session class
//   fork    `forks` on the profile in `src/hmz/coganchor/backends.py`
//   search  `searches` on the profile
//   trace   a reader in `_READERS`, `src/hmz/runtime/tracing/collector.py`
//   skills  a non-empty `mounts` on the profile
//   fast    `fast` among the agent class's `service_tiers`
// The ladders are the `_CLAUDE`, `_CODEX`, … tuples in `backends.py`, and `spend` is whether
// the driver calls `_spends` as each request lands or only states the turn's cost at its end.
import { computed, ref } from 'vue'

type Cap = 'steer' | 'goal' | 'shape' | 'fork' | 'search' | 'trace' | 'skills' | 'fast'
type Spend = 'live' | 'end' | 'none'

interface Backend {
  name: string
  called: string
  efforts: string[]
  has: Cap[]
  partly?: Cap[]
  spend: Spend
  extra?: string
  note: string
}

const CAPS: { key: Cap; said: string; head: string }[] = [
  { key: 'steer', said: 'takes a line mid-turn', head: 'steered mid-turn' },
  { key: 'goal', said: 'keeps a goal of its own', head: 'its own goal' },
  { key: 'shape', said: 'is held to a shape', head: 'held to a shape' },
  { key: 'fork', said: 'forks a conversation', head: 'forks' },
  { key: 'search', said: 'can be kept off the web', head: 'web search switch' },
  { key: 'trace', said: 'is read back as a trace', head: 'trace' },
  { key: 'skills', said: 'carries a flow’s skills', head: 'skills from a flow' },
  { key: 'fast', said: 'has a faster tier', head: 'fast tier' },
]

const BACKENDS: Backend[] = [
  {
    name: 'claude',
    called: 'Claude Code',
    efforts: ['ultracode', 'max', 'xhigh', 'high', 'medium', 'low'],
    has: ['steer', 'goal', 'shape', 'fork', 'search', 'trace', 'skills', 'fast'],
    spend: 'live',
    note: '“ultracode” is “xhigh” with the turn orchestrating a fleet of its own: a rung Claude Code takes and never lists.',
  },
  {
    name: 'codex',
    called: 'Codex',
    efforts: ['ultra', 'max', 'xhigh', 'high', 'medium', 'low'],
    has: ['steer', 'goal', 'shape', 'fork', 'search', 'trace', 'skills', 'fast'],
    spend: 'live',
    note: 'Its models take different rungs, “ultra” on some and not on others, so each model offers only the rungs it takes.',
  },
  {
    name: 'cursor-agent',
    called: 'Cursor Agent',
    efforts: ['max', 'xhigh', 'extra-high', 'high', 'medium', 'low', 'minimal', 'none'],
    has: ['skills', 'fast'],
    spend: 'end',
    note: 'The effort is part of the model’s own name, as in gpt-5.2-high, and some models take no rung at all: “auto” is the one to pick for those. A flow cannot keep it off the web.',
  },
  {
    name: 'dsh',
    called: 'DeepSeek Harness',
    efforts: ['max', 'high', 'low', 'off'],
    has: ['goal', 'search', 'trace'],
    spend: 'live',
    extra: 'dsh',
    note: 'Runs on your own DeepSeek key or gateway rather than a subscription login. “off” asks the model not to reason. It takes none of the skills a flow brings.',
  },
  {
    name: 'grok',
    called: 'Grok Build',
    efforts: ['xhigh', 'high', 'medium', 'low'],
    has: ['shape', 'fork', 'search', 'trace', 'skills'],
    spend: 'end',
    note: 'The four rungs are the ones Grok Build itself names when it refuses a fifth.',
  },
  {
    name: 'kimi',
    called: 'Kimi Code',
    efforts: ['max', 'high', 'medium', 'low'],
    has: ['steer', 'goal', 'fork', 'search', 'trace', 'skills'],
    spend: 'live',
    extra: 'kimi',
    note: '“swarm” in front of a rung, as in swarmmax, is the same thinking run as a fleet of agents rather than one. The fleet is a width, chosen beside the effort.',
  },
  {
    name: 'pi',
    called: 'pi',
    efforts: ['max', 'xhigh', 'high', 'medium', 'low', 'minimal', 'off'],
    has: ['steer', 'fork', 'trace'],
    spend: 'live',
    note: '“off” asks the model not to think at all. It takes none of the skills a flow brings, and a flow cannot keep it off the web.',
  },
  {
    name: 'qwen',
    called: 'Qwen Code',
    efforts: ['max', 'xhigh', 'high', 'medium', 'low', 'none'],
    has: ['shape', 'fork', 'search', 'trace', 'skills'],
    spend: 'end',
    note: '“none” asks the model not to reason. It is the rung a model with no reasoning setting runs at.',
  },
  {
    name: 'agy',
    called: 'Antigravity',
    efforts: ['high', 'medium', 'low'],
    has: ['shape', 'trace', 'skills'],
    spend: 'end',
    note: 'Some of its models have no variants and take no rung: “auto” is the one to pick for those. A flow cannot keep it off the web.',
  },
  {
    name: 'opencode',
    called: 'opencode',
    efforts: ['xhigh', 'high', 'medium', 'low', 'minimal'],
    has: ['fork', 'search', 'trace', 'skills'],
    spend: 'live',
    note: 'Its effort picks the model’s variant. A provider with no variants takes the rung and ignores it.',
  },
  {
    name: 'mimo',
    called: 'mimocode',
    efforts: ['xhigh', 'high', 'medium', 'low', 'minimal'],
    has: ['fork', 'search', 'trace', 'skills'],
    spend: 'live',
    note: 'A fork of opencode, with models of its own. Its effort picks the model’s variant, as opencode’s does.',
  },
  {
    name: 'zcode',
    called: 'ZCode',
    efforts: ['max', 'xhigh', 'high', 'medium', 'low', 'enabled', 'nothink', 'disabled'],
    has: ['goal', 'fork', 'search', 'trace', 'skills'],
    spend: 'live',
    note: 'Its models take different rungs. Some take a thinking budget up to “max”, one takes “nothink”, and some take only “enabled” or “disabled”.',
  },
  {
    name: 'your own',
    called: 'any CLI speaking ACP',
    efforts: ['as configured'],
    has: [],
    partly: ['fork'],
    spend: 'none',
    note: 'Anything that speaks the Agent Client Protocol, added in the providers menu. It runs the model and effort you configured it with, and humanize sends neither. It forks only if it serves the protocol’s fork call.',
  },
]

const SPEND: Record<Spend, string> = {
  live: 'as each request lands, so a limit on tokens or cost can stop a turn midway',
  end: 'only once the turn is over, so a limit on tokens or cost can only stop it then',
  none: 'never: only a limit on time can stop one of its turns',
}

const wanted = ref<Cap[]>([])
const opened = ref('claude')

function want(key: Cap) {
  wanted.value = wanted.value.includes(key)
    ? wanted.value.filter((one) => one !== key)
    : [...wanted.value, key]
}

const mark = (one: Backend, cap: Cap) =>
  one.has.includes(cap) ? 'yes' : one.partly?.includes(cap) ? 'partly' : 'no'
const fits = (one: Backend) => wanted.value.every((cap) => mark(one, cap) !== 'no')
const counted = computed(() => BACKENDS.filter(fits).length)
const open = computed(() => BACKENDS.find((one) => one.name === opened.value) ?? BACKENDS[0])

function rowLabel(one: Backend) {
  const yes = CAPS.filter((cap) => mark(one, cap.key) !== 'no').map((cap) => cap.head)
  return `${one.name}, ${one.called}: ${yes.length ? yes.join(', ') : 'none of these'}`
}
</script>

<template>
  <div class="backends hmz-panel">
    <div class="bar">
      <span class="what">What does your role need?</span>
      <div class="wants" role="group" aria-label="filter backends by what they can do">
        <button
          v-for="one in CAPS"
          :key="one.key"
          type="button"
          :aria-pressed="wanted.includes(one.key)"
          :class="{ on: wanted.includes(one.key) }"
          @click="want(one.key)"
        >
          {{ one.said }}
        </button>
      </div>
      <span class="count" aria-live="polite">
        <b>{{ counted }}</b> of {{ BACKENDS.length }} fit
      </span>
    </div>

    <div class="grid">
      <div class="head" aria-hidden="true">
        <span class="corner">backend</span>
        <span
          v-for="one in CAPS"
          :key="one.key"
          class="cap"
          :class="{ on: wanted.includes(one.key) }"
        >
          <span>{{ one.head }}</span>
        </span>
      </div>
      <button
        v-for="one in BACKENDS"
        :key="one.name"
        type="button"
        class="row"
        :class="{ dim: !fits(one), on: opened === one.name }"
        :aria-label="rowLabel(one)"
        :aria-pressed="opened === one.name"
        aria-controls="hmz-backend-detail"
        @click="opened = one.name"
      >
        <span class="name">
          <code>{{ one.name }}</code>
          <em>{{ one.called }}</em>
        </span>
        <span
          v-for="cap in CAPS"
          :key="cap.key"
          class="dot"
          :class="[mark(one, cap.key), { on: wanted.includes(cap.key) }]"
          aria-hidden="true"
          :title="`${cap.head}: ${mark(one, cap.key) === 'partly' ? 'if the CLI serves it' : mark(one, cap.key)}`"
        >
          {{ mark(one, cap.key) === 'yes' ? '●' : mark(one, cap.key) === 'partly' ? '◐' : '·' }}
        </span>
      </button>
    </div>

    <div id="hmz-backend-detail" class="detail" aria-live="polite">
      <div class="ladder">
        <span class="lab"><code>{{ open.name }}</code> · its efforts, hardest first</span>
        <div class="rungs">
          <span v-for="(one, i) in open.efforts" :key="`${open.name}-${one}`" :style="{ '--i': i }">
            {{ one }}
          </span>
        </div>
        <p class="auto">
          <code>auto</code> is on every backend: humanize says nothing about effort, and the
          model runs at its CLI’s own default.
        </p>
      </div>
      <div class="said">
        <p><strong>Spend is known</strong> {{ SPEND[open.spend] }}.</p>
        <p v-if="open.extra">
          <strong>Needs</strong> humanize installed with its <code>{{ open.extra }}</code> extra.
        </p>
        <p class="note">{{ open.note }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 10px 14px;
  flex-wrap: wrap;
  padding: 12px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-2);
}

.what {
  font-weight: 650;
  color: var(--vp-c-text-1);
}

.wants {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  flex: 1 1 320px;
}

.wants button {
  padding: 3px 11px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 11.5px;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, border-color 0.2s;
}

.wants button:hover {
  border-color: var(--vp-c-brand-1);
}

.wants button.on {
  border-style: solid;
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.count {
  font-family: var(--vp-font-family-mono);
  white-space: nowrap;
}

.count b {
  color: var(--vp-c-brand-1);
}

.grid {
  padding: 6px 10px 0;
}

.head,
.row {
  display: grid;
  grid-template-columns: minmax(96px, 1fr) repeat(8, minmax(24px, 52px));
  align-items: center;
  column-gap: 2px;
}

.head {
  align-items: end;
  padding: 0 8px 6px;
  border-bottom: 1px solid var(--vp-c-divider);
}

.corner {
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.cap {
  display: flex;
  justify-content: center;
  height: 104px;
}

.cap span {
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  font-size: 11px;
  line-height: 1.2;
  color: var(--vp-c-text-3);
  white-space: nowrap;
}

.cap.on span {
  color: var(--vp-c-brand-1);
  font-weight: 650;
}

.row {
  width: 100%;
  padding: 5px 8px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  text-align: left;
  color: var(--vp-c-text-2);
  cursor: pointer;
  transition: opacity 0.2s, background 0.2s, border-color 0.2s;
}

.row:hover {
  background: var(--vp-c-default-soft);
}

.row.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
}

.row.dim {
  opacity: 0.32;
}

.name {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.name code {
  font-size: 12.5px;
  font-weight: 650;
  color: var(--vp-c-text-1);
  background: none;
  padding: 0;
}

.name em {
  font-style: normal;
  font-size: 10.5px;
  color: var(--vp-c-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dot {
  text-align: center;
  font-size: 13px;
  line-height: 1;
}

.dot.yes {
  color: var(--hmz-accent);
}

.dot.partly {
  color: var(--hmz-warm);
}

.dot.no {
  font-size: 16px;
  color: var(--vp-c-text-3);
}

.dot.on.yes,
.dot.on.partly {
  text-shadow: 0 0 8px var(--hmz-accent);
}

.detail {
  display: grid;
  grid-template-columns: minmax(0, 280px) minmax(0, 1fr);
  gap: 18px;
  margin: 12px 16px 16px;
  padding: 14px 16px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
}

.lab {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.lab code {
  text-transform: none;
  letter-spacing: 0;
  color: var(--vp-c-text-1);
}

.rungs {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 10px 0 0;
}

.rungs span {
  padding: 3px 10px;
  border-radius: 7px;
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  color: var(--vp-c-text-1);
  background: linear-gradient(
    90deg,
    var(--vp-c-brand-soft) calc(100% - var(--i) * 11%),
    transparent calc(100% - var(--i) * 11%)
  );
  animation: rung 0.4s ease backwards;
  animation-delay: calc(var(--i) * 40ms);
}

@keyframes rung {
  from {
    opacity: 0;
    transform: translateX(-6px);
  }
}

.auto {
  margin: 10px 0 0;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--vp-c-text-3);
}

.said p {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.said strong {
  color: var(--vp-c-text-1);
  margin-right: 4px;
}

.said .note {
  color: var(--vp-c-text-2);
}

@media (max-width: 780px) {
  .detail {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 480px) {
  .grid {
    padding: 6px 4px 0;
  }

  .head,
  .row {
    grid-template-columns: minmax(84px, 1fr) repeat(8, 24px);
    padding-left: 6px;
    padding-right: 6px;
  }

  .name em {
    display: none;
  }

  .detail {
    margin: 12px 10px 14px;
    padding: 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .rungs span {
    animation: none;
  }
}
</style>
