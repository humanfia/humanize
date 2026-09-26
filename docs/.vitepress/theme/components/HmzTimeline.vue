<script setup lang="ts">
// What a trace hands Perfetto: a process per agent, named by its role, a track per row of its
// sessions, a slice per thing it did -- two CLIs on one clock. For a run in a profiled
// directory, the programs those turns ran are drawn the same way underneath, which is what
// the switch shows. A simulation: the run is made up, the shape of the document is not.
import { computed, ref } from 'vue'

type Kind = 'tool' | 'think' | 'say' | 'prog'

interface Slice {
  t0: number
  t1: number
  label: string
  kind: Kind
  args: string
}

interface Row {
  head: string
  cli: string
  sub: string
  lane: number
  slices: Slice[]
  program?: boolean
}

const SPAN = 36

const AGENTS: Row[] = [
  {
    head: 'actor',
    cli: 'claude',
    sub: 'main',
    lane: 1,
    slices: [
      { t0: 0, t1: 1.6, label: 'thinking', kind: 'think', args: 'reasoning · 412 tokens' },
      { t0: 1.6, t1: 2.4, label: 'Read', kind: 'tool', args: 'src/billing.py · 214 lines' },
      { t0: 2.4, t1: 3.1, label: 'Grep', kind: 'tool', args: 'pattern: def charge' },
      { t0: 3.1, t1: 5.2, label: 'thinking', kind: 'think', args: 'reasoning · 1,180 tokens' },
      { t0: 5.2, t1: 6.0, label: 'Edit', kind: 'tool', args: 'src/billing.py · 1 hunk' },
      { t0: 6.0, t1: 14.8, label: 'Bash', kind: 'tool', args: 'pytest -q · exit 1 · 8.8s' },
      { t0: 14.8, t1: 16.0, label: 'thinking', kind: 'think', args: 'reasoning · 903 tokens' },
      { t0: 16.0, t1: 17.2, label: 'Task', kind: 'tool', args: 'explore · where is the retry?' },
      { t0: 17.2, t1: 19.0, label: 'says', kind: 'say', args: 'the failure is in the retry path' },
      { t0: 22.0, t1: 23.4, label: 'Read', kind: 'tool', args: 'tests/test_billing.py' },
      { t0: 23.4, t1: 27.0, label: 'Bash', kind: 'tool', args: 'ruff check --fix · exit 0' },
      { t0: 27.0, t1: 28.2, label: 'says', kind: 'say', args: 'green, and the diff is small' },
    ],
  },
  {
    head: '',
    cli: '',
    sub: 'subagent · explore',
    lane: 1,
    slices: [
      { t0: 16.2, t1: 17.4, label: 'Glob', kind: 'tool', args: '**/retry*.py' },
      { t0: 17.4, t1: 19.8, label: 'Read', kind: 'tool', args: 'src/retry.py' },
      { t0: 19.8, t1: 21.6, label: 'says', kind: 'say', args: 'four call sites, one of them bare' },
    ],
  },
  {
    head: 'reviewer',
    cli: 'codex',
    sub: 'main',
    lane: 2,
    slices: [
      { t0: 19.0, t1: 20.4, label: 'thinking', kind: 'think', args: 'reasoning · 640 tokens' },
      { t0: 20.4, t1: 21.8, label: 'Read', kind: 'tool', args: 'the diff' },
      { t0: 28.4, t1: 31.0, label: 'thinking', kind: 'think', args: 'reasoning · 1,502 tokens' },
      { t0: 31.0, t1: 33.2, label: 'says', kind: 'say', args: 'done: false · notes: name the case' },
    ],
  },
]

const PROGRAMS: Row[] = [
  {
    head: 'pytest · 48219',
    cli: '',
    sub: 'main',
    lane: 4,
    program: true,
    slices: [{ t0: 6.05, t1: 14.72, label: 'pytest -q', kind: 'prog', args: 'started by the actor’s Bash' }],
  },
  {
    head: '',
    cli: '',
    sub: 'thread 48221',
    lane: 4,
    program: true,
    slices: [{ t0: 6.6, t1: 11.9, label: 'python', kind: 'prog', args: 'one of pytest’s workers' }],
  },
  {
    head: '',
    cli: '',
    sub: 'thread 48222',
    lane: 4,
    program: true,
    slices: [{ t0: 6.6, t1: 13.9, label: 'python', kind: 'prog', args: 'the worker the run waited on' }],
  },
  {
    head: 'rg · 48602',
    cli: '',
    sub: 'main',
    lane: 3,
    program: true,
    slices: [{ t0: 16.5, t1: 16.9, label: 'rg', kind: 'prog', args: 'the sub-agent’s Glob' }],
  },
  {
    head: 'ruff · 48533',
    cli: '',
    sub: 'main',
    lane: 5,
    program: true,
    slices: [
      { t0: 23.44, t1: 26.9, label: 'ruff', kind: 'prog', args: 'ruff check --fix · 312 files' },
    ],
  },
]

const profiled = ref(true)
const hovered = ref<Slice | null>(null)

const rows = computed(() => (profiled.value ? [...AGENTS, ...PROGRAMS] : AGENTS))

// Drawn as rows rather than as one scaled drawing, so that a label on the left is beside the
// track it names at every width -- a viewBox would scale the rows out from under them.
const across = (t: number) => `${(t / SPAN) * 100}%`

function show(slice: Slice) {
  hovered.value = slice
}

const caption = computed(() => {
  if (hovered.value) {
    const slice = hovered.value
    return `${slice.label} · ${(slice.t1 - slice.t0).toFixed(2)}s · ${slice.args}`
  }
  const n = rows.value.reduce((sum, row) => sum + row.slices.length, 0)
  return `${rows.value.length} tracks · ${n} slices · point at one`
})
</script>

<template>
  <div class="trace hmz-panel">
    <div class="bar">
      <span class="what">one run · two CLIs · one timeline</span>
      <div class="spacer" />
      <label class="sw">
        <input v-model="profiled" type="checkbox" />
        profiled: the programs the turns ran
      </label>
      <span class="sim">simulation</span>
    </div>

    <div class="board" @mouseleave="hovered = null">
      <div v-for="(row, i) in rows" :key="i" class="row" :class="{ program: row.program }">
        <div class="label">
          <strong v-if="row.head">
            {{ row.head }}<em v-if="row.cli"> · {{ row.cli }}</em>
          </strong>
          <span>{{ row.sub }}</span>
        </div>
        <div class="track">
          <button
            v-for="(slice, j) in row.slices"
            :key="j"
            type="button"
            class="slice"
            :class="slice.kind"
            :aria-label="`${slice.label}, ${slice.args}`"
            :style="{
              left: across(slice.t0),
              width: across(slice.t1 - slice.t0),
              '--tone': `var(--hmz-lane-${row.lane})`,
            }"
            @mouseenter="show(slice)"
            @focus="show(slice)"
            @click="show(slice)"
          >
            {{ slice.t1 - slice.t0 >= 2.8 ? slice.label : '' }}
          </button>
        </div>
      </div>
    </div>

    <p class="caption" aria-live="polite">{{ caption }}</p>

    <p class="verdict">
      <template v-if="!profiled">
        Without the programs, the long <code>Bash</code> is a bar that says only that
        something took eight seconds. A turn is mostly other programs, and a timeline that stops
        at the tool call stops exactly where the time went.
      </template>
      <template v-else>
        Every program sits under the tool call that started it, thread by thread. Now the eight
        seconds have a shape: two workers, and the run waited on the slower one.
      </template>
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 8px 16px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.what {
  font-weight: 650;
  color: var(--vp-c-text-2);
}

.spacer {
  flex: 1;
}

.sim {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.sw {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  color: var(--vp-c-text-2);
}

.sw input {
  accent-color: var(--vp-c-brand-1);
}

.board {
  padding: 12px 16px 0;
}

.row {
  display: flex;
  align-items: stretch;
  gap: 10px;
  min-height: 26px;
}

.label {
  flex: none;
  width: 150px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  line-height: 1.15;
}

.label strong {
  font-size: 11.5px;
  color: var(--vp-c-text-1);
  font-weight: 650;
}

.label em {
  font-style: normal;
  font-weight: 500;
  color: var(--vp-c-text-3);
}

.label span {
  font-size: 10.5px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.row.program .label span {
  color: var(--hmz-warm);
}

/* One line every four seconds, so a slice is read against something. */
.track {
  position: relative;
  flex: 1;
  min-width: 0;
  background-image: linear-gradient(90deg, var(--hmz-grid) 0 1px, transparent 1px 100%);
  background-size: 11.111% 100%;
}

.slice {
  position: absolute;
  top: 50%;
  height: 16px;
  transform: translateY(-50%);
  min-width: 3px;
  border: 0;
  border-radius: 3px;
  padding: 0 5px;
  display: flex;
  align-items: center;
  overflow: hidden;
  white-space: nowrap;
  background: var(--tone);
  color: var(--vp-c-bg);
  font-size: 10px;
  font-family: var(--vp-font-family-mono);
  opacity: 0.86;
  cursor: pointer;
  transition: opacity 0.2s;
}

.slice.think {
  opacity: 0.38;
  color: var(--vp-c-text-1);
}

.slice.prog {
  opacity: 0.72;
}

.slice:hover,
.slice:focus-visible {
  opacity: 1;
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 1px;
}

.caption {
  margin: 0;
  padding: 10px 16px 0;
  min-height: 2.6em;
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-2);
}

.verdict {
  margin: 0;
  padding: 10px 16px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

.verdict code {
  font-size: 12px;
  padding: 1px 5px;
  border-radius: 5px;
  background: var(--vp-c-default-soft);
}

@media (max-width: 760px) {
  .label {
    width: 104px;
  }

  .label strong {
    font-size: 10.5px;
  }
}

/* Too narrow for a word inside a slice: the caption says what one is. */
@media (max-width: 480px) {
  .slice,
  .slice.think {
    color: transparent;
  }
}

@media (prefers-reduced-motion: reduce) {
  .slice {
    transition: none;
  }
}
</style>
