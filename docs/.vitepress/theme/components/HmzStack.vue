<script setup lang="ts">
// The layers of `src/hmz/`, and what code in each may import. It draws `ALLOWED` and
// `HANDED_THROUGH` from `tests/integration/layering/test_layering.py`, copied below entry for
// entry: keep the two in step. `cli` is not in that table (it joins the rest and may import
// any of them), so what it does import is drawn instead.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { withBase } from 'vitepress'

interface Layer {
  id: string
  dotted: string
  here: string
  note?: string
  spec: string
  ref?: string
}

const ALLOWED: Record<string, string[]> = {
  'hmz.coganchor': ['hmz.runtime.telemetry'],
  'hmz.coganchor.serve': ['hmz.coganchor.proto'],
  'hmz.runtime': [],
  'hmz.runtime.kept': [],
  'hmz.runtime.settings': ['hmz.runtime.kept'],
  'hmz.runtime.telemetry': ['hmz.runtime.settings'],
  'hmz.runtime.epic': ['hmz.coganchor', 'hmz.runtime.tracing'],
  'hmz.runtime.tracing': ['hmz.coganchor'],
  'hmz.runtime.exporting': ['hmz.coganchor', 'hmz.runtime.epic', 'hmz.runtime.tracing'],
  'hmz.runtime.runner': [
    'hmz.coganchor',
    'hmz.flows',
    'hmz.runtime.epic',
    'hmz.runtime.flowing',
    'hmz.runtime.kept',
    'hmz.runtime.settings',
    'hmz.runtime.telemetry',
  ],
  'hmz.runtime.flowing': [
    'hmz.coganchor',
    'hmz.flows',
    'hmz.runtime.epic',
    'hmz.runtime.telemetry',
  ],
  'hmz.flows': ['hmz.runtime.flowing'],
  'hmz.runtime.doing': [
    'hmz.coganchor',
    'hmz.flows',
    'hmz.runtime.epic',
    'hmz.runtime.exporting',
    'hmz.runtime.flowing',
    'hmz.runtime.runner',
    'hmz.runtime.settings',
    'hmz.runtime.telemetry',
    'hmz.runtime.tracing',
  ],
  'hmz.daemon': ['hmz.runtime'],
  'hmz.tui': [
    'hmz.coganchor',
    'hmz.flows',
    'hmz.runtime.flowing',
    'hmz.runtime.epic',
    'hmz.runtime.exporting',
    'hmz.runtime.kept',
    'hmz.runtime.telemetry',
    'hmz.daemon',
  ],
  'hmz.sdk': ['hmz.daemon', 'hmz.runtime'],
}

// The one pair allowed to point both ways, and only from inside `flow`, `load` and
// `Outworlder.new`.
const HANDED = { from: 'hmz.flows', to: 'hmz.runtime.flowing' }

// What `hmz.cli` imports, since the table leaves it out.
const CLI_IMPORTS = [
  'hmz.tui',
  'hmz.daemon',
  'hmz.runtime',
  'hmz.flows',
  'hmz.coganchor',
  'hmz.coganchor.serve',
  'hmz.runtime.telemetry',
]

// What the front door hands through out of its own package, which the table need not list.
const FRONT = ['hmz.runtime.doing', 'hmz.runtime.runner']

const LAYERS: Layer[] = [
  {
    id: 'cli',
    dotted: 'hmz.cli',
    here: 'The command line: a new command, and how a command writes its output.',
    note: 'Not in the table. It joins the layers, so it may import any of them, inside the command that needs it.',
    spec: 'cli.md',
    ref: '/reference/cli',
  },
  {
    id: 'tui',
    dotted: 'hmz.tui',
    here: 'The terminal interface: slash commands, keys, menus, and what they draw.',
    note: 'Reaches the runtime only through `daemon`.',
    spec: 'tui.md',
    ref: '/reference/tui',
  },
  {
    id: 'sdk',
    dotted: 'hmz.sdk',
    here: 'The Python API a tool outside humanize calls: `from hmz.sdk import Hmz`.',
    note: 'Nothing imports it: it is the way in from outside.',
    spec: 'sdk.md',
    ref: '/reference/sdk',
  },
  {
    id: 'daemon',
    dotted: 'hmz.daemon',
    here: 'A run held apart from the terminal, and the terminals that attach to it.',
    note: 'Names the runtime by its front door, `hmz.runtime`.',
    spec: 'daemon.md',
    ref: '/reference/daemon',
  },
  {
    id: 'runtime',
    dotted: 'hmz.runtime',
    here: 'The front door: hands `Hmz`, `Run` and `Refused` through from `doing` and `runner`.',
    spec: 'runtime/SPEC.md',
  },
  {
    id: 'doing',
    dotted: 'hmz.runtime.doing',
    here: 'humanize as one object, `Hmz`. Anything `cli`, `tui` and `daemon` would each write goes here once.',
    spec: 'runtime/doing.md',
    ref: '/reference/sdk',
  },
  {
    id: 'runner',
    dotted: 'hmz.runtime.runner',
    here: 'The `hmz exec` line: reading it, finding the flow, checking it, refusing it, running it.',
    spec: 'runtime/SPEC.md',
    ref: '/reference/cli',
  },
  {
    id: 'flowing',
    dotted: 'hmz.runtime.flowing',
    here: 'Everything done to a flow: the engine, budgets, resuming, the agent and environment drivers, the `-a` `-e` `-p` `-b` parsers, the fakes, finding flows and flowverses.',
    spec: 'runtime/flowing.md',
    ref: '/reference/flows',
  },
  {
    id: 'flows',
    dotted: 'hmz.flows',
    here: 'The flow API: the types a flow imports. Each is a promise to somebody else\'s repository.',
    note: 'Names `flowing` only inside `flow`, `load` and `Outworlder.new`, never at import. Importing `hmz.flows` loads nothing else of humanize.',
    spec: 'flows.md',
    ref: '/reference/flows',
  },
  {
    id: 'exporting',
    dotted: 'hmz.runtime.exporting',
    here: 'One whole run packaged up to send somewhere.',
    spec: 'runtime/SPEC.md',
  },
  {
    id: 'epic',
    dotted: 'hmz.runtime.epic',
    here: 'One run of one flow, written down as it happens.',
    spec: 'runtime/SPEC.md',
  },
  {
    id: 'tracing',
    dotted: 'hmz.runtime.tracing',
    here: 'The backends\' own logs read back as one trace: a reader per backend.',
    spec: 'runtime/tracing.md',
    ref: '/reference/tracing',
  },
  {
    id: 'coganchor',
    dotted: 'hmz.coganchor',
    here: 'Driving a coding agent CLI: backends, drivers, accounts, models, fallbacks, prices, machines, and the anchor.',
    spec: 'coganchor/SPEC.md',
    ref: '/reference/agents',
  },
  {
    id: 'serve',
    dotted: 'hmz.coganchor.serve',
    here: 'The half of the anchor that ships to the target machine.',
    note: 'The target may be any architecture, so it may import `hmz.coganchor.proto` and nothing else.',
    spec: 'coganchor/serve.md',
    ref: '/reference/remote-execution',
  },
  {
    id: 'telemetry',
    dotted: 'hmz.runtime.telemetry',
    here: 'What humanize reports about itself, and whether it does.',
    spec: 'runtime/SPEC.md',
  },
  {
    id: 'settings',
    dotted: 'hmz.runtime.settings',
    here: 'What each workspace was set up to run.',
    spec: 'runtime/SPEC.md',
  },
  {
    id: 'kept',
    dotted: 'hmz.runtime.kept',
    here: 'An agent written down, in the `CLI/MODEL:EFFORT` shape `-a` takes.',
    spec: 'runtime/SPEC.md',
  },
]

const BANDS: { label: string; ids: string[] }[] = [
  { label: 'ways in', ids: ['cli', 'tui', 'sdk'] },
  { label: 'holding a run', ids: ['daemon'] },
  { label: 'front door', ids: ['runtime', 'doing'] },
  { label: 'running a flow', ids: ['runner', 'flowing', 'flows'] },
  { label: 'what a run leaves', ids: ['exporting', 'epic', 'tracing'] },
  { label: 'driving agents', ids: ['coganchor', 'serve'] },
  { label: 'remembered', ids: ['telemetry', 'settings', 'kept'] },
]

const byId = Object.fromEntries(LAYERS.map((l) => [l.id, l])) as Record<string, Layer>
const band = Object.fromEntries(BANDS.flatMap((b, i) => b.ids.map((id) => [id, i]))) as Record<
  string,
  number
>
const byDotted = Object.fromEntries(LAYERS.map((l) => [l.dotted, l])) as Record<string, Layer>

const covers = (layer: string, name: string) => name === layer || name.startsWith(`${layer}.`)
const names = (l: Layer) =>
  l.id === 'cli' ? CLI_IMPORTS : l.id === 'runtime' ? FRONT : ALLOWED[l.dotted]

const active = ref('runner')
const layer = computed(() => byId[active.value])

// What it names outright, and what it may reach because it sits inside one of those, or
// inside its own package.
const named = computed(() =>
  LAYERS.filter((o) => o.id !== active.value && names(layer.value).includes(o.dotted)).map(
    (o) => o.id,
  ),
)
const inside = computed(() => {
  const grants = layer.value.id === 'cli' ? ['hmz'] : [layer.value.dotted, ...names(layer.value)]
  return LAYERS.filter(
    (o) =>
      o.id !== active.value &&
      !named.value.includes(o.id) &&
      grants.some((g) => covers(g, o.dotted)),
  ).map((o) => o.id)
})
const namedBy = computed(() =>
  LAYERS.filter((o) => o.id !== active.value && names(o).includes(layer.value.dotted)).map(
    (o) => o.id,
  ),
)
const outside = computed(() => names(layer.value).filter((n) => !byDotted[n]))
const handed = (id: string) =>
  layer.value.dotted === HANDED.from && byId[id].dotted === HANDED.to

function role(id: string) {
  if (id === active.value) return 'on'
  if (named.value.includes(id)) return handed(id) ? 'named handed' : 'named'
  if (inside.value.includes(id)) return 'inside'
  if (namedBy.value.includes(id)) return 'by'
  return 'off'
}

// The arrows are measured off the chips once they are laid out, so they follow the page
// through every width. Only arrows between bands are drawn: the rest is said by the chips.
const host = ref<HTMLElement | null>(null)
const chips = new Map<string, HTMLElement>()
const arrows = ref<{ key: string; d: string; kind: string }[]>([])
const size = ref({ w: 0, h: 0 })
let watching: ResizeObserver | undefined

function chip(id: string) {
  return (el: unknown) => {
    if (el instanceof HTMLElement) chips.set(id, el)
  }
}

function draw() {
  const root = host.value
  if (!root) return
  const o = root.getBoundingClientRect()
  size.value = { w: o.width, h: o.height }
  const at = (id: string) => {
    const r = chips.get(id)!.getBoundingClientRect()
    return { x: r.left - o.left + r.width / 2, top: r.top - o.top, bottom: r.bottom - o.top }
  }
  const curve = (x0: number, y0: number, x1: number, y1: number) => {
    const m = (y1 - y0) / 2
    return `M ${x0} ${y0} C ${x0} ${y0 + m}, ${x1} ${y1 - m}, ${x1} ${y1 - 2}`
  }
  const me = at(active.value)
  const mine = band[active.value]
  const out: { key: string; d: string; kind: string }[] = []
  for (const id of named.value) {
    const t = at(id)
    if (band[id] > mine)
      out.push({ key: `to-${id}`, d: curve(me.x, me.bottom, t.x, t.top), kind: 'to' })
  }
  for (const id of namedBy.value) {
    const s = at(id)
    if (band[id] < mine)
      out.push({ key: `by-${id}`, d: curve(s.x, s.bottom, me.x, me.top), kind: 'by' })
  }
  arrows.value = out
}

onMounted(() => {
  draw()
  document.fonts?.ready.then(draw)
  watching = new ResizeObserver(() => draw())
  if (host.value) watching.observe(host.value)
})

onBeforeUnmount(() => watching?.disconnect())

watch(active, () => nextTick(draw))

function pick(id: string) {
  active.value = id
}

// Prose with `code` in it, as alternating runs of text and code.
const parts = (text: string) => text.split('`').map((t, i) => ({ t, code: i % 2 === 1 }))

const spec = (path: string) => `https://github.com/humanfia/humanize/blob/main/specs/${path}`
</script>

<template>
  <figure class="stack hmz-panel">
    <figcaption class="cap">
      <span>Pick a layer to see what its code may import.</span>
      <span class="src">
        Drawn from the table in <code>tests/integration/layering/test_layering.py</code>
      </span>
    </figcaption>

    <div class="body">
      <div ref="host" class="bands">
        <svg
          class="wires"
          :viewBox="`0 0 ${size.w || 1} ${size.h || 1}`"
          :width="size.w"
          :height="size.h"
          aria-hidden="true"
        >
          <defs>
            <marker id="hmz-stack-to" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0 0 L8 4 L0 8 z" class="head to" />
            </marker>
            <marker id="hmz-stack-by" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0 0 L8 4 L0 8 z" class="head by" />
            </marker>
          </defs>
          <path
            v-for="a in arrows"
            :key="`${active}-${a.key}`"
            :d="a.d"
            :class="['wire', a.kind]"
            :marker-end="`url(#hmz-stack-${a.kind})`"
            pathLength="1"
          />
        </svg>

        <div v-for="band in BANDS" :key="band.label" class="band">
          <span class="label">{{ band.label }}</span>
          <div class="row">
            <button
              v-for="id in band.ids"
              :key="id"
              :ref="chip(id)"
              type="button"
              :class="['chip', role(id)]"
              :aria-pressed="id === active"
              @click="pick(id)"
            >
              {{ id }}
            </button>
          </div>
        </div>
      </div>

      <div class="read" aria-live="polite">
        <code class="who">{{ layer.dotted }}</code>
        <p class="here">
          <template v-for="(p, i) in parts(layer.here)" :key="i">
            <code v-if="p.code">{{ p.t }}</code><template v-else>{{ p.t }}</template>
          </template>
        </p>

        <p class="k">may import</p>
        <p class="list">
          <button
            v-for="id in named"
            :key="id"
            type="button"
            :class="['tag', 'named', { handed: handed(id) }]"
            @click="pick(id)"
          >
            {{ id }}
          </button>
          <button v-for="id in inside" :key="id" type="button" class="tag inside" @click="pick(id)">
            {{ id }}
          </button>
          <code v-for="n in outside" :key="n" class="tag outside">{{ n }}</code>
          <span v-if="!named.length && !inside.length && !outside.length" class="none">
            nothing else of humanize
          </span>
        </p>

        <p class="k">imported by</p>
        <p class="list">
          <button v-for="id in namedBy" :key="id" type="button" class="tag by" @click="pick(id)">
            {{ id }}
          </button>
          <span v-if="!namedBy.length" class="none">nothing</span>
        </p>

        <p v-if="layer.note" class="note">
          <template v-for="(p, i) in parts(layer.note)" :key="i">
            <code v-if="p.code">{{ p.t }}</code><template v-else>{{ p.t }}</template>
          </template>
        </p>

        <p class="links">
          <a :href="spec(layer.spec)" target="_blank" rel="noreferrer">its SPEC ↗</a>
          <a v-if="layer.ref" :href="withBase(layer.ref)">reference →</a>
        </p>
      </div>
    </div>

    <p class="legend">
      <span><i class="sw on" /> picked</span>
      <span><i class="sw named" /> may import</span>
      <span><i class="sw inside" /> inside one of those</span>
      <span><i class="sw by" /> imports it</span>
      <span><i class="sw off" /> may not</span>
    </p>
  </figure>
</template>

<style scoped>
.stack {
  margin: 0;
  container-type: inline-size;
}

.cap {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 16px;
  padding: 14px 18px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}

.cap .src {
  font-weight: 400;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.cap code {
  font-size: 11px;
  word-break: break-all;
}

.body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
}

@container (min-width: 620px) {
  .body {
    grid-template-columns: minmax(0, 1fr) 260px;
  }

  .read {
    border-left: 1px solid var(--hmz-panel-border);
    border-top: 0 !important;
  }
}

.bands {
  position: relative;
  padding: 10px 14px 14px;
}

.wires {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: visible;
}

.wire {
  fill: none;
  stroke-width: 1.6;
  stroke-dasharray: 1;
  stroke-dashoffset: 0;
  animation: draw 0.45s ease-out;
}

.wire.to {
  stroke: var(--vp-c-brand-1);
}

.wire.by {
  stroke: var(--hmz-accent);
}

.head.to {
  fill: var(--vp-c-brand-1);
}

.head.by {
  fill: var(--hmz-accent);
}

@keyframes draw {
  from {
    stroke-dashoffset: 1;
  }
}

.band {
  position: relative;
  margin-top: 16px;
}

.band:first-of-type {
  margin-top: 6px;
}

.label {
  position: relative;
  z-index: 1;
  display: inline-block;
  margin-bottom: 4px;
  padding-right: 6px;
  background: var(--hmz-panel-bg);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px 14px;
}

.chip {
  position: relative;
  z-index: 1;
  min-width: 84px;
  padding: 5px 12px;
  border: 1.5px solid var(--vp-c-divider);
  border-radius: 9px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s, color 0.2s, opacity 0.2s;
}

.chip:hover {
  border-color: var(--vp-c-brand-2);
}

.chip:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.chip.on {
  background: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-bg);
}

.chip.named {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.chip.handed {
  border-style: dashed;
}

.chip.inside {
  border-style: dotted;
  border-color: var(--vp-c-brand-3);
  color: var(--vp-c-brand-1);
}

.chip.by {
  border-color: var(--hmz-accent);
  color: var(--vp-c-text-1);
}

.chip.off {
  border-color: var(--vp-c-divider);
  color: var(--vp-c-text-3);
  font-weight: 500;
}

.read {
  padding: 16px 18px 18px;
  border-top: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.who {
  display: inline-block;
  font-size: 14px;
  font-weight: 700;
  color: var(--vp-c-text-1);
  word-break: break-all;
}

.read p {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--vp-c-text-2);
}

.read p code {
  font-size: 12px;
}

.read .k {
  margin-top: 14px;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.read .list {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.tag {
  padding: 1px 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 20px;
  cursor: pointer;
}

.tag.named {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.tag.handed {
  border: 1px dashed var(--vp-c-brand-1);
}

.tag.inside {
  border: 1px dotted var(--vp-c-brand-3);
  color: var(--vp-c-brand-1);
}

.tag.outside {
  border: 1px solid var(--vp-c-divider);
  background: transparent;
  color: var(--vp-c-text-2);
  cursor: default;
}

.tag.by {
  border-color: var(--hmz-accent);
  color: var(--vp-c-text-1);
}

.none {
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.read .note {
  margin-top: 14px;
  padding-left: 10px;
  border-left: 2px solid var(--hmz-accent);
  font-size: 12.5px;
}

.links {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 14px !important;
}

.links a {
  font-size: 12px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  text-decoration: none;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin: 0;
  padding: 10px 18px 12px;
  border-top: 1px solid var(--hmz-panel-border);
  font-size: 12px;
  color: var(--vp-c-text-2);
}

.legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.sw {
  display: inline-block;
  width: 16px;
  height: 11px;
  border: 1.5px solid var(--vp-c-divider);
  border-radius: 3px;
  background: var(--vp-c-bg);
}

.sw.on {
  background: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}

.sw.named {
  background: var(--vp-c-brand-soft);
  border-color: var(--vp-c-brand-1);
}

.sw.inside {
  border-style: dotted;
  border-color: var(--vp-c-brand-3);
}

.sw.by {
  border-color: var(--hmz-accent);
}

.sw.off {
  border-color: var(--vp-c-divider);
  background: transparent;
}

@media (prefers-reduced-motion: reduce) {
  .wire {
    animation: none;
  }

  .chip {
    transition: none;
  }
}
</style>
