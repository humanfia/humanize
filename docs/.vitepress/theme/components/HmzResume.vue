<script setup lang="ts">
// A loop meant to run for a week is a loop that will be stopped. Run one, pull the plug, and
// pick it up: the round it kept comes back, and so do the copies it made; the conversation
// does not, because a picked-up run opens new sessions. A simulation of a loop that keeps
// one session a run, which is where losing the conversation shows most.
import { computed, onMounted, onUnmounted, ref } from 'vue'

type State = 'idle' | 'running' | 'stopped'

interface Run {
  rounds: number[]
  from: number
  state: State
  session: string
  why: string
}

// Three runs fill the panel; the fourth starts the list again rather than scroll it.
const SHOWN = 3
const BUDGET = 10

// How many runs there have been since the story began, which is what names each one's
// session: every run opens a new one, and none is ever named twice.
let made = 0

const runs = ref<Run[]>([fresh(0)])
const round = ref(0)

let timer = 0
let idle = false

function fresh(from: number): Run {
  const session = `session ${String.fromCharCode(65 + (made % 26))}`
  made += 1
  return { rounds: [], from, state: 'idle', session, why: '' }
}

const now = computed(() => runs.value[runs.value.length - 1])
const running = computed(() => now.value.state === 'running')
const stopped = computed(() => now.value.state === 'stopped')

function tick() {
  if (idle) return
  const run = now.value
  round.value += 1
  run.rounds.push(round.value)
  if (run.rounds.length >= BUDGET) stop('its budget ran out')
}

function start() {
  if (now.value.state !== 'idle') return
  now.value.state = 'running'
  window.clearInterval(timer)
  timer = window.setInterval(tick, 900)
}

function stop(why: string) {
  window.clearInterval(timer)
  now.value.state = 'stopped'
  now.value.why = why
}

function again() {
  if (!stopped.value) return
  const next = fresh(round.value)
  runs.value = runs.value.length >= SHOWN ? [next] : [...runs.value, next]
  start()
}

function reset() {
  window.clearInterval(timer)
  round.value = 0
  made = 0
  runs.value = [fresh(0)]
}

const root = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined

onMounted(() => {
  observer = new IntersectionObserver((entries) => (idle = !entries[0].isIntersecting), {
    rootMargin: '120px',
  })
  if (root.value) observer.observe(root.value)
})

onUnmounted(() => {
  window.clearInterval(timer)
  observer?.disconnect()
})

const said = computed(() => {
  const run = now.value
  if (run.state === 'idle') return 'Nothing has run yet. Start it.'
  if (run.state === 'running' && run.from)
    return `Picked up at round ${run.from + 1}, in a new session that remembers none of rounds 1–${run.from}.`
  if (run.state === 'running') return 'Running. Every round it counts is saved the moment it is counted.'
  return `Stopped at round ${round.value}: ${run.why}. Pick it up and round ${round.value + 1} is next.`
})
</script>

<template>
  <div ref="root" class="resume hmz-panel">
    <div class="bar">
      <button class="go" type="button" :disabled="now.state !== 'idle'" @click="start">
        run it
      </button>
      <button class="kill" type="button" :disabled="!running" @click="stop('you pulled the plug')">
        pull the plug
      </button>
      <button class="go alt" type="button" :disabled="!stopped" @click="again">
        pick it up
      </button>
      <div class="spacer" />
      <span class="sim">simulation</span>
      <button class="ctl" type="button" @click="reset">start over</button>
    </div>

    <div class="body">
      <div class="runs">
        <div v-for="(run, i) in runs" :key="`${run.session}-${run.from}`" class="run" :class="run.state">
          <header>
            <strong>{{ i === 0 && !run.from ? 'the first run' : 'a run picking it up' }}</strong>
            <span v-if="run.state === 'stopped'" class="tag stopped">stopped · {{ run.why }}</span>
            <span v-else-if="run.state === 'running'" class="tag live">running</span>
            <span v-else class="tag">not started</span>
          </header>
          <div class="session">
            <span class="name">{{ run.session }}</span>
            <span class="rounds">
              <span v-for="one in run.rounds" :key="one" class="round">{{ one }}</span>
              <span v-if="!run.rounds.length" class="none">no rounds yet</span>
            </span>
          </div>
        </div>
      </div>

      <aside class="kept" aria-label="what the next run starts from">
        <header>what a run picking it up starts from</header>
        <ul>
          <li class="yes">
            <span class="mark">✓</span>
            <span class="what">what the flow kept</span>
            <code>round: {{ round }}</code>
          </li>
          <li class="yes">
            <span class="mark">✓</span>
            <span class="what">copies and scratch directories it made</span>
            <span class="how">still there</span>
          </li>
          <li class="yes">
            <span class="mark">✓</span>
            <span class="what">your repository</span>
            <span class="how">as the agent left it</span>
          </li>
          <li class="no">
            <span class="mark">✗</span>
            <span class="what">the conversation</span>
            <span class="how">a new session</span>
          </li>
        </ul>
      </aside>
    </div>

    <p class="said" aria-live="polite">{{ said }}</p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 8px 10px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.go,
.kill,
.ctl {
  padding: 5px 14px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
  border: 1px solid var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.go.alt {
  border-color: var(--hmz-accent);
  color: var(--hmz-accent);
  background: transparent;
}

.kill {
  border-color: var(--hmz-warm);
  color: var(--hmz-warm);
  background: transparent;
}

.ctl {
  border-color: var(--vp-c-divider);
  color: var(--vp-c-text-3);
  background: transparent;
  font-weight: 500;
}

button:disabled {
  opacity: 0.4;
  cursor: default;
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

.body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 300px);
  gap: 16px;
  padding: 14px 16px 0;
}

.run {
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  padding: 10px 12px;
  margin-bottom: 10px;
  background: var(--vp-c-bg);
}

.run.running {
  border-color: var(--hmz-accent);
}

.run.stopped {
  border-color: var(--hmz-warm);
  border-style: dashed;
}

.run header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.run strong {
  font-size: 12.5px;
  color: var(--vp-c-text-1);
}

.tag {
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.tag.live {
  color: var(--hmz-accent);
}

.tag.stopped {
  color: var(--hmz-warm);
}

.session {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 9px;
}

.name {
  flex: none;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--vp-c-default-soft);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  line-height: 18px;
  color: var(--vp-c-text-2);
}

.rounds {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  min-height: 22px;
}

.round {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  animation: land 0.3s ease;
}

@keyframes land {
  from {
    opacity: 0;
    transform: scale(0.7);
  }
}

.none {
  font-size: 11.5px;
  line-height: 22px;
  color: var(--vp-c-text-3);
}

.kept {
  align-self: start;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  overflow: hidden;
}

.kept header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.kept ul {
  list-style: none;
  margin: 0;
  padding: 6px 12px 8px;
}

.kept li {
  margin: 0;
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: baseline;
  padding: 5px 0;
  font-size: 12px;
  line-height: 1.4;
}

.kept li + li {
  border-top: 1px solid var(--vp-c-divider);
}

.mark {
  font-weight: 700;
}

.yes .mark {
  color: var(--hmz-accent);
}

.no .mark,
.no .how {
  color: var(--hmz-warm);
}

.what {
  color: var(--vp-c-text-1);
}

.how {
  font-size: 11px;
  color: var(--vp-c-text-3);
  text-align: right;
}

.kept code {
  font-size: 11px;
  color: var(--hmz-accent);
}

.said {
  margin: 0;
  padding: 6px 16px 16px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

@media (max-width: 760px) {
  .body {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .round {
    animation: none;
  }
}
</style>
