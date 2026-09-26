<script setup lang="ts">
// Two ways a turn keeps going. Left, the CLI's own goal: the model judges the objective and
// takes the next turn itself. Right, the same thing written by hand: a hook on the end of the
// turn reads TASK.md and sends the agent back while boxes are unticked, told each time how
// often it already has. Which CLIs have a goal is `pursues` in `hmz/coganchor/agents/`, and
// the flow-level `GoalCommandAgentMixin` in `hmz/flows/agents.py`.
import { onMounted, onUnmounted, ref } from 'vue'

interface Turn {
  n: number
  said: string
  end: boolean
}

const HAVE = [
  { name: 'claude', has: true },
  { name: 'codex', has: true },
  { name: 'dsh', has: true },
  { name: 'kimi', has: true },
  { name: 'zcode', has: true },
  { name: 'agy', has: false },
  { name: 'cursor-agent', has: false },
  { name: 'grok', has: false },
  { name: 'mimo', has: false },
  { name: 'opencode', has: false },
  { name: 'pi', has: false },
  { name: 'qwen', has: false },
]

const PURSUED = [
  'runs the suite · three failures',
  'fixes the retry path · one failure left',
  'fixes the fixture · the suite passes',
  'reads its own diff · nothing was stubbed out',
  'judges the objective met · the goal ends',
]

const ITEMS = ['port the parser', 'port the printer', 'port the CLI']
const LIMIT = 5

const root = ref<HTMLElement | null>(null)
let reduced = false
let visible = true
let observer: IntersectionObserver | undefined

const goal = ref<Turn[]>([])
const goalRunning = ref(false)
let goalTimer = 0

function goalTurns(): Turn[] {
  return PURSUED.map((said, i) => ({ n: i + 1, said, end: i === PURSUED.length - 1 }))
}

function pursue() {
  window.clearInterval(goalTimer)
  const turns = goalTurns()
  if (reduced) {
    goal.value = turns
    return
  }
  goal.value = []
  goalRunning.value = true
  goalTimer = window.setInterval(() => {
    if (!visible) return
    const next = turns[goal.value.length]
    if (!next) {
      window.clearInterval(goalTimer)
      goalRunning.value = false
      return
    }
    goal.value = [...goal.value, next]
  }, 800)
}

const boxes = ref([false, false, false])
const stuck = ref(false)
const hook = ref<Turn[]>([])
const hookRunning = ref(false)

// One turn of the agent, then the hook's word on it. Returns whether the turn ended.
function step(again: number): { turn: Turn; ended: boolean } {
  const n = hook.value.length + 1
  const next = boxes.value.findIndex((one) => !one)
  let did = 'does nothing it can tick'
  if (next >= 0 && !(stuck.value && next === ITEMS.length - 1)) {
    boxes.value = boxes.value.map((one, i) => one || i === next)
    did = `ticks “${ITEMS[next]}”`
  } else if (next >= 0) {
    did = `stuck on “${ITEMS[next]}”`
  }
  const left = boxes.value.filter((one) => !one).length
  if (!left) {
    return { turn: { n, said: `${did} · nothing unticked, the turn ends`, end: true }, ended: true }
  }
  if (again >= LIMIT) {
    return {
      turn: { n, said: `${did} · sent back ${LIMIT} times already, the hook lets it end`, end: true },
      ended: true,
    }
  }
  return {
    turn: { n, said: `${did} · ${left} unticked, sent back`, end: false },
    ended: false,
  }
}

let hookTimer = 0

function take() {
  window.clearInterval(hookTimer)
  boxes.value = [false, false, false]
  hook.value = []
  let again = 0
  if (reduced) {
    for (;;) {
      const { turn, ended } = step(again)
      hook.value = [...hook.value, turn]
      if (ended) return
      again += 1
    }
  }
  hookRunning.value = true
  hookTimer = window.setInterval(() => {
    if (!visible) return
    const { turn, ended } = step(again)
    hook.value = [...hook.value, turn]
    again += 1
    if (ended) {
      window.clearInterval(hookTimer)
      hookRunning.value = false
    }
  }, 900)
}

onMounted(() => {
  reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduced || !root.value) return
  observer = new IntersectionObserver((entries) => {
    visible = entries[entries.length - 1].isIntersecting
  })
  observer.observe(root.value)
})

onUnmounted(() => {
  observer?.disconnect()
  window.clearInterval(goalTimer)
  window.clearInterval(hookTimer)
})
</script>

<template>
  <div ref="root" class="goal hmz-panel">
    <div class="top">
      <span>Two ways to keep an agent working until the job is done</span>
      <em class="sim">simulation</em>
    </div>
    <div class="cols">
      <section class="col">
        <header>
          <strong>the model decides</strong>
          <span>a goal</span>
        </header>
        <p class="lede">
          The CLI's own goal feature: a turn that would have ended starts another, until the model
          judges the objective met. The flow gets the last turn's answer.
        </p>
        <p class="objective">“the suite passes and nothing has been stubbed out”</p>
        <button type="button" class="go" :disabled="goalRunning" @click="pursue">
          {{ goalRunning ? 'working…' : 'give it this goal' }}
        </button>
        <ol class="turns" aria-live="polite">
          <li v-for="one in goal" :key="one.n" :class="{ end: one.end }">
            <span class="n">turn {{ one.n }}</span>
            <span>{{ one.said }}</span>
          </li>
        </ol>
        <footer>
          <span class="lab">has a goal</span>
          <span
            v-for="one in HAVE"
            :key="one.name"
            class="has"
            :class="{ no: !one.has }"
            >{{ one.name }}</span
          >
        </footer>
      </section>

      <section class="col hand">
        <header>
          <strong>your code decides</strong>
          <span>a turn sent back</span>
        </header>
        <p class="lede">
          A hook on the end of the turn reads <code>TASK.md</code> and sends the agent back while
          anything is unticked. It is told how many times it already has, so it can give up.
        </p>
        <div class="task">
          <span class="file">TASK.md</span>
          <span
            v-for="(one, i) in ITEMS"
            :key="one"
            class="item"
            :class="{ done: boxes[i] }"
            role="checkbox"
            :aria-checked="boxes[i]"
            aria-readonly="true"
          >
            <span class="box" aria-hidden="true">{{ boxes[i] ? '✓' : '' }}</span>
            {{ one }}
          </span>
        </div>
        <div class="controls">
          <button type="button" class="go alt" :disabled="hookRunning" @click="take">
            {{ hookRunning ? 'working…' : 'run the turn' }}
          </button>
          <label class="sw">
            <input v-model="stuck" type="checkbox" :disabled="hookRunning" />
            it gets stuck on the last one
          </label>
        </div>
        <ol class="turns" aria-live="polite">
          <li v-for="one in hook" :key="one.n" :class="{ end: one.end }">
            <span class="n">turn {{ one.n }}</span>
            <span>{{ one.said }}</span>
          </li>
        </ol>
        <footer class="plain">
          <em>Works on every CLI. One more turn per refusal, decided by anything code can read.</em>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.goal {
  container-type: inline-size;
}

.top {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12.5px;
  color: var(--vp-c-text-2);
}

.cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.col {
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.col + .col {
  border-left: 1px solid var(--hmz-panel-border);
}

header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

header strong {
  font-size: 15px;
  color: var(--vp-c-brand-1);
}

.hand header strong {
  color: var(--hmz-accent);
}

header span {
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.sim {
  margin-left: auto;
  padding: 1px 8px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  font-style: normal;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.lede {
  margin: 8px 0 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.lede code {
  font-size: 12px;
}

.go {
  align-self: flex-start;
  padding: 5px 14px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.go.alt {
  border-color: var(--hmz-accent);
  color: var(--hmz-accent);
  background: transparent;
}

.go:disabled {
  opacity: 0.5;
  cursor: default;
}

.objective {
  margin: 0 0 12px;
  padding: 8px 12px;
  border-left: 3px solid var(--vp-c-brand-1);
  background: var(--vp-c-bg);
  border-radius: 0 8px 8px 0;
  font-size: 13px;
  color: var(--vp-c-text-1);
  font-style: italic;
}

.task {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
  font-size: 12.5px;
  color: var(--vp-c-text-2);
}

.task .file {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--vp-c-text-3);
  margin-bottom: 2px;
}

.item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border: 1px solid var(--vp-c-text-3);
  border-radius: 3px;
  font-size: 10px;
  line-height: 1;
  color: var(--vp-c-bg);
}

.item.done .box {
  border-color: var(--hmz-accent);
  background: var(--hmz-accent);
}

.item.done {
  color: var(--vp-c-text-3);
  text-decoration: line-through;
}

.controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.sw {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--vp-c-text-2);
  cursor: pointer;
}

.sw input {
  accent-color: var(--hmz-accent);
}

.turns {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  min-height: 150px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.turns li {
  display: flex;
  gap: 10px;
  padding: 2px 0;
  animation: land 0.3s ease;
}

.turns .n {
  flex: none;
  width: 52px;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  line-height: 1.9;
  color: var(--vp-c-text-3);
}

.turns li.end {
  color: var(--hmz-accent);
  font-weight: 600;
}

@keyframes land {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}

footer {
  margin-top: auto;
  padding-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
}

.lab {
  flex: 1 0 100%;
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.has {
  padding: 2px 9px;
  border-radius: 999px;
  border: 1px solid var(--hmz-accent);
  color: var(--hmz-accent);
  font-size: 11px;
  font-family: var(--vp-font-family-mono);
}

.has.no {
  border-color: var(--vp-c-divider);
  color: var(--vp-c-text-3);
  text-decoration: line-through;
}

footer em {
  flex: 1 0 100%;
  font-style: normal;
  font-size: 12px;
  line-height: 1.6;
  color: var(--vp-c-text-3);
}

@container (max-width: 580px) {
  .cols {
    grid-template-columns: minmax(0, 1fr);
  }

  .col + .col {
    border-left: 0;
    border-top: 1px solid var(--hmz-panel-border);
  }

  .turns {
    min-height: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .turns li {
    animation: none;
  }
}
</style>
