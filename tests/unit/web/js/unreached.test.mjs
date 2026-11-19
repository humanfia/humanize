import assert from 'node:assert/strict'
import { test } from 'node:test'

import { called, unreached } from '../../../../src/hmz/web/static/unreached.js'

test('Local is called Local, and any other daemon by its name', () => {
  assert.equal(called('local'), 'Local')
  assert.equal(called('lab'), 'lab')
})

test('a daemon out of reach says which, how it stands and why, in one sentence', () => {
  assert.equal(unreached('local', 'failed', 'unix: closed.').why, 'Local is unavailable, failed: unix: closed.')
  assert.equal(unreached('lab', 'connecting', 'no route').why, 'lab is unavailable, connecting: no route.')
  assert.equal(unreached('lab', 'failed', '').why, 'lab is unavailable, failed.')
})

test('what to do next follows from where the daemon is reached from', () => {
  assert.match(unreached('local', 'failed', '').next, /hmz web is still running.*Connect.*start it again/)
  assert.match(unreached('local', 'failed', '', { desktop: true }).next, /hmz is installed where your login shell finds it/)
  assert.match(unreached('box', 'failed', '', { kind: 'SSH' }).next, /ssh reaches its host/)
  assert.match(unreached('far', 'failed', '', { kind: 'P2P' }).next, /same secret.*paired/)
  assert.match(unreached('pal', 'failed', '', { kind: 'Paired' }).next, /machine is on/)
  for (const said of [unreached('local', 'failed', ''), unreached('box', 'failed', '', { kind: 'SSH' })]) assert.match(said.next, /\.$/)
})
