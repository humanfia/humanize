<script setup lang="ts">
// The arc back under the lanes: from where a round ends to where the next one starts, with an
// arrowhead at the start it returns to, what repeats, and a comet while it does.
import FlowGlyph from './FlowGlyph.vue'

withDefaults(
  defineProps<{
    d: string
    lit?: string
    tip: { x: number; y: number; a: number; s: number }
    head?: { x: number; y: number; s: number } | null
    said?: string
    at: { x: number; y: number; s: number }
    live?: boolean
    bare?: boolean
  }>(),
  { lit: '', head: null, said: '', live: false, bare: false },
)
</script>

<template>
  <g class="f-loop" :class="{ live }">
    <path class="track" :d="d" />
    <path v-if="lit" class="lit" :d="lit" />
    <path
      class="tip"
      :transform="`translate(${tip.x} ${tip.y}) rotate(${tip.a}) scale(${tip.s})`"
      d="M 0 0 L -9 -4.5 L -9 4.5 Z"
    />
    <g v-if="head" :transform="`translate(${head.x} ${head.y}) scale(${head.s})`">
      <circle class="halo" r="12" />
      <circle class="comet" r="4.6" />
    </g>
    <g v-if="!bare" class="said" :transform="`translate(${at.x} ${at.y}) scale(${at.s})`">
      <rect :x="-(said.length * 5.9 + 34) / 2" y="-9.5" :width="said.length * 5.9 + 34" height="19" rx="9.5" />
      <FlowGlyph name="loop" :x="-(said.length * 5.9) / 2 - 4" :size="11" />
      <text :x="8" y="3.8">{{ said }}</text>
    </g>
  </g>
</template>
