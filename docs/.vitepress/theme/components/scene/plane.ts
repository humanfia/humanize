// Moves the feature scenes on the features pages share, built only from the motion core's own
// pieces, so they cut the same way every other scene does.

type Timeline = gsap.core.Timeline
type Query = (selector: string) => Element[]

/**
 * Lay down a `ScenePlane`: its two axes drawn out from the origin both ways, then every other
 * line from its middle out, nearest the origin first, then the ticks.
 */
export function drawPlane(tl: Timeline, q: Query, at: number, opts: { duration?: number } = {}) {
  const d = opts.duration ?? 1.6
  tl.fromTo(q('.plane-axis'), { drawSVG: '50% 50%' }, { drawSVG: '0% 100%', duration: d * 0.6, ease: 'cine' }, at)
  tl.fromTo(q('.plane-line'), { drawSVG: '50% 50%' }, { drawSVG: '0% 100%', duration: d * 0.55, ease: 'cine', stagger: { amount: d * 0.45 } }, at + d * 0.2)
  tl.fromTo(q('.plane-ticks line'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3, stagger: { amount: d * 0.3 } }, at + d * 0.5)
}

/**
 * A label that becomes another, or a copy of one that flies to where it is wanted: `to` starts
 * offset by `dx`, `dy` (in the units of its own drawing) -- where the word it comes from is
 * drawn -- and glides home, while `from`, if given, fades. `to` must be a group rather than a
 * `<text>`: GSAP writes a transform on what it moves, and the stage lifts a small `<text>` on a
 * narrow screen with a transform of its own. Neither is scaled on the way, so both stay at a
 * size a reader can read.
 */
export function glide(
  tl: Timeline,
  from: Element | null,
  to: Element,
  dx: number,
  dy: number,
  at: number,
  opts: { duration?: number; ease?: string } = {},
) {
  const d = opts.duration ?? 0.9
  tl.fromTo(to, { x: dx, y: dy }, { x: 0, y: 0, duration: d, ease: opts.ease ?? 'cine' }, at)
  // Fully there by the first fifth of the move: a word is never two half-words for long.
  tl.fromTo(to, { autoAlpha: 0 }, { autoAlpha: 1, duration: d * 0.2, ease: 'none' }, at)
  if (from) tl.to(from, { autoAlpha: 0, duration: d * 0.2, ease: 'none' }, at)
}
