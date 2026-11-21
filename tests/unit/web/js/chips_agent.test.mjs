import assert from 'node:assert/strict'
import { test } from 'node:test'

import { agentLabel, modelsNamed, nousLabel, nousNamed, nousOffered, nousSaid, offering, parted, spelled } from '../../../../src/hmz/web/static/chips/agent.js'

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

test('a chip says the harness, the model and the effort of an agent by name, `Default` where none is set', () => {
  assert.deepEqual(nousSaid('claude/claude-fable-5-2:medium'), { harness: 'Claude Code', model: 'Fable 5.2', effort: 'Medium' })
  assert.deepEqual(nousSaid('codex@work/gpt-6.2-sol'), { harness: 'Codex', model: 'GPT-6.2 Sol', effort: 'Default' })
  assert.deepEqual(nousSaid('codex/gpt-5:auto'), { harness: 'Codex', model: 'GPT-5', effort: 'Default' })
  // One the table does not hold is said as written.
  assert.deepEqual(nousSaid('mine/some-model:hard'), { harness: 'mine', model: 'some-model', effort: 'hard' })
  for (const none of ['', 'claude/', 'nothing']) assert.deepEqual(nousSaid(none), { harness: '', model: '', effort: '' })
  assert.equal(agentLabel('claude/claude-opus-4-1:max'), 'Claude Code Opus 4.1 Max')
  assert.equal(agentLabel('claude@work/claude-haiku-4-5'), 'Claude Code Haiku 4.5 Default')
  assert.equal(agentLabel(''), '')
  // A list of nous names each whole: the account and the effort only where it names them.
  assert.equal(nousNamed('claude/claude-opus-4-1'), 'Claude Code - Opus 4.1')
  assert.equal(nousNamed('claude@work/claude-opus-4-1:high'), 'Claude Code - Opus 4.1 · @work · High')
  assert.equal(nousNamed('codex/gpt-5.2-codex:auto'), 'Codex - GPT-5.2-Codex')
  assert.equal(nousNamed('fast'), 'fast')
  assert.equal(nousNamed(''), '')
  assert.equal(nousLabel('codex', 'gpt-6.2-sol'), 'Codex - GPT-6.2 Sol')
  assert.equal(nousLabel('mine', 'some-model'), 'mine - some-model')
})

test('every nous the harnesses here run is offered, a group a harness, the one chosen marked', () => {
  const chosen = parted('claude/claude-opus-4-1:max')
  const [claude, codex] = nousOffered(chosen, clis, names)
  assert.deepEqual([claude.cli, claude.name, claude.account, claude.state], ['claude', 'Claude Code', '', 'listed'])
  assert.deepEqual(claude.rows.map((one) => [one.label, one.spec, one.chosen]), [
    ['Claude Code - Haiku 4.5', 'claude/claude-haiku-4-5', false],
    ['Claude Code - Opus 4.1', 'claude/claude-opus-4-1', true],
  ])
  // A harness that lists nothing is a group of no row, which says why.
  assert.deepEqual([codex.name, codex.state, codex.rows], ['Codex', 'empty', []])
})

test('a harness runs as the account chosen for it, another as its own or the first that lists any', () => {
  const work = { accounts: [{ name: '', asked: true, models: [] }, { name: 'work', asked: true, models: [{ name: 'gpt-6.2-sol', efforts: [] }] }] }
  const [claude, codex] = nousOffered(parted('claude@work/'), { ...clis, codex: work }, names)
  assert.deepEqual([claude.account, claude.state], ['work', 'unasked'])
  assert.deepEqual(codex.rows.map((one) => [one.account, one.spec]), [['work', 'codex@work/gpt-6.2-sol']])
  // Being asked, and why asking failed, as `cli@account`.
  assert.equal(nousOffered(parted('claude@work/'), clis, names, { waiting: (key) => key === 'claude@work' })[0].state, 'asking')
  const failed = nousOffered(parted('claude@work/'), clis, names, { why: (key) => (key === 'claude@work' ? 'not signed in' : undefined) })[0]
  assert.deepEqual([failed.state, failed.why], ['failed', 'not signed in'])
})

test('a model nobody listed is a row of its harness, and a harness not installed is offered while chosen', () => {
  const [claude] = nousOffered(parted('claude/claude-next'), clis, names)
  assert.deepEqual(claude.rows.at(-1), { cli: 'claude', account: '', model: 'claude-next', named: 'claude-next', label: 'Claude Code - claude-next', spec: 'claude/claude-next', chosen: true, unlisted: true })
  // Not said unlisted while its harness is still being asked.
  assert.equal(nousOffered(parted('claude@work/claude-next'), clis, names, { waiting: () => true })[0].rows.at(-1).unlisted, false)
  const gone = nousOffered(parted('gemini/gemini-pro'), clis, names).at(-1)
  assert.deepEqual([gone.cli, gone.name, gone.rows.map((one) => one.label)], ['gemini', 'gemini', ['gemini - gemini-pro']])
})

test('no two nous of a harness are named alike: one model by two routes says who routes each', () => {
  const routed = ['azure_ai/claude-opus-4-5', 'vertex_ai/claude-opus-4-5', 'openrouter/anthropic/claude-opus-4-5', 'claude-opus-4-5', 'claude-opus-4-5-20251101', 'azure_ai/gpt-5', 'gemini/gemini-3-pro']
  assert.deepEqual(modelsNamed(routed), [
    'Opus 4.5 (azure_ai)',
    'Opus 4.5 (vertex_ai)',
    'Opus 4.5 (openrouter/anthropic)',
    // Routed by nobody, or as another of them is: its id whole.
    'Opus 4.5 (claude-opus-4-5)',
    'Opus 4.5 (claude-opus-4-5-20251101)',
    // One of a name of its own is named as ever.
    'GPT-5',
    'Gemini 3 Pro',
  ])
  assert.deepEqual(modelsNamed(['a/claude-opus-5', 'a/claude-opus-5-20260101']), ['Opus 5 (a/claude-opus-5)', 'Opus 5 (a/claude-opus-5-20260101)'])
  const litellm = { accounts: [{ name: '', asked: true, models: routed.map((name) => ({ name, efforts: [] })) }] }
  for (const group of nousOffered(parted('litellm/vertex_ai/claude-opus-4-5'), { ...clis, litellm }, [...names, 'litellm'])) {
    const labels = group.rows.map((one) => one.label)
    assert.equal(new Set(labels).size, labels.length, group.cli)
  }
  const [, , group] = nousOffered(parted('litellm/vertex_ai/claude-opus-4-5'), { ...clis, litellm }, [...names, 'litellm'])
  assert.deepEqual(group.rows.filter((one) => one.chosen).map((one) => [one.named, one.label, one.spec]), [['Opus 4.5 (vertex_ai)', 'LiteLLM - Opus 4.5 (vertex_ai)', 'litellm/vertex_ai/claude-opus-4-5']])
})

test('with nothing chosen, the first CLI, its own account and its first model are', () => {
  const chosen = { ...none }
  const offered = offering(chosen, clis, names)
  assert.deepEqual(chosen, { cli: 'claude', account: '', model: 'claude-haiku-4-5', effort: '' })
  assert.deepEqual(offered.clis, [{ value: 'claude', label: 'Claude Code' }, { value: 'codex', label: 'Codex' }])
  assert.deepEqual(offered.models.map((one) => one.label), ['Haiku 4.5', 'Opus 4.1'])
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
