<script setup lang="ts">
// A filter over the reference table in its slot. The table is ordinary markdown, rendered on
// the server like any other, so the site search, a search engine and a reader with scripts off
// all get every row; this only hides rows in the browser, and only once it is mounted.
//
// Two ways to narrow, which combine: words typed into the box, each of which a row must
// contain somewhere, and a chip, which a row's first cell must be -- or begin with, followed
// by a space, so that `/flow` takes in `/flow agent` and leaves `/flowverses` out.
//
// Each row may carry an anchor. A link to one whose row is filtered away clears the filter
// first, so the page has somewhere to scroll to.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  // What the box is for, as a screen reader and the placeholder say it.
  label: string
  // Values of the first column worth one click each. The one already on turns off again.
  chips?: string[]
}>()

const root = ref<HTMLElement | null>(null)
const query = ref('')
const chip = ref('')
const shown = ref(0)
const total = ref(0)
// Whether the rows have been counted, which is only ever true in a browser: the server has no
// count to give, and a bar saying `0 rows` over a full table would be wrong.
const ready = ref(false)

interface Row {
  row: HTMLTableRowElement
  said: string
  where: string
}

let rows: Row[] = []
let tables: HTMLTableElement[] = []

function lower(said: string | null | undefined): string {
  return (said ?? '').replace(/\s+/g, ' ').trim().toLowerCase()
}

function apply() {
  const words = lower(query.value).split(' ').filter(Boolean)
  const scope = lower(chip.value)
  let count = 0
  for (const one of rows) {
    const inScope = !scope || one.where === scope || one.where.startsWith(`${scope} `)
    const hit = inScope && words.every((word) => one.said.includes(word))
    one.row.classList.toggle('ref-gone', !hit)
    if (hit) count += 1
  }
  // A table with nothing left in it is a header row over nothing: it goes with its rows.
  for (const table of tables) {
    const kept = Array.from(table.tBodies[0]?.rows ?? [])
    table.classList.toggle(
      'ref-gone',
      kept.every((row) => row.classList.contains('ref-gone')),
    )
  }
  shown.value = count
}

function pick(value: string) {
  chip.value = chip.value === value ? '' : value
}

function clear() {
  query.value = ''
  chip.value = ''
}

// VitePress dispatches `hashchange` for an in-page link and scrolls straight after, so the
// rows are shown again here and now rather than on the next render.
function reveal() {
  const at = root.value
  const id = decodeURIComponent(location.hash.slice(1))
  const target = id ? document.getElementById(id) : null
  if (!at || !target || !at.contains(target) || !target.closest('.ref-gone')) return
  clear()
  apply()
}

onMounted(() => {
  const at = root.value
  if (!at) return
  tables = Array.from(at.querySelectorAll<HTMLTableElement>('table'))
  rows = tables.flatMap((table) =>
    Array.from(table.tBodies[0]?.rows ?? []).map((row) => ({
      row,
      said: lower(row.textContent),
      where: lower(row.cells[0]?.textContent),
    })),
  )
  total.value = rows.length
  shown.value = rows.length
  ready.value = true
  window.addEventListener('hashchange', reveal)
})

onBeforeUnmount(() => window.removeEventListener('hashchange', reveal))

watch([query, chip], apply)
</script>

<template>
  <div ref="root" class="ref-filter">
    <div class="bar">
      <label class="box">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          v-model="query"
          type="search"
          :placeholder="props.label"
          :aria-label="props.label"
          autocomplete="off"
          spellcheck="false"
        />
      </label>
      <span v-if="ready" class="count" aria-live="polite">
        {{ query || chip ? `${shown} of ${total}` : `${total} rows` }}
      </span>
    </div>
    <div
      v-if="props.chips?.length"
      class="chips"
      role="group"
      :aria-label="`${props.label}: where`"
    >
      <button
        v-for="one in props.chips"
        :key="one"
        type="button"
        :class="{ on: chip === one }"
        :aria-pressed="chip === one"
        @click="pick(one)"
      >
        {{ one }}
      </button>
    </div>
    <slot />
    <p v-if="(query || chip) && shown === 0" class="none">
      No row matches.
      <button type="button" @click="clear">Show them all</button>
    </p>
  </div>
</template>

<style scoped>
.ref-filter {
  margin: 16px 0 24px;
}

.bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.box {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 0 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: var(--vp-c-bg-soft);
  transition: border-color 0.2s;
}

.box:focus-within {
  border-color: var(--vp-c-brand-1);
}

.box svg {
  flex: none;
  width: 16px;
  height: 16px;
  fill: none;
  stroke: var(--vp-c-text-3);
  stroke-width: 2;
  stroke-linecap: round;
}

.box input {
  flex: 1;
  min-width: 0;
  height: 38px;
  border: 0;
  background: transparent;
  font-size: 14px;
  color: var(--vp-c-text-1);
  outline: none;
}

.box input::placeholder {
  color: var(--vp-c-text-3);
}

.count {
  flex: none;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--vp-c-text-3);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.chips button {
  padding: 2px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 20px;
  color: var(--vp-c-text-2);
  transition:
    border-color 0.2s,
    color 0.2s;
}

.chips button:hover {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}

.chips button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.ref-filter :deep(.ref-gone) {
  display: none;
}

.none {
  margin: 8px 0 0;
  font-size: 14px;
  color: var(--vp-c-text-3);
}

.none button {
  margin-left: 6px;
  font-size: 14px;
  font-weight: 500;
  color: var(--vp-c-brand-1);
}

/* On a phone a three-column table is a column of words a few letters wide. Each row becomes a
   card instead: the first two cells side by side, whatever follows them underneath. */
@media (max-width: 640px) {
  .ref-filter :deep(thead) {
    display: none;
  }

  /* Every card has all four borders and overlaps the one above by a pixel, so whichever row
     a filter leaves first still has its top edge. */
  .ref-filter :deep(tbody) {
    display: block;
    padding-top: 1px;
  }

  .ref-filter :deep(tr) {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    column-gap: 12px;
    margin-top: -1px;
    padding: 10px 12px;
    border: 1px solid var(--vp-c-divider);
  }

  .ref-filter :deep(td) {
    display: block;
    padding: 2px 0;
    border: 0;
  }

  .ref-filter :deep(td:nth-child(n + 3)) {
    grid-column: 1 / -1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .box,
  .chips button {
    transition: none;
  }
}
</style>
