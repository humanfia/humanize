<script setup lang="ts">
// How `hmz exec` reads one `-a`, played in the browser: the role, the CLI, the account, the
// model and the effort, or the refusal it would print instead.
//
// A simulation, and it has to say what the code says. The reading is
// `hmz.runtime.flowing.specs.parse_agents` over `hmz.coganchor.backends.read`, the ladders
// are each profile's `efforts` in `hmz.coganchor.backends`, and every refusal below is the
// line `hmz exec` prints for it. It knows the twelve CLIs humanize ships and no CLI added at
// /providers, and it cannot know which roles a flow declares.
import { computed, ref } from 'vue'

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
  { name: 'zcode', title: 'ZCode', aliases: ['zcode', 'zcode-cli'], efforts: ['max', 'xhigh', 'high', 'medium', 'low', 'enabled', 'nothink', 'disabled'] },
  { name: 'cursor-agent', title: 'Cursor Agent', aliases: ['cursor-agent', 'cursor-cli'], efforts: ['max', 'xhigh', 'extra-high', 'high', 'medium', 'low', 'minimal', 'none'] },
]

const EXAMPLES = [
  { label: 'ralph_loop', spec: 'agent=claude/claude-opus-5:high' },
  { label: 'an account', spec: 'actor=claude@deepseek/claude-opus-5:high' },
  { label: 'two agents', spec: 'actor=claude/claude-opus-5:max,reviewer=codex/gpt-5.6-sol:high' },
  { label: 'slashes in the model', spec: 'agent=kimi/kimi-code/k3:swarmmax' },
  { label: 'no effort', spec: 'agent=claude/claude-opus-5:auto' },
  { label: 'no role', spec: 'claude/claude-opus-5:high' },
  { label: 'effort off the ladder', spec: 'agent=codex/gpt-5.6-sol:extreme' },
]

const USAGE = [
  'usage: hmz exec [-h] -f FLOW [-a ROLE=SPEC[,...]] [-e ROLE=SPEC[,...]]',
  '                [-p KEY=VALUE[,...]] [-b KEY=VALUE[,...]] [--resume] [--json]',
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
      return refused(`-a '${one}': expected <role>=<harness>[@<provider>]/<model>:<effort>`)
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
    // Read from both ends: the CLI up to the first slash, the effort after the last colon.
    const slash = rest.indexOf('/')
    const head = slash < 0 ? rest : rest.slice(0, slash)
    const tail = slash < 0 ? '' : rest.slice(slash + 1)
    const colon = tail.lastIndexOf(':')
    const model = (colon < 0 ? '' : tail.slice(0, colon)).trim()
    const effort = (colon < 0 ? tail : tail.slice(colon + 1)).trim()
    const monkey = head.indexOf('@')
    const cliAs = (monkey < 0 ? head : head.slice(0, monkey)).trim()
    const account = monkey < 0 ? '' : head.slice(monkey + 1).trim()
    if (monkey >= 0 && !account) {
      return refused(`-a '${one}': expected an account after @, as in claude@deepseek/MODEL:EFFORT`)
    }
    const cli = named(cliAs)
    if (!cli || !model) return refused(`-a '${one}': expected [NAME=]CLI[@PROVIDER]/MODEL:EFFORT`)
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
</script>

<template>
  <div class="spec hmz-panel">
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
        @click="said = one.spec"
      >
        {{ one.label }}
      </button>
    </div>

    <div v-if="reading.error" class="refused" aria-live="polite">
      <template v-if="reading.usage">
        <div v-for="line in USAGE" :key="line" class="dim">{{ line }}</div>
      </template>
      <div class="err">hmz exec: error: {{ reading.error }}</div>
      <div class="status">refused before any agent starts · exit status 2</div>
    </div>

    <div v-else class="agents" aria-live="polite">
      <div v-for="one in reading.agents" :key="one.role" class="agent">
        <div class="spelled">
          <span class="p role">{{ one.role }}</span><span class="sep">=</span><span class="p cli">{{ one.cliAs }}</span><template v-if="one.account"><span class="sep">@</span><span class="p account">{{ one.account }}</span></template><span class="sep">/</span><span class="p model">{{ one.model }}</span><span class="sep">:</span><span class="p effort">{{ one.effort || 'auto' }}</span>
        </div>
        <dl>
          <div class="role">
            <dt>role</dt>
            <dd><code>{{ one.role }}</code> — must be a role the flow declares</dd>
          </div>
          <div class="cli">
            <dt>CLI</dt>
            <dd>{{ one.cli.title }}<span v-if="one.cliAs !== one.cli.name"> (<code>{{ one.cli.name }}</code>)</span></dd>
          </div>
          <div class="account">
            <dt>account</dt>
            <dd v-if="one.account"><code>{{ one.account }}</code>, made at <code>/providers</code></dd>
            <dd v-else>none — the CLI as this machine is signed in</dd>
          </div>
          <div class="model">
            <dt>model</dt>
            <dd><code>{{ one.model }}</code> — passed to the CLI as written</dd>
          </div>
          <div class="effort">
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
  margin-bottom: 8px;
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  overflow-wrap: anywhere;
}

.sep {
  color: var(--vp-c-text-3);
}

.p {
  padding: 1px 3px;
  border-radius: 4px;
  font-weight: 600;
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
