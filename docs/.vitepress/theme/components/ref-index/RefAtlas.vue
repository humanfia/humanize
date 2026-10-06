<script setup lang="ts">
// The reference as a map of humanize as built: one card per page, with the package it covers,
// in four tiers -- what you type into, the Python you write against, what sits below the flow
// API, and what a run reads and leaves behind. The pages and packages are the table under
// "Pages" on docs/reference/index.md.
//
// Then one request is followed through it, along edges the layering table allows
// (tests/integration/test_core_layering.py): `hmz exec` is the CLI, which may name any
// layer; `hmz.runtime.runner` reads the line and runs the flow it names, granted what it
// declared; the flow's turns reach the agent through `hmz.runtime.flowing`, whose drivers are
// written against `hmz.coganchor`, which drives the CLI as an account (`claude/…` has no
// `@provider`, so it runs as local) on a machine (`twice`'s workspace is a `LocalEnv`, the
// directory the run started in). `hmz exec` reads its environment at start
// (docs/reference/environment.md), and every run writes an epic under `H/epics/`
// (docs/reference/files.md, docs/reference/tracing.md).
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig } from '../../motion/camera'
import { createFx, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'humanize as built, layer by layer',
  'One line, typed into the CLI',
  'The runtime runs the flow it names',
  'Its turn drives a CLI, as an account, on a machine',
  'And the run is written down',
]

interface Node {
  key: string
  name: string
  sub: string
  badge?: string
  /** The badge on a phone, where the card is narrower. */
  short?: string
}
const TIERS: { label: string; nodes: Node[] }[] = [
  {
    label: 'you type into',
    nodes: [
      { key: 'cli', name: 'CLI', sub: 'hmz.cli', badge: 'hmz exec' },
      { key: 'tui', name: 'TUI', sub: 'hmz.tui' },
      { key: 'daemon', name: 'Daemon', sub: 'hmz.daemon' },
    ],
  },
  {
    label: 'you write against',
    nodes: [
      { key: 'flows', name: 'Flows', sub: 'hmz.flows', badge: 'twice, $1 budget', short: 'twice, $1' },
      { key: 'sdk', name: 'SDK', sub: 'hmz.sdk' },
    ],
  },
  {
    label: 'below the flow API',
    nodes: [
      { key: 'agents', name: 'Agents', sub: 'hmz.coganchor', badge: 'claude' },
      { key: 'machines', name: 'Machines', sub: 'hmz.coganchor', badge: 'local' },
      { key: 'providers', name: 'Providers', sub: 'hmz.coganchor', badge: 'as local' },
      { key: 'remote', name: 'Remote execution', sub: 'hmz.coganchor' },
    ],
  },
  {
    label: 'read and left behind',
    nodes: [
      { key: 'tracing', name: 'Tracing', sub: 'hmz.runtime' },
      { key: 'files', name: 'Files', sub: '~/.hmz, .hmz/' },
      { key: 'env', name: 'Environment variables', sub: 'HUMANIZE_HOME, …' },
      { key: 'settings', name: 'Settings', sub: 'settings.yaml' },
    ],
  },
]

interface Place {
  x: number
  y: number
  w: number
}
interface Layout {
  w: number
  h: number
  cmd: { x: number; y: number; w: number; h: number; lines: string[][] }
  /** Where each tier's label sits, and each of its cards. */
  tiers: { y: number; at: Place[] }[]
  strip: { x: number; y: number; w: number }
  open: { x: number; y: number; s: number }
  whole: { x: number; y: number; s: number }
}

const NODE_H = 40
const EDGE_X = 60

// The command line, cut into the parts each beat lights.
const ARG_F = '-f twice'
const ARG_A = '-a builder=claude/…'
const ARG_P = '-p budget.cost=1'

const WIDE: Layout = {
  w: 640,
  h: 360,
  cmd: { x: 14, y: 12, w: 420, h: 26, lines: [['$ hmz exec ', ARG_F, ' ', ARG_A, ' ', ARG_P, ' "…"']] },
  tiers: [
    { y: 64, at: [0, 1, 2].map((i) => ({ x: 14 + i * 207, y: 64, w: 198 })) },
    { y: 126, at: [0, 1].map((i) => ({ x: 14 + i * 311, y: 126, w: 301 })) },
    { y: 188, at: [0, 1, 2, 3].map((i) => ({ x: 14 + i * 155, y: 188, w: 147 })) },
    {
      y: 250,
      at: [
        { x: 14, y: 250, w: 120 },
        { x: 142, y: 250, w: 120 },
        { x: 270, y: 250, w: 196 },
        { x: 474, y: 250, w: 152 },
      ],
    },
  ],
  strip: { x: 14, y: 304, w: 612 },
  open: { x: 230, y: 70, s: 1.4 },
  whole: { x: 320, y: 180, s: 1 },
}

const NARROW: Layout = {
  w: 360,
  h: 480,
  cmd: { x: 14, y: 10, w: 332, h: 44, lines: [['$ hmz exec ', ARG_F, ' ', ARG_A], ['    ', ARG_P, ' "…"']] },
  tiers: [
    { y: 74, at: [0, 1, 2].map((i) => ({ x: 14 + i * 113, y: 74, w: 106 })) },
    { y: 136, at: [0, 1].map((i) => ({ x: 14 + i * 170, y: 136, w: 162 })) },
    {
      y: 198,
      at: [
        { x: 14, y: 198, w: 162 },
        { x: 184, y: 198, w: 162 },
        { x: 14, y: 246, w: 162 },
        { x: 184, y: 246, w: 162 },
      ],
    },
    {
      y: 310,
      at: [
        { x: 14, y: 310, w: 162 },
        { x: 184, y: 310, w: 162 },
        { x: 14, y: 358, w: 162 },
        { x: 184, y: 358, w: 162 },
      ],
    },
  ],
  strip: { x: 14, y: 414, w: 332 },
  open: { x: 180, y: 80, s: 1.3 },
  whole: { x: 180, y: 240, s: 1 },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

/** Every card, by key, where it is. */
const place = computed(() => {
  const out: Record<string, Place> = {}
  TIERS.forEach((t, i) => t.nodes.forEach((n, j) => (out[n.key] = L.value.tiers[i].at[j])))
  return out
})
const P = (key: string) => place.value[key]
const top = (key: string) => ({ x: P(key).x + P(key).w / 2, y: P(key).y })
const mid = (key: string) => ({ x: P(key).x + P(key).w / 2, y: P(key).y + NODE_H / 2 })
const bottom = (key: string) => ({ x: P(key).x + P(key).w / 2, y: P(key).y + NODE_H })

/** The route the request takes down the left of the map: CLI to Flows to Agents. */
const edge1 = computed(() => `M${EDGE_X} ${P('cli').y + NODE_H} L${EDGE_X} ${P('flows').y}`)
const edge2 = computed(() => `M${EDGE_X} ${P('flows').y + NODE_H} L${EDGE_X} ${P('agents').y}`)
const edge3 = computed(() => {
  const a = P('agents')
  const m = P('machines')
  const y = a.y + NODE_H / 2
  return `M${a.x + a.w} ${y} L${m.x} ${y}`
})

const scene = useScene({
  still: 'rest',
  repeatDelay: 1.2,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const at = (sel: string) => q(sel)
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), fx: () => fx, start: l.open })
    const lane1 = () => palette.lane[0]
    const lane3 = () => palette.lane[2]
    const ok = () => palette.accent
    const warm = () => palette.warm

    const light = (key: string, when: number) => {
      tl.to(one(`.lit-${key}`), { opacity: 1, duration: 0.4 }, when)
      tl.fromTo(one(`.badge-${key}`), { opacity: 0, x: 6 }, { opacity: 1, x: 0, duration: 0.45 }, when + 0.1)
    }
    const arg = (cls: string, when: number) => {
      tl.to(at(`.${cls}`), { fill: 'var(--hmz-lane-1)', duration: 0.3 }, when)
      tl.to(at(`.${cls}-hl`), { opacity: 1, duration: 0.3 }, when)
    }
    const argAt = (cls: string) => {
      const r = one(`.${cls}-hl`) as SVGGraphicsElement | undefined
      return r ? { x: Number(r.getAttribute('x')) + Number(r.getAttribute('width')) / 2, y: Number(r.getAttribute('y')) + 16 } : top('cli')
    }

    // Each highlight is put under its part of the line as the font draws it, not as a guess.
    const texts = at('.cmd-text') as SVGTextElement[]
    for (const r of at('.arg-hl')) {
      const t = texts[Number(r.getAttribute('data-line'))]
      const from = Number(r.getAttribute('data-from'))
      const len = Number(r.getAttribute('data-len'))
      try {
        const x = t.getStartPositionOfChar(from).x
        r.setAttribute('x', String(x - 2))
        r.setAttribute('width', String(t.getSubStringLength(from, len) + 4))
      } catch {
        // Not laid out yet: the guess in the markup stands.
      }
    }

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.lit, .badge, .tier-label, .edge-word, .arg-hl, .strip-line'), { opacity: 0 }, 0)
    tl.set(at('.wire'), { drawSVG: '0%' }, 0)
    tl.set(one('.type-clip'), { attr: { width: 0 } }, 0)
    tl.set(at('.strip-clip'), { attr: { width: 0 } }, 0)

    // 0 · the map: a tier at a time, a card per page, each with its package.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.cmd'), { opacity: 0 }, { opacity: 1, duration: 0.5 }, 0.1)
    TIERS.forEach((_, i) => {
      const t = 0.3 + i * 0.55
      tl.to(at('.tier-label')[i], { opacity: 1, duration: 0.5 }, t)
      tl.fromTo(at(`.tier-${i} .node`), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.09 }, t)
    })
    tl.fromTo(one('.strip'), { opacity: 0 }, { opacity: 1, duration: 0.5 }, 2.4)
    cam.shot(l.whole, 0.6, 2.6)

    // 1 · the line is typed, and the CLI takes it, reading its environment as it starts.
    const T1 = 3.6
    tl.addLabel('beat-1', T1)
    tl.to(one('.type-clip'), { attr: { width: l.cmd.w }, duration: 1.6, ease: 'none' }, T1)
    cam.beam({ x: l.cmd.x + 60, y: l.cmd.y + l.cmd.h }, top('cli'), lane1, T1 + 1.5, { duration: 0.6, bend: 0.2 })
    light('cli', T1 + 2.1)
    cam.flare(top('cli'), lane1, T1 + 2.1, 16)
    cam.beam(mid('cli'), top('env'), warm, T1 + 2.4, { duration: 1, bend: -0.12 })
    tl.to(one('.lit-env'), { opacity: 0.7, duration: 0.4 }, T1 + 3.3)

    // 2 · `-f twice` and `-p budget.cost=1`: the runner reads the flow and the budget, and runs it.
    const T2 = T1 + 4
    tl.addLabel('beat-2', T2)
    arg('arg-f', T2)
    arg('arg-p', T2 + 0.3)
    cam.beam(argAt('arg-f'), mid('cli'), lane1, T2 + 0.3, { duration: 0.5, bend: 0.2 })
    tl.to(one('.wire-1'), { drawSVG: '100%', duration: 0.7, ease: 'cine' }, T2 + 0.8)
    tl.to(one('.edge-word-1'), { opacity: 1, duration: 0.4 }, T2 + 1)
    cam.beam({ x: EDGE_X, y: P('cli').y + NODE_H }, { x: EDGE_X, y: P('flows').y + 4 }, lane1, T2 + 0.8, { duration: 0.7, bend: 0 })
    light('flows', T2 + 1.5)
    cam.flare({ x: EDGE_X, y: P('flows').y + 4 }, lane1, T2 + 1.5, 16)

    // 3 · `-a builder=claude/…`: the flow's turn goes down to the driver, which runs the CLI as
    //     the machine's own login, in the workspace; the answer comes back up.
    const T3 = T2 + 3
    tl.addLabel('beat-3', T3)
    arg('arg-a', T3)
    cam.shot({ x: narrow.value ? 180 : 300, y: narrow.value ? 230 : 190, s: 1.12 }, T3, 1.6)
    tl.to(one('.wire-2'), { drawSVG: '100%', duration: 0.7, ease: 'cine' }, T3 + 0.4)
    tl.to(one('.edge-word-2'), { opacity: 1, duration: 0.4 }, T3 + 0.6)
    cam.beam({ x: EDGE_X, y: P('flows').y + NODE_H }, { x: EDGE_X, y: P('agents').y + 4 }, lane1, T3 + 0.4, { duration: 0.7, bend: 0 })
    light('agents', T3 + 1.1)
    cam.beam(mid('agents'), narrow.value ? top('providers') : top('providers'), lane3, T3 + 1.4, { duration: 0.8, bend: narrow.value ? 0.3 : -0.25 })
    light('providers', T3 + 2.2)
    tl.to(one('.wire-3'), { drawSVG: '100%', duration: 0.4, ease: 'cine' }, T3 + 2.3)
    cam.beam({ x: P('agents').x + P('agents').w - 10, y: mid('agents').y }, mid('machines'), lane1, T3 + 2.3, { duration: 0.6, bend: 0.1 })
    light('machines', T3 + 2.9)
    cam.flare(mid('machines'), lane1, T3 + 2.9, 22)
    cam.beam(mid('machines'), mid('agents'), ok, T3 + 3.4, { duration: 0.5, bend: -0.25 })
    cam.beam({ x: EDGE_X + 10, y: P('agents').y }, { x: EDGE_X + 10, y: P('flows').y + NODE_H }, ok, T3 + 3.9, { duration: 0.4, bend: 0 })
    cam.beam({ x: EDGE_X + 10, y: P('flows').y }, { x: EDGE_X + 10, y: P('cli').y + NODE_H }, ok, T3 + 4.3, { duration: 0.4, bend: 0 })

    // 4 · the run is written down: an epic, read back as a trace.
    const T4 = T3 + 5.2
    tl.addLabel('beat-4', T4)
    cam.shot(l.whole, T4, 1.6)
    cam.beam(mid('flows'), top('tracing'), warm, T4 + 0.3, { duration: 0.9, bend: 0.25 })
    cam.beam(mid('flows'), top('files'), warm, T4 + 0.5, { duration: 0.9, bend: 0.2 })
    tl.to(at('.lit-tracing, .lit-files'), { opacity: 1, duration: 0.4, stagger: 0.2 }, T4 + 1.2)
    cam.flare(top('files'), warm, T4 + 1.3, 18)
    cam.beam(bottom('files'), { x: l.strip.x + 30, y: l.strip.y + 4 }, warm, T4 + 1.5, { duration: 0.6, bend: -0.15 })
    tl.to(at('.strip-line'), { opacity: 1, duration: 0.2, stagger: 0.6 }, T4 + 2)
    tl.to(at('.strip-clip'), { attr: { width: l.strip.w }, duration: 1.1, ease: 'none', stagger: 0.6 }, T4 + 2)

    tl.addLabel('rest', T4 + 4)
    cam.shot({ ...l.whole, s: l.whole.s * 1.025 }, T4 + 2.4, 3, 'sine.inOut')
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 6)
  },
})

/** Where each part of the command line starts, in monospace columns. */
const CH = 6.6
const cols = (line: string[]) => {
  let c = 0
  return line.map((part) => {
    const from = c
    c += part.length
    return { part, from }
  })
}
const argClass = (part: string) => (part === ARG_F ? 'arg-f' : part === ARG_A ? 'arg-a' : part === ARG_P ? 'arg-p' : '')
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="3 / 4"
    label="The reference as a map of humanize as built, a card per page with the package it covers. What you type into: CLI, hmz.cli; TUI, hmz.tui; Daemon, hmz.daemon. The Python you write against: Flows, hmz.flows; SDK, hmz.sdk. Below the flow API, all in hmz.coganchor: Agents, Machines, Providers, Remote execution. What a run reads and leaves behind: Tracing, hmz.runtime; Files; Environment variables; Settings. One request is followed through it: hmz exec -f twice -a builder=claude/… -p budget.cost=1 is typed into the CLI, which reads its environment as it starts; the runtime's runner reads the flow and its budget and runs twice; its turn goes through the runtime's flowing drivers to the claude agent driver, which runs the CLI as local, on this machine, in the workspace, and the answer comes back up; the run is written down as an epic under ~/.hmz/epics, with epic.jsonl and the sessions' logs, which Tracing reads back."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <clipPath id="ref-atlas-type"><rect class="type-clip" :x="L.cmd.x" :y="L.cmd.y" :width="L.cmd.w" :height="L.cmd.h" /></clipPath>
        <clipPath id="ref-atlas-strip-0"><rect class="strip-clip" :x="L.strip.x" :y="L.strip.y" :width="L.strip.w" height="24" /></clipPath>
        <clipPath id="ref-atlas-strip-1"><rect class="strip-clip" :x="L.strip.x" :y="L.strip.y + 24" :width="L.strip.w" height="20" /></clipPath>
      </defs>
      <g class="world">
        <!-- the line typed -->
        <g class="cmd">
          <rect class="cmd-box" :x="L.cmd.x" :y="L.cmd.y" :width="L.cmd.w" :height="L.cmd.h" rx="7" />
          <g clip-path="url(#ref-atlas-type)">
            <template v-for="(line, i) in L.cmd.lines" :key="`l${i}`">
              <template v-for="c in cols(line)" :key="`h${i}-${c.from}`">
                <rect
                  v-if="argClass(c.part)"
                  class="arg-hl"
                  :class="`${argClass(c.part)}-hl`"
                  :data-line="i"
                  :data-from="c.from"
                  :data-len="c.part.length"
                  :x="L.cmd.x + 10 + c.from * CH - 2"
                  :y="L.cmd.y + 4 + i * 18"
                  :width="c.part.length * CH + 4"
                  height="18"
                  rx="3"
                />
              </template>
              <text class="cmd-text" :x="L.cmd.x + 10" :y="L.cmd.y + 17 + i * 18"><tspan v-for="c in cols(line)" :key="c.from" :class="argClass(c.part)">{{ c.part }}</tspan></text>
            </template>
          </g>
        </g>

        <!-- the tiers -->
        <g v-for="(t, i) in TIERS" :key="t.label" :class="`tier tier-${i}`">
          <text class="tier-label" :x="L.w - 14" :y="L.tiers[i].y - 7" text-anchor="end">{{ t.label }}</text>
          <g v-for="n in t.nodes" :key="n.key" class="node">
            <rect class="node-box" :x="P(n.key).x" :y="P(n.key).y" :width="P(n.key).w" :height="NODE_H" rx="7" />
            <rect class="lit" :class="`lit-${n.key}`" :x="P(n.key).x" :y="P(n.key).y" :width="P(n.key).w" :height="NODE_H" rx="7" />
            <text class="node-name" :x="P(n.key).x + 10" :y="P(n.key).y + 17">{{ n.name }}</text>
            <text class="node-sub" :x="P(n.key).x + 10" :y="P(n.key).y + 32">{{ n.sub }}</text>
            <g v-if="n.badge" class="badge" :class="`badge-${n.key}`">
              <text :x="P(n.key).x + P(n.key).w - 9" :y="P(n.key).y + 17" text-anchor="end">{{ narrow && n.short ? n.short : n.badge }}</text>
            </g>
          </g>
        </g>

        <!-- the route, along edges the layering table allows -->
        <path class="wire wire-1" :d="edge1" />
        <path class="wire wire-2" :d="edge2" />
        <path class="wire wire-3" :d="edge3" />
        <g class="edge-word edge-word-1"><text :x="EDGE_X + 8" :y="P('flows').y - 7">runtime.runner</text></g>
        <g class="edge-word edge-word-2"><text :x="EDGE_X + 8" :y="P('agents').y - 7">runtime.flowing</text></g>

        <!-- what the run left -->
        <g class="strip">
          <rect class="strip-box" :x="L.strip.x" :y="L.strip.y" :width="L.strip.w" height="44" rx="7" />
          <g class="strip-line" clip-path="url(#ref-atlas-strip-0)">
            <text class="strip-path" :x="L.strip.x + 10" :y="L.strip.y + 18">~/.hmz/epics/&lt;ws&gt;/&lt;stamp&gt;-&lt;hex6&gt;/</text>
          </g>
          <g class="strip-line" clip-path="url(#ref-atlas-strip-1)">
            <text class="strip-files" :x="L.strip.x + 22" :y="L.strip.y + 35">epic.jsonl · sessions/claude/…</text>
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

.cmd-box,
.strip-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.cmd-text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  white-space: pre;
  fill: var(--hmz-stage-ink);
}

.arg-hl {
  fill: var(--hmz-lane-1);
  fill-opacity: 0.16;
}

.tier-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.node-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.lit {
  fill: var(--hmz-lane-1);
  fill-opacity: 0.12;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.8;
}

.lit-providers {
  fill: var(--hmz-lane-3);
  stroke: var(--hmz-lane-3);
}

.lit-env,
.lit-tracing,
.lit-files {
  fill: var(--hmz-warm);
  stroke: var(--hmz-warm);
}

.node-name {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.node-sub {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.badge text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-lane-1);
}

.badge-providers text {
  fill: var(--hmz-lane-3);
}

.wire {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
  stroke-dasharray: 5 4;
}

.edge-word text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-lane-1);
}

.strip-box {
  stroke: var(--hmz-warm);
  stroke-opacity: 0.6;
}

.strip-path {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-warm);
}

.strip-files {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}
</style>
