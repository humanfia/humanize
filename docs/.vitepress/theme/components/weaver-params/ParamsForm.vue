<script setup lang="ts">
// How params work, from "Params of its own": one pydantic class, `Params(FlowParams)`, is every
// way in. `-p passes=1,focus=tests,commit=true` is read field by field, each value as its
// field's type; the same fields are the form `/flow` puts up (its headings the `section`s in
// `json_schema_extra`, a `Literal` and a `bool` picked from, the rest written); a calling flow
// passes an instance. What does not validate is refused before any agent starts, in pydantic's
// words: `le=5`, a key the model has no field for (`extra="forbid"` on FlowParams), and the
// model validator's own message. Inside the flow `params.passes` is the number of review turns.
// Drawn from docs/weaver/flow-settings.md (the `polish` example, its form and its refusals),
// `FlowParams` in src/hmz/flows/defining.py and `params_of` in src/hmz/runtime/flowing/engine.py.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { createFx, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'One pydantic class declares the params',
  '-p is read field by field, as each type',
  'The same fields are the form at /flow',
  'A calling flow passes an instance',
  'Refused before any agent starts',
  'params.passes sets the review turns',
]

type Tok = [cls: '' | 'kw' | 'fn' | 'str' | 'num' | 'dim', text: string]
const CLASS: Tok[][] = [
  [['', '  passes: '], ['fn', 'int'], ['', ' = Field('], ['num', '1'], ['', ', ge='], ['num', '1'], ['', ', le='], ['num', '5'], ['', ')']],
  [['', '  focus: '], ['fn', 'Literal'], ['', '['], ['str', '"correctness"'], ['', ',']],
  [['str', '                 "style"'], ['', ', '], ['str', '"tests"'], ['', ']']],
  [['', '  commit: '], ['fn', 'bool'], ['', ' = '], ['kw', 'False']],
  [['', '  message: '], ['fn', 'str'], ['', ' = '], ['str', '""']],
  [['', '  @'], ['fn', 'model_validator'], ['', '(mode='], ['str', '"after"'], ['', ')']],
  [['dim', '    → '], ['str', '"a message needs commit=true"']],
]
const LINE = 16

/** The -p line, token by token: where it goes, and what it is read as. */
const CW = 6.6
const TOKENS = [
  { text: 'passes=1', col: 3, field: 0, chip: '1 · int' },
  { text: 'focus=tests', col: 12, field: 1, chip: '"tests"' },
  { text: 'commit=true', col: 24, field: 3, chip: 'True · bool' },
]

const FORM = [
  { kind: 'sec', text: 'passes  ·  what the agent does', field: -1 },
  { kind: 'row', text: 'passes', value: '1', field: 0 },
  { kind: 'row', text: 'focus', value: 'correctness ▾', field: 1 },
  { kind: 'sec', text: 'after  ·  what happens at the end', field: -1 },
  { kind: 'row', text: 'commit', value: '○ off ▾', field: 3 },
  { kind: 'row', text: 'message', value: '—', field: 4 },
] as const
const FORM_Y = [34, 50, 66, 86, 102, 118]

const REFUSALS = [
  { key: 'passes=9', why: 'Input should be less than or equal to 5', field: 0 },
  { key: 'colour=red', why: 'Extra inputs are not permitted', field: -1 },
  { key: 'message=hi', why: 'Value error, a message needs commit=true', field: 6 },
]

/** The turns two runs take: what -p set, and what the caller passed. */
const RUNS = [
  { label: 'passes=1 · focus=tests · commit=true', turns: ['task', 'pass 1', 'commit'] },
  { label: 'Params(passes=3) · the rest defaults', turns: ['task', 'pass 1', 'pass 2', 'pass 3'] },
]

interface Box {
  x: number
  y: number
  w: number
}
interface Layout {
  w: number
  h: number
  cls: Box
  flow: Box
  cli: Box
  form: Box
  call: Box
  refuse: Box
  open: { x: number; y: number; s: number }
  whole: { x: number; y: number; s: number }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  cls: { x: 12, y: 12, w: 272 },
  flow: { x: 12, y: 176, w: 272 },
  cli: { x: 298, y: 12, w: 330 },
  form: { x: 298, y: 94, w: 330 },
  call: { x: 298, y: 228, w: 330 },
  refuse: { x: 298, y: 266, w: 330 },
  open: { x: 150, y: 90, s: 1.4 },
  whole: { x: 320, y: 180, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 640,
  cls: { x: 14, y: 8, w: 332 },
  cli: { x: 14, y: 156, w: 332 },
  form: { x: 14, y: 234, w: 332 },
  call: { x: 14, y: 364, w: 332 },
  refuse: { x: 14, y: 398, w: 332 },
  flow: { x: 14, y: 478, w: 332 },
  open: { x: 180, y: 84, s: 1.16 },
  whole: { x: 180, y: 320, s: 1 },
}

const CLS_H = 34 + CLASS.length * LINE - 2
const CHIP_W = 54

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const lineY = (i: number) => L.value.cls.y + 38 + i * LINE
/** Where a field's line ends, on the right edge of the class card. */
const fieldAt = (i: number) => ({ x: L.value.cls.x + L.value.cls.w - 6, y: lineY(i) - 4 })
const tokX = (col: number, len: number) => L.value.cli.x + 12 + (col + len / 2) * CW
const chipW = (t: string) => Math.max(48, t.length * CW + 14)
const turnX = (k: number) => L.value.flow.x + 12 + k * (CHIP_W + 6)

const scene = useScene({
  still: 'rest',
  repeatDelay: 1.2,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
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
    const danger = () => palette.danger
    const his = at('.field-hi')
    const flash = (i: number, when: number, cls: 'ok' | 'bad') => {
      tl.set(his[i], { attr: { class: `field-hi ${cls}` } }, when)
      tl.fromTo(his[i], { opacity: 0.9 }, { opacity: 0, duration: 1.1, ease: 'power1.in' }, when)
    }

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.cls-line, .cli, .tok, .comma, .chip, .form, .form-row, .call, .refuse, .ref-row, .flow, .flow-code, .run-label, .turn, .count, .card-bad'), { opacity: 0 }, 0)
    tl.set(his, { opacity: 0 }, 0)

    // 0 · the class.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.cls'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.7 }, 0.1)
    tl.fromTo(at('.cls-line'), { x: -10 }, { opacity: 1, x: 0, duration: 0.5, stagger: 0.14 }, 0.4)
    cam.shot(l.whole, 2, 1.8)

    // 1 · the -p line, split at its commas, each value read as its field's type.
    const B1 = 3.4
    tl.addLabel('beat-1', B1)
    tl.to(at('.cli'), { opacity: 1, duration: 0.5 }, B1)
    tl.to(at('.tok, .comma'), { opacity: 1, duration: 0.3, stagger: 0.12 }, B1 + 0.3)
    TOKENS.forEach((t, i) => {
      const when = B1 + 1.1 + i * 0.75
      tl.fromTo(at('.tok-in')[i], { y: 0 }, { y: -3, duration: 0.25, yoyo: true, repeat: 1, ease: 'power1.inOut' }, when)
      cam.beam({ x: tokX(t.col, t.text.length), y: l.cli.y + 34 }, fieldAt(t.field), lane1, when, { duration: 0.7, bend: 0.2 })
      flash(t.field, when + 0.7, 'ok')
      cam.beam(fieldAt(t.field), { x: tokX(t.col, t.text.length), y: l.cli.y + 56 }, ok, when + 0.85, { duration: 0.6, bend: -0.2 })
      tl.to(at('.chip')[i], { opacity: 1, duration: 0.3 }, when + 1.4)
      tl.fromTo(at('.chip-in')[i], { scale: 0.6, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.45, ease: 'back.out(2.4)' }, when + 1.4)
    })

    // 2 · the form: a heading per section, a row per field.
    const B2 = B1 + 4.4
    tl.addLabel('beat-2', B2)
    tl.to(one('.form'), { opacity: 1, duration: 0.5 }, B2)
    FORM.forEach((r, i) => {
      const when = B2 + 0.4 + i * 0.32
      if (r.field >= 0) {
        cam.beam(fieldAt(r.field), { x: l.form.x + 14, y: l.form.y + FORM_Y[i] - 4 }, lane3, when - 0.3, { duration: 0.5, bend: -0.15 })
        flash(r.field, when - 0.3, 'ok')
      }
      tl.to(at('.form-row')[i], { opacity: 1, duration: 0.35 }, when + 0.2)
      tl.fromTo(at('.form-row-in')[i], { x: 10 }, { x: 0, duration: 0.5 }, when + 0.2)
    })

    // 3 · another flow passes an instance.
    const B3 = B2 + 3.2
    tl.addLabel('beat-3', B3)
    tl.to(one('.call'), { opacity: 1, duration: 0.5 }, B3)
    tl.fromTo(one('.call-in'), { x: 14 }, { x: 0, duration: 0.6 }, B3)
    cam.beam({ x: l.call.x + 30, y: l.call.y + 10 }, { x: l.cls.x + l.cls.w - 30, y: l.cls.y + 18 }, ok, B3 + 0.6, { duration: 0.8, bend: -0.2, burst: 16 })

    // 4 · three refusals, before any agent starts.
    const B4 = B3 + 2.2
    tl.addLabel('beat-4', B4)
    tl.to(one('.refuse'), { opacity: 1, duration: 0.5 }, B4)
    REFUSALS.forEach((r, i) => {
      const when = B4 + 0.5 + i * 1.1
      const from = { x: l.refuse.x + 40, y: l.refuse.y + 32 + i * 18 - 4 }
      if (r.field >= 0) {
        cam.beam(from, fieldAt(r.field), danger, when, { duration: 0.6, bend: 0.2 })
        flash(r.field, when + 0.6, 'bad')
      } else {
        // No field of that name: it hits the class itself.
        cam.beam(from, { x: l.cls.x + l.cls.w - 4, y: l.cls.y + 30 }, danger, when, { duration: 0.6, bend: 0.2 })
        tl.fromTo(one('.card-bad'), { opacity: 1 }, { opacity: 0, duration: 1, ease: 'power1.in' }, when + 0.6)
      }
      cam.flare({ x: from.x - 30, y: from.y }, danger, when + 0.7, 14, 70)
      tl.to(at('.ref-row')[i], { opacity: 1, duration: 0.4 }, when + 0.7)
    })

    // 5 · inside the flow: params.passes is how many review turns it takes.
    const B5 = B4 + 4.2
    tl.addLabel('beat-5', B5)
    tl.to(one('.flow'), { opacity: 1, duration: 0.5 }, B5)
    tl.to(at('.flow-code'), { opacity: 1, duration: 0.4, stagger: 0.15 }, B5 + 0.2)
    const turns = at('.turn')
    let n = 0
    RUNS.forEach((run, r) => {
      const t0 = B5 + 0.8 + r * 2.2
      tl.to(at('.run-label')[r], { opacity: 1, duration: 0.4 }, t0)
      cam.beam(r === 0 ? { x: tokX(0, 8), y: l.cli.y + 60 } : { x: l.call.x + 30, y: l.call.y + 20 }, { x: turnX(0), y: l.flow.y + 86 + r * 40 }, r === 0 ? lane1 : ok, t0, { duration: 0.8, bend: 0.15 })
      run.turns.forEach((_, k) => {
        const when = t0 + 0.6 + k * 0.32
        tl.to(turns[n], { opacity: 1, duration: 0.2 }, when)
        tl.fromTo(turns[n], { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 0.35, ease: 'cine.out' }, when)
        if (run.turns[k].startsWith('pass')) cam.flare({ x: turnX(k) + CHIP_W / 2, y: l.flow.y + 86 + r * 40 }, lane1, when + 0.2, 8, 50)
        n += 1
      })
    })
    tl.to(one('.count'), { opacity: 1, duration: 0.5 }, B5 + 5.4)

    tl.addLabel('rest', B5 + 6.4)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, B5 + 8.6)

    tl.fromTo(at('.hum'), { strokeDashoffset: 0 }, { strokeDashoffset: -120, duration: tl.duration(), ease: 'none' }, 0)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 16"
    label="How params work, on the polish example. One pydantic class, Params(FlowParams), declares passes, an int from 1 to 5; focus, one of correctness, style or tests; commit, a bool; message, a str; and a model validator that says a message needs commit=true. On the command line, -p passes=1,focus=tests,commit=true is split at its commas and each value read as its field's type: 1 as an int, tests as one of the choices, true as True. At the prompt, /flow puts up the same fields as a form, under the sections passes and after. A calling flow passes an instance, Params(passes=3). What does not validate is refused before any agent starts: passes=9 with Input should be less than or equal to 5, colour=red with Extra inputs are not permitted, and message=hi with Value error, a message needs commit=true. Inside the flow, params.passes is how many review turns it takes: the -p run takes the task, one pass and a commit; the caller's takes the task and three passes."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="world">
        <!-- the class -->
        <g class="cls">
          <rect class="card-box" :x="L.cls.x" :y="L.cls.y" :width="L.cls.w" :height="CLS_H" rx="10" />
          <rect class="card-bad" :x="L.cls.x" :y="L.cls.y" :width="L.cls.w" :height="CLS_H" rx="10" />
          <text class="card-head" :x="L.cls.x + 12" :y="L.cls.y + 19"><tspan class="kw">class </tspan><tspan class="fn">Params</tspan>(FlowParams):</text>
          <rect v-for="(line, i) in CLASS" :key="`h${i}`" class="field-hi ok" :x="L.cls.x + 6" :y="lineY(i) - 12" :width="L.cls.w - 12" height="16" rx="4" />
          <g v-for="(line, i) in CLASS" :key="i" class="cls-line">
            <text :x="L.cls.x + 12" :y="lineY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>

        <!-- 1 · the command line -->
        <g class="cli">
          <rect class="card-box" :x="L.cli.x" :y="L.cli.y" :width="L.cli.w" height="74" rx="10" />
          <text class="card-head" :x="L.cli.x + 12" :y="L.cli.y + 18">hmz exec -f polish …</text>
          <text class="mono flag" :x="L.cli.x + 12" :y="L.cli.y + 38">-p</text>
        </g>
        <g v-for="t in TOKENS" :key="t.text" class="tok">
          <g class="tok-in"><text class="mono tok-word" :x="tokX(t.col, t.text.length)" :y="L.cli.y + 38" text-anchor="middle">{{ t.text }}</text></g>
        </g>
        <text v-for="c in [11, 23]" :key="c" class="mono comma" :x="L.cli.x + 12 + c * CW" :y="L.cli.y + 38">,</text>
        <g v-for="t in TOKENS" :key="`c${t.text}`" class="chip">
          <g class="chip-in">
            <rect class="chip-box" :x="tokX(t.col, t.text.length) - chipW(t.chip) / 2" :y="L.cli.y + 47" :width="chipW(t.chip)" height="18" rx="9" />
            <text class="mono chip-word" :x="tokX(t.col, t.text.length)" :y="L.cli.y + 60" text-anchor="middle">{{ t.chip }}</text>
          </g>
        </g>

        <!-- 2 · the form at the prompt -->
        <g class="form">
          <rect class="card-box" :x="L.form.x" :y="L.form.y" :width="L.form.w" height="126" rx="10" />
          <text class="card-head" :x="L.form.x + 12" :y="L.form.y + 16">hmz › /flow › Set up polish</text>
        </g>
        <g v-for="(r, i) in FORM" :key="r.text" class="form-row">
          <g class="form-row-in">
            <text v-if="r.kind === 'sec'" class="form-sec" :x="L.form.x + 12" :y="L.form.y + FORM_Y[i]">{{ r.text }}</text>
            <template v-else>
              <text class="form-key" :x="L.form.x + 20" :y="L.form.y + FORM_Y[i]">{{ r.text }}</text>
              <text class="mono form-val" :x="L.form.x + L.form.w - 14" :y="L.form.y + FORM_Y[i]" text-anchor="end">{{ r.value }}</text>
            </template>
          </g>
        </g>

        <!-- 3 · a calling flow -->
        <g class="call">
          <g class="call-in">
            <rect class="card-box" :x="L.call.x" :y="L.call.y" :width="L.call.w" height="30" rx="8" />
            <text class="mono call-word" :x="L.call.x + 10" :y="L.call.y + 19"><tspan class="kw">await </tspan><tspan class="fn">polish</tspan>(task, …, params=<tspan class="fn">Params</tspan>(passes=3))</text>
          </g>
        </g>

        <!-- 4 · refusals -->
        <g class="refuse">
          <rect class="card-box refuse-box hum" :x="L.refuse.x" :y="L.refuse.y" :width="L.refuse.w" height="76" rx="10" />
          <text class="refuse-head" :x="L.refuse.x + 12" :y="L.refuse.y + 15">refused before any agent starts</text>
        </g>
        <g v-for="(r, i) in REFUSALS" :key="r.key" class="ref-row">
          <text class="mono ref-key" :x="L.refuse.x + 12" :y="L.refuse.y + 33 + i * 18">{{ r.key }}</text>
          <text class="ref-why" :x="L.refuse.x + 88" :y="L.refuse.y + 33 + i * 18">{{ r.why }}</text>
        </g>

        <!-- 5 · inside the flow -->
        <g class="flow">
          <rect class="card-box" :x="L.flow.x" :y="L.flow.y" :width="L.flow.w" height="158" rx="10" />
          <text class="card-head" :x="L.flow.x + 12" :y="L.flow.y + 18">inside polish</text>
        </g>
        <text class="mono flow-code" :x="L.flow.x + 12" :y="L.flow.y + 36"><tspan class="kw">for </tspan>_ <tspan class="kw">in </tspan><tspan class="fn">range</tspan>(params.passes):</text>
        <text class="mono flow-code" :x="L.flow.x + 12" :y="L.flow.y + 52">{{ '  ' }}<tspan class="kw">await </tspan><tspan class="fn">builder.run</tspan>(review, session=s)</text>
        <template v-for="(run, r) in RUNS" :key="run.label">
          <text class="run-label" :x="L.flow.x + 12" :y="L.flow.y + 86 + r * 40 - 14">{{ run.label }}</text>
          <g v-for="(t, k) in run.turns" :key="`${r}${k}`" class="turn" :class="{ pass: t.startsWith('pass'), commit: t === 'commit' }">
            <rect :x="turnX(k)" :y="L.flow.y + 86 + r * 40 - 9" :width="CHIP_W" height="18" rx="9" />
            <text class="mono" :x="turnX(k) + CHIP_W / 2" :y="L.flow.y + 86 + r * 40 + 4" text-anchor="middle">{{ t }}</text>
          </g>
        </template>
        <text class="count" :x="L.flow.x + 12" :y="L.flow.y + 150">turns = 1 + passes, and 1 more to commit</text>
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

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

.card-bad {
  fill: none;
  stroke: var(--vp-c-danger-1);
  stroke-width: 2;
}

.card-head {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.cls-line text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  white-space: pre;
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

.num {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.dim {
  fill: var(--hmz-stage-dim);
}

.field-hi.ok {
  fill: var(--hmz-accent);
  fill-opacity: 0.2;
}

.field-hi.bad {
  fill: var(--vp-c-danger-1);
  fill-opacity: 0.22;
}

.flag,
.comma {
  fill: var(--hmz-stage-dim);
}

.tok-word {
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.chip-box {
  fill: var(--hmz-accent);
}

.chip-word {
  font-weight: 700;
  fill: #fff;
}

.form-sec {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.form-key {
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.form-val {
  fill: var(--hmz-lane-3);
  font-weight: 600;
}

.call-word {
  fill: var(--hmz-stage-ink);
}

.refuse-box {
  stroke: var(--vp-c-danger-1);
  stroke-opacity: 0.6;
  stroke-dasharray: 6 3;
}

.refuse-head {
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-danger-1);
}

.ref-key {
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.ref-why {
  font-size: 11px;
  fill: var(--vp-c-danger-1);
}

.flow-code {
  fill: var(--hmz-stage-ink);
}

.run-label {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.turn rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.3;
}

.turn text {
  font-weight: 700;
  fill: var(--hmz-lane-1);
}

.turn.pass rect {
  fill: var(--hmz-lane-1);
}

.turn.pass text {
  fill: #fff;
}

.turn.commit rect {
  stroke: var(--hmz-accent);
}

.turn.commit text {
  fill: var(--hmz-accent);
}

.count {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}
</style>
