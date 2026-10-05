<script setup lang="ts">
// A run of a flow, simulated, as the opening scene of the features landing: the flow at the
// top, one node per agent it declares, a turn going out to an agent as a beam of light and its
// answer coming back, and every call each agent makes landing on one timeline underneath, the
// way a collected trace lands them in Perfetto.
//
// What is held to the code: each flow's roles are the ones it declares in its own source,
// every agent is spelled the way `hmz exec -a` takes it (role=cli/model:effort,
// with the effort on that CLI's ladder in `coganchor/backends.py`), and who takes a turn after
// whom is the flow's own order. What is invented: the calls, their lengths, and the models.
//
// Drawn the way a lecture draws it: the squared paper first, the flow's loop in one stroke, a
// wire out of it to every agent, and each agent's name carried down to its row of the
// timeline, so the row is visibly the same agent. A turn is a flash of light down its wire and
// back up it; a current runs down every wire while the scene plays.
import { computed, nextTick, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, streak, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'
import ScenePlane from './scene/ScenePlane.vue'
import { drawPlane, glide } from './scene/plane'

interface Lane {
  role: string
  agent: string
  tone: number
}

interface Play {
  name: string
  shape: string
  lanes: Lane[]
  /** Lanes side by side in one column (wide) or one row (narrow). */
  groups: number[][]
  first: number[]
  after: (lane: number) => number[]
}

const PLAYS: Play[] = [
  {
    name: 'ralph_loop',
    shape: 'one agent, a fresh session every round',
    lanes: [{ role: 'agent', agent: 'claude/claude-opus-5:high', tone: 1 }],
    groups: [[0]],
    first: [0],
    after: () => [0],
  },
  {
    name: 'flame_chase',
    shape: 'two agents taking turns on one tree',
    lanes: [
      { role: 'first_chaser', agent: 'claude/claude-opus-5:high', tone: 1 },
      { role: 'second_chaser', agent: 'codex/gpt-5.6-sol:high', tone: 2 },
    ],
    groups: [[0], [1]],
    first: [0],
    after: (lane) => [1 - lane],
  },
  {
    name: 'parallel_flame_chase',
    shape: 'a coordinator plans, then three lanes run at once',
    lanes: [
      { role: 'coordinator', agent: 'claude/claude-opus-5:max', tone: 6 },
      { role: 'lane_1_actor_a', agent: 'claude/claude-opus-5:high', tone: 1 },
      { role: 'lane_1_actor_b', agent: 'codex/gpt-5.6-sol:high', tone: 1 },
      { role: 'lane_2_actor_a', agent: 'kimi/kimi-code/k3:high', tone: 2 },
      { role: 'lane_2_actor_b', agent: 'grok/grok-4.6:high', tone: 2 },
      { role: 'lane_3_actor_a', agent: 'opencode/opencode/big-pickle:high', tone: 3 },
      { role: 'lane_3_actor_b', agent: 'mimo/mimo-v3:high', tone: 3 },
    ],
    groups: [[0], [1, 2], [3, 4], [5, 6]],
    first: [0],
    // The coordinator hands over to the three a's at once; inside a lane, a and b alternate.
    after: (lane) => (lane === 0 ? [1, 3, 5] : [lane % 2 ? lane + 1 : lane - 1]),
  },
]

const BEATS = ['Pick a flow', 'Every role, a coding agent of its own', 'Turns go out in the flow’s order', 'Every call, one timeline']

const RUN = 12 // seconds of run played
const INTRO = 3.2 // before the first turn goes out

interface Turn {
  lane: number
  t0: number
  t1: number
  calls: { t0: number; t1: number; kind: 'tool' | 'think' | 'say' }[]
}

function schedule(play: Play): Turn[] {
  let seed = 20260817 + play.lanes.length
  const rand = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff
  const turns: Turn[] = []
  const busy = play.lanes.map(() => 0)
  const queue: { lane: number; at: number }[] = play.first.map((lane) => ({ lane, at: 0.1 }))
  while (queue.length) {
    queue.sort((a, b) => a.at - b.at)
    const { lane, at } = queue.shift()!
    if (at >= RUN - 0.6 || busy[lane] > at) continue
    const long = play.lanes.length === 1 ? 3.6 : lane === 0 && play.lanes.length > 2 ? 2.2 : 2.6
    const t1 = Math.min(RUN, at + long * (0.75 + rand() * 0.5))
    const calls: Turn['calls'] = []
    let t = at + 0.1
    while (t < t1 - 0.25) {
      const roll = rand()
      const kind = roll < 0.55 ? 'tool' : roll < 0.85 ? 'think' : 'say'
      const end = Math.min(t1 - 0.05, t + 0.25 + rand() * 0.6)
      calls.push({ t0: t, t1: end, kind })
      t = end + 0.06
    }
    turns.push({ lane, t0: at, t1, calls })
    busy[lane] = t1
    for (const to of play.after(lane)) queue.push({ lane: to, at: t1 + 0.8 })
  }
  return turns
}

const picked = ref(2)
const play = computed(() => PLAYS[picked.value])
const turns = computed(() => schedule(play.value))

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined
const narrow = useNarrow(() => scene.rebuild())

// Where everything sits, in viewBox units.
const layout = computed(() => {
  const p = play.value
  if (!narrow.value) {
    const w = 640
    const cols = p.groups.length
    const colW = Math.min(150, (w - 40) / cols)
    const x0 = (w - colW * cols) / 2
    const nodes: { x: number; y: number }[] = []
    p.groups.forEach((g, c) =>
      g.forEach((lane, r) => {
        nodes[lane] = { x: x0 + c * colW + 18, y: g.length === 1 ? 164 : 144 + r * 42 }
      }),
    )
    return { w, h: 360, core: { x: 76, y: 60 }, nodes, strip: { x: 150, y: 232, w: 450, h: 92 }, label: 40 }
  }
  const w = 360
  const nodes: { x: number; y: number }[] = []
  p.groups.forEach((g, r) =>
    g.forEach((lane, c) => {
      nodes[lane] = { x: g.length === 1 ? 110 : 22 + c * 170, y: 132 + r * 42 }
    }),
  )
  const top = 132 + p.groups.length * 42 + 8
  return { w, h: top + 158, core: { x: 56, y: 54 }, nodes, strip: { x: 34, y: top, w: 310, h: 118 }, label: 22 }
})

const L = layout
const rowH = computed(() => L.value.strip.h / play.value.lanes.length)
const rowY = (i: number) => L.value.strip.y + rowH.value * (i + 0.5)
const sx = (t: number) => L.value.strip.x + (t / RUN) * L.value.strip.w
const short = (agent: string) => {
  const [cli] = agent.split('/')
  const effort = agent.split(':').pop()
  return `${cli} · ${effort}`
}
// The ticks of the timeline's clock, every three seconds of the run.
const TICKS = [0, 3, 6, 9, 12]
// Out of the bottom of the flow and into the top of an agent: the wire its turns go down.
const spoke = (i: number) => {
  const c = L.value.core
  const n = L.value.nodes[i]
  const y0 = c.y + 26
  return `M ${c.x} ${y0} C ${c.x} ${y0 + 46}, ${n.x} ${n.y - 54}, ${n.x} ${n.y - 13}`
}

const scene = useScene({
  still: 'rest',
  repeatDelay: 0.8,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    const get = () => fx
    const world = q('.cam')
    const pct = (x: number, y: number) => `${(x / l.w) * 100}% ${(y / l.h) * 100}%`
    const nodes = q('.node')
    const halos = q('.node-halo')
    const spokes = q('.spoke')
    const lit = q('.spoke-lit')
    const rows = q('.row-label')
    const tone = (lane: number) => () => palette.lane[play.value.lanes[lane].tone - 1]
    const core = l.core
    const name = q('.flow-name')[0]

    // 0 · the flow, close up, drawn on its squared paper; then the camera pulls back to show
    // whom it drives.
    tl.addLabel('beat-0', 0)
    tl.set(q('.call'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(halos, { autoAlpha: 0 }, 0)
    tl.set(q('.playhead'), { x: 0, autoAlpha: 0 }, 0)
    tl.set(lit, { drawSVG: '0% 0%' }, 0)
    drawPlane(tl, q, 0.1, { duration: 2 })
    tl.fromTo(world, { scale: 1.9, transformOrigin: pct(core.x, core.y + 20), autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: 2.6, ease: 'cine' }, 0)
    tl.fromTo(q('.core-ring'), { drawSVG: '50% 50%' }, { drawSVG: '0% 100%', duration: 1.2, ease: 'cine' }, 0.1)
    // The loop the flow is, drawn in one stroke: the arc, then its head.
    tl.fromTo(q('.core-loop'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.9, ease: 'cine' }, 0.45)
    tl.fromTo(q('.core-head'), { autoAlpha: 0, scale: 0.4, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(3)' }, 1.25)
    tl.set(name, { text: '' }, 0)
    tl.to(name, { text: { value: play.value.name }, duration: play.value.name.length / 30, ease: 'none' }, 0.45)
    tl.fromTo(q('.flow-shape'), { autoAlpha: 0, x: -8 }, { autoAlpha: 1, x: 0, duration: 0.7 }, 1)

    // 1 · the agents, one per role, each down a wire of its own; and their rows on the
    // timeline, each one's name carried down to it.
    tl.addLabel('beat-1', 1.4)
    tl.fromTo(spokes, { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.7, ease: 'cine', stagger: 0.09 }, 1.4)
    tl.fromTo(q('.spoke-flow'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.8 }, 2.4)
    nodes.forEach((node, i) => {
      const t = 1.4 + i * 0.09 + 0.55
      tl.fromTo(node, { autoAlpha: 0, scale: 0.3, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.55, ease: 'back.out(2.2)' }, t)
      tl.call(() => fx?.spark(l.nodes[i].x, l.nodes[i].y, tone(i)(), 8, 50), [], t)
    })
    tl.fromTo(q('.tag'), { autoAlpha: 0, x: -6 }, { autoAlpha: 1, x: 0, duration: 0.5, stagger: 0.04 }, 1.8)
    tl.fromTo(q('.strip-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.1, ease: 'cine' }, 2)
    tl.fromTo(q('.strip-title, .tick'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5, stagger: 0.05 }, 2.3)
    tl.fromTo(q('.row'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.8, ease: 'cine', stagger: 0.05 }, 2.4)
    rows.forEach((row, i) => {
      const n = l.nodes[i]
      // From the role's name beside its node (wide), or from the node itself (narrow), down to
      // its row: the same name, now the row's.
      const dx = narrow.value ? n.x - l.label : n.x + 18 - l.label
      const dy = narrow.value ? n.y - rowY(i) : n.y - 2 - (rowY(i) + 4)
      glide(tl, null, row, dx, dy, 2.4 + i * 0.06, { duration: 1 })
    })

    // 2 · the run: a flash down the wire to the agent whose turn it is, its calls landing on
    // its row, and its answer flashed back up to the flow, which hands over to whoever goes
    // next.
    tl.addLabel('beat-2', INTRO)
    tl.to(q('.playhead'), { autoAlpha: 1, duration: 0.3 }, INTRO)
    tl.to(q('.core-spin'), { rotation: 360 * 3, svgOrigin: '0 0', duration: RUN, ease: 'none' }, INTRO)
    tl.fromTo(q('.playhead'), { x: 0 }, { x: l.strip.w, duration: RUN, ease: 'none', immediateRender: false }, INTRO)
    const callEls = q('.call')
    let c = 0
    for (const turn of turns.value) {
      const at = INTRO + turn.t0
      const node = l.nodes[turn.lane]
      const wire = lit[turn.lane]
      // Out: a segment of light runs the length of the wire, head first.
      tl.fromTo(wire, { drawSVG: '0% 0%' }, { drawSVG: '0% 35%', duration: 0.12, ease: 'none', immediateRender: false }, at - 0.32)
      tl.to(wire, { drawSVG: '65% 100%', duration: 0.2, ease: 'none' }, at - 0.2)
      tl.to(wire, { drawSVG: '100% 100%', duration: 0.1, ease: 'none' }, at)
      streak(tl, get, { x: core.x, y: core.y + 26 }, node, tone(turn.lane), at - 0.4, { duration: 0.45, bend: 0.12, burst: 8 })
      tl.to(halos[turn.lane], { autoAlpha: 1, duration: 0.2 }, at)
      tl.to(halos[turn.lane], { autoAlpha: 0, duration: 0.3 }, INTRO + turn.t1)
      tl.fromTo(nodes[turn.lane], { scale: 1 }, { scale: 1.25, duration: 0.18, yoyo: true, repeat: 1, ease: 'power2.out', immediateRender: false }, at)
      for (const call of turn.calls) {
        tl.to(callEls[c], { scaleX: 1, duration: call.t1 - call.t0, ease: 'none' }, INTRO + call.t0)
        c += 1
      }
      // Back: the same light, running up the wire.
      const back = INTRO + turn.t1
      tl.fromTo(wire, { drawSVG: '100% 100%' }, { drawSVG: '65% 100%', duration: 0.12, ease: 'none', immediateRender: false }, back)
      tl.to(wire, { drawSVG: '0% 35%', duration: 0.22, ease: 'none' }, back + 0.12)
      tl.to(wire, { drawSVG: '0% 0%', duration: 0.12, ease: 'none' }, back + 0.34)
      streak(tl, get, node, { x: core.x, y: core.y + 26 }, tone(turn.lane), back, { duration: 0.45, bend: -0.12 })
    }

    // 3 · the camera goes down onto the trace as it fills, and back out to the whole.
    const T3 = INTRO + RUN * 0.55
    tl.addLabel('beat-3', T3)
    const sc = l.strip
    tl.to(world, { scale: narrow.value ? 1.15 : 1.35, transformOrigin: pct(sc.x + sc.w * 0.6, sc.y + sc.h / 2), duration: 1.6, ease: 'cine' }, T3)
    tl.to(world, { scale: 1, duration: 1.4, ease: 'cine' }, INTRO + RUN - 1.2)
    tl.addLabel('rest', INTRO + RUN + 0.5)
    tl.to(world, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, INTRO + RUN + 2.4)
  },
})

function pick(i: number) {
  if (picked.value === i) return
  picked.value = i
  void nextTick(() => scene.rebuild())
}

const label = computed(
  () =>
    `A simulated run of ${play.value.name}: ${play.value.shape}. Its agents are ${play.value.lanes
      .map((lane) => `${lane.role} on ${lane.agent}`)
      .join(', ')}. Each turn goes out from the flow to one agent, its calls land on that agent's row of one timeline, and its answer returns to the flow.`,
)
</script>

<template>
  <div class="orchestra">
    <div class="plays" role="group" aria-label="Which flow to play">
      <button v-for="(p, i) in PLAYS" :key="p.name" type="button" :class="{ on: picked === i }" :aria-pressed="picked === i" @click="pick(i)">
        {{ p.name }}
      </button>
    </div>
    <HmzStage :scene="scene" :beats="BEATS" :label="label" sim :mobile-ratio="`${L.w} / ${L.h}`">
      <div class="layer cam">
      <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
        <defs>
          <radialGradient v-for="n in 6" :id="`orchestra-halo-${n}`" :key="n">
            <stop offset="0" :stop-color="`var(--hmz-lane-${n})`" stop-opacity="0.8" />
            <stop offset="0.4" :stop-color="`var(--hmz-lane-${n})`" stop-opacity="0.35" />
            <stop offset="1" :stop-color="`var(--hmz-lane-${n})`" stop-opacity="0" />
          </radialGradient>
          <linearGradient id="orchestra-head" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0" />
            <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0.9" />
          </linearGradient>
        </defs>
        <ScenePlane :key="`plane-${narrow}`" :w="L.w" :h="L.h" :ox="L.core.x" :oy="L.core.y" :step="narrow ? 28 : 32" />
        <g class="world">
          <g v-for="(lane, i) in play.lanes" :key="`w-${play.name}-${lane.role}`">
            <path class="spoke" :d="spoke(i)" />
            <path class="spoke-flow" :d="spoke(i)" />
            <path class="spoke-lit" :d="spoke(i)" :style="{ stroke: `var(--hmz-lane-${lane.tone})` }" />
          </g>

          <g class="core" :transform="`translate(${L.core.x} ${L.core.y})`">
            <circle class="core-glow" r="46" />
            <circle class="core-ring" r="26" />
            <circle class="core-spin" r="33" />
            <path class="core-loop" d="M 9.9 -9.9 A 14 14 0 1 0 14 0" />
            <path class="core-head" d="M 14.6 -15.2 L 11.6 -4.6 L 4.4 -11.8 Z" />
            <g class="core-words">
              <text class="flow-name" x="44" y="-4">{{ play.name }}</text>
              <g v-if="!narrow" class="flow-shape"><text x="44" y="13">{{ play.shape }}</text></g>
            </g>
          </g>

          <g v-for="(lane, i) in play.lanes" :key="`${play.name}-${lane.role}`" :transform="`translate(${L.nodes[i].x} ${L.nodes[i].y})`">
            <circle class="node-halo" r="30" :fill="`url(#orchestra-halo-${lane.tone})`" />
            <g class="node">
              <circle r="11" :style="{ fill: `var(--hmz-lane-${lane.tone})` }" />
              <circle r="4" class="node-eye" />
            </g>
            <g class="tag">
              <text class="role" x="18" y="-2">{{ lane.role }}</text>
              <text class="spec" x="18" y="12">{{ short(lane.agent) }}</text>
            </g>
          </g>

          <g class="strip">
            <rect class="strip-frame" :x="L.label - 12" :y="L.strip.y - 20" :width="L.strip.x + L.strip.w - L.label + 22" :height="L.strip.h + 46" rx="10" />
            <text class="strip-title" :x="L.label" :y="L.strip.y - 7">one timeline</text>
            <g v-for="(lane, i) in play.lanes" :key="`row-${play.name}-${i}`">
              <line class="row" :x1="L.strip.x" :x2="L.strip.x + L.strip.w" :y1="rowY(i)" :y2="rowY(i)" />
              <g class="row-label">
                <circle v-if="narrow" :cx="L.label" :cy="rowY(i)" r="4.5" :style="{ fill: `var(--hmz-lane-${lane.tone})` }" />
                <text v-else :x="L.label" :y="rowY(i) + 4" :style="{ fill: `var(--hmz-lane-${lane.tone})` }">{{ lane.role }}</text>
              </g>
            </g>
            <g v-for="t in TICKS" :key="`t-${t}`" class="tick">
              <line :x1="sx(t)" :x2="sx(t)" :y1="L.strip.y + L.strip.h + 3" :y2="L.strip.y + L.strip.h + 8" />
              <text :x="sx(t)" :y="L.strip.y + L.strip.h + 20" :text-anchor="t === 0 ? 'start' : t === RUN ? 'end' : 'middle'">{{ t }}s</text>
            </g>
            <template v-for="(turn, t) in turns" :key="`turn-${picked}-${t}`">
              <rect
                v-for="(call, k) in turn.calls"
                :key="`c-${t}-${k}`"
                class="call"
                :class="call.kind"
                :x="sx(call.t0)"
                :y="L.strip.y + rowH * turn.lane + rowH * 0.18"
                :width="Math.max(2, sx(call.t1) - sx(call.t0))"
                :height="rowH * 0.64"
                rx="2"
                :style="{ fill: `var(--hmz-lane-${play.lanes[turn.lane].tone})` }"
              />
            </template>
            <g class="playhead">
              <rect :x="L.strip.x - 10" :y="L.strip.y - 2" width="10" :height="L.strip.h + 4" fill="url(#orchestra-head)" />
              <line :x1="L.strip.x" :x2="L.strip.x" :y1="L.strip.y - 4" :y2="L.strip.y + L.strip.h + 4" />
            </g>
          </g>
        </g>
      </svg>
      <canvas ref="canvas" />
      </div>
    </HmzStage>
  </div>
</template>

<style scoped>
/* The camera moves this layer, so the light on the canvas moves with the drawing under it. */
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

.orchestra {
  margin: 22px 0 30px;
}

.orchestra :deep(.hmz-stage) {
  margin: 0;
}

.plays {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.plays button {
  padding: 4px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  color: var(--vp-c-text-2);
  background: var(--vp-c-bg-soft);
  transition: all 0.2s;
}

.plays button:hover {
  color: var(--vp-c-text-1);
  border-color: var(--vp-c-brand-1);
}

.plays button.on {
  color: var(--vp-c-bg);
  background: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}

svg {
  font-family: var(--vp-font-family-base);
}

.spoke {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.5;
}

/* The current down every wire, once it is drawn: always flowing, while the scene plays. A
   path of its own, so the flow never fights the stroke that drew the wire on. */
.spoke-flow {
  fill: none;
  stroke: color-mix(in srgb, var(--hmz-stage-dim) 55%, transparent);
  stroke-width: 1.5;
  stroke-dasharray: 2 10;
  stroke-linecap: round;
  animation: orchestra-flow 1.6s linear infinite paused;
}

:global(.screen.running) .spoke-flow {
  animation-play-state: running;
}

@keyframes orchestra-flow {
  to {
    stroke-dashoffset: -16;
  }
}

.spoke-lit {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
}

.core-glow {
  fill: var(--hmz-accent);
  opacity: calc(0.12 * var(--hmz-glow));
}

.core-ring {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 2.5;
}

.core-spin {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
  stroke-dasharray: 10 14;
  opacity: 0.7;
}

.core-loop {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 3;
  stroke-linecap: round;
}

.core-head {
  fill: var(--hmz-accent);
}

.flow-name {
  font-family: var(--vp-font-family-mono);
  font-size: 15px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.flow-shape text {
  font-size: 12px;
  fill: var(--hmz-stage-dim);
}

.node-halo {
  opacity: var(--hmz-glow);
}

.node-eye {
  fill: var(--hmz-stage-card);
  opacity: 0.9;
}

.role {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.spec {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.strip-frame {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
}

.strip-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.row {
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 2 4;
}

.row-label text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
}

.tick line {
  stroke: var(--hmz-stage-dim);
}

.tick text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.call.think {
  opacity: 0.55;
}

.call.say {
  opacity: 0.8;
}

.playhead line {
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
}
</style>
