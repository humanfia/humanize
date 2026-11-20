import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { test } from 'node:test'

import { PRESETS, SCOPES, created, missing, permissionSaid, scopeOf, scopeSaid, sessionOf, stateOf, stateSaid, told } from '../../../../src/hmz/web/static/aichan.js'

const at = (path) => {
  const url = new URL(path, 'http://page')
  return [url.pathname.split('/').filter(Boolean).map(decodeURIComponent), url.searchParams]
}

const FORM = { scope: 'workspace', workspace: '/w', epic: '', nous: '', preset: 'read-only', network: false, title: '', task: 'look around' }

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

test('the form offers every scope and preset, read-only first', () => {
  assert.deepEqual(SCOPES.map(([value]) => value), ['daemon', 'workspace', 'epic'])
  assert.equal(PRESETS[0], 'read-only')
  assert.deepEqual(PRESETS, ['read-only', 'danger-full-access'])
})

test('aichan.create is sent only what the scope takes, and leaves defaults out', () => {
  assert.deepEqual(created({ ...FORM, scope: 'daemon', workspace: '/w', epic: 'e' }), { scope: 'daemon', preset: 'read-only', network: false, task: 'look around' })
  assert.deepEqual(created({ ...FORM, epic: 'e' }), { scope: 'workspace', workspace: '/w', preset: 'read-only', network: false, task: 'look around' })
  assert.deepEqual(created({ ...FORM, scope: 'epic', epic: ' e ', nous: ' fast ', title: ' T ', preset: 'danger-full-access', network: true, task: ' go \n' }), {
    scope: 'epic',
    workspace: '/w',
    epic: 'e',
    nous: 'fast',
    title: 'T',
    preset: 'danger-full-access',
    network: true,
    task: 'go',
  })
})

test('the form says what it lacks before it makes a conversation', () => {
  assert.equal(missing({ ...FORM, workspace: '' }, 'fast'), 'Pick the workspace she works in.')
  assert.equal(missing({ ...FORM, scope: 'epic' }, 'fast'), 'Name the epic she works on.')
  assert.equal(missing(FORM, ''), 'Pick her nous: Settings name none for Ai-chan.')
  assert.equal(missing({ ...FORM, task: '  ' }, 'fast'), 'Tell Ai-chan something to start with.')
  assert.equal(missing({ ...FORM, nous: 'claude/claude-opus-5' }, ''), '')
  assert.equal(missing({ ...FORM, scope: 'daemon', workspace: '' }, 'fast'), '')
})

test('a conversation is said by its state, its scope and its permission', () => {
  assert.equal(stateSaid('running'), 'Answering')
  assert.equal(stateSaid('waiting'), 'Waiting')
  assert.equal(stateSaid('folded'), 'Folded away')
  assert.equal(scopeSaid({ scope: 'daemon', workspace: '/home/me/ai/box', epic: '' }), 'Daemon')
  assert.equal(scopeSaid({ scope: 'workspace', workspace: '/home/me/proj', epic: '' }), 'Workspace proj')
  assert.equal(scopeSaid({ scope: 'epic', workspace: '/home/me/proj', epic: 'brave-otter' }), 'Epic brave-otter · proj')
  assert.equal(permissionSaid({ preset: 'read-only', network: false }), 'read-only · network off')
  assert.equal(permissionSaid({ preset: 'danger-full-access', network: true }), 'danger-full-access · network on')
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

test('a conversation whose chat ended failed stands failed, with what the harness said', () => {
  const failed = [{ type: 'started', run: 1 }, { type: 'ended', run: 1, how: 'failed', why: 'HarnessNotInstalled: codex is not installed here' }]
  // Her host still holds the chat that failed, idle and between no turns: never `waiting`.
  assert.deepEqual(stateOf({ connected: true, turn: 'done', records: failed }), { state: 'failed', why: 'HarnessNotInstalled: codex is not installed here' })
  assert.deepEqual(stateOf({ connected: false, turn: '', records: failed }), { state: 'failed', why: 'HarnessNotInstalled: codex is not installed here' })
  assert.equal(stateSaid('failed'), 'Failed')
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
