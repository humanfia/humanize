<script setup lang="ts">
// A filter over the reference table in its slot. The table is ordinary markdown, rendered on
// the server like any other, so the site search, a search engine and a reader with scripts off
// all get every row; this only hides rows in the browser, and only once it is mounted.
//
// Two ways to narrow, which combine: words typed into the box, each of which a row must
// contain somewhere, and a chip, which a row's first cell must be -- or begin with, followed
// by a space, so that `/settings` takes in `/settings accounts` and `/flow` would leave a `/flowchart` out.
//
// Each row may carry an anchor. A link to one whose row is filtered away clears the filter
// first, so the page has somewhere to scroll to.
//
// It moves only to say what the filter did: the count runs to its new number and a hairline
// under the box fills to the share of rows left; a row that comes back eases in; the chip that
// is on is marked by one pill that slides from chip to chip; and every word typed is lit where
// it was found, with the CSS Custom Highlight API, so the table's own markup is never touched.
// Under reduced motion all of it simply is where it ends up.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { motion } from '../../motion/gsap'

// Every filter on a page lights its finds under one highlight, so each keeps its own ranges here.
const HIT = 'hmz-ref-hit'
const finds = new Map<symbol, Range[]>()
function light() {
  if (typeof CSS === 'undefined' || !('highlights' in CSS)) return
  const all = [...finds.values()].flat()
  if (all.length) CSS.highlights.set(HIT, new Highlight(...all))
  else CSS.highlights.delete(HIT)
}

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
/** The count as drawn: it runs to `shown` rather than jumping. */
const drawn = ref(0)
const share = computed(() => (total.value ? shown.value / total.value : 1))
const me = Symbol('ref-filter')
let calm = false
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
  const found: Range[] = []
  for (const one of rows) {
    const inScope = !scope || one.where === scope || one.where.startsWith(`${scope} `)
    const hit = inScope && words.every((word) => one.said.includes(word))
    const back = hit && one.row.classList.contains('ref-gone')
    one.row.classList.toggle('ref-gone', !hit)
    if (back && !calm) {
      // Restarted, so a row that comes and goes as a word is typed eases in each time.
      one.row.classList.remove('ref-in')
      void one.row.offsetWidth
      one.row.classList.add('ref-in')
    }
    if (hit) {
      count += 1
      if (words.length) found.push(...ranges(one.row, words))
    }
  }
  finds.set(me, found)
  light()
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

/** Where each word is found in a row's text, as ranges for the highlight. */
function ranges(row: HTMLElement, words: string[]): Range[] {
  const out: Range[] = []
  const walk = document.createTreeWalker(row, NodeFilter.SHOW_TEXT)
  for (let node = walk.nextNode(); node; node = walk.nextNode()) {
    const text = (node.textContent ?? '').toLowerCase()
    for (const word of words) {
      for (let at = text.indexOf(word); at >= 0; at = text.indexOf(word, at + word.length)) {
        const range = new Range()
        range.setStart(node, at)
        range.setEnd(node, at + word.length)
        out.push(range)
      }
    }
  }
  return out
}

// The count runs to its new number.
watch(shown, (to) => {
  if (calm) {
    drawn.value = to
    return
  }
  const box = { n: drawn.value }
  motion().to(box, { n: to, duration: 0.45, ease: 'cine.out', onUpdate: () => (drawn.value = Math.round(box.n)) })
})

// One pill marks the chip that is on, and slides to the next one picked.
const chipsEl = ref<HTMLElement | null>(null)
const pill = ref<{ x: number; y: number; w: number; h: number } | null>(null)
function place() {
  const box = chipsEl.value
  const on = box?.querySelector<HTMLElement>('button.on')
  pill.value = on ? { x: on.offsetLeft, y: on.offsetTop, w: on.offsetWidth, h: on.offsetHeight } : null
}
watch(chip, () => void nextTick(place))

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
  drawn.value = rows.length
  calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ready.value = true
  window.addEventListener('hashchange', reveal)
  window.addEventListener('resize', place)
})

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', reveal)
  window.removeEventListener('resize', place)
  finds.delete(me)
  light()
})

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
      <!-- What is drawn runs to its number; what is read out is only the number it lands on. -->
      <span v-if="ready" class="count" aria-hidden="true">
        {{ query || chip ? `${drawn} of ${total}` : `${total} rows` }}
      </span>
      <span v-if="ready" class="sr" aria-live="polite">
        {{ query || chip ? `${shown} of ${total}` : `${total} rows` }}
      </span>
      <span v-if="ready" class="share" aria-hidden="true"><span :style="{ transform: `scaleX(${share})` }" /></span>
    </div>
    <div
      v-if="props.chips?.length"
      ref="chipsEl"
      class="chips"
      role="group"
      :aria-label="`${props.label}: where`"
    >
      <span
        class="pill"
        :class="{ shown: pill }"
        aria-hidden="true"
        :style="pill ? { transform: `translate(${pill.x}px, ${pill.y}px)`, width: `${pill.w}px`, height: `${pill.h}px` } : undefined"
      />
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
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
}

/* The share of rows the filter leaves, as a hairline under the box. */
.share {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: -1px;
  height: 2px;
  overflow: hidden;
  border-radius: 1px;
  pointer-events: none;
}

.share span {
  display: block;
  height: 100%;
  transform-origin: left center;
  background: linear-gradient(90deg, var(--hmz-lane-1), var(--hmz-accent));
  opacity: 0.8;
  transition: transform 0.45s cubic-bezier(0.16, 1, 0.3, 1);
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
  transition: border-color 0.2s, box-shadow 0.25s;
}

.box:focus-within {
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 0 0 3px var(--vp-c-brand-soft);
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
  position: relative;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

/* The one pill under whichever chip is on: it slides there rather than appearing. */
.pill {
  position: absolute;
  top: 0;
  left: 0;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  opacity: 0;
  pointer-events: none;
  transition:
    transform 0.4s cubic-bezier(0.7, 0, 0.2, 1),
    width 0.4s cubic-bezier(0.7, 0, 0.2, 1),
    opacity 0.2s;
}

.pill.shown {
  opacity: 1;
}

.chips button {
  position: relative;
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
  border-color: transparent;
  background: transparent;
  color: var(--vp-c-brand-1);
}

.ref-filter :deep(.ref-gone) {
  display: none;
}

.ref-filter :deep(.ref-in) {
  animation: ref-in 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes ref-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
}

.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
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
  .chips button,
  .pill,
  .share span {
    transition: none;
  }

  .ref-filter :deep(.ref-in) {
    animation: none;
  }
}
</style>
