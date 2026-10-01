<script setup lang="ts">
// One turn under a budget of its own, played three ways and then once more, graceful. The rules
// are the driver's in `src/hmz/runtime/flowing/harnesses.py`: a graceful turn runs to its end;
// one that is not is cut off the moment a limit is reached, which for a token limit is when the
// spending is reported (`_spends` in each driver under `src/hmz/coganchor/agents/`, or only the
// turn's `result` for agy, cursor, grok, mcode and qwen), and for a time limit is the clock. A turn cut
// off keeps what it did, and the flow gets an error instead of an answer. The figures are
// invented.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { count, createFx, type Fx } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'A turn gets a budget of its own',
  'Each response is counted as it lands',
  'Over the limit, the turn is cut',
  'Some CLIs count only at the end',
  'A time limit cuts a quiet turn',
  'Graceful lets the turn finish',
]

// The responses of one turn: where each lands, as a share of the turn, and what it writes.
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
const LIMIT = 4000
const CROSS = (() => {
  let spent = 0
  return REQUESTS.findIndex((one) => (spent += one.tokens) >= LIMIT)
})()
const CUT = REQUESTS[CROSS].at
const MINUTES = 10 // the whole turn
const DEADLINE = 0.5 // the time limit, as a share of it
const QUIET = 3 // a quiet turn: its first three responses, then nothing

const LANES = [
  { name: 'tokens', sub: 'reported live', kind: 'live' },
  { name: 'tokens', sub: 'reported at the end', kind: 'end' },
  { name: 'time', sub: 'the clock', kind: 'time' },
] as const

interface Layout {
  w: number
  h: number
  lanes: number[]
  x0: number
  x1: number
  /** Where the lane's name goes, and whether its two words share a line. */
  label: { x: number; dy: number; inline: boolean }
  chip: { x: number; w: number }
  toggle: { x: number; dy: number }
  focus: number
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  lanes: [96, 196, 296],
  x0: 156,
  x1: 504,
  label: { x: 34, dy: -2, inline: false },
  chip: { x: 568, w: 76 },
  toggle: { x: 34, dy: 26 },
  focus: 1.1,
}

const NARROW: Layout = {
  w: 360,
  h: 440,
  lanes: [112, 252, 392],
  x0: 18,
  x1: 262,
  label: { x: 18, dy: -58, inline: true },
  chip: { x: 311, w: 70 },
  toggle: { x: 250, dy: -63 },
  focus: 1.04,
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const W = computed(() => L.value.x1 - L.value.x0)
const px = (share: number) => L.value.x0 + share * W.value
const limitX = computed(() => px(LIMIT / TOTAL))
const thousands = (n: number) => Math.round(n).toLocaleString('en-US')

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const gsap = motion()
    const l = L.value
    const w = W.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const world = q('.world')[0]
    const lane = q('.lane')
    const one = (i: number, sel: string) => lane[i].querySelectorAll(sel)

    // The camera: a point of the world brought to the middle of the screen at a scale.
    const cam = rig(tl, { w: l.w, h: l.h, world, fx: () => fx, start: { s: 1.12 } })
    const look = (i: number, at: number, s = l.focus) => {
      const y = l.lanes[i] + (narrow.value ? -14 : 0)
      cam.shot({ x: l.w / 2, y, s }, at, 1.3)
      lane.forEach((el, k) => tl.to(el, { opacity: k === i ? 1 : 0.28, duration: 0.8, ease: 'power1.inOut' }, at))
    }

    // A turn playing from `from` to `to` (shares of it) over its share of `D` seconds.
    const D = 4.4
    // The playhead leaves a trail of light behind it as the turn runs.
    const head = (i: number, from: number, to: number, at: number, ease = 'none') => {
      const el = one(i, '.head')[0]
      tl.fromTo(
        el,
        { x: from * w },
        {
          x: to * w,
          duration: (to - from) * D,
          ease,
          onUpdate() {
            const p = cam.view({ x: l.x0 + Number(gsap.getProperty(el, 'x')), y: l.lanes[i] + 13 })
            fx?.trail(p.x, p.y + (Math.random() - 0.5) * 4, palette.lane[0], 1.8)
          },
        },
        at,
      )
    }
    const land = (i: number, k: number, at: number) => {
      const block = one(i, '.block')[k]
      tl.fromTo(block, { scaleY: 0 }, { scaleY: 1, duration: 0.35, ease: 'back.out(2.4)' }, at)
      sparkAt(px(REQUESTS[k].at - 0.05), l.lanes[i] - 12, () => palette.lane[0], 6, at + 0.05, 50)
    }
    const sparkAt = (x: number, y: number, color: () => string, n: number, at: number, speed = 80) =>
      cam.flare({ x, y }, color, at, n, speed)
    const meter = (i: number, spent: number, at: number, duration = 0.4) => {
      tl.to(one(i, '.fill'), { scaleX: Math.min(spent, LIMIT) / TOTAL, duration, }, at)
      tl.to(one(i, '.over'), { scaleX: Math.max(0, spent - LIMIT) / (TOTAL - LIMIT), duration }, at + (spent > LIMIT ? duration * 0.5 : 0))
    }
    const cut = (i: number, share: number, at: number) => {
      const x = px(share)
      tl.fromTo(one(i, '.blade'), { drawSVG: '50% 50%', opacity: 1 }, { drawSVG: '0% 100%', duration: 0.18, ease: 'power4.out' }, at)
      tl.fromTo(one(i, '.flare'), { opacity: 0, scale: 0.3 }, { opacity: 1, scale: 1.3, duration: 0.2, ease: 'power2.out' }, at)
      tl.to(one(i, '.flare'), { opacity: 0.35, scale: 1, duration: 0.8 }, at + 0.2)
      sparkAt(x, l.lanes[i], () => palette.warm, 30, at, 150)
      tl.to(one(i, '.head'), { opacity: 0, duration: 0.2 }, at)
      tl.to(one(i, '.lost'), { opacity: 0.12, y: 10, duration: 0.7, stagger: 0.05, ease: 'power2.in' }, at + 0.05)
      tl.fromTo(lane[i], { x: 0 }, { keyframes: { x: [0, -4, 4, -2, 2, 0] }, duration: 0.4, ease: 'none' }, at)
    }
    const result = (i: number, which: 'error' | 'answer', at: number) => {
      const chip = one(i, `.chip-${which}`)
      tl.fromTo(chip, { opacity: 0, scale: 1.5 }, { opacity: 1, scale: 1, duration: 0.5, ease: 'back.out(1.8)' }, at)
      tl.fromTo(one(i, `.chip-${which}-halo`), { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.6 }, at)
      sparkAt(l.chip.x, l.lanes[i], () => (which === 'error' ? palette.warm : palette.accent), 22, at + 0.05, 110)
    }

    // Everything back where a loop starts.
    tl.set(world, { autoAlpha: 1 }, 0)
    // Origins first and on their own, so that GSAP has nothing to compensate for.
    tl.set(q('.block'), { transformOrigin: '50% 100%', smoothOrigin: false }, 0)
    tl.set(q('.fill, .over'), { transformOrigin: '0% 50%', smoothOrigin: false }, 0)
    tl.set(q('.flare, .chip, .chip-halo'), { transformOrigin: '50% 50%', smoothOrigin: false }, 0)
    tl.set(q('.limit'), { transformOrigin: '50% 100%', smoothOrigin: false }, 0)
    tl.set(q('.block'), { scaleY: 0 }, 0)
    tl.set(q('.fill, .over'), { scaleX: 0 }, 0)
    tl.set(q('.head'), { x: 0, opacity: 1 }, 0)
    tl.set(q('.blade'), { drawSVG: '50% 50%', opacity: 0 }, 0)
    tl.set(q('.flare, .chip, .chip-halo, .kept, .quiet, .toggle, .toggle-on, .notyet'), { opacity: 0 }, 0)
    tl.set(q('.lost'), { opacity: 1, y: 0 }, 0)
    tl.set(q('.knob'), { x: 0 }, 0)
    tl.set(q('.read'), { text: '0', opacity: 1 }, 0)
    tl.set(one(2, '.read'), { text: '0 min' }, 0)
    tl.set(lane, { opacity: 1 }, 0)

    // 0 · the budget: three lanes drawn in, the camera settling, then onto the first.
    tl.addLabel('beat-0', 0)
    cam.shot({ x: l.w / 2, y: l.h / 2, s: 1 }, 0, 2)
    tl.fromTo(q('.slot-track, .meter-track'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1, stagger: 0.08, ease: 'cine' }, 0.1)
    tl.fromTo(q('.limit'), { opacity: 0, scaleY: 0 }, { opacity: 1, scaleY: 1, duration: 0.5, stagger: 0.15, ease: 'back.out(3)' }, 0.8)
    tl.fromTo(q('.words'), { opacity: 0, x: -10 }, { opacity: 1, x: 0, duration: 0.6, stagger: 0.12 }, 0.4)
    tl.fromTo(q('.to-flow'), { opacity: 0 }, { opacity: 1, duration: 0.6, stagger: 0.12 }, 1)
    look(0, 1.9)

    // 1 · live: every response counted as it lands.
    const T1 = 3
    tl.addLabel('beat-1', T1)
    head(0, 0, CUT, T1)
    let spent = 0
    REQUESTS.slice(0, CROSS + 1).forEach((r, k) => {
      const at = T1 + r.at * D
      land(0, k, at)
      const before = spent
      spent += r.tokens
      meter(0, spent, at + 0.1)
      count(tl, one(0, '.read')[0], before, spent, at + 0.1, { duration: 0.4, format: thousands })
    })

    // 2 · the response that crosses the limit lands, and the turn is cut there.
    const T2 = T1 + CUT * D + 0.15
    tl.addLabel('beat-2', T2 - 0.1)
    cut(0, CUT, T2)
    tl.fromTo(one(0, '.kept'), { opacity: 0 }, { opacity: 1, duration: 0.5 }, T2 + 0.5)
    tl.fromTo(one(0, '.kept-line'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.6, ease: 'cine' }, T2 + 0.5)
    result(0, 'error', T2 + 0.7)

    // 3 · a CLI that says what it spent only when the turn ends: it runs on, then pays at once.
    const T3 = T2 + 2.4
    tl.addLabel('beat-3', T3)
    look(1, T3 - 0.3)
    tl.to(one(1, '.notyet'), { opacity: 1, duration: 0.3 }, T3 + 0.3)
    tl.to(one(1, '.read'), { opacity: 0, duration: 0.2 }, T3 + 0.3)
    head(1, 0, 1, T3 + 0.4)
    REQUESTS.forEach((r, k) => land(1, k, T3 + 0.4 + r.at * D))
    const E3 = T3 + 0.4 + D
    tl.to(one(1, '.notyet'), { opacity: 0, duration: 0.15 }, E3)
    tl.set(one(1, '.read'), { opacity: 1, text: thousands(TOTAL) }, E3)
    meter(1, TOTAL, E3, 0.25)
    sparkAt(limitX.value, l.lanes[1] - 28, () => palette.warm, 26, E3 + 0.15, 130)
    tl.to(one(1, '.head'), { opacity: 0, duration: 0.2 }, E3)
    result(1, 'error', E3 + 0.4)

    // 4 · a time limit: the clock runs whatever the turn says, even when it says nothing.
    const T4 = E3 + 1.7
    tl.addLabel('beat-4', T4)
    look(2, T4 - 0.3)
    const S4 = T4 + 0.4
    head(2, 0, DEADLINE, S4)
    tl.to(one(2, '.fill'), { scaleX: DEADLINE, duration: DEADLINE * D, ease: 'none' }, S4)
    count(tl, one(2, '.read')[0], 0, DEADLINE * MINUTES, S4, { duration: DEADLINE * D, ease: 'none', format: (n) => `${Math.floor(n)} min` })
    REQUESTS.slice(0, QUIET).forEach((r, k) => land(2, k, S4 + r.at * D))
    tl.to(one(2, '.quiet'), { opacity: 1, duration: 0.4 }, S4 + REQUESTS[QUIET - 1].at * D + 0.3)
    tl.fromTo(one(2, '.quiet circle'), { opacity: 0.25 }, { opacity: 1, duration: 0.35, stagger: { each: 0.15, repeat: 3, yoyo: true } }, S4 + REQUESTS[QUIET - 1].at * D + 0.3)
    cut(2, DEADLINE, S4 + DEADLINE * D + 0.05)
    tl.to(one(2, '.quiet'), { opacity: 0, duration: 0.3 }, S4 + DEADLINE * D + 0.1)
    result(2, 'error', S4 + DEADLINE * D + 0.6)

    // 5 · the first turn again, graceful: nothing is cut, and it answers.
    const T5 = S4 + DEADLINE * D + 2
    tl.addLabel('beat-5', T5)
    look(0, T5 - 0.3)
    tl.to(one(0, '.toggle'), { opacity: 1, duration: 0.3 }, T5 + 0.3)
    tl.to(one(0, '.knob'), { x: 16, duration: 0.35, ease: 'back.out(2)' }, T5 + 0.7)
    tl.to(one(0, '.toggle-on'), { opacity: 1, duration: 0.3 }, T5 + 0.7)
    tl.to(one(0, '.blade, .flare, .kept'), { opacity: 0, duration: 0.4 }, T5 + 1)
    tl.to(one(0, '.chip-error, .chip-error-halo'), { opacity: 0, scale: 0.8, duration: 0.35 }, T5 + 1)
    tl.to(one(0, '.lost'), { opacity: 1, y: 0, duration: 0.5, stagger: 0.05, ease: 'back.out(2)' }, T5 + 1.05)
    tl.set(one(0, '.head'), { opacity: 1 }, T5 + 1.2)
    const S5 = T5 + 1.3
    head(0, CUT, 1, S5)
    REQUESTS.slice(CROSS + 1).forEach((r, k) => {
      const at = S5 + (r.at - CUT) * D
      land(0, CROSS + 1 + k, at)
      const before = spent
      spent += r.tokens
      meter(0, spent, at + 0.1)
      count(tl, one(0, '.read')[0], before, spent, at + 0.1, { duration: 0.4, format: thousands })
    })
    const E5 = S5 + (1 - CUT) * D
    tl.to(one(0, '.head'), { opacity: 0, duration: 0.2 }, E5)
    result(0, 'answer', E5 + 0.1)

    // Pull back on all three, hold, and fade for the loop.
    cam.shot({ x: l.w / 2, y: l.h / 2, s: 1 }, E5 + 0.8, 1.4)
    tl.to(lane, { opacity: 1, duration: 0.8 }, E5 + 0.8)
    tl.addLabel('rest', E5 + 2.3)
    tl.to(world, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, E5 + 4.6)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 11"
    label="One turn with a budget of its own. On a CLI that reports its spending live, the turn is cut off as the response that crosses the token limit lands, keeping what it did, and the flow gets an error. On a CLI that reports only at the end, the turn runs to its end, then the whole spend arrives and the flow gets an error. A time limit cuts the turn at the clock even while it is quiet. A graceful budget lets the turn finish and answer."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <radialGradient id="turn-budget-warm">
          <stop offset="0" stop-color="var(--hmz-warm)" stop-opacity="0.6" />
          <stop offset="1" stop-color="var(--hmz-warm)" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="turn-budget-cool">
          <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.55" />
          <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
        </radialGradient>
      </defs>
      <g class="world">
        <g v-for="(ln, i) in LANES" :key="i" class="lane">
          <g class="words">
            <template v-if="L.label.inline">
              <text class="name" :x="L.label.x" :y="L.lanes[i] + L.label.dy">{{ ln.name }}<tspan class="sub" dx="6">{{ ln.sub }}</tspan></text>
            </template>
            <template v-else>
              <text class="name" :x="L.label.x" :y="L.lanes[i] + L.label.dy">{{ ln.name }}</text>
              <text class="sub" :x="L.label.x" :y="L.lanes[i] + L.label.dy + 16">{{ ln.sub }}</text>
            </template>
          </g>

          <!-- the meter: what is counted, against the limit -->
          <line class="meter-track" :x1="L.x0" :x2="L.x1" :y1="L.lanes[i] - 28" :y2="L.lanes[i] - 28" />
          <rect class="fill" :class="ln.kind === 'time' ? 'clock' : ''" :x="L.x0" :y="L.lanes[i] - 31" :width="W" height="6" rx="3" />
          <rect v-if="ln.kind !== 'time'" class="over" :x="limitX" :y="L.lanes[i] - 31" :width="L.x1 - limitX" height="6" rx="3" />
          <g class="limit">
            <line :x1="ln.kind === 'time' ? px(DEADLINE) : limitX" :x2="ln.kind === 'time' ? px(DEADLINE) : limitX" :y1="L.lanes[i] - 37" :y2="L.lanes[i] - 22" />
            <text :x="ln.kind === 'time' ? px(DEADLINE) : limitX" :y="L.lanes[i] - 41" text-anchor="middle">{{ ln.kind === 'time' ? `${DEADLINE * MINUTES} min` : thousands(LIMIT) }}</text>
          </g>
          <text class="read" :x="L.x1" :y="L.lanes[i] - 41" text-anchor="end">0</text>
          <text v-if="ln.kind === 'end'" class="notyet" :x="L.x1" :y="L.lanes[i] - 41" text-anchor="end">not yet</text>

          <!-- the turn: a slot per response, filled as each lands -->
          <line class="slot-track" :x1="L.x0" :x2="L.x1" :y1="L.lanes[i] + 13" :y2="L.lanes[i] + 13" />
          <g v-for="(r, k) in REQUESTS" :key="k" :class="{ lost: ln.kind === 'time' ? r.at > DEADLINE : r.at > CUT }">
            <rect v-if="ln.kind !== 'time' || k < QUIET || r.at > DEADLINE" class="slot" :x="px(r.at - 0.09)" :y="L.lanes[i] - 12" :width="W * 0.08" height="24" rx="5" />
            <rect v-if="ln.kind !== 'time' || k < QUIET" class="block" :x="px(r.at - 0.09)" :y="L.lanes[i] - 12" :width="W * 0.08" height="24" rx="5" />
          </g>
          <g v-if="ln.kind === 'time'" class="quiet">
            <circle v-for="k in 3" :key="k" :cx="px(0.4) + k * 9" :cy="L.lanes[i]" r="2.6" />
          </g>
          <line class="head" :x1="L.x0" :x2="L.x0" :y1="L.lanes[i] - 19" :y2="L.lanes[i] + 19" />

          <g class="glow"><circle class="flare" :cx="px(ln.kind === 'time' ? DEADLINE : CUT)" :cy="L.lanes[i]" r="34" fill="url(#turn-budget-warm)" /></g>
          <line class="blade" :x1="px(ln.kind === 'time' ? DEADLINE : CUT)" :x2="px(ln.kind === 'time' ? DEADLINE : CUT)" :y1="L.lanes[i] - 24" :y2="L.lanes[i] + 24" />

          <g v-if="ln.kind === 'live'" class="kept">
            <path class="kept-line" :d="`M${L.x0} ${L.lanes[i] + 20} v5 H${px(CUT) - 4} v-5`" />
            <text :x="(L.x0 + px(CUT)) / 2" :y="L.lanes[i] + 39" text-anchor="middle">kept</text>
          </g>

          <g v-if="ln.kind === 'live'" class="toggle" :transform="`translate(${L.toggle.x} ${L.lanes[i] + L.toggle.dy})`">
            <rect class="toggle-track" x="0" y="-8" width="32" height="16" rx="8" />
            <rect class="toggle-on" x="0" y="-8" width="32" height="16" rx="8" />
            <circle class="knob" cx="8" cy="0" r="5.5" />
            <text x="40" y="4">graceful</text>
          </g>

          <text class="caption to-flow" :x="L.chip.x" :y="L.lanes[i] - 22" text-anchor="middle">flow</text>
          <rect class="chip-slot" :x="L.chip.x - L.chip.w / 2" :y="L.lanes[i] - 13" :width="L.chip.w" height="26" rx="13" />
          <g class="glow"><circle class="chip-halo chip-error-halo" :cx="L.chip.x" :cy="L.lanes[i]" r="38" fill="url(#turn-budget-warm)" />
          <circle v-if="ln.kind === 'live'" class="chip-halo chip-answer-halo" :cx="L.chip.x" :cy="L.lanes[i]" r="38" fill="url(#turn-budget-cool)" /></g>
          <g class="chip chip-error">
            <rect :x="L.chip.x - L.chip.w / 2" :y="L.lanes[i] - 13" :width="L.chip.w" height="26" rx="13" />
            <text :x="L.chip.x" :y="L.lanes[i] + 4.5" text-anchor="middle">error</text>
          </g>
          <g v-if="ln.kind === 'live'" class="chip chip-answer">
            <rect :x="L.chip.x - L.chip.w / 2" :y="L.lanes[i] - 13" :width="L.chip.w" height="26" rx="13" />
            <text :x="L.chip.x" :y="L.lanes[i] + 4.5" text-anchor="middle">answer</text>
          </g>
        </g>
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.caption {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.name {
  font-size: 15px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}

.sub {
  font-size: 12px;
  font-weight: 500;
  fill: var(--hmz-stage-dim);
}

.meter-track {
  stroke: var(--hmz-stage-line);
  stroke-width: 6;
  stroke-linecap: round;
}

.fill {
  fill: var(--hmz-accent);
}

.fill.clock {
  fill: var(--hmz-lane-1);
}

.over {
  fill: var(--hmz-warm);
}

.limit line {
  stroke: var(--hmz-stage-ink);
  stroke-width: 2;
}

.limit text,
.read,
.notyet {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  fill: var(--hmz-stage-dim);
}

.read {
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.notyet {
  font-style: italic;
}

.slot-track {
  stroke: var(--hmz-stage-line);
  stroke-width: 1;
}

.slot {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 3 3;
}

.block {
  fill: var(--hmz-lane-1);
}

.quiet circle {
  fill: var(--hmz-stage-dim);
}

.head {
  stroke: var(--hmz-stage-ink);
  stroke-width: 2;
  stroke-linecap: round;
}

.blade {
  stroke: var(--hmz-warm);
  stroke-width: 3.5;
  stroke-linecap: round;
}

.glow {
  opacity: var(--hmz-glow);
}

.flare,
.chip-halo {
  opacity: 0;
}

.kept path {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
}

.kept text {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-accent);
}

.toggle-track {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
}

.toggle-on {
  fill: var(--hmz-accent);
}

.knob {
  fill: var(--hmz-stage-ink);
}

.toggle text {
  font-size: 12px;
  font-weight: 650;
  fill: var(--hmz-accent);
}

.chip-slot {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 3 3;
}

.chip rect {
  fill: var(--hmz-stage-card);
  stroke-width: 1.5;
}

.chip text {
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  font-weight: 700;
}

.chip-error rect {
  stroke: var(--hmz-warm);
}

.chip-error text {
  fill: var(--hmz-warm);
}

.chip-answer rect {
  stroke: var(--hmz-accent);
}

.chip-answer text {
  fill: var(--hmz-accent);
}
</style>
