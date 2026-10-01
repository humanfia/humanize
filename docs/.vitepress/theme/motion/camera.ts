// The camera a feature scene films its world with: a centre and a zoom. Every scene that moves
// its world and draws light over it takes it from here -- anchor, tracing, resuming, goals,
// steering, budgets -- rather than writing its own.
//
// The world group is moved by a camera (a centre and a zoom) rather than by tweening its
// transform, so a point in the world can always be turned into a point on the screen -- which
// is what the light canvas needs: a spark or a trail drawn while the camera is pushed in still
// lands on the thing it belongs to. A second, far layer follows the camera at a fraction of
// its movement, for parallax.
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

export function rig(
  tl: Timeline,
  o: { w: number; h: number; world?: Element; far?: Element; fx: () => Fx | undefined; start?: Partial<Shot> },
) {
  const { w, h } = o
  const home: Shot = { x: w / 2, y: h / 2, s: 1 }
  const first: Shot = { ...home, ...o.start }
  const cam: Shot = { ...first }

  function apply() {
    o.world?.setAttribute('transform', `translate(${w / 2} ${h / 2}) scale(${cam.s}) translate(${-cam.x} ${-cam.y})`)
    if (o.far) {
      // The far layer moves a third as much, and barely zooms.
      const k = 0.35
      const s = 1 + (cam.s - 1) * 0.25
      const x = w / 2 + (cam.x - w / 2) * k
      const y = h / 2 + (cam.y - h / 2) * k
      o.far.setAttribute('transform', `translate(${w / 2} ${h / 2}) scale(${s}) translate(${-x} ${-y})`)
    }
  }

  /** A world point, where it is on the screen right now. */
  const view = (p: Point): Point => ({ x: (p.x - cam.x) * cam.s + w / 2, y: (p.y - cam.y) * cam.s + h / 2 })

  tl.fromTo(cam, { ...first }, { ...first, duration: 0.001, onUpdate: apply, immediateRender: true }, 0)
  apply()

  /** Move the camera. */
  function shot(to: Partial<Shot>, at: gsap.Position, duration = 1.6, ease = 'cine') {
    tl.to(cam, { ...to, duration, ease, onUpdate: apply }, at)
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

  /** An `onUpdate` that leaves a trail behind an element moved by its own x/y, in world units. */
  function trail(el: Element, color: () => string, size?: number) {
    const gsap = motion()
    return () => {
      const v = view({ x: Number(gsap.getProperty(el, 'x')), y: Number(gsap.getProperty(el, 'y')) })
      o.fx()?.trail(v.x, v.y, color(), size)
    }
  }

  return { cam, view, shot, beam, flare, trail }
}
