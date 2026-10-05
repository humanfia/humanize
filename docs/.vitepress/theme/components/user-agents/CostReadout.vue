<script setup lang="ts">
// The readout above the editor, for a run of whichever agents are switched on. The figures are
// invented; the rules are the interface's own: every kind any agent reports is a column, a
// kind is marked `+` where some agent of the run does not report it (`Monitor.reckoning` in
// `src/hmz/tui/monitor.py`), the money is the priced models' sum and wears `+` where a model
// has no price (`HmzApp._draw` in `src/hmz/tui/app.py`), and the rate is output tokens a
// second. Which kinds each backend reports is its `counts`, plus what its own log names.
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { motion } from '../../motion/gsap'

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

function flip(id: string, event: MouseEvent) {
  const left = AGENTS.filter((one) => on.value[one.id] && one.id !== id)
  const button = event.currentTarget as HTMLElement
  if (on.value[id] && !left.length) {
    // A run has at least one agent: the last one shakes its head.
    if (!still()) motion().fromTo(button, { x: 0 }, { keyframes: { x: [0, -5, 4, -3, 2, 0] }, duration: 0.4, ease: 'none' })
    return
  }
  on.value = { ...on.value, [id]: !on.value[id] }
  if (!still()) motion().fromTo(button, { scale: 1 }, { keyframes: { scale: [1, 0.92, 1.06, 1] }, duration: 0.4, ease: 'none' })
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

// The motion, laid over the readout without changing what it says. Switching an agent in or
// out rolls every figure to its new count, slides a column in or out of the line while the
// rest make room, pops a `+` on where a figure becomes a floor, and lets an agent's line and
// each reason in or out. The rate glints now and then, as a live figure. Under reduced motion
// every one of those is its final frame.
const readout = ref<HTMLElement | null>(null)

// The figures as drawn, which roll to the figures as counted.
function counted(): Record<string, number> {
  const all: Record<string, number> = { bill: bill.value, rate: rate.value }
  for (const one of columns.value) all[one.kind] = one.tokens
  return all
}
const roll = reactive<Record<string, number>>(counted())
let drawn = new Set<string>(columns.value.map((one) => one.kind))
let seen: IntersectionObserver | undefined

const still = () => typeof window === 'undefined' || window.matchMedia('(prefers-reduced-motion: reduce)').matches

watch(counted, (to) => {
  // A column that has just arrived counts up from nothing.
  for (const kind of Object.keys(to)) if (kind !== 'bill' && kind !== 'rate' && !drawn.has(kind)) roll[kind] = 0
  drawn = new Set(columns.value.map((one) => one.kind))
  if (still()) Object.assign(roll, to)
  else motion().to(roll, { ...to, duration: 0.9, ease: 'power3.out', overwrite: true })
})

// What a figure shows: its rolled count, or its count where nothing has rolled it.
function figure(kind: string, fallback: number): number {
  return roll[kind] ?? fallback
}

// In: a line opens to its height and slides in from the right, where the readout is set.
function open(el: Element, done: () => void) {
  if (still()) return done()
  motion().fromTo(
    el,
    { height: 0, autoAlpha: 0, x: 28 },
    { height: 'auto', autoAlpha: 1, x: 0, duration: 0.5, ease: 'cine.out', clearProps: 'height,transform', onComplete: done },
  )
}

function shut(el: Element, done: () => void) {
  if (still()) return done()
  motion().to(el, { height: 0, autoAlpha: 0, x: 28, duration: 0.4, ease: 'cine', onComplete: done })
}

// A column comes into the line as wide as it is, and the columns after it make room.
function widen(el: Element, done: () => void) {
  if (still()) return done()
  const col = el as HTMLElement
  const width = col.offsetWidth
  motion().fromTo(
    col,
    { maxWidth: 0, autoAlpha: 0, overflow: 'hidden' },
    { maxWidth: width, autoAlpha: 1, duration: 0.55, ease: 'cine', clearProps: 'maxWidth,overflow', onComplete: done },
  )
}

function narrow(el: Element, done: () => void) {
  if (still()) return done()
  const col = el as HTMLElement
  motion().fromTo(
    col,
    { maxWidth: col.offsetWidth, overflow: 'hidden' },
    { maxWidth: 0, autoAlpha: 0, duration: 0.45, ease: 'cine', onComplete: done },
  )
}

// A `+` pops on, glowing for a moment in the colour of a floor.
function plus(el: Element, done: () => void) {
  if (still()) return done()
  const gsap = motion()
  gsap.fromTo(el, { scale: 0, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: 0.5, ease: 'back.out(3.5)', delay: 0.25, onComplete: done })
  gsap.fromTo(el, { textShadow: '0 0 0px currentColor' }, { textShadow: '0 0 10px currentColor', duration: 0.3, delay: 0.3, yoyo: true, repeat: 1, ease: 'sine.inOut' })
}

function unplus(el: Element, done: () => void) {
  if (still()) return done()
  motion().to(el, { scale: 0, autoAlpha: 0, duration: 0.25, ease: 'cine.in', onComplete: done })
}

onMounted(() => {
  if (still() || !readout.value) return
  // The figures count up from nothing the first time the readout is scrolled to.
  for (const kind of Object.keys(roll)) roll[kind] = 0
  seen = new IntersectionObserver(
    (entries) => {
      if (!entries.some((one) => one.isIntersecting)) return
      seen?.disconnect()
      const gsap = motion()
      gsap.to(roll, { ...counted(), duration: 1.4, ease: 'power3.out' })
      const box = readout.value!
      gsap.fromTo(box.querySelectorAll('.agent'), { autoAlpha: 0, x: 24 }, { autoAlpha: 1, x: 0, duration: 0.6, stagger: 0.12, clearProps: 'transform' })
      gsap.fromTo(box.querySelectorAll('.col'), { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.5, stagger: 0.08, delay: 0.2, clearProps: 'transform' })
      gsap.fromTo(box.querySelectorAll('.why li'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.5, stagger: 0.1, delay: 0.6 })
    },
    { threshold: 0.4 },
  )
  nextTick(() => readout.value && seen?.observe(readout.value))
})

onBeforeUnmount(() => seen?.disconnect())
</script>

<template>
  <div ref="readout" class="readout hmz-panel">
    <div class="pick" role="group" aria-label="agents in the run">
      <span>agents in the run</span>
      <button
        v-for="one in AGENTS"
        :key="one.id"
        type="button"
        :class="{ on: on[one.id] }"
        :aria-pressed="Boolean(on[one.id])"
        @click="flip(one.id, $event)"
      >
        {{ one.called }}
      </button>
    </div>

    <div class="screen" aria-live="polite">
      <TransitionGroup tag="div" :css="false" @enter="open" @leave="shut">
        <p v-for="one in running" :key="one.id" class="agent">
          {{ one.role }} · <span class="spec">{{ one.spec }}</span>
        </p>
      </TransitionGroup>
      <TransitionGroup tag="p" class="kinds" :css="false" @enter="widen" @leave="narrow">
        <span v-for="(one, at) in columns" :key="one.kind" class="col"
          ><span v-if="at" class="dot">·</span
          ><span :class="{ floor: !one.whole }"
            >{{ one.kind }} {{ thousands(figure(one.kind, one.tokens))
            }}<Transition :css="false" @enter="plus" @leave="unplus"><b v-if="!one.whole">+</b></Transition></span
          ></span
        >
      </TransitionGroup>
      <p class="money">
        <span :class="{ floor: unpriced.length && priced.length }"
          ><template v-if="priced.length"
            >${{ figure('bill', bill).toFixed(2)
            }}<Transition :css="false" @enter="plus" @leave="unplus"><span v-if="unpriced.length" class="up">+</span></Transition
            >{{ ' · ' }}</template
          ><span class="rate">{{ figure('rate', rate).toFixed(0) }} out/s</span></span
        >
      </p>
    </div>

    <TransitionGroup tag="ul" class="why" :css="false" @enter="open" @leave="shut">
      <li v-for="one in why" :key="one">{{ one }}</li>
    </TransitionGroup>

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
  margin: 0 0.6ch;
  color: var(--vp-c-text-3);
}

.screen .floor {
  color: var(--hmz-warm);
}

.screen b {
  display: inline-block;
  font-weight: 700;
}

.screen .up {
  display: inline-block;
}

.screen .col {
  display: inline-block;
  vertical-align: top;
  white-space: nowrap;
}

/* The rate is a live figure: a glint runs across it now and then. */
.screen .rate {
  display: inline-block;
}

.screen .agent {
  overflow: hidden;
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

@media (prefers-reduced-motion: no-preference) {
  .screen .rate {
    color: transparent;
    background: linear-gradient(100deg, var(--vp-c-text-1) 40%, var(--hmz-accent) 50%, var(--vp-c-text-1) 60%) 100% 0 / 300% 100% no-repeat;
    background-clip: text;
    -webkit-background-clip: text;
    animation: glint 4.2s ease-in-out infinite;
  }

  .screen .floor .rate {
    background-image: linear-gradient(100deg, var(--hmz-warm) 40%, var(--hmz-accent) 50%, var(--hmz-warm) 60%);
  }
}

@keyframes glint {
  0%,
  55% {
    background-position: 100% 0;
  }

  100% {
    background-position: 0 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .pick button {
    transition: none;
  }
}
</style>
