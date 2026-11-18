<script setup lang="ts">
// The name, drawn rather than typed: the H, then "humanfia" in the same stems and bars, and one
// green circle that belongs to both. It rests as the dot of the i. On its own -- the first time
// the wordmark is on screen, and then on a loop a few seconds apart while it stays in view, with
// no pointer needed -- and at once when a pointer comes to it, it hops across the word into the slot over the H's right stem, waits there, and hops
// back. Either resting place is a finished lockup: the H is complete without its circle, and the
// i is a plain stem without its dot.
//
// The hop is a real throw rather than a tween along a curve. A crouch first (the circle squashes
// against whatever it is sitting on), then a parabola at constant speed across, stretched along
// its own velocity so it is longest where it is fastest, then a landing that squashes, overshoots
// a little in the direction it was travelling and rings out on a damped spring. The numbers are
// in the wordmark's own units (the mark is 108 tall), so it hops the same at any size.
//
// One element, one attribute written per frame, and no frames at all while nothing moves. A reader
// who asked for less motion gets the still wordmark: the dot on the i, the H without it.
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { I_DOT, DOT, MARK_PATH, WORDMARK, WORD_PATH } from './logo'

const props = withDefaults(defineProps<{ loop?: boolean }>(), { loop: true })

const root = ref<SVGSVGElement | null>(null)
const dot = ref<SVGCircleElement | null>(null)

type Pose = { x: number; y: number; sx: number; sy: number; rot: number; foot: boolean }
type Segment = { dur: number; pose: (t: number) => Pose }

const R = DOT.r
const AT_I = { x: I_DOT.cx, y: I_DOT.cy }
const AT_H = { x: DOT.cx, y: DOT.cy }

const rest = (p: { x: number; y: number }): Pose => ({ ...p, sx: 1, sy: 1, rot: 0, foot: true })

/** The transform for a pose. A crouch or a landing squashes from the circle's foot, so it reads as
 *  pressing on something; in the air it stretches about its centre, along the way it is going. */
function transform({ x, y, sx, sy, rot, foot }: Pose) {
  if (foot) return `translate(${x} ${y + R}) scale(${sx} ${sy}) translate(0 ${-R})`
  const deg = (rot * 180) / Math.PI
  return `translate(${x} ${y}) rotate(${deg}) scale(${sx} ${sy}) rotate(${-deg})`
}

const CROUCH = 0.2
const FLIGHT = 0.7
const SETTLE = 0.75
/** Height of the arc above the cap line, in mark units: a little over two stems. Bounded by the
 *  nav: the wordmark is 27px tall in a 64px bar, so its top is ~18px from the window's edge, and
 *  at 56 units the dot's top clears that edge with a few pixels to spare at the arc's peak. */
const APEX = 56

/** One hop: crouch, throw, land. */
function hop(from: { x: number; y: number }, to: { x: number; y: number }): Segment[] {
  const dir = Math.sign(to.x - from.x)
  const vx = (to.x - from.x) / FLIGHT
  // Fastest at either end of a parabola, so the stretch is normalised by the launch speed.
  const v0 = Math.hypot(vx, (4 * APEX) / FLIGHT)
  return [
    {
      dur: CROUCH,
      pose: (t) => {
        const k = Math.sin((t / CROUCH) * Math.PI * 0.5)
        return { ...rest(from), sy: 1 - 0.22 * k, sx: 1 + 0.14 * k }
      },
    },
    {
      dur: FLIGHT,
      pose: (t) => {
        const u = t / FLIGHT
        const vy = (-4 * APEX * (1 - 2 * u)) / FLIGHT
        const stretch = 1 + 0.26 * (Math.hypot(vx, vy) / v0) ** 2
        return {
          x: from.x + (to.x - from.x) * u,
          y: from.y - 4 * APEX * u * (1 - u),
          sx: stretch,
          sy: 1 / stretch,
          rot: Math.atan2(vy, vx),
          foot: false,
        }
      },
    },
    {
      dur: SETTLE,
      pose: (t) => {
        const ring = Math.exp(-6.5 * t)
        const squash = 0.3 * ring * Math.cos(17 * t)
        return {
          // A little past the slot in the direction of travel, then back: the slight overshoot.
          x: to.x + dir * 7 * Math.exp(-7 * t) * Math.sin(13 * t),
          y: to.y,
          sx: 1 + squash * 0.8,
          sy: 1 - squash,
          rot: 0,
          foot: true,
        }
      },
    },
  ]
}

const hold = (at: { x: number; y: number }, dur: number): Segment[] => [{ dur, pose: () => rest(at) }]

/** There and back, with a wait at the H long enough to see the mark whole. */
const roundTrip = (wait: number) => [...hop(AT_I, AT_H), ...hold(AT_H, wait), ...hop(AT_H, AT_I)]

let queue: Segment[] = []
let start = 0
let raf = 0
let timer: ReturnType<typeof setTimeout> | undefined
let visible = false
let still = true
let io: IntersectionObserver | null = null
let seen = false

function draw(pose: Pose) {
  dot.value?.setAttribute('transform', transform(pose))
}

function frame(now: number) {
  let t = (now - start) / 1000
  while (queue.length && t >= queue[0].dur) {
    t -= queue[0].dur
    start += queue[0].dur * 1000
    const done = queue.shift()!
    if (!queue.length) {
      draw(done.pose(done.dur))
      raf = 0
      schedule()
      return
    }
  }
  draw(queue[0].pose(t))
  raf = requestAnimationFrame(frame)
}

function play(segments: Segment[]) {
  if (still || raf) return
  clearTimeout(timer)
  queue = segments
  start = performance.now()
  raf = requestAnimationFrame(frame)
}

/** The loop: the next round trip a few seconds after the last one ended, only while on screen. */
function schedule() {
  clearTimeout(timer)
  if (!props.loop || !visible) return
  timer = setTimeout(() => play(roundTrip(2.6)), 4000)
}

/** The first round trip, shortly after the wordmark is first on screen. */
function first() {
  if (seen) return
  seen = true
  clearTimeout(timer)
  timer = setTimeout(() => play(roundTrip(2.2)), 900)
}

/** A pointer arriving is answered at once, with a shorter wait at the H. */
function poke() {
  play(roundTrip(1.2))
}

onMounted(() => {
  still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  draw(rest(AT_I))
  if (still || !root.value) return
  // Started from where the wordmark is, rather than waiting on the observer's first report, which
  // a browser may hold back -- in the nav it is on screen from the first frame.
  const box = root.value.getBoundingClientRect()
  visible = box.bottom > 0 && box.top < innerHeight && box.width > 0
  if (visible) first()
  io = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting
    if (!visible) return clearTimeout(timer)
    if (raf) return
    if (!seen) first()
    else schedule()
  })
  io.observe(root.value)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  clearTimeout(timer)
  io?.disconnect()
})

defineExpose({ poke })
</script>

<template>
  <!-- `overflow: visible` because the arc rises above the box: the box is the lockup at rest,
       which is what the layout should make room for. -->
  <svg
    ref="root"
    class="hf-wordmark"
    :viewBox="`0 0 ${WORDMARK.width} ${WORDMARK.height}`"
    role="img"
    aria-label="Humanfia"
    :style="{ aspectRatio: `${WORDMARK.width} / ${WORDMARK.height}` }"
    @pointerenter="poke"
  >
    <path class="hf-wordmark-ink" :d="MARK_PATH" />
    <path class="hf-wordmark-ink" :d="WORD_PATH" fill-rule="evenodd" />
    <circle
      ref="dot"
      class="hf-wordmark-dot"
      cx="0"
      cy="0"
      :r="R"
      :transform="`translate(${AT_I.x} ${AT_I.y})`"
    />
  </svg>
</template>

<style scoped>
.hf-wordmark {
  display: block;
  height: var(--hf-wordmark-height, 24px);
  width: auto;
  overflow: visible;
}

.hf-wordmark-ink {
  fill: var(--hf-mark);
}

.hf-wordmark-dot {
  fill: var(--hf-green);
}
</style>
