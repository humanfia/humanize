import assert from 'node:assert/strict'
import { test } from 'node:test'

import { ADDS, PANES, added, dismissing, nextSteps, paneOf, standing, stepKey, toggled, usageSaid } from '../../../../src/hmz/web/static/desk.js'

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
  assert.deepEqual(nextSteps(runs, chat, mark, [], 1).map((one) => one.name), ['a'])
  assert.deepEqual(nextSteps(null, chat, mark), [])
})

test('what is dismissed is kept once, the latest last, and no more than asked', () => {
  assert.deepEqual(dismissing(['a', 'b'], 'a'), ['b', 'a'])
  assert.deepEqual(dismissing(['a', 'b'], 'c', 2), ['b', 'c'])
})

test('the usage chip says what was spent where priced, else the tokens, else nothing', () => {
  assert.equal(usageSaid({ tally: ['12.4k tokens · 3 turns', '$0.42 · 80 tok/s'] }, null), '$0.42')
  assert.equal(usageSaid({ tally: ['12.4k tokens · 3 turns', '80 tok/s'] }, null), '12.4k tokens')
  assert.equal(usageSaid({ tally: [] }, { money: '$1.20', tokens: '9k' }), '$1.20')
  assert.equal(usageSaid(null, { money: '', tokens: '9k' }), '9k tokens')
  assert.equal(usageSaid(null, { money: '$0.00', tokens: '0' }), '')
  assert.equal(usageSaid(null, null), '')
})

test('how a chat stands is said only while it answers, waits or has failed', () => {
  assert.equal(standing('running', 'Haiku 4.5'), 'Haiku 4.5 is responding')
  assert.equal(standing('running'), 'The assistant is responding')
  assert.equal(standing('asking'), 'Waiting for you')
  assert.equal(standing('crashed'), 'The chat failed')
  assert.equal(standing('stopped'), '')
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
