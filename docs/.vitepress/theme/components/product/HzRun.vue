<script setup lang="ts">
// The hero's picture: one flow, two agents, one trace, running.
//
// The command is typed, the lanes open, and the two chasers take turns, as flame_chase runs them:
// each turn's tool calls land on one clock as the playhead crosses them; when the run is over it says so, holds, and starts again. Nothing here
// is a recording -- the slices come from a seeded sequence, so the server and the browser draw
// the same run, and the still frame (on the server, and for a reader who asked for less motion)
// is that run finished.
//
// One number moves: `--now`, set on the root once a frame by a Clock that stops while the
// picture is off screen. Every slice reads it in CSS and grows itself, so a frame is one style
// write rather than a re-render; the few words that change (the typed command, the tallies, the
// clock) are refs that change a few times a second.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Clock, prefersReducedMotion } from './motion'

const COMMAND = 'hmz exec -f flame_chase'

/** flame_chase's two chasers, each as `-a` names it. */
const AGENTS = [
  { who: 'claude/claude-opus-5:high', role: 'first_chaser' },
  { who: 'codex/gpt-5.6-sol:high', role: 'second_chaser' },
]
/** How many turns the run takes; they alternate, first chaser first. */
const TURNS = 4

/** What a slice is. `kind` is only a colour: the model thinking, a read, a write, a run. */
const KINDS = [
  { kind: 'think', label: 'turn', min: 9, max: 17 },
  { kind: 'read', label: 'Read', min: 5, max: 9 },
  { kind: 'write', label: 'Edit', min: 6, max: 11 },
  { kind: 'exec', label: 'Bash', min: 8, max: 15 },
  { kind: 'read', label: 'Grep', min: 4, max: 7 },
  { kind: 'write', label: 'Write', min: 5, max: 9 },
]

const SPAN = 100
/** Seconds: typing, the run, and the hold on the finished trace before it starts again. */
const TYPE = 1.4
const RUN = 11
const HOLD = 3.2

/** A tiny LCG, seeded, so the run is the same run for everybody. */
function rng(seed: number) {
  let state = seed * 1103515245 + 12345
  return () => {
    state = (state * 1103515245 + 12345) & 0x7fffffff
    return state / 0x7fffffff
  }
}

type Slice = { at: number; len: number; kind: string; label: string; tok: number }
const LANES = AGENTS.map((agent) => ({ ...agent, slices: [] as Slice[] }))
{
  // Each turn is a fresh session on one lane; the other waits. A turn opens with the model
  // thinking, and its tool calls follow until its share of the clock is used.
  const next = rng(8)
  const share = SPAN / TURNS
  for (let t = 0; t < TURNS; t++) {
    const end = (t + 1) * share - 1.5
    let at = t * share + 0.5
    let pick = KINDS[0]
    while (true) {
      const len = pick.min + next() * (pick.max - pick.min)
      if (at + len > end) break
      LANES[t % 2].slices.push({ at, len, kind: pick.kind, label: pick.label, tok: Math.round(140 + next() * 2600) })
      at += len + 0.6 + next() * 1.4
      pick = KINDS[1 + Math.floor(next() * (KINDS.length - 1))]
    }
  }
}

const root = ref<HTMLElement | null>(null)
const typed = ref(COMMAND.length)
/** The playhead, rounded, for the words; the slices read the exact value from CSS. */
const tick = ref(SPAN)
const live = ref(false)
let clock: Clock | null = null

onMounted(() => {
  if (prefersReducedMotion() || !root.value) return
  live.value = true
  const el = root.value
  clock = new Clock(el, (t) => {
    const u = t % (TYPE + RUN + HOLD)
    typed.value = Math.min(COMMAND.length, Math.floor((u / TYPE) * COMMAND.length))
    const now = Math.max(0, Math.min(1, (u - TYPE) / RUN)) * SPAN
    el.style.setProperty('--now', now.toFixed(2))
    const rounded = Math.floor(now)
    if (rounded !== tick.value) tick.value = rounded
  })
})
onBeforeUnmount(() => clock?.destroy())

const done = computed(() => tick.value >= SPAN)
const running = computed(() => live.value && typed.value >= COMMAND.length && !done.value)

const tally = (slices: (typeof LANES)[number]['slices']) => {
  const sum = slices.filter((s) => s.at + s.len <= tick.value).reduce((n, s) => n + s.tok, 0)
  return sum >= 1000 ? `${(sum / 1000).toFixed(1)}k` : `${sum}`
}
const turns = computed(() => LANES.reduce((n, l) => n + l.slices.filter((s) => s.at <= tick.value).length, 0))
/** The clock reads as minutes into an eleven-hour run, so the axis is a day's work, not a demo. */
const stamp = computed(() => {
  const minutes = Math.round((tick.value / SPAN) * 660)
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
})
const pct = (v: number) => `${v}%`
</script>

<template>
  <figure
    ref="root"
    class="run"
    :class="{ live, done }"
    aria-label="flame_chase running two agents that take turns on one task: each turn's tool calls land on one shared clock, and the whole run is written down as one trace."
  >
    <div class="run-bar">
      <span class="run-mark" aria-hidden="true" />
      <code class="run-cmd"><span class="run-prompt">$</span>{{ COMMAND.slice(0, typed) }}<i v-if="live && typed < COMMAND.length" class="run-caret" /></code>
      <span class="run-state" :class="{ on: running }">
        <i aria-hidden="true" />{{ done ? 'done' : running ? 'running' : 'starting' }}
      </span>
    </div>

    <div class="run-lanes">
      <div v-for="(lane, i) in LANES" :key="lane.who" class="run-lane" :style="{ '--i': i }">
        <div class="run-who">
          <b>{{ lane.who }}</b>
          <span>{{ lane.role }}</span>
        </div>
        <div class="run-track">
          <span
            v-for="s in lane.slices"
            :key="s.at"
            class="run-slice"
            :class="s.kind"
            :style="{ left: pct(s.at), width: pct(s.len), '--at': s.at, '--len': s.len }"
          >
            <i />
            <em v-if="s.len > 7">{{ s.label }}</em>
          </span>
        </div>
        <span class="run-tok">{{ tally(lane.slices) }}<small> tok</small></span>
      </div>
      <div class="run-head" aria-hidden="true"><span>{{ stamp }}</span></div>
    </div>

    <div class="run-foot">
      <span class="run-key"><i class="think" />turn</span>
      <span class="run-key"><i class="read" />read</span>
      <span class="run-key"><i class="write" />write</span>
      <span class="run-key"><i class="exec" />run</span>
      <span class="run-out">
        {{ turns }} slices · one clock ·
        <b>{{ done ? 'trace.json → Perfetto' : 'writing the trace' }}</b>
      </span>
    </div>
  </figure>
</template>

<style scoped>
.run {
  /* At rest, the run finished. Only the Clock writes it inline: bound in the template, every
     re-render (a few a second) would put it back to SPAN for a frame, and the trace would flash. */
  --now: 100;
  --ink: #141a1f;
  --paper: #e8f0f2;
  --paper-2: #b3c3c8;
  --paper-3: #82939a;
  --accent: #76b900;
  --who: 196px;
  --tok: 64px;
  position: relative;
  margin: 0;
  padding: 18px 20px 16px;
  color: var(--paper);
  background: var(--ink);
  box-shadow: 14px 14px 0 0 var(--hf-cyan);
  font-family: var(--vp-font-family-mono);
  container-type: inline-size;
}
:global(.dark) .run {
  background: var(--hf-night-2);
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--hf-paper) 12%, transparent),
    14px 14px 0 0 var(--hf-cyan);
}

/* ---- the command ----------------------------------------------------------------------- */

.run-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--paper) 14%, transparent);
}
.run-mark {
  flex: none;
  width: 12px;
  height: 12px;
  background: var(--accent);
}
.run-cmd {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 13.5px;
  color: var(--paper);
  background: none;
}
.run-prompt {
  margin-right: 10px;
  color: var(--accent);
}
.run-caret {
  display: inline-block;
  width: 8px;
  height: 15px;
  margin-left: 1px;
  vertical-align: -2px;
  background: var(--paper);
  animation: run-blink 0.9s steps(2) infinite;
}
@keyframes run-blink {
  50% {
    opacity: 0;
  }
}
.run-state {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--paper-3);
}
.run-state i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--paper-3);
}
.run-state.on {
  color: var(--paper);
}
.run-state.on i {
  background: var(--accent);
  animation: run-pulse 1.2s ease-in-out infinite;
}
.done .run-state {
  color: var(--accent);
}
.done .run-state i {
  background: var(--accent);
}
@keyframes run-pulse {
  50% {
    box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 25%, transparent);
  }
}

/* ---- the lanes ------------------------------------------------------------------------- */

.run-lanes {
  position: relative;
  padding: 14px 0 26px;
}
.run-lane {
  display: grid;
  grid-template-columns: var(--who) minmax(0, 1fr) var(--tok);
  align-items: center;
  gap: 12px;
  min-height: 54px;
  border-bottom: 1px dashed color-mix(in srgb, var(--paper) 10%, transparent);
}
.run-who {
  min-width: 0;
}
.run-who b {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
  color: var(--paper);
}
.run-who span {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  color: var(--paper-3);
}
.run-track {
  position: relative;
  height: 26px;
}
.run-slice {
  position: absolute;
  top: 0;
  height: 100%;
}
/* The fill grows from the slice's start as the playhead crosses it. */
.run-slice i {
  position: absolute;
  inset: 0;
  transform-origin: left;
  transform: scaleX(clamp(0, calc((var(--now) - var(--at)) / var(--len)), 1));
  background: var(--fill);
}
.run-slice em {
  position: absolute;
  left: 6px;
  top: 0;
  font-size: 11px;
  font-style: normal;
  line-height: 26px;
  color: var(--on);
  opacity: clamp(0, calc((var(--now) - var(--at)) / var(--len) * 3 - 2), 1);
  pointer-events: none;
}
.run-slice.think {
  --fill: color-mix(in srgb, var(--paper) 22%, transparent);
  --on: var(--paper);
}
.run-slice.read {
  --fill: var(--paper-3);
  --on: var(--ink);
}
.run-slice.write {
  --fill: var(--paper);
  --on: var(--ink);
}
.run-slice.exec {
  --fill: var(--accent);
  --on: var(--ink);
}
.run-tok {
  text-align: right;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--paper);
}
.run-tok small {
  font-size: 11px;
  color: var(--paper-3);
}

/* The playhead: placed against the track column, not the figure. */
.run-head {
  position: absolute;
  top: 6px;
  bottom: 0;
  left: calc(var(--who) + 12px + (100% - var(--who) - var(--tok) - 24px) * var(--now) / 100);
  width: 2px;
  background: var(--accent);
  pointer-events: none;
}
.run-head span {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  padding: 2px 6px;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
  background: var(--accent);
}
.run:not(.live) .run-head {
  display: none;
}

/* ---- the key --------------------------------------------------------------------------- */

.run-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  padding-top: 12px;
  border-top: 1px solid color-mix(in srgb, var(--paper) 14%, transparent);
  font-size: 11px;
  color: var(--paper-3);
}
.run-key {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.run-key i {
  width: 14px;
  height: 8px;
}
.run-key i.think {
  background: color-mix(in srgb, var(--paper) 22%, transparent);
}
.run-key i.read {
  background: var(--paper-3);
}
.run-key i.write {
  background: var(--paper);
}
.run-key i.exec {
  background: var(--accent);
}
.run-out {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}
.run-out b {
  font-weight: 600;
  color: var(--paper);
}
.done .run-out b {
  color: var(--accent);
}

/* ---- narrow ---------------------------------------------------------------------------- */

@container (max-width: 640px) {
  .run {
    --who: 0px;
    --tok: 52px;
  }
  .run-lane {
    grid-template-columns: minmax(0, 1fr) var(--tok);
    grid-template-areas:
      'who who'
      'track tok';
    gap: 6px 10px;
    padding: 8px 0;
  }
  .run-who {
    grid-area: who;
    display: flex;
    gap: 10px;
    align-items: baseline;
  }
  .run-who span {
    margin: 0;
  }
  .run-track {
    grid-area: track;
  }
  .run-tok {
    grid-area: tok;
  }
  .run-head {
    left: calc((100% - var(--tok) - 10px) * var(--now) / 100);
  }
  .run-out {
    margin-left: 0;
    width: 100%;
  }
}

/* A phone: the agent's name alone, and slices too narrow to be named are not. */
@container (max-width: 440px) {
  .run {
    --tok: 46px;
  }
  .run-who span,
  .run-slice em {
    display: none;
  }
  .run-who b {
    font-size: 11.5px;
  }
  .run-lane {
    min-height: 0;
  }
  .run-cmd {
    font-size: 12px;
  }
}
</style>
