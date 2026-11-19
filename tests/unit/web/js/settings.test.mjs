import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

test('General is said to hold what it holds: the display, Ai-chan and reporting, and no side questions', () => {
  const view = readFileSync(new URL('../../../../src/hmz/web/static/views/settings.js', import.meta.url), 'utf8')
  const about = /^\s*general: \{.*?about: '([^']*)'/m.exec(view)?.[1]
  assert.equal(about, 'Display, Ai-chan and reporting')
})
