// The verbs of a 3Blue1Brown animation, as timeline moves: the vocabulary manim cuts every video
// with, so a scene here can say what it does the way one of those says it -- `create` a shape,
// `write` its label, `transform` one thing into the next, `indicate` the one that matters --
// rather than spelling out the tweens each time.
//
// Every move takes the scene's timeline, what it moves, and where on the timeline it goes, and
// adds tweens to that timeline and nothing else, so a scene that uses them still pauses, seeks,
// loops and holds a reduced-motion still frame as one that does not. The few moves that need a
// drawing of their own (a ring round a thing, a flash along a path) add it to the SVG while the
// scene is built and take it away again when the scene is rebuilt or leaves the page.
//
// Colours are taken as CSS -- `var(--hmz-red)` -- so they follow the theme like the rest of
// the drawing.
import type { Fx } from './fx'
import { motion, SplitText } from './gsap'

type Timeline = gsap.core.Timeline
type Targets = Element | Element[]

const list = (t: Targets): Element[] => (Array.isArray(t) ? t : [t])

/** Where each element already is, by its own x and y (an SVG `transform` attribute counts):
 *  a move is made from there, not from the origin. Read when the move is cut. */
function at0(els: Element[]) {
  const gsap = motion()
  return els.map((e) => ({ x: Number(gsap.getProperty(e, 'x')) || 0, y: Number(gsap.getProperty(e, 'y')) || 0 }))
}
const SVG = 'http://www.w3.org/2000/svg'

/** Add a drawing to the scene for as long as the scene is built: gone again on a rebuild. */
function own<T extends Element>(node: T): T {
  // A context made while the scene's own is being filled is reverted with it, and runs the
  // function its body returns when it is.
  motion().context(() => () => node.remove())
  return node
}

/** A shape's paint as it is drawn, to come back to. */
function paint(el: Element) {
  const css = getComputedStyle(el)
  return { fill: Number(css.fillOpacity || 1), stroke: Number(css.strokeOpacity || 1) }
}

/**
 * Draw a shape on: its outline traced from start to end, then its fill flooded in behind it.
 * manim's `Create`. For an SVG path, line, rect, circle, ellipse, polyline or polygon.
 */
export function create(tl: Timeline, el: Targets, at: gsap.Position, opts: { duration?: number; stagger?: number; ease?: string } = {}) {
  const els = list(el)
  const duration = opts.duration ?? 1.1
  const stagger = opts.stagger ?? 0.08
  // Read before the first tween is made, which may already have hidden the fill.
  const fills = els.map((e) => paint(e).fill)
  tl.fromTo(els, { drawSVG: '0%', autoAlpha: 1 }, { drawSVG: '100%', duration, ease: opts.ease ?? 'smooth', stagger }, at)
  // Each fill comes in once its own outline is half drawn.
  tl.fromTo(els, { fillOpacity: 0 }, { fillOpacity: (i: number) => fills[i], duration: duration * 0.6, ease: 'smooth', stagger }, `<${duration * 0.45}`)
}

/** The reverse of `create`: the fill drains, then the outline is taken back to nothing. */
export function erase(tl: Timeline, el: Targets, at: gsap.Position, opts: { duration?: number; stagger?: number } = {}) {
  const els = list(el)
  const duration = opts.duration ?? 0.8
  tl.to(els, { fillOpacity: 0, duration: duration * 0.4, ease: 'smooth' }, at)
  tl.to(els, { drawSVG: '100% 100%', duration, ease: 'smooth', stagger: opts.stagger ?? 0.05 }, '<0.1')
  tl.set(els, { autoAlpha: 0 }, '>')
}

/** Trace a stroke on, and nothing else: an arrow, a wire, a curve of a graph. */
export function drawOn(
  tl: Timeline,
  el: Targets,
  at: gsap.Position,
  opts: { duration?: number; stagger?: number; ease?: string; from?: 'start' | 'end' | 'middle' } = {},
) {
  const start = { start: '0% 0%', end: '100% 100%', middle: '50% 50%' }[opts.from ?? 'start']
  tl.fromTo(list(el), { drawSVG: start, autoAlpha: 1 }, { drawSVG: '0% 100%', duration: opts.duration ?? 0.9, ease: opts.ease ?? 'smooth', stagger: opts.stagger ?? 0.06 }, at)
}

/**
 * Write a label on, as a hand would: manim's `Write`. An SVG `<text>` has its letters traced in
 * outline and then filled; an HTML element has its characters come up one after another, each
 * rising into place.
 */
export function write(tl: Timeline, el: Element, at: gsap.Position, opts: { duration?: number } = {}) {
  if (el instanceof SVGTextElement) {
    const length = Math.max(40, el.getComputedTextLength() * 4)
    const duration = opts.duration ?? Math.min(1.6, 0.5 + length / 900)
    const { fill } = paint(el)
    // Traced in the colour it is filled with, so the outline and the fill are one ink.
    const ink = getComputedStyle(el).fill
    tl.fromTo(
      el,
      { autoAlpha: 1, fillOpacity: 0, strokeOpacity: 1, stroke: ink, strokeWidth: 0.6, strokeDasharray: length, strokeDashoffset: length },
      { strokeDashoffset: 0, duration, ease: 'smooth' },
      at,
    )
    tl.to(el, { fillOpacity: fill, duration: duration * 0.5, ease: 'smooth' }, `<${duration * 0.55}`)
    tl.to(el, { strokeOpacity: 0, duration: duration * 0.35, ease: 'smooth' }, '<0.15')
    return
  }
  const chars = new SplitText(el, { type: 'chars' }).chars
  tl.set(el, { autoAlpha: 1 }, at)
  tl.from(chars, { autoAlpha: 0, y: '0.35em', duration: opts.duration ?? 0.5, ease: 'cine.out', stagger: { amount: Math.min(0.9, chars.length * 0.03) } }, '<')
}

/**
 * Change what a label says, its characters scrambling through others on the way: a value that
 * is recomputed, a state renamed. Holds its width steady while it runs.
 */
export function retype(tl: Timeline, el: Element, text: string, at: gsap.Position, opts: { duration?: number; chars?: string } = {}) {
  tl.to(
    el,
    {
      duration: opts.duration ?? Math.min(1.2, 0.35 + text.length * 0.03),
      ease: 'none',
      scrambleText: { text, chars: opts.chars ?? 'lowerCase', speed: 0.6, revealDelay: 0.15 },
    },
    at,
  )
}

/** Where an element is drawn, in the coordinates of its parent: its box, with its transform. */
function box(el: Element) {
  const g = el as SVGGraphicsElement
  const b = g.getBBox()
  const m = g.transform?.baseVal.consolidate()?.matrix
  if (!m) return { x: b.x, y: b.y, width: b.width, height: b.height }
  return { x: b.x * m.a + m.e, y: b.y * m.d + m.f, width: b.width * m.a, height: b.height * m.d }
}

/**
 * Turn one thing into another: `from` moves and scales onto where `to` is drawn while it fades
 * into it. manim's `Transform`, for any two SVG elements under the same parent (or parents
 * placed alike). `to` is left in its place and `from` hidden.
 */
export function transform(tl: Timeline, from: Element, to: Element, at: gsap.Position, opts: { duration?: number; ease?: string } = {}) {
  const duration = opts.duration ?? 1
  const ease = opts.ease ?? 'smooth'
  const a = box(from)
  const b = box(to)
  const sx = b.width / Math.max(a.width, 1e-3)
  const sy = b.height / Math.max(a.height, 1e-3)
  const [f, t] = at0([from, to])
  tl.fromTo(
    from,
    { x: f.x, y: f.y, scaleX: 1, scaleY: 1, autoAlpha: 1, transformOrigin: '0% 0%' },
    { x: f.x + b.x - a.x, y: f.y + b.y - a.y, scaleX: sx || 1, scaleY: sy || 1, autoAlpha: 0, duration, ease },
    at,
  )
  tl.fromTo(
    to,
    { x: t.x + a.x - b.x, y: t.y + a.y - b.y, scaleX: 1 / (sx || 1), scaleY: 1 / (sy || 1), autoAlpha: 0, transformOrigin: '0% 0%' },
    { x: t.x, y: t.y, scaleX: 1, scaleY: 1, autoAlpha: 1, duration, ease },
    '<',
  )
}

/**
 * Morph one path's outline into another's: `shape` is a path element, or a path's `d`. The two
 * need not have the same points; MorphSVG matches them up.
 */
export function morph(tl: Timeline, path: Element, shape: SVGPathElement | string, at: gsap.Position, opts: { duration?: number; ease?: string } = {}) {
  tl.to(path, { morphSVG: shape, duration: opts.duration ?? 1.1, ease: opts.ease ?? 'smooth' }, at)
}

/**
 * Point at a thing: it swells and takes on a colour for a moment, and is as it was after.
 * manim's `Indicate`.
 */
export function indicate(tl: Timeline, el: Targets, at: gsap.Position, opts: { color?: string; scale?: number; duration?: number } = {}) {
  const els = list(el)
  const duration = opts.duration ?? 0.8
  tl.to(els, { scale: opts.scale ?? 1.18, transformOrigin: '50% 50%', duration, ease: 'there.back' }, at)
  if (!opts.color) return
  const color = opts.color
  for (const e of els) {
    const prop = getComputedStyle(e).fill !== 'none' ? 'fill' : 'stroke'
    tl.fromTo(e, { [prop]: getComputedStyle(e)[prop] }, { [prop]: color, duration: duration / 2, ease: 'smooth', yoyo: true, repeat: 1 }, '<')
  }
}

/**
 * Spokes of light thrown out from a point, at `at`: manim's `Flash`, in light on the scene's
 * canvas rather than in the drawing. The point is where it is on the canvas, in viewBox units.
 */
export function flash(
  tl: Timeline,
  fx: () => Fx | undefined,
  p: { x: number; y: number },
  color: string | (() => string),
  at: gsap.Position,
  opts: { lines?: number; radius?: number; from?: number } = {},
) {
  tl.call(() => fx()?.flash(p.x, p.y, typeof color === 'function' ? color() : color, opts), [], at)
}

/**
 * Draw a frame round a thing and take it away again: manim's `Circumscribe`. A rectangle, or a
 * circle with `shape: 'circle'`, traced on round it with `pad` of room, held, and traced off.
 */
export function circumscribe(
  tl: Timeline,
  el: Element,
  at: gsap.Position,
  opts: { color?: string; pad?: number; shape?: 'rect' | 'circle'; width?: number; hold?: number; duration?: number } = {},
) {
  const parent = el.parentNode
  if (!parent) return
  const b = box(el)
  const pad = opts.pad ?? 6
  const ring = document.createElementNS(SVG, opts.shape === 'circle' ? 'circle' : 'rect')
  if (opts.shape === 'circle') {
    ring.setAttribute('cx', String(b.x + b.width / 2))
    ring.setAttribute('cy', String(b.y + b.height / 2))
    ring.setAttribute('r', String(Math.hypot(b.width, b.height) / 2 + pad))
  } else {
    ring.setAttribute('x', String(b.x - pad))
    ring.setAttribute('y', String(b.y - pad))
    ring.setAttribute('width', String(b.width + pad * 2))
    ring.setAttribute('height', String(b.height + pad * 2))
    ring.setAttribute('rx', String(Math.min(8, pad)))
  }
  ring.setAttribute('fill', 'none')
  ring.setAttribute('stroke', opts.color ?? 'var(--hmz-red)')
  ring.setAttribute('stroke-width', String(opts.width ?? 2))
  ring.setAttribute('stroke-linecap', 'round')
  ring.setAttribute('pointer-events', 'none')
  ring.setAttribute('aria-hidden', 'true')
  ring.style.visibility = 'hidden'
  parent.insertBefore(own(ring), el.nextSibling)
  const duration = opts.duration ?? 0.7
  tl.fromTo(ring, { drawSVG: '0%', autoAlpha: 1 }, { drawSVG: '100%', duration, ease: 'smooth' }, at)
  tl.to(ring, { drawSVG: '100% 100%', duration, ease: 'smooth' }, `>${opts.hold ?? 0.5}`)
  tl.set(ring, { autoAlpha: 0 }, '>')
}

/**
 * A short bright stretch running the length of a path and off its end: manim's
 * `ShowPassingFlash`, for a signal going down a wire. Drawn on a copy laid over the path.
 */
export function passingFlash(
  tl: Timeline,
  path: Element,
  at: gsap.Position,
  opts: { color?: string; width?: number; length?: number; duration?: number; ease?: string } = {},
) {
  const parent = path.parentNode
  if (!parent) return
  const copy = path.cloneNode(false) as SVGGeometryElement
  copy.removeAttribute('class')
  copy.removeAttribute('id')
  copy.setAttribute('fill', 'none')
  copy.setAttribute('stroke', opts.color ?? 'var(--hmz-red)')
  copy.setAttribute('stroke-width', String(opts.width ?? (parseFloat(getComputedStyle(path).strokeWidth) || 1.6) * 1.8))
  copy.setAttribute('stroke-linecap', 'round')
  copy.setAttribute('pointer-events', 'none')
  copy.setAttribute('aria-hidden', 'true')
  copy.style.visibility = 'hidden'
  parent.insertBefore(own(copy), path.nextSibling)
  const length = (opts.length ?? 0.22) * 100
  tl.fromTo(
    copy,
    { drawSVG: `0% 0%`, autoAlpha: 1 },
    { keyframes: { drawSVG: [`0% 0%`, `0% ${length}%`, `${100 - length}% 100%`, `100% 100%`] }, duration: opts.duration ?? 1, ease: opts.ease ?? 'none' },
    at,
  )
  tl.set(copy, { autoAlpha: 0 }, '>')
}

/**
 * Grow a thing from nothing out of a point: its centre, an edge, or a corner, as a
 * `transformOrigin` (`'50% 100%'` grows a bar up from its foot). It overshoots a little and
 * settles. manim's `GrowFromPoint`.
 */
export function growFrom(tl: Timeline, el: Targets, at: gsap.Position, opts: { origin?: string; duration?: number; stagger?: number } = {}) {
  tl.fromTo(
    list(el),
    { scale: 0, autoAlpha: 0, transformOrigin: opts.origin ?? '50% 50%' },
    { scale: 1, autoAlpha: 1, duration: opts.duration ?? 0.8, ease: 'settle', stagger: opts.stagger ?? 0.06 },
    at,
  )
}

/** Fade a thing in, moving the last of the way from `shift` (in its own units) as it comes. */
export function fadeIn(tl: Timeline, el: Targets, at: gsap.Position, opts: { shift?: { x?: number; y?: number }; duration?: number; stagger?: number } = {}) {
  const els = list(el)
  const home = at0(els)
  tl.fromTo(
    els,
    { autoAlpha: 0, x: (i: number) => home[i].x + (opts.shift?.x ?? 0), y: (i: number) => home[i].y + (opts.shift?.y ?? 0) },
    { autoAlpha: 1, x: (i: number) => home[i].x, y: (i: number) => home[i].y, duration: opts.duration ?? 0.7, ease: 'smooth.out', stagger: opts.stagger ?? 0.06 },
    at,
  )
}

/** Fade a thing out, moving off by `shift` as it goes. */
export function fadeOut(tl: Timeline, el: Targets, at: gsap.Position, opts: { shift?: { x?: number; y?: number }; duration?: number; stagger?: number } = {}) {
  const els = list(el)
  const home = at0(els)
  tl.to(els, { autoAlpha: 0, x: (i: number) => home[i].x + (opts.shift?.x ?? 0), y: (i: number) => home[i].y + (opts.shift?.y ?? 0), duration: opts.duration ?? 0.6, ease: 'smooth', stagger: opts.stagger ?? 0.04 }, at)
}

/** A damped shake about where it is, for "this one, here". manim's `Wiggle`. */
export function wiggle(tl: Timeline, el: Targets, at: gsap.Position, opts: { angle?: number; scale?: number; duration?: number } = {}) {
  const els = list(el)
  const duration = opts.duration ?? 0.9
  tl.to(els, { rotation: opts.angle ?? 6, transformOrigin: '50% 50%', duration, ease: 'wiggle' }, at)
  tl.to(els, { scale: opts.scale ?? 1.08, duration, ease: 'there.back' }, '<')
}

/**
 * A number that is kept, and seen changing: manim's `DecimalNumber` tracking a `ValueTracker`.
 * Counts from `from` to `to` in `el`'s text with `digits` after the point, the digits set in
 * tabular figures so the number does not jitter as it runs, and gives a small pulse as it lands.
 */
export function ticker(
  tl: Timeline,
  el: Element,
  from: number,
  to: number,
  at: gsap.Position,
  opts: { digits?: number; prefix?: string; suffix?: string; duration?: number; ease?: string; pulse?: boolean } = {},
) {
  const digits = opts.digits ?? 0
  const show = (n: number) =>
    `${opts.prefix ?? ''}${n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}${opts.suffix ?? ''}`
  const value = { n: from }
  const duration = opts.duration ?? 1.2
  tl.set(el, { fontVariantNumeric: 'tabular-nums' }, at)
  tl.fromTo(
    value,
    { n: from },
    {
      n: to,
      duration,
      ease: opts.ease ?? 'linger',
      onStart: () => {
        el.textContent = show(from)
      },
      onUpdate: () => {
        el.textContent = show(value.n)
      },
    },
    '<',
  )
  if (opts.pulse !== false) tl.to(el, { scale: 1.12, transformOrigin: '50% 50%', duration: 0.45, ease: 'there.back' }, `<${duration * 0.8}`)
}
