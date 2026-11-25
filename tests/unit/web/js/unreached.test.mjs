import assert from 'node:assert/strict'
import { test } from 'node:test'

const root = { lang: '', dataset: {} }
globalThis.document = { documentElement: root }

const { called, nextStep, unreached } = await import('../../../../src/hmz/web/static/unreached.js')

/** Does something with the page written in a language, then puts it back in English. */
function written(language, act) {
  root.lang = language
  try {
    return act()
  } finally {
    root.lang = ''
  }
}

test('Local is called Local, and any other daemon by its name', () => {
  assert.equal(called('local'), 'Local')
  assert.equal(called('lab'), 'lab')
  assert.equal(written('zh-Hans', () => called('local')), '本地')
})

test('a daemon out of reach says which, how it stands and why, in one sentence', () => {
  assert.equal(unreached('local', 'failed', 'unix: closed.'), 'Local is unavailable, failed: unix: closed.')
  assert.equal(unreached('lab', 'connecting', 'no route'), 'lab is unavailable, connecting: no route')
  assert.equal(unreached('lab', 'failed', ''), 'lab is unavailable, failed.')
  // What the daemon said stays as it said it: the page's own words are translated.
  assert.match(written('zh-Hans', () => unreached('lab', 'failed', 'no route')), /^lab 不可用，.+：no route$/)
})

test('what to do next follows from where the daemon is reached from', () => {
  assert.match(nextStep('local'), /hmz web is still running.*Connect.*start it again/)
  assert.match(nextStep('local', { desktop: true }), /hmz is installed where your login shell finds it/)
  assert.match(nextStep('box', { kind: 'SSH' }), /ssh reaches its host/)
  assert.match(nextStep('far', { kind: 'EasyTier' }), /same network secret/)
  assert.match(nextStep('pal', { kind: 'WebRTC' }), /machine is on/)
  for (const said of [nextStep('local'), nextStep('box', { kind: 'SSH' })]) assert.match(said, /\.$/)
  assert.match(written('zh-Hant', () => nextStep('pal')), /常駐程式/)
})
