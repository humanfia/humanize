<script setup lang="ts">
// Two ways a turn keeps going. Left, the CLI's own goal (`/goal <objective>`): a turn that would
// have ended starts another, until the model judges the objective met, and the flow gets the
// last turn's answer. Each turn is drawn as one lap of a spiral closing in on the objective, and
// what it came to is plotted under it. Right, the same thing by hand: a hook on the end of the
// turn reads TASK.md and sends the agent back while boxes are unticked, told each time how often
// it already has. Which CLIs have a goal is `pursues` in `hmz/coganchor/agents/`, and the
// flow-level `GoalCommandAgentMixin` in `hmz/flows/agents.py`. The turns are invented.
import { computed, ref, useId } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { rig } from '../motion/camera'
import { createFx, type Fx } from '../motion/fx'
import { motion } from '../motion/gsap'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'

const BEATS = [
  'A goal instead of a prompt',
  'It keeps taking turns',
  'Until the model judges it met',
  'Or a hook sends the turn back',
  'Until your own check passes',
]

// What each of the goal's turns comes to: the tests still failing after it, and how it reads.
const LAPS = [
  { failing: 3, word: '3 failing' },
  { failing: 1, word: '1 failing' },
  { failing: 0, word: 'suite passes' },
  { failing: 0, word: 'judged met' },
]
const ITEMS = ['port the parser', 'port the printer', 'port the CLI']

// The world is one 640 × 360 plane in both layouts: the goal on its left half, the hook on its
// right. Only the camera differs, and the screen it looks through.
const C = { x: 160, y: 150 }
// One ellipse per lap, each a little tighter than the last: the turns close in on the goal.
const RINGS = [
  { rx: 128, ry: 70 },
  { rx: 120, ry: 62 },
  { rx: 112, ry: 55 },
  { rx: 104, ry: 48 },
]
// A lap is half of its own ellipse, then half of one between it and the next, so the laps join
// into a single spiral: each starts exactly where the last one ended, at the bottom.
function lapPath(i: number) {
  const a = RINGS[i]
  const b = RINGS[i + 1] ?? a
  const rx = (a.rx + b.rx) / 2
  const ry = (a.ry + b.ry) / 2
  return `M${C.x} ${C.y + a.ry} A${a.rx} ${a.ry} 0 0 1 ${C.x} ${C.y - a.ry} A${rx} ${ry} 0 0 1 ${C.x} ${C.y + b.ry}`
}
const LAP_D = RINGS.map((_, i) => lapPath(i))
const LAST = RINGS[RINGS.length - 1]

// The plot under the spiral: tests failing, turn by turn.
const PLOT = { x0: 168, x1: 292, y0: 296, top: 240, step: 16 }
const pt = (i: number) => ({ x: 186 + i * 28, y: PLOT.y0 - LAPS[i].failing * PLOT.step })
const POINTS = LAPS.map((_, i) => pt(i))

const FLOW = [
  { x: 84, y: 306 },
  { x: 480, y: 306 },
]
const EXIT_D = `M${C.x} ${C.y + LAST.ry} C${C.x} 240 ${FLOW[0].x} 244 ${FLOW[0].x} ${FLOW[0].y - 14}`

const TRACK = { x0: 350, x1: 548, y: 206 }
const GATE = { x: 596, y: 206 }
const BACK_D = `M${GATE.x - 12} ${TRACK.y - 12} C${GATE.x - 12} 156 ${TRACK.x0} 156 ${TRACK.x0} ${TRACK.y - 12}`
const PASS_D = `M${GATE.x + 10} ${TRACK.y} C${GATE.x + 40} ${TRACK.y} ${GATE.x + 40} ${FLOW[1].y} ${FLOW[1].x + 46} ${FLOW[1].y}`

interface Shot {
  x: number
  y: number
  s: number
}

interface Layout {
  w: number
  h: number
  /** Where the hook's half sits against the goal's: beside it, or under it on a phone. */
  off: { x: number; y: number }
  open: Shot
  goal: Shot
  plot: Shot
  hook: Shot
  both: Shot
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  off: { x: 0, y: 0 },
  open: { x: 160, y: 150, s: 1.5 },
  goal: { x: 168, y: 184, s: 1.12 },
  plot: { x: 196, y: 238, s: 1.55 },
  hook: { x: 472, y: 186, s: 1.12 },
  both: { x: 320, y: 184, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 560,
  off: { x: -318, y: 300 },
  open: { x: 160, y: 150, s: 1.45 },
  goal: { x: 160, y: 196, s: 1.08 },
  plot: { x: 196, y: 248, s: 1.5 },
  hook: { x: 156, y: 486, s: 1.1 },
  both: { x: 160, y: 336, s: 0.92 },
}

const id = useId()
const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const gsap = motion()
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const at = (sel: string) => q(sel)
    const one = (sel: string) => q(sel)[0]
    const world = one('.world')
    const comet = one('.comet')
    const pill = one('.pill')

    const cam = rig(tl, { w: l.w, h: l.h, world, far: one('.far'), fx: () => fx, start: l.open })
    const spark = (x: number, y: number, color: () => string, n: number, when: number, speed = 90) => cam.flare({ x, y }, color, when, n, speed)
    const trail = (el: Element, color: () => string, size = 2.6) => () => {
      const o = el === pill ? l.off : { x: 0, y: 0 }
      const p = cam.view({ x: Number(gsap.getProperty(el, 'x')) + o.x, y: Number(gsap.getProperty(el, 'y')) + o.y })
      fx?.trail(p.x, p.y, color(), size)
    }
    const along = (el: Element, path: string, when: number, duration: number, color: () => string, ease = 'power1.inOut') =>
      tl.to(el, { motionPath: { path, start: 0, end: 1 }, duration, ease, onUpdate: trail(el, color) }, when)

    // Where a loop starts.
    tl.set(world, { autoAlpha: 1 }, 0)
    tl.set(at('.check-glow, .gate-glow, .card, .answer, .counter, .pt, .pt-ring, .comet-halo'), { transformOrigin: '50% 50%', smoothOrigin: false }, 0)
    tl.set(at('.comet, .pill, .answer, .check, .scan, .gate-ok, .gate-no, .counter, .tick, .pt, .pt-ring, .met, .readout-g, .plot, .hook-note'), { opacity: 0 }, 0)
    tl.set(at('.check-glow, .gate-glow'), { opacity: 0 }, 0)
    tl.set(at('.obj'), { text: '' }, 0)
    tl.set(at('.readout'), { text: '' }, 0)
    tl.set(at('.item'), { opacity: 1 }, 0)
    tl.set(at('.strike, .trace, .seg, .axis-x, .axis-y, .cross'), { drawSVG: '0%' }, 0)
    tl.set(at('.trace, .cross, .ring-0'), { opacity: 1 }, 0)
    tl.set(at('.back, .pass'), { opacity: 0, drawSVG: '0%' }, 0)
    tl.set(at('.hook-half'), { opacity: 0.25 }, 0)
    tl.set(at('.goal-half'), { opacity: 1 }, 0)
    tl.set(at('.grid'), { opacity: 0 }, 0)
    tl.set(comet, { x: C.x, y: C.y + RINGS[0].ry }, 0)
    tl.set(pill, { x: TRACK.x0, y: TRACK.y }, 0)

    // 0 · a goal, not a prompt. The construction first -- the paper, the axes through the
    // objective -- then the first ring drawn round it, and the objective written in.
    tl.addLabel('beat-0', 0)
    cam.shot(l.goal, 0.2, 2.6)
    tl.to(at('.grid'), { opacity: 0.6, duration: 1.2, ease: 'power1.out' }, 0)
    tl.to(at('.cross'), { drawSVG: '100%', duration: 0.9, stagger: 0.12, ease: 'cine' }, 0.05)
    tl.fromTo(at('.hub'), { scale: 0, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.5, ease: 'back.out(3)' }, 0.3)
    tl.fromTo(at('.ring-0'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.4, ease: 'cine' }, 0.4)
    tl.fromTo(at('.card'), { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.6 }, 0.6)
    const obj = at('.obj')
    tl.to(obj[0], { text: { value: 'the suite passes,' }, duration: 0.6, ease: 'none' }, 1.0)
    tl.to(obj[1], { text: { value: 'nothing stubbed out' }, duration: 0.6, ease: 'none' }, 1.6)
    tl.fromTo(at('.goal-half .title, .flow-slot-0, .flow-word-0'), { opacity: 0 }, { opacity: 1, duration: 0.6 }, 1.1)
    tl.to(at('.cross'), { opacity: 0.35, duration: 0.8 }, 2.0)

    // 1 · turn after turn round the objective, without anyone asking. Each lap is traced as it
    // is run, a little tighter than the last, and what it came to is plotted underneath.
    const T1 = 2.5
    const LAP = 1.4
    tl.addLabel('beat-1', T1)
    tl.to(comet, { opacity: 1, duration: 0.3 }, T1)
    spark(C.x, C.y + RINGS[0].ry, () => palette.lane[0], 14, T1)
    tl.to(at('.plot'), { opacity: 1, duration: 0.4 }, T1)
    tl.to(at('.axis-y'), { drawSVG: '100%', duration: 0.6, ease: 'cine' }, T1)
    tl.to(at('.axis-x'), { drawSVG: '100%', duration: 0.8, ease: 'cine' }, T1 + 0.2)
    tl.to(at('.ring-0'), { opacity: 0.3, duration: 0.8 }, T1)
    const readout = one('.readout')
    LAPS.forEach((lap, i) => {
      const t = T1 + i * LAP
      along(comet, LAP_D[i], t, LAP, () => palette.lane[0], i === 0 ? 'power1.in' : 'none')
      tl.to(at('.trace')[i], { drawSVG: '100%', duration: LAP, ease: i === 0 ? 'power1.in' : 'none' }, t)
      if (i > 0) tl.to(at('.trace')[i - 1], { opacity: 0.32, duration: 0.6 }, t)
      const end = t + LAP - 0.02
      tl.set(readout, { text: `turn ${i + 1} · ${lap.word}` }, end)
      tl.fromTo(one('.readout-g'), { opacity: 0.2, y: 4 }, { opacity: 1, y: 0, duration: 0.35 }, end)
      tl.fromTo(at('.pt')[i], { opacity: 0, scale: 0 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(3)' }, end)
      if (i > 0) tl.to(at('.seg')[i - 1], { drawSVG: '100%', duration: 0.35, ease: 'power1.inOut' }, end - 0.2)
    })

    // 2 · on the last lap the model judges it met. The camera leans in on the plot as the line
    // reaches zero and stays there; the objective lights, and the answer leaves for the flow.
    const T2 = T1 + 3 * LAP
    tl.addLabel('beat-2', T2)
    cam.shot(l.plot, T2 + 0.1, 1.2)
    const J = T2 + LAP
    tl.fromTo(at('.pt-ring'), { opacity: 1, scale: 0.4 }, { opacity: 0, scale: 2.2, duration: 0.9, ease: 'power2.out' }, J)
    tl.fromTo(at('.met'), { opacity: 0, y: 4 }, { opacity: 1, y: 0, duration: 0.4 }, J + 0.1)
    cam.shot(l.goal, J + 0.5, 1.2)
    tl.fromTo(at('.check-glow'), { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1.1, duration: 0.5, ease: 'power2.out' }, J + 0.3)
    tl.fromTo(at('.check'), { opacity: 1, drawSVG: '0%' }, { drawSVG: '100%', duration: 0.4, ease: 'power2.out' }, J + 0.4)
    spark(C.x, C.y, () => palette.accent, 30, J + 0.4, 140)
    along(comet, EXIT_D, J + 0.8, 0.9, () => palette.accent, 'power2.in')
    tl.to(comet, { opacity: 0, duration: 0.15 }, J + 1.7)
    tl.fromTo(at('.answer-0'), { opacity: 0, scale: 1.4 }, { opacity: 1, scale: 1, duration: 0.5, ease: 'back.out(1.8)' }, J + 1.7)
    spark(FLOW[0].x, FLOW[0].y, () => palette.accent, 22, J + 1.7, 110)

    // 3 · pan across: the same loop by hand, a hook on the end of the turn.
    const T3 = J + 2.6
    tl.addLabel('beat-3', T3)
    cam.shot(l.hook, T3, 1.6)
    tl.to(at('.goal-half'), { opacity: 0.25, duration: 1 }, T3)
    tl.to(at('.hook-half'), { opacity: 1, duration: 1 }, T3 + 0.2)
    tl.fromTo(at('.rail'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.9, ease: 'cine' }, T3 + 0.4)
    tl.fromTo(at('.hook-note'), { opacity: 0, y: 4 }, { opacity: 1, y: 0, duration: 0.5 }, T3 + 0.9)
    tl.to(at('.counter'), { opacity: 1, duration: 0.4 }, T3 + 1.2)
    const count = one('.counter-n')
    tl.set(count, { text: '0' }, T3)

    const TRAVEL = 1.3
    const hookLap = (i: number, t: number) => {
      tl.set(one('.pill-n'), { text: `turn ${i + 1}` }, t)
      tl.fromTo(pill, { opacity: 0, x: TRACK.x0, y: TRACK.y, scaleX: 1 }, { opacity: 1, duration: 0.2 }, t)
      tl.to(pill, { x: TRACK.x1, duration: TRAVEL, ease: 'power1.inOut', onUpdate: trail(pill, () => palette.lane[2], 2) }, t)
      // The agent ticks a box on the way.
      tl.to(at('.tick')[i], { opacity: 1, duration: 0.2 }, t + TRAVEL * 0.55)
      tl.fromTo(at('.tick')[i], { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.3 }, t + TRAVEL * 0.55)
      tl.to(at('.strike')[i], { drawSVG: '100%', duration: 0.4 }, t + TRAVEL * 0.6)
      tl.to(at('.item')[i], { opacity: 0.5, duration: 0.4 }, t + TRAVEL * 0.6)
      // The turn arrives at the hook and squashes against it while the hook reads TASK.md.
      const c = t + TRAVEL
      tl.to(pill, { scaleX: 0.86, duration: 0.12, ease: 'power2.out', transformOrigin: '100% 50%' }, c - 0.05)
      tl.to(pill, { scaleX: 1, duration: 0.35, ease: 'back.out(3)' }, c + 0.1)
      tl.fromTo(at('.scan'), { opacity: 1, drawSVG: '0% 0%' }, { drawSVG: '0% 100%', duration: 0.3, ease: 'power2.out' }, c)
      tl.to(at('.scan'), { drawSVG: '100% 100%', duration: 0.25, ease: 'power2.in' }, c + 0.3)
      tl.set(at('.scan'), { opacity: 0 }, c + 0.56)
      return c + 0.55
    }
    const refuse = (i: number, c: number) => {
      tl.fromTo(at('.gate-no'), { opacity: 0 }, { opacity: 1, duration: 0.12, yoyo: true, repeat: 1, repeatDelay: 0.3 }, c)
      tl.fromTo(at('.gate-glow-no'), { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1.1, duration: 0.25, yoyo: true, repeat: 1, repeatDelay: 0.2 }, c)
      spark(GATE.x + l.off.x, GATE.y + l.off.y, () => palette.warm, 20, c, 120)
      tl.set(count, { text: String(i + 1) }, c + 0.2)
      tl.fromTo(at('.counter'), { scale: 1.3 }, { scale: 1, duration: 0.4, ease: 'back.out(2)' }, c + 0.2)
      // The way back is drawn as the turn takes it, then lifts once it is home.
      tl.set(at('.back'), { opacity: 1 }, c + 0.1)
      tl.fromTo(at('.back'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.8, ease: 'power2.inOut' }, c + 0.1)
      tl.to(at('.back'), { opacity: 0, duration: 0.4 }, c + 1)
      along(pill, BACK_D, c + 0.1, 0.9, () => palette.warm, 'power2.inOut')
      tl.to(pill, { opacity: 0, duration: 0.12 }, c + 0.95)
      return c + 1.1
    }
    let t = refuse(0, hookLap(0, T3 + 1.3))

    // 4 · sent back until nothing is unticked, then let through.
    tl.addLabel('beat-4', t)
    t = refuse(1, hookLap(1, t))
    const c = hookLap(2, t)
    tl.to(at('.gate-ok'), { opacity: 1, duration: 0.2 }, c)
    tl.fromTo(at('.gate-glow-ok'), { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1.1, duration: 0.4 }, c)
    spark(GATE.x + l.off.x, GATE.y + l.off.y, () => palette.accent, 22, c, 110)
    tl.set(at('.pass'), { opacity: 1 }, c + 0.15)
    tl.fromTo(at('.pass'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1, ease: 'power2.inOut' }, c + 0.15)
    along(pill, PASS_D, c + 0.15, 1, () => palette.accent, 'power2.inOut')
    tl.to(pill, { opacity: 0, duration: 0.15 }, c + 1.1)
    tl.fromTo(at('.answer-1'), { opacity: 0, scale: 1.4 }, { opacity: 1, scale: 1, duration: 0.5, ease: 'back.out(1.8)' }, c + 1.1)
    spark(FLOW[1].x + l.off.x, FLOW[1].y + l.off.y, () => palette.accent, 22, c + 1.1, 110)

    // Pull back on both, hold, and fade for the loop.
    const E = c + 1.9
    cam.shot(l.both, E, 1.6)
    tl.to(at('.goal-half, .hook-half'), { opacity: 1, duration: 1 }, E)
    tl.to(at('.gate-glow'), { opacity: 0, duration: 0.6 }, E)
    tl.addLabel('rest', E + 1.8)
    tl.to(world, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, E + 4.2)

    // Underneath it all, the slow motion that keeps a still frame alive: the dashes creep along
    // their lines, the comet's halo breathes, the gate idles. Laid over the whole timeline, so a
    // seek lands on it like on anything else.
    const D = tl.duration()
    tl.fromTo(at('.drift'), { strokeDashoffset: 0 }, { strokeDashoffset: -D * 9, duration: D, ease: 'none' }, 0)
    tl.fromTo(at('.comet-halo'), { scale: 0.85 }, { scale: 1.2, duration: 0.7, ease: 'sine.inOut', yoyo: true, repeat: Math.floor(D / 0.7) - 1 }, 0)
    tl.fromTo(at('.gate-idle'), { opacity: 0.15 }, { opacity: 0.55, duration: 1.1, ease: 'sine.inOut', yoyo: true, repeat: Math.floor(D / 1.1) - 1 }, 0)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 14"
    label="Two ways to keep an agent working until the job is done. Left, a goal: the agent takes turn after turn round its objective, each a tighter lap of a spiral, while a plot underneath shows the failing tests falling from three to one to none; the model judges the goal met, and the flow gets the last answer. Right, a hook on the end of the turn reads TASK.md and sends the turn back while boxes are unticked, counting how often it has, and lets it end once every box is ticked."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <pattern :id="`${id}-grid`" width="20" height="20" patternUnits="userSpaceOnUse">
          <path class="grid-minor" d="M20 0 H0 V20" />
        </pattern>
        <pattern :id="`${id}-major`" width="80" height="80" patternUnits="userSpaceOnUse">
          <path class="grid-major" d="M80 0 H0 V80" />
        </pattern>
        <radialGradient :id="`${id}-cool`">
          <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.55" />
          <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
        </radialGradient>
        <radialGradient :id="`${id}-warm`">
          <stop offset="0" stop-color="var(--hmz-warm)" stop-opacity="0.6" />
          <stop offset="1" stop-color="var(--hmz-warm)" stop-opacity="0" />
        </radialGradient>
        <radialGradient :id="`${id}-comet`">
          <stop offset="0" stop-color="var(--hmz-lane-1)" stop-opacity="0.8" />
          <stop offset="1" stop-color="var(--hmz-lane-1)" stop-opacity="0" />
        </radialGradient>
        <marker :id="`${id}-tip-warm`" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path class="tip-warm" d="M0 1 L9 5 L0 9 Z" />
        </marker>
        <marker :id="`${id}-tip-cool`" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path class="tip-cool" d="M0 1 L9 5 L0 9 Z" />
        </marker>
      </defs>

      <!-- The paper the scene is drawn on, a little behind it: it moves a third as far. -->
      <g class="far">
        <g class="grid">
          <rect x="-600" y="-600" width="1840" height="1600" :fill="`url(#${id}-grid)`" />
          <rect x="-600" y="-600" width="1840" height="1600" :fill="`url(#${id}-major)`" />
        </g>
      </g>

      <g class="world">
        <line v-if="narrow" class="divider drift" x1="30" x2="290" y1="338" y2="338" />
        <line v-else class="divider drift" x1="320" x2="320" y1="70" y2="330" />

        <!-- the goal: turns round the objective -->
        <g class="goal-half">
          <text class="title" :x="C.x" y="44" text-anchor="middle">the model decides</text>

          <!-- the construction: axes through the objective, and its centre -->
          <line class="cross" :x1="C.x - RINGS[0].rx - 14" :x2="C.x + RINGS[0].rx + 14" :y1="C.y" :y2="C.y" />
          <line class="cross" :x1="C.x" :x2="C.x" :y1="C.y - RINGS[0].ry - 12" :y2="C.y + RINGS[0].ry + 12" />
          <circle class="hub" :cx="C.x" :cy="C.y" r="2.5" />

          <ellipse class="ring-0" :cx="C.x" :cy="C.y" :rx="RINGS[0].rx" :ry="RINGS[0].ry" />
          <path v-for="(d, i) in LAP_D" :key="`t${i}`" class="trace" :d="d" />

          <g class="glow"><circle class="check-glow" :cx="C.x" :cy="C.y" r="80" :fill="`url(#${id}-cool)`" /></g>
          <g class="card">
            <rect class="card-box" :x="C.x - 86" :y="C.y - 24" width="172" height="50" rx="12" />
            <text class="caption mono" :x="C.x" :y="C.y - 32" text-anchor="middle">/goal</text>
            <text class="obj" :x="C.x" :y="C.y - 3" text-anchor="middle" />
            <text class="obj" :x="C.x" :y="C.y + 14" text-anchor="middle" />
            <path class="check" :d="`M${C.x + 64} ${C.y - 30} l7 7 l14 -16`" />
          </g>

          <!-- the plot: tests failing after each turn -->
          <g class="plot">
            <line class="axis-y" :x1="PLOT.x0" :x2="PLOT.x0" :y1="PLOT.y0" :y2="PLOT.top" />
            <line class="axis-x" :x1="PLOT.x0" :x2="PLOT.x1" :y1="PLOT.y0" :y2="PLOT.y0" />
            <text class="axis-word" :x="PLOT.x0 - 8" :y="(PLOT.y0 + PLOT.top) / 2" text-anchor="middle" :transform="`rotate(-90 ${PLOT.x0 - 8} ${(PLOT.y0 + PLOT.top) / 2})`">failing</text>
            <text class="axis-word" :x="PLOT.x1" :y="PLOT.y0 + 15" text-anchor="end">turn →</text>
            <line v-for="i in 3" :key="`s${i}`" class="seg" :x1="POINTS[i - 1].x" :y1="POINTS[i - 1].y" :x2="POINTS[i].x" :y2="POINTS[i].y" />
            <circle v-for="(p, i) in POINTS" :key="`p${i}`" class="pt" :cx="p.x" :cy="p.y" r="4" />
            <circle class="pt-ring" :cx="POINTS[3].x" :cy="POINTS[3].y" r="9" />
            <!-- Words that move are moved by a group: a word's own transform is the stage's,
                 to lift it on a phone. -->
            <g class="readout-g"><text class="readout" :x="PLOT.x1" :y="PLOT.top - 4" text-anchor="end" /></g>
            <g class="met"><text class="met-word" :x="POINTS[3].x" :y="POINTS[3].y - 12" text-anchor="middle">met</text></g>
          </g>

          <text class="flow-word flow-word-0" :x="FLOW[0].x" :y="FLOW[0].y - 22" text-anchor="middle">flow</text>
          <rect class="flow-slot flow-slot-0" :x="FLOW[0].x - 44" :y="FLOW[0].y - 14" width="88" height="28" rx="14" />
          <g class="answer answer-0">
            <rect :x="FLOW[0].x - 44" :y="FLOW[0].y - 14" width="88" height="28" rx="14" />
            <text :x="FLOW[0].x" :y="FLOW[0].y + 4.5" text-anchor="middle">answer</text>
          </g>
        </g>

        <!-- by hand: a hook on the end of the turn -->
        <g :transform="`translate(${L.off.x} ${L.off.y})`">
          <g class="hook-half">
            <text class="title" x="480" y="44" text-anchor="middle">your code decides</text>
            <g class="task">
              <rect class="card-box" x="384" y="62" width="190" height="86" rx="10" />
              <text class="file" x="398" y="81">TASK.md</text>
              <g v-for="(item, i) in ITEMS" :key="item">
                <rect class="box" x="398" :y="92 + i * 17" width="11" height="11" rx="2.5" />
                <path class="tick" :d="`M400 ${98 + i * 17} l3 3 l5 -6`" />
                <text class="item" x="416" :y="101.5 + i * 17">{{ item }}</text>
                <line class="strike" x1="416" :x2="416 + item.length * 5.5" :y1="98 + i * 17" :y2="98 + i * 17" />
              </g>
            </g>
            <line class="rail" :x1="TRACK.x0 - 10" :x2="GATE.x - 8" :y1="TRACK.y + 16" :y2="TRACK.y + 16" />
            <g class="hook-note"><text class="hook-note-word" :x="(TRACK.x0 + TRACK.x1) / 2" :y="TRACK.y + 38" text-anchor="middle">turn ends → any box left?</text></g>
            <path class="back" :d="BACK_D" :marker-end="`url(#${id}-tip-warm)`" />
            <path class="pass" :d="PASS_D" :marker-end="`url(#${id}-tip-cool)`" />
            <line class="scan" :x1="GATE.x" :y1="GATE.y - 24" x2="574" y2="126" />
            <g class="glow">
              <circle class="gate-glow gate-glow-no" :cx="GATE.x" :cy="GATE.y" r="46" :fill="`url(#${id}-warm)`" />
              <circle class="gate-glow gate-glow-ok" :cx="GATE.x" :cy="GATE.y" r="46" :fill="`url(#${id}-cool)`" />
            </g>
            <rect class="gate-idle" :x="GATE.x - 11" :y="GATE.y - 28" width="22" height="56" rx="7" />
            <rect class="gate" :x="GATE.x - 7" :y="GATE.y - 24" width="14" height="48" rx="4" />
            <rect class="gate gate-no" :x="GATE.x - 7" :y="GATE.y - 24" width="14" height="48" rx="4" />
            <rect class="gate gate-ok" :x="GATE.x - 7" :y="GATE.y - 24" width="14" height="48" rx="4" />
            <text class="caption" :x="GATE.x" :y="GATE.y + 44" text-anchor="middle">hook</text>
            <g :transform="`translate(${(TRACK.x0 + GATE.x) / 2} 176)`">
              <g class="counter">
                <text class="counter-lab" text-anchor="middle">sent back <tspan class="counter-n">0</tspan></text>
              </g>
            </g>
            <text class="flow-word" :x="FLOW[1].x" :y="FLOW[1].y - 22" text-anchor="middle">flow</text>
            <rect class="flow-slot" :x="FLOW[1].x - 44" :y="FLOW[1].y - 14" width="88" height="28" rx="14" />
            <g class="answer answer-1">
              <rect :x="FLOW[1].x - 44" :y="FLOW[1].y - 14" width="88" height="28" rx="14" />
              <text :x="FLOW[1].x" :y="FLOW[1].y + 4.5" text-anchor="middle">answer</text>
            </g>
          </g>
          <g class="pill">
            <rect x="-30" y="-11" width="60" height="22" rx="11" />
            <text class="pill-n" y="4" text-anchor="middle">turn 1</text>
          </g>
        </g>

        <g class="comet">
          <circle class="comet-halo" r="16" :fill="`url(#${id}-comet)`" />
          <circle class="comet-core" r="6" />
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

.grid-minor {
  fill: none;
  stroke: var(--hmz-grid);
  stroke-width: 0.5;
  stroke-opacity: 0.6;
}

.grid-major {
  fill: none;
  stroke: var(--hmz-grid);
  stroke-width: 1;
}

.title {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-stage-ink);
}

.caption,
.flow-word {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.caption.mono {
  font-family: var(--vp-font-family-mono);
  letter-spacing: 0;
  text-transform: none;
  fill: var(--hmz-lane-1);
}

.divider {
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 2 5;
}

.cross {
  stroke: var(--hmz-stage-dim);
  stroke-width: 1;
  stroke-dasharray: 3 4;
}

.hub {
  fill: var(--hmz-stage-dim);
}

.ring-0 {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-opacity: 0.55;
  stroke-width: 1.2;
}

.trace {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
  stroke-linecap: round;
}

.card-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.obj {
  font-size: 13px;
  font-style: italic;
  fill: var(--hmz-stage-ink);
}

.check {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.glow {
  opacity: var(--hmz-glow);
}

.axis-x,
.axis-y {
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.2;
}

.axis-word {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  fill: var(--hmz-stage-dim);
}

.seg {
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
  stroke-linecap: round;
}

.pt {
  fill: var(--hmz-lane-1);
  stroke: var(--hmz-stage-card);
  stroke-width: 1.5;
}

.pt-ring {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.readout {
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}

.met-word {
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-accent);
}

.flow-slot {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 3 3;
}

.answer rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
}

.answer text {
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.comet-core {
  fill: var(--hmz-lane-1);
}

.comet-halo {
  opacity: var(--hmz-glow);
}

.file {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  fill: var(--hmz-stage-dim);
}

.box {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.2;
}

.tick {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.item {
  font-size: 12px;
  fill: var(--hmz-stage-ink);
}

.strike {
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.2;
}

.rail {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.5;
}

.hook-note-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  fill: var(--hmz-stage-dim);
}

.back,
.pass {
  fill: none;
  stroke-width: 1.5;
  stroke-linecap: round;
}

.back {
  stroke: var(--hmz-warm);
}

.pass {
  stroke: var(--hmz-accent);
}

.tip-warm {
  fill: var(--hmz-warm);
}

.tip-cool {
  fill: var(--hmz-accent);
}

.scan {
  stroke: var(--hmz-lane-3);
  stroke-width: 2;
  stroke-linecap: round;
}

.gate-idle {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1;
  stroke-dasharray: 2 3;
}

.gate {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.5;
}

.gate-no {
  fill: var(--hmz-warm);
  stroke: var(--hmz-warm);
}

.gate-ok {
  fill: var(--hmz-accent);
  stroke: var(--hmz-accent);
}

.counter-lab {
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  font-weight: 650;
  fill: var(--hmz-warm);
}

.pill rect {
  fill: var(--hmz-lane-3);
}

.pill text {
  font-size: 11.5px;
  font-weight: 650;
  fill: var(--vp-c-bg);
}
</style>
