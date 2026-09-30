<script setup lang="ts">
// A turn asked for a shape answers in it, or fails. The flow names fields; a CLI that can
// hold the shape is given it as a setting of its own, and the rest are given it in the prompt
// (`SessionBase._shaped_ask` in `src/hmz/coganchor/agents/base.py`) and the answer is checked
// when it comes back. Which is which is each backend's `shapes` in `src/hmz/coganchor/agents/`;
// a CLI added in /settings is asked. The answer lands as the fields: one decides whether the
// loop goes round again, one carries the notes into the next prompt (`rlar`'s `Review` in
// `humanfia/flowverse`). An answer out of shape fails the turn with `OutputSchemaError`, and
// the same shape put to a person is a question per field. Pick a CLI.
import { computed, nextTick, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, fly, streak, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'

const HELD = ['claude', 'codex', 'agy', 'grok', 'qwen']
const ASKED = ['cursor-agent', 'dsh', 'kimi', 'mimo', 'opencode', 'pi', 'a CLI you added']

const cli = ref('claude')
const held = computed(() => HELD.includes(cli.value))
const shown = computed(() => (cli.value === 'a CLI you added' ? 'your CLI' : cli.value))

const BEATS = computed(() => [
  'The flow asks for fields',
  held.value ? `${shown.value} holds the shape itself` : 'Put in the prompt, checked after',
  'The answer lands as fields',
  'One decides, one carries',
  'Out of shape: the turn fails',
  'A person gets the same questions',
])

const FIELDS = [
  { name: 'done', type: 'yes or no', first: 'no', person: 'no' },
  { name: 'notes', type: 'text', first: 'fix the parser', person: 'add a test' },
]

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

const WIDE = {
  w: 640,
  h: 360,
  S: { x: 24, y: 92, w: 170, h: 140 },
  capS: { x: 24, y: 80 },
  head: { x: 40, y: 118 },
  rows: [152, 198],
  rRows: [152, 198],
  type: { dx: 0, dy: 17 },
  R: { x: 420, y: 92, w: 198, h: 140 },
  capR: { x: 420, y: 80 },
  slot: { x: 488, w: 118 },
  C: { x: 262, y: 118, w: 116, h: 96 },
  cliName: { x: 320, y: 142 },
  orb: { x: 320, y: 180, r: 14 },
  clamp: { x: 296, y: 156, w: 48, h: 48 },
  sheet: { x: 206, y: 144, w: 30, h: 40 },
  gate: { x1: 399, y1: 126, x2: 399, y2: 206 },
  gateLabel: { x: 414, y: 226, anchor: 'end' },
  into: 'M194 162 L262 166',
  out: 'M378 166 L420 162',
  arc: 'M519 232 C519 322 109 322 109 232',
  arcLabel: { x: 316, y: 300 },
  q: { x: 232, y: 18, w: 176, h: 88 },
  stamp: { x: 519, y: 252 },
}

const NARROW = {
  w: 360,
  h: 432,
  S: { x: 40, y: 42, w: 280, h: 94 },
  capS: { x: 40, y: 32 },
  head: { x: 54, y: 66 },
  rows: [94, 122],
  rRows: [338, 374],
  type: { dx: 90, dy: 0 },
  R: { x: 40, y: 306, w: 280, h: 96 },
  capR: { x: 40, y: 298 },
  slot: { x: 124, w: 182 },
  C: { x: 40, y: 164, w: 280, h: 84 },
  cliName: { x: 104, y: 184 },
  orb: { x: 104, y: 218, r: 12 },
  clamp: { x: 84, y: 198, w: 40, h: 40 },
  sheet: { x: 236, y: 184, w: 30, h: 40 },
  gate: { x1: 124, y1: 272, x2: 236, y2: 272 },
  gateLabel: { x: 244, y: 276, anchor: 'start' },
  into: 'M180 136 L180 164',
  out: 'M180 248 L180 306',
  arc: 'M40 356 C2 356 2 80 40 80',
  arcLabel: { x: 17, y: 222 },
  q: { x: 150, y: 172, w: 160, h: 68 },
  stamp: { x: 180, y: 408 },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined
const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const mid = (r: Rect) => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 })
const slotY = (i: number) => L.value.rRows[i] - 18

function pick(name: string) {
  if (name === cli.value) return
  cli.value = name
  void nextTick(() => scene.rebuild())
}

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    const isHeld = held.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const get = () => fx
    const one = (s: string) => q(s)[0]
    const slotMid = (i: number) => ({ x: l.slot.x + l.slot.w / 2, y: slotY(i) + 13 })
    const cMid = narrow.value ? { x: l.orb.x, y: l.orb.y } : mid(l.C)
    const s = mid(l.S)

    tl.set(q('.sh-world'), { autoAlpha: 1 }, 0)
    tl.set(q('.sh-c, .sh-r, .sh-beam, .sh-clamp-g, .sh-sheet, .sh-gate, .sh-val, .sh-arc-g, .sh-note, .sh-bad, .sh-stamp, .sh-pval, .sh-q, .sh-person, .sh-pick, .sh-typed'), { autoAlpha: 0 }, 0)
    tl.set(q('.sh-machine'), { autoAlpha: 1 }, 0)
    tl.set(one('.sh-typed'), { text: '' }, 0)

    // 0 · the flow names its fields, close up.
    tl.addLabel('beat-0', 0)
    const cam = one('.sh-cam')
    const push = narrow.value ? 1.12 : 1.45
    tl.fromTo(cam, { scale: push * 1.03, x: l.w / 2 - s.x, y: (narrow.value ? 150 : l.h / 2) - s.y, svgOrigin: `${s.x} ${s.y}` }, { scale: push, duration: 2.6, ease: 'none' }, 0)
    tl.fromTo(one('.sh-s-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1, ease: 'cine' }, 0.1)
    tl.fromTo(q('.sh-s-words'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.5, stagger: 0.18 }, 0.4)
    tl.fromTo(q('.sh-field'), { autoAlpha: 0, x: -10 }, { autoAlpha: 1, x: 0, duration: 0.5, stagger: 0.3 }, 0.9)

    // 1 · the shape goes to the CLI: held by the CLI itself, or written into the prompt.
    const T1 = 2.6
    tl.addLabel('beat-1', T1)
    tl.to(cam, { scale: 1, x: 0, y: 0, duration: 1.3, ease: 'cine' }, T1)
    tl.to(q('.sh-c, .sh-r'), { autoAlpha: 1, duration: 0.5, stagger: 0.2 }, T1 + 0.4)
    tl.fromTo(one('.sh-c-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.9, ease: 'cine' }, T1 + 0.4)
    tl.to(one('.sh-into'), { autoAlpha: 1, duration: 0.1 }, T1 + 0.9)
    tl.fromTo(one('.sh-into'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.5 }, T1 + 0.9)
    if (isHeld) {
      streak(tl, get, s, cMid, () => palette.accent, T1 + 1.1, { duration: 0.6, bend: 0.1, burst: 16 })
      tl.to(one('.sh-clamp-g'), { autoAlpha: 1, duration: 0.1 }, T1 + 1.6)
      tl.fromTo(one('.sh-clamp'), { drawSVG: '50% 50%' }, { drawSVG: '0% 100%', duration: 0.6, ease: 'cine' }, T1 + 1.6)
      tl.fromTo(one('.sh-orb'), { scale: 1.35, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.6, ease: 'back.out(3)' }, T1 + 1.7)
    } else {
      const sheet = one('.sh-sheet')
      const from = { x: s.x - (l.sheet.x + l.sheet.w / 2), y: s.y - (l.sheet.y + l.sheet.h / 2) }
      tl.fromTo(sheet, { autoAlpha: 0, x: from.x, y: from.y, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, x: 0, y: 0, scale: 1, duration: 0.9, ease: 'cine' }, T1 + 1)
      tl.fromTo(one('.sh-sheet-shape'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3 }, T1 + 1.5)
      tl.call(() => fx?.spark(l.sheet.x + l.sheet.w / 2, l.sheet.y + l.sheet.h / 2, palette.accent, 14, 80), [], T1 + 1.9)
      tl.to(one('.sh-gate'), { autoAlpha: 1, duration: 0.3 }, T1 + 2)
      tl.fromTo(one('.sh-gate-line'), { drawSVG: '50% 50%' }, { drawSVG: '0% 100%', duration: 0.5 }, T1 + 2)
    }

    // 2 · the answer comes back as the fields themselves.
    const T2 = T1 + 2.7
    tl.addLabel('beat-2', T2)
    tl.to(one('.sh-out'), { autoAlpha: 1, duration: 0.1 }, T2)
    tl.fromTo(one('.sh-out'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.5 }, T2)
    tl.fromTo(one('.sh-orb'), { scale: 1 }, { keyframes: { scale: [1, 1.3, 1] }, duration: 0.5, transformOrigin: '50% 50%' }, T2)
    if (!isHeld) tl.fromTo(one('.sh-gate-line'), { opacity: 1 }, { keyframes: { opacity: [1, 0.3, 1, 0.3, 1] }, duration: 0.5 }, T2 + 0.3)
    FIELDS.forEach((_, i) => {
      streak(tl, get, cMid, slotMid(i), () => palette.accent, T2 + 0.3 + i * 0.2, { duration: 0.6, bend: i ? -0.15 : 0.15, burst: 12 })
      tl.fromTo(q('.sh-v1')[i], { autoAlpha: 0, scale: 0.7, transformOrigin: '0% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(2)' }, T2 + 0.85 + i * 0.2)
    })

    // 3 · done is no, so the loop goes round again, and the notes are the next prompt.
    const T3 = T2 + 2.3
    tl.addLabel('beat-3', T3)
    tl.fromTo(q('.sh-slot')[0], { scale: 1 }, { keyframes: { scale: [1, 1.08, 1] }, duration: 0.5, transformOrigin: '50% 50%' }, T3)
    tl.to(one('.sh-arc-g'), { autoAlpha: 1, duration: 0.1 }, T3 + 0.2)
    tl.fromTo(one('.sh-arc'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1, ease: 'cine' }, T3 + 0.2)
    fly(tl, one('.sh-note'), one('.sh-arc') as SVGPathElement, T3 + 0.9, { duration: 1.3, fx: get, color: palette.warm })
    tl.call(() => fx?.spark(s.x, l.S.y + l.S.h, palette.warm, 20, 100), [], T3 + 2.2)
    tl.fromTo(one('.sh-s-frame'), { opacity: 1 }, { keyframes: { opacity: [1, 0.3, 1] }, duration: 0.4 }, T3 + 2.2)

    // 4 · the next answer is not the shape: nothing lands, and the turn fails.
    const T4 = T3 + 2.8
    tl.addLabel('beat-4', T4)
    tl.to(q('.sh-val'), { autoAlpha: 0, duration: 0.3 }, T4)
    tl.to(one('.sh-arc-g'), { autoAlpha: 0, duration: 0.3 }, T4)
    tl.fromTo(one('.sh-orb'), { scale: 1 }, { keyframes: { scale: [1, 1.3, 1] }, duration: 0.5, transformOrigin: '50% 50%' }, T4 + 0.2)
    const stop = isHeld ? { x: l.R.x + 8, y: mid(l.R).y } : { x: (l.gate.x1 + l.gate.x2) / 2, y: (l.gate.y1 + l.gate.y2) / 2 }
    streak(tl, get, cMid, stop, () => palette.danger, T4 + 0.4, { duration: 0.5, bend: 0.3, size: 3 })
    streak(tl, get, cMid, stop, () => palette.warm, T4 + 0.5, { duration: 0.5, bend: -0.3, size: 3 })
    tl.call(() => fx?.spark(stop.x, stop.y, palette.danger, 34, 140), [], T4 + 1)
    if (!isHeld) tl.fromTo(one('.sh-gate'), { x: 0 }, { keyframes: { x: [0, -4, 4, -2, 2, 0] }, duration: 0.4, ease: 'none' }, T4 + 1)
    tl.fromTo(q('.sh-bad'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.25, stagger: 0.08 }, T4 + 1.05)
    tl.fromTo(one('.sh-stamp'), { autoAlpha: 0, scale: 1.5, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.5, ease: 'back.out(1.8)' }, T4 + 1.3)
    tl.to(q('.sh-bad, .sh-stamp'), { autoAlpha: 0, duration: 0.4 }, T4 + 2.6)

    // 5 · the same fields, put to a person: a question each, the answers in the same slots.
    const T5 = T4 + 3
    tl.addLabel('beat-5', T5)
    tl.to(one('.sh-machine'), { autoAlpha: 0, duration: 0.4 }, T5)
    tl.to(q('.sh-clamp-g, .sh-sheet, .sh-gate'), { autoAlpha: 0, duration: 0.4 }, T5)
    tl.fromTo(one('.sh-person'), { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.5 }, T5 + 0.3)
    tl.fromTo(one('.sh-q'), { autoAlpha: 0, scale: 0.85, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.5, ease: 'back.out(1.6)' }, T5 + 0.5)
    tl.fromTo(one('.sh-pick'), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.3, ease: 'back.out(2)' }, T5 + 1.3)
    tl.set(one('.sh-typed'), { autoAlpha: 1 }, T5 + 1.6)
    tl.to(one('.sh-typed'), { text: { value: FIELDS[1].person }, duration: 0.6, ease: 'none' }, T5 + 1.6)
    const qMid = mid(l.q)
    FIELDS.forEach((_, i) => {
      streak(tl, get, qMid, slotMid(i), () => palette.lane[0], T5 + 2.4 + i * 0.15, { duration: 0.6, bend: 0.2, burst: 10 })
      tl.fromTo(q('.sh-pval')[i], { autoAlpha: 0, scale: 0.7, transformOrigin: '0% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, T5 + 2.9 + i * 0.15)
    })
    tl.addLabel('rest', T5 + 3.8)
    tl.to(q('.sh-world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T5 + 5.6)
    tl.set(q('.sh-pval'), { autoAlpha: 0 }, T5 + 6.3)
  },
})
</script>

<template>
  <div class="hmz-shape">
    <div class="picker" role="group" aria-label="Which CLI answers">
      <span class="group">held</span>
      <button v-for="name in HELD" :key="name" type="button" class="held" :class="{ on: cli === name }" :aria-pressed="cli === name" @click="pick(name)">{{ name }}</button>
      <span class="group">asked</span>
      <button v-for="name in ASKED" :key="name" type="button" :class="{ on: cli === name }" :aria-pressed="cli === name" @click="pick(name)">{{ name }}</button>
    </div>
    <HmzStage
      :scene="scene"
      :beats="BEATS"
      sim
      mobile-ratio="5 / 6"
      :label="`A flow asks for two fields: done, yes or no, and notes, text. ${held ? `${shown} holds the shape as a setting of its own` : `${shown} is given the shape in the prompt, and the answer is checked when it comes back`}. The answer lands as the fields: done is no, so the loop goes round again, and the notes become the next prompt. An answer that is not the shape fails the turn. Put to a person, the same fields are a question each, and the answers land in the same fields.`"
    >
      <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
        <defs>
          <radialGradient id="hmz-shape-glow">
            <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.5" />
            <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
          </radialGradient>
        </defs>
        <g class="sh-world">
          <g class="sh-cam">
            <!-- The flow's shape. -->
            <text class="sh-cap sh-s-words" :x="L.capS.x" :y="L.capS.y">the flow asks for</text>
            <rect class="sh-card" :x="L.S.x" :y="L.S.y" :width="L.S.w" :height="L.S.h" rx="14" />
            <rect class="sh-s-frame" :x="L.S.x" :y="L.S.y" :width="L.S.w" :height="L.S.h" rx="14" />
            <text class="sh-head sh-s-words" :x="L.head.x" :y="L.head.y">Review</text>
            <g v-for="(f, i) in FIELDS" :key="f.name" class="sh-field">
              <text class="sh-fname" :x="L.head.x" :y="L.rows[i]">{{ f.name }}</text>
              <text class="sh-ftype" :x="L.head.x + L.type.dx" :y="L.rows[i] + L.type.dy">{{ f.type }}</text>
            </g>

            <!-- The CLI, or the person. -->
            <path class="sh-beam sh-into" :d="L.into" />
            <g class="sh-c">
              <circle class="sh-halo" :cx="L.orb.x" :cy="L.orb.y" :r="narrow ? 60 : 70" fill="url(#hmz-shape-glow)" />
              <rect class="sh-card" :x="L.C.x" :y="L.C.y" :width="L.C.w" :height="L.C.h" rx="16" />
              <rect class="sh-c-frame" :x="L.C.x" :y="L.C.y" :width="L.C.w" :height="L.C.h" rx="16" />
              <g class="sh-machine">
                <text class="sh-cli" :x="L.cliName.x" :y="L.cliName.y" text-anchor="middle">{{ shown }}</text>
                <g class="sh-orb">
                  <circle class="sh-orb-core" :cx="L.orb.x" :cy="L.orb.y" :r="L.orb.r" />
                </g>
              </g>
              <g class="sh-clamp-g">
                <rect class="sh-clamp" :x="L.clamp.x" :y="L.clamp.y" :width="L.clamp.w" :height="L.clamp.h" rx="10" />
              </g>
              <g class="sh-person">
                <circle class="sh-person-line" :cx="L.orb.x" :cy="L.orb.y - 7" r="6" />
                <path class="sh-person-line" :d="`M${L.orb.x - 12} ${L.orb.y + 12} C${L.orb.x - 12} ${L.orb.y} ${L.orb.x + 12} ${L.orb.y} ${L.orb.x + 12} ${L.orb.y + 12}`" />
                <text class="sh-cli" :x="L.cliName.x" :y="L.cliName.y" text-anchor="middle">you</text>
              </g>
            </g>
            <g class="sh-sheet">
              <rect class="sh-paper" :x="L.sheet.x" :y="L.sheet.y" :width="L.sheet.w" :height="L.sheet.h" rx="3" />
              <line v-for="k in 3" :key="k" class="sh-paper-line" :x1="L.sheet.x + 5" :x2="L.sheet.x + L.sheet.w - 5" :y1="L.sheet.y + 6 + k * 6" :y2="L.sheet.y + 6 + k * 6" />
              <rect class="sh-sheet-shape" :x="L.sheet.x + 5" :y="L.sheet.y + L.sheet.h - 13" :width="L.sheet.w - 10" height="8" rx="2" />
            </g>
            <g class="sh-gate">
              <line class="sh-gate-line" :x1="L.gate.x1" :y1="L.gate.y1" :x2="L.gate.x2" :y2="L.gate.y2" />
              <text class="sh-cap" :x="L.gateLabel.x" :y="L.gateLabel.y" :text-anchor="L.gateLabel.anchor">checked</text>
            </g>

            <!-- What the flow gets. -->
            <path class="sh-beam sh-out" :d="L.out" />
            <g class="sh-r">
              <text class="sh-cap" :x="L.capR.x" :y="L.capR.y">the flow gets</text>
              <rect class="sh-card" :x="L.R.x" :y="L.R.y" :width="L.R.w" :height="L.R.h" rx="14" />
              <rect class="sh-r-frame" :x="L.R.x" :y="L.R.y" :width="L.R.w" :height="L.R.h" rx="14" />
              <g v-for="(f, i) in FIELDS" :key="`r${f.name}`">
                <text class="sh-fname" :x="L.R.x + 16" :y="L.rRows[i]">{{ f.name }}</text>
                <g class="sh-slot">
                  <rect class="sh-slot-box" :x="L.slot.x" :y="L.rRows[i] - 18" :width="L.slot.w" height="26" rx="7" />
                </g>
                <rect class="sh-bad" :x="L.slot.x" :y="L.rRows[i] - 18" :width="L.slot.w" height="26" rx="7" />
                <text class="sh-val sh-v1" :x="L.slot.x + 9" :y="L.rRows[i]" :class="{ no: i === 0 }">{{ f.first }}</text>
                <text class="sh-val sh-pval" :x="L.slot.x + 9" :y="L.rRows[i]" :class="{ no: i === 0 }">{{ f.person }}</text>
              </g>
              <g :transform="`translate(${L.stamp.x} ${L.stamp.y})`">
                <g class="sh-stamp">
                  <rect x="-66" y="-15" width="132" height="30" rx="15" />
                  <text y="5" text-anchor="middle">the turn fails</text>
                </g>
              </g>
            </g>

            <g class="sh-arc-g">
              <path class="sh-arc" :d="L.arc" />
              <text v-if="!narrow" class="sh-again" :x="L.arcLabel.x" :y="L.arcLabel.y" text-anchor="middle">again, with the notes</text>
              <text v-else class="sh-again" :x="L.arcLabel.x" :y="L.arcLabel.y" text-anchor="middle" :transform="`rotate(-90 ${L.arcLabel.x} ${L.arcLabel.y})`">again</text>
            </g>
            <g class="sh-note">
              <rect x="0" y="0" width="58" height="20" rx="10" />
              <text x="29" y="14" text-anchor="middle">notes</text>
            </g>

            <!-- The same fields, as questions. -->
            <g class="sh-q">
              <rect class="sh-q-box" :x="L.q.x" :y="L.q.y" :width="L.q.w" :height="L.q.h" rx="12" />
              <text class="sh-qtext" :x="L.q.x + 12" :y="L.q.y + (narrow ? 22 : 30)">done?</text>
              <g v-for="(a, k) in ['yes', 'no']" :key="a">
                <rect class="sh-choice" :x="L.q.x + 62 + k * 46" :y="L.q.y + (narrow ? 8 : 15)" width="40" height="22" rx="11" />
                <text class="sh-choice-text" :x="L.q.x + 82 + k * 46" :y="L.q.y + (narrow ? 23 : 30)" text-anchor="middle">{{ a }}</text>
              </g>
              <g class="sh-pick">
                <rect class="sh-choice on" :x="L.q.x + 108" :y="L.q.y + (narrow ? 8 : 15)" width="40" height="22" rx="11" />
                <text class="sh-choice-text on" :x="L.q.x + 128" :y="L.q.y + (narrow ? 23 : 30)" text-anchor="middle">no</text>
              </g>
              <text class="sh-qtext" :x="L.q.x + 12" :y="L.q.y + (narrow ? 54 : 68)">notes?</text>
              <text class="sh-typed" :x="L.q.x + 62" :y="L.q.y + (narrow ? 54 : 68)" />
            </g>
          </g>
        </g>
      </svg>
      <canvas ref="canvas" />
    </HmzStage>
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 22px 0 0;
}

.picker .group {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
  margin: 0 2px 0 4px;
}

.picker .group:first-child {
  margin-left: 0;
}

.picker button {
  padding: 3px 10px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}

.picker button.held {
  border-style: solid;
  border-color: color-mix(in srgb, var(--hmz-accent) 60%, transparent);
}

.picker button:hover {
  color: var(--vp-c-text-1);
}

.picker button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 650;
}

.hmz-shape > .hmz-stage {
  margin-top: 10px;
}

svg {
  font-family: var(--vp-font-family-base);
}

.sh-cap {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.sh-card {
  fill: var(--hmz-stage-card);
}

.sh-s-frame,
.sh-c-frame,
.sh-r-frame {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
}

.sh-c-frame {
  stroke: var(--hmz-lane-1);
}

.sh-r-frame {
  stroke: var(--hmz-stage-line);
}

.sh-head {
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.sh-fname {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.sh-ftype {
  font-size: 11.5px;
  fill: var(--hmz-stage-dim);
}

.sh-beam {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.5;
  stroke-linecap: round;
}

.sh-halo {
  opacity: calc(var(--hmz-glow) * 0.6);
}

.sh-cli {
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.sh-orb-core {
  fill: var(--hmz-lane-1);
}

.sh-clamp {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2.5;
}

.sh-person-line {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 2.2;
  stroke-linecap: round;
}

.sh-paper {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.2;
}

.sh-paper-line {
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.2;
  opacity: 0.6;
}

.sh-sheet-shape {
  fill: var(--hmz-accent);
}

.sh-gate-line {
  stroke: var(--hmz-accent);
  stroke-width: 3;
  stroke-linecap: round;
}

.sh-slot-box {
  fill: color-mix(in srgb, var(--hmz-accent) 6%, transparent);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
  stroke-dasharray: 4 3;
}

.sh-bad {
  fill: color-mix(in srgb, var(--hmz-lane-5) 16%, transparent);
  stroke: var(--hmz-lane-5);
  stroke-width: 1.6;
}

.sh-val {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.sh-val.no {
  fill: var(--hmz-warm);
}

.sh-stamp rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-5);
  stroke-width: 1.6;
}

.sh-stamp text {
  font-size: 12.5px;
  font-weight: 700;
  fill: var(--hmz-lane-5);
}

.sh-arc {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2;
  stroke-linecap: round;
}

.sh-again {
  font-size: 11.5px;
  font-weight: 700;
  fill: var(--hmz-warm);
}

.sh-note rect {
  fill: var(--hmz-warm);
}

.sh-note text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.sh-q-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.5;
}

.sh-qtext {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.sh-typed {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  fill: var(--hmz-lane-1);
}

.sh-choice {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.sh-choice.on {
  fill: var(--hmz-lane-1);
  stroke: var(--hmz-lane-1);
}

.sh-choice-text {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.sh-choice-text.on {
  fill: #fff;
}
</style>
