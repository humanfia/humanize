<script setup lang="ts">
// Why one flow cannot do every task, drawn as a search over a landscape: every program that
// could be written along the bottom, how good each one is going up.
//
// Building a project is constraint satisfaction: a line across the landscape is "passes every
// check", and any program above it will do, so a loop of work and fresh review stops at the
// first one it reaches (RLCR). A kernel is optimization: the best one is wanted. An agent that
// fine-tunes climbs the nearest peak and stays there; one that rewrites jumps, and can land
// lower than it started. Flame-chase alternates the two on one repository, so a rewrite lifts
// the work off one peak and fine-tuning climbs the next. And each kind of problem has its own
// flow. A simulation: the landscape is a sum of three bumps, not a measurement.
import { computed } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { create, drawOn, fadeIn, fadeOut, growFrom, indicate, passingFlash, retype, wiggle, write } from '../../motion/manim'
import { useNarrow } from '../../motion/layout'
import { useScene } from '../../motion/useScene'
import { pop, ring } from '../user-kit/moves'

type Timeline = gsap.core.Timeline

const BEATS = [
  'Building a project: any program that passes every check will do',
  'A kernel: only the fastest will do, and one agent stalls',
  'Flame-chase: a rewrite, then fine-tuning, peak after peak',
  'Each kind of problem has a flow of its own',
]

/** How good the program at `u` (0..1 along the bottom) is: three bumps on a floor. */
const bump = (u: number, c: number, s: number) => Math.exp(-(((u - c) / s) ** 2) / 2)
const f = (u: number) => 0.08 + 0.37 * bump(u, 0.22, 0.075) + 0.6 * bump(u, 0.55, 0.08) + 0.84 * bump(u, 0.84, 0.07)

/** "Passes every check", for the first beat. */
const BAR = 0.5
/** Where the review loop's rounds land: the last one is the first above the bar. */
const ROUNDS = [0.4, 0.44, 0.47, 0.51]
/** The chase: a rewrite jumps, fine-tuning climbs. */
const CHASE: { kind: 'jump' | 'climb'; from: number; to: number }[] = [
  { kind: 'jump', from: 0.22, to: 0.465 },
  { kind: 'climb', from: 0.465, to: 0.55 },
  { kind: 'jump', from: 0.55, to: 0.765 },
  { kind: 'climb', from: 0.765, to: 0.84 },
]

const ROWS = [
  { kind: 'constraint satisfaction', eg: 'building a project', flow: 'humanize1 · rlar', how: 'work, review, repeat' },
  { kind: 'optimization', eg: 'a faster kernel', flow: 'flame_chase', how: 'rewrite, then fine-tune' },
  { kind: 'proof search', eg: 'a Lean theorem', flow: 'recursive_lean_prover', how: 'split, prove, review' },
  { kind: 'a problem of yours', eg: 'decision, prediction, games…', flow: 'a flow you weave', how: 'an async Python function' },
]

interface Layout {
  w: number
  h: number
  plot: { x0: number; x1: number; top: number; floor: number }
  axis: { y: number }
  kind: { x: number; y: number }
  legend: { x: number; y: number; dy: number; anchor: 'start' | 'end' }
  map: { left: number; right: number; cw: number; ch: number; y0: number; dy: number; stacked: boolean }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  plot: { x0: 52, x1: 604, top: 64, floor: 296 },
  axis: { y: 326 },
  kind: { x: 52, y: 36 },
  legend: { x: 604, y: 32, dy: 18, anchor: 'end' },
  map: { left: 40, right: 360, cw: 240, ch: 52, y0: 34, dy: 76, stacked: false },
}

const NARROW: Layout = {
  w: 360,
  h: 520,
  plot: { x0: 22, x1: 342, top: 150, floor: 418 },
  axis: { y: 450 },
  kind: { x: 22, y: 40 },
  legend: { x: 22, y: 76, dy: 20, anchor: 'start' },
  map: { left: 22, right: 70, cw: 270, ch: 46, y0: 18, dy: 126, stacked: true },
}

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const X = (u: number) => L.value.plot.x0 + u * (L.value.plot.x1 - L.value.plot.x0)
const Y = (v: number) => L.value.plot.floor - v * (L.value.plot.floor - L.value.plot.top)
const at = (u: number) => ({ x: X(u), y: Y(f(u)) })

/** The landscape's outline, from `a` to `b`, as a path. */
function ridge(a = 0, b = 1, n = 140): string {
  const pts: string[] = []
  for (let i = 0; i <= n; i += 1) {
    const u = a + ((b - a) * i) / n
    pts.push(`${X(u).toFixed(1)} ${Y(f(u)).toFixed(1)}`)
  }
  return `M${pts.join(' L')}`
}
const land = computed(() => `${ridge()} L${X(1)} ${L.value.plot.floor} L${X(0)} ${L.value.plot.floor} Z`)

/** A rewrite's leap from one program to another, as an arc over the landscape. */
function leap(a: number, b: number): string {
  const p = at(a)
  const q = at(b)
  const lift = Math.abs(q.x - p.x) * 0.45 + 20
  return `M${p.x} ${p.y} Q${(p.x + q.x) / 2} ${Math.min(p.y, q.y) - lift} ${q.x} ${q.y}`
}

/** The points a dot passes through: along the ridge for a climb, along the arc for a leap. */
function route(kind: 'jump' | 'climb', a: number, b: number, n = 24) {
  const xs: number[] = []
  const ys: number[] = []
  const p = at(a)
  const q = at(b)
  const lift = Math.abs(q.x - p.x) * 0.45 + 20
  const cy = Math.min(p.y, q.y) - lift
  for (let i = 0; i <= n; i += 1) {
    const t = i / n
    if (kind === 'climb') {
      const r = at(a + (b - a) * t)
      xs.push(r.x)
      ys.push(r.y)
    } else {
      xs.push((1 - t) ** 2 * p.x + 2 * (1 - t) * t * ((p.x + q.x) / 2) + t ** 2 * q.x)
      ys.push((1 - t) ** 2 * p.y + 2 * (1 - t) * t * cy + t ** 2 * q.y)
    }
  }
  return { x: xs, y: ys }
}

function move(tl: Timeline, dot: Element, kind: 'jump' | 'climb', a: number, b: number, when: gsap.Position, duration: number) {
  const r = route(kind, a, b)
  tl.to(dot, { keyframes: { x: r.x, y: r.y, easeEach: 'none' }, duration, ease: kind === 'jump' ? 'rush.from' : 'smooth' }, when)
}

/** Where row `i` of the map puts its problem and its flow. */
const cell = (i: number, side: 0 | 1) => {
  const m = L.value.map
  if (m.stacked) return { x: side ? m.right : m.left, y: m.y0 + i * m.dy + side * (m.ch + 20) }
  return { x: side ? m.right : m.left, y: m.y0 + i * m.dy }
}
const wire = (i: number) => {
  const m = L.value.map
  const a = cell(i, 0)
  const b = cell(i, 1)
  if (m.stacked) return `M${b.x - 22} ${a.y + m.ch} V${b.y + m.ch / 2} H${b.x}`
  return `M${a.x + m.cw} ${a.y + m.ch / 2} C${a.x + m.cw + 40} ${a.y + m.ch / 2} ${b.x - 40} ${b.y + m.ch / 2} ${b.x} ${b.y + m.ch / 2}`
}

const scene = useScene({
  still: 'rest',
  repeatDelay: 1.2,
  build(tl, q) {
    const one = (s: string) => q(s)[0]

    tl.set(q('.plot, .map'), { autoAlpha: 1 }, 0)
    // What `create` and `drawOn` draw is hidden by its own stroke, drawn to nothing, rather than
    // by its visibility: they fade a thing in from wherever it is, and from hidden that is out.
    tl.set(q('.land, .ok-zone, .bar-word, .axis-word, .kind, .legend, .dot, .miss, .done, .tag, .best, .stuck, .lower, .row'), { autoAlpha: 0 }, 0)
    tl.set(one('.dot-r'), { x: at(ROUNDS[0]).x, y: at(ROUNDS[0]).y }, 0)
    tl.set(one('.dot-a'), { x: at(0.08).x, y: at(0.08).y }, 0)
    tl.set(one('.dot-b'), { x: at(0.22).x, y: at(0.22).y }, 0)
    tl.set(one('.dot-c'), { x: at(0.22).x, y: at(0.22).y }, 0)
    tl.set(one('.best'), { y: Y(f(0.22)) }, 0)

    // 0 · constraint satisfaction: one feasible program is enough.
    tl.addLabel('beat-0', 0)
    drawOn(tl, one('.axis'), 0.1, { duration: 0.6 })
    tl.set(q('.axis-word, .kind, .bar-word'), { autoAlpha: 1 }, 0.3)
    q('.axis-text').forEach((el, i) => write(tl, el, 0.3 + i * 0.2))
    create(tl, one('.ridge'), 0.4, { duration: 1.4 })
    tl.to(one('.land'), { autoAlpha: 1, duration: 0.8, ease: 'smooth' }, 1.2)
    write(tl, one('.kind-text'), 0.5)
    drawOn(tl, one('.bar'), 1.6, { duration: 0.9 })
    tl.to(one('.ok-zone'), { autoAlpha: 1, duration: 0.6, ease: 'smooth' }, 2.1)
    write(tl, one('.bar-text'), 2.2)
    growFrom(tl, one('.dot-r'), 2.9)
    ROUNDS.slice(1).forEach((u, i) => {
      const t = 3.5 + i * 0.95
      pop(tl, one(`.miss-${i}`), t)
      move(tl, one('.dot-r'), 'climb', ROUNDS[i], u, t + 0.2, 0.55)
    })
    const T0done = 3.5 + (ROUNDS.length - 1) * 0.95
    ring(tl, one('.dot-r .halo'), T0done, { to: 2.4 })
    pop(tl, one('.done'), T0done + 0.1, { from: 0.6 })
    indicate(tl, one('.done'), T0done + 0.6, { scale: 1.1 })

    // 1 · optimization: the bar is gone; the best program is wanted, and one agent stalls.
    const T1 = T0done + 2.2
    tl.addLabel('beat-1', T1)
    fadeOut(tl, q('.bar, .ok-zone, .bar-word, .done, .miss, .dot-r'), T1, { duration: 0.5 })
    retype(tl, one('.kind-text'), 'optimization: only the best will do', T1 + 0.3)
    fadeIn(tl, q('.legend'), T1 + 0.5, { shift: { y: -6 }, stagger: 0.15 })
    growFrom(tl, one('.dot-a'), T1 + 0.9)
    move(tl, one('.dot-a'), 'climb', 0.08, 0.22, T1 + 1.3, 1.4)
    pop(tl, one('.stuck'), T1 + 2.8)
    wiggle(tl, one('.dot-a circle'), T1 + 2.9)
    growFrom(tl, one('.dot-b'), T1 + 3.5)
    tl.set(one('.dot-a'), { autoAlpha: 0.35 }, T1 + 3.5)
    move(tl, one('.dot-b'), 'jump', 0.22, 0.36, T1 + 3.9, 0.9)
    pop(tl, one('.lower'), T1 + 4.8)

    // 2 · flame-chase: the two alternate, and the work climbs from peak to higher peak.
    const T2 = T1 + 6.2
    tl.addLabel('beat-2', T2)
    fadeOut(tl, q('.dot-a, .dot-b, .stuck, .lower'), T2, { duration: 0.5 })
    retype(tl, one('.kind-text'), 'flame-chase: take turns', T2 + 0.3)
    growFrom(tl, one('.dot-c'), T2 + 0.6)
    tl.to(one('.best'), { autoAlpha: 1, duration: 0.4 }, T2 + 0.8)
    let t = T2 + 1.2
    CHASE.forEach((step, i) => {
      const d = step.kind === 'jump' ? 0.9 : 1.1
      drawOn(tl, one(`.chase-${i}`), t, { duration: d, ease: step.kind === 'jump' ? 'rush.from' : 'smooth' })
      move(tl, one('.dot-c'), step.kind, step.from, step.to, t, d)
      pop(tl, one(`.tag-${i}`), t + d * 0.4)
      if (step.kind === 'climb') {
        tl.to(one('.best'), { y: Y(f(step.to)), duration: 0.6, ease: 'settle' }, t + d)
        ring(tl, one('.dot-c .halo'), t + d)
      }
      t += d + 0.45
    })
    indicate(tl, one('.dot-c circle'), t, { scale: 1.4 })
    tl.addLabel('rest', t + 0.9)

    // 3 · different problems, different flows.
    const T3 = t + 2.6
    tl.addLabel('beat-3', T3)
    fadeOut(tl, one('.plot'), T3, { duration: 0.7 })
    ROWS.forEach((_, i) => {
      fadeIn(tl, one(`.row-${i} .from`), T3 + 0.6 + i * 0.55, { shift: { x: -14 } })
      tl.set(one(`.row-${i}`), { autoAlpha: 1 }, T3 + 0.6 + i * 0.55)
      drawOn(tl, one(`.wire-${i}`), T3 + 0.9 + i * 0.55, { duration: 0.6 })
      fadeIn(tl, one(`.row-${i} .to`), T3 + 1.3 + i * 0.55, { shift: { x: 14 } })
      passingFlash(tl, one(`.wire-${i}`), T3 + 1.5 + i * 0.55, { color: 'var(--hmz-accent)', duration: 0.7 })
    })
    tl.to(q('.map'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T3 + 0.6 + ROWS.length * 0.55 + 4.2)
  },
})

const LABEL =
  'Why one flow cannot do every task, drawn over a landscape of every program that could be written, higher meaning better. ' +
  'Building a project is constraint satisfaction: a line marks "passes every check", and a loop of work and fresh review (RLCR) stops at the first program above it. ' +
  'A kernel is optimization: the best program is wanted. An agent that fine-tunes climbs the nearest peak and stalls there; one that rewrites jumps, and can land lower. ' +
  'Flame-chase alternates the two: a rewrite leaves one peak, fine-tuning climbs the next, until the work is on the highest peak. ' +
  'Then a map: constraint satisfaction to humanize1 and rlar, optimization to flame_chase, proof search to recursive_lean_prover, and a problem of your own to a flow you weave.'
</script>

<template>
  <HmzStage :scene="scene" :beats="BEATS" sim mobile-ratio="9 / 13" :label="LABEL">
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="plot">
        <g class="kind"><text class="kind-text" :x="L.kind.x" :y="L.kind.y">constraint satisfaction: one is enough</text></g>
        <g class="legend"><circle :cx="L.legend.anchor === 'end' ? L.legend.x - 182 : L.legend.x + 5" :cy="L.legend.y - 4" r="5" class="swatch-a" /><text class="legend-text" :x="L.legend.anchor === 'end' ? L.legend.x - 172 : L.legend.x + 16" :y="L.legend.y">fine-tunes, as Codex did</text></g>
        <g class="legend"><circle :cx="L.legend.anchor === 'end' ? L.legend.x - 182 : L.legend.x + 5" :cy="L.legend.y + L.legend.dy - 4" r="5" class="swatch-b" /><text class="legend-text" :x="L.legend.anchor === 'end' ? L.legend.x - 172 : L.legend.x + 16" :y="L.legend.y + L.legend.dy">rewrites, as Claude Code did</text></g>

        <path class="land" :d="land" />
        <rect class="ok-zone" :x="L.plot.x0" :y="L.plot.top - 20" :width="L.plot.x1 - L.plot.x0" :height="Y(BAR) - L.plot.top + 20" />
        <line class="bar" :x1="L.plot.x0" :x2="L.plot.x1" :y1="Y(BAR)" :y2="Y(BAR)" />
        <g class="bar-word"><text class="bar-text" :x="L.plot.x0 + 4" :y="Y(BAR) - 8">passes every check</text></g>
        <path class="ridge" :d="ridge()" />
        <line class="axis" :x1="L.plot.x0" :x2="L.plot.x1" :y1="L.plot.floor + 8" :y2="L.plot.floor + 8" />
        <g class="axis-word"><text class="axis-text" :x="L.plot.x0" :y="L.axis.y">every program that could be written →</text></g>
        <g class="axis-word"><text class="axis-text" :x="L.plot.x1" :y="L.axis.y" text-anchor="end">↑ better</text></g>

        <!-- The review loop's rounds: each one short of the bar, then one over it. -->
        <g v-for="(u, i) in ROUNDS.slice(0, -1)" :key="`m${i}`" class="miss" :class="`miss-${i}`">
          <text class="miss-text" :x="at(u).x" :y="at(u).y + 22" text-anchor="middle">✗</text>
        </g>
        <g class="done">
          <rect class="done-bg" :x="at(ROUNDS[3]).x + 14" :y="at(ROUNDS[3]).y - 40" width="156" height="24" rx="6" />
          <text class="done-text" :x="at(ROUNDS[3]).x + 92" :y="at(ROUNDS[3]).y - 24" text-anchor="middle">✓ done: one is enough</text>
        </g>

        <!-- Flame-chase: the path the work takes. -->
        <path v-for="(s, i) in CHASE" :key="`c${i}`" class="chase-path" :class="[`chase-${i}`, s.kind]" :d="s.kind === 'jump' ? leap(s.from, s.to) : ridge(s.from, s.to, 30)" />
        <g v-for="(s, i) in CHASE" :key="`t${i}`" class="tag" :class="[`tag-${i}`, s.kind]">
          <text class="tag-text" :x="(at(s.from).x + at(s.to).x) / 2 + (s.kind === 'jump' ? 0 : 12)" :y="s.kind === 'jump' ? Math.min(at(s.from).y, at(s.to).y) - Math.abs(at(s.to).x - at(s.from).x) * 0.22 - 18 : (at(s.from).y + at(s.to).y) / 2 + 12" :text-anchor="s.kind === 'jump' ? 'middle' : 'start'">{{ s.kind === 'jump' ? 'rewrite' : 'fine-tune' }}</text>
        </g>
        <g class="best">
          <line class="best-line" :x1="L.plot.x0" :x2="L.plot.x1" y1="0" y2="0" />
          <text class="best-text" :x="L.plot.x0 + 4" y="-6">best so far</text>
        </g>

        <g class="stuck"><text class="note-text" :x="at(0.22).x" :y="at(0.22).y - 18" text-anchor="middle">stuck on the nearest peak</text></g>
        <g class="lower"><text class="note-text" :x="at(0.36).x + 8" :y="at(0.36).y + 26" text-anchor="middle">landed lower</text></g>

        <g class="dot dot-r"><circle class="halo" r="7" /><circle class="core" r="7" /></g>
        <g class="dot dot-a"><circle class="core" r="7" /></g>
        <g class="dot dot-b"><circle class="core" r="7" /></g>
        <g class="dot dot-c"><circle class="halo" r="7" /><circle class="core" r="7.5" /></g>
      </g>

      <g class="map">
        <path v-for="(_, i) in ROWS" :key="`w${i}`" class="wire" :class="`wire-${i}`" :d="wire(i)" />
        <g v-for="(row, i) in ROWS" :key="`r${i}`" class="row" :class="`row-${i}`">
          <g class="from">
            <rect class="cell" :x="cell(i, 0).x" :y="cell(i, 0).y" :width="L.map.cw" :height="L.map.ch" rx="9" />
            <text class="cell-name" :x="cell(i, 0).x + 14" :y="cell(i, 0).y + 21">{{ row.kind }}</text>
            <text class="cell-sub" :x="cell(i, 0).x + 14" :y="cell(i, 0).y + 38">{{ row.eg }}</text>
          </g>
          <g class="to">
            <rect class="cell flow" :x="cell(i, 1).x" :y="cell(i, 1).y" :width="L.map.cw" :height="L.map.ch" rx="9" />
            <text class="cell-name mono" :x="cell(i, 1).x + 14" :y="cell(i, 1).y + 21">{{ row.flow }}</text>
            <text class="cell-sub" :x="cell(i, 1).x + 14" :y="cell(i, 1).y + 38">{{ row.how }}</text>
          </g>
        </g>
      </g>
    </svg>
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.land {
  fill: color-mix(in srgb, var(--hmz-lane-1) 9%, transparent);
}

.ridge {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 2;
  stroke-linejoin: round;
}

.axis {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.4;
}

.axis-text,
.legend-text,
.cell-sub {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.kind-text {
  font-size: 14px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.ok-zone {
  fill: color-mix(in srgb, var(--hmz-accent) 10%, transparent);
}

.bar {
  stroke: var(--hmz-accent);
  stroke-width: 1.6;
  stroke-dasharray: 6 5;
}

.bar-text {
  font-size: 12px;
  font-weight: 600;
  fill: var(--hmz-accent);
}

.miss-text {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-red);
}

.done-bg {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.4;
}

.done-text {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.dot .core {
  stroke: var(--hmz-stage-card);
  stroke-width: 2;
}

.dot .halo {
  fill: none;
  stroke-width: 2;
}

.dot-r .core,
.swatch-r {
  fill: var(--hmz-accent);
}

.dot-r .halo {
  stroke: var(--hmz-accent);
}

.dot-a .core,
.swatch-a {
  fill: var(--hmz-lane-1);
}

.dot-b .core,
.swatch-b {
  fill: var(--hmz-accent-2);
}

.dot-c .core {
  fill: var(--hmz-warm);
}

.dot-c .halo {
  stroke: var(--hmz-warm);
}

.chase-path {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
}

.chase-path.jump {
  stroke: var(--hmz-accent-2);
  stroke-dasharray: 5 6;
  stroke-width: 2;
}

.chase-path.climb {
  stroke: var(--hmz-lane-1);
}

.tag-text {
  font-size: 12px;
  font-weight: 700;
}

.tag.jump .tag-text {
  fill: var(--hmz-accent-2);
}

.tag.climb .tag-text {
  fill: var(--hmz-lane-1);
}

.best-line {
  stroke: var(--hmz-warm);
  stroke-width: 1.2;
  stroke-dasharray: 3 5;
}

.best-text {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-warm);
}

.note-text {
  font-size: 12px;
  font-style: italic;
  fill: var(--hmz-stage-ink);
}

.cell {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.cell.flow {
  fill: color-mix(in srgb, var(--hmz-accent) 8%, var(--hmz-stage-card));
  stroke: var(--hmz-accent);
}

.cell-name {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.cell-name.mono {
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
}

.wire {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.4;
  stroke-dasharray: 4 4;
}
</style>
