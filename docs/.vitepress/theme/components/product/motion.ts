import { onBeforeUnmount, onMounted, ref, type Directive, type Ref } from 'vue'

// The product page's motion, in one place. Everything on it moves for one of two reasons: where
// a section is on screen is a timeline (`useScrollProgress`), or something arrived on screen and
// plays once (`vReveal`). Both are read off a single scroll listener and a single
// IntersectionObserver, however many sections ask. Nothing is pinned: the page moves at the
// speed of the hand.

export const clamp = (v: number, lo = 0, hi = 1) => (v < lo ? lo : v > hi ? hi : v)

/** Asked once per call site, never at import: the page is rendered on the server first. */
export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

// ---------------------------------------------------------------------------------- scroll

type Tick = () => void
const ticks = new Set<Tick>()
let queued = false

const flush = () => {
  queued = false
  ticks.forEach((tick) => tick())
}
const queue = () => {
  if (!queued) {
    queued = true
    requestAnimationFrame(flush)
  }
}

/** Run `fn` once per animation frame in which the page scrolled or resized. */
function onScrollFrame(fn: Tick) {
  onMounted(() => {
    if (!ticks.size) {
      addEventListener('scroll', queue, { passive: true })
      addEventListener('resize', queue)
    }
    ticks.add(fn)
    fn()
  })
  onBeforeUnmount(() => {
    ticks.delete(fn)
    if (!ticks.size) {
      removeEventListener('scroll', queue)
      removeEventListener('resize', queue)
    }
  })
}

/**
 * A number driven by where `el` is in the window, recomputed on every frame the page scrolls or
 * resizes. `map` gets the element's box and the window height and returns whatever the section
 * wants -- usually how far through the window the element has travelled, as 0..1.
 */
export function useScrollProgress(el: Ref<HTMLElement | null>, map: (box: DOMRect, vh: number) => number) {
  const progress = ref(0)
  onScrollFrame(() => {
    const node = el.value
    if (node) progress.value = map(node.getBoundingClientRect(), innerHeight)
  })
  return progress
}

// ---------------------------------------------------------------------------------- reveal

let io: IntersectionObserver | null = null
const observer = () =>
  (io ??= new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        entry.target.classList.add('rv-in')
        io!.unobserve(entry.target)
      }
    },
    { threshold: 0.16, rootMargin: '0px 0px -6% 0px' },
  ))

/**
 * `v-reveal` or `v-reveal="120"`: fade and rise into place the first time the element is on
 * screen, after an optional delay in milliseconds. The hidden state lives in CSS under
 * `.hz-motion`, which is only set once the page has mounted and motion is allowed -- so the
 * server-rendered page, and a reader who asked for less motion, see everything at once.
 */
export const vReveal: Directive<HTMLElement, number | undefined> = {
  mounted(el, { value }) {
    el.classList.add('rv')
    if (value) el.style.setProperty('--rv-delay', `${value}ms`)
    observer().observe(el)
  },
  unmounted(el) {
    io?.unobserve(el)
  },
}
