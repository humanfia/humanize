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

interface Mote {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  age: number
  size: number
  color: string
  drag: number
}

export interface Fx {
  /** A burst of sparks, in viewBox units. */
  spark: (x: number, y: number, color: string, count?: number, speed?: number) => void
  /** One mote of a light trail. Call it every frame from the moving thing's `onUpdate`. */
  trail: (x: number, y: number, color: string, size?: number) => void
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

  function add(m: Omit<Mote, 'age'>) {
    if (motes.length > 600) motes.shift()
    motes.push({ ...m, age: 0 })
  }

  return {
    spark(x, y, color, count = 16, speed = 90) {
      if (quiet) return
      for (let i = 0; i < count; i += 1) {
        const a = Math.random() * Math.PI * 2
        const v = speed * (0.35 + Math.random() * 0.65)
        add({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 0.5 + Math.random() * 0.6, size: 1.2 + Math.random() * 1.8, color, drag: 3.2 })
      }
    },
    trail(x, y, color, size = 2.4) {
      if (quiet) return
      add({ x, y, vx: (Math.random() - 0.5) * 8, vy: (Math.random() - 0.5) * 8, life: 0.55, size, color, drag: 1 })
    },
    step(dt) {
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      if (!motes.length) return
      ctx.setTransform(dpr * scale, 0, 0, dpr * scale, dpr * ox, dpr * oy)
      // Light adds up on a dark stage and would wash out to white on a light one.
      ctx.globalCompositeOperation = dark() ? 'lighter' : 'source-over'
      for (let i = motes.length - 1; i >= 0; i -= 1) {
        const m = motes[i]
        m.age += dt
        if (m.age >= m.life) {
          motes.splice(i, 1)
          continue
        }
        const k = Math.exp(-m.drag * dt)
        m.vx *= k
        m.vy *= k
        m.x += m.vx * dt
        m.y += m.vy * dt
        const left = 1 - m.age / m.life
        ctx.globalAlpha = left * (dark() ? 0.9 : 0.6)
        ctx.fillStyle = m.color
        ctx.beginPath()
        ctx.arc(m.x, m.y, m.size * (0.4 + 0.6 * left), 0, Math.PI * 2)
        ctx.fill()
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
