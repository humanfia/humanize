<script setup lang="ts">
// One frame of a scene: the layout, the camera and the time go in, and every primitive of the
// grammar comes out, projected. Nothing here keeps state -- the player, the cards and the
// reduced-motion picture are all this component at some `t` and some camera.
import { computed, useId } from 'vue'

import type { Does, RoleKind } from '../../flows'
import FlowGate from './FlowGate.vue'
import FlowHead from './FlowHead.vue'
import FlowLoop from './FlowLoop.vue'
import FlowMeter from './FlowMeter.vue'
import FlowPlate from './FlowPlate.vue'
import FlowTurn from './FlowTurn.vue'
import FlowWire, { type Dot } from './FlowWire.vue'
import { doesOf, SIZE } from './grammar'
import {
  cubic,
  type Cam,
  kidWidth,
  type LaneG,
  type Layout,
  matrix,
  type P3,
  place,
  project,
  spentAt,
  stateAt,
  through,
  type TurnG,
  type View,
} from './stage'
import './grammar.css'

const props = withDefaults(
  defineProps<{
    lay: Layout
    view: View
    cam: Cam
    t: number
    /** `play` moves; `still` is the whole run at rest, every label showing. */
    mode?: 'play' | 'still'
    /** A card's small picture: the marks alone, with no words at all. */
    bare?: boolean
    /** Whether the picture fades out and back in where the run loops, which only a run that is
     *  playing does: one paused or scrubbed to either end stays in sight. */
    fades?: boolean
  }>(),
  { mode: 'play', bare: false, fades: false },
)

const shade = `flow-shade-${useId()}`

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v))
const lerp = (a: number, b: number, u: number) => a + (b - a) * u
const f = (n: number) => n.toFixed(1)

/** Motes far behind the scene, which the camera's moves set drifting at their own speed: the
 *  parallax that says the picture has depth. The same scatter every time. */
const dust = computed(() => {
  let seed = 7
  const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646
  return Array.from({ length: 42 }, () => [
    -200 + rand() * (props.lay.width + 400),
    -120 + rand() * (props.lay.height + 240),
    260 + rand() * 1300,
  ] as P3)
})

/** What one step of a split's copies is: the line a lemma runs, in small. */
const LINE: [RoleKind, Does][] = [
  ['maker', 'plan'],
  ['maker', 'work'],
  ['checker', 'read'],
  ['maker', 'work'],
  ['program', 'run'],
]

type State = 'waiting' | 'running' | 'landed'

const frame = computed(() => {
  const { lay, view, cam, t, mode, bare } = props
  const play = mode === 'play'
  const fan = cam.fan
  const P = (p: P3) => project(cam, view, p)
  const M = (p: P3) => place(cam, view, p)
  const X = (u: number) => SIZE.x0 + u * lay.beat
  // Lanes fold onto one another more slowly than they move apart in depth, so that half way
  // through a fan no two layers are in the same place at once.
  const fold = fan * fan
  const yOf = (lane: LaneG) => lerp(lane.y, lane.ys, fold)
  const zOf = (lane: LaneG) => lane.zf * fan
  const pulse = 0.5 + 0.5 * Math.sin(t * Math.PI * 1.9)
  const bottom = lerp(lay.lanesBottom, lay.lanesBottomS, fold)
  const lastT = Math.max(...lay.turns.map((g) => g.t1))
  const path = (at: (u: number) => P3, u0: number, u1: number, n: number) => {
    const pts: string[] = []
    for (let k = 0; k <= n; k++) {
      const p = P(at(lerp(u0, u1, k / n)))
      pts.push(`${f(p.x)} ${f(p.y)}`)
    }
    return `M ${pts.join(' L ')}`
  }
  const bezier =
    (A: P3, C1: P3, C2: P3, B: P3) =>
    (u: number): P3 => [
      cubic(A[0], C1[0], C2[0], B[0], u),
      cubic(A[1], C1[1], C2[1], B[1], u),
      cubic(A[2], C1[2], C2[2], B[2], u),
    ]

  /* The layers: one for each depth the lanes sit at, drawn far to near, each a little hazier
     the further it is. Laid flat there is just the one. */
  type Layer = {
    key: string
    z: number
    fog: number
    plates: { key: string; points: string; m: string; name: string; lit: boolean }[]
    rails: { key: string; d: string }[]
    threads: { key: string; d: string; w: number; kind: RoleKind; on: boolean }[]
    turns: { key: string; m: string; w: number; kind: RoleKind; g: TurnG; state: State; progress: number; ignite: number }[]
    playhead: string
  }
  const layers = new Map<number, Layer>()
  const layerOf = (zf: number): Layer => {
    let layer = layers.get(zf)
    if (!layer) {
      const z = zf * fan
      const d = P([lay.width / 2, bottom / 2, z]).d
      layer = {
        key: `z${zf}`,
        z,
        fog: bare ? 1 : clamp(1 - Math.max(0, d) / 1500, 0.42, 1),
        plates: [],
        rails: [],
        threads: [],
        turns: [],
        playhead: '',
      }
      layers.set(zf, layer)
    }
    return layer
  }

  const running = new Set(lay.turns.filter((g) => stateAt(g, t) === 'running').map((g) => g.lane.role.id))

  for (const plate of lay.plates) {
    const layer = layerOf(plate.zf)
    const y0 = lerp(plate.y0, plate.ys0, fold)
    const y1 = lerp(plate.y1, plate.ys1, fold)
    const x0 = 6
    const x1 = lay.gateX - 16
    const pts = [
      [x0, y0],
      [x1, y0],
      [x1, y1],
      [x0, y1],
    ].map(([x, y]) => P([x, y, layer.z]))
    layer.plates.push({
      key: plate.env.id,
      points: pts.map((p) => `${f(p.x)},${f(p.y)}`).join(' '),
      m: M([x0, y0, layer.z]).m,
      name: plate.env.name,
      lit: play && lay.lanes.some((l) => l.role.env === plate.env.id && running.has(l.role.id)),
    })
  }

  /* The lane heads go on top of everything, and while the camera is close on a flat scene they
     keep to the left edge of the frame, over a shade, so a lane is never without its name. */
  const heads: { key: string; m: string; kind: RoleKind; name: string; note: string; glow: number; fog: number }[] = []
  let pushed = 0
  let shadeW = 0
  for (const lane of lay.lanes) {
    const layer = layerOf(lane.zf)
    const y = yOf(lane)
    const z = zOf(lane)
    const a = P([SIZE.x0 - 16, y, z])
    const b = P([lay.gateX - 22, y, z])
    layer.rails.push({ key: lane.role.id, d: `M ${f(a.x)} ${f(a.y)} L ${f(b.x)} ${f(b.y)}` })
    const { k } = M([SIZE.head, y, z])
    if (play && !bare && fan < 0.02) {
      const edge = 20 * k[0] + 6
      if (k[4] < edge) {
        pushed = Math.max(pushed, edge - k[4])
        k[4] = edge
      }
      shadeW = Math.max(shadeW, k[4] + 150 * k[0])
    }
    heads.push({
      key: lane.role.id,
      m: matrix(k),
      kind: lane.kind,
      name: lane.role.name,
      note: lane.role.note,
      glow: play && running.has(lane.role.id) ? 0.55 + 0.45 * pulse : 0,
      fog: layer.fog,
    })
  }

  for (const g of lay.turns) {
    const layer = layerOf(g.lane.zf)
    const y = yOf(g.lane)
    const z = zOf(g.lane)
    const state = play ? stateAt(g, t) : 'landed'
    if (g.prev) {
      // The held session's thread: from the turn it continues, under both, thicker for every
      // turn the session has already taken.
      const a = P([g.prev.x0 + 18, y, z])
      const b = P([g.x1 - 18, y, z])
      layer.threads.push({
        key: g.turn.id,
        d: `M ${f(a.x)} ${f(a.y)} L ${f(b.x)} ${f(b.y)}`,
        w: (3 + 2.2 * g.depth) * a.s,
        kind: g.lane.kind,
        on: state !== 'waiting',
      })
    }
    layer.turns.push({
      key: g.turn.id,
      m: M([g.x0, y, z]).m,
      w: g.x1 - g.x0,
      kind: g.lane.kind,
      g,
      state,
      progress: through(g, t),
      ignite: play && g.turn.session === 'new' ? (t - g.t0) / 0.45 : -1,
    })
  }

  if (play && t >= 0 && t <= lastT) {
    for (const [zf, layer] of layers) {
      const ys = lay.lanes.filter((l) => l.zf === zf).map(yOf)
      if (!ys.length) continue
      const a = P([X(t), Math.min(...ys) - 30, layer.z])
      const b = P([X(t), Math.max(...ys) + 30, layer.z])
      layer.playhead = `M ${f(a.x)} ${f(a.y)} L ${f(b.x)} ${f(b.y)}`
    }
  }

  const ordered = [...layers.values()].sort(
    (a, b) => P([lay.width / 2, bottom / 2, b.z]).d - P([lay.width / 2, bottom / 2, a.z]).d,
  )

  /* What is handed on. */
  const wires = lay.passes.map((pass) => {
    const from = pass.from
    const A: P3 = [from.x1, yOf(from.lane), zOf(from.lane)]
    const B: P3 = pass.to ? [pass.to.x0, yOf(pass.to.lane), zOf(pass.to.lane)] : [lay.gateX - 2, A[1], A[2]]
    const flat = Math.abs(A[1] - B[1]) < 1 && A[2] === B[2]
    const bend = clamp((B[0] - A[0]) * 0.5, 26, 80)
    const at = bezier(A, flat ? A : [A[0] + bend, A[1], A[2]], flat ? B : [B[0] - bend, B[1], B[2]], B)
    const p = play ? clamp((t - pass.t0) / (pass.t1 - pass.t0), 0, 1) : 1
    const trail: Dot[] = []
    let head: { x: number; y: number; s: number } | null = null
    if (play && p > 0 && p < 1) {
      const h = P(at(p))
      head = { x: h.x, y: h.y, s: h.s }
      for (let k = 1; k <= 9; k++) {
        const u = p - k * 0.028
        if (u <= 0) break
        const q = P(at(u))
        trail.push({ x: q.x, y: q.y, r: 4 * (1 - k / 10) * q.s, o: 0.55 * (1 - k / 10) })
      }
    }
    const sparks: Dot[] = []
    const since = (t - pass.t1) / 0.4
    if (play && since >= 0 && since < 1) {
      const end = P(B)
      for (let k = 0; k < 7; k++) {
        const angle = (k / 7) * Math.PI * 2 + 0.4
        const r = (6 + 22 * since) * end.s
        sparks.push({ x: end.x + Math.cos(angle) * r, y: end.y + Math.sin(angle) * r, r: 2.3 * (1 - since) * end.s, o: 1 - since })
      }
    }
    const mid = flat ? P([(A[0] + B[0]) / 2, A[1] - 31, A[2]]) : P(at(0.5))
    const labelOn = bare
      ? 0
      : !play
        ? 1
        : p <= 0
          ? 0
          : t < pass.t1 + 0.9
            ? clamp(p * 5, 0, 1)
            : clamp(1 - (t - pass.t1 - 0.9) / 0.4, 0, 1)
    return {
      key: pass.key,
      kind: from.lane.kind,
      via: pass.via,
      d: path(at, 0, 1, 20),
      lit: p > 0 ? path(at, 0, p, Math.max(2, Math.round(20 * p))) : '',
      trail,
      head,
      sparks,
      said: pass.said,
      at: { x: mid.x, y: mid.y, s: mid.s },
      labelOn,
    }
  })

  /* The loop back. */
  let loop = null as null | {
    d: string
    lit: string
    tip: { x: number; y: number; a: number; s: number }
    head: { x: number; y: number; s: number } | null
    said: string
    at: { x: number; y: number; s: number }
    live: boolean
  }
  if (lay.loop) {
    const { from, to } = lay.loop
    const arcY = bottom + lay.arcOff
    const A: P3 = [from.x1 - 8, yOf(from.lane) + SIZE.turn / 2, zOf(from.lane)]
    const B: P3 = [to.x0 + 10, yOf(to.lane) + SIZE.turn / 2, zOf(to.lane)]
    const at = bezier(A, [A[0] + 10, arcY + 6, A[2]], [B[0] - 10, arcY + 6, B[2]], B)
    const p = play && lay.loop.plays ? clamp((t - lay.loop.t0) / (lay.loop.t1 - lay.loop.t0), 0, 1) : 0
    const live = p > 0 && p < 1
    const end = P(B)
    const near = P(at(0.94))
    const mid = P(at(0.5))
    const h = live ? P(at(p)) : null
    loop = {
      d: path(at, 0, 1, 28),
      lit: live ? path(at, 0, p, Math.max(2, Math.round(28 * p))) : '',
      tip: { x: end.x, y: end.y, a: (Math.atan2(end.y - near.y, end.x - near.x) * 180) / Math.PI, s: end.s },
      head: h ? { x: h.x, y: h.y, s: h.s } : null,
      said: lay.loop.said,
      at: { x: mid.x, y: mid.y, s: mid.s },
      live,
    }
  }

  /* The finish, and the budget. */
  const gateH = Math.max(bottom - lay.lanesTop, lay.scene.ends.length * 26 + 44)
  const fired = !play ? 1 : t >= lay.firedAt ? Math.max(0.001, clamp((t - lay.firedAt) / 0.8, 0, 1)) : 0
  const gate = { m: M([lay.gateX, lay.lanesTop - 4, 0]).m, h: gateH, fired }
  const meter =
    lay.scene.budget === false
      ? null
      : {
          m: M([SIZE.x0, bottom + lay.meterOff, 0]).m,
          w: lay.gateX - SIZE.x0 - 24,
          fill: play ? spentAt(lay, t) : spentAt(lay, lay.firedAt),
        }

  /* A split: copies of the line, a level down, flown in from the depth as the part splits. */
  const kids: {
    key: string
    points: string
    m: string
    name: string
    drop: string
    minis: { key: string; m: string; w: number; kind: RoleKind; does: Does; state: State }[]
    o: number
  }[] = []
  if (lay.split && cam.open > 0.01) {
    const s = lay.split
    const w = kidWidth(lay)
    const cw = (w - 20) / LINE.length - 6
    for (let k = 0; k < s.into; k++) {
      const z = (1 - cam.open) * (420 + 160 * k)
      const x0 = s.at.x0 + k * (w + 18)
      const y0 = bottom + lay.splitOff
      const y1 = y0 + 56
      const pts = [
        [x0, y0],
        [x0 + w, y0],
        [x0 + w, y1],
        [x0, y1],
      ].map(([x, y]) => P([x, y, z]))
      const q = play ? clamp((t - s.t0 - 0.25 - 0.3 * k) / Math.max(0.4, s.t1 - s.t0 - 0.6), 0, 1) : 1
      const top = P([(s.at.x0 + s.at.x1) / 2, yOf(s.at.lane) + SIZE.turn / 2, 0])
      const land = P([x0 + w / 2, y0, z])
      kids.push({
        key: `k${k}`,
        points: pts.map((p) => `${f(p.x)},${f(p.y)}`).join(' '),
        m: M([x0, y0, z]).m,
        name: `lemma ${k + 1}: ${k === 0 ? s.said : 'the same line'}`,
        drop: `M ${f(top.x)} ${f(top.y)} L ${f(land.x)} ${f(land.y)}`,
        minis: LINE.map(([kind, does], j) => ({
          key: `${k}-${j}`,
          m: M([x0 + 10 + j * (cw + 6), y0 + 36, z]).m,
          w: cw,
          kind,
          does,
          state: q * LINE.length >= j + 1 ? 'landed' : q * LINE.length > j ? 'running' : 'waiting',
        })),
        o: cam.open,
      })
    }
  }

  const motes =
    play && !bare
      ? dust.value.map((p) => {
          const q = P(p)
          return { x: q.x, y: q.y, r: 1.5 * q.s + 0.3, o: clamp(0.5 - q.d / 3600, 0.08, 0.45) }
        })
      : []

  const fade = !play || !props.fades
    ? 0
    : t > lay.end - 0.4
      ? clamp((t - (lay.end - 0.4)) / 0.4, 0, 1)
      : t < lay.start + 0.35
        ? 1 - (t - lay.start) / 0.35
        : 0

  return {
    layers: ordered,
    heads,
    shade: pushed > 0 ? { w: shadeW, o: clamp(pushed / 30, 0, 1) } : null,
    wires,
    loop,
    gate,
    meter,
    kids,
    motes,
    fade,
    pulse,
  }
})
</script>

<template>
  <svg
    class="hmz-flow f-scene"
    :class="[mode, { bare }]"
    :viewBox="`0 0 ${view.w} ${view.h}`"
    :width="view.w"
    :height="view.h"
    aria-hidden="true"
    focusable="false"
  >
    <defs>
      <linearGradient :id="shade" x1="0" x2="1" y1="0" y2="0">
        <stop offset="0" style="stop-color: var(--hmz-panel-bg); stop-opacity: 0.96" />
        <stop offset="0.72" style="stop-color: var(--hmz-panel-bg); stop-opacity: 0.85" />
        <stop offset="1" style="stop-color: var(--hmz-panel-bg); stop-opacity: 0" />
      </linearGradient>
    </defs>
    <g :opacity="1 - frame.fade">
      <circle
        v-for="(mote, n) in frame.motes"
        :key="`d${n}`"
        class="f-mote"
        :cx="mote.x"
        :cy="mote.y"
        :r="mote.r"
        :opacity="mote.o"
      />

      <g v-for="layer in frame.layers" :key="layer.key" class="f-layer" :opacity="layer.fog">
        <FlowPlate
          v-for="plate in layer.plates"
          :key="plate.key"
          :points="plate.points"
          :m="plate.m"
          :name="plate.name"
          :lit="plate.lit"
          :bare="bare"
        />
        <path v-for="rail in layer.rails" :key="rail.key" class="f-rail" :d="rail.d" />
        <path
          v-for="thread in layer.threads"
          :key="thread.key"
          class="f-thread"
          :class="[`k-${thread.kind}`, { on: thread.on }]"
          :d="thread.d"
          :stroke-width="thread.w"
        />
        <path v-if="layer.playhead" class="f-now" :d="layer.playhead" />
        <g v-for="turn in layer.turns" :key="turn.key" :transform="turn.m">
          <FlowTurn
            :kind="turn.kind"
            :w="turn.w"
            :session="turn.g.turn.session"
            :does="doesOf(turn.kind, turn.g.turn.does)"
            :state="turn.state"
            :progress="turn.progress"
            :ignite="turn.ignite"
            :pulse="frame.pulse"
            :lines="turn.g.lines"
            :inside="turn.g.turn.inside ?? 0"
            :calls="turn.g.turn.calls ?? ''"
            :bare="bare"
          />
        </g>
      </g>

      <!-- a split's copies, a level down -->
      <g v-for="kid in frame.kids" :key="kid.key" class="f-kid" :opacity="kid.o">
        <path class="drop" :d="kid.drop" />
        <polygon class="floor" :points="kid.points" />
        <g v-if="!bare" :transform="kid.m">
          <text class="name" x="10" y="16">{{ kid.name }}</text>
        </g>
        <g v-for="mini in kid.minis" :key="mini.key" :transform="mini.m">
          <g transform="scale(0.5)">
            <FlowTurn :kind="mini.kind" :w="mini.w * 2" session="new" :does="mini.does" :state="mini.state" bare />
          </g>
        </g>
      </g>

      <FlowLoop
        v-if="frame.loop"
        :d="frame.loop.d"
        :lit="frame.loop.lit"
        :tip="frame.loop.tip"
        :head="frame.loop.head"
        :said="frame.loop.said"
        :at="frame.loop.at"
        :live="frame.loop.live"
        :bare="bare"
      />

      <FlowWire
        v-for="wire in frame.wires"
        :key="wire.key"
        :kind="wire.kind"
        :via="wire.via"
        :d="wire.d"
        :lit="wire.lit"
        :trail="wire.trail"
        :head="wire.head"
        :sparks="wire.sparks"
        :said="wire.said"
        :at="wire.at"
        :label-on="wire.labelOn"
      />

      <g :transform="frame.gate.m">
        <FlowGate :ends="lay.scene.ends" :h="frame.gate.h" :fired="frame.gate.fired" :bare="bare" />
      </g>

      <g v-if="frame.meter" :transform="frame.meter.m">
        <FlowMeter :w="frame.meter.w" :fill="frame.meter.fill" :bare="bare" />
      </g>

      <rect
        v-if="frame.shade"
        class="f-shade"
        x="0"
        y="0"
        :width="frame.shade.w"
        :height="view.h"
        :fill="`url(#${shade})`"
        :opacity="frame.shade.o"
      />
      <g v-for="head in frame.heads" :key="head.key" :transform="head.m" :opacity="head.fog">
        <FlowHead :kind="head.kind" :name="head.name" :note="head.note" :glow="head.glow" :bare="bare" />
      </g>
    </g>
  </svg>
</template>
