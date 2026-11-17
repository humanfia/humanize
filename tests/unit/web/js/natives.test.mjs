import assert from 'node:assert/strict'
import { test } from 'node:test'

import { both, bothHint, completions, pathItems, pathParts, preferSaid, refusedSaid, route, shellOf, shellParts, tagOf, typing } from '../../../../src/hmz/web/static/natives.js'

/** A catalogue as `chat.commands` answers one: native entries, then hmz's, then the flows. */
const entries = [
  { sigil: '/', name: 'model', about: 'Change the model', how: 'call', source: 'native' },
  { sigil: '/', name: 'review', about: 'Review changes', how: 'call', source: 'native' },
  { sigil: '/', name: 'config', about: 'Settings dialog', how: 'refuse', source: 'native' },
  { sigil: '$', name: 'ralph', about: 'A skill', how: 'call', source: 'native' },
  { sigil: '$', name: 'lint', about: 'Lint it', how: 'call', source: 'native' },
  { sigil: '!', name: '', about: 'Run a command', how: 'call', source: 'native' },
  { sigil: '@', name: '', about: 'Mention a file', how: 'call', source: 'native' },
  { sigil: '/', name: 'flow', about: '', how: '', source: 'hmz' },
  { sigil: '/', name: 'prefer', about: '', how: '', source: 'hmz' },
  { sigil: '$', name: 'ralph', about: 'Loop until done', how: '', source: 'flow' },
  { sigil: '$', name: 'swe', about: 'Software flow', how: '', source: 'flow' },
]

test('a sigil names something at the start of a line, `@` wherever a word starts, `!` never completes', () => {
  assert.deepEqual(typing('/mo', 3), { sigil: '/', word: 'mo', from: 0, to: 3 })
  assert.deepEqual(typing('  $ra', 5), { sigil: '$', word: 'ra', from: 2, to: 5 })
  assert.equal(typing('say /mo', 7), null)
  assert.equal(typing('/model x', 8), null)
  assert.deepEqual(typing('look at @src/ma', 15), { sigil: '@', word: 'src/ma', from: 8, to: 15 })
  assert.equal(typing('!ls', 3), null)
  assert.equal(typing('plain', 5), null)
  // The second word of `/flow` names a flow.
  assert.deepEqual(typing('/flow sw', 8), { sigil: 'flow', word: 'sw', from: 6, to: 8 })
})

test('each entry is tagged with where it comes from', () => {
  assert.deepEqual(entries.map(tagOf), ['command', 'command', 'command', 'skill', 'skill', 'command', 'command', 'hmz', 'hmz', 'flow', 'flow'])
})

test('`/` completes native commands and hmz names, grouped by source, those it starts first', () => {
  const groups = completions(entries, typing('/', 1), 'native')
  assert.deepEqual(groups.map((one) => one.label), ['Native', 'hmz'])
  assert.deepEqual(groups[0].items.map((one) => one.insert), ['/model ', '/review ', '/config '])
  assert.equal(groups[0].items[2].refused, true)
  const found = completions(entries, typing('/e', 2), 'native').flatMap((one) => one.items.map((item) => item.name))
  // Started with first, then those it is within.
  assert.deepEqual(found, ['/model', '/review', '/prefer'])
})

test('`$` completes skills and flows, saying which a name that is both goes to', () => {
  const groups = completions(entries, typing('$r', 2), 'native')
  assert.deepEqual(
    groups.map((one) => [one.label, one.items.map((item) => [item.name, item.tag])]),
    [
      ['Native', [['$ralph', 'skill']]],
      ['Flows', [['$ralph', 'flow']]],
    ],
  )
  assert.match(groups[0].items[0].hint, /uses the skill.*\/flow ralph starts the flow/)
  assert.equal(completions(entries, typing('$sw', 3), 'native')[0].items[0].hint, '')
})

test('the hint for a name that is both follows the preference', () => {
  assert.equal(both(entries, 'ralph'), true)
  assert.equal(both(entries, 'swe'), false)
  assert.equal(both(entries, 'lint'), false)
  assert.match(bothHint('ralph', 'native'), /^\$ralph uses the skill/)
  assert.match(bothHint('ralph', 'flow'), /^\$ralph starts the flow/)
})

test('`/flow` completes only flows, by name alone', () => {
  const groups = completions(entries, typing('/flow ', 6), 'native')
  assert.deepEqual(groups.map((one) => one.label), ['Flows'])
  assert.deepEqual(groups[0].items.map((one) => one.insert), ['ralph ', 'swe '])
})

test('`@` offers the catalogue entry, which names no path', () => {
  const groups = completions(entries, typing('@', 1), 'native')
  assert.deepEqual(groups.map((one) => one.items.map((item) => item.name)), [['@']])
  assert.deepEqual(completions([], typing('@', 1), 'native'), [])
  assert.deepEqual(completions(entries, typing('@src', 4), 'native'), [])
})

test('a path after `@` is completed from its directory', () => {
  assert.deepEqual(pathParts('src/hm'), { dir: 'src/', base: 'hm' })
  assert.deepEqual(pathParts('READ'), { dir: '', base: 'READ' })
  const items = pathItems('src/', 'h', [
    { name: 'hmz', dir: true },
    { name: 'hello.py', dir: false },
    { name: 'other', dir: true },
  ])
  assert.deepEqual(items.map((one) => [one.insert, one.tag]), [['@src/hmz/', 'dir'], ['@src/hello.py ', 'file']])
})

test('a line is the page’s where hmz keeps its name or it names a flow; everything else is said', () => {
  assert.deepEqual(route('/settings', entries, 'native'), { kind: 'reserved', name: 'settings', rest: '' })
  assert.deepEqual(route('/btw what now?', entries, 'native'), { kind: 'reserved', name: 'btw', rest: 'what now?' })
  assert.deepEqual(route('/flow swe fix the bug', entries, 'native'), { kind: 'flow', name: 'swe', rest: 'fix the bug' })
  // `/flow` always names a flow, even one that is also a skill.
  assert.deepEqual(route('/flow ralph go', entries, 'native'), { kind: 'flow', name: 'ralph', rest: 'go' })
  assert.deepEqual(route('$swe fix it', entries, 'native'), { kind: 'flow', name: 'swe', rest: 'fix it' })
  // Both: the preference decides.
  assert.equal(route('$ralph go', entries, 'native').kind, 'say')
  assert.deepEqual(route('$ralph go', entries, 'flow'), { kind: 'flow', name: 'ralph', rest: 'go' })
  for (const line of ['$lint', '$nothing here', '/model', '/nope', '!ls', '@src/a.py', 'hello']) assert.equal(route(line, entries, 'native').kind, 'say', line)
})

test('the preference says where it comes from', () => {
  assert.equal(preferSaid('native', 'settings'), '$ prefers native · from the settings')
  assert.equal(preferSaid('flow', 'chat'), '$ prefers flows · set for this chat')
})

test('a `!` command is read off its record and drawn as a shell draws it', () => {
  assert.equal(shellOf({ type: 'said', text: 'x' }), null)
  const ran = shellOf({ type: 'shell', command: 'ls -1', out: 'a\nb\n', err: '', status: 0 })
  assert.deepEqual(ran, { command: 'ls -1', out: 'a\nb\n', err: '', status: 0 })
  assert.deepEqual(shellParts(ran), [
    { part: 'input', text: '$ ls -1' },
    { part: 'stdout', text: 'a\nb' },
  ])
  // Only the host's own `shell` record is one (Section 4.9.2.4 of daemon.md).
  assert.equal(shellOf({ type: 'event', kind: 'shell', command: 'ls' }), null)
  const failed = shellOf({ type: 'shell', command: '!false', out: '', err: 'no\n', status: 1 })
  assert.deepEqual(shellParts(failed), [
    { part: 'input', text: '$ false' },
    { part: 'stderr', text: 'no' },
    { part: 'status', text: 'exit 1' },
  ])
})

test('a refused line is said with why', () => {
  assert.equal(refusedSaid({ text: '/config', because: 'only its own interface serves it' }), '/config -- refused: only its own interface serves it')
  assert.equal(refusedSaid({ text: '/x' }), '/x -- refused')
})
