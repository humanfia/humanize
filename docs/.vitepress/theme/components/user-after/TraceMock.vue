<script setup lang="ts">
// A trace as Perfetto lays it out: a process per agent of the run, a track per row of its
// sessions, a slice per thing it did -- and, for a profiled run, a process per program its
// turns started. The names are the ones `hmz.runtime.tracing.chrome` writes:
// `<role> · <model>[ · <effort>] · <n> sessions`, `main`, `subagent · <kind>` for a row of one
// kind, and `<program> · <pid>`; a slice is `<tool>: <what it was given>`, `say: …` or `think: …`.
//
// It builds itself once when it is scrolled to: the process headers are written on, their tracks
// unfold, and a playhead sweeps the clock left to right with each slice growing behind it; a
// program's process appears the moment the turn that started it does. Where it comes to rest is
// the still drawing, and under reduced motion that drawing is all there is. A slice can be
// pointed at or focused, to light it and read its name.
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { motion } from '../../motion/gsap'

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
    process: 'builder · claude-opus-5 · 4 sessions',
    track: 'main',
    lane: 1,
    slices: [
      { at: 0, width: 8, label: 'Read' },
      { at: 9, width: 2 },
      { at: 12, width: 20, label: 'Bash: pytest -q' },
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
    process: 'reviewer · gpt-5.6-sol · 2 sessions',
    track: 'main',
    lane: 3,
    slices: [
      { at: 58, width: 10, label: 'Read' },
      { at: 90, width: 10, label: 'say' },
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

// The process a row's track belongs to: its own, or the last one above it.
const owners = computed(() => {
  let last = ''
  return rows.value.map((row) => (last = row.process ?? last))
})

/* ----------------------------------------------------------------------------------------------
   Pointing at a slice.
   ---------------------------------------------------------------------------------------------- */

const figure = ref<HTMLElement | null>(null)
const hot = ref<string | null>(null)
const tip = ref<{ name: string; where: string; x: number; y: number; flip: boolean } | null>(null)

function light(i: number, j: number, event: Event): void {
  const row = rows.value[i]
  const one = row.slices[j]
  hot.value = `${i}-${j}`
  const box = figure.value?.getBoundingClientRect()
  const it = (event.currentTarget as HTMLElement).getBoundingClientRect()
  if (!box || !one.label) {
    tip.value = null
    return
  }
  const x = it.left + it.width / 2 - box.left
  tip.value = {
    name: one.label,
    where: `${owners.value[i].split(' · ')[0]} › ${row.track}`,
    x: Math.min(Math.max(x, 90), box.width - 90),
    y: it.top - box.top,
    flip: it.top - box.top < 52,
  }
}

function dark(): void {
  hot.value = null
  tip.value = null
}

/* ----------------------------------------------------------------------------------------------
   The build.
   ---------------------------------------------------------------------------------------------- */

const grid = ref<HTMLElement | null>(null)
let tl: gsap.core.Timeline | null = null
let io: IntersectionObserver | null = null

// How long the playhead takes to cross the clock, and when it sets off.
const SWEEP = 2.6
const START = 0.9

function all(sel: string): HTMLElement[] {
  return grid.value ? Array.from(grid.value.querySelectorAll<HTMLElement>(sel)) : []
}

function build(): gsap.core.Timeline {
  const g = motion()
  const t = g.timeline({ paused: true })
  const el = grid.value!
  const lanes = all('.lane')
  const head = el.querySelector<HTMLElement>('.head')!
  const link = el.querySelector<HTMLElement>('.link')
  const shut = 'inset(0% 100% 0% 0%)'
  const open = 'inset(0% 0% 0% 0%)'
  const when = (at: number) => START + (at / 100) * SWEEP

  // Where the clock is on screen: the lanes all span the same column.
  const place = () => {
    const box = el.getBoundingClientRect()
    const first = lanes[0].getBoundingClientRect()
    g.set(head, { left: first.left - box.left, x: 0 })
    if (link && lanes[1]) {
      const below = lanes[1].getBoundingClientRect()
      g.set(link, {
        left: first.left - box.left + (PROGRAM.slices[0].at / 100) * first.width,
        top: first.bottom - box.top,
        height: below.top - first.bottom,
      })
    }
    return first.width
  }
  t.call(() => {
    const w = place()
    g.fromTo(head, { x: 0 }, { x: w, duration: SWEEP, ease: 'none', delay: START - 0.01 })
  }, [], 0.01)

  // Its first frame, drawn now: nothing but the empty panel.
  g.set(all('.slice'), { autoAlpha: 0 })

  el.querySelectorAll<HTMLElement>('.row').forEach((row, i) => {
    const program = props.profiled && i === 1
    // A program's process is drawn the moment the turn that started it is.
    const at = program ? when(PROGRAM.slices[0].at) - 0.45 : 0.1 + i * 0.2
    const process = row.querySelector('.process')
    if (process) {
      t.fromTo(process, { clipPath: shut, autoAlpha: 0 }, { clipPath: open, autoAlpha: 1, duration: 0.6, ease: 'cine' }, at)
    }
    t.fromTo(row.querySelector('.track'), { autoAlpha: 0, x: -10 }, { autoAlpha: 1, x: 0, duration: 0.5 }, at + 0.15)
    t.fromTo(
      row.querySelector('.lane'),
      { clipPath: 'inset(50% 0% 50% 0%)', autoAlpha: 0 },
      { clipPath: open, autoAlpha: 1, duration: 0.45, ease: 'cine.out' },
      at + 0.2,
    )
    if (program && link) {
      // The turn's `Bash: pytest -q` and the program it started, tied for a moment.
      t.fromTo(link, { autoAlpha: 1, scaleY: 0 }, { scaleY: 1, duration: 0.35, ease: 'cine.out' }, at + 0.1)
      t.to(link, { autoAlpha: 0, duration: 0.5 }, when(PROGRAM.slices[0].at + PROGRAM.slices[0].width))
    }
  })

  rows.value.forEach((row, i) => {
    const slices = el.querySelectorAll(`.row:nth-child(${i + 1}) .slice`)
    row.slices.forEach((one, j) => {
      const at = when(one.at)
      t.set(slices[j], { autoAlpha: 1, clipPath: shut }, at)
      t.to(slices[j], { clipPath: open, duration: (one.width / 100) * SWEEP, ease: 'none' }, at)
    })
  })

  t.to(head, { autoAlpha: 1, duration: 0.3, ease: 'none' }, START - 0.2)
  t.to(head, { autoAlpha: 0, duration: 0.5, ease: 'none' }, START + SWEEP)
  // At rest it is the still drawing: nothing left behind on any element.
  t.call(() => g.set(all('.process, .track, .lane, .slice'), { clearProps: 'clipPath,opacity,visibility,transform' }), [], '>')
  return t
}

onMounted(async () => {
  await nextTick()
  if (!grid.value || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  tl = build()
  // Held at its first frame until it is scrolled to, then built once.
  io = new IntersectionObserver(
    (entries) => {
      if (!entries.some((one) => one.isIntersecting)) return
      io?.disconnect()
      tl?.play(0)
    },
    { threshold: 0.4 },
  )
  io.observe(grid.value)
})

onBeforeUnmount(() => {
  io?.disconnect()
  tl?.kill()
})
</script>

<template>
  <figure ref="figure" class="trace hmz-panel">
    <div ref="grid" class="grid" :class="{ lit: hot }">
      <div v-for="(row, i) in rows" :key="i" class="row">
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
            :class="{ on: hot === `${i}-${j}` }"
            :style="{ left: `${one.at}%`, width: `${one.width}%` }"
            :tabindex="one.label ? 0 : undefined"
            :aria-label="one.label ? `${one.label}, ${owners[i]}, ${row.track}` : undefined"
            @pointerenter="light(i, j, $event)"
            @pointerleave="dark"
            @focus="light(i, j, $event)"
            @blur="dark"
            >{{ one.label }}</span
          >
        </div>
      </div>
      <span class="head" aria-hidden="true" />
      <span v-if="profiled" class="link" aria-hidden="true" />
    </div>
    <div
      v-if="tip"
      class="tip"
      :class="{ below: tip.flip }"
      :style="{ left: `${tip.x}px`, top: `${tip.y}px` }"
      aria-hidden="true"
    >
      <strong>{{ tip.name }}</strong>
      <span>{{ tip.where }}</span>
    </div>
    <figcaption>Drawn for this page, in the layout Perfetto gives a trace.</figcaption>
  </figure>
</template>

<style scoped>
.trace {
  position: relative;
  margin: 16px 0;
  padding: 14px 16px 10px;
}

.grid {
  position: relative;
  display: grid;
  grid-template-columns: minmax(6.5em, max-content) 1fr;
  gap: 4px 12px;
  align-items: center;
}

/* A row only groups its cells: they sit in the grid as they always have. */
.row {
  display: contents;
}

.process {
  grid-column: 1 / -1;
  margin-top: 6px;
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--vp-c-text-1);
  overflow-wrap: anywhere;
}

.row:first-child .process {
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
  outline: none;
  transition:
    opacity 0.2s,
    box-shadow 0.2s;
}

.grid.lit .slice:not(.on) {
  opacity: 0.38;
}

.slice.on {
  z-index: 1;
  box-shadow:
    0 0 0 2px var(--vp-c-bg),
    0 0 0 3.5px var(--c);
}

/* The playhead: one line down every lane, a notch at its top. */
.head {
  position: absolute;
  top: -4px;
  bottom: -4px;
  left: 0;
  width: 2px;
  margin-left: -1px;
  border-radius: 1px;
  background: var(--hmz-accent);
  box-shadow: 0 0 10px var(--hmz-accent);
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
}

.head::before {
  content: '';
  position: absolute;
  top: -2px;
  left: -4px;
  border: 5px solid transparent;
  border-top-color: var(--hmz-accent);
  border-bottom: 0;
}

/* The tie between a turn's command and the program it started. */
.link {
  position: absolute;
  width: 0;
  border-left: 2px dashed var(--hmz-lane-4);
  transform-origin: 50% 0;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
}

.tip {
  position: absolute;
  z-index: 3;
  display: grid;
  gap: 1px;
  padding: 5px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 6px;
  background: var(--vp-c-bg-elv);
  box-shadow: var(--vp-shadow-2);
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 1.35;
  white-space: nowrap;
  transform: translate(-50%, calc(-100% - 8px));
  pointer-events: none;
  animation: tip-in 0.18s ease-out;
}

.tip.below {
  transform: translate(-50%, 30px);
}

.tip span {
  color: var(--vp-c-text-2);
  font-size: 11px;
}

@keyframes tip-in {
  from {
    opacity: 0;
  }
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

@media (prefers-reduced-motion: reduce) {
  .slice {
    transition: none;
  }

  .tip {
    animation: none;
  }
}
</style>
