<script setup lang="ts">
// Every way into each backend, as `/providers` offers them once `a` has been told which CLI.
// Read off the `ways` of each profile in `src/hmz/coganchor/backends.py`, in the order the
// backends are listed there, plus `env` -- which `ways()` in
// `src/hmz/coganchor/providers/store.py` adds to every backend but dsh, and which is the only
// way into a CLI of your own once `_speaks` in `src/hmz/tui/pick.py` has added it. `runs` is
// the way's `argv`, `asks` its `Asked`s, `sets` its `sets`. A way with a command of its own
// hands that command the terminal; one without is only answers. A way changed in
// `backends.py` is a way to change here.
import { computed, ref } from 'vue'

interface Asked {
  env: string
  secret?: boolean
  fixed?: string
}

interface Way {
  name: string
  about: string
  runs?: string
  asks?: Asked[]
  sets?: string[]
  typed?: boolean
}

interface Backend {
  cli: string
  called: string
  ways: Way[]
  // Not a backend yet: the last row of the list `a` shows, which adds one.
  own?: boolean
  // Said under its ways, for a backend whose list is not the usual one.
  note?: string
}

const ENV: Way = {
  name: 'env',
  about: 'variables of your own: whatever this CLI reads a key or an endpoint under',
  typed: true,
}

const GATEWAY = 'an endpoint speaking this CLI’s own protocol: a proxy, a router, another vendor'
const BROWSERLESS = 'the same, from a machine with no browser on it'

const BACKENDS: Backend[] = [
  {
    cli: 'claude',
    called: 'Claude Code',
    ways: [
      { name: 'login', about: 'sign in to an Anthropic account', runs: 'claude auth login' },
      {
        name: 'token',
        about: 'a long-lived token, as claude setup-token prints one',
        asks: [{ env: 'CLAUDE_CODE_OAUTH_TOKEN', secret: true }],
      },
      {
        name: 'key',
        about: 'an Anthropic API key, from the console',
        asks: [{ env: 'ANTHROPIC_API_KEY', secret: true }],
      },
      {
        name: 'gateway',
        about: GATEWAY,
        asks: [{ env: 'ANTHROPIC_BASE_URL' }, { env: 'ANTHROPIC_AUTH_TOKEN', secret: true }],
      },
      {
        name: 'bedrock',
        about: 'Anthropic’s models on an AWS account of yours',
        asks: [{ env: 'AWS_PROFILE' }, { env: 'AWS_REGION', fixed: 'us-east-1' }],
        sets: ['CLAUDE_CODE_USE_BEDROCK=1'],
      },
      {
        name: 'vertex',
        about: 'Anthropic’s models on a Google Cloud project of yours',
        asks: [{ env: 'ANTHROPIC_VERTEX_PROJECT_ID' }, { env: 'CLOUD_ML_REGION', fixed: 'us-east5' }],
        sets: ['CLAUDE_CODE_USE_VERTEX=1'],
      },
      ENV,
    ],
  },
  {
    cli: 'agy',
    called: 'Antigravity',
    ways: [
      { name: 'login', about: 'sign in to a Google account, in a session opened for it', runs: 'agy' },
      {
        name: 'key',
        about: 'a Gemini API key, from AI Studio',
        asks: [{ env: 'GEMINI_API_KEY', secret: true }],
      },
      {
        name: 'adc',
        about: 'Google Application Default Credentials, for a service account',
        asks: [{ env: 'GOOGLE_APPLICATION_CREDENTIALS' }],
        sets: ['AGY_ADC_AUTH=1'],
      },
      ENV,
    ],
  },
  {
    cli: 'codex',
    called: 'Codex',
    ways: [
      { name: 'login', about: 'sign in to a ChatGPT account, in a browser', runs: 'codex login' },
      { name: 'device', about: BROWSERLESS, runs: 'codex login --device-auth' },
      {
        name: 'key',
        about: 'an OpenAI API key, which codex keeps in its own store',
        asks: [{ env: 'OPENAI_API_KEY', secret: true }],
        runs: 'codex login --with-api-key',
      },
      {
        name: 'token',
        about: 'an access token, which is how an organisation hands one out',
        asks: [{ env: 'CODEX_ACCESS_TOKEN', secret: true }],
        runs: 'codex login --with-access-token',
      },
      {
        name: 'gateway',
        about: GATEWAY,
        asks: [{ env: 'CODEX_PROVIDER_URL' }, { env: 'CODEX_PROVIDER_KEY', secret: true }],
      },
      ENV,
    ],
  },
  {
    cli: 'dsh',
    called: 'DeepSeek Harness',
    note: 'No env way here: DeepSeek Harness takes only its own key and gateway.',
    ways: [
      {
        name: 'key',
        about: 'a DeepSeek API key, from the platform',
        asks: [{ env: 'DEEPSEEK_API_KEY', secret: true }],
      },
      {
        name: 'gateway',
        about: GATEWAY,
        asks: [{ env: 'DEEPSEEK_BASE_URL' }, { env: 'DEEPSEEK_API_KEY', secret: true }],
      },
    ],
  },
  {
    cli: 'grok',
    called: 'Grok Build',
    ways: [
      { name: 'login', about: 'sign in to an xAI account, in a browser', runs: 'grok login' },
      { name: 'device', about: BROWSERLESS, runs: 'grok login --device-auth' },
      {
        name: 'key',
        about: 'an xAI API key, from the console',
        asks: [{ env: 'XAI_API_KEY', secret: true }],
      },
      {
        name: 'gateway',
        about: GATEWAY,
        asks: [{ env: 'GROK_XAI_API_BASE_URL' }, { env: 'XAI_API_KEY', secret: true }],
      },
      {
        name: 'oidc',
        about: 'your own identity provider, for an organisation that signs in through one',
        asks: [{ env: 'GROK_OIDC_ISSUER' }, { env: 'GROK_OIDC_CLIENT_ID' }],
      },
      ENV,
    ],
  },
  {
    cli: 'kimi',
    called: 'Kimi Code',
    ways: [
      { name: 'login', about: 'sign in to a Kimi account, by the code it prints', runs: 'kimi login' },
      {
        name: 'model',
        about: GATEWAY,
        asks: [
          { env: 'KIMI_MODEL_NAME' },
          { env: 'KIMI_MODEL_API_KEY', secret: true },
          { env: 'KIMI_MODEL_BASE_URL' },
          { env: 'KIMI_MODEL_PROVIDER_TYPE', fixed: 'openai' },
        ],
      },
      ENV,
    ],
  },
  {
    cli: 'pi',
    called: 'pi',
    ways: [{ name: 'login', about: 'pi’s own /login, in a session opened for it', runs: 'pi' }, ENV],
  },
  {
    cli: 'qwen',
    called: 'Qwen Code',
    ways: [
      { name: 'login', about: 'sign in to a Qwen account, in a session opened for it', runs: 'qwen' },
      {
        name: 'key',
        about: 'a key for the OpenAI-compatible endpoint it runs against',
        asks: [
          { env: 'OPENAI_API_KEY', secret: true },
          { env: 'OPENAI_BASE_URL', fixed: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
        ],
      },
      ENV,
    ],
  },
  {
    cli: 'opencode',
    called: 'opencode',
    ways: [
      {
        name: 'login',
        about: 'opencode’s own provider list, and whichever way that one takes',
        runs: 'opencode auth login',
      },
      {
        name: 'wellknown',
        about: 'a provider that hands out its own credential, by URL',
        asks: [{ env: 'OPENCODE_WELLKNOWN' }],
        runs: 'opencode auth login <url>',
      },
      {
        name: 'zen',
        about: 'an OpenCode Zen key, which its own models run on',
        asks: [{ env: 'OPENCODE_API_KEY', secret: true }],
      },
      ENV,
    ],
  },
  {
    cli: 'mimo',
    called: 'mimocode',
    ways: [
      {
        name: 'login',
        about: 'mimocode’s own provider list, and whichever way that one takes',
        runs: 'mimo auth login',
      },
      {
        name: 'key',
        about: 'a MiMo key, which its own models run on',
        asks: [{ env: 'XIAOMI_API_KEY', secret: true }],
      },
      ENV,
    ],
  },
  {
    cli: 'zcode',
    called: 'ZCode',
    ways: [
      { name: 'login', about: 'sign in to a Z.AI account, in a browser', runs: 'zcode login' },
      { name: 'device', about: BROWSERLESS, runs: 'zcode login --no-browser' },
      {
        name: 'key',
        about: 'a Z.AI or BigModel coding plan key, which its own models run on',
        asks: [{ env: 'ZCODE_API_KEY', secret: true }],
      },
      {
        name: 'gateway',
        about: GATEWAY,
        asks: [{ env: 'ZCODE_BASE_URL' }, { env: 'ZCODE_API_KEY', secret: true }],
      },
      ENV,
    ],
  },
  {
    cli: 'cursor-agent',
    called: 'Cursor Agent',
    ways: [
      { name: 'login', about: 'sign in to a Cursor account, in a browser', runs: 'cursor-agent login' },
      {
        name: 'key',
        about: 'a Cursor API key, from the dashboard',
        asks: [{ env: 'CURSOR_API_KEY', secret: true }],
      },
      {
        name: 'gateway',
        about: GATEWAY,
        asks: [{ env: 'CURSOR_API_ENDPOINT' }, { env: 'CURSOR_API_KEY', secret: true }],
      },
      ENV,
    ],
  },
  {
    cli: 'a CLI of your own',
    called: 'A CLI that speaks ACP',
    own: true,
    note:
      'Choosing this row asks for the command that starts your CLI, and adds it as a ' +
      'backend. From then on it is listed under its own name, and env is its way in.',
    ways: [ENV],
  },
]

const chosen = ref(BACKENDS[0].cli)
const open = computed(() => BACKENDS.find((one) => one.cli === chosen.value) ?? BACKENDS[0])
</script>

<template>
  <div class="ways hmz-panel">
    <div class="bar">
      <span class="lab">sign in to</span>
      <div class="clis" role="group" aria-label="choose a coding agent CLI">
        <button
          v-for="one in BACKENDS"
          :key="one.cli"
          type="button"
          :aria-pressed="chosen === one.cli"
          :class="{ on: chosen === one.cli, own: one.own }"
          @click="chosen = one.cli"
        >
          {{ one.cli }}
        </button>
      </div>
    </div>

    <div class="list">
      <p class="head" aria-live="polite">
        <strong>{{ open.called }}</strong>
        <span>{{ open.ways.length }} {{ open.ways.length === 1 ? 'way' : 'ways' }} in</span>
      </p>
      <p v-if="open.own" class="note">{{ open.note }}</p>
      <div v-for="way in open.ways" :key="way.name" class="way">
        <code class="name">{{ way.name }}</code>
        <div class="said">
          <p class="about">{{ way.about }}</p>
          <p class="does">
            <template v-if="way.asks">
              <span class="kind asks">asks</span>
              <span
                v-for="one in way.asks"
                :key="one.env"
                class="var"
                :class="{ secret: one.secret }"
                >{{ one.env }}<em v-if="one.secret"> · secret</em
                ><em v-if="one.fixed"> · {{ one.fixed }}, filled in</em></span
              >
            </template>
            <template v-if="way.typed">
              <span class="kind asks">asks</span>
              <span class="var">NAME=VALUE<em> one per line</em></span>
            </template>
            <template v-if="way.runs">
              <span class="kind runs">{{ way.asks ? 'then runs' : 'runs' }}</span>
              <code class="cmd">{{ way.runs }}</code>
            </template>
            <template v-if="way.sets">
              <span class="kind sets">and sets</span>
              <span v-for="one in way.sets" :key="one" class="var">{{ one }}</span>
            </template>
          </p>
        </div>
      </div>
      <p v-if="open.note && !open.own" class="note">{{ open.note }}</p>
    </div>

    <p class="foot">
      A lookup of what humanize offers, not a live screen. <code>/providers</code> on your
      machine is the list to trust.
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.lab {
  padding-top: 4px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
  white-space: nowrap;
}

.clis {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.clis button {
  padding: 3px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  cursor: pointer;
}

.clis button:hover {
  border-color: var(--vp-c-brand-2);
  color: var(--vp-c-text-1);
}

.clis button.own {
  border-style: dashed;
  font-family: var(--vp-font-family-base);
}

.clis button.on {
  border-style: solid;
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.list {
  padding: 6px 16px 4px;
}

.head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 8px 0 6px;
  font-size: 13px;
  line-height: 1.5;
}

.head span {
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.way {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  gap: 12px;
  padding: 9px 0;
  border-top: 1px solid var(--vp-c-divider);
}

.name {
  align-self: start;
  justify-self: start;
  font-size: 13px;
  font-weight: 650;
  color: var(--vp-c-text-1);
}

.said p {
  margin: 0;
  line-height: 1.5;
}

.about {
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.does {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px 6px;
  margin-top: 5px !important;
}

.kind {
  font-size: 10.5px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.kind.runs {
  color: var(--hmz-warm);
}

.var {
  padding: 1px 7px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 6px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  color: var(--vp-c-text-1);
  overflow-wrap: anywhere;
}

.var.secret {
  border-color: var(--hmz-accent-2);
}

.var em {
  font-style: normal;
  color: var(--vp-c-text-3);
}

.var.secret em {
  color: var(--hmz-accent-2);
}

.cmd {
  font-size: 11.5px;
  overflow-wrap: anywhere;
}

.note {
  margin: 4px 0 10px;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--vp-c-text-2);
}

.foot {
  margin: 0;
  padding: 8px 16px 12px;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

@media (max-width: 560px) {
  .bar {
    flex-direction: column;
    gap: 8px;
  }

  .way {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }
}

@media (prefers-reduced-motion: no-preference) {
  .clis button {
    transition:
      background 0.15s,
      border-color 0.15s,
      color 0.15s;
  }
}
</style>
