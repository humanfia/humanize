// A scene, laid out in a small three-dimensional world, and the camera that films it.
//
// `lay` turns a scene from `theme/flows.ts` into geometry once: where each lane, turn, pass,
// plate, loop, finish and budget bar sits, and when each turn starts and ends, in beats. The
// whole of a run is then a pure function of one number, the time `t` in beats: which turns are
// running, where every comet is, how full the budget is, and where the camera stands
// (`direct`). That is what makes the player scrubbable and the reduced-motion picture exact:
// both are the same function at another `t`.
//
// The world is x along time, y down the lanes and z into the screen. Everything is drawn in
// SVG, each element flat on its plane and placed by the affine matrix the perspective gives at
// its own origin (`place`), which at these sizes is indistinguishable from true perspective and
// keeps text as text. Curves are sampled and projected point by point.
import { gsap } from 'gsap'

import type { Env, Outcome, Pass, Role, RoleKind, Scene, Turn } from '../../flows'
import { SIZE } from './grammar'

export interface LaneG {
  role: Role
  kind: RoleKind
  i: number
  /** Its centre, laid flat. */
  y: number
  /** Its centre, with the lanes that run at once folded onto one another. */
  ys: number
  /** Its layer, where the scene fans lanes out in depth. */
  stack: number | null
  /** How deep it sits once fanned out: its layer's depth, or, for a lane above the layers --
   *  the one that plans them -- behind them all, so that it looks down on them. */
  zf: number
}

export interface TurnG {
  turn: Turn
  lane: LaneG
  x0: number
  x1: number
  t0: number
  t1: number
  /** The turn before it in the same session, which the thread runs from. */
  prev: TurnG | null
  /** How many turns the session has held before this one: the thread's thickness. */
  depth: number
  lines: string[]
}

export interface PassG {
  key: string
  from: TurnG
  to: TurnG | null
  said: string
  via: Pass['via']
  t0: number
  t1: number
}

export interface PlateG {
  env: Env
  y0: number
  y1: number
  ys0: number
  ys1: number
  zf: number
}

export interface Layout {
  scene: Scene
  lanes: LaneG[]
  turns: TurnG[]
  passes: PassG[]
  plates: PlateG[]
  beat: number
  gateX: number
  /** The widest of the finish's endings, which is how much room the finish takes. */
  gateW: number
  width: number
  /** The top of the first lane and the bottom of the last, laid flat and folded. */
  lanesTop: number
  lanesBottom: number
  lanesBottomS: number
  /** How far under the last lane a split's copies, the loop's arc and the budget bar are. */
  splitOff: number
  arcOff: number
  meterOff: number
  height: number
  heightS: number
  loop: { from: TurnG; to: TurnG; said: string; t0: number; t1: number; plays: boolean } | null
  split: { at: TurnG; into: number; said: string; t0: number; t1: number } | null
  fired: Outcome
  firedAt: number
  /** The beats the whole episode runs, from the opening shot to the fade. */
  start: number
  end: number
  /** Beats of model turns up to the finish, which is what the budget bar measures. */
  spend: number
  /** The beats a step goes between: every moment a turn starts, the loop, and the finish. */
  marks: number[]
}

export const INTRO = 1.1
const HOLD = 2.3
const PLATE_GAP = 16
const PLATE_PAD = 8

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v))
const lerp = (a: number, b: number, u: number) => a + (b - a) * u

/** A label that fits a turn, over one line or two. */
export function wrap(label: string, width: number, px = 6.4): string[] {
  const room = Math.max(5, Math.floor(width / px))
  if (label.length <= room) return [label]
  const words = label.split(' ')
  const one: string[] = []
  while (words.length && [...one, words[0]].join(' ').length <= room) one.push(words.shift()!)
  if (!one.length) return [label.slice(0, room - 1) + '…']
  const two = words.join(' ')
  return [one.join(' '), two.length > room ? two.slice(0, room - 1) + '…' : two]
}

export function lay(scene: Scene): Layout {
  const beat = scene.beat ?? SIZE.beat
  const envs = new Map((scene.envs ?? []).map((env) => [env.id, env]))
  const X = (t: number) => SIZE.x0 + t * beat

  // Lanes, top to bottom, with a little air wherever the workspace changes.
  const lanes: LaneG[] = []
  let y = SIZE.top
  let last: string | undefined = '\u0000'
  for (const [i, role] of scene.roles.entries()) {
    if (i > 0 && role.env !== last) y += PLATE_GAP
    const env = role.env ? envs.get(role.env) : undefined
    lanes.push({ role, kind: role.kind, i, y: y + SIZE.lane / 2, ys: 0, stack: env?.stack ?? null, zf: 0 })
    y += SIZE.lane
    last = role.env
  }
  const lanesTop = SIZE.top
  const lanesBottom = y

  // Folded: every layer's lanes share the rows of the first layer, and what is below moves up.
  const stacked = lanes.filter((lane) => lane.stack !== null)
  const firstY = stacked.length ? Math.min(...stacked.map((l) => l.y)) : 0
  const layerTop = new Map<number, number>()
  for (const lane of stacked) {
    const top = layerTop.get(lane.stack!)
    if (top === undefined || lane.y < top) layerTop.set(lane.stack!, lane.y)
  }
  const layerH = stacked.length
    ? Math.max(...[...layerTop.entries()].map(([s, top]) => {
        const rows = stacked.filter((l) => l.stack === s)
        return Math.max(...rows.map((l) => l.y)) - top + SIZE.lane
      }))
    : 0
  const stackedBottom = stacked.length ? Math.max(...stacked.map((l) => l.y)) + SIZE.lane / 2 : 0
  const shiftUp = stacked.length ? stackedBottom - (firstY - SIZE.lane / 2 + layerH) : 0
  const behind = stacked.length ? (Math.max(...stacked.map((l) => l.stack!)) + 1) * SIZE.stack : 0
  for (const lane of lanes) {
    if (lane.stack !== null) lane.ys = firstY + (lane.y - layerTop.get(lane.stack)!)
    else lane.ys = stacked.length && lane.y > stackedBottom ? lane.y - shiftUp : lane.y
    lane.zf = lane.stack !== null ? lane.stack * SIZE.stack : stacked.length && lane.y < firstY ? behind : 0
  }
  const lanesBottomS = lanesBottom - shiftUp

  const laneOf = new Map(lanes.map((lane) => [lane.role.id, lane]))

  // Turns, in time order, each knowing the turn its session held before it.
  const sorted = [...scene.turns].sort((a, b) => a.at - b.at)
  const lastOf = new Map<string, TurnG>()
  const turns: TurnG[] = []
  for (const turn of sorted) {
    const lane = laneOf.get(turn.role)!
    const x0 = X(turn.at + SIZE.gap)
    const x1 = X(turn.at + (turn.span ?? 1)) - 4
    const before = lastOf.get(turn.role) ?? null
    const prev = turn.session === 'held' ? before : null
    const g: TurnG = {
      turn,
      lane,
      x0,
      x1,
      t0: turn.at + SIZE.gap,
      t1: turn.at + (turn.span ?? 1),
      prev,
      depth: prev ? prev.depth + 1 : 0,
      lines: wrap(turn.label, x1 - x0 - (turn.inside ? 30 : 38)),
    }
    turns.push(g)
    if (turn.session !== 'none') lastOf.set(turn.role, g)
  }
  const byId = new Map(turns.map((g) => [g.turn.id, g]))
  const lastT = Math.max(...turns.map((g) => g.t1))
  const cols = Math.max(...scene.turns.map((t) => t.at + (t.span ?? 1)))
  const gateX = X(cols) + 30
  const gateW = Math.max(...scene.ends.map((end) => end.said.length * 6.1 + 34)) + 22

  const split = scene.split && byId.get(scene.split.at)
  // A pass leaves as its turn ends and lands as the next one starts; a long gap is crossed in
  // its last beat, so what is handed on arrives rather than hangs.
  const passes: PassG[] = []
  for (const g of turns) {
    for (const pass of g.turn.pass ?? []) {
      const to = pass.to === 'end' ? null : byId.get(pass.to) ?? null
      let t0 = g.t1
      let t1 = to ? to.t0 : g.t1 + 0.5
      if (to && t1 - t0 > 0.7) t0 = t1 - 0.6
      if (t1 - t0 < 0.25) t1 = t0 + 0.25
      passes.push({ key: `${g.turn.id}>${pass.to}`, from: g, to, said: pass.said, via: pass.via, t0, t1 })
    }
  }

  let loop: Layout['loop'] = null
  if (scene.loop) {
    const from = byId.get(scene.loop.from)!
    const to = byId.get(scene.loop.to)!
    const ends = (from.turn.pass ?? []).some((p) => p.to === 'end')
    loop = { from, to, said: scene.loop.said, t0: from.t1 + 0.05, t1: from.t1 + 1, plays: !ends }
  }

  const fired = scene.ends[0].is
  const toEnd = passes.filter((p) => !p.to).map((p) => p.t1)
  const firedAt = toEnd.length
    ? Math.max(...toEnd)
    : Math.max(lastT, loop?.plays ? loop.t1 : 0) + 0.3

  const budget = scene.budget !== false
  const splitBand = split ? 84 : 0
  const arcBand = loop ? SIZE.arc : 10
  const meterY = splitBand + arcBand + (budget ? SIZE.meter : 0)
  const gateH = scene.ends.length * 26 + 44
  const height = Math.max(lanesBottom + meterY, lanesTop + gateH) + 16
  const heightS = Math.max(lanesBottomS + meterY, lanesTop + gateH) + 16

  const plates: PlateG[] = []
  for (const env of scene.envs ?? []) {
    const on = lanes.filter((lane) => lane.role.env === env.id)
    if (!on.length) continue
    plates.push({
      env,
      y0: Math.min(...on.map((l) => l.y)) - SIZE.lane / 2 + PLATE_PAD / 2,
      y1: Math.max(...on.map((l) => l.y)) + SIZE.lane / 2 - PLATE_PAD / 2,
      ys0: Math.min(...on.map((l) => l.ys)) - SIZE.lane / 2 + PLATE_PAD / 2,
      ys1: Math.max(...on.map((l) => l.ys)) + SIZE.lane / 2 - PLATE_PAD / 2,
      zf: on[0].zf,
    })
  }

  const model = turns.filter((g) => g.lane.kind !== 'human' && g.lane.kind !== 'program')
  const spend = model.reduce((sum, g) => sum + (Math.min(g.t1, firedAt) - g.t0), 0)

  const marks = [...new Set(turns.map((g) => g.t0))]
  if (loop?.plays) marks.push(loop.t0)
  marks.push(firedAt)
  marks.sort((a, b) => a - b)

  return {
    scene,
    lanes,
    turns,
    passes,
    plates,
    beat,
    gateX,
    gateW,
    width: gateX + gateW,
    lanesTop,
    lanesBottom,
    lanesBottomS,
    splitOff: 12,
    arcOff: splitBand + 26,
    meterOff: meterY - 12,
    height,
    heightS,
    loop,
    split: split
      ? { at: split, into: scene.split!.into, said: scene.split!.said, t0: split.t1, t1: byId.get(split.turn.pass![0].to)!.t0 - 0.6 }
      : null,
    fired,
    firedAt,
    start: -INTRO,
    end: firedAt + HOLD,
    spend,
    marks,
  }
}

/* ------------------------------------------------------------------------------------------
   The camera.
   ------------------------------------------------------------------------------------------ */

export interface Cam {
  /** What it looks at. */
  x: number
  y: number
  z: number
  zoom: number
  /** Degrees: tipped forward to look down on the scene, and turned to look across it. */
  pitch: number
  yaw: number
  /** 0 flat, 1 with the lanes that run at once fanned out in depth. */
  fan: number
  /** 0 closed, 1 with a split's copies open a level down. */
  open: number
}

export interface View {
  w: number
  h: number
}

const DIST = 1200
const RAD = Math.PI / 180

export type P3 = [number, number, number]
export interface P2 {
  x: number
  y: number
  /** How much nearer or further it is than the plane the camera looks at, as a scale. */
  s: number
  /** Its distance into the screen, for depth order and haze. */
  d: number
}

export function project(cam: Cam, view: View, [x, y, z]: P3): P2 {
  const vx = x - cam.x
  const vy = y - cam.y
  const vz = z - cam.z
  const cy = Math.cos(cam.yaw * RAD)
  const sy = Math.sin(cam.yaw * RAD)
  const cp = Math.cos(cam.pitch * RAD)
  const sp = Math.sin(cam.pitch * RAD)
  const x1 = vx * cy + vz * sy
  const z1 = -vx * sy + vz * cy
  const y2 = vy * cp - z1 * sp
  const z2 = vy * sp + z1 * cp
  const d = Math.max(200, DIST + z2)
  const s = (cam.zoom * DIST) / d
  return { x: view.w / 2 + x1 * s, y: view.h / 2 + y2 * s, s, d: z2 }
}

/** The affine matrix that draws something flat at `at` the way perspective would there, as
 *  its six numbers and as the attribute. */
export function place(cam: Cam, view: View, at: P3): { m: string; k: number[]; p: P2 } {
  const p = project(cam, view, at)
  const u = 24
  const px = project(cam, view, [at[0] + u, at[1], at[2]])
  const py = project(cam, view, [at[0], at[1] + u, at[2]])
  const k = [(px.x - p.x) / u, (px.y - p.y) / u, (py.x - p.x) / u, (py.y - p.y) / u, p.x, p.y]
  return { m: matrix(k), k, p }
}

export const matrix = (k: number[]) => `matrix(${k.map((n) => n.toFixed(3)).join(' ')})`

/** The zoom and centre that show the whole of a scene, flat or fanned, from a given angle. */
function wide(
  lay: Layout,
  view: View,
  fan: number,
  pitch: number,
  yaw: number,
  margin = 0.92,
  right = lay.width,
): Cam {
  const bottom = lerp(lay.height, lay.heightS, fan)
  const deepest = Math.max(0, ...lay.lanes.map((l) => l.zf)) * fan
  const zs = deepest ? [0, deepest] : [0]
  const base: Cam = { x: right / 2, y: bottom / 2, z: deepest / 2, zoom: 1, pitch, yaw, fan, open: 0 }
  const pts: P2[] = []
  for (const x of [0, right]) for (const y of [0, bottom]) for (const z of zs) pts.push(project(base, view, [x, y, z]))
  const minX = Math.min(...pts.map((p) => p.x))
  const maxX = Math.max(...pts.map((p) => p.x))
  const minY = Math.min(...pts.map((p) => p.y))
  const maxY = Math.max(...pts.map((p) => p.y))
  const zoom = Math.min((view.w * margin) / (maxX - minX), (view.h * margin) / (maxY - minY))
  // Recentre on what the projection actually covered, which perspective moves off the middle.
  const cx = (minX + maxX) / 2 - view.w / 2
  const cy = (minY + maxY) / 2 - view.h / 2
  return { ...base, x: base.x + cx, y: base.y + cy / Math.cos(pitch * RAD), zoom }
}

export interface Key {
  t: number
  cam: Cam
}

/** The shots, worked out from the scene alone, so every flow is filmed by the same rules:
 *  a crane down onto the whole run, a dolly to each turn as it starts and a slow push while it
 *  runs, a crane up and a fan into depth while lanes run at once, a dive onto the copies where
 *  the work splits, a pull back to the whole for the loop, and a push onto the finish. */
export function direct(lay: Layout, view: View): Key[] {
  const flat = wide(lay, view, 0, 0, 0)
  const fanned = wide(lay, view, 1, 36, -16, 0.96)
  const close = clamp(Math.max(flat.zoom * 1.3, Math.min(1, view.w / (2.4 * lay.beat))), flat.zoom, 1.15)

  const aim = (cam: Cam): Cam => {
    // Never show more than a little past the edges of the scene.
    const hw = view.w / (2 * cam.zoom)
    const hh = view.h / (2 * cam.zoom)
    const bottom = lerp(lay.height, lay.heightS, cam.fan)
    return {
      ...cam,
      x: lay.width < 2 * hw ? lay.width / 2 : clamp(cam.x, hw - 20, lay.width - hw + 20),
      y: bottom < 2 * hh || cam.pitch ? cam.y : clamp(cam.y, hh - 10, bottom - hh + 10),
    }
  }

  /** A shot: the camera is at `cam` by `at`, having taken up to `move` beats to get there. */
  const shots: { at: number; move: number; cam: Cam }[] = []

  const running = (t: number) => lay.turns.filter((g) => g.t0 <= t && t < g.t1)
  const fans = (set: TurnG[]) => new Set(set.filter((g) => g.lane.stack !== null).map((g) => g.lane.stack)).size > 1
  for (const t0 of new Set(lay.turns.map((g) => g.t0))) {
    const set = running(t0 + 0.01)
    let cam: Cam
    if (fans(set)) {
      const lo = Math.min(...set.map((g) => g.x0))
      const hi = Math.max(...set.map((g) => g.x1))
      cam = { ...fanned, x: lerp(fanned.x, (lo + hi) / 2, 0.35) }
    } else {
      // Close on the turns starting, and keep in frame the lanes that just handed them work.
      const from = lay.passes.filter((p) => p.to && set.includes(p.to)).map((p) => p.from)
      const ys = [...set, ...from].map((g) => g.lane.y)
      const lo = Math.min(...ys)
      const hi = Math.max(...ys)
      const x = set.reduce((sum, g) => sum + (g.x0 + g.x1) / 2, 0) / set.length
      const zoom = Math.max(flat.zoom, Math.min(close, (view.h * 0.9) / (hi - lo + SIZE.lane + 50)))
      // Centred in what the lane heads, kept at the left edge, leave free.
      cam = aim({ ...flat, x: x - Math.min(150, view.w * 0.3) / (2 * zoom), y: (lo + hi) / 2, zoom })
    }
    shots.push({ at: t0 + 0.08, move: 0.48, cam })
  }

  const split = lay.split
  if (split) {
    const w = kidWidth(lay)
    const across = split.into * w + (split.into - 1) * 18
    shots.push({
      at: split.t0 + 0.5,
      move: 0.55,
      cam: {
        ...flat,
        x: split.at.x0 + across / 2,
        y: lay.lanesBottom + lay.splitOff + 30,
        zoom: Math.max(flat.zoom, Math.min(close, (view.w * 0.8) / (across + 60))),
        pitch: 24,
        yaw: 12,
        open: 1,
      },
    })
  }

  if (lay.loop?.plays) shots.push({ at: lay.loop.t0 + 0.4, move: 0.5, cam: flat })

  shots.push({
    at: lay.firedAt + 0.2,
    move: 0.55,
    cam: aim({
      ...flat,
      x: lay.gateX + lay.gateW / 2,
      y: lay.lanesTop + (lay.scene.ends.length * 26 + 44) / 2,
      zoom: clamp(Math.max(flat.zoom * 1.5, close * 0.9), flat.zoom, 1.1),
    }),
  })
  shots.push({ at: lay.end, move: 0.8, cam: { ...flat, zoom: flat.zoom * 0.96 } })
  shots.sort((a, b) => a.at - b.at)
  // Once the copies of a split are open they stay open: they are part of the run from then on.
  if (split) for (const shot of shots) if (shot.at >= split.t0 + 0.5) shot.cam = { ...shot.cam, open: 1 }

  const crane: Cam = { ...flat, zoom: flat.zoom * 0.78, pitch: 44, yaw: -24 }
  const keys: Key[] = [
    { t: -INTRO, cam: crane },
    { t: -0.1, cam: flat },
  ]
  for (const shot of shots) {
    const before = keys[keys.length - 1]
    const leave = Math.max(before.t, shot.at - shot.move)
    // Held until it is time to move -- with a slow push in, the way a camera leans into a
    // scene -- and then moved.
    if (leave > before.t + 1e-3) keys.push({ t: leave, cam: { ...before.cam, zoom: before.cam.zoom * 1.03 } })
    if (shot.at > keys[keys.length - 1].t + 1e-3) keys.push({ t: shot.at, cam: shot.cam })
    else keys[keys.length - 1] = { t: keys[keys.length - 1].t, cam: shot.cam }
  }
  return keys
}

const ease = gsap.parseEase('power2.inOut')

/** Where the camera is at `t`: between two shots, eased in and out. */
export function film(keys: Key[], t: number): Cam {
  if (t <= keys[0].t) return keys[0].cam
  for (let i = 1; i < keys.length; i++) {
    const b = keys[i]
    if (t <= b.t) {
      const a = keys[i - 1]
      const u = ease((t - a.t) / Math.max(1e-6, b.t - a.t))
      const out = {} as Cam
      for (const k of Object.keys(a.cam) as (keyof Cam)[]) out[k] = lerp(a.cam[k], b.cam[k], u)
      return out
    }
  }
  return keys[keys.length - 1].cam
}

/** The shot the camera settles on at or after `t`: what a cut, rather than a move, shows. */
export function cut(keys: Key[], t: number): Cam {
  return (keys.find((key) => key.t >= t) ?? keys[keys.length - 1]).cam
}

/** The whole run seen at once, flat: what reduced motion shows. */
export function still(lay: Layout, view: View): Cam {
  return { ...wide(lay, view, 0, 0, 0, 0.96), open: 1 }
}

/** A card's small picture: the whole run up to the finish's post -- a card has no words for
 *  the endings beside it -- and lanes that run at once shown fanned in depth, since that is the
 *  one thing a card of theirs has to say. */
export function card(lay: Layout, view: View): Cam {
  const right = lay.gateX + 30
  return lay.scene.depth === 'lanes'
    ? wide(lay, view, 1, 40, -18, 0.95, right)
    : { ...wide(lay, view, 0, 0, 0, 0.92, right), open: 1 }
}

/** How tall a card's picture is, at 300 wide. */
export const cardHeight = (lay: Layout) =>
  lay.scene.depth === 'lanes' ? 150 : Math.round(clamp((300 * lay.height) / (lay.gateX + 30), 80, 150))

/** How wide each of a split's copies is drawn. */
export const kidWidth = (lay: Layout) => lay.beat * 2.1

/** How tall a scene's picture is at a given width, in pixels: the whole run with a little
 *  room around it, and never so short that a close shot has nothing to close on. */
export function heightFor(lay: Layout, width: number): number {
  const fit = Math.min(1, width / lay.width)
  return Math.round(clamp(lay.height * fit * 1.12 + 10, 240, 480))
}

/* ------------------------------------------------------------------------------------------
   What is happening at `t`.
   ------------------------------------------------------------------------------------------ */

export type TurnState = 'waiting' | 'running' | 'landed'

export const stateAt = (g: TurnG, t: number): TurnState =>
  t >= g.t1 ? 'landed' : t >= g.t0 ? 'running' : 'waiting'

export const through = (g: TurnG, t: number) => clamp((t - g.t0) / (g.t1 - g.t0), 0, 1)

/** How much of the budget the run has spent by `t`, 0 to 1. The bar fills only while a model
 *  is working, and reaches the end exactly when the budget is what stops the run. */
export function spentAt(lay: Layout, t: number): number {
  if (!lay.spend) return 0
  let sum = 0
  for (const g of lay.turns) {
    if (g.lane.kind === 'human' || g.lane.kind === 'program') continue
    sum += clamp(Math.min(t, lay.firedAt) - g.t0, 0, Math.min(g.t1, lay.firedAt) - g.t0)
  }
  return (sum / lay.spend) * (lay.fired === 'budget' ? 1 : 0.58)
}

/** A point on a cubic. */
export const cubic = (a: number, b: number, c: number, d: number, p: number) => {
  const q = 1 - p
  return q * q * q * a + 3 * q * q * p * b + 3 * q * p * p * c + p * p * p * d
}
