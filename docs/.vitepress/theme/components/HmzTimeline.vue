<script setup lang="ts">
// A trace, put together. A CLI logs each session under an id and never says whose it was; the
// run's own record (`src/hmz/runtime/tracing/session.py`, `collector.py`) says which agent of
// the run each session belonged to and which CLI took its turns, so the trace holds only that
// run's sessions, each under its agent's name. `chrome.py` writes them as Perfetto reads them:
// a process per agent, a track per row of its sessions (`main`, or `subagent` for agents its
// turns started), a slice per thing it did, all on one clock. In a profiled directory
// (`profile.py`) the programs those turns ran are drawn underneath, each under the tool call
// that started it, thread by thread. The run itself is invented; the shape of the trace is not.
import { computed, ref, useId } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'
import { rig, type Point, type Shot } from '../motion/camera'

const BEATS = [
  'A CLI logs sessions under bare ids',
  'The run knows whose each one was',
  'Every agent, one clock, one timeline',
  'Profiled: the programs under each tool call',
  'Opened in Perfetto, never uploaded',
]

type Kind = 'tool' | 'think' | 'say' | 'prog'

interface Slice {
  t0: number
  t1: number
  label: string
  kind: Kind
}

interface Row {
  head: string
  sub: string
  /** Shorter words for a phone. */
  narrow?: [string, string]
  lane: number
  program?: boolean
  slices: Slice[]
}

const SPAN = 34

const ROWS: Row[] = [
  {
    head: 'actor',
    sub: 'claude · main',
    lane: 1,
    slices: [
      { t0: 0, t1: 1.6, label: '', kind: 'think' },
      { t0: 1.6, t1: 2.4, label: '', kind: 'tool' },
      { t0: 2.4, t1: 3.1, label: '', kind: 'tool' },
      { t0: 3.1, t1: 5.2, label: '', kind: 'think' },
      { t0: 5.2, t1: 6.0, label: '', kind: 'tool' },
      { t0: 6.0, t1: 14.8, label: 'Bash', kind: 'tool' },
      { t0: 14.8, t1: 16.0, label: '', kind: 'think' },
      { t0: 16.0, t1: 17.2, label: '', kind: 'tool' },
      { t0: 17.2, t1: 19.0, label: '', kind: 'say' },
      { t0: 22.0, t1: 23.4, label: '', kind: 'tool' },
      { t0: 23.4, t1: 27.0, label: 'Bash', kind: 'tool' },
      { t0: 27.0, t1: 28.2, label: '', kind: 'say' },
    ],
  },
  {
    head: '',
    sub: 'subagent · explore',
    narrow: ['subagent', 'explore'],
    lane: 1,
    slices: [
      { t0: 16.2, t1: 17.4, label: '', kind: 'tool' },
      { t0: 17.4, t1: 19.8, label: '', kind: 'tool' },
      { t0: 19.8, t1: 21.6, label: '', kind: 'say' },
    ],
  },
  {
    head: 'reviewer',
    sub: 'codex · main',
    lane: 2,
    slices: [
      { t0: 19.0, t1: 20.4, label: '', kind: 'think' },
      { t0: 20.4, t1: 21.8, label: '', kind: 'tool' },
      { t0: 28.4, t1: 31.0, label: '', kind: 'think' },
      { t0: 31.0, t1: 33.2, label: '', kind: 'say' },
    ],
  },
  { head: 'pytest', sub: 'main', lane: 4, program: true, slices: [{ t0: 6.05, t1: 14.72, label: 'pytest -q', kind: 'prog' }] },
  { head: '', sub: 'thread 48221', lane: 4, program: true, slices: [{ t0: 6.6, t1: 11.9, label: 'python', kind: 'prog' }] },
  { head: '', sub: 'thread 48222', lane: 4, program: true, slices: [{ t0: 6.6, t1: 13.9, label: 'python', kind: 'prog' }] },
  { head: 'rg', sub: 'main', lane: 3, program: true, slices: [{ t0: 16.5, t1: 16.9, label: '', kind: 'prog' }] },
  { head: 'ruff', sub: 'main', lane: 5, program: true, slices: [{ t0: 23.44, t1: 26.9, label: 'ruff', kind: 'prog' }] },
]

/** Which tool call started which program: row and slice of the call, row of the program. */
const STARTED = [
  { row: 0, slice: 5, prog: 3 },
  { row: 1, slice: 0, prog: 6 },
  { row: 0, slice: 10, prog: 7 },
]

/** Session logs, as a CLI leaves them: an id and nothing else. Two are this run's. */
const LOGS = [
  { id: '7f3a9c', cli: 'claude', ours: 0 },
  { id: '2b61e0', cli: 'codex', ours: -1 },
  { id: 'a2d7b1', cli: 'claude', ours: -1 },
  { id: 'c19e04', cli: 'codex', ours: 2 },
  { id: '5e8f22', cli: 'claude', ours: -1 },
  { id: '91bc0d', cli: 'codex', ours: -1 },
]

interface Layout {
  w: number
  h: number
  x0: number
  x1: number
  rowY: number[]
  rowH: number
  axis: number
  divider: number
  logs: { x: number; y: number; s: number }[]
  card: { w: number; h: number }
  ledger: { x: number; y: number; w: number }
  chrome: { x: number; y: number; w: number; h: number }
  lock: Point
  shots: Record<'open' | 'sweepFrom' | 'sweepTo' | 'push' | 'wide' | 'end', Partial<Shot>>
  tick: number
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  x0: 168,
  x1: 616,
  rowY: [64, 94, 124, 178, 206, 234, 262, 290],
  rowH: 20,
  axis: 54,
  divider: 162,
  logs: [
    { x: 110, y: 104, s: 1.05 },
    { x: 300, y: 76, s: 0.9 },
    { x: 500, y: 110, s: 0.95 },
    { x: 150, y: 262, s: 1 },
    { x: 360, y: 290, s: 0.9 },
    { x: 540, y: 250, s: 0.9 },
  ],
  card: { w: 96, h: 42 },
  ledger: { x: 320, y: 184, w: 240 },
  chrome: { x: 8, y: 8, w: 624, h: 320 },
  lock: { x: 330, y: 22 },
  shots: {
    open: { x: 330, y: 185, s: 1.18 },
    sweepFrom: { x: 268, y: 104, s: 1.2 },
    sweepTo: { x: 400, y: 104, s: 1.2 },
    push: { x: 300, y: 170, s: 1.35 },
    wide: { x: 400, y: 200, s: 1.1 },
    end: { x: 320, y: 172, s: 0.96 },
  },
  tick: 5,
}

const NARROW: Layout = {
  w: 360,
  h: 400,
  x0: 96,
  x1: 348,
  rowY: [74, 108, 142, 196, 230, 264, 298, 332],
  rowH: 24,
  axis: 60,
  divider: 180,
  logs: [
    { x: 72, y: 96, s: 1 },
    { x: 190, y: 74, s: 0.95 },
    { x: 296, y: 118, s: 0.95 },
    { x: 84, y: 296, s: 1.05 },
    { x: 200, y: 330, s: 0.95 },
    { x: 296, y: 286, s: 0.95 },
  ],
  card: { w: 90, h: 40 },
  ledger: { x: 180, y: 204, w: 236 },
  chrome: { x: 6, y: 8, w: 348, h: 360 },
  lock: { x: 290, y: 382 },
  shots: {
    open: { x: 180, y: 200, s: 1.12 },
    sweepFrom: { x: 170, y: 118, s: 1.1 },
    sweepTo: { x: 200, y: 118, s: 1.1 },
    push: { x: 170, y: 190, s: 1.3 },
    wide: { x: 220, y: 240, s: 1.1 },
    end: { x: 180, y: 200, s: 1 },
  },
  tick: 10,
}

const id = useId()
const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const X = (t: number) => L.value.x0 + (t / SPAN) * (L.value.x1 - L.value.x0)
const ticks = computed(() => Array.from({ length: Math.floor(SPAN / L.value.tick) + 1 }, (_, i) => i * L.value.tick))
const head = (r: Row) => (narrow.value && r.narrow ? r.narrow[0] : r.head)
const word = (label: string) => (narrow.value ? label.split(' ')[0] : label)
const sub = (r: Row) => (narrow.value && r.narrow ? r.narrow[1] : r.sub)

// How long the playhead takes to cross the whole run.
const SWEEP = 5.2

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const at = (sel: string) => q(sel)
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), far: one('.far'), fx: () => fx, start: l.shots.open })
    const lane = (n: number) => () => palette.lane[n - 1]
    const rowEls = at('.row')
    const slicesOf = (r: number) => q(`.row-${r} .slice`)
    const mid = (r: number) => l.rowY[r] + l.rowH / 2

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.log'), { autoAlpha: 0 }, 0)
    tl.set(at('.log-name'), { autoAlpha: 0 }, 0)
    tl.set(at('.log-id'), { autoAlpha: 1 }, 0)
    tl.set(at('.log-move'), { x: 0, y: 0, scale: 1, transformOrigin: '50% 50%' }, 0)
    tl.set(at('.ledger, .ledger-line, .row, .axis, .playhead, .divider, .chrome, .lock, .link, .slice-word, .log-halo'), { autoAlpha: 0 }, 0)
    tl.set(at('.slice'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(at('.link-line'), { drawSVG: '0%' }, 0)

    // 0 · sessions, as the CLIs left them: ids, some this run's, most not.
    tl.addLabel('beat-0', 0)
    cam.shot({ s: 1.02 }, 0, 3.4, 'none')
    at('.log').forEach((el, i) => {
      tl.fromTo(el, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.7 }, 0.15 + i * 0.18)
      tl.fromTo(q('.log-float')[i], { y: -4 }, { y: 4, duration: 1.6 + (i % 3) * 0.3, ease: 'sine.inOut', repeat: 3, yoyo: true }, 0)
    })

    // 1 · the run's record says whose each of its sessions was.
    const T1 = 3.2
    tl.addLabel('beat-1', T1)
    tl.fromTo(one('.ledger'), { autoAlpha: 0, scale: 0.85, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.7, ease: 'back.out(1.6)' }, T1)
    tl.fromTo(at('.ledger-line'), { autoAlpha: 0, x: -8 }, { autoAlpha: 1, x: 0, duration: 0.4, stagger: 0.3 }, T1 + 0.5)
    const lines = [0, 1].map((i) => ({ x: l.ledger.x - l.ledger.w / 2 + 14, y: l.ledger.y + 2 + i * 20 }))
    LOGS.forEach((log, i) => {
      if (log.ours < 0) {
        tl.to(at('.log')[i], { autoAlpha: 0, duration: 0.6 }, T1 + 1.5 + i * 0.05)
        tl.to(q('.log-move')[i], { scale: 0.6, duration: 0.8, ease: 'cine.in' }, T1 + 1.4 + i * 0.05)
        return
      }
      const k = log.ours === 0 ? 0 : 1
      cam.beam(lines[k], l.logs[i], lane(k ? 2 : 1), T1 + 1.1 + k * 0.3, { duration: 0.6, bend: 0.2, burst: 12 })
      tl.to(q('.log-halo')[i], { autoAlpha: 1, duration: 0.4 }, T1 + 1.6 + k * 0.3)
    })
    tl.to(one('.ledger'), { autoAlpha: 0, scale: 0.9, duration: 0.5 }, T1 + 2.6)
    // The two fly to where their agents' names will stand, and turn into those names.
    const T1b = T1 + 2.5
    cam.shot(l.shots.sweepFrom, T1b, 1.8)
    LOGS.forEach((log, i) => {
      if (log.ours < 0) return
      const r = log.ours
      const to = { x: (narrow.value ? 12 : 20) + l.card.w / 2 - 4, y: mid(r) }
      tl.to(q('.log-move')[i], { x: (to.x - l.logs[i].x) / l.logs[i].s, y: (to.y - l.logs[i].y) / l.logs[i].s, scale: 1 / l.logs[i].s, duration: 1.4, ease: 'cine' }, T1b + (r ? 0.15 : 0))
      tl.to(q('.log-id')[i], { autoAlpha: 0, duration: 0.3 }, T1b + 1.0)
      tl.to(at('.log')[i], { autoAlpha: 0, duration: 0.4 }, T1b + 1.35)
      tl.to(rowEls[r], { autoAlpha: 1, duration: 0.4 }, T1b + 1.2)
    })

    // 2 · one clock: the playhead crosses the run and every slice grows as it happened.
    const T2 = T1b + 1.9
    tl.addLabel('beat-2', T2)
    tl.to(one('.axis'), { autoAlpha: 1, duration: 0.5 }, T2 - 0.3)
    tl.to(one('.playhead'), { autoAlpha: 1, duration: 0.2 }, T2)
    tl.fromTo(one('.playhead-in'), { x: 0 }, { x: l.x1 - l.x0, duration: SWEEP, ease: 'none' }, T2)
    cam.shot(l.shots.sweepTo, T2, SWEEP, 'sine.inOut')
    const when = (t: number) => T2 + (t / SPAN) * SWEEP
    ;[0, 1, 2].forEach((r) => {
      ROWS[r].slices.forEach((s, j) => {
        tl.to(slicesOf(r)[j], { scaleX: 1, duration: ((s.t1 - s.t0) / SPAN) * SWEEP, ease: 'none' }, when(s.t0))
      })
    })
    // The sub-agent's row opens when the actor's Task starts it.
    tl.fromTo(rowEls[1], { autoAlpha: 0, y: -10 }, { autoAlpha: 1, y: 0, duration: 0.4 }, when(16.0))
    cam.flare({ x: X(16.0), y: mid(1) }, lane(1), when(16.0), 12, 60)
    ;[0, 1, 2].forEach((r) => {
      q(`.row-${r} .slice-word`).forEach((el) => {
        const s = ROWS[r].slices[Number((el as SVGElement).dataset.slice)]
        tl.to(el, { autoAlpha: 1, duration: 0.3 }, when(s.t1) - 0.2)
      })
    })
    tl.to(one('.playhead'), { autoAlpha: 0, duration: 0.3 }, T2 + SWEEP + 0.1)

    // 3 · profiled: under each tool call, the program it ran, thread by thread.
    const T3 = T2 + SWEEP + 0.4
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.push, T3, 1.4)
    tl.to(one('.divider'), { autoAlpha: 1, duration: 0.5 }, T3 + 0.4)
    STARTED.forEach((link, k) => {
      const t = T3 + (k === 0 ? 0.9 : 2.9 + (k - 1) * 0.7)
      const call = ROWS[link.row].slices[link.slice]
      const prog = ROWS[link.prog]
      tl.to(q('.link')[k], { autoAlpha: 1, duration: 0.1 }, t)
      tl.to(q('.link-line')[k], { drawSVG: '100%', duration: 0.5, ease: 'power2.in' }, t)
      cam.beam({ x: X(call.t0) + 3, y: l.rowY[link.row] + l.rowH }, { x: X(prog.slices[0].t0) + 3, y: l.rowY[link.prog] }, lane(prog.lane), t, { duration: 0.5, bend: 0, burst: 14, ease: 'power2.in' })
      tl.to(rowEls[link.prog], { autoAlpha: 1, duration: 0.3 }, t + 0.35)
      tl.to(slicesOf(link.prog)[0], { scaleX: 1, duration: 0.7, ease: 'cine.out' }, t + 0.45)
      tl.to(q(`.row-${link.prog} .slice-word`), { autoAlpha: 1, duration: 0.3 }, t + 0.9)
      if (k === 0) {
        // pytest's threads, one under the other.
        ;[4, 5].forEach((r, n) => {
          tl.fromTo(rowEls[r], { autoAlpha: 0, y: -12 }, { autoAlpha: 1, y: 0, duration: 0.4 }, t + 0.9 + n * 0.3)
          tl.to(slicesOf(r)[0], { scaleX: 1, duration: 0.7, ease: 'cine.out' }, t + 1.0 + n * 0.3)
          tl.to(q(`.row-${r} .slice-word`), { autoAlpha: 1, duration: 0.3 }, t + 1.5 + n * 0.3)
        })
        cam.shot(l.shots.wide, t + 1.7, 1.4)
      }
    })

    // 4 · the whole thing, as one file on this machine, open in Perfetto.
    const T4 = T3 + 5.2
    tl.addLabel('beat-4', T4)
    cam.shot(l.shots.end, T4, 1.6)
    tl.fromTo(one('.chrome'), { autoAlpha: 0, scale: 1.04, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.9 }, T4 + 0.5)
    tl.fromTo(one('.lock'), { autoAlpha: 0, scale: 1.4, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.5, ease: 'back.out(2)' }, T4 + 1.3)
    cam.flare(l.lock, () => palette.accent, T4 + 1.35, 22, 90)
    tl.addLabel('rest', T4 + 2.2)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 4.6)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 10"
    label="Building a trace. The CLIs leave session logs under bare ids, from many runs. The run's own record says which two are its own: one was the actor's, on claude, one the reviewer's, on codex. They become named rows on one timeline, and a playhead crosses the run as every slice grows: the actor's tool calls, a sub-agent row opened by its Task, the reviewer's turns. In a profiled directory the programs appear under the tool calls that started them: pytest and its two threads under a long Bash, rg under the sub-agent's Glob, ruff under a second Bash. The whole trace is one file on this machine, opened in Perfetto."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <pattern :id="`${id}-dots`" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" class="grid-dot" />
        </pattern>
        <radialGradient v-for="n in [1, 2]" :id="`${id}-halo-${n}`" :key="n">
          <stop offset="0" :stop-color="`var(--hmz-lane-${n})`" stop-opacity="0.55" />
          <stop offset="1" :stop-color="`var(--hmz-lane-${n})`" stop-opacity="0" />
        </radialGradient>
        <linearGradient :id="`${id}-head`" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0" />
          <stop offset="0.5" stop-color="var(--hmz-accent)" stop-opacity="0.9" />
          <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
        </linearGradient>
      </defs>

      <g class="far"><rect x="-400" y="-400" :width="L.w + 800" :height="L.h + 800" :fill="`url(#${id}-dots)`" /></g>

      <g class="world">
        <!-- The Perfetto window, which only shows at the end. -->
        <g class="chrome">
          <rect class="chrome-frame" :x="L.chrome.x" :y="L.chrome.y" :width="L.chrome.w" :height="L.chrome.h" rx="12" />
          <line class="chrome-bar" :x1="L.chrome.x" :x2="L.chrome.x + L.chrome.w" :y1="L.chrome.y + 28" :y2="L.chrome.y + 28" />
          <circle v-for="i in 3" :key="i" class="chrome-dot" :cx="L.chrome.x + 6 + i * 11" :cy="L.chrome.y + 14" r="3.2" />
          <text class="chrome-title" :x="L.chrome.x + 50" :y="L.chrome.y + 18">Perfetto</text>
          <text class="chrome-file" :x="L.chrome.x + (narrow ? 110 : 116)" :y="L.chrome.y + 18">export.trace.json</text>
        </g>
        <g :transform="`translate(${L.lock.x} ${L.lock.y})`">
          <g class="lock">
            <rect x="-62" y="-10" width="124" height="20" rx="10" />
            <text y="4" text-anchor="middle">on this machine</text>
          </g>
        </g>

        <!-- The clock. -->
        <g class="axis">
          <line class="axis-line" :x1="L.x0" :x2="L.x1" :y1="L.axis" :y2="L.axis" />
          <g v-for="t in ticks" :key="t">
            <line class="axis-tick" :x1="X(t)" :x2="X(t)" :y1="L.axis - 4" :y2="L.rowY[7] + L.rowH" />
            <text class="axis-word" :x="X(t) + 3" :y="L.axis - 6">{{ t }}s</text>
          </g>
        </g>
        <g class="divider">
          <text class="divider-word" :x="narrow ? 12 : 20" :y="L.divider + 4">programs</text>
          <line class="divider-line" :x1="narrow ? 86 : 90" :x2="L.x1" :y1="L.divider" :y2="L.divider" />
        </g>

        <!-- Tool call → the program it started. -->
        <g v-for="(link, k) in STARTED" :key="`l${k}`" class="link">
          <path
            class="link-line"
            :class="`lane-${ROWS[link.prog].lane}`"
            :d="`M${X(ROWS[link.row].slices[link.slice].t0) + 3} ${L.rowY[link.row] + L.rowH} L${X(ROWS[link.prog].slices[0].t0) + 3} ${L.rowY[link.prog]}`"
          />
        </g>

        <!-- The rows. -->
        <g v-for="(row, r) in ROWS" :key="r" class="row" :class="`row-${r}`">
          <line class="track" :x1="L.x0" :x2="L.x1" :y1="L.rowY[r] + L.rowH / 2" :y2="L.rowY[r] + L.rowH / 2" />
          <text v-if="head(row)" class="row-head" :x="narrow ? 12 : 20" :y="L.rowY[r] + L.rowH / 2 - 2">{{ head(row) }}</text>
          <text class="row-sub" :x="narrow ? 12 : 20" :y="head(row) ? L.rowY[r] + L.rowH / 2 + 11 : L.rowY[r] + L.rowH / 2 + 4">{{ sub(row) }}</text>
          <g v-for="(s, j) in row.slices" :key="j">
            <rect class="slice" :class="[s.kind, `lane-${row.lane}`]" :x="X(s.t0)" :y="L.rowY[r]" :width="Math.max(X(s.t1) - X(s.t0) - 1, 2)" :height="L.rowH" rx="3" />
            <text v-if="s.label && X(s.t1) - X(s.t0) > word(s.label).length * 6.8 + 8" class="slice-word" :data-slice="j" :x="X(s.t0) + 5" :y="L.rowY[r] + L.rowH / 2 + 4">{{ word(s.label) }}</text>
          </g>
        </g>

        <g class="playhead" :transform="`translate(${L.x0} 0)`">
          <g class="playhead-in">
            <rect x="-10" :y="L.axis - 6" width="20" :height="L.rowY[2] + L.rowH - L.axis + 16" :fill="`url(#${id}-head)`" opacity="0.25" />
            <line :y1="L.axis - 6" :y2="L.rowY[2] + L.rowH + 10" class="playhead-line" />
          </g>
        </g>

        <!-- The session logs, and the run's record of them. -->
        <g v-for="(log, i) in LOGS" :key="log.id" :transform="`translate(${L.logs[i].x} ${L.logs[i].y}) scale(${L.logs[i].s})`">
          <g class="log-move">
            <g class="log-float">
              <circle v-if="log.ours >= 0" class="log-halo" r="70" :fill="`url(#${id}-halo-${log.ours ? 2 : 1})`" />
              <g class="log" :class="{ distant: L.logs[i].s < 0.9 }">
                <rect :x="-L.card.w / 2" :y="-L.card.h / 2" :width="L.card.w" :height="L.card.h" rx="8" />
                <g class="log-id">
                  <text class="log-hex" y="-2" text-anchor="middle">{{ log.id }}</text>
                  <text class="log-cli" y="13" text-anchor="middle">{{ log.cli }}.jsonl</text>
                </g>
              </g>
            </g>
          </g>
        </g>

        <g :transform="`translate(${L.ledger.x} ${L.ledger.y})`">
          <g class="ledger">
            <rect :x="-L.ledger.w / 2" y="-38" :width="L.ledger.w" height="76" rx="10" />
            <text class="ledger-head" :x="-L.ledger.w / 2 + 14" y="-16">the run's record</text>
            <text class="ledger-line" :x="-L.ledger.w / 2 + 14" y="6">7f3a9c → actor · claude</text>
            <text class="ledger-line" :x="-L.ledger.w / 2 + 14" y="26">c19e04 → reviewer · codex</text>
          </g>
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

.grid-dot {
  fill: var(--hmz-stage-line);
}

.log-halo {
  opacity: var(--hmz-glow);
}

.log rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.4;
}

.log.distant {
  opacity: 0.75;
}

.log-hex {
  font-family: var(--vp-font-family-mono);
  font-size: 13.5px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.log-cli {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  fill: var(--hmz-stage-dim);
}

.ledger rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
}

.ledger-head {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-accent);
}

.ledger-line {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  fill: var(--hmz-stage-ink);
}

.axis-line,
.divider-line {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.axis-tick {
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 2 4;
}

.axis-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.divider-word {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-lane-4);
}

.track {
  stroke: var(--hmz-stage-line);
}

.row-head {
  font-size: 12.5px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.row-sub {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.slice.lane-1 {
  fill: var(--hmz-lane-1);
  stroke: var(--hmz-lane-1);
}

.slice.lane-2 {
  fill: var(--hmz-lane-2);
  stroke: var(--hmz-lane-2);
}

.slice.lane-3 {
  fill: var(--hmz-lane-3);
  stroke: var(--hmz-lane-3);
}

.slice.lane-4 {
  fill: var(--hmz-lane-4);
  stroke: var(--hmz-lane-4);
}

.slice.lane-5 {
  fill: var(--hmz-lane-5);
  stroke: var(--hmz-lane-5);
}

.slice.think {
  fill-opacity: 0.35;
}

.slice.say {
  fill-opacity: 0.12;
  stroke-width: 1.5;
}

.slice.prog {
  fill-opacity: 0.85;
}

.slice-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
  pointer-events: none;
}

.link-line {
  fill: none;
  stroke-width: 1.5;
  stroke-dasharray: 3 3;
}

.link-line.lane-3 {
  stroke: var(--hmz-lane-3);
}

.link-line.lane-4 {
  stroke: var(--hmz-lane-4);
}

.link-line.lane-5 {
  stroke: var(--hmz-lane-5);
}

.playhead-line {
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.chrome-frame {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.5;
}

.chrome-bar {
  stroke: var(--hmz-stage-line);
}

.chrome-dot {
  fill: var(--hmz-stage-line);
}

.chrome-title {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.chrome-file {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.lock rect {
  fill: color-mix(in srgb, var(--hmz-accent) 18%, var(--hmz-stage-card));
  stroke: var(--hmz-accent);
}

.lock text {
  font-size: 11.5px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}
</style>
