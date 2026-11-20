import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { daemon, provider, until } from './helpers.mjs'
import { page } from './page.mjs'

const { body, el, press, key } = page()

/** What the daemon lists: one workspace, until a test says otherwise. */
const ONE = { here: '', workspaces: [{ name: 'app', path: '/w/app' }] }
let listed = ONE
const served = daemon({ methods: { 'workspaces.list': () => listed } })
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { chain, dismiss, opened } = await import('../../../../src/hmz/web/static/layers.js')
const { firstOf, firstWorkspace, goneSaid, lostSaid, missing, unplaced, workspacePicker, workspaces } = await import('../../../../src/hmz/web/static/places.js')

after(async () => (await api.client('local')).close())

/** The folder picker in the page, its menu's `Open folder…` picked. */
async function opening(offers) {
  const made = workspacePicker('/w/app', () => {}, offers)
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=workspace-picker]')
  const form = made.node.querySelector('form')
  await until(() => button.textContent === 'app')
  button.box = { left: 1168, top: 8, width: 112, height: 28 }
  button.click()
  made.menuLeft = made.node.querySelector('[role=menu]').style.left
  made.node.querySelectorAll('[role=menuitem]').find((one) => one.textContent === 'Open folder…').click()
  return { ...made, button, form, field: form.querySelector('input') }
}

test('the form a folder is opened by takes the place of the menu it was picked from', async () => {
  const made = await opening()
  assert.equal(made.form.hidden, false)
  assert.equal(made.node.querySelector('[role=menu]'), null)
  assert.equal(chain().length, 1)
  assert.equal(made.button.getAttribute('aria-expanded'), 'true')
  assert.equal(document.activeElement, made.field)
  // The button pressed again shuts it, and opens no menu behind it.
  made.button.click()
  assert.equal(made.form.hidden, true)
  assert.equal(made.node.querySelector('[role=menu]'), null)
  assert.equal(made.button.getAttribute('aria-expanded'), 'false')
  assert.equal(chain().length, 0)
  // Shut, the button opens its menu again.
  made.button.click()
  assert.ok(made.node.querySelector('[role=menu]'))
  dismiss('route')
  made.leave()
  made.node.remove()
})

test('the form closes as a menu does, from wherever in it the focus is, and keeps what is typed while the window is left', async () => {
  const made = await opening()
  made.field.value = '~/work'
  for (const why of ['blur', 'resize']) dismiss(why)
  assert.equal(made.form.hidden, false)
  made.form.querySelector('[type=submit]').focus()
  key('Escape')
  assert.equal(made.form.hidden, true)
  assert.equal(document.activeElement, made.button)
  made.leave()
  made.node.remove()
  for (const closes of [() => press(body), () => dismiss('route'), () => dismiss('dialog'), () => opened({ node: el('div'), anchor: el('button'), close() {} })]) {
    const next = await opening()
    closes()
    assert.equal(next.form.hidden, true)
    assert.equal(next.button.getAttribute('aria-expanded'), 'false')
    dismiss('route')
    next.leave()
    next.node.remove()
  }
})

/** Has the daemon list other workspaces, and waits until whoever watches them was told. */
async function lists(answer) {
  listed = answer
  api.refresh('workspaces.list')
  let seen
  const stop = api.poll('workspaces.list', {}, null, (data) => (seen = data))
  await until(() => JSON.stringify(seen) === JSON.stringify(answer))
  stop()
}

/** A row of `workspaces.list`. */
const row = (name, there) => ({ name, path: `/w/${name}`, ...(there === undefined ? {} : { there }) })

test('the workspace offered first is never one whose directory is gone', () => {
  // Where `hmz web` started, while it is there; a daemon that says nothing of `there` means it is.
  assert.equal(firstOf({ here: '/w/here', workspaces: [row('here'), row('app')] }), '/w/here')
  assert.equal(firstOf({ here: '/w/here', workspaces: [row('app')] }), '/w/here')
  // Gone, it is passed over for the first listed that is there.
  assert.equal(firstOf({ here: '/w/here', workspaces: [row('here', false), row('old', false), row('app', true), row('next', true)] }), '/w/app')
  assert.equal(firstOf({ here: '', workspaces: [row('old', false), row('app')] }), '/w/app')
  // None there, or none at all: the user's home.
  assert.equal(firstOf({ here: '/w/here', workspaces: [row('here', false), row('old', false)] }), '~')
  assert.equal(firstOf({ here: '', workspaces: [] }), '~')
})

test('a directory is missing only where the daemon listed it and said it is not there', () => {
  const answer = { workspaces: [row('app', true), row('old', false), row('plain')] }
  assert.equal(missing('/w/old', answer), true)
  for (const path of ['/w/app', '/w/plain', '/w/unlisted', '', null]) assert.equal(missing(path, answer), false)
  assert.equal(missing('/w/old', null), false)
})

test('a start refused for a directory that is gone is said as the form says it', () => {
  const gone = new api.Refused('There is no directory /w/old.', 404)
  assert.equal(unplaced(gone, '/w/old').message, 'The folder old is no longer on this machine. Pick another folder.')
  assert.equal(unplaced(gone, '/w/old').message, goneSaid('/w/old'))
  // A chat carried on there has no other to pick.
  assert.equal(unplaced(gone, '/w/old', lostSaid).message, 'The folder old is no longer on this machine.')
  // Any other refusal keeps its own words.
  for (const other of [new api.Refused('No such flow.', 404), new api.Refused('There is no directory /w/old.', 400), new Error('Unreachable.')]) assert.equal(unplaced(other, '/w/old'), other)
})

test('the first workspace is read again, so that one gone since is not offered', async () => {
  try {
    listed = { here: '', workspaces: [row('old', false), row('app', true)] }
    await workspaces(true)
    assert.equal(await firstWorkspace(), '/w/app')
    listed = { here: '', workspaces: [row('old', false), row('app', false)] }
    await workspaces(true)
    assert.equal(await firstWorkspace(), '~')
  } finally {
    listed = ONE
    await workspaces(true)
  }
})

test('the menu lists the folders that are there, and the one chosen though it is gone, said to be missing', async () => {
  await lists({ here: '', workspaces: [row('app', true), row('old', false), row('lost', false)] })
  const made = workspacePicker('/w/old', () => {}, { plain: true })
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=workspace-picker]')
  try {
    await until(() => made.gone())
    assert.equal(button.textContent, 'old (missing)')
    assert.equal(button.getAttribute('aria-invalid'), 'true')
    assert.ok(button.classList.contains('gone'))
    assert.equal(button.dataset.tip, 'This folder is no longer on this machine: /w/old')
    button.click()
    const rows = made.node.querySelectorAll('[role=menuitem]')
    assert.deepEqual(rows.map((one) => one.textContent), ['app', 'oldMissing', 'Open folder…'])
    assert.ok('missing' in rows[1].dataset)
    dismiss('route')
    // Another picked, the one that is gone is offered no more.
    rows[0].click()
    assert.equal(made.gone(), false)
    assert.equal(button.textContent, 'app')
    assert.equal(button.getAttribute('aria-invalid'), null)
    button.click()
    assert.deepEqual(made.node.querySelectorAll('[role=menuitem]').map((one) => one.textContent), ['app', 'Open folder…'])
    dismiss('route')
  } finally {
    made.leave()
    made.node.remove()
    await lists(ONE)
  }
})

test('a folder chosen that goes while the picker stands is said to be gone, and to be back', async () => {
  const told = []
  /** What `workspaces` answers of the folder as the picker says it went or came back, as a form reads it then. */
  const read = []
  // Read a moment before it goes: an answer the forms would still take for fresh.
  await workspaces(true)
  const made = workspacePicker('/w/app', () => {}, { went: (gone) => (told.push(gone), read.push(workspaces().then((answer) => missing('/w/app', answer)))) })
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=workspace-picker]')
  try {
    await until(() => button.textContent === 'app')
    assert.equal(made.gone(), false)
    await lists({ here: '', workspaces: [row('app', false)] })
    await until(() => made.gone())
    assert.equal(button.textContent, 'app (missing)')
    await lists({ here: '', workspaces: [row('app', true)] })
    await until(() => !made.gone())
    assert.equal(button.textContent, 'app')
    assert.ok(!button.classList.contains('gone'))
    assert.deepEqual(told, [true, false])
    // Whoever is told reads the answer that said so, never one from before it.
    assert.deepEqual(await Promise.all(read), [true, false])
    // Left, it hears no more of the directories.
    made.leave()
    await lists({ here: '', workspaces: [row('app', false)] })
    await new Promise((resolve) => setTimeout(resolve, 30))
    assert.equal(made.gone(), false)
  } finally {
    made.leave()
    made.node.remove()
    await lists(ONE)
  }
})

test('a picker opened on no folder names the first that is there', async () => {
  await lists({ here: '/w/here', workspaces: [row('here', false), row('app', true)] })
  const made = workspacePicker('', () => {})
  try {
    await until(() => made.value() === '/w/app')
    assert.equal(made.gone(), false)
  } finally {
    made.leave()
    await lists(ONE)
  }
})
