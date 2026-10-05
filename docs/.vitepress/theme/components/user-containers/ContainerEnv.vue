<script setup lang="ts">
// A container per environment, as Containers says it goes. One `-e` names the role, the
// backend, the saved daemon and the directory; the daemon starts a container for the role from
// its image, with exactly the CPUs and memory the role declares out of what the daemon was
// saved to hand out; the directory is mounted into it at the path it has; the agent's CLI runs
// here, in a copy of the directory kept under `~/.hmz/envs/mirrors/`, and every command it runs
// lands in the container through `docker exec`; its edit lands in the directory; and when the
// run ends the container goes, its share back with the daemon, the work left behind. A
// simulation: what the role declares is invented.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { createFx, type, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'
import { rig, type Point, type Shot } from '../../motion/camera'
import { brace, braceD, curve, draw, pop, pulse, ring, rise } from '../user-kit/moves'

const BEATS = [
  'One -e names the role, the backend, the daemon and the directory',
  "The daemon starts a container from the role's image, with exactly what the role declares",
  'The directory is mounted into it at the path it has',
  "The agent's CLI runs here, working in a mirror of the directory",
  'Every command it runs lands in the container through docker exec',
  'The edit lands in /home/me/myproject; the container goes when the run ends',
]

/** A mono character's advance at 12px. */
const CW = 7.2
/** The second line of the command, in pieces; `part` is the brace each piece gets. */
const PIECES = [
  { text: '-e', col: 2, part: -1 },
  { text: 'box', col: 5, part: 0 },
  { text: '=', col: 8, part: -1 },
  { text: 'docker', col: 9, part: 1 },
  { text: '@', col: 15, part: -1 },
  { text: 'gpubox', col: 16, part: 2 },
  { text: '/home/me/myproject', col: 22, part: 3 },
]
const PART_NAMES = ['role', 'backend', 'daemon', 'workdir']
const LANE_OF = ['--hmz-accent-2', '--hmz-lane-1', '--hmz-lane-3', '--hmz-warm']

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Layout {
  w: number
  h: number
  cmd: Box
  mach: Box
  dmn: Box
  shots: Record<'open' | 'daemon' | 'host' | 'mach' | 'all', Partial<Shot>>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  cmd: { x: 24, y: 16, w: 312, h: 56 },
  mach: { x: 24, y: 120, w: 260, h: 224 },
  dmn: { x: 356, y: 16, w: 264, h: 328 },
  shots: {
    open: { x: 180, y: 66, s: 1.75 },
    daemon: { x: 488, y: 140, s: 1.35 },
    host: { x: 488, y: 230, s: 1.35 },
    mach: { x: 250, y: 220, s: 1.2 },
    all: { x: 320, y: 180, s: 1 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 664,
  cmd: { x: 12, y: 12, w: 336, h: 56 },
  mach: { x: 12, y: 112, w: 336, h: 196 },
  dmn: { x: 12, y: 324, w: 336, h: 328 },
  shots: {
    // A phone's screen is as tall as the scene: the camera holds still and the light moves.
    open: { x: 180, y: 332, s: 1 },
    daemon: { x: 180, y: 332, s: 1 },
    host: { x: 180, y: 332, s: 1 },
    mach: { x: 180, y: 332, s: 1 },
    all: { x: 180, y: 332, s: 1 },
  },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const textX = computed(() => L.value.cmd.x + 12)
const lineY = (i: number) => L.value.cmd.y + 22 + i * 20
const pieceW = (text: string) => text.length * CW
const braceOf = (k: number) => {
  const piece = PIECES.find((p) => p.part === k)!
  const x = textX.value + piece.col * CW
  const y = lineY(1) + 8
  const w = pieceW(piece.text)
  return { d: braceD({ x: x + 1, y }, { x: x + w - 1, y }, 9), cx: x + w / 2, ly: y + 23 }
}

/** The container: inside the daemon's card, under the row of what it hands out. */
const ctr = computed<Box>(() => ({ x: L.value.dmn.x + 12, y: L.value.dmn.y + 64, w: L.value.dmn.w - 24, h: 140 }))
/** The directory on the daemon's host. */
const host = computed<Box>(() => ({ x: L.value.dmn.x + 12, y: ctr.value.y + ctr.value.h + 32, w: L.value.dmn.w - 24, h: 76 }))

const CELL = 14
const poolCell = (i: number): Point => ({ x: L.value.dmn.x + 80 + i * 18, y: L.value.dmn.y + 38 })
const ctrCell = (i: number): Point => ({ x: ctr.value.x + 12 + i * 18, y: ctr.value.y + 30 })
const poolMem = computed<Point>(() => ({ x: L.value.dmn.x + 156, y: L.value.dmn.y + 38 }))
const ctrMem = computed<Point>(() => ({ x: ctr.value.x + 50, y: ctr.value.y + 30 }))

/** Where things are, for the light. */
const at = computed(() => {
  const m = L.value.mach
  const c = ctr.value
  const h = host.value
  return {
    chip: { x: m.x + m.w - 30, y: m.y + 46 },
    tool: { x: m.x + 200, y: m.y + 160 },
    mirror: { x: m.x + m.w / 2, y: m.y + 122 },
    term: { x: c.x + c.w - 40, y: c.y + 70 },
    mount: { x: c.x + c.w / 2, y: c.y + 112 },
    dir: { x: h.x + h.w / 2, y: h.y + 34 },
    file: { x: h.x + 120, y: h.y + 56 },
  }
})
/** The `docker exec` path, from the CLI to the container, and the middle of it for its name. */
const exec = computed(() => {
  const m = L.value.mach
  const c = ctr.value
  const a = narrow.value ? { x: m.x + m.w - 18, y: m.y + 60 } : at.value.chip
  const b = narrow.value ? { x: c.x + c.w - 18, y: c.y + 52 } : { x: c.x + 12, y: c.y + 70 }
  const bend = narrow.value ? 0.05 : 0.3
  const d = curve(a, b, bend)
  const cx = (a.x + b.x) / 2 + (b.y - a.y) * bend
  const cy = (a.y + b.y) / 2 - (b.x - a.x) * bend
  const mid = { x: Math.min((a.x + 2 * cx + b.x) / 4, L.value.w - 46), y: (a.y + 2 * cy + b.y) / 4 }
  return { d, a, b, bend, mid }
})

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    const c = ctr.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), far: one('.far'), fx: () => fx, start: l.shots.open })
    const hue = {
      cli: () => palette.lane[0],
      box: () => palette.lane[2],
      work: () => palette.warm,
      ok: () => palette.accent,
    }
    const P = at.value

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(
      q(
        '.cmd, .hl, .brace-path, .brace-label, .dmn, .pool, .cell, .mem, .taken, .ctr, .ctr-frame, .ctr-head, .ctr-res, .ctr-note, .term, .term-line, .term-out, .mount, .mount-path, .mount-note, .host, .code-new, .mark, .mach, .chip, .aff, .mirror, .tool, .exec-path, .exec-name, .gone, .stays',
      ),
      { autoAlpha: 0 },
      0,
    )
    tl.set(q('.taken'), { x: 0, y: 0 }, 0)
    tl.set(q('.code-old, .cmd-line, .piece'), { autoAlpha: 1 }, 0)
    tl.set(one('.ctr'), { scale: 1, transformOrigin: '50% 50%' }, 0)

    // 0 · the line, typed, then each part of what follows -e named.
    tl.addLabel('beat-0', 0)
    rise(tl, one('.cmd'), 0.1, { y: 10 })
    type(tl, one('.cmd-line'), '$ hmz exec -f boxed', 0.4)
    tl.fromTo(q('.piece'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.12, stagger: 0.09, ease: 'none' }, 1.1)
    PART_NAMES.forEach((_, k) => {
      tl.to(one(`.hl-${k}`), { autoAlpha: 1, duration: 0.3 }, 2.0 + k * 0.45)
      brace(tl, q, `.brace-${k}`, 2.05 + k * 0.45)
    })

    // 1 · the daemon, what it hands out, and the container it starts with the role's share.
    const T1 = 4.3
    tl.addLabel('beat-1', T1)
    cam.shot(l.shots.daemon, T1, 1.5)
    cam.beam({ x: braceOf(2).cx, y: braceOf(2).ly }, { x: l.dmn.x + 40, y: l.dmn.y + 20 }, hue.box, T1 + 0.2, { duration: 1.0, bend: -0.2, burst: 10 })
    rise(tl, one('.dmn'), T1 + 0.6)
    rise(tl, q('.pool'), T1 + 1.0, { y: 6 })
    pop(tl, q('.cell, .mem'), T1 + 1.2, { stagger: 0.08 })
    tl.set(q('.taken'), { autoAlpha: 1 }, T1 + 1.7)
    tl.set(one('.ctr'), { autoAlpha: 1 }, T1 + 1.8)
    draw(tl, one('.ctr-frame'), T1 + 1.8, { duration: 1.0 })
    rise(tl, one('.ctr-head'), T1 + 2.2, { y: 6 })
    tl.to(q('.taken'), { x: (i: number) => (i < 2 ? ctrCell(i).x - poolCell(i).x : ctrMem.value.x - poolMem.value.x), y: () => c.y + 30 - (l.dmn.y + 38), duration: 1.1, ease: 'cine', stagger: 0.15 }, T1 + 2.6)
    tl.to(q('.cell-0, .cell-1, .mem-0'), { autoAlpha: 0.25, duration: 0.4 }, T1 + 2.7)
    rise(tl, one('.ctr-res'), T1 + 3.6, { y: 4 })
    cam.flare({ x: c.x + 40, y: c.y + 37 }, hue.box, T1 + 3.7, 14, 70)

    // 2 · the directory on the daemon's host, mounted where it is.
    const T2 = T1 + 4.6
    tl.addLabel('beat-2', T2)
    cam.shot(l.shots.host, T2, 1.4)
    rise(tl, one('.host'), T2 + 0.4)
    tl.fromTo(one('.mount'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, T2 + 1.1)
    cam.beam(P.dir, P.mount, hue.work, T2 + 1.1, { duration: 0.7, bend: 0, burst: 12 })
    pop(tl, one('.mount-path'), T2 + 1.75, { from: 0.85 })
    rise(tl, one('.mount-note'), T2 + 2.1, { x: -6, y: 0 })
    ring(tl, one('.mount-ring'), T2 + 1.85, { to: 1.12 })

    // 3 · the CLI, here, in a mirror of the directory.
    const T3 = T2 + 3.2
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.mach, T3, 1.5)
    rise(tl, one('.mach'), T3 + 0.4)
    pop(tl, one('.chip'), T3 + 0.9, { from: 0.8 })
    rise(tl, q('.aff'), T3 + 1.3, { y: 6, stagger: 0.25 })
    rise(tl, one('.mirror'), T3 + 2.0)
    cam.beam(P.dir, P.mirror, hue.work, T3 + 2.2, { duration: 1.0, bend: 0.25, burst: 12 })
    pulse(tl, one('.mirror'), T3 + 3.2, 1.04)

    // 4 · a command, sent through docker exec, run in the container.
    const T4 = T3 + 4.0
    tl.addLabel('beat-4', T4)
    cam.shot(l.shots.all, T4, 1.4)
    tl.set(one('.tool-0'), { autoAlpha: 1 }, T4 + 0.3)
    type(tl, one('.tool-0 text'), '● Bash(hostname && uname -a)', T4 + 0.3)
    draw(tl, one('.exec-path'), T4 + 1.2, { duration: 0.9 })
    pop(tl, one('.exec-name'), T4 + 1.6, { from: 0.7 })
    cam.beam(exec.value.a, exec.value.b, hue.cli, T4 + 1.4, { duration: 0.9, bend: -exec.value.bend, burst: 14 })
    rise(tl, one('.term'), T4 + 2.1, { y: 4 })
    type(tl, one('.term-line'), '$ hostname', T4 + 2.3)
    tl.set(one('.term-line'), { autoAlpha: 1 }, T4 + 2.31)
    tl.set(one('.term-out'), { autoAlpha: 1 }, T4 + 2.81)
    type(tl, one('.term-out'), '14a684eac2e0', T4 + 2.8)
    cam.beam(exec.value.b, exec.value.a, hue.cli, T4 + 3.3, { duration: 0.9, bend: exec.value.bend, burst: 10 })
    ring(tl, one('.chip-ring'), T4 + 4.2)

    // 5 · the edit lands in the directory; the run ends, and the container goes.
    const T5 = T4 + 5.0
    tl.addLabel('beat-5', T5)
    tl.set(one('.tool-1'), { autoAlpha: 1 }, T5 + 0.2)
    type(tl, one('.tool-1 text'), '● Edit(…/mirrors/…/calc.py)', T5 + 0.2)
    cam.beam(P.mirror, P.file, hue.work, T5 + 1.0, { duration: 1.1, bend: narrow.value ? -0.3 : 0.2, burst: 16 })
    tl.to(one('.code-old'), { autoAlpha: 0, y: -6, duration: 0.35 }, T5 + 2.0)
    tl.fromTo(one('.code-new'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.45, ease: 'cine.out' }, T5 + 2.15)
    pop(tl, one('.mark'), T5 + 2.4)
    const END = T5 + 3.4
    // The still frame: everything at work, the edit landed, the container still up.
    tl.addLabel('rest', END - 0.2)
    tl.to(q('.exec-path, .exec-name, .term, .mount, .mount-note'), { autoAlpha: 0, duration: 0.5 }, END)
    tl.to(one('.ctr'), { autoAlpha: 0, scale: 0.9, duration: 0.8, ease: 'cine.in' }, END + 0.3)
    tl.to(q('.taken'), { x: 0, y: 0, duration: 1.0, ease: 'cine', stagger: 0.1 }, END + 0.5)
    tl.to(q('.cell-0, .cell-1, .mem-0'), { autoAlpha: 1, duration: 0.3 }, END + 1.4)
    tl.set(q('.taken'), { autoAlpha: 0 }, END + 1.5)
    rise(tl, q('.gone'), END + 1.2, { y: 6, stagger: 0.2 })
    rise(tl, one('.stays'), END + 1.6, { y: 6 })
    cam.flare(P.dir, hue.ok, END + 1.7, 20, 90)
    // A breath of secondary motion over the whole loop: the mount's dashes keep flowing.
    tl.fromTo(one('.flow-dash'), { strokeDashoffset: 0 }, { strokeDashoffset: -120, duration: END + 6, ease: 'none' }, 0)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, END + 5.4)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="45 / 83"
    label="A container per environment. The line hmz exec -f boxed -e box=docker@gpubox/home/me/myproject names the role (box), the backend (docker), the saved daemon (gpubox) and the directory (/home/me/myproject). The daemon gpubox, saved to hand out 4 CPUs and 8G, starts a container for the role from its image, python:3.12-slim, with exactly the CPUs and memory the role declares, here 2 CPUs and 4G. The directory on the daemon's host is mounted into the container at the same path. The agent's CLI runs on this machine by default, its harness here, since the image has no CLI and the daemon's affinity is blank; it works in a mirror of the directory kept under ~/.hmz/envs/mirrors/. Each command it runs, such as hostname, lands in the container through docker exec, and prints the container's id. Its edit lands in /home/me/myproject. When the run ends the container goes, its share goes back to the daemon, and the work stays in the directory."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <pattern id="ce-dots" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" class="grid-dot" />
        </pattern>
      </defs>
      <g class="far"><rect x="-400" y="-400" :width="L.w + 800" :height="L.h + 800" fill="url(#ce-dots)" /></g>

      <g class="world">
        <!-- The line. -->
        <g class="cmd">
          <rect class="card" :x="L.cmd.x" :y="L.cmd.y" :width="L.cmd.w" :height="L.cmd.h" rx="10" />
          <rect
            v-for="(piece, i) in PIECES.filter((p) => p.part >= 0)"
            :key="`hl${i}`"
            class="hl"
            :class="`hl-${piece.part}`"
            :style="{ '--c': `var(${LANE_OF[piece.part]})` }"
            :x="textX + piece.col * CW - 2"
            :y="lineY(1) - 13"
            :width="pieceW(piece.text) + 4"
            height="18"
            rx="4"
          />
          <text class="cmd-line prompt" :x="textX" :y="lineY(0)">$ hmz exec -f boxed</text>
        </g>
        <g v-for="(piece, i) in PIECES" :key="i" class="piece">
          <text class="mono12" :class="{ strong: piece.part >= 0 }" :x="textX + piece.col * CW" :y="lineY(1)">{{ piece.text }}</text>
        </g>
        <g v-for="(name, k) in PART_NAMES" :key="name" :class="`brace-${k}`" :style="{ '--c': `var(${LANE_OF[k]})` }">
          <path class="brace-path" :d="braceOf(k).d" />
          <g class="brace-label"><text class="brace-word" :x="braceOf(k).cx" :y="braceOf(k).ly" text-anchor="middle">{{ name }}</text></g>
        </g>

        <!-- The daemon. -->
        <g class="dmn">
          <rect class="card dmn-card" :x="L.dmn.x" :y="L.dmn.y" :width="L.dmn.w" :height="L.dmn.h" rx="12" />
          <text class="name" :x="L.dmn.x + 12" :y="L.dmn.y + 22">gpubox</text>
          <text class="dim" :x="L.dmn.x + 66" :y="L.dmn.y + 22">a saved docker daemon</text>
        </g>
        <g class="pool"><text class="dim" :x="L.dmn.x + 12" :y="L.dmn.y + 49">hands out</text></g>
        <rect v-for="i in [0, 1, 2, 3]" :key="`c${i}`" class="cell" :class="`cell-${i}`" :x="poolCell(i).x" :y="poolCell(i).y" :width="CELL" :height="CELL" rx="3" />
        <g class="mem">
          <rect class="mem-out" :x="poolMem.x" :y="poolMem.y" width="80" :height="CELL" rx="3" />
          <rect class="mem-fill mem-0" :x="poolMem.x" :y="poolMem.y" width="40" :height="CELL" rx="3" />
          <rect class="mem-fill" :x="poolMem.x + 40" :y="poolMem.y" width="40" :height="CELL" rx="3" />
        </g>
        <g class="pool"><text class="dim strong" :x="poolMem.x + 86" :y="L.dmn.y + 49">8G</text></g>

        <!-- The container. -->
        <g class="ctr">
          <rect class="ctr-frame" :x="ctr.x" :y="ctr.y" :width="ctr.w" :height="ctr.h" rx="10" />
          <g class="ctr-head">
            <text class="name" :x="ctr.x + 12" :y="ctr.y + 20">container</text>
            <text class="mono11 dim" :x="ctr.x + ctr.w - 12" :y="ctr.y + 20" text-anchor="end">python:3.12-slim</text>
          </g>
          <g class="ctr-res"><text class="dim" :x="ctr.x + 100" :y="ctr.y + 41">what box declares</text></g>
          <g class="term">
            <rect class="term-box" :x="ctr.x + 12" :y="ctr.y + 52" :width="ctr.w - 24" height="36" rx="6" />
            <text class="mono11 term-line" :x="ctr.x + 20" :y="ctr.y + 67">$ hostname</text>
            <text class="mono11 term-out" :x="ctr.x + 20" :y="ctr.y + 82">14a684eac2e0</text>
          </g>
          <g class="mount-path">
            <path class="folder" :d="`M${ctr.x + 12} ${ctr.y + 100} q0 -4 4 -4 h40 l6 4 h${ctr.w - 78} q4 0 4 4 v24 q0 4 -4 4 h${-(ctr.w - 32)} q-4 0 -4 -4 z`" />
            <text class="mono11 strong" :x="ctr.x + 22" :y="ctr.y + 117">/home/me/myproject</text>
          </g>
          <g :transform="`translate(${ctr.x + ctr.w / 2} ${ctr.y + 112})`">
            <rect class="mount-ring" :x="-(ctr.w - 24) / 2" y="-16" :width="ctr.w - 24" height="32" rx="6" />
          </g>
        </g>
        <!-- The role's share, as it moves from the daemon into the container and back. -->
        <rect v-for="i in [0, 1]" :key="`t${i}`" class="taken cell-taken" :x="poolCell(i).x" :y="poolCell(i).y" :width="CELL" :height="CELL" rx="3" />
        <g class="taken">
          <rect class="mem-taken" :x="poolMem.x" :y="poolMem.y" width="40" :height="CELL" rx="3" />
          <text class="chip-word" :x="poolMem.x + 20" :y="poolMem.y + 11" text-anchor="middle">4G</text>
        </g>

        <!-- The directory on the daemon's host, and its mount. -->
        <path class="mount flow-dash" :d="`M${ctr.x + 40} ${host.y - 2} L${ctr.x + 40} ${ctr.y + ctr.h - 10}`" />
        <g class="mount-note"><text class="note" :x="ctr.x + 50" :y="host.y - 12">mounted at the same path</text></g>
        <g class="host">
          <path class="folder host-box" :d="`M${host.x} ${host.y + 6} q0 -6 6 -6 h60 l8 6 h${host.w - 80} q6 0 6 6 v${host.h - 12} q0 6 -6 6 h${-(host.w - 12)} q-6 0 -6 -6 z`" />
          <text class="dim" :x="host.x + host.w - 12" :y="host.y + 20" text-anchor="end">on gpubox's host</text>
          <text class="mono12 strong" :x="host.x + 12" :y="host.y + 38">/home/me/myproject</text>
          <text class="mono11 dim" :x="host.x + 12" :y="host.y + 60">calc.py</text>
          <g class="code-old"><text class="mono11 minus" :x="host.x + 76" :y="host.y + 60">return a - b</text></g>
          <g class="code-new"><text class="mono11 plus" :x="host.x + 76" :y="host.y + 60">return a + b</text></g>
          <g class="mark"><text class="mark-word" :x="host.x + host.w - 12" :y="host.y + 60" text-anchor="end">edited</text></g>
        </g>

        <!-- This machine. -->
        <g class="mach">
          <rect class="card" :x="L.mach.x" :y="L.mach.y" :width="L.mach.w" :height="L.mach.h" rx="12" />
          <text class="name" :x="L.mach.x + 12" :y="L.mach.y + 22">this machine</text>
        </g>
        <g class="chip">
          <rect class="chip-bg" :x="L.mach.x + 12" :y="L.mach.y + 32" :width="L.mach.w - 24" height="28" rx="7" />
          <text class="chip-word" :x="L.mach.x + 24" :y="L.mach.y + 50">claude: coder's harness runs here</text>
          <g :transform="`translate(${L.mach.x + L.mach.w / 2} ${L.mach.y + 46})`">
            <rect class="chip-ring" :x="-(L.mach.w - 24) / 2" y="-14" :width="L.mach.w - 24" height="28" rx="7" />
          </g>
        </g>
        <g class="aff"><text class="dim" :x="L.mach.x + 12" :y="L.mach.y + 78">affinity blank: the image has no CLI,</text></g>
        <g class="aff"><text class="dim" :x="L.mach.x + 12" :y="L.mach.y + 93">so the CLI runs here, with your sign-in</text></g>
        <g class="mirror">
          <rect class="mirror-box" :x="L.mach.x + 12" :y="L.mach.y + 102" :width="L.mach.w - 24" height="42" rx="7" />
          <text class="mono11 strong" :x="L.mach.x + 22" :y="L.mach.y + 119">~/.hmz/envs/mirrors/</text>
          <text class="mono11 dim" :x="L.mach.x + 22" :y="L.mach.y + 135">…/731d95dbbabe/calc.py</text>
          <text v-if="!narrow" class="note" :x="L.mach.x + L.mach.w - 22" :y="L.mach.y + 119" text-anchor="end">a mirror</text>
        </g>
        <g class="tool tool-0"><text class="mono11" :x="L.mach.x + 12" :y="L.mach.y + 166"></text></g>
        <g class="tool tool-1"><text class="mono11" :x="L.mach.x + 12" :y="L.mach.y + 186"></text></g>

        <!-- docker exec. -->
        <path class="exec-path" :d="exec.d" />
        <g class="exec-name">
          <rect class="exec-bg" :x="exec.mid.x - 40" :y="exec.mid.y - 11" width="80" height="18" rx="9" />
          <text class="exec-word" :x="exec.mid.x" :y="exec.mid.y + 2" text-anchor="middle">docker exec</text>
        </g>

        <!-- When the run ends. -->
        <g class="gone"><text class="note" :x="ctr.x + ctr.w / 2" :y="ctr.y + ctr.h / 2 - 4" text-anchor="middle">the run ended: the container is gone,</text></g>
        <g class="gone"><text class="note" :x="ctr.x + ctr.w / 2" :y="ctr.y + ctr.h / 2 + 12" text-anchor="middle">its 2 CPUs and 4G back with gpubox</text></g>
        <g class="stays"><text class="ok-word" :x="ctr.x + 50" :y="host.y - 12">the work stays in the directory</text></g>
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

.dmn-card {
  stroke: color-mix(in srgb, var(--hmz-lane-3) 55%, var(--hmz-stage-line));
}

.mono11,
.mono12,
.cmd-line {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.mono12,
.cmd-line {
  font-size: 12px;
}

.strong {
  font-weight: 700;
}

.prompt {
  fill: var(--hmz-stage-dim);
}

.hl {
  fill: color-mix(in srgb, var(--c) 20%, transparent);
}

.brace-path {
  fill: none;
  stroke: var(--c);
  stroke-width: 1.4;
  stroke-linecap: round;
}

.brace-word {
  font-size: 12px;
  font-style: italic;
  fill: var(--c);
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

.mono11.dim {
  font-family: var(--vp-font-family-mono);
}

.note {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.cell {
  fill: color-mix(in srgb, var(--hmz-lane-3) 30%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-3);
  stroke-width: 1;
}

.mem-out {
  fill: none;
  stroke: var(--hmz-lane-2);
  stroke-width: 1;
}

.mem-fill {
  fill: color-mix(in srgb, var(--hmz-lane-2) 30%, var(--hmz-stage-card));
}

.cell-taken {
  fill: var(--hmz-lane-3);
}

.mem-taken {
  fill: var(--hmz-lane-2);
}

.ctr-frame {
  fill: color-mix(in srgb, var(--hmz-lane-3) 7%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-3);
  stroke-width: 1.6;
}

.term-box {
  fill: color-mix(in srgb, var(--hmz-stage-ink) 6%, var(--vp-c-bg));
  stroke: var(--hmz-stage-line);
}

.term-out {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.folder {
  fill: color-mix(in srgb, var(--hmz-warm) 9%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
  stroke-width: 1.3;
}

.mount-ring {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2;
}

.mount {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 1.6;
  stroke-dasharray: 5 4;
}

.minus {
  fill: var(--vp-c-danger-1);
}

.plus {
  fill: var(--hmz-accent);
  font-weight: 700;
}

.mark-word,
.ok-word {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
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

.mirror-box {
  fill: color-mix(in srgb, var(--hmz-warm) 6%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
  stroke-width: 1.1;
  stroke-dasharray: 4 3;
}

.exec-path {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.6;
  stroke-dasharray: 5 4;
}

.exec-bg {
  fill: var(--vp-c-bg);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.2;
}

.exec-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-lane-1);
}
</style>
