<script setup lang="ts">
// `twice`, from "Your first flow", played out. Left, the flow's code with a caret on the line
// that is running. Right, the three things `@flow` declares -- the agents by role, the
// environments, the params -- each filled when the flow runs: the role by whoever runs it
// (`-a builder=CLI/MODEL:EFFORT`), the `LocalEnv` by the runtime (the directory the run was
// started in), the params by `-p` or, as here with plain `FlowParams`, their defaults. Under
// them the session `spawn` opens: only a history, empty until `run` takes a turn of it. A turn
// gives no `env=`, so it works in the run's workspace (`env=None`), and `run` returns the
// answer as a string. The second `run` is in the same session, so it remembers the first; a
// new `spawn` would have been a stranger. The flow returns and every session it opened is
// closed. Drawn from docs/weaver/writing-a-flow.md and `Agent.spawn` / `Agent.run` in
// src/hmz/flows/agents.py; the answer is the page's real run, abridged.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { createFx, type Fx } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  '@flow declares agents, envs and params',
  'Whoever runs it fills each one',
  'spawn opens a session: an empty history',
  'run takes turn 1 in the workspace',
  'The second run remembers turn 1',
  'It returns, and its sessions close',
]

type Tok = [cls: '' | 'kw' | 'fn' | 'str' | 'dim' | 'deco', text: string]
const CODE: Tok[][] = [
  [['deco', '@flow'], ['', '(agents=Agents, envs=Envs,']],
  [['', '      params=FlowParams)']],
  [['kw', 'async def '], ['fn', 'twice'], ['', '(task, *, agents, …):']],
  [['', '  builder = agents['], ['str', '"builder"'], ['', ']']],
  [['', '  s = '], ['kw', 'await '], ['fn', 'builder.spawn'], ['', '()']],
  [['kw', '  await '], ['fn', 'builder.run'], ['', '(task, session=s)']],
  [['kw', '  await '], ['fn', 'builder.run'], ['', '(REVIEW, session=s)']],
  [['dim', '  # returns: its sessions close']],
]

interface Slot {
  decl: string
  fill: string
  cap: string
  tone: string
}
const SLOTS: Slot[] = [
  { decl: 'builder: Agent', fill: 'claude/…:high', cap: 'whoever runs it · -a builder=CLI/MODEL:EFFORT', tone: 'var(--hmz-lane-1)' },
  { decl: 'workspace: LocalEnv', fill: 'the run’s dir', cap: 'the runtime · where the run was started', tone: 'var(--hmz-warm)' },
  { decl: 'params: FlowParams', fill: 'FlowParams()', cap: '-p KEY=VALUE · none of its own: defaults', tone: 'var(--hmz-lane-3)' },
]

interface Layout {
  w: number
  h: number
  code: { x: number; y: number; w: number }
  /** The right-hand column: the slots, the session and the workspace. */
  x0: number
  x1: number
  slotY: number
  ribbonY: number
  wsY: number
  answerY: number
  ghostY: number
  open: { x: number; y: number; s: number }
  whole: { x: number; y: number; s: number }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  code: { x: 14, y: 40, w: 286 },
  x0: 318,
  x1: 626,
  slotY: 52,
  ribbonY: 228,
  wsY: 282,
  answerY: 246,
  ghostY: 292,
  open: { x: 160, y: 134, s: 1.34 },
  whole: { x: 320, y: 180, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 640,
  code: { x: 14, y: 14, w: 332 },
  x0: 14,
  x1: 346,
  slotY: 222,
  ribbonY: 404,
  wsY: 462,
  answerY: 550,
  ghostY: 588,
  open: { x: 180, y: 110, s: 1.2 },
  whole: { x: 180, y: 320, s: 1 },
}

const LINE = 19
const ROW = 46
const DECL_W = 144

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const lineY = (i: number) => L.value.code.y + 34 + i * LINE
const codeOut = (i: number) => ({ x: L.value.code.x + L.value.code.w - 8, y: lineY(i) - 4 })
const rowY = (i: number) => L.value.slotY + 12 + i * ROW
const fillX = computed(() => L.value.x0 + DECL_W + 34)
/** The two turns along the ribbon. */
const T1 = computed(() => ({ x: L.value.x0 + 8, w: 128 }))
const T2 = computed(() => ({ x: L.value.x0 + 144, w: L.value.x1 - L.value.x0 - 152 }))
const mid = (t: { x: number; w: number }) => t.x + t.w / 2

const memory = computed(() => {
  const a = mid(T1.value)
  const b = mid(T2.value)
  const y = L.value.ribbonY - 2
  return `M${a} ${y} C${a + 20} ${y - 26} ${b - 20} ${y - 26} ${b} ${y}`
})

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
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), fx: () => fx, start: l.open })
    const lane1 = () => palette.lane[0]
    const lane3 = () => palette.lane[2]
    const warm = () => palette.warm
    const ok = () => palette.accent
    const tones = [lane1, warm, lane3]

    const caret = one('.caret')
    const pc = (i: number, when: number, tone = 'var(--hmz-lane-1)') => {
      tl.to(caret, { attr: { y: lineY(i) - 13 }, duration: 0.45, ease: 'cine' }, when)
      tl.to(caret, { fill: tone, duration: 0.3, ease: 'none' }, when)
      tl.fromTo(at('.code-line')[i], { opacity: 0.5 }, { opacity: 1, duration: 0.3 }, when + 0.1)
    }

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.code-line'), { opacity: 0 }, 0)
    tl.set(at('.ribbon-box, .slot-head, .slot-decl, .slot-fill, .slot-cap, .ribbon-label, .empty, .turn-word, .mem-word, .mark, .ws-text, .answer, .ghost, .closed, .spark'), { opacity: 0 }, 0)
    tl.set(at('.slot-arrow, .ws-box, .drop, .memory'), { drawSVG: '0%' }, 0)
    tl.set(at('.turn'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(caret, { opacity: 0, attr: { y: lineY(0) - 13 } }, 0)

    // 0 · the code, and the three slots its decorator declares, empty.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.card'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.7 }, 0.1)
    tl.fromTo(at('.code-line'), { opacity: 0, x: -10 }, { opacity: 0.5, x: 0, duration: 0.5, stagger: 0.12 }, 0.35)
    tl.to(caret, { opacity: 1, duration: 0.3 }, 1.3)
    pc(0, 1.3, 'var(--hmz-accent)')
    tl.to(at('.slot-head'), { opacity: 1, duration: 0.5 }, 1.6)
    cam.shot(l.whole, 1.5, 2)
    SLOTS.forEach((_, i) => {
      const t = 2 + i * 0.4
      cam.beam(codeOut(i < 2 ? 0 : 1), { x: l.x0 + 4, y: rowY(i) }, tones[i], t, { duration: 0.7, bend: -0.15 })
      tl.fromTo(at('.slot-decl')[i], { opacity: 0 }, { opacity: 1, duration: 0.4 }, t + 0.55)
      tl.fromTo(at('.slot-decl-in')[i], { x: -10 }, { x: 0, duration: 0.5 }, t + 0.55)
    })
    pc(1, 2.8, 'var(--hmz-accent)')

    // 1 · filled: the role by -a, the LocalEnv by the runtime, the params by their defaults.
    const B1 = 4.2
    tl.addLabel('beat-1', B1)
    SLOTS.forEach((_, i) => {
      const t = B1 + 0.2 + i * 0.9
      tl.to(at('.slot-arrow')[i], { drawSVG: '100%', duration: 0.45, ease: 'cine' }, t)
      tl.to(at('.slot-fill')[i], { opacity: 1, duration: 0.4 }, t + 0.3)
      tl.fromTo(at('.slot-fill-in')[i], { x: 34 }, { x: 0, duration: 0.6, ease: 'cine.out' }, t + 0.3)
      cam.flare({ x: fillX.value + 8, y: rowY(i) }, tones[i], t + 0.5, 16, 70)
      tl.to(at('.slot-cap')[i], { opacity: 1, duration: 0.5 }, t + 0.6)
    })
    // The workspace the LocalEnv names, drawn where the turns will work.
    cam.beam({ x: l.x1 - 30, y: rowY(1) }, { x: l.x1 - 30, y: l.wsY }, warm, B1 + 1.6, { duration: 0.9, bend: 0.12 })
    tl.to(one('.ws-box'), { drawSVG: '100%', duration: 1, ease: 'cine' }, B1 + 2.2)
    tl.to(one('.ws-name'), { opacity: 1, duration: 0.5 }, B1 + 2.6)

    // 2 · spawn: a session opens, with no turns in it.
    const B2 = B1 + 3.8
    tl.addLabel('beat-2', B2)
    pc(3, B2)
    cam.beam({ x: fillX.value + 40, y: rowY(0) }, codeOut(3), lane1, B2 + 0.1, { duration: 0.6, bend: 0.12 })
    pc(4, B2 + 0.9)
    cam.beam(codeOut(4), { x: l.x0 + 6, y: l.ribbonY + 14 }, lane1, B2 + 1.2, { duration: 0.8, bend: -0.2 })
    tl.to(one('.spark'), { opacity: 1, duration: 0.2 }, B2 + 2)
    tl.fromTo(one('.spark'), { scale: 0, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.5, ease: 'back.out(3)' }, B2 + 2)
    cam.flare({ x: l.x0 + 6, y: l.ribbonY + 14 }, lane1, B2 + 2, 22, 90)
    tl.to(one('.ribbon-box'), { opacity: 1, duration: 0.3 }, B2 + 2)
    tl.fromTo(one('.ribbon-box'), { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 1, ease: 'cine' }, B2 + 2)
    tl.to(one('.ribbon-label'), { opacity: 1, duration: 0.5 }, B2 + 2.3)
    tl.to(one('.empty'), { opacity: 1, duration: 0.5 }, B2 + 2.6)

    // 3 · run: turn 1 enters the history, works in the workspace, and answers with a string.
    const B3 = B2 + 3.8
    tl.addLabel('beat-3', B3)
    pc(5, B3)
    tl.to(one('.empty'), { opacity: 0, duration: 0.3 }, B3 + 0.3)
    cam.beam(codeOut(5), { x: T1.value.x, y: l.ribbonY + 14 }, lane1, B3 + 0.2, { duration: 0.8, bend: -0.2 })
    tl.to(at('.turn')[0], { scaleX: 1, duration: 1.1, ease: 'power1.inOut' }, B3 + 0.9)
    tl.to(at('.turn-word')[0], { opacity: 1, duration: 0.4 }, B3 + 1.3)
    tl.to(at('.drop')[0], { drawSVG: '100%', duration: 0.5, ease: 'power2.in' }, B3 + 1.4)
    tl.fromTo(at('.mark')[0], { opacity: 0, scale: 0, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.45, ease: 'back.out(2.4)' }, B3 + 1.85)
    tl.to(one('.ws-none'), { opacity: 1, duration: 0.5 }, B3 + 1.9)
    tl.fromTo(one('.ws-none-in'), { x: -8 }, { x: 0, duration: 0.6 }, B3 + 1.9)
    cam.beam({ x: mid(T1.value), y: l.ribbonY }, codeOut(5), ok, B3 + 2.6, { duration: 0.8, bend: 0.2 })
    cam.beam(codeOut(5), { x: l.code.x + 30, y: l.answerY + 10 }, ok, B3 + 3.3, { duration: 0.6, bend: 0.2, burst: 14 })
    tl.to(one('.answer'), { opacity: 1, duration: 0.5 }, B3 + 3.8)
    tl.fromTo(one('.answer-in'), { y: 6 }, { y: 0, duration: 0.6, ease: 'back.out(2)' }, B3 + 3.8)

    // 4 · the second run, same session: it remembers turn 1. A new spawn would be a stranger.
    const B4 = B3 + 5
    tl.addLabel('beat-4', B4)
    pc(6, B4)
    cam.beam(codeOut(6), { x: T2.value.x, y: l.ribbonY + 14 }, lane1, B4 + 0.2, { duration: 0.8, bend: -0.2 })
    tl.to(one('.memory'), { drawSVG: '100%', duration: 0.9, ease: 'cine' }, B4 + 0.9)
    tl.to(one('.mem-word'), { opacity: 1, duration: 0.5 }, B4 + 1.3)
    tl.to(at('.turn')[1], { scaleX: 1, duration: 1.2, ease: 'power1.inOut' }, B4 + 1.1)
    tl.to(at('.turn-word')[1], { opacity: 1, duration: 0.4 }, B4 + 1.5)
    tl.to(at('.drop')[1], { drawSVG: '100%', duration: 0.5, ease: 'power2.in' }, B4 + 1.7)
    tl.fromTo(at('.mark')[1], { opacity: 0, scale: 0, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.45, ease: 'back.out(2.4)' }, B4 + 2.15)
    tl.to(one('.ghost'), { opacity: 1, duration: 0.6 }, B4 + 2.8)
    tl.fromTo(one('.ghost-in'), { x: 14 }, { x: 0, duration: 0.8, ease: 'cine.out' }, B4 + 2.8)
    tl.to(one('.ghost'), { opacity: 0.7, duration: 0.6 }, B4 + 4.4)

    // 5 · it returns, and the session closes.
    const B5 = B4 + 5.2
    tl.addLabel('beat-5', B5)
    pc(7, B5, 'var(--hmz-accent)')
    tl.to(one('.ribbon-label'), { opacity: 0, duration: 0.4 }, B5 + 0.6)
    tl.to(one('.closed'), { opacity: 1, duration: 0.5 }, B5 + 0.9)
    cam.flare({ x: l.x1 - 4, y: l.ribbonY + 14 }, ok, B5 + 0.8, 26, 100)
    tl.to(at('.turn, .ribbon-box'), { opacity: 0.75, duration: 0.8 }, B5 + 1)
    tl.to(one('.spark'), { opacity: 0.4, duration: 0.8 }, B5 + 1)
    tl.to(caret, { opacity: 0.35, duration: 0.6 }, B5 + 1.4)

    tl.addLabel('rest', B5 + 2.4)
    cam.shot({ ...l.whole, s: 1.02 }, B5 + 2, 3, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, B5 + 5)

    tl.fromTo(at('.hum'), { strokeDashoffset: 0 }, { strokeDashoffset: -140, duration: tl.duration(), ease: 'none' }, 0)
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
    label="The flow twice, played out. Its @flow decorator declares three things: an agent for the role builder, an environment called workspace that is a LocalEnv, and params, here plain FlowParams. When it runs, whoever runs it fills builder with -a builder=CLI/MODEL:EFFORT, the runtime fills the workspace with the directory the run was started in, and the params take their defaults. builder.spawn() opens a session, which is only a conversation history, empty. builder.run(task, session=s) takes turn 1; it gives no env, so it works in the run's workspace, edits calc.py, and returns the agent's answer as a string. The second run, in the same session, remembers turn 1 and reviews it; a new spawn there would have been a stranger with no memory of it. The flow returns and every session it opened closes."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <linearGradient id="first-flow-env" x1="0" x2="1">
          <stop offset="0" stop-color="var(--hmz-warm)" stop-opacity="0.16" />
          <stop offset="1" stop-color="var(--hmz-warm)" stop-opacity="0.04" />
        </linearGradient>
      </defs>
      <g class="world">
        <!-- the flow's code -->
        <g class="card">
          <rect class="card-box" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="30 + CODE.length * LINE" rx="10" />
          <text class="card-head" :x="L.code.x + 12" :y="L.code.y + 17">.hmz/flows/twice/__init__.py</text>
          <rect class="caret" :x="L.code.x + 4" :y="lineY(0) - 13" width="3" height="16" rx="1.5" />
          <g v-for="(line, i) in CODE" :key="i" class="code-line">
            <text :x="L.code.x + 12" :y="lineY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>

        <!-- what it declares, and what fills each when it runs -->
        <text class="slot-head" :x="L.x0" :y="L.slotY - 6">it declares</text>
        <text class="slot-head" :x="fillX" :y="L.slotY - 6">filled when it runs</text>
        <g v-for="(s, i) in SLOTS" :key="s.decl">
          <g class="slot-decl">
            <g class="slot-decl-in">
              <rect class="decl-box" :x="L.x0" :y="rowY(i) - 12" :width="DECL_W" height="24" rx="6" :style="{ stroke: s.tone }" />
              <text class="decl-word" :x="L.x0 + 8" :y="rowY(i) + 4">{{ s.decl }}</text>
            </g>
          </g>
          <path class="slot-arrow" :d="`M${L.x0 + DECL_W + 4} ${rowY(i)} H${fillX - 6} M${fillX - 11} ${rowY(i) - 4} L${fillX - 6} ${rowY(i)} L${fillX - 11} ${rowY(i) + 4}`" :style="{ stroke: s.tone }" />
          <g class="slot-fill">
            <g class="slot-fill-in">
              <rect class="fill-box" :x="fillX" :y="rowY(i) - 12" :width="L.x1 - fillX" height="24" rx="12" :style="{ fill: s.tone }" />
              <text class="fill-word" :x="fillX + (L.x1 - fillX) / 2" :y="rowY(i) + 4" text-anchor="middle">{{ s.fill }}</text>
            </g>
          </g>
          <text class="slot-cap" :x="L.x0 + 2" :y="rowY(i) + 27">{{ s.cap }}</text>
        </g>

        <!-- the session: a history, nothing more -->
        <text class="ribbon-label" :x="L.x0" :y="L.ribbonY - 30">session s · its history</text>
        <text class="closed" :x="L.x0" :y="L.ribbonY - 30">session s · closed</text>
        <path class="memory" :d="memory" />
        <text class="mem-word" :x="L.x1" :y="L.ribbonY - 30" text-anchor="end">turn 2 remembers turn 1</text>
        <rect class="ribbon-box hum" :x="L.x0" :y="L.ribbonY" :width="L.x1 - L.x0" height="28" rx="8" />
        <circle class="spark" :cx="L.x0 + 1" :cy="L.ribbonY + 14" r="5" />
        <text class="empty" :x="(L.x0 + L.x1) / 2" :y="L.ribbonY + 18" text-anchor="middle">no turns yet</text>
        <rect class="turn" :x="T1.x" :y="L.ribbonY + 5" :width="T1.w" height="18" rx="9" />
        <text class="turn-word" :x="mid(T1)" :y="L.ribbonY + 18" text-anchor="middle">1 · task</text>
        <rect class="turn" :x="T2.x" :y="L.ribbonY + 5" :width="T2.w" height="18" rx="9" />
        <text class="turn-word" :x="mid(T2)" :y="L.ribbonY + 18" text-anchor="middle">2 · REVIEW</text>

        <!-- where the turns work -->
        <rect class="ws-fill" :x="L.x0" :y="L.wsY" :width="L.x1 - L.x0" height="34" rx="8" fill="url(#first-flow-env)" />
        <rect class="ws-box" :x="L.x0" :y="L.wsY" :width="L.x1 - L.x0" height="34" rx="8" />
        <text class="ws-text ws-name" :x="L.x0 + 2" :y="L.wsY + 50">workspace · LocalEnv</text>
        <g class="ws-text ws-none"><g class="ws-none-in"><text :x="L.x0 + 2" :y="L.wsY + 66">no env= on run: the run’s own workspace</text></g></g>
        <line class="drop" :x1="mid(T1)" :x2="mid(T1)" :y1="L.ribbonY + 24" :y2="L.wsY + 9" />
        <line class="drop" :x1="mid(T2)" :x2="mid(T2)" :y1="L.ribbonY + 24" :y2="L.wsY + 9" />
        <g class="mark mark-edit"><rect :x="mid(T1) - 46" :y="L.wsY + 9" width="92" height="17" rx="4" /><text :x="mid(T1)" :y="L.wsY + 21" text-anchor="middle">edit calc.py</text></g>
        <g class="mark mark-read"><rect :x="mid(T2) - 46" :y="L.wsY + 9" width="92" height="17" rx="4" /><text :x="mid(T2)" :y="L.wsY + 21" text-anchor="middle">read, run</text></g>

        <!-- what run returned -->
        <g class="answer">
          <g class="answer-in">
            <text class="answer-head" :x="L.code.x + 2" :y="L.answerY">run returned a str</text>
            <rect class="answer-box" :x="L.code.x" :y="L.answerY + 6" :width="L.code.w" height="22" rx="6" />
            <text class="answer-word" :x="L.code.x + 10" :y="L.answerY + 21">"I added `subtract(a, b)` to calc.py…"</text>
          </g>
        </g>

        <!-- the road not taken: a new spawn is a stranger -->
        <g class="ghost">
          <g class="ghost-in">
            <text class="ghost-head" :x="L.code.x + 2" :y="L.ghostY + 10">had it spawned again instead:</text>
            <rect class="ghost-box" :x="L.code.x" :y="L.ghostY + 18" :width="L.code.w" height="26" rx="8" />
            <circle class="ghost-dot" :cx="L.code.x + 1" :cy="L.ghostY + 31" r="4" />
            <text class="ghost-word" :x="L.code.x + 14" :y="L.ghostY + 35">empty: a stranger to turn 1</text>
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
  fill: var(--hmz-warm);
}

.code-line .deco {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.code-line .dim {
  fill: var(--hmz-stage-dim);
  font-style: italic;
}

.caret {
  fill: var(--hmz-lane-1);
}

.slot-head {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.decl-box {
  fill: var(--hmz-stage-card);
  stroke-width: 1.4;
}

.decl-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.slot-arrow {
  fill: none;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.fill-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.slot-cap {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.ribbon-label {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.mem-word {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-lane-1);
}

.memory {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.5;
  stroke-dasharray: 3 3;
}

.ribbon-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-opacity: 0.7;
  stroke-width: 1.4;
  stroke-dasharray: 7 3;
}

.spark {
  fill: var(--hmz-lane-1);
}

.empty {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.turn {
  fill: var(--hmz-lane-1);
}

.turn-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.closed {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.ws-box {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-opacity: 0.75;
  stroke-width: 1.3;
}

.ws-name {
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-warm);
}

.ws-none text {
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
  stroke: var(--hmz-lane-1);
}

.mark-read text {
  fill: var(--hmz-lane-1);
}

.answer-head,
.ghost-head {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-dim);
}

.answer-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.3;
}

.answer-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-accent);
}

.ghost-box {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.3;
  stroke-dasharray: 4 4;
}

.ghost-dot {
  fill: var(--hmz-stage-dim);
}

.ghost-word {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}
</style>
