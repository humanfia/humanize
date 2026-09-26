<script setup lang="ts">
// The person, asked for a shape. One question per field, in the order the model declares
// them: the description is the question, a Literal or a bool offers its words, a default is
// "-- or `-` for <it>". The answers are checked together once every field has one, and a
// field the model refuses is asked again with pydantic's own message above it. Too many
// refusals, or /afk, and the flow is answered as if nobody were there: the defaults where
// every field has one, OutworlderAway where not. What it mirrors is `HumanSession._filled`
// in `hmz/coganchor/agents/human.py`, the questions as `_show_question` in `hmz/tui/app.py`
// draws them, and `away_answer` in `hmz/runtime/flowing/viewing.py`. One difference: after
// the third refusal `_filled` puts the fields once more and then drops what is typed, which
// is a bug there rather than something to draw; this gives up at the third refusal.
import { computed, nextTick, ref, watch } from 'vue'

interface Field {
  name: string
  kind: 'literal' | 'bool' | 'int'
  type: string
  asks: string
  options: string[]
  fallback: string
  fallbackShown: string
  refuses: string
}

const PROMPT = 'Before the builder starts:'
const TRIES = 3

const BASE: Field[] = [
  {
    name: 'approach',
    kind: 'literal',
    type: 'Literal["fast", "careful"]',
    asks: 'Which way should this be built?',
    options: ['fast', 'careful'],
    fallback: "'careful'",
    fallbackShown: 'careful',
    refuses: "Input should be 'fast' or 'careful'",
  },
  {
    name: 'tests',
    kind: 'bool',
    type: 'bool',
    asks: 'Write tests for it?',
    options: ['yes', 'no'],
    fallback: 'True',
    fallbackShown: 'yes',
    refuses: 'Input should be a valid boolean, unable to interpret input',
  },
  {
    name: 'rounds',
    kind: 'int',
    type: 'int',
    asks: 'How many rounds may it take?',
    options: [],
    fallback: '3',
    fallbackShown: '3',
    refuses: 'Input should be a valid integer, unable to parse string as an integer',
  },
]

const TRUE = ['yes', 'y', 'true', 't', 'on', '1']
const FALSE = ['no', 'n', 'false', 'f', 'off', '0']

// What pydantic makes of what was typed, or null where it refuses it.
function read(field: Field, said: string): string | null {
  const low = said.toLowerCase()
  if (field.kind === 'literal') return field.options.includes(said) ? `'${said}'` : null
  if (field.kind === 'bool') {
    if (TRUE.includes(low)) return 'True'
    if (FALSE.includes(low)) return 'False'
    return null
  }
  // pydantic takes `3`, `+3`, `1_000` and `3.0` for an int, and refuses `3.`, `3.5`, `three`.
  const plain = said.trim()
  if (!/^[+-]?\d+(_\d+)*(\.0+)?$/.test(plain)) return null
  return String(Math.trunc(Number(plain.replaceAll('_', ''))))
}

const everyDefault = ref(false)
const fields = computed(() =>
  BASE.map((one) => ({
    ...one,
    defaulted: everyDefault.value || one.name === 'rounds',
  })),
)

interface Line {
  kind: 'asked' | 'option' | 'hint' | 'you'
  text: string
}

type Phase = 'asking' | 'done' | 'away'

const lines = ref<Line[]>([])
const typed = ref<Record<string, string>>({})
const queue = ref<{ at: number; about: string }[]>([])
const tries = ref(0)
const phase = ref<Phase>('asking')
const why = ref('')
const put = ref('')
const screen = ref<HTMLElement | null>(null)

const current = computed(() => (phase.value === 'asking' ? queue.value[0] : undefined))
const field = computed(() => (current.value ? fields.value[current.value.at] : undefined))

function ask() {
  const next = current.value
  if (!next) return
  const one = fields.value[next.at]
  let hint = one.kind === 'int' ? ' (a number)' : ''
  if (one.defaulted) hint += ` -- or \`-\` for ${one.fallbackShown}`
  const text = next.about ? `${next.about}\n\n${one.asks}${hint}` : `${one.asks}${hint}`
  lines.value.push({ kind: 'asked', text })
  for (const option of one.options) lines.value.push({ kind: 'option', text: option })
  lines.value.push({ kind: 'hint', text: 'type an answer, or /afk to stop being asked' })
}

function start() {
  lines.value = []
  typed.value = {}
  tries.value = 0
  phase.value = 'asking'
  why.value = ''
  put.value = ''
  queue.value = fields.value.map((_, at) => ({ at, about: at === 0 ? PROMPT : '' }))
  ask()
}

function away(because: string) {
  phase.value = 'away'
  why.value = because
  queue.value = []
}

function afk() {
  lines.value.push({ kind: 'you', text: '/afk' })
  away('You went /afk.')
}

function answer(said: string) {
  const next = current.value
  if (!next) return
  const text = said.trim()
  put.value = ''
  lines.value.push({ kind: 'you', text })
  if (text === '/afk') {
    away('You went /afk.')
    return
  }
  const one = fields.value[next.at]
  const copy = { ...typed.value }
  if (text === '-' && one.defaulted) delete copy[one.name]
  else copy[one.name] = text
  typed.value = copy
  queue.value = queue.value.slice(1)
  if (!queue.value.length) check()
  ask()
}

// Every field has an answer: the model reads them all at once.
function check() {
  const wrong = fields.value
    .map((one, at) => ({ one, at }))
    .filter(({ one }) => one.name in typed.value && read(one, typed.value[one.name]) === null)
  if (!wrong.length) {
    phase.value = 'done'
    return
  }
  tries.value += 1
  if (tries.value >= TRIES) {
    away('The model refused the answers three times over.')
    return
  }
  queue.value = wrong.map(({ one, at }) => ({ at, about: one.refuses }))
}

function value(one: (typeof fields.value)[number]): string {
  if (one.name in typed.value) return read(one, typed.value[one.name]) ?? typed.value[one.name]
  return one.defaulted ? one.fallback : ''
}

function shown(one: (typeof fields.value)[number]): string {
  if (phase.value === 'away') return defaultsCover.value ? one.fallback : '—'
  return phase.value === 'done' || one.name in typed.value ? value(one) : 'not yet'
}

const built = computed(() =>
  fields.value
    .map((one) => `${one.name}=${phase.value === 'away' ? one.fallback : value(one)}`)
    .join(', '),
)

const defaultsCover = computed(() => fields.value.every((one) => one.defaulted))

watch(everyDefault, start)

watch(
  () => lines.value.length,
  async () => {
    await nextTick()
    if (screen.value) screen.value.scrollTop = screen.value.scrollHeight
  },
)

start()
</script>

<template>
  <div class="person hmz-panel">
    <div class="bar">
      <span class="sim">simulation</span>
      <span class="what">a flow asks <strong>you</strong> for a <code>Settled</code></span>
      <div class="spacer" />
      <label class="sw">
        <input v-model="everyDefault" type="checkbox" />
        every field has a default
      </label>
      <button class="ctl" type="button" @click="start">restart</button>
      <button
        class="ctl away"
        type="button"
        :disabled="phase !== 'asking'"
        @click="afk"
      >
        go /afk
      </button>
    </div>

    <div class="body">
      <section class="term" aria-label="the prompt, as the interface shows it">
        <div ref="screen" class="screen" aria-live="polite">
          <p v-for="(one, i) in lines" :key="i" :class="one.kind">
            <span v-if="one.kind === 'asked'" class="mark">●</span>
            <span v-else-if="one.kind === 'you'" class="mark you">❯</span>
            <span v-else-if="one.kind === 'option'" class="mark">·</span>
            <span class="text">{{ one.text }}</span>
          </p>
        </div>
        <div v-if="field" class="reply">
          <div v-if="field.options.length" class="offers">
            <button v-for="one in field.options" :key="one" type="button" @click="answer(one)">
              {{ one }}
            </button>
          </div>
          <form class="typed" @submit.prevent="put.trim() && answer(put)">
            <span class="mark you">❯</span>
            <input
              v-model="put"
              type="text"
              :placeholder="field.options.length ? 'or type anything' : 'type an answer'"
              aria-label="your answer"
            />
            <button type="submit" :disabled="!put.trim()">enter</button>
          </form>
        </div>
      </section>

      <aside class="model">
        <header>the shape the flow declared</header>
        <div
          v-for="one in fields"
          :key="one.name"
          class="field"
          :class="{
            got:
              phase === 'done' ||
              (phase === 'away' && defaultsCover) ||
              (phase === 'asking' && one.name in typed),
            now: field?.name === one.name,
          }"
        >
          <div class="head">
            <code>{{ one.name }}</code>
            <span class="type">{{ one.type }}{{ one.defaulted ? ` = ${one.fallback}` : '' }}</span>
          </div>
          <p>{{ one.asks }}</p>
          <span class="value">{{
            shown(one)
          }}</span>
        </div>
        <footer v-if="phase === 'done'" class="landed">
          <strong>Settled({{ built }})</strong>
          <span>The flow reads a field, as it would from a model's answer.</span>
        </footer>
        <footer v-else-if="phase === 'away' && defaultsCover" class="landed">
          <strong>Settled({{ built }})</strong>
          <span>{{ why }} Every field has a default, so the flow gets those, at once.</span>
        </footer>
        <footer v-else-if="phase === 'away'" class="landed bad">
          <strong>OutworlderAway</strong>
          <span>{{ why }} Some field has no default, so there is nothing to answer with: the
            flow has to catch this, or give its fields defaults.</span>
        </footer>
        <footer v-else class="waiting">
          Nothing reaches the flow until every field has an answer the model takes.
        </footer>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.person {
  container-type: inline-size;
}

.bar {
  display: flex;
  align-items: center;
  gap: 8px 10px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12.5px;
  color: var(--vp-c-text-2);
}

.bar code {
  font-size: 12px;
}

.spacer {
  flex: 1;
}

.sw {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
}

.sw input {
  accent-color: var(--vp-c-brand-1);
}

.ctl {
  padding: 4px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  cursor: pointer;
}

.ctl.away {
  border-color: var(--hmz-warm);
  color: var(--hmz-warm);
}

.ctl:disabled {
  opacity: 0.45;
  cursor: default;
}

.sim {
  padding: 1px 8px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 270px);
  gap: 16px;
  padding: 16px;
}

.term {
  display: flex;
  flex-direction: column;
  min-height: 300px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-code-block-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  overflow: hidden;
}

.screen {
  flex: 1;
  max-height: 320px;
  overflow-y: auto;
  padding: 12px 14px;
}

.screen p {
  display: flex;
  gap: 8px;
  margin: 0;
  line-height: 1.6;
  color: var(--vp-c-text-1);
}

.screen .text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.screen .asked {
  margin-top: 8px;
}

.screen .asked:first-child {
  margin-top: 0;
}

.screen .asked .mark {
  color: var(--vp-c-warning-1);
}

.screen .option {
  padding-left: 24px;
  color: var(--vp-c-text-3);
}

.screen .hint {
  padding-left: 12px;
  color: var(--vp-c-text-3);
}

.mark {
  flex: none;
}

.mark.you {
  color: var(--vp-c-brand-1);
}

.screen .you {
  margin-top: 4px;
  color: var(--vp-c-text-1);
  font-weight: 600;
}

.reply {
  padding: 10px 14px 12px;
  border-top: 1px solid var(--vp-c-divider);
}

.offers {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.offers button {
  padding: 4px 14px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 12px;
  font-weight: 600;
  font-family: var(--vp-font-family-mono);
  cursor: pointer;
}

.typed {
  display: flex;
  align-items: center;
  gap: 8px;
}

.typed input {
  flex: 1;
  min-width: 0;
  padding: 5px 8px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 6px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 12.5px;
  font-family: var(--vp-font-family-mono);
}

.typed button {
  padding: 5px 12px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 6px;
  background: transparent;
  color: var(--vp-c-brand-1);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.typed button:disabled {
  opacity: 0.45;
  cursor: default;
}

.model {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  overflow: hidden;
}

.model header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.field {
  padding: 9px 12px;
  border-bottom: 1px dashed var(--vp-c-divider);
  border-left: 3px solid transparent;
}

.field.now {
  border-left-color: var(--vp-c-warning-1);
  background: var(--vp-c-bg-soft);
}

.field .head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.field code {
  font-size: 12.5px;
  color: var(--vp-c-brand-1);
  font-weight: 650;
}

.field .type {
  font-size: 11px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
  overflow-wrap: anywhere;
}

.field p {
  margin: 3px 0 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--vp-c-text-2);
}

.field .value {
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.field.got .value {
  color: var(--hmz-accent);
}

.model footer {
  margin-top: auto;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--vp-c-text-2);
}

.landed strong {
  display: block;
  margin-bottom: 4px;
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  color: var(--hmz-accent);
  overflow-wrap: anywhere;
}

.landed.bad strong {
  color: var(--hmz-warm);
}

.waiting {
  color: var(--vp-c-text-3);
}

@container (max-width: 580px) {
  .body {
    grid-template-columns: minmax(0, 1fr);
  }

  .term {
    min-height: 0;
  }

  .screen {
    max-height: 260px;
  }
}
</style>
