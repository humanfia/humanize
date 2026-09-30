<script setup lang="ts">
// A run of a flow, simulated, as the opening scene of the features landing: the flow at the
// top, one node per agent it declares, a turn going out to an agent as a beam of light and its
// answer coming back, and every call each agent makes landing on one timeline underneath, the
// way a collected trace lands them in Perfetto.
//
// What is held to the code: each flow's roles are the ones it declares in the official
// flowverse, every agent is spelled the way `hmz exec -a` takes it (role=cli/model:effort,
// with the effort on that CLI's ladder in `coganchor/backends.py`), and who takes a turn after
// whom is the flow's own order. What is invented: the calls, their lengths, and the models.
import { computed, nextTick, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, streak, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'

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
    for (const to of play.after(lane)) queue.push({ lane: to, at: t1 + 0.45 })
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
    return { w, h: 360, core: { x: 76, y: 60 }, nodes, strip: { x: 40, y: 236, w: 560, h: 96 } }
  }
  const w = 360
  const nodes: { x: number; y: number }[] = []
  p.groups.forEach((g, r) =>
    g.forEach((lane, c) => {
      nodes[lane] = { x: g.length === 1 ? 110 : 22 + c * 170, y: 132 + r * 42 }
    }),
  )
  const top = 132 + p.groups.length * 42 + 8
  return { w, h: top + 150, core: { x: 180, y: 58 }, nodes, strip: { x: 16, y: top, w: 328, h: 118 } }
})

const L = layout
const rowH = computed(() => L.value.strip.h / play.value.lanes.length)
const sx = (t: number) => L.value.strip.x + (t / RUN) * L.value.strip.w
const short = (agent: string) => {
  const [cli] = agent.split('/')
  const effort = agent.split(':').pop()
  return `${cli} · ${effort}`
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
    const tone = (lane: number) => () => palette.lane[play.value.lanes[lane].tone - 1]
    const core = l.core

    // 0 · the flow, close up, then the camera pulls back to show whom it drives.
    tl.addLabel('beat-0', 0)
    tl.set(q('.call'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(halos, { autoAlpha: 0 }, 0)
    tl.set(q('.playhead'), { x: 0 }, 0)
    tl.fromTo(world, { scale: 1.9, transformOrigin: pct(core.x, core.y + 20), autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: 2.6, ease: 'cine' }, 0)
    tl.fromTo(q('.core-ring'), { drawSVG: '50% 50%' }, { drawSVG: '0% 100%', duration: 1.2, ease: 'cine' }, 0.1)
    tl.fromTo(q('.core-words'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.8 }, 0.5)

    // 1 · the agents, one per role, each on its own CLI.
    tl.addLabel('beat-1', 1.3)
    tl.fromTo(nodes, { autoAlpha: 0, scale: 0.3, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.6, ease: 'back.out(2.2)', stagger: 0.09 }, 1.3)
    tl.fromTo(q('.strip'), { autoAlpha: 0, y: 20 }, { autoAlpha: 1, y: 0, duration: 0.9 }, 1.9)

    // 2 · the run: a beam out to the agent whose turn it is, its calls landing on its row,
    // and its answer beamed back to the flow, which hands over to whoever goes next.
    tl.addLabel('beat-2', INTRO)
    tl.to(q('.core-spin'), { rotation: 360 * 3, svgOrigin: '0 0', duration: RUN, ease: 'none' }, INTRO)
    tl.fromTo(q('.playhead'), { x: 0 }, { x: l.strip.w, duration: RUN, ease: 'none' }, INTRO)
    const callEls = q('.call')
    let c = 0
    for (const turn of turns.value) {
      const at = INTRO + turn.t0
      const node = l.nodes[turn.lane]
      streak(tl, get, { x: core.x, y: core.y + 26 }, node, tone(turn.lane), at - 0.35, { duration: 0.45, bend: 0.12, burst: 8 })
      tl.to(halos[turn.lane], { autoAlpha: 1, duration: 0.2 }, at)
      tl.to(halos[turn.lane], { autoAlpha: 0, duration: 0.3 }, INTRO + turn.t1)
      tl.fromTo(nodes[turn.lane], { scale: 1 }, { scale: 1.25, duration: 0.18, yoyo: true, repeat: 1, ease: 'power2.out' }, at)
      for (const call of turn.calls) {
        tl.to(callEls[c], { scaleX: 1, duration: call.t1 - call.t0, ease: 'none' }, INTRO + call.t0)
        c += 1
      }
      streak(tl, get, node, { x: core.x, y: core.y + 26 }, tone(turn.lane), INTRO + turn.t1, { duration: 0.45, bend: -0.12 })
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
        <g class="world">
          <g class="core" :transform="`translate(${L.core.x} ${L.core.y})`">
            <circle class="core-glow" r="46" />
            <circle class="core-ring" r="26" />
            <circle class="core-spin" r="33" />
            <text class="core-glyph" y="6" text-anchor="middle">↻</text>
            <g class="core-words">
              <text class="flow-name" :x="narrow ? 0 : 44" :y="narrow ? 50 : -4" :text-anchor="narrow ? 'middle' : 'start'">{{ play.name }}</text>
              <text v-if="!narrow" class="flow-shape" x="44" y="13">{{ play.shape }}</text>
            </g>
          </g>

          <g v-for="(lane, i) in play.lanes" :key="`${play.name}-${lane.role}`" :transform="`translate(${L.nodes[i].x} ${L.nodes[i].y})`">
            <circle class="node-halo" r="30" :fill="`url(#orchestra-halo-${lane.tone})`" />
            <g class="node">
              <circle r="11" :style="{ fill: `var(--hmz-lane-${lane.tone})` }" />
              <circle r="4" class="node-eye" />
            </g>
            <text class="role" x="18" y="-2">{{ lane.role }}</text>
            <text class="spec" x="18" y="12">{{ short(lane.agent) }}</text>
          </g>

          <g class="strip">
            <rect class="strip-frame" :x="L.strip.x - 8" :y="L.strip.y - 20" :width="L.strip.w + 16" :height="L.strip.h + 28" rx="10" />
            <text class="strip-title" :x="L.strip.x" :y="L.strip.y - 7">one timeline</text>
            <line
              v-for="(lane, i) in play.lanes"
              :key="`row-${i}`"
              class="row"
              :x1="L.strip.x"
              :x2="L.strip.x + L.strip.w"
              :y1="L.strip.y + rowH * (i + 0.5)"
              :y2="L.strip.y + rowH * (i + 0.5)"
            />
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
              <rect :x="L.strip.x - 10" :y="L.strip.y - 2" width="10" :height="L.strip.h + 4" fill="url(#orchestra-head)" transform="rotate(0)" />
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

.core-glyph {
  font-size: 22px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.flow-name {
  font-family: var(--vp-font-family-mono);
  font-size: 15px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.flow-shape {
  font-size: 12px;
  fill: var(--hmz-stage-dim);
}

.node-halo {
  opacity: var(--hmz-glow);
}

.node-eye {
  fill: #fff;
  opacity: 0.85;
}

.role {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.spec {
  font-family: var(--vp-font-family-mono);
  font-size: 10px;
  fill: var(--hmz-stage-dim);
}

.strip-frame {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
}

.strip-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.row {
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 2 4;
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
