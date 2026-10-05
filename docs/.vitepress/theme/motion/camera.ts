// The camera a feature scene films its world with: a centre and a zoom. Every scene that moves
// its world and draws light over it takes it from here -- anchor, tracing, resuming, goals,
// steering, budgets -- rather than writing its own.
//
// The world group is moved by a camera (a centre and a zoom) rather than by tweening its
// transform, so a point in the world can always be turned into a point on the screen -- which
// is what the light canvas needs: a spark or a trail drawn while the camera is pushed in still
// lands on the thing it belongs to. A second, far layer follows the camera at a fraction of
// its movement, for parallax; any number of other layers may be given a depth of their own; and
// the stage's graph paper (`HmzStage`) is told where the camera is, and slides behind it all.
//
// On top of where the camera is sent there are two small motions of its own, both kept apart
// from `cam` so `view` and a shot's target stay exact: `drift`, the slow float of a hand-held
// camera, and `pulse`, a quick push in and back for a beat that lands.
//
// Every camera tween writes the transform itself in its `onUpdate`, which GSAP also calls when
// the timeline is seeked across it, so a chapter jump or the reduced-motion still frame shows
// the camera where it would be.
import type { Fx } from './fx'
import { motion } from './gsap'

type Timeline = gsap.core.Timeline

export interface Point {
  x: number
  y: number
}

export interface Shot {
  /** The world point at the centre of the screen. */
  x: number
  y: number
  /** Zoom. */
  s: number
}

/** A layer that follows the camera by a fraction: 0 stays put, 1 moves with the world. */
export interface Layer {
  el: Element
  depth: number
}

export function rig(
  tl: Timeline,
  o: {
    w: number
    h: number
    world?: Element
    far?: Element
    fx: () => Fx | undefined
    start?: Partial<Shot>
    /** More layers at depths of their own, nearest last. */
    layers?: Layer[]
    /** Tell the stage where the camera is, so its graph paper slides behind it. On by default. */
    backdrop?: boolean
  },
) {
  const { w, h } = o
  const home: Shot = { x: w / 2, y: h / 2, s: 1 }
  const first: Shot = { ...home, ...o.start }
  const cam: Shot = { ...first }
  // The hand-held float and the push of a pulse: added when the transform is written, never
  // to `cam`, so they never move a shot's target or what `view` says.
  const sway = { x: 0, y: 0, s: 1 }
  const screen = o.backdrop === false ? null : (o.world?.closest('.hmz-stage .screen') as HTMLElement | null)

  const place = (el: Element, depth: number, zoom: number) => {
    const s = 1 + (cam.s * sway.s - 1) * zoom
    const x = w / 2 + (cam.x + sway.x - w / 2) * depth
    const y = h / 2 + (cam.y + sway.y - h / 2) * depth
    el.setAttribute('transform', `translate(${w / 2} ${h / 2}) scale(${s}) translate(${-x} ${-y})`)
  }

  function apply() {
    if (o.world) place(o.world, 1, 1)
    // The far layer moves a third as much, and barely zooms.
    if (o.far) place(o.far, 0.35, 0.25)
    for (const layer of o.layers ?? []) place(layer.el, layer.depth, layer.depth * layer.depth)
    if (screen) {
      // As a fraction of the scene, so the stage needs no size to follow it; the paper is
      // further back than any layer, so it moves a fifth as much.
      screen.style.setProperty('--hmz-cam-x', String(round((-(cam.x + sway.x - w / 2) / w) * 0.2)))
      screen.style.setProperty('--hmz-cam-y', String(round((-(cam.y + sway.y - h / 2) / h) * 0.2)))
      screen.style.setProperty('--hmz-cam-s', String(round(1 + (cam.s * sway.s - 1) * 0.15)))
    }
  }

  /** A world point, where it is on the screen right now. */
  const view = (p: Point): Point => ({ x: (p.x - cam.x) * cam.s + w / 2, y: (p.y - cam.y) * cam.s + h / 2 })

  tl.fromTo(cam, { ...first }, { ...first, duration: 0.001, onUpdate: apply, immediateRender: true }, 0)
  tl.fromTo(sway, { x: 0, y: 0, s: 1 }, { x: 0, y: 0, s: 1, duration: 0.001, onUpdate: apply, immediateRender: true }, 0)
  apply()

  /** Move the camera. */
  function shot(to: Partial<Shot>, at: gsap.Position, duration = 1.6, ease = 'cine') {
    tl.to(cam, { ...to, duration, ease, onUpdate: apply }, at)
  }

  /**
   * Fit a box of the world to the screen, with `pad` of room round it (a fraction of the
   * screen): the camera's "look at all of this". `max` caps the zoom, for a small box.
   */
  function frame(
    box: { x: number; y: number; width: number; height: number },
    at: gsap.Position,
    opts: { pad?: number; max?: number; duration?: number; ease?: string } = {},
  ) {
    const pad = 1 - 2 * (opts.pad ?? 0.08)
    const s = Math.min((w * pad) / Math.max(box.width, 1), (h * pad) / Math.max(box.height, 1), opts.max ?? 3)
    shot({ x: box.x + box.width / 2, y: box.y + box.height / 2, s }, at, opts.duration, opts.ease)
  }

  /** Centre a world point, at a zoom (the one it has, if none is given): "look here". */
  function focus(p: Point, at: gsap.Position, opts: { s?: number; duration?: number; ease?: string } = {}) {
    shot({ x: p.x, y: p.y, ...(opts.s === undefined ? {} : { s: opts.s }) }, at, opts.duration, opts.ease)
  }

  /**
   * Float for `duration` seconds from `at`, by `amount` world units and back: what keeps a
   * held shot alive, a camera breathing rather than fixed to a tripod. It ends where it began.
   */
  function drift(at: gsap.Position, duration: number, amount = 4) {
    const half = duration / 2
    tl.to(sway, { x: amount, y: -amount * 0.6, s: 1 + amount / 900, duration: half, ease: 'sine.inOut', onUpdate: apply }, at)
    tl.to(sway, { x: 0, y: 0, s: 1, duration: half, ease: 'sine.inOut', onUpdate: apply }, '>')
  }

  /** A quick push in by `by` and back, for a beat that lands. */
  function pulse(at: gsap.Position, by = 0.035, duration = 0.5) {
    tl.to(sway, { s: 1 + by, duration, ease: 'there.back', onUpdate: apply }, at)
  }

  /** A mote of light from one world point to another, on a curve, in step with the camera. */
  function beam(
    from: Point,
    to: Point,
    color: () => string,
    at: gsap.Position,
    opts: {
      duration?: number
      bend?: number
      burst?: number
      size?: number
      ease?: string
      /** How fast the burst's sparks fly. */
      speed?: number
      /** Where a point of the curve is in the world, if the curve is drawn on something that
       *  moves under the camera (a side that leans in): called every frame. */
      place?: (p: Point) => Point
    } = {},
  ) {
    const p = { t: 0 }
    const onto = opts.place ?? ((q: Point) => q)
    const bend = opts.bend ?? 0.2
    const cx = (from.x + to.x) / 2 - (to.y - from.y) * bend
    const cy = (from.y + to.y) / 2 + (to.x - from.x) * bend
    tl.fromTo(
      p,
      { t: 0 },
      {
        t: 1,
        duration: opts.duration ?? 0.8,
        ease: opts.ease ?? 'cine',
        onUpdate() {
          const t = p.t
          const u = 1 - t
          const v = view(onto({ x: u * u * from.x + 2 * u * t * cx + t * t * to.x, y: u * u * from.y + 2 * u * t * cy + t * t * to.y }))
          o.fx()?.trail(v.x, v.y, color(), opts.size)
        },
        onComplete() {
          if (!opts.burst) return
          const v = view(onto(to))
          o.fx()?.spark(v.x, v.y, color(), opts.burst, opts.speed ?? 60)
        },
      },
      at,
    )
  }

  /** A burst of sparks at a world point. */
  function flare(p: Point, color: () => string, at: gsap.Position, count = 24, speed = 110) {
    tl.call(
      () => {
        const v = view(p)
        o.fx()?.spark(v.x, v.y, color(), count, speed * cam.s)
      },
      [],
      at,
    )
  }

  /** A ring opening from a world point, sized with the camera's zoom. */
  function ring(p: Point, color: () => string, at: gsap.Position, radius = 34) {
    tl.call(
      () => {
        const v = view(p)
        o.fx()?.ring(v.x, v.y, color(), { radius: radius * cam.s })
      },
      [],
      at,
    )
  }

  /** An `onUpdate` that leaves a trail behind an element moved by its own x/y, in world units. */
  function trail(el: Element, color: () => string, size?: number) {
    const gsap = motion()
    return () => {
      const v = view({ x: Number(gsap.getProperty(el, 'x')), y: Number(gsap.getProperty(el, 'y')) })
      o.fx()?.trail(v.x, v.y, color(), size)
    }
  }

  return { cam, view, shot, frame, focus, drift, pulse, beam, flare, ring, trail }
}

const round = (n: number) => Math.round(n * 10000) / 10000
