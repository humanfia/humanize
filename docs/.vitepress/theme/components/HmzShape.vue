<script setup lang="ts">
// A turn asked for a shape answers in it, or fails. The flow names fields; a CLI that can
// hold the shape is given it as a setting of its own, and the rest are given it in the prompt
// (`SessionBase._shaped_ask` in `src/hmz/coganchor/agents/base.py`) and the answer is checked
// when it comes back. Which is which is each backend's `shapes` in `src/hmz/coganchor/agents/`;
// a CLI added in /settings is asked. The answer lands as the fields: one decides whether the
// loop goes round again, one carries the notes into the next prompt (`rlar`'s `Review` in
// `src/hmz/flows/builtin/rlar/__init__.py`). An answer out of shape fails the turn with
// `OutputSchemaError`, and the same shape put to a person is a question per field. Pick a CLI.
//
// Each kind of field is drawn as a socket of its own shape -- a toggle for yes or no, a strip
// for text -- and the same shapes are what the CLI is handed, what the answer is cut into, and
// what an answer out of shape does not fit.
import { computed, nextTick, ref, useId } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { rig } from '../motion/camera'
import { createFx, fly, type Fx } from '../motion/fx'
import { motion } from '../motion/gsap'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'

const HELD = ['claude', 'codex', 'agy', 'grok', 'mcode', 'qwen']
const ASKED = ['cursor-agent', 'dsh', 'kimi', 'mimo', 'omp', 'opencode', 'pi', 'a CLI you added']

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
  { name: 'done', type: 'yes or no', first: 'no', person: 'no', tag: 'decides' },
  { name: 'notes', type: 'text', first: 'fix the parser', person: 'add a test', tag: 'carries' },
]

// What comes back, as written: a line of JSON. The parts set apart are the values the fields
// are cut from; the second line is an answer out of shape.
type Part = [string, '' | 'hl' | 'bad']
const RAW: Part[][] = [
  [
    ['{"done": ', ''],
    ['false', 'hl'],
    [', "notes": ', ''],
    ['"fix the parser"', 'hl'],
    ['}', ''],
  ],
  [
    ['{"done": ', ''],
    ['"maybe"', 'bad'],
    ['}', ''],
  ],
]
const rawLen = (k: number) => RAW[k].reduce((n, [s]) => n + s.length, 0)

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

interface Spot {
  x: number
  y: number
  anchor?: string
}

interface Layout {
  w: number
  h: number
  open: { x: number; y: number; s: number }
  S: Rect
  capS: Spot
  head: Spot
  rows: number[]
  type: { dx: number; dy: number }
  /** The sockets in the flow's card, one per field, in the shape of its kind. */
  sock: Rect[]
  R: Rect
  capR: Spot
  rRows: number[]
  slot: { x: number; w: number }
  tags: Spot[]
  C: Rect
  cliName: Spot
  orb: { x: number; y: number; r: number }
  clamp: Rect
  mode: Spot
  sheet: Rect
  gate: { x1: number; y1: number; x2: number; y2: number }
  gateLabel: Spot
  into: string
  out: string
  arc: string
  arcLabel: Spot
  raw: Spot
  q: Rect
  stamp: Spot
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  open: { x: 112, y: 167, s: 1.5 },
  S: { x: 24, y: 92, w: 176, h: 150 },
  capS: { x: 24, y: 80 },
  head: { x: 40, y: 120 },
  rows: [154, 204],
  type: { dx: 0, dy: 17 },
  sock: [
    { x: 144, y: 141, w: 40, h: 18 },
    { x: 128, y: 190, w: 56, h: 22 },
  ],
  R: { x: 420, y: 92, w: 198, h: 150 },
  capR: { x: 420, y: 80 },
  rRows: [154, 204],
  slot: { x: 488, w: 118 },
  tags: [
    { x: 606, y: 175, anchor: 'end' },
    { x: 606, y: 225, anchor: 'end' },
  ],
  C: { x: 262, y: 112, w: 116, h: 108 },
  cliName: { x: 320, y: 136 },
  orb: { x: 320, y: 178, r: 14 },
  clamp: { x: 296, y: 154, w: 48, h: 48 },
  mode: { x: 320, y: 238, anchor: 'middle' },
  sheet: { x: 212, y: 146, w: 32, h: 42 },
  gate: { x1: 399, y1: 128, x2: 399, y2: 206 },
  gateLabel: { x: 399, y: 258, anchor: 'middle' },
  into: 'M200 167 L262 167',
  out: 'M378 167 L420 167',
  arc: 'M519 242 C519 332 112 332 112 248',
  arcLabel: { x: 316, y: 332, anchor: 'middle' },
  raw: { x: 320, y: 46 },
  q: { x: 232, y: 18, w: 176, h: 88 },
  stamp: { x: 519, y: 274 },
}

const NARROW: Layout = {
  w: 360,
  h: 460,
  open: { x: 186, y: 89, s: 1.15 },
  S: { x: 52, y: 42, w: 268, h: 94 },
  capS: { x: 52, y: 32 },
  head: { x: 66, y: 66 },
  rows: [96, 124],
  type: { dx: 70, dy: 0 },
  sock: [
    { x: 262, y: 85, w: 40, h: 16 },
    { x: 246, y: 111, w: 56, h: 18 },
  ],
  R: { x: 52, y: 338, w: 268, h: 96 },
  capR: { x: 52, y: 330 },
  rRows: [372, 410],
  slot: { x: 124, w: 182 },
  tags: [
    { x: 298, y: 372, anchor: 'end' },
    { x: 298, y: 410, anchor: 'end' },
  ],
  C: { x: 52, y: 164, w: 268, h: 84 },
  cliName: { x: 112, y: 186 },
  orb: { x: 112, y: 220, r: 12 },
  clamp: { x: 92, y: 200, w: 40, h: 40 },
  mode: { x: 300, y: 240, anchor: 'end' },
  sheet: { x: 236, y: 176, w: 30, h: 40 },
  gate: { x1: 124, y1: 262, x2: 236, y2: 262 },
  gateLabel: { x: 244, y: 266, anchor: 'start' },
  into: 'M186 136 L186 164',
  out: 'M186 248 L186 338',
  arc: 'M52 392 C18 392 18 80 48 80',
  arcLabel: { x: 15, y: 236, anchor: 'middle' },
  raw: { x: 182, y: 296 },
  q: { x: 150, y: 172, w: 160, h: 68 },
  stamp: { x: 182, y: 296 },
}

const id = useId()
const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined
const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const mid = (r: Rect) => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 })
const slotY = (i: number) => L.value.rRows[i] - 18

// A character of the answer's line, with room on a phone for its words to be lifted (see
// HmzStage), and the chip the line sits in.
const CH = computed(() => (narrow.value ? 6.9 * 1.08 : 6.9))
const rawW = (k: number) => rawLen(k) * CH.value + 22
const rawX0 = (k: number) => L.value.raw.x - rawW(k) / 2 + 11
/** The middle of part `p` of answer `k`, where its value is read from. */
function partAt(k: number, p: number) {
  const before = RAW[k].slice(0, p).reduce((n, [s]) => n + s.length, 0)
  return { x: rawX0(k) + (before + RAW[k][p][0].length / 2) * CH.value, y: L.value.raw.y - 4 }
}

// The sockets as one piece: what the CLI is handed.
const moldBox = computed(() => {
  const [a, b] = L.value.sock
  const x0 = Math.min(a.x, b.x)
  const y0 = Math.min(a.y, b.y)
  const x1 = Math.max(a.x + a.w, b.x + b.w)
  const y1 = Math.max(a.y + a.h, b.y + b.h)
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
})

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
    const gsap = motion()
    const l = L.value
    const isHeld = held.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const get = () => fx
    const at = (s: string) => q(s)
    const one = (s: string) => q(s)[0]
    const world = one('.sh-world')
    const slotMid = (i: number) => ({ x: l.slot.x + l.slot.w / 2, y: slotY(i) + 13 })
    const orb = { x: l.orb.x, y: l.orb.y }
    const s = mid(l.S)
    const home = { x: l.w / 2, y: l.h / 2, s: 1 }

    const cam = rig(tl, { w: l.w, h: l.h, world, far: one('.sh-far'), fx: () => fx, start: l.open })
    const flare = (p: { x: number; y: number }, color: () => string, when: number, n = 20, speed = 100) => cam.flare(p, color, when, n, speed)
    const beam = (from: { x: number; y: number }, to: { x: number; y: number }, color: () => string, when: number, o: { duration?: number; bend?: number; burst?: number; size?: number } = {}) =>
      cam.beam(from, to, color, when, { duration: o.duration ?? 0.6, bend: o.bend ?? 0.15, burst: o.burst, size: o.size ?? 2.6, speed: 70 })
    const pulse = (el: Element | Element[], when: number, k = 1.3) =>
      tl.fromTo(el, { scale: 1 }, { keyframes: { scale: [1, k, 1] }, duration: 0.5, transformOrigin: '50% 50%' }, when)
    const reveal = (k: number, when: number, duration: number) => {
      tl.set(at('.sh-raw')[k], { autoAlpha: 1 }, when)
      tl.fromTo(at('.sh-raw-chip')[k], { attr: { width: 22 } }, { attr: { width: rawW(k) }, duration, ease: 'none' }, when)
      tl.fromTo(at('.sh-raw-clip')[k], { attr: { width: 0 } }, { attr: { width: rawW(k) }, duration, ease: 'none' }, when)
    }

    // Where every loop starts.
    tl.set(world, { autoAlpha: 1 }, 0)
    tl.set(at('.sh-c, .sh-r, .sh-clamp-g, .sh-sheet, .sh-gate, .sh-val, .sh-arc-g, .sh-note, .sh-bad, .sh-stamp, .sh-pval, .sh-q, .sh-person, .sh-pick, .sh-typed, .sh-mold, .sh-raw, .sh-tag, .sh-mode, .sh-lit, .sh-dash, .sh-grid'), { autoAlpha: 0 }, 0)
    tl.set(at('.sh-machine'), { autoAlpha: 1 }, 0)
    tl.set(at('.sh-typed'), { text: '' }, 0)
    tl.set(at('.sh-knob'), { x: 0 }, 0)

    // 0 · the flow names its fields, close up: a card drawn on paper, and under each field the
    // socket of its kind.
    tl.addLabel('beat-0', 0)
    cam.shot({ s: l.open.s * 0.95 }, 0, 2.8, 'none')
    tl.to(at('.sh-grid'), { autoAlpha: 0.7, duration: 1.2, ease: 'power1.out' }, 0)
    tl.fromTo(one('.sh-s-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1, ease: 'cine' }, 0.1)
    tl.fromTo(at('.sh-s-words'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.5, stagger: 0.18 }, 0.4)
    tl.fromTo(at('.sh-field'), { autoAlpha: 0, x: -10 }, { autoAlpha: 1, x: 0, duration: 0.5, stagger: 0.3 }, 0.9)
    tl.fromTo(at('.sh-sock-line'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.7, stagger: 0.25, ease: 'cine' }, 1.3)
    tl.fromTo(at('.sh-sock-in'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3, stagger: 0.25 }, 1.8)
    // The toggle is tried once, so its kind reads as yes or no.
    const knobRun = l.sock[0].w - l.sock[0].h
    tl.to(at('.sh-knob'), { x: knobRun, duration: 0.35, ease: 'back.out(2)' }, 2.1)
    tl.to(at('.sh-knob'), { x: 0, duration: 0.35, ease: 'back.out(2)' }, 2.55)

    // 1 · the shape goes to the CLI: held by the CLI itself, or written into the prompt.
    const T1 = 2.9
    tl.addLabel('beat-1', T1)
    cam.shot(home, T1, 1.4)
    tl.to(at('.sh-c, .sh-r'), { autoAlpha: 1, duration: 0.5, stagger: 0.2 }, T1 + 0.4)
    tl.fromTo(one('.sh-c-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.9, ease: 'cine' }, T1 + 0.4)
    tl.fromTo(one('.sh-r-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.9, ease: 'cine' }, T1 + 0.6)
    tl.fromTo(one('.sh-into'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.5 }, T1 + 0.9)
    tl.to(one('.sh-dash-in'), { autoAlpha: 1, duration: 0.4 }, T1 + 1.3)

    // A copy of the sockets lifts off the card and travels: into the CLI, or onto the prompt.
    const mold = one('.sh-mold')
    const mb = moldBox.value
    const mc = mid(mb)
    const dest = isHeld ? orb : mid(l.sheet)
    const moldAt = T1 + (isHeld ? 1.0 : 1.3)
    tl.set(mold, { x: 0, y: 0, scale: 1, svgOrigin: `${mc.x} ${mc.y}` }, 0)
    tl.to(mold, { autoAlpha: 1, duration: 0.2 }, moldAt)
    tl.to(
      mold,
      {
        motionPath: { path: [{ x: 0, y: 0 }, { x: (dest.x - mc.x) / 2, y: (dest.y - mc.y) / 2 - 46 }, { x: dest.x - mc.x, y: dest.y - mc.y }], curviness: 1.2 },
        scale: isHeld ? 0.42 : 0.4,
        duration: 0.9,
        ease: 'cine',
        onUpdate() {
          const v = cam.view({ x: mc.x + Number(gsap.getProperty(mold, 'x')), y: mc.y + Number(gsap.getProperty(mold, 'y')) })
          fx?.trail(v.x, v.y, palette.accent, 2.4)
        },
      },
      moldAt,
    )
    tl.to(mold, { autoAlpha: 0, duration: 0.25 }, moldAt + 0.9)
    if (isHeld) {
      // Taken in whole: the clamp closes round the CLI, which now holds the shape itself.
      const lock = moldAt + 0.85
      tl.to(one('.sh-clamp-g'), { autoAlpha: 1, duration: 0.1 }, lock)
      tl.fromTo(one('.sh-clamp'), { drawSVG: '50% 50%' }, { drawSVG: '0% 100%', duration: 0.6, ease: 'cine' }, lock)
      tl.fromTo(one('.sh-orb'), { scale: 1.4, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.6, ease: 'back.out(3)' }, lock + 0.05)
      flare(orb, () => palette.accent, lock, 18, 80)
      tl.fromTo(one('.sh-mode'), { autoAlpha: 0, y: 4 }, { autoAlpha: 1, y: 0, duration: 0.4 }, lock + 0.3)
    } else {
      // Written into the prompt: the sheet comes off the card, the sockets are printed on it,
      // and a check stands on the way back.
      const sheet = one('.sh-sheet')
      const from = { x: s.x - mid(l.sheet).x, y: s.y - mid(l.sheet).y }
      tl.fromTo(sheet, { autoAlpha: 0, x: from.x, y: from.y, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, x: 0, y: 0, scale: 1, duration: 0.9, ease: 'cine' }, T1 + 0.8)
      const printed = moldAt + 0.85
      tl.fromTo(one('.sh-sheet-shape'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3 }, printed)
      flare(mid(l.sheet), () => palette.accent, printed, 14, 80)
      tl.fromTo(one('.sh-mode'), { autoAlpha: 0, y: 4 }, { autoAlpha: 1, y: 0, duration: 0.4 }, printed + 0.2)
      tl.to(one('.sh-gate'), { autoAlpha: 1, duration: 0.3 }, printed + 0.3)
      tl.fromTo(one('.sh-gate-line'), { drawSVG: '50% 50%' }, { drawSVG: '0% 100%', duration: 0.5 }, printed + 0.3)
    }

    // 2 · the answer comes back as a line of JSON, and its values are cut out into the fields.
    const T2 = T1 + 3.3
    tl.addLabel('beat-2', T2)
    tl.fromTo(one('.sh-out'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.5 }, T2)
    tl.to(one('.sh-dash-out'), { autoAlpha: 1, duration: 0.4 }, T2 + 0.4)
    pulse(one('.sh-orb'), T2)
    beam(orb, { x: l.raw.x, y: l.raw.y }, () => palette.lane[0], T2 + 0.1, { duration: 0.5, bend: 0.2 })
    reveal(0, T2 + 0.5, 1.1)
    if (!isHeld) {
      tl.fromTo(one('.sh-gate-line'), { opacity: 1 }, { keyframes: { opacity: [1, 0.3, 1, 0.3, 1] }, duration: 0.5 }, T2 + 1.5)
      tl.fromTo(one('.sh-gate-ok'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.25, yoyo: true, repeat: 1, repeatDelay: 0.4 }, T2 + 1.6)
    }
    FIELDS.forEach((_, i) => {
      const w = T2 + 1.75 + i * 0.25
      beam(partAt(0, i ? 3 : 1), slotMid(i), () => palette.accent, w, { duration: 0.6, bend: i ? -0.18 : 0.18, burst: 12 })
      tl.fromTo(at('.sh-lit')[i], { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.2, yoyo: true, repeat: 1, repeatDelay: 0.15 }, w + 0.5)
      tl.fromTo(at('.sh-v1')[i], { autoAlpha: 0, scale: 0.6, transformOrigin: '0% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(2.2)' }, w + 0.55)
    })

    // 3 · done is no, so the loop goes round again, and the notes are the next prompt.
    const T3 = T2 + 3.1
    tl.addLabel('beat-3', T3)
    tl.to(one('.sh-raw'), { autoAlpha: 0, duration: 0.4 }, T3)
    tl.fromTo(at('.sh-tag'), { autoAlpha: 0, y: 4 }, { autoAlpha: 1, y: 0, duration: 0.4, stagger: 0.35 }, T3)
    pulse(at('.sh-slot')[0], T3, 1.08)
    tl.to(one('.sh-arc-g'), { autoAlpha: 1, duration: 0.1 }, T3 + 0.4)
    tl.fromTo(one('.sh-arc'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1, ease: 'cine' }, T3 + 0.4)
    fly(tl, one('.sh-note'), one('.sh-arc') as SVGPathElement, T3 + 1.1, { duration: 1.3, fx: get, color: palette.warm })
    flare({ x: l.S.x + (narrow.value ? 0 : l.S.w * 0.5), y: narrow.value ? 80 : l.S.y + l.S.h }, () => palette.warm, T3 + 2.4, 22, 100)
    tl.fromTo(one('.sh-s-frame'), { opacity: 1 }, { keyframes: { opacity: [1, 0.3, 1] }, duration: 0.4 }, T3 + 2.4)

    // 4 · the next answer is not the shape: a word where a yes or no should be. It does not fit
    // the socket, and the turn fails.
    const T4 = T3 + 3.1
    tl.addLabel('beat-4', T4)
    tl.to(at('.sh-val, .sh-tag'), { autoAlpha: 0, duration: 0.3 }, T4)
    tl.to(one('.sh-arc-g'), { autoAlpha: 0, duration: 0.3 }, T4)
    pulse(one('.sh-orb'), T4 + 0.1)
    reveal(1, T4 + 0.3, 0.6)
    const miss = slotMid(0)
    beam(partAt(1, 1), miss, () => palette.danger, T4 + 1.0, { duration: 0.5, bend: 0.25, size: 3 })
    flare(miss, () => palette.danger, T4 + 1.5, 30, 130)
    tl.fromTo(at('.sh-slot')[0], { x: 0 }, { keyframes: { x: [0, -5, 5, -3, 3, 0] }, duration: 0.4, ease: 'none' }, T4 + 1.5)
    if (!isHeld) {
      tl.fromTo(one('.sh-gate-line'), { opacity: 1 }, { keyframes: { opacity: [1, 0.2, 1, 0.2, 1] }, duration: 0.4 }, T4 + 1.4)
      tl.fromTo(one('.sh-gate'), { x: 0 }, { keyframes: { x: [0, -4, 4, -2, 2, 0] }, duration: 0.4, ease: 'none' }, T4 + 1.5)
    }
    tl.fromTo(at('.sh-bad'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.25, stagger: 0.08 }, T4 + 1.55)
    // On a phone the verdict takes the place of the line it is about.
    if (narrow.value) tl.to(at('.sh-raw')[1], { autoAlpha: 0, duration: 0.25 }, T4 + 1.7)
    tl.fromTo(one('.sh-stamp'), { autoAlpha: 0, scale: 1.5, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.5, ease: 'back.out(1.8)' }, T4 + 1.8)
    tl.to(at('.sh-bad, .sh-stamp'), { autoAlpha: 0, duration: 0.4 }, T4 + 3.1)
    tl.to(at('.sh-raw')[1], { autoAlpha: 0, duration: 0.4 }, T4 + 3.1)

    // 5 · the same fields, put to a person: a question each, the answers in the same slots.
    const T5 = T4 + 3.5
    tl.addLabel('beat-5', T5)
    tl.to(one('.sh-machine'), { autoAlpha: 0, duration: 0.4 }, T5)
    tl.to(at('.sh-clamp-g, .sh-sheet, .sh-gate, .sh-mode'), { autoAlpha: 0, duration: 0.4 }, T5)
    tl.fromTo(one('.sh-person'), { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.5 }, T5 + 0.3)
    tl.fromTo(one('.sh-q'), { autoAlpha: 0, scale: 0.85, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.5, ease: 'back.out(1.6)' }, T5 + 0.5)
    tl.fromTo(one('.sh-pick'), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.3, ease: 'back.out(2)' }, T5 + 1.3)
    tl.set(one('.sh-typed'), { autoAlpha: 1 }, T5 + 1.6)
    tl.to(one('.sh-typed'), { text: { value: FIELDS[1].person }, duration: 0.6, ease: 'none' }, T5 + 1.6)
    const qMid = mid(l.q)
    FIELDS.forEach((_, i) => {
      beam(qMid, slotMid(i), () => palette.lane[0], T5 + 2.4 + i * 0.15, { duration: 0.6, bend: 0.2, burst: 10 })
      tl.fromTo(at('.sh-pval')[i], { autoAlpha: 0, scale: 0.6, transformOrigin: '0% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, T5 + 2.95 + i * 0.15)
    })
    tl.addLabel('rest', T5 + 3.8)
    tl.to(world, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T5 + 5.6)
    tl.set(at('.sh-pval'), { autoAlpha: 0 }, T5 + 6.3)

    // Underneath it all, the slow motion that keeps a still frame alive: the wires carry, the
    // CLI breathes. Laid over the whole timeline, so a seek lands on it like on anything else.
    const D = tl.duration()
    tl.fromTo(at('.sh-dash'), { strokeDashoffset: 0 }, { strokeDashoffset: -D * 10, duration: D, ease: 'none' }, 0)
    tl.fromTo(at('.sh-breath'), { scale: 0.9, opacity: 0.5, transformOrigin: '50% 50%' }, { scale: 1.25, opacity: 0, duration: 1.6, ease: 'sine.out', repeat: Math.floor(D / 1.6) - 1 }, 0)
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
      mobile-ratio="36 / 46"
      :label="`A flow asks for two fields: done, yes or no, and notes, text. ${held ? `${shown} holds the shape as a setting of its own` : `${shown} is given the shape in the prompt, and the answer is checked when it comes back`}. The answer comes back as a line of JSON and its values land as the fields: done is no, so the loop goes round again, and the notes become the next prompt. An answer that is not the shape, a word where a yes or no should be, fails the turn. Put to a person, the same fields are a question each, and the answers land in the same fields.`"
    >
      <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
        <defs>
          <pattern :id="`${id}-grid`" width="20" height="20" patternUnits="userSpaceOnUse">
            <path class="grid-minor" d="M20 0 H0 V20" />
          </pattern>
          <pattern :id="`${id}-major`" width="80" height="80" patternUnits="userSpaceOnUse">
            <path class="grid-major" d="M80 0 H0 V80" />
          </pattern>
          <radialGradient :id="`${id}-glow`">
            <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.5" />
            <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
          </radialGradient>
          <marker :id="`${id}-tip`" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path class="tip-warm" d="M0 1 L9 5 L0 9 Z" />
          </marker>
          <clipPath v-for="(_, k) in RAW" :id="`${id}-raw-${k}`" :key="`clip${k}`">
            <rect class="sh-raw-clip" :x="L.raw.x - rawW(k) / 2" :y="L.raw.y - 20" :width="rawW(k)" height="30" />
          </clipPath>
        </defs>

        <!-- The paper the scene is drawn on, a little behind it: it moves a third as far. -->
        <g class="sh-far">
          <g class="sh-grid">
            <rect x="-600" y="-600" width="1840" height="1700" :fill="`url(#${id}-grid)`" />
            <rect x="-600" y="-600" width="1840" height="1700" :fill="`url(#${id}-major)`" />
          </g>
        </g>

        <g class="sh-world">
          <!-- The flow's shape. Words that move are moved by a group: a word's own transform is
               the stage's, to lift it on a phone. -->
          <g class="sh-s-words"><text class="sh-cap" :x="L.capS.x" :y="L.capS.y">the flow asks for</text></g>
          <rect class="sh-card" :x="L.S.x" :y="L.S.y" :width="L.S.w" :height="L.S.h" rx="14" />
          <rect class="sh-s-frame" :x="L.S.x" :y="L.S.y" :width="L.S.w" :height="L.S.h" rx="14" />
          <g class="sh-s-words">
            <text class="sh-head" :x="L.head.x" :y="L.head.y"><tspan class="sh-kw">class</tspan> Review</text>
          </g>
          <g v-for="(f, i) in FIELDS" :key="f.name" class="sh-field">
            <text class="sh-fname" :x="L.head.x" :y="L.rows[i]">{{ f.name }}</text>
            <text class="sh-ftype" :x="L.head.x + L.type.dx" :y="L.rows[i] + L.type.dy">{{ f.type }}</text>
          </g>
          <!-- A socket per field, in the shape of its kind: a toggle, a strip of text. -->
          <g class="sh-sock">
            <rect class="sh-sock-line" :x="L.sock[0].x" :y="L.sock[0].y" :width="L.sock[0].w" :height="L.sock[0].h" :rx="L.sock[0].h / 2" />
            <g class="sh-sock-in">
              <circle class="sh-knob" :cx="L.sock[0].x + L.sock[0].h / 2" :cy="L.sock[0].y + L.sock[0].h / 2" :r="L.sock[0].h / 2 - 3.5" />
            </g>
            <rect class="sh-sock-line" :x="L.sock[1].x" :y="L.sock[1].y" :width="L.sock[1].w" :height="L.sock[1].h" rx="4" />
            <g class="sh-sock-in">
              <line class="sh-sock-text" :x1="L.sock[1].x + 7" :x2="L.sock[1].x + L.sock[1].w - 9" :y1="L.sock[1].y + L.sock[1].h / 2 - 3" :y2="L.sock[1].y + L.sock[1].h / 2 - 3" />
              <line class="sh-sock-text" :x1="L.sock[1].x + 7" :x2="L.sock[1].x + L.sock[1].w - 24" :y1="L.sock[1].y + L.sock[1].h / 2 + 3" :y2="L.sock[1].y + L.sock[1].h / 2 + 3" />
            </g>
          </g>

          <!-- The CLI, or the person. -->
          <path class="sh-beam sh-into" :d="L.into" />
          <path class="sh-dash sh-dash-in" :d="L.into" />
          <g class="sh-c">
            <circle class="sh-halo" :cx="L.orb.x" :cy="L.orb.y" :r="narrow ? 60 : 70" :fill="`url(#${id}-glow)`" />
            <rect class="sh-card" :x="L.C.x" :y="L.C.y" :width="L.C.w" :height="L.C.h" rx="16" />
            <rect class="sh-c-frame" :x="L.C.x" :y="L.C.y" :width="L.C.w" :height="L.C.h" rx="16" />
            <g class="sh-machine">
              <text class="sh-cli" :x="L.cliName.x" :y="L.cliName.y" text-anchor="middle">{{ shown }}</text>
              <circle class="sh-breath" :cx="L.orb.x" :cy="L.orb.y" :r="L.orb.r + 6" />
              <g class="sh-orb">
                <circle class="sh-orb-core" :cx="L.orb.x" :cy="L.orb.y" :r="L.orb.r" />
              </g>
            </g>
            <g class="sh-clamp-g">
              <rect class="sh-clamp" :x="L.clamp.x" :y="L.clamp.y" :width="L.clamp.w" :height="L.clamp.h" rx="10" />
            </g>
            <g class="sh-mode">
              <text class="sh-mode-word" :x="L.mode.x" :y="L.mode.y" :text-anchor="L.mode.anchor">{{ held ? 'held as a setting' : 'written into the prompt' }}</text>
            </g>
            <g class="sh-person">
              <circle class="sh-person-line" :cx="L.orb.x" :cy="L.orb.y - 7" r="6" />
              <path class="sh-person-line" :d="`M${L.orb.x - 12} ${L.orb.y + 12} C${L.orb.x - 12} ${L.orb.y} ${L.orb.x + 12} ${L.orb.y} ${L.orb.x + 12} ${L.orb.y + 12}`" />
              <text class="sh-cli" :x="L.cliName.x" :y="L.cliName.y" text-anchor="middle">you</text>
            </g>
          </g>
          <g class="sh-sheet">
            <rect class="sh-paper" :x="L.sheet.x" :y="L.sheet.y" :width="L.sheet.w" :height="L.sheet.h" rx="3" />
            <line v-for="k in 3" :key="k" class="sh-paper-line" :x1="L.sheet.x + 5" :x2="L.sheet.x + L.sheet.w - 5" :y1="L.sheet.y + 4 + k * 6" :y2="L.sheet.y + 4 + k * 6" />
            <g class="sh-sheet-shape">
              <rect :x="L.sheet.x + 5" :y="L.sheet.y + L.sheet.h - 15" width="11" height="6" rx="3" />
              <rect :x="L.sheet.x + 5" :y="L.sheet.y + L.sheet.h - 7" :width="L.sheet.w - 10" height="4" rx="1" />
            </g>
          </g>
          <g class="sh-gate">
            <line class="sh-gate-line" :x1="L.gate.x1" :y1="L.gate.y1" :x2="L.gate.x2" :y2="L.gate.y2" />
            <line class="sh-gate-line sh-gate-ok" :x1="L.gate.x1" :y1="L.gate.y1" :x2="L.gate.x2" :y2="L.gate.y2" />
            <text class="sh-cap" :x="L.gateLabel.x" :y="L.gateLabel.y" :text-anchor="L.gateLabel.anchor">checked</text>
          </g>

          <!-- What the flow gets. -->
          <path class="sh-beam sh-out" :d="L.out" />
          <path class="sh-dash sh-dash-out" :d="L.out" />
          <g class="sh-r">
            <text class="sh-cap" :x="L.capR.x" :y="L.capR.y">the flow gets</text>
            <rect class="sh-card" :x="L.R.x" :y="L.R.y" :width="L.R.w" :height="L.R.h" rx="14" />
            <rect class="sh-r-frame" :x="L.R.x" :y="L.R.y" :width="L.R.w" :height="L.R.h" rx="14" />
            <g v-for="(f, i) in FIELDS" :key="`r${f.name}`">
              <text class="sh-fname" :x="L.R.x + 16" :y="L.rRows[i]">{{ f.name }}</text>
              <g class="sh-slot">
                <rect class="sh-slot-box" :x="L.slot.x" :y="slotY(i)" :width="L.slot.w" height="26" :rx="i === 0 ? 13 : 6" />
                <rect class="sh-lit" :x="L.slot.x" :y="slotY(i)" :width="L.slot.w" height="26" :rx="i === 0 ? 13 : 6" />
                <rect class="sh-bad" :x="L.slot.x" :y="slotY(i)" :width="L.slot.w" height="26" :rx="i === 0 ? 13 : 6" />
              </g>
              <g class="sh-val sh-v1"><text class="sh-val-word" :x="L.slot.x + 11" :y="L.rRows[i]" :class="{ no: i === 0 }">{{ f.first }}</text></g>
              <g class="sh-val sh-pval"><text class="sh-val-word" :x="L.slot.x + 11" :y="L.rRows[i]" :class="{ no: i === 0 }">{{ f.person }}</text></g>
              <g class="sh-tag"><text class="sh-tag-word" :x="L.tags[i].x" :y="L.tags[i].y" :text-anchor="L.tags[i].anchor">{{ f.tag }}</text></g>
            </g>
          </g>

          <!-- What comes back, as written. -->
          <g v-for="(parts, k) in RAW" :key="`raw${k}`" class="sh-raw">
            <rect class="sh-raw-chip" :class="{ bad: k === 1 }" :x="L.raw.x - rawW(k) / 2" :y="L.raw.y - 17" :width="rawW(k)" height="24" rx="6" />
            <g :clip-path="`url(#${id}-raw-${k})`">
              <text class="sh-raw-word" :x="rawX0(k)" :y="L.raw.y"><tspan v-for="(p, n) in parts" :key="n" :class="p[1]">{{ p[0] }}</tspan></text>
            </g>
          </g>

          <g :transform="`translate(${L.stamp.x} ${L.stamp.y})`">
            <g class="sh-stamp">
              <rect x="-80" y="-21" width="160" height="42" rx="12" />
              <text class="sh-err" y="-3" text-anchor="middle">OutputSchemaError</text>
              <text y="13" text-anchor="middle">the turn fails</text>
            </g>
          </g>

          <g class="sh-arc-g">
            <path class="sh-arc" :d="L.arc" :marker-end="`url(#${id}-tip)`" />
            <text v-if="!narrow" class="sh-again" :x="L.arcLabel.x" :y="L.arcLabel.y" text-anchor="middle">again, with the notes</text>
            <text v-else class="sh-again" :x="L.arcLabel.x" :y="L.arcLabel.y" text-anchor="middle" :transform="`rotate(-90 ${L.arcLabel.x} ${L.arcLabel.y})`">again</text>
          </g>
          <g class="sh-note">
            <rect x="0" y="0" width="50" height="20" rx="10" />
            <text x="25" y="14" text-anchor="middle">notes</text>
          </g>

          <!-- The copy of the sockets that is handed over. -->
          <g class="sh-mold">
            <rect class="sh-mold-line" :x="L.sock[0].x" :y="L.sock[0].y" :width="L.sock[0].w" :height="L.sock[0].h" :rx="L.sock[0].h / 2" />
            <rect class="sh-mold-line" :x="L.sock[1].x" :y="L.sock[1].y" :width="L.sock[1].w" :height="L.sock[1].h" rx="4" />
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

.grid-minor {
  fill: none;
  stroke: var(--hmz-grid);
  stroke-width: 0.5;
  stroke-opacity: 0.6;
}

.grid-major {
  fill: none;
  stroke: var(--hmz-grid);
  stroke-width: 1;
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
  stroke: var(--hmz-stage-dim);
  stroke-opacity: 0.45;
}

.sh-head {
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.sh-kw {
  fill: var(--hmz-accent-2);
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

.sh-sock-line,
.sh-mold-line {
  fill: color-mix(in srgb, var(--hmz-accent) 10%, transparent);
  stroke: var(--hmz-accent);
  stroke-width: 1.4;
}

.sh-mold-line {
  stroke-width: 2;
}

.sh-knob {
  fill: var(--hmz-accent);
}

.sh-sock-text {
  stroke: var(--hmz-accent);
  stroke-width: 1.6;
  stroke-linecap: round;
  opacity: 0.7;
}

.sh-beam {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-opacity: 0.45;
  stroke-width: 1.5;
  stroke-linecap: round;
}

.sh-dash {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.6;
  stroke-dasharray: 2 6;
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

.sh-breath {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.2;
}

.sh-clamp {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2.5;
}

.sh-mode-word {
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--hmz-accent);
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

.sh-sheet-shape rect {
  fill: var(--hmz-accent);
}

.sh-gate-line {
  stroke: var(--hmz-accent);
  stroke-width: 3;
  stroke-linecap: round;
}

.sh-gate-ok {
  stroke-width: 7;
  opacity: 0.35;
}

.sh-slot-box {
  fill: color-mix(in srgb, var(--hmz-accent) 6%, transparent);
  stroke: var(--hmz-stage-dim);
  stroke-opacity: 0.5;
  stroke-width: 1.2;
  stroke-dasharray: 4 3;
}

.sh-lit {
  fill: color-mix(in srgb, var(--hmz-accent) 18%, transparent);
  stroke: var(--hmz-accent);
  stroke-width: 1.8;
}

.sh-bad {
  fill: color-mix(in srgb, var(--hmz-lane-5) 16%, transparent);
  stroke: var(--hmz-lane-5);
  stroke-width: 1.6;
}

.sh-val-word {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.sh-val-word.no {
  fill: var(--hmz-warm);
}

.sh-tag-word {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-accent-2);
}

.sh-raw-chip {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.2;
}

.sh-raw-chip.bad {
  stroke: var(--hmz-lane-5);
}

.sh-raw-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  fill: var(--hmz-stage-dim);
  white-space: pre;
}

.sh-raw-word .hl {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.sh-raw-word .bad {
  fill: var(--hmz-lane-5);
  font-weight: 700;
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

.sh-stamp .sh-err {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
}

.sh-arc {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2;
  stroke-linecap: round;
}

.tip-warm {
  fill: var(--hmz-warm);
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
  fill: var(--vp-c-bg);
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
  stroke: var(--hmz-stage-dim);
  stroke-opacity: 0.5;
  stroke-width: 1.2;
}

.sh-choice.on {
  fill: var(--hmz-lane-1);
  stroke: var(--hmz-lane-1);
  stroke-opacity: 1;
}

.sh-choice-text {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.sh-choice-text.on {
  fill: var(--vp-c-bg);
}
</style>
