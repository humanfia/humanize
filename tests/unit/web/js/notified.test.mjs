import assert from 'node:assert/strict'
import { test } from 'node:test'

import { addressOf, gathered, KEPT, kindOf, lineOf, of } from '../../../../src/hmz/web/static/notified.js'
import { stored } from '../../../../src/hmz/web/static/stored.js'
import { fakeIndexedDB } from './helpers.mjs'

/** A notice as a daemon makes one. */
const notice = (id, fields = {}) => ({ id, kind: 'done', workspace: '/w', slot: '', epic: `e${id}`, flow: 'f', task: 't', role: '', text: '', at: id, ...fields })

test('a chat turn done and a flow listening are chat turns; every other notice is its own kind', () => {
  assert.equal(kindOf(notice(1, { slot: 'chat:ab' })), 'listening')
  assert.equal(kindOf(notice(1, { kind: 'listening' })), 'listening')
  assert.equal(kindOf(notice(1)), 'done')
  assert.equal(kindOf(notice(1, { kind: 'asked', slot: 'chat:ab' })), 'asked')
})

test('notices of every daemon gather into one list, newest first, each naming its daemon', async () => {
  const kept = gathered(stored('n', fakeIndexedDB()))
  await kept.heard('local', notice(1))
  await kept.heard('box', notice(1))
  // Heard twice, kept once.
  assert.equal(await kept.heard('local', notice(1)), null)
  const items = await kept.items()
  assert.deepEqual(items.map((one) => [one.daemon, one.id, one.read]), [['box', 1, false], ['local', 1, false]])
  assert.equal(await kept.after('local'), 1)
  assert.equal(await kept.after('box'), 1)
  assert.equal(await kept.after('other'), undefined)
})

test('a kind switched off is not kept, but where to take up again moves past it', async () => {
  const kept = gathered(stored('n', fakeIndexedDB()))
  assert.deepEqual((await kept.preferences()).kinds, { done: true, failed: true, stopped: true, asked: true, listening: true })
  await kept.prefer({ kinds: { listening: false }, system: false })
  assert.equal(await kept.heard('local', notice(4, { slot: 'chat:1' })), null)
  assert.notEqual(await kept.heard('local', notice(5)), null)
  assert.equal(await kept.after('local'), 5)
  assert.equal((await kept.preferences()).system, false)
  assert.deepEqual((await kept.items()).map((one) => one.id), [5])
})

test('the list keeps the newest 200, marks one or all read, and clears', async () => {
  const kept = gathered(stored('n', fakeIndexedDB()))
  await Promise.all(Array.from({ length: KEPT + 5 }, (_, at) => kept.heard('local', notice(at + 1))))
  let items = await kept.items()
  assert.equal(items.length, KEPT)
  assert.equal(items[0].id, KEPT + 5)
  await kept.read([items[0].key])
  items = await kept.items()
  assert.deepEqual([items[0].read, items[1].read], [true, false])
  await kept.read(null)
  assert.ok((await kept.items()).every((one) => one.read))
  await kept.clear()
  assert.deepEqual(await kept.items(), [])
})

test('a daemon never heard of is taken up from where its first subscription stood, once', async () => {
  const kept = gathered(stored('n', fakeIndexedDB()))
  await kept.from('box', 7)
  await kept.from('box', 9)
  assert.equal(await kept.after('box'), 7)
})

test('a notice of a chat names it as chat, with no epic, and opens the chat at its own address', () => {
  const turn = notice(1, { slot: 'chat:ab', epic: '', chat: 'c1' })
  assert.equal(of(turn), 'c1')
  assert.equal(addressOf(turn), '#/chats/c1')
  // Whatever it is told of: a question, a turn done, or that it failed.
  for (const kind of ['asked', 'listening', 'done', 'failed']) assert.equal(addressOf({ ...turn, kind }), '#/chats/c1')
  assert.equal(addressOf({ ...turn, daemon: 'box' }), '#/@box/chats/c1')
  assert.doesNotMatch(addressOf(turn), /epic/)
})

test('a notice of an epic opens the epic, or, for what waits on a person, the epic going', () => {
  const ended = notice(2, { chat: '' })
  assert.equal(of(ended), 'e2')
  assert.equal(addressOf(ended), '#/epics/e2')
  assert.equal(addressOf({ ...ended, kind: 'asked' }), '#/live?workspace=%2Fw')
})

test('a notice says one line of plain words: the first of its text that says anything, without Markdown\'s marks', () => {
  assert.equal(lineOf('Here is what the **notes** come to.\n\n## Three themes\n\n1. **Starting is too many clicks.**'), 'Here is what the notes come to.')
  assert.equal(lineOf('\n\n## Which `env` first?\n- staging'), 'Which env first?')
  assert.equal(lineOf('---\n> - [The plan](https://example.com/plan) is _done_, ~~nearly~~'), 'The plan is done, nearly')
  assert.equal(lineOf('```js\nconst total = a * b * c\n```'), 'const total = a * b * c')
  assert.equal(lineOf('1. *First*, read `snake_case_name` in src/a_b.py'), 'First, read snake_case_name in src/a_b.py')
  // What is no Markdown is said as it is, and nothing is said of nothing.
  assert.equal(lineOf("HarnessUnrecoverable: Command 'claude' returned non-zero exit status 1."), "HarnessUnrecoverable: Command 'claude' returned non-zero exit status 1.")
  assert.equal(lineOf('#42 is fixed; 2 * 3 is 6'), '#42 is fixed; 2 * 3 is 6')
  assert.equal(lineOf(''), '')
  assert.equal(lineOf(undefined), '')
  assert.equal(lineOf('***\n|---|---|'), '')
})
