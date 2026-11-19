import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { daemon, provider, until } from './helpers.mjs'
import { page } from './page.mjs'

const { body, el, press, key } = page()

/** A daemon that knows one workspace. */
const served = daemon({ methods: { 'workspaces.list': () => ({ here: '', workspaces: [{ name: 'app', path: '/w/app' }] }) } })
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { chain, dismiss, opened } = await import('../../../../src/hmz/web/static/layers.js')
const { workspacePicker } = await import('../../../../src/hmz/web/static/places.js')

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
  made.node.remove()
  for (const closes of [() => press(body), () => dismiss('route'), () => dismiss('dialog'), () => opened({ node: el('div'), anchor: el('button'), close() {} })]) {
    const next = await opening()
    closes()
    assert.equal(next.form.hidden, true)
    assert.equal(next.button.getAttribute('aria-expanded'), 'false')
    dismiss('route')
    next.node.remove()
  }
})

test('the last thing in its row, the picker lines what it opens up with its end', async () => {
  for (const [offers, left] of [[{}, '1168px'], [{ end: true }, '1180px']]) {
    const made = await opening(offers)
    assert.equal(made.menuLeft, left)
    assert.equal(made.form.style.left, left)
    dismiss('route')
    made.node.remove()
  }
})
