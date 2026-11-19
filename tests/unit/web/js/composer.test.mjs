import assert from 'node:assert/strict'
import { test } from 'node:test'

import { page } from './page.mjs'

const { body, el } = page()
const { composer } = await import('../../../../src/hmz/web/static/composer.js')
const { chain, closed, dismiss, opened } = await import('../../../../src/hmz/web/static/layers.js')

/** A box that offers one file for whatever is typed, in the page; and the list it offers it in. */
function box() {
  const made = composer({
    placeholder: 'Message',
    label: 'Message',
    submit: async () => {},
    complete: (text) => ({ from: 0, to: text.length, groups: [{ label: 'Files', items: [{ insert: '@notes.md', name: 'notes.md', about: '', tag: 'file', hint: '', refused: false }] }] }),
  })
  body.append(made.node)
  return { ...made, list: made.node.querySelector('[data-hmz=completions]') }
}

/** A menu open by a chip, as its owner keeps it. */
function menu() {
  const node = el('div', { class: 'popover' })
  body.append(node)
  const layer = {
    node,
    anchor: el('button'),
    close() {
      closed(layer)
      node.remove()
    },
  }
  opened(layer)
  return layer
}

/** Types into a box, and waits for what it offers. */
async function typed(made, text) {
  made.text.value = text
  await made.again()
}

test('what a box offers closes as a menu opens, as a dialog does, and as the page goes elsewhere', async () => {
  const made = box()
  await typed(made, '@')
  assert.equal(made.list.hidden, false)
  // The window sized or left, or the sidebar folded, it stays: nothing came to stand over it.
  for (const why of ['resize', 'blur', 'fold']) dismiss(why)
  assert.equal(made.list.hidden, false)
  menu().close()
  assert.equal(made.list.hidden, true)
  for (const why of ['dialog', 'route']) {
    await typed(made, '@')
    assert.equal(made.list.hidden, false)
    dismiss(why)
    assert.equal(made.list.hidden, true)
  }
  made.node.remove()
})

test('what a box offers closes no menu: it is no layer of its own', async () => {
  const made = box()
  const open = menu()
  await typed(made, '@')
  assert.equal(made.list.hidden, false)
  assert.deepEqual(chain(), [open])
  open.close()
  // The menu closed, what is offered stays: only one opening takes it away.
  assert.equal(made.list.hidden, false)
  made.node.remove()
})

test('closed by a key, what a box offers opens again with what is typed next, and closes as before', async () => {
  const made = box()
  await typed(made, '@')
  made.text.dispatchEvent(Object.assign(new Event('keydown', { cancelable: true }), { key: 'Escape' }))
  assert.equal(made.list.hidden, true)
  await typed(made, '@n')
  assert.equal(made.list.hidden, false)
  menu().close()
  assert.equal(made.list.hidden, true)
  made.node.remove()
})
