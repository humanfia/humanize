<script setup lang="ts">
// Many turns at once, played out on `fanout` from Many turns at once. The files are the four
// of its test (`git ls-files *.py` answers a.py to d.py), the cap is its `Semaphore(2)`, and
// b.py's turn fails with a `HarnessError` ("the CLI died mid-turn"), which
// `gather(..., return_exceptions=True)` hands back in b.py's place, for the flow to print and
// read past. A session is spawned inside the semaphore, so no more are open than turns are
// going. The rule under it: a session takes one turn at a time, so a second `run` on a session
// whose turn is still going raises `SessionError` (src/hmz/flows/errors.py), neither queued nor
// interleaved; two sessions go at once. Sessions of one agent are still one agent. `spawn` and
// `run` are `Agent.spawn` and `Agent.run` in src/hmz/flows/agents.py: a turn given no `env=`
// works in the run's workspace. The timings are invented.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig, type Shot } from '../../motion/camera'
import { createFx, type Fx, type } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'git ls-files: four files, a turn for each',
  'Semaphore(2): two turns at a time',
  'b.py fails, and c.py takes its slot',
  'a.py answers, and d.py goes in',
  'gather: a failure in its place, the rest kept',
  'Two turns at once need two sessions',
]

type Tok = [cls: '' | 'kw' | 'fn' | 'str', text: string]
const CODE: Tok[][] = [
  [['', '_, out, _ = '], ['kw', 'await '], ['fn', 'workspace.exec'], ['', '(']],
  [['', '  ['], ['str', '"git"'], ['', ', '], ['str', '"ls-files"'], ['', ', '], ['str', '"*.py"'], ['', '])']],
  [['', 'gate = '], ['fn', 'asyncio.Semaphore'], ['', '(2)']],
  [['kw', 'async def '], ['fn', 'one'], ['', '(path):']],
  [['kw', '  async with '], ['', 'gate:']],
  [['', '    s = '], ['kw', 'await '], ['fn', 'agent.spawn'], ['', '()']],
  [['kw', '    return await '], ['fn', 'agent.run'], ['', '(']],
  [['str', '      f"…The file is {path}."'], ['', ',']],
  [['', '      session=s)']],
  [['', 'said = '], ['kw', 'await '], ['fn', 'asyncio.gather'], ['', '(*…,']],
  [['', '  return_exceptions=True)']],
]

/** Each file's turn, as fractions of the time axis: when it reaches the gate is 0 for all. */
const FILES = [
  { name: 'a.py', start: 0, end: 0.42, failed: false },
  { name: 'b.py', start: 0, end: 0.3, failed: true },
  { name: 'c.py', start: 0.3, end: 0.78, failed: false },
  { name: 'd.py', start: 0.42, end: 0.9, failed: false },
] as const

/** Who holds each of the two slots, and from when. */
const SLOTS = [
  [
    ['a.py', 0],
    ['d.py', 0.42],
    ['free', 0.9],
  ],
  [
    ['b.py', 0],
    ['c.py', 0.3],
    ['free', 0.78],
  ],
] as const

interface Layout {
  w: number
  h: number
  code: { x: number; y: number; w: number }
  line: number
  agent: { x: number; y: number }
  sem: { x: number; y: number; slots: number[]; slotW: number }
  lanes: number[]
  x0: number
  x1: number
  label: number
  said: { x: number; y: number; cells: number[] }
  printed: number
  dict: number
  rule: { head: number; sub: number; rows: number[]; foot: number; left: [number, number]; right: [number, number] }
  shots: Record<'open' | 'lanes' | 'said' | 'rule' | 'whole', Shot>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  code: { x: 12, y: 16, w: 254 },
  line: 15.5,
  agent: { x: 286, y: 22 },
  sem: { x: 286, y: 60, slots: [384, 498], slotW: 104 },
  lanes: [114, 144, 174, 204],
  x0: 330,
  x1: 620,
  label: 286,
  said: { x: 14, y: 244, cells: [52, 92, 190, 230] },
  printed: 292,
  dict: 314,
  rule: { head: 254, sub: 274, rows: [290, 314], foot: 340, left: [286, 448], right: [470, 626] },
  shots: {
    open: { x: 150, y: 140, s: 1.36 },
    lanes: { x: 440, y: 140, s: 1.2 },
    said: { x: 230, y: 230, s: 1.12 },
    rule: { x: 456, y: 270, s: 1.3 },
    whole: { x: 320, y: 180, s: 1 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 640,
  code: { x: 12, y: 8, w: 336 },
  line: 15.5,
  agent: { x: 12, y: 230 },
  sem: { x: 12, y: 262, slots: [112, 232], slotW: 112 },
  lanes: [312, 340, 368, 396],
  x0: 54,
  x1: 344,
  label: 12,
  said: { x: 12, y: 422, cells: [48, 88, 186, 226] },
  printed: 466,
  dict: 488,
  rule: { head: 522, sub: 542, rows: [558, 582], foot: 608, left: [12, 172], right: [200, 348] },
  shots: {
    open: { x: 180, y: 250, s: 1.04 },
    lanes: { x: 180, y: 330, s: 1 },
    said: { x: 180, y: 330, s: 1 },
    rule: { x: 180, y: 330, s: 1 },
    whole: { x: 180, y: 320, s: 1 },
  },
}

/** How wide each cell of `said` is: the failure needs room for its name. */
const CELL = [34, 92, 34, 34]

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const lineY = (i: number) => L.value.code.y + 36 + i * L.value.line
const codeEnd = (i: number) => ({ x: L.value.code.x + L.value.code.w - 8, y: lineY(i) - 4 })
const codeH = computed(() => 36 + CODE.length * L.value.line + 2)
const X = (f: number) => L.value.x0 + f * (L.value.x1 - L.value.x0)
const lanesTop = computed(() => L.value.lanes[0] - 18)
const lanesBottom = computed(() => L.value.lanes[3] + 16)

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
    const ok = () => palette.accent
    const warm = () => palette.warm
    const danger = () => palette.danger

    const caret = one('.caret')
    const pc = (i: number, when: number) => {
      tl.to(caret, { attr: { y: lineY(i) - 12 }, duration: 0.4, ease: 'cine' }, when)
      tl.fromTo(at('.code-line')[i], { opacity: 0.55 }, { opacity: 1, duration: 0.3 }, when + 0.1)
    }
    const pop = (el: Element, when: number) =>
      tl.fromTo(el, { opacity: 0, scale: 0.3, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.45, ease: 'back.out(2.6)' }, when)

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.code-line'), { opacity: 0 }, 0)
    tl.set(at('.agent, .sem, .lane-name, .spawn, .end-ok, .end-bad, .fail-word, .cell, .said-name, .printed, .dict, .rule-head, .rule-sub, .rule-row, .rule-bad, .rule-ok, .who, .rbar-word'), { opacity: 0 }, 0)
    tl.set(at('.lane, .wait'), { drawSVG: '0%' }, 0)
    tl.set(one('.playhead'), { opacity: 0, x: 0 }, 0)
    tl.set(caret, { opacity: 0, attr: { y: lineY(0) - 12 } }, 0)

    // 0 · the flow lists the files: a lane for each, and one agent behind them all.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.card'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.7 }, 0.1)
    tl.fromTo(at('.code-line'), { opacity: 0, x: -10 }, { opacity: 0.55, x: 0, duration: 0.45, stagger: 0.07 }, 0.3)
    tl.to(caret, { opacity: 1, duration: 0.3 }, 1.2)
    pc(0, 1.2)
    pc(1, 1.6)
    cam.shot(l.shots.lanes, 1.9, 1.8)
    FILES.forEach((f, i) => {
      cam.beam(codeEnd(1), { x: l.label + 4, y: l.lanes[i] }, lane1, 2.3 + i * 0.18, { duration: 0.8, bend: -0.12 })
      tl.fromTo(at('.lane-name')[i], { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.4 }, 3 + i * 0.18)
      tl.to(at('.lane')[i], { drawSVG: '100%', duration: 0.9, ease: 'cine' }, 3.1 + i * 0.18)
    })
    tl.fromTo(one('.agent'), { opacity: 0, y: -6 }, { opacity: 1, y: 0, duration: 0.5 }, 3.9)

    // 1 · the semaphore lets two through: a and b spawn a session each and go; c and d wait.
    const T1 = 4.8
    const D = 9
    const S = T1 + 1.6
    const when = (f: number) => S + f * D
    tl.addLabel('beat-1', T1)
    pc(2, T1)
    tl.fromTo(one('.sem'), { opacity: 0, y: -6 }, { opacity: 1, y: 0, duration: 0.5 }, T1 + 0.3)
    pc(3, T1 + 0.8)
    pc(4, T1 + 1.2)
    tl.to(one('.playhead'), { opacity: 1, duration: 0.3 }, S - 0.2)
    tl.fromTo(one('.playhead'), { x: 0 }, { x: l.x1 - l.x0, duration: D, ease: 'none' }, S)
    tl.to(one('.playhead'), { opacity: 0, duration: 0.4 }, S + D)
    // Each slot names who holds it.
    SLOTS.forEach((held, k) =>
      held.forEach(([, f], j) => {
        const w = j === 0 ? S - 0.1 : when(f)
        if (j > 0) tl.to(at(`.who-${k}`)[j - 1], { opacity: 0, duration: 0.25 }, w)
        pop(at(`.who-${k}`)[j], w + 0.05)
      }),
    )
    FILES.forEach((f, i) => {
      if (f.start > 0) tl.to(at('.wait')[i], { drawSVG: '100%', duration: f.start * D, ease: 'none' }, S)
      pc(5, when(f.start))
      pop(at('.spawn')[i], when(f.start))
      cam.flare({ x: X(f.start), y: l.lanes[i] }, lane1, when(f.start), 14, 60)
      tl.fromTo(at('.bar')[i], { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: (f.end - f.start) * D, ease: 'none' }, when(f.start))
      if (f.failed) {
        pop(at('.end-bad')[0], when(f.end))
        tl.to(at('.fail-word')[0], { opacity: 1, duration: 0.4 }, when(f.end) + 0.1)
        cam.flare({ x: X(f.end), y: l.lanes[i] }, danger, when(f.end), 26, 90)
      } else {
        pop(at('.end-ok')[i], when(f.end))
        cam.flare({ x: X(f.end), y: l.lanes[i] }, ok, when(f.end), 16, 70)
      }
    })
    pc(6, S + 0.5)
    pc(7, S + 0.9)
    pc(8, S + 1.3)

    // 2 and 3 · fall where the sweep reaches the failure, and a's answer.
    tl.addLabel('beat-2', when(0.3) - 0.4)
    tl.addLabel('beat-3', when(0.42) - 0.3)

    // 4 · gather answers in the order of the paths, whatever order they finished in, the
    //     failure in its place; the flow prints it and returns the rest.
    const T4 = S + D + 0.6
    tl.addLabel('beat-4', T4)
    cam.shot(l.shots.said, T4, 1.6)
    pc(9, T4)
    pc(10, T4 + 0.3)
    tl.to(one('.said-name'), { opacity: 1, duration: 0.4 }, T4 + 0.6)
    FILES.forEach((f, i) => {
      const w = T4 + 0.8 + i * 0.35
      cam.beam({ x: X(f.end), y: l.lanes[i] }, { x: l.said.cells[i] + CELL[i] / 2, y: l.said.y + 10 }, f.failed ? danger : ok, w, { duration: 0.8, bend: 0.12, burst: 10 })
      pop(at('.cell')[i], w + 0.75)
    })
    tl.to(one('.printed'), { opacity: 1, duration: 0.2 }, T4 + 2.7)
    type(tl, one('.printed-text'), 'b.py: failed, the CLI died mid-turn', T4 + 2.7, 34)
    tl.fromTo(one('.dict'), { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.5 }, T4 + 4)
    cam.flare({ x: l.said.x + 120, y: l.dict - 4 }, ok, T4 + 4.2, 22, 80)

    // 5 · the rule: one session takes one turn at a time. A second run on it is refused.
    const T5 = T4 + 5.2
    tl.addLabel('beat-5', T5)
    cam.shot(l.shots.rule, T5, 1.6)
    tl.to(caret, { opacity: 0.3, duration: 0.4 }, T5)
    tl.to(one('.rule-head'), { opacity: 1, duration: 0.5 }, T5 + 0.4)
    tl.to(at('.rule-sub'), { opacity: 1, duration: 0.5, stagger: 0.2 }, T5 + 0.6)
    tl.to(at('.rule-row'), { opacity: 1, duration: 0.4, stagger: 0.1 }, T5 + 0.8)
    tl.fromTo(at('.rbar-a'), { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 2.4, ease: 'none' }, T5 + 1.1)
    tl.to(at('.rbar-word'), { opacity: 1, duration: 0.4 }, T5 + 1.9)
    // The second run on `s` comes in, and bounces off.
    const knock = one('.knock')
    tl.fromTo(knock, { opacity: 0, x: -24 }, { opacity: 1, x: 0, duration: 0.6, ease: 'power2.in' }, T5 + 1.6)
    tl.to(knock, { x: -6, duration: 0.08, repeat: 3, yoyo: true, ease: 'none' }, T5 + 2.2)
    tl.to(knock, { opacity: 0.35, duration: 0.4 }, T5 + 2.6)
    cam.flare({ x: (l.rule.left[0] + l.rule.left[1]) / 2, y: l.rule.rows[1] }, danger, T5 + 2.2, 24, 80)
    pop(one('.rule-bad'), T5 + 2.3)
    // Two sessions, both at once.
    tl.fromTo(at('.rbar-b'), { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 2.4, ease: 'none' }, T5 + 1.6)
    pop(one('.rule-ok'), T5 + 4.1)
    cam.flare({ x: l.rule.right[1] - 8, y: l.rule.rows[0] }, ok, T5 + 4, 12, 60)
    cam.flare({ x: l.rule.right[1] - 8, y: l.rule.rows[1] }, ok, T5 + 4, 12, 60)

    tl.addLabel('rest', T5 + 6.4)
    cam.shot(l.shots.whole, T5 + 4.6, 1.6)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T5 + 8.4)

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
    label="Many turns at once, in the fanout flow. git ls-files lists four Python files, a.py to d.py, and each gets a turn of one agent in a session of its own. asyncio.Semaphore(2) lets two through at a time: a.py and b.py spawn a session and start, c.py and d.py wait. b.py's turn fails with a HarnessError, and c.py takes its slot; a.py answers, and d.py takes that one. gather with return_exceptions=True answers in the order of the files, with the HarnessError in b.py's place: the flow prints b.py: failed, the CLI died mid-turn, and returns the other three answers as a dict. The rule beneath it: two turns at once need two sessions. A second run on a session whose turn is still going raises SessionError, neither queued nor interleaved; two sessions both go at once."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="world">
        <g class="card">
          <rect class="card-box" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="codeH" rx="10" />
          <text class="card-head" :x="L.code.x + 12" :y="L.code.y + 17">@flow · async def fanout(task, …)</text>
          <rect class="caret" :x="L.code.x + 4" :y="lineY(0) - 12" width="3" height="15" rx="1.5" />
          <g v-for="(line, i) in CODE" :key="i" class="code-line">
            <text :x="L.code.x + 13" :y="lineY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>

        <!-- one agent behind every lane -->
        <g class="agent">
          <rect class="agent-pill" :x="L.agent.x" :y="L.agent.y" width="50" height="18" rx="9" />
          <text class="agent-name" :x="L.agent.x + 25" :y="L.agent.y + 13" text-anchor="middle">agent</text>
          <text class="agent-says" :x="L.agent.x + 58" :y="L.agent.y + 13">one CLI, one model, one role</text>
        </g>

        <!-- the semaphore: two slots, and who holds each -->
        <g class="sem">
          <text class="sem-name" :x="L.sem.x" :y="L.sem.y + 15">Semaphore(2)</text>
          <g v-for="(sx, k) in L.sem.slots" :key="`slot${k}`">
            <rect class="slot" :x="sx" :y="L.sem.y" :width="L.sem.slotW" height="22" rx="11" />
            <text class="slot-n" :x="sx + 12" :y="L.sem.y + 15">{{ k + 1 }}</text>
          </g>
        </g>
        <template v-for="(held, k) in SLOTS" :key="`h${k}`">
          <g v-for="(h, j) in held" :key="`w${k}${j}`" class="who" :class="[`who-${k}`, h[0] === 'free' ? 'free' : '']">
            <text :x="L.sem.slots[k] + L.sem.slotW / 2 + 6" :y="L.sem.y + 15" text-anchor="middle">{{ h[0] }}</text>
          </g>
        </template>

        <!-- a lane per file -->
        <line class="playhead" :x1="L.x0" :x2="L.x0" :y1="lanesTop" :y2="lanesBottom" />
        <g v-for="(f, i) in FILES" :key="f.name">
          <g class="lane-name"><text :x="L.label" :y="L.lanes[i] + 4">{{ f.name }}</text></g>
          <line class="lane" :x1="L.x0" :x2="L.x1" :y1="L.lanes[i]" :y2="L.lanes[i]" />
          <line class="wait" :x1="L.x0" :x2="X(f.start)" :y1="L.lanes[i]" :y2="L.lanes[i]" />
          <rect class="bar" :class="{ bad: f.failed }" :x="X(f.start)" :y="L.lanes[i] - 7" :width="X(f.end) - X(f.start)" height="14" rx="7" />
          <circle class="spawn" :cx="X(f.start)" :cy="L.lanes[i]" r="5" />
          <g v-if="!f.failed" class="end-ok">
            <circle :cx="X(f.end)" :cy="L.lanes[i]" r="7" />
            <path :d="`M${X(f.end) - 3.5} ${L.lanes[i]} l2.5 2.5 l4.5 -5`" />
          </g>
          <g v-else class="end-ok" />
        </g>
        <g class="end-bad">
          <circle :cx="X(FILES[1].end)" :cy="L.lanes[1]" r="7" />
          <path :d="`M${X(FILES[1].end) - 3} ${L.lanes[1] - 3} l6 6 M${X(FILES[1].end) + 3} ${L.lanes[1] - 3} l-6 6`" />
        </g>
        <text class="fail-word" :x="X(FILES[1].end) + 12" :y="L.lanes[1] + 4">HarnessError</text>

        <!-- what gather answers, in the order of the paths -->
        <text class="said-name" :x="L.said.x" :y="L.said.y + 14">said</text>
        <g v-for="(f, i) in FILES" :key="`c${i}`" class="cell" :class="{ bad: f.failed }">
          <rect :x="L.said.cells[i]" :y="L.said.y" :width="CELL[i]" height="20" rx="5" />
          <text :x="L.said.cells[i] + CELL[i] / 2" :y="L.said.y + 14" text-anchor="middle">{{ f.failed ? 'HarnessError' : f.name[0] }}</text>
        </g>
        <g class="printed"><text class="printed-text" :x="L.said.x" :y="L.printed">b.py: failed, the CLI died mid-turn</text></g>
        <g class="dict"><text :x="L.said.x" :y="L.dict">→ {"a.py": …, "c.py": …, "d.py": …}</text></g>

        <!-- the rule: a session takes one turn at a time -->
        <text class="head rule-head" :x="L.rule.left[0]" :y="L.rule.head">two turns at once need two sessions</text>
        <text class="rule-sub" :x="L.rule.left[0]" :y="L.rule.sub">one session</text>
        <text class="rule-sub" :x="L.rule.right[0]" :y="L.rule.sub">two sessions</text>
        <g class="rule-row">
          <text class="rule-s" :x="L.rule.left[0]" :y="L.rule.rows[0] + 4">s</text>
          <rect class="rbar rbar-a" :x="L.rule.left[0] + 16" :y="L.rule.rows[0] - 7" :width="L.rule.left[1] - L.rule.left[0] - 16" height="14" rx="7" />
          <text class="rbar-word" :x="L.rule.left[0] + 24" :y="L.rule.rows[0] + 4">run(a)</text>
        </g>
        <g class="rule-row">
          <text class="rule-s" :x="L.rule.left[0]" :y="L.rule.rows[1] + 4">s</text>
          <g class="knock">
            <rect class="rbar-try" :x="L.rule.left[0] + 16" :y="L.rule.rows[1] - 7" width="56" height="14" rx="7" />
            <text class="rbar-try-word" :x="L.rule.left[0] + 24" :y="L.rule.rows[1] + 4">run(b)</text>
          </g>
        </g>
        <g class="rule-bad">
          <circle :cx="L.rule.left[0] + 82" :cy="L.rule.rows[1]" r="7" />
          <path :d="`M${L.rule.left[0] + 79} ${L.rule.rows[1] - 3} l6 6 M${L.rule.left[0] + 85} ${L.rule.rows[1] - 3} l-6 6`" />
          <text class="rule-err" :x="L.rule.left[0] + 93" :y="L.rule.rows[1] + 4">SessionError</text>
          <text class="rule-foot" :x="L.rule.left[0]" :y="L.rule.foot">not queued, not interleaved</text>
        </g>
        <g v-for="(n, i) in ['s1', 's2']" :key="n" class="rule-row">
          <text class="rule-s" :x="L.rule.right[0]" :y="L.rule.rows[i] + 4">{{ n }}</text>
          <rect class="rbar rbar-b" :x="L.rule.right[0] + 22" :y="L.rule.rows[i] - 7" :width="L.rule.right[1] - L.rule.right[0] - 22" height="14" rx="7" />
          <text class="rbar-word" :x="L.rule.right[0] + 30" :y="L.rule.rows[i] + 4">run({{ i ? 'b' : 'a' }})</text>
        </g>
        <g class="rule-ok"><text :x="L.rule.right[0]" :y="L.rule.foot">both go at once</text></g>
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
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

.code-line .str {
  fill: var(--hmz-lane-4);
}

.caret {
  fill: var(--hmz-lane-1);
}

.head {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.agent-pill {
  fill: var(--hmz-lane-1);
}

.agent-name {
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.agent-says {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.sem-name {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent-2);
}

.slot {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent-2);
  stroke-width: 1.3;
}

.slot-n {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.who text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.who.free text {
  font-weight: 400;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.lane-name text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.lane {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
  stroke-dasharray: 2 5;
}

.wait {
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.6;
  stroke-dasharray: 4 4;
}

.playhead {
  stroke: var(--hmz-accent-2);
  stroke-width: 1.4;
  stroke-opacity: 0.7;
}

.bar {
  fill: var(--hmz-lane-1);
  fill-opacity: 0.85;
}

.bar.bad {
  fill: var(--vp-c-danger-1);
  fill-opacity: 0.7;
}

.spawn {
  fill: var(--hmz-lane-1);
  stroke: var(--vp-c-bg);
  stroke-width: 2;
}

.end-ok circle {
  fill: var(--hmz-accent);
}

.end-ok path,
.end-bad path,
.rule-bad path {
  fill: none;
  stroke: #fff;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.end-bad circle,
.rule-bad circle {
  fill: var(--vp-c-danger-1);
}

.fail-word,
.rule-err {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-danger-1);
}

.said-name {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.cell rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.3;
}

.cell text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.cell.bad rect {
  stroke: var(--vp-c-danger-1);
}

.cell.bad text {
  fill: var(--vp-c-danger-1);
}

.printed text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-warm);
}

.dict text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.rule-sub {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.rule-s {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-dim);
}

.rbar {
  fill: var(--hmz-lane-1);
}

.rbar-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.rbar-try {
  fill: none;
  stroke: var(--vp-c-danger-1);
  stroke-width: 1.4;
  stroke-dasharray: 3 2;
}

.rbar-try-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-danger-1);
}

.rule-foot {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.rule-ok text {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
}
</style>
