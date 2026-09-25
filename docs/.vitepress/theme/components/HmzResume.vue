<script setup lang="ts">
// A loop meant to run for a week is a loop that will be stopped. What a resumable flow keeps
// is written to the run's journal as the flow writes it -- setting a key is a line there --
// against the flow call that wrote it. Pull the plug, and pick it up with --resume.
import { computed, onUnmounted, ref } from 'vue'

interface Epic {
  name: string
  rounds: number[]
  from: number
  state: 'running' | 'stopped' | 'idle'
}

const NAMES = [
  '20260817T014455.212Z-9f21ab',
  '20260818T221305.884Z-4c07de',
  '20260819T060102.019Z-71b3aa',
]

const epics = ref<Epic[]>([
  { name: NAMES[0], rounds: [], from: 0, state: 'idle' },
])
const round = ref(0)
const running = ref(false)

let timer = 0

const now = computed(() => epics.value[epics.value.length - 1])

function start() {
  const epic = now.value
  if (epic.state === 'stopped') return
  epic.state = 'running'
  running.value = true
  window.clearInterval(timer)
  timer = window.setInterval(() => {
    round.value += 1
    epic.rounds.push(round.value)
    if (epic.rounds.length > 14) pull()
  }, 900)
}

function pull() {
  window.clearInterval(timer)
  running.value = false
  now.value.state = 'stopped'
}

function again() {
  if (epics.value.length >= NAMES.length) reset()
  const epic = { name: NAMES[epics.value.length], rounds: [], from: round.value, state: 'idle' as const }
  epics.value = [...epics.value, epic]
  start()
}

function reset() {
  window.clearInterval(timer)
  running.value = false
  round.value = 0
  epics.value = [{ name: NAMES[0], rounds: [], from: 0, state: 'idle' }]
}

onUnmounted(() => window.clearInterval(timer))

const held = computed(() =>
  [
    { t: 'call', id: 1, parent: 0, ref: 'nightly:nightly' },
    { t: 'set', id: 1, key: 'rounds', value: round.value },
  ]
    .map((one) => JSON.stringify(one))
    .join('\n'),
)
</script>

<template>
  <div class="resume hmz-panel">
    <div class="bar">
      <button class="go" type="button" :disabled="running || now.state === 'stopped'" @click="start">
        run it
      </button>
      <button class="kill" type="button" :disabled="!running" @click="pull">pull the plug</button>
      <button class="go alt" type="button" :disabled="running || now.state !== 'stopped'" @click="again">
        run it again, --resume
      </button>
      <div class="spacer" />
      <button class="ctl" type="button" @click="reset">start over</button>
    </div>

    <div class="body">
      <div class="runs">
        <div v-for="(epic, i) in epics" :key="epic.name" class="run" :class="epic.state">
          <header>
            <code>{{ epic.name }}</code>
            <span v-if="epic.state === 'stopped'" class="tagline stopped">stopped where it stood</span>
            <span v-else-if="epic.state === 'running'" class="tagline live">running</span>
            <span v-else class="tagline">not started</span>
          </header>
          <p v-if="i > 0" class="picked">
            picked up at round {{ epic.from + 1 }} — the newest resumable run of this flow in this workspace
          </p>
          <div class="rounds">
            <span v-for="one in epic.rounds" :key="one" class="round">{{ one }}</span>
            <span v-if="!epic.rounds.length" class="none">no rounds yet</span>
          </div>
          <ul class="tree">
            <li><code>epic.jsonl</code><em>what the run was, appended as it happened</em></li>
            <li><code>sessions/</code><em>a link apiece to the backend's own transcript</em></li>
            <li v-if="epic.rounds.length">
              <code>journal.jsonl</code><em>what the flow keeps, written as it is set</em>
            </li>
            <li v-if="epic.state === 'stopped'"><code>traces/</code><em>collected afterwards, and filed in here</em></li>
          </ul>
        </div>
      </div>

      <aside class="state">
        <header>journal.jsonl</header>
        <pre>{{ held }}</pre>
        <p>
          Kept against the flow call that wrote it, so a flow that called another is two calls
          and neither writes the other's. Written when a key is set rather than when the run ends — a run
          worth picking up is one that was stopped or killed, and state saved only at the end is
          state such a run has none of.
        </p>
        <p class="lost">
          <strong>What does not come back:</strong> the conversation. A session is spawned rather
          than reopened, so the next run starts from the task and the repository — which is why
          what a flow keeps is its own handful of things and never a second copy of the
          transcript.
        </p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 10px;
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

.body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 320px);
  gap: 16px;
  padding: 14px 16px 16px;
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

.run code {
  font-size: 12px;
  color: var(--vp-c-text-1);
}

.tagline {
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.tagline.live {
  color: var(--hmz-accent);
}

.tagline.stopped {
  color: var(--hmz-warm);
}

.picked {
  margin: 6px 0 0;
  font-size: 11.5px;
  color: var(--hmz-accent);
}

.rounds {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  margin: 9px 0;
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
  color: var(--vp-c-text-3);
}

.tree {
  list-style: none;
  margin: 0;
  padding: 0;
}

.tree li {
  display: flex;
  gap: 10px;
  font-size: 11.5px;
  line-height: 1.8;
}

.tree code {
  min-width: 104px;
  color: var(--vp-c-text-2);
}

.tree em {
  font-style: normal;
  color: var(--vp-c-text-3);
}

.state {
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  overflow: hidden;
}

.state header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.state pre {
  margin: 0;
  padding: 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--hmz-accent);
  background: transparent;
}

.state p {
  margin: 0;
  padding: 0 12px 12px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--vp-c-text-3);
}

.state .lost strong {
  color: var(--vp-c-text-2);
}

@media (max-width: 820px) {
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
