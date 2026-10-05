<script setup lang="ts">
// The person as an agent, from the flow's side. A role typed `Outworlder` is filled by the
// runtime and never by `-a`: naming it is refused with the message src/hmz/runtime/runner.py
// raises for an automatic role. `talk` (The person as an agent) drives it like any agent: the
// assistant answers, `human.run(answered, session=listening)` shows the person that answer and
// waits for what they type, which is the assistant's next prompt; an empty line ends
// `while said:`. Away -- `hmz exec`, or /afk on -- `run` answers at once: `""` for text, the
// schema's defaults where every field has one, else `OutworlderAway` (the `Outworlder`
// docstring in src/hmz/flows/agents.py). It runs no model and spends nothing. The words and
// the assistant's costs are drawn after the runs on that page.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { count, createFx, type Fx } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'An Outworlder role: humanize fills it, not -a',
  'human.run shows the person the answer',
  'What they type is the next prompt',
  'An empty line ends while said:',
  'Away, it answers at once and spends nothing',
]

type Tok = [cls: '' | 'kw' | 'fn' | 'ty', text: string]
const CODE: Tok[][] = [
  [['', 'human: '], ['ty', 'Outworlder']],
  [['', 'said = task']],
  [['kw', 'while '], ['', 'said:']],
  [['', '  answered = '], ['kw', 'await '], ['fn', 'assistant.run'], ['', '(']],
  [['', '      said, session=conversation)']],
  [['', '  said = '], ['kw', 'await '], ['fn', 'human.run'], ['', '(']],
  [['', '      answered, session=listening)']],
]
const ERROR = ["hmz exec: error: talk: 'human' is", 'assigned automatically by the runtime', 'and cannot be set with -a']
const TYPED = 'Now in one word.'
const SAID_1 = '● `calc.py` is a tiny module…'
const SAID_2 = '● Calculator.'

// Along the time axis: the assistant's turns, the person's, and where the loop ends.
const SPAN = { a1: [0, 0.22], h1: [0.26, 0.5], a2: [0.54, 0.74], h2: [0.78, 0.88] } as const

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
  fill: Box
  errY: number
  x0: number
  ax0: number
  ax1: number
  yA: number
  yH: number
  term: Box
  away: Box
  print: { x: number; y: number }
  open: Shot
  whole: Shot
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  code: { x: 14, y: 14, w: 254 },
  fill: { x: 14, y: 170, w: 254 },
  errY: 254,
  x0: 284,
  ax0: 362,
  ax1: 622,
  yA: 62,
  yH: 150,
  term: { x: 362, y: 190, w: 260 },
  away: { x: 284, y: 266, w: 342 },
  print: { x: 14, y: 334 },
  open: { x: 141, y: 120, s: 1.35 },
  whole: { x: 320, y: 180, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 630,
  code: { x: 14, y: 12, w: 332 },
  fill: { x: 14, y: 166, w: 332 },
  errY: 250,
  x0: 14,
  ax0: 92,
  ax1: 346,
  yA: 330,
  yH: 412,
  term: { x: 92, y: 450, w: 254 },
  away: { x: 14, y: 518, w: 332 },
  print: { x: 14, y: 616 },
  open: { x: 180, y: 140, s: 1.08 },
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
const typedX = computed(() => L.value.term.x + 24)

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
    const ok = () => palette.accent
    const warm = () => palette.warm
    const bad = () => palette.danger

    const caret = one('.caret')
    const pc = (i: number, when: number, tone = 'var(--hmz-lane-1)') => {
      tl.to(caret, { attr: { y: lineY(i) - 12 }, fill: tone, duration: 0.45, ease: 'cine' }, when)
      tl.fromTo(at('.code-line')[i], { opacity: 0.55 }, { opacity: 1, duration: 0.3 }, when + 0.1)
    }
    const codeOut = (i: number) => ({ x: l.code.x + l.code.w - 8, y: lineY(i) - 4 })
    const bar = (sel: string, when: number, dur: number) =>
      tl.to(one(sel), { scaleX: 1, duration: dur, ease: 'power1.inOut' }, when)
    const said = one('.said')
    const typed = one('.typed')
    const tcaret = one('.t-caret')

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.code-line, .row, .err, .role, .cost, .term, .pill-word, .ends, .away, .a-row, .print, .zero'), { opacity: 0 }, 0)
    tl.set(at('.card, .fill'), { opacity: 0 }, 0)
    tl.set(at('.pill'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(at('.lane, .pass'), { drawSVG: '0%' }, 0)
    tl.set(caret, { opacity: 0, attr: { y: lineY(0) - 12 } }, 0)
    tl.set(said, { text: SAID_1 }, 0)
    tl.set(typed, { text: '' }, 0)
    tl.set(tcaret, { attr: { x: typedX.value } }, 0)

    // 0 · the person is a role; humanize fills it, and naming it with -a is refused.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.card'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.6 }, 0.1)
    tl.to(at('.code-line'), { opacity: 0.55, duration: 0.4, stagger: 0.08 }, 0.3)
    tl.to(caret, { opacity: 1, duration: 0.3 }, 0.8)
    pc(0, 0.8, 'var(--hmz-accent)')
    tl.fromTo(one('.fill'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.5 }, 1.3)
    tl.to(at('.row'), { opacity: 1, duration: 0.4, stagger: 0.3 }, 1.6)
    tl.fromTo(one('.row-bad'), { x: 0 }, { keyframes: { x: [0, -4, 4, -3, 3, 0] }, duration: 0.5, ease: 'none' }, 2.5)
    cam.flare({ x: l.fill.x + 60, y: l.fill.y + 52 }, bad, 2.5, 14, 60)
    tl.to(at('.err'), { opacity: 1, duration: 0.4, stagger: 0.25 }, 2.8)
    cam.shot(l.whole, 3.4, 1.7)
    tl.to(at('.lane'), { drawSVG: '100%', duration: 1, stagger: 0.15 }, 3.6)
    tl.to(at('.role, .cost'), { opacity: 1, duration: 0.4, stagger: 0.1 }, 3.8)

    // 1 · the assistant answers, and human.run shows the person that answer.
    const T1 = 5.2
    tl.addLabel('beat-1', T1)
    pc(3, T1)
    cam.beam(codeOut(3), { x: X(0), y: l.yA }, lane1, T1 + 0.1, { duration: 0.7, bend: -0.15 })
    bar('.pill-a1', T1 + 0.7, 1.4)
    tl.to(one('.pill-a1-word'), { opacity: 1, duration: 0.3 }, T1 + 1.1)
    count(tl, one('.cost-a'), 0, 2, T1 + 0.7, { duration: 1.4, format: (n) => `$${(n / 100).toFixed(2)}` })
    pc(5, T1 + 2.1, 'var(--hmz-warm)')
    tl.to(one('.pass-1'), { drawSVG: '100%', duration: 0.7, ease: 'cine' }, T1 + 2.2)
    cam.beam({ x: X(SPAN.a1[1]), y: l.yA + 8 }, { x: X(SPAN.h1[0]), y: l.yH - 8 }, lane1, T1 + 2.2, { duration: 0.7, bend: 0.2, burst: 14 })
    tl.fromTo(one('.term'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5 }, T1 + 2.8)

    // 2 · the person types; their line goes back as the assistant's next prompt.
    const T2 = T1 + 3.6
    tl.addLabel('beat-2', T2)
    bar('.pill-h1', T2, 2.4)
    tl.to(one('.pill-h1-word'), { opacity: 1, duration: 0.3 }, T2 + 0.3)
    tl.to(typed, { text: { value: TYPED }, duration: 1.6, ease: 'none' }, T2 + 0.4)
    tl.to(tcaret, { attr: { x: typedX.value + TYPED.length * CW + 1 }, duration: 1.6, ease: 'none' }, T2 + 0.4)
    tl.fromTo(one('.enter'), { opacity: 0 }, { opacity: 1, duration: 0.15, yoyo: true, repeat: 1 }, T2 + 2.2)
    tl.to(one('.pass-2'), { drawSVG: '100%', duration: 0.7, ease: 'cine' }, T2 + 2.5)
    cam.beam({ x: X(SPAN.h1[1]), y: l.yH - 8 }, { x: X(SPAN.a2[0]), y: l.yA + 8 }, warm, T2 + 2.5, { duration: 0.7, bend: 0.2, burst: 14 })
    pc(3, T2 + 2.6)
    bar('.pill-a2', T2 + 3.2, 1.2)
    tl.to(one('.pill-a2-word'), { opacity: 1, duration: 0.3 }, T2 + 3.5)
    count(tl, one('.cost-a'), 2, 3, T2 + 3.2, { duration: 1.2, format: (n) => `$${(n / 100).toFixed(2)}` })

    // 3 · the next answer is shown; an empty line comes back, and the loop ends.
    const T3 = T2 + 4.6
    tl.addLabel('beat-3', T3)
    pc(5, T3, 'var(--hmz-warm)')
    tl.to(one('.pass-3'), { drawSVG: '100%', duration: 0.6, ease: 'cine' }, T3 + 0.1)
    cam.beam({ x: X(SPAN.a2[1]), y: l.yA + 8 }, { x: X(SPAN.h2[0]), y: l.yH - 8 }, lane1, T3 + 0.1, { duration: 0.6, bend: 0.2 })
    tl.set(said, { text: SAID_2 }, T3 + 0.7)
    tl.set(typed, { text: '' }, T3 + 0.7)
    tl.set(tcaret, { attr: { x: typedX.value } }, T3 + 0.7)
    tl.fromTo(said, { opacity: 0.3 }, { opacity: 1, duration: 0.3 }, T3 + 0.7)
    bar('.pill-h2', T3 + 0.8, 0.9)
    tl.fromTo(one('.enter'), { opacity: 0 }, { opacity: 1, duration: 0.15, yoyo: true, repeat: 1 }, T3 + 1.6)
    pc(2, T3 + 2, 'var(--hmz-warm)')
    tl.fromTo(one('.ends'), { opacity: 0, x: -6 }, { opacity: 1, x: 0, duration: 0.5 }, T3 + 2.2)
    cam.flare({ x: X(SPAN.h2[1]) + 8, y: l.yH }, warm, T3 + 2.2, 18, 70)
    tl.fromTo(one('.print'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5 }, T3 + 2.8)

    // 4 · nobody there: run answers at once, by rule, and the person's meter never moves.
    const T4 = T3 + 3.8
    tl.addLabel('beat-4', T4)
    tl.fromTo(one('.away'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.5 }, T4)
    tl.to(at('.a-row'), { opacity: 1, duration: 0.4, stagger: 0.35 }, T4 + 0.5)
    tl.to(at('.zero'), { opacity: 1, duration: 0.4 }, T4 + 1.7)
    tl.fromTo(one('.cost-h'), { opacity: 1 }, { opacity: 0.35, duration: 0.25, yoyo: true, repeat: 3 }, T4 + 1.7)
    cam.flare({ x: l.x0 + 20, y: l.yH + 27 }, ok, T4 + 1.8, 16, 60)
    tl.to(caret, { opacity: 0.35, duration: 0.6 }, T4 + 2.4)

    tl.addLabel('rest', T4 + 3)
    cam.shot({ ...l.whole, s: l.whole.s * 1.03 }, T4 + 2.4, 3, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 5.6)

    // The caret in the terminal blinks the whole time, and the threads hum.
    tl.fromTo(tcaret, { opacity: 1 }, { opacity: 0.15, duration: 0.5, repeat: Math.ceil(tl.duration() / 0.5), yoyo: true, ease: 'steps(1)' }, 0)
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
    label="The person as an agent. The flow talk declares human: Outworlder. humanize fills that role itself, never -a: naming it with -a is refused with hmz exec: error: talk: 'human' is assigned automatically by the runtime and cannot be set with -a. In the loop, the assistant answers; human.run shows the person that answer and waits for what they type; what they type, Now in one word., is the assistant's next prompt. The next answer is shown, the person enters an empty line, and while said: ends after two turns. When the person is away, under hmz exec or with /afk on, run answers at once without asking: an empty string for text, the schema's defaults where every field has one, otherwise OutworlderAway. It runs no model and spends nothing: the assistant's cost goes up, the person's stays at zero."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="world">
        <!-- the flow -->
        <g class="card">
          <rect class="card-box" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="codeH" rx="10" />
          <text class="card-head" :x="L.code.x + 12" :y="L.code.y + 18">talk · the flow’s own code</text>
          <rect class="caret" :x="L.code.x + 4" :y="lineY(0) - 12" width="3" height="16" rx="1.5" />
          <g v-for="(line, i) in CODE" :key="i" class="code-line">
            <text :x="L.code.x + 14" :y="lineY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>

        <!-- who fills the roles -->
        <g class="fill">
          <rect class="card-box" :x="L.fill.x" :y="L.fill.y" :width="L.fill.w" height="66" rx="10" />
          <text class="fill-head" :x="L.fill.x + 12" :y="L.fill.y + 18">who fills the roles</text>
          <g class="row"><text class="row-line" :x="L.fill.x + 12" :y="L.fill.y + 36">assistant ← -a assistant=claude/…</text></g>
          <g class="row row-bad"><text class="row-line" :x="L.fill.x + 12" :y="L.fill.y + 54">{{ 'human     ← ' }}<tspan class="ty">humanize</tspan>, never -a</text></g>
        </g>
        <g v-for="(line, i) in ERROR" :key="i" class="err">
          <text class="err-text" :x="L.fill.x" :y="L.errY + i * 15">{{ line }}</text>
        </g>
        <g class="print">
          <text class="print-text" :x="L.print.x" :y="L.print.y">talk: 2 turns, away=False</text>
        </g>

        <!-- the lanes -->
        <g class="role">
          <text class="role-name" :x="L.x0" :y="L.yA - 2">assistant</text>
          <text class="role-fill" :x="L.x0" :y="L.yA + 13">claude/…</text>
        </g>
        <text class="cost cost-a" :x="L.x0" :y="L.yA + 28">$0.00</text>
        <g class="role">
          <text class="role-name" :x="L.x0" :y="L.yH - 2">human</text>
          <text class="role-fill" :x="L.x0" :y="L.yH + 13">Outworlder</text>
        </g>
        <text class="cost cost-h" :x="L.x0" :y="L.yH + 28">$0.00</text>
        <line class="lane" :x1="L.ax0 - 4" :x2="L.ax1" :y1="L.yA" :y2="L.yA" />
        <line class="lane" :x1="L.ax0 - 4" :x2="L.ax1" :y1="L.yH" :y2="L.yH" />

        <rect class="pill pill-a pill-a1" :x="X(SPAN.a1[0])" :y="L.yA - 8" :width="X(SPAN.a1[1]) - X(SPAN.a1[0])" height="16" rx="8" />
        <text class="pill-word pill-a1-word" :x="(X(SPAN.a1[0]) + X(SPAN.a1[1])) / 2" :y="L.yA + 4" text-anchor="middle">task</text>
        <rect class="pill pill-a pill-a2" :x="X(SPAN.a2[0])" :y="L.yA - 8" :width="X(SPAN.a2[1]) - X(SPAN.a2[0])" height="16" rx="8" />
        <text class="pill-word pill-a2-word" :x="(X(SPAN.a2[0]) + X(SPAN.a2[1])) / 2" :y="L.yA + 4" text-anchor="middle">said</text>
        <rect class="pill pill-h pill-h1" :x="X(SPAN.h1[0])" :y="L.yH - 8" :width="X(SPAN.h1[1]) - X(SPAN.h1[0])" height="16" rx="8" />
        <text class="pill-word pill-h1-word" :x="(X(SPAN.h1[0]) + X(SPAN.h1[1])) / 2" :y="L.yH + 4" text-anchor="middle">typing</text>
        <rect class="pill pill-h pill-h2" :x="X(SPAN.h2[0])" :y="L.yH - 8" :width="X(SPAN.h2[1]) - X(SPAN.h2[0])" height="16" rx="8" />
        <g class="ends">
          <text :x="X(SPAN.h2[1]) + 6" :y="L.yH - 12">""</text>
        </g>

        <path class="pass pass-1" :d="`M${X(SPAN.a1[1])} ${L.yA + 8} L${X(SPAN.h1[0])} ${L.yH - 8}`" />
        <path class="pass pass-2 back" :d="`M${X(SPAN.h1[1])} ${L.yH - 8} L${X(SPAN.a2[0])} ${L.yA + 8}`" />
        <path class="pass pass-3" :d="`M${X(SPAN.a2[1])} ${L.yA + 8} L${X(SPAN.h2[0])} ${L.yH - 8}`" />

        <!-- what the person sees -->
        <g class="term">
          <rect class="term-box" :x="L.term.x" :y="L.term.y" :width="L.term.w" height="52" rx="8" />
          <text class="said" :x="L.term.x + 10" :y="L.term.y + 20">{{ SAID_1 }}</text>
          <text class="prompt" :x="L.term.x + 10" :y="L.term.y + 40">❯</text>
          <text class="typed" :x="typedX" :y="L.term.y + 40">{{ TYPED }}</text>
          <rect class="t-caret" :x="typedX" :y="L.term.y + 30" width="6" height="13" />
          <text class="enter" :x="L.term.x + L.term.w - 10" :y="L.term.y + 40" text-anchor="end">⏎</text>
        </g>

        <!-- nobody there -->
        <g class="away">
          <rect class="card-box away-box" :x="L.away.x" :y="L.away.y" :width="L.away.w" height="74" rx="10" />
          <text class="away-head" :x="L.away.x + 12" :y="L.away.y + 17"><tspan class="mono">human.away</tspan> (hmz exec, or /afk): answers at once</text>
          <g class="a-row"><text class="a-line" :x="L.away.x + 12" :y="L.away.y + 34">{{ 'text                 → ' }}<tspan class="v">""</tspan></text></g>
          <g class="a-row"><text class="a-line" :x="L.away.x + 12" :y="L.away.y + 49">{{ 'schema, all defaults → ' }}<tspan class="v">the defaults</tspan></text></g>
          <g class="a-row"><text class="a-line" :x="L.away.x + 12" :y="L.away.y + 64">{{ 'otherwise            → ' }}<tspan class="x">OutworlderAway</tspan></text></g>
        </g>
        <text class="zero" :x="L.x0 + 44" :y="L.yH + 28">runs no model, spends nothing</text>
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
.row-line,
.err-text,
.print-text,
.role-fill,
.cost,
.pill-word,
.ends text,
.said,
.prompt,
.typed,
.enter,
.a-line,
.mono {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  white-space: pre;
}

.card-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.card-head {
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.code-line text {
  fill: var(--hmz-stage-ink);
}

.kw {
  fill: var(--hmz-lane-3);
  font-weight: 600;
}

.fn {
  fill: var(--hmz-lane-1);
}

.ty {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.caret {
  fill: var(--hmz-accent);
}

.fill-head {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.row-line {
  fill: var(--hmz-stage-ink);
}

.err-text {
  fill: var(--vp-c-danger-1);
}

.print-text {
  font-weight: 700;
  fill: var(--hmz-accent);
}

.role-name {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.role-fill {
  fill: var(--hmz-stage-dim);
}

.cost {
  font-weight: 700;
  fill: var(--hmz-lane-1);
}

.cost-h {
  fill: var(--hmz-accent);
}

.lane {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
  stroke-dasharray: 2 5;
}

.pill-a {
  fill: var(--hmz-lane-1);
}

.pill-h {
  fill: var(--hmz-warm);
}

.pill-word {
  font-weight: 700;
  fill: #fff;
}

.ends text {
  font-weight: 700;
  fill: var(--hmz-warm);
}

.pass {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.4;
  stroke-dasharray: 3 3;
}

.pass.back {
  stroke: var(--hmz-warm);
}

.term-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-warm);
  stroke-opacity: 0.7;
  stroke-width: 1.2;
}

.said {
  fill: var(--hmz-stage-ink);
}

.prompt {
  font-weight: 700;
  fill: var(--hmz-accent);
}

.typed {
  font-weight: 700;
  fill: var(--hmz-warm);
}

.t-caret {
  fill: var(--hmz-warm);
}

.enter {
  font-weight: 700;
  fill: var(--hmz-warm);
}

.away-box {
  stroke: var(--hmz-accent);
  stroke-opacity: 0.6;
  stroke-dasharray: 4 3;
}

.away-head {
  font-size: 11.5px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.away-head .mono {
  fill: var(--hmz-accent);
}

.a-line {
  fill: var(--hmz-stage-dim);
}

.a-line .v {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.a-line .x {
  fill: var(--vp-c-danger-1);
  font-weight: 700;
}

.zero {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-accent);
}
</style>
