<script setup lang="ts">
// A goal, as the flow that sets it sees it. The role carries `GoalCommandAgentMixin`, and only a
// CLI whose agent type has it can fill the role: in `HARNESS_AGENTS` (src/hmz/flows/agents.py)
// that is claude, codex, kimi and dsh. Any other is refused before a turn is taken, with the
// message `src/hmz/runtime/runner.py` raises for a role whose mixins a CLI lacks. A prompt
// starting `/goal ` is handed to the CLI's own goal feature (`GoalCommandAgentMixin` in
// agents.py), so the flow waits on one `run` while the CLI takes turn after turn against the
// objective; every turn draws on the run's budget, which is what bounds a goal that never
// settles; when the CLI judges it met, `run` returns what the agent said last. The flow is
// `aim` on Goals; the turns, their costs and the answer are drawn after the run on that page.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { count, createFx, type Fx } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'Only a CLI with a goal can fill the role',
  '/goal hands the rest to the CLI’s own goal',
  'One run waits while the CLI takes turns',
  'Every turn draws on the run’s budget',
  'Met: run returns the last answer',
]

type Tok = [cls: '' | 'kw' | 'fn' | 'str' | 'mx', text: string]
const CODE: Tok[][] = [
  [['kw', 'class '], ['fn', 'Worker'], ['', '(Agent, '], ['mx', 'GoalCommandAgentMixin'], ['', ')']],
  [['', 's = '], ['kw', 'await '], ['fn', 'worker.spawn'], ['', '()']],
  [['kw', 'return await '], ['fn', 'worker.run'], ['', '(']],
  [['', '    '], ['str', 'f"/goal {task}"'], ['', ', session=s)']],
]

const CHIPS = [
  { n: 'claude', goal: true },
  { n: 'codex', goal: true },
  { n: 'kimi', goal: true },
  { n: 'dsh', goal: true },
  { n: 'mcode', goal: false },
]
const ERROR = "hmz exec: error: aim: 'worker' needs GoalCommandAgentMixin, which mcode does not support"

// What each turn did (drawn after the run on the page), and what is left of a one-dollar budget.
const TURNS = ['read', 'edit', 'run check', 'judged met']
const LEFT = [1, 0.91, 0.8, 0.7, 0.62]

type Shot = { x: number; y: number; s: number }
interface Layout {
  w: number
  h: number
  code: { x: number; y: number; w: number }
  filter: { x: number; y: number; w: number }
  error: { x: number; y: number; lines: string[] }
  x0: number
  x1: number
  flowY: number
  goalY: number
  cliY: number
  budgetY: number
  note: string[]
  goal: string
  open: Shot
  peek: Shot
  whole: Shot
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  code: { x: 14, y: 36, w: 300 },
  filter: { x: 328, y: 36, w: 298 },
  error: { x: 14, y: 154, lines: [ERROR] },
  x0: 104,
  x1: 626,
  flowY: 194,
  goalY: 226,
  cliY: 254,
  budgetY: 312,
  note: ['every turn draws on it, so it bounds a goal that never settles'],
  goal: '◎ goal: subtract in calc.py, and check.py prints ok',
  open: { x: 168, y: 84, s: 1.45 },
  peek: { x: 470, y: 86, s: 1.35 },
  whole: { x: 320, y: 180, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 504,
  code: { x: 14, y: 14, w: 332 },
  filter: { x: 14, y: 122, w: 332 },
  error: {
    x: 14,
    y: 238,
    lines: ["hmz exec: error: aim: 'worker' needs", 'GoalCommandAgentMixin, which mcode does', 'not support'],
  },
  x0: 84,
  x1: 346,
  flowY: 306,
  goalY: 340,
  cliY: 370,
  budgetY: 424,
  note: ['every turn draws on it, so it bounds', 'a goal that never settles'],
  goal: '◎ goal: subtract, and check.py prints ok',
  open: { x: 180, y: 76, s: 1.08 },
  peek: { x: 180, y: 176, s: 1.08 },
  whole: { x: 180, y: 252, s: 1 },
}

const LINE = 17

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const lineY = (i: number) => L.value.code.y + 38 + i * LINE
const codeOut = (i: number) => ({ x: L.value.code.x + L.value.code.w - 8, y: lineY(i) - 4 })
const codeH = 38 + (CODE.length - 1) * LINE + 12
const FILTER_H = 98

const chipW = (n: string) => n.length * 6.6 + 16
const chips = computed(() => {
  let x = L.value.filter.x + 12
  return CHIPS.map((c) => {
    const at = { ...c, x, w: chipW(c.n), cx: x + chipW(c.n) / 2 }
    x += at.w + 8
    return at
  })
})
const chipY = computed(() => L.value.filter.y + 30)

// The turns, between the ends of the flow's one await.
const GAP = 14
const turns = computed(() => {
  const a = L.value.x0 + 8
  const b = L.value.x1 - 8
  const w = (b - a - GAP * (TURNS.length - 1)) / TURNS.length
  return TURNS.map((cap, i) => {
    const x = a + i * (w + GAP)
    return { cap, x, w, cx: x + w / 2, end: x + w }
  })
})
/** How far the flow's bar has grown, when the CLI is at x. */
const grown = (x: number) => (x - L.value.x0) / (L.value.x1 - L.value.x0)

const answerPath = computed(() => {
  const t = turns.value[turns.value.length - 1]
  const l = L.value
  return `M${t.end - 4} ${l.cliY - 9} C${t.end + 8} ${l.cliY - 40} ${l.x1 + 2} ${l.flowY + 40} ${l.x1 - 2} ${l.flowY + 8}`
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
    const T = turns.value
    const lane1 = () => palette.lane[0]
    const ok = () => palette.accent
    const warm = () => palette.warm
    const bad = () => palette.danger

    const caret = one('.caret')
    const pc = (i: number, when: number) => {
      tl.to(caret, { attr: { y: lineY(i) - 13 }, duration: 0.45, ease: 'cine' }, when)
      tl.fromTo(at('.code-line')[i], { opacity: 0.55 }, { opacity: 1, duration: 0.3 }, when + 0.1)
    }

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.code-line'), { opacity: 0 }, 0)
    tl.set(
      at('.chip, .chip-ring, .chip-x, .under, .fills, .err, .lane-name, .goal-word, .turn-word, .cap, .met-dot, .budget-word, .note, .turns-n, .guide'),
      { opacity: 0 },
      0,
    )
    tl.set(at('.goal-line, .answer-path, .track'), { drawSVG: '0%' }, 0)
    tl.set(at('.flow-bar, .flow-clip, .turn'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(one('.left-bar'), { scaleX: 1, transformOrigin: '0% 50%' }, 0)
    tl.set(at('.flow-cap, .answer'), { opacity: 0 }, 0)
    tl.set(caret, { opacity: 0, attr: { y: lineY(0) - 13 } }, 0)

    // 0 · the role asks for a goal; four CLIs have one, and mcode is refused before anything runs.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.card'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.7 }, 0.1)
    tl.to(at('.code-line'), { opacity: 0.55, duration: 0.5, stagger: 0.12 }, 0.3)
    tl.to(caret, { opacity: 1, duration: 0.3 }, 0.9)
    pc(0, 0.9)
    tl.fromTo(one('.mixin-hl'), { opacity: 0 }, { opacity: 1, duration: 0.4 }, 1.1)
    tl.fromTo(one('.filter'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.6 }, 1.1)
    cam.shot(l.peek, 1.2, 1.4)
    cam.beam(codeOut(0), { x: l.filter.x + 20, y: l.filter.y + 14 }, ok, 1.3, { duration: 0.7, bend: -0.2 })
    tl.fromTo(at('.chip'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.4, stagger: 0.12 }, 1.8)
    tl.to(at('.chip-ring'), { opacity: 1, duration: 0.4, stagger: 0.12 }, 2.6)
    tl.to(at('.under-yes'), { opacity: 1, duration: 0.4 }, 2.9)
    tl.fromTo(one('.chip-bad'), { x: 0 }, { keyframes: { x: [0, -4, 4, -3, 3, 0] }, duration: 0.5, ease: 'none' }, 3.2)
    tl.to(at('.chip-x, .under-no'), { opacity: 1, duration: 0.3 }, 3.3)
    const bx = chips.value[4]
    cam.flare({ x: bx.cx, y: chipY.value + 9 }, bad, 3.3, 16, 70)
    cam.shot(l.whole, 3.5, 1.6)
    tl.to(at('.err'), { opacity: 1, duration: 0.2 }, 3.7)
    at('.err-text').forEach((el, i) => {
      const words = l.error.lines[i]
      const start = 3.75 + i * 0.6
      tl.set(el, { text: '' }, 3.7)
      tl.to(el, { text: { value: words }, duration: words.length / 70, ease: 'none' }, start)
    })
    tl.to(one('.fills'), { opacity: 1, duration: 0.4 }, 5.1)
    cam.flare({ x: chips.value[0].cx, y: chipY.value + 9 }, ok, 5.1, 18, 70)
    tl.to(one('.mixin-hl'), { opacity: 0, duration: 0.4 }, 5.6)

    // 1 · the prompt is not words: the rest of it goes to claude's own goal, and one run opens.
    const T1 = 6.6
    tl.addLabel('beat-1', T1)
    pc(1, T1)
    pc(2, T1 + 0.5)
    pc(3, T1 + 0.9)
    tl.fromTo(one('.goal-hl'), { opacity: 0 }, { opacity: 1, duration: 0.4 }, T1 + 1)
    tl.to(at('.lane-name'), { opacity: 1, duration: 0.5, stagger: 0.15 }, T1 + 0.2)
    tl.to(at('.guide'), { opacity: 1, duration: 0.6 }, T1 + 1.2)
    cam.beam(codeOut(3), { x: l.x0, y: l.flowY }, lane1, T1 + 1.2, { duration: 0.8, bend: 0.2 })
    tl.to(at('.flow-bar, .flow-clip'), { scaleX: grown(T[0].x), duration: 0.8, ease: 'power1.out' }, T1 + 2)
    cam.beam({ x: l.x0 + 8, y: l.flowY + 6 }, { x: T[0].x, y: l.goalY }, ok, T1 + 2.3, { duration: 0.7, bend: -0.25, burst: 18 })
    tl.to(one('.goal-line'), { drawSVG: '100%', duration: 1.2, ease: 'cine' }, T1 + 3)
    tl.to(one('.goal-word'), { opacity: 1, duration: 0.5 }, T1 + 3.4)

    // 2 · turn after turn on the CLI's lane; the flow's bar only grows, one await the whole time.
    const turnsN = one('.turns-n')
    const said = (n: number) => `${n} turn${n === 1 ? '' : 's'}`
    const turn = (i: number, when: number, dur: number) => {
      const t = T[i]
      const last = i === T.length - 1
      tl.to(at('.turn')[i], { scaleX: 1, duration: dur, ease: 'power1.inOut' }, when)
      tl.to(at('.turn-word')[i], { opacity: 1, duration: 0.3 }, when + dur * 0.4)
      tl.to(at('.cap')[i], { opacity: 1, duration: 0.3 }, when + dur * 0.6)
      tl.to(at('.flow-bar, .flow-clip'), { scaleX: grown(t.end + (last ? 8 : GAP / 2)), duration: dur, ease: 'none' }, when)
      tl.to(one('.left-bar'), { scaleX: LEFT[i + 1], duration: dur, ease: 'power1.inOut' }, when)
      count(tl, one('.left-n'), LEFT[i] * 100, LEFT[i + 1] * 100, when, { duration: dur, format: (n) => `$${(n / 100).toFixed(2)} left` })
      // A set rather than a call: a set is undone when the timeline goes back over it, so the
      // count reads right on every loop and after a jump to any chapter.
      tl.set(turnsN, { text: said(i + 1) }, when)
      tl.fromTo(at('.met-dot')[i], { opacity: 0, scale: 0, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(2.4)' }, when + dur)
      cam.flare({ x: t.end, y: l.cliY }, last ? ok : warm, when + dur, last ? 26 : 10, 70)
    }
    tl.set(turnsN, { text: said(0) }, 0)
    const T2 = T1 + 4.6
    tl.addLabel('beat-2', T2)
    tl.to(turnsN, { opacity: 1, duration: 0.4 }, T2)
    tl.to(at('.budget-word'), { opacity: 1, duration: 0.4 }, T2)
    tl.to(one('.track'), { drawSVG: '100%', duration: 0.8 }, T2)
    turn(0, T2 + 0.4, 1.4)
    turn(1, T2 + 2.1, 1.4)

    // 3 · the budget: every turn spends from it, and an objective that never settles runs it dry.
    const T3 = T2 + 3.9
    tl.addLabel('beat-3', T3)
    cam.shot({ x: l.whole.x, y: (l.cliY + l.budgetY) / 2 + 6, s: 1.12 }, T3, 1.4)
    turn(2, T3 + 0.3, 1.4)
    cam.beam({ x: T[2].cx, y: l.cliY + 10 }, { x: l.x0 + (l.x1 - l.x0) * LEFT[3], y: l.budgetY }, warm, T3 + 1.1, { duration: 0.6, bend: 0.15, burst: 10 })
    tl.fromTo(one('.left-bar'), { opacity: 1 }, { opacity: 0.5, duration: 0.25, yoyo: true, repeat: 3 }, T3 + 1.7)
    tl.to(at('.note'), { opacity: 1, duration: 0.5, stagger: 0.2 }, T3 + 1.9)
    cam.shot(l.whole, T3 + 3.4, 1.4)

    // 4 · the CLI judges the objective met, and the one run returns what it said last.
    const T4 = T3 + 4
    tl.addLabel('beat-4', T4)
    turn(3, T4, 1.3)
    tl.to(one('.answer-path'), { drawSVG: '100%', duration: 0.8, ease: 'cine' }, T4 + 1.5)
    cam.beam({ x: T[3].end, y: l.cliY - 9 }, { x: l.x1 - 2, y: l.flowY + 8 }, ok, T4 + 1.5, { duration: 0.8, bend: 0.3, burst: 22 })
    tl.to(one('.flow-cap'), { opacity: 1, duration: 0.3 }, T4 + 2.3)
    tl.fromTo(one('.answer'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5 }, T4 + 2.4)
    tl.to(caret, { opacity: 0.35, duration: 0.6 }, T4 + 2.8)

    tl.addLabel('rest', T4 + 3.4)
    cam.shot({ ...l.whole, s: l.whole.s * 1.03 }, T4 + 3, 3, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 6.4)

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
    mobile-ratio="5 / 7"
    label="A goal, from the flow's side. The role worker is typed Worker, which carries GoalCommandAgentMixin, so only a CLI with a goal can fill it: claude, codex, kimi or dsh. mcode is refused before anything runs: hmz exec: error: aim: 'worker' needs GoalCommandAgentMixin, which mcode does not support. With claude filling it, the flow runs a prompt that starts with /goal, which is not sent as words: the rest is handed to claude's own goal feature. The flow waits on that one run while claude takes turn after turn, reading, editing, running the check; every turn draws on the run's budget, which is what bounds a goal that never settles. When claude judges the objective met, the run returns the last thing it said."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <clipPath id="goal-run-bar"><rect class="flow-clip" :x="L.x0" :y="L.flowY - 8" :width="L.x1 - L.x0" height="16" rx="8" /></clipPath>
      </defs>
      <g class="world">
        <!-- the flow's code -->
        <g class="card">
          <rect class="card-box" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="codeH" rx="10" />
          <text class="card-head" :x="L.code.x + 12" :y="L.code.y + 18">aim · .hmz/flows/aim/__init__.py</text>
          <rect class="mixin-hl" :x="L.code.x + 12 + 20 * 6.6" :y="lineY(0) - 12" :width="21 * 6.6 + 4" height="16" rx="3" />
          <rect class="goal-hl" :x="L.code.x + 12 + 4 * 6.6" :y="lineY(3) - 12" :width="15 * 6.6 + 4" height="16" rx="3" />
          <rect class="caret" :x="L.code.x + 4" :y="lineY(0) - 13" width="3" height="16" rx="1.5" />
          <g v-for="(line, i) in CODE" :key="i" class="code-line">
            <text :x="L.code.x + 14" :y="lineY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>

        <!-- who can fill the role -->
        <g class="filter">
          <rect class="card-box" :x="L.filter.x" :y="L.filter.y" :width="L.filter.w" :height="FILTER_H" rx="10" />
          <text class="filter-head" :x="L.filter.x + 12" :y="L.filter.y + 18">who can fill <tspan class="mono">worker: Worker</tspan></text>
          <g v-for="c in chips" :key="c.n" class="chip" :class="{ 'chip-bad': !c.goal }">
            <rect class="chip-box" :class="c.goal ? 'yes' : 'no'" :x="c.x" :y="chipY" :width="c.w" height="18" rx="9" />
            <rect v-if="c.goal" class="chip-ring" :x="c.x - 2.5" :y="chipY - 2.5" :width="c.w + 5" height="23" rx="11.5" />
            <text class="chip-word" :class="c.goal ? 'yes' : 'no'" :x="c.cx" :y="chipY + 13" text-anchor="middle">{{ c.n }}</text>
            <g v-if="!c.goal" class="chip-x">
              <line :x1="c.x + 6" :x2="c.x + c.w - 6" :y1="chipY + 9" :y2="chipY + 9" />
            </g>
          </g>
          <text class="under under-yes" :x="(chips[0].x + chips[3].x + chips[3].w) / 2" :y="chipY + 34" text-anchor="middle">have a goal</text>
          <text class="under under-no" :x="chips[4].cx" :y="chipY + 34" text-anchor="middle">no goal</text>
          <text class="fills" :x="L.filter.x + 12" :y="L.filter.y + 86">✓ <tspan class="mono">-a worker=claude/…</tspan> fills it</text>
        </g>

        <g class="err">
          <text v-for="(line, i) in L.error.lines" :key="i" class="err-text" :x="L.error.x" :y="L.error.y + i * 15">{{ line }}</text>
        </g>

        <!-- the flow's one await, and the CLI's turns under it -->
        <g class="lane-name">
          <text class="role-name" :x="14" :y="L.flowY - 1">flow</text>
          <text class="role-fill" :x="14" :y="L.flowY + 13">aim</text>
        </g>
        <g class="lane-name">
          <text class="role-name" :x="14" :y="L.cliY - 1">claude</text>
          <text class="role-fill turns-n" :x="14" :y="L.cliY + 13">0 turns</text>
        </g>
        <line class="guide hum" :x1="L.x0 + 8" :x2="L.x0 + 8" :y1="L.flowY + 8" :y2="L.cliY - 10" />
        <line class="guide hum" :x1="L.x1 - 8" :x2="L.x1 - 8" :y1="L.flowY + 8" :y2="L.cliY - 10" />
        <rect class="flow-bar" :x="L.x0" :y="L.flowY - 8" :width="L.x1 - L.x0" height="16" rx="8" />
        <g clip-path="url(#goal-run-bar)"><text class="flow-word" :x="L.x0 + 12" :y="L.flowY + 4">await worker.run(…) · one run</text></g>
        <circle class="flow-cap" :cx="L.x1 - 4" :cy="L.flowY" r="4" />
        <g class="answer">
          <text class="answer-text" :x="L.x1" :y="L.flowY - 16" text-anchor="end">returns "I added subtract(a, b)…"</text>
        </g>

        <line class="goal-line" :x1="turns[0].x" :x2="turns[turns.length - 1].end" :y1="L.goalY" :y2="L.goalY" />
        <text class="goal-word" :x="(turns[0].x + turns[turns.length - 1].end) / 2" :y="L.goalY - 6" text-anchor="middle">{{ L.goal }}</text>

        <g v-for="(t, i) in turns" :key="i">
          <rect class="turn" :x="t.x" :y="L.cliY - 9" :width="t.w" height="18" rx="9" />
          <text class="turn-word" :x="t.cx" :y="L.cliY + 4" text-anchor="middle">turn {{ i + 1 }}</text>
          <text class="cap" :class="{ met: i === turns.length - 1 }" :x="t.cx" :y="L.cliY + 26" text-anchor="middle">{{ t.cap }}</text>
          <circle class="met-dot" :class="i === turns.length - 1 ? 'met' : 'not'" :cx="t.end" :cy="L.cliY - 9" r="4" />
        </g>
        <path class="answer-path" :d="answerPath" />

        <!-- the run's budget -->
        <g class="budget-word">
          <text class="role-name" :x="14" :y="L.budgetY - 1">budget</text>
          <text class="role-fill" :x="14" :y="L.budgetY + 13">cost=1</text>
        </g>
        <rect class="track" :x="L.x0" :y="L.budgetY - 4" :width="L.x1 - L.x0" height="8" rx="4" />
        <rect class="left-bar budget-word" :x="L.x0" :y="L.budgetY - 4" :width="L.x1 - L.x0" height="8" rx="4" />
        <text class="left-n budget-word" :x="L.x1" :y="L.budgetY - 10" text-anchor="end">$1.00 left</text>
        <text v-for="(line, i) in L.note" :key="i" class="note" :x="L.x0" :y="L.budgetY + 22 + i * 15">{{ line }}</text>
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.mono,
.code-line text,
.card-head,
.chip-word,
.err-text,
.turn-word,
.flow-word,
.answer-text,
.left-n,
.role-fill {
  font-family: var(--vp-font-family-mono);
}

.card-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.card-head {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.code-line text {
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

.code-line .mx {
  fill: var(--hmz-accent);
  font-weight: 600;
}

.mixin-hl {
  fill: var(--hmz-accent);
  fill-opacity: 0.16;
}

.goal-hl {
  fill: var(--hmz-warm);
  fill-opacity: 0.16;
}

.caret {
  fill: var(--hmz-lane-1);
}

.filter-head {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.filter-head .mono {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-accent);
}

.chip-box.yes {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.3;
}

.chip-box.no {
  fill: var(--hmz-stage-card);
  stroke: var(--vp-c-danger-1);
  stroke-width: 1.3;
  stroke-dasharray: 3 2;
}

.chip-ring {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-opacity: 0.35;
  stroke-width: 2;
}

.chip-word {
  font-size: 11px;
  font-weight: 600;
}

.chip-word.yes {
  fill: var(--hmz-stage-ink);
}

.chip-word.no {
  fill: var(--vp-c-danger-1);
}

.chip-x line {
  stroke: var(--vp-c-danger-1);
  stroke-width: 1.4;
}

.under {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.under-no {
  fill: var(--vp-c-danger-1);
}

.fills {
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--hmz-accent);
}

.fills .mono {
  font-size: 11px;
}

.err-text {
  font-size: 11px;
  fill: var(--vp-c-danger-1);
}

.role-name {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.role-fill {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.guide {
  stroke: var(--hmz-stage-dim);
  stroke-opacity: 0.6;
  stroke-width: 1.1;
  stroke-dasharray: 2 4;
}

.flow-bar {
  fill: var(--hmz-lane-1);
}

.flow-word {
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.flow-cap {
  fill: var(--hmz-accent);
  stroke: var(--hmz-stage-card);
  stroke-width: 2;
}

.answer-text {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.goal-line {
  stroke: var(--hmz-accent);
  stroke-width: 1.6;
  stroke-dasharray: 5 3;
}

.goal-word {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-accent);
}

.turn {
  fill: var(--hmz-lane-3);
}

.turn-word {
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.cap {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.cap.met {
  font-weight: 700;
  fill: var(--hmz-accent);
}

.met-dot {
  stroke: var(--hmz-stage-card);
  stroke-width: 1.5;
}

.met-dot.not {
  fill: var(--hmz-warm);
}

.met-dot.met {
  fill: var(--hmz-accent);
}

.answer-path {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.8;
  stroke-linecap: round;
}

.track {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.left-bar {
  fill: var(--hmz-warm);
}

.left-n {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-warm);
}

.note {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}
</style>
