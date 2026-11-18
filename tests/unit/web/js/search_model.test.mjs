import assert from 'node:assert/strict'
import { test } from 'node:test'

import { HINTS, PAGE, TABS, asked, chosenOf, filtered, heading, moved, narrowed, onFlow, onTab, paged, turned } from '../../../../src/hmz/web/static/search-model.js'

const chosen = (text = '') => chosenOf(new URLSearchParams(text))

test('the tabs are everything, the chats and the epics, and a chat is never an epic', () => {
  assert.deepEqual(TABS, [['', 'All'], ['chat', 'Chats'], ['flow', 'Epics']])
})

test('every label of the tabs and the foot is a few words and no sentence', () => {
  for (const said of [...TABS.map(([, name]) => name), ...HINTS.map(([does]) => does)]) {
    assert.ok(said.split(' ').length <= 4, said)
    assert.doesNotMatch(said, /[.?!]$/)
  }
})

test('the foot says how to move, to open and to close', () => {
  const keys = Object.fromEntries(HINTS)
  assert.deepEqual(keys.Move, ['↑', '↓'])
  assert.deepEqual(keys.Open, ['Enter'])
  assert.deepEqual(keys.Close, ['Esc'])
})

test('an address with nothing in it asks for everything from the first', () => {
  assert.deepEqual(chosen(), { kind: '', status: '', flow: '', workspace: '', q: '', offset: 0 })
  assert.deepEqual(asked(chosen()), { kind: '', status: '', flow: '', workspace: '', q: '', offset: 0, limit: PAGE })
})

test('an address says its tab, and one that is no tab is everything', () => {
  assert.equal(chosen('kind=chat').kind, 'chat')
  assert.equal(chosen('kind=flow').kind, 'flow')
  assert.equal(chosen('kind=session').kind, '')
})

test('an address of before the tabs, with chats as a flow, is the tab of the chats', () => {
  const old = chosen('flow=chat&q=hello')
  assert.deepEqual([old.kind, old.flow, old.q], ['chat', '', 'hello'])
  assert.equal(asked(old).flow, '')
})

test('an offset that is no number, or under nothing, is the first page', () => {
  assert.equal(chosen('offset=abc').offset, 0)
  assert.equal(chosen('offset=-50').offset, 0)
  assert.equal(chosen('offset=100').offset, 100)
})

test('the tab of the chats drops the flow, and a flow chosen there goes to the epics', () => {
  const epics = onFlow(chosen('kind=chat&offset=50'), 'ralph')
  assert.deepEqual([epics.kind, epics.flow, epics.offset], ['flow', 'ralph', 0])
  const chats = onTab(epics, 'chat')
  assert.deepEqual([chats.kind, chats.flow], ['chat', ''])
  // On everything a flow chosen stays on everything, and no flow chosen leaves the chats.
  assert.equal(onFlow(chosen(), 'ralph').kind, '')
  assert.equal(onFlow(chosen('kind=chat'), '').kind, 'chat')
  assert.equal(onTab(chosen('flow=ralph'), 'flow').flow, 'ralph')
})

test('left and right go a tab over and stop at either end', () => {
  assert.equal(turned('', 1), 'chat')
  assert.equal(turned('chat', 1), 'flow')
  assert.equal(turned('flow', 1), 'flow')
  assert.equal(turned('flow', -1), 'chat')
  assert.equal(turned('', -1), '')
})

test('the arrows go round what was found, and Home and End to its ends', () => {
  assert.equal(moved(-1, 3, 'ArrowDown'), 0)
  assert.equal(moved(0, 3, 'ArrowDown'), 1)
  assert.equal(moved(2, 3, 'ArrowDown'), 0)
  assert.equal(moved(0, 3, 'ArrowUp'), 2)
  assert.equal(moved(-1, 3, 'ArrowUp'), 2)
  assert.equal(moved(1, 3, 'Home'), 0)
  assert.equal(moved(1, 3, 'End'), 2)
  assert.equal(moved(1, 3, 'a'), 1)
  assert.equal(moved(5, 3, 'a'), 2)
  assert.equal(moved(0, 0, 'ArrowDown'), -1)
})

test('the filters show open only where one is set, and a tab or words narrow as they do', () => {
  assert.equal(filtered(chosen()), false)
  assert.equal(filtered(chosen('q=hello&kind=chat')), false)
  for (const one of ['status=done', 'flow=ralph', 'workspace=/w']) assert.equal(filtered(chosen(one)), true)
  assert.equal(narrowed(chosen()), false)
  for (const one of ['q=hello', 'kind=chat', 'status=done']) assert.equal(narrowed(chosen(one)), true)
})

test('what is listed is headed as the newest, or as what was found', () => {
  assert.equal(heading(chosen()), 'Recents')
  assert.equal(heading(chosen('q=hello')), 'Results')
})

test('the foot says which rows of how many, and nothing of none', () => {
  assert.equal(paged({ offset: 50, total: 120, runs: new Array(50) }), '51–100 of 120')
  assert.equal(paged({ offset: 0, total: 0, runs: [] }), '')
})
