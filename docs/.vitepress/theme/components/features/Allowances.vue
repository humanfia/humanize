<script setup lang="ts">
// A run's budget, played out: three limits set when the run starts (duration, output tokens,
// cost), every turn spending from all three, a called flow held to the tighter of its own
// budget and what its caller has left, and the first limit reached stopping the run --
// gracefully, the default: the turn under way finishes, the next one is refused, and the run
// ends with a budget error and exit status 0. Drawn from `Budget` in `src/hmz/flows/agents.py`
// and the limits in `src/hmz/runtime/flowing/viewing.py`. The figures are invented.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { count, createFx, streak, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'
import { breathe } from '../sway'

const BEATS = [
  'Three limits, set at the start',
  'Every turn spends from all three',
  'A called flow gets the tighter budget',
  'The first limit reached stops the run',
  'The turn ends; the next is refused',
]

interface Box {
  x: number
  y: number
  w: number
}

interface Layout {
  w: number
  h: number
  r: number
  gauges: { x: number; y: number }[]
  turns: Box[]
  review: { x: number; y: number; w: number; h: number }
  inner: Box[]
  refused: Box
  stamp: { x: number; y: number }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  r: 46,
  gauges: [
    { x: 150, y: 104 },
    { x: 320, y: 104 },
    { x: 490, y: 104 },
  ],
  turns: [
    { x: 36, y: 238, w: 66 },
    { x: 110, y: 238, w: 66 },
    { x: 184, y: 238, w: 66 },
    { x: 258, y: 238, w: 66 },
  ],
  review: { x: 334, y: 206, w: 206, h: 80 },
  inner: [{ x: 346, y: 250, w: 80 }],
  refused: { x: 552, y: 238, w: 64 },
  stamp: { x: 320, y: 326 },
}

const NARROW: Layout = {
  w: 360,
  h: 420,
  r: 36,
  gauges: [
    { x: 64, y: 78 },
    { x: 180, y: 78 },
    { x: 296, y: 78 },
  ],
  turns: [
    { x: 20, y: 188, w: 72 },
    { x: 100, y: 188, w: 72 },
    { x: 180, y: 188, w: 72 },
    { x: 260, y: 188, w: 80 },
  ],
  review: { x: 20, y: 240, w: 200, h: 84 },
  inner: [{ x: 32, y: 286, w: 88 }],
  refused: { x: 240, y: 286, w: 100 },
  stamp: { x: 180, y: 384 },
}

const GAUGES = [
  { name: 'duration', limit: 'of 6 h', color: 'var(--hmz-lane-1)' },
  { name: 'output tokens', limit: 'of 1M', color: 'var(--hmz-lane-3)' },
  { name: 'cost', limit: 'of $50', color: 'var(--hmz-warm)' },
]

// What each turn has spent by its end: tokens (thousands) and dollars.
const SPENT = [
  { k: 150, usd: 12 },
  { k: 290, usd: 24 },
  { k: 420, usd: 37 },
  { k: 560, usd: 49 },
]

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const TURN_H = 24
// A dial's ticks, every 30 degrees from the top.
const TICKS = Array.from({ length: 12 }, (_, k) => (k * Math.PI) / 6)
// How far round the duration dial the run gets: 2h 40m of 6 h.
const DURATION = 160 / 360

function hm(minutes: number) {
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`
}

const scene = useScene({
  still: 'rest',
  repeatDelay: 1.2,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const get = () => fx
    const at = (sel: string) => q(sel)
    const ring = at('.ring-fill')
    const value = at('.value')
    const turn = at('.turn .bar')
    const centre = (b: Box) => ({ x: b.x + b.w / 2, y: b.y + TURN_H / 2 })

    // 0 · the limits, drawn in as the camera settles.
    tl.addLabel('beat-0', 0)
    tl.fromTo(at('.cam'), { scale: 1.1, transformOrigin: '50% 40%' }, { scale: 1, duration: 2.4, ease: 'cine' }, 0)
    tl.fromTo(at('.ring-track'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.1, stagger: 0.15, ease: 'cine' }, 0.1)
    tl.fromTo(at('.gauge-words'), { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.7, stagger: 0.15 }, 0.5)
    tl.fromTo(at('.tick'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.3, stagger: 0.025, ease: 'cine.out' }, 0.4)
    tl.fromTo(at('.hand'), { autoAlpha: 0, rotation: 0, svgOrigin: '0 0' }, { autoAlpha: 1, duration: 0.4 }, 1.4)
    tl.set(at('.formula, .first'), { autoAlpha: 0 }, 0)
    tl.set(ring, { drawSVG: '0%' }, 0)
    tl.set(at('.turn, .review, .refused, .stamp, .chip'), { autoAlpha: 0 }, 0)
    tl.set(value, { text: '0' }, 0)
    tl.set(at('.halo'), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, 0)
    tl.set(at('.ring-alarm'), { autoAlpha: 0 }, 0)

    // 1 · every turn spends from all three. Time runs by itself; tokens and dollars land
    // as each turn reports them.
    const T0 = 2
    const STEP = 1.05
    tl.addLabel('beat-1', T0)
    tl.to(ring[0], { drawSVG: `0% ${DURATION * 100}%`, duration: 9, ease: 'none' }, T0)
    // The duration dial's hand sweeps with the clock, whatever the turns are doing.
    tl.to(at('.hand'), { rotation: DURATION * 360, svgOrigin: '0 0', duration: 9, ease: 'none' }, T0)
    count(tl, value[0], 0, 160, T0, { duration: 9, ease: 'none', format: hm })
    SPENT.forEach((s, i) => {
      const t = T0 + i * STEP
      tl.to(at('.turn')[i], { autoAlpha: 1, duration: 0.2 }, t)
      tl.fromTo(turn[i], { scaleX: 0 }, { scaleX: 1, duration: STEP - 0.15, ease: 'power1.inOut', transformOrigin: '0% 50%' }, t)
      const from = centre(l.turns[i])
      streak(tl, get, from, l.gauges[1], () => palette.lane[2], t + STEP - 0.2, { duration: 0.7, bend: 0.25, burst: 5 })
      streak(tl, get, from, l.gauges[2], () => palette.warm, t + STEP - 0.15, { duration: 0.7, bend: -0.2, burst: 5 })
      tl.to(ring[1], { drawSVG: `0% ${s.k / 10}%`, duration: 0.5 }, t + STEP + 0.45)
      tl.to(ring[2], { drawSVG: `0% ${s.usd * 2}%`, duration: 0.5 }, t + STEP + 0.5)
      count(tl, value[1], i ? SPENT[i - 1].k : 0, s.k, t + STEP + 0.45, { duration: 0.5, format: (n) => `${Math.round(n)}k` })
      count(tl, value[2], i ? SPENT[i - 1].usd : 0, s.usd, t + STEP + 0.5, { duration: 0.5, format: (n) => `$${Math.round(n)}` })
    })

    // 2 · a called flow: $2 asked for, $1 left above it, so $1 it is.
    const T2 = T0 + 4 * STEP + 0.6
    tl.addLabel('beat-2', T2)
    tl.to(at('.cam'), { scale: 1.12, xPercent: narrow.value ? 0 : -6, yPercent: narrow.value ? -7 : -6.5, transformOrigin: '50% 50%', duration: 1.4, ease: 'cine' }, T2)
    tl.to(at('.review'), { autoAlpha: 1, duration: 0.3 }, T2 + 0.1)
    tl.fromTo(at('.review-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.9, ease: 'cine' }, T2 + 0.1)
    tl.fromTo(at('.chip'), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.6, ease: 'back.out(2)' }, T2 + 1.1)
    streak(tl, get, l.gauges[2], { x: l.review.x + l.review.w - 40, y: l.review.y + 20 }, () => palette.warm, T2 + 0.7, { duration: 0.6, bend: 0.3, burst: 10 })
    tl.fromTo(at('.chip-asked'), { opacity: 1 }, { opacity: 0.45, duration: 0.3 }, T2 + 1.6)
    tl.fromTo(at('.chip-strike'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.3 }, T2 + 1.6)
    tl.fromTo(at('.formula'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, T2 + 1.3)

    // 3 · the review's turn spends the last dollar while it is still running.
    const T3 = T2 + 2.2
    const inner = at('.inner .bar')[0]
    tl.to(at('.inner'), { autoAlpha: 1, duration: 0.2 }, T3 - 0.4)
    tl.fromTo(inner, { scaleX: 0 }, { scaleX: 1, duration: 2.2, ease: 'none', transformOrigin: '0% 50%' }, T3 - 0.4)
    tl.to(at('.cam'), { scale: 1, xPercent: 0, yPercent: 0, duration: 1.3, ease: 'cine' }, T3)
    tl.addLabel('beat-3', T3 + 0.4)
    streak(tl, get, centre(l.inner[0]), l.gauges[2], () => palette.warm, T3, { duration: 0.6, bend: -0.25 })
    tl.to(ring[2], { drawSVG: '0% 100%', duration: 0.4, ease: 'power2.in' }, T3 + 0.5)
    count(tl, value[2], 49, 50, T3 + 0.5, { duration: 0.4, format: (n) => `$${Math.round(n)}` })
    tl.to(at('.ring-alarm'), { autoAlpha: 1, duration: 0.25 }, T3 + 0.9)
    tl.fromTo(at('.first'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.35 }, T3 + 1)
    tl.to(at('.halo')[2], { autoAlpha: 1, scale: 1.25, duration: 0.35, ease: 'power2.out' }, T3 + 0.9)
    tl.to(at('.halo')[2], { autoAlpha: 0.55, scale: 1, duration: 0.8 }, T3 + 1.25)
    tl.call(() => fx?.spark(l.gauges[2].x, l.gauges[2].y - l.r, palette.danger, 36, 140), [], T3 + 0.9)
    tl.fromTo(at('.gauge')[2], { x: 0 }, { keyframes: { x: [0, -5, 5, -3, 3, 0] }, duration: 0.45, ease: 'none' }, T3 + 0.9)

    // 4 · graceful: that turn runs to its end, the next is refused, and the run is over.
    const T4 = T3 + 1.9
    tl.addLabel('beat-4', T4)
    tl.to(at('.refused'), { autoAlpha: 1, duration: 0.25 }, T4 + 0.1)
    tl.fromTo(at('.refused .bar'), { scaleX: 0 }, { scaleX: 0.18, duration: 0.3, transformOrigin: '0% 50%' }, T4 + 0.1)
    tl.fromTo(at('.cross'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.25, stagger: 0.1 }, T4 + 0.45)
    tl.fromTo(at('.refused'), { x: 0 }, { keyframes: { x: [0, -6, 6, -4, 4, 0] }, duration: 0.45, ease: 'none' }, T4 + 0.45)
    tl.call(() => fx?.spark(centre(l.refused).x, centre(l.refused).y, palette.danger, 18, 90), [], T4 + 0.5)
    tl.to(at('.refused .bar'), { opacity: 0.35, duration: 0.4 }, T4 + 0.9)
    tl.fromTo(at('.stamp'), { autoAlpha: 0, scale: 1.4, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.5, ease: 'back.out(1.6)' }, T4 + 1.1)
    tl.addLabel('rest', T4 + 2.2)
    breathe(tl, at('.halo')[2], T3 + 2.1, T4 + 4.2, { period: 1.6, rest: 0.55, opacity: 0.2 })
    tl.to(at('.cam'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 4.2)
    tl.set(at('.cam'), { autoAlpha: 1 }, 0)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="6 / 7"
    label="A run's budget: duration, output tokens and cost. Each turn spends from all three. A review flow called with 2 dollars, while the run has 1 dollar left, gets the smaller, 1 dollar. Its turn spends the last dollar, the cost limit is the first reached, that turn finishes, and the next turn is refused. The run ends with a budget error, exit status 0."
  >
    <div class="layer cam">
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <radialGradient id="allowance-halo">
          <stop offset="0" stop-color="var(--hmz-lane-5)" stop-opacity="0.55" />
          <stop offset="1" stop-color="var(--hmz-lane-5)" stop-opacity="0" />
        </radialGradient>
      </defs>
      <g class="world">
        <g v-for="(g, i) in GAUGES" :key="g.name" :transform="`translate(${L.gauges[i].x} ${L.gauges[i].y})`"><g class="gauge">
          <circle class="halo" :r="L.r * 1.9" fill="url(#allowance-halo)" />
          <circle class="ring-track" :r="L.r" :transform="`rotate(-90)`" />
          <circle class="ring-fill" :r="L.r" transform="rotate(-90)" :style="{ stroke: g.color }" />
          <circle v-if="i === 2" class="ring-alarm" :r="L.r" />
          <line v-for="(a, k) in TICKS" :key="k" class="tick" :x1="Math.sin(a) * (L.r + 7)" :y1="-Math.cos(a) * (L.r + 7)" :x2="Math.sin(a) * (L.r + (k % 3 ? 10 : 13))" :y2="-Math.cos(a) * (L.r + (k % 3 ? 10 : 13))" />
          <line v-if="i === 0" class="hand" x1="0" :y1="-L.r + 5" x2="0" :y2="-L.r - 9" :style="{ stroke: g.color }" />
          <g v-if="i === 2" class="first">
            <text :y="-L.r - 18" text-anchor="middle">first limit reached</text>
          </g>
          <text class="value" y="5" text-anchor="middle">0</text>
          <g class="gauge-words">
            <text class="limit" :y="narrow ? 18 : 22" text-anchor="middle">{{ g.limit }}</text>
            <text class="name" :y="L.r + (narrow ? 22 : 26)" text-anchor="middle">{{ g.name }}</text>
          </g>
        </g></g>

        <text class="caption" :x="L.turns[0].x" :y="L.turns[0].y - 12">the run's turns</text>
        <g v-for="(t, i) in L.turns" :key="`t${i}`" class="turn">
          <rect class="slot" :x="t.x" :y="t.y" :width="t.w" :height="TURN_H" rx="7" />
          <rect class="bar lane-1" :x="t.x" :y="t.y" :width="t.w" :height="TURN_H" rx="7" />
          <text class="turn-name" :x="t.x + t.w / 2" :y="t.y + 16" text-anchor="middle">turn {{ i + 1 }}</text>
        </g>

        <g class="review">
          <rect class="review-frame" :x="L.review.x" :y="L.review.y" :width="L.review.w" :height="L.review.h" rx="12" />
          <text class="caption" :x="L.review.x + 12" :y="L.review.y + 22">review</text>
          <g class="formula">
            <text :x="L.review.x + 12" :y="L.review.y + 39">min($2 asked, $1 left) = $1</text>
          </g>
          <g :transform="`translate(${L.review.x + L.review.w - 12} ${L.review.y + 16})`">
            <g class="chip">
              <text class="chip-asked" text-anchor="end" x="-44" y="5">$2</text>
              <line class="chip-strike" x1="-66" x2="-42" y1="1" y2="1" />
              <text class="chip-got" text-anchor="end" y="5">$1</text>
            </g>
          </g>
          <g v-for="(t, i) in L.inner" :key="`r${i}`" class="inner">
            <rect class="slot" :x="t.x" :y="t.y" :width="t.w" :height="TURN_H" rx="7" />
            <rect class="bar lane-3" :x="t.x" :y="t.y" :width="t.w" :height="TURN_H" rx="7" />
            <text class="turn-name" :x="t.x + t.w / 2" :y="t.y + 16" text-anchor="middle">its turn</text>
          </g>
        </g>

        <g class="refused">
          <rect class="slot" :x="L.refused.x" :y="L.refused.y" :width="L.refused.w" :height="TURN_H" rx="7" />
          <rect class="bar lane-5" :x="L.refused.x" :y="L.refused.y" :width="L.refused.w" :height="TURN_H" rx="7" />
          <line class="cross" :x1="L.refused.x + L.refused.w / 2 - 8" :y1="L.refused.y + 4" :x2="L.refused.x + L.refused.w / 2 + 8" :y2="L.refused.y + 20" />
          <line class="cross" :x1="L.refused.x + L.refused.w / 2 + 8" :y1="L.refused.y + 4" :x2="L.refused.x + L.refused.w / 2 - 8" :y2="L.refused.y + 20" />
          <text class="caption refused-word" :x="L.refused.x + L.refused.w / 2" :y="L.refused.y + TURN_H + 18" text-anchor="middle">refused</text>
        </g>

        <g :transform="`translate(${L.stamp.x} ${L.stamp.y})`">
          <g class="stamp">
            <rect :x="narrow ? -166 : -170" y="-17" :width="narrow ? 332 : 340" height="34" rx="17" />
            <text y="5" text-anchor="middle">budget reached · the run ends, exit 0</text>
          </g>
        </g>
      </g>
    </svg>
    <canvas ref="canvas" />
    </div>
  </HmzStage>
</template>

<style scoped>

/* The camera moves this layer, so the light on the canvas moves with the drawing under it. */
.cam svg,
.cam canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.cam canvas {
  pointer-events: none;
}
svg {
  font-family: var(--vp-font-family-base);
}

.ring-track {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 7;
}

.ring-alarm {
  fill: none;
  stroke: var(--hmz-lane-5);
  stroke-width: 7;
}

.ring-fill {
  fill: none;
  stroke-width: 7;
  stroke-linecap: round;
}

.value {
  font-family: var(--vp-font-family-mono);
  font-size: 19px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.limit {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.name {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  fill: var(--hmz-stage-ink);
}

.caption {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.slot {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 3 3;
}

.bar.lane-1 {
  fill: var(--hmz-lane-1);
}

.bar.lane-3 {
  fill: var(--hmz-lane-3);
}

.bar.lane-5 {
  fill: var(--hmz-lane-5);
}

.turn-name {
  font-size: 11px;
  font-weight: 600;
  fill: var(--vp-c-bg);
  pointer-events: none;
}

.review-frame {
  fill: color-mix(in srgb, var(--hmz-lane-3) 8%, transparent);
  stroke: var(--hmz-lane-3);
  stroke-width: 1.5;
}

.chip text {
  font-family: var(--vp-font-family-mono);
  font-size: 16px;
  font-weight: 700;
  fill: var(--hmz-warm);
}

.chip .chip-asked {
  fill: var(--hmz-stage-dim);
}

.chip-strike {
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
}

.cross {
  stroke: var(--vp-c-bg);
  stroke-width: 2.5;
  stroke-linecap: round;
}

.refused-word {
  fill: var(--hmz-lane-5);
}

.stamp rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-5);
  stroke-width: 1.5;
}

.stamp text {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.halo {
  opacity: var(--hmz-glow);
}

.tick {
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.4;
  stroke-linecap: round;
  opacity: 0.6;
}

.hand {
  stroke-width: 3;
  stroke-linecap: round;
}

.formula text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.first text {
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  fill: var(--hmz-lane-5);
}
</style>
