<script setup lang="ts">
// A run of a flow, simulated: one row per agent, each turn a band, and every tool call it
// makes landing on the strip the way a collected trace lands them in Perfetto.
//
// What is held to the code: each flow's roles are the ones it declares in the official
// flowverse, every agent is spelled the way `hmz exec -a` takes it (role=cli/model:effort,
// with the effort on that CLI's ladder in `coganchor/backends.py`), and who takes a turn after
// whom is the flow's own order. What is invented: the tool calls, their lengths and the
// token counts.
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'

type Kind = 'tool' | 'think' | 'say'

interface Lane {
  role: string
  agent: string
  tone: number
  idle: string
}

interface Play {
  name: string
  shape: string
  lanes: Lane[]
  first: number[]
  after: (lane: number) => number[]
}

const PLAYS: Play[] = [
  {
    name: 'ralph_loop',
    shape: 'one agent, a fresh session every round',
    lanes: [{ role: 'agent', agent: 'claude/claude-opus-5:high', tone: 1, idle: 'new session' }],
    first: [0],
    after: () => [0],
  },
  {
    name: 'flame_chase',
    shape: 'two agents taking turns on the same tree',
    lanes: [
      { role: 'first_chaser', agent: 'claude/claude-opus-5:high', tone: 1, idle: 'its turn next' },
      { role: 'second_chaser', agent: 'codex/gpt-5.6-sol:high', tone: 2, idle: 'its turn next' },
    ],
    first: [0],
    after: (lane) => [1 - lane],
  },
  {
    name: 'parallel_flame_chase',
    shape: 'a coordinator plans, then three lanes run at once, a and b taking turns in each',
    lanes: [
      { role: 'coordinator', agent: 'claude/claude-opus-5:max', tone: 6, idle: 'planned' },
      { role: 'lane_1_actor_a', agent: 'claude/claude-opus-5:high', tone: 1, idle: 'b’s turn' },
      { role: 'lane_1_actor_b', agent: 'codex/gpt-5.6-sol:high', tone: 1, idle: 'a’s turn' },
      { role: 'lane_2_actor_a', agent: 'kimi/kimi-code/k3:high', tone: 2, idle: 'b’s turn' },
      { role: 'lane_2_actor_b', agent: 'grok/grok-4.6:high', tone: 2, idle: 'a’s turn' },
      {
        role: 'lane_3_actor_a',
        agent: 'opencode/opencode/big-pickle:high',
        tone: 3,
        idle: 'b’s turn',
      },
      { role: 'lane_3_actor_b', agent: 'zcode/zai/glm-5.3:high', tone: 3, idle: 'a’s turn' },
    ],
    first: [0],
    // The coordinator hands over to the three a's at once; inside a lane, a and b alternate.
    after: (lane) => (lane === 0 ? [1, 3, 5] : [lane % 2 ? lane + 1 : lane - 1]),
  },
]

const TOOLS = ['Read', 'Bash', 'Edit', 'Grep', 'Write', 'Glob', 'WebFetch', 'Task']
const WINDOW = 22 // seconds of trace kept on screen
const GAP = 0.45 // between one turn ending and the next starting
const PREFILL = 26 // seconds already run when it is first drawn

interface Slice {
  id: number
  lane: number
  label: string
  kind: Kind
  t0: number
  t1: number
}

interface Band {
  id: number
  lane: number
  t0: number
  t1: number | null
}

interface Doing {
  label: string
  kind: Kind
  t0: number
  t1: number
  rate: number
}

interface State {
  band: Band | null
  left: number
  doing: Doing | null
  tokens: number
  startAt: number | null
}

const picked = ref(1)
const play = computed(() => PLAYS[picked.value])
const running = ref(true)
const clock = ref(0)
const slices = shallowRef<Slice[]>([])
const bands = shallowRef<Band[]>([])
const lanes = shallowRef<State[]>([])
const hovered = ref<Slice | null>(null)
const focused = ref<number | null>(null)

const laneHeight = 26
const stripHeight = computed(() => play.value.lanes.length * laneHeight + 8)

let seed = 20260817
const rand = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff)
const between = (lo: number, hi: number) => lo + rand() * (hi - lo)
let counter = 0

function act(at: number): Doing {
  const roll = rand()
  const kind: Kind = roll < 0.5 ? 'tool' : roll < 0.85 ? 'think' : 'say'
  const label =
    kind === 'tool' ? TOOLS[Math.floor(rand() * TOOLS.length)] : kind === 'think' ? 'thinking' : 'says'
  return {
    label,
    kind,
    t0: at,
    t1: at + (kind === 'tool' ? between(0.5, 2.4) : between(0.5, 1.8)),
    rate: between(38, 190),
  }
}

function begin(state: State, lane: number, at: number) {
  const band: Band = { id: (counter += 1), lane, t0: at, t1: null }
  bands.value = [...bands.value, band]
  state.band = band
  state.left = Math.floor(between(3, 7))
  state.doing = act(at)
  state.tokens = 0
  state.startAt = null
}

function reset() {
  seed = 20260817
  counter = 0
  clock.value = 0
  slices.value = []
  bands.value = []
  const fresh: State[] = play.value.lanes.map(() => ({
    band: null,
    left: 0,
    doing: null,
    tokens: 0,
    startAt: null,
  }))
  for (const lane of play.value.first) fresh[lane].startAt = between(0, 0.6)
  lanes.value = fresh
  // A run that has been going a while, so what you scroll onto is a trace being written
  // rather than an empty strip waiting to be.
  for (let i = 0; i < PREFILL / 0.05; i += 1) step(0.05)
}

function step(dt: number) {
  clock.value += dt
  const now = clock.value
  const next = lanes.value.slice()
  let changed = false
  for (let lane = 0; lane < next.length; lane += 1) {
    const state = next[lane]
    if (state.startAt !== null && now >= state.startAt) {
      begin(state, lane, state.startAt)
      changed = true
    }
    const doing = state.doing
    if (!doing) continue
    state.tokens += doing.rate * dt
    if (now < doing.t1) continue
    slices.value = [
      ...slices.value,
      { id: (counter += 1), lane, label: doing.label, kind: doing.kind, t0: doing.t0, t1: doing.t1 },
    ]
    changed = true
    state.left -= 1
    if (state.left > 0) {
      state.doing = act(doing.t1)
      continue
    }
    // The turn is over: close its band and hand over to whoever the flow says goes next.
    if (state.band) {
      const closed = { ...state.band, t1: doing.t1 }
      bands.value = bands.value.map((b) => (b.id === closed.id ? closed : b))
    }
    state.band = null
    state.doing = null
    for (const to of play.value.after(lane)) next[to].startAt = doing.t1 + GAP
  }
  lanes.value = next
  if (changed) {
    const left = now - WINDOW
    if (slices.value.length > 200) slices.value = slices.value.filter((s) => s.t1 > left)
    if (bands.value.length > 60) bands.value = bands.value.filter((b) => b.t1 === null || b.t1 > left)
  }
}

let frame = 0
let last = 0
let idle = false

function loop(at: number) {
  frame = requestAnimationFrame(loop)
  const dt = Math.min((at - last) / 1000, 0.1)
  last = at
  if (running.value && !idle) step(dt * 1.35)
}

let observer: IntersectionObserver | undefined
const root = ref<HTMLElement | null>(null)

onMounted(() => {
  reset()
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    running.value = false // the filled strip is the whole of it: no animation
    return
  }
  observer = new IntersectionObserver((entries) => (idle = !entries[0].isIntersecting), {
    rootMargin: '120px',
  })
  if (root.value) observer.observe(root.value)
  last = performance.now()
  frame = requestAnimationFrame(loop)
})

onUnmounted(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
})

function pick(i: number) {
  picked.value = i
  focused.value = null
  hovered.value = null
  reset()
}

const left = computed(() => Math.max(0, clock.value - WINDOW))
const scale = 1000 / WINDOW
const x = (t: number) => (t - left.value) * scale
const drawn = computed(() =>
  slices.value
    .filter((s) => s.t1 > left.value)
    .map((s) => ({ slice: s, x: x(s.t0), w: Math.max(3, (s.t1 - s.t0) * scale) })),
)
const drawnBands = computed(() =>
  bands.value
    .filter((b) => b.t1 === null || b.t1 > left.value)
    .map((b) => ({ band: b, x: x(b.t0), w: Math.max(3, ((b.t1 ?? clock.value) - b.t0) * scale) })),
)
const ticks = computed(() => {
  const first = Math.ceil(left.value / 4) * 4
  return Array.from({ length: 6 }, (_, i) => first + i * 4).filter((t) => t <= clock.value)
})
const tone = (lane: number) => `var(--hmz-lane-${play.value.lanes[lane]?.tone ?? 1})`
const dim = (lane: number) => focused.value !== null && focused.value !== lane
const caption = computed(() => {
  if (hovered.value) {
    const s = hovered.value
    const lane = play.value.lanes[s.lane]
    return `${s.label} · ${(s.t1 - s.t0).toFixed(1)}s · ${lane.role}=${lane.agent}`
  }
  const n = drawn.value.length
  const agents = play.value.lanes.length
  return `${agents} agent${agents === 1 ? '' : 's'} · ${n} call${n === 1 ? '' : 's'} on screen · one trace for the whole run`
})
</script>

<template>
  <div ref="root" class="orchestra hmz-panel">
    <div class="bar">
      <span class="live" :class="{ paused: !running }">
        <i />
        simulated
      </span>
      <div class="plays" role="group" aria-label="which flow to play">
        <button
          v-for="(p, i) in PLAYS"
          :key="p.name"
          type="button"
          :class="{ on: picked === i }"
          :aria-pressed="picked === i"
          @click="pick(i)"
        >
          {{ p.name }}
        </button>
      </div>
      <div class="spacer" />
      <button
        class="toggle"
        type="button"
        :aria-label="running ? 'pause' : 'play'"
        @click="running = !running"
      >
        {{ running ? '❙❙' : '▶' }}
      </button>
    </div>
    <p class="shape">{{ play.shape }}</p>

    <div class="lanes">
      <div
        v-for="(lane, i) in play.lanes"
        :key="lane.role"
        class="lane"
        :class="{ dim: dim(i) }"
        :style="{ '--tone': tone(i) }"
        @mouseenter="focused = i"
        @mouseleave="focused = null"
      >
        <span class="dot" :class="{ off: !lanes[i]?.doing }" />
        <code class="spec"><b>{{ lane.role }}</b>={{ lane.agent }}</code>
        <span class="doing" :class="lanes[i]?.doing?.kind ?? 'idle'">
          {{ lanes[i]?.doing?.label ?? lane.idle }}
        </span>
        <span class="tok">{{ lanes[i]?.doing ? `${Math.round(lanes[i].tokens)} tok` : '' }}</span>
      </div>
    </div>

    <div class="strip">
      <svg :viewBox="`0 0 1000 ${stripHeight}`" role="img" aria-label="a simulated trace of the run">
        <line
          v-for="t in ticks"
          :key="t"
          :x1="x(t)"
          :x2="x(t)"
          y1="0"
          :y2="stripHeight"
          class="tick"
        />
        <rect
          v-for="item in drawnBands"
          :key="`b${item.band.id}`"
          :x="item.x"
          :y="item.band.lane * laneHeight + 3"
          :width="item.w"
          :height="laneHeight - 4"
          rx="5"
          class="band"
          :class="{ dim: dim(item.band.lane) }"
          :style="{ '--tone': tone(item.band.lane) }"
        />
        <g v-for="item in drawn" :key="item.slice.id">
          <rect
            :x="item.x"
            :y="item.slice.lane * laneHeight + 6"
            :width="item.w"
            :height="laneHeight - 10"
            rx="3"
            class="slice"
            :class="[item.slice.kind, { dim: dim(item.slice.lane) }]"
            :style="{ '--tone': tone(item.slice.lane) }"
            @mouseenter="hovered = item.slice"
            @mouseleave="hovered = null"
          />
          <text
            v-if="item.w > 52"
            :x="item.x + 7"
            :y="item.slice.lane * laneHeight + laneHeight / 2 + 2"
            class="label"
            :class="[item.slice.kind, { dim: dim(item.slice.lane) }]"
          >
            {{ item.slice.label }}
          </text>
        </g>
        <line x1="1000" x2="1000" y1="0" :y2="stripHeight" class="head" />
      </svg>
    </div>

    <p class="caption">{{ caption }}</p>
  </div>
</template>

<style scoped>
.orchestra {
  --tone: var(--hmz-lane-1);
}

.bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
}

.live {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--vp-c-text-2);
  font-weight: 600;
}

.live i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--hmz-accent);
  box-shadow: 0 0 0 0 var(--hmz-accent);
  animation: pulse 2s ease-out infinite;
}

.live.paused i {
  background: var(--vp-c-text-3);
  animation: none;
}

@keyframes pulse {
  70% {
    box-shadow: 0 0 0 7px transparent;
  }
  100% {
    box-shadow: 0 0 0 0 transparent;
  }
}

.spacer {
  flex: 1;
}

.plays {
  display: inline-flex;
  flex-wrap: wrap;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  overflow: hidden;
}

.plays button,
.toggle {
  padding: 4px 10px;
  border: 0;
  background: transparent;
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.plays button + button {
  border-left: 1px solid var(--vp-c-divider);
}

.plays button.on {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.toggle {
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  min-width: 34px;
  font-family: inherit;
}

.plays button:hover,
.toggle:hover {
  color: var(--vp-c-brand-1);
}

.plays button:focus-visible,
.toggle:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: -2px;
}

.shape {
  margin: 0;
  padding: 10px 22px 0;
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.lanes {
  padding: 8px 14px 4px;
}

.lane {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px;
  border-radius: 8px;
  font-size: 12px;
  transition: background 0.2s, opacity 0.2s;
}

.lane:hover {
  background: var(--vp-c-default-soft);
}

.lane.dim {
  opacity: 0.34;
}

.dot {
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
  background: var(--tone);
  box-shadow: 0 0 8px var(--tone);
  transition: opacity 0.2s;
}

.dot.off {
  opacity: 0.3;
  box-shadow: none;
}

.spec {
  flex: 1;
  min-width: 0;
  padding: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: none;
  color: var(--vp-c-text-2);
  font-size: 12px;
}

.spec b {
  color: var(--vp-c-text-1);
  font-weight: 650;
}

.doing {
  flex: none;
  min-width: 96px;
  text-align: right;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--tone);
}

.doing.think,
.doing.idle {
  color: var(--vp-c-text-3);
  font-style: italic;
}

.tok {
  flex: none;
  width: 70px;
  text-align: right;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--vp-c-text-3);
  font-variant-numeric: tabular-nums;
}

.strip {
  margin: 6px 14px 0;
  border-top: 1px solid var(--hmz-panel-border);
  background: linear-gradient(180deg, var(--vp-c-bg-alt), transparent);
}

svg {
  display: block;
  width: 100%;
  height: auto;
}

.tick {
  stroke: var(--hmz-grid);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.band {
  fill: var(--tone);
  fill-opacity: 0.1;
  stroke: var(--tone);
  stroke-opacity: 0.4;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
  transition: opacity 0.2s;
}

.band.dim {
  opacity: 0.25;
}

.slice {
  fill: var(--tone);
  opacity: 0.86;
  transition: opacity 0.2s;
}

.slice.think {
  opacity: 0.4;
}

.slice.dim {
  opacity: 0.12;
}

.slice:hover {
  opacity: 1;
}

.label {
  fill: var(--vp-c-bg);
  font-size: 10px;
  font-family: var(--vp-font-family-mono);
  pointer-events: none;
}

/* A thinking slice is drawn faint, so its label is read against the panel rather than
   against the slice. */
.label.think {
  fill: var(--vp-c-text-2);
}

.label.dim {
  opacity: 0.15;
}

.head {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
  filter: drop-shadow(0 0 4px var(--hmz-accent));
}

.caption {
  margin: 0;
  padding: 8px 16px 12px;
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

@media (prefers-reduced-motion: reduce) {
  .live i {
    animation: none;
  }
}

@media (max-width: 720px) {
  .tok {
    display: none;
  }

  .doing {
    min-width: 0;
  }

  /* Narrow enough that scaling the strip to fit would make every label a smudge, so it
     keeps its size and scrolls instead -- starting at the right, where the newest is. */
  .strip {
    overflow-x: auto;
    direction: rtl;
  }

  .strip svg {
    width: 680px;
    direction: ltr;
  }
}

@media (max-width: 480px) {
  .plays {
    order: 3;
    flex-basis: 100%;
  }

  .plays button {
    flex: 1 1 auto;
    padding: 4px 6px;
    font-size: 10.5px;
  }

  .shape {
    padding: 10px 14px 0;
  }

  .doing {
    display: none;
  }
}
</style>
