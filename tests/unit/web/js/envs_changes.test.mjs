import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  bytesText,
  chosen,
  commitPlan,
  comparePaths,
  decoded,
  fullDate,
  groupsOf,
  hunks,
  LARGE,
  letterOf,
  moveOf,
  pathsOf,
  picked,
  placeOf,
  relative,
  rowsOf,
  sizeOf,
  split,
  subjectHint,
  treeOf,
} from '../../../../src/hmz/web/static/views/envs/changes_logic.js'
import { joinPath } from '../../../../src/hmz/web/static/views/envs/files_logic.js'

const b64 = (text) => Buffer.from(text).toString('base64')
const paths = (list) => list.map((one) => one.path)

const STATUS = [
  { path: 'src/b.py', index: 'M', worktree: 'M', state: 'changed' },
  { path: 'README.md', index: '.', worktree: 'M', state: 'changed' },
  { path: 'src/a.py', index: 'A', worktree: '.', state: 'changed' },
  { path: 'docs/new.md', orig: 'docs/old.md', index: 'R', worktree: '.', state: 'changed' },
  { path: 'gone.txt', index: '.', worktree: 'D', state: 'changed' },
  { path: 'mode.sh', index: 'T', worktree: '.', state: 'changed' },
  { path: 'both.c', index: 'U', worktree: 'U', state: 'conflict' },
  { path: 'notes/todo.txt', index: '?', worktree: '?', state: 'untracked' },
]

test('each file falls in its group, a file changed in both the index and the worktree in both', () => {
  const groups = groupsOf(STATUS)
  assert.deepEqual(paths(groups.merge), ['both.c'])
  assert.deepEqual(paths(groups.staged), ['docs/new.md', 'mode.sh', 'src/a.py', 'src/b.py'])
  assert.deepEqual(paths(groups.changes), ['gone.txt', 'README.md', 'src/b.py'])
  assert.deepEqual(paths(groups.untracked), ['notes/todo.txt'])
  assert.deepEqual(groupsOf(), { merge: [], staged: [], changes: [], untracked: [] })
})

test('each entry is marked with its letter, keyed by its group, and split into name and folder', () => {
  const groups = groupsOf(STATUS)
  const of = (group, path) => groups[group].find((one) => one.path === path)
  assert.equal(of('merge', 'both.c').letter, 'U')
  assert.equal(of('untracked', 'notes/todo.txt').letter, '?')
  assert.equal(of('staged', 'src/a.py').letter, 'A')
  assert.equal(of('staged', 'mode.sh').letter, 'M')
  assert.equal(of('changes', 'gone.txt').letter, 'D')
  const renamed = of('staged', 'docs/new.md')
  assert.equal(renamed.letter, 'R')
  assert.equal(renamed.orig, 'docs/old.md')
  assert.equal(renamed.name, 'new.md')
  assert.equal(renamed.dir, 'docs')
  assert.equal(of('staged', 'src/b.py').key, 'staged:src/b.py')
  assert.equal(of('changes', 'src/b.py').key, 'changes:src/b.py')
  assert.equal(of('changes', 'src/b.py').orig, undefined)
})

test('a rename keeps its old path only where it is the rename', () => {
  const groups = groupsOf([{ path: 'b', orig: 'a', index: 'R', worktree: 'M', state: 'changed' }])
  assert.equal(groups.staged[0].orig, 'a')
  assert.equal(groups.changes[0].orig, undefined)
  assert.deepEqual(pathsOf(groups.staged), ['b', 'a'])
  assert.deepEqual(pathsOf([...groups.staged, ...groups.changes]), ['b', 'a'])
})

test('letters: a type change is a modification, anything unknown too', () => {
  assert.deepEqual(['M', 'T', 'A', 'D', 'R', 'C', 'U', '?', 'X'].map(letterOf), ['M', 'M', 'A', 'D', 'R', 'C', 'U', '?', 'M'])
})

test('paths are ordered a folder at a time, case aside first', () => {
  const list = ['a-b', 'a/z', 'B.txt', 'a.txt', 'a/b/c', 'A/x', 'b.txt']
  assert.deepEqual([...list].sort(comparePaths), ['A/x', 'a/b/c', 'a/z', 'a-b', 'a.txt', 'b.txt', 'B.txt'].sort(comparePaths))
  assert.ok(comparePaths('a/z', 'a-b') < 0)
  assert.ok(comparePaths('a', 'a/b') < 0)
  assert.ok(comparePaths('A', 'a') < 0)
  assert.equal(comparePaths('x/y', 'x/y'), 0)
  assert.deepEqual(split('a/b/c.txt'), { name: 'c.txt', dir: 'a/b' })
  assert.deepEqual(split('top'), { name: 'top', dir: '' })
})

test('a tree holds folders before files, and folds a folder holding one folder alone', () => {
  const { changes } = groupsOf([
    { path: 'z.txt', index: '.', worktree: 'M', state: 'changed' },
    { path: 'src/deep/er/x.py', index: '.', worktree: 'M', state: 'changed' },
    { path: 'src/a.py', index: '.', worktree: 'M', state: 'changed' },
    { path: 'lib/one/two/b.py', index: '.', worktree: 'M', state: 'changed' },
  ])
  const tree = treeOf(changes)
  assert.deepEqual(tree.dirs.map((dir) => dir.name), ['lib/one/two', 'src'])
  assert.equal(tree.dirs[0].path, 'lib/one/two')
  assert.deepEqual(paths(tree.files), ['z.txt'])
  const src = tree.dirs[1]
  assert.deepEqual(src.dirs.map((dir) => [dir.name, dir.path]), [['deep/er', 'src/deep/er']])
  assert.deepEqual(paths(src.files), ['src/a.py'])
})

test('rows: each group with files under its header, as a list or a tree, folded where asked', () => {
  const groups = groupsOf(STATUS)
  const list = rowsOf(groups)
  assert.deepEqual(
    list.filter((row) => row.kind === 'group').map((row) => [row.title, row.count]),
    [
      ['Merge Changes', 1],
      ['Staged Changes', 4],
      ['Changes', 3],
      ['Untracked', 1],
    ],
  )
  assert.equal(list.length, 4 + 9)
  assert.ok(list.filter((row) => row.kind === 'file').every((row) => row.depth === 1))

  const tree = rowsOf(groups, { view: 'tree' })
  const staged = tree.filter((row) => row.group === 'staged').map((row) => [row.kind, row.depth, row.kind === 'file' ? row.entry.path : row.name || row.title])
  assert.deepEqual(staged, [
    ['group', 0, 'Staged Changes'],
    ['dir', 1, 'docs'],
    ['file', 2, 'docs/new.md'],
    ['dir', 1, 'src'],
    ['file', 2, 'src/a.py'],
    ['file', 2, 'src/b.py'],
    ['file', 1, 'mode.sh'],
  ])
  const dir = tree.find((row) => row.key === 'staged:src/')
  assert.deepEqual(paths(dir.entries), ['src/a.py', 'src/b.py'])

  const folded = rowsOf(groups, { view: 'tree', collapsed: new Set(['staged:src/', 'changes']) })
  assert.ok(!folded.some((row) => row.key === 'staged:src/a.py'))
  assert.ok(folded.some((row) => row.key === 'staged:src/' && !row.open))
  assert.deepEqual(folded.filter((row) => row.group === 'changes').map((row) => row.kind), ['group'])
  assert.equal(folded.find((row) => row.key === 'changes').open, false)
  assert.deepEqual(rowsOf(groupsOf([])), [])
})

test('picking: alone, with Ctrl to add or take away, with Shift for a run from the anchor', () => {
  const keys = ['a', 'b', 'c', 'd', 'e']
  let at = picked({ selected: new Set(), anchor: null }, keys, 'b')
  assert.deepEqual([...at.selected], ['b'])
  at = picked(at, keys, 'd', { range: true })
  assert.deepEqual([...at.selected].sort(), ['b', 'c', 'd'])
  assert.equal(at.anchor, 'b')
  at = picked(at, keys, 'a', { range: true })
  assert.deepEqual([...at.selected].sort(), ['a', 'b'])
  at = picked(at, keys, 'e', { toggle: true })
  assert.deepEqual([...at.selected].sort(), ['a', 'b', 'e'])
  assert.equal(at.anchor, 'e')
  at = picked(at, keys, 'a', { toggle: true })
  assert.deepEqual([...at.selected].sort(), ['b', 'e'])
  // Ctrl and Shift together add the run from the anchor, the row last toggled.
  at = picked(at, keys, 'c', { range: true, toggle: true })
  assert.deepEqual([...at.selected].sort(), ['a', 'b', 'c', 'e'])
  // An anchor no longer drawn picks the row alone.
  at = picked({ selected: new Set(['x']), anchor: 'x' }, keys, 'c', { range: true })
  assert.deepEqual([...at.selected], ['c'])
})

test('what is picked stands for its entries by group, a folder for every file under it', () => {
  const rows = rowsOf(groupsOf(STATUS), { view: 'tree' })
  const by = chosen(rows, new Set(['staged:src/', 'staged:src/a.py', 'merge:both.c', 'untracked']))
  assert.deepEqual(paths(by.staged), ['src/a.py', 'src/b.py'])
  assert.deepEqual(paths(by.merge), ['both.c'])
  assert.deepEqual(paths(by.untracked), ['notes/todo.txt'])
  assert.equal(moveOf('staged'), 'unstage')
  assert.equal(moveOf('changes'), 'stage')
  assert.equal(moveOf('merge'), 'stage')
})

test('a commit: refused with conflicts or no message, smart where nothing is staged', () => {
  const none = { merge: [], staged: [], changes: [], untracked: [] }
  const groups = groupsOf(STATUS)
  assert.deepEqual(commitPlan({ groups, message: 'x' }), { action: 'refuse', why: 'Resolve the merge conflicts before committing.' })
  const clean = { ...groups, merge: [] }
  assert.equal(commitPlan({ groups: clean, message: '  \n' }).action, 'refuse')
  assert.deepEqual(commitPlan({ groups: clean, message: 'Fix' }), { action: 'commit' })
  const unstaged = { ...clean, staged: [] }
  assert.deepEqual(commitPlan({ groups: unstaged, message: 'Fix' }), { action: 'stage', paths: ['gone.txt', 'README.md', 'src/b.py'] })
  assert.deepEqual(commitPlan({ groups: { ...none, untracked: groups.untracked }, message: 'Add' }), { action: 'stage', paths: ['notes/todo.txt'] })
  assert.deepEqual(commitPlan({ groups: none, message: 'Nothing' }), { action: 'refuse', why: 'There is nothing to commit.' })
  assert.deepEqual(commitPlan({ groups: none, message: 'Reword', amend: true }), { action: 'commit' })
})

test('a subject is fine to 50 characters, long to 72, over past it', () => {
  assert.deepEqual(subjectHint(''), { length: 0, level: 'ok' })
  assert.deepEqual(subjectHint('x'.repeat(50)), { length: 50, level: 'ok' })
  assert.deepEqual(subjectHint(`${'x'.repeat(51)}\n\nbody`), { length: 51, level: 'long' })
  assert.deepEqual(subjectHint('x'.repeat(72)), { length: 72, level: 'long' })
  assert.deepEqual(subjectHint('x'.repeat(73)), { length: 73, level: 'over' })
  assert.equal(subjectHint('é✓😀').length, 3)
})

test('a moment is said as how long ago it was', () => {
  const now = Date.parse('2026-11-17T12:00:00Z')
  const ago = (seconds) => relative(new Date(now - seconds * 1000).toISOString(), now)
  assert.equal(ago(10), 'just now')
  assert.equal(ago(60), '1 minute ago')
  assert.equal(ago(5 * 60), '5 minutes ago')
  assert.equal(ago(3600), '1 hour ago')
  assert.equal(ago(5 * 3600), '5 hours ago')
  assert.equal(ago(86400), '1 day ago')
  assert.equal(ago(3 * 86400), '3 days ago')
  assert.equal(ago(14 * 86400), '2 weeks ago')
  assert.equal(ago(60 * 86400), '2 months ago')
  assert.equal(ago(800 * 86400), '2 years ago')
  assert.equal(relative((now - 7200 * 1000) / 1000, now), '2 hours ago')
  assert.equal(relative('2026-11-17T13:00:00Z', now), 'just now')
  assert.equal(relative('nonsense', now), '')
  assert.equal(relative(null, now), '')
  assert.equal(fullDate('2026-11-17T12:00:00.123Z'), '2026-11-17 12:00:00 UTC')
  assert.equal(fullDate(''), '')
})

test('a side of a diff is decoded as text, binary where it holds a NUL or is not UTF-8', () => {
  assert.deepEqual(decoded(b64('héllo\n')), { text: 'héllo\n', binary: false, absent: false, size: 7 })
  assert.deepEqual(decoded(null), { text: '', binary: false, absent: true, size: 0 })
  assert.deepEqual(decoded(''), { text: '', binary: false, absent: false, size: 0 })
  assert.equal(decoded(Buffer.from([0x89, 0x50, 0x00, 0x47]).toString('base64')).binary, true)
  assert.equal(decoded(Buffer.from([0xff, 0xfe, 0x41]).toString('base64')).binary, true)
  assert.equal(decoded(Buffer.concat([Buffer.alloc(9000, 0x61), Buffer.from([0])]).toString('base64')).binary, false)
})

test('a size is read off base64 without decoding it, and said in binary units', () => {
  for (const length of [0, 1, 2, 3, 4, 5, 100]) assert.equal(sizeOf(Buffer.alloc(length).toString('base64')), length)
  assert.equal(sizeOf(null), 0)
  assert.equal(LARGE, 2 * 1024 * 1024)
  assert.equal(bytesText(512), '512 B')
  assert.equal(bytesText(1536), '1.5 KiB')
  assert.equal(bytesText(3 * 1024 * 1024), '3.0 MiB')
  assert.equal(bytesText(200 * 1024 * 1024), '200 MiB')
})

test('the changes of a diff are found as runs of lines on each side', () => {
  assert.deepEqual(hunks('a\nb\nc', 'a\nb\nc'), [])
  assert.deepEqual(hunks('a\nb\nc', 'a\nB\nc'), [{ fromA: 1, toA: 2, fromB: 1, toB: 2 }])
  assert.deepEqual(hunks('a\nc', 'a\nb\nc'), [{ fromA: 1, toA: 1, fromB: 1, toB: 2 }])
  assert.deepEqual(hunks('a\nb\nc', 'a\nc'), [{ fromA: 1, toA: 2, fromB: 1, toB: 1 }])
  assert.deepEqual(hunks('', 'x\ny'), [{ fromA: 0, toA: 1, fromB: 0, toB: 2 }])
  assert.deepEqual(hunks('1\n2\n3\n4\n5\n6\n7', '1\nX\n3\n4\n5\nY\nZ\n7'), [
    { fromA: 1, toA: 2, fromB: 1, toB: 2 },
    { fromA: 5, toA: 6, fromB: 5, toB: 7 },
  ])
  // Every line not in a run is the same line on both sides, in order.
  const old = Array.from({ length: 300 }, (_, i) => `line ${i % 37}`).join('\n')
  const now = Array.from({ length: 280 }, (_, i) => `line ${(i * 7) % 41}`).join('\n')
  const runs = hunks(old, now)
  const a = old.split('\n')
  const b = now.split('\n')
  let i = 0
  let j = 0
  for (const run of [...runs, { fromA: a.length, toA: a.length, fromB: b.length, toB: b.length }]) {
    assert.equal(run.fromA - i, run.fromB - j)
    while (i < run.fromA) assert.equal(a[i++], b[j++])
    i = run.toA
    j = run.toB
  }
  // Past the most edits looked for, the middle is one change.
  assert.deepEqual(hunks('a\n1\n2\nz', 'a\n3\n4\nz', 1), [{ fromA: 1, toA: 3, fromB: 1, toB: 3 }])
})

test('a changed file opens in Files where it is, the workdir a directory inside the repository', () => {
  // `env.git.status` names a file from the repository's top; Files resolves a path from the workdir.
  const [root, workdir] = ['/repo', '/repo/pkg']
  assert.equal(joinPath(workdir, placeOf(root, 'pkg/a.txt')), '/repo/pkg/a.txt')
  assert.equal(joinPath(workdir, placeOf(root, 'top.txt')), '/repo/top.txt')
  assert.equal(joinPath(workdir, placeOf(root, 'pkg/sp ace.txt')), '/repo/pkg/sp ace.txt')
  assert.equal(joinPath('/repo', placeOf('/repo/', 'a.txt')), '/repo/a.txt')
  assert.equal(placeOf('/', 'a.txt'), '/a.txt')
})
