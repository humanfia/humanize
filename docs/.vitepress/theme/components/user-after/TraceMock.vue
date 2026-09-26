<script setup lang="ts">
// A trace as Perfetto lays it out, drawn still: a process per agent of the run, a track per row
// of its sessions, a slice per thing it did -- and, for a profiled run, a process per program
// its turns started. The names are the ones `hmz.runtime.tracing.chrome` writes:
// `<role> · <n> sessions`, `main`, `subagent · <kind>` for a row of one kind, and
// `<program> · <pid>`.
import { computed } from 'vue'

const props = defineProps<{ profiled?: boolean }>()

interface Slice {
  at: number
  width: number
  label?: string
}

interface Row {
  process?: string
  track: string
  lane: number
  slices: Slice[]
}

const AGENTS: Row[] = [
  {
    process: 'builder · 4 sessions',
    track: 'main',
    lane: 1,
    slices: [
      { at: 0, width: 8, label: 'Read' },
      { at: 9, width: 2 },
      { at: 12, width: 20, label: 'Bash · pytest' },
      { at: 33, width: 5 },
      { at: 45, width: 12, label: 'Edit' },
      { at: 72, width: 3 },
      { at: 76, width: 14, label: 'Bash' },
    ],
  },
  {
    track: 'subagent · explore',
    lane: 2,
    slices: [{ at: 40, width: 22, label: 'Grep, Read' }],
  },
  {
    process: 'reviewer · 2 sessions',
    track: 'main',
    lane: 3,
    slices: [
      { at: 58, width: 10, label: 'Read' },
      { at: 90, width: 10, label: 'says' },
    ],
  },
]

const PROGRAM: Row = {
  process: 'pytest · 41207',
  track: 'main',
  lane: 4,
  slices: [{ at: 12, width: 20, label: 'pytest -q' }],
}

const rows = computed(() => (props.profiled ? [AGENTS[0], PROGRAM] : AGENTS))
</script>

<template>
  <figure class="trace hmz-panel">
    <div class="grid">
      <template v-for="(row, i) in rows" :key="i">
        <div v-if="row.process" class="process">
          <span class="kind">{{ row === PROGRAM ? 'program' : 'agent' }}</span>
          {{ row.process }}
        </div>
        <div class="track">{{ row.track }}</div>
        <div class="lane" :style="{ '--c': `var(--hmz-lane-${row.lane})` }">
          <span
            v-for="(one, j) in row.slices"
            :key="j"
            class="slice"
            :style="{ left: `${one.at}%`, width: `${one.width}%` }"
            >{{ one.label }}</span
          >
        </div>
      </template>
    </div>
    <figcaption>Drawn for this page, in the layout Perfetto gives a trace.</figcaption>
  </figure>
</template>

<style scoped>
.trace {
  margin: 16px 0;
  padding: 14px 16px 10px;
}

.grid {
  display: grid;
  grid-template-columns: minmax(6.5em, max-content) 1fr;
  gap: 4px 12px;
  align-items: center;
}

.process {
  grid-column: 1 / -1;
  margin-top: 6px;
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}

.process:first-child {
  margin-top: 0;
}

.kind {
  margin-right: 6px;
  color: var(--vp-c-text-3);
  font-weight: 400;
}

.track {
  padding-left: 12px;
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  color: var(--vp-c-text-2);
  white-space: nowrap;
}

.lane {
  position: relative;
  height: 22px;
  border-radius: 4px;
  background: var(--hmz-grid);
}

.slice {
  position: absolute;
  top: 2px;
  bottom: 2px;
  overflow: hidden;
  padding: 0 4px;
  border-radius: 3px;
  background: var(--c);
  color: #111;
  font-size: 11px;
  line-height: 18px;
  white-space: nowrap;
  text-overflow: clip;
}

figcaption {
  margin-top: 10px;
  color: var(--vp-c-text-3);
  font-size: 12px;
}

@media (max-width: 480px) {
  .grid {
    grid-template-columns: 1fr;
    gap: 2px;
  }

  .track {
    padding-left: 0;
  }
}
</style>
