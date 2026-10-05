<script setup lang="ts">
// Remote execution's split, acted out with `onbox`. This machine keeps the agent's CLI, its
// sign-in and its sessions; ssh to build-box carries every command the agent runs, at the
// host's own paths, on the host's network. A session is only history, kept here: the builder's
// turns name `env=envs["box"]` when they run and work on build-box, the reviewer's name the
// workspace and work here, and the builder's one session takes its next turn on build-box
// again. Last, where the harness itself runs: a saved host's affinity, tried in order, the
// next place only when the one before has no room.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { createFx, type, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'
import { rig, type Point, type Shot } from '../../motion/camera'
import { draw, pop, pulse, ring, rise, shake } from '../user-kit/moves'

const BEATS = [
  "This machine keeps the agent's CLI, its sign-in and its sessions",
  "ssh carries every command to build-box: the host's files, at its paths, on its network",
  'The builder spawns a session here, and runs its turn with env=envs["box"]: on build-box',
  "The reviewer's turn runs in the workspace, here; the builder's session takes its next turn on build-box",
  "Where the harness runs: a saved host's affinity, tried in order",
]

/** A mono character's advance at 11px. */
const CW = 6.6

interface Line {
  text: string
  /** Which step of the flow it is part of: 0 spawn builder, 1 run builder, 2 spawn reviewer, 3 run reviewer. */
  step: number
  env?: { col: number; len: number }
}

const WIDE_CODE: Line[] = [
  { text: 'working = await builder.spawn()', step: 0 },
  { text: 'await builder.run(task, session=working, env=envs["box"])', step: 1, env: { col: 41, len: 15 } },
  { text: 'reading = await reviewer.spawn()', step: 2 },
  { text: 'review = await reviewer.run(…, session=reading, env=envs["workspace"])', step: 3, env: { col: 48, len: 21 } },
]
const NARROW_CODE: Line[] = [
  { text: 'working = await builder.spawn()', step: 0 },
  { text: 'await builder.run(task, session=working,', step: 1 },
  { text: '    env=envs["box"])', step: 1, env: { col: 4, len: 15 } },
  { text: 'reading = await reviewer.spawn()', step: 2 },
  { text: 'review = await reviewer.run(…, session=reading,', step: 3 },
  { text: '    env=envs["workspace"])', step: 3, env: { col: 4, len: 21 } },
]

/** The affinity of build-box, once saved, in the order its places are tried. */
const PLACES = [
  { name: 'self', w: 40 },
  { name: 'local', w: 46 },
  { name: 'ssh:gpu2', w: 66 },
]

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Layout {
  w: number
  h: number
  mach: Box
  box: Box
  code: Box
  link: [Point, Point]
  shots: Record<'mach' | 'link' | 'all' | 'box', Partial<Shot>>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  mach: { x: 20, y: 16, w: 236, h: 216 },
  box: { x: 372, y: 16, w: 248, h: 216 },
  code: { x: 20, y: 248, w: 600, h: 98 },
  link: [
    { x: 256, y: 112 },
    { x: 372, y: 112 },
  ],
  shots: {
    mach: { x: 160, y: 124, s: 1.45 },
    link: { x: 320, y: 124, s: 1.15 },
    all: { x: 320, y: 180, s: 1 },
    box: { x: 486, y: 150, s: 1.4 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 640,
  mach: { x: 12, y: 12, w: 336, h: 216 },
  box: { x: 12, y: 270, w: 336, h: 216 },
  code: { x: 12, y: 502, w: 336, h: 128 },
  link: [
    { x: 180, y: 228 },
    { x: 180, y: 270 },
  ],
  // A phone's screen is as tall as the scene: the camera holds still and the light moves.
  shots: {
    mach: { x: 180, y: 320, s: 1 },
    link: { x: 180, y: 320, s: 1 },
    all: { x: 180, y: 320, s: 1 },
    box: { x: 180, y: 320, s: 1 },
  },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const CODE = computed(() => (narrow.value ? NARROW_CODE : WIDE_CODE))

const codeY = (i: number) => L.value.code.y + (narrow.value ? 20 : 22) + i * (narrow.value ? 18 : 20)
const codeX = computed(() => L.value.code.x + 14)
const placeX = (k: number) => L.value.box.x + 12 + PLACES.slice(0, k).reduce((s, p) => s + p.w + 6, 0)
const linkMid = computed(() => ({ x: (L.value.link[0].x + L.value.link[1].x) / 2, y: (L.value.link[0].y + L.value.link[1].y) / 2 }))

/** A turn's mark in a session: `lane` 0 the builder's, 1 the reviewer's. */
const DOT_W = 16
const dotX = (i: number) => L.value.mach.x + L.value.mach.w - 30 - (1 - i) * 22 - DOT_W / 2
const pillY = (lane: number) => L.value.mach.y + 86 + lane * 32
const dotC = (lane: number, i: number): Point => ({ x: dotX(i) + DOT_W / 2, y: pillY(lane) + 13 })

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    const m = l.mach
    const b = l.box
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), far: one('.far'), fx: () => fx, start: l.shots.mach })
    const hue = {
      cli: () => palette.lane[0],
      builder: () => palette.lane[0],
      reviewer: () => palette.accent2,
      ssh: () => palette.lane[2],
      here: () => palette.warm,
      ok: () => palette.accent,
    }
    const term = { x: b.x + 40, y: b.y + 86 }
    const ws = { x: m.x + 60, y: m.y + 178 }
    /** Light along the ssh link, from this machine to build-box or back. */
    const over = (from: Point, to: Point, color: () => string, t: number, back = false) => {
      const [a, z] = back ? [l.link[1], l.link[0]] : [l.link[0], l.link[1]]
      cam.beam(from, a, color, t, { duration: 0.45, bend: 0.15 })
      cam.beam(a, z, color, t + 0.4, { duration: 0.5, bend: 0, size: 3 })
      cam.beam(z, to, color, t + 0.85, { duration: 0.45, bend: 0.15, burst: 12 })
    }

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(
      q('.mach, .chip, .kept, .slot, .pill, .dot, .ws, .link, .ssh, .box, .folder, .term, .term-line, .net, .code, .cl, .env-bg, .env-ring, .aff, .place, .place-ring, .cross, .msg, .gpu-skip, .runs-here'),
      { autoAlpha: 0 },
      0,
    )

    // 0 · this machine: the CLI, its sign-in, where its sessions are kept.
    tl.addLabel('beat-0', 0)
    rise(tl, one('.mach'), 0.2)
    pop(tl, one('.chip'), 0.8, { from: 0.8 })
    cam.flare({ x: m.x + m.w / 2, y: m.y + 45 }, hue.cli, 1.1, 16, 80)
    rise(tl, one('.kept'), 1.5, { y: 6 })
    rise(tl, q('.slot'), 1.8, { y: 6, stagger: 0.2 })
    rise(tl, one('.ws'), 2.5)

    // 1 · ssh to build-box, and what goes over it.
    const T1 = 3.6
    tl.addLabel('beat-1', T1)
    cam.shot(l.shots.link, T1, 1.4)
    draw(tl, one('.link'), T1 + 0.3, { duration: 0.8 })
    pop(tl, one('.ssh'), T1 + 0.8)
    cam.beam(l.link[0], l.link[1], hue.ssh, T1 + 0.9, { duration: 0.7, bend: 0, burst: 10 })
    rise(tl, one('.box'), T1 + 1.3)
    cam.shot(l.shots.box, T1 + 1.9, 1.4)
    rise(tl, one('.folder'), T1 + 2.2)
    rise(tl, one('.term'), T1 + 2.6)
    rise(tl, one('.net'), T1 + 3.0)
    ring(tl, one('.net-ring'), T1 + 3.2, { to: 2.2, duration: 1.1 })

    // 2 · the builder's session, opened here; its turn, run on build-box.
    const T2 = T1 + 4.4
    tl.addLabel('beat-2', T2)
    cam.shot(l.shots.all, T2, 1.4)
    rise(tl, one('.code'), T2 + 0.2, { y: 8 })
    tl.to(q('.cl-0'), { autoAlpha: 1, duration: 0.3 }, T2 + 0.7)
    tl.to(one('.slot-0'), { autoAlpha: 0, duration: 0.3 }, T2 + 1.0)
    pop(tl, one('.pill-0'), T2 + 1.0, { from: 0.8 })
    cam.beam({ x: codeX.value + 120, y: codeY(0) - 4 }, { x: m.x + 70, y: pillY(0) + 13 }, hue.builder, T2 + 0.8, { duration: 0.6, bend: -0.2, burst: 8 })
    tl.to(q('.cl-1'), { autoAlpha: 1, duration: 0.3, stagger: 0.15 }, T2 + 1.6)
    tl.to(q('.env-bg-1'), { autoAlpha: 1, duration: 0.3 }, T2 + 2.0)
    ring(tl, q('.env-ring-1'), T2 + 2.05, { to: 1.3 })
    pop(tl, one('.dot-0-0'), T2 + 2.4)
    over(dotC(0, 0), term, hue.builder, T2 + 2.6)
    tl.set(one('.term-0'), { autoAlpha: 1 }, T2 + 3.5)
    type(tl, one('.term-0'), '$ python test_calc.py', T2 + 3.5)
    tl.set(one('.term-1'), { autoAlpha: 1 }, T2 + 4.2)
    type(tl, one('.term-1'), 'OK: the test passes', T2 + 4.2)
    pulse(tl, one('.folder'), T2 + 4.0, 1.03)

    // 3 · the reviewer's turn in the workspace, here; the builder's next turn, back on the box.
    const T3 = T2 + 5.3
    tl.addLabel('beat-3', T3)
    over(term, { x: m.x + 70, y: pillY(1) + 13 }, hue.here, T3 + 0.1, true)
    tl.set(one('.term-2'), { autoAlpha: 1 }, T3 + 0.1)
    type(tl, one('.term-2'), '$ git diff', T3 + 0.1)
    tl.to(q('.cl-2'), { autoAlpha: 1, duration: 0.3 }, T3 + 0.6)
    tl.to(one('.slot-1'), { autoAlpha: 0, duration: 0.3 }, T3 + 1.2)
    pop(tl, one('.pill-1'), T3 + 1.2, { from: 0.8 })
    tl.to(q('.cl-3'), { autoAlpha: 1, duration: 0.3, stagger: 0.15 }, T3 + 1.5)
    tl.to(q('.env-bg-3'), { autoAlpha: 1, duration: 0.3 }, T3 + 1.9)
    ring(tl, q('.env-ring-3'), T3 + 1.95, { to: 1.3 })
    pop(tl, one('.dot-1-0'), T3 + 2.3)
    cam.beam(dotC(1, 0), ws, hue.here, T3 + 2.5, { duration: 0.8, bend: 0.35, burst: 14 })
    pulse(tl, one('.ws'), T3 + 3.2, 1.04)
    cam.beam(dotC(1, 0), dotC(0, 1), hue.reviewer, T3 + 3.6, { duration: 0.5, bend: 0.6 })
    pop(tl, one('.dot-0-1'), T3 + 4.0)
    over(dotC(0, 1), term, hue.builder, T3 + 4.2)
    pulse(tl, one('.folder'), T3 + 5.2, 1.03)

    // 4 · where the harness runs: build-box saved with an affinity, its places tried in order.
    const T4 = T3 + 6.0
    tl.addLabel('beat-4', T4)
    cam.shot(l.shots.box, T4, 1.4)
    rise(tl, one('.aff'), T4 + 0.4, { y: 6 })
    pop(tl, q('.place'), T4 + 0.8, { stagger: 0.15 })
    ring(tl, one('.place-ring-0'), T4 + 1.6)
    shake(tl, one('.place-0'), T4 + 1.9)
    tl.to(one('.cross'), { autoAlpha: 1, duration: 0.3 }, T4 + 1.9)
    rise(tl, one('.msg-0'), T4 + 2.0, { y: 4 })
    tl.to(one('.msg-0'), { autoAlpha: 0, duration: 0.3 }, T4 + 3.4)
    ring(tl, one('.place-ring-1'), T4 + 3.4)
    rise(tl, one('.msg-1'), T4 + 3.6, { y: 4 })
    tl.to(one('.gpu-skip'), { autoAlpha: 1, duration: 0.4 }, T4 + 4.0)
    tl.to(one('.place-2'), { autoAlpha: 0.4, duration: 0.4 }, T4 + 4.0)
    cam.shot(l.shots.all, T4 + 4.2, 1.4)
    const local = { x: placeX(1) + PLACES[1].w / 2, y: b.y + 175 }
    over(local, { x: m.x + m.w / 2, y: m.y + 45 }, hue.cli, T4 + 4.6, true)
    ring(tl, one('.chip-ring'), T4 + 6.0)
    tl.to(one('.chip-a'), { autoAlpha: 0, y: -5, duration: 0.3 }, T4 + 6.0)
    tl.fromTo(one('.runs-here'), { autoAlpha: 0, y: 5 }, { autoAlpha: 1, y: 0, duration: 0.4, ease: 'cine.out' }, T4 + 6.15)
    tl.addLabel('rest', T4 + 7.2)
    // Secondary motion over the whole loop: the link's dashes keep flowing.
    tl.fromTo(one('.link-flow'), { strokeDashoffset: 0 }, { strokeDashoffset: -160, duration: T4 + 11, ease: 'none' }, 0)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 10.4)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    mobile-ratio="9 / 16"
    label="Remote execution's split, with the onbox flow. This machine keeps the agent's CLI, signed in, and its sessions, which are only history. ssh to build-box carries every command the agent runs, at the host's own paths, /home/me/build/myproject, on the host's network. The builder spawns its session here with working = await builder.spawn(), and runs its turn with builder.run(task, session=working, env=envs['box']): the turn works on build-box, where python test_calc.py runs. The flow runs git diff on build-box; the reviewer spawns its session with reading = await reviewer.spawn() and runs its turn with env=envs['workspace'], in the workspace here. The builder's same session then takes its next turn on build-box. Where the agent's CLI itself runs is the affinity of a saved host, its places tried in order: self has no room on a host without claude, so local is tried, which always has room, and the builder's harness runs here; ssh:gpu2 after it is never tried."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <pattern id="rs-dots" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" class="grid-dot" />
        </pattern>
      </defs>
      <g class="far"><rect x="-400" y="-400" :width="L.w + 800" :height="L.h + 800" fill="url(#rs-dots)" /></g>

      <g class="world">
        <!-- This machine. -->
        <g class="mach">
          <rect class="card" :x="L.mach.x" :y="L.mach.y" :width="L.mach.w" :height="L.mach.h" rx="12" />
          <text class="name" :x="L.mach.x + 12" :y="L.mach.y + 22">this machine</text>
        </g>
        <g class="chip">
          <rect class="chip-bg" :x="L.mach.x + 12" :y="L.mach.y + 32" :width="L.mach.w - 24" height="26" rx="7" />
          <g class="chip-a"><text class="chip-word" :x="L.mach.x + 22" :y="L.mach.y + 49">claude: the agent's CLI, signed in</text></g>
          <g class="runs-here"><text class="chip-word" :x="L.mach.x + 22" :y="L.mach.y + 49">claude: builder's harness runs here</text></g>
          <g :transform="`translate(${L.mach.x + L.mach.w / 2} ${L.mach.y + 45})`">
            <rect class="chip-ring" :x="-(L.mach.w - 24) / 2" y="-13" :width="L.mach.w - 24" height="26" rx="7" />
          </g>
        </g>
        <g class="kept"><text class="dim" :x="L.mach.x + 12" :y="L.mach.y + 77">its sessions, only history, kept here</text></g>
        <rect v-for="k in [0, 1]" :key="`s${k}`" class="slot" :class="`slot-${k}`" :x="L.mach.x + 12" :y="pillY(k)" :width="L.mach.w - 24" height="26" rx="13" />
        <g v-for="k in [0, 1]" :key="`p${k}`" class="pill" :class="[`pill-${k}`, k ? 'pill-r' : 'pill-b']">
          <rect :x="L.mach.x + 12" :y="pillY(k)" :width="L.mach.w - 24" height="26" rx="13" />
          <text class="pill-word" :x="L.mach.x + 24" :y="pillY(k) + 17">{{ k ? 'reading' : 'working' }}</text>
          <text class="dim" :x="L.mach.x + 82" :y="pillY(k) + 17">{{ k ? "reviewer's" : "builder's" }}</text>
        </g>
        <rect v-for="i in [0, 1]" :key="`d0${i}`" class="dot dot-b" :class="`dot-0-${i}`" :x="dotX(i)" :y="pillY(0) + 6" :width="DOT_W" height="14" rx="4" />
        <rect class="dot dot-r dot-1-0" :x="dotX(1)" :y="pillY(1) + 6" :width="DOT_W" height="14" rx="4" />
        <g class="ws">
          <path class="ws-box" :d="`M${L.mach.x + 12} ${L.mach.y + 160} q0 -6 6 -6 h56 l8 6 h${L.mach.w - 100} q6 0 6 6 v38 q0 6 -6 6 h${-(L.mach.w - 36)} q-6 0 -6 -6 z`" />
          <text class="name" :x="L.mach.x + 24" :y="L.mach.y + 180">workspace</text>
          <text class="dim" :x="L.mach.x + 24" :y="L.mach.y + 196">the directory hmz ran in</text>
        </g>

        <!-- ssh. -->
        <path class="link" :d="`M${L.link[0].x} ${L.link[0].y} L${L.link[1].x} ${L.link[1].y}`" />
        <path class="link link-flow" :d="`M${L.link[0].x} ${L.link[0].y} L${L.link[1].x} ${L.link[1].y}`" />
        <g class="ssh">
          <rect class="ssh-bg" :x="linkMid.x - 20" :y="linkMid.y - 10" width="40" height="20" rx="10" />
          <text class="ssh-word" :x="linkMid.x" :y="linkMid.y + 4" text-anchor="middle">ssh</text>
        </g>

        <!-- build-box. -->
        <g class="box">
          <rect class="card box-card" :x="L.box.x" :y="L.box.y" :width="L.box.w" :height="L.box.h" rx="12" />
          <text class="name" :x="L.box.x + 12" :y="L.box.y + 22">build-box</text>
        </g>
        <g class="folder">
          <path class="folder-box" :d="`M${L.box.x + 12} ${L.box.y + 36} q0 -4 4 -4 h36 l6 4 h${L.box.w - 74} q4 0 4 4 v18 q0 4 -4 4 h${-(L.box.w - 32)} q-4 0 -4 -4 z`" />
          <text class="mono strong" :x="L.box.x + 22" :y="L.box.y + 51">/home/me/build/myproject</text>
        </g>
        <g class="term">
          <rect class="term-box" :x="L.box.x + 12" :y="L.box.y + 66" :width="L.box.w - 24" height="58" rx="6" />
          <text class="mono term-line term-0" :x="L.box.x + 20" :y="L.box.y + 82">$ python test_calc.py</text>
          <text class="mono term-line term-out term-1" :x="L.box.x + 20" :y="L.box.y + 98">OK: the test passes</text>
          <text class="mono term-line term-2" :x="L.box.x + 20" :y="L.box.y + 114">$ git diff</text>
        </g>
        <g class="net">
          <circle class="net-dot" :cx="L.box.x + 18" :cy="L.box.y + 138" r="4" />
          <text class="dim" :x="L.box.x + 28" :y="L.box.y + 142">on its network, every command</text>
          <g :transform="`translate(${L.box.x + 18} ${L.box.y + 138})`"><circle class="net-ring" r="6" /></g>
        </g>
        <g class="aff"><text class="dim" :x="L.box.x + 12" :y="L.box.y + 162">saved with harness runs on</text></g>
        <g v-for="(p, k) in PLACES" :key="p.name" class="place" :class="`place-${k}`">
          <rect class="place-bg" :x="placeX(k)" :y="L.box.y + 168" :width="p.w" height="20" rx="5" />
          <text class="mono" :x="placeX(k) + p.w / 2" :y="L.box.y + 182" text-anchor="middle">{{ p.name }}</text>
          <g :transform="`translate(${placeX(k) + p.w / 2} ${L.box.y + 178})`">
            <rect class="place-ring" :class="`place-ring-${k}`" :x="-p.w / 2" y="-10" :width="p.w" height="20" rx="5" />
          </g>
        </g>
        <path class="cross" :d="`M${placeX(0) + 4} ${L.box.y + 178} L${placeX(0) + PLACES[0].w - 4} ${L.box.y + 178}`" />
        <g class="gpu-skip"><text class="note" :x="placeX(2) + PLACES[2].w + 6" :y="L.box.y + 182">never tried</text></g>
        <g class="msg msg-0"><text class="note-word bad" :x="L.box.x + 12" :y="L.box.y + 205">self: no claude on build-box, no room</text></g>
        <g class="msg msg-1"><text class="note-word good" :x="L.box.x + 12" :y="L.box.y + 205">local: always has room, so here</text></g>

        <!-- The flow. -->
        <g class="code">
          <rect class="card" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="L.code.h" rx="10" />
        </g>
        <template v-for="(line, i) in CODE" :key="`l${i}`">
          <g v-if="line.env" class="env-bg" :class="`env-bg-${line.step}`">
            <rect
              :class="line.step === 1 ? 'env-box' : 'env-ws'"
              :x="codeX + line.env.col * CW - 3"
              :y="codeY(i) - 12"
              :width="line.env.len * CW + 6"
              height="17"
              rx="4"
            />
          </g>
          <g class="cl" :class="`cl-${line.step}`">
            <text class="mono" :x="codeX" :y="codeY(i)">{{ line.text }}</text>
          </g>
          <g v-if="line.env" :transform="`translate(${codeX + (line.env.col + line.env.len / 2) * CW} ${codeY(i) - 4})`">
            <rect
              class="env-ring"
              :class="[`env-ring-${line.step}`, line.step === 1 ? 'ring-box' : 'ring-ws']"
              :x="-(line.env.len * CW + 6) / 2"
              y="-9"
              :width="line.env.len * CW + 6"
              height="17"
              rx="4"
            />
          </g>
        </template>
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

.card {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.box-card {
  stroke: color-mix(in srgb, var(--hmz-lane-3) 55%, var(--hmz-stage-line));
}

.name {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.dim {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.mono {
  white-space: pre;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.strong {
  font-weight: 700;
}

.chip-bg {
  fill: var(--hmz-lane-1);
}

.chip-word {
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.chip-ring {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
}

.slot {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
  stroke-dasharray: 4 4;
}

.pill rect {
  fill: color-mix(in srgb, var(--hmz-lane-1) 9%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-1);
  stroke-width: 1.2;
}

.pill-r rect {
  fill: color-mix(in srgb, var(--hmz-accent-2) 9%, var(--hmz-stage-card));
  stroke: var(--hmz-accent-2);
}

.pill-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.dot-b {
  fill: var(--hmz-lane-1);
}

.dot-r {
  fill: var(--hmz-accent-2);
}

.ws-box {
  fill: color-mix(in srgb, var(--hmz-warm) 8%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
  stroke-width: 1.3;
}

.link {
  fill: none;
  stroke: color-mix(in srgb, var(--hmz-lane-3) 35%, transparent);
  stroke-width: 6;
  stroke-linecap: round;
}

.link-flow {
  stroke: var(--hmz-lane-3);
  stroke-width: 2;
  stroke-dasharray: 3 7;
}

.ssh-bg {
  fill: var(--hmz-lane-3);
}

.ssh-word {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: #fff;
}

.folder-box {
  fill: color-mix(in srgb, var(--hmz-lane-3) 8%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-3);
  stroke-width: 1.2;
}

.term-box {
  fill: color-mix(in srgb, var(--hmz-stage-ink) 6%, var(--vp-c-bg));
  stroke: var(--hmz-stage-line);
}

.term-out {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.net-dot {
  fill: var(--hmz-lane-3);
}

.net-ring {
  fill: none;
  stroke: var(--hmz-lane-3);
  stroke-width: 1.5;
}

.place-bg {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-3);
  stroke-width: 1.2;
}

.place-ring {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.place-ring-0 {
  stroke: var(--vp-c-danger-1);
}

.cross {
  fill: none;
  stroke: var(--vp-c-danger-1);
  stroke-width: 1.6;
}

.note {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.note-word {
  font-size: 11px;
  font-weight: 700;
}

.bad {
  fill: var(--vp-c-danger-1);
}

.good {
  fill: var(--hmz-accent);
}

.env-box {
  fill: color-mix(in srgb, var(--hmz-lane-3) 22%, transparent);
  stroke: var(--hmz-lane-3);
}

.env-ws {
  fill: color-mix(in srgb, var(--hmz-warm) 22%, transparent);
  stroke: var(--hmz-warm);
}

.env-ring {
  fill: none;
  stroke-width: 2;
}

.ring-box {
  stroke: var(--hmz-lane-3);
}

.ring-ws {
  stroke: var(--hmz-warm);
}
</style>
