<script setup lang="ts">
// Two ways a turn keeps going. Left, the CLI's own goal: a turn that would have ended starts
// another, until the model judges the objective met, and the flow gets the last turn's answer.
// Right, the same thing by hand: a hook on the end of the turn reads TASK.md and sends the agent
// back while boxes are unticked, told each time how often it already has. Which CLIs have a goal
// is `pursues` in `hmz/coganchor/agents/`, and the flow-level `GoalCommandAgentMixin` in
// `hmz/flows/agents.py`. The turns are invented.
import { computed, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
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

// What the goal's turns come to, one per lap.
const LAPS = ['3 failing', '1 failing', 'suite passes', 'judged met']
const ITEMS = ['port the parser', 'port the printer', 'port the CLI']

// The world is one 640 × 360 plane in both layouts: the goal on its left half, the hook on its
// right. Only the camera differs, and the screen it looks through.
const WORLD = { w: 640, h: 360 }
const ORBIT = { cx: 160, cy: 150, rx: 128, ry: 70 }
const ORBIT_D = `M${ORBIT.cx} ${ORBIT.cy + ORBIT.ry} A${ORBIT.rx} ${ORBIT.ry} 0 0 1 ${ORBIT.cx} ${ORBIT.cy - ORBIT.ry} A${ORBIT.rx} ${ORBIT.ry} 0 0 1 ${ORBIT.cx} ${ORBIT.cy + ORBIT.ry}`
const EXIT_D = `M${ORBIT.cx} ${ORBIT.cy + ORBIT.ry} C${ORBIT.cx} ${ORBIT.cy + ORBIT.ry + 30} ${ORBIT.cx} 280 ${ORBIT.cx} 312`
const TRACK = { x0: 350, x1: 548, y: 206 }
const GATE = { x: 596, y: 206 }
const BACK_D = `M${GATE.x - 12} ${TRACK.y - 10} C${GATE.x - 12} 160 ${TRACK.x0} 160 ${TRACK.x0} ${TRACK.y - 10}`
const PASS_D = `M${GATE.x + 10} ${TRACK.y} C${GATE.x + 36} ${TRACK.y} ${GATE.x + 36} 312 ${GATE.x - 70} 312`
const FLOW = [
  { x: 160, y: 312 },
  { x: 480, y: 312 },
]

interface Layout {
  w: number
  h: number
  /** Where the hook's half sits against the goal's: beside it, or under it on a phone. */
  off: { x: number; y: number }
  goal: { cx: number; cy: number; s: number }
  hook: { cx: number; cy: number; s: number }
  both: { cx: number; cy: number; s: number }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  off: { x: 0, y: 0 },
  goal: { cx: 176, cy: 180, s: 1.15 },
  hook: { cx: 470, cy: 180, s: 1.15 },
  both: { cx: 320, cy: 184, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 560,
  off: { x: -318, y: 300 },
  goal: { cx: 160, cy: 180, s: 1.1 },
  hook: { cx: 156, cy: 476, s: 1.1 },
  both: { cx: 160, cy: 330, s: 0.88 },
}

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
    const world = at('.world')[0]
    const comet = at('.comet')[0]
    const pill = at('.pill')[0]

    const shot = (c: { cx: number; cy: number; s: number }) => ({ x: l.w / 2 - c.cx * c.s, y: l.h / 2 - c.cy * c.s, scale: c.s })
    const screen = (x: number, y: number) => {
      const s = Number(gsap.getProperty(world, 'scale'))
      return { x: x * s + Number(gsap.getProperty(world, 'x')), y: y * s + Number(gsap.getProperty(world, 'y')) }
    }
    const spark = (x: number, y: number, color: () => string, n: number, when: number, speed = 90) =>
      tl.call(
        () => {
          const p = screen(x, y)
          fx?.spark(p.x, p.y, color(), n, speed)
        },
        [],
        when,
      )
    const trail = (el: Element, color: () => string, size = 2.6) => () => {
      const o = el === pill ? l.off : { x: 0, y: 0 }
      const p = screen(Number(gsap.getProperty(el, 'x')) + o.x, Number(gsap.getProperty(el, 'y')) + o.y)
      fx?.trail(p.x, p.y, color(), size)
    }
    const along = (el: Element, path: string, when: number, duration: number, color: () => string, ease = 'power1.inOut') =>
      tl.to(el, { motionPath: { path, start: 0, end: 1 }, duration, ease, onUpdate: trail(el, color) }, when)

    // Where a loop starts.
    tl.set(world, { svgOrigin: '0 0', ...shot({ ...l.goal, s: l.goal.s * 1.25 }), autoAlpha: 1 }, 0)
    tl.set(at('.check-glow, .gate-glow, .card, .answer, .counter'), { transformOrigin: '50% 50%', smoothOrigin: false }, 0)
    tl.set(at('.comet, .pill, .answer, .check, .scan, .gate-ok, .gate-no, .counter, .tick'), { opacity: 0 }, 0)
    tl.set(at('.check-glow, .gate-glow'), { opacity: 0 }, 0)
    tl.set(at('.obj'), { text: '' }, 0)
    tl.set(at('.lap'), { text: '' }, 0)
    tl.set(at('.item'), { opacity: 1 }, 0)
    tl.set(at('.strike'), { drawSVG: '0%' }, 0)
    tl.set(at('.hook-half'), { opacity: 0.25 }, 0)
    tl.set(at('.goal-half'), { opacity: 1 }, 0)
    tl.set(comet, { x: ORBIT.cx, y: ORBIT.cy + ORBIT.ry }, 0)
    tl.set(pill, { x: TRACK.x0, y: TRACK.y }, 0)

    // 0 · a goal, not a prompt: the orbit is drawn round the objective as it is written.
    tl.addLabel('beat-0', 0)
    tl.to(world, { ...shot(l.goal), duration: 2.4, ease: 'cine' }, 0)
    tl.fromTo(at('.orbit'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.6, ease: 'cine' }, 0.2)
    tl.fromTo(at('.card'), { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.6 }, 0.3)
    const obj = at('.obj')
    tl.to(obj[0], { text: { value: 'the suite passes,' }, duration: 0.6, ease: 'none' }, 0.8)
    tl.to(obj[1], { text: { value: 'nothing stubbed out' }, duration: 0.6, ease: 'none' }, 1.45)
    tl.fromTo(at('.goal-half .title, .flow-slot-0'), { opacity: 0 }, { opacity: 1, duration: 0.6 }, 1)

    // 1 · turn after turn round the objective, without anyone asking.
    const T1 = 2.4
    const LAP = 1.35
    tl.addLabel('beat-1', T1)
    tl.to(comet, { opacity: 1, duration: 0.3 }, T1)
    spark(ORBIT.cx, ORBIT.cy + ORBIT.ry, () => palette.lane[0], 14, T1)
    const lap = at('.lap')[0]
    LAPS.forEach((word, i) => {
      const t = T1 + i * LAP
      along(comet, ORBIT_D, t, LAP, () => palette.lane[0], i === 0 ? 'power1.in' : 'none')
      tl.set(lap, { text: `turn ${i + 1} · ${word}` }, t + LAP - 0.02)
      tl.fromTo(lap, { opacity: 0.2, y: 4 }, { opacity: 1, y: 0, duration: 0.35 }, t + LAP - 0.02)
    })

    // 2 · on the last lap the model judges it met: the objective lights, and the answer leaves.
    const T2 = T1 + 3 * LAP
    tl.addLabel('beat-2', T2)
    const J = T2 + LAP
    tl.fromTo(at('.check-glow'), { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1.1, duration: 0.5, ease: 'power2.out' }, J - 0.1)
    tl.fromTo(at('.check'), { opacity: 1, drawSVG: '0%' }, { drawSVG: '100%', duration: 0.4, ease: 'power2.out' }, J)
    spark(ORBIT.cx, ORBIT.cy, () => palette.accent, 30, J, 140)
    along(comet, EXIT_D, J + 0.3, 0.9, () => palette.accent, 'power2.in')
    tl.to(comet, { opacity: 0, duration: 0.15 }, J + 1.2)
    tl.fromTo(at('.answer-0'), { opacity: 0, scale: 1.4 }, { opacity: 1, scale: 1, duration: 0.5, ease: 'back.out(1.8)' }, J + 1.2)
    spark(FLOW[0].x, FLOW[0].y, () => palette.accent, 22, J + 1.2, 110)

    // 3 · pan across: the same loop by hand, a hook on the end of the turn.
    const T3 = J + 2.2
    tl.addLabel('beat-3', T3)
    tl.to(world, { ...shot(l.hook), duration: 1.6, ease: 'cine' }, T3)
    tl.to(at('.goal-half'), { opacity: 0.25, duration: 1 }, T3)
    tl.to(at('.hook-half'), { opacity: 1, duration: 1 }, T3 + 0.2)
    tl.to(at('.counter'), { opacity: 1, duration: 0.4 }, T3 + 1.2)
    const count = at('.counter-n')[0]
    tl.set(count, { text: '0' }, T3)

    const TRAVEL = 1.3
    const hookLap = (i: number, t: number) => {
      tl.set(at('.pill-n')[0], { text: `turn ${i + 1}` }, t)
      tl.fromTo(pill, { opacity: 0, x: TRACK.x0, y: TRACK.y }, { opacity: 1, duration: 0.2 }, t)
      tl.to(pill, { x: TRACK.x1, duration: TRAVEL, ease: 'power1.inOut', onUpdate: trail(pill, () => palette.lane[2], 2) }, t)
      // The agent ticks a box on the way.
      tl.to(at('.tick')[i], { opacity: 1, duration: 0.2 }, t + TRAVEL * 0.55)
      tl.fromTo(at('.tick')[i], { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.3 }, t + TRAVEL * 0.55)
      tl.to(at('.strike')[i], { drawSVG: '100%', duration: 0.4 }, t + TRAVEL * 0.6)
      tl.to(at('.item')[i], { opacity: 0.5, duration: 0.4 }, t + TRAVEL * 0.6)
      // The hook reads TASK.md.
      const c = t + TRAVEL
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
    along(pill, PASS_D, c + 0.15, 1, () => palette.accent, 'power2.inOut')
    tl.to(pill, { opacity: 0, duration: 0.15 }, c + 1.1)
    tl.fromTo(at('.answer-1'), { opacity: 0, scale: 1.4 }, { opacity: 1, scale: 1, duration: 0.5, ease: 'back.out(1.8)' }, c + 1.1)
    spark(FLOW[1].x + l.off.x, FLOW[1].y + l.off.y, () => palette.accent, 22, c + 1.1, 110)

    // Pull back on both, hold, and fade for the loop.
    const E = c + 1.9
    tl.to(world, { ...shot(l.both), duration: 1.6, ease: 'cine' }, E)
    tl.to(at('.goal-half, .hook-half'), { opacity: 1, duration: 1 }, E)
    tl.to(at('.gate-glow'), { opacity: 0, duration: 0.6 }, E)
    tl.addLabel('rest', E + 1.8)
    tl.to(world, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, E + 4.2)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 14"
    label="Two ways to keep an agent working until the job is done. Left, a goal: the agent takes turn after turn round its objective until the model judges it met, and the flow gets the last answer. Right, a hook on the end of the turn reads TASK.md and sends the turn back while boxes are unticked, counting how often it has, and lets it end once every box is ticked."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <radialGradient id="hmz-goal-cool">
          <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.55" />
          <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="hmz-goal-warm">
          <stop offset="0" stop-color="var(--hmz-warm)" stop-opacity="0.6" />
          <stop offset="1" stop-color="var(--hmz-warm)" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="hmz-goal-comet">
          <stop offset="0" stop-color="var(--hmz-lane-1)" stop-opacity="0.8" />
          <stop offset="1" stop-color="var(--hmz-lane-1)" stop-opacity="0" />
        </radialGradient>
      </defs>
      <g class="world">
        <line v-if="narrow" class="divider" x1="30" x2="290" y1="334" y2="334" />
        <line v-else class="divider" x1="320" x2="320" y1="70" y2="300" />

        <!-- the goal: turns round the objective -->
        <g class="goal-half">
          <text class="title" :x="ORBIT.cx" y="50" text-anchor="middle">the model decides</text>
          <path class="orbit" :d="ORBIT_D" />
          <g class="glow"><circle class="check-glow" :cx="ORBIT.cx" :cy="ORBIT.cy" r="80" fill="url(#hmz-goal-cool)" /></g>
          <g class="card">
            <rect class="card-box" :x="ORBIT.cx - 86" :y="ORBIT.cy - 24" width="172" height="50" rx="12" />
            <text class="caption" :x="ORBIT.cx" :y="ORBIT.cy - 32" text-anchor="middle">goal</text>
            <text class="obj" :x="ORBIT.cx" :y="ORBIT.cy - 3" text-anchor="middle" />
            <text class="obj" :x="ORBIT.cx" :y="ORBIT.cy + 14" text-anchor="middle" />
            <path class="check" :d="`M${ORBIT.cx + 64} ${ORBIT.cy - 30} l7 7 l14 -16`" />
          </g>
          <text class="lap" :x="ORBIT.cx" :y="ORBIT.cy + ORBIT.ry + 24" text-anchor="middle" />
          <rect class="flow-slot flow-slot-0" :x="FLOW[0].x - 44" :y="FLOW[0].y - 14" width="88" height="28" rx="14" />
          <text class="flow-word" :x="FLOW[0].x - 52" :y="FLOW[0].y + 4" text-anchor="end">flow</text>
          <g class="answer answer-0">
            <rect :x="FLOW[0].x - 44" :y="FLOW[0].y - 14" width="88" height="28" rx="14" />
            <text :x="FLOW[0].x" :y="FLOW[0].y + 4.5" text-anchor="middle">answer</text>
          </g>
        </g>

        <!-- by hand: a hook on the end of the turn -->
        <g :transform="`translate(${L.off.x} ${L.off.y})`">
        <g class="hook-half">
          <text class="title" x="480" y="50" text-anchor="middle">your code decides</text>
          <g class="task">
            <rect class="card-box" x="384" y="68" width="190" height="86" rx="10" />
            <text class="file" x="398" y="87">TASK.md</text>
            <g v-for="(item, i) in ITEMS" :key="item">
              <rect class="box" x="398" :y="98 + i * 17" width="11" height="11" rx="2.5" />
              <path class="tick" :d="`M400 ${104 + i * 17} l3 3 l5 -6`" />
              <text class="item" x="416" :y="107.5 + i * 17">{{ item }}</text>
              <line class="strike" x1="416" :x2="416 + item.length * 5.5" :y1="104 + i * 17" :y2="104 + i * 17" />
            </g>
          </g>
          <line class="rail" :x1="TRACK.x0 - 10" :x2="GATE.x - 8" :y1="TRACK.y + 16" :y2="TRACK.y + 16" />
          <path class="back" :d="BACK_D" />
          <path class="pass" :d="PASS_D" />
          <line class="scan" :x1="GATE.x" :y1="GATE.y - 24" x2="574" y2="130" />
          <g class="glow">
            <circle class="gate-glow gate-glow-no" :cx="GATE.x" :cy="GATE.y" r="46" fill="url(#hmz-goal-warm)" />
            <circle class="gate-glow gate-glow-ok" :cx="GATE.x" :cy="GATE.y" r="46" fill="url(#hmz-goal-cool)" />
          </g>
          <rect class="gate" :x="GATE.x - 7" :y="GATE.y - 24" width="14" height="48" rx="4" />
          <rect class="gate gate-no" :x="GATE.x - 7" :y="GATE.y - 24" width="14" height="48" rx="4" />
          <rect class="gate gate-ok" :x="GATE.x - 7" :y="GATE.y - 24" width="14" height="48" rx="4" />
          <text class="caption" :x="GATE.x" :y="GATE.y + 42" text-anchor="middle">hook</text>
          <g :transform="`translate(${(TRACK.x0 + GATE.x) / 2} 176)`"><g class="counter">
            <text class="counter-lab" text-anchor="middle">sent back <tspan class="counter-n">0</tspan></text>
          </g></g>
          <rect class="flow-slot" :x="FLOW[1].x - 44" :y="FLOW[1].y - 14" width="88" height="28" rx="14" />
          <text class="flow-word" :x="FLOW[1].x - 52" :y="FLOW[1].y + 4" text-anchor="end">flow</text>
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
          <circle class="comet-halo" r="16" fill="url(#hmz-goal-comet)" />
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

.title {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-stage-ink);
}

.caption,
.flow-word {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.divider {
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 2 5;
}

.orbit {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-opacity: 0.45;
  stroke-width: 1.5;
  stroke-dasharray: 4 5;
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

.lap {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
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
  font-size: 11px;
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
}

.back,
.pass {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
  stroke-dasharray: 3 4;
}

.scan {
  stroke: var(--hmz-lane-3);
  stroke-width: 2;
  stroke-linecap: round;
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
  fill: #fff;
}
</style>
