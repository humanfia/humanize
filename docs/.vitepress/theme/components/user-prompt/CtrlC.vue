<script setup lang="ts">
// What the next ctrl+c does, played. The ladder, the three-second window, the lines the
// interface prints and the keys its status line offers are the ones `action_interrupt`,
// `action_stop` and `_keys` in src/hmz/tui/app.py have. The flow itself is a simulation:
// nothing here runs, and the left of the status line is simplified.
//
// Beside the screen the same rules are drawn as a ladder: where you are on it, lit, and each
// rung the last key of the status line there. A press that climbs it lights the step it took;
// the window a first press opens drains, on the button and over the status line, and lets the
// marker slide back down when it runs out. Under reduced motion every change is instant and
// the window is shown open, not draining.
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import { motion } from '../../motion/gsap'

type Phase = 'idle' | 'running' | 'stopping' | 'closed'
type Kind = 'you' | 'agent' | 'note' | 'error'

interface Line {
  id: number
  text: string
  kind: Kind
}

const AGAIN = 3000 // ms: a second press later than this is a first press again (`_AGAIN`)
const TASK = 'fix the flaky test'
const HALF = 'and keep the old'

const phase = ref<Phase>('running')
const typed = ref('')
const presses = ref(0)
const lines = ref<Line[]>([])
const said = ref('')
let pressedAt = 0
let counter = 0
let window_: ReturnType<typeof setTimeout> | undefined

function put(text: string, kind: Kind) {
  lines.value = [...lines.value, { id: (counter += 1), text, kind }].slice(-6)
}

function begin() {
  lines.value = []
  put(`$ralph_loop ${TASK}`, 'you')
  put('coder  Read tests/test_pay.py', 'agent')
  put('coder  Bash pytest -q tests/test_pay.py', 'agent')
  phase.value = 'running'
}

function arm() {
  if (window_ !== undefined) clearTimeout(window_)
  // Where the interface forgets an unfinished gesture: the next redraw after the window.
  window_ = setTimeout(() => {
    presses.value = 0
    window_ = undefined
    said.value = 'Three seconds passed without another press, so the next one starts over.'
  }, AGAIN)
  drain()
}

function disarm() {
  presses.value = 0
  if (window_ !== undefined) clearTimeout(window_)
  window_ = undefined
}

function stopFlow() {
  put('— stopping the flow —', 'note')
  phase.value = 'stopping'
}

function press() {
  if (phase.value === 'closed') return
  tap()
  if (typed.value) {
    typed.value = ''
    disarm()
    said.value = 'Something was typed, so the press cleared the line and counts for nothing else.'
    return
  }
  const now = Date.now()
  presses.value = presses.value && now - pressedAt < AGAIN ? presses.value + 1 : 1
  pressedAt = now
  if (phase.value === 'running') {
    if (presses.value < 2) {
      arm()
      put('— press ctrl+c again to stop the flow —', 'note')
      said.value = 'Nothing has stopped yet. The next press, within 3 seconds, stops the flow.'
      return
    }
    disarm()
    stopFlow()
    said.value =
      'The flow is stopping: the turn is cut off and the flow winds down in its own time. ' +
      'One more press does not wait for it.'
    return
  }
  if (phase.value === 'stopping') {
    disarm()
    put('— closed 1 conversation(s) mid-turn —', 'note')
    phase.value = 'idle'
    said.value =
      'The third press closed the agent still in its turn. Nothing is running now; ' +
      '/resume works again.'
    return
  }
  if (presses.value > 1) {
    disarm()
    phase.value = 'closed'
    said.value = 'Nothing was running, so the second press quit hmz.'
    return
  }
  arm()
  put('— press ctrl+c again to exit —', 'note')
  said.value = 'Nothing is running, so the next press, within 3 seconds, quits hmz.'
}

function type() {
  typed.value = phase.value === 'running' ? HALF : TASK
  said.value = 'A half-typed line: the next ctrl+c clears it rather than anything else.'
}

function slashStop() {
  typed.value = ''
  put('/stop', 'you')
  if (phase.value === 'running') {
    stopFlow()
    said.value = '/stop is typed out on purpose, so it stops the flow at once.'
  } else if (phase.value === 'stopping') {
    put('hmz: the flow is already stopping: it is finishing the turn it was in', 'error')
    said.value = 'A second /stop does not hurry it. A ctrl+c does.'
  } else {
    put('hmz: no flow is running', 'error')
    said.value = '/stop says so when there is nothing to stop. It never quits.'
  }
  disarm()
}

function unwound() {
  phase.value = 'idle'
  said.value = 'The flow finished winding down by itself. Nothing is running.'
}

function start() {
  // Starting a flow leaves an unfinished ctrl+c standing, as the interface does: a press
  // within the window after this one is its second.
  typed.value = ''
  begin()
  said.value = 'A flow is running again.'
}

function reopen() {
  lines.value = []
  typed.value = ''
  disarm()
  phase.value = 'idle'
  said.value = 'hmz is open again, with nothing running.'
}

function reset() {
  typed.value = ''
  disarm()
  said.value = ''
  begin()
}

const counting = computed(() => presses.value > 0)

// The keys the status line offers, in the order `_keys` puts them.
const keys = computed(() => {
  const held: string[] = []
  if (typed.value) held.push(phase.value === 'running' ? 'enter send' : 'enter start')
  held.push('/ commands', 'shift+enter newline', '← monitor')
  if (typed.value) held.push('ctrl+c clear')
  else if (counting.value)
    held.push(phase.value === 'running' ? 'ctrl+c again to stop' : 'ctrl+c again to exit')
  else if (phase.value === 'running') held.push('ctrl+c stop')
  else if (phase.value === 'stopping') held.push('ctrl+c force stop')
  else held.push('ctrl+c exit')
  return held
})

const next = computed(() => keys.value[keys.value.length - 1])

const where = computed(() => {
  if (phase.value === 'running') return 'ralph_loop · coder working'
  if (phase.value === 'stopping') return 'ralph_loop · stopping'
  return 'ralph_loop · ~/code/app'
})

// ---- the ladder ------------------------------------------------------------------------------

// Each rung is a state, named with the last key the status line ends with there; each step
// up is what moves you to the next one.
const RUNGS = [
  { name: 'a flow running', key: 'ctrl+c stop' },
  { name: 'one press, waiting', key: 'ctrl+c again to stop' },
  { name: 'the flow stopping', key: 'ctrl+c force stop' },
  { name: 'nothing running', key: 'ctrl+c exit' },
  { name: 'one press, waiting', key: 'ctrl+c again to exit' },
  { name: 'hmz has quit', key: '$' },
]
const STEPS = ['ctrl+c', 'again within 3 s', 'once more, or it winds down', 'ctrl+c', 'again within 3 s']

const rung = computed(() => {
  if (phase.value === 'closed') return 5
  if (phase.value === 'stopping') return 2
  if (phase.value === 'running') return counting.value ? 1 : 0
  return counting.value ? 4 : 3
})

// What took you from one rung to another, said beside the step it lit.
const how = ref<{ at: number; text: string } | null>(null)

// ---- motion ----------------------------------------------------------------------------------

const root = ref<HTMLElement | null>(null)
const left = ref(AGAIN)
const still = ref(false)
let draining: gsap.core.Tween | undefined

function quiet() {
  return still.value || typeof window === 'undefined'
}

// The window a first press opens, drained on the bar over the status line and the ring round
// the button: the second press counts only while there is some left.
function drain() {
  draining?.kill()
  const ms = Math.max(0, AGAIN - (Date.now() - pressedAt))
  left.value = ms
  if (quiet()) return
  const clock = { ms }
  draining = motion().to(clock, {
    ms: 0,
    duration: ms / 1000,
    ease: 'none',
    onUpdate: () => {
      left.value = clock.ms
    },
  })
}

const share = computed(() => (counting.value ? left.value / AGAIN : 0))
const seconds = computed(() => (Math.ceil(left.value / 100) / 10).toFixed(1))

// The press itself: the key goes down, and a ring goes out from the status line's last key.
function tap() {
  if (quiet()) return
  const gsap = motion()
  const kbd = root.value?.querySelector('.press kbd')
  if (kbd) gsap.fromTo(kbd, { y: 2, scale: 0.94 }, { y: 0, scale: 1, duration: 0.4, ease: 'back.out(3)' })
  const pulse = root.value?.querySelector('.tap')
  if (pulse) gsap.fromTo(pulse, { scale: 0.6, autoAlpha: 0.9 }, { scale: 2.4, autoAlpha: 0, duration: 0.7, ease: 'power2.out' })
}

// The marker on the ladder glides to the rung you are on; the step taken, if one was, lights.
function climb(to: number, from: number) {
  const box = root.value?.querySelector<HTMLElement>('.ladder')
  const mark = box?.querySelector<HTMLElement>('.marker')
  const fill = box?.querySelector<HTMLElement>('.fill')
  const dot = box?.querySelectorAll<HTMLElement>('.rung .dot')[to]
  if (!box || !mark || !dot) return
  const y = (dot.parentElement?.offsetTop ?? 0) + dot.offsetTop + dot.offsetHeight / 2
  const gsap = motion()
  const d = quiet() ? 0 : 0.7
  gsap.to(mark, { y, duration: d, ease: 'cine' })
  if (fill) gsap.to(fill, { height: Math.max(0, y - 22), duration: d, ease: 'cine' })
  if (quiet() || from === to) return
  const rung = box.querySelectorAll<HTMLElement>('.rung')[to]
  if (rung) gsap.fromTo(rung, { x: -6 }, { x: 0, duration: 0.6, ease: 'back.out(2.4)' })
  if (to === from + 1) {
    const step = box.querySelectorAll<HTMLElement>('.step')[from]
    if (step) gsap.fromTo(step, { '--lit': 1 }, { '--lit': 0, duration: 1.6, ease: 'power2.in', delay: 0.2 })
  }
  const note = box.querySelector('.how')
  if (note) gsap.fromTo(note, { autoAlpha: 0, x: -8 }, { autoAlpha: 1, x: 0, duration: 0.45, delay: 0.25 })
}

watch(rung, async (to, from) => {
  // What moved you, when it was not the step drawn between the two rungs.
  if (to === from + 1 || to === from) how.value = null
  else if (from === 1 && to === 0) how.value = { at: 0, text: '3 s passed: back down' }
  else if (from === 4 && to === 3) how.value = { at: 3, text: '3 s passed: back down' }
  else if (to === 2 && from === 0) how.value = { at: 2, text: '/stop: straight here' }
  else if (to === 3 && from === 5) how.value = { at: 3, text: 'hmz run again' }
  else if (to <= 1 && from >= 3) how.value = { at: to, text: 'a flow started' }
  else if (to === 0) how.value = { at: 0, text: 'started over' }
  else how.value = null
  await nextTick()
  climb(to, from)
})

// What the last thing did, said under the controls, rises in each time it changes.
watch(said, async () => {
  await nextTick()
  const el = root.value?.querySelector('.said')
  if (el) slideIn(el, () => {})
})

watch(counting, (on) => {
  if (!on) draining?.kill()
})

// Lines printed into the transcript are typed on; status keys slide in.
function typeOn(el: Element, done: () => void) {
  if (quiet()) return done()
  const n = (el.textContent ?? '').length
  motion().fromTo(
    el,
    { clipPath: 'inset(0 100% 0 0)', y: 6 },
    {
      clipPath: 'inset(0 0% 0 0)',
      y: 0,
      duration: Math.min(0.9, 0.2 + n * 0.012),
      ease: `steps(${Math.max(6, n)})`,
      onComplete: () => {
        ;(el as HTMLElement).style.removeProperty('clip-path')
        done()
      },
    },
  )
}

function slideIn(el: Element, done: () => void) {
  if (quiet()) return done()
  motion().fromTo(el, { autoAlpha: 0, y: 9 }, { autoAlpha: 1, y: 0, duration: 0.45, onComplete: done })
}

// Quitting switches the screen off to a line, as an old monitor did; reopening switches it on.
function off(el: Element, done: () => void) {
  // Not straight away even when still: an out-in transition must not be done inside its hook.
  if (quiet()) return void setTimeout(done)
  motion()
    .timeline({ onComplete: done })
    .to(el, { scaleY: 0.015, scaleX: 1, filter: 'brightness(1.8)', duration: 0.32, ease: 'cine.in' })
    .to(el, { scaleX: 0, autoAlpha: 0, duration: 0.22, ease: 'cine.in' })
}

function on(el: Element, done: () => void) {
  if (quiet()) return done()
  motion()
    .timeline({ onComplete: done })
    .fromTo(el, { scaleX: 0, scaleY: 0.015, autoAlpha: 1 }, { scaleX: 1, duration: 0.25, ease: 'cine.out' })
    .to(el, { scaleY: 1, duration: 0.4, ease: 'cine.out', clearProps: 'transform,filter' })
}

let fit: ResizeObserver | undefined

begin()

onMounted(() => {
  still.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  void nextTick(() => climb(rung.value, rung.value))
  // The ladder's rungs move when its column changes width: keep the marker on its rung.
  const box = root.value?.querySelector('.ladder')
  if (box) {
    fit = new ResizeObserver(() => climb(rung.value, rung.value))
    fit.observe(box)
  }
})

onUnmounted(() => {
  if (window_ !== undefined) clearTimeout(window_)
  draining?.kill()
  fit?.disconnect()
})
</script>

<template>
  <figure ref="root" class="up-ctrlc">
    <figcaption>
      <span class="title">What the next <kbd>ctrl+c</kbd> does</span>
      <span class="tag">a simulation: nothing runs</span>
    </figcaption>

    <div class="stage">
      <div class="screen">
        <Transition mode="out-in" :css="false" @leave="off" @enter="on">
          <div v-if="phase !== 'closed'" key="tui" class="tui">
            <TransitionGroup tag="div" class="transcript" aria-live="polite" :css="false" @enter="typeOn">
              <div v-for="one in lines" :key="one.id" class="line" :class="one.kind">
                <span v-if="one.kind === 'you'" class="mark">❯</span>
                <span v-else-if="one.kind === 'agent'" class="mark dot">●</span>
                <span>{{ one.text }}</span>
              </div>
            </TransitionGroup>
            <div class="rule" />
            <div class="prompt">
              <span class="caret">❯</span> {{ typed }}<span class="cursor" />
            </div>
            <div class="rule window" :class="{ open: counting }">
              <span class="drain" :style="{ transform: `scaleX(${share})` }" />
              <span v-if="counting" class="left-s">{{ still ? 'press again within 3 s' : `${seconds} s to press again` }}</span>
            </div>
            <div class="status">
              <span class="left">
                <span class="dot" :class="phase">{{ phase === 'idle' ? '◉' : '·|·' }}</span>
                {{ where }}
              </span>
              <TransitionGroup tag="span" class="keys" :css="false" @enter="slideIn">
                <span v-for="(key, at) in keys" :key="key" class="key" :class="{ next: key === next }"
                  ><span v-if="at" class="sep"> · </span
                  ><span class="word">{{ key }}<span v-if="key === next" class="tap" aria-hidden="true" /></span
                ></span>
              </TransitionGroup>
            </div>
          </div>
          <div v-else key="shell" class="shell">
            <span class="d">$</span> <span class="cursor" />
            <span class="gone">hmz has quit</span>
          </div>
        </Transition>
      </div>

      <ol class="ladder" aria-label="What each ctrl+c leads to, from a running flow to hmz quitting">
        <span class="rail" aria-hidden="true" />
        <span class="fill" aria-hidden="true" />
        <span class="marker" aria-hidden="true" />
        <template v-for="(one, n) in RUNGS" :key="n">
          <li class="rung" :class="{ here: n === rung, past: n < rung }" :aria-current="n === rung ? 'step' : undefined">
            <span class="dot" aria-hidden="true" />
            <span class="name">{{ one.name }}</span>
            <span class="says">{{ one.key }}</span>
            <span v-if="how && how.at === n" class="how">{{ how.text }}</span>
          </li>
          <li v-if="n < STEPS.length" class="step" aria-hidden="true">
            <span class="up">↓</span> {{ STEPS[n] }}
          </li>
        </template>
      </ol>
    </div>

    <div class="controls">
      <button type="button" class="press" :disabled="phase === 'closed'" @click="press">
        <svg class="arc" viewBox="0 0 40 40" aria-hidden="true">
          <circle class="track" cx="20" cy="20" r="17" pathLength="1" />
          <circle
            class="left-arc"
            cx="20"
            cy="20"
            r="17"
            pathLength="1"
            :style="{ strokeDashoffset: 1 - share }"
          />
        </svg>
        <kbd>ctrl+c</kbd>
      </button>
      <button type="button" :disabled="phase === 'closed' || !!typed" @click="type">
        type something
      </button>
      <button type="button" :disabled="phase === 'closed'" @click="slashStop">send /stop</button>
      <button v-if="phase === 'stopping'" type="button" @click="unwound">
        let it finish winding down
      </button>
      <button v-if="phase === 'idle'" type="button" @click="start">start a flow</button>
      <button v-if="phase === 'closed'" type="button" @click="reopen">run hmz again</button>
      <button type="button" class="ghost" @click="reset">start over</button>
    </div>

    <p class="said" aria-live="polite">
      {{ said || 'A flow is running. Press ctrl+c and watch the last key on the status line.' }}
    </p>
  </figure>
</template>

<style scoped>
.up-ctrlc {
  container-type: inline-size;
  margin: 20px 0 28px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-code-block-bg);
  overflow: hidden;
  box-shadow: 0 16px 36px -28px color-mix(in srgb, var(--hmz-accent-2) 75%, transparent);
}

figcaption {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: linear-gradient(to bottom, var(--vp-c-bg-soft), transparent);
  font-size: 13px;
  color: var(--vp-c-text-2);
}

kbd {
  display: inline-block;
  padding: 0 0.4em;
  border: 1px solid var(--vp-c-divider);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--vp-c-bg-soft);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 1.6;
  color: var(--vp-c-text-1);
  white-space: nowrap;
}

figcaption kbd {
  font-size: 11px;
}

.tag {
  margin-left: auto;
  font-size: 12px;
  font-style: italic;
  color: var(--vp-c-text-3);
}

/* The screen and, beside it where there is room, the ladder. */
.stage {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
}

@container (min-width: 620px) {
  .stage {
    grid-template-columns: minmax(0, 1fr) 196px;
  }

  .ladder {
    border-top: 0;
    border-left: 1px solid var(--vp-c-divider);
  }
}

.screen {
  position: relative;
  overflow: hidden;
  padding: 12px 14px 8px;
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-1);
  min-height: 236px;
  background:
    radial-gradient(120% 80% at 50% -20%, color-mix(in srgb, var(--hmz-accent) 7%, transparent), transparent 62%),
    repeating-linear-gradient(to bottom, color-mix(in srgb, var(--vp-c-text-1) 3%, transparent) 0 1px, transparent 1px 3px);
}

.tui {
  display: flex;
  flex-direction: column;
  min-height: 216px;
  transform-origin: 50% 50%;
}

.transcript {
  flex: 1;
  min-height: 120px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.line {
  display: flex;
  gap: 8px;
  overflow-wrap: anywhere;
}

.line.you .mark {
  color: var(--vp-c-text-3);
}

.line.agent .mark {
  color: var(--hmz-accent);
}

.line.agent {
  color: var(--vp-c-text-2);
}

.line.note {
  color: var(--vp-c-text-3);
}

.line.error {
  color: var(--vp-c-danger-1);
}

.rule {
  height: 0;
  margin: 4px 0;
  border-top: 1px solid var(--vp-c-divider);
}

/* The rule under the editor doubles as the window: while it is open it fills and drains. */
.rule.window {
  position: relative;
  height: 1px;
  border-top: 0;
  background: var(--vp-c-divider);
  transition: height 0.2s;
}

.rule.window.open {
  height: 3px;
  margin-bottom: 18px;
  border-radius: 2px;
}

.drain {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--hmz-accent-2), var(--hmz-warm));
  box-shadow: 0 0 10px color-mix(in srgb, var(--hmz-accent-2) 60%, transparent);
  transform-origin: left;
}

.left-s {
  position: absolute;
  right: 0;
  top: 4px;
  font-family: var(--vp-font-family-base);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  line-height: 1.3;
  color: var(--hmz-accent-2);
}

.prompt {
  min-height: 1.6em;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.caret {
  color: var(--vp-c-text-3);
}

.cursor {
  display: inline-block;
  width: 0.6em;
  height: 1.1em;
  margin-left: 1px;
  vertical-align: text-bottom;
  background: var(--vp-c-text-2);
  animation: blink 1.1s steps(1) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.status {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 2px 16px;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.status .dot {
  color: var(--hmz-accent-2);
}

.status .dot.running,
.status .dot.stopping {
  animation: breathe 1.4s ease-in-out infinite;
}

@keyframes breathe {
  50% {
    opacity: 0.35;
  }
}

.status .dot.idle {
  color: var(--hmz-accent);
}

.keys {
  text-align: right;
}

.key,
.word {
  display: inline-block;
  white-space: pre;
}

.word {
  position: relative;
}

.keys .next {
  color: var(--hmz-accent-2);
  font-weight: 700;
}

/* The ring a press sends out from the key it pressed. */
.tap {
  position: absolute;
  inset: -3px -6px;
  border: 1.5px solid var(--hmz-accent-2);
  border-radius: 6px;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
}

.shell {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 216px;
  align-content: flex-start;
}

.shell .d {
  color: var(--vp-c-text-3);
}

.gone {
  margin-left: auto;
  font-family: var(--vp-font-family-base);
  font-size: 13px;
  font-style: italic;
  color: var(--vp-c-text-3);
}

/* ---- the ladder ---- */
.ladder {
  position: relative;
  margin: 0;
  padding: 12px 12px 12px 34px;
  border-top: 1px solid var(--vp-c-divider);
  list-style: none;
  background: color-mix(in srgb, var(--vp-c-bg-soft) 60%, transparent);
}

.rail,
.fill {
  position: absolute;
  left: 19px;
  width: 2px;
  border-radius: 1px;
}

.rail {
  top: 22px;
  bottom: 22px;
  background: var(--vp-c-divider);
}

.fill {
  top: 22px;
  height: 0;
  background: linear-gradient(to bottom, var(--hmz-accent), var(--hmz-accent-2));
}

.marker {
  position: absolute;
  top: 0;
  left: 13px;
  width: 14px;
  height: 14px;
  margin-top: -7px;
  border: 2px solid var(--hmz-accent-2);
  border-radius: 50%;
  background: var(--vp-code-block-bg);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--hmz-accent-2) 22%, transparent);
  animation: halo 2.2s ease-in-out infinite;
  z-index: 1;
}

@keyframes halo {
  50% {
    box-shadow: 0 0 0 7px color-mix(in srgb, var(--hmz-accent-2) 8%, transparent);
  }
}

.ladder li {
  margin: 0;
  padding: 0;
  list-style: none;
}

.rung {
  position: relative;
  display: grid;
  line-height: 1.35;
  transition: opacity 0.3s;
}

.rung .dot {
  position: absolute;
  left: -18px;
  top: 6px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--vp-c-divider);
}

.rung.past .dot {
  background: var(--hmz-accent);
}

.rung .name {
  font-size: 12.5px;
  color: var(--vp-c-text-2);
}

.rung.here .name {
  color: var(--vp-c-text-1);
  font-weight: 600;
}

.says {
  justify-self: start;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.rung.here .says {
  color: var(--hmz-accent-2);
  font-weight: 700;
}

.how {
  justify-self: start;
  margin-top: 2px;
  padding: 0 6px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--hmz-warm) 18%, transparent);
  font-size: 11px;
  color: var(--vp-c-text-1);
}

.step {
  --lit: 0;
  position: relative;
  isolation: isolate;
  margin: 3px 0 5px !important;
  font-size: 11px;
  line-height: 1.5;
  color: color-mix(in srgb, var(--hmz-accent-2) calc(var(--lit) * 100%), var(--vp-c-text-3));
}

.step::before {
  content: '';
  position: absolute;
  inset: -1px -6px;
  z-index: -1;
  border-radius: 6px;
  background: var(--hmz-accent-2);
  opacity: calc(var(--lit) * 0.16);
}

.up {
  display: inline-block;
  width: 1em;
  color: inherit;
}

/* ---- the controls ---- */
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
}

button {
  padding: 4px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 6px;
  background: var(--vp-c-bg);
  font-size: 13px;
  color: var(--vp-c-text-1);
  cursor: pointer;
}

button:hover:not(:disabled) {
  border-color: var(--hmz-accent-2);
}

button:disabled {
  opacity: 0.45;
  cursor: default;
}

button.press {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding-left: 6px;
  border-color: var(--hmz-accent-2);
}

button.press kbd {
  font-size: 12px;
}

/* The window on the button: a ring that drains as the three seconds go. */
.arc {
  width: 20px;
  height: 20px;
  transform: rotate(-90deg);
}

.arc circle {
  fill: none;
  stroke-width: 4;
}

.arc .track {
  stroke: var(--vp-c-divider);
}

.arc .left-arc {
  stroke: var(--hmz-accent-2);
  stroke-dasharray: 1;
  stroke-linecap: round;
}

button.ghost {
  margin-left: auto;
  border-color: transparent;
  background: none;
  color: var(--vp-c-text-2);
}

.said {
  margin: 0;
  padding: 10px 14px 12px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--vp-c-text-2);
  border-top: 1px solid var(--vp-c-divider);
}

@media (prefers-reduced-motion: reduce) {
  .cursor,
  .status .dot.running,
  .status .dot.stopping,
  .marker {
    animation: none;
  }

  .rule.window,
  .rung {
    transition: none;
  }
}

@media (max-width: 640px) {
  .screen {
    font-size: 12px;
  }

  .status {
    font-size: 11px;
  }

  .keys {
    text-align: left;
  }
}
</style>
