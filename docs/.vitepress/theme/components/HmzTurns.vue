<script setup lang="ts">
// Turns wait for each other only inside one session. Twelve prompts for one agent: on one
// session they run one after the other, and asking that session for a second turn while the
// first is under way is an error (`SessionError` in `src/hmz/runtime/flowing/viewing.py`; a
// backend's session holds one turn at a time, `SessionBase._lock` in
// `src/hmz/coganchor/agents/base.py`). Opened over more sessions, the same agent works on all
// of them at once, each in a place of its own, and the wall clock is what changes. Pick how
// many sessions. The minutes are made up, and fixed, so the picture is the same every time.
import { computed, nextTick, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { count, createFx, streak, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'
import { breathe } from './sway'

const MINUTES = [3.1, 1.4, 4.2, 2.0, 1.1, 3.6, 2.7, 1.8, 5.0, 2.3, 1.6, 3.3]
const FILES = ['parser.py', 'printer.py', 'cli.py', 'billing.py', 'retry.py', 'store.py', 'search.py', 'auth.py', 'jobs.py', 'cache.py', 'email.py', 'models.py']
const SERIAL = MINUTES.reduce((a, b) => a + b, 0)
// The prompt that tries to go before its turn.
const JUMPER = 8

const BEATS = ['Twelve prompts, one agent', 'One session: one turn at a time', 'More sessions, the same agent', 'Each works in a place of its own']

const width = ref(4)
const shown = ref(4)

interface Box {
  x: number
  y: number
  w: number
  h: number
}

function schedule(lanes: number) {
  const free = Array.from({ length: lanes }, () => 0)
  return MINUTES.map((m) => {
    let lane = 0
    for (let j = 1; j < free.length; j += 1) if (free[j] < free[lane]) lane = j
    const t0 = free[lane]
    free[lane] = t0 + m
    return { lane, t0, t1: t0 + m }
  })
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined
const narrow = useNarrow(() => scene.rebuild())

const G = computed(() => {
  const n = narrow.value
  const w = n ? 360 : 640
  const h = n ? 420 : 360
  const x0 = n ? 16 : 128
  const x1 = n ? 344 : 616
  const k = (x1 - x0) / SERIAL
  const orb = n ? { x: 322, y: 62, r: 17 } : { x: 66, y: 226, r: 26 }
  const cols = n ? 3 : 4
  const grid: Box[] = FILES.map((_, i) => {
    const c = i % cols
    const r = Math.floor(i / cols)
    return n
      ? { x: 16 + c * 110, y: 130 + r * 32, w: 102, h: 26 }
      : { x: x0 + c * 124, y: 100 + r * 38, w: 116, h: 28 }
  })
  const serialY = n ? 284 : 262
  const serial: Box[] = schedule(1).map((s) => ({ x: x0 + s.t0 * k, y: serialY, w: (s.t1 - s.t0) * k - 2, h: 26 }))
  const lanes = Math.max(1, width.value)
  const plan = schedule(lanes)
  const top = n ? 136 : 104
  const room = n ? 246 : 224
  const pitch = Math.min(40, room / lanes)
  const bh = Math.min(26, pitch - 5)
  const span = room - (lanes - 1) * pitch
  const y0 = top + Math.max(0, span / 2 - bh / 2)
  const laneY = Array.from({ length: lanes }, (_, j) => y0 + j * pitch)
  const wide: Box[] = plan.map((s) => ({ x: x0 + s.t0 * k, y: laneY[s.lane], w: (s.t1 - s.t0) * k - 2, h: bh }))
  const ends = laneY.map((_, j) => Math.max(0, ...plan.filter((s) => s.lane === j).map((s) => s.t1)))
  const makespan = Math.max(...ends)
  const rails = laneY.map((y) =>
    n ? '' : `M${orb.x + orb.r} ${orb.y} C${orb.x + 50} ${orb.y} ${x0 - 40} ${y + bh / 2} ${x0 - 4} ${y + bh / 2}`,
  )
  const hit = { x: serial[0].x + serial[0].w * 0.6, y: serialY }
  const bubble = Math.max(n ? 116 : 112, hit.x)
  const gain = n ? { x: 16, y: 84 } : { x: x0 + 132, y: 56 }
  return { gain, hit, bubble, n, w, h, x0, x1, k, orb, grid, serial, serialY, wide, laneY, bh, ends, makespan, rails, lanes, pitch }
})

const labelled = (b: Box) => (b.w > 62 && b.h >= 18 ? 1 : 0)
const tone = (i: number) => `var(--hmz-lane-${(i % 6) + 1})`
const min = (m: number) => `${m.toFixed(1)} min`

function set(v: number) {
  width.value = v
  void nextTick(() => scene.rebuild())
}

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const g = G.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, g.w, g.h) : undefined
    fx?.clear()
    const get = () => fx
    const one = (s: string) => q(s)[0]
    const slot = q('.tn-slot')
    const fill = q('.tn-fill')
    const name = q('.tn-name')
    const at = (b: Box, grow = true) => ({ x: b.x, y: b.y, width: grow ? b.w : 0, height: b.h })
    const text = (b: Box) => ({ x: b.x + 7, y: b.y + b.h / 2 + 4 })
    const clock = one('.tn-clock')
    const cap = one('.tn-what')
    // The words under the clock say what it adds up, and change when that does.
    const say = (words: string, t: number) => {
      tl.to(cap, { autoAlpha: 0, duration: 0.2, ease: 'power1.in' }, t)
      tl.set(cap, { text: words }, t + 0.2)
      tl.to(cap, { autoAlpha: 1, duration: 0.3, ease: 'power1.out' }, t + 0.2)
    }

    tl.set(q('.tn-world'), { autoAlpha: 1 }, 0)
    tl.set(q('.tn-p, .tn-head, .tn-rail, .tn-serial, .tn-err, .tn-place, .tn-finish, .tn-ghost, .tn-sessions, .tn-one'), { autoAlpha: 0 }, 0)
    FILES.forEach((_, i) => {
      tl.set(slot[i], { attr: at(g.grid[i]) }, 0)
      tl.set(fill[i], { attr: at(g.grid[i], false) }, 0)
      tl.set(name[i], { attr: text(g.grid[i]), opacity: 1 }, 0)
    })
    tl.set(clock, { text: min(0) }, 0)
    tl.set(cap, { text: 'wall clock', autoAlpha: 1 }, 0)
    tl.set(one('.tn-gain'), { autoAlpha: 0 }, 0)

    // 0 · one agent, and twelve prompts for it.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.tn-orb'), { scale: 0, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.8, ease: 'back.out(2)' }, 0.2)
    tl.fromTo(one('.tn-halo'), { scale: 0.4, autoAlpha: 0, transformOrigin: '50% 50%' }, { scale: 1, autoAlpha: 1, duration: 1.2 }, 0.3)
    tl.fromTo(q('.tn-p'), { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: 0.5, stagger: 0.07 }, 0.6)
    FILES.forEach((_, i) => streak(tl, get, g.orb, { x: g.grid[i].x + 10, y: g.grid[i].y + g.grid[i].h / 2 }, () => palette.lane[i % 6], 0.55 + i * 0.07, { duration: 0.5, bend: 0.15, size: 1.8 }))

    // 1 · on one session they queue: each turn begins when the last one ends, and a second
    // turn asked for while one is under way is refused.
    const T1 = 2.8
    const SW = 6.2
    const play = T1 + 1
    const when = (m: number) => play + (m / SERIAL) * SW
    tl.addLabel('beat-1', T1)
    tl.to(q('.tn-serial'), { autoAlpha: 1, duration: 0.4 }, T1)
    tl.fromTo(q('.tn-serial-rail'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.8, ease: 'cine' }, T1)
    const sched = schedule(1)
    sched.forEach((s, i) => {
      const land = Math.max(T1 + 0.3 + i * 0.06, when(s.t0) - 0.45)
      if (i === JUMPER) {
        // Too soon: the session is busy with parser.py, and says so.
        const hit = g.hit
        tl.to(slot[i], { attr: { x: hit.x - 20, y: hit.y - 36 }, duration: 0.4, ease: 'power2.in' }, play + 0.1)
        tl.to(name[i], { attr: { x: hit.x - 13, y: hit.y - 36 + 18 }, duration: 0.4, ease: 'power2.in' }, play + 0.1)
        tl.call(() => fx?.spark(hit.x, hit.y, palette.danger, 26, 130), [], play + 0.5)
        tl.fromTo(slot[i], { opacity: 1 }, { keyframes: { opacity: [1, 0.4, 1] }, duration: 0.3 }, play + 0.5)
        tl.fromTo(one('.tn-err'), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.3, ease: 'back.out(2)' }, play + 0.5)
        tl.to(one('.tn-err'), { autoAlpha: 0, duration: 0.3 }, play + 2)
        tl.to(slot[i], { attr: { x: g.grid[i].x, y: g.grid[i].y }, duration: 0.45 }, play + 0.6)
        tl.to(name[i], { attr: text(g.grid[i]), duration: 0.45 }, play + 0.6)
      }
      tl.to(slot[i], { attr: at(g.serial[i]), duration: 0.45, ease: 'cine' }, land)
      tl.to(fill[i], { attr: at(g.serial[i], false), duration: 0.45, ease: 'cine' }, land)
      tl.to(name[i], { attr: text(g.serial[i]), opacity: labelled(g.serial[i]), duration: 0.45, ease: 'cine' }, land)
      tl.to(fill[i], { attr: { width: g.serial[i].w }, duration: (MINUTES[i] / SERIAL) * SW, ease: 'none' }, Math.max(land + 0.45, when(s.t0)))
    })
    tl.fromTo(one('.tn-head'), { attr: { x1: g.x0, x2: g.x0 } }, { attr: { x1: g.x0 + SERIAL * g.k, x2: g.x0 + SERIAL * g.k }, duration: SW, ease: 'none' }, play)
    tl.to(one('.tn-head'), { autoAlpha: 1, duration: 0.2 }, play)
    count(tl, clock, 0, SERIAL, play, { duration: SW, ease: 'none', format: min })
    say(`wall clock = Σ of ${FILES.length} turns`, play - 0.3)
    tl.to(one('.tn-head'), { autoAlpha: 0, duration: 0.3 }, play + SW)

    // 2 · the same agent, more sessions: every turn flies to a lane of its own time, and the
    // wall clock falls.
    const T2 = play + SW + 0.8
    tl.addLabel('beat-2', T2)
    tl.to(q('.tn-serial'), { autoAlpha: 0, duration: 0.5 }, T2)
    tl.fromTo(one('.tn-ghost'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.6 }, T2)
    tl.to(q('.tn-rail'), { autoAlpha: 1, duration: 0.1 }, T2 + 0.1)
    tl.fromTo(q('.tn-rail'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.8, stagger: 0.04, ease: 'cine' }, T2 + 0.1)
    tl.fromTo(one('.tn-orb-core'), { scale: 1, transformOrigin: '50% 50%' }, { keyframes: { scale: [1, 1.25, 1] }, duration: 0.6 }, T2)
    tl.to(q('.tn-sessions'), { autoAlpha: 1, duration: 0.5 }, T2 + 0.3)
    FILES.forEach((_, i) => {
      const t = T2 + 0.4 + i * 0.05
      tl.to(slot[i], { attr: at(g.wide[i]), duration: 1.1, ease: 'cine' }, t)
      tl.to(fill[i], { attr: at(g.wide[i]), duration: 1.1, ease: 'cine' }, t)
      tl.to(name[i], { attr: text(g.wide[i]), opacity: labelled(g.wide[i]), duration: 1.1, ease: 'cine' }, t)
    })
    const endX = g.x0 + g.makespan * g.k
    tl.fromTo(one('.tn-finish'), { autoAlpha: 0, attr: { x1: g.x0 + SERIAL * g.k - 2, x2: g.x0 + SERIAL * g.k - 2 } }, { autoAlpha: 1, attr: { x1: endX, x2: endX }, duration: 1.6, ease: 'cine' }, T2 + 0.5)
    count(tl, clock, SERIAL, g.makespan, T2 + 0.5, { duration: 1.6, ease: 'cine', format: min })
    say(`wall clock = max of ${g.lanes} sessions`, T2 + 0.3)
    tl.fromTo(one('.tn-gain'), { autoAlpha: 0, x: -8 }, { autoAlpha: 1, x: 0, duration: 0.5, ease: 'cine.out' }, T2 + 2.1)
    tl.call(() => fx?.spark(endX, g.laneY[0], palette.accent, 22, 110), [], T2 + 2.1)

    // 3 · each session works in a place of its own.
    const T3 = T2 + 3
    tl.addLabel('beat-3', T3)
    g.ends.forEach((m, j) => {
      const t = T3 + j * 0.08
      const place = q('.tn-place')[j]
      tl.fromTo(place, { autoAlpha: 0, x: -10 }, { autoAlpha: 1, x: 0, duration: 0.45 }, t)
      streak(tl, get, { x: g.x0 + m * g.k, y: g.laneY[j] + g.bh / 2 }, { x: endX + 14, y: g.laneY[j] + g.bh / 2 }, () => palette.lane[j % 6], t, { duration: 0.3, bend: 0, burst: 6, size: 1.6 })
    })
    tl.fromTo(q('.tn-one'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, T3 + 0.6)
    tl.addLabel('rest', T3 + 1.6)
    breathe(tl, one('.tn-halo'), 1.6, T3 + 4.4, { period: 2.2, opacity: 0.55, scale: 1.08 })
    tl.to(q('.tn-world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T3 + 4.4)
  },
})
</script>

<template>
  <div class="hmz-turns">
    <label class="control">
      <span>sessions at once</span>
      <input type="range" min="2" max="12" step="1" :value="width" aria-label="How many sessions at once" @change="set(Number(($event.target as HTMLInputElement).value))" @input="shown = Number(($event.target as HTMLInputElement).value)" />
      <b>{{ shown }}</b>
    </label>
    <HmzStage
      :scene="scene"
      :beats="BEATS"
      sim
      mobile-ratio="6 / 7"
      :label="`Twelve prompts for one agent. On one session they run one after another, ${SERIAL.toFixed(1)} minutes in all, and asking it for a second turn while one is under way raises SessionError: a turn of this session is under way. Over ${G.lanes} sessions the same agent runs them at once and the wall clock falls to ${G.makespan.toFixed(1)} minutes, the longest of the sessions rather than the sum of the turns, ${(SERIAL / G.makespan).toFixed(1)} times sooner for the same work, each session working in a worktree of its own.`"
    >
      <svg :viewBox="`0 0 ${G.w} ${G.h}`" aria-hidden="true">
        <defs>
          <radialGradient id="hmz-turns-halo">
            <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.55" />
            <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
          </radialGradient>
        </defs>
        <g class="tn-world">
          <g class="tn-clock-box">
            <text class="tn-clock" :x="G.n ? 16 : G.x0" :y="G.n ? 46 : 58">0.0 min</text>
            <text class="tn-cap tn-what" :x="G.n ? 16 : G.x0" :y="G.n ? 64 : 78">wall clock</text>
            <!-- moved as a group: a transform on a word itself fights the stage's lift of it -->
            <g class="tn-gain"><text :x="G.gain.x" :y="G.gain.y">{{ (SERIAL / G.makespan).toFixed(1) }}× sooner, the same work</text></g>
          </g>

          <circle class="tn-halo" :cx="G.orb.x" :cy="G.orb.y" :r="G.orb.r * 3" fill="url(#hmz-turns-halo)" />
          <g class="tn-orb">
            <circle class="tn-orb-ring" :cx="G.orb.x" :cy="G.orb.y" :r="G.orb.r" />
            <circle class="tn-orb-core" :cx="G.orb.x" :cy="G.orb.y" :r="G.orb.r * 0.45" />
          </g>
          <text class="tn-orb-name" :x="G.n ? 344 : G.orb.x" :y="G.orb.y + G.orb.r + 18" :text-anchor="G.n ? 'end' : 'middle'">one agent</text>
          <text v-if="G.n" class="tn-one tn-cap" x="344" :y="G.orb.y + G.orb.r + 34" text-anchor="end">one CLI · one model</text>
          <text v-else class="tn-one tn-cap" :x="G.orb.x" :y="G.orb.y + G.orb.r + 34" text-anchor="middle">
            <tspan :x="G.orb.x">one CLI</tspan>
            <tspan :x="G.orb.x" dy="14">one model</tspan>
          </text>

          <g class="tn-serial">
            <path v-if="!G.n" class="tn-serial-rail tn-line" :d="`M${G.orb.x + G.orb.r} ${G.orb.y} C${G.orb.x + 50} ${G.orb.y} ${G.x0 - 40} ${G.serialY + 13} ${G.x0 - 4} ${G.serialY + 13}`" />
            <line class="tn-serial-rail tn-track" :x1="G.x0" :x2="G.x1" :y1="G.serialY + 13" :y2="G.serialY + 13" />
            <text class="tn-cap tn-lane-name" :x="G.x0" :y="G.serialY - 10">one session</text>
          </g>
          <path v-for="(d, j) in G.rails" v-show="d" :key="`r${j}`" class="tn-rail tn-line" :d="d" :style="{ stroke: tone(j) }" />
          <text class="tn-sessions tn-cap tn-lane-name" :x="G.x0" :y="G.laneY[0] - 10">{{ G.lanes }} sessions</text>

          <g class="tn-ghost">
            <line class="tn-ghost-line" :x1="G.x0 + SERIAL * G.k - 2" :x2="G.x0 + SERIAL * G.k - 2" :y1="G.n ? 124 : 92" :y2="G.n ? 392 : 336" />
            <text class="tn-cap" :x="G.x0 + SERIAL * G.k - 6" :y="G.n ? 404 : 350" text-anchor="end">{{ SERIAL.toFixed(1) }} min, one after another</text>
          </g>

          <g v-for="(f, i) in FILES" :key="f" class="tn-p">
            <rect class="tn-slot" rx="6" :x="G.grid[i].x" :y="G.grid[i].y" :width="G.grid[i].w" :height="G.grid[i].h" :style="{ '--tone': tone(i) }" />
            <rect class="tn-fill" rx="6" :x="G.grid[i].x" :y="G.grid[i].y" width="0" :height="G.grid[i].h" :style="{ fill: tone(i) }" />
            <text class="tn-name" :x="G.grid[i].x + 7" :y="G.grid[i].y + G.grid[i].h / 2 + 4">{{ f }}</text>
          </g>

          <line class="tn-head" :x1="G.x0" :x2="G.x0" :y1="G.serialY - 6" :y2="G.serialY + 32" />
          <line class="tn-finish" :x1="G.x0 + SERIAL * G.k - 2" :x2="G.x0 + SERIAL * G.k - 2" :y1="G.n ? 108 : 92" :y2="G.n ? 392 : 336" />

          <g :transform="`translate(${G.bubble} ${G.serialY + 50})`"><g class="tn-err">
            <rect x="-108" y="-19" width="216" height="38" rx="10" />
            <text class="tn-err-kind" y="-3" text-anchor="middle">SessionError</text>
            <text y="12" text-anchor="middle">a turn of this session is under way</text>
          </g></g>

          <g v-for="(m, j) in G.ends" :key="`p${j}`" :transform="`translate(${G.x0 + G.makespan * G.k + 10} ${G.laneY[j] + G.bh / 2})`"><g class="tn-place">
            <path class="tn-branch" :style="{ stroke: tone(j) }" d="M2 -6 V6 M2 -1 C2 -4 10 -3 10 -7" />
            <circle class="tn-branch-dot" cx="10" cy="-7" r="2" :style="{ fill: tone(j) }" />
            <text v-if="G.pitch >= 20" class="tn-place-name" x="16" y="4">worktree</text>
          </g></g>
        </g>
      </svg>
      <canvas ref="canvas" />
    </HmzStage>
  </div>
</template>

<style scoped>
.control {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 22px 0 0;
  font-size: 12.5px;
  color: var(--vp-c-text-2);
}

.control input {
  width: 160px;
  accent-color: var(--vp-c-brand-1);
}

.control b {
  font-family: var(--vp-font-family-mono);
  font-variant-numeric: tabular-nums;
  color: var(--vp-c-text-1);
}

.hmz-turns > .hmz-stage {
  margin-top: 10px;
}

svg {
  font-family: var(--vp-font-family-base);
}

.tn-clock {
  font-family: var(--vp-font-family-mono);
  font-size: 24px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  fill: var(--hmz-stage-ink);
}

.tn-cap {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  fill: var(--hmz-stage-dim);
}

.tn-lane-name {
  text-transform: uppercase;
}

.tn-halo {
  opacity: var(--hmz-glow);
}

.tn-orb-ring {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.tn-orb-core {
  fill: var(--hmz-accent);
}

.tn-orb-name {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.tn-line {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
  opacity: 0.75;
}

.tn-track {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.5;
}

.tn-slot {
  fill: var(--hmz-stage-card);
  stroke: var(--tone);
  stroke-width: 1.3;
}

.tn-fill {
  opacity: 0.85;
}

.tn-name {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
  pointer-events: none;
}

.tn-head {
  stroke: var(--hmz-stage-ink);
  stroke-width: 2;
  opacity: 0;
}

.tn-finish {
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.tn-ghost-line {
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.2;
  stroke-dasharray: 4 4;
}

.tn-err rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-5);
  stroke-width: 1.5;
}

.tn-err text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.tn-err .tn-err-kind {
  font-weight: 700;
  fill: var(--hmz-lane-5);
}

.tn-gain text {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.tn-branch {
  fill: none;
  stroke-width: 1.8;
  stroke-linecap: round;
}

.tn-place-name {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}
</style>
