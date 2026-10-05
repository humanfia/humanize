<script setup lang="ts">
// Where each thing an anchored agent does lands, played out. The routing is
// `src/hmz/coganchor/policy.py` and `supervisor.py`: the agent runs here, unchanged; files in
// the workspace are read and written through a local copy of the target, and an edited file is
// pushed to the target whole before any command runs there; creating, removing, renaming and
// mode changes are replayed on the target first; programs the agent spawns, and their
// connections, run on the target; the agent's own runtime, state directory, credentials and
// connections (its model provider) stay here. The file names and test counts are invented.
//
// The paper under it is a plane whose origin is the anchor, drifting at a third of the
// camera's pace. The command that crosses glides into the terminal's title, and the exit
// status it ends with flies home whole onto the agent; a current runs across the anchor while
// the scene plays.
import { computed, ref, useId } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, type, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'
import { rig, type Point, type Shot } from '../motion/camera'
import ScenePlane from './scene/ScenePlane.vue'
import { drawPlane, glide } from './scene/plane'

const BEATS = [
  'The agent runs here, unchanged',
  'Its files: a local copy, local speed',
  'An edit crosses whole, before any command',
  'Commands and their network run there',
  'Its account and keys stay here',
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
  here: Box
  there: Box
  /** The anchor: a column between the two machines, or a band between them on a phone. */
  anchor: { x1: number; y1: number; x2: number; y2: number }
  agent: Box
  vault: Box
  mirror: Box
  ws: Box
  term: Box
  provider: Point
  pypi: Point
  pill: number
  paths: { cmdIn: string; cmdOut: string; file: string }
  fileFrom: Point
  fileTo: Point
  shots: Record<'open' | 'files' | 'cross' | 'cmd' | 'keys', Partial<Shot>>
  stamp: Point
  /** Where the anchor's name sits on it. */
  word: Point
  stampW: number
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  here: { x: 16, y: 52, w: 284, h: 290 },
  there: { x: 340, y: 52, w: 284, h: 290 },
  anchor: { x1: 320, y1: 66, x2: 320, y2: 328 },
  agent: { x: 98, y: 92, w: 120, h: 64 },
  vault: { x: 32, y: 230, w: 116, h: 96 },
  mirror: { x: 164, y: 230, w: 120, h: 96 },
  ws: { x: 356, y: 230, w: 120, h: 96 },
  term: { x: 356, y: 78, w: 252, h: 110 },
  provider: { x: 158, y: 24 },
  pypi: { x: 482, y: 24 },
  pill: 124,
  paths: {
    cmdIn: 'M218 124 C 262 124, 292 150, 320 150',
    cmdOut: 'M320 150 C 336 150, 344 96, 392 96',
    file: 'M224 270 C 270 196, 370 196, 416 270',
  },
  fileFrom: { x: 224, y: 270 },
  fileTo: { x: 416, y: 270 },
  shots: {
    open: { x: 158, y: 124, s: 1.9 },
    files: { x: 210, y: 214, s: 1.3 },
    cross: { x: 320, y: 232, s: 1.5 },
    cmd: { x: 470, y: 150, s: 1.4 },
    keys: { x: 170, y: 180, s: 1.3 },
  },
  stamp: { x: 320, y: 342 },
  word: { x: 320, y: 197 },
  stampW: 330,
}

const NARROW: Layout = {
  w: 360,
  h: 440,
  here: { x: 10, y: 40, w: 340, h: 170 },
  there: { x: 10, y: 248, w: 340, h: 162 },
  anchor: { x1: 24, y1: 229, x2: 336, y2: 229 },
  // Left of the middle, to leave "this machine" its corner on the narrowest phones.
  agent: { x: 112, y: 50, w: 116, h: 58 },
  vault: { x: 22, y: 116, w: 150, h: 86 },
  mirror: { x: 188, y: 116, w: 150, h: 86 },
  ws: { x: 206, y: 282, w: 132, h: 86 },
  term: { x: 22, y: 282, w: 172, h: 118 },
  provider: { x: 170, y: 18 },
  pypi: { x: 180, y: 426 },
  pill: 124,
  paths: {
    cmdIn: 'M170 108 C 170 150, 180 200, 180 229',
    cmdOut: 'M180 229 C 150 250, 90 262, 60 294',
    file: 'M263 156 C 360 190, 360 290, 272 322',
  },
  fileFrom: { x: 263, y: 156 },
  fileTo: { x: 272, y: 322 },
  shots: {
    open: { x: 170, y: 80, s: 1.8 },
    files: { x: 180, y: 170, s: 1.2 },
    cross: { x: 260, y: 234, s: 1.3 },
    cmd: { x: 150, y: 330, s: 1.3 },
    keys: { x: 172, y: 110, s: 1.25 },
  },
  stamp: { x: 180, y: 229 },
  word: { x: 262, y: 229 },
  stampW: 320,
}

const FILES = ['src/pay.py', 'build/', 'tests/']
const KEYS = ['sign-in', 'API keys', 'state']

const id = useId()
const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const rowY = (b: Box, i: number) => b.y + 44 + i * 18
const anchorMid = computed(() => ({ x: (L.value.anchor.x1 + L.value.anchor.x2) / 2, y: (L.value.anchor.y1 + L.value.anchor.y2) / 2 }))

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
    const c = {
      here: () => palette.lane[0],
      there: () => palette.accent,
      warm: () => palette.warm,
      cmd: () => palette.lane[2],
      danger: () => palette.danger,
    }
    const agentC = { x: l.agent.x + l.agent.w / 2, y: l.agent.y + l.agent.h / 2 }
    const status = one('.status')
    const row = (b: Box, i: number) => ({ x: b.x + 22, y: rowY(b, i) - 4 })

    // Clean slate for every loop.
    tl.set(at('.frame, .frame-lit, .anchor-line'), { drawSVG: '0%' }, 0)
    tl.set(at('.frame-lit'), { autoAlpha: 0 }, 0)
    tl.set(at('.machine-name, .pill, .card, .anchor-word, .stamp, .chip, .packet, .dot, .strike, .row-flash, .out, .exit, .glint'), { autoAlpha: 0 }, 0)
    tl.set(at('.row'), { autoAlpha: 1 }, 0)
    tl.set(at('.strike'), { drawSVG: '0%' }, 0)
    tl.set(at('.halo'), { autoAlpha: 0, scale: 0.7, transformOrigin: '50% 50%' }, 0)
    tl.set(at('.term-title'), { text: '' }, 0)
    tl.set(status, { text: 'idle' }, 0)
    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.anchor-flow'), { autoAlpha: 0 }, 0)
    drawPlane(tl, q, 0.2, { duration: 2.4 })

    // 0 · the agent, alone, close; then the camera pulls back to show two machines.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.agent-in'), { scale: 0.8, autoAlpha: 0, transformOrigin: '50% 50%' }, { scale: 1, autoAlpha: 1, duration: 0.9, ease: 'back.out(1.6)' }, 0.1)
    tl.to(one('.agent-halo'), { autoAlpha: 1, scale: 1, duration: 1.2 }, 0.2)
    cam.shot({ x: l.w / 2, y: l.h / 2, s: 1 }, 1.1, 2.2)
    tl.to(at('.frame'), { drawSVG: '100%', duration: 1.6, stagger: 0.25, ease: 'cine' }, 1.2)
    tl.to(at('.machine-name'), { autoAlpha: 1, duration: 0.6, stagger: 0.25 }, 2.0)
    tl.to(one('.anchor-line'), { drawSVG: '100%', duration: 1.0, ease: 'cine' }, 2.1)
    tl.to(one('.anchor-word'), { autoAlpha: 1, duration: 0.5 }, 2.6)
    tl.to(at('.anchor-flow'), { autoAlpha: 1, duration: 0.6 }, 3.1)
    tl.fromTo(at('.card'), { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.6, stagger: 0.1 }, 2.3)
    tl.fromTo(at('.pill'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.6, stagger: 0.15 }, 2.7)

    // 1 · files: reads from the local copy, at local speed; an edit stays local for now; a
    // removal lands on the target first, and only then on the copy.
    const T1 = 3.6
    tl.addLabel('beat-1', T1)
    cam.shot(l.shots.files, T1, 1.4)
    type(tl, status, 'read pay.py', T1 + 0.2, 30)
    cam.beam({ x: agentC.x, y: l.agent.y + l.agent.h }, row(l.mirror, 0), c.here, T1 + 0.5, { duration: 0.3, bend: 0.1 })
    cam.beam(row(l.mirror, 0), { x: agentC.x, y: l.agent.y + l.agent.h }, c.here, T1 + 0.8, { duration: 0.3, bend: 0.1 })
    tl.fromTo(at('.mirror .row-flash')[0], { autoAlpha: 0 }, { autoAlpha: 0.9, duration: 0.15, yoyo: true, repeat: 1 }, T1 + 0.7)
    type(tl, status, 'edit pay.py', T1 + 1.3, 30)
    tl.fromTo(at('.mirror .dot.warm')[0], { autoAlpha: 0, scale: 0, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4, ease: 'back.out(3)' }, T1 + 1.8)
    cam.flare(row(l.mirror, 0), c.warm, T1 + 1.8, 10, 50)
    type(tl, status, 'rm build/', T1 + 2.3, 30)
    cam.beam({ x: agentC.x, y: l.agent.y + l.agent.h }, row(l.ws, 1), c.danger, T1 + 2.7, { duration: 0.7, bend: narrow.value ? -0.3 : 0.25, burst: 12 })
    tl.set(at('.ws .strike')[1], { autoAlpha: 1 }, T1 + 3.3)
    tl.to(at('.ws .strike')[1], { drawSVG: '100%', duration: 0.3 }, T1 + 3.3)
    tl.to(at('.ws .row')[1], { autoAlpha: 0.3, duration: 0.4 }, T1 + 3.5)
    tl.set(at('.mirror .strike')[1], { autoAlpha: 1 }, T1 + 3.8)
    tl.to(at('.mirror .strike')[1], { drawSVG: '100%', duration: 0.3 }, T1 + 3.8)
    tl.to(at('.mirror .row')[1], { autoAlpha: 0.3, duration: 0.4 }, T1 + 4.0)

    // 2 · a command is on its way: it waits at the anchor while the edited file crosses whole.
    const T2 = T1 + 4.6
    tl.addLabel('beat-2', T2)
    type(tl, status, 'pytest -q', T2, 30)
    const chip = one('.chip')
    tl.set(chip, { autoAlpha: 1 }, T2 + 0.3)
    tl.fromTo(chip, { x: agentC.x, y: agentC.y }, { duration: 0.9, ease: 'cine', motionPath: { path: l.paths.cmdIn }, onUpdate: cam.trail(chip, c.cmd) }, T2 + 0.3)
    cam.shot(l.shots.cross, T2 + 0.4, 1.4)
    tl.to(one('.anchor-halo'), { autoAlpha: 1, scale: 1, duration: 0.5 }, T2 + 1.1)
    tl.fromTo(one('.chip-in'), { scale: 1 }, { scale: 1.12, duration: 0.35, yoyo: true, repeat: 3, ease: 'sine.inOut', transformOrigin: '50% 50%' }, T2 + 1.2)
    const packet = one('.packet')
    tl.set(packet, { x: l.fileFrom.x, y: l.fileFrom.y, autoAlpha: 0 }, 0)
    tl.to(packet, { autoAlpha: 1, duration: 0.25 }, T2 + 1.2)
    tl.fromTo(one('.packet-in'), { scale: 1, transformOrigin: '50% 50%' }, { scale: 1.2, duration: 0.3, ease: 'back.out(3)' }, T2 + 1.2)
    tl.to(packet, { duration: 1.2, ease: 'cine', motionPath: { path: l.paths.file }, onUpdate: cam.trail(packet, c.warm, 3) }, T2 + 1.5)
    tl.to(one('.packet-in'), { scale: 1, duration: 0.3 }, T2 + 2.4)
    tl.to(packet, { autoAlpha: 0, duration: 0.25 }, T2 + 2.75)
    cam.flare(l.fileTo, c.warm, T2 + 2.7, 26, 110)
    tl.fromTo(at('.ws .row-flash')[0], { autoAlpha: 0 }, { autoAlpha: 0.9, duration: 0.2, yoyo: true, repeat: 1 }, T2 + 2.7)
    tl.fromTo(at('.ws .dot.warm')[0], { autoAlpha: 0, scale: 0, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(3)' }, T2 + 2.7)
    // In step: both copies turn the same colour.
    tl.to(at('.dot.warm'), { autoAlpha: 0, duration: 0.4 }, T2 + 3.2)
    tl.fromTo(at('.dot.even'), { autoAlpha: 0, scale: 0.4, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4, stagger: 0.1 }, T2 + 3.2)
    tl.to(one('.anchor-halo'), { autoAlpha: 0, duration: 0.5 }, T2 + 3.3)

    // 3 · the command runs on the target; what it starts reaches the network from there; its
    // output and exit status come back to the agent as if it were a local child.
    const T3 = T2 + 3.8
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.cmd, T3, 1.4)
    tl.to(chip, { duration: 0.6, ease: 'cine', motionPath: { path: l.paths.cmdOut }, onUpdate: cam.trail(chip, c.cmd) }, T3 + 0.1)
    tl.to(chip, { autoAlpha: 0, duration: 0.2 }, T3 + 0.7)
    cam.flare({ x: l.term.x + 36, y: l.term.y + 14 }, c.cmd, T3 + 0.7, 14, 70)
    tl.set(one('.term-lit'), { autoAlpha: 0 }, 0)
    tl.to(one('.term-lit'), { autoAlpha: 1, duration: 0.4 }, T3 + 0.7)
    // The command that crossed is the one the terminal runs: its name glides into the title.
    const landed = l.paths.cmdOut.trim().split(/[ ,]+/).slice(-2).map(Number)
    glide(tl, null, one('.term-head'), landed[0] - (l.term.x + 44), landed[1] - (l.term.y + 14), T3 + 0.65, { duration: 0.6 })
    type(tl, one('.term-title'), 'pytest -q', T3 + 0.8, 26)
    tl.fromTo(at('.out'), { autoAlpha: 0, x: -6 }, { autoAlpha: 1, x: 0, duration: 0.35, stagger: 0.35 }, T3 + 1.3)
    cam.beam({ x: l.pypi.x, y: narrow.value ? l.term.y + l.term.h : l.term.y }, l.pypi, c.there, T3 + 1.7, { duration: 0.6, bend: 0.15, burst: 16 })
    cam.beam(l.pypi, { x: l.pypi.x + 8, y: narrow.value ? l.term.y + l.term.h : l.term.y }, c.there, T3 + 2.3, { duration: 0.6, bend: 0.15 })
    tl.fromTo(one('.pypi-lit'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3, yoyo: true, repeat: 1, repeatDelay: 0.4 }, T3 + 2.2)
    tl.fromTo(one('.exit'), { autoAlpha: 0, scale: 1.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(2)' }, T3 + 2.9)
    cam.shot({ x: l.w / 2, y: l.h / 2, s: 1 }, T3 + 3.0, 1.4)
    cam.beam({ x: l.term.x, y: l.term.y + l.term.h - 16 }, { x: l.agent.x + l.agent.w, y: agentC.y }, c.cmd, T3 + 3.1, { duration: 1.0, bend: narrow.value ? 0.3 : -0.25, burst: 14 })
    // And what it ended with goes home whole: the same words, onto the agent.
    const home = { x: agentC.x, y: agentC.y + 12 }
    const from = { x: l.term.x + l.term.w - 38, y: l.term.y + l.term.h - 18 }
    glide(tl, null, one('.exit-home'), from.x - home.x, from.y - home.y, T3 + 3.1, { duration: 1 })
    tl.to(one('.exit-home'), { autoAlpha: 0, duration: 0.2 }, T3 + 4.0)
    type(tl, status, 'exit 0', T3 + 4.0, 20)

    // 4 · what stays here: the agent's sign-in, its keys, its state, and its own connection to
    // its model provider.
    const T4 = T3 + 4.6
    tl.addLabel('beat-4', T4)
    cam.shot(l.shots.keys, T4, 1.4)
    tl.to(one('.frame-lit'), { autoAlpha: 1, duration: 0.2 }, T4 + 0.3)
    tl.to(one('.frame-lit'), { drawSVG: '100%', duration: 1.4, ease: 'cine' }, T4 + 0.3)
    tl.to(one('.vault-halo'), { autoAlpha: 1, scale: 1, duration: 0.8 }, T4 + 0.5)
    tl.fromTo(at('.key-row'), { x: 0 }, { keyframes: { x: [0, 4, 0] }, duration: 0.4, stagger: 0.18 }, T4 + 0.6)
    tl.fromTo(at('.glint'), { autoAlpha: 0, scale: 0.3, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.3, stagger: 0.18, yoyo: true, repeat: 1 }, T4 + 0.6)
    const up = { x: l.provider.x, y: l.agent.y }
    const top = { x: l.provider.x, y: l.provider.y + 12 }
    for (let i = 0; i < 3; i += 1) {
      cam.beam({ x: up.x - 6, y: up.y }, top, c.here, T4 + 1.0 + i * 0.5, { duration: 0.5, bend: 0.3 })
      cam.beam(top, { x: up.x + 6, y: up.y }, c.here, T4 + 1.25 + i * 0.5, { duration: 0.5, bend: 0.3 })
    }
    tl.fromTo(one('.provider-lit'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4 }, T4 + 1.2)
    type(tl, status, 'asks its model', T4 + 1.0, 30)

    // The key frame: both machines, and what went where.
    const T5 = T4 + 3.2
    cam.shot({ x: l.w / 2, y: l.h / 2, s: 1 }, T5, 1.4)
    if (narrow.value) tl.to(one('.anchor-word'), { autoAlpha: 0, duration: 0.3 }, T5 + 1.0)
    tl.fromTo(one('.stamp'), { autoAlpha: 0, scale: 1.3, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.6, ease: 'back.out(1.5)' }, T5 + 1.1)
    cam.flare(l.stamp, c.there, T5 + 1.2, 30, 140)
    tl.addLabel('rest', T5 + 1.9)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T5 + 4.4)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 11"
    label="An anchored agent. The agent runs on this machine, unchanged. It reads and edits a local copy of the target's workspace; removing a directory happens on the target first. When it runs a command, the edited file crosses to the target whole before the command runs there. The command, and its network traffic, run on the target; its output and exit status come back to the agent. The agent's sign-in, keys, state and its connection to its model provider stay on this machine."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <radialGradient :id="`${id}-halo-here`">
          <stop offset="0" stop-color="var(--hmz-lane-1)" stop-opacity="0.5" />
          <stop offset="1" stop-color="var(--hmz-lane-1)" stop-opacity="0" />
        </radialGradient>
        <radialGradient :id="`${id}-halo-warm`">
          <stop offset="0" stop-color="var(--hmz-warm)" stop-opacity="0.45" />
          <stop offset="1" stop-color="var(--hmz-warm)" stop-opacity="0" />
        </radialGradient>
        <radialGradient :id="`${id}-halo-there`">
          <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.6" />
          <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
        </radialGradient>
      </defs>

      <g class="far">
        <ScenePlane :key="`plane-${narrow}`" :w="L.w" :h="L.h" :ox="anchorMid.x" :oy="anchorMid.y" :step="44" :bleed="320" />
      </g>

      <g class="world">
        <!-- The two machines. -->
        <rect class="frame here" :x="L.here.x" :y="L.here.y" :width="L.here.w" :height="L.here.h" rx="18" />
        <rect class="frame-lit" :x="L.here.x" :y="L.here.y" :width="L.here.w" :height="L.here.h" rx="18" />
        <rect class="frame there" :x="L.there.x" :y="L.there.y" :width="L.there.w" :height="L.there.h" rx="18" />
        <text class="machine-name here" :x="narrow ? L.here.x + L.here.w - 12 : L.here.x + 14" :y="L.here.y + 20" :text-anchor="narrow ? 'end' : 'start'">this machine</text>
        <text class="machine-name there" :x="narrow ? L.there.x + L.there.w - 12 : L.there.x + 14" :y="L.there.y + 20" :text-anchor="narrow ? 'end' : 'start'">the target</text>

        <!-- The anchor between them. -->
        <g :transform="`translate(${anchorMid.x} ${anchorMid.y})`">
          <ellipse class="halo anchor-halo" :rx="narrow ? 170 : 44" :ry="narrow ? 40 : 150" :fill="`url(#${id}-halo-there)`" />
        </g>
        <line class="anchor-line" :x1="L.anchor.x1" :y1="L.anchor.y1" :x2="L.anchor.x2" :y2="L.anchor.y2" />
        <line class="anchor-flow" :x1="L.anchor.x1" :y1="L.anchor.y1" :x2="L.anchor.x2" :y2="L.anchor.y2" />
        <g class="anchor-word" :transform="`translate(${L.word.x} ${L.word.y})${narrow ? '' : ' rotate(-90)'}`">
          <rect :x="-34" y="-9" width="68" height="18" rx="9" />
          <text y="4" text-anchor="middle">anchor</text>
        </g>

        <!-- Outside: the model provider, reached from here; the network, reached from there. -->
        <g class="pill" :transform="`translate(${L.provider.x} ${L.provider.y})`">
          <rect :x="-L.pill / 2" y="-11" :width="L.pill" height="22" rx="11" />
          <rect class="provider-lit lit" :x="-L.pill / 2" y="-11" :width="L.pill" height="22" rx="11" />
          <text y="4" text-anchor="middle">model provider</text>
        </g>
        <g class="pill" :transform="`translate(${L.pypi.x} ${L.pypi.y})`">
          <rect :x="-L.pill / 2 + 20" y="-11" :width="L.pill - 40" height="22" rx="11" />
          <rect class="pypi-lit lit there" :x="-L.pill / 2 + 20" y="-11" :width="L.pill - 40" height="22" rx="11" />
          <text y="4" text-anchor="middle">pypi.org</text>
        </g>

        <!-- The agent. -->
        <g :transform="`translate(${L.agent.x + L.agent.w / 2} ${L.agent.y + L.agent.h / 2})`">
          <circle class="halo agent-halo" r="90" :fill="`url(#${id}-halo-here)`" />
          <g class="agent-in">
            <rect :x="-L.agent.w / 2" :y="-L.agent.h / 2" :width="L.agent.w" :height="L.agent.h" rx="14" class="agent-box" />
            <text class="agent-name" y="-5" text-anchor="middle">agent</text>
            <text class="status" y="16" text-anchor="middle">idle</text>
          </g>
        </g>

        <!-- Sign-in, keys, state: this machine's. -->
        <g class="card vault">
          <g :transform="`translate(${L.vault.x + L.vault.w / 2} ${L.vault.y + L.vault.h / 2})`">
            <circle class="halo vault-halo" r="80" :fill="`url(#${id}-halo-warm)`" />
          </g>
          <rect class="box" :x="L.vault.x" :y="L.vault.y" :width="L.vault.w" :height="L.vault.h" rx="10" />
          <text class="head" :x="L.vault.x + 10" :y="L.vault.y + 20">its account</text>
          <g v-for="(k, i) in KEYS" :key="k" class="key-row">
            <g :transform="`translate(${L.vault.x + 16} ${rowY(L.vault, i) - 4})`">
              <circle r="3.5" class="key-dot" />
              <circle class="glint" r="7" />
            </g>
            <text class="row-text" :x="L.vault.x + 26" :y="rowY(L.vault, i)">{{ k }}</text>
          </g>
        </g>

        <!-- The local copy here, and the workspace there: the same rows. -->
        <g v-for="(b, side) in [L.mirror, L.ws]" :key="side" class="card" :class="side ? 'ws' : 'mirror'">
          <rect class="box" :x="b.x" :y="b.y" :width="b.w" :height="b.h" rx="10" />
          <text class="head" :x="b.x + 10" :y="b.y + 20">{{ side ? 'workspace' : 'local copy' }}</text>
          <g v-for="(f, i) in FILES" :key="f">
            <rect class="row-flash" :x="b.x + 4" :y="rowY(b, i) - 13" :width="b.w - 8" height="17" rx="5" />
            <g class="row">
              <text class="row-text mono" :x="b.x + 12" :y="rowY(b, i)">{{ f }}</text>
              <line class="strike" :x1="b.x + 10" :x2="b.x + 18 + f.length * 6.6" :y1="rowY(b, i) - 4" :y2="rowY(b, i) - 4" />
            </g>
            <g v-if="i === 0" :transform="`translate(${b.x + b.w - 14} ${rowY(b, i) - 4})`">
              <circle class="dot warm" r="4" />
              <circle class="dot even" r="4" />
            </g>
          </g>
        </g>

        <!-- A terminal on the target. -->
        <g class="card term">
          <rect class="box" :x="L.term.x" :y="L.term.y" :width="L.term.w" :height="L.term.h" rx="10" />
          <rect class="box term-lit" :x="L.term.x" :y="L.term.y" :width="L.term.w" :height="L.term.h" rx="10" />
          <circle v-for="i in 3" :key="i" class="term-dot" :cx="L.term.x + 6 + i * 9" :cy="L.term.y + 14" r="2.6" />
          <g class="term-head"><text class="term-title mono" :x="L.term.x + 44" :y="L.term.y + 18" /></g>
          <g class="out"><text class="out-line mono" :x="L.term.x + 12" :y="L.term.y + 42">collected 42 items</text></g>
          <g class="out"><text class="out-line mono dim" :x="L.term.x + 12" :y="L.term.y + 60">{{ '.'.repeat(Math.floor((L.term.w - 24) / 8.2)) }}</text></g>
          <g class="out"><text class="out-line mono ok" :x="L.term.x + 12" :y="L.term.y + 78">42 passed</text></g>
          <g :transform="`translate(${L.term.x + L.term.w - 38} ${L.term.y + L.term.h - 18})`">
            <g class="exit">
              <rect x="-30" y="-10" width="60" height="20" rx="10" />
              <text y="4" text-anchor="middle">exit 0</text>
            </g>
          </g>
        </g>

        <!-- In flight: the command, and the edited file. -->
        <g class="chip">
          <g class="chip-in">
            <rect x="-30" y="-10" width="60" height="20" rx="10" />
            <text y="4" text-anchor="middle">pytest</text>
          </g>
        </g>
        <g class="packet">
          <g class="packet-in">
            <rect x="-30" y="-11" width="60" height="22" rx="5" />
            <text y="4" text-anchor="middle">pay.py</text>
          </g>
        </g>

        <g :transform="`translate(${L.agent.x + L.agent.w / 2} ${L.agent.y + L.agent.h / 2 + 12})`">
          <g class="exit-home">
            <rect x="-30" y="-10" width="60" height="20" rx="10" />
            <text y="4" text-anchor="middle">exit 0</text>
          </g>
        </g>

        <g :transform="`translate(${L.stamp.x} ${L.stamp.y})`">
          <g class="stamp">
            <rect :x="-L.stampW / 2" y="-15" :width="L.stampW" height="30" rx="15" />
            <text y="5" text-anchor="middle">work over there · account over here</text>
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

.mono {
  font-family: var(--vp-font-family-mono);
}

.halo {
  opacity: var(--hmz-glow);
}

.frame {
  fill: color-mix(in srgb, var(--hmz-lane-1) 5%, transparent);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.5;
}

.frame.there {
  fill: color-mix(in srgb, var(--hmz-accent) 5%, transparent);
}

.frame-lit {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2.5;
}

.machine-name {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.machine-name.here {
  fill: var(--hmz-lane-1);
}

/* Tighter on a phone, where "this machine" shares its row with the agent. */
@media (max-width: 640px) {
  .machine-name {
    letter-spacing: 0.04em;
  }
}

.machine-name.there {
  fill: var(--hmz-accent);
}

.anchor-line {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  stroke-dasharray: 4 5;
}

/* The current across the anchor, once it is up: running while the scene plays. */
.anchor-flow {
  stroke: var(--hmz-accent);
  stroke-width: 3;
  stroke-dasharray: 1 17;
  stroke-linecap: round;
  animation: syscalls-flow 1.8s linear infinite paused;
}

.screen.running .anchor-flow {
  animation-play-state: running;
}

@keyframes syscalls-flow {
  to {
    stroke-dashoffset: -36;
  }
}

.anchor-word rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
}

.anchor-word text {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  fill: var(--hmz-accent);
}

.pill rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
}

.pill rect.lit {
  fill: color-mix(in srgb, var(--hmz-lane-1) 22%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-1);
  opacity: 0;
}

.pill rect.lit.there {
  fill: color-mix(in srgb, var(--hmz-accent) 22%, var(--hmz-stage-card));
  stroke: var(--hmz-accent);
}

.pill text {
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.agent-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
}

.agent-name {
  font-size: 16px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.status {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  fill: var(--hmz-lane-1);
}

.box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.term-lit {
  fill: none;
  stroke: var(--hmz-lane-3);
  stroke-width: 1.8;
}

.head {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.row-text {
  font-size: 11.5px;
  fill: var(--hmz-stage-ink);
}

.row-flash {
  fill: color-mix(in srgb, var(--hmz-lane-1) 25%, transparent);
}

.ws .row-flash {
  fill: color-mix(in srgb, var(--hmz-warm) 28%, transparent);
}

.strike {
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
}

.dot.warm {
  fill: var(--hmz-warm);
}

.dot.even {
  fill: var(--hmz-accent);
}

.key-dot {
  fill: var(--hmz-warm);
}

.glint {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 1.5;
}

.term-dot {
  fill: var(--hmz-stage-line);
}

.term-title {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-lane-3);
}

.out-line {
  font-size: 11.5px;
  fill: var(--hmz-stage-ink);
}

.out-line.dim {
  fill: var(--hmz-accent);
  letter-spacing: 0.05em;
}

.out-line.ok {
  font-weight: 700;
  fill: var(--hmz-accent);
}

.exit rect,
.exit-home rect {
  fill: color-mix(in srgb, var(--hmz-accent) 20%, var(--hmz-stage-card));
  stroke: var(--hmz-accent);
}

.exit-home {
  visibility: hidden;
}

.exit text,
.exit-home text,
.chip text {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.chip rect {
  fill: color-mix(in srgb, var(--hmz-lane-3) 25%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-3);
  stroke-width: 1.5;
}

.packet rect {
  fill: color-mix(in srgb, var(--hmz-warm) 25%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
  stroke-width: 1.5;
}

.packet text {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.stamp rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
}

.stamp text {
  font-size: 14px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}
</style>
