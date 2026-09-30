<script setup lang="ts">
// The budget: a bar along the bottom that fills only while a model is working. Drawn from its
// left end at the origin; its name sits to the left, in the lane heads' column.
import FlowGlyph from './FlowGlyph.vue'

withDefaults(defineProps<{ w: number; fill: number; bare?: boolean }>(), { bare: false })
</script>

<template>
  <g class="f-meter o-budget" :class="{ full: fill >= 0.999 }">
    <g v-if="!bare" transform="translate(-150 0)">
      <FlowGlyph name="budget" :x="0" :y="0" :size="14" />
      <text class="name" x="21" y="4">budget</text>
    </g>
    <rect class="trough" x="0" y="-3.5" :width="w" height="7" rx="3.5" />
    <rect class="poured" x="0" y="-3.5" :width="Math.max(7, w * fill)" height="7" rx="3.5" />
    <text v-if="!bare" class="read mono" :x="w" y="19">{{ Math.round(fill * 100) }}% of -b spent</text>
  </g>
</template>
