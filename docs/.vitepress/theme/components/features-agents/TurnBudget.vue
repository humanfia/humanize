<script setup lang="ts">
// One turn under a budget of its own, played three ways at once: which limit, whether it is
// graceful, and whether the backend counts its spending as each response lands or only states
// it when the turn ends. The rules are the driver's in `src/hmz/runtime/flowing/harnesses.py`:
// a graceful turn runs to its end; one that is not is cut off the moment a limit is reached,
// which for a token limit is when the spending is reported (`_spends` in each driver under
// `src/hmz/coganchor/agents/`, or only the turn's `result` for agy, cursor, grok and qwen), and
// for a time limit is the clock.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

type Limit = 'tokens' | 'time'
type Counts = 'live' | 'end'

const REQUESTS = [
  { at: 0.1, tokens: 700 },
  { at: 0.22, tokens: 900 },
  { at: 0.35, tokens: 800 },
  { at: 0.48, tokens: 1000 },
  { at: 0.6, tokens: 1100 },
  { at: 0.72, tokens: 700 },
  { at: 0.84, tokens: 600 },
  { at: 0.96, tokens: 500 },
]
const TOTAL = REQUESTS.reduce((sum, one) => sum + one.tokens, 0)
const TOKENS = 4000 // the token limit
const MINUTES = 10 // how long the turn would take
const DEADLINE = 0.55 // the time limit, as a share of that

const limit = ref<Limit>('tokens')
const graceful = ref(false)
const counts = ref<Counts>('live')

const clock = ref(1) // 0..1 of the turn; 1 is at rest, showing the end
const playing = ref(false)

// Where the turn is cut off, as a share of it, or 1 where it runs to its end.
const cut = computed(() => {
  if (graceful.value) return 1
  if (limit.value === 'time') return DEADLINE
  if (counts.value === 'end') return 1
  let spent = 0
  for (const one of REQUESTS) {
    spent += one.tokens
    if (spent >= TOKENS) return one.at
  }
  return 1
})

const cutOff = computed(() => cut.value < 1)
const raises = computed(() => !graceful.value && (cutOff.value || overAtEnd.value))
const overAtEnd = computed(
  () => limit.value === 'tokens' && counts.value === 'end' && TOTAL >= TOKENS,
)

const now = computed(() => Math.min(clock.value, cut.value))
const landed = computed(() => REQUESTS.filter((one) => one.at <= now.value))
const written = computed(() => landed.value.reduce((sum, one) => sum + one.tokens, 0))
const ended = computed(() => clock.value >= cut.value)
const counted = computed(() => {
  if (counts.value === 'live') return written.value
  return ended.value && cut.value === 1 ? TOTAL : 0
})
const reported = computed(() => counts.value === 'live' || (ended.value && cut.value === 1))

const outcome = computed(() => {
  if (graceful.value) {
    return limit.value === 'time'
      ? 'Graceful: the turn runs on past its time and answers in full. A graceful limit never cuts a turn short.'
      : 'Graceful: the turn runs to its end and answers in full, whatever it spends. A graceful limit never cuts a turn short.'
  }
  if (limit.value === 'time') {
    return `Cut off at ${Math.round(DEADLINE * MINUTES)} minutes, whatever the backend reports. The flow gets an error instead of an answer.`
  }
  if (counts.value === 'live') {
    return 'Cut off as the response that crosses the limit lands. The flow gets an error instead of an answer.'
  }
  return 'Nothing is reported until the turn ends, so it runs to its end. Then the whole spend arrives at once, and the flow gets an error instead of an answer.'
})

let frame = 0
let last = 0
let idle = false

function tick(at: number) {
  const dt = Math.min((at - last) / 1000, 0.1)
  last = at
  if (!idle) clock.value = Math.min(1, clock.value + dt / 6)
  if (clock.value >= cut.value || clock.value >= 1) {
    playing.value = false
    return
  }
  frame = requestAnimationFrame(tick)
}

function play() {
  cancelAnimationFrame(frame)
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    clock.value = 1
    return
  }
  clock.value = 0
  playing.value = true
  last = performance.now()
  frame = requestAnimationFrame(tick)
}

// A setting changed mid-play shows where that setting ends up rather than half a run of each.
watch([limit, graceful, counts], () => {
  cancelAnimationFrame(frame)
  playing.value = false
  clock.value = 1
})

const root = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined

onMounted(() => {
  observer = new IntersectionObserver((entries) => (idle = !entries[0].isIntersecting))
  if (root.value) observer.observe(root.value)
})

onUnmounted(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
})

const pct = (share: number) => `${(share * 100).toFixed(1)}%`
const thousands = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div ref="root" class="budget hmz-panel">
    <div class="bar">
      <div class="seg" role="group" aria-label="which limit">
        <button type="button" :aria-pressed="limit === 'tokens'" :class="{ on: limit === 'tokens' }" @click="limit = 'tokens'">
          {{ thousands(TOKENS) }} output tokens
        </button>
        <button type="button" :aria-pressed="limit === 'time'" :class="{ on: limit === 'time' }" @click="limit = 'time'">
          {{ Math.round(DEADLINE * MINUTES) }} minutes
        </button>
      </div>
      <div class="seg" role="group" aria-label="graceful or not">
        <button type="button" :aria-pressed="!graceful" :class="{ on: !graceful }" @click="graceful = false">
          not graceful
        </button>
        <button type="button" :aria-pressed="graceful" :class="{ on: graceful }" @click="graceful = true">
          graceful
        </button>
      </div>
      <div class="seg" role="group" aria-label="when the backend reports what it spent">
        <button type="button" :aria-pressed="counts === 'live'" :class="{ on: counts === 'live' }" @click="counts = 'live'">
          counts as it goes
        </button>
        <button type="button" :aria-pressed="counts === 'end'" :class="{ on: counts === 'end' }" @click="counts = 'end'">
          counts at the end
        </button>
      </div>
      <div class="spacer" />
      <span class="sim">simulation</span>
      <button class="go" type="button" :disabled="playing" @click="play">
        {{ playing ? 'running…' : 'run the turn' }}
      </button>
    </div>

    <div class="rows">
      <div class="row">
        <span class="lab">the turn</span>
        <div class="track">
          <span
            v-for="(one, i) in REQUESTS"
            :key="i"
            class="req"
            :class="{ in: one.at <= now, lost: one.at > cut }"
            :style="{ left: pct(one.at - 0.09), width: pct(0.08) }"
          />
          <span v-if="cutOff" class="cut" :class="{ in: ended }" :style="{ left: pct(cut) }">
            <em>cut off</em>
          </span>
          <span class="head" :style="{ left: pct(now) }" />
        </div>
      </div>

      <div v-if="limit === 'tokens'" class="row">
        <span class="lab">tokens counted</span>
        <div class="meter">
          <span class="fill" :class="{ over: counted >= TOKENS }" :style="{ width: pct(counted / TOTAL) }" />
          <span class="mark" :style="{ left: pct(TOKENS / TOTAL) }"><em>limit</em></span>
        </div>
        <span class="num">{{ reported ? thousands(counted) : 'not yet' }}</span>
      </div>

      <div v-else class="row">
        <span class="lab">the clock</span>
        <div class="meter">
          <span class="fill" :class="{ over: now >= DEADLINE }" :style="{ width: pct(now) }" />
          <span class="mark" :style="{ left: pct(DEADLINE) }"><em>limit</em></span>
        </div>
        <span class="num">{{ Math.round(now * MINUTES) }} min</span>
      </div>
    </div>

    <p v-if="playing" class="outcome running">The turn is running…</p>
    <p v-else class="outcome" :class="{ hard: raises }" aria-live="polite">
      <strong>{{ raises ? 'Stopped.' : 'Answered.' }}</strong> {{ outcome }}
      <template v-if="raises">
        What it did before that is on disk, and the conversation is still open.
      </template>
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
}

.seg {
  display: inline-flex;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  overflow: hidden;
}

.seg button {
  padding: 4px 11px;
  border: 0;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 11.5px;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.seg button + button {
  border-left: 1px solid var(--vp-c-divider);
}

.seg button.on {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 650;
}

.spacer {
  flex: 1;
}

.sim {
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.go {
  padding: 5px 14px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.go:disabled {
  opacity: 0.55;
  cursor: default;
}

.rows {
  padding: 18px 16px 4px;
}

.row {
  display: grid;
  grid-template-columns: 7.5rem minmax(0, 1fr) 4.5rem;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.lab {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.num {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  text-align: right;
  color: var(--vp-c-text-1);
}

.track,
.meter {
  position: relative;
  height: 22px;
  border-radius: 6px;
  background: var(--vp-c-default-soft);
}

.req {
  position: absolute;
  top: 4px;
  bottom: 4px;
  border-radius: 4px;
  border: 1px dashed var(--vp-c-text-3);
  transition: background 0.25s, opacity 0.25s;
}

.req.in {
  border-style: solid;
  border-color: transparent;
  background: var(--vp-c-brand-1);
}

.req.lost {
  opacity: 0.5;
}

.head {
  position: absolute;
  top: -3px;
  bottom: -3px;
  width: 2px;
  background: var(--vp-c-text-1);
}

.cut {
  position: absolute;
  top: -6px;
  bottom: -6px;
  width: 2px;
  background: var(--hmz-warm);
  opacity: 0.35;
}

.cut.in {
  opacity: 1;
}

.cut em,
.mark em {
  position: absolute;
  top: -16px;
  left: 50%;
  transform: translateX(-50%);
  font-style: normal;
  font-size: 10px;
  white-space: nowrap;
  color: var(--hmz-warm);
}

.meter .fill {
  display: block;
  height: 100%;
  border-radius: 6px;
  background: var(--hmz-accent);
  transition: width 0.2s;
}

.meter .fill.over {
  background: var(--hmz-warm);
}

.mark {
  position: absolute;
  top: -4px;
  bottom: -4px;
  width: 2px;
  background: var(--vp-c-text-1);
}

.mark em {
  color: var(--vp-c-text-2);
}

.outcome {
  margin: 0 16px 16px;
  padding: 12px 14px;
  border: 1px solid var(--vp-c-divider);
  border-left: 3px solid var(--hmz-accent);
  border-radius: 10px;
  background: var(--vp-c-bg);
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.outcome.hard {
  border-left-color: var(--hmz-warm);
}

.outcome.running {
  border-left-color: var(--vp-c-divider);
  color: var(--vp-c-text-3);
}

.outcome strong {
  color: var(--vp-c-text-1);
}

@media (max-width: 560px) {
  .row {
    grid-template-columns: minmax(0, 1fr) 4rem;
  }

  .lab {
    grid-column: 1 / -1;
    margin-bottom: -6px;
  }
}
</style>
