<script setup lang="ts">
// An agent on your machine whose work lands on another one, drawn as the reader meets it:
// pick something the agent does and watch where it happens. The routes are the default
// arrangement in `specs/coganchor/SPEC.md` and `reference/remote-execution`: the project's
// files, the commands and whatever those commands reach are the target's; the agent's own
// link to its model provider, its settings and its login stay here.
//
// Two drawings of the same thing: side by side where there is room, and one above the other
// on a phone, where the side-by-side one would have to shrink its words out of legibility.
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'

type Route = 'target' | 'here'
type Where = 'files' | 'commands' | 'network' | 'local'

interface Act {
  what: string
  by: string
  route: Route
  where: Where
  note: string
}

const ACTS: Act[] = [
  {
    what: 'reads kernel.cu',
    by: 'the agent',
    route: 'target',
    where: 'files',
    note: "It sees the target's files, at the target's own paths.",
  },
  {
    what: 'edits kernel.cu',
    by: 'the agent',
    route: 'target',
    where: 'files',
    note: "The edit lands in the target's copy of the project.",
  },
  {
    what: 'runs pytest',
    by: 'the agent',
    route: 'target',
    where: 'commands',
    note: "The tests run on the target, and the exit status is the target's own.",
  },
  {
    what: 'pip install numpy',
    by: 'a command it ran',
    route: 'target',
    where: 'network',
    note: 'Whatever its commands download, the target downloads.',
  },
  {
    what: 'asks the model',
    by: 'the agent',
    route: 'here',
    where: 'local',
    note: 'The agent talks to its model provider from here, as it always does.',
  },
  {
    what: 'reads its login',
    by: 'the agent',
    route: 'here',
    where: 'local',
    note: 'Its settings and credentials stay here, with the agent.',
  },
]

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Layout {
  view: string
  mine: Box
  theirs: Box
  mineLabel: { x: number; y: number; end?: boolean }
  theirsLabel: { x: number; y: number; end?: boolean }
  drawn: { x: number; y: number; end?: boolean }
  agent: Box
  feed: string
  humanize: Box
  here: Box
  header: Box
  dests: Record<'files' | 'commands' | 'network', Box>
  toTarget: string
  toHere: string
  // Where the lit wire's gradient runs, in the drawing's own units: a straight wire has no
  // width or no height, and a gradient laid over its bounding box would draw nothing at all.
  grad: { x1: number; y1: number; x2: number; y2: number }
  over: { x: number; y: number; end?: boolean; start?: boolean }
}

const WIDE: Layout = {
  view: '0 0 760 300',
  mine: { x: 12, y: 36, w: 250, h: 252 },
  theirs: { x: 498, y: 36, w: 250, h: 252 },
  mineLabel: { x: 20, y: 24 },
  theirsLabel: { x: 740, y: 24, end: true },
  drawn: { x: 380, y: 24 },
  agent: { x: 30, y: 52, w: 214, h: 46 },
  feed: 'M 137 100 L 137 136',
  humanize: { x: 30, y: 138, w: 214, h: 46 },
  here: { x: 30, y: 226, w: 196, h: 46 },
  header: { x: 516, y: 52, w: 214, h: 40 },
  dests: {
    files: { x: 516, y: 104, w: 214, h: 52 },
    commands: { x: 516, y: 164, w: 214, h: 52 },
    network: { x: 516, y: 224, w: 214, h: 52 },
  },
  toTarget: 'M 244 161 C 360 161 390 131 498 131',
  toHere: 'M 244 161 C 280 161 284 249 252 249 L 226 249',
  grad: { x1: 244, y1: 0, x2: 498, y2: 0 },
  over: { x: 380, y: 118 },
}

const NARROW: Layout = {
  view: '0 0 360 566',
  mine: { x: 8, y: 32, w: 344, h: 204 },
  theirs: { x: 8, y: 306, w: 344, h: 252 },
  mineLabel: { x: 14, y: 22 },
  theirsLabel: { x: 346, y: 298, end: true },
  drawn: { x: 346, y: 22, end: true },
  agent: { x: 24, y: 46, w: 312, h: 46 },
  feed: 'M 180 94 L 180 118',
  humanize: { x: 24, y: 120, w: 312, h: 46 },
  here: { x: 150, y: 180, w: 186, h: 46 },
  header: { x: 24, y: 320, w: 312, h: 40 },
  dests: {
    files: { x: 24, y: 370, w: 312, h: 54 },
    commands: { x: 24, y: 432, w: 312, h: 54 },
    network: { x: 24, y: 494, w: 312, h: 54 },
  },
  toTarget: 'M 90 166 L 90 306',
  toHere: 'M 90 166 C 90 196 110 203 150 203',
  grad: { x1: 0, y1: 166, x2: 0, y2: 306 },
  over: { x: 102, y: 270, start: true },
}

const narrow = ref(false)
const L = computed(() => (narrow.value ? NARROW : WIDE))
const mid = (b: Box) => b.x + b.w / 2

const picked = ref(2)
const act = computed(() => ACTS[picked.value])

const wireTarget = ref<SVGPathElement | null>(null)
const wireHere = ref<SVGPathElement | null>(null)
const at = ref({ x: 0, y: 0, shown: false })

let frame = 0
let travelled = 0
let last = 0
let still = false
const idle = ref(false)

function place() {
  const wire = act.value.route === 'target' ? wireTarget.value : wireHere.value
  if (!wire) return
  const t = Math.min(travelled, 1)
  const point = wire.getPointAtLength(t * wire.getTotalLength())
  at.value = { x: point.x, y: point.y, shown: travelled <= 1.02 }
}

function tick(now: number) {
  frame = requestAnimationFrame(tick)
  const dt = Math.min((now - last) / 1000, 0.1)
  last = now
  if (idle.value) return
  travelled = (travelled + dt * 0.42) % 1.35
  place()
}

function pick(i: number) {
  picked.value = i
  travelled = still ? 0.55 : 0
  if (still) nextTick(place)
}

let observer: IntersectionObserver | undefined
let phone: MediaQueryList | undefined
const root = ref<HTMLElement | null>(null)

function fit() {
  narrow.value = phone?.matches ?? false
  if (still) nextTick(place)
}

onMounted(() => {
  phone = window.matchMedia('(max-width: 640px)')
  phone.addEventListener('change', fit)
  fit()
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    still = true
    travelled = 0.55
    nextTick(place)
    return
  }
  observer = new IntersectionObserver((entries) => (idle.value = !entries[0].isIntersecting), {
    rootMargin: '120px',
  })
  if (root.value) observer.observe(root.value)
  last = performance.now()
  frame = requestAnimationFrame(tick)
})

onUnmounted(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
  phone?.removeEventListener('change', fit)
})

const lit = (where: Where) => (act.value.where === where ? 'lit' : '')
const DESTS = [
  { key: 'files', title: 'the project', sub: 'every file it reads or edits' },
  { key: 'commands', title: 'commands', sub: 'builds, tests, whatever it runs' },
  { key: 'network', title: 'the network', sub: 'whatever those commands reach' },
] as const
</script>

<template>
  <div ref="root" class="anchor hmz-panel" :class="{ still: idle, narrow }">
    <svg
      :viewBox="L.view"
      role="img"
      aria-label="an agent on your machine, its work landing on the target"
    >
      <defs>
        <linearGradient
          id="hmz-wire"
          gradientUnits="userSpaceOnUse"
          :x1="L.grad.x1"
          :y1="L.grad.y1"
          :x2="L.grad.x2"
          :y2="L.grad.y2"
        >
          <stop offset="0" stop-color="var(--vp-c-brand-3)" />
          <stop offset="1" stop-color="var(--hmz-accent)" />
        </linearGradient>
      </defs>

      <text :x="L.mineLabel.x" :y="L.mineLabel.y" class="side">your machine</text>
      <text :x="L.drawn.x" :y="L.drawn.y" class="drawn" :class="L.drawn.end ? 'end' : 'mid'">
        a drawing, not a recording
      </text>
      <text :x="L.theirsLabel.x" :y="L.theirsLabel.y" class="side end">the target</text>
      <rect v-bind="{ x: L.mine.x, y: L.mine.y, width: L.mine.w, height: L.mine.h }" rx="14" class="zone" />
      <rect v-bind="{ x: L.theirs.x, y: L.theirs.y, width: L.theirs.w, height: L.theirs.h }" rx="14" class="zone" />

      <rect v-bind="{ x: L.agent.x, y: L.agent.y, width: L.agent.w, height: L.agent.h }" rx="9" class="box" />
      <text :x="mid(L.agent)" :y="L.agent.y + 20" class="title mid">claude, codex, …</text>
      <text :x="mid(L.agent)" :y="L.agent.y + 37" class="sub mid">unchanged, and told none of this</text>

      <path :d="L.feed" class="feed" />

      <rect
        v-bind="{ x: L.humanize.x, y: L.humanize.y, width: L.humanize.w, height: L.humanize.h }"
        rx="9"
        class="box strong"
      />
      <text :x="mid(L.humanize)" :y="L.humanize.y + 20" class="title mid">humanize</text>
      <text :x="mid(L.humanize)" :y="L.humanize.y + 37" class="sub mid">routes each thing it does</text>

      <rect
        v-bind="{ x: L.here.x, y: L.here.y, width: L.here.w, height: L.here.h }"
        rx="9"
        class="box"
        :class="lit('local')"
      />
      <text :x="mid(L.here)" :y="L.here.y + 20" class="title mid">stays here</text>
      <text :x="mid(L.here)" :y="L.here.y + 37" class="sub mid">login · settings · the model</text>

      <path ref="wireHere" :d="L.toHere" class="wire local" :class="{ on: act.route === 'here' }" />
      <path ref="wireTarget" :d="L.toTarget" class="wire" :class="{ on: act.route === 'target' }" />
      <text :x="L.over.x" :y="L.over.y" class="sub" :class="L.over.start ? '' : 'mid'">
        over ssh, or into a container
      </text>

      <rect
        v-bind="{ x: L.header.x, y: L.header.y, width: L.header.w, height: L.header.h }"
        rx="9"
        class="box strong"
      />
      <text :x="mid(L.header)" :y="L.header.y + 25" class="title mid">an ssh host or a container</text>

      <g v-for="d in DESTS" :key="d.key" class="dest" :class="lit(d.key)">
        <rect
          v-bind="{ x: L.dests[d.key].x, y: L.dests[d.key].y, width: L.dests[d.key].w, height: L.dests[d.key].h }"
          rx="9"
          class="box"
        />
        <text :x="L.dests[d.key].x + 16" :y="L.dests[d.key].y + 22" class="title">{{ d.title }}</text>
        <text :x="L.dests[d.key].x + 16" :y="L.dests[d.key].y + 40" class="sub">{{ d.sub }}</text>
      </g>

      <g v-show="at.shown" class="packet" :transform="`translate(${at.x} ${at.y})`">
        <rect x="-60" y="-13" width="120" height="26" rx="13" />
        <text y="4">{{ act.route === 'target' ? 'on the target' : 'stays here' }}</text>
      </g>
    </svg>

    <div class="acts" role="group" aria-label="something the agent does">
      <button
        v-for="(item, i) in ACTS"
        :key="item.what"
        type="button"
        :class="{ on: picked === i, here: item.route === 'here' }"
        :aria-pressed="picked === i"
        @click="pick(i)"
      >
        <code>{{ item.what }}</code>
        <span>{{ item.by }}</span>
      </button>
    </div>
    <p class="note" aria-live="polite">
      <strong>{{ act.route === 'target' ? 'On the target.' : 'On your machine.' }}</strong>
      {{ act.note }}
    </p>
  </div>
</template>

<style scoped>
svg {
  display: block;
  width: 100%;
  height: auto;
  background:
    radial-gradient(60% 90% at 12% 50%, var(--vp-c-brand-soft), transparent 70%),
    radial-gradient(60% 90% at 88% 50%, rgba(20, 184, 166, 0.1), transparent 70%);
}

.narrow svg {
  background:
    radial-gradient(90% 40% at 50% 20%, var(--vp-c-brand-soft), transparent 70%),
    radial-gradient(90% 40% at 50% 80%, rgba(20, 184, 166, 0.1), transparent 70%);
}

.side {
  fill: var(--vp-c-text-3);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-weight: 700;
}

.drawn {
  fill: var(--vp-c-text-3);
  font-size: 11px;
  font-style: italic;
}

.end {
  text-anchor: end;
}

.zone {
  fill: var(--vp-c-bg);
  stroke: var(--hmz-panel-border);
  stroke-dasharray: 4 5;
}

.box {
  fill: var(--vp-c-bg-soft);
  stroke: var(--hmz-panel-border);
  transition: stroke 0.3s, fill 0.3s, filter 0.3s;
}

.box.strong {
  stroke: var(--vp-c-brand-3);
  fill: var(--vp-c-bg-elv);
}

.title {
  fill: var(--vp-c-text-1);
  font-size: 15px;
  font-weight: 650;
}

.sub {
  fill: var(--vp-c-text-2);
  font-size: 12px;
}

.mid {
  text-anchor: middle;
}

.feed {
  stroke: var(--vp-c-divider);
  stroke-width: 1.5;
  fill: none;
}

.wire {
  fill: none;
  stroke: var(--vp-c-divider);
  stroke-width: 2;
  stroke-dasharray: 3 7;
  transition: stroke 0.3s, stroke-width 0.3s;
}

.wire.on {
  stroke: url(#hmz-wire);
  stroke-width: 2.5;
  animation: crawl 1.1s linear infinite;
}

.wire.local.on {
  stroke: var(--hmz-warm);
}

@keyframes crawl {
  to {
    stroke-dashoffset: -20;
  }
}

.still .wire.on {
  animation-play-state: paused;
}

.dest:not(.lit) .box {
  opacity: 0.55;
}

.dest.lit .box {
  stroke: var(--hmz-accent);
  filter: drop-shadow(0 0 8px var(--vp-c-brand-soft));
}

.box.lit {
  stroke: var(--hmz-warm);
  filter: drop-shadow(0 0 8px var(--vp-c-brand-soft));
}

.packet rect {
  fill: var(--vp-c-text-1);
}

.packet text {
  fill: var(--vp-c-bg);
  font-size: 11px;
  font-weight: 650;
  text-anchor: middle;
  font-family: var(--vp-font-family-mono);
}

.acts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 14px 16px 0;
}

.acts button {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 9px;
  background: var(--vp-c-bg);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s, transform 0.2s;
}

.acts button:hover {
  transform: translateY(-1px);
  border-color: var(--vp-c-brand-1);
}

.acts button:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.acts button code {
  padding: 0;
  background: none;
  font-size: 12.5px;
  color: var(--vp-c-text-1);
}

.acts button span {
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.acts button.on {
  border-color: var(--hmz-accent);
  background: var(--vp-c-brand-soft);
}

.acts button.on.here {
  border-color: var(--hmz-warm);
}

.note {
  margin: 0;
  padding: 12px 16px 14px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.note strong {
  margin-right: 6px;
  color: var(--vp-c-text-1);
}

@media (prefers-reduced-motion: reduce) {
  .wire.on {
    animation: none;
  }

  .acts button {
    transition: none;
  }

  .acts button:hover {
    transform: none;
  }
}

@media (max-width: 860px) {
  .acts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
