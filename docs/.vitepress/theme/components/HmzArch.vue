<script setup lang="ts">
// Four bands, and what passes downward between them: the rough shape of the system, for the
// page at the site's root. `HmzMap` on the features landing is the detailed one, and this
// deliberately is not that.
//
// Held to the code:
// - The flows are grouped by where they come from. `chat` and the six loops FlowBench scores
//   are in the package (`hmz/flows/builtin/`); the rest are released from repositories of
//   their own and installed from a flowverse, the official one (humanfia/flowverse) or one you
//   added; and a project's `.hmz/flows` and `~/.hmz/flows` are offered as `local`
//   and `user`. Each flow's page is on humanfia.ai, where the catalogue lives.
// - The backends are `PROFILES` in `hmz/coganchor/backends.py`, in alphabetical order.
//   `dsh` is the one driven through a Python SDK rather than a CLI, signed in with
//   a DeepSeek API key rather than a login; it and `kimi` are the two with an extra of their
//   own in `pyproject.toml`, and `[kimi]` adds a client, not the CLI. A CLI that speaks the
//   Agent Client Protocol is added on the accounts page of `/settings`.
// - The ways in are the three a reader types or imports: `hmz`, `hmz exec` and `hmz.sdk`.
//
// Every chip that has a page links to it.
//
// It moves, and says nothing only by moving. Scrolled to, each band slides in on the diagonal
// and its chips land after it; then a pulse keeps travelling down the arrows, band to band,
// the way a turn does, and each band takes it with a wash of its tone. A rail down the side
// fills as the stack is scrolled through. Under reduced motion it is the stack, still.
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { withBase } from 'vitepress'

import { motion } from '../motion/gsap'

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

// The flow catalogue lives on humanfia.ai.
const FLOWS = 'https://humanfia.ai/flows/'

const BANDS: Band[] = [
  {
    name: 'Flows',
    owns: 'what the work is: which agents take turns, what each is asked, and when it stops',
    tone: 'var(--hmz-red)',
    groups: [
      {
        label: 'in humanize',
        chips: [
          { text: 'chat', href: `${FLOWS}chat` },
          { text: 'ralph_loop', href: `${FLOWS}ralph-loop` },
          { text: 'rlar', href: `${FLOWS}rlar` },
          { text: 'flame_chase', href: `${FLOWS}flame-chase` },
          { text: 'and three more', href: FLOWS, apart: true },
        ],
      },
      {
        label: 'installed from a flowverse',
        chips: [
          { text: 'humanize1', href: `${FLOWS}humanize1`, tag: 'official' },
          { text: 'parallel_flame_chase', href: `${FLOWS}parallel-flame-chase`, tag: 'official' },
          { text: 'aot', href: `${FLOWS}aot`, tag: 'official' },
          { text: 'your own', href: '/weaver/flowverses', apart: true },
        ],
      },
      {
        label: 'yours',
        chips: [
          { text: '.hmz/flows', href: '/weaver/writing-a-flow', tag: 'local' },
          { text: '~/.hmz/flows', href: '/weaver/writing-a-flow', tag: 'user' },
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
    tone: 'var(--hmz-ink)',
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
    tone: 'var(--vp-c-brand-1)',
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
          { text: 'mcode' },
          { text: 'mimo' },
          { text: 'opencode' },
          { text: 'pi' },
          { text: 'qwen' },
          { text: 'any ACP CLI', href: '/user/settings#accounts', tag: '/settings', apart: true },
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
    tone: 'var(--vp-c-text-2)',
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

const link = (href: string) => (href.startsWith('http') ? href : withBase(href))

const root = ref<HTMLElement | null>(null)
let context: gsap.Context | undefined

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  void nextTick(() => {
    const el = root.value
    if (!el) return
    const gsap = motion()
    context = gsap.context((self) => {
      const q = (s: string) => self.selector!(s) as Element[]
      // Each band on its own, as it is scrolled to: in along the diagonal, then its chips.
      for (const band of q('.band')) {
        const chips = band.querySelectorAll('.chips li, .label, .foot')
        const tl = gsap.timeline({ scrollTrigger: { trigger: band, start: 'top 88%', once: true } })
        tl.from(band, { autoAlpha: 0, x: -36, y: 12, duration: 0.8, ease: 'cine.out' })
        tl.from(band.querySelector('.edge'), { scaleY: 0, transformOrigin: '50% 0%', duration: 0.6, ease: 'cine' }, 0.15)
        tl.from(band.querySelector('.n'), { autoAlpha: 0, x: -10, duration: 0.5 }, 0.25)
        tl.from(chips, { autoAlpha: 0, y: 10, duration: 0.45, stagger: 0.025, ease: 'back.out(2)' }, 0.3)
      }
      for (const down of q('.down')) {
        gsap.from(down.querySelector('.arrow'), {
          scaleY: 0,
          transformOrigin: '50% 0%',
          duration: 0.6,
          ease: 'cine',
          scrollTrigger: { trigger: down, start: 'top 90%', once: true },
        })
        gsap.from(down.querySelector('.says'), {
          autoAlpha: 0,
          x: -10,
          duration: 0.5,
          delay: 0.25,
          scrollTrigger: { trigger: down, start: 'top 90%', once: true },
        })
      }
      // The rail down the side, filled as far as the stack has been read.
      gsap.fromTo(
        q('.rail-fill'),
        { scaleY: 0 },
        {
          scaleY: 1,
          ease: 'none',
          transformOrigin: '50% 0%',
          scrollTrigger: { trigger: el.querySelector('.stack'), start: 'top 70%', end: 'bottom 60%', scrub: 0.5 },
        },
      )
    }, el)
  })
})

onUnmounted(() => context?.revert())
</script>

<template>
  <div ref="root" class="arch">
    <div class="stack">
      <span class="rail" aria-hidden="true"><span class="rail-fill" /></span>
      <template v-for="(band, b) in BANDS" :key="band.name">
        <section class="band" :style="{ '--tone': band.tone, '--k': b }">
          <span class="edge" aria-hidden="true"></span>
          <header>
            <span class="n" aria-hidden="true">{{ String(b + 1).padStart(2, '0') }}</span>
            <h3>{{ band.name }}</h3>
            <p>{{ band.owns }}</p>
          </header>
          <div class="groups">
            <div v-for="(group, at) in band.groups" :key="at" class="group">
              <span v-if="group.label" class="label">{{ group.label }}</span>
              <ul class="chips">
                <li v-for="chip in group.chips" :key="chip.text" :class="{ apart: chip.apart }">
                  <a v-if="chip.href" :href="link(chip.href)">
                    {{ chip.text }}<small v-if="chip.tag">{{ chip.tag }}</small>
                  </a>
                  <span v-else>{{ chip.text }}<small v-if="chip.tag">{{ chip.tag }}</small></span>
                </li>
              </ul>
            </div>
          </div>
          <p v-if="band.foot" class="foot">{{ band.foot }}</p>
        </section>

        <p v-if="band.down" class="down" :style="{ '--k': b }">
          <span class="arrow" aria-hidden="true"><i class="pulse" /></span>
          <span class="says">{{ band.down }}</span>
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
.arch {
  /* One pulse goes down the whole stack in this long, band after band. */
  --beat: 3.6s;
}

.stack {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

/* How far down the stack the page has been read: a hairline down the left, filling. */
.rail {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -18px;
  width: 2px;
  background: var(--hmz-con-line);
}

.rail-fill {
  position: absolute;
  inset: 0;
  background: var(--hmz-red);
  transform: scaleY(0);
  transform-origin: 50% 0%;
}

.band {
  position: relative;
  padding: 18px 20px 16px 30px;
  border: 1px solid var(--hmz-panel-border);
  background: var(--hmz-panel-bg);
  overflow: hidden;
  transition:
    border-color 0.25s,
    background 0.25s,
    transform 0.25s;
}

/* The band's edge: a bar in its tone, cut on the diagonal at the top. */
.edge {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 10px;
  background: var(--tone);
  clip-path: polygon(0 10px, 100% 0, 100% 100%, 0 100%);
}

/* The band taking the pulse that came down the arrow above it: a wash of its tone, gone again. */
.band::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(100deg, color-mix(in srgb, var(--tone) 16%, transparent), transparent 40%);
  opacity: 0;
  animation: hmz-take var(--beat) ease-out infinite;
  animation-delay: calc(var(--k) * var(--beat) / 4 - var(--beat) / 8);
}

.band:first-of-type::before {
  animation: none;
}

@keyframes hmz-take {
  0% {
    opacity: 0;
  }
  4% {
    opacity: 1;
  }
  30%,
  100% {
    opacity: 0;
  }
}

.band:hover {
  border-color: var(--tone);
  background: var(--vp-c-bg);
  transform: translateX(4px);
}

header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 14px;
}

.n {
  color: var(--tone);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

h3 {
  margin: 0;
  border: 0;
  padding: 0;
  color: var(--vp-c-text-1);
  font-size: 17px;
  font-weight: 800;
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
    box-shadow 0.2s,
    transform 0.2s;
}

.chips li:has(> a):hover {
  border-color: var(--tone);
  box-shadow: 3px 3px 0 var(--tone);
  transform: translate(-1px, -1px);
}

.vp-doc .chips li > a:hover {
  color: var(--vp-c-text-1);
}

.chips small {
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-base);
  font-size: 11px;
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
  gap: 12px;
  margin: 0;
  padding: 9px 0 9px 26px;
  color: var(--vp-c-text-2);
  font-size: 12.5px;
  line-height: 1.4;
}

.says {
  font-style: italic;
}

.arrow {
  position: relative;
  flex: none;
  width: 2px;
  height: 30px;
  background: var(--hmz-con-mark);
}

.arrow::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: -4px;
  border-top: 7px solid var(--hmz-con-mark);
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
}

/* The pulse: a red square down the arrow, one band after the other. */
.pulse {
  position: absolute;
  top: 0;
  left: -3px;
  width: 8px;
  height: 8px;
  background: var(--hmz-red);
  opacity: 0;
  animation: hmz-pulse var(--beat) linear infinite;
  animation-delay: calc(var(--k) * var(--beat) / 4);
}

@keyframes hmz-pulse {
  0% {
    opacity: 0;
    transform: translateY(-4px);
  }
  2% {
    opacity: 1;
  }
  12% {
    opacity: 1;
  }
  15%,
  100% {
    opacity: 0;
    transform: translateY(26px);
  }
}

@media (max-width: 640px) {
  .band {
    padding: 15px 15px 13px 24px;
  }

  .edge {
    width: 7px;
  }

  header p {
    flex-basis: 100%;
  }

  .rail {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .band,
  .chips li:has(> a),
  .vp-doc .chips li > a {
    transition: none;
  }

  .band::before,
  .pulse {
    animation: none;
  }

  .band:hover,
  .chips li:has(> a):hover {
    transform: none;
  }

  .rail {
    display: none;
  }
}
</style>
