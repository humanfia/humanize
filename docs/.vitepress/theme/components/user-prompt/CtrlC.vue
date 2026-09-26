<script setup lang="ts">
// What the next ctrl+c does, played. The ladder, the three-second window, the lines the
// interface prints and the keys its status line offers are the ones `action_interrupt`,
// `action_stop` and `_keys` in src/hmz/tui/app.py have. The flow itself is a simulation:
// nothing here runs, and the left of the status line is simplified.
import { computed, onUnmounted, ref } from 'vue'

type Phase = 'idle' | 'running' | 'stopping' | 'closed'
type Kind = 'you' | 'agent' | 'note' | 'error'

interface Line {
  id: number
  text: string
  kind: Kind
}

const AGAIN = 3000 // ms: a second press later than this is a first press again
const TASK = 'fix the flaky test'
const HALF = 'and keep the old'

const phase = ref<Phase>('running')
const typed = ref('')
const presses = ref(0)
const lines = ref<Line[]>([])
const said = ref('')
let pressedAt = 0
let counter = 0
let window_: ReturnType<typeof setTimeout> | undefined

function put(text: string, kind: Kind) {
  lines.value = [...lines.value, { id: (counter += 1), text, kind }].slice(-6)
}

function begin() {
  lines.value = []
  put(`$ralph_loop ${TASK}`, 'you')
  put('coder  Read tests/test_pay.py', 'agent')
  put('coder  Bash pytest -q tests/test_pay.py', 'agent')
  phase.value = 'running'
}

function arm() {
  if (window_ !== undefined) clearTimeout(window_)
  // Where the interface forgets an unfinished gesture: the next redraw after the window.
  window_ = setTimeout(() => {
    presses.value = 0
    window_ = undefined
    said.value = 'Three seconds passed without another press, so the next one starts over.'
  }, AGAIN)
}

function disarm() {
  presses.value = 0
  if (window_ !== undefined) clearTimeout(window_)
  window_ = undefined
}

function stopFlow() {
  put('— stopping the flow —', 'note')
  phase.value = 'stopping'
}

function press() {
  if (phase.value === 'closed') return
  if (typed.value) {
    typed.value = ''
    disarm()
    said.value = 'Something was typed, so the press cleared the line and counts for nothing else.'
    return
  }
  const now = Date.now()
  presses.value = presses.value && now - pressedAt < AGAIN ? presses.value + 1 : 1
  pressedAt = now
  if (phase.value === 'running') {
    if (presses.value < 2) {
      arm()
      put('— press ctrl+c again to stop the flow —', 'note')
      said.value = 'Nothing has stopped yet. The next press, within 3 seconds, stops the flow.'
      return
    }
    disarm()
    stopFlow()
    said.value =
      'The flow is stopping: the turn is cut off and the flow winds down in its own time. ' +
      'One more press does not wait for it.'
    return
  }
  if (phase.value === 'stopping') {
    disarm()
    put('— closing 1 conversation(s) under their turns —', 'note')
    phase.value = 'idle'
    said.value =
      'The third press closed the agent still in its turn. Nothing is running now; ' +
      '/resume works again.'
    return
  }
  if (presses.value > 1) {
    disarm()
    phase.value = 'closed'
    said.value = 'Nothing was running, so the second press quit hmz.'
    return
  }
  arm()
  put('— press ctrl+c again to leave —', 'note')
  said.value = 'Nothing is running, so the next press, within 3 seconds, quits hmz.'
}

function type() {
  typed.value = phase.value === 'running' ? HALF : TASK
  said.value = 'A half-typed line: the next ctrl+c clears it rather than anything else.'
}

function slashStop() {
  typed.value = ''
  put('/stop', 'you')
  if (phase.value === 'running') {
    stopFlow()
    said.value = '/stop is typed out on purpose, so it stops the flow at once.'
  } else if (phase.value === 'stopping') {
    put('hmz: the flow is already stopping: it is closing out the turn it was in', 'error')
    said.value = 'A second /stop does not hurry it. A ctrl+c does.'
  } else {
    put('hmz: no flow is running, so there is nothing to stop', 'error')
    said.value = '/stop says so when there is nothing to stop. It never quits.'
  }
  disarm()
}

function unwound() {
  phase.value = 'idle'
  said.value = 'The flow finished winding down by itself. Nothing is running.'
}

function start() {
  // Starting a flow leaves an unfinished ctrl+c standing, as the interface does: a press
  // within the window after this one is its second.
  typed.value = ''
  begin()
  said.value = 'A flow is running again.'
}

function reopen() {
  lines.value = []
  typed.value = ''
  disarm()
  phase.value = 'idle'
  said.value = 'hmz is open again, with nothing running.'
}

function reset() {
  typed.value = ''
  disarm()
  said.value = ''
  begin()
}

const counting = computed(() => presses.value > 0)

// The keys the status line offers, in the order `_keys` puts them.
const keys = computed(() => {
  const held: string[] = []
  if (typed.value) held.push(phase.value === 'running' ? 'enter say' : 'enter start')
  held.push('/ commands', 'shift+enter newline', 'esc monitor')
  if (typed.value) held.push('ctrl+c clear')
  else if (counting.value)
    held.push(phase.value === 'running' ? 'ctrl+c again to stop' : 'ctrl+c again to exit')
  else if (phase.value === 'running') held.push('ctrl+c stop')
  else if (phase.value === 'stopping') held.push('ctrl+c close them')
  else held.push('ctrl+c exit')
  return held
})

const next = computed(() => keys.value[keys.value.length - 1])

const where = computed(() => {
  if (phase.value === 'running') return 'ralph_loop · coder working'
  if (phase.value === 'stopping') return 'ralph_loop · stopping'
  return 'ralph_loop · ~/code/app'
})

begin()

onUnmounted(() => {
  if (window_ !== undefined) clearTimeout(window_)
})
</script>

<template>
  <figure class="up-ctrlc">
    <figcaption>
      <span class="title">What the next <kbd>ctrl+c</kbd> does</span>
      <span class="tag">a simulation: nothing runs</span>
    </figcaption>

    <div class="screen" :class="{ closed: phase === 'closed' }">
      <template v-if="phase !== 'closed'">
        <div class="transcript" aria-live="polite">
          <div v-for="one in lines" :key="one.id" class="line" :class="one.kind">
            <span v-if="one.kind === 'you'" class="mark">❯</span>
            <span v-else-if="one.kind === 'agent'" class="mark dot">●</span>
            <span>{{ one.text }}</span>
          </div>
        </div>
        <div class="rule" />
        <div class="prompt"><span class="caret">❯</span> {{ typed }}<span class="cursor" /></div>
        <div class="rule" />
        <div class="status">
          <span class="left">
            <span class="dot" :class="phase">{{ phase === 'idle' ? '◉' : '·|·' }}</span>
            {{ where }}
          </span>
          <span class="keys">
            <template v-for="(key, at) in keys" :key="key">
              <span v-if="at" class="sep"> · </span>
              <span :class="{ next: key === next }">{{ key }}</span>
            </template>
          </span>
        </div>
      </template>
      <div v-else class="shell">
        <span class="d">$</span> <span class="cursor" />
        <span class="gone">hmz has quit</span>
      </div>
    </div>

    <div class="controls">
      <button type="button" class="press" :disabled="phase === 'closed'" @click="press">
        <kbd>ctrl+c</kbd>
      </button>
      <button type="button" :disabled="phase === 'closed' || !!typed" @click="type">
        type something
      </button>
      <button type="button" :disabled="phase === 'closed'" @click="slashStop">send /stop</button>
      <button v-if="phase === 'stopping'" type="button" @click="unwound">
        let it finish winding down
      </button>
      <button v-if="phase === 'idle'" type="button" @click="start">start a flow</button>
      <button v-if="phase === 'closed'" type="button" @click="reopen">run hmz again</button>
      <button type="button" class="ghost" @click="reset">start over</button>
    </div>

    <p class="said" aria-live="polite">
      {{ said || 'A flow is running. Press ctrl+c and watch the last key on the status line.' }}
    </p>
  </figure>
</template>

<style scoped>
.up-ctrlc {
  margin: 20px 0 28px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-code-block-bg);
  overflow: hidden;
}

figcaption {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--vp-c-divider);
  font-size: 13px;
  color: var(--vp-c-text-2);
}

kbd {
  display: inline-block;
  padding: 0 0.4em;
  border: 1px solid var(--vp-c-divider);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--vp-c-bg-soft);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 1.6;
  color: var(--vp-c-text-1);
  white-space: nowrap;
}

figcaption kbd {
  font-size: 11px;
}

.tag {
  margin-left: auto;
  font-size: 12px;
  font-style: italic;
  color: var(--vp-c-text-3);
}

.screen {
  padding: 12px 14px 8px;
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-1);
  min-height: 212px;
}

.transcript {
  min-height: 120px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.line {
  display: flex;
  gap: 8px;
  overflow-wrap: anywhere;
}

.line.you .mark {
  color: var(--vp-c-text-3);
}

.line.agent .mark {
  color: var(--hmz-accent);
}

.line.agent {
  color: var(--vp-c-text-2);
}

.line.note {
  color: var(--vp-c-text-3);
}

.line.error {
  color: var(--vp-c-danger-1);
}

.rule {
  height: 0;
  margin: 4px 0;
  border-top: 1px solid var(--vp-c-divider);
}

.prompt {
  min-height: 1.6em;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.caret {
  color: var(--vp-c-text-3);
}

.cursor {
  display: inline-block;
  width: 0.6em;
  height: 1.1em;
  margin-left: 1px;
  vertical-align: text-bottom;
  background: var(--vp-c-text-2);
}

.status {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 2px 16px;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.status .dot {
  color: var(--hmz-accent-2);
}

.status .dot.idle {
  color: var(--hmz-accent);
}

.keys {
  text-align: right;
}

.keys .next {
  color: var(--hmz-accent-2);
  font-weight: 700;
}

.shell {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 190px;
  align-content: flex-start;
}

.shell .d {
  color: var(--vp-c-text-3);
}

.gone {
  margin-left: auto;
  font-family: var(--vp-font-family-base);
  font-size: 13px;
  font-style: italic;
  color: var(--vp-c-text-3);
}

.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
}

button {
  padding: 4px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 6px;
  background: var(--vp-c-bg);
  font-size: 13px;
  color: var(--vp-c-text-1);
  cursor: pointer;
}

button:hover:not(:disabled) {
  border-color: var(--hmz-accent-2);
}

button:disabled {
  opacity: 0.45;
  cursor: default;
}

button.press {
  border-color: var(--hmz-accent-2);
}

button.press kbd {
  font-size: 12px;
}

button.ghost {
  margin-left: auto;
  border-color: transparent;
  background: none;
  color: var(--vp-c-text-2);
}

.said {
  margin: 0;
  padding: 10px 14px 12px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--vp-c-text-2);
  border-top: 1px solid var(--vp-c-divider);
}

@media (max-width: 640px) {
  .screen {
    font-size: 12px;
  }

  .status {
    font-size: 11px;
  }

  .keys {
    text-align: left;
  }
}
</style>
