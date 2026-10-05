<script setup lang="ts">
// What a weaver writes, played out: a flow is Python that drives agents. Left, the flow's own
// code, with a caret on the line that is running. Right, a lane per role, and under them the
// directory the turns work in. `spawn` opens a session, which is only a history; `run` takes a
// turn of it, in an environment -- the run's own workspace when none is given (`env=None`); the
// flow branches on what a turn answers, and returns when it decides to. The API is
// `Agent.spawn` and `Agent.run` in src/hmz/flows/agents.py. The loop is the shape of
// `reviewed` on Answers in a shape; the CLIs filling the roles are only examples.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { createFx, type Fx } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'A flow is Python that drives agents',
  'spawn opens a session: a history, nothing more',
  'run takes a turn, in the run’s workspace',
  'It branches on what a turn answers',
  'And decides when to stop',
]

// One token of a line of code: a class for its colour, and its text.
type Tok = [cls: '' | 'kw' | 'fn', text: string]
const CODE: Tok[][] = [
  [['', 'b = '], ['kw', 'await '], ['fn', 'builder.spawn'], ['', '()']],
  [['kw', 'await '], ['fn', 'builder.run'], ['', '(task, session=b)']],
  [['kw', 'for '], ['', '_ '], ['kw', 'in '], ['fn', 'range'], ['', '(params.rounds):']],
  [['', '  r = '], ['kw', 'await '], ['fn', 'reviewer.spawn'], ['', '()']],
  [['', '  v = '], ['kw', 'await '], ['fn', 'reviewer.run'], ['', '(ASK,']],
  [['', '      session=r, output_schema=Verdict)']],
  [['kw', '  if '], ['', 'v.done: '], ['kw', 'return '], ['', 'v']],
  [['kw', '  await '], ['fn', 'builder.run'], ['', '(v.notes, session=b)']],
]

// Where each turn sits along the lanes, as fractions of the time axis.
const SPAN = {
  t1: [0.02, 0.27],
  r1: [0.31, 0.47],
  t2: [0.51, 0.73],
  r2: [0.77, 0.92],
  end: 0.985,
} as const

interface Layout {
  w: number
  h: number
  /** The code card: its top-left corner and width. */
  code: { x: number; y: number; w: number }
  /** The lanes: where they run from and to, and the height of each row. */
  x0: number
  x1: number
  yB: number
  yR: number
  yE: number
  /** Where the camera starts, and where it settles. */
  open: { x: number; y: number; s: number }
  whole: { x: number; y: number; s: number }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  code: { x: 14, y: 70, w: 278 },
  x0: 316,
  x1: 626,
  yB: 132,
  yR: 214,
  yE: 278,
  open: { x: 156, y: 160, s: 1.32 },
  whole: { x: 320, y: 180, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 600,
  code: { x: 26, y: 56, w: 308 },
  x0: 26,
  x1: 338,
  yB: 340,
  yR: 424,
  yE: 516,
  open: { x: 180, y: 150, s: 1.18 },
  whole: { x: 180, y: 300, s: 1 },
}

const LINE = 19
/** The lanes' names sit in a gutter at their left; time runs from past it. */
const GUTTER = 76

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

/** Where a fraction of the time axis is. */
const X = (f: number) => L.value.x0 + GUTTER + f * (L.value.x1 - L.value.x0 - GUTTER)
/** The baseline of a line of code, and where its right end is drawn to. */
const lineY = (i: number) => L.value.code.y + 34 + i * LINE
const codeOut = (i: number) => ({ x: L.value.code.x + L.value.code.w - 6, y: lineY(i) - 4 })
const mid = (span: readonly [number, number]) => (X(span[0]) + X(span[1])) / 2

const memory = computed(() => {
  const a = X(SPAN.t1[1])
  const b = X(SPAN.t2[0])
  const y = L.value.yB - 11
  return `M${a - 4} ${y} C${a + 14} ${y - 34} ${b - 14} ${y - 34} ${b + 4} ${y}`
})

const out = computed(() => {
  const x = X(SPAN.r2[1])
  const y = L.value.yR
  const e = X(SPAN.end)
  return `M${x + 2} ${y} C${x + 12} ${y} ${e - 4} ${y + 4} ${e} ${y + 22}`
})

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

    // The caret on the running line.
    const caret = one('.caret')
    const pc = (i: number, when: number, tone = 'var(--hmz-lane-1)') => {
      tl.to(caret, { attr: { y: lineY(i) - 13 }, duration: 0.45, ease: 'cine' }, when)
      tl.to(caret, { fill: tone, duration: 0.3, ease: 'none' }, when)
      tl.fromTo(at('.code-line')[i], { opacity: 0.55 }, { opacity: 1, duration: 0.3 }, when + 0.1)
    }
    const turn = (sel: string, when: number, dur: number) => {
      tl.fromTo(one(sel), { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: dur, ease: 'power1.inOut' }, when)
      tl.fromTo(one(`${sel}-word`), { opacity: 0 }, { opacity: 1, duration: 0.4 }, when + dur * 0.4)
    }
    const drop = (i: number, when: number) => {
      tl.fromTo(at('.drop')[i], { drawSVG: '0%', opacity: 1 }, { drawSVG: '100%', duration: 0.45, ease: 'power2.in' }, when)
      tl.fromTo(at('.mark')[i], { opacity: 0, scale: 0, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.45, ease: 'back.out(2.4)' }, when + 0.42)
    }
    const flare = (x: number, y: number, color: () => string, when: number, n = 18) => cam.flare({ x, y }, color, when, n, 90)
    const lane1 = () => palette.lane[0]
    const lane3 = () => palette.lane[2]
    const ok = () => palette.accent
    const warm = () => palette.warm

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.code-line'), { opacity: 0 }, 0)
    tl.set(at('.role, .env, .turn-word, .verdict, .note, .mark, .fresh, .ret-word, .closed'), { opacity: 0 }, 0)
    tl.set(at('.drop, .memory, .ret'), { drawSVG: '0%' }, 0)
    tl.set(at('.thread-b'), { drawSVG: '0% 0%' }, 0)
    tl.set(caret, { opacity: 0, attr: { y: lineY(0) - 13 } }, 0)

    // 0 · the code, line by line, and the roles it names, filled by whoever runs it.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.card'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.7 }, 0.1)
    tl.fromTo(at('.code-line'), { opacity: 0, x: -10 }, { opacity: 0.55, x: 0, duration: 0.5, stagger: 0.13 }, 0.35)
    tl.fromTo(at('.lane'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.2, ease: 'cine', stagger: 0.15 }, 1.2)
    tl.fromTo(at('.role'), { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.6, stagger: 0.18 }, 1.5)
    tl.fromTo(one('.env-box'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.1, ease: 'cine' }, 1.7)
    tl.to(at('.env'), { opacity: 1, duration: 0.6 }, 2.2)
    tl.set(at('.env-none'), { opacity: 0 }, 2.2)
    cam.shot(l.whole, 1.9, 1.9)

    // 1 · spawn: a session opens on the builder's lane, with nothing in it yet.
    const T1 = 3.4
    tl.addLabel('beat-1', T1)
    tl.to(caret, { opacity: 1, duration: 0.3 }, T1)
    pc(0, T1)
    cam.beam(codeOut(0), { x: X(SPAN.t1[0]), y: l.yB }, lane1, T1 + 0.3, { duration: 0.8, bend: -0.18 })
    flare(X(SPAN.t1[0]), l.yB, lane1, T1 + 1.1, 22)
    tl.fromTo(one('.spark-b'), { scale: 0, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.5, ease: 'back.out(3)' }, T1 + 1.1)
    tl.to(one('.fresh-b'), { opacity: 1, duration: 0.4 }, T1 + 1.2)

    // 2 · run: the task goes down the lane as a turn, which works in the workspace and answers.
    const T2 = T1 + 2.2
    tl.addLabel('beat-2', T2)
    pc(1, T2)
    tl.to(one('.fresh-b'), { opacity: 0, duration: 0.3 }, T2)
    cam.beam(codeOut(1), { x: X(SPAN.t1[0]), y: l.yB }, lane1, T2 + 0.2, { duration: 0.7, bend: -0.16 })
    turn('.turn-t1', T2 + 0.8, 1.6)
    tl.to(one('.thread-b'), { drawSVG: '0% 36%', duration: 1.6, ease: 'power1.inOut' }, T2 + 0.8)
    drop(0, T2 + 1.3)
    tl.to(at('.env-none'), { opacity: 1, duration: 0.4 }, T2 + 1.5)
    tl.fromTo(at('.env-none'), { scale: 1.12, transformOrigin: '0% 50%' }, { scale: 1, duration: 0.6, ease: 'back.out(2)' }, T2 + 1.5)
    cam.beam({ x: X(SPAN.t1[1]), y: l.yB }, codeOut(1), ok, T2 + 2.5, { duration: 0.8, bend: 0.2 })

    // 3 · the reviewer, in a new session of its own, answers in a shape; the flow reads it and
    //     sends the notes back to the builder, whose session remembers its first turn.
    const T3 = T2 + 3.6
    tl.addLabel('beat-3', T3)
    pc(2, T3)
    pc(3, T3 + 0.5)
    cam.beam(codeOut(3), { x: X(SPAN.r1[0]), y: l.yR }, lane3, T3 + 0.8, { duration: 0.7, bend: -0.12 })
    flare(X(SPAN.r1[0]), l.yR, lane3, T3 + 1.5, 18)
    tl.fromTo(one('.spark-r1'), { scale: 0, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.5, ease: 'back.out(3)' }, T3 + 1.5)
    tl.to(one('.fresh-r'), { opacity: 1, duration: 0.4 }, T3 + 1.5)
    pc(4, T3 + 1.7)
    turn('.turn-r1', T3 + 2, 1.1)
    tl.to(one('.thread-b'), { drawSVG: '0% 62%', duration: 2.6, ease: 'none' }, T3 + 0.4)
    drop(1, T3 + 2.3)
    tl.fromTo(one('.verdict-no'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5, ease: 'back.out(2)' }, T3 + 3.1)
    cam.beam({ x: X(SPAN.r1[1]), y: l.yR }, codeOut(6), warm, T3 + 3.4, { duration: 0.8, bend: 0.2 })
    pc(6, T3 + 4.1, 'var(--hmz-warm)')
    tl.to(one('.fresh-r'), { opacity: 0, duration: 0.3 }, T3 + 4.1)
    pc(7, T3 + 4.8)
    cam.beam(codeOut(7), { x: X(SPAN.t2[0]), y: l.yB }, lane1, T3 + 5, { duration: 0.8, bend: -0.2 })
    tl.to(one('.memory'), { drawSVG: '100%', duration: 1.1, ease: 'cine' }, T3 + 5.3)
    tl.to(one('.note-mem'), { opacity: 1, duration: 0.5 }, T3 + 5.8)
    turn('.turn-t2', T3 + 5.8, 1.6)
    tl.to(one('.thread-b'), { drawSVG: '0% 100%', duration: 1.6, ease: 'power1.inOut' }, T3 + 5.8)
    drop(2, T3 + 6.3)

    // 4 · round two: a new reviewer session, `done` this time, and the flow returns.
    const T4 = T3 + 8
    tl.addLabel('beat-4', T4)
    tl.to(one('.note-mem'), { opacity: 0.55, duration: 0.5 }, T4)
    pc(3, T4)
    cam.beam(codeOut(3), { x: X(SPAN.r2[0]), y: l.yR }, lane3, T4 + 0.3, { duration: 0.7, bend: -0.1 })
    flare(X(SPAN.r2[0]), l.yR, lane3, T4 + 1, 18)
    tl.fromTo(one('.spark-r2'), { scale: 0, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.5, ease: 'back.out(3)' }, T4 + 1)
    pc(4, T4 + 1.1)
    turn('.turn-r2', T4 + 1.3, 1)
    drop(3, T4 + 1.5)
    tl.fromTo(one('.verdict-ok'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5, ease: 'back.out(2)' }, T4 + 2.3)
    cam.beam({ x: X(SPAN.r2[1]), y: l.yR }, codeOut(6), ok, T4 + 2.6, { duration: 0.8, bend: 0.2 })
    pc(6, T4 + 3.3, 'var(--hmz-accent)')
    tl.to(one('.ret'), { drawSVG: '100%', duration: 0.8, ease: 'cine' }, T4 + 3.5)
    tl.to(one('.ret-word'), { opacity: 1, duration: 0.4 }, T4 + 4.1)
    flare(X(SPAN.end), l.yR + 22, ok, T4 + 4.2, 28)
    tl.to(at('.closed'), { opacity: 1, duration: 0.5, stagger: 0.1 }, T4 + 4.4)
    tl.to(caret, { opacity: 0.35, duration: 0.6 }, T4 + 4.6)

    tl.addLabel('rest', T4 + 5.2)
    // A breath of drift while it rests, then fade for the loop.
    cam.shot({ ...l.whole, s: l.whole.s * 1.03 }, T4 + 4.4, 3.2, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 7.6)

  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="3 / 5"
    label="A flow is Python that drives agents. The flow's code runs line by line: builder.spawn opens a session, which is only a history; builder.run sends the task as a turn, which works in the run's workspace since no env is given; a reviewer, in a new session each round, answers in a shape; the flow reads done false and sends the notes back to the builder, whose session remembers its first turn; the next review says done, and the flow returns."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <linearGradient id="weaver-loom-env" x1="0" x2="1">
          <stop offset="0" stop-color="var(--hmz-warm)" stop-opacity="0.16" />
          <stop offset="1" stop-color="var(--hmz-warm)" stop-opacity="0.04" />
        </linearGradient>
      </defs>
      <g class="world">
        <!-- the flow's code; each line in a group, so the stage may lift its words alone -->
        <g class="card">
          <rect class="card-box" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="34 + CODE.length * LINE" rx="10" />
          <text class="card-head" :x="L.code.x + 12" :y="L.code.y + 18">@flow · async def reviewed(task, …)</text>
          <rect class="caret" :x="L.code.x + 4" :y="lineY(0) - 13" width="3" height="16" rx="1.5" />
          <g v-for="(line, i) in CODE" :key="i" class="code-line">
            <text :x="L.code.x + 14" :y="lineY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>

        <!-- a lane per role, named in its gutter with what fills it -->
        <g class="role">
          <text class="role-name" :x="L.x0" :y="L.yB - 2">builder</text>
          <text class="role-fill" :x="L.x0" :y="L.yB + 13">claude/…</text>
        </g>
        <g class="role">
          <text class="role-name" :x="L.x0" :y="L.yR - 2">reviewer</text>
          <text class="role-fill" :x="L.x0" :y="L.yR + 13">codex/…</text>
        </g>
        <line class="lane" :x1="L.x0 + GUTTER - 6" :x2="L.x1" :y1="L.yB" :y2="L.yB" />
        <line class="lane" :x1="L.x0 + GUTTER - 6" :x2="L.x1" :y1="L.yR" :y2="L.yR" />

        <!-- the builder's one session: a thread that runs on while the reviewer works -->
        <line class="thread-b" :x1="X(SPAN.t1[0])" :x2="X(SPAN.t2[1])" :y1="L.yB" :y2="L.yB" />
        <circle class="spark spark-b" :cx="X(SPAN.t1[0])" :cy="L.yB" r="6" />
        <text class="fresh fresh-b" :x="X(SPAN.t1[0]) + 10" :y="L.yB + 22">session b · no turns yet</text>
        <path class="memory" :d="memory" />
        <text class="note note-mem" :x="(X(SPAN.t1[1]) + X(SPAN.t2[0])) / 2" :y="L.yB - 40" text-anchor="middle">same session: remembers</text>

        <!-- turns -->
        <rect class="turn turn-b turn-t1" :x="X(SPAN.t1[0])" :y="L.yB - 9" :width="X(SPAN.t1[1]) - X(SPAN.t1[0])" height="18" rx="9" />
        <text class="turn-word turn-t1-word" :x="mid(SPAN.t1)" :y="L.yB + 4" text-anchor="middle">task</text>
        <rect class="turn turn-b turn-t2" :x="X(SPAN.t2[0])" :y="L.yB - 9" :width="X(SPAN.t2[1]) - X(SPAN.t2[0])" height="18" rx="9" />
        <text class="turn-word turn-t2-word" :x="mid(SPAN.t2)" :y="L.yB + 4" text-anchor="middle">notes</text>

        <circle class="spark spark-r spark-r1" :cx="X(SPAN.r1[0])" :cy="L.yR" r="5" />
        <circle class="spark spark-r spark-r2" :cx="X(SPAN.r2[0])" :cy="L.yR" r="5" />
        <text class="fresh fresh-r" :x="X(SPAN.r1[0])" :y="L.yR + 24">a new session each round</text>
        <rect class="turn turn-r turn-r1" :x="X(SPAN.r1[0])" :y="L.yR - 9" :width="X(SPAN.r1[1]) - X(SPAN.r1[0])" height="18" rx="9" />
        <text class="turn-word turn-r1-word" :x="mid(SPAN.r1)" :y="L.yR + 4" text-anchor="middle">ASK</text>
        <rect class="turn turn-r turn-r2" :x="X(SPAN.r2[0])" :y="L.yR - 9" :width="X(SPAN.r2[1]) - X(SPAN.r2[0])" height="18" rx="9" />
        <text class="turn-word turn-r2-word" :x="mid(SPAN.r2)" :y="L.yR + 4" text-anchor="middle">ASK</text>

        <g class="verdict verdict-no">
          <rect :x="mid(SPAN.r1) - 38" :y="L.yR - 38" width="76" height="20" rx="5" />
          <text :x="mid(SPAN.r1)" :y="L.yR - 24" text-anchor="middle">done=False</text>
        </g>
        <g class="verdict verdict-ok">
          <rect :x="mid(SPAN.r2) - 38" :y="L.yR - 38" width="76" height="20" rx="5" />
          <text :x="mid(SPAN.r2)" :y="L.yR - 24" text-anchor="middle">done=True</text>
        </g>

        <path class="ret" :d="out" />
        <text class="ret-word" :x="X(SPAN.end)" :y="L.yR + 38" text-anchor="end">return v</text>
        <text class="closed" :x="X(SPAN.t2[1]) + 6" :y="L.yB + 4">┤ closed</text>

        <!-- where the turns work -->
        <g class="env">
          <rect class="env-fill" :x="L.x0" :y="L.yE - 20" :width="L.x1 - L.x0" height="40" rx="8" fill="url(#weaver-loom-env)" />
          <text class="env-name" :x="L.x0 + 2" :y="L.yE + 38">workspace · LocalEnv</text>
          <g class="env-none"><text :x="L.x0 + 2" :y="L.yE + 55">no env= given: the run’s own workspace</text></g>
        </g>
        <rect class="env-box" :x="L.x0" :y="L.yE - 20" :width="L.x1 - L.x0" height="40" rx="8" />
        <line class="drop" :x1="mid(SPAN.t1)" :x2="mid(SPAN.t1)" :y1="L.yB + 10" :y2="L.yE - 8" />
        <line class="drop" :x1="mid(SPAN.r1)" :x2="mid(SPAN.r1)" :y1="L.yR + 10" :y2="L.yE - 8" />
        <line class="drop" :x1="mid(SPAN.t2)" :x2="mid(SPAN.t2)" :y1="L.yB + 10" :y2="L.yE - 8" />
        <line class="drop" :x1="mid(SPAN.r2)" :x2="mid(SPAN.r2)" :y1="L.yR + 10" :y2="L.yE - 8" />
        <g class="mark mark-edit"><rect :x="mid(SPAN.t1) - 18" :y="L.yE - 8" width="36" height="16" rx="3" /><text :x="mid(SPAN.t1)" :y="L.yE + 4" text-anchor="middle">edit</text></g>
        <g class="mark mark-read"><rect :x="mid(SPAN.r1) - 18" :y="L.yE - 8" width="36" height="16" rx="3" /><text :x="mid(SPAN.r1)" :y="L.yE + 4" text-anchor="middle">read</text></g>
        <g class="mark mark-edit"><rect :x="mid(SPAN.t2) - 18" :y="L.yE - 8" width="36" height="16" rx="3" /><text :x="mid(SPAN.t2)" :y="L.yE + 4" text-anchor="middle">edit</text></g>
        <g class="mark mark-read"><rect :x="mid(SPAN.r2) - 18" :y="L.yE - 8" width="36" height="16" rx="3" /><text :x="mid(SPAN.r2)" :y="L.yE + 4" text-anchor="middle">read</text></g>
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

.caret {
  fill: var(--hmz-lane-1);
}

.role-name {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.role-fill {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.lane {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
  stroke-dasharray: 2 5;
}

.thread-b {
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
  stroke-opacity: 0.55;
  stroke-dasharray: 6 4;
}

.spark {
  stroke: var(--vp-c-bg);
  stroke-width: 2;
}

.spark-b {
  fill: var(--hmz-lane-1);
}

.spark-r {
  fill: var(--hmz-lane-3);
}

.fresh,
.note {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.memory {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.5;
  stroke-dasharray: 3 3;
}

.turn-b {
  fill: var(--hmz-lane-1);
}

.turn-r {
  fill: var(--hmz-lane-3);
}

.turn-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.verdict rect {
  fill: var(--hmz-stage-card);
  stroke-width: 1.4;
}

.verdict text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
}

.verdict-no rect {
  stroke: var(--hmz-warm);
}

.verdict-no text {
  fill: var(--hmz-warm);
}

.verdict-ok rect {
  stroke: var(--hmz-accent);
}

.verdict-ok text {
  fill: var(--hmz-accent);
}

.ret {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  stroke-linecap: round;
}

.ret-word {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.closed {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.env-box {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-opacity: 0.7;
  stroke-width: 1.3;
}

.env-name {
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-warm);
}

.env-none text {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.drop {
  stroke: var(--hmz-stage-dim);
  stroke-opacity: 0.6;
  stroke-width: 1.2;
  stroke-dasharray: 2 3;
}

.mark rect {
  stroke-width: 1.2;
}

.mark text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
}

.mark-edit rect {
  fill: var(--hmz-lane-1);
  stroke: var(--hmz-lane-1);
}

.mark-edit text {
  fill: #fff;
}

.mark-read rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-3);
}

.mark-read text {
  fill: var(--hmz-lane-3);
}
</style>
