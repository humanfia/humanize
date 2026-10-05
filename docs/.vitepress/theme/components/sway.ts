// The small motion that keeps a still part of a scene alive -- a cursor blinking, dashes
// crawling along a wire, a glow breathing -- put on the scene's own timeline rather than left
// to a CSS animation or a loose tween. A loop of its own would run on a clock of its own: a
// chapter jump, the reduced-motion still frame or the legibility check holding the scene at
// a moment would each find it wherever its clock had got to. On the timeline it is where the
// timeline is, every time.
//
// Each helper fills a span of the timeline, `from` to `to` seconds, with whole periods of its
// motion, and leaves the element as it found it at the end.
type Timeline = gsap.core.Timeline
type Targets = gsap.TweenTarget

/** How many whole half-periods fit in the span, at least one. */
const halves = (from: number, to: number, period: number) => Math.max(1, Math.floor(((to - from) * 2) / period))

/** A cursor blinking: hidden and shown, `period` seconds a blink. */
export function blink(tl: Timeline, el: Targets, from: number, to: number, period = 1) {
  const n = halves(from, to, period)
  tl.fromTo(el, { autoAlpha: 1 }, { autoAlpha: 0, duration: period / 2, ease: 'steps(1)', repeat: n - 1, yoyo: true, immediateRender: false }, from)
  if (n % 2) tl.set(el, { autoAlpha: 1 }, from + (n * period) / 2)
}

/** Dashes crawling along a stroke: `step` user units every `period` seconds. */
export function crawl(tl: Timeline, el: Targets, from: number, to: number, opts: { step?: number; period?: number } = {}) {
  const step = opts.step ?? 14
  const period = opts.period ?? 1
  tl.fromTo(el, { strokeDashoffset: 0 }, { strokeDashoffset: (-step * (to - from)) / period, duration: to - from, ease: 'none', immediateRender: false }, from)
}

/** A glow breathing: up to `opacity` (and `scale`, about its centre) and back, `period` a breath. */
export function breathe(tl: Timeline, el: Targets, from: number, to: number, opts: { period?: number; opacity?: number; scale?: number; rest?: number } = {}) {
  const period = opts.period ?? 2.4
  const n = halves(from, to, period)
  const even = n - (n % 2)
  if (!even) return
  const rest = opts.rest ?? 1
  const peak: gsap.TweenVars = { opacity: opts.opacity ?? 0.55 }
  const base: gsap.TweenVars = { opacity: rest }
  if (opts.scale) {
    peak.scale = opts.scale
    base.scale = 1
    base.transformOrigin = '50% 50%'
  }
  tl.fromTo(el, base, { ...peak, duration: period / 2, ease: 'sine.inOut', repeat: even - 1, yoyo: true, immediateRender: false }, from)
}
