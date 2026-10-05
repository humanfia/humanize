<script setup lang="ts">
// A loop that is stopped, and picked up. What the flow keeps (`ctx.state`, see
// `docs/reference/flows.md#a-flow-that-can-be-picked-up`) is saved the moment it is written,
// so a run stopped mid-round still has the last round it finished, and the copies it made are
// kept. A run picking it up is a new run: it names the run it carries on, starts the flow's
// code from the top (so a fix made in between is what runs), opens new sessions -- the
// conversation does not come back -- and has a budget of its own. A simulation: the rounds and
// the spend are invented.
import { computed, ref, useId } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'
import { rig, type Point, type Shot } from '../motion/camera'

const BEATS = [
  'A loop keeps every round it finishes',
  'Pull the plug: the run stops',
  'What it kept survives the stop',
  'Picked up: round 41 follows 40',
  'A new session, its own budget, the latest code',
]

/** The rounds each run finishes, and the one the first run is in when it stops. */
const FIRST = [37, 38, 39, 40]
const CUT = 41
const SECOND = [41, 42]
const ALL = [...FIRST, CUT, 42]

interface Layout {
  w: number
  h: number
  lanes: number[]
  laneH: number
  /** Where a run's name, its code, and (for the second) what it carries on stand. */
  name: Point
  tag: Point
  carries: Point
  session: { x: number; dy: number; w: number }
  col: (n: number) => number
  tileW: number
  tileDy: number
  budget: { x: number; dy: number; w: number }
  kept: { x: number; y: number; w: number; h: number }
  code: { x: number; y: number; w: number; h: number }
  shots: Record<'open' | 'drift' | 'stop' | 'kept' | 'pick', Partial<Shot>>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  lanes: [80, 164],
  laneH: 68,
  name: { x: 44, y: -12 },
  tag: { x: 44, y: 5 },
  carries: { x: 44, y: 22 },
  session: { x: 134, dy: -20, w: 100 },
  col: (n) => 250 + (n - 37) * 50,
  tileW: 42,
  tileDy: 0,
  budget: { x: 556, dy: -3, w: 56 },
  kept: { x: 330, y: 236, w: 200, h: 92 },
  code: { x: 150, y: 252, w: 150, h: 60 },
  shots: {
    open: { x: 250, y: 110, s: 1.3 },
    drift: { x: 330, y: 150, s: 1.05 },
    stop: { x: 440, y: 90, s: 1.7 },
    kept: { x: 340, y: 270, s: 1.35 },
    pick: { x: 320, y: 172, s: 1.08 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 400,
  lanes: [96, 208],
  laneH: 92,
  name: { x: 22, y: -26 },
  tag: { x: 70, y: -26 },
  carries: { x: 22, y: 41 },
  session: { x: 20, dy: -12, w: 94 },
  col: (n) => 124 + (n - 37) * 38,
  tileW: 34,
  tileDy: 8,
  budget: { x: 262, dy: -33, w: 78 },
  kept: { x: 20, y: 282, w: 190, h: 92 },
  code: { x: 222, y: 290, w: 118, h: 76 },
  shots: {
    open: { x: 180, y: 110, s: 1.2 },
    drift: { x: 180, y: 150, s: 1.05 },
    stop: { x: 260, y: 104, s: 1.5 },
    kept: { x: 180, y: 300, s: 1.05 },
    pick: { x: 180, y: 200, s: 1.04 },
  },
}

const id = useId()
const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const TILE_H = 32

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const at = (sel: string) => q(sel)
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), far: one('.far'), fx: () => fx, start: l.shots.open })
    const c = {
      one: () => palette.lane[0],
      two: () => palette.accent,
      warm: () => palette.warm,
      danger: () => palette.danger,
      kept: () => palette.accent2,
    }
    const tile = (lane: number, n: number) => one(`.lane-${lane} .tile-${n}`)
    const fill = (lane: number, n: number) => one(`.lane-${lane} .tile-${n} .fill`)
    const tileC = (lane: number, n: number) => ({ x: l.col(n) + l.tileW / 2, y: l.lanes[lane] + l.tileDy })
    const keptTop = { x: l.kept.x + l.kept.w / 2, y: l.kept.y }
    const round = one('.kept-round')
    const bubbles = (lane: number) => at(`.lane-${lane} .bubble`)
    const budget = (lane: number) => one(`.lane-${lane} .budget-fill`)

    // A clean slate every loop.
    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.slot'), { autoAlpha: 1 }, 0)
    tl.set(at('.cut, .lane, .tile, .kept, .code, .bubble, .flash, .stopped, .link, .glow, .edited, .code-dot, .fresh, .ring'), { autoAlpha: 0 }, 0)
    tl.set(at('.fill'), { scaleX: 0, autoAlpha: 1, transformOrigin: '0% 50%' }, 0)
    tl.set(at('.tile-word'), { autoAlpha: 0 }, 0)
    tl.set(at('.budget-fill'), { scaleX: 1, transformOrigin: '0% 50%' }, 0)
    tl.set(at('.lane-0 .lane-dim'), { autoAlpha: 1 }, 0)
    tl.set(at('.link-line, .edit-line'), { drawSVG: '0%' }, 0)
    tl.set(round, { text: 'round: 36' }, 0)
    tl.set(at('.cut-line, .axis-line'), { drawSVG: '0%' }, 0)
    tl.set(at('.axis-word, .cut-flow'), { autoAlpha: 0 }, 0)
    if (!narrow.value) tl.set(at('.state-name'), { autoAlpha: 0 }, 0)
    tl.set(at('.cut-line'), { autoAlpha: 1 }, 0)

    // 0 · round after round, each one kept the moment it is written down.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.lane-0'), { autoAlpha: 0, x: -20 }, { autoAlpha: 1, x: 0, duration: 0.7 }, 0.1)
    tl.fromTo(one('.kept'), { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: 0.7 }, 0.3)
    cam.shot(l.shots.drift, 0.4, 4.2, 'sine.inOut')
    // The rounds stand on one axis across both runs, so a round has one place whichever run
    // takes it.
    tl.to(at('.axis-line'), { drawSVG: '100%', duration: 1.6, ease: 'cine' }, 0.2)
    tl.fromTo(at('.axis-word'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, 1.2)
    if (!narrow.value) tl.fromTo(at('.state-name'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, 0.9)
    const STEP = 0.95
    FIRST.forEach((n, i) => {
      const t = 0.7 + i * STEP
      tl.set(tile(0, n), { autoAlpha: 1 }, t)
      tl.to(fill(0, n), { scaleX: 1, duration: STEP - 0.25, ease: 'power1.inOut' }, t)
      tl.set(q(`.lane-0 .tile-${n} .slot`), { autoAlpha: 0 }, t + STEP - 0.25)
      tl.fromTo(q(`.lane-0 .tile-${n} .tile-word`), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.3, ease: 'back.out(3)' }, t + STEP - 0.3)
      tl.to(bubbles(0)[i], { autoAlpha: 1, duration: 0.25 }, t + 0.2)
      cam.beam(tileC(0, n), keptTop, c.kept, t + STEP - 0.25, { duration: 0.55, bend: 0.15, burst: 8 })
      tl.set(round, { text: `round: ${n}` }, t + STEP + 0.3)
      tl.fromTo(one('.kept-pulse'), { autoAlpha: 0.9 }, { autoAlpha: 0, duration: 0.5 }, t + STEP + 0.3)
      tl.to(budget(0), { scaleX: 1 - (i + 1) * 0.16, duration: 0.4 }, t + STEP - 0.2)
    })
    // Round 41 starts, and will not finish.
    const TC = 0.7 + FIRST.length * STEP
    tl.set(tile(0, CUT), { autoAlpha: 1 }, TC)
    tl.to(fill(0, CUT), { scaleX: 0.55, duration: 1.1, ease: 'none' }, TC)

    // 1 · the plug is pulled: a flash, a jolt, and the round under way is gone.
    const T1 = TC + 0.9
    tl.addLabel('beat-1', T1 - 0.3)
    cam.shot(l.shots.stop, T1 - 0.3, 0.5, 'cine.out')
    tl.fromTo(one('.flash'), { autoAlpha: 0.75 }, { autoAlpha: 0, duration: 0.7, ease: 'power2.out' }, T1 + 0.2)
    tl.fromTo(one('.shake'), { x: 0 }, { keyframes: { x: [0, -7, 6, -4, 3, 0] }, duration: 0.45, ease: 'none' }, T1 + 0.2)
    cam.flare(tileC(0, CUT), c.danger, T1 + 0.2, 34, 150)
    tl.to(fill(0, CUT), { autoAlpha: 0, duration: 0.5 }, T1 + 0.25)
    // Where it stopped, marked down through both runs: the second will pick up on this line.
    tl.to(at('.cut-line'), { drawSVG: '100%', duration: 0.7, ease: 'cine' }, T1 + 0.3)
    // Drawn, the line turns to a current running down it: from where one run stopped to where
    // the next picks up.
    tl.to(at('.cut-line'), { autoAlpha: 0, duration: 0.5 }, T1 + 1.1)
    tl.to(at('.cut-flow'), { autoAlpha: 0.8, duration: 0.5 }, T1 + 1.1)
    tl.to(q(`.lane-0 .tile-${CUT} .cut`), { autoAlpha: 1, duration: 0.3 }, T1 + 0.25)
    tl.fromTo(at('.lane-0 .stopped'), { autoAlpha: 0, scale: 1.5, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(2)' }, T1 + 0.3)
    tl.to(one('.lane-0 .lane-dim'), { autoAlpha: 0.55, duration: 0.8 }, T1 + 0.9)
    tl.to(FIRST.map((n) => fill(0, n)), { autoAlpha: 0.55, duration: 0.8 }, T1 + 0.9)

    // 2 · what it kept is still there: the last round it finished, and the copies it made.
    // Meanwhile, somebody fixes the flow.
    const T2 = T1 + 1.5
    tl.addLabel('beat-2', T2)
    cam.shot(l.shots.kept, T2, 1.4)
    tl.fromTo(one('.ring'), { autoAlpha: 0.9, scale: 0.9, transformOrigin: '50% 50%' }, { autoAlpha: 0, scale: 1.25, duration: 1.1, ease: 'power2.out' }, T2 + 0.8)
    tl.to(one('.kept .glow'), { autoAlpha: 1, duration: 0.6 }, T2 + 0.8)
    tl.fromTo(at('.kept-row'), { x: 0 }, { keyframes: { x: [0, 4, 0] }, duration: 0.35, stagger: 0.2 }, T2 + 0.9)
    tl.fromTo(one('.code'), { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.5 }, T2 + 1.2)
    tl.to(at('.edited'), { autoAlpha: 1, duration: 0.2 }, T2 + 1.8)
    tl.to(one('.edit-line'), { drawSVG: '100%', duration: 0.6, ease: 'power1.inOut' }, T2 + 1.8)
    tl.fromTo(one('.code .code-dot'), { autoAlpha: 0, scale: 0, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.3, ease: 'back.out(3)' }, T2 + 2.4)
    cam.flare({ x: l.code.x + l.code.w - 16, y: l.code.y + 18 }, c.warm, T2 + 2.4, 12, 60)

    // 3 · picked up: a new run, naming the one it carries on, starts from what was kept.
    const T3 = T2 + 3.0
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.pick, T3, 1.4)
    tl.fromTo(one('.lane-1'), { autoAlpha: 0, y: 24 }, { autoAlpha: 1, y: 0, duration: 0.7 }, T3 + 0.3)
    tl.to(one('.link'), { autoAlpha: 1, duration: 0.1 }, T3 + 0.6)
    tl.to(one('.link-line'), { drawSVG: '100%', duration: 0.7, ease: 'cine' }, T3 + 0.6)
    cam.beam(keptTop, tileC(1, CUT), c.kept, T3 + 1.0, { duration: 0.8, bend: -0.2, burst: 18, size: 3 })
    SECOND.forEach((n, i) => {
      const t = T3 + 1.7 + i * STEP
      tl.set(tile(1, n), { autoAlpha: 1 }, t)
      tl.to(fill(1, n), { scaleX: 1, duration: STEP - 0.25, ease: 'power1.inOut' }, t)
      tl.set(q(`.lane-1 .tile-${n} .slot`), { autoAlpha: 0 }, t + STEP - 0.25)
      tl.fromTo(q(`.lane-1 .tile-${n} .tile-word`), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.3, ease: 'back.out(3)' }, t + STEP - 0.3)
      tl.to(bubbles(1)[i], { autoAlpha: 1, duration: 0.25 }, t + 0.2)
      cam.beam(tileC(1, n), keptTop, c.kept, t + STEP - 0.25, { duration: 0.5, bend: 0.2, burst: 8 })
      tl.set(round, { text: `round: ${n}` }, t + STEP + 0.25)
      tl.fromTo(one('.kept-pulse'), { autoAlpha: 0.9 }, { autoAlpha: 0, duration: 0.5 }, t + STEP + 0.25)
      tl.to(budget(1), { scaleX: 1 - (i + 1) * 0.12, duration: 0.4 }, t + STEP - 0.2)
    })
    cam.flare(tileC(1, CUT), c.two, T3 + 1.7 + STEP - 0.3, 20, 90)

    // 4 · what is new about it: its session, its budget, and the code it runs.
    const T4 = T3 + 1.7 + SECOND.length * STEP + 0.1
    tl.addLabel('beat-4', T4)
    cam.shot({ x: l.w / 2, y: l.h / 2, s: 1 }, T4, 1.5)
    tl.fromTo(at('.lane-1 .fresh'), { autoAlpha: 0, scale: 0.8, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4, stagger: 0.5, ease: 'back.out(2)' }, T4 + 0.6)
    cam.beam({ x: l.code.x + l.code.w / 2, y: l.code.y }, { x: l.tag.x + 24, y: l.lanes[1] + l.tag.y + 4 }, c.warm, T4 + 1.4, { duration: 0.8, bend: -0.25, burst: 12 })
    tl.fromTo(one('.lane-1 .code-dot'), { autoAlpha: 0, scale: 0, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.3, ease: 'back.out(3)' }, T4 + 2.1)
    tl.addLabel('rest', T4 + 2.6)

    // Under it all, what keeps a held frame alive: the stop line's dashes creep, and the kept
    // state breathes. Over the whole timeline, so a seek lands on it like on anything else.
    const D = T4 + 5.6
    const loops = (period: number) => Math.max(0, Math.floor(D / period) - 1)
    tl.fromTo(at('.cut-flow'), { strokeDashoffset: 0 }, { strokeDashoffset: -D * 8, duration: D, ease: 'none' }, 0)
    tl.fromTo(at('.kept-breath'), { opacity: 0.15 }, { opacity: 0.6, duration: 1.3, ease: 'sine.inOut', yoyo: true, repeat: loops(1.3) }, 0)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 5.0)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 10"
    label="A loop, stopped and picked up. Run 1 finishes rounds 37 to 40, each saved as the flow's kept state the moment it is written, in session A. The plug is pulled during round 41, which is lost. What the flow kept, round 40 and the copies it made, survives; meanwhile the flow's code is fixed. Run 2 picks up run 1: it starts from what was kept and finishes round 41, then 42, in a new session B, with a budget of its own, running the fixed code."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <pattern :id="`${id}-dots`" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" class="grid-dot" />
        </pattern>
        <radialGradient :id="`${id}-glow`">
          <stop offset="0" stop-color="var(--hmz-accent-2)" stop-opacity="0.5" />
          <stop offset="1" stop-color="var(--hmz-accent-2)" stop-opacity="0" />
        </radialGradient>
      </defs>

      <g class="far"><rect x="-400" y="-400" :width="L.w + 800" :height="L.h + 800" :fill="`url(#${id}-dots)`" /></g>

      <g class="world">
        <g class="shake">
          <!-- run 2 carries on run 1. -->
          <g class="link">
            <path
              class="link-line"
              :d="narrow
                ? `M14 ${L.lanes[0] + 20} C 2 ${L.lanes[0] + 60}, 2 ${L.lanes[1] - 60}, 14 ${L.lanes[1] - 20}`
                : `M38 ${L.lanes[0] + 10} C 14 ${L.lanes[0] + 40}, 14 ${L.lanes[1] - 40}, 38 ${L.lanes[1] - 10}`"
            />
          </g>

          <g v-for="(lane, k) in L.lanes" :key="k" class="lane" :class="`lane-${k}`">
            <g class="lane-dim">
              <rect class="band" :x="narrow ? 10 : 32" :y="lane - L.laneH / 2" :width="L.w - (narrow ? 20 : 46)" :height="L.laneH" rx="14" />
              <text class="run-name" :x="L.name.x" :y="lane + L.name.y">run {{ k + 1 }}</text>
              <g :transform="`translate(${L.tag.x} ${lane + L.tag.y})`">
                <text class="code-tag">flow.py</text>
                <circle class="code-dot" cx="54" cy="-4" r="3.5" />
              </g>
              <text v-if="k === 1" class="carries" :x="L.carries.x" :y="lane + L.carries.y">picks up run 1</text>

              <!-- Its session: a conversation that only it has. -->
              <g :transform="`translate(${L.session.x} ${lane + L.session.dy})`">
                <rect class="session" :width="L.session.w" height="40" rx="8" />
                <text class="session-name" x="8" y="15">session {{ k ? 'B' : 'A' }}</text>
                <rect v-for="b in 4" :key="b" class="bubble" :class="{ own: k }" :x="8 + (b - 1) * 21" y="24" width="17" height="7" rx="3.5" />
                <g v-if="k" :transform="`translate(${L.session.w - 4} 0)`">
                  <g class="fresh">
                    <rect x="-26" y="-9" width="30" height="16" rx="8" />
                    <text x="-11" y="3" text-anchor="middle">new</text>
                  </g>
                </g>
              </g>

              <!-- Its budget. -->
              <g :transform="`translate(${L.budget.x} ${lane + L.budget.dy})`">
                <text class="budget-word" x="0" y="-6">budget</text>
                <rect class="budget-track" :width="L.budget.w" height="7" rx="3.5" />
                <rect class="budget-fill" :width="L.budget.w" height="7" rx="3.5" />
                <g v-if="k" :transform="`translate(${narrow ? L.budget.w - 15 : L.budget.w / 2} ${narrow ? -10 : 22})`">
                  <g class="fresh">
                    <rect x="-15" y="-8" width="30" height="16" rx="8" />
                    <text y="4" text-anchor="middle">own</text>
                  </g>
                </g>
              </g>
            </g>

            <!-- Its rounds, on one axis across both runs. -->
            <g v-for="n in ALL" :key="n" class="tile" :class="`tile-${n}`">
              <rect class="slot" :x="L.col(n)" :y="lane + L.tileDy - TILE_H / 2" :width="L.tileW" :height="TILE_H" rx="7" />
              <rect v-if="!k && n === CUT" class="slot cut" :x="L.col(n)" :y="lane + L.tileDy - TILE_H / 2" :width="L.tileW" :height="TILE_H" rx="7" />
              <rect class="fill" :class="k ? 'two' : 'one'" :x="L.col(n)" :y="lane + L.tileDy - TILE_H / 2" :width="L.tileW" :height="TILE_H" rx="7" />
              <g class="tile-word"><text :x="L.col(n) + L.tileW / 2" :y="lane + L.tileDy + 5" text-anchor="middle">{{ n }}</text></g>
              <g v-if="!k && n === CUT" :transform="`translate(${L.col(n) + L.tileW / 2 + 10} ${lane + L.tileDy - TILE_H / 2 - 4}) rotate(-8)`">
                <g class="stopped">
                  <rect x="-34" y="-10" width="68" height="20" rx="10" />
                  <text y="4" text-anchor="middle">stopped</text>
                </g>
              </g>
            </g>
          </g>

          <!-- The axis the rounds stand on, and the line where the first run stopped. -->
          <g :transform="`translate(0 ${L.lanes[1] + L.laneH / 2 + 10})`">
            <line class="axis-line" :x1="L.col(37) - 6" :x2="L.col(42) + L.tileW + 6" y1="0" y2="0" />
            <text class="axis-word" :x="L.col(42) + L.tileW + 6" y="14" text-anchor="end">round →</text>
          </g>
          <g>
            <line class="cut-line" :x1="L.col(CUT) + L.tileW / 2" :x2="L.col(CUT) + L.tileW / 2" :y1="L.lanes[0] - L.laneH / 2 - 6" :y2="L.lanes[1] + L.laneH / 2 + 4" />
            <line class="cut-flow" :x1="L.col(CUT) + L.tileW / 2" :x2="L.col(CUT) + L.tileW / 2" :y1="L.lanes[0] - L.laneH / 2 - 6" :y2="L.lanes[1] + L.laneH / 2 + 4" />
          </g>

          <!-- What the flow kept. -->
          <g class="kept">
            <g :transform="`translate(${L.kept.x + L.kept.w / 2} ${L.kept.y + L.kept.h / 2})`">
              <circle class="glow" :r="L.kept.w * 0.7" :fill="`url(#${id}-glow)`" />
              <rect class="ring" :x="-L.kept.w / 2" :y="-L.kept.h / 2" :width="L.kept.w" :height="L.kept.h" rx="14" />
            </g>
            <rect class="kept-box" :x="L.kept.x" :y="L.kept.y" :width="L.kept.w" :height="L.kept.h" rx="14" />
            <rect class="kept-pulse" :x="L.kept.x" :y="L.kept.y" :width="L.kept.w" :height="L.kept.h" rx="14" />
            <rect class="kept-breath" :x="L.kept.x - 4" :y="L.kept.y - 4" :width="L.kept.w + 8" :height="L.kept.h + 8" rx="17" />
            <text v-if="!narrow" class="state-name" :x="L.kept.x + L.kept.w - 14" :y="L.kept.y + 50" text-anchor="end">ctx.state</text>
            <text class="kept-head" :x="L.kept.x + 14" :y="L.kept.y + 22">what the flow kept</text>
            <g class="kept-row">
              <text class="kept-round" :x="L.kept.x + 14" :y="L.kept.y + 50">round: 36</text>
            </g>
            <g class="kept-row">
              <text class="kept-copies" :x="L.kept.x + 14" :y="L.kept.y + 76">copies it made ✓</text>
            </g>
          </g>

          <!-- The flow's code, fixed while nothing runs. -->
          <g class="code">
            <rect class="code-box" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="L.code.h" rx="10" />
            <text class="kept-head" :x="L.code.x + 12" :y="L.code.y + 22">the flow</text>
            <text class="code-name" :x="L.code.x + 12" :y="L.code.y + (narrow ? 44 : 42)">flow.py</text>
            <circle class="code-dot" :cx="L.code.x + L.code.w - 16" :cy="L.code.y + 18" r="4.5" />
            <g class="edited">
              <line class="edit-line" :x1="L.code.x + 12" :x2="L.code.x + 64" :y1="L.code.y + (narrow ? 50 : 48)" :y2="L.code.y + (narrow ? 50 : 48)" />
            </g>
            <text v-if="narrow" class="edited code-fixed" :x="L.code.x + 12" :y="L.code.y + 66">fixed</text>
            <text v-else class="edited code-fixed" :x="L.code.x + 74" :y="L.code.y + 42">fixed</text>
          </g>
        </g>

        <rect class="flash" x="-400" y="-400" :width="L.w + 800" :height="L.h + 800" />
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.grid-dot {
  fill: var(--hmz-stage-line);
}

.band {
  fill: color-mix(in srgb, var(--hmz-lane-1) 5%, transparent);
  stroke: var(--hmz-stage-line);
}

.lane-1 .band {
  fill: color-mix(in srgb, var(--hmz-accent) 6%, transparent);
}

.run-name {
  font-size: 14px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.code-tag {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.code-dot {
  fill: var(--hmz-warm);
}

.carries {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-accent);
}

.session {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.2;
}

.lane-1 .session {
  stroke: var(--hmz-accent);
}

.session-name {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.bubble {
  fill: var(--hmz-lane-1);
}

.bubble.own {
  fill: var(--hmz-accent);
}

.fresh rect {
  fill: var(--hmz-accent);
}

.fresh text {
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-bg);
}

.budget-word {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.budget-track {
  fill: var(--hmz-stage-line);
}

.budget-fill {
  fill: var(--hmz-warm);
}

.stopped rect {
  fill: var(--hmz-lane-5);
}

.stopped text {
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-bg);
  letter-spacing: 0.04em;
}

.slot {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 3 3;
}

.slot.cut {
  stroke: var(--hmz-lane-5);
  stroke-width: 1.5;
}

.fill.one {
  fill: var(--hmz-lane-1);
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
}

.fill.two {
  fill: var(--hmz-accent);
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.axis-line {
  stroke: var(--hmz-stage-dim);
  stroke-width: 1;
}

.axis-word {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  fill: var(--hmz-stage-dim);
}

.cut-line {
  stroke: var(--hmz-lane-5);
  stroke-width: 1.2;
  opacity: 0.55;
}

.cut-flow {
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
  stroke-dasharray: 2 6;
  stroke-linecap: round;
}

.state-name {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  fill: var(--hmz-accent-2);
}

.kept-breath {
  fill: none;
  stroke: var(--hmz-accent-2);
  stroke-width: 1;
  stroke-dasharray: 3 4;
}

.tile-word text {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 700;
  fill: var(--vp-c-white);
}

.glow {
  opacity: var(--hmz-glow);
}

.ring {
  fill: none;
  stroke: var(--hmz-accent-2);
  stroke-width: 2;
}

.kept-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent-2);
  stroke-width: 1.5;
}

.kept-pulse {
  fill: color-mix(in srgb, var(--hmz-accent-2) 22%, transparent);
  opacity: 0;
}

.kept-head {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.kept-round {
  font-family: var(--vp-font-family-mono);
  font-size: 18px;
  font-weight: 700;
  fill: var(--hmz-accent-2);
}

.kept-copies {
  font-size: 12px;
  fill: var(--hmz-stage-ink);
}

.code-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.code-name {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.edit-line {
  stroke: var(--hmz-warm);
  stroke-width: 2.5;
  stroke-linecap: round;
}

.code-fixed {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-warm);
}

.link-line {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.8;
  stroke-dasharray: 4 4;
}

.flash {
  fill: var(--hmz-lane-5);
  fill-opacity: 0.4;
}
</style>
