import { onBeforeUnmount, onMounted, ref, type Directive, type Ref } from 'vue'

// The product page's motion, in one place (the same module humanfia.ai's home page moves by). Everything on it moves for one of two reasons: where a
// section is on screen is a timeline (`useScrollProgress`), or something arrived on screen and
// plays once (`vReveal`). Both are read off a single scroll listener and a single
// IntersectionObserver, however many sections ask.
//
// Nothing is pinned for longer than the reader would scroll past it anyway. The page used to hold
// its scenes still for two to five screens each, which made the wheel feel as if it were slipping;
// now the page moves at the speed of the hand, and the pictures are driven by where their section
// happens to be.

export const clamp = (v: number, lo = 0, hi = 1) => (v < lo ? lo : v > hi ? hi : v)
export const lerp = (a: number, b: number, u: number) => a + (b - a) * u

/** Where `p` is between `a` and `b`, as 0..1. The workhorse of every scroll timeline. */
export const span = (p: number, a: number, b: number) => clamp((p - a) / (b - a))

export const easeInOut = (u: number) => (u < 0.5 ? 4 * u * u * u : 1 - (-2 * u + 2) ** 3 / 2)
export const easeOut = (u: number) => 1 - (1 - u) ** 3

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
export function onScrollFrame(fn: Tick) {
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

/** Calls `fn` once, the first time `el` is mostly on screen. */
export function onFirstSight(el: Ref<HTMLElement | null>, fn: () => void, threshold = 0.35) {
  let seen: IntersectionObserver | null = null
  onMounted(() => {
    if (!el.value) return
    seen = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return
        seen?.disconnect()
        fn()
      },
      { threshold },
    )
    seen.observe(el.value)
  })
  onBeforeUnmount(() => seen?.disconnect())
}

// ---------------------------------------------------------------------------------- canvas

/**
 * A canvas that draws every frame while it is on screen and not at all when it is not. `draw`
 * gets the time in seconds and the canvas's CSS size; the backing store is kept at the device
 * pixel ratio, capped at 2 because a third of the pixels again is not worth the fill rate.
 */
export class Stage {
  readonly ctx: CanvasRenderingContext2D
  width = 0
  height = 0
  dpr = 1
  private raf = 0
  private visible = false
  private readonly start = performance.now()
  private readonly ro: ResizeObserver
  private readonly vo: IntersectionObserver

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly draw: (t: number, stage: Stage) => void,
    private readonly animated = true,
  ) {
    this.ctx = canvas.getContext('2d')!
    this.ro = new ResizeObserver(() => this.resize())
    this.ro.observe(canvas)
    this.vo = new IntersectionObserver(([entry]) => {
      this.visible = entry.isIntersecting
      if (this.visible) this.loop()
    })
    this.vo.observe(canvas)
    this.resize()
  }

  private resize() {
    const box = this.canvas.getBoundingClientRect()
    this.dpr = Math.min(2, devicePixelRatio || 1)
    this.width = box.width
    this.height = box.height
    this.canvas.width = Math.round(box.width * this.dpr)
    this.canvas.height = Math.round(box.height * this.dpr)
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this.frame()
  }

  /** Draw once now -- for a still canvas, or one whose inputs just changed. */
  frame() {
    if (!this.width || !this.height) return
    this.draw((performance.now() - this.start) / 1000, this)
  }

  private loop = () => {
    cancelAnimationFrame(this.raf)
    if (!this.visible) return
    this.frame()
    if (this.animated) this.raf = requestAnimationFrame(this.loop)
  }

  destroy() {
    cancelAnimationFrame(this.raf)
    this.ro.disconnect()
    this.vo.disconnect()
  }
}

/**
 * The same loop for something that is not a canvas: `draw` gets the time in seconds on every
 * frame while `el` is on screen, and none while it is not.
 */
export class Clock {
  private raf = 0
  private visible = false
  private readonly start = performance.now()
  private readonly vo: IntersectionObserver

  constructor(
    private readonly el: Element,
    private readonly draw: (t: number) => void,
    private readonly animated = true,
  ) {
    this.vo = new IntersectionObserver(([entry]) => {
      this.visible = entry.isIntersecting
      if (this.visible) this.loop()
    })
    this.vo.observe(el)
    this.frame()
  }

  frame() {
    this.draw((performance.now() - this.start) / 1000)
  }

  private loop = () => {
    cancelAnimationFrame(this.raf)
    if (!this.visible) return
    this.frame()
    if (this.animated) this.raf = requestAnimationFrame(this.loop)
  }

  destroy() {
    cancelAnimationFrame(this.raf)
    this.vo.disconnect()
  }
}
