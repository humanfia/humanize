import assert from 'node:assert/strict'
import { test } from 'node:test'

import { PAGE, TABS, asked, chosenOf, filtered, found, heading, hints, keyed, moved, narrowed, nothing, onFlow, onTab, paged, turned } from '../../../../src/hmz/web/static/search-model.js'

const chosen = (text = '') => chosenOf(new URLSearchParams(text))

test('the tabs are everything, the chats and the epics, and a chat is never an epic', () => {
  assert.deepEqual(TABS, [['', 'All'], ['chat', 'Chats'], ['flow', 'Epics']])
})

test('every label of the tabs and the foot is a few words and no sentence', () => {
  for (const said of [...TABS.map(([, name]) => name), ...hints(true).map(([does]) => does), ...[chosen(), chosen('q=a'), chosen('kind=chat'), chosen('kind=flow')].map((one) => nothing(one)[0].replace(/\.$/, ''))]) {
    assert.ok(said.split(' ').length <= 4, said)
    assert.doesNotMatch(said, /[.?!]$/)
  }
})

test('the foot says how to move, to open and to close, and what opens what can be done', () => {
  assert.deepEqual(hints(false).map(([does]) => does), ['Close', 'Change type', 'Filters', 'Actions', 'Move', 'Open'])
  const keys = Object.fromEntries(hints(false))
  assert.deepEqual(keys.Move, ['↑', '↓'])
  assert.deepEqual(keys.Open, ['Enter'])
  assert.deepEqual(keys.Close, ['Esc'])
  assert.deepEqual(keys.Actions, ['Alt', 'Enter'])
  assert.deepEqual(Object.fromEntries(hints(true)).Actions, ['Option', 'Enter'])
})

test('the arrows move wherever they are pressed but in a select, and Enter opens from the field and the tabs', () => {
  const press = (key, where, empty = false, held = {}) => keyed({ key, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, ...held }, where, empty)
  for (const where of ['field', 'tabs', 'else']) {
    assert.equal(press('ArrowDown', where), 'down')
    assert.equal(press('ArrowUp', where), 'up')
  }
  assert.equal(press('ArrowDown', 'select'), '')
  assert.equal(press('Enter', 'field'), 'open')
  assert.equal(press('Enter', 'tabs'), 'open')
  // A button pressed by Enter is pressed, and a select keeps every key.
  assert.equal(press('Enter', 'else'), '')
  assert.equal(press('Enter', 'select'), '')
  // The field keeps the keys it types and moves its caret with, but while it is empty.
  for (const [key, does] of [['ArrowLeft', 'left'], ['ArrowRight', 'right'], ['/', 'filters']]) {
    assert.equal(press(key, 'field', true), does)
    assert.equal(press(key, 'field', false), '')
    assert.equal(press(key, 'tabs'), does)
    assert.equal(press(key, 'else'), '')
  }
  assert.equal(press('a', 'field', true), '')
  // A key held with another is the browser's, or the field's own selecting.
  assert.equal(press('ArrowDown', 'field', false, { shiftKey: true }), '')
  assert.equal(press('ArrowDown', 'field', false, { metaKey: true }), '')
  assert.equal(press('Enter', 'field', false, { ctrlKey: true }), '')
})

test('Alt and Enter, or the menu key, open what can be done with the one moved to', () => {
  const press = (key, held = {}, where = 'field') => keyed({ key, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, ...held }, where)
  assert.equal(press('Enter', { altKey: true }), 'act')
  assert.equal(press('Enter', { altKey: true }, 'else'), 'act')
  assert.equal(press('ContextMenu'), 'act')
  assert.equal(press('F10', { shiftKey: true }), 'act')
  assert.equal(press('F10'), '')
  assert.equal(press('ArrowDown', { altKey: true }), '')
  assert.equal(press('Enter', { altKey: true }, 'select'), '')
})

test('nothing found is nothing like that only where something typed or filtered can be cleared', () => {
  assert.equal(nothing(chosen())[0], 'Nothing here yet.')
  assert.equal(nothing(chosen('kind=chat'))[0], 'No chats yet.')
  assert.equal(nothing(chosen('kind=flow'))[0], 'No epics yet.')
  for (const one of ['q=hello', 'kind=flow&status=done', 'flow=ralph', 'workspace=/w']) {
    assert.equal(nothing(chosen(one))[0], 'Nothing is like that.')
    assert.match(nothing(chosen(one))[1], /Clear the filters/)
  }
  assert.doesNotMatch(nothing(chosen('kind=chat'))[1], /filters/)
})

test('an address with nothing in it asks for everything from the first', () => {
  assert.deepEqual(chosen(), { kind: '', status: '', flow: '', workspace: '', q: '', offset: 0 })
  // Everything is the chats and the epics, each asked for from its first.
  assert.deepEqual(asked(chosen()), [
    ['chat.list', { workspace: '', q: '', offset: 0, limit: PAGE }],
    ['runs.list', { status: '', flow: '', workspace: '', q: '', offset: 0, limit: PAGE }],
  ])
})

test('the chats are asked of chat.list and the epics of runs.list, which is asked for no kind', () => {
  assert.deepEqual(asked(chosen('kind=chat&q=hello&workspace=/w&offset=50')), [['chat.list', { workspace: '/w', q: 'hello', offset: 50, limit: PAGE }]])
  assert.deepEqual(asked(chosen('kind=flow&status=done&flow=ralph&offset=50')), [['runs.list', { status: 'done', flow: 'ralph', workspace: '', q: '', offset: 50, limit: PAGE }]])
  for (const [, params] of [...asked(chosen()), ...asked(chosen('kind=chat')), ...asked(chosen('kind=flow'))]) assert.equal('kind' in params, false)
})

test('on everything, a later page asks each list as far as it, and a flow or an ending asks for epics alone', () => {
  assert.deepEqual(asked(chosen('offset=100')).map(([method, params]) => [method, params.offset, params.limit]), [['chat.list', 0, 150], ['runs.list', 0, 150]])
  assert.deepEqual(asked(chosen('offset=400')).map(([, params]) => params.limit), [200, 200])
  assert.deepEqual(asked(chosen('status=done')).map(([method]) => method), ['runs.list'])
  assert.deepEqual(asked(chosen('flow=ralph')).map(([method]) => method), ['runs.list'])
})

test('a chat is not found by how it went: the tab of the chats drops it', () => {
  assert.equal(chosen('kind=chat&status=done').status, '')
  assert.equal(onTab(chosen('status=done'), 'chat').status, '')
  assert.equal(onTab(chosen('status=done'), 'flow').status, 'done')
})

test('what was found is one list, the chats and the epics newest first, a chat at its own address', () => {
  const chats = { chats: [{ id: 'c1', title: 'A chat', workspace: '/w', agent: 'claude/opus', began: '2026-01-03T00:00:00Z', updated: '2026-01-03T00:00:00Z', state: 'resting', slot: '', asking: [] }], total: 1 }
  const epics = { runs: [{ name: 'e2', kind: 'flow', flow: 'ralph', task: 'An epic', began: '2026-01-04T00:00:00Z' }, { name: 'e1', kind: 'flow', flow: 'chat', task: 'An epic of a flow named chat', began: '2026-01-02T00:00:00Z' }], total: 2, counts: { done: 2 }, flows: ['chat', 'ralph'] }
  const all = found(chosen(), [chats, epics])
  assert.deepEqual(all.runs.map((run) => [run.name, run.kind, run.flow]), [['e2', 'flow', 'ralph'], ['c1', 'chat', ''], ['e1', 'flow', 'chat']])
  assert.deepEqual([all.total, all.offset, all.counts, all.flows], [3, 0, { done: 2 }, ['chat', 'ralph']])
  // The chats alone: of no flow, and with nothing counted by how it went.
  const only = found(chosen('kind=chat'), [chats])
  assert.deepEqual([only.runs.map((run) => run.name), only.total, only.counts, only.flows], [['c1'], 1, {}, []])
  // A later page of everything is cut out of the two lists as one.
  const many = (count, at) => Array.from({ length: count }, (_, index) => ({ name: `e${index}`, kind: 'flow', began: new Date(at - index * 1000).toISOString() }))
  const later = found(chosen(`offset=${PAGE}`), [{ chats: [], total: 0 }, { runs: many(PAGE + 5, 1e12), total: PAGE + 5, counts: {}, flows: [] }])
  assert.deepEqual([later.runs.length, later.runs[0].name, later.offset], [5, `e${PAGE}`, PAGE])
})

test('an address says its tab, and one that is no tab is everything', () => {
  assert.equal(chosen('kind=chat').kind, 'chat')
  assert.equal(chosen('kind=flow').kind, 'flow')
  assert.equal(chosen('kind=session').kind, '')
})

test('an address of before the tabs, with chats as a flow, is the tab of the chats', () => {
  const old = chosen('flow=chat&q=hello')
  assert.deepEqual([old.kind, old.flow, old.q], ['chat', '', 'hello'])
  assert.deepEqual(asked(old), [['chat.list', { workspace: '', q: 'hello', offset: 0, limit: PAGE }]])
})

test('an address that names a flow is on everything, and with the chats the flow is dropped', () => {
  assert.deepEqual([chosen('flow=ralph').kind, chosen('flow=ralph').flow], ['', 'ralph'])
  assert.deepEqual([chosen('kind=flow&flow=ralph').kind, chosen('kind=flow&flow=ralph').flow], ['flow', 'ralph'])
  const chats = chosen('kind=chat&flow=ralph')
  assert.deepEqual([chats.kind, chats.flow], ['chat', ''])
  assert.equal(filtered(chats), false)
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
