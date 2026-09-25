<script setup lang="ts">
// The moments a turn passes through, and what a hook hung on one of them can say back. Hang
// a hook, run the turn, and read what it was told and what it did about it. Each moment is one
// `on_*` method of the agent a flow holds; the ones only some harnesses reach need a mixin.
import { computed, onUnmounted, ref } from 'vue'

interface Moment {
  name: string
  about: string
  carries: string
  refusable: string
  everywhere: boolean
}

const MOMENTS: Moment[] = [
  {
    name: 'on_session_start',
    about: 'a session is about to take its first turn',
    carries: 'ctx · session',
    refusable: '',
    everywhere: true,
  },
  {
    name: 'on_user_prompt_submit',
    about: 'a prompt is about to go to the agent',
    carries: 'prompt',
    refusable: 'the turn does not run; context it adds goes into the prompt',
    everywhere: true,
  },
  {
    name: 'on_pre_tool_use',
    about: 'the agent has reached for a tool',
    carries: 'tool · input',
    refusable: 'the tool does not run, where the CLI gates its tools',
    everywhere: true,
  },
  {
    name: 'on_permission_request',
    about: 'the harness is asking whether a tool may run',
    carries: 'tool · input',
    refusable: 'the tool does not run',
    everywhere: false,
  },
  {
    name: 'on_ask_user',
    about: 'the agent has stopped mid-turn to ask its user',
    carries: 'question · options',
    refusable: '',
    everywhere: false,
  },
  {
    name: 'on_subagent_start',
    about: 'the agent has started an agent of its own',
    carries: 'subagent · task',
    refusable: '',
    everywhere: false,
  },
  {
    name: 'on_subagent_stop',
    about: 'one of those is about to finish',
    carries: 'subagent · said',
    refusable: '',
    everywhere: false,
  },
  {
    name: 'on_notification',
    about: 'the agent has stopped to tell its user something',
    carries: 'message',
    refusable: '',
    everywhere: true,
  },
  {
    name: 'on_stop',
    about: 'a turn is about to end',
    carries: 'said · again',
    refusable: 'the agent is sent on, with the reason as its next prompt',
    everywhere: true,
  },
  {
    name: 'on_session_end',
    about: 'a session is being closed',
    carries: 'ctx · session',
    refusable: '',
    everywhere: true,
  },
]

const at_ = (name: string) => MOMENTS.findIndex((one) => one.name === name)

interface Hook {
  key: string
  on: string
  said: string
  does: string
  verdict: string
}

const HOOKS: Hook[] = [
  {
    key: 'house',
    on: 'on_user_prompt_submit',
    said: 'add the house rules',
    does: 'adds a line to what the agent is about to be told',
    verdict: 'context: “never touch the generated files”',
  },
  {
    key: 'rm',
    on: 'on_permission_request',
    said: 'refuse anything that removes',
    does: 'reads the command and refuses it',
    verdict: 'allow=False: “rm is not yours to run here”',
  },
  {
    key: 'answer',
    on: 'on_ask_user',
    said: 'answer its questions',
    does: 'answers the question the agent asked',
    verdict: 'answer: “no — keep the old column”',
  },
  {
    key: 'unfinished',
    on: 'on_stop',
    said: 'not while TASK.md has boxes',
    does: 'sends the agent on rather than letting the turn end',
    verdict: 'block=True: “TASK.md still has unticked boxes.”',
  },
]

const hung = ref<string[]>(['rm'])
const log = ref<{ moment: string; said: string; kind: 'told' | 'said' | 'done' }[]>([])
const at = ref(-1)
const playing = ref(false)
let timer = 0

function hang(key: string) {
  hung.value = hung.value.includes(key)
    ? hung.value.filter((one) => one !== key)
    : [...hung.value, key]
}

const hookAt = (moment: string) =>
  HOOKS.find((one) => one.on === moment && hung.value.includes(one.key))

interface Beat {
  moment: number
  said: string
  kind: 'told' | 'said' | 'done'
}

function script(): Beat[] {
  const made: Beat[] = []
  const walk = (again: number) => {
    made.push({ moment: at_('on_pre_tool_use'), said: 'Read · src/pay.py', kind: 'told' })
    made.push({ moment: at_('on_pre_tool_use'), said: 'Bash · rm -rf build/', kind: 'told' })
    made.push({ moment: at_('on_permission_request'), said: 'Bash · rm -rf build/', kind: 'told' })
    const rm = hookAt('on_permission_request')
    if (rm) {
      made.push({ moment: at_('on_permission_request'), said: rm.verdict, kind: 'said' })
      made.push({
        moment: at_('on_permission_request'),
        said: 'the tool does not run; the agent is told why',
        kind: 'done',
      })
    } else {
      made.push({
        moment: at_('on_permission_request'),
        said: 'granted, because nothing was hung here',
        kind: 'done',
      })
    }
    made.push({ moment: at_('on_ask_user'), said: 'asks: “shall I drop the old column?”', kind: 'told' })
    const answer = hookAt('on_ask_user')
    if (answer) {
      made.push({ moment: at_('on_ask_user'), said: answer.verdict, kind: 'said' })
    } else {
      made.push({ moment: at_('on_ask_user'), said: 'unanswered: the agent carries on without one', kind: 'done' })
    }
    made.push({ moment: at_('on_stop'), said: `said: “that is the lot” · again = ${again}`, kind: 'told' })
    const stop = hookAt('on_stop')
    if (stop && again < 1) {
      made.push({ moment: at_('on_stop'), said: stop.verdict, kind: 'said' })
      made.push({ moment: at_('on_stop'), said: 'the turn does not end — the agent is sent on', kind: 'done' })
      walk(again + 1)
      return
    }
    made.push({ moment: at_('on_session_end'), said: 'the session is closed', kind: 'done' })
  }

  made.push({ moment: at_('on_session_start'), said: 'the first turn of this session', kind: 'told' })
  made.push({ moment: at_('on_user_prompt_submit'), said: 'prompt: “port the parser”', kind: 'told' })
  const house = hookAt('on_user_prompt_submit')
  if (house) {
    made.push({ moment: at_('on_user_prompt_submit'), said: house.verdict, kind: 'said' })
    made.push({ moment: at_('on_user_prompt_submit'), said: 'the line goes into the prompt', kind: 'done' })
  }
  walk(0)
  return made
}

function run() {
  const beats = script()
  log.value = []
  at.value = -1
  playing.value = true
  let i = 0
  window.clearInterval(timer)
  timer = window.setInterval(() => {
    if (i >= beats.length) {
      window.clearInterval(timer)
      playing.value = false
      at.value = -1
      return
    }
    const beat = beats[i]
    at.value = beat.moment
    log.value = [...log.value.slice(-11), { moment: MOMENTS[beat.moment].name, said: beat.said, kind: beat.kind }]
    i += 1
  }, 620)
}

onUnmounted(() => window.clearInterval(timer))

const hooked = computed(() => HOOKS.filter((one) => hung.value.includes(one.key)))
</script>

<template>
  <div class="moments hmz-panel">
    <div class="shelf">
      <span class="lab">hang a hook</span>
      <button
        v-for="one in HOOKS"
        :key="one.key"
        type="button"
        :class="{ on: hung.includes(one.key) }"
        @click="hang(one.key)"
      >
        <strong>{{ one.said }}</strong>
        <em>on {{ one.on }}</em>
      </button>
      <div class="spacer" />
      <button class="go" type="button" :disabled="playing" @click="run">
        {{ playing ? 'the turn is running…' : 'run the turn' }}
      </button>
    </div>

    <div class="track">
      <div
        v-for="(one, i) in MOMENTS"
        :key="one.name"
        class="station"
        :class="{ here: at === i, hooked: Boolean(hookAt(one.name)), rare: !one.everywhere }"
      >
        <span class="dot" />
        <strong>{{ one.name }}</strong>
        <span class="about">{{ one.about }}</span>
        <span class="carries">{{ one.carries }}</span>
        <span v-if="one.refusable" class="refusable">refusing it: {{ one.refusable }}</span>
        <span v-if="!one.everywhere" class="only">only on a role declared with its mixin</span>
      </div>
    </div>

    <ol class="log">
      <li v-for="(one, i) in log" :key="i" :class="one.kind">
        <span class="who">{{ one.moment }}</span>
        {{ one.said }}
      </li>
      <li v-if="!log.length" class="idle">
        {{
          hooked.length
            ? `${hooked.length} hook${hooked.length === 1 ? '' : 's'} hung — run the turn and read what each was told`
            : 'nothing is hung: run the turn and it passes through every moment untouched'
        }}
      </li>
    </ol>

    <p class="note">
      A hook is a word in the turn rather than a note about it: the CLI waits here for the flow's
      coroutine to answer, so one that takes a while is a turn that takes a while. One that raises
      fails the turn it arrived in, as the flow's own code raising would.
    </p>
  </div>
</template>

<style scoped>
.shelf {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 12px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.lab {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.shelf button {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 5px 12px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 10px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.shelf button strong {
  font-size: 12px;
  color: var(--vp-c-text-2);
  font-weight: 600;
}

.shelf button em {
  font-style: normal;
  font-size: 10.5px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.shelf button.on {
  border-style: solid;
  border-color: var(--hmz-accent);
  background: var(--vp-c-brand-soft);
}

.shelf button.on strong {
  color: var(--vp-c-text-1);
}

.spacer {
  flex: 1;
}

.shelf .go {
  padding: 6px 16px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.shelf .go:disabled {
  opacity: 0.5;
  cursor: default;
}

.track {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  padding: 16px 16px 0;
}

.station {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 10px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
  transition: border-color 0.25s, background 0.25s, transform 0.25s;
}

.station .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--vp-c-divider);
}

.station.hooked {
  border-color: var(--hmz-accent);
}

.station.hooked .dot {
  background: var(--hmz-accent);
}

.station.here {
  transform: translateY(-3px);
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
}

.station.here .dot {
  background: var(--vp-c-brand-1);
  box-shadow: 0 0 0 4px var(--vp-c-brand-soft);
}

.station.rare {
  border-style: dashed;
}

.station strong {
  font-size: 11px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.station .about {
  font-size: 10.5px;
  line-height: 1.4;
  color: var(--vp-c-text-3);
}

.station .carries {
  font-size: 10px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-brand-1);
}

.station .refusable,
.station .only {
  font-size: 10px;
  line-height: 1.4;
  color: var(--vp-c-text-3);
  font-style: italic;
}

.log {
  list-style: none;
  margin: 14px 16px 0;
  padding: 10px 14px;
  min-height: 128px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  line-height: 1.9;
  color: var(--vp-c-text-2);
}

.log li {
  display: flex;
  gap: 10px;
}

.log .who {
  flex: none;
  width: 184px;
  color: var(--vp-c-text-3);
}

.log .said {
  color: var(--hmz-accent);
}

.log .done {
  color: var(--hmz-warm);
}

.log .idle {
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-base);
}

.note {
  margin: 0;
  padding: 14px 16px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

@media (max-width: 900px) {
  .track {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 520px) {
  .track {
    grid-template-columns: minmax(0, 1fr);
  }

  .log .who {
    width: 110px;
  }
}
</style>
