<script setup lang="ts">
// Two halves of one idea. What a turn under an account is given: that account's credentials,
// none of the variables a backend would take another account from, and the CLI's own sessions,
// settings and skills (`src/hmz/coganchor/providers/`, `Profile.hushes` and `Profile.creds` in
// `src/hmz/coganchor/backends.py`). And what a failed turn does: the tries and waits each kind
// of failure gets are `ANSWERS` in `src/hmz/coganchor/fallbacks.py`, the waits are its
// `waits()`, and the walk is `_falling_back` in `src/hmz/coganchor/agents/base.py`.
import { computed, onUnmounted, ref } from 'vue'

type View = 'runs' | 'fails'

// ------------------------------------------------------------------ what a turn runs as

type Tag = 'yours' | 'account' | 'unset' | 'same'

interface Line {
  what: string
  gets: string
  tag: Tag
}

interface Runs {
  name: string
  kind: string
  lines: Line[]
}

const SAME: Line = {
  what: 'sessions, settings, installed skills',
  gets: 'Claude Code’s own, so traces, cost and skills work as always',
  tag: 'same',
}

const RUNS: Runs[] = [
  {
    name: 'no account',
    kind: 'the CLI as you run it',
    lines: [
      { what: 'credentials', gets: 'whoever claude is signed in as on this machine', tag: 'yours' },
      { what: 'ANTHROPIC_API_KEY in your shell', gets: 'used, as it would be anyway', tag: 'yours' },
      SAME,
    ],
  },
  {
    name: 'claude@work',
    kind: 'a subscription, signed in',
    lines: [
      { what: 'credentials', gets: 'the work sign-in, made by Claude Code’s own login', tag: 'account' },
      { what: 'ANTHROPIC_API_KEY in your shell', gets: 'unset for this turn', tag: 'unset' },
      { what: 'a token refreshed mid-turn', gets: 'written back to the work account, never to yours', tag: 'account' },
      SAME,
    ],
  },
  {
    name: 'claude@key',
    kind: 'an API key',
    lines: [
      { what: 'credentials', gets: 'the key this account holds', tag: 'account' },
      { what: 'ANTHROPIC_API_KEY in your shell', gets: 'replaced by the account’s key', tag: 'account' },
      { what: 'CLAUDE_CODE_OAUTH_TOKEN in your shell', gets: 'unset for this turn', tag: 'unset' },
      SAME,
    ],
  },
  {
    name: 'claude@gateway',
    kind: 'somebody’s endpoint',
    lines: [
      { what: 'credentials', gets: 'the gateway’s URL and token, from the account', tag: 'account' },
      { what: 'ANTHROPIC_API_KEY in your shell', gets: 'unset for this turn', tag: 'unset' },
      { what: 'models on offer', gets: 'what the gateway says it serves', tag: 'account' },
      SAME,
    ],
  },
]

const TAGS: Record<Tag, string> = {
  yours: 'yours',
  account: 'the account’s',
  unset: 'taken away',
  same: 'unchanged',
}

// ------------------------------------------------------------------ when an account fails

type Fault = 'ok' | 'throttled' | 'refused' | 'unlisted' | 'retired' | 'dropped'

interface Answer {
  said: string
  tries: number
  held: boolean
  least: number
  accounts: boolean
  reopen: boolean
  why: string
}

// `ANSWERS` in fallbacks.py, for the kinds drawn here.
const FAULTS: Record<Fault, Answer> = {
  ok: { said: 'answers', tries: 0, held: false, least: 0, accounts: true, reopen: false, why: '' },
  throttled: {
    said: '429 · rate-limited',
    tries: 1,
    held: false,
    least: 30,
    accounts: true,
    reopen: false,
    why: 'a rate limit gets at least one more try, after at least 30 s',
  },
  refused: {
    said: '401 · key refused',
    tries: 0,
    held: true,
    least: 0,
    accounts: true,
    reopen: false,
    why: 'the same key would be refused again, so it is not retried',
  },
  unlisted: {
    said: '403 · model not on this account',
    tries: 0,
    held: true,
    least: 0,
    accounts: true,
    reopen: false,
    why: 'the next account may have it, so it is not retried here',
  },
  retired: {
    said: '404 · no such model',
    tries: 0,
    held: true,
    least: 0,
    accounts: false,
    reopen: false,
    why: 'no account of claude has it, so the rest of the chain is skipped',
  },
  dropped: {
    said: 'connection dropped',
    tries: 1,
    held: false,
    least: 0,
    accounts: true,
    reopen: true,
    why: 'reconnected, and the same conversation picked up again',
  },
}

const CHOICES: Fault[] = ['ok', 'throttled', 'refused', 'unlisted', 'retired', 'dropped']

interface Account {
  name: string
  kind: string
  fault: Fault
}

const ACCOUNTS = ref<Account[]>([
  { name: 'claude@work', kind: 'subscription', fault: 'throttled' },
  { name: 'claude@key', kind: 'API key', fault: 'refused' },
  { name: 'claude@gateway', kind: 'gateway', fault: 'ok' },
])

const PLACE = 'codex/gpt-5.6-sol'
const placeFails = ref(false)

const POLICIES = [
  { name: 'none', about: 'Tries again at once.' },
  { name: 'constant', about: 'The same wait every time: 1 s, 1 s, 1 s.' },
  { name: 'linear', about: 'One second longer each time: 1 s, 2 s, 3 s.' },
  { name: 'exponential', about: 'Twice as long each time: 1 s, 2 s, 4 s, 8 s.' },
  {
    name: 'exponential-jitter',
    about:
      'Exponential, each wait drawn anywhere below it, so agents failing together do not come back together.',
  },
  { name: 'fibonacci', about: 'The Fibonacci sequence: 1 s, 1 s, 2 s, 3 s, 5 s.' },
]

const CEILING = 60

function fib(n: number): number {
  let before = 0
  let held = 1
  for (let i = 0; i < n - 1; i += 1) [before, held] = [held, before + held]
  return held
}

// `waits()` in fallbacks.py, with the jitter given as the top of the band it is drawn from.
function waits(policy: string, attempt: number): number {
  const over = Math.min(Math.max(attempt - 1, 0), 64)
  if (!over || policy === 'none') return 0
  if (policy === 'constant') return 1
  if (policy === 'linear') return Math.min(over, CEILING)
  if (policy === 'fibonacci') return Math.min(fib(over), CEILING)
  return Math.min(2 ** (over - 1), CEILING)
}

const view = ref<View>('runs')
const picked = ref(1)
const policy = ref('exponential-jitter')
const tries = ref(0)

const ladder = computed(() =>
  Array.from({ length: 5 }, (_, i) => ({ attempt: i + 2, seconds: waits(policy.value, i + 2) })),
)
const tallest = computed(() => Math.max(1, ...ladder.value.map((one) => one.seconds)))

// What a wait before one try comes to: the place's own, floored by what the failure asks for.
function waiting(answer: Answer, attempt: number): string {
  const top = waits(policy.value, attempt)
  const floor = answer.least
  if (policy.value === 'exponential-jitter') {
    const high = Math.max(top, floor)
    if (floor >= high) return `waits ${high} s`
    return floor > 0 ? `waits ${floor}–${high} s` : `waits up to ${high} s`
  }
  const seconds = Math.max(top, floor)
  return seconds ? `waits ${seconds} s` : 'tries again at once'
}

type Kind = 'try' | 'wait' | 'why' | 'moved' | 'landed' | 'ended'

interface Beat {
  who: string
  said: string
  kind: Kind
}

function script(): Beat[] {
  const made: Beat[] = []
  let answer = FAULTS.ok
  let skip = false
  for (let which = 0; which < ACCOUNTS.value.length && !skip; which += 1) {
    const account = ACCOUNTS.value[which]
    const failing = FAULTS[account.fault]
    for (let attempt = 1; ; attempt += 1) {
      if (attempt > 1) {
        const floor = answer.least ? `, the least a rate limit waits` : ''
        made.push({ who: account.name, said: `${waiting(answer, attempt)}${floor}`, kind: 'wait' })
      }
      if (account.fault === 'ok') {
        made.push({ who: account.name, said: `try ${attempt} · the turn lands`, kind: 'landed' })
        return made
      }
      made.push({ who: account.name, said: `try ${attempt} · ${failing.said}`, kind: 'try' })
      answer = failing
      const goes = answer.held ? 0 : Math.max(tries.value, answer.tries)
      if (attempt > goes) {
        if (answer.held) made.push({ who: '', said: answer.why, kind: 'why' })
        break
      }
      if (answer.reopen) made.push({ who: '', said: answer.why, kind: 'why' })
    }
    if (!answer.accounts) {
      skip = true
    } else if (which + 1 < ACCOUNTS.value.length) {
      made.push({
        who: '',
        said: `carries on as ${ACCOUNTS.value[which + 1].name}, in the same conversation`,
        kind: 'moved',
      })
    }
  }
  made.push({ who: '', said: `carries on at ${PLACE}, in a new conversation`, kind: 'moved' })
  if (placeFails.value) {
    made.push({ who: PLACE, said: 'try 1 · fails', kind: 'try' })
    made.push({ who: '', said: 'nowhere left to go: the flow sees the turn fail', kind: 'ended' })
  } else {
    made.push({ who: PLACE, said: 'try 1 · the turn lands', kind: 'landed' })
  }
  return made
}

const beats = ref<Beat[]>([])
const shown = ref(0)
const playing = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

function stop() {
  if (timer) clearTimeout(timer)
  timer = undefined
  playing.value = false
}

function play() {
  stop()
  beats.value = script()
  const still =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (still) {
    shown.value = beats.value.length
    return
  }
  shown.value = 0
  playing.value = true
  const next = () => {
    shown.value += 1
    if (shown.value >= beats.value.length) {
      playing.value = false
      return
    }
    const now = beats.value[shown.value - 1]
    timer = setTimeout(next, now.kind === 'wait' ? 1100 : 650)
  }
  next()
}

function reset() {
  stop()
  beats.value = []
  shown.value = 0
}

const visible = computed(() => beats.value.slice(0, shown.value))
const landedOn = computed(
  () => visible.value.find((one) => one.kind === 'landed')?.who ?? '',
)
const current = computed(() => {
  const named = [...visible.value].reverse().find((one) => one.who)
  return named?.who ?? ''
})

onUnmounted(stop)
</script>

<template>
  <div class="accounts hmz-panel">
    <div class="tabs">
      <div class="pick" role="group" aria-label="which half to show">
        <button
          type="button"
          :aria-pressed="view === 'runs'"
          :class="{ on: view === 'runs' }"
          @click="view = 'runs'"
        >
          what a turn runs as
        </button>
        <button
          type="button"
          :aria-pressed="view === 'fails'"
          :class="{ on: view === 'fails' }"
          @click="view = 'fails'"
        >
          when an account fails
        </button>
      </div>
      <span class="sim">simulation</span>
    </div>

    <div v-if="view === 'runs'" class="runs">
      <div class="who" role="group" aria-label="which account the agent runs as">
        <button
          v-for="(one, i) in RUNS"
          :key="one.name"
          type="button"
          :aria-pressed="picked === i"
          :class="{ on: picked === i }"
          @click="picked = i"
        >
          <code>{{ one.name }}</code>
          <span>{{ one.kind }}</span>
        </button>
      </div>

      <div class="card" aria-live="polite">
        <p class="turn">
          a turn of <code>claude</code>, run as <strong>{{ RUNS[picked].name }}</strong>
        </p>
        <div v-for="line in RUNS[picked].lines" :key="line.what" class="line">
          <span class="what">{{ line.what }}</span>
          <span class="gets">{{ line.gets }}</span>
          <span class="tag" :class="line.tag">{{ TAGS[line.tag] }}</span>
        </div>
      </div>
      <p class="note">
        Two agents of one CLI can run as two of these at the same time. A turn under an account
        never reads or writes the sign-in you use yourself.
      </p>
    </div>

    <div v-else class="chain">
      <div class="controls">
        <label>
          <span>tries at this place</span>
          <input v-model.number="tries" type="range" min="0" max="4" step="1" @input="reset" />
          <b>{{ tries }}</b>
        </label>
        <label>
          <span>waits</span>
          <select v-model="policy" @change="reset">
            <option v-for="one in POLICIES" :key="one.name" :value="one.name">
              {{ one.name }}
            </option>
          </select>
        </label>
        <div class="spacer" />
        <button class="go" type="button" :disabled="playing" @click="play">
          {{ playing ? 'running…' : 'take a turn' }}
        </button>
      </div>

      <div class="ladder">
        <div class="bars" aria-hidden="true">
          <div v-for="one in ladder" :key="one.attempt" class="bar">
            <div class="col">
              <span
                class="fill"
                :class="{ jitter: policy === 'exponential-jitter' }"
                :style="{ height: `${(one.seconds / tallest) * 100}%` }"
              />
            </div>
            <span class="tick">{{ one.seconds ? `${one.seconds}s` : '0' }}</span>
          </div>
        </div>
        <p class="about">
          {{ POLICIES.find((one) => one.name === policy)?.about }} Never more than a minute.
        </p>
      </div>

      <div class="rows">
        <div
          v-for="one in ACCOUNTS"
          :key="one.name"
          class="row"
          :class="{ here: current === one.name, landed: landedOn === one.name }"
        >
          <code>{{ one.name }}</code>
          <span class="kind">{{ one.kind }}</span>
          <select
            v-model="one.fault"
            :aria-label="`what ${one.name} does`"
            :class="{ bad: one.fault !== 'ok' }"
            @change="reset"
          >
            <option v-for="fault in CHOICES" :key="fault" :value="fault">
              {{ FAULTS[fault].said }}
            </option>
          </select>
        </div>
        <div class="row place" :class="{ here: current === PLACE, landed: landedOn === PLACE }">
          <code>{{ PLACE }}</code>
          <span class="kind">another place</span>
          <button
            type="button"
            class="flip"
            :class="{ bad: placeFails }"
            @click="placeFails = !placeFails; reset()"
          >
            {{ placeFails ? 'fails' : 'answers' }}
          </button>
        </div>
      </div>

      <ol class="log" aria-live="polite">
        <li v-for="(one, i) in visible" :key="i" :class="one.kind">
          <span class="by">{{ one.who || '↳' }}</span>
          <span>{{ one.said }}</span>
        </li>
        <li v-if="!visible.length" class="idle">
          Set what each account does, then take a turn. Time is compressed.
        </li>
      </ol>
      <p v-if="landedOn && landedOn !== ACCOUNTS[0].name && !playing" class="note">
        The agent stays on <code>{{ landedOn }}</code> for its next turn rather than trying the
        accounts that failed again.
      </p>
    </div>
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.pick {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
}

.pick button {
  padding: 5px 14px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, border-color 0.2s;
}

.pick button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.sim {
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

/* ------------------------------------------------------------------ what a turn runs as */

.who {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 14px 16px 0;
}

.who button {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.who button:hover {
  border-color: var(--vp-c-brand-1);
}

.who button.on {
  border-color: var(--hmz-accent);
  background: var(--vp-c-brand-soft);
}

.who code {
  font-size: 12px;
  font-weight: 650;
  color: var(--vp-c-text-1);
  background: none;
  padding: 0;
}

.who span {
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.card {
  margin: 12px 16px 0;
  padding: 12px 14px 6px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
}

.turn {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.turn strong {
  color: var(--vp-c-text-1);
}

.line {
  display: grid;
  grid-template-columns: minmax(0, 13rem) minmax(0, 1fr) auto;
  gap: 4px 12px;
  align-items: baseline;
  padding: 7px 0;
  border-top: 1px dashed var(--vp-c-divider);
  font-size: 13px;
}

.line .what {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  color: var(--vp-c-text-2);
}

.line .gets {
  color: var(--vp-c-text-1);
}

.tag {
  padding: 1px 9px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 650;
  white-space: nowrap;
}

.tag.yours {
  color: var(--vp-c-text-2);
  background: var(--vp-c-default-soft);
}

.tag.account {
  color: var(--hmz-accent);
  background: color-mix(in srgb, var(--hmz-accent) 14%, transparent);
}

.tag.unset {
  color: var(--hmz-warm);
  background: color-mix(in srgb, var(--hmz-warm) 14%, transparent);
}

.tag.same {
  color: var(--vp-c-text-3);
  border: 1px solid var(--vp-c-divider);
}

/* ------------------------------------------------------------------ when an account fails */

.controls {
  display: flex;
  align-items: center;
  gap: 10px 18px;
  flex-wrap: wrap;
  padding: 12px 16px 0;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.controls label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

select {
  padding: 3px 8px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 12px;
}

.controls input[type='range'] {
  width: 92px;
  accent-color: var(--vp-c-brand-1);
}

.controls b {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
}

.spacer {
  flex: 1;
}

.go {
  padding: 5px 14px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.go:disabled {
  opacity: 0.55;
  cursor: default;
}

.ladder {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 12px 16px 0;
}

.bars {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  flex: none;
}

.bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 26px;
}

.col {
  display: flex;
  align-items: flex-end;
  width: 100%;
  height: 44px;
  border-bottom: 1px solid var(--vp-c-divider);
}

.fill {
  width: 100%;
  min-height: 2px;
  border-radius: 4px 4px 0 0;
  background: var(--vp-c-brand-1);
  transition: height 0.35s ease;
}

.fill.jitter {
  background: linear-gradient(180deg, var(--vp-c-brand-1), transparent);
}

.tick {
  font-size: 10px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.ladder .about {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--vp-c-text-3);
}

.rows {
  padding: 14px 16px 0;
}

.row {
  display: flex;
  align-items: center;
  gap: 8px 12px;
  flex-wrap: wrap;
  padding: 7px 12px;
  margin-bottom: 6px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
  font-size: 12px;
  transition: border-color 0.25s, background 0.25s;
}

.row.place {
  border-style: dashed;
}

.row.here {
  border-color: var(--hmz-warm);
}

.row.landed {
  border-color: var(--hmz-accent);
  background: var(--vp-c-brand-soft);
}

.row code {
  min-width: 8.5rem;
  font-weight: 650;
  color: var(--vp-c-text-1);
  background: none;
  padding: 0;
}

.row .kind {
  flex: 1;
  color: var(--vp-c-text-3);
}

.row select.bad,
.flip.bad {
  color: var(--hmz-warm);
  border-color: var(--hmz-warm);
}

.flip {
  padding: 3px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: var(--vp-c-bg);
  color: var(--hmz-accent);
  font-size: 12px;
  cursor: pointer;
}

.log {
  margin: 8px 16px 0;
  padding: 10px 14px;
  list-style: none;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  line-height: 1.8;
  min-height: 110px;
  color: var(--vp-c-text-2);
}

.log li {
  display: flex;
  gap: 10px;
  margin: 0;
  animation: land 0.3s ease;
}

.log .by {
  flex: none;
  min-width: 8.5rem;
  color: var(--vp-c-text-3);
}

.log .try {
  color: var(--hmz-warm);
}

.log .wait,
.log .why {
  color: var(--vp-c-text-3);
}

.log .why span:last-child {
  font-style: italic;
}

.log .moved {
  color: var(--vp-c-brand-1);
}

.log .landed {
  color: var(--hmz-accent);
  font-weight: 650;
}

.log .ended {
  color: var(--hmz-warm);
  font-weight: 650;
}

.log .idle {
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-base);
  line-height: 1.6;
}

@keyframes land {
  from {
    opacity: 0;
    transform: translateY(3px);
  }
}

.note {
  margin: 0;
  padding: 12px 16px 15px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.runs .note {
  padding-top: 10px;
}

@media (max-width: 780px) {
  .who {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .line {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .line .gets {
    grid-column: 1 / -1;
    grid-row: 2;
  }

  .ladder {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 480px) {
  .log .by {
    min-width: 0;
  }

  .log li {
    flex-direction: column;
    gap: 0;
  }

  .log li.idle {
    flex-direction: row;
  }

  .row code {
    min-width: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .log li {
    animation: none;
  }
}
</style>
