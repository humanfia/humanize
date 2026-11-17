import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  HEIGHTS,
  askOf,
  cached,
  errorsOf,
  hashOf,
  heightOf,
  jsonOf,
  outcome,
  overflow,
  rootRule,
  sessionOf,
  titleOf,
  tokenFor,
  tokensOf,
} from '../../../../src/hmz/web/static/faces/logic.js'

test('a face is named by its hash, as the wire says it or as a host does', () => {
  assert.equal(hashOf({ face: { hash: 'ab12', title: 'Review' } }), 'ab12')
  assert.equal(hashOf({ face: 'ab12' }), 'ab12')
  assert.equal(hashOf({ face: null }), '')
  assert.equal(hashOf({}), '')
  assert.equal(titleOf({ face: { hash: 'ab12', title: 'Review' } }), 'Review')
  assert.equal(titleOf({ face: 'ab12' }), '')
})

test('a question is asked in its session, or in one of its own where it names none', () => {
  assert.equal(sessionOf({ session: 'reviewer/1', key: 'q1' }), 'reviewer/1')
  assert.equal(sessionOf({ role: 'reviewer', key: 'q1' }), 'reviewer/q1')
})

test('a face is told the prompt, the context, the schema and what was refused', () => {
  const schema = { type: 'object', properties: { ok: { type: 'boolean' } } }
  assert.deepEqual(askOf({ text: 'Merge?', context: [{ kind: 'markdown', text: 'x' }], schema, options: ['a'] }), {
    prompt: 'Merge?',
    context: [{ kind: 'markdown', text: 'x' }],
    schema,
    errors: [],
  })
  assert.deepEqual(askOf({ prompt: 'Name?', errors: [{ path: ['name'], message: 'Required.' }] }), {
    prompt: 'Name?',
    context: [],
    schema: null,
    errors: [{ path: ['name'], message: 'Required.' }],
  })
})

test('a submission taken is ok, and one refused says where and why', async () => {
  assert.deepEqual(await outcome(async () => undefined, { a: 1 }), { ok: true })
  assert.deepEqual(await outcome(async () => ({}), 1), { ok: true })
  assert.deepEqual(await outcome(async () => ({ ok: false, errors: [{ path: ['a'], message: 'No.' }] }), 1), {
    ok: false,
    errors: [{ path: ['a'], message: 'No.' }],
  })
  // A JSON-RPC refusal, as RpcError carries it, and as api.js's Refused does.
  const rpc = Object.assign(new Error('the answer does not fit: no'), { code: 400, data: { errors: [{ path: ['notes', 0], message: 'Too short.' }] } })
  assert.deepEqual(await outcome(async () => Promise.reject(rpc), 1), { ok: false, errors: [{ path: ['notes', 0], message: 'Too short.' }] })
  const refused = Object.assign(new Error('the answer does not fit: no'), { said: { errors: [{ path: [], message: 'No.' }] } })
  assert.deepEqual(await outcome(async () => Promise.reject(refused), 1), { ok: false, errors: [{ path: [], message: 'No.' }] })
  // Any other failure is said as the one error it is.
  assert.deepEqual(await outcome(() => Promise.reject(new Error('The question went away.')), 1), {
    ok: false,
    errors: [{ path: [], message: 'The question went away.' }],
  })
})

test('errors are each a path and a message, whatever came', () => {
  assert.deepEqual(errorsOf([{ path: ['a', 1, {}], message: 'x' }, null, 'y']), [{ path: ['a', 1], message: 'x' }])
  assert.deepEqual(errorsOf(undefined, 'Refused.'), [{ path: [], message: 'Refused.' }])
})

test('a value is sent as the JSON it is', () => {
  assert.deepEqual(jsonOf({ a: [1, 'b'], skipped: undefined }), { a: [1, 'b'] })
  const loop = {}
  loop.loop = loop
  assert.equal(jsonOf(loop), undefined)
  assert.equal(jsonOf(undefined), undefined)
})

test('a frame is never drawn shorter or taller than it may be', () => {
  assert.equal(heightOf(300.4), 300)
  assert.equal(heightOf(1), HEIGHTS.least)
  assert.equal(heightOf(1e9), HEIGHTS.most)
  assert.equal(heightOf('nope'), HEIGHTS.first)
  assert.equal(heightOf(), HEIGHTS.first)
})

test('only tokens that are plain values reach a face, set on its root', () => {
  const tokens = tokensOf({ '--paper': ' #fff ', '--sans': "Inter, 'Segoe UI'", '--evil': 'red;} body{display:none', '--x': '</style>', color: 'red', '--scheme': 'dark' })
  assert.deepEqual(tokens, { '--paper': '#fff', '--sans': "Inter, 'Segoe UI'", '--scheme': 'dark' })
  assert.equal(rootRule(tokens), ":root{--paper:#fff;--sans:Inter, 'Segoe UI';--scheme:dark;color-scheme:dark;}")
})

test('each mount is handed a token of its own', () => {
  const one = tokenFor()
  assert.match(one, /^[0-9a-f]{32}$/)
  assert.notEqual(one, tokenFor())
})

test('a face is fetched once per hash, and again after a fetch that failed', async () => {
  const fetched = cached()
  let asked = 0
  const fetchFace = async (hash) => {
    asked += 1
    return { html: `<p>${hash}</p>`, title: 'T' }
  }
  const [a, b] = await Promise.all([fetched('h1', fetchFace), fetched('h1', fetchFace)])
  assert.deepEqual(a, { html: '<p>h1</p>', title: 'T' })
  assert.equal(a, b)
  assert.equal(asked, 1)

  let fail = true
  const flaky = async () => {
    if (fail) throw new Error('no face h2')
    return { html: '<p>ok</p>' }
  }
  await assert.rejects(fetched('h2', flaky), /no face h2/)
  await new Promise((resolve) => setTimeout(resolve))
  fail = false
  assert.deepEqual(await fetched('h2', flaky), { html: '<p>ok</p>', title: '' })
  await assert.rejects(fetched('h3', async () => ({ html: '  ' })), /is empty/)
})

test('the sessions used longest ago are let go of first', () => {
  assert.deepEqual(overflow(['a', 'b', 'c'], 2), ['a'])
  assert.deepEqual(overflow(['a'], 2), [])
})
