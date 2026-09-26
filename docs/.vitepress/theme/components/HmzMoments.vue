<script setup lang="ts">
// The moments a turn passes through, and what a hook hung on one can do there. Pick a CLI,
// hang hooks, run the turn. The moments each CLI reaches are the harness protocols in
// `hmz/flows/agents.py`; a tool refused as it is reached for stops only where the CLI waits on
// its own hook table for the answer (claude and qwen, `Gate` in `hmz/coganchor/agents/hooks.py`),
// and a hook on a moment the CLI cannot reach is refused before the run with the line
// `hmz/runtime/runner.py` writes.
import { computed, onMounted, onUnmounted, ref } from 'vue'

type Rare = 'perm' | 'ask' | 'sub'

interface Moment {
  name: string
  about: string
  can: string
  rare?: Rare
}

const MOMENTS: Moment[] = [
  { name: 'on_session_start', about: 'a session starts', can: 'put context before the first prompt' },
  { name: 'on_user_prompt_submit', about: 'a prompt is about to go', can: 'add to it, or refuse it' },
  { name: 'on_pre_tool_use', about: 'the agent reaches for a tool', can: 'refuse it' },
  {
    name: 'on_permission_request',
    about: 'the CLI asks whether a tool may run',
    can: 'allow or refuse it',
    rare: 'perm',
  },
  { name: 'on_subagent_start', about: 'it starts a subagent', can: 'hear it', rare: 'sub' },
  { name: 'on_subagent_stop', about: 'the subagent finishes', can: 'hear it', rare: 'sub' },
  { name: 'on_ask_user', about: 'the agent asks its user', can: 'answer it', rare: 'ask' },
  { name: 'on_notification', about: 'the agent tells its user something', can: 'hear it' },
  { name: 'on_stop', about: 'the turn is about to end', can: 'send the agent on' },
  { name: 'on_session_end', about: 'the session closes', can: 'hear it' },
]

type Asked = 'perm' | 'ask'

const MIXIN: Record<Asked, string> = {
  perm: 'PermissionRequestHookAgentMixin',
  ask: 'AskUserHookAgentMixin',
}

interface Cli {
  name: string
  reaches: Rare[]
  gates: boolean
}

const CLIS: Cli[] = [
  { name: 'claude', reaches: ['perm', 'ask', 'sub'], gates: true },
  { name: 'codex', reaches: ['perm', 'ask', 'sub'], gates: false },
  { name: 'kimi', reaches: ['perm', 'ask'], gates: false },
  { name: 'zcode', reaches: ['perm', 'ask'], gates: false },
  { name: 'pi', reaches: ['ask'], gates: false },
  { name: 'cursor-agent', reaches: ['sub'], gates: false },
  { name: 'qwen', reaches: [], gates: true },
  { name: 'agy', reaches: [], gates: false },
  { name: 'dsh', reaches: [], gates: false },
  { name: 'grok', reaches: [], gates: false },
  { name: 'mimo', reaches: [], gates: false },
  { name: 'opencode', reaches: [], gates: false },
]

interface Hook {
  key: string
  on: string
  label: string
  verdict: string
  needs?: Asked
}

const HOOKS: Hook[] = [
  {
    key: 'house',
    on: 'on_user_prompt_submit',
    label: 'add the house rules',
    verdict: 'adds “never edit generated files”',
  },
  {
    key: 'guard',
    on: 'on_pre_tool_use',
    label: 'refuse rm -rf as it is reached for',
    verdict: 'refuses: “rm is not yours to run here”',
  },
  {
    key: 'perm',
    on: 'on_permission_request',
    label: 'refuse rm -rf when the CLI asks',
    verdict: 'refuses: “rm is not yours to run here”',
    needs: 'perm',
  },
  {
    key: 'answer',
    on: 'on_ask_user',
    label: 'answer its questions',
    verdict: 'answers: “no, keep the old column”',
    needs: 'ask',
  },
  {
    key: 'unfinished',
    on: 'on_stop',
    label: 'not while TASK.md has boxes',
    verdict: 'sends it on: “TASK.md still has unticked boxes”',
  },
]

type Kind = 'told' | 'said' | 'done' | 'bad'

interface Beat {
  moment: number
  said: string
  kind: Kind
}

const cliName = ref('claude')
const hung = ref<string[]>(['guard'])
const log = ref<Beat[]>([])
const at = ref(-1)
const playing = ref(false)

const cli = computed(() => CLIS.find((one) => one.name === cliName.value) ?? CLIS[0])

const reaches = (moment: Moment) => !moment.rare || cli.value.reaches.includes(moment.rare)
const hookOn = (moment: string) =>
  HOOKS.find((one) => one.on === moment && hung.value.includes(one.key))
const idx = (name: string) => MOMENTS.findIndex((one) => one.name === name)

function can(moment: Moment): string {
  if (!reaches(moment)) return `not reached on ${cli.value.name}`
  if (moment.name === 'on_pre_tool_use') {
    return cli.value.gates
      ? 'refuse it: the tool does not run'
      : 'refuse it: too late here, it only watches'
  }
  return moment.can
}

function hang(key: string) {
  reset()
  hung.value = hung.value.includes(key)
    ? hung.value.filter((one) => one !== key)
    : [...hung.value, key]
}

const lacking = computed(() =>
  [
    ...new Set(
      HOOKS.filter(
        (one) => hung.value.includes(one.key) && one.needs && !cli.value.reaches.includes(one.needs),
      ).map((one) => MIXIN[one.needs as Asked]),
    ),
  ].sort(),
)

function script(): Beat[] {
  const beats: Beat[] = []
  const push = (name: string, said: string, kind: Kind) =>
    beats.push({ moment: idx(name), said, kind })
  const c = cli.value

  push('on_session_start', 'the first turn of this session', 'told')
  push('on_user_prompt_submit', 'prompt: “port the parser”', 'told')
  const house = hookOn('on_user_prompt_submit')
  if (house) push('on_user_prompt_submit', house.verdict, 'said')

  push('on_pre_tool_use', 'Read src/parser.py', 'told')
  let stopped = false
  const guard = hookOn('on_pre_tool_use')
  const perm = hookOn('on_permission_request')
  // Where the CLI asks first -- claude always, codex, kimi and zcode while a hook is hung
  // there -- the question comes before the tool starts. A CLI that gates on its own hook
  // table asks that before it asks for permission; the others only say what they reached for
  // once the tool is under way.
  const answer = hookOn('on_ask_user')
  const either = Boolean(perm || answer)
  const rung = c.name === 'kimi' || c.name === 'zcode'
  const asks =
    c.reaches.includes('perm') && (c.name === 'claude' || Boolean(perm) || (rung && either))
  const permission = () => {
    push('on_permission_request', 'may Bash run rm -rf build/?', 'told')
    if (perm) {
      push('on_permission_request', perm.verdict, 'said')
      push('on_permission_request', 'the tool does not run; the agent is told why', 'done')
      stopped = true
    } else {
      push('on_permission_request', 'allowed: nothing is hung here', 'done')
    }
  }
  if (c.gates) {
    push('on_pre_tool_use', 'Bash rm -rf build/', 'told')
    if (guard) {
      push('on_pre_tool_use', guard.verdict, 'said')
      push('on_pre_tool_use', 'the tool does not run; the agent is told why', 'done')
      stopped = true
    }
    if (!stopped && asks) permission()
  } else {
    if (asks) permission()
    if (!stopped) {
      push('on_pre_tool_use', 'Bash rm -rf build/', 'told')
      if (guard) {
        push('on_pre_tool_use', guard.verdict, 'said')
        push('on_pre_tool_use', `too late on ${c.name}: the tool had already started`, 'bad')
      }
    }
  }
  if (!stopped) push('on_pre_tool_use', 'rm -rf build/ ran', 'bad')

  if (c.reaches.includes('sub')) {
    push('on_subagent_start', 'Explore: “find every caller”', 'told')
    push('on_subagent_stop', 'Explore said: “three callers”', 'told')
  }
  // Claude and pi may ask whether or not a hook is there; codex only while one is hung on
  // this moment, kimi and zcode while either asking hook is (`hmz/runtime/flowing/harnessing.py`).
  const free = c.name === 'claude' || c.name === 'pi'
  if (c.reaches.includes('ask') && (answer || free || (rung && either))) {
    push('on_ask_user', 'asks: “shall I drop the old column?”', 'told')
    push(
      'on_ask_user',
      answer ? answer.verdict : 'nobody answers; the agent carries on without one',
      answer ? 'said' : 'done',
    )
  }

  push('on_notification', 'message: “the build is slow, carrying on”', 'told')
  push('on_stop', 'said: “that is the lot” · sent back 0 times', 'told')
  const unfinished = hookOn('on_stop')
  if (unfinished) {
    push('on_stop', unfinished.verdict, 'said')
    push('on_pre_tool_use', 'Edit TASK.md', 'told')
    push('on_stop', 'said: “all ticked now” · sent back 1 time', 'told')
    push('on_stop', 'lets it end: every box is ticked', 'said')
  }
  push('on_session_end', 'the session closes', 'told')
  return beats
}

const root = ref<HTMLElement | null>(null)
let reduced = false
let visible = true
let observer: IntersectionObserver | undefined
let timer = 0

function run() {
  window.clearInterval(timer)
  at.value = -1
  if (lacking.value.length) {
    log.value = [
      {
        moment: -1,
        said: `demo: 'coder' needs ${lacking.value.join(', ')}, which ${cli.value.name} does not do`,
        kind: 'bad',
      },
      { moment: -1, said: 'refused before the run starts: nothing ran', kind: 'done' },
    ]
    return
  }
  const beats = script()
  if (reduced) {
    log.value = beats
    return
  }
  log.value = []
  playing.value = true
  let i = 0
  timer = window.setInterval(() => {
    if (!visible) return
    if (i >= beats.length) {
      window.clearInterval(timer)
      playing.value = false
      at.value = -1
      return
    }
    at.value = beats[i].moment
    log.value = [...log.value, beats[i]]
    i += 1
  }, 620)
}

function reset() {
  window.clearInterval(timer)
  playing.value = false
  at.value = -1
  log.value = []
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
  window.clearInterval(timer)
})
</script>

<template>
  <div ref="root" class="moments hmz-panel">
    <div class="shelf">
      <label class="pick">
        <span class="lab">CLI</span>
        <select v-model="cliName" :disabled="playing" @change="reset">
          <option v-for="one in CLIS" :key="one.name" :value="one.name">{{ one.name }}</option>
        </select>
      </label>
      <button class="go" type="button" :disabled="playing" @click="run">
        {{ playing ? 'the turn is running…' : 'run the turn' }}
      </button>
      <div class="spacer" />
      <span class="sim">simulation</span>
    </div>

    <div class="hooks">
      <span class="lab">hang a hook</span>
      <button
        v-for="one in HOOKS"
        :key="one.key"
        type="button"
        :class="{ on: hung.includes(one.key), rare: one.needs }"
        :aria-pressed="hung.includes(one.key)"
        :disabled="playing"
        @click="hang(one.key)"
      >
        <strong>{{ one.label }}</strong>
        <em>{{ one.on }}</em>
      </button>
    </div>

    <ol class="track">
      <li
        v-for="(one, i) in MOMENTS"
        :key="one.name"
        class="station"
        :class="{
          here: at === i,
          hooked: Boolean(hookOn(one.name)),
          rare: one.rare,
          absent: !reaches(one),
        }"
      >
        <span class="dot" aria-hidden="true" />
        <span class="what">
          <span class="about">{{ one.about }}</span>
          <code>{{ one.name }}</code>
        </span>
        <span class="can">{{ can(one) }}</span>
      </li>
    </ol>

    <ol class="log" aria-live="polite">
      <li v-for="(one, i) in log" :key="i" :class="one.kind">
        <span v-if="one.moment >= 0" class="who">{{ MOMENTS[one.moment].name }}</span>
        <span class="what">{{ one.said }}</span>
      </li>
      <li v-if="!log.length" class="idle">
        Pick a CLI, hang hooks, and run the turn. Hollow dots are moments only some CLIs reach.
      </li>
    </ol>
  </div>
</template>

<style scoped>
.moments {
  container-type: inline-size;
}

.shelf,
.hooks {
  display: flex;
  align-items: center;
  gap: 8px 10px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.lab {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.pick {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.pick select {
  padding: 4px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-text-1);
  font-size: 12.5px;
  font-family: var(--vp-font-family-mono);
  cursor: pointer;
}

.go {
  padding: 5px 16px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 12.5px;
  font-weight: 650;
  cursor: pointer;
}

.go:disabled {
  opacity: 0.5;
  cursor: default;
}

.spacer {
  flex: 1;
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

.hooks button {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 5px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.hooks button.rare {
  border-style: dashed;
}

.hooks button strong {
  font-size: 12px;
  color: var(--vp-c-text-2);
  font-weight: 600;
}

.hooks button em {
  font-style: normal;
  font-size: 10.5px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.hooks button.on {
  border-color: var(--hmz-accent);
  background: var(--vp-c-brand-soft);
}

.hooks button.on strong {
  color: var(--vp-c-text-1);
}

.hooks button:disabled {
  cursor: default;
}

.track {
  position: relative;
  list-style: none;
  margin: 0;
  padding: 12px 16px 0;
}

/* The turn, top to bottom: one line through every dot. */
.track::before {
  content: '';
  position: absolute;
  left: 32px;
  top: 26px;
  bottom: 14px;
  width: 2px;
  background: var(--vp-c-divider);
}

.station {
  position: relative;
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr) minmax(0, 1fr);
  align-items: baseline;
  gap: 2px 12px;
  margin: 0;
  padding: 6px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  transition: border-color 0.25s, background 0.25s, opacity 0.25s;
}

.station .dot {
  position: relative;
  top: 1px;
  width: 10px;
  height: 10px;
  margin-left: 2px;
  border: 2px solid var(--vp-c-text-3);
  border-radius: 50%;
  background: var(--vp-c-text-3);
}

.station.rare .dot {
  background: var(--hmz-panel-bg);
}

.station.absent {
  opacity: 0.4;
}

.station.hooked .dot {
  border-color: var(--hmz-accent);
  background: var(--hmz-accent);
}

.station.hooked .can {
  color: var(--hmz-accent);
  font-weight: 600;
}

.station.here {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
}

.station.here .dot {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-1);
  box-shadow: 0 0 0 4px var(--vp-c-brand-soft);
}

.station .what {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 8px;
}

.station .about {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--vp-c-text-1);
}

.station code {
  padding: 0;
  background: none;
  font-size: 11px;
  color: var(--vp-c-brand-1);
  overflow-wrap: anywhere;
}

.station .can {
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--vp-c-text-2);
}

.log {
  list-style: none;
  margin: 14px 16px 16px;
  padding: 10px 14px;
  min-height: 136px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  line-height: 1.8;
  color: var(--vp-c-text-2);
}

.log li {
  display: flex;
  gap: 10px;
}

.log .who {
  flex: none;
  width: 176px;
  color: var(--vp-c-text-3);
}

.log .said .what {
  color: var(--hmz-accent);
}

.log .done .what {
  color: var(--vp-c-text-1);
}

.log .bad .what {
  color: var(--hmz-warm);
  font-weight: 600;
}

.log .idle {
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-base);
  font-size: 12.5px;
}

@container (max-width: 560px) {
  .station {
    grid-template-columns: 14px minmax(0, 1fr);
  }

  .station .can {
    grid-column: 2;
  }

  .log li {
    flex-direction: column;
    gap: 0;
    padding: 2px 0;
  }

  .log .who {
    width: auto;
    font-size: 10.5px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .station {
    transition: none;
  }
}
</style>
