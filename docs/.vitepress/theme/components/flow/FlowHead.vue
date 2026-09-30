<script setup lang="ts">
// Who a lane is: a disc for an agent, in the colour of what the role is; a ring with a person
// for you; a square with a prompt for a program. Drawn with its centre at the origin.
import type { RoleKind } from '../../flows'
import FlowGlyph from './FlowGlyph.vue'

withDefaults(defineProps<{ kind: RoleKind; name?: string; note?: string; glow?: number; bare?: boolean }>(), {
  name: '',
  note: '',
  glow: 0,
  bare: false,
})
</script>

<template>
  <g class="f-head" :class="`k-${kind}`">
    <circle v-if="glow > 0.01" class="halo" :r="17 + 9 * glow" :opacity="0.28 * glow" />
    <template v-if="kind === 'human'">
      <circle class="ring" r="12.5" />
      <FlowGlyph name="human" :size="15" class="on-ring" />
    </template>
    <template v-else-if="kind === 'program'">
      <rect class="disc" x="-12" y="-12" width="24" height="24" rx="5" />
      <FlowGlyph name="program" :size="15" class="on-disc" />
    </template>
    <template v-else>
      <circle class="disc" r="12.5" />
      <FlowGlyph name="agent" :size="14" fill class="on-disc" />
    </template>
    <template v-if="!bare">
      <text class="name mono" x="21" y="-1">{{ name }}</text>
      <text class="note" x="21" y="12">{{ note }}</text>
    </template>
  </g>
</template>
