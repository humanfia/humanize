<script setup lang="ts">
// A change's way from a clone to `main`. Along the top, the stops; left, the terminal they are
// typed into, with what each says back; under it, the three tiers of tests by what is on the
// other side of them; right, what CI runs as the change gets closer to `main`.
//
// Drawn from docs/contributing/index.md (set up, the checks, the table of what runs where, the
// tiers) and docs/contributing/ci.md with .github/workflows/ci.yml: a push runs the hooks
// (`lint`) and `unit`; a pull request adds `typecheck` (pyright), `workflows` (actionlint and
// zizmor) and `integration`; on the way to `main` `system` runs too, on Linux and Python 3.12
// with no coding agent CLI, and `unit` and `integration` run on Linux and macOS for Python
// 3.12, 3.13 and 3.14. The unit run's count and time are the page's own.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { count, createFx, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'Clone, then uv sync: Python and all, pinned',
  'Hooks in, an edit, and the fast loop',
  'Before you push: every hook, every tier',
  'A push runs the hooks and the unit tier',
  'A pull request adds pyright and integration',
  'On the way to main: system, two OSes, 3 Pythons',
]

const STOPS = ['clone', 'uv sync', 'hooks', 'edit', 'fast loop', 'before push', 'push', 'CI']

type Kind = 'cmd' | 'note' | 'out'
const TERM: { kind: Kind; text: string }[] = [
  { kind: 'cmd', text: '$ git clone …github.com/humanfia/humanize.git' },
  { kind: 'cmd', text: '$ uv sync' },
  { kind: 'note', text: '# .venv, as uv.lock pins it, Python included' },
  { kind: 'cmd', text: '$ uv run pre-commit install' },
  { kind: 'note', text: '# checks each commit with the hooks CI runs' },
  { kind: 'note', text: '# edit: a change and its tests, one commit' },
  { kind: 'cmd', text: '$ uv run pytest tests/unit' },
  { kind: 'out', text: '2405 passed in 15.51s' },
  { kind: 'cmd', text: '$ uv run pre-commit run --all-files' },
  { kind: 'note', text: '# format, lint, types: seconds' },
  { kind: 'cmd', text: '$ uv run pytest' },
  { kind: 'note', text: '# every tier: minutes' },
  { kind: 'cmd', text: '$ git push' },
]
/** How many lines the terminal scrolls by before you push: it shows eight at once. */
const SCROLL = 5
const LH = 15

const TIERS = [
  { dir: 'unit/', say: ['talks to hmz,', 'and nothing else'], you: false },
  { dir: 'integration/', say: ['stand-ins this', 'repo wrote'], you: false },
  { dir: 'system/', say: ['the real thing,', '--run-agents'], you: true },
]

const CHECKS = [
  { name: 'hooks', when: 'every push' },
  { name: 'pyright', when: 'from a PR on' },
  { name: 'workflow linters', when: 'from a PR on' },
  { name: 'unit', when: 'every push' },
  { name: 'integration', when: 'every PR' },
  { name: 'system', when: 'to main' },
]
const PYTHONS = ['3.12', '3.13', '3.14']
const OSES = ['Linux', 'macOS']
/** What runs in each cell of the full tier: system on Linux and 3.12 alone. */
const cell = (os: number, py: number) => (os === 0 && py === 0 ? 'u·i·s' : 'u·i')

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
  cellW: number
  cellX: number
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
  cellW: 50,
  cellX: 62,
  open: { x: 200, y: 140, s: 1.32 },
  ciShot: { x: 420, y: 200, s: 1.12 },
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
  cellW: 70,
  cellX: 90,
  open: { x: 180, y: 190, s: 1.22 },
  ciShot: { x: 180, y: 500, s: 1.1 },
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
const checkY = (i: number) => L.value.ci.y + 42 + i * 18
const gridY = (os: number) => L.value.ci.y + 174 + os * 26
const cellX = (py: number) => L.value.ci.x + L.value.cellX + py * (L.value.cellW + 5)

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
    const check = (i: number, when: number) => {
      tl.to(at('.check')[i], { opacity: 1, duration: 0.3 }, when)
      tl.to(at('.check-off .check-name')[i], { opacity: 0, duration: 0.3 }, when)
      tl.fromTo(at('.check-dot')[i], { scale: 0.3, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.4, ease: 'back.out(3)', immediateRender: false }, when)
      cam.flare({ x: l.ci.x + 16, y: checkY(i) - 4 }, ok, when, 8, 50)
    }
    const status = (i: number, when: number) => {
      tl.to(at('.status'), { opacity: 0, duration: 0.25 }, when)
      tl.fromTo(at('.status')[i], { opacity: 0, y: 4 }, { opacity: 1, y: 0, duration: 0.4, immediateRender: false }, when + 0.2)
    }
    /** The right end of a line once the terminal has scrolled. */
    const termOut = (i: number) => ({ x: l.term.x + l.term.w - 10, y: termY(i - SCROLL) - 4 })

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.term-line, .stop-dot, .tier-lit, .you-hot, .check, .status, .cell-lit, .grid-word, .foot'), { opacity: 0 }, 0)
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

    // 1 · the hooks, an edit, and the unit tier as the loop you write in.
    const T1 = 4.4
    tl.addLabel('beat-1', T1)
    stop(2, T1)
    say(3, T1 + 0.2)
    say(4, T1 + 1)
    stop(3, T1 + 1.6)
    say(5, T1 + 1.9)
    stop(4, T1 + 2.6)
    say(6, T1 + 2.8)
    tl.set(at('.term-line')[7], { opacity: 1 }, T1 + 3.5)
    count(tl, one('.passed'), 0, 2405, T1 + 3.5, { duration: 1, format: (n) => String(Math.round(n)) })
    cam.flare({ x: l.term.x + 70, y: termY(7) - 4 }, ok, T1 + 4.5, 20)

    // 2 · before the push: every hook, then every tier, by what is on the other side of it.
    const T2 = T1 + 5.4
    tl.addLabel('beat-2', T2)
    stop(5, T2)
    tl.to(one('.scroll'), { y: -SCROLL * LH, duration: 0.6, ease: 'cine' }, T2 + 0.1)
    const t8 = say(8, T2 + 0.7)
    say(9, t8 + 0.15)
    const t10 = say(10, t8 + 0.7)
    say(11, t10 + 0.15)
    TIERS.forEach((_, i) => {
      cam.beam({ x: l.term.x + 120, y: termY(10 - SCROLL) - 4 }, { x: tierX(i) + tierW.value / 2, y: tierTop.value + 2 }, i === 2 ? warm : lane1, t10 + 0.3 + i * 0.25, { duration: 0.6, bend: 0.15 })
      tl.to(at('.tier-lit')[i], { opacity: 1, duration: 0.35 }, t10 + 0.85 + i * 0.25)
    })
    tl.fromTo(one('.you-hot'), { opacity: 0 }, { opacity: 1, duration: 0.3, yoyo: true, repeat: 3, immediateRender: false }, t10 + 1.5)

    // 3 · the push, and the push tier: the hooks and unit, on Linux and 3.12.
    const T3 = T2 + 5
    tl.addLabel('beat-3', T3)
    stop(6, T3)
    const t12 = say(12, T3 + 0.2)
    cam.shot(l.ciShot, T3 + 0.2, 1.6)
    stop(7, t12 + 0.3)
    cam.beam(termOut(12), { x: l.ci.x + 12, y: l.ci.y + 14 }, lane1, t12 + 0.2, { duration: 0.7, bend: -0.2 })
    status(0, t12 + 0.9)
    check(0, t12 + 1.2)
    check(3, t12 + 1.5)

    // 4 · a pull request: pyright, the workflow linters, integration.
    const T4 = T3 + 3
    tl.addLabel('beat-4', T4)
    status(1, T4)
    check(1, T4 + 0.4)
    check(2, T4 + 0.7)
    check(4, T4 + 1)

    // 5 · on the way to main: system, and the tiers on two systems and three Pythons.
    const T5 = T4 + 2.2
    tl.addLabel('beat-5', T5)
    check(5, T5 + 0.2)
    tl.to(at('.grid-word'), { opacity: 1, duration: 0.4 }, T5 + 0.4)
    OSES.forEach((_, os) =>
      PYTHONS.forEach((__, py) => {
        const t = T5 + 0.8 + (os + py) * 0.22
        tl.to(at(`.cell-lit-${os}-${py}`), { opacity: 1, duration: 0.3 }, t)
        cam.flare({ x: cellX(py) + l.cellW / 2, y: gridY(os) + 11 }, ok, t, 10, 60)
      }),
    )
    tl.to(one('.foot'), { opacity: 1, duration: 0.4 }, T5 + 2)
    status(2, T5 + 2.2)
    cam.flare({ x: l.ci.x + l.ci.w - 30, y: l.ci.y + 13 }, ok, T5 + 2.5, 24)
    cam.shot(l.whole, T5 + 2.2, 1.6)

    tl.addLabel('rest', T5 + 4)
    cam.shot({ ...l.whole, s: l.whole.s * 1.025 }, T5 + 3.9, 2.6, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T5 + 6.6)

    // The empty cells of the matrix hum while they wait: a slow march of their dashes.
    tl.fromTo(at('.hum'), { strokeDashoffset: 0 }, { strokeDashoffset: -40, duration: tl.duration(), ease: 'none' }, 0)
  },
})

const statusW = (s: string) => Math.round(s.length * 6.6 + 16)
const STATUS = ['ci-ok (push tier)', 'ci-ok (pr tier)', 'ci-ok']
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 17"
    label="A change's way from a clone to main. git clone; uv sync makes .venv exactly as uv.lock pins it, Python included; uv run pre-commit install checks each commit with the hooks CI runs. You edit, a change and its tests in one commit, and run the fast loop, uv run pytest tests/unit: 2405 passed in 15.51s. Before you push: uv run pre-commit run --all-files, seconds, and uv run pytest, every tier, minutes. The tiers are by what is on the other side: unit talks to hmz and nothing else; integration to stand-ins this repository wrote; system to the real thing, and the tests that drive real CLIs wait for --run-agents and are yours to run. Then git push. CI runs the hooks and unit on every push, adds pyright, the workflow linters and integration from a pull request on, and on the way to main adds system, on Linux with no coding agent CLI, and runs unit and integration on Linux and macOS for Python 3.12, 3.13 and 3.14, reporting ci-ok."
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
                <text v-if="t.kind === 'out'" :x="L.term.x + 12" :y="termY(i)"><tspan class="passed">2405</tspan> passed in 15.51s</text>
                <text v-else :x="L.term.x + 12" :y="termY(i)">{{ t.text }}</text>
              </g>
            </g>
          </g>
        </g>

        <!-- the tiers, by what is on the other side -->
        <g class="panel">
          <g v-for="(t, i) in TIERS" :key="t.dir">
            <rect class="card" :x="tierX(i)" :y="tierTop" :width="tierW" :height="L.tiers.h - 4" rx="8" />
            <rect class="tier-lit" :class="{ you: t.you }" :x="tierX(i)" :y="tierTop" :width="tierW" :height="L.tiers.h - 4" rx="8" />
            <text class="tier-dir" :x="tierX(i) + 10" :y="tierTop + 17">{{ t.dir }}</text>
            <text class="tier-say" :x="tierX(i) + 10" :y="tierTop + 34">{{ t.say[0] }}</text>
            <text class="tier-say" :class="{ flag: t.you }" :x="tierX(i) + 10" :y="tierTop + 49">{{ t.say[1] }}</text>
            <g class="pill pill-ci">
              <rect :x="tierX(i) + 10" :y="tierTop + 56" width="26" height="14" rx="7" />
              <text :x="tierX(i) + 23" :y="tierTop + 66" text-anchor="middle">CI</text>
            </g>
            <g v-if="t.you" class="pill pill-you">
              <rect class="you-hot" :x="tierX(i) + 38" :y="tierTop + 54" width="34" height="18" rx="9" />
              <rect :x="tierX(i) + 40" :y="tierTop + 56" width="30" height="14" rx="7" />
              <text :x="tierX(i) + 55" :y="tierTop + 66" text-anchor="middle">you</text>
            </g>
          </g>
        </g>

        <!-- CI -->
        <g class="panel">
          <rect class="card" :x="L.ci.x" :y="L.ci.y" :width="L.ci.w" :height="L.ci.h" rx="9" />
          <text class="head" :x="L.ci.x + 12" :y="L.ci.y + 17">ci.yml</text>
          <g v-for="(s, i) in STATUS" :key="s" class="status" :class="{ full: i === 2 }">
            <rect :x="L.ci.x + L.ci.w - 8 - statusW(s)" :y="L.ci.y + 6" :width="statusW(s)" height="16" rx="8" />
            <text :x="L.ci.x + L.ci.w - 8 - statusW(s) / 2" :y="L.ci.y + 18" text-anchor="middle">{{ s }}</text>
          </g>
          <g v-for="(c, i) in CHECKS" :key="c.name">
            <g class="check-off">
              <circle class="dot-off" :cx="L.ci.x + 16" :cy="checkY(i) - 4" r="4" />
              <text class="check-name off" :x="L.ci.x + 28" :y="checkY(i)">{{ c.name }}</text>
              <text class="check-when" :x="L.ci.x + L.ci.w - 10" :y="checkY(i)" text-anchor="end">{{ c.when }}</text>
            </g>
            <g class="check">
              <g class="check-dot"><circle class="dot-on" :cx="L.ci.x + 16" :cy="checkY(i) - 4" r="4.5" /></g>
              <text class="check-name" :x="L.ci.x + 28" :y="checkY(i)">{{ c.name }}</text>
            </g>
          </g>
          <g class="grid-word">
            <text class="grid-cap" :x="L.ci.x + 12" :y="L.ci.y + 154">on the way to main</text>
            <text v-for="(p, py) in PYTHONS" :key="p" class="grid-head" :x="cellX(py) + L.cellW / 2" :y="L.ci.y + 168" text-anchor="middle">{{ p }}</text>
          </g>
          <g v-for="(o, os) in OSES" :key="o">
            <text class="grid-os" :x="L.ci.x + 12" :y="gridY(os) + 15">{{ o }}</text>
            <g v-for="(p, py) in PYTHONS" :key="p">
              <rect class="cell hum" :x="cellX(py)" :y="gridY(os)" :width="L.cellW" height="22" rx="4" />
              <g class="cell-lit" :class="`cell-lit-${os}-${py}`">
                <rect :x="cellX(py)" :y="gridY(os)" :width="L.cellW" height="22" rx="4" />
                <text :x="cellX(py) + L.cellW / 2" :y="gridY(os) + 15" text-anchor="middle">{{ cell(os, py) }}</text>
              </g>
            </g>
          </g>
          <g class="foot">
            <text :x="L.ci.x + 12" :y="L.ci.y + 240">u unit · i integration · s system</text>
            <text :x="L.ci.x + 12" :y="L.ci.y + 255">system: Linux, 3.12, no CLIs</text>
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

.term-line.out text {
  fill: var(--hmz-accent);
  font-weight: 700;
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
  font-family: var(--vp-font-family-mono);
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
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.2;
}

.status text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-lane-1);
}

.status.full rect {
  fill: var(--hmz-accent);
  stroke: var(--hmz-accent);
}

.status.full text {
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

.grid-cap {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.grid-head,
.grid-os {
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
