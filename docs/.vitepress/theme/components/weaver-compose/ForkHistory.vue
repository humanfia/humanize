<script setup lang="ts">
// Which conversations know which turns once a session is forked. A simulation of the rules
// `agent.fork(session, env=...)` keeps (src/hmz/runtime/flowing/harnesses.py and
// src/hmz/coganchor/agents/base.py): a fork is cut at its own first turn and carries every
// turn its parent had by then; that first turn raises SessionError if the parent has taken a
// turn since the fork was asked for; and a session that has taken no turn has nothing to fork.
import { computed, ref } from 'vue'

interface Turn {
  n: number
  by: number
}

interface Lane {
  name: string
  parent: number | null
  at: number
  cut: boolean
  carried: Turn[]
  own: Turn[]
  refused: boolean
}

const NAMES = ['session', 'careful', 'quick', 'third', 'fourth']
const MOST = NAMES.length

function start(): Lane[] {
  return [
    {
      name: NAMES[0],
      parent: null,
      at: 0,
      cut: true,
      carried: [],
      own: [{ n: 1, by: 0 }],
      refused: false,
    },
  ]
}

const lanes = ref<Lane[]>(start())
const turns = ref(1)
const said = ref({
  text: 'session has taken one turn. Fork it, then take turns on either side.',
  error: false,
})

const full = computed(() => lanes.value.length >= MOST)

function tell(text: string, error = false) {
  said.value = { text, error }
}

function knows(lane: Lane): string {
  const all = [...lane.carried, ...lane.own].map((one) => one.n)
  return all.length ? all.join(', ') : 'nothing yet'
}

function fork(i: number) {
  const parent = lanes.value[i]
  if (!parent.cut) {
    const from = parent.parent === null ? '' : lanes.value[parent.parent].name
    tell(
      `SessionError: the session to fork has taken no turn to carry on from. ` +
        (stale(parent)
          ? `Fork ${from} again instead.`
          : `Take ${parent.name}'s first turn, then fork it.`),
      true,
    )
    return
  }
  if (full.value) return
  const name = NAMES[lanes.value.length]
  lanes.value.push({
    name,
    parent: i,
    at: parent.own.length,
    cut: false,
    carried: [],
    own: [],
    refused: false,
  })
  tell(
    `${name} = fork(${parent.name}). Nothing is carried yet: ${name} is cut at its own ` +
      `first turn, and takes everything ${parent.name} knows at that moment.`,
  )
}

function run(i: number) {
  const lane = lanes.value[i]
  if (lane.parent !== null && !lane.cut) {
    const parent = lanes.value[lane.parent]
    if (parent.own.length !== lane.at) {
      lane.refused = true
      tell(
        `SessionError: the conversation this one was forked from has taken a turn since; ` +
          `fork it again to branch from where it is now.`,
        true,
      )
      return
    }
    lane.cut = true
    lane.carried = [...parent.carried, ...parent.own]
  }
  turns.value += 1
  lane.own.push({ n: turns.value, by: i })
  const others = lanes.value.filter((one, j) => j !== i && one.cut).map((one) => one.name)
  const left = lanes.value
    .filter((one) => one.parent === i && !one.cut && !one.refused && one.at === lane.own.length - 1)
    .map((one) => one.name)
  tell(
    `Turn ${turns.value} ran on ${lane.name}, which now knows turns ${knows(lane)}.` +
      (others.length ? ` ${listed(others)} never ${others.length === 1 ? 'sees' : 'see'} it.` : '') +
      (left.length
        ? ` ${listed(left)} ${left.length === 1 ? 'has' : 'have'} not taken ` +
          `${left.length === 1 ? 'its' : 'their'} first turn yet, so ` +
          `${left.length === 1 ? 'that turn' : 'those turns'} will be refused.`
        : ''),
  )
}

function listed(names: string[]): string {
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

function reset() {
  lanes.value = start()
  turns.value = 1
  tell('session has taken one turn. Fork it, then take turns on either side.')
}

function stale(lane: Lane): boolean {
  if (lane.parent === null || lane.cut) return false
  return lane.refused || lanes.value[lane.parent].own.length !== lane.at
}

function waiting(lane: Lane): string {
  if (lane.parent === null || lane.cut) return ''
  const parent = lanes.value[lane.parent]
  if (stale(lane)) {
    return `${parent.name} has moved on: this first turn is refused. Fork again.`
  }
  return `waiting for its first turn, which carries what ${parent.name} knows then`
}

function tone(by: number): string {
  return `var(--hmz-lane-${(by % 6) + 1})`
}
</script>

<template>
  <div class="forks hmz-panel">
    <div class="bar">
      <span class="label">Simulation: no CLI is run, the rules are the ones <code>fork</code> keeps</span>
      <button type="button" class="reset" @click="reset">reset</button>
    </div>

    <ol class="lanes">
      <li
        v-for="(lane, i) in lanes"
        :key="lane.name"
        class="lane"
        :class="{ refused: lane.refused }"
        :style="{ '--tone': tone(i) }"
      >
        <div class="who">
          <b>{{ lane.name }}</b>
          <span v-if="lane.parent !== null" class="from">fork of {{ lanes[lane.parent].name }}</span>
        </div>
        <div class="history" :aria-label="`${lane.name} knows turns ${knows(lane)}`">
          <span
            v-for="one in lane.carried"
            :key="`c${one.n}`"
            class="turn carried"
            :style="{ '--tone': tone(one.by) }"
            :title="`turn ${one.n}, carried from ${lanes[one.by].name}`"
          >{{ one.n }}</span>
          <span v-if="lane.carried.length" class="cut" aria-hidden="true" />
          <span
            v-for="one in lane.own"
            :key="`o${one.n}`"
            class="turn"
            :style="{ '--tone': tone(one.by) }"
            :title="`turn ${one.n}, taken on ${lane.name}`"
          >{{ one.n }}</span>
          <span v-if="waiting(lane)" class="waiting" :class="{ bad: stale(lane) }">
            {{ waiting(lane) }}
          </span>
        </div>
        <div class="acts">
          <button type="button" @click="run(i)">run a turn</button>
          <button type="button" :disabled="full" @click="fork(i)">fork</button>
        </div>
      </li>
    </ol>

    <p class="said" :class="{ error: said.error }" aria-live="polite">{{ said.text }}</p>

    <p class="key">
      <span class="turn sample" :style="{ '--tone': tone(1) }">3</span> a turn taken on this
      session ·
      <span class="turn carried sample" :style="{ '--tone': tone(0) }">1</span> a turn carried
      from the session it was forked from
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.label {
  flex: 1;
  min-width: 0;
}

.label code {
  font-size: 11.5px;
}

button {
  padding: 3px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-2);
  font-size: 12px;
  line-height: 1.5;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.2s, color 0.2s;
}

button:hover:not(:disabled) {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}

button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.lanes {
  list-style: none;
  margin: 0;
  padding: 6px 16px;
}

.lanes .lane {
  display: grid;
  grid-template-columns: 7.5rem 1fr auto;
  align-items: center;
  gap: 10px;
  margin: 0;
  padding: 9px 0;
  border-bottom: 1px dashed var(--hmz-panel-border);
}

.lanes .lane:last-child {
  border-bottom: none;
}

.who {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  border-left: 3px solid var(--tone);
  padding-left: 8px;
}

.who b {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  color: var(--vp-c-text-1);
}

.from {
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.refused .who b {
  text-decoration: line-through;
  color: var(--vp-c-text-3);
}

.history {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  min-height: 26px;
}

.turn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 22px;
  padding: 0 5px;
  border: 1.5px solid var(--tone);
  border-radius: 6px;
  background: var(--tone);
  color: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  font-weight: 600;
  animation: pop 0.22s ease-out;
}

.turn.carried {
  background: transparent;
  color: var(--vp-c-text-2);
  border-style: dashed;
}

.turn.sample {
  animation: none;
  vertical-align: middle;
}

.cut {
  width: 2px;
  height: 22px;
  margin: 0 3px;
  border-radius: 1px;
  background: var(--vp-c-text-3);
}

.waiting {
  font-size: 12px;
  font-style: italic;
  color: var(--vp-c-text-3);
}

.waiting.bad {
  font-style: normal;
  color: var(--vp-c-danger-1);
}

.acts {
  display: flex;
  gap: 6px;
}

.said {
  margin: 0;
  padding: 12px 16px;
  border-top: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
  min-height: 3.2em;
}

.said.error {
  color: var(--vp-c-danger-1);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
}

.key {
  margin: 0;
  padding: 8px 16px 12px;
  border-top: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 11.5px;
  line-height: 2;
  color: var(--vp-c-text-3);
}

@keyframes pop {
  from {
    transform: scale(0.6);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .turn {
    animation: none;
  }

  button {
    transition: none;
  }
}

@media (max-width: 640px) {
  .lanes .lane {
    grid-template-columns: 1fr auto;
    grid-template-areas:
      'who acts'
      'history history';
    row-gap: 8px;
  }

  .who {
    grid-area: who;
  }

  .acts {
    grid-area: acts;
  }

  .history {
    grid-area: history;
  }
}
</style>
