<script setup lang="ts">
// The person, asked for a shape. One question per field, in the order the model declares them:
// the description is the question, a Literal or a bool lists its words under it, a number says
// `(a number)`, a default is "-- or `-` for <it>" (`_asking` in
// `src/hmz/coganchor/agents/human.py`). What is typed is held as typed, and the model reads all
// of it at once when every field has an answer: pydantic turns `careful` into 'careful' and
// `yes` into True, and a field it refuses is asked again with its own message above it
// (`HumanSession._filled`). Nobody there -- `/afk`, or `hmz exec` -- and the flow is answered
// at once: with the defaults where every field has one, with `OutworlderAway` where not
// (`away_answer` in `src/hmz/runtime/flowing/viewing.py`). The toggle over the scene picks
// which of those two shapes the flow declared. The flow and its answers are drawn.
import { computed, nextTick, ref, watch } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'

const everyDefault = ref(false)

const BEATS = computed(() => [
  'The flow asks you for a shape',
  'One question per field',
  'Read together; one is refused',
  'Your answers land as its fields',
  everyDefault.value ? 'Away: its defaults answer at once' : 'Away, with no default: it fails',
])

interface Field {
  name: string
  asks: string
  options: string[]
  /** What the flow falls back to, as a person is told it and as the model holds it. */
  told: string
  held: string
  typed: string
  read: string
}

const FIELDS: Field[] = [
  { name: 'approach', asks: 'Which way should this be built?', options: ['fast', 'careful'], told: 'careful', held: "'careful'", typed: 'careful', read: "'careful'" },
  { name: 'tests', asks: 'Write tests for it?', options: ['yes', 'no'], told: 'yes', held: 'True', typed: 'yes', read: 'True' },
  { name: 'rounds', asks: 'How many rounds may it take?', options: [], told: '3', held: '3', typed: 'three', read: '4' },
]

const defaulted = (i: number) => everyDefault.value || i === 2

// The questions as the prompt puts them: the three fields, then the one refused, again.
const QUESTIONS = computed(() =>
  [0, 1, 2, 2].map((f, n) => {
    const one = FIELDS[f]
    let hint = one.options.length ? '' : '(a number)'
    if (defaulted(f)) hint += `${hint ? ' ' : ''}-- or \`-\` for ${one.told}`
    const about =
      n === 0 ? ['Before the builder starts:'] : n === 3 ? ['Input should be a valid integer,', 'unable to parse string as an integer'] : []
    return { field: f, asks: one.asks, hint, options: one.options, about, refused: n === 3, answer: n === 3 ? '4' : one.typed }
  }),
)

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Layout {
  w: number
  h: number
  card: Box
  panel: Box
  glyph: { x: number; y: number }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  card: { x: 22, y: 62, w: 262, h: 222 },
  panel: { x: 322, y: 78, w: 298, h: 226 },
  glyph: { x: 336, y: 56 },
}

const NARROW: Layout = {
  w: 360,
  h: 530,
  card: { x: 14, y: 40, w: 332, h: 222 },
  panel: { x: 14, y: 310, w: 332, h: 204 },
  glyph: { x: 28, y: 290 },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

// Everything else is placed off the card and the panel.
const G = computed(() => {
  const { card, panel } = L.value
  const shape = { x: card.x + 14, y: card.y + 64, w: card.w - 28, h: 142 }
  const slotW = 104
  return {
    bar: { x1: card.x + 16, x2: card.x + card.w - 16, y: card.y + 42 },
    shape,
    field: FIELDS.map((_, i) => ({ y: shape.y + 56 + i * 30 })),
    slot: { x: shape.x + shape.w - 12 - slotW, w: slotW },
    q: {
      x: panel.x + 16,
      about: panel.y + 28,
      asks: panel.y + 66,
      hint: panel.y + 86,
      option: panel.y + 112,
    },
    input: { x: panel.x + 12, y: panel.y + panel.h - 46, w: panel.w - 24, h: 34 },
  }
})

// The flow's progress bar: where it stops to ask, twice.
const STOP1 = 0.38
const STOP2 = 0.7

const scene = useScene({
  still: 'rest',
  repeatDelay: 0.8,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    const g = G.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const at = (sel: string) => q(sel)
    const world = at('.world')
    const values = at('.value')
    const holders = at('.holder')
    const ticks = at('.tick')
    const barW = g.bar.x2 - g.bar.x1
    const barAt = (f: number) => ({ x: g.bar.x1 + barW * f, y: g.bar.y })
    const slotAt = (i: number) => ({ x: g.slot.x + g.slot.w / 2, y: g.field[i].y - 4 })
    const shapeEdge = { x: g.shape.x + g.shape.w, y: g.shape.y + 20 }
    const you = { x: l.glyph.x, y: l.glyph.y }
    const inputAt = { x: g.input.x + 40, y: g.input.y + g.input.h / 2 }

    // Clean slate for every loop.
    tl.set(at('.q, .now, .tick, .cross, .stamp, .away, .check, .scan, .glow, .result, .bar-bad'), { autoAlpha: 0 }, 0)
    tl.set(at('.holder'), { autoAlpha: 1 }, 0)
    tl.set(values, { text: '', autoAlpha: 1 }, 0)
    tl.set(at('.typed'), { text: '' }, 0)
    tl.set(at('.bar-fill'), { attr: { width: 0 } }, 0)
    tl.set(at('.bar-head'), { attr: { cx: g.bar.x1 } }, 0)
    tl.set(at('.person'), { opacity: 1 }, 0)
    tl.set(values[2], { attr: { class: 'value t-value' } }, 0)
    tl.set(at('.status'), { text: 'running' }, 0)
    tl.set(at('.option-lit'), { autoAlpha: 0 }, 0)
    tl.set(at('.card-side, .you-side'), { scale: 1, opacity: 1, transformOrigin: '50% 50%' }, 0)

    // Rack focus: one side comes forward, the other falls back.
    function focus(near: string, far: string, when: number) {
      tl.to(at(near), { scale: 1.03, opacity: 1, duration: 1.2, ease: 'cine' }, when)
      tl.to(at(far), { scale: 0.97, opacity: 0.55, duration: 1.2, ease: 'cine' }, when)
    }

    // 0 · the flow runs, stops, and asks you for a shape.
    tl.addLabel('beat-0', 0)
    tl.fromTo(world, { scale: 1.1, transformOrigin: '50% 45%' }, { scale: 1, duration: 2.6, ease: 'cine' }, 0)
    tl.fromTo(at('.card-line, .panel-line'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.3, stagger: 0.2, ease: 'cine' }, 0)
    tl.to(at('.bar-fill'), { attr: { width: barW * STOP1 }, duration: 1.3, ease: 'power1.inOut' }, 0.2)
    tl.to(at('.bar-head'), { attr: { cx: barAt(STOP1).x }, duration: 1.3, ease: 'power1.inOut' }, 0.2)
    tl.set(at('.status'), { text: 'waiting on you' }, 1.5)
    tl.fromTo(at('.shape'), { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: 0.7 }, 1.0)
    tl.fromTo(at('.row'), { autoAlpha: 0, x: -8 }, { autoAlpha: 1, x: 0, duration: 0.4, stagger: 0.12 }, 1.3)
    const toYou = 1.8
    streakLine(shapeEdge, you, () => palette.accent2, toYou, 0.7, 20)
    tl.fromTo(at('.person-halo'), { autoAlpha: 0, scale: 0.5, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.6 }, toYou + 0.6)

    // 1 · one question per field; each answer is written in its field, as typed.
    const T1 = 2.7
    tl.addLabel('beat-1', T1)
    focus('.you-side', '.card-side', T1)
    const ask = (n: number, t: number) => {
      const field = QUESTIONS.value[n].field
      tl.fromTo(at('.q')[n], { autoAlpha: 0, x: 18 }, { autoAlpha: 1, x: 0, duration: 0.5 }, t)
      tl.to(at('.now')[field], { autoAlpha: 1, duration: 0.3 }, t)
      const answer = QUESTIONS.value[n].answer
      const typing = answer.length / 16
      tl.set(at('.typed'), { text: '' }, t + 0.7)
      tl.to(at('.typed'), { text: { value: answer }, duration: typing, ease: 'none' }, t + 0.7)
      const pick = QUESTIONS.value[n].options.indexOf(answer)
      if (pick >= 0) tl.to(at(`.q-${n} .option-lit`)[pick], { autoAlpha: 1, duration: 0.2 }, t + 0.7 + typing)
      const sent = t + 0.9 + typing
      tl.set(at('.typed'), { text: '' }, sent)
      streakLine(inputAt, slotAt(field), () => palette.accent2, sent, 0.6, 12)
      tl.set(values[field], { text: answer }, sent + 0.55)
      tl.fromTo(values[field], { autoAlpha: 0, scale: 1.4, transformOrigin: '0% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, sent + 0.55)
      tl.to(holders[field], { autoAlpha: 0, duration: 0.2 }, sent + 0.5)
      tl.to(at('.now')[field], { autoAlpha: 0, duration: 0.3 }, sent + 0.8)
      tl.to(at('.q')[n], { autoAlpha: 0, x: -18, duration: 0.3, ease: 'cine.in' }, sent + 0.75)
      return sent + 1.35
    }
    let t = ask(0, T1)
    t = ask(1, t)
    t = ask(2, t)

    // 2 · every field has an answer: the model reads them together, and refuses one.
    const T2 = t + 0.1
    tl.addLabel('beat-2', T2)
    focus('.card-side', '.you-side', T2 - 0.2)
    tl.fromTo(at('.scan'), { autoAlpha: 1, attr: { y: g.shape.y + 30 } }, { attr: { y: g.shape.y + g.shape.h - 8 }, duration: 0.9, ease: 'power1.inOut' }, T2)
    tl.to(at('.scan'), { autoAlpha: 0, duration: 0.2 }, T2 + 0.9)
    FIELDS.forEach((f, i) => {
      const moment = T2 + 0.25 + i * 0.25
      if (i < 2) {
        tl.set(values[i], { text: f.read }, moment)
        tl.fromTo(ticks[i], { autoAlpha: 0, scale: 0, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(3)' }, moment)
      }
    })
    const wrong = T2 + 0.75
    tl.fromTo(at('.cross'), { autoAlpha: 0, scale: 0, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(3)' }, wrong)
    tl.set(values[2], { attr: { class: 'value t-value bad' } }, wrong)
    tl.fromTo(at('.row')[2], { x: 0 }, { keyframes: { x: [0, -5, 5, -3, 3, 0] }, duration: 0.4, ease: 'none' }, wrong)
    tl.call(() => fx?.spark(slotAt(2).x, slotAt(2).y, palette.danger, 22, 100), [], wrong)
    streakLine(slotAt(2), { x: g.q.x + 20, y: g.q.about }, () => palette.danger, wrong + 0.3, 0.6, 10)
    tl.to(at('.card-side, .you-side'), { scale: 1, opacity: 1, duration: 0.8, ease: 'cine' }, wrong + 0.4)
    t = ask(3, wrong + 0.8)
    tl.addLabel('rest', wrong + 1.6)
    tl.set(values[2], { attr: { class: 'value t-value' } }, t - 0.55)
    tl.to(at('.cross'), { autoAlpha: 0, duration: 0.2 }, t - 0.6)
    tl.fromTo(ticks[2], { autoAlpha: 0, scale: 0, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(3)' }, t - 0.2)

    // 3 · the shape is whole, and goes back to the flow as its fields; the flow goes on.
    const T3 = t + 0.3
    tl.addLabel('beat-3', T3)
    tl.to(at('.card-side, .you-side'), { scale: 1, opacity: 1, duration: 1.2, ease: 'cine' }, T3 + 0.6)
    tl.fromTo(at('.shape-glow'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3, yoyo: true, repeat: 1 }, T3)
    tl.to(at('.check'), { autoAlpha: 1, duration: 0.3 }, T3 + 0.1)
    tl.to(at('.person-halo'), { autoAlpha: 0, duration: 0.6 }, T3)
    streakLine({ x: g.shape.x + 40, y: g.shape.y + 8 }, barAt(STOP1), () => palette.accent, T3 + 0.2, 0.6, 24)
    tl.set(at('.status'), { text: 'running' }, T3 + 0.8)
    tl.to(at('.bar-fill'), { attr: { width: barW * STOP2 }, duration: 1.6, ease: 'power1.inOut' }, T3 + 0.8)
    tl.to(at('.bar-head'), { attr: { cx: barAt(STOP2).x }, duration: 1.6, ease: 'power1.inOut' }, T3 + 0.8)

    // 4 · you go away, and the flow asks again: nobody is asked, and it is answered at once.
    const T4 = T3 + 2.6
    tl.addLabel('beat-4', T4)
    tl.to(at('.card-side'), { scale: 1.03, duration: 1.4, ease: 'cine' }, T4 + 0.4)
    tl.to(at('.person'), { opacity: 0.35, duration: 0.5 }, T4)
    tl.fromTo(at('.away'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.4 }, T4 + 0.1)
    tl.set(at('.status'), { text: 'asking again' }, T4 + 0.5)
    tl.to(at('.check'), { autoAlpha: 0, duration: 0.2 }, T4 + 0.4)
    tl.to(at('.tick'), { autoAlpha: 0, duration: 0.2 }, T4 + 0.4)
    tl.to(values, { autoAlpha: 0, duration: 0.3 }, T4 + 0.4)
    tl.to(holders, { autoAlpha: 1, duration: 0.3 }, T4 + 0.6)
    streakLine(shapeEdge, you, () => palette.accent2, T4 + 0.8, 0.55, 0)
    streakLine(you, shapeEdge, () => palette.dim, T4 + 1.35, 0.45, 0)
    const back = T4 + 1.85
    if (everyDefault.value) {
      FIELDS.forEach((f, i) => {
        tl.set(values[i], { text: f.held }, back + i * 0.12)
        tl.to(holders[i], { autoAlpha: 0, duration: 0.15 }, back + i * 0.12)
        tl.fromTo(values[i], { autoAlpha: 0, scale: 1.4, transformOrigin: '0% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(2)' }, back + i * 0.12)
      })
      tl.to(at('.result-ok'), { autoAlpha: 1, duration: 0.4 }, back + 0.4)
      streakLine({ x: g.shape.x + 40, y: g.shape.y + 8 }, barAt(STOP2), () => palette.accent, back + 0.5, 0.5, 24)
      tl.set(at('.status'), { text: 'running' }, back + 1)
      tl.to(at('.bar-fill'), { attr: { width: barW }, duration: 1.4, ease: 'power1.inOut' }, back + 1)
      tl.to(at('.bar-head'), { attr: { cx: g.bar.x2 }, duration: 1.4, ease: 'power1.inOut' }, back + 1)
    } else {
      tl.fromTo(at('.stamp'), { autoAlpha: 0, scale: 1.5, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(1.6)' }, back)
      tl.call(() => fx?.spark(g.shape.x + g.shape.w / 2, g.shape.y + g.shape.h / 2, palette.danger, 36, 140), [], back + 0.1)
      tl.fromTo(at('.card-shake'), { x: 0 }, { keyframes: { x: [0, -6, 6, -4, 4, 0] }, duration: 0.45, ease: 'none' }, back + 0.1)
      tl.set(at('.status'), { text: 'failed' }, back + 0.1)
      tl.fromTo(at('.bar-bad'), { autoAlpha: 0, scale: 2.4, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4 }, back + 0.1)
    }
    const END = back + 3.2
    tl.to(at('.card-side'), { scale: 1, duration: 0.6 }, END)
    tl.to(world, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, END)
    tl.set(world, { autoAlpha: 1 }, 0)

    function streakLine(from: { x: number; y: number }, to: { x: number; y: number }, color: () => string, when: number, duration: number, burst: number) {
      const p = { t: 0 }
      const cx = (from.x + to.x) / 2
      const cy = Math.min(from.y, to.y) - 30
      tl.fromTo(
        p,
        { t: 0 },
        {
          t: 1,
          duration,
          ease: 'cine',
          onUpdate: () => {
            const k = p.t
            const u = 1 - k
            fx?.trail(u * u * from.x + 2 * u * k * cx + k * k * to.x, u * u * from.y + 2 * u * k * cy + k * k * to.y, color(), 2.6)
          },
          onComplete: () => {
            if (burst) fx?.spark(to.x, to.y, color(), burst, 70)
          },
        },
        when,
      )
    }
  },
})

watch(everyDefault, () => void nextTick(() => scene.rebuild()))

const label = computed(
  () =>
    'A flow stops and asks you for a shape, Settled, with three fields. You get one question per field: approach, fast or careful; tests, yes or no; rounds, a number. You type careful, yes and three. The model reads them together: careful and yes are taken, as careful and True; three is refused, and asked again with the reason above it. You type 4, and the three fields go back to the flow, which carries on. Then you are away, and the flow asks again: nobody is asked, and ' +
    (everyDefault.value
      ? 'since every field has a default, the flow gets the defaults at once.'
      : 'since two fields have no default, the flow fails with OutworlderAway.'),
)

function optionWidth(text: string) {
  return (text.length + 3) * 7.6 + 18
}
</script>

<template>
  <div class="person-scene">
    <div class="pick" role="group" aria-label="What the flow's shape falls back to">
      <span>defaults on</span>
      <button type="button" :aria-pressed="!everyDefault" :class="{ on: !everyDefault }" @click="everyDefault = false">rounds only</button>
      <button type="button" :aria-pressed="everyDefault" :class="{ on: everyDefault }" @click="everyDefault = true">every field</button>
    </div>
    <HmzStage :scene="scene" :beats="BEATS" sim mobile-ratio="36 / 53" :label="label">
      <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
        <defs>
          <radialGradient id="person-halo">
            <stop offset="0" stop-color="var(--hmz-accent-2)" stop-opacity="0.5" />
            <stop offset="1" stop-color="var(--hmz-accent-2)" stop-opacity="0" />
          </radialGradient>
          <radialGradient id="person-shape-glow">
            <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.35" />
            <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
          </radialGradient>
        </defs>
        <g class="world">
          <!-- the flow, and the shape it asked for -->
          <g class="card-side"><g class="card-shake">
            <rect class="card-bg" :x="L.card.x" :y="L.card.y" :width="L.card.w" :height="L.card.h" rx="14" />
            <rect class="card-line" :x="L.card.x" :y="L.card.y" :width="L.card.w" :height="L.card.h" rx="14" />
            <text class="t-title" :x="L.card.x + 16" :y="L.card.y + 26">flow</text>
            <text class="t-status status" :x="L.card.x + L.card.w - 16" :y="L.card.y + 26" text-anchor="end">running</text>
            <rect class="bar-slot" :x="G.bar.x1" :y="G.bar.y - 3" :width="G.bar.x2 - G.bar.x1" height="6" rx="3" />
            <rect class="bar-fill" :x="G.bar.x1" :y="G.bar.y - 3" width="0" height="6" rx="3" />
            <circle class="bar-head" :cx="G.bar.x1" :cy="G.bar.y" r="5" />
            <circle class="bar-bad" :cx="G.bar.x1 + (G.bar.x2 - G.bar.x1) * STOP2" :cy="G.bar.y" r="6" />

            <ellipse
              class="shape-glow glow"
              :cx="G.shape.x + G.shape.w / 2"
              :cy="G.shape.y + G.shape.h / 2"
              :rx="G.shape.w * 0.75"
              :ry="G.shape.h * 0.8"
              fill="url(#person-shape-glow)"
            />
            <g class="shape">
              <rect class="shape-box" :x="G.shape.x" :y="G.shape.y" :width="G.shape.w" :height="G.shape.h" rx="10" />
              <text class="t-shape" :x="G.shape.x + 12" :y="G.shape.y + 24">Settled</text>
              <text class="check t-ok" :x="G.shape.x + 80" :y="G.shape.y + 24">✓</text>
              <text class="result result-ok t-dim" :x="G.shape.x + G.shape.w - 12" :y="G.shape.y + 24" text-anchor="end">defaults</text>
              <rect class="scan" :x="G.shape.x + 6" :width="G.shape.w - 12" height="2" rx="1" :y="G.shape.y + 30" />
              <g v-for="(f, i) in FIELDS" :key="f.name" class="row">
                <rect class="now" :x="G.shape.x + 4" :y="G.field[i].y - 19" width="3" height="22" rx="1.5" />
                <text class="t-field" :x="G.shape.x + 14" :y="G.field[i].y">{{ f.name }}</text>
                <rect class="slot" :x="G.slot.x" :y="G.field[i].y - 19" :width="G.slot.w" height="22" rx="6" />
                <text class="holder t-dim" :x="G.slot.x + 10" :y="G.field[i].y - 4">{{ defaulted(i) ? `= ${f.held}` : '—' }}</text>
                <text class="value t-value" :x="G.slot.x + 10" :y="G.field[i].y - 4" />
                <text class="tick t-ok" :x="G.slot.x + G.slot.w - 16" :y="G.field[i].y - 3">✓</text>
                <text v-if="i === 2" class="cross t-bad" :x="G.slot.x + G.slot.w - 16" :y="G.field[i].y - 3">✗</text>
              </g>
              <g :transform="`translate(${G.shape.x + G.shape.w / 2} ${G.shape.y + G.shape.h / 2 + 4})`"><g class="stamp">
                <rect :x="-100" y="-17" width="200" height="34" rx="17" />
                <text y="5" text-anchor="middle">OutworlderAway</text>
              </g></g>
            </g>
          </g></g>

          <!-- you, and the prompt the questions come to -->
          <g class="you-side">
          <g class="person">
            <circle class="person-halo" :cx="L.glyph.x" :cy="L.glyph.y" r="30" fill="url(#person-halo)" />
            <circle class="person-head" :cx="L.glyph.x" :cy="L.glyph.y - 5" r="5" />
            <path class="person-body" :d="`M ${L.glyph.x - 9} ${L.glyph.y + 9} a 9 8 0 0 1 18 0`" />
            <text class="t-title t-you" :x="L.glyph.x + 16" :y="L.glyph.y + 5">you</text>
          </g>
          <g :transform="`translate(${L.glyph.x + 62} ${L.glyph.y})`"><g class="away">
            <rect x="0" y="-11" width="44" height="20" rx="10" />
            <text x="22" y="3" text-anchor="middle">/afk</text>
          </g></g>
          <rect class="panel-bg" :x="L.panel.x" :y="L.panel.y" :width="L.panel.w" :height="L.panel.h" rx="14" />
          <rect class="panel-line" :x="L.panel.x" :y="L.panel.y" :width="L.panel.w" :height="L.panel.h" rx="14" />
          <g v-for="(one, n) in QUESTIONS" :key="n" class="q" :class="`q-${n}`">
            <text v-for="(line, k) in one.about" :key="k" class="t-about" :class="{ bad: one.refused }" :x="G.q.x" :y="G.q.about + k * 15">{{ line }}</text>
            <text class="t-q" :x="G.q.x" :y="G.q.asks"><tspan class="dot">●</tspan> {{ one.asks }}</text>
            <text v-if="one.hint" class="t-hint" :x="G.q.x + 14" :y="G.q.hint">{{ one.hint }}</text>
            <g v-for="(option, k) in one.options" :key="option">
              <rect class="option option-lit" :x="G.q.x + 10" :y="G.q.option - 15 + k * 24" :width="optionWidth(option)" height="21" rx="7" />
              <text class="t-option" :x="G.q.x + 20" :y="G.q.option + k * 24">{{ k + 1 }}. {{ option }}</text>
            </g>
          </g>
          <rect class="input" :x="G.input.x" :y="G.input.y" :width="G.input.w" :height="G.input.h" rx="9" />
          <text class="t-caret" :x="G.input.x + 12" :y="G.input.y + G.input.h / 2 + 4.5">❯</text>
          <text class="typed t-typed" :x="G.input.x + 28" :y="G.input.y + G.input.h / 2 + 4.5" />
          </g>
        </g>
      </svg>
      <canvas ref="canvas" />
    </HmzStage>
  </div>
</template>

<style scoped>
.person-scene {
  margin: 22px 0 30px;
}

.person-scene :deep(.hmz-stage) {
  margin-top: 8px;
}

.pick {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12.5px;
  color: var(--vp-c-text-2);
}

.pick span {
  margin-right: 2px;
}

.pick button {
  padding: 3px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  color: var(--vp-c-text-2);
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}

.pick button:hover,
.pick button:focus-visible {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}

.pick button.on {
  border-color: var(--hmz-accent);
  background: color-mix(in srgb, var(--hmz-accent) 14%, transparent);
  color: var(--vp-c-text-1);
}

svg {
  font-family: var(--vp-font-family-base);
}

.card-bg,
.panel-bg {
  fill: var(--hmz-stage-card);
}

.card-line {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-opacity: 0.6;
  stroke-width: 1.3;
}

.panel-line {
  fill: none;
  stroke: var(--hmz-accent-2);
  stroke-opacity: 0.6;
  stroke-width: 1.3;
}

.t-title {
  font-size: 14px;
  font-weight: 700;
  fill: var(--hmz-lane-1);
}

.t-you {
  fill: var(--hmz-accent-2);
}

.t-status {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  fill: var(--hmz-stage-dim);
}

.bar-slot {
  fill: var(--hmz-stage-line);
}

.bar-fill {
  fill: var(--hmz-lane-1);
}

.bar-head {
  fill: var(--hmz-lane-1);
}

.bar-bad {
  fill: var(--hmz-lane-5);
}

.t-value.bad {
  fill: var(--hmz-lane-5);
}

.shape-box {
  fill: color-mix(in srgb, var(--hmz-accent) 5%, transparent);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.t-shape {
  font-family: var(--vp-font-family-mono);
  font-size: 13.5px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.t-field,
.t-value,
.t-dim,
.t-hint,
.t-typed,
.t-caret,
.t-option,
.t-about {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
}

.t-field {
  fill: var(--hmz-stage-ink);
}

.slot {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 3 3;
}

.t-dim,
.t-hint {
  fill: var(--hmz-stage-dim);
}

.t-value {
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.t-ok {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.t-bad {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-lane-5);
}

.now {
  fill: var(--hmz-accent-2);
}

.scan {
  fill: var(--hmz-accent);
}

.stamp rect {
  fill: var(--vp-c-bg);
  stroke: var(--hmz-lane-5);
  stroke-width: 1.5;
}

.stamp text {
  font-family: var(--vp-font-family-mono);
  font-size: 13.5px;
  font-weight: 700;
  fill: var(--hmz-lane-5);
}

.person-head,
.person-body {
  fill: var(--hmz-accent-2);
}

.away rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-dim);
}

.away text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.t-about {
  fill: var(--hmz-stage-dim);
}

.t-about.bad {
  fill: var(--hmz-lane-5);
  font-size: 11px;
}

.t-q {
  font-size: 13.5px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}

.t-q .dot {
  fill: var(--hmz-accent-2);
}

.t-option {
  fill: var(--hmz-stage-ink);
}

.option {
  fill: color-mix(in srgb, var(--hmz-accent-2) 20%, transparent);
  stroke: var(--hmz-accent-2);
  stroke-width: 1.2;
}

.input {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.t-caret {
  font-weight: 700;
  fill: var(--hmz-accent-2);
}

.t-typed {
  fill: var(--hmz-stage-ink);
}
</style>
