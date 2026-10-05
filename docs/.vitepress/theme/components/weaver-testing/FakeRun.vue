<script setup lang="ts">
// A flow under test is run the way `hmz exec` runs it, with only the far side swapped. Left, the
// test from "Example: test `twice`", with a caret on the line that is running, and under it the
// prompts the fake kept. In the middle, the two ways into one engine -- `hmz exec` and
// `fakes.run_fake` -- and the checks `run_flow` makes either way: the flow looked up by name,
// the roles it declares, the budget, the hooks. Right of the seam, the far side: a coding agent
// CLI, the working directory and the person at the prompt, which turn into `FakeAgentDriver`,
// `FakeEnvDriver` and `FakeOutworlder`. A role the test names gets its fake; the others get
// `run_fake`'s defaults (an empty `FakeEnvDriver` at `/here` for a `LocalEnv` role when no
// `local=` is given, and an outworlder who is away). Drawn from `run_fake` and the fakes in
// src/hmz/runtime/flowing/fakes.py (handed through as `hmz.sdk.fakes`), and `twice`, which
// spawns a session and takes two turns of it. The timing is the page's own pytest output.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { count, createFx, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'hmz exec: lookup, roles, budget, hooks, a CLI',
  'A test swaps only the far side for fakes',
  'run_fake fills each role: yours, or a default',
  'Each turn answers at once; its prompt is kept',
  'The assertion is the flow’s whole contract',
  '1 passed in 0.36s: no CLI, nothing spent',
]

type Tok = [cls: '' | 'kw' | 'fn' | 'str', text: string]
const TEST: Tok[][] = [
  [['', 'builder = '], ['fn', 'fakes.FakeAgentDriver'], ['', '()']],
  [['kw', 'await '], ['fn', 'fakes.run_fake'], ['', '("twice",']],
  [['', '    '], ['str', '"add a --dry-run flag"'], ['', ',']],
  [['', '    agents={'], ['str', '"builder"'], ['', ': builder})']],
  [['kw', 'assert '], ['', 'builder.prompts == [']],
  [['', '    '], ['str', '"add a --dry-run flag"'], ['', ',']],
  [['', '    '], ['str', '"Now review what you…"'], ['', ']']],
]

const CHECKS = ['“twice” found by name', 'each role’s declaration', 'the budget', 'the hooks']
const STEPS = ['spawn()', 'run(task)', 'run("Now review…")']

interface Slot {
  key: string
  role: string
  real: { main: string; sub: [string, string] }
  fake: { main: string; sub: [string, string] }
  tag: string
}
const SLOTS: Slot[] = [
  {
    key: 'agent',
    role: 'builder',
    real: { main: 'claude', sub: ['a coding agent CLI', 'real tokens, real time'] },
    fake: { main: 'FakeAgentDriver', sub: ['answers each turn at once', 'keeps every prompt'] },
    tag: 'yours',
  },
  {
    key: 'env',
    role: 'workspace',
    real: { main: 'your working directory', sub: ['real files', 'real commands'] },
    fake: { main: 'FakeEnvDriver', sub: ['files in a dictionary', 'exec answered from a table'] },
    tag: 'default',
  },
  {
    key: 'person',
    role: 'person',
    real: { main: 'you, at the prompt', sub: ['asked, and answering', ''] },
    fake: { main: 'FakeOutworlder', sub: ['answers from a script', 'or is away'] },
    tag: 'default: away',
  },
]
const tagW = (s: string) => Math.round(s.length * 6.1 + 16)

interface Box {
  x: number
  y: number
  w: number
  h: number
}
interface Layout {
  w: number
  h: number
  test: Box
  line: number
  prompts: Box
  doors: { x: number; y: number; w: number }[]
  engine: Box
  flow: Box
  seam: { x1: number; y1: number; x2: number; y2: number }
  slots: { x: number; w: number; ys: number[]; h: number }
  score: Box
  /** One line under each fake's name, rather than two. */
  joined: boolean
  open: { x: number; y: number; s: number }
  whole: { x: number; y: number; s: number }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  test: { x: 10, y: 46, w: 238, h: 156 },
  line: 18,
  prompts: { x: 10, y: 214, w: 238, h: 76 },
  doors: [
    { x: 262, y: 46, w: 172 },
    { x: 262, y: 72, w: 172 },
  ],
  engine: { x: 262, y: 102, w: 172, h: 96 },
  flow: { x: 262, y: 208, w: 172, h: 82 },
  seam: { x1: 443, y1: 40, x2: 443, y2: 292 },
  slots: { x: 452, w: 176, ys: [46, 124, 202], h: 72 },
  score: { x: 10, y: 304, w: 618, h: 42 },
  joined: false,
  open: { x: 346, y: 118, s: 1.38 },
  whole: { x: 320, y: 180, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 640,
  test: { x: 14, y: 20, w: 332, h: 148 },
  line: 17,
  prompts: { x: 14, y: 502, w: 332, h: 66 },
  doors: [
    { x: 14, y: 180, w: 162 },
    { x: 184, y: 180, w: 162 },
  ],
  engine: { x: 14, y: 210, w: 162, h: 96 },
  flow: { x: 184, y: 210, w: 162, h: 96 },
  seam: { x1: 14, y1: 318, x2: 346, y2: 318 },
  slots: { x: 14, w: 332, ys: [328, 386, 444], h: 50 },
  score: { x: 14, y: 580, w: 332, h: 42 },
  joined: true,
  open: { x: 180, y: 250, s: 1.3 },
  whole: { x: 180, y: 320, s: 1 },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const lineY = (i: number) => L.value.test.y + 36 + i * L.value.line
const testOut = (i: number) => ({ x: L.value.test.x + L.value.test.w - 8, y: lineY(i) - 4 })
const checkY = (i: number) => L.value.engine.y + 38 + i * 16
const stepY = (i: number) => L.value.flow.y + 26 + i * (narrow.value ? 22 : 18)
const slotY = (i: number) => L.value.slots.ys[i]
const rowY = (i: number) => L.value.prompts.y + 38 + i * 18
/** The left edge of a slot, where a beam lands. */
const slotIn = (i: number) =>
  narrow.value ? { x: L.value.slots.x + L.value.slots.w / 2, y: slotY(i) + 2 } : { x: L.value.slots.x + 2, y: slotY(i) + 30 }
const scoreX = (i: number) => L.value.score.x + 14 + [0, 0.5, 0.74][i] * L.value.score.w

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
    const warm = () => palette.warm

    const caret = one('.caret')
    const pc = (i: number, when: number) => {
      tl.to(caret, { attr: { y: lineY(i) - 13 }, duration: 0.45, ease: 'cine' }, when)
      tl.to(at('.test-line')[i], { opacity: 1, duration: 0.3 }, when + 0.1)
    }
    const step = (i: number, when: number) => {
      tl.to(at('.step-hl'), { opacity: 0, duration: 0.2 }, when)
      tl.to(at('.step-hl')[i], { opacity: 1, duration: 0.3 }, when + 0.05)
      tl.to(at('.step-word')[i], { opacity: 1, duration: 0.3 }, when)
    }
    const stepOut = (i: number) =>
      narrow.value ? { x: l.flow.x + l.flow.w / 2, y: stepY(i) + 8 } : { x: l.flow.x + l.flow.w - 8, y: stepY(i) + 8 }
    const engineIn = { x: l.engine.x + l.engine.w / 2, y: l.engine.y + 4 }
    const doorOut = (i: number) => ({ x: l.doors[i].x + l.doors[i].w / 2, y: l.doors[i].y + 18 })

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.test-line, .row, .tag, .reply, .score-cell, .pass-mark, .step-hl, .fake, .fake-box, .slot-hot, .seam-word, .check, .door-hot'), { opacity: 0 }, 0)
    tl.set(at('.step-word'), { opacity: 0.45 }, 0)
    tl.set(at('.real'), { opacity: 1 }, 0)
    tl.set(at('.seam'), { drawSVG: '0%' }, 0)
    tl.set(caret, { opacity: 0, attr: { y: lineY(0) - 13 } }, 0)

    // 0 · `hmz exec` comes in at the top, the engine checks what it always checks, and the flow's
    //     turn goes out across the far side to a real CLI.
    tl.addLabel('beat-0', 0)
    tl.fromTo(at('.panel'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.6, stagger: 0.08 }, 0.05)
    tl.fromTo(at('.door-hot')[0], { opacity: 0 }, { opacity: 1, duration: 0.4 }, 0.6)
    cam.beam(doorOut(0), engineIn, lane1, 0.9, { duration: 0.6, bend: 0.25 })
    tl.fromTo(at('.check'), { opacity: 0 }, { opacity: 1, duration: 0.3, stagger: 0.3 }, 1.4)
    tl.fromTo(at('.tick'), { scale: 0, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.35, ease: 'back.out(3)', stagger: 0.3 }, 1.4)
    cam.shot(l.whole, 1.2, 2.2)
    step(0, 2.7)
    step(1, 3.1)
    cam.beam(stepOut(1), slotIn(0), warm, 3.2, { duration: 0.7, bend: -0.15 })
    tl.fromTo(at('.slot-hot')[0], { opacity: 0 }, { opacity: 1, duration: 0.3, yoyo: true, repeat: 1 }, 3.9)
    cam.flare(slotIn(0), warm, 3.9, 14)

    // 1 · the seam between what humanize is and what it drives; everything past it is faked.
    const T1 = 4.8
    tl.addLabel('beat-1', T1)
    tl.to(at('.step-hl'), { opacity: 0, duration: 0.3 }, T1)
    tl.to(at('.step-word'), { opacity: 0.45, duration: 0.3 }, T1)
    tl.to(at('.door-hot')[0], { opacity: 0, duration: 0.4 }, T1)
    tl.to(at('.seam'), { drawSVG: '100%', duration: 1, ease: 'cine' }, T1)
    tl.to(at('.seam-word'), { opacity: 1, duration: 0.4 }, T1 + 0.5)
    SLOTS.forEach((_, i) => {
      const t = T1 + 0.9 + i * 0.45
      tl.to(at('.real')[i], { opacity: 0, y: -8, duration: 0.35, ease: 'power2.in' }, t)
      tl.fromTo(at('.fake')[i], { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.45, ease: 'back.out(2)' }, t + 0.3)
      tl.to(at('.fake-box')[i], { opacity: 1, duration: 0.4 }, t + 0.3)
      cam.flare(narrow.value ? { x: l.slots.x + 20, y: slotY(i) + 20 } : { x: l.slots.x + 4, y: slotY(i) + 30 }, ok, t + 0.3, 16)
    })
    // and the test that swaps it comes up.
    tl.to(at('.test-line'), { opacity: 0.5, duration: 0.5, stagger: 0.06 }, T1 + 2.2)

    // 2 · the test's own way in. It names `builder`; the others get run_fake's defaults.
    const T2 = 7.6
    tl.addLabel('beat-2', T2)
    tl.to(caret, { opacity: 1, duration: 0.3 }, T2)
    pc(0, T2)
    pc(1, T2 + 0.5)
    pc(2, T2 + 0.7)
    pc(3, T2 + 0.9)
    tl.to(at('.door-hot')[1], { opacity: 1, duration: 0.4 }, T2 + 0.6)
    cam.beam(testOut(1), { x: l.doors[1].x + 6, y: l.doors[1].y + 10 }, lane1, T2 + 0.6, { duration: 0.6, bend: -0.2 })
    cam.beam(doorOut(1), engineIn, lane1, T2 + 1.2, { duration: 0.5, bend: 0.25 })
    tl.to(at('.check'), { opacity: 0.4, duration: 0.15 }, T2 + 1.45)
    tl.to(at('.check'), { opacity: 1, duration: 0.25, stagger: 0.12 }, T2 + 1.6)
    cam.beam(testOut(0), slotIn(0), lane1, T2 + 1.8, { duration: 0.9, bend: -0.12 })
    SLOTS.forEach((_, i) => {
      tl.fromTo(at('.tag')[i], { opacity: 0, scale: 0.6, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(2.4)' }, T2 + 2.7 + i * 0.35)
    })

    // 3 · two turns: each prompt goes over, `ok` comes straight back, and the fake keeps it.
    const T3 = T2 + 4.2
    tl.addLabel('beat-3', T3)
    tl.to(at('.test-line'), { opacity: 0.7, duration: 0.3 }, T3)
    step(0, T3)
    const turn = (i: number, when: number) => {
      step(i + 1, when)
      cam.beam(stepOut(i + 1), slotIn(0), lane1, when + 0.2, { duration: 0.6, bend: -0.15 })
      tl.fromTo(at('.reply')[i], { opacity: 0, scale: 0.4, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.3, ease: 'back.out(3)' }, when + 0.8)
      cam.beam(slotIn(0), stepOut(i + 1), ok, when + 0.85, { duration: 0.35, bend: 0.15 })
      tl.to(at('.reply')[i], { opacity: 0, duration: 0.4 }, when + 1.7)
      const row = { x: l.prompts.x + 20, y: rowY(i) - 4 }
      cam.beam(narrow.value ? { x: l.slots.x + 40, y: slotY(0) + 40 } : { x: l.slots.x + 30, y: slotY(0) + 60 }, row, lane1, when + 1.1, { duration: 0.8, bend: 0.12 })
      tl.fromTo(at('.row')[i], { opacity: 0, x: -10 }, { opacity: 1, x: 0, duration: 0.45 }, when + 1.8)
      cam.flare(row, lane1, when + 1.9, 10, 70)
    }
    turn(0, T3 + 0.4)
    turn(1, T3 + 2.6)

    // 4 · the test reads the prompts back: the task first, the review second.
    const T4 = T3 + 5.4
    tl.addLabel('beat-4', T4)
    tl.to(at('.step-hl'), { opacity: 0, duration: 0.3 }, T4)
    pc(4, T4)
    pc(5, T4 + 0.4)
    pc(6, T4 + 0.7)
    tl.to(at('.row text'), { fill: 'var(--hmz-accent)', duration: 0.3, stagger: 0.2 }, T4 + 0.8)
    tl.to(at('.assert-tok'), { fill: 'var(--hmz-accent)', duration: 0.3 }, T4 + 1.3)
    tl.to(at('.test-line').slice(4), { opacity: 1, duration: 0.3 }, T4 + 1.3)
    tl.fromTo(one('.pass-mark'), { opacity: 0, scale: 0, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.45, ease: 'back.out(3)' }, T4 + 1.5)
    cam.flare({ x: l.test.x + l.test.w - 18, y: lineY(4) - 4 }, ok, T4 + 1.5, 24)

    // 5 · what it cost: pytest's own line, and nothing else.
    const T5 = T4 + 2.6
    tl.addLabel('beat-5', T5)
    tl.to(caret, { opacity: 0.3, duration: 0.5 }, T5)
    tl.fromTo(at('.score-cell'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.35 }, T5 + 0.1)
    count(tl, one('.secs'), 0, 0.36, T5 + 0.2, { duration: 0.9, format: (n) => `${n.toFixed(2)}s` })
    cam.flare({ x: scoreX(0) + 60, y: l.score.y + 16 }, ok, T5 + 1.1, 26)

    tl.addLabel('rest', T5 + 2)
    cam.shot({ ...l.whole, s: l.whole.s * 1.025 }, T5 + 1.2, 3, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T5 + 4.4)

    // The seam's dotted line hums for the whole timeline: a slow march of its dashes.
    tl.fromTo(at('.hum'), { strokeDashoffset: 0 }, { strokeDashoffset: -90, duration: tl.duration(), ease: 'none' }, 0)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 16"
    label="A test runs a flow the way hmz exec runs it. hmz exec looks the flow up by name, checks each role's declaration, the budget and the hooks, and sends the flow's turns across to a real coding agent CLI, in your working directory, with you at the prompt. A test swaps only that far side: the CLI for FakeAgentDriver, the directory for FakeEnvDriver, the person for FakeOutworlder. fakes.run_fake, called with twice and its task, goes through the same engine; the builder role gets the test's fake, the workspace gets a default empty FakeEnvDriver at /here and the person a default who is away. Each of twice's two turns is answered ok at once, and the fake keeps its prompt in builder.prompts. The assertion that builder.prompts is the task and then the review passes: 1 passed in 0.36s, nothing spent, no CLI started."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="world">
        <!-- the test -->
        <g class="panel">
          <rect class="card" :x="L.test.x" :y="L.test.y" :width="L.test.w" :height="L.test.h" rx="9" />
          <text class="head" :x="L.test.x + 12" :y="L.test.y + 17">tests/test_twice.py</text>
          <rect class="caret" :x="L.test.x + 4" :y="lineY(0) - 13" width="3" height="16" rx="1.5" />
          <g v-for="(line, i) in TEST" :key="i" class="test-line">
            <text :x="L.test.x + 14" :y="lineY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="[tok[0], i >= 4 ? 'assert-tok' : '']">{{ tok[1] }}</tspan></text>
          </g>
          <g class="pass-mark">
            <circle :cx="L.test.x + L.test.w - 18" :cy="lineY(4) - 4" r="9" />
            <path :d="`M${L.test.x + L.test.w - 22} ${lineY(4) - 4} l3 3 l6 -6`" />
          </g>
        </g>

        <!-- what the fake kept -->
        <g class="panel">
          <rect class="card" :x="L.prompts.x" :y="L.prompts.y" :width="L.prompts.w" :height="L.prompts.h" rx="9" />
          <text class="head" :x="L.prompts.x + 12" :y="L.prompts.y + 17">builder.prompts</text>
          <g class="row"><text :x="L.prompts.x + 14" :y="rowY(0)">[0] "add a --dry-run flag"</text></g>
          <g class="row"><text :x="L.prompts.x + 14" :y="rowY(1)">[1] "Now review what you just…"</text></g>
        </g>

        <!-- two ways in, one engine -->
        <g v-for="(d, i) in L.doors" :key="`d${i}`" class="panel">
          <rect class="door" :x="d.x" :y="d.y" :width="d.w" height="20" rx="10" />
          <rect class="door-hot" :x="d.x" :y="d.y" :width="d.w" height="20" rx="10" />
          <text class="door-word" :x="d.x + d.w / 2" :y="d.y + 14" text-anchor="middle">{{ i === 0 ? 'hmz exec -f twice …' : 'run_fake("twice", …)' }}</text>
        </g>
        <g class="panel">
          <rect class="card engine" :x="L.engine.x" :y="L.engine.y" :width="L.engine.w" :height="L.engine.h" rx="9" />
          <text class="head" :x="L.engine.x + 12" :y="L.engine.y + 17">run_flow · checks</text>
          <g v-for="(c, i) in CHECKS" :key="c" class="check">
            <g class="tick"><circle :cx="L.engine.x + 18" :cy="checkY(i) - 4" r="5" /></g>
            <text class="check-word" :x="L.engine.x + 30" :y="checkY(i)">{{ c }}</text>
          </g>
        </g>
        <g class="panel">
          <rect class="card" :x="L.flow.x" :y="L.flow.y" :width="L.flow.w" :height="L.flow.h" rx="9" />
          <text class="head" :x="L.flow.x + 12" :y="L.flow.y + 17">flow twice</text>
          <g v-for="(s, i) in STEPS" :key="s">
            <rect class="step-hl" :x="L.flow.x + 8" :y="stepY(i)" :width="L.flow.w - 16" height="16" rx="4" />
            <text class="step-word" :x="L.flow.x + 14" :y="stepY(i) + 12">{{ s }}</text>
          </g>
        </g>

        <!-- the seam, and the far side -->
        <line class="seam-base hum" :x1="L.seam.x1" :y1="L.seam.y1" :x2="L.seam.x2" :y2="L.seam.y2" />
        <line class="seam" :x1="L.seam.x1" :y1="L.seam.y1" :x2="L.seam.x2" :y2="L.seam.y2" />
        <g class="seam-word">
          <text :x="L.slots.x + L.slots.w" :y="L.joined ? L.seam.y1 - 4 : L.seam.y2 - 4" text-anchor="end">the far side: faked</text>
        </g>
        <g v-for="(s, i) in SLOTS" :key="s.key" class="panel">
          <rect class="slot-box" :x="L.slots.x" :y="slotY(i)" :width="L.slots.w" :height="L.slots.h" rx="8" />
          <rect class="fake-box" :x="L.slots.x" :y="slotY(i)" :width="L.slots.w" :height="L.slots.h" rx="8" />
          <rect class="slot-hot" :x="L.slots.x" :y="slotY(i)" :width="L.slots.w" :height="L.slots.h" rx="8" />
          <text class="caps" :x="L.slots.x + 10" :y="slotY(i) + 15">{{ s.role }}</text>
          <g class="real">
            <text class="main real-main" :x="L.slots.x + 10" :y="slotY(i) + (L.joined ? 31 : 34)">{{ s.real.main }}</text>
            <template v-if="L.joined">
              <text class="sub" :x="L.slots.x + 10" :y="slotY(i) + 45">{{ s.real.sub.filter(Boolean).join(' · ') }}</text>
            </template>
            <template v-else>
              <text class="sub" :x="L.slots.x + 10" :y="slotY(i) + 50">{{ s.real.sub[0] }}</text>
              <text class="sub" :x="L.slots.x + 10" :y="slotY(i) + 64">{{ s.real.sub[1] }}</text>
            </template>
          </g>
          <g class="fake">
            <text class="main fake-main" :x="L.slots.x + 10" :y="slotY(i) + (L.joined ? 31 : 34)">{{ s.fake.main }}</text>
            <template v-if="L.joined">
              <text class="sub" :x="L.slots.x + 10" :y="slotY(i) + 45">{{ s.fake.sub.join(' · ') }}</text>
            </template>
            <template v-else>
              <text class="sub" :x="L.slots.x + 10" :y="slotY(i) + 50">{{ s.fake.sub[0] }}</text>
              <text class="sub" :x="L.slots.x + 10" :y="slotY(i) + 64">{{ s.fake.sub[1] }}</text>
            </template>
          </g>
          <g class="tag" :class="i === 0 ? 'tag-yours' : 'tag-default'">
            <rect :x="L.slots.x + L.slots.w - 8 - tagW(s.tag)" :y="slotY(i) + 5" :width="tagW(s.tag)" height="15" rx="7.5" />
            <text :x="L.slots.x + L.slots.w - 8 - tagW(s.tag) / 2" :y="slotY(i) + 16" text-anchor="middle">{{ s.tag }}</text>
          </g>
        </g>
        <g v-for="i in 2" :key="`r${i}`" class="reply">
          <rect :x="L.slots.x + L.slots.w - 40" :y="slotY(0) + (L.joined ? 26 : 26)" width="30" height="16" rx="8" />
          <text :x="L.slots.x + L.slots.w - 25" :y="slotY(0) + (L.joined ? 38 : 38)" text-anchor="middle">"ok"</text>
        </g>

        <!-- pytest's line -->
        <g class="panel">
          <rect class="card score" :x="L.score.x" :y="L.score.y" :width="L.score.w" :height="L.score.h" rx="9" />
          <g class="score-cell">
            <text class="score-big" :x="scoreX(0)" :y="L.score.y + 19">1 passed in <tspan class="secs">0.36s</tspan></text>
            <text class="score-cap" :x="scoreX(0)" :y="L.score.y + 34">pytest -q</text>
          </g>
          <g class="score-cell">
            <text class="score-big" :x="scoreX(1)" :y="L.score.y + 19">$0</text>
            <text class="score-cap" :x="scoreX(1)" :y="L.score.y + 34">spent</text>
          </g>
          <g class="score-cell">
            <text class="score-big" :x="scoreX(2)" :y="L.score.y + 19">0</text>
            <text class="score-cap" :x="scoreX(2)" :y="L.score.y + 34">CLIs started</text>
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

.card {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.head {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.test-line text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  white-space: pre;
  fill: var(--hmz-stage-ink);
}

.test-line .kw {
  fill: var(--hmz-lane-3);
  font-weight: 600;
}

.test-line .fn {
  fill: var(--hmz-lane-1);
}

.test-line .str {
  fill: var(--hmz-warm);
}

.caret {
  fill: var(--hmz-lane-1);
}

.pass-mark circle {
  fill: var(--hmz-accent);
}

.pass-mark path {
  fill: none;
  stroke: #fff;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.row text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  white-space: pre;
  fill: var(--hmz-stage-ink);
}

.door {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.door-hot {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
}

.door-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.engine {
  stroke: var(--hmz-lane-1);
  stroke-opacity: 0.5;
}

.tick circle {
  fill: var(--hmz-lane-1);
}

.check-word {
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.step-hl {
  fill: var(--hmz-lane-1);
  fill-opacity: 0.16;
  stroke: var(--hmz-lane-1);
  stroke-width: 1;
}

.step-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.seam-base {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
  stroke-dasharray: 2 5;
}

.seam {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  stroke-dasharray: 7 5;
}

.seam-word text {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-accent);
}

.slot-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-warm);
  stroke-opacity: 0.7;
  stroke-width: 1.2;
}

.fake-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.4;
  stroke-dasharray: 5 3;
}

.slot-hot {
  fill: var(--hmz-warm);
  fill-opacity: 0.18;
  stroke: var(--hmz-warm);
  stroke-width: 2;
}

.caps {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.main {
  font-size: 13px;
  font-weight: 700;
}

.real-main {
  fill: var(--hmz-warm);
}

.fake-main {
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-accent);
}

.sub {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.tag text {
  font-size: 11px;
  font-weight: 600;
}

.tag-yours rect {
  fill: var(--hmz-lane-1);
}

.tag-yours text {
  fill: #fff;
}

.tag-default rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-dim);
  stroke-width: 1;
}

.tag-default text {
  fill: var(--hmz-stage-dim);
}

.reply rect {
  fill: var(--hmz-accent);
}

.reply text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.score {
  stroke: var(--hmz-accent);
  stroke-opacity: 0.55;
}

.score-big {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.score-cap {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}
</style>
