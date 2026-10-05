<script setup lang="ts">
// The Glossary's words, met in one run. One `hmz exec` line names a flow, its agents and a
// budget; an agent splits into its role, backend, model and effort; each role opens sessions
// and runs turns in them (the actor keeps one session, the reviewer opens a fresh one every
// round, as `rlar` does); a turn run with no environment (`run(…, env=None)`) works in the
// workspace, the directory hmz ran in; and the whole run is written down as an epic, whose
// trace lays every turn on one timeline. A simulation: the rounds and the run's name are
// invented.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { createFx, type, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'
import { rig, type Point, type Shot } from '../../motion/camera'
import { brace, braceD, curve, draw, pop, ring, rise } from '../user-kit/moves'

const BEATS = [
  'One line names a flow, its agents and a budget',
  'An agent: a role filled by a backend, a model, an effort',
  'Each role opens sessions and runs turns in them',
  'A turn with no environment works in the workspace',
  'The run is an epic; its trace is one timeline',
]

/** A mono character's advance at 12px. */
const CW = 7.2
const ROUNDS = [0, 1, 2]

/** The actor's `-a`, in pieces: the four that become chips, and what separates them. */
const PIECES = [
  { text: 'actor', col: 5, chip: 0 },
  { text: '=', col: 10, chip: -1 },
  { text: 'claude', col: 11, chip: 1 },
  { text: '/', col: 17, chip: -1 },
  { text: 'claude-opus-5-5', col: 18, chip: 2 },
  { text: ':', col: 33, chip: -1 },
  { text: 'high', col: 34, chip: 3 },
]
const CHIP_NAMES = ['role', 'backend', 'model', 'effort']
const CHIP_GAP = 8
const chipW = (text: string) => text.length * CW + 12

interface Layout {
  w: number
  h: number
  cmd: { x: number; y: number; w: number; h: number }
  chips: { x: number; y: number }
  lanes: { label: number; box: number; ys: [number, number] }
  code: Point
  ws: { x: number; y: number; w: number; h: number }
  trace: { x: number; y: number; w: number; label: number }
  shots: Record<'open' | 'split' | 'lanes' | 'ws', Partial<Shot>>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  cmd: { x: 24, y: 22, w: 306, h: 118 },
  chips: { x: 28, y: 178 },
  lanes: { label: 350, box: 430, ys: [68, 132] },
  code: { x: 350, y: 174 },
  ws: { x: 350, y: 188, w: 264, h: 66 },
  trace: { x: 24, y: 270, w: 592, label: 126 },
  shots: {
    open: { x: 177, y: 82, s: 1.6 },
    split: { x: 182, y: 150, s: 1.45 },
    lanes: { x: 488, y: 100, s: 1.55 },
    ws: { x: 482, y: 175, s: 1.3 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 520,
  cmd: { x: 12, y: 14, w: 336, h: 118 },
  chips: { x: 18, y: 168 },
  lanes: { label: 14, box: 96, ys: [258, 318] },
  code: { x: 14, y: 362 },
  ws: { x: 14, y: 374, w: 332, h: 62 },
  trace: { x: 14, y: 448, w: 332, label: 82 },
  shots: {
    open: { x: 180, y: 84, s: 1.05 },
    split: { x: 172, y: 150, s: 1.05 },
    lanes: { x: 150, y: 286, s: 1.25 },
    ws: { x: 180, y: 400, s: 1.05 },
  },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const textX = computed(() => L.value.cmd.x + 12)
const lineY = (i: number) => L.value.cmd.y + 24 + i * 18
/** Where each chip's words start once it has left the line. */
const chipX = computed(() => {
  const out: number[] = []
  let x = L.value.chips.x
  for (const piece of PIECES.filter((p) => p.chip >= 0)) {
    out.push(x + 6)
    x += chipW(piece.text) + CHIP_GAP
  }
  return out
})
const braceOf = (k: number) => {
  const piece = PIECES.find((p) => p.chip === k)!
  const x = chipX.value[k] - 6
  const y = L.value.chips.y + 12
  return { d: braceD({ x: x + 2, y }, { x: x + chipW(piece.text) - 2, y }, 9), cx: x + chipW(piece.text) / 2, ly: y + 23 }
}

const TURN_W = 40
const TURN_H = 24
const actorTurn = (i: number) => L.value.lanes.box + 8 + i * 48
const reviewSession = (i: number) => L.value.lanes.box + i * 64
/** The middle of a turn: lane 0 the actor's, lane 1 the reviewer's. */
const turnC = (lane: number, i: number): Point => ({
  x: (lane ? reviewSession(i) + 8 : actorTurn(i)) + TURN_W / 2,
  y: L.value.lanes.ys[lane],
})

/** Where on the trace each turn is, as fractions of its track. */
const SLICES = [
  ROUNDS.map((i) => ({ at: i * 0.33, w: 0.2 })),
  ROUNDS.map((i) => ({ at: i * 0.33 + 0.21, w: 0.1 })),
]
const trackX = computed(() => L.value.trace.x + L.value.trace.label)
const trackW = computed(() => L.value.trace.w - L.value.trace.label - 10)

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), far: one('.far'), fx: () => fx, start: l.shots.open })
    const c = {
      actor: () => palette.lane[0],
      review: () => palette.accent2,
      ws: () => palette.warm,
    }

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(q('.cmd, .hl, .chip-bg, .brace-path, .brace-label, .lane, .session, .turn, .count-2, .link-path, .code, .env-chip, .env-ring, .ws, .mark, .trace, .slice, .head, .ws-arrow'), { autoAlpha: 0 }, 0)
    tl.set(q('.piece'), { x: 0, y: 0 }, 0)
    tl.set(q('.sep, .count-1, .cmd-line, .piece'), { autoAlpha: 1 }, 0)
    tl.set(q('.slice'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)

    // 0 · the line, typed.
    tl.addLabel('beat-0', 0)
    rise(tl, one('.cmd'), 0.1, { y: 10 })
    const lines = q('.cmd-line')
    type(tl, lines[0], '$ hmz exec -f rlar', 0.4)
    tl.fromTo(q('.piece, .sep, .dash'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.12, stagger: 0.07, ease: 'none' }, 1.0)
    type(tl, lines[1], '-a reviewer=codex/gpt-5.6-sol:high', 1.7)
    type(tl, lines[2], '-p budget.duration=2h', 2.7)
    type(tl, lines[3], '"fix the flaky payment test"', 3.3)
    ring(tl, one('.cmd-ring'), 4.2, { to: 1.08, duration: 0.7 })

    // 1 · the agent comes apart into what it is made of, each part named.
    const T1 = 4.7
    tl.addLabel('beat-1', T1)
    cam.shot(l.shots.split, T1, 1.4)
    tl.to(one('.hl'), { autoAlpha: 1, duration: 0.4 }, T1 + 0.2)
    tl.to(q('.sep'), { autoAlpha: 0, duration: 0.3 }, T1 + 0.8)
    PIECES.forEach((piece, i) => {
      if (piece.chip < 0) return
      const from = textX.value + piece.col * CW
      tl.to(one(`.piece-${i}`), { x: chipX.value[piece.chip] - from, y: l.chips.y - lineY(1), duration: 1.0, ease: 'cine' }, T1 + 0.8 + piece.chip * 0.09)
      tl.to(one(`.piece-${i} .chip-bg`), { autoAlpha: 1, duration: 0.4 }, T1 + 1.5 + piece.chip * 0.09)
    })
    tl.to(one('.hl'), { autoAlpha: 0, duration: 0.4 }, T1 + 1.4)
    CHIP_NAMES.forEach((_, k) => brace(tl, q, `.brace-${k}`, T1 + 2.1 + k * 0.4))
    tl.to(one('.cmd'), { autoAlpha: 0.45, duration: 0.6 }, T1 + 3.8)

    // 2 · the two roles at work: the actor keeps one session, the reviewer opens one a round.
    const T2 = T1 + 4.4
    tl.addLabel('beat-2', T2)
    cam.shot(l.shots.lanes, T2, 1.6)
    draw(tl, one('.link-path'), T2 + 0.3, { duration: 1.0 })
    rise(tl, q('.lane'), T2 + 0.6, { x: -10, y: 0, stagger: 0.15 })
    pop(tl, one('.session-a'), T2 + 1.1, { from: 0.85 })
    const ROUND = 1.5
    ROUNDS.forEach((i) => {
      const t = T2 + 1.5 + i * ROUND
      pop(tl, one(`.turn-a-${i}`), t)
      ring(tl, one(`.turn-a-${i} .turn-ring`), t + 0.25)
      cam.beam(turnC(0, i), turnC(1, i), c.review, t + 0.35, { duration: 0.55, bend: 0.25, burst: 8 })
      pop(tl, one(`.session-r-${i}`), t + 0.55, { from: 0.8 })
      pop(tl, one(`.turn-r-${i}`), t + 0.8)
      if (i === 1) {
        tl.to(one('.count-1'), { autoAlpha: 0, duration: 0.2 }, t + 0.6)
        tl.to(one('.count-2'), { autoAlpha: 1, duration: 0.2 }, t + 0.6)
      }
      tl.set(one('.count-2'), { text: `${i + 1} sessions` }, t + 0.6)
      if (i < ROUNDS.length - 1) cam.beam(turnC(1, i), turnC(0, i + 1), c.actor, t + 1.05, { duration: 0.5, bend: 0.25 })
    })

    // 3 · none of those turns named an environment: each one worked in the workspace.
    const T3 = T2 + 1.5 + ROUNDS.length * ROUND + 0.2
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.ws, T3, 1.4)
    rise(tl, one('.ws'), T3 + 0.3)
    rise(tl, one('.code'), T3 + 0.7, { y: 6 })
    tl.to(one('.env-chip'), { autoAlpha: 1, duration: 0.3 }, T3 + 1.3)
    ring(tl, one('.env-ring'), T3 + 1.35, { to: 1.5 })
    draw(tl, one('.ws-arrow'), T3 + 1.5, { duration: 0.5 })
    ROUNDS.forEach((i) => {
      cam.beam(turnC(0, i), { x: l.ws.x + l.ws.w * 0.35, y: l.ws.y + 12 }, c.ws, T3 + 1.8 + i * 0.2, { duration: 0.75, bend: -0.15, burst: 6 })
      cam.beam(turnC(1, i), { x: l.ws.x + l.ws.w * 0.65, y: l.ws.y + 12 }, c.ws, T3 + 1.9 + i * 0.2, { duration: 0.75, bend: 0.15, burst: 6 })
    })
    pop(tl, q('.mark'), T3 + 2.7, { stagger: 0.25 })

    // 4 · the whole run, written down, read back as one timeline.
    const T4 = T3 + 3.9
    tl.addLabel('beat-4', T4)
    cam.shot({ x: l.w / 2, y: l.h / 2, s: 1 }, T4, 1.6)
    rise(tl, one('.trace'), T4 + 0.5)
    const SWEEP = 2.6
    const sweepAt = T4 + 1.1
    tl.fromTo(one('.head'), { autoAlpha: 1, x: 0 }, { x: trackW.value, duration: SWEEP, ease: 'none' }, sweepAt)
    SLICES.forEach((lane, k) =>
      lane.forEach((s, i) => {
        tl.set(one(`.slice-${k}-${i}`), { autoAlpha: 1 }, sweepAt + s.at * SWEEP)
        tl.to(one(`.slice-${k}-${i}`), { scaleX: 1, duration: s.w * SWEEP, ease: 'none' }, sweepAt + s.at * SWEEP)
      }),
    )
    tl.to(one('.head'), { autoAlpha: 0, duration: 0.3 }, sweepAt + SWEEP)
    tl.addLabel('rest', sweepAt + SWEEP + 0.3)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, sweepAt + SWEEP + 4)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 13"
    label="One run of rlar, in the Glossary's words. The line hmz exec -f rlar -a actor=claude/claude-opus-5-5:high -a reviewer=codex/gpt-5.6-sol:high -p budget.duration=2h names the flow, two agents and a budget. The actor's agent comes apart into its role (actor), backend (claude), model (claude-opus-5-5) and effort (high). Over three rounds the actor keeps one session and runs a turn in it each round, while the reviewer opens a fresh session each round for one turn. No turn names an environment, run(…, env=None), so every turn works in the workspace, the directory hmz ran in. The run is written down as an epic, and its trace lays every turn on one timeline."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <pattern id="ra-dots" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" class="grid-dot" />
        </pattern>
      </defs>
      <g class="far"><rect x="-400" y="-400" :width="L.w + 800" :height="L.h + 800" fill="url(#ra-dots)" /></g>

      <g class="world">
        <!-- The line. -->
        <g class="cmd">
          <rect class="cmd-box" :x="L.cmd.x" :y="L.cmd.y" :width="L.cmd.w" :height="L.cmd.h" rx="10" />
          <g :transform="`translate(${L.cmd.x + L.cmd.w / 2} ${L.cmd.y + L.cmd.h / 2})`">
            <rect class="cmd-ring" :x="-L.cmd.w / 2" :y="-L.cmd.h / 2" :width="L.cmd.w" :height="L.cmd.h" rx="10" />
          </g>
          <rect class="hl" :x="textX - 4" :y="lineY(1) - 13" :width="38 * CW + 8" height="18" rx="4" />
          <text class="cmd-line prompt" :x="textX" :y="lineY(0)">$ hmz exec -f rlar</text>
          <text class="cmd-line" :x="textX + 2 * CW" :y="lineY(2)">-a reviewer=codex/gpt-5.6-sol:high</text>
          <text class="cmd-line" :x="textX + 2 * CW" :y="lineY(3)">-p budget.duration=2h</text>
          <text class="cmd-line task" :x="textX + 2 * CW" :y="lineY(4)">"fix the flaky payment test"</text>
          <text class="dash" :x="textX + 2 * CW" :y="lineY(1)">-a</text>
        </g>
        <!-- The actor's agent, a piece at a time, so its parts can leave the line. -->
        <g v-for="(piece, i) in PIECES" :key="i" :transform="`translate(${textX + piece.col * CW} ${lineY(1)})`">
          <g v-if="piece.chip >= 0" class="piece" :class="`piece-${i} chip-${piece.chip}`">
            <rect class="chip-bg" x="-6" y="-14" :width="chipW(piece.text)" height="20" rx="5" />
            <text class="piece-text">{{ piece.text }}</text>
          </g>
          <text v-else class="sep">{{ piece.text }}</text>
        </g>
        <g v-for="(name, k) in CHIP_NAMES" :key="name" :class="`brace-${k}`">
          <path class="brace-path" :d="braceOf(k).d" />
          <g class="brace-label"><text class="brace-word" :x="braceOf(k).cx" :y="braceOf(k).ly" text-anchor="middle">{{ name }}</text></g>
        </g>

        <!-- The role, to the lane where its agent works. -->
        <path class="link-path" :d="curve({ x: chipX[0] + 18, y: L.chips.y - 16 }, { x: L.lanes.label - 4, y: L.lanes.ys[0] - 4 }, narrow ? -0.25 : 0.25)" />

        <!-- The two roles, their sessions and turns. -->
        <g v-for="(y, k) in L.lanes.ys" :key="k" class="lane" :class="`lane-${k}`">
          <text class="lane-name" :x="L.lanes.label" :y="y - 1">{{ k ? 'reviewer' : 'actor' }}</text>
          <text v-if="!k" class="lane-count" :x="L.lanes.label" :y="y + 15">1 session</text>
          <template v-else>
            <text class="lane-count count-1" :x="L.lanes.label" :y="y + 15">1 session</text>
            <text class="lane-count count-2" :x="L.lanes.label" :y="y + 15">3 sessions</text>
          </template>
          <text class="lane-note" :x="L.lanes.box" :y="y - 24">{{ k ? 'a new one each round' : 'one session, kept' }}</text>
        </g>
        <rect class="session session-a" :x="L.lanes.box" :y="L.lanes.ys[0] - 19" width="184" height="38" rx="9" />
        <rect v-for="i in ROUNDS" :key="`sr${i}`" class="session session-r" :class="`session-r-${i}`" :x="reviewSession(i)" :y="L.lanes.ys[1] - 19" width="56" height="38" rx="9" />
        <g v-for="i in ROUNDS" :key="`ta${i}`" class="turn turn-a" :class="`turn-a-${i}`">
          <rect :x="actorTurn(i)" :y="L.lanes.ys[0] - TURN_H / 2" :width="TURN_W" :height="TURN_H" rx="6" />
          <text :x="actorTurn(i) + TURN_W / 2" :y="L.lanes.ys[0] + 4" text-anchor="middle">turn</text>
          <g :transform="`translate(${actorTurn(i) + TURN_W / 2} ${L.lanes.ys[0]})`">
            <rect class="turn-ring" :x="-TURN_W / 2" :y="-TURN_H / 2" :width="TURN_W" :height="TURN_H" rx="6" />
          </g>
        </g>
        <g v-for="i in ROUNDS" :key="`tr${i}`" class="turn turn-r" :class="`turn-r-${i}`">
          <rect :x="reviewSession(i) + 8" :y="L.lanes.ys[1] - TURN_H / 2" :width="TURN_W" :height="TURN_H" rx="6" />
          <text :x="reviewSession(i) + 8 + TURN_W / 2" :y="L.lanes.ys[1] + 4" text-anchor="middle">turn</text>
        </g>

        <!-- Where they worked. -->
        <g class="code">
          <text class="code-text" :x="L.code.x" :y="L.code.y">run(task, session=s, </text>
          <text class="code-text" :x="L.code.x + 29 * 6.6" :y="L.code.y">)</text>
        </g>
        <g class="env-chip">
          <rect class="env-bg" :x="L.code.x + 21 * 6.6 - 3" :y="L.code.y - 12" :width="8 * 6.6 + 6" height="16" rx="4" />
          <text class="code-text env-text" :x="L.code.x + 21 * 6.6" :y="L.code.y">env=None</text>
          <g :transform="`translate(${L.code.x + 25 * 6.6} ${L.code.y - 4})`">
            <rect class="env-ring" x="-30" y="-8" width="60" height="16" rx="4" />
          </g>
        </g>
        <path class="ws-arrow" :d="`M${L.code.x + 25 * 6.6} ${L.code.y + 5} L${L.code.x + 25 * 6.6} ${L.ws.y + 2}`" />
        <g class="ws">
          <path class="ws-box" :d="`M${L.ws.x} ${L.ws.y + 6} q0 -6 6 -6 h70 l8 6 h${L.ws.w - 90} q6 0 6 6 v${L.ws.h - 12} q0 6 -6 6 h${-(L.ws.w - 12)} q-6 0 -6 -6 z`" />
          <text class="ws-name" :x="L.ws.x + 12" :y="L.ws.y + 24">workspace</text>
          <text class="ws-path" :x="L.ws.x + 92" :y="L.ws.y + 24">~/shop · where hmz ran</text>
          <text class="ws-file" :x="L.ws.x + 12" :y="L.ws.y + 44">payment.py</text>
          <text class="ws-file" :x="L.ws.x + 12" :y="L.ws.y + 58">test_payment.py</text>
          <g class="mark"><text class="mark-word" :x="L.ws.x + L.ws.w - 12" :y="L.ws.y + 44" text-anchor="end">edited</text></g>
          <g class="mark"><text class="mark-word" :x="L.ws.x + L.ws.w - 12" :y="L.ws.y + 58" text-anchor="end">passes</text></g>
        </g>

        <!-- The epic, and its trace. -->
        <g class="trace">
          <rect class="trace-box" :x="L.trace.x" :y="L.trace.y" :width="L.trace.w" :height="narrow ? 66 : 74" rx="10" />
          <text class="trace-head" :x="L.trace.x + 12" :y="L.trace.y + 17">epic · rlar · 20261005T091233Z</text>
          <text v-if="!narrow" class="trace-tag" :x="L.trace.x + L.trace.w - 12" :y="L.trace.y + 17" text-anchor="end">its trace, in Perfetto</text>
          <g v-for="(lane, k) in SLICES" :key="k">
            <text class="track-name" :x="L.trace.x + 12" :y="L.trace.y + (narrow ? 37 : 40) + k * (narrow ? 18 : 21)">{{ k ? 'reviewer' : 'actor' }}</text>
            <rect class="track" :x="trackX" :y="L.trace.y + (narrow ? 28 : 30) + k * (narrow ? 18 : 21)" :width="trackW" height="13" rx="3" />
            <rect
              v-for="(s, i) in lane"
              :key="i"
              class="slice"
              :class="[`slice-${k}-${i}`, k ? 'slice-r' : 'slice-a']"
              :x="trackX + s.at * trackW"
              :y="L.trace.y + (narrow ? 28 : 30) + k * (narrow ? 18 : 21)"
              :width="s.w * trackW"
              height="13"
              rx="3"
            />
          </g>
          <line class="head" :x1="trackX" :x2="trackX" :y1="L.trace.y + 24" :y2="L.trace.y + (narrow ? 62 : 68)" />
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

.grid-dot {
  fill: var(--hmz-stage-line);
}

.cmd-box,
.trace-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.cmd-ring {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.cmd-line,
.piece-text,
.sep,
.dash {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  fill: var(--hmz-stage-ink);
}

.prompt {
  fill: var(--hmz-stage-dim);
}

.task {
  fill: var(--hmz-warm);
}

.hl {
  fill: color-mix(in srgb, var(--hmz-lane-1) 16%, transparent);
}

.chip-bg {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.4;
}

.chip-0 .piece-text {
  font-weight: 700;
}

.brace-path {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.4;
  stroke-linecap: round;
}

.brace-word {
  font-size: 12px;
  font-style: italic;
  fill: var(--hmz-lane-1);
}

.link-path,
.ws-arrow {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.3;
  stroke-dasharray: 4 4;
}

.ws-arrow {
  stroke: var(--hmz-warm);
}

.lane-name {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.lane-count,
.lane-note {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.session {
  fill: color-mix(in srgb, var(--hmz-lane-1) 6%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-1);
  stroke-width: 1.2;
}

.session-r {
  fill: color-mix(in srgb, var(--hmz-accent-2) 6%, var(--hmz-stage-card));
  stroke: var(--hmz-accent-2);
}

.turn rect {
  fill: var(--hmz-lane-1);
}

.turn-r rect {
  fill: var(--hmz-accent-2);
}

.turn text {
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.turn .turn-ring {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
}

.code-text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.env-bg {
  fill: color-mix(in srgb, var(--hmz-warm) 22%, transparent);
  stroke: var(--hmz-warm);
}

.env-text {
  font-weight: 700;
  fill: var(--hmz-warm);
}

.env-ring {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2;
}

.ws-box {
  fill: color-mix(in srgb, var(--hmz-warm) 7%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
  stroke-width: 1.4;
}

.ws-name {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.ws-path,
.ws-file {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.mark-word {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.trace-head {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.trace-tag,
.track-name {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.track {
  fill: var(--hmz-stage-line);
  opacity: 0.6;
}

.slice-a {
  fill: var(--hmz-lane-1);
}

.slice-r {
  fill: var(--hmz-accent-2);
}

.head {
  stroke: var(--hmz-warm);
  stroke-width: 2;
}
</style>
