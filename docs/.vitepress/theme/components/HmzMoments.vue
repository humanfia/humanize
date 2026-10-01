<script setup lang="ts">
// The moments a turn passes through, and what a hook hung on one does there, on the CLI picked.
// The moments each CLI reaches are the harness protocols in `hmz/flows/agents.py`
// (`PermissionRequestHookAgentMixin`, `AskUserHookAgentMixin`, the two subagent mixins). A tool
// refused as it is reached for stops only where the CLI waits on its own hook table for the
// answer (claude and qwen, `Gate` in `hmz/coganchor/agents/hooks.py`); where the CLI asks
// permission first and a hook is hung there, that refusal holds instead; everywhere else the hook
// hears of the tool once it has started. A hook on the end of the turn sends the agent back, told
// how often it already has. The turn itself is invented.
import { computed, nextTick, ref, watch } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, type Fx } from '../motion/fx'
import { motion } from '../motion/gsap'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'

type Rare = 'perm' | 'ask' | 'sub'

interface Cli {
  name: string
  reaches: Rare[]
  /** Waits on its own hook table as a tool is reached for, so a refusal there holds. */
  gates: boolean
}

const CLIS: Cli[] = [
  { name: 'claude', reaches: ['perm', 'ask', 'sub'], gates: true },
  { name: 'codex', reaches: ['perm', 'ask', 'sub'], gates: false },
  { name: 'kimi', reaches: ['perm', 'ask'], gates: false },
  { name: 'pi', reaches: ['ask'], gates: false },
  { name: 'cursor-agent', reaches: ['sub'], gates: false },
  { name: 'qwen', reaches: [], gates: true },
  { name: 'agy', reaches: [], gates: false },
  { name: 'dsh', reaches: [], gates: false },
  { name: 'grok', reaches: [], gates: false },
  { name: 'mcode', reaches: ['sub'], gates: false },
  { name: 'mimo', reaches: [], gates: false },
  { name: 'opencode', reaches: [], gates: false },
]

// The moments, in the order a turn meets them. The tool's is two hooks in one place: as the tool
// is reached for, and as the CLI asks whether it may run.
const MOMENTS: { words: string[]; rare?: Rare }[] = [
  { words: ['session', 'starts'] },
  { words: ['prompt'] },
  { words: ['tool'] },
  { words: ['subagent'], rare: 'sub' },
  { words: ['question'], rare: 'ask' },
  { words: ['message'] },
  { words: ['turn', 'ends'] },
  { words: ['session', 'ends'] },
]

// What each hung hook does, by moment.
const HOOKS: Record<number, string> = { 1: 'add rule', 2: 'refuse', 4: 'answer', 6: 'send back' }

const cliName = ref('claude')
const cli = computed(() => CLIS.find((one) => one.name === cliName.value) ?? CLIS[0])
const reached = (i: number) => {
  const rare = MOMENTS[i].rare
  return !rare || cli.value.reaches.includes(rare)
}
// How a refused tool goes on this CLI.
const tool = computed<'gate' | 'perm' | 'late'>(() =>
  cli.value.gates ? 'gate' : cli.value.reaches.includes('perm') ? 'perm' : 'late',
)

const BEATS = computed(() => [
  'Every turn passes the same moments',
  'A hook adds to the prompt',
  { gate: 'Refused as it is reached for', perm: 'Refused when the CLI asks', late: 'Too late here: the tool runs' }[tool.value],
  reached(4) ? 'A hook answers the agent' : 'Some moments this CLI never reaches',
  'A hook sends the agent back',
])

const label = computed(
  () =>
    `One turn on ${cli.value.name}, passing the moments a hook can hang on: the session starting, the prompt, a tool, a subagent, a question to the user, a message, the turn ending, the session ending. A hook adds a rule to the prompt. A hook refuses a tool: ${
      { gate: 'the tool never runs', perm: 'the CLI asks first, the refusal holds and the tool never runs', late: 'but it only hears of the tool once it has started, so the tool runs' }[tool.value]
    }. ${reached(4) ? 'A hook answers the question the agent asks its user.' : `${cli.value.name} never reaches some moments.`} A hook on the end of the turn sends the agent back once, then lets the turn end.`,
)

interface Layout {
  w: number
  h: number
  st: { x: number; y: number }[]
  /** Station words: one line or two, and where. */
  word: (i: number) => { x: number; y: number; anchor: string; lines: string[] }
  tag: (i: number) => { x: number; y: number }
  /** The thread from the tag to the hook, and the way the hook faces. */
  thread: (i: number) => string
  glyph: (i: number) => string
  hangFrom: { x: number; y: number }
  act: (i: number) => { x: number; y: number }
  ask: (i: number) => { x: number; y: number }
  loop: (i: number) => string
  back: string
  focus: (i: number) => { cx: number; cy: number; s: number }
  all: { cx: number; cy: number; s: number }
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

function wide(): Layout {
  const st = MOMENTS.map((_, i) => ({ x: 50 + i * 77, y: 190 }))
  const s = 1.25
  return {
    w: 640,
    h: 360,
    st,
    word: (i) => ({ x: st[i].x, y: 218, anchor: 'middle', lines: MOMENTS[i].words }),
    tag: (i) => ({ x: st[i].x, y: 82 }),
    thread: (i) => `M${st[i].x} 94 V${st[i].y - 34}`,
    glyph: (i) => `translate(${st[i].x} ${st[i].y - 34})`,
    hangFrom: { x: 0, y: -50 },
    act: (i) => ({ x: st[i].x, y: 272 }),
    ask: (i) => ({ x: st[i].x, y: 262 }),
    loop: (i) => `M${st[i].x} ${st[i].y} C${st[i].x + 70} 300 ${st[i].x - 70} 300 ${st[i].x} ${st[i].y}`,
    back: `M${st[6].x} ${st[6].y} C${st[6].x} 330 ${st[2].x} 330 ${st[2].x} ${st[2].y}`,
    focus: (i) => ({ cx: clamp(st[i].x, 320 / s, 640 - 320 / s), cy: 178, s }),
    all: { cx: 320, cy: 186, s: 1 },
  }
}

function tall(): Layout {
  const st = MOMENTS.map((_, i) => ({ x: 150, y: 80 + i * 60 }))
  const s = 1.06
  const h = 560
  return {
    w: 360,
    h,
    st,
    word: (i) => ({ x: 132, y: st[i].y + 4, anchor: 'end', lines: [MOMENTS[i].words.join(' ')] }),
    tag: (i) => ({ x: 292, y: st[i].y }),
    thread: (i) => `M${250} ${st[i].y} H${st[i].x + 30}`,
    glyph: (i) => `translate(${st[i].x + 30} ${st[i].y}) rotate(90)`,
    hangFrom: { x: 50, y: 0 },
    act: (i) => ({ x: 80, y: st[i].y + 24 }),
    ask: (i) => ({ x: 80, y: st[i].y + 29 }),
    loop: (i) => `M${st[i].x} ${st[i].y} C${st[i].x + 80} ${st[i].y - 40} ${st[i].x + 80} ${st[i].y + 40} ${st[i].x} ${st[i].y}`,
    back: `M${st[6].x} ${st[6].y} C${st[6].x + 190} ${st[6].y} ${st[2].x + 190} ${st[2].y} ${st[2].x} ${st[2].y}`,
    focus: (i) => ({ cx: 180, cy: clamp(st[i].y, 256, 300), s }),
    all: { cx: 180, cy: 282, s: 1 },
  }
}

const WIDE = wide()
const TALL = tall()

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? TALL : WIDE))

const tagWidth = (text: string) => text.length * 7 + 20

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const gsap = motion()
    const l = L.value
    const how = tool.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const at = (sel: string) => q(sel)
    const world = at('.world')[0]
    const mote = at('.mote')[0]
    const mini = at('.mini')[0]
    const S = l.st

    const shot = (c: { cx: number; cy: number; s: number }) => ({ x: l.w / 2 - c.cx * c.s, y: l.h / 2 - c.cy * c.s, scale: c.s })
    const screen = (x: number, y: number) => {
      const s = Number(gsap.getProperty(world, 'scale'))
      return { x: x * s + Number(gsap.getProperty(world, 'x')), y: y * s + Number(gsap.getProperty(world, 'y')) }
    }
    const spark = (p: { x: number; y: number }, color: () => string, n: number, when: number, speed = 90) =>
      tl.call(
        () => {
          const o = screen(p.x, p.y)
          fx?.spark(o.x, o.y, color(), n, speed)
        },
        [],
        when,
      )
    const trail = (el: Element, color: () => string, size = 2.6) => () => {
      const p = screen(Number(gsap.getProperty(el, 'x')), Number(gsap.getProperty(el, 'y')))
      fx?.trail(p.x, p.y, color(), size)
    }
    // A mote of light from a hook's tag to what it acts on.
    const beam = (from: { x: number; y: number }, to: { x: number; y: number }, color: () => string, when: number, duration = 0.45) => {
      const p = { t: 0 }
      tl.fromTo(
        p,
        { t: 0 },
        {
          t: 1,
          duration,
          ease: 'power2.in',
          onUpdate: () => {
            const o = screen(from.x + (to.x - from.x) * p.t, from.y + (to.y - from.y) * p.t)
            fx?.trail(o.x, o.y, color(), 2.8)
          },
        },
        when,
      )
      spark(to, color, 14, when + duration, 90)
    }
    const follow = (i: number, when: number, duration = 1.1) => tl.to(world, { ...shot(l.focus(i)), duration, ease: 'cine' }, when)
    const go = (i: number, when: number, duration = 0.7) =>
      tl.to(mote, { x: S[i].x, y: S[i].y, duration, ease: 'power2.inOut', onUpdate: trail(mote, () => palette.lane[0]) }, when)
    const arrive = (i: number, when: number) => {
      tl.fromTo(at('.ring')[i], { scale: 0.6, opacity: 0.9 }, { scale: 2.4, opacity: 0, duration: 0.7, ease: 'power2.out' }, when)
      spark(S[i], () => palette.lane[0], 8, when, 50)
    }
    const hookAt = (i: number) => at(`.hook-${i}`)[0]
    const flash = (i: number, warm: boolean, when: number) => {
      const el = hookAt(i).querySelector(warm ? '.tag-warm' : '.tag-cool')
      tl.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.15 }, when)
      tl.to(el, { opacity: 0, duration: 0.6 }, when + 0.9)
      tl.fromTo(hookAt(i).querySelector('.swing'), { rotation: 0 }, { keyframes: { rotation: [0, -8, 6, -3, 0] }, duration: 0.6, ease: 'none' }, when)
    }

    // Where a loop starts.
    tl.set(world, { svgOrigin: '0 0', ...shot({ ...l.all, s: l.all.s * 1.08 }), autoAlpha: 1 }, 0)
    tl.set(at('.ring, .tool, .ask-bubble, .perm-bubble, .counter, .dot'), { transformOrigin: '50% 50%', smoothOrigin: false }, 0)
    tl.set(at('.swing'), { transformOrigin: '50% 0%', smoothOrigin: false }, 0)
    tl.set(at('.mote, .mini, .mote-rule, .tool, .tool-x, .tool-fill, .verdict, .ask-bubble, .answer-text, .perm-bubble, .counter, .back, .tag-warm, .tag-cool, .ring'), { opacity: 0 }, 0)
    tl.set(at('.question-text'), { opacity: 1 }, 0)
    tl.set(at('.tool-fill'), { scaleX: 0, transformOrigin: '0% 50%', smoothOrigin: false }, 0)
    tl.set(mote, { x: S[0].x, y: S[0].y, scale: 1 }, 0)

    // 0 · the turn laid out, and the hooks hung on it.
    tl.addLabel('beat-0', 0)
    tl.to(world, { ...shot(l.all), duration: 2.6, ease: 'cine' }, 0)
    tl.fromTo(at('.rail'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.3, ease: 'cine' }, 0.1)
    tl.fromTo(at('.dot'), { scale: 0 }, { scale: 1, duration: 0.45, stagger: 0.09, ease: 'back.out(2.5)' }, 0.3)
    tl.fromTo(at('.word'), { opacity: 0 }, { opacity: 1, duration: 0.5, stagger: 0.09 }, 0.5)
    tl.fromTo(at('.thread'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.6, stagger: 0.18, ease: 'power2.out' }, 1.1)
    tl.fromTo(at('.hang'), { x: l.hangFrom.x, y: l.hangFrom.y, opacity: 0 }, { x: 0, y: 0, opacity: 1, duration: 0.8, stagger: 0.18, ease: 'bounce.out' }, 1.1)
    tl.fromTo(at('.tag'), { opacity: 0 }, { opacity: 1, duration: 0.4, stagger: 0.18 }, 1.2)
    tl.to(mote, { opacity: 1, duration: 0.3 }, 2.6)
    arrive(0, 2.6)
    follow(1, 2.8, 1.3)

    // 1 · the prompt goes out with the hook's rule on it.
    const T1 = 3.2
    tl.addLabel('beat-1', T1)
    go(1, T1)
    arrive(1, T1 + 0.7)
    flash(1, false, T1 + 0.8)
    beam(l.tag(1), S[1], () => palette.accent, T1 + 0.85)
    tl.fromTo(at('.mote-rule'), { opacity: 0, scale: 2 }, { opacity: 1, scale: 1, duration: 0.45, ease: 'back.out(2)' }, T1 + 1.3)

    // 2 · a tool reached for, and refused -- in time, or not.
    const T2 = T1 + 2.1
    tl.addLabel('beat-2', T2)
    follow(2, T2 - 0.2)
    go(2, T2)
    arrive(2, T2 + 0.7)
    const chip = l.act(2)
    tl.fromTo(at('.tool'), { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, T2 + 0.8)
    let end: number
    if (how === 'late') {
      // It has started before the hook hears of it; the refusal arrives after it ran.
      tl.to(at('.tool-fill'), { opacity: 1, duration: 0.1 }, T2 + 1.1)
      tl.to(at('.tool-fill'), { scaleX: 1, duration: 1, ease: 'power1.inOut' }, T2 + 1.1)
      flash(2, true, T2 + 1.5)
      beam(l.tag(2), chip, () => palette.warm, T2 + 1.55, 0.6)
      tl.set(at('.verdict-ran'), { opacity: 1 }, T2 + 2.2)
      tl.fromTo(at('.verdict-ran'), { y: 6 }, { y: 0, duration: 0.3 }, T2 + 2.2)
      end = T2 + 3
    } else {
      let when = T2 + 1.2
      if (how === 'perm') {
        tl.fromTo(at('.perm-bubble'), { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1, duration: 0.35, ease: 'back.out(2)' }, T2 + 1.1)
        when = T2 + 1.7
      }
      flash(2, true, when)
      beam(l.tag(2), chip, () => palette.warm, when + 0.05, 0.5)
      tl.fromTo(at('.tool-x'), { opacity: 1, drawSVG: '0%' }, { drawSVG: '100%', duration: 0.2, stagger: 0.1 }, when + 0.55)
      tl.to(at('.tool'), { keyframes: { x: [0, -5, 5, -3, 3, 0] }, duration: 0.35, ease: 'none' }, when + 0.55)
      spark(chip, () => palette.danger, 30, when + 0.6, 140)
      tl.to(at('.tool'), { opacity: 0.35, duration: 0.4 }, when + 0.9)
      tl.to(at('.perm-bubble'), { opacity: 0, duration: 0.3 }, when + 0.9)
      tl.set(at('.verdict-stopped'), { opacity: 1 }, when + 0.9)
      tl.fromTo(at('.verdict-stopped'), { y: 6 }, { y: 0, duration: 0.3 }, when + 0.9)
      end = when + 1.7
    }

    // 3 · a subagent and a question -- where this CLI reaches them.
    const T3 = end
    tl.addLabel('beat-3', T3)
    follow(4, T3 - 0.1, 1.6)
    go(3, T3)
    let t = T3 + 0.7
    if (reached(3)) {
      arrive(3, t)
      tl.set(mini, { x: S[3].x, y: S[3].y }, t)
      tl.to(mini, { opacity: 1, duration: 0.15 }, t)
      tl.to(mini, { motionPath: { path: l.loop(3), start: 0, end: 1 }, duration: 1.1, ease: 'power1.inOut', onUpdate: trail(mini, () => palette.lane[2], 2) }, t)
      tl.to(mini, { opacity: 0, duration: 0.15 }, t + 1.05)
      t += 1.2
    } else {
      tl.fromTo(at('.station')[3], { opacity: 0.45 }, { keyframes: { opacity: [0.45, 0.15, 0.45, 0.15, 0.45] }, duration: 0.6, ease: 'none' }, T3 + 0.2)
    }
    go(4, t)
    t += 0.7
    if (reached(4)) {
      arrive(4, t)
      tl.fromTo(at('.ask-bubble'), { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1, duration: 0.35, ease: 'back.out(2)' }, t + 0.1)
      flash(4, false, t + 0.7)
      beam(l.tag(4), l.ask(4), () => palette.accent, t + 0.75)
      tl.to(at('.question-text'), { opacity: 0, duration: 0.2 }, t + 1.2)
      tl.to(at('.answer-text'), { opacity: 1, duration: 0.3 }, t + 1.25)
      t += 2
    } else {
      tl.fromTo(at('.station')[4], { opacity: 0.45 }, { keyframes: { opacity: [0.45, 0.15, 0.45, 0.15, 0.45] }, duration: 0.6, ease: 'none' }, t - 0.5)
      t += 0.3
    }

    // 4 · the turn would end; the hook sends it back once, then lets it.
    go(5, t)
    arrive(5, t + 0.7)
    const T4 = t + 0.8
    tl.addLabel('beat-4', T4)
    follow(6, T4 - 0.3)
    go(6, T4)
    arrive(6, T4 + 0.7)
    flash(6, true, T4 + 0.8)
    beam(l.tag(6), S[6], () => palette.warm, T4 + 0.85)
    tl.fromTo(at('.back'), { opacity: 1, drawSVG: '0%' }, { drawSVG: '100%', duration: 0.6, ease: 'power2.out' }, T4 + 1.2)
    follow(3, T4 + 1.3, 1.2)
    tl.to(mote, { motionPath: { path: l.back, start: 0, end: 1 }, duration: 1.2, ease: 'power2.inOut', onUpdate: trail(mote, () => palette.warm) }, T4 + 1.3)
    tl.fromTo(at('.counter'), { opacity: 0, scale: 1.5 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, T4 + 1.4)
    tl.to(at('.back'), { opacity: 0, duration: 0.5 }, T4 + 2.4)
    arrive(2, T4 + 2.5)
    follow(6, T4 + 2.6, 1.2)
    tl.to(mote, { x: S[6].x, y: S[6].y, duration: 1.2, ease: 'power1.inOut', onUpdate: trail(mote, () => palette.lane[0]) }, T4 + 2.6)
    arrive(6, T4 + 3.8)
    flash(6, false, T4 + 3.9)
    go(7, T4 + 4.3)
    arrive(7, T4 + 5)
    spark(S[7], () => palette.accent, 26, T4 + 5, 120)
    tl.to(mote, { opacity: 0, scale: 0.4, duration: 0.4 }, T4 + 5)

    // Pull back over the whole turn, hold, and fade for the loop.
    tl.to(world, { ...shot(l.all), duration: 1.5, ease: 'cine' }, T4 + 5.1)
    tl.addLabel('rest', T4 + 6.8)
    tl.to(world, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 8.8)
  },
})

watch(cliName, () => void nextTick(() => scene.rebuild()))
</script>

<template>
  <HmzStage :scene="scene" :beats="BEATS" sim interactive mobile-ratio="9 / 14" :label="label">
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <radialGradient id="hmz-moments-mote">
          <stop offset="0" stop-color="var(--hmz-lane-1)" stop-opacity="0.85" />
          <stop offset="1" stop-color="var(--hmz-lane-1)" stop-opacity="0" />
        </radialGradient>
      </defs>
      <g class="world">
        <path class="rail" :d="`M${L.st[0].x} ${L.st[0].y} L${L.st[7].x} ${L.st[7].y}`" />
        <path class="back" :d="L.back" />

        <g v-for="(m, i) in MOMENTS" :key="i" class="station" :class="{ absent: !reached(i) }">
          <circle class="ring" :cx="L.st[i].x" :cy="L.st[i].y" r="10" />
          <g :transform="`translate(${L.st[i].x} ${L.st[i].y})`"><circle class="dot" r="7" /></g>
          <text class="word" :x="L.word(i).x" :y="L.word(i).y" :text-anchor="L.word(i).anchor">
            <tspan v-for="(line, k) in L.word(i).lines" :key="k" :x="L.word(i).x" :dy="k ? 14 : 0">{{ line }}</tspan>
          </text>
        </g>

        <g v-for="(text, i) in HOOKS" :key="`h${i}`" :class="['hook', `hook-${i}`, { absent: !reached(Number(i)) }]">
          <path class="thread" :d="L.thread(Number(i))" />
          <g class="hang">
            <g :transform="L.glyph(Number(i))"><g class="swing">
              <path class="glyph" d="M0 -6 V4 a5 5 0 0 1 -10 0" />
            </g></g>
            <g class="tag" :transform="`translate(${L.tag(Number(i)).x} ${L.tag(Number(i)).y})`">
              <rect class="tag-box" :x="-tagWidth(text) / 2" y="-12" :width="tagWidth(text)" height="24" rx="12" />
              <rect class="tag-cool" :x="-tagWidth(text) / 2" y="-12" :width="tagWidth(text)" height="24" rx="12" />
              <rect class="tag-warm" :x="-tagWidth(text) / 2" y="-12" :width="tagWidth(text)" height="24" rx="12" />
              <text y="4" text-anchor="middle">{{ text }}</text>
            </g>
          </g>
        </g>

        <!-- the tool reached for, and what became of it -->
        <g :transform="`translate(${L.act(2).x} ${L.act(2).y})`">
          <g :transform="narrow ? 'translate(0 -46)' : 'translate(0 -24)'"><g class="perm-bubble">
            <rect x="-44" y="-10" width="88" height="20" rx="10" />
            <text y="4" text-anchor="middle">may it run?</text>
          </g></g>
          <g class="tool">
            <rect class="tool-box" x="-48" y="-12" width="96" height="24" rx="6" />
            <rect class="tool-fill" x="-48" y="-12" width="96" height="24" rx="6" />
            <text y="4" text-anchor="middle">delete build/</text>
            <line class="tool-x" x1="-9" y1="-9" x2="9" y2="9" />
            <line class="tool-x" x1="9" y1="-9" x2="-9" y2="9" />
          </g>
          <text class="verdict verdict-stopped" :y="narrow ? 21 : 28" text-anchor="middle">never ran</text>
          <text class="verdict verdict-ran" :y="narrow ? 21 : 28" text-anchor="middle">ran · too late</text>
        </g>

        <!-- the question, and the hook's answer -->
        <g :transform="`translate(${L.ask(4).x} ${L.ask(4).y})`">
          <g class="ask-bubble">
            <rect x="-58" y="-11" width="116" height="22" rx="11" />
            <text class="question-text" y="4" text-anchor="middle">drop the column?</text>
            <text class="answer-text" y="4" text-anchor="middle">no, keep it</text>
          </g>
        </g>

        <g :transform="`translate(${L.act(6).x} ${L.act(6).y})`">
          <text class="counter" y="4" text-anchor="middle">sent back 1</text>
        </g>

        <g class="mini"><circle r="4" /></g>
        <g class="mote">
          <circle class="mote-halo" r="18" fill="url(#hmz-moments-mote)" />
          <circle class="mote-rule" r="10" />
          <circle class="mote-core" r="6" />
        </g>
      </g>
    </svg>
    <canvas ref="canvas" />
    <div class="layer pick">
      <label>
        <span>CLI</span>
        <select v-model="cliName" aria-label="The CLI the turn runs on">
          <option v-for="one in CLIS" :key="one.name" :value="one.name">{{ one.name }}</option>
        </select>
      </label>
    </div>
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.rail {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 3;
  stroke-linecap: round;
}

.back {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 1.5;
  stroke-dasharray: 4 4;
}

.dot {
  fill: var(--hmz-lane-1);
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
}

.ring {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.5;
}

.word {
  font-size: 12px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.station.absent .dot {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-dasharray: 2 2.4;
}

.station.absent .word {
  fill: var(--hmz-stage-dim);
  text-decoration: line-through;
}

.station.absent {
  opacity: 0.45;
}

.hook.absent {
  opacity: 0.3;
}

.hook.absent .tag text {
  text-decoration: line-through;
}

.thread {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1;
  stroke-dasharray: 1 3;
  stroke-linecap: round;
}

.glyph {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2.4;
  stroke-linecap: round;
}

.tag-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.2;
}

.tag-cool {
  fill: color-mix(in srgb, var(--hmz-accent) 30%, var(--hmz-stage-card));
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.tag-warm {
  fill: color-mix(in srgb, var(--hmz-warm) 30%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
  stroke-width: 2;
}

.tag text {
  font-size: 11.5px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}

.tool-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.2;
}

.tool-fill {
  fill: color-mix(in srgb, var(--hmz-warm) 45%, transparent);
}

.tool text {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.tool-x {
  stroke: var(--hmz-lane-5);
  stroke-width: 3;
  stroke-linecap: round;
}

.verdict {
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.verdict-stopped {
  fill: var(--hmz-accent);
}

.verdict-ran {
  fill: var(--hmz-warm);
}

.perm-bubble rect,
.ask-bubble rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-3);
  stroke-width: 1.2;
}

.perm-bubble text,
.ask-bubble text {
  font-size: 11.5px;
  font-style: italic;
  fill: var(--hmz-stage-ink);
}

.ask-bubble .answer-text {
  font-style: normal;
  font-weight: 650;
  fill: var(--hmz-accent);
}

.counter {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-warm);
}

.mote-halo {
  opacity: var(--hmz-glow);
}

.mote-core {
  fill: var(--hmz-lane-1);
}

.mote-rule {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.mini circle {
  fill: var(--hmz-lane-3);
}

.pick {
  z-index: 6;
  pointer-events: none;
}

.pick label {
  position: absolute;
  top: 10px;
  left: 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px 2px 10px;
  border: 1px solid var(--hmz-stage-line);
  border-radius: 999px;
  background: var(--hmz-stage-card);
  pointer-events: auto;
}

.pick span {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--hmz-stage-dim);
}

.pick select {
  padding: 2px 6px;
  border: 0;
  background: transparent;
  color: var(--hmz-stage-ink);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.pick select option {
  color: var(--vp-c-text-1);
  background: var(--vp-c-bg);
}
</style>
