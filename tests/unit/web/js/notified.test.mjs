import assert from 'node:assert/strict'
import { test } from 'node:test'

import { addressOf, followed, fresh, kindOf, lineOf, of, onScreen, shownAs, STALE } from '../../../../src/hmz/web/static/notified.js'
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

test('a notice heard names its daemon and moves where its daemon is taken up', async () => {
  const kept = followed(stored('n', fakeIndexedDB()))
  const local = await kept.heard('local', notice(1))
  const box = await kept.heard('box', notice(2))
  assert.deepEqual([local.daemon, local.key, local.epic], ['local', 'local:1', 'e1'])
  assert.deepEqual([box.daemon, box.key], ['box', 'box:2'])
  assert.equal(await kept.after('local'), 1)
  assert.equal(await kept.after('box'), 2)
  assert.equal(await kept.after('other'), undefined)
  // No list of them is kept.
  assert.equal(kept.items, undefined)
})

test('a kind switched off is not told, but where to take up again moves past it', async () => {
  const kept = followed(stored('n', fakeIndexedDB()))
  assert.deepEqual((await kept.preferences()).kinds, { done: true, failed: true, stopped: true, asked: true, listening: true })
  await kept.prefer({ kinds: { listening: false }, system: false })
  assert.equal(await kept.heard('local', notice(4, { slot: 'chat:1' })), null)
  assert.equal(await kept.after('local'), 4)
  assert.notEqual(await kept.heard('local', notice(5)), null)
  assert.equal(await kept.after('local'), 5)
  assert.equal((await kept.preferences()).system, false)
})

test('the system shows a notice by its kind and daemon, over its flow and what it says', () => {
  assert.deepEqual(shownAs({ ...notice(5, { flow: 'ralph', text: '## All green' }), daemon: 'local', key: 'local:5' }), { title: 'Done · Local', body: 'ralph · All green', address: '#/epics/e5', tag: 'local:5' })
  const asked = shownAs({ ...notice(6, { kind: 'asked', slot: 's', flow: 'goal', text: 'Which one?' }), daemon: 'box', key: 'box:6' })
  assert.deepEqual([asked.title, asked.body, asked.address], ['Question · box', 'goal · Which one?', '#/@box/live?workspace=%2Fw&slot=s'])
  const turn = shownAs({ ...notice(7, { slot: 'chat:ab', epic: '', chat: 'ab', flow: '', text: '' , task: 'Cut the tiles\nand more' }), daemon: 'local', key: 'local:7' })
  assert.deepEqual([turn.title, turn.body, turn.address], ['Waiting · Local', 'Cut the tiles', '#/chats/ab'])
  // A chat's flow is told as `chat`: what says which chat is its task, before what was answered.
  const answered = shownAs({ ...notice(7, { slot: 'chat:ab', epic: '', chat: 'ab', flow: 'chat', text: 'did: the tiles', task: 'Cut the tiles\nand more' }), daemon: 'local', key: 'local:7' })
  assert.equal(answered.body, 'Cut the tiles · did: the tiles')
  // With neither text nor task, by its name.
  assert.equal(shownAs({ ...notice(8, { flow: '', task: '' }), daemon: 'local', key: 'local:8' }).body, 'e8')
})

test('a notice is on screen only of the chat or epic the page is on, of its daemon, while looked at', () => {
  const at = (hash, said = {}) => {
    const url = new URL(hash, 'http://page')
    return { looked: true, daemon: 'local', parts: url.pathname.split('/').filter(Boolean), query: url.searchParams, ...said }
  }
  const epic = { ...notice(7), daemon: 'local' }
  const chat = { ...notice(8, { epic: '', chat: 'ab', slot: 'chat:ab' }), daemon: 'local' }
  const asked = { ...notice(9, { kind: 'asked', slot: 's' }), daemon: 'local' }
  assert.equal(onScreen(epic, at('/epics/e7')), true)
  assert.equal(onScreen(epic, at('/epics/e7', { looked: false })), false)
  assert.equal(onScreen(epic, at('/epics/e7', { daemon: 'box' })), false)
  assert.equal(onScreen(epic, at('/epics/e8')), false)
  assert.equal(onScreen(epic, at('/chats/e7')), false)
  assert.equal(onScreen(chat, at('/chats/ab')), true)
  assert.equal(onScreen(chat, at('/chats/cd')), false)
  assert.equal(onScreen(asked, at('/live?workspace=%2Fw&slot=s')), true)
  assert.equal(onScreen(asked, at('/live?workspace=%2Fw&slot=other')), false)
  assert.equal(onScreen(asked, at('/settings/notifications')), false)
})

test('a notice made long before it is heard is not for the system to show', () => {
  const now = 10000
  assert.equal(fresh({ at: now }, now), true)
  assert.equal(fresh({ at: now - STALE + 1 }, now), true)
  assert.equal(fresh({ at: now - STALE - 1 }, now), false)
  // One that does not say when it was made is taken as made now.
  assert.equal(fresh({}, now), true)
})

test('a daemon never heard of is taken up from where its first subscription stood, once', async () => {
  const kept = followed(stored('n', fakeIndexedDB()))
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
