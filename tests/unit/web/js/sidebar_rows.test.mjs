import assert from 'node:assert/strict'
import { test } from 'node:test'

import { CHAT_SAID, chatState, grouped, rowTitle, wording } from '../../../../src/hmz/web/static/sidebar-rows.js'

const run = (name, workspace, began, more = {}) => ({ name, workspace, began, task: name, ...more })

test('every workspace is listed, with its rows as they came, even one nothing ran in', () => {
  const groups = grouped([{ path: '/empty' }, { path: '/a' }], [run('new', '/a', '2026-10-12T10:00:00Z'), run('old', '/a', '2026-10-12T09:00:00Z')])
  assert.deepEqual(groups.map((one) => [one.path, one.runs.map((row) => row.name)]), [['/a', ['new', 'old']], ['/empty', []]])
})

test('a workspace no list of workspaces names is still offered, by what ran in it', () => {
  assert.deepEqual(grouped(null, [run('one', '/b', '2026-10-12T10:00:00Z')]).map((one) => one.path), ['/b'])
})

test('a workspace with one a host goes with stands before a later one that rests', () => {
  const groups = grouped([], [run('late', '/late', '2026-10-13T10:00:00Z'), run('held', '/held', '2026-10-12T10:00:00Z', { held: true }), run('early', '/early', '2026-10-11T10:00:00Z')])
  assert.deepEqual(groups.map((one) => one.path), ['/held', '/late', '/early'])
})

test('a chat goes, asks, failed, or says nothing', () => {
  assert.equal(chatState('running'), 'working')
  assert.equal(chatState('asking'), 'asking')
  for (const how of ['failed', 'refused', 'crashed']) assert.equal(chatState(how), 'failed')
  for (const how of ['stopped', 'stopping', 'done', '']) assert.equal(chatState(how), '')
  for (const state of ['working', 'asking', 'failed']) assert.ok(CHAT_SAID[state])
})

test('a chat pointed at never says epic or flow, and a flow epic names its flow', () => {
  const chat = rowTitle({ task: 'hello\nthere' }, { chat: true, state: chatState('running'), flow: 'chat', began: 'today' })
  assert.equal(chat, 'hello\nthere\nWorking · today')
  assert.equal(rowTitle({ task: 'hi' }, { chat: true, state: chatState('stopped'), flow: 'chat', began: 'today' }), 'hi\ntoday')
  assert.equal(rowTitle({ task: 'fix' }, { chat: false, how: 'done', flow: 'ralph', began: 'today' }), 'fix\nralph · done · today')
})

test('a chat menu is worded for a chat, an epic menu for an epic, each a short phrase', () => {
  for (const said of Object.values(wording(true))) assert.doesNotMatch(said, /epic|flow|task/i)
  assert.equal(wording(false).like, 'New epic like it')
  for (const chat of [true, false]) for (const said of Object.values(wording(chat))) assert.ok(said.split(' ').length <= 4 && !/[.?!]$/.test(said))
})
