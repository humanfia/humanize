<script setup lang="ts">
// A workspace: the plate under the lanes that work in it, and its name on a folder tab over its
// top left. `points` is the plate already projected; `m` places the tab.
import FlowGlyph from './FlowGlyph.vue'

withDefaults(defineProps<{ points: string; m: string; name: string; lit?: boolean; bare?: boolean }>(), {
  lit: false,
  bare: false,
})
</script>

<template>
  <g class="f-plate" :class="{ lit }">
    <polygon class="floor" :points="points" />
    <g :transform="m">
      <FlowGlyph name="folder" :x="9" :y="-8" :size="11" class="tab" />
      <text v-if="!bare" class="name" x="19" y="-4.5">{{ name }}</text>
    </g>
  </g>
</template>
