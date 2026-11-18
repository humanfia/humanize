import assert from 'node:assert/strict'
import { test } from 'node:test'

import { agentLabel, effortName, modelName, offering, parted, spelled } from '../../../../src/hmz/web/static/chips/agent.js'

/** The CLIs of a machine, as `flows.backends` answers them. */
const clis = {
  claude: {
    accounts: [
      {
        name: '',
        asked: true,
        models: [
          { name: 'claude-haiku-4-5', efforts: [] },
          { name: 'claude-opus-4-1', efforts: ['low', 'high', 'max'] },
        ],
      },
      { name: 'work', asked: false, models: [] },
      { name: 'mute', asked: true, models: [] },
    ],
  },
  codex: { accounts: [] },
}
const names = Object.keys(clis)
const none = { cli: '', account: '', model: '', effort: '' }

test('an agent is taken apart and put back together as `-a` spells it', () => {
  assert.deepEqual(parted('claude@work/claude-opus-4-1:max'), { cli: 'claude', account: 'work', model: 'claude-opus-4-1', effort: 'max' })
  assert.deepEqual(parted('claude/claude-haiku-4-5'), { cli: 'claude', account: '', model: 'claude-haiku-4-5', effort: '' })
  assert.deepEqual(parted('nothing'), none)
  for (const spec of ['claude@work/claude-opus-4-1:max', 'claude/claude-haiku-4-5', 'codex/gpt-5']) assert.equal(spelled(parted(spec)), spec)
  assert.equal(spelled({ cli: 'claude', account: '', model: 'm', effort: 'auto' }), 'claude/m')
  assert.equal(spelled({ cli: 'claude', account: '', model: '', effort: '' }), '')
})

test('a chip says the model as a person reads it, and its effort where one is set', () => {
  assert.equal(modelName('claude-opus-4-1'), 'Opus 4.1')
  assert.equal(modelName('claude-haiku-4-5-20251001'), 'Haiku 4.5')
  assert.equal(modelName('claude-opus-4-20250514'), 'Opus 4')
  assert.equal(modelName('claude-3-5-sonnet-20241022'), 'Sonnet 3.5')
  // Any other name is said as it is.
  for (const raw of ['gpt-5.1-codex', 'opus', 'sonnet[1m]', 'claude-opus-4-1-fast']) assert.equal(modelName(raw), raw)
  assert.equal(effortName('max'), 'Max')
  assert.equal(effortName(''), 'Default')
  assert.equal(effortName('auto'), 'Default')
  assert.equal(agentLabel('claude/claude-opus-4-1:max'), 'Opus 4.1 Max')
  assert.equal(agentLabel('claude@work/claude-haiku-4-5'), 'Haiku 4.5')
  assert.equal(agentLabel('codex/gpt-5:auto'), 'gpt-5')
  assert.equal(agentLabel(''), '')
})

test('with nothing chosen, the first CLI, its own account and its first model are', () => {
  const chosen = { ...none }
  const offered = offering(chosen, clis, names)
  assert.deepEqual(chosen, { cli: 'claude', account: '', model: 'claude-haiku-4-5', effort: '' })
  assert.deepEqual(offered.clis, [{ value: 'claude', label: 'claude' }, { value: 'codex', label: 'codex' }])
  assert.deepEqual(offered.accounts.map((one) => one.label), ['Local', 'work', 'mute'])
  assert.deepEqual(offered.models.map((one) => one.value), ['claude-haiku-4-5', 'claude-opus-4-1'])
  assert.deepEqual(offered.efforts, [])
  assert.equal(offered.unlisted, false)
  assert.equal(offered.typed, false)
  assert.equal(offered.unasked, false)
})

test('an effort is kept only where the model takes it', () => {
  const chosen = parted('claude/claude-opus-4-1:max')
  assert.deepEqual(offering(chosen, clis, names).efforts, ['low', 'high', 'max'])
  assert.equal(chosen.effort, 'max')
  chosen.model = 'claude-haiku-4-5'
  offering(chosen, clis, names)
  assert.equal(chosen.effort, '')
})

test('a model nobody listed is kept, and said to be unlisted', () => {
  const chosen = parted('claude/claude-next:high')
  const offered = offering(chosen, clis, names)
  assert.equal(chosen.model, 'claude-next')
  assert.equal(chosen.effort, '')
  assert.equal(offered.unlisted, true)
})

test('an account that is not one of the CLI is left for its own', () => {
  const chosen = parted('claude@gone/claude-opus-4-1')
  offering(chosen, clis, names)
  assert.equal(chosen.account, '')
})

test('a CLI that is not installed is offered as such, and one unknown gives way to the first', () => {
  const kept = parted('gemini/gemini-pro')
  assert.deepEqual(offering(kept, { ...clis, gemini: { accounts: [] } }, names).clis.at(-1), { value: 'gemini', label: 'gemini (not installed)' })
  const unknown = parted('gemini/gemini-pro')
  offering(unknown, clis, names)
  assert.equal(unknown.cli, 'claude')
  assert.deepEqual(offering({ ...none }, {}, []).clis, [{ value: '', label: 'None installed' }])
})

test('a CLI with no account of its own offers this machine’s', () => {
  const offered = offering(parted('codex/gpt-5'), clis, names)
  assert.deepEqual(offered.accounts, [{ value: '', label: 'Local' }])
  assert.equal(offered.unlisted, true)
  assert.equal(offered.unasked, false)
})

test('an account nobody asked yet is to be asked; while it is, or once it failed, it is not', () => {
  const chosen = () => parted('claude@work/')
  assert.equal(offering(chosen(), clis, names).unasked, true)
  const asking = offering(chosen(), clis, names, { waiting: (key) => key === 'claude@work' })
  assert.equal(asking.asking, true)
  assert.equal(asking.unasked, false)
  assert.equal(asking.typed, false)
  const failed = offering(chosen(), clis, names, { why: (key) => (key === 'claude@work' ? 'not signed in' : undefined) })
  assert.equal(failed.failed, 'not signed in')
  assert.equal(failed.unasked, false)
  // Typed where nothing could be listed: refused, or asked and told nothing.
  assert.equal(failed.typed, true)
  assert.equal(offering(parted('claude@mute/'), clis, names).typed, true)
})
