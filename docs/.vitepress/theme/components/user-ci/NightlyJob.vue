<script setup lang="ts">
// The nightly job, on a runner that starts empty every time. At 02:00 UTC the job checks the
// repository out, installs the agent's CLI and humanize, and signs the CLI in from a
// repository secret. `hmz exec -f ralph_loop … -p budget.duration=45m,budget.cost=20` fetches a
// price list before its first turn and works until a limit is spent, and the step exits 0. A
// script keeps the trace as an artifact, and a branch is pushed and a pull request opened. The
// exit status says what the job leaves: 0 a trace and a pull request, 1 a trace and nothing
// else, 2 refused in seconds before any agent ran. A simulation: the spend and the number of
// turns are invented.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { count, createFx, type, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'
import { rig, type Point, type Shot } from '../../motion/camera'
import { brace, braceD, curve, draw, pop, pulse, ring, rise, shake } from '../user-kit/moves'

const BEATS = [
  'At 02:00 a fresh runner starts empty, and the job checks the repository out',
  "It installs the agent's CLI and hmz, and signs the CLI in from a secret",
  'The run fetches a price list and works until its budget is spent',
  'A script keeps the trace; a branch is pushed and a pull request opened',
  'The exit status: 0 done or stopped, 1 failed, 2 refused in seconds',
]

/** A mono character's advance at 11px. */
const CW = 6.6

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Layout {
  w: number
  h: number
  cron: Point
  secret: Point
  runner: Box
  run: Box
  table: { x: number; y: number; w: number; row: number; two: boolean }
  shots: Record<'open' | 'install' | 'run' | 'after', Partial<Shot>>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  cron: { x: 16, y: 14 },
  secret: { x: 330, y: 14 },
  runner: { x: 16, y: 46, w: 298, h: 206 },
  run: { x: 330, y: 46, w: 294, h: 206 },
  table: { x: 16, y: 262, w: 608, row: 28, two: false },
  shots: {
    open: { x: 220, y: 140, s: 1.45 },
    install: { x: 280, y: 132, s: 1.25 },
    run: { x: 392, y: 140, s: 1.3 },
    after: { x: 320, y: 180, s: 1 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 640,
  cron: { x: 10, y: 12 },
  secret: { x: 10, y: 38 },
  runner: { x: 10, y: 68, w: 340, h: 190 },
  run: { x: 10, y: 270, w: 340, h: 206 },
  table: { x: 10, y: 486, w: 340, row: 46, two: true },
  shots: {
    open: { x: 180, y: 292, s: 1.05 },
    install: { x: 180, y: 300, s: 1.05 },
    run: { x: 180, y: 336, s: 1.05 },
    after: { x: 180, y: 320, s: 1 },
  },
}

/** What a runner has when the job starts: nothing. What each step puts there. */
const SLOTS = [
  { name: 'the repo', detail: 'TASK.md · ci/trace.py', by: 'checkout' },
  { name: 'claude', detail: '@anthropic-ai/claude-code', by: 'npm' },
  { name: 'hmz', detail: 'uv pip install humanize', by: 'uv' },
  { name: 'signed in', detail: 'CLAUDE_CODE_OAUTH_TOKEN', by: 'secret' },
  { name: 'price list', detail: 'fetched, at most 20 s', by: 'hmz' },
]

/** How the run can end, and what the job leaves for each. */
const ENDS = [
  { code: '0', means: 'done, or its budget stopped it', trace: 'trace kept', branch: 'nightly/<run id>', pr: 'PR opened', kept: true },
  { code: '1', means: 'failed: an error not handled', trace: 'trace kept', branch: '', pr: 'no branch, no PR', kept: false },
  { code: '2', means: 'refused, in seconds', trace: 'no agent ran', branch: '', pr: 'no branch, no PR', kept: false },
]
const TURNS = [0.08, 0.2, 0.33, 0.45, 0.57, 0.7, 0.82, 0.93]
const COST = 0.57

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const slotY = (i: number) => L.value.runner.y + 56 + i * 27
const slotDetail = computed(() => L.value.runner.x + (narrow.value ? 112 : 100))
const lineY = (i: number) => L.value.run.y + 40 + i * 16
const meterY = (i: number) => L.value.run.y + 114 + i * 20
const meterX = computed(() => L.value.run.x + 72)
const meterW = computed(() => L.value.run.w - 72 - 98)

/** The table of endings: where each row's status, meaning and outcomes sit. */
const endY = (i: number) => L.value.table.y + 26 + i * L.value.table.row
const cols = computed(() => {
  const t = L.value.table
  return t.two
    ? { means: t.x + 34, trace: t.x + 34, branch: t.x + 34 + 92, pr: t.x + 34 + 92 + 130, line2: 20 }
    : { means: t.x + 34, trace: t.x + 222, branch: t.x + 316, pr: t.x + 446, line2: 0 }
})
/** From the step's `exit 0` to the first row of the table: the status is what it branches on. */
const exitPath = computed(() => {
  const l = L.value
  if (narrow.value) return curve({ x: l.run.x + 14, y: l.run.y + l.run.h - 6 }, { x: l.table.x + 12, y: endY(0) - 15 }, 0.4)
  return curve({ x: l.run.x + 30, y: l.run.y + l.run.h - 4 }, { x: l.table.x + 21, y: endY(0) - 11 }, 0.06)
})
const pill = (text: string, mono = false) => text.length * (mono ? CW : 5.9) + 16

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), far: one('.far'), fx: () => fx, start: l.shots.open })
    const c = {
      job: () => palette.lane[0],
      secret: () => palette.warm,
      run: () => palette.accent,
      out: () => palette.accent2,
    }
    const slotMid = (i: number): Point => ({ x: slotDetail.value + 60, y: slotY(i) - 4 })

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(
      q('.cron, .runner-head, .runner-edge, .slot, .fill, .secret, .run, .cmd-line, .meter, .tick, .stop, .exit, .table-head, .end, .end-part, .brace-budget .brace-path, .brace-budget .brace-label, .exit-path'),
      { autoAlpha: 0 },
      0,
    )
    tl.set(q('.meter-fill'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(q('.slot-empty'), { autoAlpha: 1 }, 0)

    // 0 · 02:00, a runner with nothing on it, and the repository checked out onto it.
    tl.addLabel('beat-0', 0)
    pop(tl, one('.cron'), 0.1, { from: 0.7 })
    tl.fromTo(one('.hand'), { rotation: -720, svgOrigin: `${l.cron.x + 9} ${l.cron.y + 9}` }, { rotation: 0, svgOrigin: `${l.cron.x + 9} ${l.cron.y + 9}`, duration: 1.6, ease: 'cine' }, 0.2)
    draw(tl, one('.runner-edge'), 0.8, { duration: 1.2 })
    rise(tl, one('.runner-head'), 1.2, { y: 6 })
    rise(tl, q('.slot'), 1.6, { x: -8, y: 0, stagger: 0.12 })
    const fill = (i: number, at: number) => {
      tl.to(one(`.slot-${i} .slot-empty`), { autoAlpha: 0, duration: 0.25 }, at)
      tl.set(one(`.fill-${i}`), { autoAlpha: 1 }, at)
      tl.fromTo(one(`.fill-${i} .fill-bg`), { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 0.5, ease: 'cine.out' }, at)
      pop(tl, one(`.fill-${i} .fill-name`), at + 0.15, { from: 0.6 })
      type(tl, one(`.fill-${i} .fill-detail`), SLOTS[i].detail, at + 0.3, 60)
    }
    cam.beam({ x: l.cron.x + 9, y: l.cron.y + 9 }, slotMid(0), c.job, 2.6, { duration: 0.7, bend: 0.25, burst: 8 })
    fill(0, 3.2)

    // 1 · the CLI and humanize installed, and the CLI signed in from a repository secret.
    const T1 = 4.4
    tl.addLabel('beat-1', T1)
    cam.shot(l.shots.install, T1, 1.3)
    fill(1, T1 + 0.4)
    fill(2, T1 + 1.3)
    pop(tl, one('.secret'), T1 + 2.0, { from: 0.7 })
    ring(tl, one('.secret-ring'), T1 + 2.3)
    cam.beam({ x: l.secret.x + 10, y: l.secret.y + 11 }, slotMid(3), c.secret, T1 + 2.5, { duration: 0.8, bend: narrow.value ? -0.4 : 0.2, burst: 10 })
    fill(3, T1 + 3.2)
    tl.fromTo(one('.key'), { autoAlpha: 0, rotation: -40, svgOrigin: `${l.runner.x + l.runner.w - 22} ${slotY(3) - 4}` }, { autoAlpha: 1, rotation: 0, svgOrigin: `${l.runner.x + l.runner.w - 22} ${slotY(3) - 4}`, duration: 0.5, ease: 'back.out(2)' }, T1 + 3.6)

    // 2 · the line runs: a price list first, then turn after turn until a limit is spent.
    const T2 = T1 + 4.5
    tl.addLabel('beat-2', T2)
    cam.shot(l.shots.run, T2, 1.4)
    rise(tl, one('.run'), T2 + 0.2)
    const lines = q('.cmd-line')
    tl.set(lines, { autoAlpha: 1 }, T2 + 0.5)
    type(tl, lines[0], '$ hmz exec -f ralph_loop', T2 + 0.5, 50)
    type(tl, lines[1], '  -a agent=claude/claude-opus-5:high', T2 + 1.0, 70)
    type(tl, lines[2], '  -p budget.duration=45m,budget.cost=20', T2 + 1.55, 70)
    brace(tl, q, '.brace-budget', T2 + 2.1)
    cam.beam({ x: l.run.x + 40, y: lineY(2) + 6 }, slotMid(4), c.run, T2 + 2.2, { duration: 0.7, bend: narrow.value ? 0.3 : -0.25, burst: 8 })
    fill(4, T2 + 2.8)
    rise(tl, q('.meter'), T2 + 2.6, { y: 6, stagger: 0.1 })
    const RUN = 3.4
    const runAt = T2 + 3.3
    tl.to(one('.meter-0 .meter-fill'), { scaleX: 1, duration: RUN, ease: 'none' }, runAt)
    tl.to(one('.meter-1 .meter-fill'), { scaleX: COST, duration: RUN, ease: 'none' }, runAt)
    count(tl, one('.dur-val'), 0, 45, runAt, { duration: RUN, ease: 'none', format: (n) => `${Math.round(n)}m / 45m` })
    count(tl, one('.cost-val'), 0, 20 * COST, runAt, { duration: RUN, ease: 'none', format: (n) => `$${n.toFixed(2)} / $20` })
    TURNS.forEach((f, i) => pop(tl, one(`.tick-${i}`), runAt + f * RUN, { from: 0.3, duration: 0.3 }))
    ring(tl, one('.dur-ring'), runAt + RUN, { to: 1.3 })
    rise(tl, one('.stop'), runAt + RUN + 0.2, { y: 4 })
    pop(tl, one('.exit-0'), runAt + RUN + 0.6)

    // 3 · what the job keeps: the trace, from a script, and a pull request on a new branch.
    const T3 = runAt + RUN + 1.3
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.after, T3, 1.4)
    rise(tl, one('.table-head'), T3 + 0.3, { y: 6 })
    rise(tl, one('.end-0'), T3 + 0.5, { x: -8, y: 0 })
    cam.beam({ x: l.run.x + l.run.w / 2, y: l.run.y + l.run.h - 14 }, { x: cols.value.trace + 30, y: endY(0) + cols.value.line2 - 4 }, c.out, T3 + 0.9, { duration: 0.8, bend: 0.2, burst: 8 })
    pop(tl, one('.end-0 .part-trace'), T3 + 1.5)
    pop(tl, one('.end-0 .part-branch'), T3 + 2.0)
    pop(tl, one('.end-0 .part-pr'), T3 + 2.5)
    ring(tl, one('.pr-ring'), T3 + 2.6)

    // 4 · and what the status says: the same job ends three ways.
    const T4 = T3 + 3.6
    tl.addLabel('beat-4', T4)
    rise(tl, one('.end-1'), T4 + 0.2, { x: -8, y: 0 })
    pop(tl, q('.end-1 .end-part'), T4 + 0.5, { stagger: 0.25 })
    shake(tl, one('.end-1 .part-pr'), T4 + 1.1, 4)
    rise(tl, one('.end-2'), T4 + 1.5, { x: -8, y: 0 })
    pop(tl, q('.end-2 .end-part'), T4 + 1.8, { stagger: 0.25 })
    pulse(tl, one('.end-2 .status'), T4 + 2.4, 1.2)
    draw(tl, one('.exit-path'), T4 + 2.6, { duration: 0.9 })
    pulse(tl, one('.exit-0'), T4 + 2.6, 1.12)
    tl.addLabel('rest', T4 + 3.8)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 7.5)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 16"
    label="The nightly job on a runner that starts empty every time. At 02:00 UTC the job checks the repository out, with TASK.md and ci/trace.py; installs the agent's CLI, @anthropic-ai/claude-code, from npm and humanize with uv; and signs the CLI in from the repository secret CLAUDE_CODE_OAUTH_TOKEN. Then hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -p budget.duration=45m,budget.cost=20 runs: with a cost limit and no price list on the runner, it fetches one before its first turn, at most 20 seconds. It runs turn after turn until 45 minutes are spent, prints that it stopped because its budget's duration is spent, and exits 0. A script, ci/trace.py, keeps the trace as an artifact, and a branch nightly/<run id> is pushed and a pull request opened. The exit status says what the job leaves: 0, the flow returned or its budget stopped it, a trace and a pull request; 1, the run failed, a trace but no branch and no pull request; 2, refused in seconds before any agent ran, with no branch and no pull request."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <pattern id="nj-dots" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" class="grid-dot" />
        </pattern>
      </defs>
      <g class="far"><rect x="-400" y="-400" :width="L.w + 800" :height="L.h + 800" fill="url(#nj-dots)" /></g>

      <g class="world">
        <!-- The schedule. -->
        <g class="cron">
          <circle class="clock" :cx="L.cron.x + 9" :cy="L.cron.y + 9" r="8" />
          <line class="clock-hour" :x1="L.cron.x + 9" :y1="L.cron.y + 9" :x2="L.cron.x + 9" :y2="L.cron.y + 4.5" />
          <line class="hand" :x1="L.cron.x + 9" :y1="L.cron.y + 9" :x2="L.cron.x + 9" :y2="L.cron.y + 3" />
          <text class="cron-text" :x="L.cron.x + 24" :y="L.cron.y + 13">cron "0 2 * * *"</text>
          <text class="dim-text" :x="L.cron.x + 24 + 16 * CW + 8" :y="L.cron.y + 13">02:00 UTC, every night</text>
        </g>

        <!-- The repository's secret. -->
        <g class="secret">
          <rect class="secret-bg" :x="L.secret.x" :y="L.secret.y - 3" width="196" height="24" rx="12" />
          <g :transform="`translate(${L.secret.x + 14} ${L.secret.y + 9})`">
            <rect class="lock-body" x="-5" y="-2" width="10" height="8" rx="1.5" />
            <path class="lock-loop" d="M-3 -2 v-3 a3 3 0 0 1 6 0 v3" />
          </g>
          <text class="secret-text" :x="L.secret.x + 30" :y="L.secret.y + 13">CLAUDE_CODE_OAUTH_TOKEN</text>
          <g :transform="`translate(${L.secret.x + 98} ${L.secret.y + 9})`">
            <rect class="secret-ring" x="-98" y="-12" width="196" height="24" rx="12" />
          </g>
        </g>

        <!-- The runner, and what it has: nothing, until a step puts it there. -->
        <rect class="runner-bg" :x="L.runner.x" :y="L.runner.y" :width="L.runner.w" :height="L.runner.h" rx="10" />
        <rect class="runner-edge" :x="L.runner.x" :y="L.runner.y" :width="L.runner.w" :height="L.runner.h" rx="10" />
        <g class="runner-head">
          <text class="title" :x="L.runner.x + 12" :y="L.runner.y + 22">runner</text>
          <text class="mono-dim" :x="L.runner.x + 66" :y="L.runner.y + 22">ubuntu-latest</text>
          <text class="dim-text" :x="L.runner.x + L.runner.w - 12" :y="L.runner.y + 22" text-anchor="end">starts empty</text>
        </g>
        <g v-for="(s, i) in SLOTS" :key="s.name" class="slot" :class="`slot-${i}`">
          <rect class="slot-box" :x="L.runner.x + 10" :y="slotY(i) - 15" :width="L.runner.w - 20" height="22" rx="5" />
          <text class="slot-empty" :x="L.runner.x + 20" :y="slotY(i)">{{ s.name }}: not there</text>
        </g>
        <g v-for="(s, i) in SLOTS" :key="`f${s.name}`" class="fill" :class="`fill-${i}`">
          <rect class="fill-bg" :x="L.runner.x + 10" :y="slotY(i) - 15" :width="L.runner.w - 20" height="22" rx="5" />
          <g class="fill-name"><text class="fill-name-text" :x="L.runner.x + 20" :y="slotY(i)">{{ s.name }}</text></g>
          <text class="fill-detail" :x="slotDetail" :y="slotY(i)">{{ s.detail }}</text>
        </g>
        <g class="key">
          <circle class="key-ring" :cx="L.runner.x + L.runner.w - 26" :cy="slotY(3) - 4" r="3.2" />
          <path class="key-stem" :d="`M${L.runner.x + L.runner.w - 22.8} ${slotY(3) - 4} h8 m-3 0 v3 m-3 -3 v2`" />
        </g>

        <!-- The line, and its budget. -->
        <g class="run">
          <rect class="run-bg" :x="L.run.x" :y="L.run.y" :width="L.run.w" :height="L.run.h" rx="10" />
          <text class="title" :x="L.run.x + 12" :y="L.run.y + 22">Run the loop</text>
        </g>
        <text v-for="i in 3" :key="i" class="cmd-line" :class="{ prompt: i === 1 }" :x="L.run.x + 12" :y="lineY(i - 1)"></text>
        <g v-for="(m, i) in ['duration', 'cost']" :key="m" class="meter" :class="`meter-${i}`">
          <text class="meter-name" :x="L.run.x + 12" :y="meterY(i) + 4">{{ m }}</text>
          <rect class="meter-track" :x="meterX" :y="meterY(i) - 5" :width="meterW" height="10" rx="3" />
          <rect class="meter-fill" :class="`fill-${m}`" :x="meterX" :y="meterY(i) - 5" :width="meterW" height="10" rx="3" />
          <text class="meter-val" :class="i ? 'cost-val' : 'dur-val'" :x="L.run.x + L.run.w - 10" :y="meterY(i) + 4" text-anchor="end">{{ i ? '$0.00 / $20' : '0m / 45m' }}</text>
        </g>
        <g :transform="`translate(${meterX + meterW} ${meterY(0)})`">
          <circle class="dur-ring" r="9" />
        </g>
        <g class="meter">
          <text class="meter-name" :x="L.run.x + 12" :y="meterY(2) + 4">turns</text>
          <line class="meter-base" :x1="meterX" :x2="meterX + meterW" :y1="meterY(2)" :y2="meterY(2)" />
        </g>
        <g v-for="(f, i) in TURNS" :key="i" class="tick" :class="`tick-${i}`">
          <rect class="tick-mark" :x="meterX + f * meterW - 3" :y="meterY(2) - 6" width="6" height="12" rx="2" />
        </g>
        <g class="brace-budget">
          <path class="brace-path" :d="braceD({ x: L.run.x + 12 + 5 * CW, y: lineY(2) + 5 }, { x: L.run.x + 12 + 39 * CW, y: lineY(2) + 5 }, 9)" />
          <g class="brace-label"><text class="brace-word" :x="L.run.x + 12 + 22 * CW" :y="lineY(2) + 27" text-anchor="middle">45 minutes or $20, whichever comes first</text></g>
        </g>
        <g class="stop">
          <text class="stop-text" :x="L.run.x + 12" :y="L.run.y + L.run.h - 30">stopped: its budget's duration is spent</text>
        </g>
        <g class="exit exit-0">
          <rect class="status-bg s0" :x="L.run.x + 12" :y="L.run.y + L.run.h - 22" width="48" height="18" rx="9" />
          <text class="status-text" :x="L.run.x + 36" :y="L.run.y + L.run.h - 9" text-anchor="middle">exit 0</text>
          <text class="dim-text" :x="L.run.x + 68" :y="L.run.y + L.run.h - 9">the step stays green</text>
        </g>

        <!-- How it ended, and what the job leaves. -->
        <g class="table-head">
          <text class="dim-text" :x="L.table.x + L.table.w" :y="L.table.y + 4" text-anchor="end">exit status, and what the job leaves</text>
        </g>
        <g v-for="(e, i) in ENDS" :key="e.code" class="end" :class="`end-${i}`">
          <g class="status">
            <circle class="status-bg" :class="`s${i}`" :cx="L.table.x + 12" :cy="endY(i) - 4" r="10" />
            <text class="status-text" :x="L.table.x + 12" :y="endY(i)" text-anchor="middle">{{ e.code }}</text>
          </g>
          <text class="means" :x="cols.means" :y="endY(i)">{{ e.means }}</text>
          <g class="end-part part-trace">
            <rect class="part-bg" :class="{ none: i === 2 }" :x="cols.trace" :y="endY(i) + cols.line2 - 13" :width="pill(e.trace)" height="18" rx="9" />
            <text class="part-text" :class="{ none: i === 2 }" :x="cols.trace + 8" :y="endY(i) + cols.line2">{{ e.trace }}</text>
          </g>
          <g v-if="e.kept" class="end-part part-branch">
            <rect class="part-bg branch" :x="cols.branch" :y="endY(i) + cols.line2 - 13" :width="pill(e.branch, true)" height="18" rx="4" />
            <text class="part-text mono" :x="cols.branch + 8" :y="endY(i) + cols.line2">{{ e.branch }}</text>
          </g>
          <g class="end-part part-pr">
            <rect class="part-bg" :class="{ pr: e.kept, none: !e.kept }" :x="e.kept ? cols.pr : cols.branch" :y="endY(i) + cols.line2 - 13" :width="pill(e.pr)" height="18" rx="9" />
            <text class="part-text" :class="{ prt: e.kept, none: !e.kept }" :x="(e.kept ? cols.pr : cols.branch) + 8" :y="endY(i) + cols.line2">{{ e.pr }}</text>
          </g>
        </g>
        <g :transform="`translate(${cols.pr + pill(ENDS[0].pr) / 2} ${endY(0) + cols.line2 - 4})`">
          <rect class="pr-ring" :x="-pill(ENDS[0].pr) / 2" y="-9" :width="pill(ENDS[0].pr)" height="18" rx="9" />
        </g>
        <path class="exit-path" :d="exitPath" />
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.grid-dot {
  fill: var(--hmz-stage-line);
}

.title {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.dim-text,
.meter-name,
.slot-empty {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.slot-empty {
  font-style: italic;
}

.mono-dim,
.cron-text,
.secret-text,
.fill-detail,
.cmd-line,
.meter-val {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.cron-text,
.cmd-line {
  fill: var(--hmz-stage-ink);
}

.cmd-line {
  white-space: pre;
}

.cmd-line.prompt {
  font-weight: 700;
}

.clock {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.5;
}

.clock-hour,
.hand {
  stroke: var(--hmz-lane-1);
  stroke-width: 1.6;
  stroke-linecap: round;
}

.secret-bg {
  fill: color-mix(in srgb, var(--hmz-warm) 10%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
  stroke-width: 1.2;
}

.secret-text {
  fill: var(--hmz-warm);
  font-weight: 700;
}

.secret-ring {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2;
}

.lock-body {
  fill: var(--hmz-warm);
}

.lock-loop {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 1.5;
}

.runner-bg,
.run-bg {
  fill: var(--hmz-stage-card);
}

.runner-edge {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.4;
}

.run-bg {
  stroke: var(--hmz-accent);
  stroke-width: 1.4;
}

.slot-box {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1;
  stroke-dasharray: 3 3;
  opacity: 0.7;
}

.fill-bg {
  fill: color-mix(in srgb, var(--hmz-lane-1) 13%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-1);
  stroke-width: 1.2;
}

.fill-3 .fill-bg {
  fill: color-mix(in srgb, var(--hmz-warm) 14%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
}

.fill-4 .fill-bg {
  fill: color-mix(in srgb, var(--hmz-accent) 14%, var(--hmz-stage-card));
  stroke: var(--hmz-accent);
}

.fill-name-text {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.fill-detail {
  fill: var(--hmz-stage-ink);
}

.key-ring,
.key-stem {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 1.6;
  stroke-linecap: round;
}

.meter-track {
  fill: var(--hmz-stage-line);
}

.meter-fill.fill-duration {
  fill: var(--hmz-accent);
}

.meter-fill.fill-cost {
  fill: var(--hmz-warm);
}

.meter-val {
  fill: var(--hmz-stage-ink);
}

.meter-base {
  stroke: var(--hmz-stage-line);
  stroke-width: 2;
}

.tick-mark {
  fill: var(--hmz-lane-1);
}

.dur-ring {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.stop-text {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-accent);
}

.status-bg {
  fill: var(--hmz-accent);
}

.status-bg.s1 {
  fill: var(--hmz-lane-5);
}

.status-bg.s2 {
  fill: var(--hmz-lane-6);
}

.status-text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.means {
  font-size: 12px;
  fill: var(--hmz-stage-ink);
}

.part-bg {
  fill: color-mix(in srgb, var(--hmz-accent-2) 14%, var(--hmz-stage-card));
  stroke: var(--hmz-accent-2);
  stroke-width: 1.2;
}

.part-bg.branch {
  fill: color-mix(in srgb, var(--hmz-lane-1) 12%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-1);
}

.part-bg.pr {
  fill: var(--hmz-accent);
  stroke: var(--hmz-accent);
}

.part-bg.none {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-dasharray: 3 3;
}

.part-text {
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.part-text.mono {
  font-family: var(--vp-font-family-mono);
}

.part-text.prt {
  font-weight: 700;
  fill: #fff;
}

.part-text.none {
  fill: var(--hmz-stage-dim);
  font-style: italic;
}

.pr-ring {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.brace-path {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.4;
  stroke-linecap: round;
}

.exit-path {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.4;
  stroke-dasharray: 4 4;
}

.brace-word {
  font-size: 12px;
  font-style: italic;
  fill: var(--hmz-accent);
}
</style>
