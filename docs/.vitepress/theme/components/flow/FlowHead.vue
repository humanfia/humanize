<script setup lang="ts">
// Who a lane is: a disc for an agent, in the colour of what the role is; a ring with a person
// for you; a square with a prompt for a program. Drawn with its centre at the origin.
import type { RoleKind } from '../../flows'
import FlowGlyph from './FlowGlyph.vue'

withDefaults(
  defineProps<{
    kind: RoleKind
    name?: string
    note?: string
    glow?: number
    bare?: boolean
    words?: number
    /** Small, over the left end of its lane rather than beside it: for a narrow screen. */
    compact?: boolean
  }>(),
  { compact: false, words: 1, name: '', note: '', glow: 0, bare: false },
)
</script>

<template>
  <g v-if="compact" class="f-head compact" :class="`k-${kind}`" transform="translate(0 -27)">
    <circle v-if="glow > 0.01" class="halo" :r="9 + 5 * glow" :opacity="0.28 * glow" />
    <circle v-if="kind === 'human'" class="ring" r="5.5" />
    <rect v-else-if="kind === 'program'" class="disc" x="-5" y="-5" width="10" height="10" rx="2.5" />
    <circle v-else class="disc" r="5.5" />
    <text v-if="!bare && words > 0" class="name mono" x="11" y="4.5" :opacity="words < 1 ? words : undefined">{{ name }}</text>
  </g>
  <g v-else class="f-head" :class="`k-${kind}`">
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
    <g v-if="!bare && words > 0" :opacity="words < 1 ? words : undefined">
      <text class="name mono" x="21" y="-1">{{ name }}</text>
      <text class="note" x="21" y="13">{{ note }}</text>
    </g>
  </g>
</template>
