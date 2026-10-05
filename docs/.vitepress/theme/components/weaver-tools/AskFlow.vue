<script setup lang="ts">
// An agent asking the flow, mid-turn. The role is typed with `AskUserHookAgentMixin`, which in
// `HARNESS_AGENTS` (src/hmz/flows/agents.py) only claude, codex, kimi and pi carry. The flow
// hangs `on_ask_user`; when the builder stops to ask its user, the hook is called with an
// `AskUserHookParams` -- `question`, `options`, and the `ctx` and `session` every hook is told
// (src/hmz/flows/hooks.py) -- and the builder's turn waits while the hook takes a whole turn of
// the reviewer in a new session. `AskUserHookResult(answer=said)` is what the builder is told,
// and its turn carries on from there. A question has no 15-minute limit, unlike the other hooks
// (The agent asking the flow, "A question waits"). The flow is `delegating` on that page; the
// timings and the waiting clock are drawn.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { count, createFx, type Fx } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'The builder’s turn is under way',
  'Mid-turn it asks its user: the flow’s hook',
  'Its turn waits while a reviewer takes one',
  'answer=said, and the builder carries on',
  'The question is the tool',
]

type Tok = [cls: '' | 'kw' | 'fn' | 'str' | 'ty', text: string]
const CODE: Tok[][] = [
  [['fn', 'builder.on_ask_user'], ['', '(asked)']],
  [['kw', 'async def '], ['fn', 'asked'], ['', '(params):']],
  [['', '  r = '], ['kw', 'await '], ['fn', 'reviewer.spawn'], ['', '()']],
  [['', '  said = '], ['kw', 'await '], ['fn', 'reviewer.run'], ['', '(']],
  [['', '    '], ['str', 'f"Review {path}…"'], ['', ', session=r)']],
  [['kw', '  return '], ['ty', 'AskUserHookResult'], ['', '(']],
  [['', '    answer=said)']],
]
const PARAMS: [string, string][] = [
  ['question', '"review calc.py"'],
  ['options', '()'],
  ['ctx', 'FlowContext'],
  ['session', 'the builder’s'],
]
const ASKERS = ['claude', 'codex', 'kimi', 'pi']

// Where each part sits along the time axis, as fractions.
const SPAN = { ask: 0.26, back: 0.8, rStart: 0.33, rEnd: 0.74 }

type Shot = { x: number; y: number; s: number }
interface Box {
  x: number
  y: number
  w: number
}
interface Layout {
  w: number
  h: number
  code: Box
  params: Box
  x0: number
  ax0: number
  ax1: number
  yB: number
  yR: number
  /** The note on waiting: where, and its lines. */
  wait: { y: number; lines: string[] }
  mixin: Box
  tag: { x: number; y: number; lines: string[] }
  open: Shot
  whole: Shot
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  code: { x: 14, y: 14, w: 248 },
  params: { x: 14, y: 172, w: 248 },
  x0: 272,
  ax0: 344,
  ax1: 622,
  yB: 96,
  yR: 186,
  wait: { y: 238, lines: ['a question waits as long as its answer takes;', 'other hooks give up after 15 minutes'] },
  mixin: { x: 272, y: 270, w: 354 },
  tag: { x: 14, y: 296, lines: ['hmz.flows has no other way', 'to hand an agent a tool'] },
  open: { x: 450, y: 110, s: 1.4 },
  whole: { x: 320, y: 180, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 630,
  code: { x: 14, y: 12, w: 332 },
  params: { x: 14, y: 168, w: 332 },
  x0: 14,
  ax0: 84,
  ax1: 346,
  yB: 318,
  yR: 400,
  wait: { y: 448, lines: ['a question waits as long as its answer takes;', 'other hooks give up after 15 minutes'] },
  mixin: { x: 14, y: 480, w: 332 },
  tag: { x: 14, y: 586, lines: ['hmz.flows has no other way to hand an agent a tool'] },
  open: { x: 180, y: 340, s: 1.25 },
  whole: { x: 180, y: 315, s: 1 },
}

const LINE = 16
const CW = 6.6

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const X = (f: number) => L.value.ax0 + f * (L.value.ax1 - L.value.ax0)
const lineY = (i: number) => L.value.code.y + 36 + i * LINE
const codeH = 36 + (CODE.length - 1) * LINE + 12
const pY = (i: number) => L.value.params.y + 38 + i * 15
const PH = 38 + (PARAMS.length - 1) * 15 + 12

const chips = computed(() => {
  let x = L.value.mixin.x + 12
  return ASKERS.map((n) => {
    const c = { n, x, w: n.length * CW + 16 }
    x += c.w + 8
    return c
  })
})

/** The thread from the question down into the hook's turn, and the answer back up. */
const down = computed(() => {
  const l = L.value
  const a = X(SPAN.ask)
  const r = X(SPAN.rStart)
  return `M${a} ${l.yB + 10} C${a} ${l.yB + 40} ${r - 10} ${l.yR - 30} ${r} ${l.yR - 10}`
})
const up = computed(() => {
  const l = L.value
  const b = X(SPAN.back)
  const r = X(SPAN.rEnd)
  return `M${r} ${l.yR - 10} C${r + 10} ${l.yR - 30} ${b} ${l.yB + 40} ${b} ${l.yB + 10}`
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
    const ok = () => palette.accent
    const warm = () => palette.warm

    const caret = one('.caret')
    const pc = (i: number, when: number) => {
      tl.to(caret, { attr: { y: lineY(i) - 12 }, duration: 0.45, ease: 'cine' }, when)
      tl.fromTo(at('.code-line')[i], { opacity: 0.55 }, { opacity: 1, duration: 0.3 }, when + 0.1)
    }
    const codeOut = (i: number) => ({ x: l.code.x + l.code.w - 8, y: lineY(i) - 4 })

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.code-line, .p-row, .ask, .answer, .r-spark, .r-word, .nest-word, .wait, .tag, .chip, .others, .end-cap, .pause-word, .role'), { opacity: 0 }, 0)
    tl.set(at('.card, .params, .mixin'), { opacity: 0 }, 0)
    tl.set(at('.work, .pause, .r-turn'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(at('.down, .up, .nest, .lane'), { drawSVG: '0%' }, 0)
    tl.set(caret, { opacity: 0, attr: { y: lineY(0) - 12 } }, 0)

    // 0 · the builder, a CLI that asks its user, is working.
    tl.addLabel('beat-0', 0)
    tl.to(at('.lane'), { drawSVG: '100%', duration: 1, stagger: 0.15 }, 0.1)
    tl.to(at('.role'), { opacity: 1, duration: 0.5, stagger: 0.15 }, 0.3)
    tl.to(at('.work')[0], { scaleX: 1, duration: 2.2, ease: 'none' }, 0.6)
    tl.fromTo(one('.mixin'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.6 }, 0.8)
    tl.to(at('.chip'), { opacity: 1, duration: 0.3, stagger: 0.1 }, 1.2)
    tl.to(one('.others'), { opacity: 1, duration: 0.4 }, 1.8)
    tl.fromTo(one('.card'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.6 }, 1.4)
    tl.to(at('.code-line'), { opacity: 0.55, duration: 0.4, stagger: 0.08 }, 1.6)
    tl.to(caret, { opacity: 1, duration: 0.3 }, 2)
    pc(0, 2)
    cam.shot(l.whole, 1.6, 1.8)

    // 1 · it stops and asks: in a flow its user is the hook, told an AskUserHookParams.
    const T1 = 3
    tl.addLabel('beat-1', T1)
    tl.fromTo(one('.ask'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5, ease: 'back.out(2)' }, T1)
    cam.flare({ x: X(SPAN.ask), y: l.yB }, warm, T1, 16, 70)
    cam.beam({ x: X(SPAN.ask), y: l.yB - 26 }, codeOut(1), warm, T1 + 0.5, { duration: 0.9, bend: 0.2, burst: 12 })
    pc(1, T1 + 1.3)
    tl.fromTo(one('.params'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.5 }, T1 + 1.5)
    tl.fromTo(at('.p-row'), { opacity: 0, x: -6 }, { opacity: 1, x: 0, duration: 0.35, stagger: 0.2 }, T1 + 1.7)

    // 2 · the builder's turn waits, and the hook takes a whole turn of the reviewer.
    const T2 = T1 + 3
    tl.addLabel('beat-2', T2)
    tl.to(one('.pause-word'), { opacity: 1, duration: 0.3 }, T2)
    tl.to(one('.pause'), { scaleX: 1, duration: 5.4, ease: 'none' }, T2)
    count(tl, one('.clock'), 0, 102, T2, { duration: 5.4, ease: 'none', format: (n) => `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, '0')}` })
    tl.to(one('.down'), { drawSVG: '100%', duration: 0.7, ease: 'cine' }, T2 + 0.3)
    pc(2, T2 + 0.4)
    cam.beam(codeOut(2), { x: X(SPAN.rStart), y: l.yR }, lane3, T2 + 0.5, { duration: 0.8, bend: -0.15 })
    tl.fromTo(one('.r-spark'), { opacity: 0, scale: 0, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.5, ease: 'back.out(3)' }, T2 + 1.3)
    cam.flare({ x: X(SPAN.rStart), y: l.yR }, lane3, T2 + 1.3, 18, 80)
    pc(3, T2 + 1.6)
    tl.to(one('.r-turn'), { scaleX: 1, duration: 2.6, ease: 'power1.inOut' }, T2 + 1.7)
    tl.to(one('.r-word'), { opacity: 1, duration: 0.4 }, T2 + 2.4)
    tl.to(one('.nest'), { drawSVG: '100%', duration: 1.2, ease: 'cine' }, T2 + 2.2)
    tl.to(one('.nest-word'), { opacity: 1, duration: 0.4 }, T2 + 3)
    tl.to(at('.wait'), { opacity: 1, duration: 0.5, stagger: 0.25 }, T2 + 3.6)

    // 3 · the hook answers; the builder reads it as its user's answer and goes on.
    const T3 = T2 + 5.6
    tl.addLabel('beat-3', T3)
    pc(5, T3)
    pc(6, T3 + 0.3)
    cam.beam(codeOut(6), { x: X(SPAN.rEnd), y: l.yR }, ok, T3 + 0.2, { duration: 0.7, bend: 0.2 })
    tl.to(one('.up'), { drawSVG: '100%', duration: 0.8, ease: 'cine' }, T3 + 0.8)
    cam.beam({ x: X(SPAN.rEnd), y: l.yR - 10 }, { x: X(SPAN.back), y: l.yB + 10 }, ok, T3 + 0.8, { duration: 0.8, bend: 0.25, burst: 22 })
    tl.fromTo(one('.answer'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5, ease: 'back.out(2)' }, T3 + 1.3)
    tl.to(one('.pause-word'), { opacity: 0.6, duration: 0.3 }, T3 + 1.5)
    tl.to(at('.work')[1], { scaleX: 1, duration: 1.8, ease: 'none' }, T3 + 1.6)
    tl.to(one('.end-cap'), { opacity: 1, duration: 0.3 }, T3 + 3.4)
    cam.flare({ x: l.ax1, y: l.yB }, lane1, T3 + 3.4, 18, 70)

    // 4 · the question is the tool.
    const T4 = T3 + 4
    tl.addLabel('beat-4', T4)
    tl.fromTo(at('.tag'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.6, stagger: 0.2 }, T4)
    cam.flare({ x: l.tag.x + 90, y: l.tag.y - 6 }, ok, T4 + 0.3, 22, 80)
    tl.to(caret, { opacity: 0.35, duration: 0.6 }, T4 + 1)

    tl.addLabel('rest', T4 + 1.8)
    cam.shot({ ...l.whole, s: l.whole.s * 1.03 }, T4 + 1.2, 3, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 4.4)

    tl.fromTo(at('.hum'), { strokeDashoffset: 0 }, { strokeDashoffset: -120, duration: tl.duration(), ease: 'none' }, 0)
    gsap.set(caret, { opacity: 0 })
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="4 / 7"
    label="An agent asking the flow. The builder's role is typed with AskUserHookAgentMixin, which claude, codex, kimi and pi carry; others are refused before the first turn. Mid-turn, the builder asks its user: review calc.py. In a flow that user is the flow: its on_ask_user hook is called with an AskUserHookParams carrying the question, the options, the flow's context and the session. The builder's turn waits, as long as the answer takes, with no 15-minute limit, while the hook spawns a reviewer session and takes a whole reviewer turn inside the builder's turn. The hook returns AskUserHookResult with answer=said, and the builder carries on from there and ends its turn. The question is the tool: hmz.flows has no other way to hand an agent a tool."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="world">
        <!-- the flow's hook -->
        <g class="card">
          <rect class="card-box" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="codeH" rx="10" />
          <text class="card-head" :x="L.code.x + 12" :y="L.code.y + 18">delegating · the flow’s own code</text>
          <rect class="caret" :x="L.code.x + 4" :y="lineY(0) - 12" width="3" height="16" rx="1.5" />
          <g v-for="(line, i) in CODE" :key="i" class="code-line">
            <text :x="L.code.x + 14" :y="lineY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>

        <!-- what the hook is told -->
        <g class="params">
          <rect class="card-box params-box" :x="L.params.x" :y="L.params.y" :width="L.params.w" :height="PH" rx="10" />
          <text class="card-head ty" :x="L.params.x + 12" :y="L.params.y + 18">params: AskUserHookParams</text>
          <g v-for="(p, i) in PARAMS" :key="p[0]" class="p-row">
            <text class="p-key" :x="L.params.x + 14" :y="pY(i)">{{ p[0] }}</text>
            <text class="p-val" :class="{ q: i === 0 }" :x="L.params.x + 14 + 10 * CW" :y="pY(i)">{{ p[1] }}</text>
          </g>
        </g>

        <!-- the lanes -->
        <g class="role">
          <text class="role-name" :x="L.x0" :y="L.yB - 2">builder</text>
          <text class="role-fill" :x="L.x0" :y="L.yB + 13">claude/…</text>
        </g>
        <g class="role">
          <text class="role-name" :x="L.x0" :y="L.yR - 2">reviewer</text>
          <text class="role-fill" :x="L.x0" :y="L.yR + 13">claude/…</text>
        </g>
        <line class="lane" :x1="L.ax0 - 6" :x2="L.ax1" :y1="L.yB" :y2="L.yB" />
        <line class="lane" :x1="L.ax0 - 6" :x2="L.ax1" :y1="L.yR" :y2="L.yR" />

        <!-- the builder's one turn: working, waiting, working -->
        <rect class="work" :x="X(0)" :y="L.yB - 8" :width="X(SPAN.ask) - X(0)" height="16" rx="8" />
        <rect class="pause hum" :x="X(SPAN.ask)" :y="L.yB - 8" :width="X(SPAN.back) - X(SPAN.ask)" height="16" rx="3" />
        <g class="pause-word">
          <text :x="(X(SPAN.ask) + X(SPAN.back)) / 2" :y="L.yB + 4" text-anchor="middle">❙❙ waiting <tspan class="clock">0:00</tspan></text>
        </g>
        <rect class="work" :x="X(SPAN.back)" :y="L.yB - 8" :width="X(1) - X(SPAN.back)" height="16" rx="8" />
        <circle class="end-cap" :cx="X(1)" :cy="L.yB" r="4" />

        <g class="ask">
          <rect class="bubble ask-box" :x="X(SPAN.ask) - 8" :y="L.yB - 38" width="122" height="20" rx="6" />
          <text class="bubble-word ask-word" :x="X(SPAN.ask)" :y="L.yB - 24">? review calc.py</text>
        </g>
        <path class="down" :d="down" />
        <path class="up" :d="up" />

        <!-- the hook's turn, inside the builder's -->
        <rect class="nest hum" :x="X(SPAN.ask) + 4" :y="L.yR - 22" :width="X(SPAN.back) - X(SPAN.ask) - 8" height="38" rx="8" />
        <circle class="r-spark" :cx="X(SPAN.rStart)" :cy="L.yR" r="5" />
        <rect class="r-turn" :x="X(SPAN.rStart) + 6" :y="L.yR - 8" :width="X(SPAN.rEnd) - X(SPAN.rStart) - 6" height="16" rx="8" />
        <text class="r-word" :x="(X(SPAN.rStart) + X(SPAN.rEnd)) / 2 + 3" :y="L.yR + 4" text-anchor="middle">review</text>
        <text class="nest-word" :x="(X(SPAN.ask) + X(SPAN.back)) / 2" :y="L.yR + 30" text-anchor="middle">inside the builder’s turn</text>

        <g class="answer">
          <rect class="bubble ans-box" :x="X(SPAN.back) - 86" :y="L.yB + 14" width="94" height="20" rx="6" />
          <text class="bubble-word ans-word" :x="X(SPAN.back) - 39" :y="L.yB + 28" text-anchor="middle">answer=said</text>
        </g>

        <text v-for="(line, i) in L.wait.lines" :key="i" class="wait" :x="L.ax0 - 6" :y="L.wait.y + i * 14">{{ line }}</text>

        <!-- who can ask -->
        <g class="mixin">
          <rect class="card-box" :x="L.mixin.x" :y="L.mixin.y" :width="L.mixin.w" height="74" rx="10" />
          <text class="mix-line" :x="L.mixin.x + 12" :y="L.mixin.y + 18"><tspan class="kw">class </tspan><tspan class="fn">Builder</tspan>(Agent, <tspan class="ty">AskUserHookAgentMixin</tspan>)</text>
          <g v-for="c in chips" :key="c.n" class="chip">
            <rect class="chip-box" :x="c.x" :y="L.mixin.y + 28" :width="c.w" height="18" rx="9" />
            <text class="chip-word" :x="c.x + c.w / 2" :y="L.mixin.y + 41" text-anchor="middle">{{ c.n }}</text>
          </g>
          <text class="others" :x="L.mixin.x + 12" :y="L.mixin.y + 64">ask their user; any other CLI is refused</text>
        </g>

        <g class="tag">
          <text class="tag-big" :x="L.tag.x" :y="L.tag.y">The question is the tool.</text>
        </g>
        <g v-for="(line, i) in L.tag.lines" :key="i" class="tag">
          <text class="tag-small" :x="L.tag.x" :y="L.tag.y + 20 + i * 14">{{ line }}</text>
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

.code-line text,
.card-head,
.p-key,
.p-val,
.role-fill,
.bubble-word,
.mix-line,
.chip-word,
.r-word,
.pause-word text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
}

.card-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.params-box {
  stroke: var(--hmz-warm);
  stroke-opacity: 0.7;
}

.card-head {
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.code-line text {
  white-space: pre;
  fill: var(--hmz-stage-ink);
}

.mix-line {
  fill: var(--hmz-stage-ink);
}

.kw {
  fill: var(--hmz-lane-3);
  font-weight: 600;
}

.fn {
  fill: var(--hmz-lane-1);
}

.str {
  fill: var(--hmz-warm);
}

.ty,
.card-head.ty {
  fill: var(--hmz-accent);
  font-weight: 600;
}

.caret {
  fill: var(--hmz-lane-1);
}

.p-key {
  fill: var(--hmz-stage-dim);
}

.p-val {
  fill: var(--hmz-stage-ink);
}

.p-val.q {
  fill: var(--hmz-warm);
  font-weight: 700;
}

.role-name {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.role-fill {
  fill: var(--hmz-stage-dim);
}

.lane {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
  stroke-dasharray: 2 5;
}

.work {
  fill: var(--hmz-lane-1);
}

.pause {
  fill: var(--hmz-lane-1);
  fill-opacity: 0.1;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.3;
  stroke-dasharray: 4 3;
}

.pause-word text {
  font-weight: 700;
  fill: var(--hmz-lane-1);
}

.end-cap {
  fill: var(--hmz-lane-1);
  stroke: var(--hmz-stage-card);
  stroke-width: 2;
}

.bubble {
  fill: var(--hmz-stage-card);
  stroke-width: 1.4;
}

.ask-box {
  stroke: var(--hmz-warm);
}

.ans-box {
  stroke: var(--hmz-accent);
}

.bubble-word {
  font-weight: 700;
}

.ask-word {
  fill: var(--hmz-warm);
}

.ans-word {
  fill: var(--hmz-accent);
}

.down {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 1.6;
  stroke-dasharray: 3 3;
}

.up {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.8;
}

.nest {
  fill: var(--hmz-lane-3);
  fill-opacity: 0.06;
  stroke: var(--hmz-lane-3);
  stroke-opacity: 0.7;
  stroke-width: 1.2;
  stroke-dasharray: 5 4;
}

.r-spark {
  fill: var(--hmz-lane-3);
  stroke: var(--hmz-stage-card);
  stroke-width: 2;
}

.r-turn {
  fill: var(--hmz-lane-3);
}

.r-word {
  font-weight: 700;
  fill: #fff;
}

.nest-word,
.wait,
.others {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.chip-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.3;
}

.chip-word {
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.tag-big {
  font-size: 16px;
  font-weight: 800;
  fill: var(--hmz-accent);
}

.tag-small {
  font-size: 11.5px;
  fill: var(--hmz-stage-dim);
}
</style>
