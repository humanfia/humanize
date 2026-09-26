<script setup lang="ts">
// A line typed while a turn is running, shown on two kinds of backend at once. On the left,
// the ones whose sessions set `steers` (Claude Code, Codex, Kimi Code and pi,
// `src/hmz/coganchor/agents/`): the line goes into the turn already running. On the right,
// every other backend: `interject` refuses, the interface says so, and the line waits for the
// next turn to start (`_hand_over`, `_unreached` and `_at_turn_start` in `src/hmz/tui/app.py`).
// Either way lines leave the queue one at a time and stay pinned until the agent has one.
import { computed, onMounted, onUnmounted, ref } from 'vue'

interface Line {
  id: number
  text: string
  state: 'held' | 'pinned' | 'taken'
  at: number
  late: boolean
}

interface Said {
  id: number
  text: string
  kind: 'tool' | 'you' | 'say' | 'edge' | 'warn'
}

const STEPS: { at: number; text: string; kind: 'tool' | 'say' }[] = [
  { at: 0.06, text: 'Read src/pay.py', kind: 'tool' },
  { at: 0.24, text: 'Grep "def charge"', kind: 'tool' },
  { at: 0.42, text: 'Edit src/pay.py', kind: 'tool' },
  { at: 0.62, text: 'Bash pytest -q', kind: 'tool' },
  { at: 0.88, text: 'the retry path was the one', kind: 'say' },
]

const SUGGESTED = ['actually, use pathlib', 'and fix the tests too', 'leave the CLI alone']

const TURN = 11 // seconds a turn takes here
const GAP = 2.6 // and the pause before the next one starts

const clock = ref(0)
const typed = ref('')
const lines = ref<Line[]>([])
const into = ref<Said[]>([])
const after = ref<Said[]>([])
const running = ref(true)

let frame = 0
let last = 0
let idle = false
let counter = 0
let round = 0
let step = 0

const progress = computed(() => Math.min(1, clock.value / TURN))
const open = computed(() => clock.value < TURN)

function say(where: 'into' | 'after', text: string, kind: Said['kind']) {
  const said = { id: (counter += 1), text, kind }
  const list = where === 'into' ? into : after
  list.value = [...list.value.slice(-7), said]
}

function submit() {
  const text = typed.value.trim()
  if (!text) return
  typed.value = ''
  hand(text)
}

function hand(text: string) {
  // Handed to the agent only when nothing typed before it is still waiting: one at a time.
  const free = open.value && lines.value.every((one) => one.state === 'taken')
  lines.value = [
    ...lines.value,
    { id: (counter += 1), text, state: free ? 'pinned' : 'held', at: clock.value, late: false },
  ]
  if (open.value) say('after', 'cannot be talked to mid-turn: held for the next turn', 'warn')
}

function tick(now: number) {
  frame = requestAnimationFrame(tick)
  const dt = Math.min((now - last) / 1000, 0.1)
  last = now
  if (!running.value || idle) return
  clock.value += dt

  // The agent works the same on both sides. What differs is when your line reaches it.
  while (step < STEPS.length && progress.value >= STEPS[step].at) {
    say('into', STEPS[step].text, STEPS[step].kind)
    say('after', STEPS[step].text, STEPS[step].kind)
    step += 1
  }

  // One line at a time: the next goes only once the agent has said it has this one.
  const waiting = lines.value.find((one) => one.state !== 'taken')
  if (waiting && open.value) {
    if (waiting.state === 'held') {
      waiting.state = 'pinned'
      waiting.at = clock.value
    } else if (clock.value - waiting.at > 0.9) {
      waiting.state = 'taken'
      say('into', waiting.text, 'you')
      say('into', 'takes it into the turn it is running', 'edge')
    }
  }

  if (clock.value >= TURN + GAP) {
    // The next turn starts, and takes what was waiting for it on the right.
    const due = lines.value.filter((one) => !one.late)
    round += 1
    if (round % 2 === 0) {
      into.value = []
      after.value = []
    }
    for (const one of due) {
      one.late = true
      say('after', one.text, 'you')
      say('after', `goes into the next turn, ${Math.max(1, Math.round(TURN + GAP - one.at))}s later`, 'edge')
    }
    lines.value = lines.value.filter((one) => !(one.late && one.state === 'taken'))
    clock.value = 0
    step = 0
  }
}

const root = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    // Held still at a moment worth reading: a line typed mid-turn, taken on one side and
    // held on the other.
    running.value = false
    clock.value = TURN * 0.5
    for (const one of STEPS.slice(0, 3)) {
      say('into', one.text, one.kind)
      say('after', one.text, one.kind)
    }
    lines.value = [{ id: (counter += 1), text: SUGGESTED[0], state: 'taken', at: clock.value, late: false }]
    say('into', SUGGESTED[0], 'you')
    say('into', 'takes it into the turn it is running', 'edge')
    say('after', 'cannot be talked to mid-turn: held for the next turn', 'warn')
    return
  }
  observer = new IntersectionObserver((entries) => (idle = !entries[0].isIntersecting), {
    rootMargin: '120px',
  })
  if (root.value) observer.observe(root.value)
  last = performance.now()
  frame = requestAnimationFrame(tick)
})

onUnmounted(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
})

const pinned = computed(() => lines.value.filter((one) => one.state !== 'taken'))
const heldRight = computed(() => lines.value.filter((one) => !one.late))
</script>

<template>
  <div ref="root" class="steer hmz-panel">
    <div class="bar">
      <span class="live" :class="{ paused: !open || !running }">
        <i />
        {{ running ? (open ? 'a turn is running' : 'between turns') : 'paused' }}
      </span>
      <div class="track">
        <span class="fill" :style="{ width: `${progress * 100}%` }" />
      </div>
      <span class="sim">simulation</span>
      <button
        class="toggle"
        type="button"
        :aria-label="running ? 'pause' : 'play'"
        @click="running = !running"
      >
        {{ running ? '❙❙' : '▶' }}
      </button>
    </div>

    <div class="lanes">
      <section class="lane">
        <header>
          <strong>into the running turn</strong>
          <span>Claude Code · Codex · Kimi Code · pi</span>
        </header>
        <ul>
          <li v-for="one in into" :key="one.id" :class="one.kind">
            <span class="mark">{{ one.kind === 'you' ? '❯' : one.kind === 'edge' ? '↳' : '▸' }}</span>
            {{ one.text }}
          </li>
        </ul>
      </section>

      <section class="lane plain">
        <header>
          <strong>held for the next turn</strong>
          <span>every other backend</span>
        </header>
        <ul>
          <li v-for="one in after" :key="one.id" :class="one.kind">
            <span class="mark">{{
              one.kind === 'you' ? '❯' : one.kind === 'edge' ? '↳' : one.kind === 'warn' ? '!' : '▸'
            }}</span>
            {{ one.text }}
          </li>
        </ul>
        <p v-if="heldRight.length" class="waiting">
          <span v-for="one in heldRight" :key="one.id">❯ {{ one.text }}</span>
        </p>
      </section>
    </div>

    <div class="editor">
      <div class="pins" aria-live="polite">
        <p v-for="one in pinned" :key="one.id" class="pin" :class="one.state">
          <span>❯</span> {{ one.text }}
          <em v-if="one.state === 'pinned'">· with claude#3a15</em>
          <em v-else>· waiting for a turn</em>
        </p>
      </div>
      <form @submit.prevent="submit">
        <span class="caret">❯</span>
        <input
          v-model="typed"
          type="text"
          placeholder="type to the turn that is running…"
          aria-label="a line typed mid-turn"
        />
        <button type="submit">enter</button>
      </form>
      <div class="chips">
        <button v-for="one in SUGGESTED" :key="one" type="button" @click="hand(one)">
          {{ one }}
        </button>
      </div>
    </div>

    <p class="note">
      No mode and no special key: type while the agent works. Lines go one at a time, and each
      stays pinned above the prompt until the agent says it has it.
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
}

.live {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--vp-c-text-2);
  font-weight: 600;
  white-space: nowrap;
}

.live i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--hmz-accent);
}

.live.paused i {
  background: var(--vp-c-text-3);
}

.track {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--vp-c-default-soft);
  overflow: hidden;
}

.fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--vp-c-brand-1), var(--hmz-accent));
}

.sim {
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.toggle {
  min-width: 34px;
  padding: 3px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: transparent;
  color: var(--vp-c-text-2);
  cursor: pointer;
  font-size: 12px;
}

.lanes {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 14px 16px 0;
}

.lane {
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  overflow: hidden;
}

.lane header {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
}

.lane header strong {
  font-size: 12.5px;
  color: var(--vp-c-brand-1);
}

.lane.plain header strong {
  color: var(--hmz-warm);
}

.lane header span {
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.lane ul {
  list-style: none;
  margin: 0;
  padding: 10px 12px;
  min-height: 176px;
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  line-height: 1.8;
  color: var(--vp-c-text-2);
}

.lane li {
  display: flex;
  gap: 8px;
  margin: 0;
  animation: land 0.35s ease;
}

.lane li .mark {
  flex: none;
  color: var(--vp-c-text-3);
}

.lane li.you {
  color: var(--hmz-accent);
  font-weight: 600;
}

.lane li.edge {
  color: var(--vp-c-text-3);
  font-style: italic;
}

.lane li.warn {
  color: var(--hmz-warm);
}

.lane li.say {
  color: var(--vp-c-text-1);
}

@keyframes land {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}

.waiting {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 8px 12px 10px;
  border-top: 1px dashed var(--vp-c-divider);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  color: var(--hmz-warm);
}

.editor {
  padding: 14px 16px 0;
}

.pins {
  min-height: 22px;
}

.pin {
  margin: 0 0 4px;
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  color: var(--vp-c-text-3);
}

.pin span {
  color: var(--vp-c-brand-1);
}

.pin.taken {
  color: var(--hmz-accent);
}

.pin em {
  font-style: normal;
  opacity: 0.75;
}

form {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
}

.caret {
  color: var(--vp-c-brand-1);
  font-family: var(--vp-font-family-mono);
}

form input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--vp-c-text-1);
  font-size: 13px;
  outline: none;
}

form button {
  padding: 3px 12px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 11px;
  font-weight: 650;
  cursor: pointer;
}

.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 0 0;
}

.chips button {
  padding: 4px 11px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 11.5px;
  cursor: pointer;
}

.chips button:hover {
  border-style: solid;
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}

.note {
  margin: 0;
  padding: 14px 16px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

@media (max-width: 720px) {
  .lanes {
    grid-template-columns: minmax(0, 1fr);
  }

  .lane ul {
    min-height: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .lane li {
    animation: none;
  }
}
</style>
