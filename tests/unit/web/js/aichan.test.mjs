import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { test } from 'node:test'

import { FACES, PRESETS, SCOPES, actionsOf, created, earlierOf, faceOf, faceUrl, marked, marksOf, missing, ordered, previewOf, read, scopeOf, scopeSaid, scopesOf, sessionOf, settled, stateOf, titleOf, told, typingOf, unreadOf } from '../../../../src/hmz/web/static/aichan.js'
import { MODES, modeOf, offered } from '../../../../src/hmz/web/static/chips/permission-modes.js'
import { HOLD, SLOP, axisOf, offsetOf, restsOpen } from '../../../../src/hmz/web/static/swipe.js'

const at = (path) => {
  const url = new URL(path, 'http://page')
  return [url.pathname.split('/').filter(Boolean).map(decodeURIComponent), url.searchParams]
}

const FORM = { scope: 'workspace', workspace: '/w', epic: '', nous: 'claude/claude-opus-5', preset: 'read-only', task: 'look around' }
const NOUS = FORM.nous

test('the scope defaults to the epic shown, else the workspace shown, else the daemon', () => {
  assert.deepEqual(scopeOf(...at('/epics/brave-otter/sessions/a%2F1')), { scope: 'epic', workspace: '', epic: 'brave-otter' })
  assert.deepEqual(scopeOf(...at('/epics/brave-otter')), { scope: 'epic', workspace: '', epic: 'brave-otter' })
  assert.deepEqual(scopeOf(...at('/live?workspace=%2Fw&slot=chat%3A1')), { scope: 'workspace', workspace: '/w', epic: '' })
  assert.deepEqual(scopeOf(...at('/new?workspace=%2Fw')), { scope: 'workspace', workspace: '/w', epic: '' })
  assert.deepEqual(scopeOf(...at('/new')), { scope: 'daemon', workspace: '', epic: '' })
  // No epic named, no epic scope: never `epic` with an empty epic.
  assert.deepEqual(scopeOf(...at('/epics')), { scope: 'daemon', workspace: '', epic: '' })
  assert.deepEqual(scopeOf(...at('/flows?workspace=%2Fw')), { scope: 'workspace', workspace: '/w', epic: '' })
  // Importing an epic shows none.
  assert.deepEqual(scopeOf(...at('/epics/import')), { scope: 'daemon', workspace: '', epic: '' })
})

test('her chip offers every scope, and her two presets as a chat names its permissions, read-only first', () => {
  assert.deepEqual(SCOPES.map(([value]) => value), ['daemon', 'workspace', 'epic'])
  assert.deepEqual(PRESETS.map((one) => one.value), ['read-only', 'danger-full-access'])
  // Named as a chat's permissions are, each with its own line of what it lets her do.
  for (const one of PRESETS) {
    assert.equal(one.label, MODES.find((mode) => mode.value === one.value).label)
    assert.ok(one.about)
  }
  // The chip of a conversation is the chat's chip over these two: the first where none is picked.
  assert.equal(modeOf(null, PRESETS).value, 'read-only')
  assert.equal(modeOf('workspace-write', PRESETS).value, 'read-only')
  assert.deepEqual(offered('danger-full-access', PRESETS).map((one) => one.chosen), [false, true])
  // A chat's own are as they were.
  assert.equal(modeOf(null).value, 'workspace-write')
  assert.equal(scopeSaid('workspace'), 'Workspace')
  assert.equal(scopeSaid('room'), 'room')
})

test('a scope is offered with what it reaches, and is not picked with nothing to hold her to', () => {
  const said = (picked) => scopesOf(picked).map((one) => [one.value, one.about, one.chosen, Boolean(one.why)])
  assert.deepEqual(said({ scope: 'epic', workspace: '/home/me/atlas/', epic: 'brave-otter' }), [
    ['daemon', 'Every workspace and epic here', false, false],
    ['workspace', 'atlas', false, false],
    ['epic', 'brave-otter', true, false],
  ])
  // No epic shown, none to hold her to; nor a workspace where the daemon has none.
  assert.deepEqual(said({ scope: 'daemon', workspace: '', epic: '' }), [
    ['daemon', 'Every workspace and epic here', true, false],
    ['workspace', '', false, true],
    ['epic', '', false, true],
  ])
})

test('nothing of a new conversation asks for its network or its title', () => {
  const sources = ['aichan.js', 'views/aichan.js'].map((name) => readFileSync(new URL(`../../../../src/hmz/web/static/${name}`, import.meta.url), 'utf8'))
  for (const source of sources) assert.doesNotMatch(source, /network|aichan-title-field|t\('Title'\)/i)
})

test('aichan.create is sent only what the scope takes, always with the nous picked, and no title or network', () => {
  assert.deepEqual(created({ ...FORM, scope: 'daemon', workspace: '/w', epic: 'e' }), { scope: 'daemon', nous: NOUS, preset: 'read-only', task: 'look around' })
  assert.deepEqual(created({ ...FORM, epic: 'e' }), { scope: 'workspace', workspace: '/w', nous: NOUS, preset: 'read-only', task: 'look around' })
  assert.deepEqual(created({ ...FORM, scope: 'epic', epic: ' e ', nous: ' fast ', title: ' T ', network: true, preset: 'danger-full-access', task: ' go \n' }), {
    scope: 'epic',
    workspace: '/w',
    epic: 'e',
    nous: 'fast',
    preset: 'danger-full-access',
    task: 'go',
  })
})

test('a conversation is not made before a nous is picked and something is said', () => {
  assert.equal(missing({ ...FORM, nous: ' ' }), 'Pick a nous for Ai-chan.')
  assert.equal(missing({ ...FORM, task: '  ' }), 'Tell Ai-chan something to start with.')
  assert.equal(missing(FORM), '')
  // What the scope lacks is the daemon's to refuse: it cannot be picked without it.
  assert.equal(missing({ ...FORM, workspace: '' }), '')
})

test('a conversation has one of her sixteen faces, its own wherever it is drawn', () => {
  const faces = Array.from({ length: 200 }, (_, at) => faceOf(at + 1))
  assert.ok(faces.every((face) => Number.isInteger(face) && face >= 1 && face <= FACES))
  assert.equal(FACES, 16)
  // The same each time it is asked, and of every face some conversation's.
  assert.deepEqual(faces, Array.from({ length: 200 }, (_, at) => faceOf(at + 1)))
  assert.equal(new Set(faces).size, 16)
  // Conversations made one after another are told apart: the first sixteen share none.
  assert.equal(new Set(faces.slice(0, 16)).size, 16)
  assert.equal(faceUrl(1), `/ai-chan/face-${String(faceOf(1)).padStart(2, '0')}.webp`)
  assert.match(faceUrl(7), /^\/ai-chan\/face-(0[1-9]|1[0-6])\.webp$/)
  // One with no number yet is drawn all the same.
  assert.ok(faceOf(undefined) >= 1)
})

test('a row says its title and one line: that she is typing, else what was last said', () => {
  assert.equal(titleOf({ id: 3, title: 'Tidy the epics' }), 'Tidy the epics')
  assert.equal(titleOf({ id: 3, title: '' }), 'Ai-chan #3')
  assert.equal(previewOf({ state: 'waiting', latest: 'All three are done.' }), 'All three are done.')
  assert.equal(previewOf({ state: 'folded', latest: 'All three are done.' }), 'All three are done.')
  assert.equal(previewOf({ state: 'running', latest: 'All three are done.' }), 'typing…')
  // Nothing of how it stands, what it reaches or what it thinks with.
  const row = { id: 3, title: 'T', state: 'folded', scope: 'daemon', nous: 'claude/opus', preset: 'read-only', latest: '' }
  assert.equal(previewOf(row), '')
  assert.doesNotMatch(`${titleOf(row)} ${previewOf(row)}`, /daemon|folded|waiting|opus|read-only|network/i)
})

const NONE = { pinned: [], unread: [], failed: [], seen: {} }

test('what this browser keeps of her conversations is kept by daemon, and unreadable is nothing', () => {
  assert.deepEqual(marksOf(null, 'local'), NONE)
  assert.deepEqual(marksOf('x', 'local'), NONE)
  assert.deepEqual(marksOf({ gpu: { pinned: [1] } }, 'local'), NONE)
  assert.deepEqual(marksOf({ local: { pinned: [1, 'two', 3], unread: 'no', failed: [2], seen: { 1: 'a' } }, gpu: { pinned: [9] } }, 'local'), { pinned: [1, 3], unread: [], failed: [2], seen: { 1: 'a' } })
})

test('a conversation is unread once something is said in it after it was read, or once marked so', () => {
  const row = { id: 1, updated: '2026-01-01T10:00:00Z' }
  // Never listed here: read up to now as it is first listed, and unread by what is said after.
  const first = settled(NONE, [row])
  assert.deepEqual(first.seen, { 1: '2026-01-01T10:00:00Z' })
  assert.equal(unreadOf(row, first), false)
  const answered = { ...row, updated: '2026-01-01T10:05:00Z' }
  assert.equal(unreadOf(answered, settled(first, [answered])), true)
  // Open in the drawer, it is read as it is said in.
  assert.equal(unreadOf(answered, first, 1), false)
  const open = settled(first, [answered], 1)
  assert.equal(unreadOf(answered, open), false)
  // Marked unread, until it is marked read or opened.
  const marks = marked(open, 'unread', 1, true)
  assert.equal(unreadOf(answered, marks), true)
  assert.equal(unreadOf(answered, read(marks, answered)), false)
  assert.equal(unreadOf(answered, settled(marks, [answered], 1)), false)
  // Marked read, it is read up to what was last said.
  assert.deepEqual(read(marked(first, 'unread', 1, true), answered), { ...NONE, seen: { 1: '2026-01-01T10:05:00Z' } })
  // One an earlier daemon lists with no `updated` is never unread on its own.
  assert.equal(unreadOf({ id: 2 }, settled(NONE, [{ id: 2 }])), false)
})

test('nothing is kept of a conversation that is gone, whose number the next may take', () => {
  const marks = { pinned: [1, 2], unread: [2], failed: [2, 3], seen: { 1: 'a', 2: 'b' } }
  assert.deepEqual(settled(marks, [{ id: 1, updated: 'c' }]), { pinned: [1], unread: [], failed: [], seen: { 1: 'a' } })
  // One deleted and made again while this browser did not look has the number, and none of the marks.
  const old = { pinned: [7, 8], unread: [7], failed: [7], seen: { 7: '2026-01-01T10:05:00Z', 8: '2026-01-01T10:05:00Z' } }
  const again = [
    { id: 7, created: '2026-01-02T09:00:00Z', updated: '2026-01-02T09:01:00Z' },
    { id: 8, created: '2026-01-01T10:00:00Z', updated: '2026-01-02T09:01:00Z' },
  ]
  const now = settled(old, again)
  assert.deepEqual(now, { pinned: [8], unread: [], failed: [], seen: { 7: '2026-01-02T09:01:00Z', 8: '2026-01-01T10:05:00Z' } })
  assert.equal(unreadOf(again[0], now), false)
  assert.equal(unreadOf(again[1], now), true)
  // Read up to no time, as an earlier daemon's is, it is the same one still.
  assert.deepEqual(settled({ ...NONE, pinned: [2], seen: { 2: '' } }, [{ id: 2, created: '2026-01-01T10:00:00Z' }]).pinned, [2])
  assert.deepEqual(marked(marks, 'pinned', 2, false).pinned, [1])
  assert.deepEqual(marked(marks, 'pinned', 2, true).pinned, [1, 2])
  assert.deepEqual(marked(marks, 'pinned', 5, true).pinned, [1, 2, 5])
})

test('the pinned are listed first, then each by when something was last said in it', () => {
  const rows = [
    { id: 4, created: '2026-01-04T00:00:00Z', updated: '2026-01-04T00:00:00Z' },
    { id: 3, created: '2026-01-03T00:00:00Z', updated: '2026-01-09T00:00:00Z' },
    { id: 2, created: '2026-01-02T00:00:00Z', updated: '2026-01-02T00:00:00Z' },
    { id: 1, created: '2026-01-01T00:00:00Z' },
  ]
  assert.deepEqual(ordered(rows, NONE).map((one) => one.id), [3, 4, 2, 1])
  assert.deepEqual(ordered(rows, { ...NONE, pinned: [1, 2] }).map((one) => one.id), [2, 1, 3, 4])
  // Said in at once, the newer first; and what is given is left as it was.
  assert.deepEqual(ordered([{ id: 1, updated: 'a' }, { id: 2, updated: 'a' }], NONE).map((one) => one.id), [2, 1])
  assert.deepEqual(rows.map((one) => one.id), [4, 3, 2, 1])
})

test('a conversation offers three things: pinning it or not, marking it read or unread, deleting it', () => {
  const row = { id: 1, updated: 'a' }
  const said = (marks) => actionsOf(row, marks).map((one) => [one.key, one.label, Boolean(one.on), Boolean(one.danger)])
  assert.deepEqual(said({ ...NONE, seen: { 1: 'a' } }), [
    ['pin', 'Pin', true, false],
    ['read', 'Mark as unread', false, false],
    ['delete', 'Delete', false, true],
  ])
  assert.deepEqual(said({ ...NONE, pinned: [1], unread: [1] }), [
    ['pin', 'Unpin', false, false],
    ['read', 'Mark as read', true, false],
    ['delete', 'Delete', false, true],
  ])
})

test('a finger that moves swipes the row or scrolls its list, and the row stays open past its half', () => {
  assert.equal(axisOf(3, 2), '')
  assert.equal(axisOf(-SLOP, 0), 'x')
  assert.equal(axisOf(-20, 6), 'x')
  assert.equal(axisOf(6, -20), 'y')
  assert.ok(HOLD >= 400)
  // Drawn no further than what is under it is wide, and never to the right of where it lies.
  assert.equal(offsetOf(-50, 204, false), -50)
  assert.equal(offsetOf(-500, 204, false), -204)
  assert.equal(offsetOf(40, 204, false), 0)
  assert.equal(offsetOf(60, 204, true), -144)
  assert.equal(offsetOf(-60, 204, true), -204)
  assert.equal(restsOpen(-103, 204), true)
  assert.equal(restsOpen(-102, 204), false)
  assert.equal(restsOpen(0, 0), false)
})

test('her session is the first conversation her host opened that is not a person', () => {
  assert.equal(sessionOf([]), '')
  assert.equal(sessionOf([{ type: 'started' }, { type: 'opened', person: true, key: 'human' }, { type: 'opened', key: 'ai_chan/1' }, { type: 'opened', key: 'ai_chan/2' }]), 'ai_chan/1')
})

test('a line typed to her answers what she waits on this page may answer, else is said', () => {
  assert.deepEqual(told([], 'me', 'hi'), ['say', { text: 'hi' }])
  assert.deepEqual(told(undefined, 'me', 'hi'), ['say', { text: 'hi' }])
  assert.deepEqual(told([{ question: 'q1', owner: 'other' }], 'me', 'hi'), ['say', { text: 'hi' }])
  assert.deepEqual(told([{ question: 'q1', owner: 'other' }, { question: 'q2' }], 'me', 'hi'), ['answer', { question: 'q2', text: 'hi' }])
  assert.deepEqual(told([{ question: 'q3', owner: 'me' }], 'me', 'hi'), ['answer', { question: 'q3', text: 'hi' }])
})

test('she is typing while her turn is open, and not while she waits on the person in it', () => {
  assert.equal(typingOf(true, [], 'me'), true)
  assert.equal(typingOf(false, [], 'me'), false)
  // A question of hers mid-turn, with answers offered or none.
  assert.equal(typingOf(true, [{ question: 'q1', options: ['yes', 'no'] }], 'me'), false)
  assert.equal(typingOf(true, [{ question: 'q1', options: [] }], 'me'), false)
  assert.equal(typingOf(true, [{ question: 'q1' }], 'me'), false)
  assert.equal(typingOf(true, [{ question: 'q1', owner: 'me' }], 'me'), false)
  // One that is another's to answer leaves her typing here.
  assert.equal(typingOf(true, [{ question: 'q1', owner: 'other' }], 'me'), true)
})

test('a conversation whose chat ended failed stands failed, with what the harness said', () => {
  const failed = [{ type: 'started', run: 1 }, { type: 'ended', run: 1, how: 'failed', why: 'HarnessNotInstalled: codex is not installed here' }]
  // Her host still holds the chat that failed, idle and between no turns: never `waiting`.
  assert.deepEqual(stateOf({ connected: true, turn: 'done', records: failed }), { state: 'failed', why: 'HarnessNotInstalled: codex is not installed here' })
  assert.deepEqual(stateOf({ connected: false, turn: '', records: failed }), { state: 'failed', why: 'HarnessNotInstalled: codex is not installed here' })
  const open = [{ type: 'started', run: 1 }]
  assert.deepEqual(stateOf({ connected: true, turn: 'running', records: open }), { state: 'running', why: '' })
  assert.deepEqual(stateOf({ connected: true, turn: 'done', records: open }), { state: 'waiting', why: '' })
  assert.deepEqual(stateOf({ connected: false, turn: '', records: open }), { state: 'folded', why: '' })
  // A chat stopped is one folded away, carried on by the next line.
  assert.deepEqual(stateOf({ connected: false, turn: '', records: [...open, { type: 'ended', run: 1, how: 'stopped' }] }), { state: 'folded', why: '' })
})

test('her avatar and her sixteen faces are WebP files of the page, and the docs carry the same', () => {
  const names = ['avatar.webp', ...Array.from({ length: 16 }, (_, at) => `face-${String(at + 1).padStart(2, '0')}.webp`)].sort()
  const page = new URL('../../../../src/hmz/web/static/ai-chan/', import.meta.url)
  const docs = new URL('../../../../docs/public/ai-chan/', import.meta.url)
  assert.deepEqual(readdirSync(page).sort(), names)
  assert.deepEqual(readdirSync(docs).sort(), names)
  for (const name of names) {
    const file = readFileSync(new URL(name, page))
    assert.equal(file.subarray(0, 4).toString('latin1'), 'RIFF', name)
    assert.equal(file.subarray(8, 12).toString('latin1'), 'WEBP', name)
    assert.ok(file.length < 64 * 1024, name)
    assert.ok(file.equals(readFileSync(new URL(name, docs))), name)
  }
})

test('what a conversation carried on did before is drawn without what she was told of herself, or the model she thought with', () => {
  const told = 'You are Ai-chan, through whom the user operates hmz.\n\nYour scope is the whole daemon.\n\nThe user says:\n\nhello\nthere'
  const actions = [
    { category: 'llm', name: 'think', args: { model: 'claude-opus-5' } },
    { category: 'turn', name: 'turn', args: { prompt: told } },
    { category: 'llm', name: 'think', args: { model: 'claude-opus-5', thinking: 'hm' } },
    { category: 'message', name: 'hi', args: { text: 'hi' } },
    { category: 'turn', name: 'turn', args: { prompt: 'The user says:\n\nnot hers' } },
    { category: 'turn', name: 'go on' },
    { category: 'tool', name: 'runs.list', args: { input: {} } },
  ]
  assert.deepEqual(earlierOf(actions), [
    { category: 'turn', name: 'turn', args: { prompt: 'hello\nthere' } },
    { category: 'llm', name: 'think', args: { model: '', thinking: 'hm' } },
    actions[3],
    // A line of the person's own that only reads like it is left as it was said.
    actions[4],
    actions[5],
    actions[6],
  ])
})
