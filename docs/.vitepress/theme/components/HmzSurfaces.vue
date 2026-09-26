<script setup lang="ts">
// Three ways into humanize -- the terminal interface, the command line and Python -- over one
// workspace: the same flows, accounts and runs whichever way a run was started. Pick what you
// want to do and the way in that does it lights up. Every answer is what that way in does.
import { computed, ref } from 'vue'

type Door = 'tui' | 'cli' | 'python'

interface Want {
  key: string
  said: string
  doors: Door[]
  answer: string
}

const DOORS: { key: Door; name: string; typed: string; kind: string }[] = [
  { key: 'tui', name: 'terminal interface', typed: 'hmz', kind: 'you, at the keyboard' },
  { key: 'cli', name: 'command line', typed: 'hmz exec', kind: 'a script, CI, cron' },
  { key: 'python', name: 'Python', typed: 'hmz.sdk', kind: 'a program of yours' },
]

const WANTS: Want[] = [
  {
    key: 'steer',
    said: 'watch it and steer it',
    doors: ['tui'],
    answer:
      'Read each agent’s conversation as it happens, type into a running turn, and see what the run has spent. Only the terminal interface has a person at the keyboard.',
  },
  {
    key: 'ask',
    said: 'answer its questions',
    doors: ['tui', 'python'],
    answer:
      'A flow can stop and ask a person. At the terminal interface, you answer. Python can hand the run someone to answer for you. The command line has nobody to ask, so the flow gets no answer, or the question’s defaults.',
  },
  {
    key: 'away',
    said: 'walk away and come back',
    doors: ['tui', 'python'],
    answer:
      'Close the terminal and the run keeps going. hmz in the same directory brings you back. From Python, a run can be held the same way, and outlive the program that started it.',
  },
  {
    key: 'ci',
    said: 'run it from CI',
    doors: ['cli'],
    answer:
      'One line says the flow, its agents, its budget and the task. A wrong line is refused before any agent starts, and the exit status says how the run ended.',
  },
  {
    key: 'events',
    said: 'read its events in a program',
    doors: ['cli', 'python'],
    answer:
      'The command line can print every event as a line of JSON. Python hands each event to a function of yours as it happens.',
  },
  {
    key: 'tool',
    said: 'build a tool on it',
    doors: ['python'],
    answer:
      'Start and stop runs, list the flows, flowverses and accounts, read past runs and build their traces, all from your own program.',
  },
  {
    key: 'held',
    said: 'look after a run left going',
    doors: ['python'],
    answer:
      'List the runs held on this machine, see what each is doing, let go of every terminal on one, or stop it.',
  },
]

const SHARED = ['the flows, nearest first', 'your flowverses', 'your accounts', 'this directory’s runs']

const want = ref(0)
const picked = computed(() => WANTS[want.value])
const lit = (door: Door) => picked.value.doors.includes(door)
</script>

<template>
  <div class="surfaces hmz-panel">
    <div class="bar">
      <span class="ask">I want to</span>
      <div class="wants" role="group" aria-label="what you want to do">
        <button
          v-for="(one, i) in WANTS"
          :key="one.key"
          type="button"
          :aria-pressed="want === i"
          :class="{ on: want === i }"
          @click="want = i"
        >
          {{ one.said }}
        </button>
      </div>
    </div>

    <div class="doors">
      <div v-for="door in DOORS" :key="door.key" class="door" :class="{ on: lit(door.key) }">
        <strong>{{ door.name }}</strong>
        <code>{{ door.typed }}</code>
        <span>{{ door.kind }}</span>
      </div>
    </div>

    <div class="wires" aria-hidden="true">
      <span v-for="door in DOORS" :key="door.key" :class="{ on: lit(door.key) }" />
    </div>

    <div class="shared">
      <span class="head">one workspace, whichever way in</span>
      <ul>
        <li v-for="one in SHARED" :key="one">{{ one }}</li>
      </ul>
    </div>

    <p class="answer" aria-live="polite">
      <strong>{{ picked.said }}:</strong> {{ picked.answer }}
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.ask {
  flex: none;
  font-size: 12px;
  font-weight: 650;
  color: var(--vp-c-text-2);
}

.wants {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.wants button {
  padding: 4px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  cursor: pointer;
}

.wants button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.doors {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding: 16px 16px 0;
}

.door {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  opacity: 0.55;
  transition: opacity 0.25s, border-color 0.25s, box-shadow 0.25s;
}

.door.on {
  opacity: 1;
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 0 0 3px var(--vp-c-brand-soft);
}

.door strong {
  font-size: 13.5px;
  color: var(--vp-c-text-1);
}

.door code {
  align-self: flex-start;
  font-size: 12px;
  color: var(--vp-c-brand-1);
}

.door span {
  font-size: 11.5px;
  color: var(--vp-c-text-3);
}

.wires {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding: 0 16px;
}

.wires span {
  justify-self: center;
  width: 2px;
  height: 22px;
  background: var(--vp-c-divider);
  transition: background 0.25s;
}

.wires span.on {
  background: var(--vp-c-brand-1);
}

.shared {
  margin: 0 16px;
  padding: 12px 14px;
  border: 1px solid var(--hmz-accent);
  border-radius: 12px;
  background: color-mix(in srgb, var(--hmz-accent) 8%, var(--vp-c-bg));
}

.shared .head {
  display: block;
  margin-bottom: 8px;
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.shared ul {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.shared li {
  margin: 0;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--vp-c-bg);
  border: 1px solid var(--vp-c-divider);
  font-size: 12px;
  color: var(--vp-c-text-1);
}

.answer {
  margin: 0;
  padding: 14px 16px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

.answer strong {
  color: var(--vp-c-text-1);
}

@media (max-width: 640px) {
  .bar {
    flex-direction: column;
    align-items: flex-start;
  }

  .doors {
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
  }

  .door {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    column-gap: 10px;
  }

  .door span {
    grid-column: 1 / -1;
  }

  .wires {
    grid-template-columns: minmax(0, 1fr);
  }

  .wires span:not(:first-child) {
    display: none;
  }

  .wires span {
    background: var(--vp-c-brand-1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .door,
  .wires span {
    transition: none;
  }
}
</style>
