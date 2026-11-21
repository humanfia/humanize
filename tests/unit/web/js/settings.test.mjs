import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import { fallbacks } from '../../../../src/hmz/web/static/views/settings/runtimes-model.js'

test('General is said to hold what it holds: the display and reporting, and neither Ai-chan nor side questions', () => {
  const view = readFileSync(new URL('../../../../src/hmz/web/static/views/settings.js', import.meta.url), 'utf8')
  const about = /^\s*general: \{.*?about: (?:t\()?'([^']*)'/m.exec(view)?.[1]
  assert.equal(about, 'Display and reporting')
})

test('Usage is two pages, one drawing: the daemon’s under Daemon and a folder’s under Workspace', () => {
  const view = readFileSync(new URL('../../../../src/hmz/web/static/views/settings.js', import.meta.url), 'utf8')
  const pages = [...view.matchAll(/^\s*'?([\w-]+)'?: \{ group: '(\w+)', label: t\('Usage'\).*?import\('([^']+)'\)/gm)].map((found) => found.slice(1))
  assert.deepEqual(pages, [
    ['usage', 'daemon', './settings/usage.js'],
    ['workspace-usage', 'workspace', './settings/usage.js'],
  ])
})

test('a runtime falls back to any other, each offered as the `<backend>:<name>` the daemon takes', () => {
  const runtimes = [
    { backend: 'ssh', name: 'gpu' },
    { backend: 'ssh', name: 'spare' },
    { backend: 'docker', name: 'gpu' },
  ]
  // Another backend's is offered, one of the same name there too; itself never.
  assert.deepEqual(fallbacks(runtimes, 'ssh', 'gpu'), ['ssh:spare', 'docker:gpu'])
  // One not yet named is none of those saved.
  assert.deepEqual(fallbacks(runtimes, 'ssh', ''), ['ssh:gpu', 'ssh:spare', 'docker:gpu'])
  assert.deepEqual(fallbacks([], 'ssh', 'gpu'), [])
})
