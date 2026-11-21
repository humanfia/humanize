import assert from 'node:assert/strict'
import { test } from 'node:test'

import { EFFORTS, HARNESSES, effortName, harnessName, modelName, modelRoute, verseName } from '../../../../src/hmz/web/static/names.js'

test('every harness Humanize drives is named as its vendor names it, one unknown as written', () => {
  // The ids of `DRIVEN` (src/hmz/coganchor/agents/__init__.py).
  const driven = ['agy', 'claude', 'codex', 'cursor-agent', 'dsh', 'grok', 'kimi', 'litellm', 'mcode', 'mimo', 'omp', 'opencode', 'pi', 'qwen']
  assert.deepEqual(Object.keys(HARNESSES).sort(), driven)
  // The other ids a harness is asked for by (`aliases`, src/hmz/coganchor/backends.py).
  assert.deepEqual(['claude-code', 'cursor-cli', 'antigravity'].map(harnessName), ['Claude Code', 'Cursor CLI', 'Antigravity'])
  const named = { claude: 'Claude Code', codex: 'Codex', 'cursor-agent': 'Cursor CLI', agy: 'Antigravity', grok: 'Grok Build', kimi: 'Kimi Code', qwen: 'Qwen Code', opencode: 'OpenCode', mimo: 'MiMo Code', mcode: 'MiniMax Code', pi: 'Pi', omp: 'Oh My Pi', dsh: 'DeepSeek Harness', litellm: 'LiteLLM' }
  for (const [id, name] of Object.entries(named)) assert.equal(harnessName(id), name)
  // A CLI somebody added, and nothing inherited from a plain object.
  for (const raw of ['gemini', 'my-agent', 'constructor', '']) assert.equal(harnessName(raw), raw)
})

test('every rung of every ladder is named, no rung is `Default`, and a fleet is said after its rung', () => {
  // The rungs of the ladders in src/hmz/coganchor/backends.py.
  const rungs = ['ultracode', 'ultra', 'max', 'xhigh', 'extra-high', 'high', 'medium', 'low', 'minimal', 'none', 'off', 'as configured']
  assert.deepEqual(Object.keys(EFFORTS).sort(), [...rungs].sort())
  assert.equal(effortName('medium'), 'Medium')
  assert.equal(effortName('xhigh'), 'Extra high')
  assert.equal(effortName('extra-high'), 'Extra high')
  assert.equal(effortName('ultracode'), 'Ultracode')
  assert.equal(effortName('as configured'), 'As configured')
  assert.equal(effortName(''), 'Default')
  assert.equal(effortName('auto'), 'Default')
  assert.equal(effortName('swarmmax'), 'Max swarm')
  assert.equal(effortName('swarmxhigh'), 'Extra high swarm')
  for (const raw of ['hard', 'swarm', 'swarmhard', 'toString']) assert.equal(effortName(raw), raw)
})

test('a model is named as its vendor writes its family', () => {
  const named = {
    'claude-fable-5-2': 'Fable 5.2',
    'claude-opus-5': 'Opus 5',
    'claude-opus-5-5': 'Opus 5.5',
    'claude-sonnet-4-5': 'Sonnet 4.5',
    'claude-sonnet-4.5': 'Sonnet 4.5',
    'claude-opus-4-1': 'Opus 4.1',
    'claude-haiku-4-5-20251001': 'Haiku 4.5',
    'claude-opus-4-20250514': 'Opus 4',
    'claude-3-5-sonnet-20241022': 'Sonnet 3.5',
    'claude-3-5-sonnet-latest': 'Sonnet 3.5',
    // What Claude Code writes after one.
    'claude-opus-4-1-fast': 'Opus 4.1 Fast',
    'claude-sonnet-4-5[1m]': 'Sonnet 4.5 (1M)',
    // As a cloud serves one: its region and vendor before it, its revision after.
    'us.anthropic.claude-opus-4-1-20250805-v1:0': 'Opus 4.1',
    'anthropic.claude-3-5-sonnet-20241022-v2:0': 'Sonnet 3.5',
    'global.anthropic.claude-opus-4-6-v1': 'Opus 4.6',
    // Not a revision where no cloud serves it.
    'mimo-v2': 'MiMo-V2',
    // A date written with hyphens is a date still, and a rung that ends an id is said as an effort is.
    'gpt-5-2025-08-07': 'GPT-5',
    'gpt-5.2-low': 'GPT-5.2 Low',
    'gpt-5.1-codex-max-xhigh': 'GPT-5.1-Codex-Max Extra high',
    'gemini-2.5-pro-preview-tts': 'Gemini 2.5 Pro Preview TTS',
    'gpt-6.2-sol': 'GPT-6.2 Sol',
    'gpt-6-luna': 'GPT-6 Luna',
    'gpt-5': 'GPT-5',
    'gpt-5.2': 'GPT-5.2',
    'gpt-5.1-codex': 'GPT-5.1-Codex',
    'gpt-5.2-codex': 'GPT-5.2-Codex',
    'gpt-5.1-codex-max': 'GPT-5.1-Codex-Max',
    'gpt-5.1-codex-mini': 'GPT-5.1-Codex-Mini',
    'gpt-5.4-mini': 'GPT-5.4 mini',
    'gpt-5-mini': 'GPT-5 mini',
    'gpt-4o': 'GPT-4o',
    'gpt-4o-mini': 'GPT-4o mini',
    'gemini-3-pro': 'Gemini 3 Pro',
    'gemini-3.1-pro': 'Gemini 3.1 Pro',
    'gemini-3.7-flash': 'Gemini 3.7 Flash',
    'gemini-2.5-flash-lite': 'Gemini 2.5 Flash-Lite',
    'grok-4': 'Grok 4',
    'grok-4.6-build': 'Grok 4.6 Build',
    'grok-5-mini': 'Grok 5 Mini',
    'grok-code-fast-1': 'Grok Code Fast 1',
    'kimi-k3': 'Kimi K3',
    'kimi-k2.7-code': 'Kimi K2.7 Code',
    'kimi-for-coding': 'Kimi for Coding',
    qwen3: 'Qwen3',
    'qwen3-coder': 'Qwen3-Coder',
    'qwen3-coder-plus': 'Qwen3-Coder-Plus',
    'qwen3.5-plus': 'Qwen3.5-Plus',
    'deepseek-chat': 'DeepSeek-Chat',
    'deepseek-v4-flash': 'DeepSeek-V4-Flash',
    'deepseek-v4-pro': 'DeepSeek-V4-Pro',
    'MiniMax-M3': 'MiniMax-M3',
    'MiniMax-M2.7-highspeed': 'MiniMax-M2.7-highspeed',
    'mimo-v2-pro': 'MiMo-V2-Pro',
    'mimo-v2.5': 'MiMo-V2.5',
    'glm-5.3': 'GLM-5.3',
    'composer-2.5': 'Composer 2.5',
    'muse-spark-1.3': 'Muse Spark 1.3',
    auto: 'Auto',
    'as configured': 'As configured',
  }
  for (const [id, name] of Object.entries(named)) assert.equal(modelName(id), name, id)
})

test('whoever routes a model is no part of its name, and one of no family is said whole as written', () => {
  assert.equal(modelName('minimax/MiniMax-M3.1-Flash-Preview'), 'MiniMax-M3.1-Flash-Preview')
  assert.equal(modelName('anthropic/claude-sonnet-5'), 'Sonnet 5')
  assert.equal(modelName('openrouter/openai/gpt-5.2'), 'GPT-5.2')
  assert.equal(modelName('bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0'), 'Haiku 4.5')
  for (const raw of ['o3', 'o4-mini', 'opus', 'sonnet[1m]', 'claude-next', 'acme/some-model', 'meta.llama3-70b-instruct-v1:0', '']) assert.equal(modelName(raw), raw)
  // Who routes it, as its id says before its last `/`.
  assert.deepEqual(['azure/azure_ai/claude-opus-4-5', 'anthropic/claude-sonnet-5', 'gpt-5', ''].map(modelRoute), ['azure/azure_ai', 'anthropic', '', ''])
  assert.deepEqual(['bedrock/us.anthropic.claude-opus-5-v1:0', 'anthropic.claude-opus-5'].map(modelRoute), ['bedrock/us.anthropic', 'anthropic'])
})

test("Humanize's own flowverse is named with a capital, and another as it was called", () => {
  assert.equal(verseName('official'), 'Official')
  for (const raw of ['acme', 'theirs', 'officially', 'OFFICIAL', '']) assert.equal(verseName(raw), raw)
})
