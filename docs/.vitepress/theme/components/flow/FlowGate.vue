<script setup lang="ts">
// The finish: a post at the right of the run, and every way the run ends beside it. The first
// is the one this run reaches; once it has, it lights, in the colour of how it ended -- done,
// gave up, budget, or you -- and bursts. Drawn from the post's top at the origin.
import { computed } from 'vue'

import type { Outcome } from '../../flows'
import FlowGlyph from './FlowGlyph.vue'

const props = withDefaults(
  defineProps<{
    ends: { is: Outcome; said: string }[]
    h: number
    /** 0 before the run ends; then 0 to 1 as the ending lands. */
    fired?: number
    bare?: boolean
    words?: number
  }>(),
  { fired: 0, bare: false, words: 1 },
)

const on = computed(() => props.fired > 0)
const first = computed(() => props.ends[0]?.is ?? 'budget')
</script>

<template>
  <g class="f-gate" :class="[{ on }, `o-${first}`]">
    <line class="post" x1="0" y1="0" x2="0" :y2="h" />
    <path class="flag" d="M 0 0 H 17 L 12.5 6 L 17 12 H 0 Z" />
    <circle v-if="on && fired < 1" class="burst" :cx="22" :cy="34" :r="8 + 34 * fired" :opacity="1 - fired" />
    <g
      v-for="(end, n) in ends"
      :key="n"
      class="end"
      :class="[`o-${end.is}`, { lit: on && n === 0 }]"
      :transform="`translate(10 ${34 + n * 26})`"
    >
      <rect v-if="!bare" class="chip" x="0" y="-10.5" :width="end.said.length * 6.4 + 34" height="21" rx="10.5" />
      <FlowGlyph :name="end.is" :x="13" :size="12" :fill="end.is === 'you'" />
      <text v-if="!bare && words > 0" class="said" x="26" y="4" :opacity="words < 1 ? words : undefined">{{ end.said }}</text>
    </g>
  </g>
</template>
