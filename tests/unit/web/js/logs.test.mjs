// What the page keeps of each conversation to draw it by at once (logs.js): its bounds, which
// goes first, what a change of format does to what an earlier one kept, a browser that keeps
// nothing, and how what is read again is drawn over what was drawn.

import assert from 'node:assert/strict'
import { test } from 'node:test'

import { fakeIndexedDB, sleep } from './helpers.mjs'

const { BOUNDS, FORMAT, fitted, keyOf, logCache, merged, warmable, weigh } = await import('../../../../src/hmz/web/static/logs.js')

/** A cache that writes behind at once, at a time the test tells. */
function cache(more = {}) {
  let at = 1000
  const made = logCache({ later: (act) => act(), now: () => at, ...more })
  return Object.assign(made, { tick: (by = 1) => (at += by), time: () => at })
}

/** What a view keeps of a chat: its record, and a trace of `lines` lines of `size` characters. */
function seen(id, { lines = 2, size = 10, daemon = 'local' } = {}) {
  return {
    daemon,
    kind: 'chat',
    id,
    workspace: '/w',
    detail: { name: id, workspace: '/w', held: false },
    traced: [{ key: 'claude:s1', actions: Array.from({ length: lines }, (_, at) => ({ category: 'message', start: at, name: 'x'.repeat(size) })) }],
  }
}

test('a conversation is kept by its daemon, its kind and its id, so that two daemons never mix', () => {
  assert.notEqual(keyOf('local', 'chat', 'a'), keyOf('far', 'chat', 'a'))
  assert.notEqual(keyOf('local', 'chat', 'a'), keyOf('local', 'epic', 'a'))
  const kept = cache()
  kept.put(keyOf('local', 'chat', 'a'), seen('a'))
  kept.put(keyOf('far', 'chat', 'a'), { ...seen('a', { daemon: 'far' }), detail: { name: 'a', workspace: '/far' } })
  assert.equal(kept.peek(keyOf('local', 'chat', 'a')).detail.workspace, '/w')
  assert.equal(kept.peek(keyOf('far', 'chat', 'a')).detail.workspace, '/far')
  // A daemon removed takes what was kept of its conversations with it, and no other's.
  kept.dropOf('far')
  assert.deepEqual(kept.keys(), [keyOf('local', 'chat', 'a')])
})

test('what is given is kept over what was, and what is not given stays as it was', () => {
  const kept = cache()
  const key = keyOf('local', 'chat', 'a')
  kept.put(key, seen('a'))
  kept.put(key, { daemon: 'local', kind: 'chat', id: 'a', scroll: { thread: 'Ada/1', top: 40, stuck: false } })
  const one = kept.peek(key)
  assert.equal(one.traced[0].actions.length, 2)
  assert.deepEqual(one.scroll, { thread: 'Ada/1', top: 40, stuck: false })
  assert.equal(one.v, FORMAT)
})

test('no more are kept than its bounds let: the one opened longest ago goes first', () => {
  const kept = cache({ bounds: { ...BOUNDS, entries: 3 } })
  // Each kept as its view is left, which opened it.
  for (const id of ['a', 'b', 'c']) {
    kept.put(keyOf('local', 'chat', id), { ...seen(id), opened: kept.time() })
    kept.tick()
  }
  // Opened again, the first is the latest opened: the second goes for a fourth.
  kept.open(keyOf('local', 'chat', 'a'))
  kept.tick()
  kept.put(keyOf('local', 'chat', 'd'), { ...seen('d'), opened: kept.time() })
  assert.deepEqual(kept.keys().sort(), ['a', 'c', 'd'].map((id) => keyOf('local', 'chat', id)))
})

test('one read ahead and never opened goes before any that was opened', () => {
  const kept = cache({ bounds: { ...BOUNDS, entries: 2 } })
  kept.put(keyOf('local', 'chat', 'opened'), { ...seen('opened'), opened: kept.time() })
  kept.tick()
  kept.put(keyOf('local', 'chat', 'ahead'), seen('ahead'))
  kept.tick()
  kept.put(keyOf('local', 'chat', 'next'), { ...seen('next'), opened: kept.time() })
  assert.deepEqual(kept.keys().sort(), ['next', 'opened'].map((id) => keyOf('local', 'chat', id)))
})

test('what is kept weighs no more together than its bounds let', () => {
  const each = weigh(seen('a', { lines: 4, size: 500 }))
  const kept = cache({ bounds: { entries: 100, bytes: each * 3, each: each * 2 } })
  for (const id of ['a', 'b', 'c', 'd', 'e']) {
    kept.put(keyOf('local', 'chat', id), { ...seen(id, { lines: 4, size: 500 }), opened: kept.time() })
    kept.tick()
  }
  assert.ok(kept.bytes() <= each * 3)
  assert.ok(kept.keys().length < 5)
  assert.ok(kept.peek(keyOf('local', 'chat', 'e')), 'the latest opened stays')
  assert.equal(kept.peek(keyOf('local', 'chat', 'a')), null)
})

test('one too heavy keeps only its end, marked cut, and is whole again once given whole', () => {
  const heavy = seen('a', { lines: 50, size: 1000 })
  const fit = fitted(heavy, 12000)
  assert.equal(fit.cut.traced, true)
  assert.ok(fit.bytes <= 12000)
  // The latest of what its log said, never the earliest.
  const starts = fit.traced[0].actions.map((one) => one.start)
  assert.ok(starts.length > 0 && starts.length < 50)
  assert.equal(starts.at(-1), 49)
  assert.deepEqual(starts, starts.toSorted((a, b) => a - b))
  // Light enough, it is kept whole.
  assert.deepEqual(fitted(seen('b'), 12000).cut, { live: false, traced: false })

  const kept = cache({ bounds: { ...BOUNDS, each: 12000 } })
  const key = keyOf('local', 'chat', 'a')
  assert.equal(kept.put(key, heavy).cut.traced, true)
  assert.equal(kept.put(key, { ...seen('a') }).cut.traced, false)
})

test('a run cut to its end keeps what says which run it is and who opened what', () => {
  const records = [
    { type: 'started', seq: 1, run: 1, task: 'hello' },
    { type: 'opened', seq: 2, run: 1, key: 'Ada/1' },
    ...Array.from({ length: 40 }, (_, at) => ({ type: 'event', kind: 'text', seq: 3 + at, run: 1, session: 'Ada/1', text: 'y'.repeat(400) })),
  ]
  const fit = fitted({ detail: { name: 'a' }, live: { epoch: 'e1', number: 1, records } }, 6000)
  assert.equal(fit.cut.live, true)
  assert.deepEqual(fit.live.records.slice(0, 2).map((one) => one.type), ['started', 'opened'])
  assert.equal(fit.live.records.at(-1).seq, 42)
  assert.ok(fit.live.records.length < records.length)
  // In the order they were told.
  const seqs = fit.live.records.map((one) => one.seq)
  assert.deepEqual(seqs, seqs.toSorted((a, b) => a - b))
})

test('a conversation whose record alone is too heavy is not kept at all', () => {
  const kept = cache({ bounds: { ...BOUNDS, each: 200 } })
  const key = keyOf('local', 'chat', 'a')
  assert.equal(kept.put(key, { ...seen('a'), detail: { name: 'a', task: 'z'.repeat(1000) } }), null)
  assert.equal(kept.peek(key), null)
})

test('one kept of another daemon gone by the same name is dropped as it is opened', () => {
  const kept = cache()
  const key = keyOf('far', 'chat', 'a')
  kept.put(key, { ...seen('a', { daemon: 'far' }), of: 'one-daemon' })
  assert.ok(kept.open(key, { of: 'one-daemon' }))
  // Not yet known which daemon answers: it stands until that is told.
  assert.ok(kept.open(key, { of: '' }))
  assert.equal(kept.open(key, { of: 'another-daemon' }), null)
  assert.equal(kept.peek(key), null)
})

test('those a daemon no longer lists are forgotten, of that kind and that daemon alone', () => {
  const kept = cache()
  for (const [daemon, kind, id] of [['local', 'aichan', 1], ['local', 'aichan', 2], ['local', 'chat', '2'], ['far', 'aichan', 2]]) kept.put(keyOf(daemon, kind, id), { daemon, kind, id, detail: null })
  kept.keep('local', 'aichan', [1])
  assert.deepEqual(kept.keys().sort(), [keyOf('far', 'aichan', 2), keyOf('local', 'aichan', 1), keyOf('local', 'chat', '2')].sort())
})

test('what is kept is in the browser for the page opened next, as it was opened and dropped', async () => {
  const indexedDB = fakeIndexedDB()
  const first = cache({ indexedDB })
  await first.ready
  first.put(keyOf('local', 'chat', 'a'), seen('a'))
  first.put(keyOf('local', 'chat', 'b'), seen('b'))
  first.drop(keyOf('local', 'chat', 'b'))
  await first.flush()
  await sleep(20)

  const next = cache({ indexedDB })
  // Nothing of it until the browser has been read; all of it after.
  assert.equal(next.peek(keyOf('local', 'chat', 'a')), null)
  await next.ready
  assert.equal(next.peek(keyOf('local', 'chat', 'a')).traced[0].actions.length, 2)
  assert.equal(next.peek(keyOf('local', 'chat', 'b')), null)
})

test('what memory has by the time the browser is read is later than what the browser kept', async () => {
  const indexedDB = fakeIndexedDB()
  const first = cache({ indexedDB })
  await first.ready
  first.put(keyOf('local', 'chat', 'a'), seen('a'))
  await first.flush()
  await sleep(20)
  const next = cache({ indexedDB })
  next.put(keyOf('local', 'chat', 'a'), seen('a', { lines: 5 }))
  await next.ready
  assert.equal(next.peek(keyOf('local', 'chat', 'a')).traced[0].actions.length, 5)
})

test('what the browser kept beyond the bounds is let go of as it is read', async () => {
  const indexedDB = fakeIndexedDB()
  const first = cache({ indexedDB })
  await first.ready
  for (const id of ['a', 'b', 'c']) {
    first.put(keyOf('local', 'chat', id), { ...seen(id), opened: first.time() })
    first.tick()
  }
  await first.flush()
  await sleep(20)
  const tight = cache({ indexedDB, bounds: { ...BOUNDS, entries: 2 } })
  await tight.ready
  assert.deepEqual(tight.keys().sort(), ['b', 'c'].map((id) => keyOf('local', 'chat', id)))
  await tight.flush()
  await sleep(20)
  const again = cache({ indexedDB })
  await again.ready
  assert.deepEqual(again.keys().sort(), ['b', 'c'].map((id) => keyOf('local', 'chat', id)))
})

test('an entry of another format is not read, and a change of format drops what the browser kept', async () => {
  const indexedDB = fakeIndexedDB()
  // An earlier format's database, with one entry in a store of its own.
  await new Promise((done) => {
    const asked = indexedDB.open('hmz-logs', FORMAT - 1 || 0.5)
    asked.onupgradeneeded = () => asked.result.createObjectStore('old')
    asked.onsuccess = () => {
      const doing = asked.result.transaction('old', 'readwrite')
      doing.objectStore('old').put({ v: 0, key: 'k', detail: {} }, 'k')
      doing.oncomplete = done
    }
  })
  const kept = cache({ indexedDB })
  await kept.ready
  assert.deepEqual(kept.keys(), [])
  // And it keeps anew from there.
  kept.put(keyOf('local', 'chat', 'a'), seen('a'))
  await kept.flush()
  await sleep(20)
  const next = cache({ indexedDB })
  await next.ready
  assert.deepEqual(next.keys(), [keyOf('local', 'chat', 'a')])

  // One written as another format, in this store, is passed over.
  await new Promise((done) => {
    const asked = indexedDB.open('hmz-logs', FORMAT)
    asked.onsuccess = () => {
      const doing = asked.result.transaction('logs', 'readwrite')
      doing.objectStore('logs').put({ v: FORMAT + 1, key: 'odd', detail: {}, bytes: 1 }, 'odd')
      doing.oncomplete = done
    }
  })
  const last = cache({ indexedDB })
  await last.ready
  assert.deepEqual(last.keys(), [keyOf('local', 'chat', 'a')])
})

test('a browser that keeps nothing leaves the cache in memory alone, and never throws', async () => {
  const refusing = [
    null,
    // A private window's: asking throws.
    { open: () => { throw new Error('SecurityError') } },
    // One that refuses, a moment later.
    { open: () => { const asked = {}; setTimeout(() => asked.onerror?.()); return asked } },
    // Another tab holds an earlier format open, and does not let go.
    { open: () => { const asked = {}; setTimeout(() => asked.onblocked?.()); return asked } },
  ]
  for (const indexedDB of refusing) {
    const kept = cache({ indexedDB })
    await kept.ready
    const key = keyOf('local', 'chat', 'a')
    kept.put(key, seen('a'))
    assert.ok(kept.open(key))
    kept.drop(key)
    assert.equal(kept.peek(key), null)
    await kept.flush()
  }
})

test('lines read again are drawn over those drawn: what was added to keeps every line it had', () => {
  // Only added to: every line drawn stays, and the new one is made.
  assert.deepEqual(merged(['a', 'b'], ['a', 'b', 'c']), { from: [0, 1, -1], dropped: [] })
  // One changed where it stood: it alone is made anew, and the one it was goes.
  assert.deepEqual(merged(['a', 'b', 'c'], ['a', 'B', 'c']), { from: [0, -1, 2], dropped: [1] })
  // Cut to its end and now read whole: the end stays, what came before it is made.
  assert.deepEqual(merged(['c', 'd'], ['a', 'b', 'c', 'd']), { from: [-1, -1, 0, 1], dropped: [] })
  // Two lines alike are two lines, the earlier drawn the earlier read.
  assert.deepEqual(merged(['a', 'a'], ['a', 'a', 'a']), { from: [0, 1, -1], dropped: [] })
  // Rewritten: nothing drawn stays.
  assert.deepEqual(merged(['a', 'b'], ['x']), { from: [-1], dropped: [0, 1] })
  // Nothing new: nothing made, nothing gone.
  assert.deepEqual(merged(['a'], ['a']), { from: [0], dropped: [] })
})

test('the latest of a list are read ahead: not the one in front, one read a moment ago, one kept as it stands, or one whose turn is open', () => {
  const kept = cache()
  const rows = [
    { name: 'old', kind: 'chat', ended: '2026-01-01' },
    { name: 'front', kind: 'chat', ended: '2026-01-09' },
    { name: 'kept', kind: 'chat', ended: '2026-01-08' },
    { name: 'stale', kind: 'chat', ended: '2026-01-07' },
    { name: 'epic', kind: 'flow', ended: '', began: '2026-01-06' },
    { name: 'going', kind: 'chat', ended: '2026-01-10', turn: 'running' },
    { name: 'outside', kind: 'harness', ended: '2026-01-11' },
    { name: 'lately', kind: 'chat', ended: '2026-01-05' },
    { name: 'older', kind: 'chat', ended: '2026-01-02' },
  ]
  kept.put(keyOf('local', 'chat', 'kept'), { ...seen('kept'), stamp: '2026-01-08' })
  kept.put(keyOf('local', 'chat', 'stale'), { ...seen('stale'), stamp: '2026-01-03' })
  const found = warmable(rows, kept, 'local', { most: 5, front: keyOf('local', 'chat', 'front'), lately: (key) => key === keyOf('local', 'chat', 'lately') })
  assert.deepEqual(found.map((one) => [one.kind, one.name, one.stamp]), [['chat', 'stale', '2026-01-07'], ['epic', 'epic', '2026-01-06']])
  assert.equal(found[0].key, keyOf('local', 'chat', 'stale'))
  // No more than asked for are looked at, the latest heard of first.
  assert.deepEqual(warmable(rows, kept, 'local', { most: 1 }).map((one) => one.name), ['front'])
})
