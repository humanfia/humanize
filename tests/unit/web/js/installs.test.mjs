// The dialog that asks before hmz is installed on a remote daemon's machine (Section 3.13.22 of
// protocol/web.md), drawn in a page with no browser: a `dialog` here is shown and closed as a
// browser's is, as far as the page tells.

import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { daemon, duplex, sleep, until } from './helpers.mjs'
import { page } from './page.mjs'

const { body } = page()
const make = document.createElement
document.createElement = (tag) => {
  const el = make(tag)
  if (tag !== 'dialog') return el
  el.returnValue = ''
  el.showModal = () => (el.open = true)
  el.close = (value) => {
    if (!el.open) return
    el.open = false
    if (value !== undefined) el.returnValue = value
    // A browser tells of it after, not within the call.
    setTimeout(() => el.dispatchEvent(new Event('close')))
  }
  return el
}

const NONE = (host) => `hmz is not installed on ${host}.`
const served = daemon()
/** Every route opened, and what each was answered. */
const opened = []
const answers = []
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, {
  opens: () => true,
  async open(route, id, { state, asked }) {
    opened.push(route)
    const host = route.slice('stdio:ssh://'.length)
    state('asking', NONE(host))
    const install = await asked()
    answers.push([host, install])
    if (!install) throw new Error(NONE(host))
    state('installing', 'hmz 1.2.3')
    const [mine, theirs] = duplex()
    served.serve(theirs)
    return mine
  },
})
await import('../../../../src/hmz/web/static/installs.js')
for (const name of ['box', 'den', 'far']) await api.daemons.add({ name, id: '', routes: [`stdio:ssh://${name}.example`] })

after(() => ['box', 'den', 'far'].forEach(api.forget))

const dialogs = () => body.querySelectorAll('[data-hmz=install-dialog]')
const asked = async (name) => {
  await until(() => dialogs().length === 1 && dialogs()[0].open && dialogs()[0].getAttribute('data-daemon') === name)
  return dialogs()[0]
}
const gone = () => until(() => dialogs().length === 0)

test('a daemon asking is asked about by its name, and Install installs', async () => {
  api.client('box')
  const dialog = await asked('box')
  assert.ok(dialog.open)
  assert.equal(dialog.querySelector('p').textContent, 'hmz is not installed on box. Install it?')
  assert.deepEqual(dialog.querySelectorAll('button').map((one) => one.textContent), ['Not now', 'Install'])
  assert.equal(api.stateOf('box').state, 'asking')
  dialog.querySelector('[data-hmz=install-yes]').click()
  await until(() => api.stateOf('box').state === 'up')
  await gone()
  assert.deepEqual(answers, [['box.example', true]])
})

test('a yes is kept: reached again, the daemon installs with no dialog', async () => {
  const states = []
  const stop = api.onState((name, state) => name === 'box' && states.push(state.state))
  await api.reconnect('box')
  await until(() => api.stateOf('box').state === 'up')
  stop()
  assert.ok(!states.includes('asking'), states.join(' '))
  assert.equal(dialogs().length, 0)
  assert.deepEqual(answers.at(-1), ['box.example', true])
})

test('Not now, Escape and a press beside it answer no, and Connect asks again', async () => {
  const no = [
    (dialog) => dialog.querySelector('[data-hmz=install-no]').click(),
    // As a browser closes it for Escape, and layers.js for a press on its backdrop.
    (dialog) => dialog.close(),
  ]
  api.client('den')
  for (const act of no) {
    const dialog = await asked('den')
    const before = opened.length
    act(dialog)
    await until(() => api.stateOf('den').state === 'failed')
    await gone()
    assert.deepEqual(api.stateOf('den'), { state: 'failed', detail: NONE('den.example') })
    assert.deepEqual(answers.at(-1), ['den.example', false])
    // Not reached again by itself: the first wait would be a second.
    await sleep(1200)
    assert.equal(opened.length, before)
    assert.equal(dialogs().length, 0)
    api.reconnect('den')
  }
  // A no is not kept: it asks again.
  await asked('den')
  api.forget('den')
  await gone()
})

test('the dialog goes unanswered once the daemon no longer asks, and asks one daemon at a time', async () => {
  const before = answers.length
  api.client('den')
  await asked('den')
  api.client('far')
  await until(() => api.stateOf('far').state === 'asking')
  assert.equal(dialogs().length, 1)
  // Let go of, den is asked about no more, and far is.
  api.forget('den')
  const dialog = await asked('far')
  assert.equal(answers.length, before)
  assert.equal(dialog.querySelector('p').textContent, 'hmz is not installed on far. Install it?')
  // The page gone elsewhere under it, it still asks.
  dispatchEvent(new Event('hmz:route'))
  const again = await asked('far')
  assert.equal(answers.length, before)
  again.querySelector('[data-hmz=install-no]').click()
  await gone()
  assert.deepEqual(answers.slice(before), [['far.example', false]])
})

test('a yes is to the machine the routes reached: kept while they stand, and not once they change', async () => {
  // Edited to the routes it had, box is reached afresh and is not asked about.
  await api.daemons.update('box', { name: 'box', routes: ['stdio:ssh://box.example'] })
  api.forget('box')
  await api.client('box')
  await until(() => api.stateOf('box').state === 'up')
  assert.equal(dialogs().length, 0)
  // Its name another machine's, that machine is asked about: by an edit, and removed and added.
  await api.daemons.update('box', { name: 'box', routes: ['stdio:ssh://other.example'] })
  api.forget('box')
  api.client('box')
  ;(await asked('box')).querySelector('[data-hmz=install-yes]').click()
  await until(() => api.stateOf('box').state === 'up')
  assert.deepEqual(answers.at(-1), ['other.example', true])
  await api.daemons.remove('box')
  api.forget('box')
  await api.daemons.add({ name: 'box', id: '', routes: ['stdio:ssh://third.example'] })
  api.client('box')
  ;(await asked('box')).querySelector('[data-hmz=install-no]').click()
  await gone()
  assert.deepEqual(answers.at(-1), ['third.example', false])
})

test('a daemon let go of while its route still probes is not asked about, and its answer is kept for nobody', async () => {
  // The route of the client let go of finds no hmz only after: it asks nobody.
  let found
  const [probing] = api.providers
  api.providers.splice(0, 1, {
    opens: () => true,
    async open(route, id, options) {
      await new Promise((resolve) => (found = resolve))
      if (!options.signal.aborted) return probing.open(route, id, options)
      // Given up meanwhile, what it found is said to nobody.
      options.state('asking', NONE('old.example'))
      options.asked()
      throw new Error('Given up.')
    },
  })
  after(() => api.providers.splice(0, 1, probing))
  await api.daemons.add({ name: 'old', id: '', routes: ['stdio:ssh://old.example'] })
  after(() => api.forget('old'))
  const states = []
  const stop = api.onState((name, state) => name === 'old' && states.push(state.state))
  await api.client('old')
  await until(() => found)
  const late = found
  found = undefined
  api.forget('old')
  late()
  await sleep(50)
  assert.deepEqual([...new Set(states)], ['connecting', 'idle'])
  assert.equal(dialogs().length, 0)
  // Answered when no client of it asks, nothing is kept: the next client of that name asks.
  api.answer('old', true)
  api.client('old')
  await until(() => found)
  found()
  ;(await asked('old')).querySelector('[data-hmz=install-no]').click()
  await gone()
  stop()
})
