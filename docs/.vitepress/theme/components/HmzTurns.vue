<script setup lang="ts">
// Turns wait for each other only inside one session. Move the slider: the same twelve
// prompts, spread across as many conversations as you allow, and the wall clock is what
// changes. The switch is the rule people read past: two turns on one session run one after
// the other, however they are awaited. A simulation -- the minutes are made up.
import { computed, ref } from 'vue'

// Fixed, so the picture is the same every time it is read: a turn is not the same length as
// the turn beside it, and a schedule drawn on equal blocks would be a schedule that lies.
const MINUTES = [3.1, 1.4, 4.2, 2.0, 1.1, 3.6, 2.7, 1.8, 5.0, 2.3, 1.6, 3.3]
const FILES = [
  'parser.py',
  'printer.py',
  'cli.py',
  'billing.py',
  'retry.py',
  'store.py',
  'search.py',
  'auth.py',
  'jobs.py',
  'cache.py',
  'email.py',
  'models.py',
]

const width = ref(4)
const shared = ref(false)

interface Block {
  file: string
  lane: number
  t0: number
  t1: number
}

const schedule = computed(() => {
  const lanes = shared.value ? 1 : Math.max(1, width.value)
  const free = Array.from({ length: lanes }, () => 0)
  const blocks: Block[] = []
  MINUTES.forEach((minutes, i) => {
    let lane = 0
    for (let j = 1; j < free.length; j += 1) if (free[j] < free[lane]) lane = j
    const t0 = free[lane]
    free[lane] = t0 + minutes
    blocks.push({ file: FILES[i], lane, t0, t1: free[lane] })
  })
  return blocks
})

const serial = MINUTES.reduce((sum, one) => sum + one, 0)
const makespan = computed(() => Math.max(...schedule.value.map((one) => one.t1)))
const lanes = computed(() => Math.max(...schedule.value.map((one) => one.lane)) + 1)
const scale = computed(() => 1000 / serial)
const height = computed(() => lanes.value * 22 + 8)
</script>

<template>
  <div class="turns hmz-panel">
    <div class="bar">
      <label class="slider">
        <span>conversations at once</span>
        <input v-model.number="width" type="range" min="1" max="12" step="1" :disabled="shared" />
        <b>{{ shared ? 1 : width }}</b>
      </label>
      <label class="sw">
        <input v-model="shared" type="checkbox" />
        all on one session
      </label>
      <div class="spacer" />
      <span class="sim">simulation</span>
    </div>

    <div class="chart">
      <p class="clock">
        <b>{{ makespan.toFixed(1) }}</b> minutes of wall clock
        <em>for {{ serial.toFixed(1) }} minutes of turns</em>
      </p>
      <svg :viewBox="`0 0 1000 ${height}`" role="img" aria-label="twelve prompts, scheduled">
        <rect
          v-for="(one, i) in schedule"
          :key="i"
          :x="one.t0 * scale"
          :y="one.lane * 22 + 4"
          :width="Math.max(4, (one.t1 - one.t0) * scale - 3)"
          height="16"
          rx="4"
          class="block"
          :style="{ '--tone': `var(--hmz-lane-${(one.lane % 6) + 1})` }"
        />
        <text
          v-for="(one, i) in schedule"
          :key="`t${i}`"
          :x="one.t0 * scale + 6"
          :y="one.lane * 22 + 16"
          class="who"
        >
          {{ (one.t1 - one.t0) * scale > 80 ? one.file : '' }}
        </text>
        <line
          :x1="makespan * scale"
          :x2="makespan * scale"
          y1="0"
          :y2="height"
          class="edge"
        />
      </svg>
      <p class="axis">
        <span>0</span>
        <span class="end">{{ serial.toFixed(0) }} min, one after another</span>
      </p>
    </div>

    <p class="note" :class="{ warn: shared }" aria-live="polite">
      <template v-if="shared">
        One session, so the slider does nothing. A conversation takes one turn at a time, and
        asking it for a second while the first is going is an error, so the flow waits for
        each turn before sending the next. Two turns at once need two
        <strong>sessions</strong>.
      </template>
      <template v-else>
        One agent holding {{ lanes }} conversation{{ lanes === 1 ? '' : 's' }}, each fixing
        its own file. The agent is one role, one CLI and one model, however many
        conversations it holds.
      </template>
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 10px 18px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-2);
}

.slider,
.sw {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  cursor: pointer;
}

.slider input {
  width: 132px;
  accent-color: var(--vp-c-brand-1);
}

.slider input:disabled {
  opacity: 0.35;
}

.sw input {
  accent-color: var(--vp-c-brand-1);
}

.slider b,
.clock b {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
  font-variant-numeric: tabular-nums;
}

.spacer {
  flex: 1;
}

.sim {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.chart {
  padding: 12px 16px 0;
}

.clock {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.clock b {
  font-size: 15px;
}

.clock em {
  font-style: normal;
  color: var(--vp-c-text-3);
}

svg {
  display: block;
  width: 100%;
  height: auto;
}

.block {
  fill: var(--tone);
  opacity: 0.85;
  transition: x 0.35s ease, y 0.35s ease, width 0.35s ease;
}

.who {
  fill: var(--vp-c-bg);
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  pointer-events: none;
}

.edge {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
  transition: x1 0.35s ease, x2 0.35s ease;
}

.axis {
  display: flex;
  justify-content: space-between;
  margin: 4px 0 0;
  font-size: 10.5px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.note {
  margin: 0;
  padding: 14px 16px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

.note.warn strong {
  color: var(--hmz-warm);
}

@media (prefers-reduced-motion: reduce) {
  .block,
  .edge {
    transition: none;
  }
}
</style>
