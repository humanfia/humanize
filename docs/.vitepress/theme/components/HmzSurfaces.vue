<script setup lang="ts">
// Three ways into humanize -- the terminal interface, the command line and Python -- over one
// workspace: the same flows (this project's first, then yours, then the flowverses), the same
// accounts, and one history of runs whichever way a run was started. A run started from the
// command line is in the terminal interface's list of runs. A flow's settings are one model, so
// a bad value is refused the same way everywhere, before any agent starts. The picker lights
// the ways in that do a thing; each answer is what that way in does (`src/hmz/tui/`,
// `src/hmz/cli/`, `src/hmz/sdk/`).
import { computed, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, streak, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'

const BEATS = [
  'Three ways in',
  'The same flows, the same accounts',
  'Every run lands in one history',
  'Start it in one, open it in another',
  'A bad value is refused everywhere',
]

type Door = 0 | 1 | 2
const DOORS = [
  { name: 'terminal interface', lane: 1 },
  { name: 'command line', lane: 4 },
  { name: 'Python', lane: 3 },
]
const NODES = ['flows', 'accounts', 'history']

const WANTS: { said: string; doors: Door[] }[] = [
  { said: 'watch it and steer it', doors: [0] },
  { said: 'answer its questions', doors: [0, 2] },
  { said: 'walk away and come back', doors: [0, 2] },
  { said: 'run it from CI', doors: [1] },
  { said: 'read its events in a program', doors: [1, 2] },
  { said: 'build a tool on it', doors: [2] },
  { said: 'look after a run left going', doors: [2] },
]
const want = ref<number | null>(null)
const lit = (door: number) => want.value === null || WANTS[want.value].doors.includes(door as Door)

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Layout {
  w: number
  h: number
  wins: Box[]
  core: Box
  nodes: Box[]
  vertical: boolean
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  wins: [
    { x: 30, y: 30, w: 176, h: 108 },
    { x: 232, y: 30, w: 176, h: 108 },
    { x: 434, y: 30, w: 176, h: 108 },
  ],
  core: { x: 30, y: 188, w: 580, h: 146 },
  nodes: [
    { x: 58, y: 222, w: 148, h: 96 },
    { x: 246, y: 222, w: 148, h: 96 },
    { x: 434, y: 222, w: 148, h: 96 },
  ],
  vertical: false,
}

const NARROW: Layout = {
  w: 360,
  h: 440,
  wins: [
    { x: 14, y: 26, w: 172, h: 108 },
    { x: 14, y: 160, w: 172, h: 108 },
    { x: 14, y: 294, w: 172, h: 108 },
  ],
  core: { x: 206, y: 14, w: 142, h: 400 },
  nodes: [
    { x: 216, y: 44, w: 122, h: 96 },
    { x: 216, y: 164, w: 122, h: 96 },
    { x: 216, y: 284, w: 122, h: 110 },
  ],
  vertical: true,
}

// The runs that land in the history, by the way in that started them, oldest first.
const RUNS: Door[] = [0, 1, 2, 1]
const PILL = { h: 10, gap: 4 }

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const wires = computed(() => {
  const l = L.value
  return l.wins.map((b) => {
    if (l.vertical) {
      const y = b.y + b.h / 2
      return `M${b.x + b.w + 3} ${y} L${l.core.x - 3} ${y}`
    }
    const x = b.x + b.w / 2
    return `M${x} ${b.y + b.h + 3} L${x} ${l.core.y - 3}`
  })
})

const pills = computed(() => {
  const n = L.value.nodes[2]
  return RUNS.map((door, k) => ({
    door,
    x: n.x + 12,
    y: n.y + n.h - 10 - (k + 1) * (PILL.h + PILL.gap),
    w: n.w - 24,
  }))
})

const label =
  'Three ways in -- the terminal interface, the command line and Python -- over one workspace. All three read the same flows and the same accounts, and every run, whichever way it was started, lands in one history. A run started from the command line opens in the terminal interface. A bad value is refused the same way by all three, before any agent starts.'

const scene = useScene({
  still: 'rest',
  repeatDelay: 0.8,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const get = () => fx
    const one = (sel: string) => q(sel)[0]
    const W = l.w
    const H = l.h
    const shot = (s: number, px: number, py: number) => ({
      scale: s,
      xPercent: ((W / 2 - s * px) / W) * 100,
      yPercent: ((H / 2 - s * py) / H) * 100,
      transformOrigin: '0% 0%',
    })
    const cam = one('.cam')
    const win = q('.win')
    const node = q('.node')
    const pill = q('.pill')
    const c = (b: Box) => ({ x: b.x + b.w / 2, y: b.y + b.h / 2 })
    const out = (i: number) => (l.vertical ? { x: l.wins[i].x + l.wins[i].w, y: c(l.wins[i]).y } : { x: c(l.wins[i]).x, y: l.wins[i].y + l.wins[i].h })
    const lane = (i: number) => () => palette.lane[DOORS[i].lane - 1]

    tl.set(cam, { autoAlpha: 1, ...shot(1.35, c(l.wins[0]).x, c(l.wins[0]).y + 10) }, 0)
    tl.set(win, { autoAlpha: 0, y: 24, scale: 0.9, transformOrigin: '50% 50%' }, 0)
    tl.set(q('.core-frame'), { drawSVG: '0%', autoAlpha: 0 }, 0)
    tl.set(q('.wire'), { drawSVG: '0%' }, 0)
    tl.set(q('.core-name, .node, .ghost, .bad, .deny, .open-row, .live'), { autoAlpha: 0 }, 0)
    tl.set(pill, { autoAlpha: 0 }, 0)
    tl.set(q('.cursor'), { autoAlpha: 1 }, 0)

    // ---------------------------------------------------------------- 0 · three ways in
    tl.addLabel('beat-0', 0)
    win.forEach((w, i) => {
      tl.to(w, { autoAlpha: 1, y: 0, scale: 1, duration: 0.9, ease: 'cine.out' }, 0.2 + i * 0.55)
      tl.fromTo(q(`.win-${i} .ink`), { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 0.4, stagger: 0.06, ease: 'cine.out' }, 0.5 + i * 0.55)
    })
    // A dolly across the three, then back to see them all.
    tl.to(cam, { ...shot(1.35, c(l.wins[2]).x, c(l.wins[2]).y + 10), duration: 1.6, ease: 'cine' }, 0.3)
    tl.to(cam, { ...shot(1, W / 2, H / 2), duration: 1.3, ease: 'cine' }, 2)
    tl.to(q('.cursor'), { autoAlpha: 0, duration: 0.3, repeat: 7, yoyo: true, ease: 'steps(1)' }, 0.8)

    // ---------------------------------------------------------------- 1 · same flows, same accounts
    const T1 = 3.4
    tl.addLabel('beat-1', T1)
    tl.to(q('.core-frame'), { drawSVG: '100%', autoAlpha: 1, duration: 1, ease: 'cine' }, T1)
    tl.to(one('.core-name'), { autoAlpha: 1, duration: 0.4 }, T1 + 0.4)
    tl.to(q('.wire'), { drawSVG: '100%', duration: 0.5, stagger: 0.1, ease: 'cine' }, T1 + 0.3)
    tl.fromTo(node, { autoAlpha: 0, scale: 0.85, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.55, stagger: 0.12, ease: 'back.out(1.6)' }, T1 + 0.6)
    ;[0, 1, 2].forEach((i) => {
      ;[0, 1].forEach((n) => {
        streak(tl, get, out(i), c(l.nodes[n]), lane(i), T1 + 1.3 + i * 0.12 + n * 0.25, { duration: 0.8, bend: (i - n) * 0.12 + 0.05, burst: 6 })
      })
    })
    tl.fromTo(q('.node-0 .bg, .node-1 .bg'), { opacity: 1 }, { keyframes: { opacity: [1, 0.5, 1] }, duration: 0.5, ease: 'none', immediateRender: false }, T1 + 2.2)
    tl.call(() => {
      ;[0, 1].forEach((n) => fx?.spark(c(l.nodes[n]).x, c(l.nodes[n]).y, palette.accent, 18, 90))
    }, [], T1 + 2.2)

    // ---------------------------------------------------------------- 2 · one history
    const T2 = T1 + 3
    tl.addLabel('beat-2', T2)
    const P = pills.value
    P.forEach((p, k) => {
      const from = out(p.door)
      const at = T2 + 0.2 + k * 0.45
      tl.fromTo(
        pill[k],
        { autoAlpha: 0, x: from.x - (p.x + p.w / 2), y: from.y - (p.y + PILL.h / 2), scale: 0.5, transformOrigin: '50% 50%' },
        { autoAlpha: 1, x: 0, y: 0, scale: 1, duration: 0.8, ease: 'cine' },
        at,
      )
      streak(tl, get, from, { x: p.x + p.w / 2, y: p.y + PILL.h / 2 }, lane(p.door), at, { duration: 0.8, bend: 0.15, burst: 8 })
      tl.fromTo(win[p.door], { scale: 1 }, { scale: 1.03, duration: 0.15, yoyo: true, repeat: 1, ease: 'power2.out', immediateRender: false }, at)
    })

    // ---------------------------------------------------------------- 3 · open it elsewhere
    const T3 = T2 + 0.4 + P.length * 0.45 + 0.8
    tl.addLabel('beat-3', T3)
    const src = P[3]
    const w0 = l.wins[0]
    const row = { x: w0.x + 12, y: w0.y + 44 }
    tl.to(cam, { ...shot(l.vertical ? 1.12 : 1.15, (c(w0).x + src.x + src.w / 2) / 2 - (l.vertical ? 0 : 40), (c(w0).y + src.y) / 2), duration: 1.3, ease: 'cine' }, T3)
    tl.to(pill[3], { scale: 1.12, duration: 0.25, yoyo: true, repeat: 1, transformOrigin: '50% 50%' }, T3 + 0.4)
    const ghost = one('.ghost')
    tl.fromTo(
      ghost,
      { autoAlpha: 1, x: src.x - row.x, y: src.y - row.y, scaleX: 1 },
      { x: 0, y: 0, duration: 1.1, ease: 'cine' },
      T3 + 0.8,
    )
    streak(tl, get, { x: src.x + src.w / 2, y: src.y }, { x: row.x + 20, y: row.y + 5 }, lane(1), T3 + 0.8, { duration: 1.1, bend: 0.2, burst: 16 })
    tl.to(ghost, { autoAlpha: 0, duration: 0.2 }, T3 + 1.9)
    tl.to(one('.open-row'), { autoAlpha: 1, duration: 0.2 }, T3 + 1.85)
    tl.to(q('.win-0 .talk'), { autoAlpha: 0, duration: 0.2 }, T3 + 1.9)
    tl.fromTo(q('.live'), { autoAlpha: 0, scaleX: 0, transformOrigin: (i: number) => (i % 2 ? '100% 50%' : '0% 50%') }, { autoAlpha: 1, scaleX: 1, duration: 0.35, stagger: 0.35, ease: 'cine.out' }, T3 + 2.1)

    // ---------------------------------------------------------------- 4 · refused everywhere
    const T4 = T3 + 3.6
    tl.addLabel('beat-4', T4)
    tl.to(cam, { ...shot(1, W / 2, H / 2), duration: 1.2, ease: 'cine' }, T4)
    const bad = q('.bad')
    bad.forEach((b, i) => {
      const w = l.wins[i]
      const hit = { x: c(w).x, y: c(w).y + 8 }
      const start = l.vertical ? { x: -60, y: hit.y - 20 } : { x: hit.x, y: -30 }
      const back = { x: hit.x + (i % 2 ? -10 : 10), y: hit.y - 10 }
      const at = T4 + 0.9
      tl.fromTo(b, { autoAlpha: 0, x: start.x, y: start.y, rotation: 0 }, { autoAlpha: 1, duration: 0.25 }, at)
      tl.to(b, { x: hit.x, y: hit.y, duration: 0.5, ease: 'power3.in' }, at + 0.1)
      tl.to(b, { x: back.x, y: back.y, rotation: i % 2 ? -9 : 9, duration: 0.55, ease: 'power3.out' }, at + 0.6)
      tl.fromTo(q('.deny')[i], { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.08 }, at + 0.6)
      tl.to(q('.deny')[i], { autoAlpha: 0, duration: 0.9 }, at + 0.75)
      tl.call(() => fx?.spark(hit.x, hit.y, palette.danger, 24, 120), [], at + 0.6)
      tl.fromTo(q('.bad-x')[i], { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.25 }, at + 0.8)
    })
    tl.addLabel('rest', T4 + 2.4)
    tl.to(cam, { autoAlpha: 0, ...shot(0.95, W / 2, H / 2), duration: 0.8, ease: 'power2.in' }, T4 + 4)
  },
})
</script>

<template>
  <div class="hmz-surfaces">
    <div class="pick" role="group" aria-label="What do you want to do? The ways in that do it light up.">
      <span class="lead">I want to</span>
      <button
        v-for="(one, i) in WANTS"
        :key="one.said"
        type="button"
        :aria-pressed="want === i"
        :class="{ on: want === i }"
        @click="want = want === i ? null : i"
      >
        {{ one.said }}
      </button>
      <span class="sr" aria-live="polite">{{ want === null ? '' : `${WANTS[want].said}: ${WANTS[want].doors.map((d) => DOORS[d].name).join(' and ')}` }}</span>
    </div>
    <HmzStage :scene="scene" :beats="BEATS" :label="label" mobile-ratio="9 / 11">
      <div class="layer cam">
        <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
          <defs>
            <radialGradient v-for="n in [1, 3, 4]" :id="`hmz-surfaces-halo-${n}`" :key="n">
              <stop offset="0" :stop-color="`var(--hmz-lane-${n})`" stop-opacity="0.45" />
              <stop offset="1" :stop-color="`var(--hmz-lane-${n})`" stop-opacity="0" />
            </radialGradient>
          </defs>

          <rect class="core-frame" :x="L.core.x" :y="L.core.y" :width="L.core.w" :height="L.core.h" rx="18" />
          <text class="core-name" :x="L.core.x + 16" :y="L.core.y + 22">one workspace</text>
          <path v-for="(d, i) in wires" :key="`w${i}`" class="wire" :class="`lane-${DOORS[i].lane}`" :d="d" />

          <g v-for="(n, i) in L.nodes" :key="NODES[i]" class="node" :class="`node-${i}`">
            <rect class="bg" :x="n.x" :y="n.y" :width="n.w" :height="n.h" rx="12" />
            <text class="node-name" :x="n.x + 12" :y="n.y + 20">{{ NODES[i] }}</text>
            <template v-if="i === 0">
              <rect v-for="k in 3" :key="k" class="glyph" :x="n.x + 12" :y="n.y + 24 + k * 16" :width="n.w - 24 - k * 14" height="9" rx="4.5" />
            </template>
            <template v-else-if="i === 1">
              <g v-for="k in 3" :key="k">
                <circle class="glyph" :cx="n.x + 22 + (k - 1) * 30" :cy="n.y + 50" r="10" />
                <rect class="glyph" :x="n.x + 12 + (k - 1) * 30" :y="n.y + 66" width="20" height="8" rx="4" />
              </g>
            </template>
          </g>
          <rect
            v-for="(p, k) in pills"
            :key="`p${k}`"
            class="pill"
            :class="`lane-${DOORS[p.door].lane}`"
            :x="p.x"
            :y="p.y"
            :width="p.w"
            :height="PILL.h"
            rx="5"
          />

          <g v-for="(b, i) in L.wins" :key="DOORS[i].name" :transform="`translate(${b.x} ${b.y})`">
            <ellipse class="halo" :class="{ on: want !== null && lit(i) }" :cx="b.w / 2" :cy="b.h / 2" :rx="b.w * 0.8" :ry="b.h * 0.9" :fill="`url(#hmz-surfaces-halo-${DOORS[i].lane})`" />
            <g class="pickwrap" :class="{ dim: !lit(i) }">
              <g class="win" :class="[`win-${i}`, `lane-${DOORS[i].lane}`]">
                <rect class="deny" x="-6" y="-6" :width="b.w + 12" :height="b.h + 12" rx="16" />
                <rect class="frame" :width="b.w" :height="b.h" rx="10" />
                <path class="bar" :d="`M0 24 L${b.w} 24`" />
                <circle v-for="k in 3" :key="k" class="dot" :cx="4 + k * 8" cy="12" r="2.6" />
                <text class="win-name" x="38" y="16">{{ DOORS[i].name }}</text>
                <!-- the terminal interface: a list of runs beside a conversation -->
                <template v-if="i === 0">
                  <path class="rule" :d="`M58 30 L58 ${b.h - 8}`" />
                  <rect v-for="k in 3" :key="k" class="ink" x="10" :y="28 + k * 14" width="40" height="7" rx="3.5" />
                  <rect class="ink talk" x="66" y="36" width="62" height="10" rx="5" />
                  <rect class="ink talk accent" :x="b.w - 10 - 76" y="54" width="76" height="10" rx="5" />
                  <rect class="ink talk" x="66" y="72" width="48" height="10" rx="5" />
                  <rect class="open-row" x="8" y="42" width="44" height="11" rx="4" />
                  <rect class="live" x="66" y="34" width="70" height="10" rx="5" />
                  <rect class="live accent" :x="b.w - 10 - 84" y="50" width="84" height="10" rx="5" />
                  <rect class="live" x="66" y="66" width="56" height="10" rx="5" />
                  <rect class="live accent" :x="b.w - 10 - 60" y="82" width="60" height="10" rx="5" />
                </template>
                <!-- the command line: one line, then its events -->
                <template v-else-if="i === 1">
                  <text class="prompt" x="10" y="44">›</text>
                  <rect class="ink accent" x="22" y="36" :width="b.w - 52" height="9" rx="4.5" />
                  <rect class="cursor" :x="b.w - 26" y="35" width="6" height="11" />
                  <rect v-for="k in 3" :key="k" class="ink faint" x="10" :y="50 + k * 13" :width="b.w - 20 - ((k * 37) % 50)" height="6" rx="3" />
                </template>
                <!-- Python: a program of yours -->
                <template v-else>
                  <g v-for="(ind, k) in [0, 14, 14, 28, 14]" :key="k">
                    <rect class="ink accent" :x="10 + ind" :y="34 + k * 14" width="18" height="7" rx="3.5" />
                    <rect class="ink" :x="32 + ind" :y="34 + k * 14" :width="[80, 64, 92, 50, 70][k]" height="7" rx="3.5" />
                  </g>
                </template>
              </g>
            </g>
          </g>

          <rect class="ghost pill lane-4" :x="L.wins[0].x + 12" :y="L.wins[0].y + 44" :width="pills[3].w" :height="PILL.h" rx="5" />

          <g v-for="i in 3" :key="`b${i}`" class="bad">
            <rect x="-40" y="-12" width="80" height="24" rx="8" />
            <text y="4" text-anchor="middle">bad value</text>
            <line class="bad-x" x1="-32" y1="0" x2="32" y2="0" />
          </g>
        </svg>
        <canvas ref="canvas" />
      </div>
    </HmzStage>
  </div>
</template>

<style scoped>
.pick {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 22px 0 0;
}

.lead {
  margin-right: 4px;
  font-size: 12.5px;
  font-weight: 650;
  color: var(--vp-c-text-2);
}

.pick button {
  padding: 3px 11px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  font-size: 12px;
  color: var(--vp-c-text-2);
  background: transparent;
  transition: color 0.2s, border-color 0.2s, background 0.2s;
}

.pick button:hover,
.pick button:focus-visible {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-text-1);
}

.pick button.on {
  border-style: solid;
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
}

.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

.hmz-surfaces :deep(.hmz-stage) {
  margin-top: 12px;
}

.cam svg,
.cam canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.cam canvas {
  pointer-events: none;
}

svg {
  font-family: var(--vp-font-family-base);
}

.halo {
  opacity: 0;
  transition: opacity 0.4s;
}

.halo.on {
  opacity: var(--hmz-glow);
}

.pickwrap {
  transition: opacity 0.4s;
}

.pickwrap.dim {
  opacity: 0.3;
}

.frame {
  fill: var(--hmz-stage-card);
  stroke-width: 1.4;
}

.lane-1 .frame { stroke: color-mix(in srgb, var(--hmz-lane-1) 70%, transparent); }
.lane-4 .frame { stroke: color-mix(in srgb, var(--hmz-lane-4) 70%, transparent); }
.lane-3 .frame { stroke: color-mix(in srgb, var(--hmz-lane-3) 70%, transparent); }

.bar,
.rule {
  stroke: var(--hmz-stage-line);
}

.dot {
  fill: var(--hmz-stage-line);
}

.win-name {
  font-size: 11.5px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}

.ink {
  fill: color-mix(in srgb, var(--hmz-stage-dim) 38%, transparent);
}

.ink.faint {
  fill: color-mix(in srgb, var(--hmz-stage-dim) 22%, transparent);
}

.lane-1 .accent { fill: var(--hmz-lane-1); }
.lane-4 .accent { fill: var(--hmz-lane-4); }
.lane-3 .accent { fill: var(--hmz-lane-3); }

.live {
  fill: color-mix(in srgb, var(--hmz-stage-dim) 38%, transparent);
}

.live.accent {
  fill: var(--hmz-lane-4);
}

.open-row {
  fill: var(--hmz-lane-4);
}

.prompt {
  font-family: var(--vp-font-family-mono);
  font-size: 15px;
  font-weight: 700;
  fill: var(--hmz-lane-4);
}

.cursor {
  fill: var(--hmz-stage-ink);
}

.deny {
  fill: color-mix(in srgb, var(--hmz-lane-5) 12%, transparent);
  stroke: var(--hmz-lane-5);
  stroke-width: 2.5;
}

.core-frame {
  fill: color-mix(in srgb, var(--hmz-accent) 5%, transparent);
  stroke: color-mix(in srgb, var(--hmz-accent) 55%, transparent);
  stroke-width: 1.5;
  stroke-dasharray: 5 4;
}

.core-name,
.node-name {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.node .bg {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
}

.glyph {
  fill: color-mix(in srgb, var(--hmz-accent) 45%, transparent);
}

.wire {
  fill: none;
  stroke-width: 2;
  stroke-dasharray: 3 4;
}

.wire.lane-1 { stroke: var(--hmz-lane-1); }
.wire.lane-4 { stroke: var(--hmz-lane-4); }
.wire.lane-3 { stroke: var(--hmz-lane-3); }

.pill.lane-1 { fill: var(--hmz-lane-1); }
.pill.lane-4 { fill: var(--hmz-lane-4); }
.pill.lane-3 { fill: var(--hmz-lane-3); }

.bad rect {
  fill: color-mix(in srgb, var(--hmz-lane-5) 12%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-5);
  stroke-width: 1.4;
}

.bad text {
  font-size: 12px;
  font-weight: 650;
  fill: var(--hmz-lane-5);
}

.bad-x {
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
}
</style>
