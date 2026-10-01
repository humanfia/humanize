<script setup lang="ts">
// One turn, drawn from the origin rightwards, `w` wide and centred on the lane. Its outline
// says who took it -- a capsule for an agent, a bubble for you, a box for a program -- its
// left edge whether a session was opened for it, its glyph what it does, and a second outline
// inside the first that it runs another flow.
import { computed } from 'vue'

import type { Does, RoleKind } from '../../flows'
import FlowGlyph from './FlowGlyph.vue'
import { SIZE } from './grammar'

const props = withDefaults(
  defineProps<{
    kind: RoleKind
    w: number
    session: 'new' | 'held' | 'none'
    does: Does
    state?: 'waiting' | 'running' | 'landed'
    progress?: number
    /** 0 to 1 while the spark of a new session bursts, else below 0. */
    ignite?: number
    pulse?: number
    lines?: string[]
    inside?: number
    calls?: string
    bare?: boolean
    /** How much of its words to show: see `legible`. */
    words?: number
  }>(),
  { state: 'landed', progress: 1, ignite: -1, pulse: 0, lines: () => [], inside: 0, calls: '', bare: false, words: 1 },
)

const h = SIZE.turn
const r = computed(() => (props.kind === 'program' ? 5 : props.kind === 'human' ? 12 : h / 2))
const bubble = computed(() => {
  const { w } = props
  const top = -h / 2
  const rr = r.value
  // A rounded box with a tail under its left end.
  return [
    `M ${rr} ${top} H ${w - rr} A ${rr} ${rr} 0 0 1 ${w} ${top + rr} V ${-top - rr}`,
    `A ${rr} ${rr} 0 0 1 ${w - rr} ${-top} H 28 L 15 ${-top + 8} L 17 ${-top} H ${rr}`,
    `A ${rr} ${rr} 0 0 1 0 ${-top - rr} V ${top + rr} A ${rr} ${rr} 0 0 1 ${rr} ${top} Z`,
  ].join(' ')
})
const glyphX = computed(() => (props.session === 'new' ? 22 : 17))
const textX = computed(() => (glyphX.value + 9 + props.w) / 2)
const ticks = computed(() =>
  Array.from({ length: props.inside }, (_, n) => ({
    x: textX.value + (n - (props.inside - 1) / 2) * 13 - 4.5,
    on: props.state === 'landed' || (props.state === 'running' && props.progress * props.inside >= n + 0.35),
  })),
)
</script>

<template>
  <g class="f-turn" :class="[`k-${kind}`, state, session]">
    <rect
      v-if="state === 'running' && !bare"
      class="aura"
      x="-5"
      :y="-h / 2 - 5"
      :width="w + 10"
      :height="h + 10"
      :rx="r + 5"
      :opacity="0.2 + 0.25 * pulse"
    />
    <path v-if="kind === 'human'" class="shell" :d="bubble" />
    <rect v-else class="shell" x="0" :y="-h / 2" :width="w" :height="h" :rx="r" />
    <rect
      v-if="state === 'running' && progress > 0.01"
      class="fill"
      x="0"
      :y="-h / 2"
      :width="Math.max(2 * r, w * progress)"
      :height="h"
      :rx="r"
    />
    <rect
      v-if="calls"
      class="inner"
      x="4"
      :y="-h / 2 + 4"
      :width="w - 8"
      :height="h - 8"
      :rx="Math.max(2, r - 4)"
    />
    <g v-if="session === 'new'" class="spark">
      <circle v-if="ignite >= 0 && ignite < 1" class="burst" :r="5 + 20 * ignite" :opacity="1 - ignite" />
      <circle class="dot" r="5.2" />
      <circle class="core" r="1.9" />
    </g>
    <FlowGlyph :name="does" :x="glyphX" :y="inside && !bare ? -4 : 0" :size="13" class="does" />
    <g v-if="!bare && words > 0" :opacity="words < 1 ? words : undefined">
      <text
        v-for="(line, n) in lines"
        :key="n"
        class="label"
        :x="textX"
        :y="(lines.length === 1 ? 4 : n * 13 - 2.5) - (inside ? 5 : 0)"
      >
        {{ line }}
      </text>
      <text v-if="calls" class="calls mono" x="8" :y="h / 2 + 13">↳ {{ calls }}</text>
    </g>
    <rect
      v-for="(tick, n) in ticks"
      :key="`i${n}`"
      class="tick"
      :class="{ on: tick.on }"
      :x="tick.x"
      :y="h / 2 - 9"
      width="9"
      height="3"
      rx="1.5"
    />
  </g>
</template>
