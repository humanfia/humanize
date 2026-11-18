import assert from 'node:assert/strict'
import { test } from 'node:test'

import { CHAT_SAID, chatState, epicSaid, rowSaid, rowTitle, wording } from '../../../../src/hmz/web/static/sidebar-rows.js'

test('a chat goes, asks, failed, or says nothing', () => {
  assert.equal(chatState('running'), 'working')
  assert.equal(chatState('asking'), 'asking')
  for (const how of ['failed', 'refused', 'crashed']) assert.equal(chatState(how), 'failed')
  for (const how of ['stopped', 'stopping', 'done', '']) assert.equal(chatState(how), '')
  assert.deepEqual(CHAT_SAID, { working: 'Running', asking: 'Awaiting input', failed: 'Failed' })
})

test('a flow epic says how it stands in a word of its own', () => {
  assert.equal(epicSaid('running'), 'Running')
  assert.equal(epicSaid('unfinished'), 'Unfinished')
  assert.equal(epicSaid('budget'), 'Budget spent')
  assert.equal(epicSaid(''), '')
})

test('a chat pointed at never says epic or flow, and a flow epic names its flow', () => {
  const chat = rowTitle({ task: 'hello\nthere' }, { chat: true, state: chatState('running'), flow: 'chat', began: 'today' })
  assert.equal(chat, 'hello\nthere\nRunning · today')
  assert.equal(rowTitle({ task: 'hi' }, { chat: true, state: chatState('stopped'), flow: 'chat', began: 'today' }), 'hi\ntoday')
  assert.equal(rowTitle({ task: 'fix' }, { chat: false, how: 'done', flow: 'ralph', began: 'today' }), 'fix\nralph · done · today')
})

test('a chat menu is worded for a chat, an epic menu for an epic, each a short phrase', () => {
  for (const said of Object.values(wording(true))) assert.doesNotMatch(said, /epic|flow|task/i)
  assert.equal(wording(false).like, 'New epic like it')
  for (const chat of [true, false]) for (const said of Object.values(wording(chat))) assert.ok(said.split(' ').length <= 4 && !/[.?!]$/.test(said))
})

test('a row stands in the same words in every list: a chat only where there is something to say', () => {
  assert.equal(rowSaid('running', true), 'Running')
  assert.equal(rowSaid('asking', true), 'Awaiting input')
  assert.equal(rowSaid('crashed', true), 'Failed')
  // A chat that rests says nothing, however its epic ended.
  assert.equal(rowSaid('stopped', true), '')
  assert.equal(rowSaid('done', true), '')
  // A flow's epic says its mark, as a word.
  assert.equal(rowSaid('done', false), 'Done')
  assert.equal(rowSaid('budget', false), 'Budget spent')
  assert.equal(rowSaid('waiting', false), 'Waiting')
})
