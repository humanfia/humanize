// GSAP, with the plugins the feature scenes use and the eases they share, registered once and
// only in a browser: the build renders every page on the server, where there is nothing to
// animate. Every scene gets its GSAP from `motion()` rather than importing it bare, so the
// registration can never be skipped.
import { gsap } from 'gsap'
import { CustomEase } from 'gsap/CustomEase'
import { CustomWiggle } from 'gsap/CustomWiggle'
import { DrawSVGPlugin } from 'gsap/DrawSVGPlugin'
import { MorphSVGPlugin } from 'gsap/MorphSVGPlugin'
import { MotionPathPlugin } from 'gsap/MotionPathPlugin'
import { ScrambleTextPlugin } from 'gsap/ScrambleTextPlugin'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'
import { TextPlugin } from 'gsap/TextPlugin'

/**
 * The eases a scene is cut with, by name: pass the name as any tween's `ease`.
 *
 * The first three are the camera's. `cine` is a camera move: slow away, slow in. `cine.out` is
 * an arrival, fast then settling. `cine.in` is a departure.
 *
 * The rest are the rate functions a 3Blue1Brown animation is timed by:
 *
 * - `smooth`: the default of a manim animation, an S-curve flatter at both ends than `cine`,
 *   for a thing that changes rather than travels -- a colour, a morph, a label redrawn.
 * - `smooth.out`: the same, starting at speed: for a second step that follows a first.
 * - `rush.into`: gathers speed and hits its mark at full tilt, for a thing that strikes.
 * - `rush.from`: leaves at full tilt and coasts in, for a thing thrown or let go.
 * - `settle`: overshoots its mark by a few percent and comes back, for a thing set down.
 * - `there.back`: out and home again in one tween, for an emphasis that leaves nothing behind
 *   (`scale: 1.2` with it is a pulse that ends where it began).
 * - `linger`: arrives early and creeps the last stretch, for a value read as it lands.
 * - `wiggle`: a damped shake about where the thing is, for "this one".
 */
export const EASES: Record<string, string> = {
  cine: '0.7,0,0.2,1',
  'cine.out': '0.16,1,0.3,1',
  'cine.in': '0.7,0,0.84,0',
  smooth: '0.62,0,0.38,1',
  'smooth.out': '0.22,0.6,0.36,1',
  'rush.into': '0.6,0,1,0.55',
  'rush.from': '0,0.5,0.35,1',
  settle: 'M0,0 C0.14,0.62 0.28,1.06 0.5,1.045 0.68,1.033 0.8,1 1,1',
  'there.back': 'M0,0 C0.18,0.72 0.32,1 0.5,1 0.68,1 0.82,0.72 1,0',
  linger: '0.08,0.82,0.16,1',
}

let ready = false

export function motion(): typeof gsap {
  if (!ready && typeof window !== 'undefined') {
    gsap.registerPlugin(
      CustomEase,
      CustomWiggle,
      DrawSVGPlugin,
      MorphSVGPlugin,
      MotionPathPlugin,
      ScrambleTextPlugin,
      ScrollTrigger,
      SplitText,
      TextPlugin,
    )
    for (const [name, curve] of Object.entries(EASES)) CustomEase.create(name, curve)
    CustomWiggle.create('wiggle', { wiggles: 6, type: 'easeOut' })
    gsap.defaults({ ease: 'cine.out', duration: 0.8 })
    ready = true
  }
  return gsap
}

export { gsap, ScrollTrigger, SplitText }
