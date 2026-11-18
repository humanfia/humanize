import assert from 'node:assert/strict'
import { test } from 'node:test'

import { DEFAULT, MODES, NOTE, modeOf, offered, shown } from '../../../../src/hmz/web/static/chips/permission-modes.js'

test('the modes are the three presets the daemon holds a chat to, narrowest first', () => {
  assert.deepEqual(MODES.map((one) => one.value), ['read-only', 'workspace-write', 'danger-full-access'])
  assert.equal(DEFAULT, 'workspace-write')
})

test('each mode is named in a phrase and described in one line', () => {
  for (const { label, about } of MODES) {
    assert.ok(label.split(' ').length <= 4 && !/[.?!]$/.test(label), label)
    assert.ok(about && !about.includes('\n') && !/[.?!]$/.test(about), about)
  }
  assert.equal(new Set(MODES.map((one) => one.label)).size, MODES.length)
  assert.match(NOTE, /without asking/)
})

test('a permission that names no mode is read as the default', () => {
  assert.equal(modeOf('read-only').label, 'Read only')
  assert.equal(modeOf('danger-full-access').label, 'Full access')
  for (const none of [undefined, null, '', 'ask', 'plan']) assert.equal(modeOf(none).value, DEFAULT)
})

test('the menu marks the one in force and no other', () => {
  assert.deepEqual(offered('read-only').map((one) => one.chosen), [true, false, false])
  assert.deepEqual(offered(undefined).map((one) => one.chosen), [false, true, false])
  assert.deepEqual(offered('danger-full-access').map((one) => one.value), MODES.map((one) => one.value))
})

test('a chat shows what was picked here, else what its host says, else what its epic records', () => {
  assert.equal(shown(), DEFAULT)
  assert.equal(shown({ epic: { permission: '' } }), DEFAULT)
  assert.equal(shown({ epic: { permission: 'read-only' } }), 'read-only')
  assert.equal(shown({ host: { permission: 'danger-full-access' }, epic: { permission: 'read-only' } }), 'danger-full-access')
  assert.equal(shown({ picked: 'read-only', host: { permission: 'danger-full-access' } }), 'read-only')
  // A host that has not said yet -- an older daemon's -- leaves the epic's.
  assert.equal(shown({ host: {}, epic: { permission: 'read-only' } }), 'read-only')
})

test('a chat whose host says it has none to set shows none', () => {
  assert.equal(shown({ host: { permission: null } }), null)
  assert.equal(shown({ picked: 'read-only', host: { permission: null }, epic: { permission: 'read-only' } }), null)
})
