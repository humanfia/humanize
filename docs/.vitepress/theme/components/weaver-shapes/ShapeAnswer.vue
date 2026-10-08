<script setup lang="ts">
// A turn asked for a shape, from the flow that asks. `run(..., output_schema=Review)` sends the
// pydantic model as a JSON Schema with the prompt: its fields, their types, which are required
// and each field's description (the model is `Review` on Answers in a shape, abridged). Which
// CLIs enforce a schema themselves is each backend's `shapes` in src/hmz/coganchor/agents/
// (claude, codex, agy, grok, mcode, qwen); the rest -- and an ACP CLI -- are given it in the
// prompt and the answer is read back out of what they say (`SessionBase` in base.py). Either way
// the answer is validated into an instance of the model, or the turn raises `OutputSchemaError`,
// a `HarnessError` (src/hmz/flows/errors.py). The flow then branches on `review.done`: the notes
// go back to the actor and a new round starts, or it returns True. The answers are drawn.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { createFx, type Fx } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'output_schema=Review: the model is the question',
  'Its fields reach the agent as a JSON Schema',
  'Some CLIs enforce it, the rest are prompted',
  'Validated: a Review, or a schema error',
  'The flow branches on review.done',
]

type Tok = [cls: '' | 'kw' | 'fn' | 'str' | 'key' | 'dim', text: string]

const KLASS: Tok[][] = [
  [['kw', 'class '], ['fn', 'Review'], ['', '(BaseModel):']],
  [['', '  done: '], ['kw', 'bool'], ['', ' = Field(']],
  [['', '    description='], ['str', '"True only…"'], ['', ')']],
  [['', '  notes: '], ['kw', 'str'], ['', ' = Field(']],
  [['', '    description='], ['str', '"What to say…"'], ['', ')']],
]
const SCHEMA: Tok[][] = [
  [['', '{'], ['key', '"type"'], ['', ': '], ['str', '"object"'], ['', ',']],
  [['', ' '], ['key', '"required"'], ['', ': ['], ['str', '"done"'], ['', ', '], ['str', '"notes"'], ['', '],']],
  [['', ' '], ['key', '"properties"'], ['', ': {']],
  [['', '  '], ['key', '"done"'], ['', ': {'], ['key', '"type"'], ['', ': '], ['str', '"boolean"'], ['', ',']],
  [['', '   '], ['key', '"description"'], ['', ': '], ['str', '"True only…"'], ['', '},']],
  [['', '  '], ['key', '"notes"'], ['', ': {'], ['key', '"type"'], ['', ': '], ['str', '"string"'], ['', ', …}}}']],
]
// Which line of the class becomes which line of the schema.
const PAIRS: [number, number][] = [
  [1, 3],
  [2, 4],
  [3, 5],
]

// The flow's lines, and which of them is the run, the branch and the actor's turn.
interface Code {
  lines: Tok[][]
  run: number
  done: number
  actor: number
  /** Where `output_schema=Review` is: line, column. */
  os: [number, number]
}
const CODE_WIDE: Code = {
  lines: [
    [['', 'review = '], ['kw', 'await '], ['fn', 'reviewer.run'], ['', '(REVIEW, session=reading, output_schema=Review)']],
    [['kw', 'if '], ['', 'review.done: '], ['kw', 'return '], ['', 'True']],
    [['kw', 'await '], ['fn', 'actor.run'], ['', '(review.notes, session=working)']],
  ],
  run: 0,
  done: 1,
  actor: 2,
  os: [0, 53],
}
const CODE_NARROW: Code = {
  lines: [
    [['', 'review = '], ['kw', 'await '], ['fn', 'reviewer.run'], ['', '(REVIEW,']],
    [['', '  session=reading, output_schema=Review)']],
    [['kw', 'if '], ['', 'review.done: '], ['kw', 'return '], ['', 'True']],
    [['kw', 'await '], ['fn', 'actor.run'], ['', '(review.notes,']],
    [['', '  session=working)']],
  ],
  run: 1,
  done: 2,
  actor: 3,
  os: [1, 19],
}

interface Box {
  x: number
  y: number
  w: number
}
interface Layout {
  w: number
  h: number
  code: Box
  codeLine: number
  klass: Box
  schema: Box
  /** The schema is drawn where the class was, and takes its place. */
  morph: boolean
  hold: Box
  ask: Box
  holdRows: string[][]
  askRows: string[][]
  holdSaid: string
  askSaid: string
  askHead: string
  /** Where the shape starts in what a prompted CLI said. */
  readCol: number
  check: { x: number; y: number }
  inst: Box
  err: Box
  /** Where the round's outcome is written. */
  out: { x: number; y: number; anchor: 'start' | 'end' }
  open: { x: number; y: number; s: number }
  whole: { x: number; y: number; s: number }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  code: { x: 14, y: 270, w: 612 },
  codeLine: 18,
  klass: { x: 14, y: 14, w: 240 },
  schema: { x: 14, y: 124, w: 240 },
  morph: false,
  hold: { x: 266, y: 14, w: 212 },
  ask: { x: 266, y: 126, w: 212 },
  holdRows: [
    ['claude', 'codex', 'agy'],
    ['grok', 'mcode', 'qwen'],
  ],
  askRows: [
    ['cursor-agent', 'dsh', 'kimi'],
    ['mimo', 'omp', 'opencode', 'pi'],
    ['an ACP CLI'],
  ],
  holdSaid: '{"done": false, "notes": …}',
  askSaid: 'said: …{"done": false, …}',
  askHead: 'prompted, then read back',
  readCol: 7,
  check: { x: 556, y: 62 },
  inst: { x: 490, y: 74, w: 136 },
  err: { x: 490, y: 172, w: 136 },
  out: { x: 618, y: 308, anchor: 'end' },
  open: { x: 260, y: 292, s: 1.45 },
  whole: { x: 320, y: 180, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 560,
  code: { x: 14, y: 12, w: 332 },
  codeLine: 17,
  klass: { x: 14, y: 124, w: 332 },
  schema: { x: 14, y: 124, w: 332 },
  morph: true,
  hold: { x: 14, y: 262, w: 162 },
  ask: { x: 184, y: 262, w: 162 },
  holdRows: [['claude', 'codex'], ['agy', 'grok'], ['mcode', 'qwen']],
  askRows: [['cursor-agent', 'omp'], ['dsh', 'kimi', 'mimo'], ['opencode', 'pi', 'ACP']],
  holdSaid: '{"done": false, …}',
  askSaid: '…{"done": false…}',
  askHead: 'prompted, read back',
  readCol: 1,
  check: { x: 180, y: 404 },
  inst: { x: 14, y: 414, w: 162 },
  err: { x: 184, y: 414, w: 162 },
  out: { x: 14, y: 504, anchor: 'start' },
  open: { x: 180, y: 70, s: 1.06 },
  whole: { x: 180, y: 280, s: 1 },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const C = computed(() => (narrow.value ? CODE_NARROW : CODE_WIDE))

const CW = 6.6
const codeY = (i: number) => L.value.code.y + 20 + i * L.value.codeLine
const codeH = computed(() => 20 + (C.value.lines.length - 1) * L.value.codeLine + 12)
const kY = (i: number) => L.value.klass.y + 22 + i * 16
const sY = (i: number) => L.value.schema.y + 38 + i * 16
const KH = 22 + (KLASS.length - 1) * 16 + 12
const SH = 38 + (SCHEMA.length - 1) * 16 + 12

const chipW = (n: string) => n.length * CW + 14
function row(box: Box, rows: string[][]) {
  return rows.flatMap((r, j) => {
    let x = box.x + 10
    return r.map((n) => {
      const c = { n, x, y: box.y + 26 + j * 22, w: chipW(n) }
      x += c.w + 6
      return c
    })
  })
}
const holdChips = computed(() => row(L.value.hold, L.value.holdRows))
const askChips = computed(() => row(L.value.ask, L.value.askRows))
const saidY = (box: Box) => box.y + 26 + (box === L.value.hold ? L.value.holdRows : L.value.askRows).length * 22 + 16
const roadH = (box: Box) => saidY(box) - box.y + 14

const scene = useScene({
  still: 'rest',
  repeatDelay: 1.2,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const gsap = motion()
    const l = L.value
    const c = C.value
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
    const bad = () => palette.danger

    const caret = one('.caret')
    const pc = (i: number, when: number, tone = 'var(--hmz-lane-1)') => {
      tl.to(caret, { attr: { y: codeY(i) - 12 }, fill: tone, duration: 0.45, ease: 'cine' }, when)
      tl.fromTo(at('.code-line')[i], { opacity: 0.55 }, { opacity: 1, duration: 0.3 }, when + 0.1)
    }
    const codeEnd = (i: number) => ({ x: Math.min(l.code.x + 14 + 70 * CW, l.code.x + l.code.w - 10), y: codeY(i) - 4 })
    const osAt = { x: l.code.x + 14 + (c.os[1] + 10) * CW, y: codeY(c.os[0]) - 14 }
    const kRight = (i: number) => ({ x: l.klass.x + l.klass.w - 10, y: kY(i) - 4 })
    const sRight = (i: number) => ({ x: l.schema.x + l.schema.w - 10, y: sY(i) - 4 })
    const holdOut = { x: l.hold.x + l.hold.w - 8, y: saidY(l.hold) - 4 }
    const askOut = { x: l.ask.x + l.ask.w - 8, y: saidY(l.ask) - 4 }
    const instIn = { x: l.inst.x + 8, y: l.inst.y + 12 }

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.code-line, .k-line, .s-line, .chip, .said, .road-head, .check-word, .inst, .err, .or, .outcome'), { opacity: 0 }, 0)
    tl.set(at('.klass, .schema, .road'), { opacity: 0 }, 0)
    tl.set(at('.k-hl, .s-hl, .os-hl'), { opacity: 0 }, 0)
    tl.set(at('.wire'), { drawSVG: '0%' }, 0)
    tl.set(caret, { opacity: 0, attr: { y: codeY(c.run) - 12 } }, 0)

    // 0 · the flow asks for a Review: the model it names is the question.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.code'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.6 }, 0.1)
    tl.to(at('.code-line'), { opacity: 0.55, duration: 0.5, stagger: 0.1 }, 0.3)
    tl.to(caret, { opacity: 1, duration: 0.3 }, 0.8)
    pc(c.run, 0.8)
    tl.to(one('.os-hl'), { opacity: 1, duration: 0.4 }, 1.3)
    cam.shot(l.whole, 1.6, 1.8)
    cam.beam(osAt, { x: l.klass.x + 40, y: l.klass.y + 10 }, lane1, 2, { duration: 0.9, bend: narrow.value ? -0.3 : 0.2, burst: 16 })
    tl.fromTo(one('.klass'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.6 }, 2.6)
    tl.to(at('.k-line'), { opacity: 1, duration: 0.4, stagger: 0.12 }, 2.8)

    // 1 · the class becomes a schema: fields, types, required, descriptions.
    const T1 = 4.6
    tl.addLabel('beat-1', T1)
    if (l.morph) {
      PAIRS.forEach(([k], j) => {
        tl.to(at('.k-hl')[k], { opacity: 1, duration: 0.3, yoyo: true, repeat: 1 }, T1 + j * 0.5)
      })
      tl.to(one('.klass'), { opacity: 0, duration: 0.5 }, T1 + 1.7)
      tl.to(one('.schema'), { opacity: 1, duration: 0.5 }, T1 + 1.9)
      tl.to(at('.s-line'), { opacity: 1, duration: 0.3, stagger: 0.12 }, T1 + 2)
      PAIRS.forEach(([, s], j) => {
        tl.to(at('.s-hl')[s], { opacity: 1, duration: 0.3, yoyo: true, repeat: 1 }, T1 + 2.9 + j * 0.4)
      })
      tl.to(at('.s-hl')[1], { opacity: 1, duration: 0.3, yoyo: true, repeat: 1 }, T1 + 4.1)
    } else {
      tl.fromTo(one('.schema'), { opacity: 0, y: -8 }, { opacity: 1, y: 0, duration: 0.6 }, T1)
      tl.to(at('.s-line'), { opacity: 1, duration: 0.3, stagger: 0.1 }, T1 + 0.2)
      tl.to(at('.s-line'), { opacity: 0.45, duration: 0.3 }, T1 + 0.9)
      PAIRS.forEach(([k, s], j) => {
        const w = T1 + 1.2 + j * 0.9
        tl.to(at('.k-hl')[k], { opacity: 1, duration: 0.25 }, w)
        cam.beam(kRight(k), sRight(s), lane1, w + 0.1, { duration: 0.6, bend: -0.35 })
        tl.to(at('.s-hl')[s], { opacity: 1, duration: 0.25 }, w + 0.6)
        tl.to(at('.s-line')[s], { opacity: 1, duration: 0.25 }, w + 0.6)
        tl.to(at('.k-hl')[k], { opacity: 0, duration: 0.3 }, w + 0.9)
        tl.to(at('.s-hl')[s], { opacity: 0, duration: 0.3 }, w + 1.1)
      })
      tl.to(at('.s-hl')[1], { opacity: 1, duration: 0.25, yoyo: true, repeat: 1 }, T1 + 3.9)
      tl.to(at('.s-line'), { opacity: 1, duration: 0.4 }, T1 + 4)
    }

    // 2 · two roads: the CLI holds the shape itself, or it is put in the prompt and read back.
    const T2 = T1 + 4.8
    tl.addLabel('beat-2', T2)
    const from = { x: l.schema.x + l.schema.w - 6, y: l.schema.y + 24 }
    tl.to(at('.road'), { opacity: 1, duration: 0.5, stagger: 0.25 }, T2)
    tl.to(at('.road-head'), { opacity: 1, duration: 0.4, stagger: 0.25 }, T2 + 0.2)
    cam.beam(from, { x: l.hold.x + 14, y: l.hold.y + 10 }, lane1, T2 + 0.3, { duration: 0.8, bend: -0.2, burst: 12 })
    cam.beam(from, { x: l.ask.x + 14, y: l.ask.y + 10 }, lane3, T2 + 0.5, { duration: 0.8, bend: 0.2, burst: 12 })
    tl.fromTo(at('.chip-hold'), { opacity: 0, y: 5 }, { opacity: 1, y: 0, duration: 0.35, stagger: 0.07 }, T2 + 1)
    tl.fromTo(at('.chip-ask'), { opacity: 0, y: 5 }, { opacity: 1, y: 0, duration: 0.35, stagger: 0.07 }, T2 + 1.3)
    tl.to(at('.said'), { opacity: 1, duration: 0.2 }, T2 + 2.3)
    const hs = one('.said-hold')
    const as = one('.said-ask')
    tl.set(hs, { text: '' }, T2 + 2.3)
    tl.to(hs, { text: { value: l.holdSaid }, duration: 0.9, ease: 'none' }, T2 + 2.35)
    tl.set(as, { text: '' }, T2 + 2.3)
    tl.to(as, { text: { value: l.askSaid }, duration: 0.9, ease: 'none' }, T2 + 2.8)
    tl.fromTo(one('.read-hl'), { opacity: 0 }, { opacity: 1, duration: 0.4 }, T2 + 3.8)

    // 3 · checked against the model: an instance, or OutputSchemaError.
    const T3 = T2 + 4.6
    tl.addLabel('beat-3', T3)
    tl.to(one('.check-word'), { opacity: 1, duration: 0.4 }, T3)
    cam.beam(holdOut, instIn, ok, T3 + 0.2, { duration: 0.8, bend: -0.2 })
    cam.beam(askOut, instIn, ok, T3 + 0.4, { duration: 0.8, bend: 0.2, burst: 20 })
    tl.fromTo(one('.inst'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5, ease: 'back.out(2)' }, T3 + 1.2)
    if (one('.or')) tl.to(one('.or'), { opacity: 1, duration: 0.4 }, T3 + 2)
    tl.fromTo(one('.err'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5 }, T3 + 2.2)
    cam.flare({ x: l.err.x + 20, y: l.err.y + 16 }, bad, T3 + 2.4, 14, 60)

    // 4 · the branch: round 1 is not done, so the notes go to the actor; round 2 is, so return.
    const T4 = T3 + 3.6
    tl.addLabel('beat-4', T4)
    tl.to(one('.done-hl'), { opacity: 1, duration: 0.3 }, T4)
    pc(c.done, T4 + 0.2, 'var(--hmz-warm)')
    cam.beam({ x: l.inst.x + 8, y: l.inst.y + 36 }, codeEnd(c.done), warm, T4 + 0.3, { duration: 0.8, bend: 0.2 })
    pc(c.actor, T4 + 1.2)
    cam.beam({ x: l.inst.x + 8, y: l.inst.y + 52 }, codeEnd(c.actor), warm, T4 + 1.3, { duration: 0.8, bend: 0.25, burst: 14 })
    tl.fromTo(one('.out-again'), { opacity: 0 }, { opacity: 1, duration: 0.4 }, T4 + 2)
    tl.to(one('.done-hl'), { opacity: 0, duration: 0.3 }, T4 + 2.6)
    // round 2: a new reviewer session, and this time the answer is done.
    tl.to(hs, { opacity: 0.3, duration: 0.2, yoyo: true, repeat: 1 }, T4 + 2.6)
    cam.beam(holdOut, instIn, ok, T4 + 2.8, { duration: 0.7, bend: -0.2 })
    tl.to(one('.inst-done'), { text: { value: '  done=True,' }, duration: 0.3, ease: 'none' }, T4 + 3.5)
    tl.to(one('.inst-notes'), { text: { value: '  notes="")' }, duration: 0.3, ease: 'none' }, T4 + 3.5)
    tl.to(one('.inst-done'), { fill: 'var(--hmz-accent)', duration: 0.3 }, T4 + 3.5)
    cam.flare({ x: l.inst.x + 50, y: l.inst.y + 36 }, ok, T4 + 3.6, 18, 70)
    pc(c.done, T4 + 4, 'var(--hmz-accent)')
    cam.beam({ x: l.inst.x + 8, y: l.inst.y + 36 }, codeEnd(c.done), ok, T4 + 4, { duration: 0.8, bend: 0.2 })
    tl.to(one('.out-again'), { opacity: 0.5, duration: 0.3 }, T4 + 4.6)
    tl.fromTo(one('.out-done'), { opacity: 0, x: -6 }, { opacity: 1, x: 0, duration: 0.5 }, T4 + 4.8)
    cam.flare({ x: l.out.x + (l.out.anchor === 'end' ? -30 : 30), y: l.out.y + 18 }, ok, T4 + 4.9, 26, 90)
    tl.to(caret, { opacity: 0.35, duration: 0.6 }, T4 + 5.4)

    tl.addLabel('rest', T4 + 6)
    cam.shot({ ...l.whole, s: l.whole.s * 1.03 }, T4 + 5.4, 3, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 8.6)

    gsap.set(caret, { opacity: 0 })
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 14"
    label="A turn asked for a shape, from the flow's side. The flow runs reviewer.run with output_schema=Review. The pydantic model is the question: its fields, done a bool and notes a str, which are required, and each field's description reach the agent as a JSON Schema sent with the prompt. Two roads: claude, codex, agy, grok, mcode and qwen enforce the schema themselves; cursor-agent, dsh, kimi, mimo, omp, opencode, pi and an ACP CLI are prompted with it, and the answer is read back out of what they say. Either way the answer is validated into a Review instance, here done=False with notes, or the turn raises OutputSchemaError, a HarnessError. The flow branches on review.done: not done, so the notes go back to the actor and a new round starts; the next review is done, and the flow returns True."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="world">
        <!-- the flow's lines -->
        <g class="code">
          <rect class="card-box" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="codeH" rx="10" />
          <rect class="os-hl" :x="L.code.x + 12 + C.os[1] * CW" :y="codeY(C.os[0]) - 12" :width="20 * CW + 4" height="16" rx="3" />
          <rect class="caret" :x="L.code.x + 4" :y="codeY(C.run) - 12" width="3" height="16" rx="1.5" />
          <g v-for="(line, i) in C.lines" :key="i" class="code-line">
            <text :x="L.code.x + 14" :y="codeY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>
        <g class="outcome out-again">
          <text :x="L.out.x" :y="L.out.y" :text-anchor="L.out.anchor">↺ done=False: notes to the actor</text>
        </g>
        <g class="outcome out-done">
          <text :x="L.out.x" :y="L.out.y + 18" :text-anchor="L.out.anchor">round 2: done=True → return True</text>
        </g>

        <!-- the model -->
        <g class="klass">
          <rect class="card-box" :x="L.klass.x" :y="L.klass.y" :width="L.klass.w" :height="KH" rx="10" />
          <rect v-for="(_, i) in KLASS" :key="'kh' + i" class="k-hl" :x="L.klass.x + 6" :y="kY(i) - 12" :width="L.klass.w - 12" height="16" rx="3" />
          <g v-for="(line, i) in KLASS" :key="i" class="k-line">
            <text :x="L.klass.x + 12" :y="kY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>

        <!-- what reaches the agent -->
        <g class="schema">
          <rect class="card-box schema-box" :x="L.schema.x" :y="L.schema.y" :width="L.schema.w" :height="SH" rx="10" />
          <text class="card-head" :x="L.schema.x + 12" :y="L.schema.y + 18">JSON Schema, with the prompt</text>
          <rect v-for="(_, i) in SCHEMA" :key="'sh' + i" class="s-hl" :x="L.schema.x + 6" :y="sY(i) - 12" :width="L.schema.w - 12" height="16" rx="3" />
          <g v-for="(line, i) in SCHEMA" :key="i" class="s-line">
            <text :x="L.schema.x + 12" :y="sY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>

        <!-- the two roads -->
        <g class="road road-hold">
          <rect class="road-box hold" :x="L.hold.x" :y="L.hold.y" :width="L.hold.w" :height="roadH(L.hold)" rx="10" />
          <text class="road-head hold" :x="L.hold.x + 10" :y="L.hold.y + 17">the CLI enforces it</text>
          <g v-for="ch in holdChips" :key="ch.n" class="chip chip-hold">
            <rect class="chip-box hold" :x="ch.x" :y="ch.y" :width="ch.w" height="17" rx="8.5" />
            <text class="chip-word" :x="ch.x + ch.w / 2" :y="ch.y + 12.5" text-anchor="middle">{{ ch.n }}</text>
          </g>
          <text class="said said-hold" :x="L.hold.x + 10" :y="saidY(L.hold)">{{ L.holdSaid }}</text>
        </g>
        <g class="road road-ask">
          <rect class="road-box ask" :x="L.ask.x" :y="L.ask.y" :width="L.ask.w" :height="roadH(L.ask)" rx="10" />
          <text class="road-head ask" :x="L.ask.x + 10" :y="L.ask.y + 17">{{ L.askHead }}</text>
          <g v-for="ch in askChips" :key="ch.n" class="chip chip-ask">
            <rect class="chip-box ask" :x="ch.x" :y="ch.y" :width="ch.w" height="17" rx="8.5" />
            <text class="chip-word" :x="ch.x + ch.w / 2" :y="ch.y + 12.5" text-anchor="middle">{{ ch.n }}</text>
          </g>
          <rect class="read-hl" :x="L.ask.x + 8 + L.readCol * CW" :y="saidY(L.ask) - 12" :width="(L.askSaid.length - L.readCol) * CW + 4" height="16" rx="3" />
          <text class="said said-ask" :x="L.ask.x + 10" :y="saidY(L.ask)">{{ L.askSaid }}</text>
        </g>

        <!-- checked against the model -->
        <text class="check-word" :x="L.check.x" :y="L.check.y" text-anchor="middle">validated against Review</text>
        <g class="inst">
          <rect class="res-box ok" :x="L.inst.x" :y="L.inst.y" :width="L.inst.w" height="64" rx="8" />
          <rect class="done-hl" :x="L.inst.x + 6" :y="L.inst.y + 25" :width="L.inst.w - 12" height="16" rx="3" />
          <text class="res-line head ok" :x="L.inst.x + 10" :y="L.inst.y + 18">Review(</text>
          <text class="res-line inst-done" :x="L.inst.x + 10" :y="L.inst.y + 37">  done=False,</text>
          <text class="res-line inst-notes" :x="L.inst.x + 10" :y="L.inst.y + 54">  notes="check…")</text>
        </g>
        <text v-if="!narrow" class="or" :x="L.inst.x + L.inst.w / 2" :y="L.err.y - 10" text-anchor="middle">or</text>
        <g class="err">
          <rect class="res-box bad" :x="L.err.x" :y="L.err.y" :width="L.err.w" height="64" rx="8" />
          <text class="res-line head bad" :x="L.err.x + 10" :y="L.err.y + 18">OutputSchemaError</text>
          <text class="res-line dim" :x="L.err.x + 10" :y="L.err.y + 37">a HarnessError</text>
          <text class="res-line" :x="L.err.x + 10" :y="L.err.y + 54">{"done":"maybe"}</text>
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
.k-line text,
.s-line text,
.card-head,
.chip-word,
.said,
.res-line,
.outcome text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  white-space: pre;
}

.card-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.schema-box {
  stroke: var(--hmz-lane-1);
  stroke-opacity: 0.6;
}

.card-head {
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.code-line text,
.k-line text,
.s-line text {
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

.key {
  fill: var(--hmz-lane-1);
}

.caret {
  fill: var(--hmz-lane-1);
}

.os-hl,
.k-hl,
.s-hl {
  fill: var(--hmz-lane-1);
  fill-opacity: 0.16;
}

.road-box {
  fill: var(--hmz-stage-card);
  stroke-width: 1.3;
}

.road-box.hold {
  stroke: var(--hmz-lane-1);
}

.road-box.ask {
  stroke: var(--hmz-lane-3);
  stroke-dasharray: 4 3;
}

.road-head {
  font-size: 12px;
  font-weight: 700;
}

.road-head.hold {
  fill: var(--hmz-lane-1);
}

.road-head.ask {
  fill: var(--hmz-lane-3);
}

.chip-box {
  fill: none;
  stroke-width: 1.1;
}

.chip-box.hold {
  stroke: var(--hmz-lane-1);
}

.chip-box.ask {
  stroke: var(--hmz-lane-3);
}

.chip-word {
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.said {
  fill: var(--hmz-stage-ink);
}

.read-hl {
  fill: var(--hmz-lane-3);
  fill-opacity: 0.18;
}

.check-word {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.res-box {
  fill: var(--hmz-stage-card);
  stroke-width: 1.4;
}

.res-box.ok {
  stroke: var(--hmz-accent);
}

.res-box.bad {
  stroke: var(--vp-c-danger-1);
  stroke-dasharray: 4 3;
}

.res-line {
  fill: var(--hmz-stage-ink);
}

.res-line.head {
  font-weight: 700;
}

.res-line.ok {
  fill: var(--hmz-accent);
}

.res-line.bad {
  fill: var(--vp-c-danger-1);
}

.res-line.dim {
  fill: var(--hmz-stage-dim);
}

.inst-done {
  fill: var(--hmz-warm);
  font-weight: 700;
}

.done-hl {
  fill: var(--hmz-warm);
  fill-opacity: 0.16;
}

.or {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.outcome text {
  font-weight: 700;
}

.out-again text {
  fill: var(--hmz-warm);
}

.out-done text {
  fill: var(--hmz-accent);
}
</style>
