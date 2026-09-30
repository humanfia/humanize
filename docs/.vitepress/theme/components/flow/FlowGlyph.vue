<script setup lang="ts">
// One glyph of the grammar, centred on where it is put, in the colour of what holds it.
import { GLYPH } from './grammar'

withDefaults(defineProps<{ name: string; x?: number; y?: number; size?: number; fill?: boolean }>(), {
  x: 0,
  y: 0,
  size: 16,
  fill: false,
})
</script>

<template>
  <path
    class="f-glyph"
    :class="{ filled: fill }"
    :d="GLYPH[name]"
    :transform="`translate(${x} ${y}) scale(${size / 16})`"
  />
</template>
