import assert from 'node:assert/strict'
import { test } from 'node:test'

import { chatDetail, chatRow, harnessRow, pathOf } from '../../../../src/hmz/web/static/chats.js'
import { GROUP_ROWS, paged, sorted } from '../../../../src/hmz/web/static/sidebar-view.js'

/** A chat as `chat.list` rows one. */
const chat = (fields = {}) => ({ id: '20260101-000000-abcdef', title: 'Fix the build', workspace: '/w', workdir: '/w', agent: 'claude/opus:high', model: 'opus', began: '2026-01-01T00:00:00Z', updated: '2026-01-02T00:00:00Z', state: 'resting', slot: '', asking: [], permission: 'workspace-write', archived: false, spent: null, ...fields })

test('a chat listed is a row named by its id and told by its title, of the kind chat and of no flow', () => {
  const row = chatRow(chat())
  assert.deepEqual([row.name, row.task, row.kind, row.flow], ['20260101-000000-abcdef', 'Fix the build', 'chat', ''])
  assert.deepEqual(row.agents, [{ name: 'assistant', role: 'assistant', runs: 'claude/opus:high' }])
  assert.equal(pathOf(row), '/chats/20260101-000000-abcdef')
})

test('a chat is never going or at rest: only failed where it failed, with a turn open where its host says so', () => {
  const stands = (fields) => {
    const { how, turn, held, ended } = chatRow(chat(fields))
    return [how, turn, held, ended]
  }
  assert.deepEqual(stands({ state: 'resting' }), ['stopped', '', false, '2026-01-02T00:00:00Z'])
  assert.deepEqual(stands({ state: 'failed' }), ['failed', '', false, '2026-01-02T00:00:00Z'])
  // A host that holds it is where it is asked, not how it stands.
  assert.deepEqual(stands({ state: 'going', slot: 'chat:ab' }), ['stopped', 'done', true, '2026-01-02T00:00:00Z'])
  assert.deepEqual(stands({ state: 'turn', slot: 'chat:ab' }), ['stopped', 'running', true, '2026-01-02T00:00:00Z'])
  assert.deepEqual(stands({ state: 'asking', slot: 'chat:ab', asking: ['1:q1'] }), ['stopped', 'running', true, '2026-01-02T00:00:00Z'])
  // Held by another process than a host: its turn unknown.
  assert.deepEqual(stands({ state: 'going' }), ['stopped', '', false, '2026-01-02T00:00:00Z'])
})

test('what a chat going waits on is what its host says, its reply between turns among it', () => {
  const going = chat({ state: 'going', slot: 'chat:ab' })
  assert.deepEqual(chatRow(going).asking, [])
  assert.deepEqual(chatRow(going, [{ chat: going.id, asking: ['1:q2'] }, { chat: 'another', asking: ['1:q9'] }]).asking, ['1:q2'])
  // One no host holds waits on what its row says: nothing.
  assert.deepEqual(chatRow(chat(), [{ chat: chat().id, asking: ['1:q2'] }]).asking, [])
})

test('a chat is sorted by when it was last heard of, whether or not a host holds it', () => {
  const rows = [chatRow(chat({ id: 'old', updated: '2026-01-02T00:00:00Z' })), chatRow(chat({ id: 'new', updated: '2026-01-05T00:00:00Z' })), chatRow(chat({ id: 'held', state: 'going', slot: 'chat:ab', updated: '2026-01-03T00:00:00Z' }))]
  assert.deepEqual(sorted(rows, { sort: 'updated', chats: true, epics: true }).map((row) => row.name), ['new', 'held', 'old'])
  assert.deepEqual(sorted(rows, { sort: 'updated', chats: false, epics: true }), [])
})

test('a chat read whole is told by its first message, keeps its title, and is always one to say something in', () => {
  const whole = { at: '/home/chats/w/c1', task: 'Fix the build\nand the tests', prefer: 'flow', forked: '', agents: [{ name: 'assistant', role: 'assistant', runs: 'claude/opus:high' }], sessions: [{ agent: 'assistant', backend: 'claude', ident: 's1' }], earlier: 1, backup: [], backed: {} }
  const detail = chatDetail({ ...chat({ title: 'Renamed' }), ...whole })
  assert.deepEqual([detail.name, detail.kind, detail.title, detail.task, detail.earlier, detail.prefer, detail.permission], ['20260101-000000-abcdef', 'chat', 'Renamed', 'Fix the build\nand the tests', 1, 'flow', 'workspace-write'])
  assert.equal(detail.picks_up, true)
  assert.equal(chatDetail({ ...chat({ state: 'failed' }), ...whole }).picks_up, true)
  assert.equal(chatDetail({ ...chat({ state: 'turn', slot: 'chat:ab' }), ...whole }).picks_up, true)
  // What an epic has and a chat has not is empty, so that one view draws both.
  assert.deepEqual([detail.used, detail.calls, detail.params, detail.budget, detail.foreign], [[], [], {}, null, ''])
})

test('an epic is at an epic address, and a chat at a chat address by the same name', () => {
  assert.equal(pathOf({ name: 'a b', kind: 'flow' }), '/epics/a%20b')
  // A chat an earlier hmz kept as an epic keeps its name, and is a chat as any other.
  assert.equal(pathOf(chatRow(chat({ id: 'a b' }))), '/chats/a%20b')
})

/** A harness session as `chat.harness.list` rows one. */
const session = (fields = {}) => ({ id: 'aaaa-1', harness: 'claude', title: 'Tidy the parser', workspace: '/w s', model: 'opus', began: '2026-01-01T00:00:00Z', updated: '2026-01-02T00:00:00Z', ...fields })

test('a harness session is a row of its own kind, told by its title or else its id, never going', () => {
  const row = harnessRow(session())
  assert.deepEqual([row.name, row.kind, row.task, row.how, row.held, row.ended], ['harness:claude:aaaa-1', 'harness', 'Tidy the parser', 'stopped', false, '2026-01-02T00:00:00Z'])
  assert.equal(harnessRow(session({ title: '' })).task, 'aaaa-1')
  // Two harnesses may give one id: the rows are told apart.
  assert.notEqual(harnessRow(session({ harness: 'codex' })).name, row.name)
})

test('a harness session has an address of its own, which names its harness, its id and its workspace', () => {
  assert.equal(pathOf(harnessRow(session())), '/harness/claude/aaaa-1?workspace=%2Fw%20s')
})

test('harness sessions after a group’s rows count among what it shows before Show N more', () => {
  const chats = Array.from({ length: GROUP_ROWS - 1 }, (_, at) => chatRow(chat({ id: `c${at}` })))
  const outside = [1, 2, 3].map((at) => harnessRow(session({ id: `s${at}` })))
  const { rows, more } = paged([...chats, ...outside])
  assert.deepEqual([rows.length, rows.at(-1).name, more], [GROUP_ROWS, 'harness:claude:s1', 2])
  // The one the page is on is shown wherever it stands.
  assert.equal(paged([...chats, ...outside], GROUP_ROWS, 'harness:claude:s3').rows.at(-1).name, 'harness:claude:s3')
})
