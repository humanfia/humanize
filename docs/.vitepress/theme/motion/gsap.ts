// GSAP, with the plugins the feature scenes use and the eases they share, registered once and
// only in a browser: the build renders every page on the server, where there is nothing to
// animate. Every scene gets its GSAP from `motion()` rather than importing it bare, so the
// registration can never be skipped.
import { gsap } from 'gsap'
import { CustomEase } from 'gsap/CustomEase'
import { DrawSVGPlugin } from 'gsap/DrawSVGPlugin'
import { MotionPathPlugin } from 'gsap/MotionPathPlugin'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'
import { TextPlugin } from 'gsap/TextPlugin'

let ready = false

export function motion(): typeof gsap {
  if (!ready && typeof window !== 'undefined') {
    gsap.registerPlugin(CustomEase, DrawSVGPlugin, MotionPathPlugin, ScrollTrigger, SplitText, TextPlugin)
    // The three eases every scene is cut with. `cine` is a camera move: slow away, slow in.
    // `cine.out` is an arrival, fast then settling. `cine.in` is a departure.
    CustomEase.create('cine', '0.7,0,0.2,1')
    CustomEase.create('cine.out', '0.16,1,0.3,1')
    CustomEase.create('cine.in', '0.7,0,0.84,0')
    gsap.defaults({ ease: 'cine.out', duration: 0.8 })
    ready = true
  }
  return gsap
}

export { gsap, ScrollTrigger, SplitText }
