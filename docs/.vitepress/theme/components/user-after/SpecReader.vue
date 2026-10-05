<script setup lang="ts">
// How `hmz exec` reads one `-a`, played in the browser: the role, the CLI, the account, the
// model and the effort, or the refusal it would print instead.
//
// A simulation, and it has to say what the code says. The reading is
// `hmz.runtime.flowing.specs.parse_agents` over `hmz.coganchor.backends.read`, the ladders
// are each profile's `efforts` in `hmz.coganchor.backends`, and every refusal below is the
// line `hmz exec` prints for it. It knows the twelve CLIs humanize ships and no CLI added at
// the accounts page of /settings, and it cannot know which roles a flow declares.
//
// The reading is played as a labelled transform: the spelled-out value comes apart, a brace
// names each part, and each name flies down into the row that explains it; a refusal jolts and
// its message types on. Under reduced motion all of it is the still result.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { motion } from '../../motion/gsap'
import { braceD, draw, rise, shake } from '../user-kit/moves'

interface Cli {
  name: string
  title: string
  aliases: string[]
  efforts: string[]
  swarms?: boolean
}

const CLIS: Cli[] = [
  { name: 'claude', title: 'Claude Code', aliases: ['claude', 'claude-code'], efforts: ['ultracode', 'max', 'xhigh', 'high', 'medium', 'low'] },
  { name: 'agy', title: 'Antigravity', aliases: ['agy', 'antigravity'], efforts: ['high', 'medium', 'low'] },
  { name: 'codex', title: 'Codex', aliases: ['codex'], efforts: ['ultra', 'max', 'xhigh', 'high', 'medium', 'low'] },
  { name: 'dsh', title: 'DeepSeek Harness', aliases: ['dsh', 'deepseek-harness'], efforts: ['max', 'high', 'low', 'off'] },
  { name: 'grok', title: 'Grok Build', aliases: ['grok', 'grok-build', 'grokbuild'], efforts: ['xhigh', 'high', 'medium', 'low'] },
  { name: 'kimi', title: 'Kimi Code', aliases: ['kimi', 'kimi-code'], efforts: ['max', 'high', 'medium', 'low'], swarms: true },
  { name: 'pi', title: 'pi', aliases: ['pi'], efforts: ['max', 'xhigh', 'high', 'medium', 'low', 'minimal', 'off'] },
  { name: 'qwen', title: 'Qwen Code', aliases: ['qwen', 'qwen-code'], efforts: ['max', 'xhigh', 'high', 'medium', 'low', 'none'] },
  { name: 'opencode', title: 'opencode', aliases: ['opencode'], efforts: ['xhigh', 'high', 'medium', 'low', 'minimal'] },
  { name: 'mimo', title: 'mimocode', aliases: ['mimo', 'mimocode', 'mimo-code'], efforts: ['xhigh', 'high', 'medium', 'low', 'minimal'] },
  { name: 'cursor-agent', title: 'Cursor Agent', aliases: ['cursor-agent', 'cursor-cli'], efforts: ['max', 'xhigh', 'extra-high', 'high', 'medium', 'low', 'minimal', 'none'] },
  { name: 'mcode', title: 'MiniMax Code', aliases: ['mcode', 'minimax', 'minimax-code'], efforts: ['max', 'xhigh', 'high', 'medium', 'low'] },
]

const EXAMPLES = [
  { label: 'ralph_loop', spec: 'agent=claude/claude-opus-5:high' },
  { label: 'an account', spec: 'actor=claude@deepseek/claude-opus-5:high' },
  { label: 'two agents', spec: 'actor=claude/claude-opus-5:max,reviewer=codex/gpt-5.6-sol:high' },
  { label: 'slashes in the model', spec: 'agent=kimi/kimi-code/k3:swarmmax' },
  { label: 'a colon in the model', spec: 'agent=mcode/custom_provider:gateway/mock/first-model' },
  { label: 'no effort', spec: 'agent=claude/claude-opus-5:auto' },
  { label: 'no role', spec: 'claude/claude-opus-5:high' },
  { label: 'effort off the ladder', spec: 'agent=codex/gpt-5.6-sol:extreme' },
]

const USAGE = [
  'usage: hmz exec [-h] -f FLOW [-a ROLE=SPEC[,...]] [-e ROLE=SPEC[,...]]',
  '                [-p KEY=VALUE[,...]] [--profile] [--resume] [--json]',
  '                task',
]

interface Agent {
  role: string
  cli: Cli
  cliAs: string
  account: string
  model: string
  effort: string
}

interface Reading {
  agents: Agent[]
  error: string
  usage: boolean
}

const said = ref(EXAMPLES[0].spec)

function named(cli: string): Cli | undefined {
  return CLIS.find((one) => one.aliases.includes(cli))
}

function takes(cli: Cli, effort: string): boolean {
  const rung = cli.swarms && effort.startsWith('swarm') ? effort.slice('swarm'.length) : effort
  return !rung || rung === 'auto' || cli.efforts.includes(rung)
}

function read(value: string): Reading {
  const refused = (error: string, usage = true): Reading => ({ agents: [], error, usage })
  // A comma starts the next agent only where a role and `=` follow it.
  const items = value.split(/,\s*(?=[A-Za-z_][\p{L}\p{N}_-]*=)/u)
  const agents: Agent[] = []
  for (const item of items) {
    if (!item.trim()) return refused(`-a '${value}': an item is empty`)
    const one = item.trim()
    const at = one.indexOf('=')
    const role = at < 0 ? '' : one.slice(0, at).trim()
    const rest = at < 0 ? '' : one.slice(at + 1)
    if (at < 0 || !role) {
      return refused(`-a '${one}': expected <role>=<harness>[@<provider>]/<model>[:<effort>]`)
    }
    // Python's `str.isidentifier`, near enough: a letter or `_`, then letters, digits, `_`.
    if (!/^[\p{L}_][\p{L}\p{N}_]*$/u.test(role)) {
      return refused(
        `-a '${one}': '${role}' is not a place a flow could declare: what is written before ` +
          '`=` is a field of the tuple of agents the flow declares, so it is a Python identifier',
      )
    }
    if (rest.includes(',')) {
      return refused(`-a '${one}': expected one agent: a \`,\` separates several, each read on its own`)
    }
    // Read from both ends: the CLI up to the first slash, the effort after the last colon --
    // where that is spelled as one. Otherwise the colon is the model's, as in
    // `custom_provider:gateway/m`, and the agent is at no effort.
    const slash = rest.indexOf('/')
    const head = slash < 0 ? rest : rest.slice(0, slash)
    const tail = slash < 0 ? '' : rest.slice(slash + 1)
    const colon = tail.lastIndexOf(':')
    const after = colon < 0 ? '' : tail.slice(colon + 1).trim()
    const parted = colon >= 0 && (!after || /^[A-Za-z]+(?:[-_ ][A-Za-z]+)*$/.test(after))
    const model = (parted ? tail.slice(0, colon) : tail).trim()
    const effort = parted ? after : ''
    const monkey = head.indexOf('@')
    const cliAs = (monkey < 0 ? head : head.slice(0, monkey)).trim()
    const account = monkey < 0 ? '' : head.slice(monkey + 1).trim()
    if (monkey >= 0 && !account) {
      return refused(`-a '${one}': expected an account after @, as in claude@deepseek/MODEL:EFFORT`)
    }
    const cli = named(cliAs)
    if (!cli || !model) return refused(`-a '${one}': expected [NAME=]CLI[@PROVIDER]/MODEL[:EFFORT]`)
    if (agents.some((other) => other.role === role)) {
      return refused(`-a: the role '${role}' is given twice`)
    }
    agents.push({ role, cli, cliAs, account, model, effort: effort === 'auto' ? '' : effort })
  }
  // Read, and then checked against each CLI's ladder as the run is set up: no usage line.
  for (const one of agents) {
    if (!takes(one.cli, one.effort)) {
      const account = one.account ? `@${one.account}` : ''
      return refused(
        `${one.role}=${one.cli.name}${account}/${one.model}:${one.effort}: ${one.cli.name} cannot ` +
          `be asked to think at '${one.effort}'; expected one of ${one.cli.efforts.join(', ')}`,
        false,
      )
    }
  }
  return { agents, error: '', usage: false }
}

const reading = computed(() => read(said.value))

/* ----------------------------------------------------------------------------------------------
   The motion. Nothing above reads any of it: the reading is the same with or without.
   ---------------------------------------------------------------------------------------------- */

type Timeline = gsap.core.Timeline
const PARTS = ['role', 'cli', 'account', 'model', 'effort'] as const

const root = ref<HTMLElement | null>(null)
// How much of the refusal has typed on, or null when all of it shows.
const typed = ref<number | null>(null)
const typedError = computed(() => (typed.value === null ? reading.value.error : reading.value.error.slice(0, typed.value)))

let reduced = true
let seen = false
let picked = false
let tl: Timeline | null = null
let io: IntersectionObserver | null = null
let ghosts: HTMLElement[] = []

function all(sel: string, from: ParentNode | null | undefined = root.value): HTMLElement[] {
  return from ? Array.from(from.querySelectorAll<HTMLElement>(sel)) : []
}

function pick(spec: string): void {
  picked = said.value !== spec
  said.value = spec
}

/** Fit every brace to the word it names: the words change width as they are typed. */
function shape(): void {
  for (const part of all('.part')) {
    const word = part.querySelector<HTMLElement>('.p')
    const svg = part.querySelector('svg')
    const path = part.querySelector('path')
    if (!word || !svg || !path) continue
    const w = Math.max(word.offsetWidth, 8)
    svg.setAttribute('width', String(w))
    svg.setAttribute('viewBox', `0 0 ${w} 11`)
    path.setAttribute('d', braceD({ x: 1, y: 1.5 }, { x: w - 1, y: 1.5 }, 8))
  }
}

function settle(): void {
  if (tl) tl.progress(1, true).kill()
  tl = null
  for (const one of ghosts) {
    motion().killTweensOf(one)
    one.remove()
  }
  ghosts = []
  if (root.value) motion().set(all('dt'), { autoAlpha: 1 })
  typed.value = null
}

/** A band of the row's colour sweeps across it and fades: this row was just written. */
function sweep(t: Timeline, row: Element, at: number): void {
  const band = row.querySelector('.band')
  if (!band) return
  t.fromTo(band, { scaleX: 0, autoAlpha: 1 }, { scaleX: 1, duration: 0.45, ease: 'cine.out' }, at)
  t.to(band, { autoAlpha: 0, duration: 0.6, ease: 'power1.out' }, at + 0.4)
}

/** Each brace's name lifts off and flies down to the head of its row. */
function fly(agent: HTMLElement): void {
  const g = motion()
  const box = root.value?.getBoundingClientRect()
  if (!box) return
  all('.part', agent).forEach((part, k) => {
    const kind = PARTS.find((one) => part.classList.contains(one))
    const name = part.querySelector<HTMLElement>('.name')
    const head = agent.querySelector<HTMLElement>(`dl > .${kind} dt`)
    if (!kind || !name || !head) return
    const a = name.getBoundingClientRect()
    const b = head.getBoundingClientRect()
    const ghost = document.createElement('span')
    ghost.className = `spec-ghost ${kind}`
    ghost.textContent = name.textContent
    ghost.setAttribute('aria-hidden', 'true')
    Object.assign(ghost.style, { color: `var(--hmz-lane-${PARTS.indexOf(kind) + 1})`, left: `${a.left - box.left}px`, top: `${a.top - box.top}px` })
    root.value?.appendChild(ghost)
    ghosts.push(ghost)
    g.to(ghost, {
      x: b.left - a.left,
      y: b.top - a.top,
      fontSize: 12,
      duration: 0.6,
      delay: k * 0.08,
      ease: 'cine',
      onComplete: () => {
        g.set(head, { autoAlpha: 1 })
        ghost.remove()
        ghosts = ghosts.filter((one) => one !== ghost)
      },
    })
  })
}

/** The whole reading, from the spelled-out value down to its rows. */
function enter(): Timeline {
  const t = motion().timeline()
  all('.agent').forEach((agent, i) => {
    const at = i * 0.35
    const spelled = agent.querySelector<HTMLElement>('.spelled')
    const gap = spelled ? getComputedStyle(spelled).columnGap : '0px'
    const rows = all('dl > div', agent)
    const fall = at + 1.05
    t.set(all('dt, dd, .band', agent), { autoAlpha: 0 }, 0)
    if (spelled) t.fromTo(spelled, { columnGap: 0 }, { columnGap: gap, duration: 0.7, ease: 'cine', clearProps: 'columnGap' }, at)
    rise(t, all('.p', agent), at, { y: 8, stagger: 0.05, duration: 0.5 })
    t.fromTo(all('.sep', agent), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3, stagger: 0.05 }, at + 0.1)
    draw(t, all('.brace path', agent), at + 0.4, { duration: 0.5, stagger: 0.08, ease: 'cine.out' })
    rise(t, all('.name', agent), at + 0.55, { y: -5, stagger: 0.08, duration: 0.4 })
    t.call(() => fly(agent), [], fall)
    rows.forEach((row, k) => {
      const land = fall + k * 0.08 + 0.6
      // A row with no part to fly from (no account) shows its head as it is reached.
      if (!agent.querySelector(`.part.${PARTS[k]}`)) t.to(row.querySelector('dt'), { autoAlpha: 1, duration: 0.3 }, land - 0.2)
      t.fromTo(row.querySelector('dd'), { autoAlpha: 0, x: -14 }, { autoAlpha: 1, x: 0, duration: 0.5 }, land - 0.1)
      sweep(t, row, land - 0.15)
    })
    // Whatever the flight left undone, every head is there at the end.
    t.set(all('dt', agent), { autoAlpha: 1 }, fall + rows.length * 0.08 + 0.7)
  })
  return t
}

/** Refused: the whole reply jolts, the usage lines rise, and the error types on. */
function refuse(): Timeline {
  const t = motion().timeline()
  const error = reading.value.error
  const count = { n: 0 }
  t.set(all('.refused .status'), { autoAlpha: 0 }, 0)
  shake(t, all('.refused'), 0, 8)
  rise(t, all('.refused .dim'), 0.05, { y: 6, stagger: 0.06, duration: 0.4 })
  t.call(() => {
    typed.value = 0
  }, [], 0)
  t.to(
    count,
    {
      n: error.length,
      duration: Math.min(1.6, 0.25 + error.length * 0.012),
      ease: 'none',
      onUpdate: () => {
        typed.value = Math.round(count.n)
      },
      onComplete: () => {
        typed.value = null
      },
    },
    0.2,
  )
  t.to(all('.refused .status'), { autoAlpha: 1, duration: 0.4 }, '>-0.05')
  return t
}

/** Typed into: only the parts whose words changed are named again. */
function touch(t: Timeline, i: number, kinds: string[]): void {
  const agent = all('.agent')[i]
  if (!agent) return
  for (const kind of kinds) {
    const part = agent.querySelector(`.part.${kind}`)
    if (part) {
      draw(t, part.querySelector('.brace path'), 0, { duration: 0.35, ease: 'cine.out' })
      t.fromTo(part.querySelector('.p'), { y: -3 }, { y: 0, duration: 0.35, ease: 'back.out(3)' }, 0)
    }
    const row = agent.querySelector(`dl > .${kind}`)
    if (row) sweep(t, row, 0.05)
  }
}

function partsOf(one: Agent): Record<string, string> {
  return { role: one.role, cli: one.cliAs, account: one.account, model: one.model, effort: one.effort || 'auto' }
}

watch(
  reading,
  (now, before) => {
    const wasPicked = picked
    picked = false
    shape()
    if (reduced || !seen) return
    settle()
    if (now.error) {
      if (!before.error || wasPicked) tl = refuse()
    } else if (before.error || wasPicked || before.agents.length !== now.agents.length) {
      tl = enter()
    } else {
      const t = motion().timeline()
      now.agents.forEach((one, i) => {
        const was = partsOf(before.agents[i])
        const is = partsOf(one)
        touch(t, i, PARTS.filter((kind) => was[kind] !== is[kind]))
      })
      tl = t
    }
  },
  { flush: 'post' },
)

onMounted(async () => {
  await nextTick()
  await document.fonts?.ready
  shape()
  reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduced || !root.value) return
  // Held at its first frame until it is scrolled to, then read out once.
  tl = (reading.value.error ? refuse() : enter()).pause(0)
  io = new IntersectionObserver(
    (entries) => {
      if (!entries.some((one) => one.isIntersecting)) return
      seen = true
      io?.disconnect()
      tl?.play()
    },
    { threshold: 0.35 },
  )
  io.observe(root.value)
})

onBeforeUnmount(() => {
  io?.disconnect()
  settle()
})
</script>

<template>
  <div ref="root" class="spec hmz-panel">
    <div class="top">
      <strong>How <code>-a</code> is read</strong>
      <span class="sim">a simulation, in your browser · built-in CLIs only</span>
    </div>

    <label class="line">
      <span class="flag">-a</span>
      <input
        v-model="said"
        type="text"
        spellcheck="false"
        autocomplete="off"
        autocapitalize="off"
        aria-label="an -a value to read"
      />
    </label>

    <div class="tries" role="group" aria-label="examples">
      <button
        v-for="one in EXAMPLES"
        :key="one.label"
        type="button"
        :class="{ on: said === one.spec }"
        @click="pick(one.spec)"
      >
        {{ one.label }}
      </button>
    </div>

    <div v-if="reading.error" class="refused" aria-live="polite">
      <template v-if="reading.usage">
        <div v-for="line in USAGE" :key="line" class="dim">{{ line }}</div>
      </template>
      <div class="err">
        <span class="sr">hmz exec: error: {{ reading.error }}</span>
        <span aria-hidden="true">hmz exec: error: {{ typedError }}</span><span v-if="typed !== null" class="caret" aria-hidden="true" />
      </div>
      <div class="status">refused before any agent starts · exit status 2</div>
    </div>

    <div v-else class="agents" aria-live="polite">
      <div v-for="(one, i) in reading.agents" :key="i" class="agent">
        <div class="spelled">
          <span class="part role"><span class="p">{{ one.role }}</span><svg class="brace" height="11" aria-hidden="true"><path /></svg><span class="name" aria-hidden="true">role</span></span>
          <span class="sep">=</span>
          <span class="part cli"><span class="p">{{ one.cliAs }}</span><svg class="brace" height="11" aria-hidden="true"><path /></svg><span class="name" aria-hidden="true">CLI</span></span>
          <template v-if="one.account">
            <span class="sep">@</span>
            <span class="part account"><span class="p">{{ one.account }}</span><svg class="brace" height="11" aria-hidden="true"><path /></svg><span class="name" aria-hidden="true">account</span></span>
          </template>
          <span class="sep">/</span>
          <span class="part model"><span class="p">{{ one.model }}</span><svg class="brace" height="11" aria-hidden="true"><path /></svg><span class="name" aria-hidden="true">model</span></span>
          <span class="sep">:</span>
          <span class="part effort"><span class="p">{{ one.effort || 'auto' }}</span><svg class="brace" height="11" aria-hidden="true"><path /></svg><span class="name" aria-hidden="true">effort</span></span>
        </div>
        <dl>
          <div class="role">
            <span class="band" aria-hidden="true" />
            <dt>role</dt>
            <dd><code>{{ one.role }}</code> — must be a role the flow declares</dd>
          </div>
          <div class="cli">
            <span class="band" aria-hidden="true" />
            <dt>CLI</dt>
            <dd>{{ one.cli.title }}<span v-if="one.cliAs !== one.cli.name"> (<code>{{ one.cli.name }}</code>)</span></dd>
          </div>
          <div class="account">
            <span class="band" aria-hidden="true" />
            <dt>account</dt>
            <dd v-if="one.account"><code>{{ one.account }}</code>, made in <code>/settings</code></dd>
            <dd v-else>none — the CLI as this machine is signed in</dd>
          </div>
          <div class="model">
            <span class="band" aria-hidden="true" />
            <dt>model</dt>
            <dd><code>{{ one.model }}</code> — passed to the CLI as written</dd>
          </div>
          <div class="effort">
            <span class="band" aria-hidden="true" />
            <dt>effort</dt>
            <dd v-if="one.effort">
              <code>{{ one.effort }}</code> — on {{ one.cli.name }}'s ladder:
              {{ one.cli.efforts.join(', ') }}<span v-if="one.cli.swarms">, each also as <code>swarm…</code></span>
            </dd>
            <dd v-else>none asked for — the CLI's own default</dd>
          </div>
        </dl>
      </div>
    </div>
  </div>
</template>

<style scoped>
.spec {
  position: relative;
  padding: 16px 18px 18px;
  font-size: 14px;
}

.top {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px 12px;
  margin-bottom: 12px;
}

.sim {
  color: var(--vp-c-text-3);
  font-size: 12px;
}

.line {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
}

.line:focus-within {
  border-color: var(--vp-c-brand-1);
}

.flag {
  color: var(--vp-c-text-3);
}

.line input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--vp-c-text-1);
  font: inherit;
  font-size: 14px;
  outline: none;
}

.tries {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0 14px;
}

.tries button {
  padding: 2px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  color: var(--vp-c-text-2);
  font-size: 12px;
  line-height: 22px;
}

.tries button:hover {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}

.tries button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.refused {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  line-height: 1.6;
  overflow-x: auto;
}

.refused .dim {
  color: var(--vp-c-text-3);
  white-space: pre;
}

.refused .err {
  color: var(--vp-c-danger-1);
  overflow-wrap: anywhere;
}

.refused .status {
  margin-top: 6px;
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-base);
  font-size: 12px;
}

.agents {
  display: grid;
  gap: 12px;
}

.agent {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--vp-c-bg);
}

.spelled {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  column-gap: 5px;
  row-gap: 6px;
  margin-bottom: 10px;
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  line-height: 22px;
}

.sep {
  color: var(--vp-c-text-3);
}

/* A part of the value, the brace under it, and the brace's name. */
.part {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  min-width: 0;
  max-width: 100%;
}

.p {
  display: block;
  max-width: 100%;
  padding: 0 3px;
  border-radius: 4px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.brace {
  display: block;
  overflow: visible;
}

.brace path {
  fill: none;
  stroke: var(--c);
  stroke-width: 1.4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.name {
  color: var(--c);
  font-family: var(--vp-font-family-base);
  font-size: 11px;
  font-weight: 600;
  line-height: 14px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* A name in flight from its brace to its row: outside the scoped tree, so not scoped. */
.spec :deep(.spec-ghost) {
  position: absolute;
  z-index: 2;
  font-family: var(--vp-font-family-base);
  font-size: 11px;
  font-weight: 600;
  line-height: 14px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  white-space: nowrap;
  pointer-events: none;
}

.refused .err .caret {
  display: inline-block;
  width: 0.55em;
  height: 1.1em;
  margin-left: 1px;
  vertical-align: text-bottom;
  background: var(--vp-c-danger-1);
  animation: caret 0.8s steps(1) infinite;
}

@keyframes caret {
  50% {
    opacity: 0;
  }
}

.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

dl > div {
  position: relative;
  isolation: isolate;
}

.band {
  position: absolute;
  inset: -2px -6px;
  z-index: -1;
  border-radius: 5px;
  background: linear-gradient(90deg, color-mix(in srgb, var(--c) 26%, transparent), color-mix(in srgb, var(--c) 6%, transparent));
  transform-origin: 0 50%;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
}

dl {
  display: grid;
  gap: 4px;
  margin: 0;
}

dl > div {
  display: grid;
  grid-template-columns: 5.5em 1fr;
  gap: 8px;
  align-items: baseline;
}

dt {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

dd {
  margin: 0;
  color: var(--vp-c-text-2);
  font-size: 13px;
  overflow-wrap: anywhere;
}

/* One colour per part, the same on the spelled-out line and on the row that explains it. */
.role {
  --c: var(--hmz-lane-1);
}

.cli {
  --c: var(--hmz-lane-2);
}

.account {
  --c: var(--hmz-lane-3);
}

.model {
  --c: var(--hmz-lane-4);
}

.effort {
  --c: var(--hmz-lane-5);
}

.p {
  color: var(--c);
  background: color-mix(in srgb, var(--c) 14%, transparent);
}

dt {
  color: var(--c);
}
</style>
