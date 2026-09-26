<script setup lang="ts">
// A turn asked for a shape answers in it, or fails. Pick the shape, pick the CLI, and say
// whether the answer fits: the flow gets the fields back, or a failed turn. Which CLIs hold
// the shape themselves is each backend's `shapes` in `hmz/coganchor/agents/`; the rest, CLIs
// added at /providers among them, are asked for it in the prompt.
import { computed, ref } from 'vue'

interface Field {
  name: string
  type: string
  about: string
  answer: string
  reads: string
}

interface Shape {
  key: string
  name: string
  fields: Field[]
  branch: string
}

const SHAPES: Shape[] = [
  {
    key: 'review',
    name: 'Review',
    branch: 'done is false, so the loop takes another round with notes as its prompt',
    fields: [
      {
        name: 'done',
        type: 'bool',
        about: 'True only if there is nothing left to do or to fix.',
        answer: 'false',
        reads: 'decides: go round again',
      },
      {
        name: 'notes',
        type: 'str',
        about: 'What to say to the agent, passed on word for word.',
        answer: '"name the case that fails, then fix it"',
        reads: 'carries: the next prompt, word for word',
      },
    ],
  },
  {
    key: 'plan',
    name: 'Settled',
    branch: 'the flow builds it the careful way, with tests, in up to three rounds',
    fields: [
      {
        name: 'approach',
        type: 'Literal["fast", "careful"]',
        about: 'Which way should this be built?',
        answer: '"careful"',
        reads: 'picks a branch, and never a third one',
      },
      {
        name: 'tests',
        type: 'bool',
        about: 'Write tests for it?',
        answer: 'true',
        reads: 'decides: yes or no',
      },
      {
        name: 'rounds',
        type: 'int = 3',
        about: 'How many rounds may it take?',
        answer: '3',
        reads: 'bounds the loop',
      },
    ],
  },
]

interface Backend {
  name: string
  held: boolean
}

const BACKENDS: Backend[] = [
  { name: 'claude', held: true },
  { name: 'codex', held: true },
  { name: 'agy', held: true },
  { name: 'grok', held: true },
  { name: 'qwen', held: true },
  { name: 'cursor-agent', held: false },
  { name: 'dsh', held: false },
  { name: 'kimi', held: false },
  { name: 'mimo', held: false },
  { name: 'opencode', held: false },
  { name: 'pi', held: false },
  { name: 'zcode', held: false },
  { name: 'a CLI you added', held: false },
]

const shape = ref(0)
const backend = ref(0)
const fits = ref(true)

const picked = computed(() => SHAPES[shape.value])
const cli = computed(() => BACKENDS[backend.value])
</script>

<template>
  <div class="shape hmz-panel">
    <div class="bar">
      <div class="tabs" role="group" aria-label="which shape">
        <button
          v-for="(one, i) in SHAPES"
          :key="one.key"
          type="button"
          :class="{ on: shape === i }"
          :aria-pressed="shape === i"
          @click="shape = i"
        >
          {{ one.name }}
        </button>
      </div>
      <div class="spacer" />
      <label class="sw">
        <input v-model="fits" type="checkbox" />
        the answer fits the shape
      </label>
      <span class="sim">simulation</span>
    </div>

    <div class="flowline">
      <section class="card model">
        <header>1 · the flow asks for</header>
        <div class="rows">
          <div v-for="one in picked.fields" :key="one.name" class="field">
            <code>{{ one.name }}</code>
            <span class="type">{{ one.type }}</span>
            <p>{{ one.about }}</p>
          </div>
        </div>
        <footer>Each field's description is what the agent is asked.</footer>
      </section>

      <div class="arrow" aria-hidden="true">
        <span />
      </div>

      <section class="card asked">
        <header>2 · the CLI answering</header>
        <div class="chips" role="group" aria-label="which CLI">
          <button
            v-for="(one, i) in BACKENDS"
            :key="one.name"
            type="button"
            :class="{ on: backend === i, held: one.held }"
            :aria-pressed="backend === i"
            @click="backend = i"
          >
            {{ one.name }}
          </button>
        </div>
        <p class="how">
          <span class="road" :class="{ held: cli.held }">{{
            cli.held ? 'holds the shape itself' : 'asked in the prompt'
          }}</span>
          <template v-if="cli.held">
            <strong>{{ cli.name }}</strong> takes the shape as a setting of its own and keeps the
            model to it.
          </template>
          <template v-else>
            <strong>{{ cli.name }}</strong> has no setting for it, so the shape goes into the
            prompt and the answer is checked when it comes back.
          </template>
        </p>
        <footer>Either way, the flow gets the same thing back.</footer>
      </section>

      <div class="arrow" aria-hidden="true">
        <span />
      </div>

      <section class="card answer" :class="{ bad: !fits }">
        <header>3 · what the flow gets</header>
        <div v-if="fits" class="rows">
          <div v-for="one in picked.fields" :key="one.name" class="got">
            <code>{{ one.name }}</code>
            <span class="value">{{ one.answer }}</span>
            <p>{{ one.reads }}</p>
          </div>
        </div>
        <div v-else class="rows">
          <div class="got none">
            <strong class="failed">the turn fails</strong>
            <code>OutputSchemaError</code>
            <p>
              An answer that is not the shape is a turn that did not do what it was told, however
              cleanly the agent finished. The flow never gets half an answer.
            </p>
          </div>
        </div>
        <footer>
          {{ fits ? picked.branch : 'the usual branch: take this round again' }}
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.shape {
  container-type: inline-size;
}

.bar {
  display: flex;
  align-items: center;
  gap: 10px 14px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.tabs {
  display: inline-flex;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  overflow: hidden;
}

.tabs button {
  padding: 4px 14px;
  border: 0;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  font-weight: 600;
  font-family: var(--vp-font-family-mono);
  cursor: pointer;
}

.tabs button.on {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.spacer {
  flex: 1;
}

.sw {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--vp-c-text-1);
  font-weight: 600;
  cursor: pointer;
}

.sw input {
  accent-color: var(--vp-c-brand-1);
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

.flowline {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 36px minmax(0, 1fr) 36px minmax(0, 1fr);
  align-items: stretch;
  padding: 16px;
}

.card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  overflow: hidden;
  transition: border-color 0.25s;
}

.card header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.card footer {
  margin-top: auto;
  padding: 9px 12px;
  border-top: 1px solid var(--vp-c-divider);
  font-size: 12px;
  line-height: 1.55;
  color: var(--vp-c-text-2);
}

.rows {
  padding: 10px 12px;
}

.field,
.got {
  padding: 6px 0;
  border-bottom: 1px dashed var(--vp-c-divider);
}

.field:last-child,
.got:last-child {
  border-bottom: 0;
}

.field code,
.got code {
  font-size: 12.5px;
  color: var(--vp-c-brand-1);
  font-weight: 650;
}

.field .type {
  margin-left: 8px;
  font-size: 11px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
  overflow-wrap: anywhere;
}

.got .value {
  margin-left: 8px;
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  color: var(--hmz-accent);
  overflow-wrap: anywhere;
}

.field p,
.got p {
  margin: 3px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--vp-c-text-2);
}

.answer.bad {
  border-color: var(--hmz-warm);
}

.answer.bad code {
  display: block;
  margin-top: 4px;
  color: var(--hmz-warm);
}

.failed {
  font-size: 14px;
  color: var(--hmz-warm);
}

.arrow {
  display: flex;
  align-items: center;
  justify-content: center;
}

.arrow span {
  position: relative;
  width: 70%;
  height: 2px;
  border-radius: 2px;
  background: var(--vp-c-brand-1);
}

.arrow span::after {
  content: '';
  position: absolute;
  right: -2px;
  top: -4px;
  border: 5px solid transparent;
  border-left-color: var(--vp-c-brand-1);
  border-right: 0;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 12px 0;
}

.chips button {
  padding: 3px 10px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 11px;
  font-family: var(--vp-font-family-mono);
  cursor: pointer;
}

.chips button.held {
  border-style: solid;
  border-color: var(--hmz-accent);
}

.chips button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 650;
}

.how {
  margin: 12px 12px 12px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.how strong {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
}

.road {
  display: block;
  width: fit-content;
  margin-bottom: 6px;
  padding: 1px 9px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 650;
  color: var(--vp-c-text-2);
}

.road.held {
  border-style: solid;
  border-color: var(--hmz-accent);
  color: var(--hmz-accent);
}

@container (max-width: 760px) {
  .flowline {
    grid-template-columns: minmax(0, 1fr);
  }

  .arrow {
    height: 26px;
  }

  .arrow span {
    width: 2px;
    height: 70%;
  }

  .arrow span::after {
    right: -4px;
    top: auto;
    bottom: -2px;
    border: 5px solid transparent;
    border-top-color: var(--vp-c-brand-1);
    border-bottom: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .card {
    transition: none;
  }
}
</style>
