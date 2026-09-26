<script setup lang="ts">
// The shapes a flow's loop takes, played beat by beat. What differs from one to the next is
// where the turns go -- a fresh session each round, one session kept, two agents handing to
// each other, several at once -- and what the flow does between them is ordinary code. Each
// shape is the one a flow of the official flowverse really runs; the timings are drawn.
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { withBase } from 'vitepress'

interface Beat {
  lane: number // -1 is the flow itself, between the turns
  text: string
  fresh?: boolean
  shaped?: boolean
  with?: boolean // lands at the same moment as the beat before it
}

interface Shape {
  key: string
  name: string
  about: string
  lanes: string[]
  beats: Beat[]
  carries: string
  seen: { text: string; link: string }
}

const SHAPES: Shape[] = [
  {
    key: 'chat',
    name: 'a conversation',
    about:
      'You say something, the agent answers, and the flow waits for the next thing you say. One session holds the whole conversation.',
    lanes: ['one session, kept'],
    carries: 'everything said so far',
    seen: { text: 'chat', link: '/flows/chat' },
    beats: [
      { lane: -1, text: 'waits for you' },
      { lane: 0, text: 'your message' },
      { lane: -1, text: 'waits again' },
      { lane: 0, text: 'your next one' },
      { lane: -1, text: 'you stop · it ends' },
    ],
  },
  {
    key: 'ralph',
    name: 'ralph',
    about:
      'A fresh session every round: the agent starts from the task and the repository, with nothing of the last round in mind. The repository is the memory.',
    lanes: ['a new session each round'],
    carries: 'nothing in mind: the repository, and which round it is',
    seen: { text: 'ralph_loop', link: '/flows/ralph-loop' },
    beats: [
      { lane: -1, text: 'counts the round' },
      { lane: 0, text: 'the task', fresh: true },
      { lane: -1, text: 'pauses' },
      { lane: 0, text: 'the task', fresh: true },
      { lane: -1, text: 'pauses' },
      { lane: 0, text: 'the task', fresh: true },
    ],
  },
  {
    key: 'stateful',
    name: 'stateful ralph',
    about:
      'One session, opened once and kept, sent the same task every round. The agent remembers every round before this one, for as long as the run lasts.',
    lanes: ['one session, kept'],
    carries: 'the whole conversation so far',
    seen: { text: 'stateful_ralph', link: '/flows/stateful-ralph' },
    beats: [
      { lane: -1, text: 'opens one session' },
      { lane: 0, text: 'the task' },
      { lane: -1, text: 'pauses' },
      { lane: 0, text: 'the task again' },
      { lane: -1, text: 'pauses' },
      { lane: 0, text: 'the task again' },
    ],
  },
  {
    key: 'reviewed',
    name: 'an actor and a reviewer',
    about:
      'Two agents. One works in a session it keeps. The other reads the work in a fresh session each round and answers in a fixed shape, so the flow reads a yes or a no rather than a paragraph.',
    lanes: ['actor · one session, kept', 'reviewer · new each round'],
    carries: 'the actor’s conversation, and the reviewer’s notes',
    seen: { text: 'rlar', link: '/flows/rlar' },
    beats: [
      { lane: 0, text: 'builds' },
      { lane: 1, text: 'reviews → done: no', fresh: true, shaped: true },
      { lane: -1, text: 'passes the notes on' },
      { lane: 0, text: 'fixes it' },
      { lane: 1, text: 'reviews → done: yes', fresh: true, shaped: true },
      { lane: -1, text: 'it ends' },
    ],
  },
  {
    key: 'fanout',
    name: 'a fan-out',
    about:
      'One agent, a session per file, all of them working at once. The flow waits for every one before it moves on.',
    lanes: ['session · parser', 'session · printer', 'session · cli'],
    carries: 'one agent, three conversations',
    seen: { text: 'Many turns at once', link: '/features/concurrency' },
    beats: [
      { lane: -1, text: 'a worktree for each' },
      { lane: 0, text: 'fixes parser', fresh: true },
      { lane: 1, text: 'fixes printer', fresh: true, with: true },
      { lane: 2, text: 'fixes cli', fresh: true, with: true },
      { lane: -1, text: 'waits for all three' },
    ],
  },
]

const shape = ref(1)
const at = ref(0)
const playing = ref(true)
const picked = computed(() => SHAPES[shape.value])

// A column is one moment: most hold one beat, and the fan-out's three turns share one, since
// they are going at the same time.
const columns = computed(() => {
  const held: Beat[][] = []
  for (const one of picked.value.beats) {
    if (one.with && held.length) held[held.length - 1].push(one)
    else held.push([one])
  }
  return held
})

let timer = 0
let idle = false

function next() {
  return at.value + 1 > columns.value.length ? 0 : at.value + 1
}

function beat() {
  if (!playing.value || idle) return
  at.value = next()
}

function pick(i: number) {
  shape.value = i
  at.value = 0
}

function step() {
  playing.value = false
  at.value = next()
}

const root = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    playing.value = false
    at.value = columns.value.length
    return
  }
  observer = new IntersectionObserver((entries) => (idle = !entries[0].isIntersecting), {
    rootMargin: '120px',
  })
  if (root.value) observer.observe(root.value)
  timer = window.setInterval(beat, 1100)
})

onUnmounted(() => {
  window.clearInterval(timer)
  observer?.disconnect()
})

const shown = computed(() => columns.value.slice(0, at.value))
const turnsShown = computed(() => shown.value.flat().filter((one) => one.lane >= 0))
const turns = computed(() => turnsShown.value.length)
const opened = computed(
  () =>
    new Set(turnsShown.value.map((one, i) => (one.fresh ? `${one.lane}:${i}` : `${one.lane}`)))
      .size,
)
const inLane = (column: Beat[], lane: number) => column.find((one) => one.lane === lane)
const tone = (lane: number) => (lane < 0 ? 'var(--vp-c-text-3)' : `var(--hmz-lane-${lane + 1})`)
</script>

<template>
  <div ref="root" class="loops hmz-panel">
    <div class="bar">
      <div class="tabs" role="group" aria-label="which loop">
        <button
          v-for="(one, i) in SHAPES"
          :key="one.key"
          type="button"
          :aria-pressed="shape === i"
          :class="{ on: shape === i }"
          @click="pick(i)"
        >
          {{ one.name }}
        </button>
      </div>
      <div class="spacer" />
      <span class="sim">simulation</span>
      <button class="ctl" type="button" @click="step">step</button>
      <button
        class="ctl"
        type="button"
        :aria-label="playing ? 'pause' : 'play'"
        @click="playing = !playing"
      >
        {{ playing ? '❙❙' : '▶' }}
      </button>
    </div>

    <p class="about">{{ picked.about }}</p>

    <!-- Wide screens: a lane per session, a column per moment. -->
    <div class="stage">
      <div v-for="(lane, i) in picked.lanes" :key="lane" class="lane">
        <span class="tag" :style="{ '--tone': tone(i) }">{{ lane }}</span>
        <div class="slots">
          <template v-for="(column, c) in columns" :key="c">
            <span
              v-if="c < at && inLane(column, i)"
              class="turn"
              :class="{ fresh: inLane(column, i)?.fresh, shaped: inLane(column, i)?.shaped }"
              :style="{ '--tone': tone(i) }"
            >
              {{ inLane(column, i)?.text }}
            </span>
            <span v-else class="hole" />
          </template>
        </div>
      </div>

      <div class="lane code">
        <span class="tag py">the flow, between turns</span>
        <div class="slots">
          <template v-for="(column, c) in columns" :key="c">
            <span v-if="c < at && inLane(column, -1)" class="py-beat">
              {{ inLane(column, -1)?.text }}
            </span>
            <span v-else class="hole" />
          </template>
        </div>
      </div>
    </div>

    <!-- Narrow screens: the same moments, one under another. -->
    <ol class="script">
      <li v-for="(column, c) in shown" :key="c">
        <div v-for="one in column" :key="`${one.lane}-${one.text}`" class="beat">
          <span class="who" :style="{ '--tone': tone(one.lane) }">
            {{ one.lane < 0 ? 'the flow' : picked.lanes[one.lane] }}
          </span>
          <span
            class="what"
            :class="{ turn: one.lane >= 0, fresh: one.fresh, shaped: one.shaped }"
            :style="{ '--tone': tone(one.lane) }"
          >
            {{ one.text }}
          </span>
        </div>
      </li>
      <li v-if="!shown.length">
        <div class="beat"><span /><span class="what">press step, or wait</span></div>
      </li>
    </ol>

    <div class="foot">
      <span><b>{{ turns }}</b> {{ turns === 1 ? 'turn' : 'turns' }}</span>
      <span><b>{{ opened }}</b> {{ opened === 1 ? 'session' : 'sessions' }} opened</span>
      <span class="carries">the next turn starts from: <em>{{ picked.carries }}</em></span>
    </div>
    <div class="legend">
      <span><i class="key fresh" /> a new session</span>
      <span><i class="key shaped" /> an answer in a fixed shape</span>
      <span class="spacer" />
      <a :href="withBase(picked.seen.link)">see it: {{ picked.seen.text }} →</a>
    </div>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.tabs button {
  padding: 4px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.tabs button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
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

.ctl {
  padding: 4px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 11.5px;
  cursor: pointer;
}

.ctl:hover {
  color: var(--vp-c-brand-1);
}

.about {
  margin: 0;
  padding: 12px 16px 0;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

.stage {
  padding: 12px 16px 0;
}

.lane {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
}

.tag {
  flex: none;
  width: 124px;
  font-size: 10.5px;
  line-height: 1.35;
  font-family: var(--vp-font-family-mono);
  color: var(--tone, var(--vp-c-text-3));
}

.tag.py {
  color: var(--vp-c-text-3);
  font-style: italic;
}

.slots {
  display: flex;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.turn,
.py-beat,
.hole {
  flex: 1;
  min-width: 0;
  min-height: 38px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 6px;
  font-size: 11px;
  text-align: center;
  line-height: 1.2;
  animation: land 0.35s ease;
}

.turn {
  background: color-mix(in srgb, var(--tone) 18%, transparent);
  border: 1px solid var(--tone);
  color: var(--vp-c-text-1);
}

.turn.fresh {
  border-style: dashed;
}

.turn.shaped {
  box-shadow: inset 0 -3px 0 0 var(--hmz-accent);
}

.py-beat {
  background: var(--vp-c-default-soft);
  color: var(--vp-c-text-2);
  font-size: 10.5px;
}

.hole {
  background: transparent;
  animation: none;
}

@keyframes land {
  from {
    opacity: 0;
    transform: translateY(5px) scale(0.97);
  }
}

.script {
  display: none;
  list-style: none;
  margin: 0;
  padding: 12px 16px 0;
}

.script li {
  margin: 0 0 6px;
  animation: land 0.35s ease;
}

.script .beat {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.script .beat + .beat {
  margin-top: 4px;
}

.script .who {
  font-size: 10px;
  line-height: 1.3;
  font-family: var(--vp-font-family-mono);
  color: var(--tone);
}

.script .what {
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.35;
  background: var(--vp-c-default-soft);
  color: var(--vp-c-text-2);
}

.script .what.turn {
  display: block;
  min-height: 0;
  text-align: left;
}

.foot {
  display: flex;
  align-items: baseline;
  gap: 18px;
  flex-wrap: wrap;
  padding: 14px 16px 0;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.foot b {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
  font-size: 13px;
}

.carries {
  flex: 1;
  min-width: 220px;
}

.carries em {
  font-style: normal;
  color: var(--vp-c-text-1);
}

.legend {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 10px 16px 14px;
  font-size: 11.5px;
  color: var(--vp-c-text-3);
}

.legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.key {
  display: inline-block;
  width: 18px;
  height: 11px;
  border-radius: 3px;
  border: 1px solid var(--vp-c-text-3);
}

.key.fresh {
  border-style: dashed;
}

.key.shaped {
  box-shadow: inset 0 -3px 0 0 var(--hmz-accent);
}

.legend a {
  font-weight: 600;
  color: var(--vp-c-brand-1);
  text-decoration: none;
}

.legend a:hover {
  text-decoration: underline;
}

@media (max-width: 640px) {
  .stage {
    display: none;
  }

  .script {
    display: block;
  }
}

@media (prefers-reduced-motion: reduce) {
  .turn,
  .py-beat,
  .script li {
    animation: none;
  }
}
</style>
