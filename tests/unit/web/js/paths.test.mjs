import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { daemon, provider, until } from './helpers.mjs'
import { page } from './page.mjs'

const { body, el, press, key } = page()

/** A daemon whose home holds one folder. */
const served = daemon({
  methods: {
    'paths.list': ({ at }) => ({ at, whole: `/home/me${at.slice(1)}`, up: at === '~' ? '' : '~', entries: at === '~' ? [{ name: 'work', dir: true }] : [], more: 0 }),
  },
})
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { chain, closed, dismiss, opened } = await import('../../../../src/hmz/web/static/layers.js')
const { pathPicker } = await import('../../../../src/hmz/web/static/paths.js')

after(async () => (await api.client('local')).close())

/** A path picker in the page, under `holder`; with its field, its button and its panel. */
function picker(holder = body) {
  const made = pathPicker({ label: 'Folder' })
  holder.append(made.node)
  const parts = { ...made, browse: made.node.querySelector('[data-hmz=path-browse]'), panel: made.node.querySelector('[data-hmz=path-panel]') }
  parts.panel.box = { left: 0, top: 0, width: 440, height: 128 }
  return parts
}

/** Opens a picker's panel, and waits for the folder it lists. */
async function browsed(made) {
  made.browse.click()
  await until(() => made.panel.querySelector('.path-entry'))
}

test('the button that browses says what it opens, and whether it is open; pressed again, it closes it', async () => {
  const made = picker()
  assert.equal(made.browse.getAttribute('aria-haspopup'), 'dialog')
  assert.equal(made.browse.getAttribute('aria-expanded'), 'false')
  await browsed(made)
  assert.equal(made.panel.hidden, false)
  assert.equal(made.browse.getAttribute('aria-expanded'), 'true')
  assert.equal(chain().length, 1)
  // Its listing has the focus, as it had: the keys go through it.
  assert.ok(made.panel.contains(document.activeElement))
  made.browse.click()
  assert.equal(made.panel.hidden, true)
  assert.equal(made.browse.getAttribute('aria-expanded'), 'false')
  assert.equal(chain().length, 0)
  made.node.remove()
})

test('the panel closes as a menu does: by Escape, a press elsewhere, another opening, the page going elsewhere', async () => {
  const made = picker()
  await browsed(made)
  key('Escape')
  assert.equal(made.panel.hidden, true)
  // The focus it held goes back to the button that opened it.
  assert.equal(document.activeElement, made.browse)
  for (const closes of [() => press(body), () => dismiss('route'), () => dismiss('dialog'), () => opened({ node: el('div'), anchor: el('button'), close() {} })]) {
    await browsed(made)
    closes()
    assert.equal(made.panel.hidden, true)
    dismiss('route')
  }
  made.node.remove()
})

test('the panel stays while its field is pressed and typed into, and Escape from the field closes it alone', async () => {
  const made = picker()
  await browsed(made)
  press(made.input)
  made.input.focus()
  assert.equal(made.panel.hidden, false)
  // The window left or sized, what was browsed to is kept.
  for (const why of ['blur', 'resize']) dismiss(why)
  assert.equal(made.panel.hidden, false)
  key('Escape')
  assert.equal(made.panel.hidden, true)
  assert.equal(document.activeElement, made.input)
  made.node.remove()
})

test('a folder picked is written in the field, which has the focus back', async () => {
  const made = picker()
  await browsed(made)
  made.panel.querySelector('[data-hmz=path-choose]').click()
  assert.equal(made.value(), '~')
  assert.equal(made.panel.hidden, true)
  assert.equal(document.activeElement, made.input)
  assert.equal(chain().length, 0)
  made.node.remove()
})

test('in a form that floats the panel is that form’s: clear of all of it, closed alone, and closed with it', async () => {
  const form = el('form', { class: 'popover' })
  form.box = { left: 500, top: 640, width: 320, height: 120 }
  const chip = el('button')
  body.append(chip, form)
  const layer = {
    node: form,
    anchor: chip,
    kind: 'panel',
    close() {
      closed(layer)
      form.hidden = true
    },
  }
  opened(layer)
  const made = picker(form)
  await browsed(made)
  assert.equal(chain().length, 2)
  // Over the form, which stands low in the window, and ending where it ends.
  assert.equal(parseFloat(made.panel.style.top) + 128, 640 - 6)
  assert.equal(parseFloat(made.panel.style.left) + 440, 500 + 320)
  key('Escape')
  assert.equal(made.panel.hidden, true)
  assert.deepEqual(chain(), [layer])
  await browsed(made)
  // A press on the form closes the panel and leaves the form.
  press(form)
  assert.equal(made.panel.hidden, true)
  assert.deepEqual(chain(), [layer])
  await browsed(made)
  layer.close()
  assert.equal(made.panel.hidden, true)
  assert.equal(chain().length, 0)
  form.remove()
  chip.remove()
})

test('a field with a label over it has the panel clear of both, on the side with the more room', async () => {
  const field = el('div', { class: 'field' })
  field.box = { left: 700, top: 200, width: 340, height: 52 }
  body.append(field)
  const made = picker(field)
  await browsed(made)
  assert.equal(parseFloat(made.panel.style.top), 200 + 52 + 6)
  made.browse.click()
  field.box.top = 600
  await browsed(made)
  assert.equal(parseFloat(made.panel.style.top) + 128, 600 - 6)
  made.browse.click()
  field.remove()
})
