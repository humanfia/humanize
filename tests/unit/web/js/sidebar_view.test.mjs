import assert from 'node:assert/strict'
import { test } from 'node:test'

import { DEFAULTS, GROUP_ROWS, NO_FOLDER, WIDTHS, arranged, paged, sorted, toggled, viewOf, viewText, widthOf } from '../../../../src/hmz/web/static/sidebar-view.js'

const run = (name, workspace, began, more = {}) => ({ name, workspace, began, task: name, kind: 'chat', ...more })
const names = (groups) => groups.filter((one) => one.kind !== 'folders').map((one) => [one.kind === 'folder' && one.path ? one.path : one.label, one.runs.map((row) => row.name)])
const folders = (groups) => groups.filter((one) => one.kind === 'folders').map((one) => [one.key, one.label, one.folders])
const NOW = Date.parse('2026-10-20T12:00:00')

test('what Group and sort chose is the defaults until it says otherwise, and wherever it was kept wrong', () => {
  assert.deepEqual(viewOf(''), DEFAULTS)
  assert.deepEqual(viewOf('not json'), DEFAULTS)
  assert.deepEqual(viewOf('{"group":"shape","sort":"size","chats":0}'), DEFAULTS)
  assert.deepEqual(viewOf('{"group":"date","sort":"created","epics":false}'), { group: 'date', sort: 'created', chats: true, epics: false })
})

test('a browser keeps nothing of a view that is the defaults', () => {
  assert.equal(viewText(DEFAULTS), null)
  assert.equal(viewText({ ...DEFAULTS, group: 'none' }), JSON.stringify({ ...DEFAULTS, group: 'none' }))
  assert.deepEqual(viewOf(viewText({ ...DEFAULTS, chats: false })), { ...DEFAULTS, chats: false })
})

test('last updated puts one going first, then by when each ended, else began', () => {
  const rows = [
    run('began-late', '/a', '2026-10-12T10:00:00Z'),
    run('ended-late', '/a', '2026-10-10T10:00:00Z', { ended: '2026-10-13T10:00:00Z' }),
    run('going', '/a', '2026-10-01T10:00:00Z', { held: true }),
  ]
  assert.deepEqual(sorted(rows, DEFAULTS, NOW).map((one) => one.name), ['going', 'ended-late', 'began-late'])
  assert.deepEqual(sorted(rows, { ...DEFAULTS, sort: 'created' }, NOW).map((one) => one.name), ['began-late', 'ended-late', 'going'])
})

test('Show leaves out the chats or the epics, as it says', () => {
  const rows = [run('chat', '/a', '2026-10-12T10:00:00Z'), run('epic', '/a', '2026-10-11T10:00:00Z', { kind: 'flow' })]
  assert.deepEqual(sorted(rows, { ...DEFAULTS, chats: false }, NOW).map((one) => one.name), ['epic'])
  assert.deepEqual(sorted(rows, { ...DEFAULTS, epics: false }, NOW).map((one) => one.name), ['chat'])
  assert.deepEqual(sorted(rows, { ...DEFAULTS, chats: false, epics: false }, NOW), [])
  // Which rows are chats is the caller's to say, where a row says no kind.
  assert.deepEqual(sorted(rows, { ...DEFAULTS, chats: false }, NOW, () => true), [])
})

test('by folder, every workspace is listed, even one nothing ran in, by its latest', () => {
  const groups = arranged({ workspaces: [{ path: '/empty' }, { path: '/a' }], runs: [run('new', '/a', '2026-10-12T10:00:00Z'), run('old', '/a', '2026-10-12T09:00:00Z')], view: DEFAULTS, now: NOW })
  assert.deepEqual(names(groups), [['/a', ['new', 'old']], ['/empty', []]])
  assert.deepEqual(groups.map((one) => one.key), ['/a', '/empty'])
})

test('a workspace no list of workspaces names is still offered, by what ran in it', () => {
  assert.deepEqual(names(arranged({ workspaces: null, runs: [run('one', '/b', '2026-10-12T10:00:00Z')], view: DEFAULTS, now: NOW })), [['/b', ['one']]])
})

test('a workspace with one a host goes with stands before a later one that rests', () => {
  const runs = [run('late', '/late', '2026-10-13T10:00:00Z'), run('held', '/held', '2026-10-12T10:00:00Z', { held: true }), run('early', '/early', '2026-10-11T10:00:00Z')]
  assert.deepEqual(arranged({ runs, view: DEFAULTS, now: NOW }).map((one) => one.path), ['/held', '/late', '/early'])
})

test('the rows pinned stand first, under Pinned, and in no other group', () => {
  const runs = [run('a', '/w', '2026-10-13T10:00:00Z'), run('b', '/w', '2026-10-12T10:00:00Z'), run('c', '/v', '2026-10-11T10:00:00Z')]
  const groups = arranged({ runs, view: DEFAULTS, pinned: new Set(['b', 'c', 'gone']), now: NOW })
  assert.deepEqual(names(groups), [['Pinned', ['b', 'c']], ['/w', ['a']]])
  assert.equal(groups[0].key, ':pinned')
  // Show holds for the pinned as for any row.
  assert.deepEqual(names(arranged({ runs, view: { ...DEFAULTS, chats: false }, pinned: new Set(['b']), workspaces: [{ path: '/w' }], now: NOW })), [['/w', []]])
})

test('by folder, a list with no folder and nothing to show keeps a heading, where Group and sort is', () => {
  // A daemon with no workspace, its one chat of no folder, and Show without the chats.
  const hidden = arranged({ workspaces: [], runs: [run('lone', '', '2026-10-13T10:00:00Z')], view: { ...DEFAULTS, chats: false }, now: NOW })
  assert.deepEqual(hidden.map((one) => [one.kind, one.key, one.label, one.path, one.runs]), [['folder', ':nowhere', NO_FOLDER, '', []]])
  assert.deepEqual(names(arranged({ view: DEFAULTS, now: NOW })), [[NO_FOLDER, []]])
  // Shown again, the chat stands under the same heading; with a folder listed, that folder's is the heading.
  assert.deepEqual(names(arranged({ runs: [run('lone', '', '2026-10-13T10:00:00Z')], view: DEFAULTS, now: NOW })), [[NO_FOLDER, ['lone']]])
  assert.deepEqual(names(arranged({ workspaces: [{ path: '/w' }], view: DEFAULTS, now: NOW })), [['/w', []]])
})

test('by date, the rows stand under how long ago each was last updated, the empty days left out', () => {
  const runs = [
    run('now', '/w', '2026-10-01T10:00:00', { held: true }),
    run('today', '/w', '2026-10-20T01:00:00'),
    run('yesterday', '/v', '2026-10-19T23:00:00'),
    run('week', '/w', '2026-10-14T10:00:00'),
    run('old', '/w', '2026-01-01T10:00:00'),
  ]
  const groups = arranged({ workspaces: [{ path: '/empty' }], runs, view: { ...DEFAULTS, group: 'date' }, now: NOW })
  assert.deepEqual(names(groups), [['Today', ['now', 'today']], ['Yesterday', ['yesterday']], ['Last 7 days', ['week']], ['Older', ['old']]])
  // By when each began, one going long since is no longer of today.
  const created = arranged({ runs, view: { group: 'date', sort: 'created', chats: true, epics: true }, now: NOW })
  assert.deepEqual(names(created), [['Today', ['today']], ['Yesterday', ['yesterday']], ['Last 7 days', ['week']], ['Last 30 days', ['now']], ['Older', ['old']]])
})

test('by date, a list with nothing to show keeps Today, so that a heading is always there', () => {
  const view = { ...DEFAULTS, group: 'date' }
  assert.deepEqual(names(arranged({ runs: [], view, now: NOW })), [['Today', []]])
  const runs = [run('a', '/w', '2026-10-13T10:00:00Z')]
  assert.deepEqual(names(arranged({ runs, view: { ...view, chats: false }, now: NOW })), [['Today', []]])
  // The rows pinned are a heading already.
  assert.deepEqual(names(arranged({ runs, view, pinned: new Set(['a']), now: NOW })), [['Pinned', ['a']]])
})

test('grouped by anything but folder, the folders stand last as a group of their own', () => {
  const runs = [run('a', '/w', '2026-10-13T10:00:00Z'), run('b', '/w', '2026-10-12T10:00:00Z'), run('nowhere', '', '2026-10-11T10:00:00Z')]
  const of = { workspaces: [{ path: '/empty' }], runs, now: NOW }
  const said = [[':folders', 'Folders', [{ path: '/w', count: 2 }, { path: '/empty', count: 0 }]]]
  for (const group of ['date', 'none']) {
    const groups = arranged({ ...of, view: { ...DEFAULTS, group } })
    assert.deepEqual(folders(groups), said)
    assert.equal(groups.at(-1).kind, 'folders')
  }
  assert.deepEqual(folders(arranged({ ...of, view: DEFAULTS })), [])
  // No folder, no such group.
  assert.deepEqual(folders(arranged({ runs: [], view: { ...DEFAULTS, group: 'none' }, now: NOW })), [])
})

test('by folder, the rows of no folder stand last, under No folder', () => {
  const runs = [run('nowhere', '', '2026-10-13T10:00:00Z', { held: true }), run('a', '/w', '2026-10-12T10:00:00Z'), run('lost', undefined, '2026-10-11T10:00:00Z')]
  const groups = arranged({ workspaces: [{ path: '/empty' }], runs, view: DEFAULTS, now: NOW })
  assert.deepEqual(names(groups), [['/w', ['a']], ['/empty', []], [NO_FOLDER, ['nowhere', 'lost']]])
  assert.deepEqual(groups.at(-1).path, '')
  assert.ok(groups.at(-1).key)
})

test('grouped by nothing, the rows are one group, even an empty one', () => {
  const runs = [run('a', '/w', '2026-10-13T10:00:00Z'), run('b', '/v', '2026-10-12T10:00:00Z')]
  assert.deepEqual(names(arranged({ runs, view: { ...DEFAULTS, group: 'none' }, now: NOW })), [['All', ['a', 'b']]])
  assert.deepEqual(names(arranged({ runs: [], view: { ...DEFAULTS, group: 'none' }, now: NOW })), [['All', []]])
})

test('a group shows its first rows and says how many Show N more would bring', () => {
  const runs = Array.from({ length: GROUP_ROWS + 3 }, (_, at) => run(`r${at}`, '/w', ''))
  const first = paged(runs)
  assert.equal(first.rows.length, GROUP_ROWS)
  assert.equal(first.more, 3)
  assert.deepEqual(paged(runs, runs.length), { rows: runs, more: 0 })
  assert.deepEqual(paged(runs.slice(0, 2)), { rows: runs.slice(0, 2), more: 0 })
})

test('the row the page is on is shown wherever in its group it stands', () => {
  const runs = Array.from({ length: 5 }, (_, at) => run(`r${at}`, '/w', ''))
  const { rows, more } = paged(runs, 2, 'r4')
  assert.deepEqual(rows.map((one) => one.name), ['r0', 'r1', 'r4'])
  assert.equal(more, 2)
})

test('a name is put among those kept, newest last, or taken out, and no more than so many stay', () => {
  assert.deepEqual(toggled(['a', 'b'], 'c', true), ['a', 'b', 'c'])
  assert.deepEqual(toggled(['a', 'b'], 'a', true), ['b', 'a'])
  assert.deepEqual(toggled(['a', 'b'], 'a', false), ['b'])
  assert.deepEqual(toggled(null, 'a', false), [])
  assert.deepEqual(toggled(['a', 'b', 'c'], 'd', true, 2), ['c', 'd'])
})

test('the sidebar is as wide as it was dragged, within its bounds, and the usual where nothing says', () => {
  assert.equal(widthOf(''), WIDTHS.usual)
  assert.equal(widthOf('wide'), WIDTHS.usual)
  assert.equal(widthOf(null), WIDTHS.usual)
  assert.equal(widthOf('300.4'), 300)
  assert.equal(widthOf(10), WIDTHS.least)
  assert.equal(widthOf(4000), WIDTHS.most)
  assert.equal(WIDTHS.usual, 275)
})
