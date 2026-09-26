<script setup lang="ts">
// Pick a backend, see its effort ladder, and check a word against it the way `hmz exec -a`
// does. The ladders are the `efforts` of each profile in `src/hmz/coganchor/backends.py`,
// hardest first; the check is `Profile.takes` there (`auto` and nothing pass everywhere, a
// `swarm` prefix comes off on Kimi only, an added ACP CLI takes any word) and the refusal is
// `AgentBase._thinks` in `src/hmz/coganchor/agents/base.py`, as `hmz exec` prints it.
import { computed, ref } from 'vue'

interface Backend {
  cli: string
  called: string
  ladder: string[]
  // What a rung means, where the word alone would mislead.
  marks?: Record<string, string>
  swarms?: boolean
  acp?: boolean
  note: string
}

const VARIANTS = ['xhigh', 'high', 'medium', 'low', 'minimal']

const BACKENDS: Backend[] = [
  {
    cli: 'claude',
    called: 'Claude Code',
    ladder: ['ultracode', 'max', 'xhigh', 'high', 'medium', 'low'],
    marks: { ultracode: 'xhigh, free to run a fleet of its own' },
    note: 'Claude Code never lists ultracode itself; humanize offers it anyway.',
  },
  {
    cli: 'codex',
    called: 'Codex',
    ladder: ['ultra', 'max', 'xhigh', 'high', 'medium', 'low'],
    note: 'Each model takes its own subset, and the agent sheet offers only those.',
  },
  {
    cli: 'cursor-agent',
    called: 'Cursor Agent',
    ladder: ['max', 'xhigh', 'extra-high', 'high', 'medium', 'low', 'minimal', 'none'],
    marks: { 'extra-high': 'one model’s spelling of xhigh', none: 'no thinking at all' },
    note: 'The effort becomes part of the model id, so a model has the rungs your account lists for it. composer-2.5 has none: give it auto.',
  },
  {
    cli: 'dsh',
    called: 'DeepSeek Harness',
    ladder: ['max', 'high', 'low', 'off'],
    marks: { off: 'no reasoning at all' },
    note: 'off is a rung: the model is asked not to reason. auto sends nothing.',
  },
  {
    cli: 'grok',
    called: 'Grok Build',
    ladder: ['xhigh', 'high', 'medium', 'low'],
    note: 'Its ladder stops at xhigh: there is no max.',
  },
  {
    cli: 'kimi',
    called: 'Kimi Code',
    ladder: ['max', 'high', 'medium', 'low'],
    swarms: true,
    note: 'Swarm mode runs the same effort as a fleet of subagents: swarmmax is max, run wide.',
  },
  {
    cli: 'mimo',
    called: 'MiMo Code',
    ladder: VARIANTS,
    note: 'The effort picks the model’s variant. A provider with no variants takes it and ignores it.',
  },
  {
    cli: 'opencode',
    called: 'opencode',
    ladder: VARIANTS,
    note: 'The effort picks the model’s variant. A provider with no variants takes it and ignores it.',
  },
  {
    cli: 'pi',
    called: 'pi',
    ladder: ['max', 'xhigh', 'high', 'medium', 'low', 'minimal', 'off'],
    marks: { off: 'no thinking at all' },
    note: 'off is a rung: the model is asked not to think. auto sends nothing.',
  },
  {
    cli: 'qwen',
    called: 'Qwen Code',
    ladder: ['max', 'xhigh', 'high', 'medium', 'low', 'none'],
    marks: { none: 'no reasoning at all' },
    note: 'none is a rung, and the one a model with no reasoning setting runs at.',
  },
  {
    cli: 'zcode',
    called: 'ZCode',
    ladder: ['max', 'xhigh', 'high', 'medium', 'low', 'enabled', 'nothink', 'disabled'],
    marks: { enabled: 'thinks', nothink: 'does not think', disabled: 'does not think' },
    note: 'Each model takes a few: GLM 5.3 takes low, high and max; a model that only thinks or not takes enabled and disabled. The agent sheet offers each model its own.',
  },
  {
    cli: 'agy',
    called: 'Antigravity',
    ladder: ['high', 'medium', 'low'],
    note: 'A model whose name ends in a rung, like gemini-3.7-flash-low, runs at that rung, and the effort after the colon is not sent.',
  },
  {
    cli: 'my-cli',
    called: 'a CLI added at /providers',
    ladder: [],
    acp: true,
    note: 'It has no ladder. Any word is taken and none is sent: it runs at whatever you configured it at.',
  },
]

const picked = ref('claude')
const typed = ref('high')
const wide = ref(false)

const backend = computed(() => BACKENDS.find((one) => one.cli === picked.value) ?? BACKENDS[0])

// The word stays as it is when the backend changes, so one word can be tried on each.
function pick(cli: string) {
  picked.value = cli
}

function take(rung: string) {
  typed.value = rung
}

// What goes after the colon: the rung, with `swarm` in front on Kimi when swarm mode is on.
const effort = computed(() => {
  const word = typed.value.trim()
  if (backend.value.swarms && wide.value && word && word !== 'auto' && !word.startsWith('swarm')) {
    return `swarm${word}`
  }
  return word
})

// The rung the ladder is checked for, as `Profile.takes` reads it.
const rung = computed(() => {
  const word = effort.value
  return backend.value.swarms ? word.replace(/^swarm/, '') : word
})

const spec = computed(() => `agent=${backend.value.cli}/MODEL:${effort.value}`)

type Verdict = { ok: boolean; text: string }

const verdict = computed<Verdict>(() => {
  const one = backend.value
  const word = rung.value
  if (!word || word === 'auto') {
    return { ok: true, text: 'no effort: the CLI is told nothing, and the model runs at its own default' }
  }
  if (one.acp) {
    return { ok: true, text: 'taken, and not sent: an added CLI runs as it was configured' }
  }
  if (one.ladder.includes(word)) {
    const said = one.marks?.[word]
    const run = one.swarms && effort.value.startsWith('swarm') ? ', run as a fleet' : ''
    return { ok: true, text: `taken${said ? ` — ${said}` : ''}${run}` }
  }
  return {
    ok: false,
    text: `hmz exec: error: ${spec.value}: ${one.cli} cannot be asked to think at '${effort.value}'; expected one of ${one.ladder.join(', ')}`,
  }
})
</script>

<template>
  <div class="ladder hmz-panel">
    <div class="clis" role="group" aria-label="backend">
      <button
        v-for="one in BACKENDS"
        :key="one.cli"
        type="button"
        :class="{ on: one.cli === picked, acp: one.acp }"
        :aria-pressed="one.cli === picked"
        @click="pick(one.cli)"
      >
        {{ one.acp ? 'added CLI' : one.cli }}
      </button>
    </div>

    <div class="body">
      <p class="called">
        <strong>{{ backend.called }}</strong>
        <span v-if="!backend.acp">hardest first · click a rung</span>
      </p>

      <ol v-if="backend.ladder.length" class="rungs">
        <li v-for="(one, at) in backend.ladder" :key="one">
          <button
            type="button"
            :class="{ on: one === rung, soft: Boolean(backend.marks?.[one]) }"
            :aria-pressed="one === rung"
            :title="backend.marks?.[one]"
            :style="{ '--depth': 1 - at / Math.max(backend.ladder.length - 1, 1) }"
            @click="take(one)"
          >
            <span class="bar" />
            <code>{{ one }}</code>
          </button>
        </li>
        <li class="apart">
          <button type="button" :class="{ on: rung === 'auto' }" :aria-pressed="rung === 'auto'" @click="take('auto')">
            <code>auto</code>
          </button>
        </li>
      </ol>
      <p v-else class="none">no ladder · <code>auto</code> or any word</p>

      <label v-if="backend.swarms" class="swarm">
        <input v-model="wide" type="checkbox" />
        swarm mode
      </label>

      <label class="word">
        <span>or type a word</span>
        <input v-model="typed" type="text" spellcheck="false" autocomplete="off" aria-label="effort" />
      </label>

      <div class="term" :class="{ bad: !verdict.ok }">
        <p><span class="dim">$ hmz exec … -a</span> {{ spec }}</p>
        <p class="said">
          <span class="mark">{{ verdict.ok ? '✓' : '✗' }}</span>
          {{ verdict.text }}
        </p>
        <p v-if="!verdict.ok" class="dim">exit status 2 · nothing ran</p>
      </div>

      <p class="note">{{ backend.note }}</p>
    </div>

    <p class="caption">
      A simulation of the check <code>hmz exec -a</code> makes, drawn from humanize’s own table
      of backends. Nothing here runs a CLI.
    </p>
  </div>
</template>

<style scoped>
.clis {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.clis button {
  padding: 3px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}

.clis button:hover {
  border-color: var(--vp-c-brand-1);
}

.clis button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.clis button.acp {
  font-family: var(--vp-font-family-base);
  font-style: italic;
}

.body {
  padding: 14px 16px 4px;
}

.called {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
  margin: 0 0 10px;
  font-size: 14px;
}

.called span {
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.rungs {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.rungs li {
  margin: 0;
}

.rungs button {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.rungs .bar {
  display: block;
  height: calc(6px + var(--depth, 0) * 26px);
  border-radius: 4px 4px 0 0;
  background: var(--vp-c-default-soft);
  transition: background 0.2s;
}

.rungs code {
  padding: 3px 8px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 7px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 12.5px;
  transition: border-color 0.2s, background 0.2s;
}

.rungs button.soft code {
  border-style: dashed;
}

.rungs button:hover code {
  border-color: var(--vp-c-brand-1);
}

.rungs button.on .bar {
  background: linear-gradient(180deg, var(--hmz-accent), var(--vp-c-brand-1));
}

.rungs button.on code {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.rungs .apart {
  margin-left: 10px;
  padding-left: 12px;
  border-left: 1px dashed var(--vp-c-divider);
}

.none {
  margin: 0;
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.swarm {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  font-size: 13px;
  color: var(--vp-c-text-2);
  cursor: pointer;
}

.word {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  margin-top: 14px;
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.word input {
  width: 12em;
  max-width: 100%;
  padding: 4px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 7px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
}

.word input:focus {
  outline: none;
  border-color: var(--vp-c-brand-1);
}

.term {
  margin-top: 14px;
  padding: 10px 12px;
  border: 1px solid var(--vp-c-divider);
  border-left: 3px solid var(--hmz-accent);
  border-radius: 8px;
  background: var(--vp-code-block-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.term.bad {
  border-left-color: var(--vp-c-danger-1);
}

.term p {
  margin: 0;
  color: var(--vp-c-text-1);
}

.term .said {
  color: var(--hmz-accent);
}

.term.bad .said {
  color: var(--vp-c-danger-1);
}

.term .mark {
  font-weight: 700;
}

.term .dim {
  color: var(--vp-c-text-3);
}

.note {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.caption {
  margin: 12px 0 0;
  padding: 8px 16px 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--vp-c-text-3);
}

@media (prefers-reduced-motion: reduce) {
  .clis button,
  .rungs .bar,
  .rungs code {
    transition: none;
  }
}
</style>
