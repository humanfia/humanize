<script setup lang="ts">
// How a loop works, from "Loops": where `spawn` sits decides what the next turn remembers, and
// four things end a loop. Above, the two built-in loops side by side, a column per round and
// in it the session's history: `ralph_loop` spawns inside the loop, so every round is a new
// session holding only this round's turn (it knows the task and the repository), while
// `stateful_ralph` spawns before it, so one session's history grows a turn a round. Below,
// `stateful_ralph` round by round: after every round it writes the session into
// `ctx.state["session"]`, which keeps the conversation as it stands then; the run is stopped
// and picked up with `--resume`, and since `resumable=True` the session read back carries on
// round 3's conversation at round 4; a turn that raises `HarnessError` is not caught, so it
// ends the run. Drawn from src/hmz/flows/builtin/ralph_loop and stateful_ralph, and
// docs/weaver/loops.md. The answers are simulated.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { count, createFx, type Fx } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'Where spawn sits: inside, or before',
  'A fresh session a round, or one that grows',
  'Four things end a loop',
  'Each round, the session is kept in ctx.state',
  'resumable=True: --resume carries it on',
  'A failed turn, uncaught, ends the run',
]

type Tok = [cls: '' | 'kw' | 'fn', text: string]
interface Panel {
  title: string
  flow: string
  code: Tok[][]
  /** Which line is the spawn. */
  spawn: number
  knows: [string, string]
}
const PANELS: Panel[] = [
  {
    title: 'spawn inside the loop',
    flow: 'ralph_loop',
    code: [
      [['kw', 'while '], ['', 'True:']],
      [['', '  s = '], ['kw', 'await '], ['fn', 'agent.spawn'], ['', '()']],
      [['kw', '  await '], ['fn', 'agent.run'], ['', '(task, session=s)']],
    ],
    spawn: 1,
    knows: ['each round knows', 'the task + the repo'],
  },
  {
    title: 'spawn before the loop',
    flow: 'stateful_ralph',
    code: [
      [['', 's = '], ['kw', 'await '], ['fn', 'agent.spawn'], ['', '()']],
      [['kw', 'while '], ['', 'True:']],
      [['kw', '  await '], ['fn', 'agent.run'], ['', '(task, session=s)']],
    ],
    spawn: 0,
    knows: ['each round knows', 'every round before'],
  },
]
const ROUNDS = 4

const ENDERS = [
  { code: 'return', why: 'a check of yours' },
  { code: 'for … in range(…)', why: 'a round limit' },
  { code: 'HarnessError', why: 'a failed turn, uncaught' },
  { code: 'BudgetExceeded', why: 'the run’s budget, spent' },
]

/** stateful_ralph, round by round: what each said, and the round whose conversation
 *  `ctx.state["session"]` holds after it (0 for none written). */
type Said = 'said' | 'failed'
const RUN: { n: number; said: Said; kept: number }[] = [
  { n: 1, said: 'said', kept: 1 },
  { n: 2, said: 'said', kept: 2 },
  { n: 3, said: 'said', kept: 3 },
  { n: 4, said: 'said', kept: 4 },
  { n: 5, said: 'failed', kept: 0 },
]
const GLYPH: Record<Said, string> = { said: '"…"', failed: '✕' }
const KEPT = (n: number) => (n > 0 ? `r${Math.round(n)}` : '—')
/** The stop falls after this many rounds. */
const STOP_AFTER = 3

const NOTES: [string, string][] = [
  ['state["session"] = session —', 'the conversation kept as it stands after the round'],
  ['stopped; --resume reads ctx.state["session"],', 'so round 4 carries on round 3’s conversation'],
  ['round 5 failed: HarnessError,', 'uncaught, so the run ends with it'],
]

interface Layout {
  w: number
  h: number
  /** Each panel's top-left, and their width and height. */
  panels: { x: number; y: number }[]
  pw: number
  ph: number
  /** The enders: top-left of each chip, and a chip's width. */
  enders: { x: number; y: number }[]
  ew: number
  /** The strip. */
  stripY: number
  state: { x: number; y: number; w: number; h: number }
  rowsX: number
  cellsX: number
  cellsY: number
  cw: number
  sw: number
  gap: number
  noteY: number
  open: { x: number; y: number; s: number }
  whole: { x: number; y: number; s: number }
  strip: { x: number; y: number; s: number }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  panels: [
    { x: 14, y: 12 },
    { x: 326, y: 12 },
  ],
  pw: 300,
  ph: 164,
  enders: [0, 1, 2, 3].map((i) => ({ x: 14 + i * 154, y: 188 })),
  ew: 148,
  stripY: 246,
  state: { x: 14, y: 256, w: 96, h: 74 },
  rowsX: 122,
  cellsX: 176,
  cellsY: 256,
  cw: 56,
  sw: 46,
  gap: 9,
  noteY: 346,
  open: { x: 164, y: 96, s: 1.3 },
  whole: { x: 320, y: 180, s: 1 },
  strip: { x: 320, y: 186, s: 1.02 },
}

const NARROW: Layout = {
  w: 360,
  h: 640,
  panels: [
    { x: 14, y: 10 },
    { x: 14, y: 182 },
  ],
  pw: 332,
  ph: 164,
  enders: [0, 1, 2, 3].map((i) => ({ x: 14 + (i % 2) * 169, y: 360 + Math.floor(i / 2) * 42 })),
  ew: 163,
  stripY: 468,
  state: { x: 14, y: 476, w: 332, h: 30 },
  rowsX: 14,
  cellsX: 62,
  cellsY: 516,
  cw: 37,
  sw: 30,
  gap: 4,
  noteY: 594,
  open: { x: 180, y: 96, s: 1.22 },
  whole: { x: 180, y: 320, s: 1 },
  strip: { x: 180, y: 332, s: 1.04 },
}

const CELL_H = 40
const BLOCK = 10
const STEP = 12

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const codeY = (p: number, i: number) => L.value.panels[p].y + 42 + i * 17
const colX = (p: number, k: number) => L.value.panels[p].x + 20 + k * 38
const base = (p: number) => L.value.panels[p].y + L.value.ph - 24
/** The x of each item along the strip: the rounds, with the stop between 3 and 4. */
const cellX = (n: number) => {
  const l = L.value
  const k = n - 1
  return l.cellsX + k * (l.cw + l.gap) + (n > STOP_AFTER ? l.sw + l.gap : 0)
}
const stopX = computed(() => L.value.cellsX + STOP_AFTER * (L.value.cw + L.value.gap))
const cellMid = (n: number) => cellX(n) + L.value.cw / 2

const scene = useScene({
  still: 'rest',
  repeatDelay: 1.2,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const at = (sel: string) => q(sel)
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), fx: () => fx, start: l.open })
    const lane1 = () => palette.lane[0]
    const ok = () => palette.accent
    const danger = () => palette.danger
    const warm = () => palette.warm

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.panel, .code-line, .knows, .spark, .block, .rlabel, .ender, .strip-head, .state, .rowlabel, .cell, .kept, .stop, .note, .ender-hot'), { opacity: 0 }, 0)
    tl.set(at('.thread, .carry'), { drawSVG: '0%' }, 0)
    tl.set(at('.spawn-bar'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(at('.block'), { scaleY: 0, transformOrigin: '50% 100%' }, 0)

    // 0 · the two loops, and where each puts its spawn.
    tl.addLabel('beat-0', 0)
    tl.to(at('.panel'), { opacity: 1, duration: 0.6, stagger: 0.25 }, 0.1)
    tl.fromTo(at('.code-line'), { x: -8 }, { opacity: 1, x: 0, duration: 0.5, stagger: 0.1 }, 0.4)
    tl.to(at('.spawn-bar'), { scaleX: 1, duration: 0.7, ease: 'cine', stagger: 0.5 }, 1.4)
    cam.shot(l.whole, 1.3, 1.9)

    // 1 · four rounds of each: a new session every round, or one history growing.
    const B1 = 3.4
    tl.addLabel('beat-1', B1)
    const blocks = at('.block')
    const sparks = at('.spark')
    const rlabels = at('.rlabel')
    // Blocks are laid out panel by panel: ralph's ROUNDS, then the stateful triangle.
    const tri = (k: number, j: number) => ROUNDS + (k * (k + 1)) / 2 + j
    for (let k = 0; k < ROUNDS; k += 1) {
      const t = B1 + 0.3 + k * 1.05
      // ralph: a spawn, then one turn in it.
      tl.fromTo(at('.spawn-bar')[0], { opacity: 0.55 }, { opacity: 1, duration: 0.25, yoyo: true, repeat: 1 }, t)
      tl.to(sparks[k], { opacity: 1, duration: 0.15 }, t + 0.2)
      tl.fromTo(sparks[k], { scale: 0, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.45, ease: 'back.out(3)' }, t + 0.2)
      cam.flare({ x: colX(0, k) + 15, y: base(0) + 6 }, lane1, t + 0.2, 10, 60)
      tl.to(blocks[k], { opacity: 1, scaleY: 1, duration: 0.45 }, t + 0.45)
      // stateful: the history so far is carried, and this round's turn goes on top.
      if (k === 0) {
        tl.to(sparks[ROUNDS], { opacity: 1, duration: 0.15 }, t + 0.2)
        tl.fromTo(sparks[ROUNDS], { scale: 0, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.45, ease: 'back.out(3)' }, t + 0.2)
        cam.flare({ x: colX(1, 0) + 15, y: base(1) + 6 }, lane1, t + 0.2, 10, 60)
      } else {
        tl.to(at('.thread')[k - 1], { drawSVG: '100%', duration: 0.4, ease: 'none' }, t + 0.1)
      }
      for (let j = 0; j < k; j += 1) tl.to(blocks[tri(k, j)], { opacity: 0.5, scaleY: 1, duration: 0.3 }, t + 0.3 + j * 0.05)
      tl.to(blocks[tri(k, k)], { opacity: 1, scaleY: 1, duration: 0.45 }, t + 0.45)
      tl.to([rlabels[k], rlabels[ROUNDS + k]], { opacity: 1, duration: 0.3 }, t + 0.4)
    }
    tl.to(at('.knows'), { opacity: 1, duration: 0.6, stagger: 0.2 }, B1 + 4.6)

    // 2 · what ends it: four things.
    const B2 = B1 + 6
    tl.addLabel('beat-2', B2)
    const enders = at('.ender')
    ENDERS.forEach((_, i) => {
      tl.to(enders[i], { opacity: 1, duration: 0.4 }, B2 + 0.2 + i * 0.35)
      tl.fromTo(at('.ender-in')[i], { y: 8 }, { y: 0, duration: 0.6, ease: 'back.out(2)' }, B2 + 0.2 + i * 0.35)
      cam.flare({ x: l.enders[i].x + l.ew / 2, y: l.enders[i].y + 17 }, i === 3 ? warm : ok, B2 + 0.4 + i * 0.35, 12, 70)
    })
    cam.shot(l.strip, B2 + 1.6, 1.8)
    tl.to(at('.strip-head, .state, .rowlabel'), { opacity: 1, duration: 0.6, stagger: 0.1 }, B2 + 2)
    const counter = one('.count')
    const cells = at('.cell')
    const kept = at('.kept')
    const round = (i: number, when: number) => {
      const r = RUN[i]
      tl.to(cells[i], { opacity: 1, duration: 0.3 }, when)
      tl.fromTo(at('.cell-in')[i], { y: -6 }, { y: 0, duration: 0.5, ease: 'back.out(2)' }, when)
      if (r.said === 'failed') {
        cam.flare({ x: cellMid(r.n), y: l.cellsY + 30 }, danger, when + 0.3, 24, 90)
        tl.to(kept[i], { opacity: 1, duration: 0.3 }, when + 0.4)
        return
      }
      // The round done, the session is written into the state, as it stands now.
      cam.beam({ x: cellMid(r.n), y: l.cellsY }, { x: l.state.x + l.state.w - 8, y: l.state.y + 12 }, lane1, when + 0.4, { duration: 0.6, bend: -0.2 })
      count(tl, counter, r.n - 1, r.kept, when + 0.9, { duration: 0.3, format: KEPT })
      tl.fromTo(at('.state-glow'), { opacity: 0.9 }, { opacity: 0, duration: 0.8 }, when + 0.9)
      tl.to(kept[i], { opacity: 1, duration: 0.3 }, when + 0.9)
    }
    round(0, B2 + 2.6)

    // 3 · round by round, the session is kept in ctx.state.
    const B3 = B2 + 4.2
    tl.addLabel('beat-3', B3)
    round(1, B3)
    const notes = at('.note')
    tl.to(notes[0], { opacity: 1, duration: 0.5 }, B3 + 1)
    round(2, B3 + 2)

    // 4 · stopped, and picked up: the session read back carries round 3's conversation on.
    const B4 = B3 + 3.8
    tl.addLabel('beat-4', B4)
    tl.to(notes[0], { opacity: 0, duration: 0.4 }, B4)
    tl.to(at('.stop'), { opacity: 1, duration: 0.4 }, B4 + 0.2)
    cam.flare({ x: stopX.value + l.sw / 2, y: l.cellsY + 12 }, danger, B4 + 0.3, 22, 90)
    tl.fromTo(at('.state-glow'), { opacity: 1 }, { opacity: 0.2, duration: 1.2 }, B4 + 0.5)
    tl.to(notes[1], { opacity: 1, duration: 0.5 }, B4 + 0.8)
    tl.to(at('.carry'), { drawSVG: '100%', duration: 0.7, ease: 'cine' }, B4 + 1.4)
    round(3, B4 + 2)

    // 5 · round 5's turn fails: HarnessError, uncaught, and the run ends with it.
    const B5 = B4 + 3.4
    tl.addLabel('beat-5', B5)
    round(4, B5)
    tl.to(notes[1], { opacity: 0, duration: 0.4 }, B5 + 1.2)
    tl.to(notes[2], { opacity: 1, duration: 0.5 }, B5 + 1.5)
    cam.beam({ x: cellMid(5), y: l.cellsY }, { x: l.enders[2].x + l.ew / 2, y: l.enders[2].y + 34 }, ok, B5 + 2.3, { duration: 0.8, bend: 0.25, burst: 22 })
    tl.to(at('.ender-hot'), { opacity: 1, duration: 0.4 }, B5 + 3)
    cam.shot(l.whole, B5 + 3.2, 1.6)

    tl.addLabel('rest', B5 + 5)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, B5 + 7)

    tl.fromTo(at('.hum'), { strokeDashoffset: 0 }, { strokeDashoffset: -120, duration: tl.duration(), ease: 'none' }, 0)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 16"
    label="How a loop works. Side by side, ralph_loop puts spawn inside the loop and stateful_ralph puts it before. Over four rounds, ralph_loop opens a new session every round, whose history holds only that round's turn, so each round knows the task and the repository; stateful_ralph keeps one session whose history grows by a turn every round. Four things end a loop: a check of yours that returns, a round limit, a failed turn the loop does not catch, which raises HarnessError, and the run's budget, which raises BudgetExceeded. Then stateful_ralph round by round: after each round it writes the session into ctx.state, keeping the conversation as it stands then; after round 3 the run is stopped, and resumed with --resume, and because the flow is resumable the session read back from ctx.state carries round 3's conversation on at round 4; round 5's turn fails with HarnessError, which the flow does not catch, so the run ends with it."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="world">
        <!-- the two loops -->
        <g v-for="(p, i) in PANELS" :key="p.flow" class="panel">
          <rect class="panel-box" :x="L.panels[i].x" :y="L.panels[i].y" :width="L.pw" :height="L.ph" rx="10" />
          <text class="panel-title" :x="L.panels[i].x + 12" :y="L.panels[i].y + 20">{{ p.title }}</text>
          <text class="panel-flow" :x="L.panels[i].x + L.pw - 12" :y="base(i) + 20" text-anchor="end">{{ p.flow }}</text>
          <rect class="spawn-bar" :x="L.panels[i].x + 8" :y="codeY(i, p.spawn) - 12" :width="L.pw - 16" height="16" rx="4" />
          <g v-for="(line, j) in p.code" :key="j" class="code-line">
            <text :x="L.panels[i].x + 14" :y="codeY(i, j)"><tspan v-for="(tok, m) in line" :key="m" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
          <line class="axis hum" :x1="L.panels[i].x + 12" :x2="colX(i, ROUNDS - 1) + 36" :y1="base(i) + 6" :y2="base(i) + 6" />
          <g class="knows">
            <text class="knows-a" :x="L.panels[i].x + L.pw - 12" :y="base(i) - 26" text-anchor="end">{{ p.knows[0] }}</text>
            <text class="knows-b" :x="L.panels[i].x + L.pw - 12" :y="base(i) - 10" text-anchor="end">{{ p.knows[1] }}</text>
          </g>
        </g>
        <!-- stateful: one session, a thread from round to round -->
        <line v-for="k in ROUNDS - 1" :key="`t${k}`" class="thread" :x1="colX(1, k - 1) + 15" :x2="colX(1, k) + 15" :y1="base(1) + 6" :y2="base(1) + 6" />
        <!-- a spark is a new session: one a round for ralph, one at the start for stateful -->
        <circle v-for="k in ROUNDS" :key="`s${k}`" class="spark" :cx="colX(0, k - 1) + 15" :cy="base(0) + 6" r="4" />
        <circle class="spark" :cx="colX(1, 0) + 15" :cy="base(1) + 6" r="4" />
        <!-- history, a block a turn -->
        <rect v-for="k in ROUNDS" :key="`a${k}`" class="block" :x="colX(0, k - 1) + 3" :y="base(0) - BLOCK" width="24" :height="BLOCK" rx="2" />
        <template v-for="k in ROUNDS" :key="`b${k}`">
          <rect v-for="j in k" :key="`b${k}-${j}`" class="block" :x="colX(1, k - 1) + 3" :y="base(1) - BLOCK - (j - 1) * STEP" width="24" :height="BLOCK" rx="2" />
        </template>
        <template v-for="i in 2" :key="`rl${i}`">
          <text v-for="k in ROUNDS" :key="`rl${i}-${k}`" class="rlabel" :x="colX(i - 1, k - 1) + 15" :y="base(i - 1) + 20" text-anchor="middle">r{{ k }}</text>
        </template>

        <!-- what ends a loop -->
        <g v-for="(e, i) in ENDERS" :key="e.code" class="ender">
          <g class="ender-in">
            <rect class="ender-box" :class="{ budget: i === 3 }" :x="L.enders[i].x" :y="L.enders[i].y" :width="L.ew" height="34" rx="7" />
            <rect v-if="i === 2" class="ender-hot" :x="L.enders[i].x" :y="L.enders[i].y" :width="L.ew" height="34" rx="7" />
            <text class="ender-code" :class="{ budget: i === 3 }" :x="L.enders[i].x + 9" :y="L.enders[i].y + 14">{{ e.code }}</text>
            <text class="ender-why" :x="L.enders[i].x + 9" :y="L.enders[i].y + 28">{{ e.why }}</text>
          </g>
        </g>

        <!-- stateful_ralph, round by round -->
        <text class="strip-head" :x="L.state.x" :y="L.stripY">stateful_ralph, round by round</text>
        <text class="strip-head strip-flag" :x="L.w - 14" :y="L.stripY" text-anchor="end">@flow(…, resumable=True)</text>
        <g class="state">
          <rect class="state-box" :x="L.state.x" :y="L.state.y" :width="L.state.w" :height="L.state.h" rx="8" />
          <rect class="state-glow" :x="L.state.x" :y="L.state.y" :width="L.state.w" :height="L.state.h" rx="8" opacity="0" />
          <template v-if="!narrow">
            <text class="state-name" :x="L.state.x + 10" :y="L.state.y + 17">ctx.state</text>
            <text class="state-key" :x="L.state.x + 10" :y="L.state.y + 34">["session"]</text>
            <text class="count" :x="L.state.x + 10" :y="L.state.y + 64">—</text>
          </template>
          <template v-else>
            <text class="state-name" :x="L.state.x + 10" :y="L.state.y + 19">ctx.state["session"]</text>
            <text class="count count-n" :x="L.state.x + L.state.w - 12" :y="L.state.y + 22" text-anchor="end">—</text>
          </template>
        </g>
        <text class="rowlabel" :x="L.rowsX" :y="L.cellsY + 16">round</text>
        <text class="rowlabel" :x="L.rowsX" :y="L.cellsY + 33">said</text>
        <text class="rowlabel" :x="L.rowsX" :y="L.cellsY + CELL_H + 16">kept</text>
        <g v-for="(r, i) in RUN" :key="r.n" class="cell">
          <g class="cell-in">
            <rect class="cell-box" :class="r.said" :x="cellX(r.n)" :y="L.cellsY" :width="L.cw" :height="CELL_H" rx="6" />
            <text class="cell-n" :x="cellMid(r.n)" :y="L.cellsY + 16" text-anchor="middle">{{ r.n }}</text>
            <text class="cell-said" :class="r.said" :x="cellMid(r.n)" :y="L.cellsY + 33" text-anchor="middle">{{ GLYPH[r.said] }}</text>
          </g>
        </g>
        <text v-for="r in RUN" :key="`kp${r.n}`" class="kept" :class="{ hot: r.said === 'failed' }" :x="cellMid(r.n)" :y="L.cellsY + CELL_H + 16" text-anchor="middle">{{ KEPT(r.kept) }}</text>
        <path class="carry" :d="`M${cellMid(3)} ${L.cellsY - 2} C${cellMid(3) + 12} ${L.cellsY - 18} ${cellMid(4) - 12} ${L.cellsY - 18} ${cellMid(4)} ${L.cellsY - 2}`" />
        <g class="stop">
          <line class="stop-line" :x1="stopX + L.sw / 2" :x2="stopX + L.sw / 2" :y1="L.cellsY - 4" :y2="L.cellsY + CELL_H + 4" />
          <text class="stop-word" :x="stopX + L.sw / 2" :y="L.cellsY + 16" text-anchor="middle">stop</text>
          <text class="resume-word" :x="stopX + L.sw / 2" :y="L.cellsY + 33" text-anchor="middle">{{ narrow ? '▶' : 'resume' }}</text>
        </g>
        <g v-for="(n, i) in NOTES" :key="i" class="note" :class="{ last: i === 2 }">
          <text v-if="!narrow" :x="L.state.x" :y="L.noteY">{{ n[0] }} {{ n[1] }}</text>
          <template v-else>
            <text :x="L.state.x" :y="L.noteY">{{ n[0] }}</text>
            <text :x="L.state.x" :y="L.noteY + 16">{{ n[1] }}</text>
          </template>
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

.panel-box,
.state-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.panel-title {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.panel-flow {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.spawn-bar {
  fill: var(--hmz-lane-1);
  opacity: 0.55;
  fill-opacity: 0.22;
}

.code-line text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  white-space: pre;
  fill: var(--hmz-stage-ink);
}

.code-line .kw {
  fill: var(--hmz-lane-3);
  font-weight: 600;
}

.code-line .fn {
  fill: var(--hmz-lane-1);
}

.axis {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
  stroke-dasharray: 2 4;
}

.thread {
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
}

.spark {
  fill: var(--hmz-lane-1);
}

.block {
  fill: var(--hmz-lane-1);
}

.rlabel {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.knows-a {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.knows-b {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-lane-1);
}

.ender-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-opacity: 0.6;
  stroke-width: 1.2;
}

.ender-box.budget {
  stroke: var(--hmz-warm);
}

.ender-hot {
  fill: var(--hmz-accent);
  fill-opacity: 0.14;
  stroke: var(--hmz-accent);
  stroke-width: 2.2;
}

.ender-code {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.ender-code.budget {
  fill: var(--hmz-warm);
}

.ender-why {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.strip-head {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.strip-flag {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-accent);
}

.state-glow {
  fill: var(--hmz-lane-1);
  fill-opacity: 0.16;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.8;
}

.state-name {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.state-key {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.count {
  font-family: var(--vp-font-family-mono);
  font-size: 26px;
  font-weight: 700;
  fill: var(--hmz-lane-1);
}

.count-n {
  font-size: 18px;
}

.rowlabel {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.cell-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-opacity: 0.6;
  stroke-width: 1.2;
}

.cell-box.failed {
  stroke: var(--vp-c-danger-1);
  stroke-opacity: 1;
}

.cell-n {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.cell-said {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.cell-said.failed {
  fill: var(--vp-c-danger-1);
}

.kept {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-lane-1);
}

.kept.hot {
  fill: var(--vp-c-danger-1);
  font-weight: 800;
}

.carry {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.5;
  stroke-linecap: round;
}

.stop-line {
  stroke: var(--vp-c-danger-1);
  stroke-width: 2;
  stroke-dasharray: 4 3;
}

.stop-word {
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-danger-1);
  paint-order: stroke;
  stroke: var(--hmz-stage-card);
  stroke-width: 4px;
}

.resume-word {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
  paint-order: stroke;
  stroke: var(--hmz-stage-card);
  stroke-width: 4px;
}

.note text {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.note.last text {
  font-family: var(--vp-font-family-mono);
  font-style: normal;
  font-weight: 600;
  fill: var(--hmz-accent);
}
</style>
