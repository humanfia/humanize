<script setup lang="ts">
// Everything humanize does, by what the reader is trying to do, each item leading to the page
// that does it. The areas and items are the sections and rows of `features/capabilities.md`,
// one for one: add a row there and it is an item here, in the same place.
import { computed, ref } from 'vue'
import { withBase } from 'vitepress'

interface Item {
  name: string
  line: string
  link: string
  page: string
}

interface Area {
  code: string
  name: string
  who: string
  items: Item[]
}

const AREAS: Area[] = [
  {
    code: 'A',
    name: 'Run it your way',
    who: 'the agents, the accounts, and how it starts',
    items: [
      {
        name: 'Ready-made loops',
        line: 'Pick a loop somebody already wrote: a Ralph loop, a reviewer loop, three lanes at once.',
        link: '/flows/',
        page: 'Flows',
      },
      {
        name: 'Any coding agent',
        line: 'Claude Code, Codex, Cursor, Kimi and eight more, most under the login they already have.',
        link: '/user/providers',
        page: 'Providers',
      },
      {
        name: 'Model and effort',
        line: 'Choose each agent’s model and how hard it thinks.',
        link: '/user/efforts',
        page: 'Efforts',
      },
      {
        name: 'Two accounts of one CLI',
        line: 'A subscription and a gateway of the same CLI, side by side, each with its own login.',
        link: '/user/providers',
        page: 'Providers',
      },
      {
        name: 'Fall back',
        line: 'When an account runs out, another takes the conversation on. When a CLI is gone, the turn moves where you said.',
        link: '/user/fallback',
        page: 'Falling back',
      },
      {
        name: 'Skills',
        line: 'See which skills each agent loads. A flow can bring its own.',
        link: '/user/skills',
        page: 'Skills',
      },
      {
        name: 'From a script',
        line: 'Run a flow from a shell script or a cron job, with no interface.',
        link: '/user/unattended',
        page: 'Run it unattended',
      },
      {
        name: 'In CI',
        line: 'Run a flow on a schedule and open a pull request with what it did.',
        link: '/user/ci',
        page: 'humanize in CI',
      },
      {
        name: 'From Python',
        line: 'Drive humanize from a Python program of your own.',
        link: '/reference/sdk',
        page: 'SDK reference',
      },
    ],
  },
  {
    code: 'B',
    name: 'While it runs',
    who: 'watching, steering, and stopping it',
    items: [
      {
        name: 'Talk into a turn',
        line: 'Correct an agent mid-turn without stopping it. On Claude Code, Codex, Kimi and pi.',
        link: '/user/steering',
        page: 'Talking to a running turn',
      },
      {
        name: 'Side questions',
        line: 'Ask what a running flow is up to without interrupting it.',
        link: '/user/btw',
        page: 'Side questions',
      },
      {
        name: 'Watch every agent',
        line: 'See who is working, for how long, and who handed over to whom.',
        link: '/user/monitor',
        page: 'Watching a run',
      },
      {
        name: 'Answer, or step away',
        line: 'Answer when an agent or the flow asks you, or say you are away so nothing waits.',
        link: '/user/questions',
        page: 'Questions',
      },
      {
        name: 'What it costs',
        line: 'Tokens, money and rate for every agent, while it runs.',
        link: '/user/tally',
        page: 'Cost and rate',
      },
      {
        name: 'A budget on every run',
        line: 'Cap a run’s time, cost or output tokens. The first limit it reaches stops it.',
        link: '/user/unattended',
        page: 'Run it unattended',
      },
      {
        name: 'Stop it',
        line: 'Stop the run from the keyboard, and force it if it will not stop.',
        link: '/user/stopping',
        page: 'Stopping',
      },
      {
        name: 'Leave it running',
        line: 'Close the terminal or lose the connection. Open humanize in the same directory to find the run again.',
        link: '/reference/daemon',
        page: 'Daemon reference',
      },
    ],
  },
  {
    code: 'C',
    name: 'Where the work lands',
    who: 'your directory, a container, another machine',
    items: [
      {
        name: 'In a container',
        line: 'Give an agent a toolchain you have not got, with your project at the path it already has.',
        link: '/user/containers',
        page: 'Containers',
      },
      {
        name: 'On another machine',
        line: 'The commands run on the build box. The agent and its login stay on your machine.',
        link: '/user/remote-execution',
        page: 'Remote execution',
      },
      {
        name: 'What an agent may touch',
        line: 'See what a flow lets each agent do. Nothing is put to you for approval.',
        link: '/user/permissions',
        page: 'Permissions',
      },
    ],
  },
  {
    code: 'D',
    name: 'After a run',
    who: 'picking it up, and reading it back',
    items: [
      {
        name: 'Pick it up',
        line: 'Carry a stopped run on from where it stood, if its flow can be picked up.',
        link: '/user/resuming',
        page: 'Picking a run up',
      },
      {
        name: 'One timeline',
        line: 'Every agent and sub-agent of a run on one clock in Perfetto, and the programs they ran if you profiled it.',
        link: '/user/tracing',
        page: 'Tracing',
      },
      {
        name: 'Hand it to somebody',
        line: 'Pack a whole run into one archive somebody else can open.',
        link: '/user/export',
        page: 'Exporting a run',
      },
      {
        name: 'Crash reports',
        line: 'Send crash reports and feedback, or never. You are asked once.',
        link: '/user/reporting',
        page: 'Reporting',
      },
    ],
  },
  {
    code: 'E',
    name: 'Writing a flow',
    who: 'for the weaver, in Python',
    items: [
      {
        name: 'A loop in plain Python',
        line: 'Write the loop as an async function and declare the agents it needs by role.',
        link: '/weaver/writing-a-flow',
        page: 'Writing a flow',
      },
      {
        name: 'Params of its own',
        line: 'Typed settings that the prompt and the command line both fill in.',
        link: '/weaver/flow-settings',
        page: 'Params of its own',
      },
      {
        name: 'Many conversations at once',
        line: 'Fan out across as many conversations as the work needs.',
        link: '/weaver/async-flows',
        page: 'Many turns at once',
      },
      {
        name: 'Answers as typed data',
        line: 'Ask for a pydantic model and read a field, not a paragraph.',
        link: '/weaver/shapes',
        page: 'Answers in a shape',
      },
      {
        name: 'The agent decides it is done',
        line: 'Give an agent a goal and let it keep going until it judges the goal met.',
        link: '/weaver/goals',
        page: 'Goals',
      },
      {
        name: 'React to each moment',
        line: 'Run your own code before a tool, on a prompt, or when a turn stops.',
        link: '/weaver/hooks',
        page: 'Hooks',
      },
      {
        name: 'Tools that call the flow',
        line: 'Let the agent reach the flow mid-turn, and answer with the flow’s own code.',
        link: '/weaver/tools',
        page: 'The agent asking the flow',
      },
      {
        name: 'Ask the person',
        line: 'Put a question to whoever is at the prompt, as one of the flow’s agents.',
        link: '/weaver/human-agent',
        page: 'The person as an agent',
      },
      {
        name: 'Cap a single turn',
        line: 'Stop one turn once it has spent enough time, money or output tokens.',
        link: '/reference/flows',
        page: 'Flows reference',
      },
      {
        name: 'Call another flow',
        line: 'Use another flow as a step, under what is left of your budget.',
        link: '/weaver/calling-flows',
        page: 'A flow that calls a flow',
      },
      {
        name: 'Branch a conversation',
        line: 'Fork a conversation and try more than one way on from the same point.',
        link: '/weaver/branching',
        page: 'Branching a conversation',
      },
      {
        name: 'Worktrees and copies',
        line: 'A worktree per task, a throwaway copy, or an empty scratch directory.',
        link: '/weaver/worktrees',
        page: 'Worktrees, copies and scratch',
      },
      {
        name: 'Test without a model',
        line: 'Run a flow against scripted agents: milliseconds a test, and nothing spent.',
        link: '/weaver/testing-flows',
        page: 'Testing a flow',
      },
      {
        name: 'Publish it',
        line: 'Put flows in a git repository that anybody can add and run by name.',
        link: '/weaver/flowverses',
        page: 'Flowverses',
      },
    ],
  },
]

const hovered = ref<Item | null>(null)
const focused = ref<Item | null>(null)
const active = computed(() => focused.value ?? hovered.value)
const count = AREAS.reduce((n, area) => n + area.items.length, 0)
const id = (area: Area, i: number) => `hmz-map-${area.code}${i}`
</script>

<template>
  <div class="map hmz-panel">
    <section
      v-for="(area, a) in AREAS"
      :key="area.code"
      class="area"
      :style="{ '--tone': `var(--hmz-lane-${a + 1})` }"
      :aria-labelledby="`hmz-area-${area.code}`"
    >
      <header>
        <span class="code">{{ area.code }}</span>
        <strong :id="`hmz-area-${area.code}`">{{ area.name }}</strong>
        <span class="who">{{ area.who }}</span>
      </header>
      <div class="items">
        <a
          v-for="(item, i) in area.items"
          :key="item.name"
          class="item"
          :class="{ held: active === item }"
          :href="withBase(item.link)"
          :aria-describedby="id(area, i)"
          @mouseenter="hovered = item"
          @mouseleave="hovered = null"
          @focus="focused = item"
          @blur="focused = null"
        >
          {{ item.name }}
          <span :id="id(area, i)" class="line">{{ item.line }}</span>
        </a>
      </div>
    </section>
    <p class="caption">
      <template v-if="active">
        {{ active.line }} <b>→ {{ active.page }}</b>
      </template>
      <template v-else>
        {{ AREAS.length }} areas, {{ count }} things it does. Point at one to read it; open it for
        the page that does it.
      </template>
    </p>
  </div>
</template>

<style scoped>
.area {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 10px 18px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--hmz-panel-border);
  border-left: 3px solid var(--tone);
}

header {
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 8px;
  align-content: start;
}

.code {
  grid-row: 1 / 3;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 7px;
  background: var(--tone);
  color: var(--vp-c-bg);
  font-size: 11px;
  font-weight: 700;
}

header strong {
  font-size: 14px;
  line-height: 1.35;
  color: var(--vp-c-text-1);
}

.who {
  font-size: 11.5px;
  line-height: 1.4;
  color: var(--vp-c-text-3);
}

.items {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  align-content: start;
}

.vp-doc .item,
.item {
  padding: 4px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-2);
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.5;
  text-decoration: none;
  transition: border-color 0.2s, background 0.2s, color 0.2s;
}

.vp-doc .item:hover,
.item:hover,
.item.held {
  border-color: var(--tone);
  color: var(--vp-c-text-1);
  background: var(--vp-c-default-soft);
  text-decoration: none;
}

.item:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.line {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.caption {
  margin: 0;
  padding: 14px 18px;
  min-height: 72px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.caption b {
  color: var(--vp-c-brand-1);
  font-weight: 600;
  white-space: nowrap;
}

@media (max-width: 720px) {
  .area {
    grid-template-columns: minmax(0, 1fr);
    padding: 12px 14px;
  }

  .caption {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .item {
    transition: none;
  }
}
</style>
