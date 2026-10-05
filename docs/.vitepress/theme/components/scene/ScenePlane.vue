<script setup lang="ts">
// The squared paper a feature scene is drawn on: a plane of faint lines a fixed step apart, two
// axes through an origin a little stronger, and ticks along them. `drawPlane` (in `plane.ts`)
// lays it down at the start of a scene the way a number plane is drawn on a blackboard: the
// axes first, out from the origin both ways, then every other line, nearest first.
//
// It runs past the edges of the viewBox by `bleed`, so a camera pulling back never shows where
// the paper ends. Every colour is the stage's own, so it follows the reader's theme.
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    w: number
    h: number
    /** Where the axes cross. The middle by default. */
    ox?: number
    oy?: number
    step?: number
    bleed?: number
  }>(),
  { ox: undefined, oy: undefined, step: 32, bleed: 160 },
)

const origin = computed(() => ({ x: props.ox ?? props.w / 2, y: props.oy ?? props.h / 2 }))

const lines = computed(() => {
  const { x: ox, y: oy } = origin.value
  const { step, bleed, w, h } = props
  const out: { x1: number; y1: number; x2: number; y2: number; d: number }[] = []
  for (let k = 1; ox - k * step >= -bleed || ox + k * step <= w + bleed; k += 1) {
    for (const x of [ox - k * step, ox + k * step]) {
      if (x >= -bleed && x <= w + bleed) out.push({ x1: x, y1: -bleed, x2: x, y2: h + bleed, d: k })
    }
  }
  for (let k = 1; oy - k * step >= -bleed || oy + k * step <= h + bleed; k += 1) {
    for (const y of [oy - k * step, oy + k * step]) {
      if (y >= -bleed && y <= h + bleed) out.push({ x1: -bleed, y1: y, x2: w + bleed, y2: y, d: k })
    }
  }
  // Nearest the origin first, so a stagger draws the plane outward.
  return out.sort((a, b) => a.d - b.d)
})

// A tick where every line crosses an axis, inside the frame.
const ticks = computed(() => {
  const o = origin.value
  const out: { x: number; y: number; v: boolean }[] = []
  for (const l of lines.value) {
    if (l.x1 === l.x2 && l.x1 >= 0 && l.x1 <= props.w) out.push({ x: l.x1, y: o.y, v: true })
    if (l.y1 === l.y2 && l.y1 >= 0 && l.y1 <= props.h) out.push({ x: o.x, y: l.y1, v: false })
  }
  return out
})
</script>

<template>
  <g class="plane" aria-hidden="true">
    <line v-for="(l, i) in lines" :key="i" class="plane-line" :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2" />
    <line class="plane-axis" :x1="-bleed" :y1="origin.y" :x2="w + bleed" :y2="origin.y" />
    <line class="plane-axis" :x1="origin.x" :y1="-bleed" :x2="origin.x" :y2="h + bleed" />
    <g class="plane-ticks">
      <line v-for="(t, i) in ticks" :key="i" :x1="t.v ? t.x : t.x - 3" :x2="t.v ? t.x : t.x + 3" :y1="t.v ? t.y - 3 : t.y" :y2="t.v ? t.y + 3 : t.y" />
    </g>
  </g>
</template>

<style scoped>
.plane-line {
  stroke: var(--hmz-grid);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.plane-axis {
  stroke: color-mix(in srgb, var(--hmz-lane-1) 30%, transparent);
  stroke-width: 1.2;
  vector-effect: non-scaling-stroke;
}

.plane-ticks line {
  stroke: color-mix(in srgb, var(--hmz-lane-1) 40%, transparent);
  stroke-width: 1;
}
</style>
