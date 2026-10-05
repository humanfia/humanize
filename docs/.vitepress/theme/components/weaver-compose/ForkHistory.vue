<script setup lang="ts">
// Which conversations know which turns once a session is forked. A simulation of the rules
// `agent.fork(session)` keeps (src/hmz/runtime/flowing/harnesses.py and
// src/hmz/coganchor/agents/base.py): a fork is cut at its own first turn and carries every
// turn its parent had by then; that first turn raises SessionError if the parent has taken a
// turn since the fork was asked for; and a session that has taken no turn has nothing to fork.
// Where a turn works is the `env` of its own `run`, so a fork is only ever a history.
//
// Drawn as a graph: time runs left to right, one rail per session, a turn a bead on its rail.
// A fork leaves its parent's rail where it was asked for, dashed until its first turn; at each
// turn a light runs back along everything it was taken on top of, so what a session knows is
// the path from the first bead to its own rail. Nothing here runs anything.
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'

import { motion } from '../../motion/gsap'

interface Turn {
  n: number
  by: number
}

interface Lane {
  name: string
  parent: number | null
  /** How many turns of its own the parent had when the fork was asked for. */
  at: number
  /** How many turns the whole run had then: where the fork leaves its parent's rail. */
  asked: number
  cut: boolean
  carried: Turn[]
  own: Turn[]
  refused: boolean
}

const NAMES = ['session', 'careful', 'quick', 'third', 'fourth']
const MOST = NAMES.length
/** Enough to tell the story, and few enough that a phone still has room for every bead. */
const TURNS = 8

function start(): Lane[] {
  return [
    {
      name: NAMES[0],
      parent: null,
      at: 0,
      asked: 0,
      cut: true,
      carried: [],
      own: [{ n: 1, by: 0 }],
      refused: false,
    },
  ]
}

const lanes = ref<Lane[]>(start())
const turns = ref(1)
const said = ref({
  text: 'session has taken one turn. Fork it, then take turns on either side.',
  error: false,
})

const full = computed(() => lanes.value.length >= MOST)
const spent = computed(() => turns.value >= TURNS)

function tell(text: string, error = false) {
  said.value = { text, error }
}

function knows(lane: Lane): string {
  const all = [...lane.carried, ...lane.own].map((one) => one.n)
  return all.length ? all.join(', ') : 'nothing yet'
}

function fork(i: number) {
  const parent = lanes.value[i]
  if (!parent.cut) {
    const from = parent.parent === null ? '' : lanes.value[parent.parent].name
    tell(
      `SessionError: the session to fork has taken no turn to carry on from. ` +
        (stale(parent)
          ? `Fork ${from} again instead.`
          : `Take ${parent.name}'s first turn, then fork it.`),
      true,
    )
    return
  }
  if (full.value) return
  const name = NAMES[lanes.value.length]
  lanes.value.push({
    name,
    parent: i,
    at: parent.own.length,
    asked: turns.value,
    cut: false,
    carried: [],
    own: [],
    refused: false,
  })
  tell(
    `${name} = await agent.fork(${parent.name}). Nothing is carried yet: ${name} is cut at its ` +
      `own first turn, and takes everything ${parent.name} knows at that moment.`,
  )
}

function run(i: number) {
  if (spent.value) return
  const lane = lanes.value[i]
  if (lane.parent !== null && !lane.cut) {
    const parent = lanes.value[lane.parent]
    if (parent.own.length !== lane.at) {
      lane.refused = true
      tell(
        `SessionError: the conversation this one was forked from has taken a turn since; ` +
          `fork it again to branch from where it is now.`,
        true,
      )
      return
    }
    lane.cut = true
    lane.carried = [...parent.carried, ...parent.own]
  }
  turns.value += 1
  lane.own.push({ n: turns.value, by: i })
  const others = lanes.value.filter((one, j) => j !== i && one.cut).map((one) => one.name)
  const left = lanes.value
    .filter((one) => one.parent === i && !one.cut && !one.refused && one.at === lane.own.length - 1)
    .map((one) => one.name)
  tell(
    `Turn ${turns.value} ran on ${lane.name}, which now knows turns ${knows(lane)}.` +
      (others.length ? ` ${listed(others)} never ${others.length === 1 ? 'sees' : 'see'} it.` : '') +
      (left.length
        ? ` ${listed(left)} ${left.length === 1 ? 'has' : 'have'} not taken ` +
          `${left.length === 1 ? 'its' : 'their'} first turn yet, so ` +
          `${left.length === 1 ? 'that turn' : 'those turns'} will be refused.`
        : '') +
      (spent.value ? ' That is as many turns as fit here: reset to start again.' : ''),
  )
  // The light runs back along everything this turn was taken on top of.
  const n = turns.value
  void nextTick(() => travel(i, n))
}

function listed(names: string[]): string {
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

function reset() {
  lanes.value = start()
  turns.value = 1
  tell('session has taken one turn. Fork it, then take turns on either side.')
}

function stale(lane: Lane): boolean {
  if (lane.parent === null || lane.cut) return false
  return lane.refused || lanes.value[lane.parent].own.length !== lane.at
}

function waiting(lane: Lane): string {
  if (lane.parent === null || lane.cut) return ''
  const parent = lanes.value[lane.parent]
  if (stale(lane)) {
    return `${parent.name} has moved on: this first turn is refused. Fork again.`
  }
  return `waiting for its first turn, which carries what ${parent.name} knows then`
}

function tone(by: number): string {
  return `var(--hmz-lane-${(by % 6) + 1})`
}

// ---- the graph ------------------------------------------------------------------------------

// The graph is drawn one unit to the pixel, so a bead is round at any width: its width is
// measured, and the server draws it at a width that fits a phone.
const graph = ref<HTMLElement | null>(null)
const width = ref(360)
let sized: ResizeObserver | undefined
onMounted(() => {
  const el = graph.value
  if (!el) return
  const measure = () => (width.value = Math.max(280, Math.round(el.clientWidth)))
  measure()
  sized = new ResizeObserver(measure)
  sized.observe(el)
})
onUnmounted(() => sized?.disconnect())

const ROW = 46
const TOP = 26
const R = computed(() => (width.value < 420 ? 8 : 9))
const GUTTER = computed(() => (width.value < 420 ? 84 : 112))
const height = computed(() => TOP + (lanes.value.length - 1) * ROW + 30)
const step = computed(() => Math.min(64, (width.value - GUTTER.value - 18) / (TURNS + 0.5)))

const yOf = (i: number) => TOP + i * ROW
/** Where turn n sits on the time axis. */
const xOf = (n: number) => GUTTER.value + (n - 0.5) * step.value

/** Where a fork leaves its parent's rail: just after the last turn there was when it was asked,
 *  and a little further for each fork of the same session asked for at the same moment. */
function forkX(lane: Lane): number {
  const twins = lanes.value.filter((one) => one.parent === lane.parent && one.asked === lane.asked)
  return xOf(lane.asked) + step.value * 0.5 + twins.indexOf(lane) * 5
}

function railStart(lane: Lane): number {
  return lane.parent === null ? GUTTER.value - 12 : forkX(lane) + 10
}

function link(lane: Lane): string {
  if (lane.parent === null) return ''
  const f = forkX(lane)
  const yp = yOf(lane.parent)
  const yc = yOf(lanes.value.indexOf(lane))
  return `M${f - 2} ${yp} C${f + 6} ${yp} ${f + 2} ${yc} ${f + 10} ${yc}`
}

/** The way back from a turn to the first bead: through every rail and fork it was cut from. */
function lineage(i: number, n: number): string {
  const chain: number[] = []
  for (let at: number | null = i; at !== null; at = lanes.value[at].parent) chain.unshift(at)
  const root = lanes.value[chain[0]]
  let d = `M${railStart(root)} ${yOf(chain[0])}`
  for (let k = 1; k < chain.length; k += 1) {
    const child = lanes.value[chain[k]]
    const f = forkX(child)
    d += ` L${f - 2} ${yOf(chain[k - 1])} C${f + 6} ${yOf(chain[k - 1])} ${f + 2} ${yOf(chain[k])} ${f + 10} ${yOf(chain[k])}`
  }
  return `${d} L${xOf(n)} ${yOf(i)}`
}

const pulse = ref<SVGCircleElement | null>(null)
const trace = ref<SVGPathElement | null>(null)

function travel(i: number, n: number) {
  const dot = pulse.value
  const path = trace.value
  if (!dot || !path || !graph.value || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const gsap = motion()
  path.setAttribute('d', lineage(i, n))
  const color = getComputedStyle(graph.value).getPropertyValue(`--hmz-lane-${(i % 6) + 1}`).trim()
  dot.style.fill = color
  path.style.stroke = color
  gsap.killTweensOf([dot, path])
  gsap.set(path, { opacity: 0.9, drawSVG: '0% 0%' })
  gsap.to(path, { drawSVG: '0% 100%', duration: 0.9, ease: 'cine' })
  gsap.to(path, { opacity: 0, duration: 0.6, delay: 0.9, ease: 'power1.in' })
  gsap.fromTo(dot, { opacity: 1 }, { duration: 0.9, ease: 'cine', motionPath: { path, align: path, alignOrigin: [0.5, 0.5] } })
  gsap.to(dot, { opacity: 0, duration: 0.3, delay: 0.9 })
}
</script>

<template>
  <div class="forks hmz-panel">
    <div class="bar">
      <span class="label">Simulation: no CLI is run, the rules are the ones <code>fork</code> keeps</span>
      <button type="button" class="reset" @click="reset">reset</button>
    </div>

    <div ref="graph" class="graph">
      <svg :viewBox="`0 0 ${width} ${height}`" :height="height" aria-hidden="true">
        <line class="axis" :x1="GUTTER - 12" :x2="width - 8" :y1="height - 8" :y2="height - 8" />
        <text class="axis-word" :x="width - 8" :y="height - 14" text-anchor="end">time →</text>
        <g v-for="(lane, i) in lanes" :key="lane.name" class="lane" :class="{ refused: lane.refused, pending: !lane.cut }" :style="{ '--tone': tone(i) }">
          <text class="name" x="10" :y="yOf(i) + 4">{{ lane.name }}</text>
          <text v-if="lane.parent !== null" class="from" x="10" :y="yOf(i) + 18">fork of {{ lanes[lane.parent].name }}</text>
          <path v-if="lane.parent !== null" class="link" :d="link(lane)" :pathLength="lane.cut ? 1 : undefined" />
          <line class="rail" :x1="railStart(lane)" :x2="width - 10" :y1="yOf(i)" :y2="yOf(i)" :pathLength="lane.cut ? 1 : undefined" />
          <circle v-if="lane.parent !== null" class="joint" :cx="forkX(lane) - 2" :cy="yOf(lane.parent)" r="3" :style="{ '--tone': tone(lane.parent) }" />
          <g v-if="lane.refused" class="cross" :transform="`translate(${forkX(lane) + 18} ${yOf(i)})`">
            <path d="M-5 -5 L5 5 M5 -5 L-5 5" />
          </g>
          <g v-for="one in lane.own" :key="one.n" class="bead" :style="{ transform: `translate(${xOf(one.n)}px, ${yOf(i)}px)` }">
            <circle class="ripple" :r="R" />
            <circle class="core" :r="R" />
            <text y="3.8" text-anchor="middle">{{ one.n }}</text>
          </g>
        </g>
        <path ref="trace" class="trace" d="M0 0" />
        <circle ref="pulse" class="pulse" r="5" cx="0" cy="0" />
      </svg>
    </div>

    <ol class="lanes">
      <li
        v-for="(lane, i) in lanes"
        :key="lane.name"
        class="lane-row"
        :class="{ refused: lane.refused }"
        :style="{ '--tone': tone(i) }"
      >
        <div class="who">
          <b>{{ lane.name }}</b>
          <span class="knows" :aria-label="`${lane.name} knows turns ${knows(lane)}`">
            <template v-if="waiting(lane)"><span class="waiting" :class="{ bad: stale(lane) }">{{ waiting(lane) }}</span></template>
            <template v-else>knows
              <span v-for="one in lane.carried" :key="`c${one.n}`" class="chip carried" :style="{ '--tone': tone(one.by) }" :title="`turn ${one.n}, carried from ${lanes[one.by].name}`">{{ one.n }}</span>
              <span v-for="one in lane.own" :key="`o${one.n}`" class="chip" :style="{ '--tone': tone(one.by) }" :title="`turn ${one.n}, taken on ${lane.name}`">{{ one.n }}</span>
            </template>
          </span>
        </div>
        <div class="acts">
          <button type="button" :disabled="spent" @click="run(i)">run a turn</button>
          <button type="button" :disabled="full" @click="fork(i)">fork</button>
        </div>
      </li>
    </ol>

    <!-- The live region stays put and only what is in it changes, so every message is read out. -->
    <div class="said-at" aria-live="polite">
      <Transition name="said" mode="out-in">
        <p :key="said.text" class="said" :class="{ error: said.error }">{{ said.text }}</p>
      </Transition>
    </div>

    <p class="key">
      <span class="chip sample" :style="{ '--tone': tone(1) }">3</span> a turn taken on this
      session ·
      <span class="chip carried sample" :style="{ '--tone': tone(0) }">1</span> a turn carried
      from the session it was forked from · a dashed fork has not taken its first turn
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.label {
  flex: 1;
  min-width: 0;
}

.label code {
  font-size: 11.5px;
}

button {
  padding: 3px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-2);
  font-size: 12px;
  line-height: 1.5;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.2s, color 0.2s, transform 0.15s;
}

button:hover:not(:disabled) {
  border-color: var(--tone, var(--vp-c-brand-1));
  color: var(--tone, var(--vp-c-brand-1));
}

button:active:not(:disabled) {
  transform: scale(0.96);
}

button:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ---- the graph ---- */

.graph {
  position: relative;
  padding: 8px 0 2px;
  background: var(--hmz-stage-bg);
  border-bottom: 1px solid var(--hmz-panel-border);
}

.graph svg {
  display: block;
  width: 100%;
  font-family: var(--vp-font-family-mono);
  overflow: visible;
}

.axis {
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 2 4;
}

.axis-word {
  font-family: var(--vp-font-family-base);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.name {
  font-size: 12.5px;
  font-weight: 700;
  fill: var(--tone);
}

.refused .name {
  text-decoration: line-through;
  fill: var(--hmz-stage-dim);
}

.from {
  font-family: var(--vp-font-family-base);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.rail {
  stroke: var(--tone);
  stroke-width: 2;
  stroke-opacity: 0.5;
  stroke-dasharray: 1;
  stroke-dashoffset: 0;
  animation: draw 0.7s cubic-bezier(0.16, 1, 0.3, 1) both;
}

.link {
  fill: none;
  stroke: var(--tone);
  stroke-width: 2;
  stroke-dasharray: 1;
  animation: draw 0.6s cubic-bezier(0.7, 0, 0.2, 1) both;
}

/* Until its first turn a fork is only asked for: its rail and its link are dashed, and the
   dashes march, the way a thing that has not happened yet waits. (Measured in pixels: only a
   cut rail is given a length of 1 to be drawn on with.) */
.pending .rail,
.pending .link {
  stroke-dasharray: 5 5;
  animation: draw-dashed 0.6s ease-out both, march 1.2s linear infinite;
}

.refused .rail,
.refused .link {
  stroke: var(--vp-c-danger-1);
  stroke-opacity: 0.8;
  animation: none;
}

.joint {
  fill: var(--hmz-stage-card);
  stroke: var(--tone);
  stroke-width: 2;
}

.cross path {
  stroke: var(--vp-c-danger-1);
  stroke-width: 2.4;
  stroke-linecap: round;
  animation: pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

.bead {
  transition: transform 0.55s cubic-bezier(0.7, 0, 0.2, 1);
}

.bead .core {
  fill: var(--tone);
  animation: pop 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  transform-box: fill-box;
  transform-origin: center;
}

.bead text {
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-bg);
  animation: fade 0.4s 0.15s both;
}

.bead .ripple {
  fill: none;
  stroke: var(--tone);
  stroke-width: 2;
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
  animation: ripple 0.9s ease-out;
}

.trace {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
  opacity: 0;
  pointer-events: none;
}

.pulse {
  opacity: 0;
  pointer-events: none;
}

/* ---- the controls ---- */

.lanes {
  list-style: none;
  margin: 0;
  padding: 4px 16px;
}

.lanes .lane-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  padding: 8px 0;
  border-bottom: 1px dashed var(--hmz-panel-border);
}

.lanes .lane-row:last-child {
  border-bottom: none;
}

.who {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  border-left: 3px solid var(--tone);
  padding-left: 8px;
}

.who b {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  color: var(--vp-c-text-1);
}

.refused .who b {
  text-decoration: line-through;
  color: var(--vp-c-text-3);
}

.knows {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 20px;
  padding: 0 4px;
  border: 1.5px solid var(--tone);
  border-radius: 6px;
  background: var(--tone);
  color: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  animation: pop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.chip.carried {
  background: transparent;
  color: var(--vp-c-text-2);
  border-style: dashed;
}

.chip.sample {
  animation: none;
  vertical-align: middle;
}

.waiting {
  font-size: 12px;
  font-style: italic;
  color: var(--vp-c-text-3);
}

.waiting.bad {
  font-style: normal;
  color: var(--vp-c-danger-1);
}

.acts {
  display: flex;
  flex: none;
  gap: 6px;
}

.said {
  margin: 0;
  padding: 12px 16px;
  border-top: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
  min-height: 3.2em;
}

.said.error {
  color: var(--vp-c-danger-1);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
}

.said-enter-active,
.said-leave-active {
  transition: opacity 0.18s, transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.said-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.said-leave-to {
  opacity: 0;
}

.key {
  margin: 0;
  padding: 8px 16px 12px;
  border-top: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 11.5px;
  line-height: 2;
  color: var(--vp-c-text-3);
}

@keyframes pop {
  from {
    transform: scale(0.4);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes fade {
  from {
    opacity: 0;
  }
}

@keyframes ripple {
  from {
    opacity: 0.8;
    transform: scale(1);
  }
  to {
    opacity: 0;
    transform: scale(2.4);
  }
}

@keyframes draw {
  from {
    stroke-dashoffset: 1;
  }
}

@keyframes draw-dashed {
  from {
    opacity: 0;
  }
}

@keyframes march {
  to {
    stroke-dashoffset: -10;
  }
}

@media (prefers-reduced-motion: reduce) {
  .chip,
  .bead .core,
  .bead text,
  .bead .ripple,
  .rail,
  .link,
  .pending .rail,
  .pending .link,
  .cross path {
    animation: none;
  }

  .bead,
  button,
  .said-enter-active,
  .said-leave-active {
    transition: none;
  }
}

@media (max-width: 640px) {
  .lanes .lane-row {
    flex-wrap: wrap;
  }

  .acts {
    margin-left: auto;
  }
}
</style>
