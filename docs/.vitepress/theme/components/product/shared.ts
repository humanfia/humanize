import { onBeforeUnmount, onMounted, ref, useId, type Ref } from 'vue'

// What every figure in the post kit shares: when it is on screen, how wide it is, whether the
// reader asked for less motion, and how a number is written.
//
// The charts draw in real pixels, not in a viewBox that is scaled to fit. A viewBox scaled down
// to a phone shrinks its labels with it -- an 11px tick label in a 640-wide box is under 6px on a
// 375px screen -- and the site's floor is 11px. So every chart measures the box it was given and
// lays itself out in that many pixels; the server renders it at a default width, and the first
// measurement after hydration redraws it at the real one.

/** Asked at call time, never at import: the page is rendered on the server first. */
export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** True once the element has come on screen, and true from the start for a reader who asked for
 *  less motion -- everything keyed off it then renders its final state straight away.
 *
 *  "On screen" is `threshold` of the element visible, or half the viewport filled by it: an
 *  element taller than the viewport divided by the threshold can never show that fraction of
 *  itself, and would otherwise wait for ever with its bars at zero. */
export function useInView(el: Ref<Element | null | undefined>, threshold = 0.25) {
  const seen = ref(false)
  let observer: IntersectionObserver | undefined
  onMounted(() => {
    if (prefersReducedMotion() || typeof IntersectionObserver === 'undefined' || !el.value) {
      seen.value = true
      return
    }
    const steps = Array.from({ length: 11 }, (_, i) => (i / 10) * threshold)
    observer = new IntersectionObserver(
      (entries) => {
        const hit = entries.some(
          (entry) =>
            entry.isIntersecting &&
            (entry.intersectionRatio >= threshold - 1e-3 ||
              entry.intersectionRect.height >= (entry.rootBounds?.height ?? window.innerHeight) * 0.5),
        )
        if (hit) {
          seen.value = true
          observer?.disconnect()
        }
      },
      { threshold: steps },
    )
    observer.observe(el.value)
  })
  onBeforeUnmount(() => observer?.disconnect())
  return seen
}

/** The element's content width in CSS pixels, kept current. `fallback` is what the server and
 *  the first client render use, before anything has been measured. */
export function useWidth(el: Ref<Element | null | undefined>, fallback = 640) {
  const width = ref(fallback)
  let observer: ResizeObserver | undefined
  onMounted(() => {
    if (!el.value) return
    const measure = () => {
      const next = Math.round(el.value!.getBoundingClientRect().width)
      if (next > 0 && next !== width.value) width.value = next
    }
    measure()
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(measure)
      observer.observe(el.value)
    }
  })
  onBeforeUnmount(() => observer?.disconnect())
  return width
}

/** A number the way a chart labels it: fixed decimals, thousands separated, a unit after. */
export function format(value: number, decimals = 0, suffix = '', prefix = '') {
  if (!Number.isFinite(value)) return '—'
  const text = value.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
  return `${prefix}${text}${suffix}`
}

/** A signed difference, for the deltas a baseline toggle shows. */
export function signed(value: number, decimals = 0, suffix = '') {
  if (!Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : '±'
  return `${sign}${format(Math.abs(value), decimals, suffix)}`
}

/** Linear scale, `domain` onto `range`. */
export const scale =
  ([d0, d1]: readonly [number, number], [r0, r1]: readonly [number, number]) =>
  (v: number) =>
    d1 === d0 ? r0 : r0 + ((v - d0) / (d1 - d0)) * (r1 - r0)

/** Round-number ticks across `[lo, hi]`, about `count` of them: 1, 2 or 5 times a power of ten. */
export function niceTicks(lo: number, hi: number, count = 5) {
  if (hi <= lo) return [lo]
  const raw = (hi - lo) / Math.max(1, count)
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? raw
  const ticks: number[] = []
  for (let t = Math.ceil(lo / step - 1e-9) * step; t <= hi + 1e-9; t += step) {
    ticks.push(Number(t.toPrecision(12)))
  }
  return ticks
}

/**
 * The tones a series can be drawn in. The palette is a constructivist poster's -- ink, paper and
 * one accent -- so a chart has three inks to spend, and every one of them is a CSS variable that
 * flips with the page: the accent is ours, the ink is the comparison, the grey is the baseline. A
 * fourth tone, `pale`, is the grey a step lighter, for a context series nobody should look at
 * first. Colour is never the only difference: a baseline is also hatched or dashed.
 */
export type Tone = 'accent' | 'ink' | 'grey' | 'pale'
export const TONES: Tone[] = ['accent', 'ink', 'grey', 'pale']
export const toneOf = (tone: Tone | undefined, index: number): Tone => tone ?? TONES[index % TONES.length]

/** A stable id for aria wiring: Vue's own, so the server and the browser agree on it. */
export const uid = (prefix: string) => `${prefix}-${useId()}`

/** A column of a results table (ResultsTable.vue), and of every chart's data view. */
export interface Column {
  key: string
  label: string
  /** Numbers are right-aligned by default and text left. */
  align?: 'left' | 'right'
  decimals?: number
  prefix?: string
  suffix?: string
  /** Draw a bar behind the number, scaled to the column's largest value. */
  bar?: boolean
  /** Lower is better: sorting by this column puts the smallest first. */
  lowerIsBetter?: boolean
  sortable?: boolean
}
