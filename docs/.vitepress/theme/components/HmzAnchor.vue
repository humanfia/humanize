<script setup lang="ts">
// An agent on your machine whose work lands on another one. The routes are the default
// arrangement in `specs/coganchor/SPEC.md` and `reference/remote-execution`: the project's
// files, the commands and whatever those commands reach are the target's; the agent's own link
// to its model provider, its settings and its login stay here. The agent reads and writes a
// local copy of the target's workspace, which humanize keeps in step with it.
//
// Two drawings of the same thing: side by side where there is room, and one above the other on
// a phone, where the side-by-side one would shrink its words out of legibility.
//
// What crosses is what lands: the edit's words glide into the label it leaves on the file, the
// command's into the line the terminal types, and the exit status that comes home settles on
// the agent as the same words. Every wire is drawn on, then carries a current while the scene
// plays.
import { computed, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, fly, streak, type, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'
import ScenePlane from './scene/ScenePlane.vue'
import { drawPlane, glide } from './scene/plane'

const BEATS = [
  'The agent runs here, unchanged',
  'Its edits land over there',
  'Its commands run over there',
  'So does what those commands fetch',
  'Its login and model stay here',
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
  mine: Box
  theirs: Box
  mineTitle: { x: number; y: number }
  theirsTitle: { x: number; y: number; end?: boolean }
  model: Box
  agent: Box
  copy: Box
  login: Box
  files: Box
  commands: Box
  network: Box
  hub: { x: number; y: number }
  toFiles: string
  toCommands: string
  toNetwork: string
  /** Where the wires leave this machine: what comes home along them lands here. */
  out: { x: number; y: number }
  /** The agent's own wire to its model provider, which never crosses. */
  toModel: string
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  mine: { x: 20, y: 56, w: 214, h: 276 },
  theirs: { x: 406, y: 56, w: 214, h: 276 },
  mineTitle: { x: 28, y: 44 },
  theirsTitle: { x: 612, y: 44, end: true },
  model: { x: 36, y: 72, w: 182, h: 42 },
  agent: { x: 36, y: 136, w: 182, h: 52 },
  copy: { x: 36, y: 206, w: 182, h: 40 },
  login: { x: 36, y: 274, w: 182, h: 42 },
  files: { x: 422, y: 72, w: 182, h: 58 },
  commands: { x: 422, y: 146, w: 182, h: 104 },
  network: { x: 422, y: 266, w: 182, h: 50 },
  hub: { x: 320, y: 162 },
  toFiles: 'M 218 162 C 300 162 320 101 422 101',
  toCommands: 'M 218 162 C 300 162 330 198 422 198',
  toNetwork: 'M 513 250 L 513 266',
  out: { x: 218, y: 162 },
  toModel: 'M 200 136 C 200 124 200 124 200 114',
}

const NARROW: Layout = {
  w: 360,
  h: 560,
  mine: { x: 14, y: 36, w: 332, h: 208 },
  theirs: { x: 14, y: 330, w: 332, h: 216 },
  mineTitle: { x: 20, y: 26 },
  theirsTitle: { x: 20, y: 320 },
  model: { x: 28, y: 50, w: 146, h: 42 },
  login: { x: 186, y: 50, w: 146, h: 42 },
  agent: { x: 28, y: 110, w: 304, h: 52 },
  copy: { x: 28, y: 178, w: 304, h: 40 },
  files: { x: 28, y: 344, w: 146, h: 62 },
  network: { x: 186, y: 344, w: 146, h: 62 },
  commands: { x: 28, y: 420, w: 304, h: 112 },
  hub: { x: 180, y: 287 },
  toFiles: 'M 180 244 C 180 290 101 300 101 344',
  toCommands: 'M 180 244 C 180 310 180 380 180 420',
  toNetwork: 'M 259 420 L 259 406',
  out: { x: 180, y: 244 },
  toModel: 'M 101 110 C 101 103 101 99 101 92',
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined
const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const mid = (b: Box) => ({ x: b.x + b.w / 2, y: b.y + b.h / 2 })

const scene = useScene({
  still: 'rest',
  repeatDelay: 0.8,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    const get = () => fx
    const world = q('.cam')[0]
    const one = (sel: string) => q(sel)[0]
    const agent = mid(l.agent)
    const model = mid(l.model)
    const login = mid(l.login)
    const mine = mid(l.mine)

    tl.set(q('.theirs, .wire, .hub, .shield, .copy-tick'), { autoAlpha: 0 }, 0)
    tl.set(q('.term-line'), { text: '' }, 0)
    tl.set(q('.lit'), { autoAlpha: 0 }, 0)
    drawPlane(tl, q, 0, { duration: 2.2 })

    // 0 · close on this machine: the agent, talking to its model as it always does.
    tl.addLabel('beat-0', 0)
    tl.fromTo(world, { scale: narrow.value ? 1.35 : 1.7, transformOrigin: `${(mine.x / l.w) * 100}% ${(mine.y / l.h) * 100}%`, autoAlpha: 0 }, { autoAlpha: 1, duration: 0.6, ease: 'none' }, 0)
    tl.fromTo(q('.mine-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.4, ease: 'cine' }, 0)
    tl.fromTo(q('.mine .item'), { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.6, stagger: 0.12 }, 0.3)
    // Its own wire to its model: drawn here, and it stays here.
    tl.fromTo(q('.model-wire'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.6, ease: 'cine' }, 0.9)
    tl.fromTo(q('.model-flow'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, 1.5)
    streak(tl, get, agent, model, () => palette.accent, 1.1, { duration: 0.5, bend: 0.3, burst: 8 })
    streak(tl, get, model, agent, () => palette.accent, 1.7, { duration: 0.5, bend: 0.3 })

    // 1 · the camera pulls back to show where the work is, and an edit crosses whole.
    const T1 = 2.4
    tl.addLabel('beat-1', T1)
    tl.to(world, { scale: 1, duration: 1.8, ease: 'cine' }, T1)
    tl.to(q('.theirs'), { autoAlpha: 1, duration: 0.4 }, T1 + 0.3)
    tl.fromTo(q('.theirs-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.3, ease: 'cine' }, T1 + 0.3)
    tl.fromTo(q('.theirs .item'), { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.6, stagger: 0.12 }, T1 + 0.7)
    tl.to(q('.wire, .hub'), { autoAlpha: 1, duration: 0.3 }, T1 + 1)
    tl.fromTo(q('.wire'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.9, ease: 'cine', stagger: 0.1 }, T1 + 1)
    tl.fromTo(q('.wire-flow'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, T1 + 2)
    fly(tl, one('.p-edit'), one('.path-files') as SVGPathElement, T1 + 2, { duration: 1.1, fx: get, color: palette.lane[0] })
    tl.call(() => fx?.spark(mid(l.files).x, mid(l.files).y, palette.lane[0], 22, 110), [], T1 + 3.1)
    tl.fromTo(q('.files .lit'), { autoAlpha: 1 }, { autoAlpha: 0, duration: 1.2 }, T1 + 3.1)
    // The edit that crossed is the label it leaves: its words glide into place on the file.
    const filesIn = { x: l.files.x, y: l.files.y + 29 }
    const doneAt = { x: l.files.x + l.files.w - 12 - 30, y: l.files.y + 38 }
    glide(tl, null, one('.done'), filesIn.x - doneAt.x, filesIn.y - doneAt.y, T1 + 3.05, { duration: 0.8 })
    tl.to(q('.copy-tick'), { autoAlpha: 1, duration: 0.3 }, T1 + 3.2)
    tl.fromTo(q('.copy .lit'), { autoAlpha: 1 }, { autoAlpha: 0, duration: 1.2 }, T1 + 3.2)

    // 2 · a command goes across, runs there, and its exit status comes home.
    const T2 = T1 + 3.8
    tl.addLabel('beat-2', T2)
    fly(tl, one('.p-run'), one('.path-commands') as SVGPathElement, T2, { duration: 1, fx: get, color: palette.lane[1] })
    // The command that crossed is the line the terminal runs.
    const cmdIn = { x: l.commands.x, y: l.commands.y + l.commands.h / 2 }
    glide(tl, null, one('.line-1'), cmdIn.x - (l.commands.x + 12), cmdIn.y - (l.commands.y + 38), T2 + 0.95, { duration: 0.7 })
    type(tl, one('.term-1'), '$ pytest -q', T2 + 1, 26)
    tl.fromTo(q('.commands .lit'), { autoAlpha: 1 }, { autoAlpha: 0, duration: 1 }, T2 + 1)
    type(tl, one('.term-2'), '12 passed in 3.1s', T2 + 1.8, 40)
    fly(tl, one('.p-back'), one('.path-commands') as SVGPathElement, T2 + 2.4, { duration: 1, fx: get, color: palette.lane[1], reverse: true })
    // What came home is what the agent is told: the same words, settling onto it.
    const badge = { x: l.agent.x + l.agent.w - 34, y: l.agent.y }
    glide(tl, null, one('.exit'), l.out.x - badge.x, l.out.y - badge.y, T2 + 3.3, { duration: 0.7 })
    tl.call(() => fx?.spark(agent.x, agent.y, palette.lane[1], 16, 90), [], T2 + 3.4)

    // 3 · what the command reaches for, the target reaches for.
    const T3 = T2 + 4
    tl.addLabel('beat-3', T3)
    type(tl, one('.term-3'), '$ pip install numpy', T3, 30)
    streak(tl, get, { x: l.network.x + l.network.w / 2, y: l.commands.y + l.commands.h - 6 }, mid(l.network), () => palette.lane[2], T3 + 0.7, { duration: 0.5, bend: narrow.value ? 0 : 0.4, burst: 12 })
    tl.fromTo(q('.network .lit'), { autoAlpha: 1 }, { autoAlpha: 0, duration: 1.2 }, T3 + 1.2)
    tl.fromTo(q('.globe'), { rotation: 0 }, { rotation: 360, svgOrigin: '0 0', duration: 2.2, ease: 'cine' }, T3 + 0.9)
    tl.addLabel('rest', T3 + 1.8)

    // 4 · and what is the agent's own stays with it: a shield goes up round the login and
    // the model link, and the other machine fades back.
    const T4 = T3 + 2.4
    tl.addLabel('beat-4', T4)
    tl.to(q('.theirs, .wire, .wire-flow, .hub'), { autoAlpha: 0.3, duration: 0.8 }, T4)
    tl.to(q('.shield'), { autoAlpha: 1, duration: 0.2 }, T4 + 0.2)
    tl.fromTo(q('.shield'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.2, ease: 'cine', stagger: 0.15 }, T4 + 0.2)
    tl.fromTo(q('.model .lit, .login .lit'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5, yoyo: true, repeat: 3 }, T4 + 0.5)
    streak(tl, get, agent, login, () => palette.warm, T4 + 0.6, { duration: 0.5, bend: -0.35, burst: 8 })
    streak(tl, get, agent, model, () => palette.accent, T4 + 1.1, { duration: 0.5, bend: 0.35, burst: 8 })
    tl.to(world, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 3.6)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    :mobile-ratio="`${NARROW.w} / ${NARROW.h}`"
    label="Two machines. On this machine: the agent, its link to its model provider, its login, and a local copy of the workspace kept in step. On the target: the project's files, the commands the agent runs, and the network those commands reach. An edit crosses to the target whole, a test run happens there and its exit status comes back, and pip install downloads from the target. The login and the model link never leave this machine."
  >
    <div class="layer cam">
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <linearGradient id="anchor-wire" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="var(--hmz-lane-1)" />
          <stop offset="1" stop-color="var(--hmz-accent)" />
        </linearGradient>
      </defs>
      <ScenePlane :key="`plane-${narrow}`" :w="L.w" :h="L.h" :step="narrow ? 28 : 32" />
      <g class="world">
        <!-- this machine -->
        <path class="model-wire" :d="L.toModel" />
        <path class="flow model-flow" :d="L.toModel" />
        <g class="mine">
          <rect class="frame mine-frame" :x="L.mine.x" :y="L.mine.y" :width="L.mine.w" :height="L.mine.h" rx="14" />
          <text class="title" :x="L.mineTitle.x" :y="L.mineTitle.y">this machine</text>
          <rect class="shield" :x="L.model.x - 5" :y="L.model.y - 5" :width="L.model.w + 10" :height="L.model.h + 10" rx="14" />
          <rect class="shield" :x="L.login.x - 5" :y="L.login.y - 5" :width="L.login.w + 10" :height="L.login.h + 10" rx="14" />
          <g class="item model">
            <rect class="box" :x="L.model.x" :y="L.model.y" :width="L.model.w" :height="L.model.h" rx="10" />
            <rect class="lit" :x="L.model.x" :y="L.model.y" :width="L.model.w" :height="L.model.h" rx="10" />
            <path class="icon" :transform="`translate(${L.model.x + 20} ${L.model.y + L.model.h / 2})`" d="M -8 5 h 15 a 5 5 0 0 0 0 -10 a 7 7 0 0 0 -13 -1 a 5 5 0 0 0 -2 11 z" />
            <text class="name" :x="L.model.x + 38" :y="L.model.y + L.model.h / 2 + 4">model link</text>
          </g>
          <g class="item agent">
            <rect class="box hero" :x="L.agent.x" :y="L.agent.y" :width="L.agent.w" :height="L.agent.h" rx="12" />
            <circle class="core" :cx="L.agent.x + 24" :cy="L.agent.y + L.agent.h / 2" r="9" />
            <text class="name big" :x="L.agent.x + 44" :y="L.agent.y + L.agent.h / 2 - 3">the agent</text>
            <text class="sub" :x="L.agent.x + 44" :y="L.agent.y + L.agent.h / 2 + 13">no plugin, no setting</text>
            <g :transform="`translate(${L.agent.x + L.agent.w - 34} ${L.agent.y})`">
              <g class="exit">
                <rect x="-24" y="-11" width="48" height="22" rx="11" />
                <text y="4" text-anchor="middle">exit 0</text>
              </g>
            </g>
          </g>
          <g class="item copy">
            <rect class="box ghost" :x="L.copy.x" :y="L.copy.y" :width="L.copy.w" :height="L.copy.h" rx="10" />
            <rect class="lit" :x="L.copy.x" :y="L.copy.y" :width="L.copy.w" :height="L.copy.h" rx="10" />
            <g class="icon" :transform="`translate(${L.copy.x + 20} ${L.copy.y + L.copy.h / 2})`">
              <rect x="-7" y="-8" width="11" height="13" rx="2" />
              <rect x="-3" y="-4" width="11" height="13" rx="2" />
            </g>
            <text class="name" :x="L.copy.x + 38" :y="L.copy.y + L.copy.h / 2 + 4">local copy</text>
            <text class="copy-tick" :x="L.copy.x + L.copy.w - 14" :y="L.copy.y + L.copy.h / 2 + 4" text-anchor="end">in step ✓</text>
          </g>
          <g class="item login">
            <rect class="box" :x="L.login.x" :y="L.login.y" :width="L.login.w" :height="L.login.h" rx="10" />
            <rect class="lit warm" :x="L.login.x" :y="L.login.y" :width="L.login.w" :height="L.login.h" rx="10" />
            <g class="icon key" :transform="`translate(${L.login.x + 20} ${L.login.y + L.login.h / 2})`">
              <circle cx="-4" r="5" />
              <path d="M 1 0 h 9 M 7 0 v 4 M 10 0 v 3" />
            </g>
            <text class="name" :x="L.login.x + 38" :y="L.login.y + L.login.h / 2 + 4">login, keys</text>
          </g>
        </g>

        <!-- between them -->
        <path class="wire path-files" :d="L.toFiles" />
        <path class="wire path-commands" :d="L.toCommands" />
        <path class="flow wire-flow" :d="L.toFiles" />
        <path class="flow wire-flow" :d="L.toCommands" />
        <g class="hub" :transform="`translate(${L.hub.x} ${L.hub.y})`">
          <rect x="-40" y="-11" width="80" height="22" rx="11" />
          <text y="4" text-anchor="middle">humanize</text>
        </g>

        <!-- the target -->
        <g class="theirs">
          <rect class="frame theirs-frame" :x="L.theirs.x" :y="L.theirs.y" :width="L.theirs.w" :height="L.theirs.h" rx="14" />
          <text class="title" :x="L.theirsTitle.x" :y="L.theirsTitle.y" :text-anchor="L.theirsTitle.end ? 'end' : 'start'">the target</text>
          <g class="item files">
            <rect class="box" :x="L.files.x" :y="L.files.y" :width="L.files.w" :height="L.files.h" rx="10" />
            <rect class="lit" :x="L.files.x" :y="L.files.y" :width="L.files.w" :height="L.files.h" rx="10" />
            <text class="label" :x="L.files.x + 12" :y="L.files.y + 18">files</text>
            <text class="mono" :x="L.files.x + 12" :y="L.files.y + 42">kernel.cu</text>
            <g class="done"><text :x="L.files.x + L.files.w - 12" :y="L.files.y + 42" text-anchor="end">edited ✓</text></g>
          </g>
          <g class="item commands">
            <rect class="box term" :x="L.commands.x" :y="L.commands.y" :width="L.commands.w" :height="L.commands.h" rx="10" />
            <rect class="lit" :x="L.commands.x" :y="L.commands.y" :width="L.commands.w" :height="L.commands.h" rx="10" />
            <text class="label" :x="L.commands.x + 12" :y="L.commands.y + 18">commands</text>
            <g class="line-1"><text class="mono term-line term-1" :x="L.commands.x + 12" :y="L.commands.y + 42" /></g>
            <text class="mono term-line term-2 ok" :x="L.commands.x + 12" :y="L.commands.y + 62" />
            <text class="mono term-line term-3" :x="L.commands.x + 12" :y="L.commands.y + 84" />
          </g>
          <g class="item network">
            <rect class="box" :x="L.network.x" :y="L.network.y" :width="L.network.w" :height="L.network.h" rx="10" />
            <rect class="lit violet" :x="L.network.x" :y="L.network.y" :width="L.network.w" :height="L.network.h" rx="10" />
            <g :transform="`translate(${L.network.x + 22} ${L.network.y + L.network.h / 2})`">
              <g class="globe">
                <circle r="10" />
                <ellipse rx="4.5" ry="10" />
                <line x1="-10" x2="10" />
              </g>
            </g>
            <text class="name" :x="L.network.x + 42" :y="L.network.y + L.network.h / 2 + 4">network</text>
          </g>
        </g>

        <!-- what crosses -->
        <g class="packet p-edit">
          <rect x="-34" y="-11" width="68" height="22" rx="6" />
          <text y="4" text-anchor="middle">edit ✎</text>
        </g>
        <g class="packet p-run">
          <rect x="-34" y="-11" width="68" height="22" rx="6" />
          <text y="4" text-anchor="middle">pytest</text>
        </g>
        <g class="packet p-back">
          <rect x="-34" y="-11" width="68" height="22" rx="6" />
          <text y="4" text-anchor="middle">exit 0</text>
        </g>
      </g>
    </svg>
    <canvas ref="canvas" />
    </div>
  </HmzStage>
</template>

<style scoped>

/* The camera moves this layer, so the light on the canvas moves with the drawing under it. The
   drawing runs past its edges, so the paper under it is still there when the camera pulls back. */
.cam svg {
  overflow: visible;
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

.frame {
  fill: var(--hmz-stage-card);
  fill-opacity: 0.45;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.5;
}

.title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
}

.box.hero {
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
}

.box.ghost {
  stroke-dasharray: 4 3;
}

.box.term {
  fill: color-mix(in srgb, var(--hmz-lane-2) 8%, var(--hmz-stage-card));
}

.lit {
  fill: color-mix(in srgb, var(--hmz-lane-1) 30%, transparent);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.5;
}

.commands .lit {
  fill: color-mix(in srgb, var(--hmz-lane-2) 22%, transparent);
  stroke: var(--hmz-lane-2);
}

.model .lit,
.copy .lit {
  fill: color-mix(in srgb, var(--hmz-accent) 22%, transparent);
  stroke: var(--hmz-accent);
}

.lit.warm {
  fill: color-mix(in srgb, var(--hmz-warm) 25%, transparent);
  stroke: var(--hmz-warm);
}

.lit.violet {
  fill: color-mix(in srgb, var(--hmz-lane-3) 25%, transparent);
  stroke: var(--hmz-lane-3);
}

.core {
  fill: var(--hmz-accent);
}

.icon,
.icon rect,
.icon circle,
.icon path {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.icon.key circle,
.icon.key path {
  stroke: var(--hmz-warm);
}

.copy .icon rect:last-child {
  fill: var(--hmz-stage-card);
}

.name {
  font-size: 13px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.name.big {
  font-size: 15px;
}

.sub {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.mono {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  fill: var(--hmz-stage-ink);
}

.term .mono,
.commands .mono {
  fill: var(--hmz-stage-ink);
}

.mono.ok,
.done text,
.copy-tick {
  fill: var(--hmz-accent);
  font-weight: 600;
}

.done text,
.copy-tick {
  font-size: 11.5px;
}

.exit rect {
  fill: var(--hmz-accent);
}

.exit text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-bg);
}

/* The agent's line to its model. */
.model-wire {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  stroke-linecap: round;
}

/* The current along a wire once it is drawn, running while the scene plays: a path of its
   own, so it never fights the stroke that drew the wire on. */
.flow {
  fill: none;
  stroke: var(--hmz-stage-card);
  stroke-width: 1.4;
  stroke-dasharray: 2 9;
  stroke-linecap: round;
  animation: anchor-flow 1.4s linear infinite paused;
}

:global(.screen.running) .flow {
  animation-play-state: running;
}

@keyframes anchor-flow {
  to {
    stroke-dashoffset: -14;
  }
}

.wire {
  fill: none;
  stroke: url(#anchor-wire);
  stroke-width: 2.5;
  opacity: 0.8;
}

.hub rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
}

.hub text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-accent);
}

.packet {
  visibility: hidden;
}

.packet rect {
  fill: var(--hmz-lane-1);
}

.p-run rect,
.p-back rect {
  fill: var(--hmz-lane-2);
}

.packet text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-bg);
}

.globe circle,
.globe ellipse,
.globe line {
  fill: none;
  stroke: var(--hmz-lane-3);
  stroke-width: 1.5;
}

.shield {
  fill: color-mix(in srgb, var(--hmz-warm) 10%, transparent);
  stroke: var(--hmz-warm);
  stroke-width: 1.5;
}
</style>
