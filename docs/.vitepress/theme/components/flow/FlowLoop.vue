<script setup lang="ts">
// The arc back under the lanes: from where a round ends to where the next one starts, with an
// arrowhead at the start it returns to, what repeats, and a comet while it does.
import FlowGlyph from './FlowGlyph.vue'
import { legible } from './grammar'

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
    <g
      v-if="!bare && legible(at.s) > 0"
      class="said"
      :transform="`translate(${at.x} ${at.y}) scale(${at.s})`"
      :opacity="legible(at.s) < 1 ? legible(at.s) : undefined"
    >
      <rect :x="-(said.length * 6.5 + 34) / 2" y="-10" :width="said.length * 6.5 + 34" height="20" rx="10" />
      <FlowGlyph name="loop" :x="-(said.length * 6.5) / 2 - 4" :size="11" />
      <text :x="8" y="4">{{ said }}</text>
    </g>
  </g>
</template>
