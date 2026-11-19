import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  clampWidth,
  defaultTab,
  factsOf,
  flatten,
  menuKey,
  nameOf,
  offOf,
  panelsOf,
  paramsOf,
  pick,
  tabOf,
  treeOf,
  usable,
  usedLine,
} from '../../../../src/hmz/web/static/views/envs/tree.js'

const env = (id, more = {}) => ({ id, role: 'coder', chain: id.split(':')[1], parent: null, run: 1, backend: 'local', provider: '', workdir: '/w', available: true, open: true, caps: [], declared: [], facts: {}, ...more })

test('an environment has the panels its real capabilities give, in their order', () => {
  assert.deepEqual(panelsOf(env('1:a', { caps: ['git', 'files', 'shell', 'bash'] })).map((one) => one.key), ['files', 'terminal', 'changes'])
  assert.deepEqual(panelsOf(env('1:a', { caps: ['files', 'git_worktree'] })).map((one) => one.key), ['files', 'changes'])
  assert.deepEqual(panelsOf(env('1:a', { caps: ['rewind', 'scratch'] })), [])
  assert.deepEqual(panelsOf(null), [])
})

test('it opens on the first panel the flow declared, else Files', () => {
  assert.equal(defaultTab(env('1:a', { caps: ['files', 'shell', 'git'], declared: ['git'] })), 'changes')
  assert.equal(defaultTab(env('1:a', { caps: ['files', 'shell', 'git'], declared: ['git_worktree', 'shell'] })), 'terminal')
  assert.equal(defaultTab(env('1:a', { caps: ['files', 'shell', 'git'], declared: ['bash'] })), 'files')
  // Declared, but not really there: not a panel to open on.
  assert.equal(defaultTab(env('1:a', { caps: ['files'], declared: ['git'] })), 'files')
  assert.equal(defaultTab(env('1:a', { caps: ['shell'], declared: [] })), 'terminal')
  assert.equal(defaultTab(env('1:a', { caps: [] })), '')
})

test('a panel asked for is opened where the environment has it', () => {
  const one = env('1:a', { caps: ['files', 'shell'], declared: ['shell'] })
  assert.equal(tabOf(one, 'files'), 'files')
  assert.equal(tabOf(one, 'changes'), 'terminal')
  assert.equal(tabOf(one, ''), 'terminal')
})

test('the tree groups by role and puts each derived environment under its parent', () => {
  const envs = [
    env('1:coder', { role: 'coder' }),
    env('1:reviewer', { role: 'reviewer' }),
    env('1:coder/wt', { role: 'coder', parent: '1:coder' }),
    env('1:coder/wt/scratch', { role: 'tester', parent: '1:coder/wt' }),
    env('1:orphan', { role: 'reviewer', parent: '9:gone' }),
  ]
  const groups = treeOf(envs)
  assert.deepEqual(groups.map((one) => one.role), ['coder', 'reviewer'])
  assert.deepEqual(flatten(groups).map(({ env: one, depth }) => [one.id, depth]), [
    ['1:coder', 0],
    ['1:coder/wt', 1],
    ['1:coder/wt/scratch', 2],
    ['1:reviewer', 0],
    ['1:orphan', 0],
  ])
})

test('a loop of parents is still drawn, once each', () => {
  const groups = treeOf([env('1:a', { parent: '1:b' }), env('1:b', { parent: '1:a' }), env('1:c', { parent: '1:c' })])
  assert.deepEqual(flatten(groups).map(({ env: one }) => one.id).sort(), ['1:a', '1:b', '1:c'])
  assert.deepEqual(treeOf(undefined), [])
})

test('the environment shown is the one asked for, else the first usable one of the latest run', () => {
  const envs = [env('1:old', { run: 1 }), env('2:closed', { run: 2, open: false }), env('2:wt', { run: 2, parent: '2:new' }), env('2:new', { run: 2 })]
  assert.equal(pick(envs, '1:old').id, '1:old')
  assert.equal(pick(envs, 'nope').id, '2:new')
  assert.equal(pick(envs, '').id, '2:new')
  assert.equal(pick([env('1:x', { available: false })], '').id, '1:x')
  assert.equal(pick([], 'x'), null)
  assert.ok(usable(env('1:a')))
  assert.ok(!usable(env('1:a', { open: false })))
  assert.ok(!usable(env('1:a', { available: false })))
})

test('an environment, what it runs on, and what was done in it are said in words', () => {
  assert.equal(nameOf(env('1:coder/wt')), 'coder/wt')
  assert.equal(nameOf(env('1:x', { chain: '', role: 'r' })), 'r')
  assert.deepEqual(factsOf(env('1:a', { facts: { cpu: 8, memory: 16 * 1024 ** 3, gpu_count: 2, gpu_memory: 80 * 1024 ** 3 } })), ['8 CPUs', '16 GiB memory', '2 GPUs · 80 GiB'])
  assert.deepEqual(factsOf(env('1:a', { facts: { cpu: 1, memory: '512M', gpu_count: 0 } })), ['1 CPU', '512M memory'])
  assert.deepEqual(factsOf(env('1:a', { facts: null })), [])
  const envs = [env('1:coder', { role: 'coder' })]
  assert.equal(usedLine({ type: 'env_used', env: '1:coder', by: 'web', what: 'wrote', path: 'src/a.py' }, envs), 'web wrote src/a.py in coder')
  assert.equal(usedLine({ type: 'env_used', env: '1:gone', by: 'tui', what: 'opened a terminal' }, envs), 'tui opened a terminal in 1:gone')
})

test('a call names the environment, but for a terminal’s own methods', () => {
  assert.deepEqual(paramsOf('env.list', { path: '.' }, '1:a'), { path: '.', env: '1:a' })
  assert.deepEqual(paramsOf('env.term.open', { cols: 80, rows: 24 }, '1:a'), { cols: 80, rows: 24, env: '1:a' })
  assert.deepEqual(paramsOf('env.term.list', {}, '1:a'), { env: '1:a' })
  for (const method of ['env.term.input', 'env.term.resize', 'env.term.ack', 'env.term.close']) assert.deepEqual(paramsOf(method, { term: 't', env: 'x' }, '1:a'), { term: 't' })
})

test('a list is never dragged narrower than it can be read, nor wider than it may be', () => {
  assert.equal(clampWidth(40, 500), 160)
  assert.equal(clampWidth(300, 500), 300)
  assert.equal(clampWidth(900, 500), 500)
  assert.equal(clampWidth(Infinity, 401.6), 402)
  // Where there is no room for the least, the least is asked for all the same.
  assert.equal(clampWidth(200, 0), 160)
  assert.equal(clampWidth(200, -395), 160)
  assert.equal(clampWidth(100, Infinity), 160)
  // A list read at more than that is asked for no narrower.
  assert.equal(clampWidth(100, 400, 200), 200)
  assert.equal(clampWidth(900, 100, 200), 200)
})

test('an environment that has closed is said closed, as the host tells it: out of reach too', () => {
  // The host tells a closed environment as neither open nor reachable.
  assert.equal(offOf(env('1:a', { available: false, open: false })), 'closed')
  assert.equal(offOf(env('1:a', { open: false })), 'closed')
  assert.equal(offOf(env('1:a', { available: false })), 'unavailable')
  assert.equal(offOf(env('1:a')), '')
})

test('the menu of what the keys are on is asked for by the menu key, or Shift+F10', () => {
  assert.equal(menuKey({ key: 'ContextMenu', shiftKey: false }), true)
  assert.equal(menuKey({ key: 'F10', shiftKey: true }), true)
  assert.equal(menuKey({ key: 'F10', shiftKey: false }), false)
  assert.equal(menuKey({ key: 'Enter', shiftKey: true }), false)
})
