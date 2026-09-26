<script setup lang="ts">
// Which CLIs can fill a role, for the mixins it declares. The table is `HARNESS_AGENTS` in
// src/hmz/flows/agents.py, which is what `hmz exec` and `/flow` both check a role against;
// the refusal is the one `src/hmz/runtime/runner.py` raises for a CLI that lacks a mixin:
// the lacking mixins' names sorted and joined by ", ". Nothing here runs anything.
import { computed, ref } from 'vue'

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
  { cli: 'zcode', serves: [G, P, A] },
  { cli: 'pi', serves: [S, A] },
  { cli: 'cursor-agent', serves: [SS, SE] },
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

const bases = computed(() => {
  const ordered = MIXINS.filter((one) => declared.value.includes(one.name)).map((one) => one.name)
  return ['Agent', ...ordered].join(', ')
})
</script>

<template>
  <div class="fit hmz-panel">
    <div class="bar">
      <span class="what">Which CLIs can fill this role?</span>
      <span class="note">worked out from the table humanize checks roles against; nothing runs</span>
    </div>

    <div class="body">
      <pre class="decl"><code><span class="kw">class</span> Builder({{ bases }}): ...</code></pre>

      <p class="step">Tick what the role declares:</p>
      <div class="mixins" role="group" aria-label="mixins the role declares">
        <button
          v-for="one in MIXINS"
          :key="one.name"
          type="button"
          class="mixin"
          :class="{ on: declared.includes(one.name) }"
          :aria-pressed="declared.includes(one.name)"
          :title="one.name"
          @click="toggle(one.name)"
        >
          <span class="tick" aria-hidden="true">{{ declared.includes(one.name) ? '✓' : '+' }}</span>
          {{ one.short }}
          <code>{{ one.lets }}</code>
        </button>
      </div>

      <p class="step">
        <strong>{{ fitting.length }}</strong> of {{ CLIS.length }} can fill it. Pick one to see what
        <code>hmz exec</code> says:
      </p>
      <div class="clis" role="group" aria-label="CLIs">
        <button
          v-for="cli in CLIS"
          :key="cli.cli"
          type="button"
          class="cli"
          :class="{ fits: lacking(cli).length === 0, picked: cli.cli === picked }"
          :aria-pressed="cli.cli === picked"
          @click="picked = cli.cli"
        >
          {{ named(cli) }}
        </button>
      </div>

      <div class="said" aria-live="polite">
        <template v-if="missing.length">
          <pre><code><span class="dim">$ hmz exec -f gated -a builder={{ written }}/… …</span>
<span class="err">hmz exec: error: gated: 'builder' needs {{ missing.join(', ') }}, which {{ chosen.cli }} does not do</span></code></pre>
        </template>
        <p v-else class="ok">
          <strong>{{ named(chosen) }}</strong> can fill it. <code>hmz exec</code> takes it, and
          <code>/flow</code> offers it for this role.
        </p>
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

.kw {
  color: var(--vp-c-brand-1);
}

.step {
  margin: 8px 0 6px;
  color: var(--vp-c-text-2);
  line-height: 1.5;
}

.mixins,
.clis {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
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
    opacity 0.2s;
}

button:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
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
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-text-1);
}

.mixin.on .tick {
  color: var(--vp-c-brand-1);
}

.cli {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  opacity: 0.55;
  text-decoration: line-through;
  text-decoration-color: var(--vp-c-text-3);
}

.cli.fits {
  opacity: 1;
  text-decoration: none;
  color: var(--vp-c-text-1);
  border-color: var(--hmz-accent);
}

.cli.picked {
  opacity: 1;
  outline: 2px solid var(--vp-c-text-2);
  outline-offset: 1px;
}

.said {
  margin-top: 12px;
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

.mixin {
  white-space: nowrap;
}

@media (max-width: 480px) {
  .mixin code {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  button {
    transition: none;
  }
}
</style>
