// The one table the page names a harness, a model and an effort by (Section 3.4.4.11 of
// protocol/web.md): a harness and a model as its vendor writes it, where its id is what `-a`
// spells -- `claude` is `Claude Code`, `claude-fable-5-2` is `Fable 5.2` -- and an effort by the
// page's own word for it, said in the page's language as every text of the page is: `xhigh` is
// `Extra high`. An id the table does not hold is said as it is written. Nothing here is drawn
// and nothing but the page's languages is imported, so that every part of the page says the
// same name and the table is tested alone.

import { t } from './i18n.js'

/** Every harness Humanize drives, by the name its vendor gives the product. */
export const HARNESSES = {
  agy: 'Antigravity',
  claude: 'Claude Code',
  codex: 'Codex',
  'cursor-agent': 'Cursor CLI',
  dsh: 'DeepSeek Harness',
  grok: 'Grok Build',
  kimi: 'Kimi Code',
  litellm: 'LiteLLM',
  mcode: 'MiniMax Code',
  mimo: 'MiMo Code',
  omp: 'Oh My Pi',
  opencode: 'OpenCode',
  pi: 'Pi',
  qwen: 'Qwen Code',
}

/** The other ids a harness is asked for by (`aliases`, src/hmz/coganchor/backends.py). */
const ALIASES = { antigravity: 'agy', 'claude-code': 'claude', 'cursor-cli': 'cursor-agent' }

/** Every rung of every harness's ladder, in the page's language; `xhigh` and Cursor's `extra-high` are one name. `Ultracode` is a product's name, kept as written. */
export const EFFORTS = {
  ultracode: 'Ultracode',
  ultra: t('Ultra'),
  max: t('Max'),
  xhigh: t('Extra high'),
  'extra-high': t('Extra high'),
  high: t('High'),
  medium: t('Medium'),
  low: t('Low'),
  minimal: t('Minimal'),
  none: t('None@@effort'),
  off: t('Off'),
  'as configured': t('As configured'),
}

/** What an effort is prefixed with to ask for a fleet of subagents: `swarmmax` is `Max swarm`. */
const SWARM = 'swarm'

/** Words a vendor writes all in capitals. */
const LOUD = new Set(['tts'])
const cap = (word) => (LOUD.has(word) ? word.toUpperCase() : word ? `${word[0].toUpperCase()}${word.slice(1)}` : word)
/** The words of an id after its family, each begun with a capital: joined as the vendor joins them. */
const words = (rest, by) => rest.split('-').filter(Boolean).map(cap).join(by)
/** Words OpenAI writes small after a model's number: `GPT-5.4 mini`. */
const SMALL = new Set(['mini', 'nano', 'pro'])

/** The rungs a harness writes onto a model's id where each is a model of its list: `gpt-5.2-high`. */
const RUNGS = new Set(['minimal', 'low', 'medium', 'high', 'xhigh'])

/**
 * `GPT-5.1-Codex-Max`, `GPT-5.4 mini`, `GPT-6.2 Sol`: Codex and what follows it is hyphened on,
 * and a rung that ends the id is said after the name, as an effort is: `GPT-5.1-Codex-Max Extra high`.
 */
function gpt(version, rest) {
  const parts = rest.split('-').filter(Boolean)
  const rung = RUNGS.has(parts.at(-1)) ? ` ${EFFORTS[parts.pop()]}` : ''
  const codex = parts.indexOf('codex')
  const plain = (codex < 0 ? parts : parts.slice(0, codex)).map((one) => ` ${SMALL.has(one) ? one : cap(one)}`).join('')
  return `GPT-${version}${plain}${codex < 0 ? '' : `-${parts.slice(codex).map(cap).join('-')}`}${rung}`
}

/**
 * The families of models, the first that fits naming it: an id is open-ended -- a harness is
 * asked what it runs -- so a family is a row, not each model.
 */
const MODELS = [
  // What Claude Code writes after one: `-fast`, and `[1m]` for the long window.
  [/^claude-([a-z]+)-(\d{1,2})(?:[-.](\d{1,2}))?(-fast)?(\[1m\])?$/, (m) => `${cap(m[1])} ${m[2]}${m[3] ? `.${m[3]}` : ''}${m[4] ? ' Fast' : ''}${m[5] ? ' (1M)' : ''}`],
  // As Anthropic once wrote them: `claude-3-5-sonnet`.
  [/^claude-(\d{1,2})(?:[-.](\d{1,2}))?-([a-z]+)$/, (m) => `${cap(m[3])} ${m[1]}${m[2] ? `.${m[2]}` : ''}`],
  [/^gpt-(\d+(?:\.\d+)?o?)((?:-[a-z0-9.]+)*)$/, (m) => gpt(m[1], m[2])],
  [/^gemini-(\d+(?:\.\d+)?)-([a-z0-9.-]+)$/, (m) => `Gemini ${m[1]} ${words(m[2], ' ').replace('Flash Lite', 'Flash-Lite')}`],
  [/^grok-([a-z0-9.-]+)$/, (m) => `Grok ${words(m[1], ' ')}`],
  [/^kimi-([a-z0-9.-]+)$/, (m) => `Kimi ${words(m[1], ' ')}`.replace(' For ', ' for ')],
  [/^qwen(\d+(?:\.\d+)?)?((?:-[a-z0-9.]+)*)$/, (m) => `Qwen${m[1] ?? ''}${m[2] ? `-${words(m[2], '-')}` : ''}`],
  [/^deepseek-([a-z0-9.-]+)$/, (m) => `DeepSeek-${words(m[1], '-')}`],
  // MiniMax writes its own capitals into the id: `MiniMax-M2.7-highspeed`.
  [/^MiniMax-.+$/, (m) => m[0]],
  [/^minimax-([a-z0-9.-]+)$/, (m) => `MiniMax-${words(m[1], '-')}`],
  [/^mimo-([a-z0-9.-]+)$/, (m) => `MiMo-${words(m[1], '-')}`],
  [/^glm-([a-z0-9.-]+)$/, (m) => `GLM-${words(m[1], '-')}`],
  [/^composer-([0-9.]+)$/, (m) => `Composer ${m[1]}`],
  [/^muse-spark-([0-9.]+)$/, (m) => `Muse Spark ${m[1]}`],
  [/^auto$/, () => 'Auto'],
  [/^as configured$/, () => t('As configured')],
]

/** A harness by its vendor's name for it: `claude` is `Claude Code`; one unknown, as written. */
export function harnessName(id) {
  const known = Object.hasOwn(ALIASES, id) ? ALIASES[id] : id
  return Object.hasOwn(HARNESSES, known) ? HARNESSES[known] : id || ''
}

/** The region and the vendor a cloud writes before a model it serves: `us.anthropic.`, `anthropic.`. */
const CLOUD = /^(?:[a-z-]+\.)?[a-z]+\.(?=[a-z])/

/**
 * A model's id without whoever routes it, the region and vendor a cloud writes before it
 * (`us.anthropic.`), the revision it writes after it (`-v1:0`) and the date it was cut.
 */
function bare(id) {
  const tail = String(id || '').split('/').pop()
  const served = tail.replace(CLOUD, '')
  return (served === tail ? tail : served.replace(/-v\d+(?::\d+)?$/, '')).replace(/-(?:\d{8}|\d{4}-\d{2}-\d{2}|latest)$/, '')
}

/**
 * Whoever routes a model and the cloud that serves it, as its id says before the model itself:
 * `azure_ai` of `azure_ai/gpt-5`, `bedrock/us.anthropic` of `bedrock/us.anthropic.claude-opus-5-v1:0`;
 * '' where nobody does.
 */
export function modelRoute(id) {
  const text = String(id || '')
  const tail = text.split('/').pop()
  return text.slice(0, text.length - tail.length + (CLOUD.exec(tail)?.[0].length ?? 0)).replace(/[/.]$/, '')
}

/**
 * A model by its vendor's name for it: `claude-fable-5-2` is `Fable 5.2`, `gpt-6.2-sol` is
 * `GPT-6.2 Sol`. Whoever routes it (`minimax/MiniMax-M3`), the cloud it is served from
 * (`us.anthropic.claude-opus-4-1-20250805-v1:0`) and the date it was cut
 * (`claude-haiku-4-5-20251001`, `gpt-5-2025-08-07`) are no part of its name; one of no family
 * here is said whole, as written.
 */
export function modelName(id) {
  const tail = bare(id)
  for (const [family, name] of MODELS) {
    const found = family.exec(tail)
    if (found) return name(found)
  }
  return id || ''
}

/** An effort by its name: none, or `auto` as an epic writes none down, is the model's own. */
export function effortName(id) {
  if (!id || id === 'auto') return t('Default')
  if (Object.hasOwn(EFFORTS, id)) return EFFORTS[id]
  const rung = id.startsWith(SWARM) ? id.slice(SWARM.length) : ''
  return Object.hasOwn(EFFORTS, rung) ? t('{effort} swarm', { effort: EFFORTS[rung] }) : id
}

/** A flowverse as the page names it: Humanize's own with a capital, another as it was called. */
export const verseName = (name) => (name === 'official' ? t('Official') : name)
