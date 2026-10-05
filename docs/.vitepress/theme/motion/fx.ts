// The effects the scenes share: light on a canvas laid over an SVG, and a handful of timeline
// moves every scene makes. Light is drawn on a canvas rather than as SVG nodes because a spark
// is a hundred short-lived things a second, and the DOM is slow at those.
import { motion } from './gsap'

type Timeline = gsap.core.Timeline

// A jump through the timeline -- to a chapter, or to the still frame -- runs every callback on
// the way, so the scene's cameras and states come out right. The light it passes over is not
// wanted: `hush` drops every spark and trail made while it runs.
let quiet = false
export function hush(jump: () => void) {
  quiet = true
  try {
    jump()
  } finally {
    quiet = false
  }
}

/** What a mote is drawn as: a dot of a trail, a stroke of a spark, a ring, a spoke of a flash. */
type Kind = 'dot' | 'stroke' | 'ring' | 'spoke'

interface Mote {
  kind: Kind
  x: number
  y: number
  vx: number
  vy: number
  life: number
  age: number
  size: number
  color: string
  drag: number
  /** A ring's or a spoke's radii: where it starts and how far out it goes. */
  r0: number
  r1: number
  /** A spoke's direction. */
  angle: number
}

export interface Fx {
  /** A burst of sparks, in viewBox units: short strokes flying out evenly all round. */
  spark: (x: number, y: number, color: string, count?: number, speed?: number) => void
  /** One mote of a light trail. Call it every frame from the moving thing's `onUpdate`. */
  trail: (x: number, y: number, color: string, size?: number) => void
  /** A ring that opens out from a point and fades as it goes: a thing landing, or sounding. */
  ring: (x: number, y: number, color: string, opts?: { radius?: number; from?: number; life?: number; width?: number }) => void
  /** Spokes of light thrown out from a point and gone: manim's `Flash`, the "here" of a scene. */
  flash: (
    x: number,
    y: number,
    color: string,
    opts?: { lines?: number; radius?: number; from?: number; life?: number; width?: number },
  ) => void
  /** Advance and draw. Put it in the scene's `tick`. */
  step: (dt: number) => void
  clear: () => void
  destroy: () => void
}

/**
 * A canvas of light laid exactly over an SVG with the same `viewBox` and the default
 * `preserveAspectRatio` (centred, fitted whole), so the two share one coordinate system.
 */
export function createFx(canvas: HTMLCanvasElement, width: number, height: number): Fx {
  const ctx = canvas.getContext('2d')!
  const motes: Mote[] = []
  let scale = 1
  let ox = 0
  let oy = 0
  let dpr = 1

  function fit() {
    dpr = Math.min(window.devicePixelRatio || 1, 2)
    // The layout box, not the bounding one: a camera may be scaling the canvas's parent.
    const box = { width: canvas.clientWidth, height: canvas.clientHeight }
    canvas.width = Math.max(1, Math.round(box.width * dpr))
    canvas.height = Math.max(1, Math.round(box.height * dpr))
    scale = Math.min(box.width / width, box.height / height)
    ox = (box.width - width * scale) / 2
    oy = (box.height - height * scale) / 2
  }
  fit()
  // Let go of the canvas once it has left the page: a scene's own `destroy` is not always
  // reached, and a leaving canvas is reported as resized to nothing.
  const resize = new ResizeObserver(() => (canvas.isConnected ? fit() : resize.disconnect()))
  resize.observe(canvas)

  const dark = () => document.documentElement.classList.contains('dark')

  // A canvas cannot read `var(--hmz-red)`: a colour given that way is looked up as it is used.
  const paint = (color: string) => {
    const name = /^var\((--[\w-]+)\)$/.exec(color.trim())?.[1]
    return name ? getComputedStyle(canvas).getPropertyValue(name).trim() || color : color
  }

  function add(m: Partial<Mote> & Pick<Mote, 'kind' | 'x' | 'y' | 'life' | 'size' | 'color'>) {
    if (motes.length > 600) motes.shift()
    motes.push({ vx: 0, vy: 0, drag: 0, r0: 0, r1: 0, angle: 0, ...m, color: paint(m.color), age: 0 })
  }

  // How far a thing that decelerates has got, `t` through its life: fast out, slow in.
  const out = (t: number) => 1 - (1 - t) ** 3

  return {
    spark(x, y, color, count = 16, speed = 90) {
      if (quiet) return
      // Evenly round, from a turn picked at random, each a hair off its slot: a burst reads as
      // one event rather than as noise, and no two bursts are the same.
      const turn = Math.random() * Math.PI * 2
      for (let i = 0; i < count; i += 1) {
        const a = turn + (i / count) * Math.PI * 2 + (Math.random() - 0.5) * (Math.PI / count) * 0.6
        const v = speed * (0.7 + Math.random() * 0.3)
        add({
          kind: 'stroke',
          x,
          y,
          vx: Math.cos(a) * v,
          vy: Math.sin(a) * v,
          life: 0.45 + Math.random() * 0.25,
          size: 1.1 + Math.random() * 0.6,
          color,
          drag: 3.6,
        })
      }
    },
    trail(x, y, color, size = 2.4) {
      if (quiet) return
      add({ kind: 'dot', x, y, vx: (Math.random() - 0.5) * 6, vy: (Math.random() - 0.5) * 6, life: 0.55, size, color, drag: 1 })
    },
    ring(x, y, color, opts = {}) {
      if (quiet) return
      add({ kind: 'ring', x, y, r0: opts.from ?? 2, r1: opts.radius ?? 34, life: opts.life ?? 0.75, size: opts.width ?? 1.6, color })
    },
    flash(x, y, color, opts = {}) {
      if (quiet) return
      const lines = opts.lines ?? 12
      const from = opts.from ?? 6
      const radius = opts.radius ?? 30
      for (let i = 0; i < lines; i += 1) {
        add({
          kind: 'spoke',
          x,
          y,
          angle: (i / lines) * Math.PI * 2 - Math.PI / 2,
          r0: from,
          r1: from + radius,
          life: opts.life ?? 0.55,
          size: opts.width ?? 1.6,
          color,
        })
      }
    },
    step(dt) {
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      if (!motes.length) return
      ctx.setTransform(dpr * scale, 0, 0, dpr * scale, dpr * ox, dpr * oy)
      // Light adds up on a dark stage and would wash out to white on a light one.
      const night = dark()
      const strength = night ? 0.9 : 0.62
      ctx.globalCompositeOperation = night ? 'lighter' : 'source-over'
      ctx.lineCap = 'round'
      for (let i = motes.length - 1; i >= 0; i -= 1) {
        const m = motes[i]
        m.age += dt
        if (m.age >= m.life) {
          motes.splice(i, 1)
          continue
        }
        const t = m.age / m.life
        const left = 1 - t
        ctx.strokeStyle = m.color
        ctx.fillStyle = m.color
        if (m.kind === 'ring') {
          ctx.globalAlpha = left * left * strength
          ctx.lineWidth = m.size * (0.4 + 0.6 * left)
          ctx.beginPath()
          ctx.arc(m.x, m.y, m.r0 + (m.r1 - m.r0) * out(t), 0, Math.PI * 2)
          ctx.stroke()
          continue
        }
        if (m.kind === 'spoke') {
          // The far end races out, the near end follows it, and the line is gone when they
          // meet: a stroke that is never longer than at the moment it is brightest.
          const far = m.r0 + (m.r1 - m.r0) * out(Math.min(1, t * 1.5))
          const near = m.r0 + (m.r1 - m.r0) * out(Math.max(0, t * 1.5 - 0.5))
          const ux = Math.cos(m.angle)
          const uy = Math.sin(m.angle)
          ctx.globalAlpha = Math.min(1, left * 1.6) * strength
          ctx.lineWidth = m.size
          ctx.beginPath()
          ctx.moveTo(m.x + ux * near, m.y + uy * near)
          ctx.lineTo(m.x + ux * far, m.y + uy * far)
          ctx.stroke()
          continue
        }
        const k = Math.exp(-m.drag * dt)
        m.vx *= k
        m.vy *= k
        m.x += m.vx * dt
        m.y += m.vy * dt
        if (m.kind === 'stroke') {
          // As long as the way it came in the last twentieth of a second, so it shortens as it
          // slows: a spark thrown, coming to rest.
          ctx.globalAlpha = left * strength
          ctx.lineWidth = m.size
          ctx.beginPath()
          ctx.moveTo(m.x, m.y)
          ctx.lineTo(m.x - m.vx * 0.05, m.y - m.vy * 0.05)
          ctx.stroke()
          continue
        }
        const r = m.size * (0.4 + 0.6 * left)
        if (night) {
          // A soft halo round a bright core: light in a dark room.
          ctx.globalAlpha = left * 0.16
          ctx.beginPath()
          ctx.arc(m.x, m.y, r * 2.8, 0, Math.PI * 2)
          ctx.fill()
        }
        ctx.globalAlpha = left * strength
        ctx.beginPath()
        ctx.arc(m.x, m.y, r, 0, Math.PI * 2)
        ctx.fill()
        if (night) {
          ctx.globalAlpha = left * 0.45
          ctx.fillStyle = '#fff'
          ctx.beginPath()
          ctx.arc(m.x, m.y, r * 0.42, 0, Math.PI * 2)
          ctx.fill()
        }
      }
      ctx.globalAlpha = 1
      ctx.globalCompositeOperation = 'source-over'
    },
    clear() {
      motes.length = 0
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, canvas.width, canvas.height)
    },
    destroy() {
      resize.disconnect()
    },
  }
}

/**
 * Rings opening one after another from a point, at `at` on the timeline: a thing arriving, or
 * a signal going out from it. Light only, so a ripple costs the DOM nothing.
 */
export function ripple(
  tl: Timeline,
  fx: () => Fx | undefined,
  p: { x: number; y: number },
  color: string | (() => string),
  at: gsap.Position,
  opts: { rings?: number; gap?: number; radius?: number; life?: number; width?: number } = {},
) {
  const rings = opts.rings ?? 3
  const gap = opts.gap ?? 0.14
  const hue = () => (typeof color === 'function' ? color() : color)
  for (let i = 0; i < rings; i += 1) {
    // Each ring its own call on the timeline rather than a timer, so a pause holds them all.
    const when = i === 0 ? at : `<${gap}`
    tl.call(() => fx()?.ring(p.x, p.y, hue(), { radius: (opts.radius ?? 36) * (1 - i * 0.12), life: opts.life ?? 0.9, width: opts.width }), [], when)
  }
}

/** The resolved value of a CSS custom property, for a canvas that cannot read `var()`. */
export function cssVar(el: Element, name: string): string {
  return getComputedStyle(el).getPropertyValue(name).trim()
}

/** Fly `head` along an SVG `path`, leaving a trail on `fx` if given. */
export function fly(
  tl: Timeline,
  head: Element,
  path: SVGPathElement | string,
  at: gsap.Position,
  opts: { duration?: number; ease?: string; fx?: () => Fx | undefined; color?: string; reverse?: boolean } = {},
) {
  const gsap = motion()
  tl.fromTo(head, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.15, ease: 'none' }, at)
  tl.to(
    head,
    {
      duration: opts.duration ?? 1.1,
      ease: opts.ease ?? 'cine',
      motionPath: { path, align: path, alignOrigin: [0.5, 0.5], start: opts.reverse ? 1 : 0, end: opts.reverse ? 0 : 1 },
      onUpdate() {
        const fx = opts.fx?.()
        if (!fx || !opts.color) return
        fx.trail(Number(gsap.getProperty(head, 'x')) + bboxCentre(head).x, Number(gsap.getProperty(head, 'y')) + bboxCentre(head).y, opts.color)
      },
    },
    at,
  )
  tl.to(head, { autoAlpha: 0, duration: 0.2, ease: 'none' }, '>-0.05')
}

const centres = new WeakMap<Element, { x: number; y: number }>()
function bboxCentre(el: Element) {
  let c = centres.get(el)
  if (!c) {
    const b = (el as SVGGraphicsElement).getBBox()
    c = { x: b.x + b.width / 2, y: b.y + b.height / 2 }
    centres.set(el, c)
  }
  return c
}

/** Count a number up (or down) in an element's text. */
export function count(
  tl: Timeline,
  el: Element,
  from: number,
  to: number,
  at: gsap.Position,
  opts: { duration?: number; format?: (n: number) => string; ease?: string } = {},
) {
  const box = { n: from }
  const format = opts.format ?? ((n: number) => String(Math.round(n)))
  tl.to(
    box,
    {
      n: to,
      duration: opts.duration ?? 1.2,
      ease: opts.ease ?? 'power2.out',
      onUpdate: () => {
        el.textContent = format(box.n)
      },
      onStart: () => {
        el.textContent = format(from)
      },
    },
    at,
  )
}

/** Type a line out, a character at a time. */
export function type(tl: Timeline, el: Element, text: string, at: gsap.Position, cps = 38) {
  tl.set(el, { text: '' }, at)
  tl.to(el, { text: { value: text }, duration: text.length / cps, ease: 'none' }, '>')
}

/**
 * A mote of light from one point to another, curving by `bend` (a fraction of the distance,
 * to the left of the direction of travel), leaving a trail on `fx`. It is only light: there is
 * no element, so any number of them cost the DOM nothing.
 */
export function streak(
  tl: Timeline,
  fx: () => Fx | undefined,
  from: { x: number; y: number },
  to: { x: number; y: number },
  color: string | (() => string),
  at: gsap.Position,
  opts: { duration?: number; bend?: number; ease?: string; size?: number; burst?: number } = {},
) {
  const p = { t: 0 }
  const dx = to.x - from.x
  const dy = to.y - from.y
  const bend = opts.bend ?? 0.2
  const cx = (from.x + to.x) / 2 - dy * bend
  const cy = (from.y + to.y) / 2 + dx * bend
  const hue = () => (typeof color === 'function' ? color() : color)
  tl.fromTo(
    p,
    { t: 0 },
    {
      t: 1,
      duration: opts.duration ?? 0.9,
      ease: opts.ease ?? 'cine',
      onUpdate: () => {
        const f = fx()
        if (!f) return
        const t = p.t
        const u = 1 - t
        const x = u * u * from.x + 2 * u * t * cx + t * t * to.x
        const y = u * u * from.y + 2 * u * t * cy + t * t * to.y
        f.trail(x, y, hue(), opts.size)
      },
      onComplete: () => {
        if (opts.burst) fx()?.spark(to.x, to.y, hue(), opts.burst, 60)
      },
    },
    at,
  )
}
