<script setup lang="ts">
// A number that counts up to itself the first time it is on screen.
//
// The final value is what the server renders and what a screen reader reads: the counting is a
// second, aria-hidden copy laid over it, so nothing that cannot see the motion ever meets a
// half-counted number, and a reader who asked for less motion sees the final value and nothing
// else. The count eases out -- fast, then settling -- because a number that arrives linearly
// reads as a timer rather than a result. `linear` is there for the one case that is a timer.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { format, prefersReducedMotion, useInView } from './shared'

const props = withDefaults(
  defineProps<{
    value: number
    from?: number
    decimals?: number
    prefix?: string
    suffix?: string
    /** Milliseconds. */
    duration?: number
    delay?: number
    linear?: boolean
  }>(),
  { from: 0, decimals: 0, prefix: '', suffix: '', duration: 1400, delay: 0, linear: false },
)

const el = ref<HTMLElement | null>(null)
const seen = useInView(el, 0.4)
const final = computed(() => format(props.value, props.decimals, props.suffix, props.prefix))
const shown = ref<string | null>(null)

let frame = 0
let timer = 0

/** Where the count is now, so a new value counts on from it rather than from the start. */
let current = props.from

function run(start = props.from) {
  cancelAnimationFrame(frame)
  clearTimeout(timer)
  if (prefersReducedMotion()) {
    shown.value = null
    current = props.value
    return
  }
  const target = props.value
  shown.value = format(start, props.decimals, props.suffix, props.prefix)
  timer = window.setTimeout(() => {
    const began = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - began) / props.duration)
      const eased = props.linear ? t : 1 - (1 - t) ** 3
      current = start + (target - start) * eased
      shown.value = format(current, props.decimals, props.suffix, props.prefix)
      if (t < 1) frame = requestAnimationFrame(tick)
      else shown.value = null
    }
    frame = requestAnimationFrame(tick)
  }, props.delay)
}

watch(seen, (now) => now && run())
// A new value (a toggle elsewhere in the figure) counts from wherever the old one was.
watch(
  () => props.value,
  () => seen.value && run(current),
)
onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  clearTimeout(timer)
})
</script>

<template>
  <span ref="el" class="ticker">
    <span :class="{ 'ticker-hold': shown !== null }">{{ final }}</span>
    <span v-if="shown !== null" class="ticker-run" aria-hidden="true">{{ shown }}</span>
  </span>
</template>

<style scoped>
.ticker {
  position: relative;
  display: inline-block;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* The final value keeps its width while the count runs over it, so nothing around it reflows --
   and it is transparent rather than hidden, so a screen reader still reads it. */
.ticker-hold {
  opacity: 0;
}

.ticker-run {
  position: absolute;
  inset: 0 auto auto 0;
}
</style>
