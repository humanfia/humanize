<script setup lang="ts">
// A flow that calls a flow, played out on `steps` from A flow that calls a flow. `load(ref)`
// finds the flow (`load` in src/hmz/flows/defining.py: `:<subflow>` in the same module, a name
// beside the flow asking -- its own directory, then wherever `-f` looks, nearest first -- or a
// pip-style git ref) and hands back a `Flow`. Awaiting it (`Flow.__call__`) first checks what
// was handed against the callee's declaration -- each failure a `RequirementError` subclass from
// src/hmz/flows/errors.py, raised before anything has run or been spent -- fills a `LocalEnv` or
// `Outworlder` left out with the run's own, and runs the callee as a branch: its own ctx, its
// own line in the running tree, a budget that is the tighter of its own and what is left of
// the caller's (`FlowContext.budget`), its spend counted against every flow above it. It
// answers with what it returned, or raises what it raised, as it raised it. The sums are
// invented: a run started with `-p budget.cost=1` that has spent 20 cents.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig, type Shot } from '../../motion/camera'
import { count, createFx, type Fx } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'load(ref) finds the flow, nearest first',
  'Awaited, it checks what it was handed',
  'What you leave out, the run fills',
  'A branch: its own ctx, the tighter budget',
  'Its spend counts against every flow above',
  'It returns its value, or raises what it raised',
]

type Tok = [cls: '' | 'kw' | 'fn' | 'str', text: string]
const CODE: Tok[][] = [
  [['', 'step = '], ['fn', 'load'], ['', '('], ['str', '":one-step"'], ['', ')']],
  [['', 'ok = '], ['kw', 'await '], ['fn', 'step'], ['', '(part,']],
  [['', '  agents={'], ['str', '"builder"'], ['', ': b},']],
  [['', '  envs={},']],
  [['', '  params=step.'], ['fn', 'expected_params'], ['', '(),']],
  [['', '  budget='], ['fn', 'Budget'], ['', '(cost=0.5))']],
]

/** Where `load` looks, in order. */
const LOOKS: { ref?: string; words: string }[] = [
  { ref: ':one-step', words: ' in the same module' },
  { words: 'beside it, in its own directory' },
  { words: 'wherever -f looks, nearest first' },
  { ref: 'git+<url>@<rev>#dir:flow', words: '' },
]

/** What is checked before a line of the callee runs, and what each failure raises. */
const CHECKS = [
  ['the mixins it declares', 'CapabilityMissing'],
  ['its permission, at least', 'PermissionTooNarrow'],
  ['the CLI a role names', 'HarnessMismatch'],
  ['the CPUs, memory, GPUs', 'ResourceUnmet'],
  ['every role it requires', 'MissingRole'],
] as const

/** Dollars, and how wide a dollar is drawn. */
const RUN = 1
const SPENT = 0.2
const OWN = 0.5
const STEP = 0.31
const PX = 140

interface Box {
  x: number
  y: number
  w: number
}

interface Layout {
  w: number
  h: number
  code: Box
  line: number
  ladder: Box & { row: number; rowH: number }
  gate: Box & { row: number; rowH: number; two: boolean; foot: number }
  fill: { y: number; head: number; slots: Box[] }
  tree: { x: number; x1: number; head: number; rows: number[]; step: number; subs: boolean }
  budget: { x: number; x1: number; head: number; rows: number[] }
  shots: Record<'open' | 'gate' | 'branch' | 'whole', Shot>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  code: { x: 12, y: 24, w: 238 },
  line: 18,
  ladder: { x: 12, y: 210, w: 238, row: 30, rowH: 26 },
  gate: { x: 264, y: 46, w: 206, row: 35, rowH: 32, two: true, foot: 238 },
  fill: { y: 270, head: 262, slots: [{ x: 264, y: 270, w: 206 }, { x: 264, y: 298, w: 206 }] },
  tree: { x: 484, x1: 628, head: 52, rows: [70, 114, 158], step: 14, subs: true },
  budget: { x: 484, x1: 628, head: 204, rows: [222, 250, 278] },
  shots: {
    open: { x: 150, y: 170, s: 1.32 },
    gate: { x: 300, y: 180, s: 1.16 },
    branch: { x: 452, y: 182, s: 1.16 },
    whole: { x: 320, y: 180, s: 1 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 640,
  code: { x: 12, y: 8, w: 336 },
  line: 17,
  ladder: { x: 12, y: 188, w: 336, row: 27, rowH: 23 },
  gate: { x: 12, y: 322, w: 336, row: 27, rowH: 24, two: false, foot: 470 },
  fill: { y: 496, head: 490, slots: [{ x: 12, y: 498, w: 164 }, { x: 184, y: 498, w: 164 }] },
  tree: { x: 14, x1: 172, head: 546, rows: [564, 590, 616], step: 12, subs: false },
  budget: { x: 192, x1: 348, head: 546, rows: [562, 589, 616] },
  shots: {
    open: { x: 180, y: 300, s: 1.04 },
    gate: { x: 180, y: 320, s: 1 },
    branch: { x: 180, y: 320, s: 1 },
    whole: { x: 180, y: 320, s: 1 },
  },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const lineY = (i: number) => L.value.code.y + 38 + i * L.value.line
const codeEnd = (i: number) => ({ x: L.value.code.x + L.value.code.w - 8, y: lineY(i) - 4 })
const rungY = (i: number) => L.value.ladder.y + 8 + i * L.value.ladder.row
const rowY = (i: number) => L.value.gate.y + i * L.value.gate.row
const nodeX = (i: number) => L.value.tree.x + 8 + i * L.value.tree.step
const money = (n: number) => `$${n.toFixed(2)}`
const codeH = computed(() => 38 + CODE.length * L.value.line + 12)

/** The connectors of the running tree: root to the call, the call to a call of its own. */
const link = (i: number) => {
  const t = L.value.tree
  const x = nodeX(i)
  return `M${x} ${t.rows[i] + 6} V${t.rows[i + 1]} H${nodeX(i + 1) - 6}`
}

const scene = useScene({
  still: 'rest',
  repeatDelay: 1.2,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const gsap = motion()
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const at = (sel: string) => q(sel)
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), fx: () => fx, start: l.shots.open })

    const lane1 = () => palette.lane[0]
    const lane3 = () => palette.lane[2]
    const ok = () => palette.accent
    const warm = () => palette.warm
    const danger = () => palette.danger
    const gateX = l.gate.x - 8

    const caret = one('.caret')
    const pc = (i: number, when: number) => {
      tl.to(caret, { attr: { y: lineY(i) - 13 }, duration: 0.45, ease: 'cine' }, when)
      tl.fromTo(at('.code-line')[i], { opacity: 0.55 }, { opacity: 1, duration: 0.3 }, when + 0.1)
    }
    const pop = (el: Element, when: number) =>
      tl.fromTo(el, { opacity: 0, scale: 0.4, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.45, ease: 'back.out(2.6)' }, when)

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.code-line, .ladder-row, .gate-row, .slot, .node, .budget-row'), { opacity: 0 }, 0)
    tl.set(at('.rung-on, .row-on, .tick, .found, .gate-head, .gate-foot, .fill-head, .own, .tree-head, .budget-head, .caption, .out-ok, .out-err, .deep, .err-dot'), { opacity: 0 }, 0)
    tl.set(at('.link, .gate-bar'), { drawSVG: '0%' }, 0)
    tl.set(caret, { opacity: 0, attr: { y: lineY(0) - 13 } }, 0)

    // 0 · the call in the code, and load finding what it names: the same module, first.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.card'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.7 }, 0.1)
    tl.fromTo(at('.code-line'), { opacity: 0, x: -10 }, { opacity: 0.55, x: 0, duration: 0.5, stagger: 0.1 }, 0.3)
    tl.to(caret, { opacity: 1, duration: 0.3 }, 1.1)
    pc(0, 1.1)
    tl.fromTo(one('.ladder-head'), { opacity: 0 }, { opacity: 1, duration: 0.5 }, 1.3)
    tl.fromTo(at('.ladder-row'), { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.5, stagger: 0.12 }, 1.4)
    cam.beam(codeEnd(0), { x: l.ladder.x + 14, y: rungY(0) + l.ladder.rowH / 2 }, lane1, 2.1, { duration: 0.8, bend: -0.25 })
    // A light down the rungs: the ref is matched at the first.
    tl.fromTo(one('.scan'), { opacity: 0, y: 0 }, { opacity: 0.9, y: 0, duration: 0.2 }, 2.8)
    tl.to(one('.scan'), { y: l.ladder.row * 3, duration: 0.9, ease: 'power1.inOut' }, 3)
    tl.to(one('.scan'), { y: 0, duration: 0.5, ease: 'cine' }, 3.9)
    tl.to(one('.scan'), { opacity: 0, duration: 0.3 }, 4.4)
    tl.to(one('.rung-on'), { opacity: 1, duration: 0.4 }, 4.3)
    cam.flare({ x: l.ladder.x + 14, y: rungY(0) + l.ladder.rowH / 2 }, ok, 4.3, 18, 80)
    cam.beam({ x: l.ladder.x + 120, y: rungY(0) + 4 }, codeEnd(0), ok, 4.5, { duration: 0.8, bend: 0.25, burst: 14 })
    pop(one('.found'), 5.2)

    // 1 · awaiting it: what is handed goes through the gate, checked against the callee's
    //     declaration before a line of it runs.
    const T1 = 6
    tl.addLabel('beat-1', T1)
    cam.shot(l.shots.gate, T1, 1.6)
    pc(1, T1)
    tl.to(one('.gate-bar'), { drawSVG: '100%', duration: 0.9, ease: 'cine' }, T1 + 0.3)
    tl.to(one('.gate-head'), { opacity: 1, duration: 0.5 }, T1 + 0.5)
    tl.fromTo(at('.gate-row'), { opacity: 0, x: 10 }, { opacity: 1, x: 0, duration: 0.5, stagger: 0.1 }, T1 + 0.6)
    for (let i = 2; i <= 5; i += 1) {
      pc(i, T1 + 1.2 + (i - 2) * 0.35)
      cam.beam(codeEnd(i), { x: gateX, y: rowY(i - 2) + l.gate.rowH / 2 + 16 }, i === 3 ? warm : lane1, T1 + 1.3 + (i - 2) * 0.35, { duration: 0.7, bend: 0.12 })
    }
    CHECKS.forEach((_, i) => {
      const w = T1 + 2.9 + i * 0.42
      tl.fromTo(at('.row-on')[i], { opacity: 0 }, { opacity: 1, duration: 0.25 }, w)
      pop(at('.tick')[i], w + 0.1)
      cam.flare({ x: l.gate.x + l.gate.w - 13, y: rowY(i) + l.gate.rowH / 2 }, ok, w + 0.15, 10, 60)
    })
    tl.to(one('.gate-foot'), { opacity: 1, duration: 0.5 }, T1 + 5.1)

    // 2 · envs={} leaves the LocalEnv out, and the run fills it with its own; an Outworlder too.
    const T2 = T1 + 6
    tl.addLabel('beat-2', T2)
    pc(3, T2)
    tl.to(one('.fill-head'), { opacity: 1, duration: 0.4 }, T2 + 0.2)
    tl.fromTo(at('.slot'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.15 }, T2 + 0.3)
    tl.to(at('.tree-head, .node-root'), { opacity: 1, duration: 0.5 }, T2 + 0.6)
    l.fill.slots.forEach((s, i) => {
      const w = T2 + 1.3 + i * 0.7
      cam.beam({ x: nodeX(0), y: l.tree.rows[0] }, { x: s.x + s.w - 30, y: s.y + 12 }, warm, w, { duration: 0.9, bend: 0.22, burst: 12 })
      tl.to(at('.slot-out')[i], { opacity: 0, duration: 0.3 }, w + 0.8)
      tl.fromTo(at('.slot-in')[i], { opacity: 0 }, { opacity: 1, duration: 0.4 }, w + 0.85)
      tl.fromTo(at('.slot-fill')[i], { opacity: 0 }, { opacity: 1, duration: 0.5 }, w + 0.8)
    })

    // 3 · it runs as a branch of the run, under the tighter of its own budget and what is left
    //     of yours.
    const T3 = T2 + 3.6
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.branch, T3, 1.6)
    pc(5, T3)
    cam.beam({ x: gateX + l.gate.w, y: rowY(2) }, { x: nodeX(1), y: l.tree.rows[1] }, lane3, T3 + 0.4, { duration: 0.9, bend: -0.2 })
    tl.to(at('.link')[0], { drawSVG: '100%', duration: 0.6, ease: 'cine' }, T3 + 0.6)
    tl.fromTo(one('.node-call'), { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.5 }, T3 + 1.1)
    cam.flare({ x: nodeX(1), y: l.tree.rows[1] }, lane3, T3 + 1.2, 20, 80)
    tl.to(one('.budget-head'), { opacity: 1, duration: 0.4 }, T3 + 1.5)
    tl.fromTo(at('.budget-row')[0], { opacity: 0 }, { opacity: 1, duration: 0.4 }, T3 + 1.6)
    tl.fromTo(at('.bar-fill')[0], { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 0.8, ease: 'cine' }, T3 + 1.7)
    tl.fromTo(at('.budget-row')[1], { opacity: 0 }, { opacity: 1, duration: 0.4 }, T3 + 2.1)
    tl.fromTo(at('.bar-fill')[1], { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 0.8, ease: 'cine' }, T3 + 2.2)
    // The tighter of the two drops into the third bar.
    tl.fromTo(one('.min-guide'), { opacity: 0 }, { opacity: 0.8, duration: 0.4 }, T3 + 3)
    tl.fromTo(at('.budget-row')[2], { opacity: 0 }, { opacity: 1, duration: 0.4 }, T3 + 3.2)
    tl.fromTo(at('.bar-fill')[2], { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 0.7, ease: 'cine' }, T3 + 3.3)
    cam.flare({ x: l.budget.x + OWN * PX, y: l.budget.rows[2] + 9 }, ok, T3 + 4, 16, 70)

    // 4 · its turns spend; every cent counts against the flows above it as it is spent.
    const T4 = T3 + 4.8
    tl.addLabel('beat-4', T4)
    tl.fromTo(one('.spend'), { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 2.4, ease: 'power1.inOut' }, T4 + 0.3)
    count(tl, one('.count-call'), 0, STEP, T4 + 0.3, { duration: 2.4, format: money, ease: 'power1.inOut' })
    count(tl, one('.count-root'), SPENT, SPENT + STEP, T4 + 0.3, { duration: 2.4, format: money, ease: 'power1.inOut' })
    count(tl, one('.count-left'), RUN - SPENT, RUN - SPENT - STEP, T4 + 0.3, { duration: 2.4, format: money, ease: 'power1.inOut' })
    tl.to(at('.bar-fill')[0], { scaleX: (RUN - SPENT - STEP) / (RUN - SPENT), duration: 2.4, ease: 'power1.inOut' }, T4 + 0.3)
    for (let k = 0; k < 4; k += 1) {
      cam.beam({ x: nodeX(1), y: l.tree.rows[1] }, { x: nodeX(0), y: l.tree.rows[0] }, warm, T4 + 0.4 + k * 0.55, { duration: 0.5, bend: 0.5, size: 2 })
    }
    cam.beam({ x: nodeX(0), y: l.tree.rows[0] }, { x: l.budget.x + 70, y: l.budget.rows[0] + 9 }, warm, T4 + 2.6, { duration: 0.7, bend: -0.2, burst: 12 })
    tl.to(at('.caption'), { opacity: 1, duration: 0.5, stagger: 0.15 }, T4 + 2.9)

    // 5 · it answers with what it returned; or what it raised comes up as it was raised.
    const T5 = T4 + 4
    tl.addLabel('beat-5', T5)
    cam.shot(l.shots.whole, T5, 1.8)
    pc(1, T5)
    cam.beam({ x: nodeX(1), y: l.tree.rows[1] }, codeEnd(1), ok, T5 + 0.5, { duration: 1.1, bend: 0.18, burst: 18 })
    tl.to(one('.out-ok'), { opacity: 1, duration: 0.5 }, T5 + 1.5)
    tl.to(at('.link')[1], { drawSVG: '100%', duration: 0.5, ease: 'cine' }, T5 + 2.2)
    tl.to(one('.deep'), { opacity: 1, duration: 0.5 }, T5 + 2.5)
    cam.flare({ x: nodeX(2), y: l.tree.rows[2] }, danger, T5 + 2.7, 18, 70)
    const dot = one('.err-dot')
    const dy1 = l.tree.rows[1] - l.tree.rows[2]
    const dy0 = l.tree.rows[0] - l.tree.rows[2]
    const dx1 = nodeX(1) - nodeX(2)
    const dx0 = nodeX(0) - nodeX(2)
    tl.fromTo(dot, { opacity: 0, x: 0, y: 0 }, { opacity: 1, duration: 0.2 }, T5 + 2.8)
    tl.to(dot, { x: dx1, y: dy1, duration: 0.6, ease: 'cine' }, T5 + 3)
    tl.to(dot, { x: dx0, y: dy0, duration: 0.6, ease: 'cine' }, T5 + 3.7)
    tl.to(dot, { opacity: 0, duration: 0.2 }, T5 + 4.3)
    cam.flare({ x: nodeX(1), y: l.tree.rows[1] }, danger, T5 + 3.6, 10, 50)
    cam.flare({ x: nodeX(0), y: l.tree.rows[0] }, danger, T5 + 4.3, 12, 60)
    cam.beam({ x: nodeX(0), y: l.tree.rows[0] }, codeEnd(6), danger, T5 + 4.3, { duration: 1, bend: -0.2, burst: 16 })
    tl.to(one('.out-err'), { opacity: 1, duration: 0.5 }, T5 + 5.2)
    tl.to(caret, { opacity: 0.35, duration: 0.6 }, T5 + 5.4)

    tl.addLabel('rest', T5 + 6)
    cam.shot({ ...l.shots.whole, s: 1.02 }, T5 + 5.6, 2.8, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T5 + 8.6)

    tl.fromTo(at('.hum'), { strokeDashoffset: 0 }, { strokeDashoffset: -90, duration: tl.duration(), ease: 'none' }, 0)
    gsap.set(caret, { opacity: 0 })
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 16"
    label="A flow that calls a flow. load(':one-step') finds the flow it names, looking in the same module, then beside the flow in its own directory, then wherever -f looks, nearest first, or at a git ref, and hands back a flow ready to call. Awaiting it checks everything handed against the callee's declaration before a line of it runs: its mixins, else CapabilityMissing; its permission, else PermissionTooNarrow; its CLI, else HarnessMismatch; its resources, else ResourceUnmet; every required role, else MissingRole; each a RequirementError, with nothing spent. A LocalEnv or Outworlder left out is filled with the run's own. It runs as a branch of the run, with its own ctx and its own line in the running tree, under the tighter of its own budget, 50 cents, and the 80 cents left of the caller's. What it spends, 31 cents, counts against the flow above it as it is spent. It answers with what it returned, True, or raises what it raised: a CostExceeded from further down arrives as a CostExceeded."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="world">
        <!-- the caller's code -->
        <g class="card">
          <rect class="card-box" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="codeH" rx="10" />
          <text class="card-head" :x="L.code.x + 12" :y="L.code.y + 18">@flow · async def steps(task, …)</text>
          <rect class="caret" :x="L.code.x + 4" :y="lineY(0) - 13" width="3" height="16" rx="1.5" />
          <g v-for="(line, i) in CODE" :key="i" class="code-line">
            <text :x="L.code.x + 14" :y="lineY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
          <g class="found">
            <rect :x="L.code.x + L.code.w - 52" :y="lineY(0) - 13" width="44" height="17" rx="8.5" />
            <text :x="L.code.x + L.code.w - 30" :y="lineY(0) - 1" text-anchor="middle">Flow</text>
          </g>
          <text class="out" :x="L.code.x + 14" :y="lineY(6)"><tspan class="out-ok">→ True</tspan><tspan class="out-err"> | raises CostExceeded</tspan></text>
        </g>

        <!-- where load looks -->
        <text class="head ladder-head" :x="L.ladder.x + 2" :y="L.ladder.y - 2">where load(ref) looks, in order</text>
        <g v-for="(r, i) in LOOKS" :key="`r${i}`" class="ladder-row">
          <rect class="rung" :x="L.ladder.x" :y="rungY(i)" :width="L.ladder.w" :height="L.ladder.rowH" rx="6" />
          <text class="rung-n" :x="L.ladder.x + 14" :y="rungY(i) + L.ladder.rowH / 2 + 4" text-anchor="middle">{{ i + 1 }}</text>
          <text class="rung-words" :x="L.ladder.x + 28" :y="rungY(i) + L.ladder.rowH / 2 + 4"><tspan v-if="r.ref" class="mono">{{ r.ref }}</tspan>{{ r.words }}</text>
        </g>
        <rect class="rung-on" :x="L.ladder.x" :y="rungY(0)" :width="L.ladder.w" :height="L.ladder.rowH" rx="6" />
        <g class="scan"><rect class="scan-bar" :x="L.ladder.x + 2" :y="rungY(0) + 2" width="4" :height="L.ladder.rowH - 4" rx="2" /></g>

        <!-- the gate: the callee's declaration -->
        <text class="head gate-head" :x="L.gate.x" :y="L.gate.y - 10">checked before it runs</text>
        <line class="gate-bar" :x1="L.gate.x - 8" :x2="L.gate.x - 8" :y1="L.gate.y" :y2="rowY(4) + L.gate.rowH" />
        <g v-for="(c, i) in CHECKS" :key="`c${i}`" class="gate-row">
          <rect class="row" :x="L.gate.x" :y="rowY(i)" :width="L.gate.w" :height="L.gate.rowH" rx="6" />
          <template v-if="L.gate.two">
            <text class="row-words" :x="L.gate.x + 10" :y="rowY(i) + 13">{{ c[0] }}</text>
            <text class="row-err" :x="L.gate.x + 10" :y="rowY(i) + 27">else {{ c[1] }}</text>
          </template>
          <template v-else>
            <text class="row-words" :x="L.gate.x + 10" :y="rowY(i) + 16">{{ c[0] }}</text>
            <text class="row-err" :x="L.gate.x + L.gate.w - 28" :y="rowY(i) + 16" text-anchor="end">{{ c[1] }}</text>
          </template>
        </g>
        <rect v-for="(c, i) in CHECKS" :key="`o${i}`" class="row-on" :x="L.gate.x" :y="rowY(i)" :width="L.gate.w" :height="L.gate.rowH" rx="6" />
        <g v-for="(c, i) in CHECKS" :key="`t${i}`" class="tick">
          <circle :cx="L.gate.x + L.gate.w - 13" :cy="rowY(i) + L.gate.rowH / 2" r="7" />
          <path :d="`M${L.gate.x + L.gate.w - 16.5} ${rowY(i) + L.gate.rowH / 2} l2.5 2.5 l4.5 -5`" />
        </g>
        <text class="gate-foot" :x="L.gate.x" :y="L.gate.foot"><tspan class="mono">RequirementError</tspan> · nothing spent</text>

        <!-- what the run fills -->
        <text class="head fill-head" :x="L.gate.x" :y="L.fill.head">left out, filled by the run</text>
        <g v-for="(s, i) in L.fill.slots" :key="`s${i}`" class="slot">
          <rect class="slot-box" :x="s.x" :y="s.y" :width="s.w" height="24" rx="6" />
          <rect class="slot-fill" :x="s.x" :y="s.y" :width="s.w" height="24" rx="6" />
          <text class="slot-name" :x="s.x + 10" :y="s.y + 16">{{ i === 0 ? 'LocalEnv' : 'Outworlder' }}</text>
          <text class="slot-out" :x="s.x + s.w - 10" :y="s.y + 16" text-anchor="end">left out</text>
          <text class="slot-in" :x="s.x + s.w - 10" :y="s.y + 16" text-anchor="end">the run’s own</text>
        </g>

        <!-- the running tree -->
        <text class="head tree-head" :x="L.tree.x" :y="L.tree.head">running tree</text>
        <text class="head tree-head" :x="L.tree.x1" :y="L.tree.head" text-anchor="end">spent</text>
        <path class="link hum" :d="link(0)" />
        <path class="link link-deep hum" :d="link(1)" />
        <g class="node node-root">
          <circle class="dot dot-root" :cx="nodeX(0)" :cy="L.tree.rows[0]" r="6" />
          <text class="node-name" :x="nodeX(0) + 12" :y="L.tree.rows[0] + 4">steps</text>
          <text v-if="L.tree.subs" class="node-sub" :x="nodeX(0) + 12" :y="L.tree.rows[0] + 18">the run</text>
          <text class="count count-root" :x="L.tree.x1" :y="L.tree.rows[0] + 4" text-anchor="end">{{ money(SPENT) }}</text>
        </g>
        <g class="node node-call">
          <circle class="dot dot-call" :cx="nodeX(1)" :cy="L.tree.rows[1]" r="6" />
          <text class="node-name" :x="nodeX(1) + 12" :y="L.tree.rows[1] + 4">one-step</text>
          <text v-if="L.tree.subs" class="node-sub" :x="nodeX(1) + 12" :y="L.tree.rows[1] + 18">its own ctx, own line</text>
          <text class="count count-call" :x="L.tree.x1" :y="L.tree.rows[1] + 4" text-anchor="end">{{ money(0) }}</text>
        </g>
        <g class="deep">
          <circle class="dot dot-deep" :cx="nodeX(2)" :cy="L.tree.rows[2]" r="5" />
          <text class="deep-err" :x="nodeX(2) + 11" :y="L.tree.rows[2] + 4">CostExceeded</text>
          <text v-if="L.tree.subs" class="node-sub" :x="nodeX(2) + 11" :y="L.tree.rows[2] + 18">raised deeper</text>
        </g>
        <g class="err-dot"><circle :cx="nodeX(2)" :cy="L.tree.rows[2]" r="4.5" /></g>

        <!-- the budget it runs under -->
        <text class="head budget-head" :x="L.budget.x" :y="L.budget.head">budget</text>
        <g v-for="(b, i) in ['yours, left', 'its own', 'the tighter']" :key="`b${i}`" class="budget-row">
          <text class="bar-name" :class="{ tight: i === 2 }" :x="L.budget.x" :y="L.budget.rows[i]">{{ b }}</text>
          <text class="bar-sum" :class="[{ tight: i === 2 }, i === 0 ? 'count-left' : '']" :x="L.budget.x1" :y="L.budget.rows[i]" text-anchor="end">{{ money(i === 0 ? RUN - SPENT : OWN) }}</text>
          <rect class="bar-track" :x="L.budget.x" :y="L.budget.rows[i] + 5" :width="(RUN - SPENT) * PX" height="7" rx="3.5" />
          <rect class="bar-fill" :class="`bar-${i}`" :x="L.budget.x" :y="L.budget.rows[i] + 5" :width="(i === 0 ? RUN - SPENT : OWN) * PX" height="7" rx="3.5" />
        </g>
        <rect class="spend" :x="L.budget.x" :y="L.budget.rows[2] + 5" :width="STEP * PX" height="7" rx="3.5" />
        <line class="min-guide" :x1="L.budget.x + OWN * PX" :x2="L.budget.x + OWN * PX" :y1="L.budget.rows[1] + 14" :y2="L.budget.rows[2] + 4" />
        <text v-if="L.tree.subs" class="caption" :x="L.budget.x" :y="L.budget.rows[2] + 32">counted against every</text>
        <text v-if="L.tree.subs" class="caption" :x="L.budget.x" :y="L.budget.rows[2] + 46">flow above it, as spent</text>
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.mono {
  font-family: var(--vp-font-family-mono);
}

.card-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.card-head {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.code-line text,
.out {
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

.code-line .str {
  fill: var(--hmz-lane-4);
}

.caret {
  fill: var(--hmz-lane-1);
}

.found rect {
  fill: var(--hmz-accent);
}

.found text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.out-ok {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.out-err {
  fill: var(--vp-c-danger-1);
  font-weight: 700;
}

.head {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.rung,
.row,
.slot-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.rung-n {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-dim);
}

.rung-words,
.row-words {
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.rung-words .mono {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-lane-1);
}

.rung-on,
.row-on {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.6;
}

.scan-bar {
  fill: var(--hmz-lane-1);
}

.gate-bar {
  stroke: var(--hmz-accent-2);
  stroke-width: 3;
  stroke-linecap: round;
}

.row-err {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.tick circle {
  fill: var(--hmz-accent);
}

.tick path {
  fill: none;
  stroke: #fff;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.gate-foot {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.gate-foot .mono {
  fill: var(--hmz-accent-2);
  font-weight: 600;
}

.slot-box {
  stroke-dasharray: 4 3;
}

.slot-fill {
  fill: var(--hmz-warm);
  fill-opacity: 0.12;
  stroke: var(--hmz-warm);
  stroke-width: 1.3;
}

.slot-name {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.slot-out {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.slot-in {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-warm);
}

.link {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.4;
  stroke-dasharray: 3 3;
}

.dot {
  stroke: var(--vp-c-bg);
  stroke-width: 2;
}

.dot-root {
  fill: var(--hmz-lane-1);
}

.dot-call {
  fill: var(--hmz-lane-3);
}

.dot-deep {
  fill: none;
  stroke: var(--vp-c-danger-1);
  stroke-dasharray: 2 2;
  stroke-width: 1.5;
}

.err-dot circle {
  fill: var(--vp-c-danger-1);
}

.node-name {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.node-sub,
.caption {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.deep-err {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-danger-1);
}

.count,
.bar-sum {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-warm);
}

.bar-name {
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.bar-sum {
  fill: var(--hmz-stage-ink);
}

.bar-name.tight,
.bar-sum.tight {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.bar-track {
  fill: var(--hmz-stage-line);
}

.bar-fill.bar-0 {
  fill: var(--hmz-lane-1);
}

.bar-fill.bar-1 {
  fill: var(--hmz-lane-3);
}

.bar-fill.bar-2 {
  fill: var(--hmz-accent);
  fill-opacity: 0.45;
}

.spend {
  fill: var(--hmz-warm);
}

.min-guide {
  stroke: var(--hmz-accent);
  stroke-width: 1.2;
  stroke-dasharray: 2 2;
}
</style>
