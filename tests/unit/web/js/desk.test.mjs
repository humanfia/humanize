import assert from 'node:assert/strict'
import { test } from 'node:test'

import { ADDS, NO_FOLDER, PANES, added, addsOf, chipNamed, dismissing, nextSteps, paneOf, paneSaid, standing, stepKey, stoppable, thousands, toggled, unmoved, usageRows, usedLately } from '../../../../src/hmz/web/static/desk.js'

test('the Add menu offers the four prefixes a line starts with, each a short label', () => {
  assert.deepEqual(ADDS.map((one) => one.sigil), ['@', '/', '$', '!'])
  assert.deepEqual(ADDS.map((one) => one.label), ['Add files', 'Slash commands', 'Skills and flows', 'Run a shell command'])
  for (const one of ADDS) assert.ok(one.label.split(' ').length <= 4 && !/[.?!…]$/.test(one.label))
})

test('@ goes in where the caret is, as a word of its own', () => {
  assert.deepEqual(added('', 0, '@'), { text: '@', caret: 1 })
  assert.deepEqual(added('look at', 7, '@'), { text: 'look at @', caret: 9 })
  assert.deepEqual(added('look at ', 8, '@'), { text: 'look at @', caret: 9 })
  assert.deepEqual(added('ab', 1, '@'), { text: 'a @b', caret: 3 })
  assert.deepEqual(added('ab', 99, '@'), { text: 'ab @', caret: 4 })
})

test('/, $ and ! go at the start of the line, and not twice', () => {
  assert.deepEqual(added('', 0, '/'), { text: '/', caret: 1 })
  assert.deepEqual(added('ls -la', 6, '!'), { text: '!ls -la', caret: 1 })
  assert.deepEqual(added('  ralph', 3, '$'), { text: '  $ralph', caret: 3 })
  assert.deepEqual(added('/model', 6, '/'), { text: '/model', caret: 1 })
})

test('the chats waiting on their person are those marked asking and not dismissed', () => {
  const runs = [
    { name: 'a', kind: 'chat', how: 'asking', asking: ['1:q1'] },
    { name: 'b', kind: 'chat', how: 'running' },
    { name: 'c', kind: 'flow', how: 'asking', asking: ['1:q2'] },
    { name: 'd', kind: 'chat', how: 'asking', asking: ['1:q3'] },
  ]
  const chat = (run) => run.kind === 'chat'
  const mark = (run) => run.how
  assert.deepEqual(nextSteps(runs, chat, mark).map((one) => one.name), ['a', 'd'])
  assert.deepEqual(nextSteps(runs, chat, mark, [stepKey(runs[0])]).map((one) => one.name), ['d'])
  // Dismissed, it is listed again once it asks something else.
  assert.deepEqual(nextSteps([{ ...runs[0], asking: ['2:q9'] }], chat, mark, [stepKey(runs[0])]).map((one) => one.name), ['a'])
  assert.deepEqual(nextSteps(null, chat, mark), [])
  // Every one that waits is listed, however many.
  const many = Array.from({ length: 40 }, (_, at) => ({ name: `n${at}`, kind: 'chat', how: 'asking', asking: [`1:q${at}`] }))
  assert.equal(nextSteps(many, chat, mark).length, 40)
})

test('a chat dismissed stays dismissed once it has folded away and lists nothing', () => {
  const chat = () => true
  const mark = () => 'asking'
  const going = { name: 'a', asking: ['1:q1'] }
  const folded = { name: 'a', asking: [] }
  // What this browser holds the chat owing, once its row lists none.
  const waits = () => ['1:q1']
  const dismissed = [stepKey(going, waits(going))]
  assert.equal(stepKey(folded, waits(folded)), stepKey(going))
  assert.deepEqual(nextSteps([folded], chat, mark, dismissed, waits), [])
  // Asking something else, it is listed again, going or folded away.
  assert.equal(nextSteps([{ name: 'a', asking: ['2:q2'] }], chat, mark, dismissed, waits).length, 1)
  assert.equal(nextSteps([folded], chat, mark, dismissed, () => ['2:q2']).length, 1)
})

test('before a chat there is, Add offers the files alone', () => {
  assert.deepEqual(addsOf(true), ADDS)
  assert.deepEqual(addsOf(['files']).map((one) => one.sigil), ['@'])
  assert.ok(NO_FOLDER.split(' ').length <= 4 && !/[.?!…]$/.test(NO_FOLDER))
})

test('a chip is called by what it picks and what is picked', () => {
  assert.equal(chipNamed('Environment', 'Local'), 'Environment: Local')
  assert.equal(chipNamed('Usage', '$0.42'), 'Usage: $0.42')
  assert.equal(chipNamed('Folder', 'No folder'), 'Folder: No folder')
  assert.equal(chipNamed('Nous', 'Claude Code Haiku 4.5 High'), 'Nous: Claude Code Haiku 4.5 High')
  assert.equal(chipNamed('Permissions', 'Edit this folder'), 'Permissions: Edit this folder')
  assert.equal(chipNamed('Usage', ''), 'Usage')
})

test('a pane that cannot be opened says its environment keeps none, and never that the chat is not going', () => {
  assert.equal(paneSaid('terminal', true), 'Terminal')
  assert.equal(paneSaid('terminal', false), 'No terminal in this environment')
  assert.equal(paneSaid('changes', false), 'No changes in this environment')
  assert.equal(paneSaid('files', false), 'No files in this environment')
  assert.equal(paneSaid('nothing', false), '')
})

test('what is dismissed is kept once, the latest last, and no more than asked', () => {
  assert.deepEqual(dismissing(['a', 'b'], 'a'), ['b', 'a'])
  assert.deepEqual(dismissing(['a', 'b'], 'c', 2), ['b', 'c'])
})

test('a count of tokens is cut short as the runs figures cut one', () => {
  assert.deepEqual([0, 999.4, 1000, 12345, 1e6, 2345678].map(thousands), ['0', '999', '1.0k', '12.3k', '1.00M', '2.35M'])
})

test('a chat going says what it spent, its tokens, its time and each kind with its share', () => {
  const reckoning = [
    { kind: 'input', tokens: 12000, whole: true },
    { kind: 'output', tokens: 3000, whole: true },
    { kind: 'cache_read', tokens: 85000, whole: true },
  ]
  const rows = usageRows({ tally: ['input 12.0k · output 3.0k · cache_read 85.0k', '$0.42 · 80 out/s'], lasting: '3m 12s', reckoning }, null)
  assert.deepEqual(rows.slice(0, 3), [
    { label: 'Spent', value: '$0.42' },
    { label: 'Tokens', value: '100.0k' },
    { label: 'Time', value: '3m 12s' },
  ])
  assert.deepEqual(rows.slice(3).map((one) => [one.label, one.value]), [['Input', '12.0k'], ['Output', '3.0k'], ['Cache read', '85.0k']])
  assert.deepEqual(rows.slice(3).map((one) => one.share), [0.12, 0.03, 0.85])
  assert.equal(rows.slice(0, 3).some((one) => 'share' in one), false)
})

test('a chat going nobody prices says no money, and a floor stays marked', () => {
  const reckoning = [
    { kind: 'input', tokens: 20, whole: false },
    { kind: 'output', tokens: 14, whole: true },
  ]
  const rows = usageRows({ tally: ['input 20+ · output 14', '3 out/s'], lasting: '41s', reckoning }, { money: '$9.00' })
  assert.deepEqual(rows.map((one) => one.value), ['—', '34+', '41s', '20+', '14'])
  // Counted in a lump, of no kind: the tokens as the tally says them, and no bars.
  assert.deepEqual(usageRows({ tally: ['12.4k tokens', '$0.10+ · 9 out/s'], lasting: '2s', reckoning: [] }, null), [
    { label: 'Spent', value: '$0.10+' },
    { label: 'Tokens', value: '12.4k' },
    { label: 'Time', value: '2s' },
  ])
})

test('a chat folded away says what was written down, and one that spent nothing says nothing', () => {
  assert.deepEqual(usageRows(null, { money: '$1.20', tokens: '9.0k', worked: '2m 3s' }), [
    { label: 'Spent', value: '$1.20' },
    { label: 'Output tokens', value: '9.0k' },
    { label: 'Time working', value: '2m 3s' },
  ])
  assert.deepEqual(usageRows({ tally: [] }, { money: '', tokens: '28', worked: '' }).map((one) => one.value), ['—', '28', '—'])
  assert.deepEqual(usageRows(null, { money: '$0.00', tokens: '0', worked: '0s' }), [])
  assert.deepEqual(usageRows({ tally: [] }, null), [])
  assert.deepEqual(usageRows(null, null), [])
})

test('what a workspace used lately is today, the last day read, and the whole of the 7', () => {
  const data = {
    days: [{ money: '$3.00', tokens: '40.0k' }, { money: '$1.20', tokens: '9.0k' }],
    whole: { runs: 14, money: '$8.40', tokens: '120.4k' },
  }
  assert.deepEqual(usedLately(data), [
    { label: 'Today (UTC)', value: '$1.20', about: '9.0k output tokens' },
    { label: 'Last 7 days', value: '$8.40', about: '120.4k output tokens', sub: 'Over 14 chats and epics' },
  ])
  assert.equal(usedLately({ days: [], whole: { runs: 1, money: '$0.10', tokens: '5' } })[1].sub, 'Over 1 chat or epic')
  assert.deepEqual(usedLately({ days: [], whole: { runs: 0 } }), [
    { label: 'Today (UTC)', value: '$0.00', about: '0 output tokens' },
    { label: 'Last 7 days', value: '$0.00', about: '0 output tokens', sub: 'No chats or epics yet' },
  ])
})

test('nothing is said of how a chat stands but that it failed', () => {
  // Neither who is answering nor that it waits on its person.
  assert.equal(standing('running'), '')
  assert.equal(standing('asking'), '')
  assert.equal(standing('stopped'), '')
  for (const failed of ['failed', 'refused', 'crashed']) assert.equal(standing(failed), 'The chat failed')
})

test('the panes of a chat are its details and the three panels of its environment', () => {
  assert.deepEqual(PANES.map((one) => one.label), ['Details', 'Terminal', 'Changes', 'Files'])
  assert.equal(paneOf({ open: false, tab: 'epic', env: 'files' }), '')
  assert.equal(paneOf({ open: true, tab: 'epic', env: 'files' }), 'details')
  assert.equal(paneOf({ open: true, tab: 'env', env: 'terminal' }), 'terminal')
  // What no button of the bar is of: the side questions.
  assert.equal(paneOf({ open: true, tab: 'aside', env: 'files' }), '')
})

test('a pane’s button opens it, moves the panel to it, or shuts the panel where it is open', () => {
  const shut = { open: false, tab: 'epic', env: 'files' }
  assert.deepEqual(toggled(shut, 'details'), { open: true, tab: 'epic', env: 'files' })
  assert.deepEqual(toggled(shut, 'changes'), { open: true, tab: 'env', env: 'changes' })
  assert.deepEqual(toggled({ open: true, tab: 'env', env: 'changes' }, 'changes'), { open: false, tab: 'env', env: 'changes' })
  assert.deepEqual(toggled({ open: true, tab: 'env', env: 'changes' }, 'files'), { open: true, tab: 'env', env: 'files' })
  assert.deepEqual(toggled({ open: true, tab: 'aside', env: 'files' }, 'details'), { open: true, tab: 'epic', env: 'files' })
  assert.deepEqual(toggled(shut, 'nothing'), shut)
})

test('a box takes the focus once its form is read only where the focus was not moved since', () => {
  const [body, view, link, chip] = [{}, {}, {}, {}]
  const loose = [body, view]
  // Still on what held it as the reading began: the link that opened the form, or nothing.
  assert.equal(unmoved(link, link, loose), true)
  assert.equal(unmoved(body, body, loose), true)
  // Gone with what held it -- a choice of a menu since closed -- or left on the view as a whole.
  assert.equal(unmoved(link, body, loose), true)
  assert.equal(unmoved(link, view, loose), true)
  assert.equal(unmoved(link, null, loose), true)
  // Moved to something else since, by a key, the pointer or a dialog closing: it stays there.
  assert.equal(unmoved(link, chip, loose), false)
  assert.equal(unmoved(body, chip, loose), false)
})

test('the button of a chat box stops only while its host says a turn is open', () => {
  assert.equal(stoppable('running'), true)
  assert.equal(stoppable('done'), false)
  assert.equal(stoppable(''), false)
  assert.equal(stoppable(), false)
})
