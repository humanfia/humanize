<script setup lang="ts">
// A change's way from a clone to `main`. Along the top, the stops; left, the terminal they are
// typed into, with what each says back; under it, the three directories of tests; right, what
// CI runs on every push and pull request.
//
// Drawn from docs/contributing/index.md (set up, the checks, where a test goes) and
// docs/contributing/ci.md with .github/workflows/ci.yml: `lint` runs every pre-commit hook;
// `unit` runs one job per package of src/hmz and `integration` one job per topic, each on
// Linux and macOS with Python 3.12; `ci-ok` is green when they all passed. tests/system is
// never in CI.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { createFx, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'Clone, then uv sync: Python and all, pinned',
  'Hooks in, an edit, and the fast loop',
  'Before you push: every hook, unit and integration',
  'A push or a pull request: lint first',
  'Unit: a job per package, on Linux and macOS',
  'Integration: a job per topic, then ci-ok',
]

const STOPS = ['clone', 'uv sync', 'hooks', 'edit', 'fast loop', 'before push', 'push', 'CI']

type Kind = 'cmd' | 'note'
const TERM: { kind: Kind; text: string }[] = [
  { kind: 'cmd', text: '$ git clone …github.com/humanfia/humanize.git' },
  { kind: 'cmd', text: '$ uv sync' },
  { kind: 'note', text: '# .venv, as uv.lock pins it, Python included' },
  { kind: 'cmd', text: '$ uv run pre-commit install' },
  { kind: 'note', text: '# checks each commit with the hooks CI runs' },
  { kind: 'note', text: '# edit: a change and its tests, one commit' },
  { kind: 'cmd', text: '$ uv run pytest tests/unit/flows' },
  { kind: 'note', text: '# one package: seconds' },
  { kind: 'cmd', text: '$ uv run pre-commit run --all-files' },
  { kind: 'note', text: '# format, lint, types: seconds' },
  { kind: 'cmd', text: '$ uv run pytest' },
  { kind: 'note', text: '# unit and integration: minutes' },
  { kind: 'cmd', text: '$ git push' },
]
/** How many lines the terminal scrolls by before you push: it shows eight at once. */
const SCROLL = 5
const LH = 15

const TIERS = [
  { dir: 'unit/', say: ['a package alone,', 'the rest mocked'], you: false },
  { dir: 'integration/', say: ['packages wired', 'against our fakes'], you: false },
  { dir: 'system/', say: ['real agents,', 'real tasks'], you: true },
]

/** The two matrices of ci.yml: a column each, a row per job, a cell per system. */
const COLUMNS = [
  { name: 'unit', by: 'per package', rows: ['cli', 'coganchor', 'daemon', 'flows', 'runtime', 'sdk', 'tui'] },
  { name: 'integration', by: 'per topic', rows: ['core', 'agents', 'tui', 'daemon', 'anchor'] },
]
const OSES = ['L', 'M']

interface Box {
  x: number
  y: number
  w: number
  h: number
}
interface Layout {
  w: number
  h: number
  stops: { x: number; y: number }[]
  track: string
  term: Box
  tiers: Box
  ci: Box
  open: { x: number; y: number; s: number }
  ciShot: { x: number; y: number; s: number }
  whole: { x: number; y: number; s: number }
}

const WIDE_STOPS = STOPS.map((_, i) => ({ x: 36 + i * 81, y: 50 }))
const NARROW_STOPS = STOPS.map((_, i) => (i < 4 ? { x: 44 + i * 90, y: 30 } : { x: 314 - (i - 4) * 90, y: 84 }))

const WIDE: Layout = {
  w: 640,
  h: 360,
  stops: WIDE_STOPS,
  track: `M${WIDE_STOPS[0].x} 50 L${WIDE_STOPS[7].x} 50`,
  term: { x: 12, y: 86, w: 372, h: 164 },
  tiers: { x: 12, y: 270, w: 372, h: 76 },
  ci: { x: 396, y: 86, w: 232, h: 262 },
  open: { x: 200, y: 140, s: 1.32 },
  ciShot: { x: 470, y: 200, s: 1.12 },
  whole: { x: 320, y: 180, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 680,
  stops: NARROW_STOPS,
  track: `M44 30 L314 30 C350 30 350 84 314 84 L44 84`,
  term: { x: 14, y: 124, w: 332, h: 166 },
  tiers: { x: 14, y: 314, w: 332, h: 76 },
  ci: { x: 14, y: 404, w: 332, h: 264 },
  open: { x: 180, y: 190, s: 1.22 },
  ciShot: { x: 180, y: 520, s: 1.1 },
  whole: { x: 180, y: 340, s: 1 },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const termY = (i: number) => L.value.term.y + 38 + i * LH
const tierW = computed(() => (L.value.tiers.w - 2 * 9) / 3)
const tierX = (i: number) => L.value.tiers.x + i * (tierW.value + 9)
const tierTop = computed(() => L.value.tiers.y + 4)
const lintY = computed(() => L.value.ci.y + 44)
const capY = computed(() => L.value.ci.y + 80)
const rowY = (i: number) => L.value.ci.y + 96 + i * 16
const okY = computed(() => L.value.ci.y + 218)
const colW = computed(() => (L.value.ci.w - 12) / 2)
const colX = (c: number) => L.value.ci.x + 12 + c * colW.value
/** The left of a job's cell for one system: two cells at the right of its column. */
const cellX = (c: number, os: number) => colX(c) + colW.value - 40 + os * 17
/** The two check rows: `lint` before the tests, `ci-ok` after them. */
const ROWS = computed(() => [
  { cls: 'lint', name: 'lint', when: 'every hook', y: lintY.value },
  { cls: 'ok', name: 'ci-ok', when: 'all of them passed', y: okY.value },
])

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
    const ok = () => palette.accent
    const warm = () => palette.warm

    // Where along the track each stop is, as a fraction of it, read off the path as drawn.
    const track = one('.progress') as SVGPathElement
    const total = track.getTotalLength?.() || 1
    const frac = l.stops.map((s) => {
      let best = 0
      let d = Infinity
      for (let k = 0; k <= 200; k += 1) {
        const p = track.getPointAtLength((total * k) / 200)
        const e = (p.x - s.x) ** 2 + (p.y - s.y) ** 2
        if (e < d) {
          d = e
          best = k / 200
        }
      }
      return best
    })

    const marker = one('.marker')
    const stop = (i: number, when: number) => {
      const s = l.stops[i]
      tl.to(marker, { x: s.x - l.stops[0].x, y: s.y - l.stops[0].y, duration: 0.6, ease: 'cine' }, when)
      tl.to(track, { drawSVG: `0% ${frac[i] * 100}%`, duration: 0.6, ease: 'cine' }, when)
      tl.to(at('.stop-dot')[i], { opacity: 1, duration: 0.3 }, when + 0.45)
      tl.to(at('.stop-word')[i], { opacity: 1, duration: 0.3 }, when + 0.45)
      cam.flare(s, lane1, when + 0.55, 10, 60)
    }
    const lines = at('.term-line text')
    const say = (i: number, when: number) => {
      const el = lines[i]
      const text = TERM[i].text
      tl.set(at('.term-line')[i], { opacity: 1 }, when)
      if (TERM[i].kind === 'cmd') {
        const d = Math.max(0.25, text.length / 46)
        tl.fromTo(el, { text: '' }, { text: { value: text }, duration: d, ease: 'none', immediateRender: false }, when)
        return when + d
      }
      tl.fromTo(at('.term-line')[i], { opacity: 0 }, { opacity: 1, duration: 0.35, immediateRender: false }, when)
      return when + 0.35
    }
    /** A check row lit: `lint` or `ci-ok`. */
    const check = (sel: string, y: number, when: number) => {
      tl.to(at(`${sel} .check`), { opacity: 1, duration: 0.3 }, when)
      tl.to(at(`${sel} .check-off .check-name`), { opacity: 0, duration: 0.3 }, when)
      tl.fromTo(at(`${sel} .check-dot`), { scale: 0.3, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.4, ease: 'back.out(3)', immediateRender: false }, when)
      cam.flare({ x: l.ci.x + 16, y: y - 4 }, ok, when, 8, 50)
    }
    /** Every job of one column, on both systems at once, each as it finishes. */
    const column = (c: number, when: number) => {
      tl.to(at(`.col-${c} .col-cap`), { opacity: 1, duration: 0.35 }, when)
      COLUMNS[c].rows.forEach((_, r) =>
        OSES.forEach((__, os) => {
          const t = when + 0.3 + r * 0.16 + os * 0.08
          tl.to(at(`.cell-lit-${c}-${r}-${os}`), { opacity: 1, duration: 0.3 }, t)
          cam.flare({ x: cellX(c, os) + 7.5, y: rowY(r) - 4 }, ok, t, 8, 50)
        }),
      )
    }
    /** The right end of a line once the terminal has scrolled. */
    const termOut = (i: number) => ({ x: l.term.x + l.term.w - 10, y: termY(i - SCROLL) - 4 })

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.term-line, .stop-dot, .tier-lit, .you-hot, .check, .status, .col-cap, .cell-lit, .foot'), { opacity: 0 }, 0)
    tl.set(at('.stop-word'), { opacity: 0.5 }, 0)
    tl.set(at('.check-off'), { opacity: 1 }, 0)
    tl.set(track, { drawSVG: '0% 0%' }, 0)
    tl.set(marker, { x: 0, y: 0, opacity: 0 }, 0)
    tl.set(one('.scroll'), { y: 0 }, 0)

    // 0 · the way laid out; a clone, and `uv sync` makes the environment uv.lock pins.
    tl.addLabel('beat-0', 0)
    tl.fromTo(at('.panel'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.6, stagger: 0.1 }, 0.05)
    tl.fromTo(one('.track-base'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.2, ease: 'cine' }, 0.1)
    tl.to(marker, { opacity: 1, duration: 0.3 }, 0.8)
    stop(0, 0.8)
    say(0, 1.2)
    cam.shot(l.whole, 1.4, 2.4)
    stop(1, 2.6)
    say(1, 2.8)
    say(2, 3.3)

    // 1 · the hooks, an edit, and one package's unit tests as the loop you write in.
    const T1 = 4.4
    tl.addLabel('beat-1', T1)
    stop(2, T1)
    say(3, T1 + 0.2)
    say(4, T1 + 1)
    stop(3, T1 + 1.6)
    say(5, T1 + 1.9)
    stop(4, T1 + 2.6)
    const t6 = say(6, T1 + 2.8)
    say(7, t6 + 0.2)
    cam.flare({ x: l.term.x + 70, y: termY(7) - 4 }, ok, t6 + 0.4, 20)

    // 2 · before the push: every hook, then unit and integration; system is yours to choose.
    const T2 = T1 + 5.4
    tl.addLabel('beat-2', T2)
    stop(5, T2)
    tl.to(one('.scroll'), { y: -SCROLL * LH, duration: 0.6, ease: 'cine' }, T2 + 0.1)
    const t8 = say(8, T2 + 0.7)
    say(9, t8 + 0.15)
    const t10 = say(10, t8 + 0.7)
    say(11, t10 + 0.15)
    TIERS.forEach((t, i) => {
      if (t.you) return
      cam.beam({ x: l.term.x + 120, y: termY(10 - SCROLL) - 4 }, { x: tierX(i) + tierW.value / 2, y: tierTop.value + 2 }, lane1, t10 + 0.3 + i * 0.25, { duration: 0.6, bend: 0.15 })
      tl.to(at('.tier-lit')[i], { opacity: 1, duration: 0.35 }, t10 + 0.85 + i * 0.25)
    })
    tl.to(at('.tier-lit')[2], { opacity: 1, duration: 0.35 }, t10 + 1.5)
    cam.flare({ x: tierX(2) + tierW.value / 2, y: tierTop.value + 30 }, warm, t10 + 1.5, 12, 60)
    tl.fromTo(one('.you-hot'), { opacity: 0 }, { opacity: 1, duration: 0.3, yoyo: true, repeat: 3, immediateRender: false }, t10 + 1.5)

    // 3 · the push, and `lint`: every pre-commit hook, before any test.
    const T3 = T2 + 5
    tl.addLabel('beat-3', T3)
    stop(6, T3)
    const t12 = say(12, T3 + 0.2)
    cam.shot(l.ciShot, T3 + 0.2, 1.6)
    stop(7, t12 + 0.3)
    cam.beam(termOut(12), { x: l.ci.x + 12, y: l.ci.y + 14 }, lane1, t12 + 0.2, { duration: 0.7, bend: -0.2 })
    check('.lint', lintY.value, t12 + 1.2)

    // 4 · `unit`: a job per package, on Linux and macOS.
    const T4 = T3 + 3
    tl.addLabel('beat-4', T4)
    column(0, T4)

    // 5 · `integration`: a job per topic; then `ci-ok`, the one check to wait for.
    const T5 = T4 + 2.2
    tl.addLabel('beat-5', T5)
    column(1, T5)
    tl.to(one('.foot'), { opacity: 1, duration: 0.4 }, T5 + 1.4)
    check('.ok', okY.value, T5 + 1.8)
    tl.fromTo(one('.status'), { opacity: 0, y: 4 }, { opacity: 1, y: 0, duration: 0.4, immediateRender: false }, T5 + 2)
    cam.flare({ x: l.ci.x + l.ci.w - 30, y: l.ci.y + 13 }, ok, T5 + 2.3, 24)
    cam.shot(l.whole, T5 + 2.2, 1.6)

    tl.addLabel('rest', T5 + 4)
    cam.shot({ ...l.whole, s: l.whole.s * 1.025 }, T5 + 3.9, 2.6, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T5 + 6.6)

    // The empty cells hum while they wait: a slow march of their dashes.
    tl.fromTo(at('.hum'), { strokeDashoffset: 0 }, { strokeDashoffset: -40, duration: tl.duration(), ease: 'none' }, 0)
  },
})

const STATUS = 'ci-ok'
const statusW = Math.round(STATUS.length * 6.6 + 16)
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 17"
    label="A change's way from a clone to main. git clone; uv sync makes .venv exactly as uv.lock pins it, Python included; uv run pre-commit install checks each commit with the hooks CI runs. You edit, a change and its tests in one commit, and run the fast loop, one package's unit tests: uv run pytest tests/unit/flows, seconds. Before you push: uv run pre-commit run --all-files, seconds, and uv run pytest, unit and integration, minutes. Tests sit in three directories: unit tests one package alone, the rest mocked; integration wires packages together against fakes this repository wrote; system runs real agents on real tasks, 5 to 30 minutes each, and is yours to run when your change needs it, never in CI. Then git push. On every push and pull request ci.yml runs lint, every pre-commit hook; then unit, one job per package, and integration, one job per topic, each on Linux and macOS with Python 3.12; and reports ci-ok when they all passed."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <clipPath id="change-path-term"><rect :x="L.term.x" :y="L.term.y + 26" :width="L.term.w" :height="L.term.h - 30" /></clipPath>
      </defs>
      <g class="world">
        <!-- the way -->
        <path class="track-base" :d="L.track" />
        <path class="progress" :d="L.track" />
        <g v-for="(s, i) in STOPS" :key="s">
          <circle class="stop-ring" :cx="L.stops[i].x" :cy="L.stops[i].y" r="6" />
          <circle class="stop-dot" :class="{ ci: i === 7 }" :cx="L.stops[i].x" :cy="L.stops[i].y" r="6" />
          <text class="stop-word" :x="L.stops[i].x" :y="L.stops[i].y + 20" text-anchor="middle">{{ s }}</text>
        </g>
        <g class="marker">
          <circle class="marker-glow" :cx="L.stops[0].x" :cy="L.stops[0].y" r="11" />
          <circle class="marker-core" :cx="L.stops[0].x" :cy="L.stops[0].y" r="4" />
        </g>

        <!-- the terminal -->
        <g class="panel">
          <rect class="card" :x="L.term.x" :y="L.term.y" :width="L.term.w" :height="L.term.h" rx="9" />
          <text class="head" :x="L.term.x + 12" :y="L.term.y + 17">~/humanize</text>
          <g clip-path="url(#change-path-term)">
            <g class="scroll">
              <g v-for="(t, i) in TERM" :key="i" class="term-line" :class="t.kind">
                <text :x="L.term.x + 12" :y="termY(i)">{{ t.text }}</text>
              </g>
            </g>
          </g>
        </g>

        <!-- the three directories of tests -->
        <g class="panel">
          <g v-for="(t, i) in TIERS" :key="t.dir">
            <rect class="card" :x="tierX(i)" :y="tierTop" :width="tierW" :height="L.tiers.h - 4" rx="8" />
            <rect class="tier-lit" :class="{ you: t.you }" :x="tierX(i)" :y="tierTop" :width="tierW" :height="L.tiers.h - 4" rx="8" />
            <text class="tier-dir" :x="tierX(i) + 10" :y="tierTop + 17">{{ t.dir }}</text>
            <text class="tier-say" :x="tierX(i) + 10" :y="tierTop + 34">{{ t.say[0] }}</text>
            <text class="tier-say" :class="{ flag: t.you }" :x="tierX(i) + 10" :y="tierTop + 49">{{ t.say[1] }}</text>
            <g v-if="!t.you" class="pill pill-ci">
              <rect :x="tierX(i) + 10" :y="tierTop + 56" width="26" height="14" rx="7" />
              <text :x="tierX(i) + 23" :y="tierTop + 66" text-anchor="middle">CI</text>
            </g>
            <g v-else class="pill pill-you">
              <rect class="you-hot" :x="tierX(i) + 8" :y="tierTop + 54" width="34" height="18" rx="9" />
              <rect :x="tierX(i) + 10" :y="tierTop + 56" width="30" height="14" rx="7" />
              <text :x="tierX(i) + 25" :y="tierTop + 66" text-anchor="middle">you</text>
            </g>
          </g>
        </g>

        <!-- CI -->
        <g class="panel">
          <rect class="card" :x="L.ci.x" :y="L.ci.y" :width="L.ci.w" :height="L.ci.h" rx="9" />
          <text class="head" :x="L.ci.x + 12" :y="L.ci.y + 17">ci.yml</text>
          <g class="status">
            <rect :x="L.ci.x + L.ci.w - 8 - statusW" :y="L.ci.y + 6" :width="statusW" height="16" rx="8" />
            <text :x="L.ci.x + L.ci.w - 8 - statusW / 2" :y="L.ci.y + 18" text-anchor="middle">{{ STATUS }}</text>
          </g>
          <g v-for="row in ROWS" :key="row.cls" :class="row.cls">
            <g class="check-off">
              <circle class="dot-off" :cx="L.ci.x + 16" :cy="row.y - 4" r="4" />
              <text class="check-name off" :x="L.ci.x + 28" :y="row.y">{{ row.name }}</text>
              <text class="check-when" :x="L.ci.x + L.ci.w - 10" :y="row.y" text-anchor="end">{{ row.when }}</text>
            </g>
            <g class="check">
              <g class="check-dot"><circle class="dot-on" :cx="L.ci.x + 16" :cy="row.y - 4" r="4.5" /></g>
              <text class="check-name" :x="L.ci.x + 28" :y="row.y">{{ row.name }}</text>
            </g>
          </g>
          <g v-for="(col, c) in COLUMNS" :key="col.name" :class="`col-${c}`">
            <text class="col-name" :x="colX(c)" :y="capY - 14">{{ col.name }}</text>
            <text class="col-cap" :x="colX(c)" :y="capY">{{ col.by }}</text>
            <g v-for="(r, ri) in col.rows" :key="r">
              <text class="job" :x="colX(c)" :y="rowY(ri)">{{ r }}</text>
              <g v-for="(o, os) in OSES" :key="o">
                <rect class="cell hum" :x="cellX(c, os)" :y="rowY(ri) - 11" width="15" height="14" rx="3" />
                <g class="cell-lit" :class="`cell-lit-${c}-${ri}-${os}`">
                  <rect :x="cellX(c, os)" :y="rowY(ri) - 11" width="15" height="14" rx="3" />
                  <text :x="cellX(c, os) + 7.5" :y="rowY(ri)" text-anchor="middle">{{ o }}</text>
                </g>
              </g>
            </g>
          </g>
          <g class="foot">
            <text :x="L.ci.x + 12" :y="L.ci.y + 240">L Linux · M macOS · Python 3.12</text>
            <text :x="L.ci.x + 12" :y="L.ci.y + 255">tests/system: never in CI</text>
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

.card {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.head {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.track-base {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 2;
}

.progress {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-dasharray: 8 4;
}

.stop-ring {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.6;
}

.stop-dot {
  fill: var(--hmz-lane-1);
}

.stop-dot.ci {
  fill: var(--hmz-accent);
}

.stop-word {
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.marker-glow {
  fill: var(--hmz-lane-1);
  fill-opacity: 0.22;
}

.marker-core {
  fill: var(--hmz-lane-1);
  stroke: var(--vp-c-bg);
  stroke-width: 1.5;
}

.term-line text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  white-space: pre;
  fill: var(--hmz-stage-ink);
}

.term-line.note text {
  fill: var(--hmz-stage-dim);
  font-style: italic;
}

.tier-lit {
  fill: var(--hmz-lane-1);
  fill-opacity: 0.1;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.6;
}

.tier-lit.you {
  fill: var(--hmz-warm);
  stroke: var(--hmz-warm);
}

.tier-dir {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.tier-say {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.tier-say.flag {
  fill: var(--hmz-warm);
}

.pill text {
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.pill-ci rect {
  fill: var(--hmz-accent);
}

.pill-you rect {
  fill: var(--hmz-warm);
}

.pill-you .you-hot {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2;
}


.status rect {
  fill: var(--hmz-accent);
}

.status text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: #fff;
}

.dot-off {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.2;
}

.dot-on {
  fill: var(--hmz-accent);
}

.check-name {
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.check-name.off {
  fill: var(--hmz-stage-dim);
  font-weight: 400;
}

.check-when {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.col-name {
  font-size: 11.5px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.col-cap {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.job {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.cell {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1;
  stroke-dasharray: 2 3;
}

.cell-lit rect {
  fill: var(--hmz-accent);
  fill-opacity: 0.18;
  stroke: var(--hmz-accent);
  stroke-width: 1.2;
}

.cell-lit text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.foot text {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}
</style>
