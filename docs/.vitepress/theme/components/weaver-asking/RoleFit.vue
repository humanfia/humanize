<script setup lang="ts">
// Which CLIs can fill a role, for the mixins it declares. The table is `HARNESS_AGENTS` in
// src/hmz/flows/agents.py, which is what `hmz exec` and `/flow` both check a role against;
// the refusal is the one `src/hmz/runtime/runner.py` raises for a CLI that lacks a mixin:
// the lacking mixins' names sorted and joined by ", ". Nothing here runs anything.
//
// Drawn as wiring: the mixins on the left, the CLIs on the right, and a wire from a mixin to
// every CLI that serves it. A mixin the role declares lights its wires; a CLI that every lit
// mixin reaches can fill the role; the CLI picked shows, in red, the wires it is missing.
// Hovering a CLI lights what it serves. The wires are measured off the buttons, so they are
// drawn only in a browser: on the server, and with scripts off, the buttons say it all.
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

interface Mixin {
  name: string
  short: string
  lets: string
}

interface Cli {
  cli: string
  serves: string[]
}

const MIXINS: Mixin[] = [
  { name: 'GoalCommandAgentMixin', short: 'Goal', lets: '/goal' },
  { name: 'LoopCommandAgentMixin', short: 'Loop', lets: '/loop' },
  { name: 'SteeringAgentMixin', short: 'Steering', lets: 'steer' },
  { name: 'PermissionRequestHookAgentMixin', short: 'PermissionRequest', lets: 'on_permission_request' },
  { name: 'SubagentStartHookAgentMixin', short: 'SubagentStart', lets: 'on_subagent_start' },
  { name: 'SubagentStopHookAgentMixin', short: 'SubagentStop', lets: 'on_subagent_stop' },
  { name: 'AskUserHookAgentMixin', short: 'AskUser', lets: 'on_ask_user' },
]

const G = 'GoalCommandAgentMixin'
const L = 'LoopCommandAgentMixin'
const S = 'SteeringAgentMixin'
const P = 'PermissionRequestHookAgentMixin'
const SS = 'SubagentStartHookAgentMixin'
const SE = 'SubagentStopHookAgentMixin'
const A = 'AskUserHookAgentMixin'

const CLIS: Cli[] = [
  { cli: 'claude', serves: [G, L, S, P, SS, SE, A] },
  { cli: 'codex', serves: [G, S, P, SS, SE, A] },
  { cli: 'kimi', serves: [G, S, P, A] },
  { cli: 'pi', serves: [S, A] },
  { cli: 'cursor-agent', serves: [SS, SE] },
  { cli: 'mcode', serves: [SS, SE] },
  { cli: 'dsh', serves: [G] },
  { cli: 'agy', serves: [] },
  { cli: 'grok', serves: [] },
  { cli: 'mimo', serves: [] },
  { cli: 'opencode', serves: [] },
  { cli: 'qwen', serves: [] },
  { cli: 'acp', serves: [] },
]

const declared = ref<string[]>([P])
const picked = ref('grok')
const hovered = ref<string | null>(null)

function toggle(name: string) {
  declared.value = declared.value.includes(name)
    ? declared.value.filter((one) => one !== name)
    : [...declared.value, name]
}

// A CLI added by hand has no name of its own here; `acp` is the harness it runs as.
function named(cli: Cli): string {
  return cli.cli === 'acp' ? 'an ACP CLI' : cli.cli
}

function lacking(cli: Cli): string[] {
  return declared.value.filter((one) => !cli.serves.includes(one)).sort()
}

const fitting = computed(() => CLIS.filter((cli) => lacking(cli).length === 0))
const chosen = computed(() => CLIS.find((cli) => cli.cli === picked.value) ?? CLIS[0])
const missing = computed(() => lacking(chosen.value))
// A CLI added by hand is written as whatever it was added as; `acp` is its harness.
const written = computed(() => (chosen.value.cli === 'acp' ? '<cli>' : chosen.value.cli))

const bases = computed(() => MIXINS.filter((one) => declared.value.includes(one.name)).map((one) => one.name))

// ---- the wiring ------------------------------------------------------------------------------

const board = ref<HTMLElement | null>(null)
const mixinEls = ref<HTMLElement[]>([])
const cliEls = ref<HTMLElement[]>([])
const size = ref({ w: 0, h: 0 })
const ends = ref<{ mixins: { x: number; y: number }[]; clis: { x: number; y: number }[] }>({ mixins: [], clis: [] })
let sized: ResizeObserver | undefined

function measure() {
  const at = board.value?.getBoundingClientRect()
  if (!at) return
  size.value = { w: at.width, h: at.height }
  ends.value = {
    mixins: mixinEls.value.map((el) => {
      const r = el.getBoundingClientRect()
      return { x: r.right - at.left, y: r.top + r.height / 2 - at.top }
    }),
    clis: cliEls.value.map((el) => {
      const r = el.getBoundingClientRect()
      return { x: r.left - at.left, y: r.top + r.height / 2 - at.top }
    }),
  }
}

onMounted(() => {
  measure()
  sized = new ResizeObserver(measure)
  if (board.value) sized.observe(board.value)
})
onUnmounted(() => sized?.disconnect())
// A ticked mixin is wider by its tick: the wires start where its button now ends.
watch(declared, () => void nextTick(measure))

interface Wire {
  key: string
  d: string
  tone: string
  state: 'idle' | 'on' | 'gap' | 'hover'
}

function curve(m: number, c: number): string {
  const a = ends.value.mixins[m]
  const b = ends.value.clis[c]
  if (!a || !b) return ''
  const mid = (a.x + b.x) / 2
  return `M${a.x + 4} ${a.y} C${mid} ${a.y} ${mid} ${b.y} ${b.x - 4} ${b.y}`
}

const wires = computed<Wire[]>(() => {
  if (!ends.value.mixins.length) return []
  const out: Wire[] = []
  MIXINS.forEach((mixin, m) => {
    const on = declared.value.includes(mixin.name)
    const tone = `var(--hmz-lane-${(m % 6) + 1})`
    CLIS.forEach((cli, c) => {
      const serves = cli.serves.includes(mixin.name)
      const looking = hovered.value === cli.cli
      if (serves) out.push({ key: `${m}-${c}-${on}`, d: curve(m, c), tone, state: on ? 'on' : looking ? 'hover' : 'idle' })
      else if (on && cli.cli === picked.value) out.push({ key: `gap-${m}-${c}`, d: curve(m, c), tone, state: 'gap' })
    })
  })
  // Lit wires last, so they are drawn over the faint ones.
  const rank = { idle: 0, hover: 1, on: 2, gap: 3 }
  return out.sort((a, b) => rank[a.state] - rank[b.state])
})
</script>

<template>
  <div class="fit hmz-panel">
    <div class="bar">
      <span class="what">Which CLIs can fill this role?</span>
      <span class="note">worked out from the table humanize checks roles against; nothing runs</span>
    </div>

    <div class="body">
      <pre class="decl"><code><span class="kw">class</span> Builder(Agent<TransitionGroup name="base"><span v-for="one in bases" :key="one" class="base">, {{ one }}</span></TransitionGroup>): ...</code></pre>

      <div ref="board" class="board">
        <svg v-if="size.w" class="wires" :viewBox="`0 0 ${size.w} ${size.h}`" aria-hidden="true">
          <path
            v-for="wire in wires"
            :key="wire.key"
            :d="wire.d"
            class="wire"
            :class="wire.state"
            :style="{ '--tone': wire.tone }"
            :pathLength="wire.state === 'on' ? 1 : undefined"
          />
        </svg>

        <div class="col mixins" role="group" aria-label="mixins the role declares">
          <p class="step">Tick what the role declares</p>
          <button
            v-for="(one, m) in MIXINS"
            :key="one.name"
            :ref="(el) => { if (el) mixinEls[m] = el as HTMLElement }"
            type="button"
            class="mixin"
            :class="{ on: declared.includes(one.name) }"
            :style="{ '--tone': `var(--hmz-lane-${(m % 6) + 1})` }"
            :aria-pressed="declared.includes(one.name)"
            :title="one.name"
            @click="toggle(one.name)"
          >
            <span class="tick" aria-hidden="true">{{ declared.includes(one.name) ? '✓' : '+' }}</span>
            {{ one.short }}
            <code>{{ one.lets }}</code>
          </button>
        </div>

        <div class="col clis" role="group" aria-label="CLIs">
          <p class="step"><strong class="count">{{ fitting.length }}</strong> of {{ CLIS.length }} can fill it</p>
          <button
            v-for="(cli, c) in CLIS"
            :key="cli.cli"
            :ref="(el) => { if (el) cliEls[c] = el as HTMLElement }"
            type="button"
            class="cli"
            :class="{ fits: lacking(cli).length === 0, picked: cli.cli === picked }"
            :aria-pressed="cli.cli === picked"
            @click="picked = cli.cli"
            @mouseenter="hovered = cli.cli"
            @mouseleave="hovered = null"
            @focus="hovered = cli.cli"
            @blur="hovered = null"
          >
            <span class="mark" aria-hidden="true">{{ lacking(cli).length === 0 ? '●' : '○' }}</span>
            {{ named(cli) }}
          </button>
        </div>
      </div>

      <p class="step">Pick a CLI to see what <code>hmz exec</code> says:</p>
      <div class="said" aria-live="polite">
        <Transition name="said" mode="out-in">
          <pre v-if="missing.length" :key="`no-${chosen.cli}-${missing.join()}`"><code><span class="dim">$ hmz exec -f gated -a builder={{ written }}/… …</span>
<span class="err">hmz exec: error: gated: 'builder' needs {{ missing.join(', ') }}, which {{ chosen.cli }} does not support</span></code></pre>
          <p v-else :key="`ok-${chosen.cli}`" class="ok">
            <strong>{{ named(chosen) }}</strong> can fill it. <code>hmz exec</code> takes it, and
            <code>/flow</code> offers it for this role.
          </p>
        </Transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fit {
  font-size: 14px;
}

.bar {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
}

.what {
  font-weight: 600;
  color: var(--vp-c-text-1);
}

.note {
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.body {
  padding: 12px 16px 16px;
}

.decl {
  margin: 0 0 12px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--vp-code-block-bg);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 13px;
  line-height: 1.5;
}

.decl code,
.said code {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
  background: none;
  padding: 0;
}

.base {
  display: inline;
  color: var(--vp-c-brand-1);
}

/* A base the role gains arrives lit, and the light fades into the line. */
.base-enter-active {
  transition: opacity 0.35s, background-color 1.2s;
  background: var(--vp-c-brand-soft);
}

.base-enter-from {
  opacity: 0;
}

.base-leave-active {
  transition: opacity 0.2s;
}

.base-leave-to {
  opacity: 0;
}

.kw {
  color: var(--vp-c-brand-1);
}

.step {
  margin: 8px 0 6px;
  color: var(--vp-c-text-2);
  line-height: 1.5;
}

/* ---- the board: two columns of buttons and the wires between them ---- */

.board {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(64px, 1fr) auto;
  align-items: start;
  margin: 4px -16px 6px;
  padding: 6px 16px 12px;
  background: var(--hmz-stage-bg);
  border-top: 1px solid var(--hmz-panel-border);
  border-bottom: 1px solid var(--hmz-panel-border);
}

.wires {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: visible;
}

.wire {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1;
  transition: stroke 0.25s, opacity 0.25s;
}

.wire.hover {
  stroke: var(--tone);
  stroke-width: 1.5;
  opacity: 0.6;
}

/* A mixin ticked: its wires draw themselves on, from the mixin out to every CLI it reaches. */
.wire.on {
  stroke: var(--tone);
  stroke-width: 2;
  stroke-dasharray: 1;
  animation: wire-draw 0.7s cubic-bezier(0.7, 0, 0.2, 1) both;
}

/* What the picked CLI is missing: a wire that is not there, drawn as a broken red one. */
.wire.gap {
  stroke: var(--vp-c-danger-1);
  stroke-width: 1.6;
  stroke-dasharray: 4 5;
  animation: wire-march 1s linear infinite;
}

.col {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.mixins {
  grid-column: 1;
  align-items: flex-start;
}

.clis {
  grid-column: 3;
  align-items: flex-end;
}

.col .step {
  margin: 4px 0 2px;
  font-size: 12.5px;
}

.count {
  display: inline-block;
  min-width: 1.2em;
  color: var(--hmz-accent);
  font-size: 15px;
}

button {
  font: inherit;
  cursor: pointer;
  border-radius: 999px;
  border: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg);
  color: var(--vp-c-text-2);
  padding: 3px 10px;
  transition:
    border-color 0.2s,
    background-color 0.2s,
    color 0.2s,
    opacity 0.25s,
    box-shadow 0.3s,
    transform 0.15s;
}

button:active {
  transform: scale(0.97);
}

button:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.mixin {
  white-space: nowrap;
}

.mixin code {
  font-size: 11px;
  margin-left: 4px;
  padding: 0 4px;
  color: var(--vp-c-text-3);
  background: var(--vp-c-default-soft);
}

.mixin .tick {
  display: inline-block;
  width: 1em;
  text-align: center;
  color: var(--vp-c-text-3);
}

.mixin.on {
  border-color: var(--tone);
  background: color-mix(in srgb, var(--tone) 14%, var(--vp-c-bg));
  color: var(--vp-c-text-1);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--tone) 18%, transparent);
}

.mixin.on .tick {
  color: var(--tone);
}

.cli {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  opacity: 0.5;
  text-decoration: line-through;
  text-decoration-color: var(--vp-c-text-3);
}

.cli .mark {
  font-size: 11px;
  margin-right: 2px;
  color: var(--vp-c-text-3);
}

.cli.fits {
  opacity: 1;
  text-decoration: none;
  color: var(--vp-c-text-1);
  border-color: var(--hmz-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--hmz-accent) 16%, transparent);
}

.cli.fits .mark {
  color: var(--hmz-accent);
}

.cli.picked {
  opacity: 1;
  outline: 2px solid var(--vp-c-text-2);
  outline-offset: 1px;
}

.said {
  min-height: 3.5em;
}

.said pre {
  margin: 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--vp-code-block-bg);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 12.5px;
  line-height: 1.55;
}

.said-enter-active,
.said-leave-active {
  transition: opacity 0.15s, transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.said-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.said-leave-to {
  opacity: 0;
}

.dim {
  color: var(--vp-c-text-3);
}

.err {
  color: var(--vp-c-danger-1);
}

.ok {
  margin: 0;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--hmz-accent);
  color: var(--vp-c-text-1);
  line-height: 1.5;
}

@keyframes wire-draw {
  from {
    stroke-dashoffset: 1;
  }
  to {
    stroke-dashoffset: 0;
  }
}

@keyframes wire-march {
  to {
    stroke-dashoffset: -18;
  }
}

@media (max-width: 480px) {
  .mixin code {
    display: none;
  }

  .board {
    grid-template-columns: auto minmax(28px, 1fr) auto;
  }

  .mixin,
  .cli {
    font-size: 12.5px;
    padding: 3px 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  button,
  .wire,
  .base-enter-active,
  .base-leave-active,
  .said-enter-active,
  .said-leave-active {
    transition: none;
  }

  .wire.on,
  .wire.gap {
    animation: none;
  }
}
</style>
