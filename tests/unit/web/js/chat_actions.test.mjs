import assert from 'node:assert/strict'
import { test } from 'node:test'

import { DELETING, NO_WORKTREE, TITLE_MOST, chatDetail, chatRow, inRepository, titled, worksIn } from '../../../../src/hmz/web/static/chats.js'
import { asked } from '../../../../src/hmz/web/static/search-model.js'

test('a title typed is recorded as chat.rename records it, and white space alone is no title', () => {
  assert.equal(titled('  a\n new\t  name '), 'a new name')
  assert.equal(titled(' \n\t'), '')
  assert.equal(titled(undefined), '')
  assert.equal(titled('x'.repeat(TITLE_MOST + 9)).length, TITLE_MOST)
})

test('a chat works in its worktree only where that is not its workspace', () => {
  assert.equal(worksIn({ workspace: '/w', workdir: '/w' }), '')
  assert.equal(worksIn({ workspace: '/w' }), '')
  assert.equal(worksIn({ workspace: '/w', workdir: '/trees/w-1' }), '/trees/w-1')
})

test('a row and a detail keep whether the chat is archived and where it works', () => {
  const chat = { id: 'c1', title: 't', task: 't', workspace: '/w', workdir: '/trees/c1', state: 'resting', slot: '', archived: true, agents: [], sessions: [] }
  assert.equal(chatRow(chat).archived, true)
  assert.equal(worksIn(chatDetail(chat)), '/trees/c1')
})

test('what deleting does is said whole: gone for good, its sessions with it, its worktree left', () => {
  assert.match(DELETING, /permanently/)
  assert.match(DELETING, /sessions/)
  assert.match(DELETING, /cannot be undone/)
  assert.match(DELETING, /worktree .* left on disk/)
})

test('why no worktree is on offer is said for no folder and for a folder that is no repository', () => {
  assert.ok(NO_WORKTREE.none && NO_WORKTREE.plain && NO_WORKTREE.none !== NO_WORKTREE.plain)
})

/**
 * A machine's directories, listed as `paths.list` lists one: `dirs` are there, `files` are
 * there and no directory, `shut` cannot be read, and anything else is not there.
 */
function lister({ dirs = [], files = [], shut = [] }, asked = []) {
  return async (at) => {
    asked.push(at)
    if (dirs.includes(at)) return { whole: at, entries: [], more: 0, up: '' }
    const why = files.includes(at) ? 'Not a directory' : shut.includes(at) ? 'Permission denied' : 'No such file or directory'
    throw new Error(`${at} cannot be read: ${why}`)
  }
}

test('a folder is in a repository where it or a directory over it holds .git', async () => {
  const asked = []
  assert.equal(await inRepository(lister({ dirs: ['/a/b/c', '/a/.git'] }, asked), '/a/b/c'), true)
  // The folder, then `.git` in it and in every directory over it, the root included.
  assert.deepEqual(asked, ['/a/b/c', '/a/b/c/.git', '/a/b/.git', '/a/.git', '/.git'])
  assert.equal(await inRepository(lister({ dirs: ['/a', '/a/.git'] }), '/a'), true)
  assert.equal(await inRepository(lister({ dirs: ['/', '/.git'] }), '/'), true)
})

test('a worktree, which keeps a file named .git, is in a repository', async () => {
  assert.equal(await inRepository(lister({ dirs: ['/trees/w'], files: ['/trees/w/.git'] }), '/trees/w'), true)
})

test('a folder with no .git up to the root is known to be in no repository', async () => {
  assert.equal(await inRepository(lister({ dirs: ['/a/b'] }), '/a/b'), false)
  assert.equal(await inRepository(lister({ dirs: ['/'] }), '/'), false)
})

test('whether a folder is in a repository is not known where it, or a .git, cannot be read', async () => {
  assert.equal(await inRepository(lister({}), '/gone'), null)
  assert.equal(await inRepository(lister({ dirs: ['/a/b'], shut: ['/a/.git'] }), '/a/b'), null)
  // Found elsewhere over it, it is known all the same.
  assert.equal(await inRepository(lister({ dirs: ['/a/b', '/a/b/.git'], shut: ['/a/.git'] }), '/a/b'), true)
  // A path this cannot go up from says nothing.
  assert.equal(await inRepository(async () => ({ whole: 'C:\\a' }), 'C:\\a'), null)
})

test('Search asks chat.list for no archived chat', () => {
  for (const kind of ['', 'chat']) {
    const chats = asked({ kind, q: 'x', workspace: '/w', flow: '', status: '', offset: 0 }).filter(([method]) => method === 'chat.list')
    assert.equal(chats.length, 1)
    assert.ok(!('archived' in chats[0][1]))
  }
})
