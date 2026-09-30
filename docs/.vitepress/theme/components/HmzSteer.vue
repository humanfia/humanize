<script setup lang="ts">
// A line typed while a turn is running, on two kinds of backend side by side. On the left, the
// ones whose sessions set `steers` (Claude Code, Codex, Kimi Code and pi,
// `src/hmz/coganchor/agents/`): the line goes into the turn already running, and that turn
// answers it. On the right, every other backend: `interject` refuses, the interface says the
// session cannot be talked to mid-turn, and the line goes back on the pin, where the next turn
// to start takes it (the screens in `docs/user/steering.md`). Either way a line is pinned above
// the prompt, saying which agent has it, until the agent has it; and lines go one at a time,
// the next only once the one before is taken. The tools, the replies and the timings are drawn.
import { computed, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'

const BEATS = [
  'A turn is running',
  'You type while it works',
  'Taken into the turn, or refused',
  'A refused line waits for the next turn',
  'Lines go one at a time',
]

interface P {
  x: number
  y: number
}

interface Layout {
  w: number
  h: number
  /** One half's size, and where each half sits. */
  W: number
  H: number
  halves: P[]
  head: number
  sub: number
  track: number
  turnWord: number
  /** The first transcript row, the row pitch, and how many rows show. */
  row0: number
  row: number
  rows: number
  pin: number
  prompt: number
  promptH: number
  focus: number
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  W: 296,
  H: 314,
  halves: [
    { x: 16, y: 34 },
    { x: 328, y: 34 },
  ],
  head: 24,
  sub: 42,
  track: 60,
  turnWord: 84,
  row0: 112,
  row: 19,
  rows: 5,
  pin: 238,
  prompt: 262,
  promptH: 36,
  focus: 1.04,
}

const NARROW: Layout = {
  w: 360,
  h: 500,
  W: 340,
  H: 222,
  halves: [
    { x: 10, y: 42 },
    { x: 10, y: 272 },
  ],
  head: 22,
  sub: 38,
  track: 54,
  turnWord: 76,
  row0: 100,
  row: 17,
  rows: 3,
  pin: 170,
  prompt: 184,
  promptH: 30,
  focus: 1.02,
}

const PAD = 14
const LINE = 'and fix the tests too'

type Kind = 'tool' | 'you' | 'say' | 'warn'

// What each side's transcript says, in order.
const SAID: { text: string; kind: Kind }[][] = [
  [
    { text: '▸ Read src/pay.py', kind: 'tool' },
    { text: '▸ Edit src/pay.py', kind: 'tool' },
    { text: `❯ ${LINE}`, kind: 'you' },
    { text: '● On it: the tests too.', kind: 'say' },
    { text: '▸ Edit tests/test_pay.py', kind: 'tool' },
    { text: '❯ use pathlib', kind: 'you' },
    { text: '● Switching to pathlib.', kind: 'say' },
    { text: '❯ keep the CLI', kind: 'you' },
    { text: '● Leaving the CLI alone.', kind: 'say' },
  ],
  [
    { text: '▸ Read src/pay.py', kind: 'tool' },
    { text: '▸ Edit src/pay.py', kind: 'tool' },
    { text: 'hmz: cannot be talked to mid-turn', kind: 'warn' },
    { text: '▸ Bash pytest -q', kind: 'tool' },
    { text: `❯ ${LINE}`, kind: 'you' },
    { text: '● On it: the tests too.', kind: 'say' },
  ],
]

// The lines that wait on the pin above the prompt, and the row each first appears on.
const PINS = [
  { text: LINE, slot: 0 },
  { text: 'use pathlib', slot: 1 },
  { text: 'keep the CLI', slot: 0 },
]
const chip = (text: string) => (text.length + 15) * (narrow.value ? 6.6 : 6.9) + 12

const SIDES = [
  { title: 'into this turn', who: 'Claude Code · Codex · Kimi Code · pi', hue: 'var(--hmz-accent)' },
  { title: 'into the next turn', who: 'every other backend', hue: 'var(--hmz-warm)' },
]

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

// Where the two turns sit on a side's track.
const turn1 = computed(() => ({ a: PAD, b: PAD + (L.value.W - 2 * PAD) * 0.64 }))
const turn2 = computed(() => ({ a: turn1.value.b + 12, b: L.value.W - PAD }))

// The camera over the whole picture, and a lens on each side (the side in focus comes forward,
// the other falls back). Both are applied by hand, so a point on a side can be followed onto
// the canvas while they move.
const cam = { x: 0, y: 0, s: 1 }
const lens = [{ s: 1 }, { s: 1 }]
let worldEl: SVGGElement | null = null
let sideEls: SVGGElement[] = []

function centre(i: number): P {
  const l = L.value
  return { x: l.halves[i].x + l.W / 2, y: l.halves[i].y + l.H / 2 }
}

function applyCam() {
  worldEl?.setAttribute('transform', `translate(${cam.x} ${cam.y}) scale(${cam.s})`)
}

function applyLens() {
  sideEls.forEach((el, i) => {
    const c = centre(i)
    el.setAttribute('transform', `translate(${c.x} ${c.y}) scale(${lens[i].s}) translate(${-c.x} ${-c.y})`)
  })
}

/** A point on side `i`, in the side's own coordinates, where it is on the screen right now. */
function onScreen(i: number, p: P): P {
  const l = L.value
  const c = centre(i)
  const wx = c.x + (l.halves[i].x + p.x - c.x) * lens[i].s
  const wy = c.y + (l.halves[i].y + p.y - c.y) * lens[i].s
  return { x: cam.x + wx * cam.s, y: cam.y + wy * cam.s }
}

const scene = useScene({
  still: 'rest',
  repeatDelay: 0.6,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    worldEl = q('.world')[0] as SVGGElement
    sideEls = q('.side') as SVGGElement[]
    const all = (sel: string) => q(sel)
    const of = (i: number, sel: string) => q(`.side-${i} ${sel}`)
    const hue = (i: number) => (i ? palette.warm : palette.accent)

    // Timings: the first turn, the gap, the second.
    const TA = 0.4
    const TEND = 8.2
    const TS2 = 8.8
    const TEND2 = 19.5
    const t1 = turn1.value
    const t2 = turn2.value
    const headAt = (t: number) =>
      t <= TEND ? t1.a + (t1.b - t1.a) * Math.max(0, (t - TA) / (TEND - TA)) : t2.a + (t2.b - t2.a) * Math.max(0, (t - TS2) / (TEND2 - TS2))
    const bar = (t: number): P => ({ x: headAt(t), y: l.track + 4 })
    const pinAt = (slot = 0): P => ({ x: PAD + 14, y: l.pin - 4 - slot * l.row })

    // A mote of light from one point of a side to another, followed through the camera.
    function beam(i: number, from: P, to: P, color: string, at: number, opts: { duration?: number; bend?: number; burst?: number } = {}) {
      const p = { t: 0 }
      const bend = opts.bend ?? 0.3
      const cx = (from.x + to.x) / 2 - (to.y - from.y) * bend
      const cy = (from.y + to.y) / 2 + (to.x - from.x) * bend
      tl.fromTo(
        p,
        { t: 0 },
        {
          t: 1,
          duration: opts.duration ?? 0.6,
          ease: 'cine',
          onUpdate: () => {
            const t = p.t
            const u = 1 - t
            const s = onScreen(i, { x: u * u * from.x + 2 * u * t * cx + t * t * to.x, y: u * u * from.y + 2 * u * t * cy + t * t * to.y })
            fx?.trail(s.x, s.y, color, 2.6)
          },
          onComplete: () => {
            if (!opts.burst) return
            const s = onScreen(i, to)
            fx?.spark(s.x, s.y, color, opts.burst, 80)
          },
        },
        at,
      )
    }

    // A transcript row appears, and the rows scroll up once they are full.
    function say(i: number, n: number, at: number) {
      tl.fromTo(of(i, '.said')[n], { autoAlpha: 0, x: -8 }, { autoAlpha: 1, x: 0, duration: 0.45 }, at)
      if (n >= l.rows) tl.to(of(i, '.scroll'), { y: -(n - l.rows + 1) * l.row, duration: 0.45, ease: 'cine' }, at)
    }

    function mark(i: number, which: number, x: number, at: number) {
      const m = of(i, '.mark')[which]
      tl.set(m, { attr: { transform: `translate(${x} ${l.track + 4})` } }, 0)
      tl.fromTo(m.querySelector('.mark-in'), { scale: 0, autoAlpha: 0, transformOrigin: '50% 50%' }, { scale: 1, autoAlpha: 1, duration: 0.5, ease: 'back.out(3)' }, at)
    }

    // Clean slate for every loop.
        tl.set(lens, { s: 1, onComplete: applyLens }, 0)
    tl.set(all('.said, .pin, .mark-in, .glow, .halo, .prompt-lit'), { autoAlpha: 0 }, 0)
    tl.set(all('.with'), { fillOpacity: 0 }, 0)
    tl.set(all('.side-in'), { autoAlpha: 1 }, 0)
    tl.set(all('.scroll'), { y: 0 }, 0)
    tl.set(all('.typed'), { text: '' }, 0)
    tl.set(all('.fill'), { attr: { width: 0 } }, 0)
    tl.set(all('.head'), { attr: { cx: t1.a }, autoAlpha: 0 }, 0)
    tl.set(all('.pin'), { y: 0 }, 0)
    tl.set(all('.turn-word-1'), { opacity: 1 }, 0)

    // 0 · the camera settles on two sides of one moment; a turn runs on both.
    tl.addLabel('beat-0', 0)
    const mid = { x: l.w / 2, y: l.h / 2 }
    tl.fromTo(cam, { s: 1.14, x: mid.x * -0.14, y: mid.y * -0.14 }, { s: 1, x: 0, y: 0, duration: 2.6, ease: 'cine', onUpdate: applyCam }, 0)
    tl.fromTo(all('.card'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.4, stagger: 0.15, ease: 'cine' }, 0)
    tl.fromTo(all('.side-words'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.6, stagger: 0.15 }, 0.3)
    for (const i of [0, 1]) {
      tl.to(of(i, '.head'), { autoAlpha: 1, duration: 0.2 }, TA)
      tl.to(of(i, '.fill1'), { attr: { width: t1.b - t1.a }, duration: TEND - TA, ease: 'none' }, TA)
      tl.to(of(i, '.head'), { attr: { cx: t1.b }, duration: TEND - TA, ease: 'none' }, TA)
      say(i, 0, 1.0)
      say(i, 1, 1.9)
    }

    // 1 · the same line, typed at both while they work, pinned as it is sent.
    const T1 = 2.5
    tl.addLabel('beat-1', T1)
    for (const i of [0, 1]) {
      tl.to(of(i, '.prompt-lit'), { autoAlpha: 1, duration: 0.3 }, T1)
      tl.set(of(i, '.typed'), { text: '' }, T1 + 0.2)
      tl.to(of(i, '.typed'), { text: { value: LINE }, duration: 0.9, ease: 'none' }, T1 + 0.2)
      tl.to(of(i, '.typed'), { autoAlpha: 0, y: -12, duration: 0.3, ease: 'cine.in' }, T1 + 1.35)
      tl.set(of(i, '.typed'), { text: '', autoAlpha: 1, y: 0 }, T1 + 1.7)
      tl.fromTo(of(i, '.pin-0'), { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.4 }, T1 + 1.45)
      tl.to(of(i, '.pin-0 .with'), { fillOpacity: 1, duration: 0.3 }, T1 + 1.6)
      tl.to(of(i, '.prompt-lit'), { autoAlpha: 0, duration: 0.4 }, T1 + 1.7)
    }

    // 2 · the left takes it into the turn it is running; the right refuses, and the line goes
    // back on the pin. The same instant, on both.
    const T2 = 4.3
    tl.addLabel('beat-2', T2)
    const hit = T2 + 0.7
    beam(0, pinAt(), bar(hit), palette.accent, T2, { burst: 22, bend: -0.35, duration: 0.7 })
    mark(0, 0, headAt(hit), hit)
    tl.to(of(0, '.glow'), { autoAlpha: 1, duration: 0.3 }, hit)
    tl.to(of(0, '.glow'), { autoAlpha: 0, duration: 1.2 }, hit + 0.4)
    tl.to(of(0, '.pin-0'), { autoAlpha: 0, y: -6, duration: 0.35 }, hit)
    say(0, 2, hit + 0.1)
    say(0, 3, hit + 0.8)

    beam(1, pinAt(), bar(hit), palette.warm, T2, { bend: -0.35, duration: 0.7 })
    tl.call(() => {
      const s = onScreen(1, bar(hit))
      fx?.spark(s.x, s.y, palette.danger, 26, 120)
    }, [], hit)
    tl.fromTo(of(1, '.track'), { x: 0 }, { keyframes: { x: [0, -5, 5, -3, 3, 0] }, duration: 0.4, ease: 'none' }, hit)
    tl.set(of(1, '.flare'), { attr: { cx: headAt(hit) } }, 0)
    tl.fromTo(of(1, '.flare'), { autoAlpha: 0, scale: 0.4, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1.3, duration: 0.18, ease: 'power2.out' }, hit)
    tl.to(of(1, '.flare'), { autoAlpha: 0, scale: 0.8, duration: 0.7 }, hit + 0.2)
    say(1, 2, hit + 0.05)
    beam(1, bar(hit + 0.1), pinAt(), palette.danger, hit + 0.1, { bend: -0.3, duration: 0.6 })
    tl.to(of(1, '.pin-0 .with'), { fillOpacity: 0, duration: 0.3 }, hit + 0.5)
    tl.fromTo(of(1, '.pin-0 .pin-chip'), { attr: { width: chip(LINE) } }, { attr: { width: chip(LINE) - 13 * (narrow.value ? 6.6 : 6.9) }, duration: 0.4 }, hit + 0.5)
    tl.to(of(1, '.pin-0'), { keyframes: { opacity: [1, 0.55, 1, 0.55, 1] }, duration: 1.6, ease: 'none' }, hit + 0.7)
    tl.addLabel('rest', hit + 1.7)
    say(0, 4, hit + 2.2)
    say(1, 3, hit + 2.3)

    // 3 · the right comes into focus. Its turn ends; the next one starts and takes the line.
    const T3 = 7.4
    tl.addLabel('beat-3', T3)
    tl.to(lens[1], { s: l.focus, duration: 1.2, ease: 'cine', onUpdate: applyLens }, T3)
    tl.to(lens[0], { s: 2 - l.focus, duration: 1.2, ease: 'cine', onUpdate: applyLens }, T3)
    tl.to(of(0, '.side-in'), { autoAlpha: 0.38, duration: 1 }, T3)
    tl.to(of(1, '.halo'), { autoAlpha: 1, duration: 1 }, T3)
    for (const i of [0, 1]) {
      tl.call(() => {
        const s = onScreen(i, bar(TEND))
        fx?.spark(s.x, s.y, hue(i), 10, 50)
      }, [], TEND)
      tl.to(of(i, '.head'), { autoAlpha: 0, duration: 0.2 }, TEND)
      tl.to(of(i, '.turn-word-1'), { opacity: 0.45, duration: 0.4 }, TEND)
      tl.set(of(i, '.head'), { attr: { cx: t2.a } }, TEND + 0.3)
      tl.to(of(i, '.head'), { autoAlpha: 1, duration: 0.2 }, TS2)
      tl.to(of(i, '.fill2'), { attr: { width: t2.b - t2.a }, duration: TEND2 - TS2, ease: 'none' }, TS2)
      tl.to(of(i, '.head'), { attr: { cx: t2.b }, duration: TEND2 - TS2, ease: 'none' }, TS2)
    }
    const take = TS2 + 0.5
    beam(1, pinAt(), bar(take), palette.warm, TS2 - 0.05, { burst: 24, bend: -0.35, duration: 0.55 })
    mark(1, 0, headAt(take), take)
    tl.to(of(1, '.glow'), { autoAlpha: 1, duration: 0.3 }, take)
    tl.to(of(1, '.glow'), { autoAlpha: 0, duration: 1.2 }, take + 0.4)
    tl.to(of(1, '.pin-0'), { autoAlpha: 0, y: -6, duration: 0.35 }, take)
    say(1, 4, take + 0.1)
    say(1, 5, take + 0.8)

    // 4 · the left again: two lines typed in a row are taken one after the other.
    const T4 = 11.2
    tl.addLabel('beat-4', T4)
    tl.to(lens[0], { s: l.focus, duration: 1.2, ease: 'cine', onUpdate: applyLens }, T4)
    tl.to(lens[1], { s: 2 - l.focus, duration: 1.2, ease: 'cine', onUpdate: applyLens }, T4)
    tl.to(of(0, '.side-in'), { autoAlpha: 1, duration: 0.8 }, T4)
    tl.to(of(1, '.side-in'), { autoAlpha: 0.38, duration: 1 }, T4)
    tl.to(of(1, '.halo'), { autoAlpha: 0, duration: 0.8 }, T4)
    tl.to(of(0, '.halo'), { autoAlpha: 1, duration: 1 }, T4)
    const typing = (text: string, at: number) => {
      tl.to(of(0, '.prompt-lit'), { autoAlpha: 1, duration: 0.2 }, at)
      tl.set(of(0, '.typed'), { text: '' }, at)
      tl.to(of(0, '.typed'), { text: { value: text }, duration: text.length / 26, ease: 'none' }, at)
      tl.to(of(0, '.typed'), { autoAlpha: 0, y: -12, duration: 0.25, ease: 'cine.in' }, at + text.length / 26 + 0.15)
      tl.set(of(0, '.typed'), { text: '', autoAlpha: 1, y: 0 }, at + text.length / 26 + 0.45)
      tl.to(of(0, '.prompt-lit'), { autoAlpha: 0, duration: 0.3 }, at + text.length / 26 + 0.4)
    }
    typing('use pathlib', T4 + 0.6)
    tl.fromTo(of(0, '.pin-1'), { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.35 }, T4 + 1.2)
    tl.to(of(0, '.pin-1 .with'), { fillOpacity: 1, duration: 0.3 }, T4 + 1.35)
    typing('keep the CLI', T4 + 1.4)
    tl.fromTo(of(0, '.pin-2'), { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.35 }, T4 + 2.05)
    const first = T4 + 2.7
    beam(0, pinAt(1), bar(first), palette.accent, first - 0.6, { burst: 20, bend: -0.35 })
    mark(0, 1, headAt(first), first)
    tl.to(of(0, '.pin-1'), { autoAlpha: 0, y: -6, duration: 0.3 }, first)
    say(0, 5, first + 0.1)
    say(0, 6, first + 0.7)
    tl.to(of(0, '.pin-2'), { y: -l.row, duration: 0.5, ease: 'cine' }, first + 0.3)
    tl.to(of(0, '.pin-2 .with'), { fillOpacity: 1, duration: 0.3 }, first + 0.8)
    const second = first + 1.9
    beam(0, pinAt(1), bar(second), palette.accent, second - 0.6, { burst: 20, bend: -0.35 })
    mark(0, 2, headAt(second), second)
    tl.to(of(0, '.pin-2'), { autoAlpha: 0, y: -l.row - 6, duration: 0.3 }, second)
    say(0, 7, second + 0.1)
    say(0, 8, second + 0.7)

    // The world goes dark before it starts again, so the seam never shows.
    const END = second + 2.6
    tl.to(lens, { s: 1, duration: 1, ease: 'cine', onUpdate: applyLens }, END - 1.4)
    tl.to(all('.side-in'), { autoAlpha: 1, duration: 0.6 }, END - 1.4)
    tl.to(all('.halo'), { autoAlpha: 0, duration: 0.6 }, END - 1.4)
    tl.to(worldEl, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, END)
    tl.set(worldEl, { autoAlpha: 1 }, 0)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="36 / 50"
    label="Two backends side by side, each running a turn. The same line, and fix the tests too, is typed at both while they work, and is pinned above the prompt. Claude Code, Codex, Kimi Code and pi take it into the turn that is running, and answer it there. Every other backend refuses it mid-turn: the line goes back on the pin and waits, and the next turn takes it as it starts. Two more lines typed in a row are taken one after the other."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <radialGradient id="steer-halo-0">
          <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.32" />
          <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="steer-halo-1">
          <stop offset="0" stop-color="var(--hmz-warm)" stop-opacity="0.32" />
          <stop offset="1" stop-color="var(--hmz-warm)" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="steer-flare">
          <stop offset="0" stop-color="#fff" stop-opacity="0.9" />
          <stop offset="0.35" stop-color="var(--hmz-lane-5)" stop-opacity="0.6" />
          <stop offset="1" stop-color="var(--hmz-lane-5)" stop-opacity="0" />
        </radialGradient>
        <clipPath v-for="(h, i) in L.halves" :id="`steer-rows-${i}`" :key="`c${i}`">
          <rect :x="0" :y="L.row0 - L.row + 4" :width="L.W" :height="L.rows * L.row" />
        </clipPath>
      </defs>
      <g class="world">
        <g v-for="(side, i) in SIDES" :key="side.title" class="side" :class="`side-${i}`">
          <ellipse
            class="halo"
            :cx="L.halves[i].x + L.W / 2"
            :cy="L.halves[i].y + L.H / 2"
            :rx="L.W * 0.75"
            :ry="L.H * 0.7"
            :fill="`url(#steer-halo-${i})`"
          />
          <g :transform="`translate(${L.halves[i].x} ${L.halves[i].y})`"><g class="side-in">
            <rect class="card-bg" :width="L.W" :height="L.H" rx="14" />
            <rect class="card" :width="L.W" :height="L.H" rx="14" :style="{ stroke: side.hue }" />

            <g class="side-words">
              <circle :cx="PAD + 4" :cy="L.head - 4" r="4" :style="{ fill: side.hue }" />
              <text class="t-head" :x="PAD + 14" :y="L.head" :style="{ fill: side.hue }">{{ side.title }}</text>
              <text class="t-sub" :x="PAD" :y="L.sub">{{ side.who }}</text>
            </g>

            <g class="track">
              <rect class="slot" :x="turn1.a" :y="L.track" :width="turn1.b - turn1.a" height="8" rx="4" />
              <rect class="slot" :x="turn2.a" :y="L.track" :width="turn2.b - turn2.a" height="8" rx="4" />
              <rect class="fill fill1" :x="turn1.a" :y="L.track" width="0" height="8" rx="4" :style="{ fill: side.hue }" />
              <rect class="fill fill2" :x="turn2.a" :y="L.track" width="0" height="8" rx="4" :style="{ fill: side.hue }" />
              <circle v-if="i === 1" class="flare" :cx="turn1.a" :cy="L.track + 4" r="22" fill="url(#steer-flare)" />
              <circle class="head-glow head" :cx="turn1.a" :cy="L.track + 4" r="11" :fill="`url(#steer-halo-${i})`" />
              <circle class="head" :cx="turn1.a" :cy="L.track + 4" r="4.5" :style="{ fill: side.hue }" />
              <g v-for="n in 3" :key="`m${n}`" class="mark" transform="translate(0 0)"><g class="mark-in">
                <circle class="glow" r="14" :fill="`url(#steer-halo-${i})`" />
                <rect x="-5" y="-5" width="10" height="10" rx="2" transform="rotate(45)" class="mark-gem" />
              </g></g>
            </g>
            <text class="t-turn turn-word-1" :x="turn1.a" :y="L.turnWord">turn 1</text>
            <text class="t-turn" :x="turn2.a" :y="L.turnWord">turn 2</text>

            <g :clip-path="`url(#steer-rows-${i})`">
              <g class="scroll">
                <text
                  v-for="(one, n) in SAID[i]"
                  :key="n"
                  class="said"
                  :class="one.kind"
                  :x="PAD"
                  :y="L.row0 + n * L.row"
                >{{ one.text }}</text>
              </g>
            </g>

            <g
              v-for="(pin, n) in i === 0 ? PINS : PINS.slice(0, 1)"
              :key="pin.text"
              class="pin"
              :class="`pin-${n}`"
            >
              <rect class="pin-chip" :x="PAD - 4" :y="pin.slot ? L.pin - L.row - 13 : L.pin - 13" :width="chip(pin.text)" height="18" rx="9" />
              <text :x="PAD + 4" :y="pin.slot ? L.pin - L.row : L.pin"><tspan class="pin-caret">❯</tspan> {{ pin.text }}<tspan class="with"> · with actor</tspan></text>
            </g>

            <rect class="prompt" :x="PAD - 4" :y="L.prompt" :width="L.W - 2 * PAD + 8" :height="L.promptH" rx="9" />
            <rect class="prompt prompt-lit" :x="PAD - 4" :y="L.prompt" :width="L.W - 2 * PAD + 8" :height="L.promptH" rx="9" :style="{ stroke: side.hue }" />
            <text class="caret" :x="PAD + 6" :y="L.prompt + L.promptH / 2 + 4.5" :style="{ fill: side.hue }">❯</text>
            <text class="typed" :x="PAD + 22" :y="L.prompt + L.promptH / 2 + 4.5" />
          </g></g>
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

.card-bg {
  fill: var(--hmz-stage-card);
}

.card {
  fill: none;
  stroke-width: 1.3;
  stroke-opacity: 0.55;
}

.halo {
  opacity: 0;
}

.t-head {
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.t-sub {
  font-size: 11.5px;
  fill: var(--hmz-stage-dim);
}

.t-turn {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.slot {
  fill: var(--hmz-stage-line);
}

.mark-gem {
  fill: var(--hmz-stage-ink);
  stroke: var(--hmz-stage-card);
  stroke-width: 1.5;
}

.said,
.pin,
.typed,
.caret {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
}

.said.tool {
  fill: var(--hmz-stage-dim);
}

.said.you {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.side-1 .said.you {
  fill: var(--hmz-warm);
}

.said.say {
  fill: var(--hmz-stage-ink);
}

.said.warn {
  fill: var(--hmz-lane-5);
  font-weight: 600;
}

.pin text {
  fill: var(--hmz-stage-ink);
  font-weight: 600;
}

.pin-chip {
  fill: var(--hmz-stage-line);
}

.pin-caret {
  fill: var(--hmz-stage-dim);
}

.with {
  fill: var(--hmz-stage-dim);
  font-weight: 400;
}

.prompt {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.prompt-lit {
  stroke-width: 1.6;
}

.typed {
  fill: var(--hmz-stage-ink);
}

.caret {
  font-weight: 700;
}

.flare {
  opacity: 0;
}

@media (max-width: 640px) {
  .said,
  .pin,
  .typed {
    font-size: 11px;
  }
}
</style>
