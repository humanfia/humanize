<script setup lang="ts">
// Picking a run up, from where the user sits. A loop counts its rounds and its flow saves the
// count the moment it changes, so whichever way the run stops -- ctrl+c, a spent budget, the
// machine switched off -- the saved record is left behind. `/resume` at the prompt (or
// `hmz exec --resume` in a script) looks through the runs kept for this directory and takes the
// last one of a flow that can be picked up. What it starts is a new run, with an id, sessions,
// a trace and an `/epics` row of its own, beginning from the record: it counts on from 40 to
// 41. The flow's kept state and its temporary copies carry over; the agents' conversations and
// what the budget had spent do not. A simulation: the run names and rounds are invented.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { createFx, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'
import { rig, type Point, type Shot } from '../../motion/camera'
import { brace, braceD, curve, draw, pop, pulse, ring, rise, shake } from '../user-kit/moves'

const BEATS = [
  'A loop counts its rounds, and its flow saves the count as it changes',
  'ctrl+c, a spent budget, the machine off: any of them stops the run',
  'Whichever it was, the saved record stays behind: round: 40',
  '/resume finds the last run here of a flow that can be picked up',
  'A new run of its own starts from the record and counts on: round 41',
  'What carries over, and what does not',
]

const FIRST = [37, 38, 39, 40]
const SECOND = [41, 42]
const CAUSES = ['ctrl+c', 'budget spent', 'machine off']
const RUNS = [
  { name: 'chat · 11:02', note: "can't be picked up" },
  { name: 'ralph_loop · 09:12', note: 'resumable' },
  { name: 'ralph_loop · 08:40', note: 'resumable' },
]
const OWN = ['sessions', 'trace', '/epics row']
const CARRY = [
  { name: 'kept state', note: 'round: 40', yes: true },
  { name: 'temp copies', note: 'where they were', yes: true },
  { name: 'conversations', note: 'fresh sessions', yes: false },
  { name: 'budget spent', note: 'counted from zero', yes: false },
]

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Layout {
  w: number
  h: number
  runA: Box
  runB: Box
  /** Where a run card's round boxes start, from its corner, and their step. */
  strip: { dx: number; dy: number; step: number; w: number }
  causes: { y: number; w: number; xs: number[] }
  record: Box
  recordBrace: number
  resume: Box
  rowW: number
  own: { y: number; w: number; xs: number[] }
  ownBrace: number
  cells: Box[]
  shots: Record<'open' | 'causes' | 'record' | 'resume' | 'newrun' | 'carry', Partial<Shot>>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  runA: { x: 16, y: 16, w: 220, h: 98 },
  runB: { x: 436, y: 44, w: 188, h: 98 },
  strip: { dx: 12, dy: 74, step: 46, w: 40 },
  causes: { y: 126, w: 78, xs: [8, 87, 166] },
  record: { x: 36, y: 174, w: 180, h: 52 },
  recordBrace: 234,
  resume: { x: 252, y: 16, w: 170, h: 236 },
  rowW: 154,
  own: { y: 152, w: 62, xs: [436, 499, 562] },
  ownBrace: 184,
  cells: [0, 1, 2, 3].map((i) => ({ x: 16 + i * 153, y: 276, w: 146, h: 66 })),
  shots: {
    open: { x: 126, y: 120, s: 1.4 },
    causes: { x: 126, y: 104, s: 1.45 },
    record: { x: 126, y: 170, s: 1.4 },
    resume: { x: 336, y: 136, s: 1.4 },
    newrun: { x: 470, y: 150, s: 1.3 },
    carry: { x: 320, y: 180, s: 1 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 780,
  runA: { x: 12, y: 12, w: 336, h: 98 },
  runB: { x: 12, y: 470, w: 336, h: 98 },
  strip: { dx: 170, dy: 70, step: 40, w: 34 },
  causes: { y: 122, w: 104, xs: [12, 128, 244] },
  record: { x: 90, y: 166, w: 180, h: 52 },
  recordBrace: 226,
  resume: { x: 12, y: 270, w: 336, h: 186 },
  rowW: 312,
  own: { y: 578, w: 104, xs: [12, 128, 244] },
  ownBrace: 610,
  cells: [0, 1, 2, 3].map((i) => ({ x: 12 + (i % 2) * 174, y: 652 + Math.floor(i / 2) * 64, w: 162, h: 58 })),
  shots: {
    open: { x: 180, y: 130, s: 1.06 },
    causes: { x: 180, y: 130, s: 1.06 },
    record: { x: 180, y: 180, s: 1.06 },
    resume: { x: 180, y: 360, s: 1.06 },
    newrun: { x: 180, y: 530, s: 1.06 },
    carry: { x: 180, y: 390, s: 1 },
  },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const boxX = (run: Box, i: number) => run.x + L.value.strip.dx + i * L.value.strip.step
const boxY = (run: Box) => run.y + L.value.strip.dy
const counter = (run: Box): Point => ({ x: run.x + 92, y: run.y + 50 })
const recordAt = computed<Point>(() => ({ x: L.value.record.x + 100, y: L.value.record.y + 36 }))
const rowY = (i: number) => L.value.resume.y + (narrow.value ? 80 : 88) + i * 38
const causeC = (i: number): Point => ({ x: L.value.causes.xs[i] + L.value.causes.w / 2, y: L.value.causes.y + 13 })

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
      a: () => palette.lane[0],
      keep: () => palette.accent,
      stop: () => palette.danger,
      b: () => palette.accent2,
    }

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(
      q(
        '.run-a, .run-b, .rbox, .cause, .stamp, .blackout, .record, .rec-line, .brace-path, .brace-label, .resume, .typed-or, .runs-head, .row, .strike, .scan, .picked, .own, .table, .cell-yes, .cell-no, .cell-lit',
      ),
      { autoAlpha: 0 },
      0,
    )
    tl.set(q('.meter'), { scaleX: 1, transformOrigin: '0% 50%' }, 0)
    tl.set(one('.count-a'), { text: '36' }, 0)
    tl.set(one('.rec-val'), { text: '36' }, 0)
    tl.set(one('.count-b'), { text: '–' }, 0)

    // 0 · a loop counts, and the count is saved each time it changes.
    tl.addLabel('beat-0', 0)
    rise(tl, one('.run-a'), 0.15)
    rise(tl, one('.record'), 0.5, { y: 10 })
    FIRST.forEach((n, i) => {
      const t = 1.0 + i * 1.05
      tl.set(one('.count-a'), { text: String(n) }, t)
      pulse(tl, one('.count-a-g'), t, 1.15)
      pop(tl, one(`.rbox-a-${i}`), t)
      cam.beam(counter(l.runA), recordAt.value, c.keep, t + 0.1, { duration: 0.55, bend: 0.2, burst: 6 })
      tl.set(one('.rec-val'), { text: String(n) }, t + 0.65)
      ring(tl, one('.rec-ring'), t + 0.65, { to: 1.12, duration: 0.6 })
    })

    // 1 · any of three things stops it.
    const T1 = 5.4
    tl.addLabel('beat-1', T1)
    cam.shot(l.shots.causes, T1, 1.2)
    CAUSES.forEach((_, i) => {
      const t = T1 + 0.7 + i * 1.4
      pop(tl, one(`.cause-${i}`), t)
      if (i === 1) tl.to(one('.meter'), { scaleX: 0, duration: 0.5, ease: 'power2.in' }, t + 0.25)
      cam.beam(causeC(i), { x: l.runA.x + l.runA.w * 0.7, y: l.runA.y + l.runA.h - 6 }, c.stop, t + 0.45, { duration: 0.45, bend: 0.25, burst: 12 })
      shake(tl, one('.run-a-in'), t + 0.9, 5)
      if (i === 0) pop(tl, one('.stamp'), t + 0.9)
      else pulse(tl, one('.stamp'), t + 0.9, 1.12)
      ring(tl, one('.stamp-ring'), t + 0.9, { to: 1.4 })
      if (i === 2) {
        tl.to(one('.blackout'), { autoAlpha: 0.75, duration: 0.15 }, t + 0.9)
        tl.to(one('.blackout'), { autoAlpha: 0, duration: 0.8 }, t + 1.2)
      }
    })

    // 2 · whichever it was, the record stays.
    const T2 = T1 + 5.2
    tl.addLabel('beat-2', T2)
    cam.shot(l.shots.record, T2, 1.3)
    draw(tl, q('.rec-line'), T2 + 0.5, { duration: 0.7, stagger: 0.18 })
    ring(tl, one('.rec-ring'), T2 + 1.3, { to: 1.2 })
    pulse(tl, one('.rec-val-g'), T2 + 1.3, 1.2)
    cam.flare(recordAt.value, c.keep, T2 + 1.3, 22, 90)
    brace(tl, q, '.brace-rec', T2 + 1.7)
    tl.to(one('.run-a-in'), { autoAlpha: 0.55, duration: 0.6 }, T2 + 2.2)

    // 3 · /resume finds the last run here that can be picked up.
    const T3 = T2 + 3.4
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.resume, T3, 1.4)
    rise(tl, one('.resume'), T3 + 0.3)
    tl.set(one('.typed'), { text: '' }, 0)
    tl.to(one('.typed'), { text: { value: '❯ /resume' }, duration: 0.5, ease: 'none' }, T3 + 0.8)
    rise(tl, one('.typed-or'), T3 + 1.4, { y: 6 })
    rise(tl, one('.runs-head'), T3 + 1.7, { y: 6 })
    rise(tl, q('.row'), T3 + 1.9, { x: 10, y: 0, stagger: 0.12 })
    tl.fromTo(one('.scan'), { autoAlpha: 0, y: 0 }, { autoAlpha: 1, duration: 0.25 }, T3 + 2.6)
    draw(tl, one('.strike'), T3 + 3.0, { duration: 0.4 })
    tl.to(one('.row-0'), { autoAlpha: 0.45, duration: 0.3 }, T3 + 3.2)
    tl.to(one('.scan'), { y: 38, duration: 0.55, ease: 'cine' }, T3 + 3.3)
    pop(tl, one('.picked'), T3 + 3.9)
    ring(tl, one('.row-ring'), T3 + 3.95)

    // 4 · a new run of its own starts from the record and counts on.
    const T4 = T3 + 5.0
    tl.addLabel('beat-4', T4)
    cam.shot(l.shots.newrun, T4, 1.5)
    rise(tl, one('.run-b'), T4 + 0.4, { x: 14, y: 0 })
    cam.beam(recordAt.value, counter(l.runB), c.keep, T4 + 1.1, { duration: 1.0, bend: -0.2, burst: 14 })
    tl.set(one('.count-b'), { text: '40' }, T4 + 2.1)
    SECOND.forEach((n, i) => {
      const t = T4 + 2.6 + i * 1.0
      tl.set(one('.count-b'), { text: String(n) }, t)
      pulse(tl, one('.count-b-g'), t, 1.2)
      pop(tl, one(`.rbox-b-${i}`), t)
    })
    pop(tl, q('.own'), T4 + 3.0, { stagger: 0.15 })
    brace(tl, q, '.brace-own', T4 + 3.6)

    // 5 · what carries over, and what does not.
    const T5 = T4 + 5.2
    tl.addLabel('beat-5', T5)
    cam.shot(l.shots.carry, T5, 1.6)
    rise(tl, one('.table'), T5 + 0.6, { y: 12 })
    const from: Point = { x: l.runA.x + l.runA.w / 2, y: l.runA.y + l.runA.h / 2 }
    const toB: Point = { x: l.runB.x + l.runB.w / 2, y: l.runB.y + l.runB.h / 2 }
    CARRY.forEach((row, i) => {
      const t = T5 + 1.2 + i * 0.9
      if (row.yes) {
        cam.beam(from, toB, c.keep, t, { duration: 0.75, bend: 0.18, burst: 10 })
        tl.to(one(`.cell-${i} .cell-lit`), { autoAlpha: 1, duration: 0.4 }, t + 0.7)
        pop(tl, one(`.cell-${i} .cell-yes`), t + 0.7)
      } else {
        const mid = { x: (from.x + toB.x) / 2, y: (from.y + toB.y) / 2 }
        cam.beam(from, mid, c.stop, t, { duration: 0.5, bend: 0.18, ease: 'cine.in' })
        cam.flare(mid, c.stop, t + 0.5, 16, 80)
        pop(tl, one(`.cell-${i} .cell-no`), t + 0.6)
        shake(tl, one(`.cell-${i}`), t + 0.7, 4)
      }
      ring(tl, one(`.cell-${i} .cell-ring`), t + 0.7, { to: 1.06 })
    })
    tl.addLabel('rest', T5 + 5.0)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T5 + 9)
  },
})

const own = (i: number) => ({ x: L.value.own.xs[i], w: L.value.own.w })
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="6 / 13"
    label="A run of ralph_loop counts its rounds, 37, 38, 39, 40, and its flow saves the count in a record each time it changes. The run is stopped: by ctrl+c, by a spent budget, or by the machine being switched off. Whichever it was, the saved record stays behind, holding round: 40. At the prompt, /resume (or hmz exec --resume from a script) looks through the runs kept for this directory: it skips a chat run, which cannot be picked up, and takes the last run of a flow that can. What it starts is a new run, with its own id, sessions, trace and /epics row, which begins from the record and counts on to round 41, then 42. What carries over: the flow's kept state and its temporary copies. What does not: the agents' conversations, which start in fresh sessions, and what the budget had spent, which is counted from zero."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <pattern id="pu-dots" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" class="grid-dot" />
        </pattern>
      </defs>
      <g class="far"><rect x="-400" y="-400" :width="L.w + 800" :height="L.h + 800" fill="url(#pu-dots)" /></g>

      <g class="world">
        <!-- The run that stops. -->
        <g class="run-a">
          <g class="run-a-in">
            <rect class="card" :x="L.runA.x" :y="L.runA.y" :width="L.runA.w" :height="L.runA.h" rx="10" />
            <text class="run-head" :x="L.runA.x + 12" :y="L.runA.y + 20">run 0912Z · ralph_loop</text>
            <text class="round-word" :x="L.runA.x + 12" :y="L.runA.y + 54">round</text>
            <g class="count-a-g"><text class="count count-a" :x="L.runA.x + 56" :y="L.runA.y + 56">36</text></g>
            <g v-for="(n, i) in FIRST" :key="n" class="rbox" :class="`rbox-a-${i}`">
              <rect class="rbox-bg" :x="boxX(L.runA, i)" :y="boxY(L.runA)" :width="L.strip.w" height="16" rx="4" />
              <text class="rbox-word" :x="boxX(L.runA, i) + L.strip.w / 2" :y="boxY(L.runA) + 12" text-anchor="middle">{{ n }}</text>
            </g>
            <rect class="blackout" :x="L.runA.x" :y="L.runA.y" :width="L.runA.w" :height="L.runA.h" rx="10" />
          </g>
          <g class="stamp">
            <rect class="stamp-bg" :x="L.runA.x + L.runA.w - 96" :y="L.runA.y + 38" width="86" height="20" rx="10" />
            <text class="stamp-word" :x="L.runA.x + L.runA.w - 53" :y="L.runA.y + 52" text-anchor="middle">stopped</text>
            <g :transform="`translate(${L.runA.x + L.runA.w - 53} ${L.runA.y + 48})`">
              <rect class="stamp-ring" x="-43" y="-10" width="86" height="20" rx="10" />
            </g>
          </g>
        </g>

        <!-- Three ways it stops. -->
        <g v-for="(word, i) in CAUSES" :key="word" class="cause" :class="`cause-${i}`">
          <rect class="cause-bg" :class="{ kbd: i === 0 }" :x="L.causes.xs[i]" :y="L.causes.y" :width="L.causes.w" height="26" rx="6" />
          <text class="cause-word" :x="L.causes.xs[i] + L.causes.w / 2" :y="L.causes.y + (i === 1 ? 15 : 17)" text-anchor="middle">{{ word }}</text>
          <rect v-if="i === 1" class="meter" :x="L.causes.xs[i] + 8" :y="L.causes.y + 19" :width="L.causes.w - 16" height="3" rx="1.5" />
        </g>
        <path v-for="i in [0, 1, 2]" :key="`rl${i}`" class="rec-line" :d="curve({ x: causeC(i).x, y: L.causes.y + 27 }, { x: L.record.x + L.record.w / 2 + (i - 1) * 40, y: L.record.y }, (1 - i) * 0.15)" />

        <!-- The saved record. -->
        <g class="record">
          <rect class="record-bg" :x="L.record.x" :y="L.record.y" :width="L.record.w" :height="L.record.h" rx="10" />
          <text class="record-head" :x="L.record.x + 12" :y="L.record.y + 18">saved record</text>
          <g class="rec-val-g">
            <text class="record-key" :x="L.record.x + 12" :y="L.record.y + 40">round:</text>
            <text class="record-key rec-val" :x="L.record.x + 72" :y="L.record.y + 40">36</text>
          </g>
          <g :transform="`translate(${L.record.x + L.record.w / 2} ${L.record.y + L.record.h / 2})`">
            <rect class="rec-ring" :x="-L.record.w / 2" :y="-L.record.h / 2" :width="L.record.w" :height="L.record.h" rx="10" />
          </g>
        </g>
        <g class="brace-rec">
          <path class="brace-path" :d="braceD({ x: L.record.x + 4, y: L.recordBrace }, { x: L.record.x + L.record.w - 4, y: L.recordBrace }, 9)" />
          <g class="brace-label">
            <text class="brace-word" :x="L.record.x + L.record.w / 2" :y="L.recordBrace + 23" text-anchor="middle">kept, whichever way it stopped</text>
          </g>
        </g>

        <!-- /resume, and the runs kept here. -->
        <g class="resume">
          <rect class="card" :x="L.resume.x" :y="L.resume.y" :width="L.resume.w" :height="L.resume.h" rx="10" />
          <text class="typed" :x="L.resume.x + 12" :y="L.resume.y + 24">❯ /resume</text>
          <g class="typed-or"><text class="or-word" :x="L.resume.x + 12" :y="L.resume.y + 42">or hmz exec --resume</text></g>
          <g class="runs-head"><text class="head-word" :x="L.resume.x + 12" :y="L.resume.y + (narrow ? 64 : 66)">runs here · ~/shop</text></g>
          <rect class="scan" :x="L.resume.x + 8" :y="rowY(0) - 14" :width="L.rowW" height="34" rx="7" />
          <g v-for="(run, i) in RUNS" :key="run.name" class="row" :class="`row-${i}`">
            <text class="row-name" :x="L.resume.x + 16" :y="rowY(i)">{{ run.name }}</text>
            <text class="row-note" :class="{ dim: i === 0 }" :x="L.resume.x + 16" :y="rowY(i) + 14">{{ run.note }}</text>
          </g>
          <path class="strike" :d="`M${L.resume.x + 14} ${rowY(0) - 4} L${L.resume.x + 16 + 12 * 6.6} ${rowY(0) - 4}`" />
          <g :transform="`translate(${L.resume.x + 8 + L.rowW / 2} ${rowY(1) + 3})`">
            <rect class="row-ring" :x="-L.rowW / 2" y="-17" :width="L.rowW" height="34" rx="7" />
          </g>
          <g class="picked">
            <text class="picked-word" :x="L.resume.x + L.rowW" :y="rowY(1) + 14" text-anchor="end">← picked</text>
          </g>
        </g>

        <!-- The new run. -->
        <g class="run-b">
          <rect class="card card-b" :x="L.runB.x" :y="L.runB.y" :width="L.runB.w" :height="L.runB.h" rx="10" />
          <text class="run-head" :x="L.runB.x + 12" :y="L.runB.y + 20">run 1104Z · ralph_loop</text>
          <text class="round-word" :x="L.runB.x + 12" :y="L.runB.y + 54">round</text>
          <g class="count-b-g"><text class="count count-b" :x="L.runB.x + 56" :y="L.runB.y + 56">–</text></g>
          <rect class="new-bg" :x="L.runB.x + L.runB.w - 70" :y="L.runB.y + 38" width="60" height="20" rx="10" />
          <text class="new-word" :x="L.runB.x + L.runB.w - 40" :y="L.runB.y + 52" text-anchor="middle">new run</text>
          <g v-for="(n, i) in SECOND" :key="n" class="rbox" :class="`rbox-b-${i}`">
            <rect class="rbox-bg rbox-b" :x="boxX(L.runB, i)" :y="boxY(L.runB)" :width="L.strip.w" height="16" rx="4" />
            <text class="rbox-word" :x="boxX(L.runB, i) + L.strip.w / 2" :y="boxY(L.runB) + 12" text-anchor="middle">{{ n }}</text>
          </g>
        </g>
        <g v-for="(word, i) in OWN" :key="word" class="own">
          <rect class="own-bg" :x="own(i).x" :y="L.own.y" :width="own(i).w" height="22" rx="6" />
          <text class="own-word" :x="own(i).x + own(i).w / 2" :y="L.own.y + 15" text-anchor="middle">{{ word }}</text>
        </g>
        <g class="brace-own">
          <path class="brace-path" :d="braceD({ x: L.own.xs[0] + 2, y: L.ownBrace - 6 }, { x: L.own.xs[2] + L.own.w - 2, y: L.ownBrace - 6 }, 9)" />
          <g class="brace-label">
            <text class="brace-word" :x="(L.own.xs[0] + L.own.xs[2] + L.own.w) / 2" :y="L.ownBrace + 17" text-anchor="middle">all its own</text>
          </g>
        </g>

        <!-- What carries over. -->
        <g class="table">
          <g v-for="(row, i) in CARRY" :key="row.name" class="cell" :class="`cell-${i}`">
            <rect class="cell-bg" :x="L.cells[i].x" :y="L.cells[i].y" :width="L.cells[i].w" :height="L.cells[i].h" rx="10" />
            <rect class="cell-lit" :x="L.cells[i].x" :y="L.cells[i].y" :width="L.cells[i].w" :height="L.cells[i].h" rx="10" />
            <text class="cell-name" :x="L.cells[i].x + 12" :y="L.cells[i].y + 22">{{ row.name }}</text>
            <text class="cell-note" :x="L.cells[i].x + 12" :y="L.cells[i].y + 40">{{ row.note }}</text>
            <g v-if="row.yes" class="cell-yes">
              <text class="yes-word" :x="L.cells[i].x + L.cells[i].w - 12" :y="L.cells[i].y + 22" text-anchor="end">yes ✓</text>
            </g>
            <g v-else class="cell-no">
              <text class="no-word" :x="L.cells[i].x + L.cells[i].w - 12" :y="L.cells[i].y + 22" text-anchor="end">no ✕</text>
            </g>
            <g :transform="`translate(${L.cells[i].x + L.cells[i].w / 2} ${L.cells[i].y + L.cells[i].h / 2})`">
              <rect class="cell-ring" :class="{ bad: !row.yes }" :x="-L.cells[i].w / 2" :y="-L.cells[i].h / 2" :width="L.cells[i].w" :height="L.cells[i].h" rx="10" />
            </g>
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

.grid-dot {
  fill: var(--hmz-stage-line);
}

.card,
.cell-bg {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.card-b {
  stroke: var(--hmz-accent-2);
  stroke-width: 1.6;
}

.run-head,
.head-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.head-word {
  font-weight: 400;
  fill: var(--hmz-stage-dim);
}

.round-word {
  font-size: 12px;
  fill: var(--hmz-stage-dim);
}

.count {
  font-family: var(--vp-font-family-mono);
  font-size: 26px;
  font-weight: 700;
  fill: var(--hmz-lane-1);
}

.count-b {
  fill: var(--hmz-accent-2);
}

.rbox-bg {
  fill: color-mix(in srgb, var(--hmz-lane-1) 18%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-1);
}

.rbox-b {
  fill: color-mix(in srgb, var(--hmz-accent-2) 18%, var(--hmz-stage-card));
  stroke: var(--hmz-accent-2);
}

.rbox-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.blackout {
  fill: var(--hmz-stage-dim);
}

.stamp-bg {
  fill: var(--hmz-lane-5);
}

.stamp-word,
.new-word {
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.new-bg {
  fill: var(--hmz-accent-2);
}

.cause-bg {
  fill: color-mix(in srgb, var(--hmz-lane-5) 10%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-5);
  stroke-width: 1.2;
}

.cause-bg.kbd {
  stroke-width: 1.2;
  stroke-dasharray: none;
}

.cause-word {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-lane-5);
}

.cause-0 .cause-word {
  font-family: var(--vp-font-family-mono);
}

.meter {
  fill: var(--hmz-lane-5);
}

.rec-line {
  fill: none;
  stroke: var(--hmz-lane-5);
  stroke-width: 1.3;
  stroke-dasharray: 4 4;
}

.record-bg {
  fill: color-mix(in srgb, var(--hmz-accent) 12%, var(--hmz-stage-card));
  stroke: var(--hmz-accent);
  stroke-width: 1.6;
}

.record-head {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.record-key {
  font-family: var(--vp-font-family-mono);
  font-size: 15px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.rec-ring,
.row-ring,
.stamp-ring,
.cell-ring {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  opacity: 0;
}

.stamp-ring {
  stroke: var(--hmz-lane-5);
}

.cell-ring.bad {
  stroke: var(--hmz-lane-5);
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
  fill: var(--hmz-accent);
}

.typed {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-accent-2);
}

.or-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.scan {
  fill: color-mix(in srgb, var(--hmz-accent-2) 14%, transparent);
  stroke: var(--hmz-accent-2);
  stroke-width: 1.2;
}

.row-name {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.row-note {
  font-size: 11px;
  fill: var(--hmz-accent);
}

.row-note.dim {
  fill: var(--hmz-lane-5);
}

.strike {
  stroke: var(--hmz-lane-5);
  stroke-width: 1.6;
}

.picked-word {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent-2);
}

.own-bg {
  fill: color-mix(in srgb, var(--hmz-accent-2) 12%, var(--hmz-stage-card));
  stroke: var(--hmz-accent-2);
}

.own-word {
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.brace-own .brace-word {
  fill: var(--hmz-accent-2);
}

.cell-lit {
  fill: color-mix(in srgb, var(--hmz-accent) 12%, var(--hmz-stage-card));
  stroke: var(--hmz-accent);
}

.cell-name {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.cell-note {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.yes-word,
.no-word {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.no-word {
  fill: var(--hmz-lane-5);
}
</style>
