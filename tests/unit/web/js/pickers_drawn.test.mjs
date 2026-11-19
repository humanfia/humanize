import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { daemon, provider, until } from './helpers.mjs'
import { page } from './page.mjs'

const { body } = page()

/** A daemon with one CLI that cannot say what it runs, for a reason longer than a line. */
const WHY = 'claude exited 1 before it listed its models: the sign-in has expired, sign in again on the machine the daemon runs on'
let refused = true
const served = daemon({
  methods: {
    'flows.backends': () => ({ clis: { claude: { accounts: [{ name: '', asked: !refused, models: refused ? [] : [{ name: 'claude-haiku-4-5', efforts: [] }] }] } } }),
    'accounts.models': () => {
      if (refused) throw new Error(WHY)
      return {}
    },
  },
})
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { agentPicker, anyCli, readBackends } = await import('../../../../src/hmz/web/static/pickers.js')

after(async () => (await api.client('local')).close())

test('what a picker says of its models is its tip too, whole, and gone when it says nothing', async () => {
  await readBackends('/w')
  const made = agentPicker(anyCli('assistant'), 'claude', () => {})
  body.append(made.node)
  const said = made.node.querySelector('.hint')
  // Why there are none is one line on the page, and the whole of it where the pointer rests.
  await until(() => said.textContent.startsWith('No models: '))
  assert.ok(said.textContent.endsWith(WHY))
  assert.equal(said.dataset.tip, said.textContent)
  // Asked again and answered, it says nothing, and no tip says what it said before.
  refused = false
  made.node.querySelector('[aria-label="Refresh models"]').click()
  await until(() => made.value() === 'claude/claude-haiku-4-5')
  assert.equal(said.textContent, '')
  assert.equal(said.dataset.tip, '')
  made.leave()
  made.node.remove()
})
