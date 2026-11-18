import assert from 'node:assert/strict'
import { test } from 'node:test'

import { batched, concrete, freshId, graphSaid, held, named, ordered, removed, renamed, withEffort, written } from '../../../../src/hmz/web/static/nous.js'

/** A graph as `nous.list` answers it: a balance node, failing over by fault class. */
const GRAPH = {
  start: 'pick',
  nodes: [
    { id: 'last', use: 'claude/claude-haiku-4-5', balance: '', among: [], spread: 0, on: {} },
    { id: 'pick', use: '', balance: 'shuffle', among: [{ nous: 'claude@work/claude-opus-5:high', weight: 2 }, { nous: 'fast', weight: 1 }], spread: 1, on: { '*': 'last', rate_limit: 'wait' } },
    { id: 'wait', use: 'codex/gpt-5', balance: '', among: [], spread: 0, on: { '*': 'last' } },
  ],
}

test('a concrete nous has a slash and an effort put on it, a virtual one is a name', () => {
  assert.ok(concrete('claude@work/claude-opus-5:high') && !concrete('fast'))
  assert.equal(withEffort('claude/claude-opus-5', 'high'), 'claude/claude-opus-5:high')
  assert.equal(withEffort('claude/claude-opus-5', ''), 'claude/claude-opus-5')
  assert.equal(withEffort('claude/claude-opus-5', 'auto'), 'claude/claude-opus-5')
  assert.equal(withEffort('opencode/ollama/qwen3:latest:auto', 'high'), 'opencode/ollama/qwen3:latest:high')
  assert.equal(withEffort('opencode/ollama/qwen3:latest:auto', ''), 'opencode/ollama/qwen3:latest:auto')
})

test('a graph is said from its start along its edges, each node once', () => {
  assert.deepEqual(ordered(GRAPH).map((one) => one.id), ['pick', 'last', 'wait'])
  assert.deepEqual(graphSaid(GRAPH), [
    { id: 'pick', start: true, text: 'shuffle: claude@work/claude-opus-5:high ×2, fast, 1 at most', edges: 'rate_limit → wait, * → last' },
    { id: 'last', start: false, text: 'claude/claude-haiku-4-5', edges: '' },
    { id: 'wait', start: false, text: 'codex/gpt-5', edges: '* → last' },
  ])
  assert.deepEqual(ordered(null), [])
})

test('a graph held by the form is written back as it was read', () => {
  const form = held(GRAPH)
  assert.equal(form.nodes[1].kind, 'balance')
  assert.deepEqual(written(form), {
    start: 'pick',
    nodes: [
      { id: 'last', use: 'claude/claude-haiku-4-5', on: {} },
      { id: 'pick', balance: 'shuffle', among: [{ nous: 'claude@work/claude-opus-5:high', weight: 2 }, { nous: 'fast', weight: 1 }], spread: 1, on: { '*': 'last', rate_limit: 'wait' } },
      { id: 'wait', use: 'codex/gpt-5', on: { '*': 'last' } },
    ],
  })
  assert.equal(written(held(null)), null)
})

test('half-written rows are left out, and a node renamed or removed takes its edges along', () => {
  const form = held(GRAPH)
  form.nodes[1].among.push({ nous: ' ', weight: 3 })
  form.nodes[0].on.push({ fault: '*', to: '' })
  assert.equal(written(form).nodes[1].among.length, 2)
  assert.deepEqual(written(form).nodes[0].on, {})
  renamed(form, 'pick', 'first')
  assert.equal(form.start, 'first')
  renamed(form, 'last', 'end')
  assert.deepEqual(form.nodes.find((one) => one.id === 'wait').on, [{ fault: '*', to: 'end' }])
  removed(form, 'first')
  assert.equal(form.start, 'end')
  removed(form, 'end')
  assert.deepEqual(form.nodes.find((one) => one.id === 'wait').on, [])
  assert.equal(freshId(form), 'n2')
  assert.equal(freshId({ nodes: [{ id: 'n2' }] }), 'n3')
})

test('every nous is written after the virtual nous it names', () => {
  const nous = [
    { name: 'claude/x', virtual: false, tries: 1, policy: 'fixed', timeout: 0, graph: null, then: { start: 'a', nodes: [{ id: 'a', use: 'careful', on: {} }] } },
    { name: 'careful', virtual: true, tries: 0, policy: 'fixed', timeout: 0, graph: GRAPH, then: null },
    { name: 'fast', virtual: true, tries: 0, policy: 'fixed', timeout: 30, graph: { start: 'a', nodes: [{ id: 'a', use: 'codex/gpt-5', on: {} }] }, then: null },
  ]
  assert.deepEqual([...named(nous[1])], ['fast'])
  const calls = batched(nous)
  assert.deepEqual(calls.map(([method, params]) => [method, params.name]), [['nous.set', 'fast'], ['nous.set', 'careful'], ['nous.set', 'claude/x']])
  assert.deepEqual(calls[0][1], { name: 'fast', tries: 0, policy: 'fixed', timeout: 30, graph: nous[2].graph, then: null })
  // Nous naming each other round go as they are, and are refused where they go.
  const round = [
    { name: 'a', graph: { start: 'n', nodes: [{ id: 'n', use: 'b' }] }, then: null },
    { name: 'b', graph: { start: 'n', nodes: [{ id: 'n', use: 'a' }] }, then: null },
  ]
  assert.deepEqual(batched(round).map(([, params]) => params.name), ['a', 'b'])
})
