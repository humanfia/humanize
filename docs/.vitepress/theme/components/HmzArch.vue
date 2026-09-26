<script setup lang="ts">
// Four bands, and what passes downward between them: the rough shape of the system, for the
// page at the site's root. `HmzMap` on the features landing is the detailed one, and this
// deliberately is not that.
//
// Held to the code:
// - The flows are grouped by where they come from. `chat` is the one flow in the package
//   (`hmz/flows/builtin/`); the rest are the official flowverse (humanfia/flowverse), which
//   the terminal interface fetches in the background each time it starts; and a project's
//   `.humanize/flows` and `~/.humanize/flows` are offered as `local` and `user`.
// - The backends are `PROFILES` in `hmz/coganchor/backends.py`, in the order `hmz exec --help`
//   lists them. `dsh` is the one driven through a Python SDK rather than a CLI, signed in with
//   a DeepSeek API key rather than a login; it and `kimi` are the two with an extra of their
//   own in `pyproject.toml`, and `[kimi]` adds a client, not the CLI. A CLI that speaks the
//   Agent Client Protocol is added at `/providers`.
// - The ways in are the three a reader types or imports: `hmz`, `hmz exec` and `hmz.sdk`.
//
// Every chip that has a page links to it. Hovering only lifts the band it is over; nothing
// here is said only by a moving thing.
import { withBase } from 'vitepress'

interface Chip {
  text: string
  href?: string
  /** A small tag after the text. */
  tag?: string
  /** Drawn dashed: not one of the list, but something that joins it. */
  apart?: boolean
}

interface Group {
  /** What the chips in this group have in common, said above them. */
  label?: string
  chips: Chip[]
}

interface Band {
  name: string
  owns: string
  tone: string
  groups: Group[]
  /** A line under the chips. */
  foot?: string
  /** What this band hands the one below it. */
  down?: string
}

const BANDS: Band[] = [
  {
    name: 'Flows',
    owns: 'what the work is: which agents take turns, what each is asked, and when it stops',
    tone: 'var(--hmz-lane-3)',
    groups: [
      { label: 'in humanize', chips: [{ text: 'chat', href: '/flows/chat' }] },
      {
        label: 'the official flowverse, fetched each time hmz starts',
        chips: [
          { text: 'ralph_loop', href: '/flows/ralph-loop' },
          { text: 'stateful_ralph', href: '/flows/stateful-ralph' },
          { text: 'rlar', href: '/flows/rlar' },
          { text: 'flame_chase', href: '/flows/flame-chase' },
          { text: 'and more', href: '/flows/', apart: true },
        ],
      },
      {
        label: 'yours',
        chips: [
          { text: '.humanize/flows', href: '/weaver/writing-a-flow', tag: 'local' },
          { text: '~/.humanize/flows', href: '/weaver/writing-a-flow', tag: 'user' },
        ],
      },
    ],
    down: 'a flow, an agent for each of its roles, and a budget',
  },
  {
    name: 'humanize',
    owns:
      'runs the flow: takes every turn, holds every conversation, keeps to the budget, ' +
      'and records the run',
    tone: 'var(--hmz-lane-1)',
    groups: [
      {
        label: 'ways in',
        chips: [
          { text: 'hmz', href: '/reference/tui', tag: 'the interface' },
          { text: 'hmz exec', href: '/reference/cli' },
          { text: 'hmz.sdk', href: '/reference/sdk' },
        ],
      },
      {
        label: 'what it looks after',
        chips: [
          { text: 'accounts and fallback', href: '/features/accounts' },
          { text: 'budgets', href: '/features/allowances' },
          { text: 'a trace of every run', href: '/user/tracing' },
          { text: 'resuming', href: '/user/resuming' },
        ],
      },
    ],
    down: 'a turn: a prompt, on one conversation, at a model and an effort',
  },
  {
    name: 'Coding agents',
    owns:
      'the model, reached through a coding agent, most of them under the login they ' +
      'already have',
    tone: 'var(--hmz-lane-2)',
    groups: [
      {
        chips: [
          { text: 'agy' },
          { text: 'claude' },
          { text: 'codex' },
          { text: 'cursor-agent' },
          { text: 'dsh', tag: 'SDK' },
          { text: 'grok' },
          { text: 'kimi', tag: '+ extra' },
          { text: 'mimo' },
          { text: 'opencode' },
          { text: 'pi' },
          { text: 'qwen' },
          { text: 'zcode' },
          { text: 'any ACP CLI', href: '/user/providers', tag: '/providers', apart: true },
        ],
      },
    ],
    foot:
      'dsh is DeepSeek Harness, a Python SDK installed with hmz[dsh] and signed in with an ' +
      'API key; kimi needs hmz[kimi] beside the Kimi Code CLI; hmz[all] brings both',
    down: 'edits, commands and commits, with approvals bypassed',
  },
  {
    name: 'Environment',
    owns: 'where the work lands, and what the flow lets each agent touch there',
    tone: 'var(--hmz-lane-4)',
    groups: [
      {
        chips: [
          { text: 'this directory', href: '/user/permissions' },
          { text: 'another machine, over ssh', href: '/user/remote-execution' },
          { text: 'a git worktree', href: '/weaver/worktrees' },
          { text: 'a container', href: '/user/containers' },
        ],
      },
    ],
  },
]
</script>

<template>
  <div class="arch">
    <div class="stack">
      <template v-for="band in BANDS" :key="band.name">
        <section class="band" :style="{ '--tone': band.tone }">
          <header>
            <h3>{{ band.name }}</h3>
            <p>{{ band.owns }}</p>
          </header>
          <div class="groups">
            <div v-for="(group, at) in band.groups" :key="at" class="group">
              <span v-if="group.label" class="label">{{ group.label }}</span>
              <ul class="chips">
                <li v-for="chip in group.chips" :key="chip.text" :class="{ apart: chip.apart }">
                  <a v-if="chip.href" :href="withBase(chip.href)">
                    {{ chip.text }}<small v-if="chip.tag">{{ chip.tag }}</small>
                  </a>
                  <span v-else>{{ chip.text }}<small v-if="chip.tag">{{ chip.tag }}</small></span>
                </li>
              </ul>
            </div>
          </div>
          <p v-if="band.foot" class="foot">{{ band.foot }}</p>
        </section>

        <p v-if="band.down" class="down">
          <span class="arrow" aria-hidden="true"></span>
          {{ band.down }}
        </p>
      </template>
    </div>

    <p class="hmz-note">
      The rough shape. Every capability, grouped and linked to its explanation, is on
      <a :href="withBase('/features/')">Features</a>; every backend against what a flow may ask
      of it is <a :href="withBase('/features/backends')">Many backends, one agent</a>.
    </p>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.band {
  padding: 18px 20px 16px;
  border: 1px solid var(--hmz-panel-border);
  border-left: 3px solid var(--tone);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
  transition:
    border-color 0.25s,
    background 0.25s;
}

.band:hover {
  border-color: var(--tone);
  background: var(--vp-c-bg);
}

header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 14px;
}

h3 {
  margin: 0;
  border: 0;
  padding: 0;
  color: var(--tone);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

header p {
  flex: 1 1 22rem;
  margin: 0;
  color: var(--vp-c-text-3);
  font-size: 13px;
  line-height: 1.55;
}

.groups {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 26px;
  margin-top: 13px;
}

.group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.label {
  color: var(--vp-c-text-3);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.chips li {
  margin: 0;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 8px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 1.4;
}

.chips li > a,
.chips li > span {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 5px 10px;
  color: var(--vp-c-text-2);
}

/* A chip that is a link is still a chip: not underlined, and lifted only on hover. */
.vp-doc .chips li > a {
  font-weight: inherit;
  text-decoration: none;
  transition: color 0.2s;
}

.chips li:has(> a) {
  transition:
    border-color 0.2s,
    transform 0.2s;
}

.chips li:has(> a):hover {
  border-color: var(--tone);
  transform: translateY(-1px);
}

.vp-doc .chips li > a:hover {
  color: var(--vp-c-text-1);
}

.chips small {
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-base);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.03em;
}

/* What joins the list rather than being one of it. */
.chips .apart {
  border-style: dashed;
  border-color: var(--tone);
}

.foot {
  margin: 10px 0 0;
  color: var(--vp-c-text-3);
  font-size: 12px;
  line-height: 1.5;
}

/* What passes from one band to the next, on the arrow that carries it. */
.down {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0;
  padding: 9px 0 9px 22px;
  color: var(--vp-c-text-3);
  font-size: 12.5px;
  line-height: 1.4;
}

.arrow {
  flex: none;
  width: 1px;
  height: 26px;
  background: linear-gradient(var(--hmz-panel-border), var(--vp-c-text-3));
  position: relative;
}

.arrow::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: -3px;
  width: 7px;
  height: 7px;
  border-right: 1px solid var(--vp-c-text-3);
  border-bottom: 1px solid var(--vp-c-text-3);
  transform: rotate(45deg);
}

@media (max-width: 640px) {
  .band {
    padding: 15px 15px 13px;
  }

  header p {
    flex-basis: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .band,
  .chips li:has(> a),
  .vp-doc .chips li > a {
    transition: none;
  }

  .chips li:has(> a):hover {
    transform: none;
  }
}
</style>
