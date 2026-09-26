<script setup lang="ts">
// A terminal watches a run; it does not own it. Close one, and the run carries on with nobody
// watching. Run `hmz` in the same directory and the whole screen is drawn again. Leaving and
// stopping are two different answers to `/exit`, and a machine that restarts takes the run
// with it -- which is what picking a run up is for. A simulation; the rounds are drawn.
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

type RunState = 'running' | 'stopped' | 'gone'

interface Term {
  id: string
  name: string
  on: boolean
  redrawn: boolean
  // What the terminal says once it is no longer watching, and whether it is still open at all.
  why: string
  open: boolean
}

const START = 7

const run = ref<RunState>('running')
const round = ref(START)
const said = ref('Two terminals are watching one run.')

const terms = reactive<Term[]>([
  { id: 'laptop', name: 'your laptop', on: true, redrawn: false, why: '', open: true },
  { id: 'desk', name: 'a second terminal', on: true, redrawn: false, why: '', open: true },
])

const watching = computed(() => terms.filter((one) => one.on).length)
const alive = computed(() => run.value === 'running')

let timer = 0
let idle = false

function tick() {
  if (idle || run.value !== 'running') return
  round.value += 1
  for (const one of terms) one.redrawn = false
}

// Every terminal still watching lets go, saying why.
function letGo(why: string) {
  for (const one of terms) {
    if (!one.on) continue
    one.on = false
    one.redrawn = false
    one.why = why
  }
}

function close(term: Term) {
  term.on = false
  term.redrawn = false
  term.open = false
  said.value =
    watching.value === 0
      ? `Nobody is watching, and round ${round.value} carries on regardless.`
      : `${cap(term.name)} closed. The run did not notice.`
}

function attach(term: Term) {
  if (!alive.value) return
  term.on = true
  term.open = true
  term.redrawn = true
  said.value = `hmz in the same directory: the whole screen is drawn again, at round ${round.value}.`
}

function leave() {
  if (!alive.value || !watching.value) return
  letGo('detached')
  said.value = '/exit → leave it running: every terminal lets go, and the run carries on.'
}

function stop() {
  if (!alive.value || !watching.value) return
  run.value = 'stopped'
  letGo('the flow stopped')
  said.value = `/exit → stop it, then leave: the flow stopped at round ${round.value}.`
}

function restart() {
  if (!alive.value) return
  run.value = 'gone'
  letGo('connection closed')
  said.value = `The machine restarted and took the run with it. A flow that can be picked up carries on after round ${round.value}.`
}

function reset() {
  run.value = 'running'
  round.value = START
  for (const one of terms) {
    one.on = true
    one.open = true
    one.redrawn = false
    one.why = ''
  }
  said.value = 'Two terminals are watching one run.'
}

function cap(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

const root = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined

onMounted(() => {
  // Held still where motion is unwanted: the round is a number, and nothing said here needs
  // it to move.
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  observer = new IntersectionObserver((entries) => (idle = !entries[0].isIntersecting), {
    rootMargin: '120px',
  })
  if (root.value) observer.observe(root.value)
  timer = window.setInterval(tick, 1600)
})

onUnmounted(() => {
  window.clearInterval(timer)
  observer?.disconnect()
})

const runLabel = computed(() => {
  if (run.value === 'stopped') return `stopped at round ${round.value}`
  if (run.value === 'gone') return 'gone with the machine'
  return `round ${round.value}`
})
</script>

<template>
  <div ref="root" class="daemon hmz-panel">
    <div class="bar">
      <span class="title">one run, in one directory</span>
      <div class="spacer" />
      <span class="sim">simulation</span>
      <button class="ctl" type="button" @click="reset">start over</button>
    </div>

    <div class="body">
      <section class="run" :class="run" aria-label="the run">
        <header>
          <span class="pulse" />
          <strong>ralph_loop</strong>
          <span class="state">{{ runLabel }}</span>
        </header>
        <p class="watchers">
          <template v-if="!alive">nothing to watch</template>
          <template v-else-if="watching">
            {{ watching }} terminal{{ watching === 1 ? '' : 's' }} watching
          </template>
          <template v-else>nobody watching · still running</template>
        </p>
        <!-- /exit is typed at a terminal, so it needs one watching. -->
        <div class="actions">
          <button type="button" :disabled="!alive || !watching" @click="leave">
            /exit → leave it running
          </button>
          <button type="button" class="stop" :disabled="!alive || !watching" @click="stop">
            /exit → stop it, then leave
          </button>
          <button type="button" class="gone" :disabled="!alive" @click="restart">
            the machine restarts
          </button>
        </div>
      </section>

      <section class="terms" aria-label="terminals">
        <article v-for="term in terms" :key="term.id" class="term" :class="{ on: term.on }">
          <header>
            <strong>{{ term.name }}</strong>
            <span>{{ term.on ? 'watching' : term.open ? 'back at its shell' : 'closed' }}</span>
          </header>
          <div class="screen" :class="{ shell: !term.on, closed: !term.open }">
            <template v-if="term.on">
              <span class="hi">ralph_loop · round {{ round }}</span>
              <span>{{ round % 2 ? 'the agent is running the tests' : 'the agent is editing' }}</span>
              <span v-if="term.redrawn" class="note">drawn again from the top</span>
              <span v-else class="dim">❯</span>
            </template>
            <template v-else-if="term.open">
              <span>{{ term.why }}</span>
              <span class="dim">$</span>
            </template>
            <template v-else>
              <span class="dim">no window</span>
            </template>
          </div>
          <button v-if="term.on" type="button" @click="close(term)">close the window</button>
          <button v-else type="button" :disabled="!alive" @click="attach(term)">
            {{ term.open ? 'run hmz here' : 'open, run hmz' }}
          </button>
        </article>
      </section>
    </div>

    <p class="said" aria-live="polite">{{ said }}</p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.title {
  font-size: 12px;
  font-weight: 650;
  color: var(--vp-c-text-2);
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

button {
  padding: 5px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
}

button:disabled {
  opacity: 0.4;
  cursor: default;
}

.ctl {
  color: var(--vp-c-text-3);
  font-weight: 500;
}

.body {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 14px;
  padding: 14px 16px 0;
}

.run {
  align-self: start;
  padding: 12px 14px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 12px;
  background: var(--vp-c-bg);
  box-shadow: 0 0 0 3px var(--vp-c-brand-soft);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.run.stopped,
.run.gone {
  border-color: var(--vp-c-divider);
  box-shadow: none;
}

.run.gone {
  border-style: dashed;
}

.run header {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}

.pulse {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--hmz-accent);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--hmz-accent) 16%, transparent);
}

.stopped .pulse,
.gone .pulse {
  background: var(--vp-c-text-3);
  box-shadow: none;
}

.run strong {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  color: var(--vp-c-text-1);
}

.state {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  color: var(--hmz-accent);
}

.stopped .state,
.gone .state {
  color: var(--hmz-warm);
}

.watchers {
  margin: 8px 0 12px;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 7px;
}

.actions button {
  font-family: var(--vp-font-family-mono);
  font-weight: 500;
  border-color: var(--hmz-accent);
  color: var(--hmz-accent);
}

.actions .stop,
.actions .gone {
  border-color: var(--hmz-warm);
  color: var(--hmz-warm);
}

.actions .gone {
  font-family: inherit;
  border-style: dashed;
}

.terms {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.term {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  transition: border-color 0.2s;
}

.term.on {
  border-style: solid;
  border-color: color-mix(in srgb, var(--hmz-accent) 65%, var(--vp-c-divider));
}

.term header {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.term header strong {
  font-size: 12px;
  color: var(--vp-c-text-1);
}

.term header span {
  font-size: 10.5px;
  color: var(--vp-c-text-3);
}

.term.on header span {
  color: var(--hmz-accent);
}

/* A terminal is dark in either theme, which is what makes it read as one. */
.screen {
  min-height: 84px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #17202c;
  color: #c5daea;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  line-height: 1.6;
}

.screen span {
  display: block;
}

.screen .hi {
  color: #75dacd;
}

.screen .note {
  color: #e8a66f;
}

.screen .dim {
  color: #7d8fa3;
}

.screen.shell {
  color: #9fb3c8;
}

.screen.closed {
  border: 1px dashed var(--vp-c-divider);
  background: transparent;
}

.screen.closed .dim {
  color: var(--vp-c-text-3);
}

.term button {
  align-self: flex-start;
}

.term.on button {
  border-color: var(--hmz-warm);
  color: var(--hmz-warm);
}

.term:not(.on) button:not(:disabled) {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.said {
  margin: 0;
  padding: 12px 16px 16px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

@media (max-width: 760px) {
  .body {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 480px) {
  .terms {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .run,
  .term {
    transition: none;
  }
}
</style>
