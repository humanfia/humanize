// The moves the User Guide's scenes are cut from, kept once so every scene in the guide moves
// alike: a thing pops in, rises into place, is drawn on, rings when something reaches it,
// shakes when it is refused, and is named by a brace drawn under it. Each takes the scene's
// timeline and a place on it, and adds tweens there: nothing here starts a clock of its own,
// so a scene stays seekable, and its reduced-motion still frame is a frame of the same moves.
//
// Move a `<g>` round a word rather than the `<text>` itself: `HmzStage` scales small words back
// up on a narrow screen with CSS `scale`, and GSAP would bake that into a transform of its own.
//
// Colours are never passed in: what these touch takes its colour from the scene's CSS, which
// reads the theme's variables, so a scene flips with the theme mid-play.
type Timeline = gsap.core.Timeline
type Targets = gsap.TweenTarget

/** A thing arrives: from nothing and small, overshooting a little into place. */
export function pop(tl: Timeline, el: Targets, at: gsap.Position, o: { from?: number; duration?: number; stagger?: number; ease?: string } = {}) {
  tl.fromTo(
    el,
    { autoAlpha: 0, scale: o.from ?? 0.4, transformOrigin: '50% 50%' },
    { autoAlpha: 1, scale: 1, duration: o.duration ?? 0.45, ease: o.ease ?? 'back.out(2.2)', stagger: o.stagger ?? 0 },
    at,
  )
}

/** Things rise into place, one after another. */
export function rise(tl: Timeline, el: Targets, at: gsap.Position, o: { y?: number; x?: number; duration?: number; stagger?: number } = {}) {
  tl.fromTo(
    el,
    { autoAlpha: 0, y: o.y ?? 14, x: o.x ?? 0 },
    { autoAlpha: 1, y: 0, x: 0, duration: o.duration ?? 0.6, stagger: o.stagger ?? 0.08, ease: 'cine.out' },
    at,
  )
}

/** A stroke drawn on from its start, as a pen would. */
export function draw(tl: Timeline, el: Targets, at: gsap.Position, o: { duration?: number; ease?: string; stagger?: number; from?: string } = {}) {
  tl.fromTo(el, { drawSVG: o.from ?? '0%', autoAlpha: 1 }, { drawSVG: '100%', duration: o.duration ?? 0.8, ease: o.ease ?? 'cine', stagger: o.stagger ?? 0 }, at)
}

/**
 * A ring goes out from a thing and fades: something reached it. It starts invisible, so a
 * seek to before it never leaves it hanging there.
 */
export function ring(tl: Timeline, el: Targets, at: gsap.Position, o: { to?: number; duration?: number } = {}) {
  tl.fromTo(el, { autoAlpha: 0, scale: 0.7, transformOrigin: '50% 50%' }, { autoAlpha: 0.9, duration: 0.06, ease: 'none' }, at)
  tl.to(el, { autoAlpha: 0, scale: o.to ?? 1.7, duration: o.duration ?? 0.9, ease: 'power2.out' }, '>')
}

/** A thing is jolted sideways: refused, cut, or hit. */
export function shake(tl: Timeline, el: Targets, at: gsap.Position, amp = 6) {
  tl.fromTo(el, { x: 0 }, { keyframes: { x: [0, -amp, amp * 0.85, -amp * 0.55, amp * 0.3, 0] }, duration: 0.45, ease: 'none' }, at)
}

/** A thing swells for a moment and settles: look here. */
export function pulse(tl: Timeline, el: Targets, at: gsap.Position, by = 1.08) {
  tl.fromTo(el, { scale: 1, transformOrigin: '50% 50%' }, { keyframes: { scale: [1, by, 1] }, duration: 0.5, ease: 'sine.inOut' }, at)
}

/**
 * A brace drawn along a span and its label risen under it: the way a 3Blue1Brown frame names
 * one part of what is on screen. `el` holds a `.brace-path` and a `.brace-label`.
 */
export function brace(tl: Timeline, q: (s: string) => Element[], el: string, at: gsap.Position) {
  draw(tl, q(`${el} .brace-path`), at, { duration: 0.55, ease: 'cine.out' })
  rise(tl, q(`${el} .brace-label`), `<0.2`, { y: 6, duration: 0.45 })
}

export interface Pt {
  x: number
  y: number
}

/**
 * The path of a curly brace from `a` to `b`, its point `depth` to the right of the direction
 * of travel: from left to right, a brace that opens downward.
 */
export function braceD(a: Pt, b: Pt, depth = 10): string {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const len = Math.hypot(dx, dy) || 1
  const ux = dx / len
  const uy = dy / len
  // To the right of travel, in screen coordinates (y down).
  const nx = -uy
  const ny = ux
  const r = Math.min(depth, len / 6)
  const at = (s: number, n: number) => `${(a.x + ux * s + nx * n).toFixed(1)} ${(a.y + uy * s + ny * n).toFixed(1)}`
  const h = depth / 2
  const m = len / 2
  return [
    `M${at(0, 0)}`,
    `Q${at(0, h)} ${at(r, h)}`,
    `L${at(m - r, h)}`,
    `Q${at(m, h)} ${at(m, depth)}`,
    `Q${at(m, h)} ${at(m + r, h)}`,
    `L${at(len - r, h)}`,
    `Q${at(len, h)} ${at(len, 0)}`,
  ].join(' ')
}

/** A curve from `a` to `b`, bowed by `bend` of its length to the left of travel. */
export function curve(a: Pt, b: Pt, bend = 0.2): string {
  const cx = (a.x + b.x) / 2 + (b.y - a.y) * bend
  const cy = (a.y + b.y) / 2 - (b.x - a.x) * bend
  return `M${a.x} ${a.y} Q${cx.toFixed(1)} ${cy.toFixed(1)} ${b.x} ${b.y}`
}
