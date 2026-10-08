<script setup lang="ts">
// Every way into each backend, as the Accounts page of `/settings` offers them once `a` has been told which CLI.
// Read off the `ways` of each profile in `src/hmz/coganchor/backends.py`, in the order the
// backends are listed there, plus `env` -- which `ways()` in
// `src/hmz/coganchor/providers/store.py` adds to every backend but dsh and litellm, and which is the only
// way into a CLI of your own once `_speaks` in `src/hmz/tui/pick.py` has added it. `runs` is
// the way's `argv`, `asks` its `Asked`s, `sets` its `sets`. A way with a command of its own
// hands that command the terminal; one without is only answers. A way changed in
// `backends.py` is a way to change here.
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import { motion } from '../../motion/gsap'

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
      { name: 'login', about: 'sign in to a Claude subscription', runs: 'claude auth login' },
      {
        name: 'console',
        about: 'sign in to an Anthropic Console account, billed per token',
        runs: 'claude auth login --console',
      },
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
        name: 'wif',
        about: 'Workload Identity Federation: a token another identity provider issues, traded for Anthropic’s',
        asks: [
          { env: 'ANTHROPIC_FEDERATION_RULE_ID' },
          { env: 'ANTHROPIC_ORGANIZATION_ID' },
          { env: 'ANTHROPIC_SERVICE_ACCOUNT_ID' },
          { env: 'ANTHROPIC_IDENTITY_TOKEN_FILE' },
        ],
      },
      {
        name: 'anthropic-gateway',
        about: 'an endpoint speaking Anthropic’s Messages API: a proxy, a router, another vendor',
        asks: [{ env: 'ANTHROPIC_BASE_URL' }, { env: 'ANTHROPIC_AUTH_TOKEN', secret: true }],
      },
      {
        name: 'bedrock-gateway',
        about: 'an endpoint speaking Amazon Bedrock’s API, which holds the AWS credentials itself',
        asks: [{ env: 'ANTHROPIC_BEDROCK_BASE_URL' }, { env: 'ANTHROPIC_AUTH_TOKEN', secret: true }],
        sets: ['CLAUDE_CODE_USE_BEDROCK=1', 'CLAUDE_CODE_SKIP_BEDROCK_AUTH=1'],
      },
      {
        name: 'vertex-gateway',
        about: 'an endpoint speaking Vertex AI’s API, which holds the Google Cloud credentials itself',
        asks: [
          { env: 'ANTHROPIC_VERTEX_BASE_URL' },
          { env: 'ANTHROPIC_AUTH_TOKEN', secret: true },
          { env: 'ANTHROPIC_VERTEX_PROJECT_ID' },
          { env: 'CLOUD_ML_REGION', fixed: 'us-east5' },
        ],
        sets: ['CLAUDE_CODE_USE_VERTEX=1', 'CLAUDE_CODE_SKIP_VERTEX_AUTH=1'],
      },
      {
        name: 'bedrock',
        about: 'Anthropic’s models on an AWS account of yours',
        asks: [{ env: 'AWS_PROFILE' }, { env: 'AWS_REGION', fixed: 'us-east-1' }],
        sets: ['CLAUDE_CODE_USE_BEDROCK=1'],
      },
      {
        name: 'bedrock-key',
        about: 'Anthropic’s models on Amazon Bedrock, by a Bedrock API key',
        asks: [{ env: 'AWS_BEARER_TOKEN_BEDROCK', secret: true }, { env: 'AWS_REGION', fixed: 'us-east-1' }],
        sets: ['CLAUDE_CODE_USE_BEDROCK=1'],
      },
      {
        name: 'mantle',
        about: 'Anthropic’s models on Amazon Bedrock’s Mantle endpoint, on an AWS account of yours',
        asks: [{ env: 'AWS_PROFILE' }, { env: 'AWS_REGION', fixed: 'us-east-1' }],
        sets: ['CLAUDE_CODE_USE_MANTLE=1'],
      },
      {
        name: 'vertex',
        about: 'Anthropic’s models on a Google Cloud project of yours',
        asks: [{ env: 'ANTHROPIC_VERTEX_PROJECT_ID' }, { env: 'CLOUD_ML_REGION', fixed: 'us-east5' }],
        sets: ['CLAUDE_CODE_USE_VERTEX=1'],
      },
      {
        name: 'foundry',
        about: 'Anthropic’s models on a Microsoft Foundry resource of yours',
        asks: [{ env: 'ANTHROPIC_FOUNDRY_RESOURCE' }, { env: 'ANTHROPIC_FOUNDRY_API_KEY', secret: true }],
        sets: ['CLAUDE_CODE_USE_FOUNDRY=1'],
      },
      {
        name: 'aws',
        about: 'Claude Platform on AWS: Anthropic’s API, billed through AWS',
        asks: [
          { env: 'ANTHROPIC_AWS_WORKSPACE_ID' },
          { env: 'AWS_REGION', fixed: 'us-east-1' },
          { env: 'ANTHROPIC_AWS_API_KEY', secret: true },
        ],
        sets: ['CLAUDE_CODE_USE_ANTHROPIC_AWS=1'],
      },
      {
        name: 'google-cloud',
        about: 'Claude Platform on Google Cloud: Anthropic’s API, billed through Google Cloud',
        asks: [
          { env: 'ANTHROPIC_GOOGLE_CLOUD_PROJECT' },
          { env: 'ANTHROPIC_GOOGLE_CLOUD_LOCATION', fixed: 'global' },
          { env: 'ANTHROPIC_GOOGLE_CLOUD_WORKSPACE_ID' },
        ],
        sets: ['CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD=1'],
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
        name: 'gemini-gateway',
        about: 'an endpoint speaking Gemini’s API: a proxy, a router, another vendor',
        asks: [{ env: 'AGY_LLM_GATEWAY_URL' }, { env: 'AGY_LLM_GATEWAY_API_KEY', secret: true }],
        sets: ['AGY_LLM_GATEWAY_WIRE_PROTOCOL=genai'],
      },
      {
        name: 'openai-gateway',
        about: 'an endpoint speaking OpenAI’s API: a proxy, a router, another vendor',
        asks: [
          { env: 'AGY_LLM_GATEWAY_URL' },
          { env: 'AGY_LLM_GATEWAY_API_KEY', secret: true },
          { env: 'AGY_LLM_GATEWAY_MODELS' },
        ],
        sets: ['AGY_LLM_GATEWAY_WIRE_PROTOCOL=openai'],
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
        name: 'workload',
        about: 'a ChatGPT workspace’s workload identity, where nobody signs in',
        asks: [{ env: 'OPENAI_FEDERATION_RULE_ID' }, { env: 'OPENAI_IDENTITY_TOKEN_FILE' }],
      },
      {
        name: 'openai-gateway',
        about: 'an endpoint speaking OpenAI’s API: a proxy, a router, another vendor',
        asks: [{ env: 'CODEX_PROVIDER_URL' }, { env: 'CODEX_PROVIDER_KEY', secret: true }],
      },
      {
        name: 'azure',
        about: 'OpenAI’s models on an Azure OpenAI resource of yours',
        asks: [
          { env: 'AZURE_OPENAI_BASE_URL' },
          { env: 'AZURE_OPENAI_API_KEY', secret: true },
          { env: 'AZURE_OPENAI_API_VERSION', fixed: '2025-04-01-preview' },
        ],
      },
      {
        name: 'bedrock',
        about: 'OpenAI’s models on an AWS account of yours',
        asks: [{ env: 'AWS_PROFILE' }, { env: 'AWS_REGION', fixed: 'us-east-1' }],
      },
      {
        name: 'bedrock-key',
        about: 'the same, with a Bedrock API key',
        asks: [{ env: 'AWS_BEARER_TOKEN_BEDROCK', secret: true }, { env: 'AWS_REGION', fixed: 'us-east-1' }],
      },
      {
        name: 'ollama',
        about: 'open models served by Ollama',
        asks: [{ env: 'CODEX_OSS_BASE_URL', fixed: 'http://localhost:11434/v1' }],
      },
      {
        name: 'lmstudio',
        about: 'open models served by LM Studio',
        asks: [{ env: 'CODEX_OSS_BASE_URL', fixed: 'http://localhost:1234/v1' }],
      },
      ENV,
    ],
  },
  {
    cli: 'dsh',
    called: 'DeepSeek Harness',
    note: 'No env way here: DeepSeek Harness takes only its own key and its gateways.',
    ways: [
      {
        name: 'key',
        about: 'a DeepSeek API key, from the platform',
        asks: [{ env: 'DEEPSEEK_API_KEY', secret: true }],
      },
      {
        name: 'openai-gateway',
        about: "an endpoint speaking OpenAI's API -- a proxy, a router, another vendor",
        asks: [
          { env: 'DEEPSEEK_BASE_URL' },
          { env: 'DEEPSEEK_API_KEY', secret: true },
          { env: 'DSH_GATEWAY_API', fixed: 'openai-completions' },
        ],
      },
      {
        name: 'anthropic-gateway',
        about: "an endpoint speaking Anthropic's Messages API -- a proxy, a router, another vendor",
        asks: [{ env: 'DEEPSEEK_BASE_URL' }, { env: 'DEEPSEEK_API_KEY', secret: true }],
      },
      {
        name: 'gemini-gateway',
        about: "an endpoint speaking Gemini's API -- a proxy, a router, another vendor",
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
        name: 'oidc',
        about: 'your own identity provider, for an organisation that signs in through one',
        runs: 'grok login',
        asks: [{ env: 'GROK_OIDC_ISSUER' }, { env: 'GROK_OIDC_CLIENT_ID' }],
      },
      {
        name: 'provider-command',
        about: "a command of your organisation's that prints a token",
        runs: 'grok login',
        asks: [{ env: 'GROK_AUTH_PROVIDER_COMMAND' }],
      },
      {
        name: 'key',
        about: 'an xAI API key, from the console',
        asks: [{ env: 'XAI_API_KEY', secret: true }],
      },
      {
        name: 'openai-gateway',
        about: "an endpoint speaking OpenAI's API -- a proxy, a router, another vendor",
        asks: [
          { env: 'GROK_XAI_API_BASE_URL' },
          { env: 'XAI_API_KEY', secret: true },
          { env: 'GROK_GATEWAY_API_BACKEND', fixed: 'responses' },
        ],
      },
      {
        name: 'anthropic-gateway',
        about: "an endpoint speaking Anthropic's Messages API -- a proxy, a router, another vendor",
        asks: [{ env: 'GROK_XAI_API_BASE_URL' }, { env: 'XAI_API_KEY', secret: true }],
        sets: ['GROK_GATEWAY_API_BACKEND=messages'],
      },
      ENV,
    ],
  },
  {
    cli: 'kimi',
    called: 'Kimi Code',
    ways: [
      {
        name: 'login',
        about: 'sign in to a Kimi account, by the code it prints',
        asks: [{ env: 'KIMI_REGION', fixed: 'global' }],
        runs: 'kimi login --region {KIMI_REGION}',
      },
      {
        name: 'kimi-key',
        about: 'a Moonshot platform key, or a Kimi for Coding one at https://api.kimi.com/coding/v1',
        asks: [
          { env: 'KIMI_MODEL_API_KEY', secret: true },
          { env: 'KIMI_MODEL_BASE_URL', fixed: 'https://api.moonshot.ai/v1' },
          { env: 'KIMI_MODEL_NAME' },
        ],
        sets: ['KIMI_MODEL_PROVIDER_TYPE=kimi'],
      },
      {
        name: 'openai-gateway',
        about: 'an endpoint speaking OpenAI’s API: a proxy, a router, another vendor',
        asks: [
          { env: 'KIMI_MODEL_BASE_URL' },
          { env: 'KIMI_MODEL_API_KEY', secret: true },
          { env: 'KIMI_MODEL_NAME' },
          { env: 'KIMI_MODEL_PROVIDER_TYPE', fixed: 'openai' },
        ],
      },
      {
        name: 'anthropic-gateway',
        about: 'an endpoint speaking Anthropic’s Messages API: a proxy, a router, another vendor',
        asks: [
          { env: 'KIMI_MODEL_BASE_URL' },
          { env: 'KIMI_MODEL_API_KEY', secret: true },
          { env: 'KIMI_MODEL_NAME' },
        ],
        sets: ['KIMI_MODEL_PROVIDER_TYPE=anthropic'],
      },
      {
        name: 'gemini-gateway',
        about: 'an endpoint speaking Gemini’s API: a proxy, a router, another vendor',
        asks: [
          { env: 'KIMI_MODEL_BASE_URL' },
          { env: 'KIMI_MODEL_API_KEY', secret: true },
          { env: 'KIMI_MODEL_NAME' },
        ],
        sets: ['KIMI_MODEL_PROVIDER_TYPE=google-genai'],
      },
      ENV,
    ],
  },
  {
    cli: 'pi',
    called: 'pi',
    ways: [
      { name: 'login', about: 'pi’s own /login, in a session opened for it', runs: 'pi' },
      {
        name: 'anthropic-key',
        about: 'an Anthropic API key, from the console',
        asks: [{ env: 'ANTHROPIC_API_KEY', secret: true }],
      },
      {
        name: 'anthropic-token',
        about: 'a long-lived Anthropic token, as claude setup-token prints one',
        asks: [{ env: 'ANTHROPIC_OAUTH_TOKEN', secret: true }],
      },
      {
        name: 'openai-key',
        about: 'an OpenAI API key, from the platform',
        asks: [{ env: 'OPENAI_API_KEY', secret: true }],
      },
      {
        name: 'gemini-key',
        about: 'a Gemini API key, from Google AI Studio',
        asks: [{ env: 'GEMINI_API_KEY', secret: true }],
      },
      { name: 'xai-key', about: 'an xAI API key, from the console', asks: [{ env: 'XAI_API_KEY', secret: true }] },
      { name: 'openrouter-key', about: 'an OpenRouter API key', asks: [{ env: 'OPENROUTER_API_KEY', secret: true }] },
      {
        name: 'deepseek-key',
        about: 'a DeepSeek API key, from the platform',
        asks: [{ env: 'DEEPSEEK_API_KEY', secret: true }],
      },
      { name: 'groq-key', about: 'a Groq API key, from the console', asks: [{ env: 'GROQ_API_KEY', secret: true }] },
      {
        name: 'mistral-key',
        about: 'a Mistral API key, from La Plateforme',
        asks: [{ env: 'MISTRAL_API_KEY', secret: true }],
      },
      {
        name: 'openai-gateway',
        about: 'an endpoint speaking OpenAI’s API: a proxy, a router, another vendor',
        asks: [
          { env: 'PI_GATEWAY_URL' },
          { env: 'PI_GATEWAY_KEY', secret: true },
          { env: 'PI_GATEWAY_MODEL' },
          { env: 'PI_GATEWAY_API', fixed: 'openai-completions' },
        ],
      },
      {
        name: 'anthropic-gateway',
        about: 'an endpoint speaking Anthropic’s Messages API: a proxy, a router, another vendor',
        asks: [{ env: 'PI_GATEWAY_URL' }, { env: 'PI_GATEWAY_KEY', secret: true }, { env: 'PI_GATEWAY_MODEL' }],
        sets: ['PI_GATEWAY_API=anthropic-messages'],
      },
      {
        name: 'gemini-gateway',
        about: 'an endpoint speaking Gemini’s API: a proxy, a router, another vendor',
        asks: [{ env: 'PI_GATEWAY_URL' }, { env: 'PI_GATEWAY_KEY', secret: true }, { env: 'PI_GATEWAY_MODEL' }],
        sets: ['PI_GATEWAY_API=google-generative-ai'],
      },
      {
        name: 'bedrock',
        about: 'models on Amazon Bedrock, under an AWS account of yours',
        asks: [{ env: 'AWS_PROFILE' }, { env: 'AWS_REGION', fixed: 'us-east-1' }],
      },
      {
        name: 'vertex',
        about: 'models on Vertex AI, under a Google Cloud project of yours',
        asks: [{ env: 'GOOGLE_CLOUD_PROJECT' }, { env: 'GOOGLE_CLOUD_LOCATION', fixed: 'us-central1' }],
      },
      {
        name: 'azure',
        about: 'OpenAI’s models on an Azure OpenAI resource of yours',
        asks: [{ env: 'AZURE_OPENAI_BASE_URL' }, { env: 'AZURE_OPENAI_API_KEY', secret: true }],
      },
      ENV,
    ],
    note:
      'A gateway way is written into pi’s own models.json as a provider named humanize-<hash>, ' +
      'its key as $PI_GATEWAY_KEY rather than as itself, and every turn is run with --provider ' +
      'naming it.',
  },
  {
    cli: 'omp',
    called: 'Oh My Pi',
    ways: [
      {
        name: 'anthropic-key',
        about: 'an Anthropic API key, from the console',
        asks: [{ env: 'ANTHROPIC_API_KEY', secret: true }],
      },
      {
        name: 'anthropic-token',
        about: 'a long-lived Anthropic token, as claude setup-token prints one',
        asks: [{ env: 'ANTHROPIC_OAUTH_TOKEN', secret: true }],
      },
      {
        name: 'openai-key',
        about: 'an OpenAI API key, from the platform',
        asks: [{ env: 'OPENAI_API_KEY', secret: true }],
      },
      {
        name: 'gemini-key',
        about: 'a Gemini API key, from Google AI Studio',
        asks: [{ env: 'GEMINI_API_KEY', secret: true }],
      },
      { name: 'xai-key', about: 'an xAI API key, from the console', asks: [{ env: 'XAI_API_KEY', secret: true }] },
      { name: 'openrouter-key', about: 'an OpenRouter API key', asks: [{ env: 'OPENROUTER_API_KEY', secret: true }] },
      {
        name: 'deepseek-key',
        about: 'a DeepSeek API key, from the platform',
        asks: [{ env: 'DEEPSEEK_API_KEY', secret: true }],
      },
      { name: 'groq-key', about: 'a Groq API key, from the console', asks: [{ env: 'GROQ_API_KEY', secret: true }] },
      {
        name: 'mistral-key',
        about: 'a Mistral API key, from La Plateforme',
        asks: [{ env: 'MISTRAL_API_KEY', secret: true }],
      },
      {
        name: 'bedrock',
        about: 'models on Amazon Bedrock, under an AWS account of yours',
        asks: [{ env: 'AWS_PROFILE' }, { env: 'AWS_REGION', fixed: 'us-east-1' }],
      },
      {
        name: 'vertex',
        about: 'models on Vertex AI, under a Google Cloud project of yours',
        asks: [{ env: 'GOOGLE_CLOUD_PROJECT' }, { env: 'GOOGLE_CLOUD_LOCATION', fixed: 'us-central1' }],
      },
      ENV,
    ],
    note:
      'There is no login: omp keeps its sign-ins in its own agent.db, which is not copied. An agent ' +
      'given no account runs as whatever this machine’s omp is signed in to.',
  },
  {
    cli: 'qwen',
    called: 'Qwen Code',
    ways: [
      {
        name: 'coding-plan',
        about: 'an Alibaba Cloud Model Studio Coding Plan',
        asks: [
          { env: 'OPENAI_BASE_URL', fixed: 'https://coding.dashscope.aliyuncs.com/v1' },
          { env: 'OPENAI_API_KEY', secret: true },
        ],
      },
      {
        name: 'token-plan',
        about: 'an Alibaba Cloud Model Studio Token Plan',
        asks: [
          {
            env: 'OPENAI_BASE_URL',
            fixed: 'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',
          },
          { env: 'OPENAI_API_KEY', secret: true },
        ],
      },
      {
        name: 'gemini-key',
        about: 'a Gemini API key, from AI Studio',
        asks: [{ env: 'GEMINI_API_KEY', secret: true }],
      },
      {
        name: 'openai-gateway',
        about: 'an endpoint speaking OpenAI’s API -- a proxy, a router, another vendor',
        asks: [
          { env: 'OPENAI_BASE_URL', fixed: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { env: 'OPENAI_API_KEY', secret: true },
          { env: 'QWEN_DEFAULT_AUTH_TYPE', fixed: 'openai' },
        ],
      },
      {
        name: 'anthropic-gateway',
        about: 'an endpoint speaking Anthropic’s Messages API -- a proxy, a router, another vendor',
        asks: [{ env: 'ANTHROPIC_BASE_URL' }, { env: 'ANTHROPIC_API_KEY', secret: true }],
      },
      {
        name: 'gemini-gateway',
        about: 'an endpoint speaking Gemini’s API -- a proxy, a router, another vendor',
        asks: [{ env: 'GOOGLE_GEMINI_BASE_URL' }, { env: 'GEMINI_API_KEY', secret: true }],
      },
      {
        name: 'vertex',
        about: 'Google’s models on a Google Cloud project of yours',
        asks: [{ env: 'GOOGLE_CLOUD_PROJECT' }, { env: 'GOOGLE_CLOUD_LOCATION', fixed: 'global' }],
      },
      {
        name: 'vertex-key',
        about: 'a Vertex AI API key, for its express mode',
        asks: [{ env: 'GOOGLE_API_KEY', secret: true }],
      },
      ENV,
    ],
    note: 'Qwen OAuth was discontinued on 2026-04-15, so there is no login: every way says its --auth-type on each turn.',
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
      {
        name: 'anthropic-key',
        about: 'an Anthropic API key, from the console',
        asks: [{ env: 'ANTHROPIC_API_KEY', secret: true }],
      },
      {
        name: 'openai-key',
        about: 'an OpenAI API key, from the platform',
        asks: [{ env: 'OPENAI_API_KEY', secret: true }],
      },
      {
        name: 'gemini-key',
        about: 'a Gemini API key, from AI Studio',
        asks: [{ env: 'GOOGLE_GENERATIVE_AI_API_KEY', secret: true }],
      },
      {
        name: 'xai-key',
        about: 'an xAI API key, from its console',
        asks: [{ env: 'XAI_API_KEY', secret: true }],
      },
      {
        name: 'openrouter-key',
        about: 'an OpenRouter key, for every model it routes to',
        asks: [{ env: 'OPENROUTER_API_KEY', secret: true }],
      },
      {
        name: 'deepseek-key',
        about: 'a DeepSeek API key, from its platform',
        asks: [{ env: 'DEEPSEEK_API_KEY', secret: true }],
      },
      {
        name: 'mistral-key',
        about: 'a Mistral API key, from its console',
        asks: [{ env: 'MISTRAL_API_KEY', secret: true }],
      },
      {
        name: 'openai-gateway',
        about: 'an endpoint speaking OpenAI’s API -- a proxy, a router, another vendor',
        asks: [
          { env: 'OPENCODE_GATEWAY_URL' },
          { env: 'OPENCODE_GATEWAY_KEY', secret: true },
          { env: 'OPENCODE_GATEWAY_MODEL' },
          { env: 'OPENCODE_GATEWAY_NPM', fixed: '@ai-sdk/openai-compatible' },
        ],
        sets: ['OPENCODE_CONFIG_CONTENT'],
      },
      {
        name: 'anthropic-gateway',
        about: 'an endpoint speaking Anthropic’s Messages API -- a proxy, a router, another vendor',
        asks: [
          { env: 'OPENCODE_GATEWAY_URL' },
          { env: 'OPENCODE_GATEWAY_KEY', secret: true },
          { env: 'OPENCODE_GATEWAY_MODEL' },
        ],
        sets: ['OPENCODE_CONFIG_CONTENT'],
      },
      {
        name: 'gemini-gateway',
        about: 'an endpoint speaking Gemini’s API -- a proxy, a router, another vendor',
        asks: [
          { env: 'OPENCODE_GATEWAY_URL' },
          { env: 'OPENCODE_GATEWAY_KEY', secret: true },
          { env: 'OPENCODE_GATEWAY_MODEL' },
        ],
        sets: ['OPENCODE_CONFIG_CONTENT'],
      },
      {
        name: 'bedrock',
        about: 'the models on an AWS account of yours',
        asks: [{ env: 'AWS_PROFILE' }, { env: 'AWS_REGION', fixed: 'us-east-1' }],
      },
      {
        name: 'vertex',
        about: 'the models on a Google Cloud project of yours',
        asks: [{ env: 'GOOGLE_CLOUD_PROJECT' }, { env: 'GOOGLE_CLOUD_LOCATION', fixed: 'global' }],
      },
      {
        name: 'azure',
        about: 'the models deployed on an Azure OpenAI resource of yours',
        asks: [{ env: 'AZURE_RESOURCE_NAME' }, { env: 'AZURE_API_KEY', secret: true }],
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
      {
        name: 'anthropic-key',
        about: 'an Anthropic API key, from the console',
        asks: [{ env: 'ANTHROPIC_API_KEY', secret: true }],
      },
      {
        name: 'openai-key',
        about: 'an OpenAI API key, from the platform',
        asks: [{ env: 'OPENAI_API_KEY', secret: true }],
      },
      {
        name: 'gemini-key',
        about: 'a Gemini API key, from Google AI Studio',
        asks: [{ env: 'GOOGLE_GENERATIVE_AI_API_KEY', secret: true }],
      },
      {
        name: 'xai-key',
        about: 'an xAI API key, from its console',
        asks: [{ env: 'XAI_API_KEY', secret: true }],
      },
      {
        name: 'openrouter-key',
        about: 'an OpenRouter key, which every model it routes to runs on',
        asks: [{ env: 'OPENROUTER_API_KEY', secret: true }],
      },
      {
        name: 'deepseek-key',
        about: 'a DeepSeek API key, from its platform',
        asks: [{ env: 'DEEPSEEK_API_KEY', secret: true }],
      },
      {
        name: 'openai-gateway',
        about: 'an endpoint speaking OpenAI’s API: a proxy, a router, another vendor',
        asks: [
          { env: 'MIMO_GATEWAY_URL' },
          { env: 'MIMO_GATEWAY_KEY', secret: true },
          { env: 'MIMO_GATEWAY_MODEL' },
          { env: 'MIMO_GATEWAY_API', fixed: '@ai-sdk/openai-compatible' },
        ],
        sets: ['MIMOCODE_CONFIG_CONTENT'],
      },
      {
        name: 'anthropic-gateway',
        about: 'an endpoint speaking Anthropic’s Messages API: a proxy, a router, another vendor',
        asks: [
          { env: 'MIMO_GATEWAY_URL' },
          { env: 'MIMO_GATEWAY_KEY', secret: true },
          { env: 'MIMO_GATEWAY_MODEL' },
        ],
        sets: ['MIMO_GATEWAY_API=@ai-sdk/anthropic', 'MIMOCODE_CONFIG_CONTENT'],
      },
      {
        name: 'gemini-gateway',
        about: 'an endpoint speaking Gemini’s API: a proxy, a router, another vendor',
        asks: [
          { env: 'MIMO_GATEWAY_URL' },
          { env: 'MIMO_GATEWAY_KEY', secret: true },
          { env: 'MIMO_GATEWAY_MODEL' },
        ],
        sets: ['MIMO_GATEWAY_API=@ai-sdk/google', 'MIMOCODE_CONFIG_CONTENT'],
      },
      {
        name: 'vertex',
        about: 'Gemini and Anthropic’s models on a Google Cloud project of yours',
        asks: [{ env: 'GOOGLE_CLOUD_PROJECT' }, { env: 'GOOGLE_VERTEX_LOCATION', fixed: 'us-central1' }],
      },
      {
        name: 'bedrock',
        about: 'the models on Amazon Bedrock, on an AWS account of yours',
        asks: [{ env: 'AWS_PROFILE' }, { env: 'AWS_REGION', fixed: 'us-east-1' }],
      },
      {
        name: 'azure',
        about: 'the models on an Azure OpenAI resource of yours',
        asks: [{ env: 'AZURE_RESOURCE_NAME' }, { env: 'AZURE_API_KEY', secret: true }],
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
        name: 'cursor-gateway',
        about: GATEWAY,
        asks: [{ env: 'CURSOR_API_ENDPOINT' }, { env: 'CURSOR_API_KEY', secret: true }],
      },
      ENV,
    ],
  },
  {
    cli: 'mcode',
    called: 'MiniMax Code',
    ways: [
      {
        name: 'login',
        about: 'sign in to a MiniMax account, in a browser',
        asks: [{ env: 'MCODE_REGION', fixed: 'global' }],
        runs: 'mcode login --region …',
      },
      {
        name: 'key',
        about: 'a MiniMax API key, from the platform',
        asks: [{ env: 'MCODE_PROVIDER_API_KEY', secret: true }, { env: 'MAVIS_REGION', fixed: 'en' }],
        runs: 'mcode provider set-minimax-key',
      },
      {
        name: 'openai-gateway',
        about: 'an endpoint speaking OpenAI’s API -- a proxy, a router, another vendor',
        asks: [
          { env: 'MCODE_GATEWAY_URL' },
          { env: 'MCODE_PROVIDER_API_KEY', secret: true },
          { env: 'MCODE_GATEWAY_MODEL' },
          { env: 'MCODE_GATEWAY_FORMAT', fixed: 'openai-completions' },
        ],
        runs: 'mcode provider add --name gateway … --use',
      },
      {
        name: 'anthropic-gateway',
        about: 'an endpoint speaking Anthropic’s Messages API -- a proxy, a router, another vendor',
        asks: [
          { env: 'MCODE_GATEWAY_URL' },
          { env: 'MCODE_PROVIDER_API_KEY', secret: true },
          { env: 'MCODE_GATEWAY_MODEL' },
        ],
        runs: 'mcode provider add --name gateway --api-format anthropic-messages … --use',
      },
      ENV,
    ],
  },
  {
    cli: 'litellm',
    called: 'litellm',
    note: 'No env way here: a litellm turn is a call in this process, handed the account on the call.',
    ways: [
      { name: 'openai-key', about: 'an OpenAI API key, from the platform', asks: [{ env: 'OPENAI_API_KEY', secret: true }] },
      { name: 'anthropic-key', about: 'an Anthropic API key, from the console', asks: [{ env: 'ANTHROPIC_API_KEY', secret: true }] },
      { name: 'gemini-key', about: 'a Gemini API key, from Google AI Studio', asks: [{ env: 'GEMINI_API_KEY', secret: true }] },
      { name: 'xai-key', about: 'an xAI API key, from the console', asks: [{ env: 'XAI_API_KEY', secret: true }] },
      { name: 'openrouter-key', about: 'an OpenRouter API key', asks: [{ env: 'OPENROUTER_API_KEY', secret: true }] },
      { name: 'deepseek-key', about: 'a DeepSeek API key, from the platform', asks: [{ env: 'DEEPSEEK_API_KEY', secret: true }] },
      { name: 'groq-key', about: 'a Groq API key, from the console', asks: [{ env: 'GROQ_API_KEY', secret: true }] },
      { name: 'mistral-key', about: 'a Mistral API key, from La Plateforme', asks: [{ env: 'MISTRAL_API_KEY', secret: true }] },
      {
        name: 'openai-gateway',
        about: "an endpoint speaking OpenAI's API -- a proxy, a router, another vendor",
        asks: [{ env: 'LITELLM_GATEWAY_URL' }, { env: 'LITELLM_GATEWAY_KEY', secret: true }],
        sets: ['LITELLM_GATEWAY_API=openai'],
      },
      {
        name: 'anthropic-gateway',
        about: "an endpoint speaking Anthropic's Messages API -- a proxy, a router, another vendor",
        asks: [{ env: 'LITELLM_GATEWAY_URL' }, { env: 'LITELLM_GATEWAY_KEY', secret: true }],
        sets: ['LITELLM_GATEWAY_API=anthropic'],
      },
      {
        name: 'bedrock',
        about: 'models on Amazon Bedrock, under an AWS account of yours',
        asks: [{ env: 'AWS_PROFILE' }, { env: 'AWS_REGION_NAME', fixed: 'us-east-1' }],
      },
      {
        name: 'vertex',
        about: 'models on Vertex AI, under a Google Cloud project of yours',
        asks: [{ env: 'VERTEXAI_PROJECT' }, { env: 'VERTEXAI_LOCATION', fixed: 'us-central1' }],
      },
      {
        name: 'azure',
        about: "OpenAI's models on an Azure OpenAI resource of yours",
        asks: [
          { env: 'AZURE_API_BASE' },
          { env: 'AZURE_API_KEY', secret: true },
          { env: 'AZURE_API_VERSION', fixed: '2024-10-21' },
        ],
      },
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

// The motion, laid over the lookup without changing what it says. Choosing a CLI glides the
// lit pill to it, draws a branch from the CLI to each of its ways, reflows the ways both CLIs
// share to where they now stand, lets the details of each way in after its branch reaches it,
// and types each command on. Under reduced motion each of those is its final frame.
const clis = ref<HTMLElement | null>(null)
const glide = ref<HTMLElement | null>(null)
const list = ref<HTMLElement | null>(null)
const rows = ref<HTMLElement | null>(null)
const live = ref(false)
const count = ref(open.value.ways.length)
// How much of each way's command has been typed; a way not in here shows all of its command.
const typing = reactive<Record<string, number>>({})
// The connectors, in the pixels of the rows they join: a spine down from the CLI, a branch
// curving off it to each way.
const tree = reactive({ spine: '', branches: [] as { d: string; x: number; y: number }[] })
const X = 7

let tl: gsap.core.Timeline | undefined
let sizes: ResizeObserver | undefined
let seen: IntersectionObserver | undefined

const still = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

function shown(way: Way): string {
  const n = typing[way.name]
  return n === undefined ? (way.runs ?? '') : (way.runs ?? '').slice(0, Math.floor(n))
}

function unshown(way: Way): string {
  const n = typing[way.name]
  return n === undefined ? '' : (way.runs ?? '').slice(Math.floor(n))
}

// The pill behind the chosen CLI, moved to it: gliding there when `move`, else at once.
function place(move: boolean) {
  const button = clis.value?.querySelector<HTMLElement>('button.on')
  if (!button || !glide.value) return
  const to = { x: button.offsetLeft, y: button.offsetTop, width: button.offsetWidth, height: button.offsetHeight }
  const gsap = motion()
  if (!move || still()) {
    gsap.set(glide.value, { ...to, autoAlpha: 1 })
    return
  }
  gsap.to(glide.value, { ...to, autoAlpha: 1, duration: 0.55, ease: 'cine', overwrite: 'auto' })
  gsap.fromTo(glide.value, { scaleY: 1 }, { keyframes: { scaleY: [1, 0.8, 1.06, 1] }, duration: 0.55, ease: 'none' })
}

// How far down `box` an element's layout box stands. A row reflowing to its new place is moved
// with a transform, which makes it the offset parent of what is in it, so climb to `box`.
function within(el: HTMLElement, box: HTMLElement): number {
  let y = 0
  for (let at: HTMLElement | null = el; at && at !== box; at = at.offsetParent as HTMLElement | null) y += at.offsetTop
  return y
}

function measure() {
  const box = rows.value
  if (!box) return
  const names = [...box.querySelectorAll<HTMLElement>('.way:not(.leaving) .name')]
  const ys = names.map((one) => Math.round(within(one, box) + one.offsetHeight / 2))
  const last = ys.at(-1)
  tree.spine = last === undefined ? '' : `M${X} -4 V${last - 7}`
  tree.branches = ys.map((y) => ({ d: `M${X} ${y - 7} Q${X} ${y} ${X + 7} ${y} H${X + 12}`, x: X + 12, y }))
}

// The ways of the chosen CLI arrive: the spine is drawn down, and each way, as its branch
// reaches it, has its name, its words and its command let in, one after another.
function play(): gsap.core.Timeline | undefined {
  const box = rows.value
  if (!box || still()) return
  const gsap = motion()
  tl?.kill()
  const ways = open.value.ways
  const els = [...box.querySelectorAll<HTMLElement>('.way:not(.leaving)')]
  for (const way of ways) if (way.runs) typing[way.name] = 0
  const t = gsap.timeline({
    onComplete() {
      for (const way of ways) delete typing[way.name]
    },
  })
  tl = t
  const step = Math.min(0.11, 0.7 / Math.max(ways.length, 1))
  const branches = box.querySelectorAll('.branch')
  const knots = box.querySelectorAll('.knot')
  const flow = box.querySelector('.flow')
  const spine = box.querySelector('.spine')
  t.fromTo(box.querySelector('.root'), { autoAlpha: 0, scale: 0.3, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(2.4)' }, 0)
  if (spine) t.fromTo(spine, { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.2 + step * ways.length, ease: 'cine' }, 0.05)
  if (flow) t.set(flow, { autoAlpha: 0 }, 0)
  const tally = { n: 0 }
  t.to(tally, { n: ways.length, duration: 0.25 + step * ways.length, ease: 'power2.out', onUpdate: () => void (count.value = Math.round(tally.n)) }, 0)
  els.forEach((row, i) => {
    const at = 0.1 + i * step
    const way = ways[i]
    if (branches[i]) t.fromTo(branches[i], { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.3, ease: 'cine.out' }, at)
    if (knots[i]) t.fromTo(knots[i], { autoAlpha: 0, scale: 0.2, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(3)' }, at + 0.2)
    t.fromTo(row.querySelector('.name'), { autoAlpha: 0, x: -10 }, { autoAlpha: 1, x: 0, duration: 0.45 }, at + 0.18)
    t.fromTo(row.querySelector('.about'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.45 }, at + 0.24)
    t.fromTo(row.querySelectorAll('.does > *'), { autoAlpha: 0, y: 5 }, { autoAlpha: 1, y: 0, duration: 0.35, stagger: 0.05 }, at + 0.32)
    if (way?.runs) t.to(typing, { [way.name]: way.runs.length, duration: way.runs.length / 55, ease: 'none' }, at + 0.5)
  })
  if (flow) t.to(flow, { autoAlpha: 1, duration: 0.6, ease: 'none' }, '>-0.2')
  return t
}

// A way the new CLI does not have leaves from where it stood, while the rest reflow round it.
function leave(el: Element, done: () => void) {
  if (still()) return done()
  const row = el as HTMLElement
  Object.assign(row.style, {
    position: 'absolute',
    top: `${row.offsetTop}px`,
    left: `${row.offsetLeft}px`,
    width: `${row.offsetWidth}px`,
  })
  row.classList.add('leaving')
  motion().to(row, { autoAlpha: 0, x: 18, duration: 0.28, ease: 'cine.in', onComplete: done })
}

async function choose(cli: string) {
  if (cli === chosen.value) return
  const from = list.value?.offsetHeight ?? 0
  chosen.value = cli
  await nextTick()
  place(true)
  measure()
  if (still()) {
    count.value = open.value.ways.length
    return
  }
  const box = list.value
  if (box && from) {
    const to = box.offsetHeight
    motion().fromTo(box, { height: from }, { height: to, duration: 0.5, ease: 'cine', clearProps: 'height' })
  }
  await nextTick()
  play()
}

onMounted(() => {
  live.value = true
  sizes = new ResizeObserver(() => {
    place(false)
    measure()
  })
  if (clis.value) sizes.observe(clis.value)
  if (rows.value) sizes.observe(rows.value)
  // The first CLI's ways are drawn in the first time the lookup is scrolled to: held at the
  // start of their entrance till then.
  nextTick(() => {
    place(false)
    measure()
    nextTick(() => play()?.pause(0))
  })
  seen = new IntersectionObserver(
    (entries) => {
      if (!entries.some((one) => one.isIntersecting)) return
      seen?.disconnect()
      tl?.play()
    },
    { threshold: 0.3 },
  )
  if (rows.value) seen.observe(rows.value)
})

onBeforeUnmount(() => {
  tl?.kill()
  sizes?.disconnect()
  seen?.disconnect()
})
</script>

<template>
  <div class="ways hmz-panel" :class="{ live }">
    <div class="bar">
      <span class="lab">sign in to</span>
      <div ref="clis" class="clis" role="group" aria-label="choose a coding agent CLI">
        <span ref="glide" class="glide" aria-hidden="true" />
        <button
          v-for="one in BACKENDS"
          :key="one.cli"
          type="button"
          :aria-pressed="chosen === one.cli"
          :class="{ on: chosen === one.cli, own: one.own }"
          @click="choose(one.cli)"
        >
          {{ one.cli }}
        </button>
      </div>
    </div>

    <div ref="list" class="list">
      <p class="head" aria-live="polite">
        <strong>{{ open.called }}</strong>
        <span>{{ live ? count : open.ways.length }} {{ open.ways.length === 1 ? 'way' : 'ways' }} in</span>
      </p>
      <p v-if="open.own" class="note">{{ open.note }}</p>
      <div ref="rows" class="rows">
        <svg class="tree" aria-hidden="true">
          <circle class="root" :cx="X" cy="-4" r="3.5" />
          <path class="spine" :d="tree.spine" />
          <path class="flow" :d="tree.spine" />
          <path v-for="(one, at) in tree.branches" :key="`b${at}`" class="branch" :d="one.d" />
          <circle v-for="(one, at) in tree.branches" :key="`k${at}`" class="knot" :cx="one.x" :cy="one.y" r="2.6" />
        </svg>
        <TransitionGroup tag="div" name="way" @leave="leave">
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
                  <code class="cmd" :class="{ typing: typing[way.name] !== undefined }" :aria-label="way.runs"
                    ><span aria-hidden="true">{{ shown(way) }}</span
                    ><span class="ghost" aria-hidden="true">{{ unshown(way) }}</span></code
                  >
                </template>
                <template v-if="way.sets">
                  <span class="kind sets">and sets</span>
                  <span v-for="one in way.sets" :key="one" class="var">{{ one }}</span>
                </template>
              </p>
            </div>
          </div>
        </TransitionGroup>
      </div>
      <p v-if="open.note && !open.own" class="note">{{ open.note }}</p>
    </div>

    <p class="foot">
      A lookup of what humanize offers, not a live screen. The Accounts page of <code>/settings</code>
      on your machine is the list to trust.
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
  position: relative;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* The lit pill behind the chosen CLI, which glides from one to the next. It shows only once the
   page has its script; until then the chosen button lights itself. */
.glide {
  position: absolute;
  top: 0;
  left: 0;
  visibility: hidden;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--vp-c-brand-1) 12%, transparent);
  pointer-events: none;
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
  position: relative;
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

.live .clis button.on {
  border-color: transparent;
  background: transparent;
}

.list {
  overflow: hidden;
}

/* The ways hang off a tree drawn in the gutter on their left: a spine down from the CLI and a
   branch to each way. */
.rows {
  position: relative;
  padding-left: 26px;
}

.tree {
  position: absolute;
  top: 0;
  left: 0;
  width: 26px;
  height: 100%;
  overflow: visible;
  pointer-events: none;
}

.tree path {
  fill: none;
  stroke-linecap: round;
}

.tree .spine,
.tree .branch {
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
  opacity: 0.75;
}

.tree .flow {
  stroke: var(--hmz-accent);
  stroke-width: 2.5;
  stroke-dasharray: 2 46;
}

.tree .root {
  fill: var(--hmz-accent);
}

.tree .knot {
  fill: var(--vp-c-bg);
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
}

.way-move {
  transition: transform 0.5s cubic-bezier(0.7, 0, 0.2, 1);
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
  font-size: 11px;
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

/* The part of a command not typed yet keeps its room, so the line does not reflow as it types;
   the caret rides at the end of what has been typed. */
.cmd .ghost {
  color: transparent;
}

.cmd.typing .ghost {
  border-left: 2px solid var(--hmz-warm);
  margin-left: -2px;
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

  /* A mote of light runs down the spine for as long as the lookup is on screen. */
  .tree .flow {
    animation: flow 2.8s linear infinite;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tree .flow {
    display: none;
  }
}

@keyframes flow {
  to {
    stroke-dashoffset: -48;
  }
}
</style>
