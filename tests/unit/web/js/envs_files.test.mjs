import assert from 'node:assert/strict'
import { test } from 'node:test'

import * as L from '../../../../src/hmz/web/static/views/envs/files_logic.js'

/** A clock the autosaver's timers run on, moved by hand. */
function clock() {
  let now = 0
  let next = 1
  const timers = new Map()
  return {
    timer: {
      set: (fn, ms) => {
        timers.set(next, { fn, at: now + ms })
        return next++
      },
      clear: (one) => timers.delete(one),
    },
    get pending() {
      return timers.size
    },
    tick(ms) {
      now += ms
      for (const [id, one] of [...timers].sort((a, b) => a[1].at - b[1].at)) {
        if (one.at > now) continue
        timers.delete(id)
        one.fn()
      }
    },
  }
}

/** A promise and the hands that settle it. */
function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

const settle = () => new Promise((resolve) => setImmediate(resolve))

// Paths

test('paths join, normalise, and are said relative to the root', () => {
  assert.equal(L.joinPath('/w', 'src/a.py'), '/w/src/a.py')
  assert.equal(L.joinPath('/w/', './src/../b'), '/w/b')
  assert.equal(L.joinPath('/w', '/etc/hosts'), '/etc/hosts')
  assert.equal(L.parentOf('/w/a/b.txt'), '/w/a')
  assert.equal(L.parentOf('/a'), '/')
  assert.equal(L.baseName('/w/a/b.txt'), 'b.txt')
  assert.equal(L.relative('/w/a/b.txt', '/w'), 'a/b.txt')
  assert.equal(L.relative('/elsewhere/x', '/w'), '/elsewhere/x')
  assert.ok(L.within('/w/a/b', '/w/a'))
  assert.ok(!L.within('/w/ab', '/w/a'))
  assert.deepEqual(L.ancestors('/w/a/b/c.txt', '/w'), ['/w', '/w/a', '/w/a/b'])
})

test('a new name is refused when empty, climbing out, or taken', () => {
  assert.equal(L.badName('  '), 'A name is needed.')
  assert.match(L.badName('../x'), /climb/)
  assert.match(L.badName('a.py', ['a.py']), /there already/)
  assert.equal(L.badName('src/new.py', ['a.py']), null)
  // Under a directory there already.
  assert.equal(L.badName('src/new.py', ['src']), null)
})

// Fuzzy matching

test('a query matches letters in order, and not out of order', () => {
  assert.ok(L.score('abc', 'a_b_c'))
  assert.equal(L.score('cba', 'abc'), null)
  assert.equal(L.score('abcd', 'abc'), null)
  assert.deepEqual(L.score('', 'x'), { score: 0, hits: [] })
})

test('letters in a row, at word starts and after slashes score higher', () => {
  assert.ok(L.score('main', 'main.py').score > L.score('main', 'm_a_i_n.py').score)
  assert.ok(L.score('fb', 'foo_bar').score > L.score('fb', 'xfxb').score)
  assert.ok(L.score('sa', 'src/app.js').score > L.score('sa', 'xsxa.js').score)
  assert.ok(L.score('gC', 'getConfig').score > L.score('gC', 'gxcx').score)
})

test('the best alignment is found, not the first one', () => {
  // The greedy first `a` would leave `pp` apart from it; the run `app` is better.
  assert.deepEqual(L.score('app', 'a/x/app.js').hits, [4, 5, 6])
})

test('a file is found by its name before its path', () => {
  const ranked = L.rank('app', ['src/application/x.txt', 'web/app.js', 'lib/apply.py']).map((one) => one.path)
  assert.equal(ranked[0], 'web/app.js')
  assert.deepEqual(L.fuzzy('app', 'web/app.js').hits, [4, 5, 6])
})

test('a query with a slash matches across the path', () => {
  const got = L.fuzzy('src/ma', 'src/main.py')
  assert.ok(got)
  assert.deepEqual(got.hits, [0, 1, 2, 3, 4, 5])
  assert.equal(L.fuzzy('src/ma', 'lib/main.py'), null)
})

test('rank: best first, shorter on a tie, and no more than asked', () => {
  const paths = Array.from({ length: 100 }, (_, i) => `d${i}/file${i}.txt`)
  assert.equal(L.rank('file', paths, 10).length, 10)
  assert.deepEqual(L.rank('a', ['bb/a', 'a']).map((one) => one.path), ['a', 'bb/a'])
  assert.deepEqual(L.rank('zzz', paths), [])
})

test('rank goes through twenty thousand paths quickly', () => {
  const paths = Array.from({ length: 20000 }, (_, i) => `src/module${i % 97}/sub${i % 13}/file_${i}.py`)
  const start = performance.now()
  const got = L.rank('mod5file', paths)
  assert.ok(got.length > 0)
  assert.ok(performance.now() - start < 2000, `took ${performance.now() - start} ms`)
})

test('quick open reads a line and column off the end of what was typed', () => {
  assert.deepEqual(L.quickQuery('src/a.py:12'), { query: 'src/a.py', line: 12, column: null })
  assert.deepEqual(L.quickQuery('a.py:3:7'), { query: 'a.py', line: 3, column: 7 })
  assert.deepEqual(L.quickQuery('a.py'), { query: 'a.py', line: null, column: null })
  assert.deepEqual(L.quickQuery(':40'), { query: '', line: 40, column: null })
})

test('spans pick out the letters hit', () => {
  assert.deepEqual(L.spans('abcd', [1, 2]), [{ text: 'a', hit: false }, { text: 'bc', hit: true }, { text: 'd', hit: false }])
})

// Autosave

test('a file is written once, the delay after the last edit', async () => {
  const time = clock()
  const writes = []
  const states = []
  const saver = L.autosaver({ save: async () => writes.push('w'), timer: time.timer, told: (one) => states.push(one) })
  saver.edited()
  time.tick(500)
  saver.edited()
  time.tick(500)
  assert.equal(writes.length, 0)
  assert.ok(saver.dirty)
  time.tick(300)
  await settle()
  assert.equal(writes.length, 1)
  assert.ok(!saver.dirty)
  assert.equal(saver.state, 'saved')
  assert.deepEqual(states, ['dirty', 'dirty', 'saving', 'saved'])
})

test('never two writes in flight: edits meanwhile are written by one more, after its delay', async () => {
  const time = clock()
  const flights = []
  let inFlight = 0
  let most = 0
  const saver = L.autosaver({
    save: () => {
      inFlight++
      most = Math.max(most, inFlight)
      const one = deferred()
      flights.push(one)
      return one.promise.finally(() => inFlight--)
    },
    timer: time.timer,
  })
  saver.edited()
  time.tick(800)
  assert.equal(flights.length, 1)
  // Edits while the first is in flight, its timer firing too.
  saver.edited()
  saver.edited()
  time.tick(800)
  assert.equal(flights.length, 1)
  flights[0].resolve()
  await settle()
  assert.equal(saver.state, 'dirty')
  time.tick(800)
  assert.equal(flights.length, 2)
  flights[1].resolve()
  await settle()
  assert.equal(most, 1)
  assert.equal(saver.state, 'saved')
})

test('now writes at once, waits for the write in flight, and coalesces what came meanwhile', async () => {
  const time = clock()
  const flights = []
  const saver = L.autosaver({
    save: () => {
      const one = deferred()
      flights.push(one)
      return one.promise
    },
    timer: time.timer,
  })
  saver.edited()
  const first = saver.now()
  assert.equal(flights.length, 1)
  saver.edited()
  saver.edited()
  const second = saver.now()
  flights[0].resolve()
  await settle()
  assert.equal(flights.length, 2)
  flights[1].resolve()
  assert.equal(await first, true)
  assert.equal(await second, true)
  assert.equal(flights.length, 2)
  assert.equal(time.pending, 0)
})

test('now with nothing edited writes nothing', async () => {
  let writes = 0
  const saver = L.autosaver({ save: async () => writes++ })
  assert.equal(await saver.now(), true)
  assert.equal(writes, 0)
})

test('a failed write is said, kept dirty, and tried again on the next edit', async () => {
  const time = clock()
  let fail = true
  const errors = []
  let writes = 0
  const saver = L.autosaver({
    save: async () => {
      writes++
      if (fail) throw new Error('disk full')
    },
    timer: time.timer,
    told: (state, error) => state === 'error' && errors.push(error.message),
  })
  saver.edited()
  assert.equal(await saver.now(), false)
  assert.deepEqual(errors, ['disk full'])
  assert.ok(saver.dirty)
  assert.equal(saver.state, 'error')
  // Not tried again by itself.
  time.tick(5000)
  assert.equal(writes, 1)
  fail = false
  saver.edited()
  time.tick(800)
  await settle()
  assert.equal(writes, 2)
  assert.equal(saver.state, 'saved')
})

test('a paused saver writes nothing until it goes on; clean forgets the edits', async () => {
  const time = clock()
  let writes = 0
  const saver = L.autosaver({ save: async () => writes++, timer: time.timer })
  saver.pause(true)
  saver.edited()
  time.tick(2000)
  assert.equal(await saver.now(), false)
  assert.equal(writes, 0)
  saver.pause(false)
  time.tick(800)
  await settle()
  assert.equal(writes, 1)
  saver.edited()
  saver.clean()
  time.tick(2000)
  assert.equal(writes, 1)
  assert.ok(!saver.dirty)
  saver.dispose()
  saver.edited()
  time.tick(2000)
  assert.equal(writes, 1)
})

test('a save that throws at once is a failed write', async () => {
  const saver = L.autosaver({
    save: () => {
      throw new Error('boom')
    },
  })
  saver.edited()
  assert.equal(await saver.now(), false)
  assert.equal(saver.state, 'error')
})

// Bytes

test('base64 goes both ways, for big runs of bytes too', () => {
  const bytes = new Uint8Array(200000).map((_, i) => i % 256)
  assert.deepEqual(L.fromBase64(L.toBase64(bytes)), bytes)
  assert.equal(L.toBase64(new TextEncoder().encode('hi')), 'aGk=')
  assert.deepEqual(L.joined([new Uint8Array([1]), new Uint8Array([2, 3])]), new Uint8Array([1, 2, 3]))
})

test('decode: text with its line endings and byte order mark, or binary', () => {
  const crlf = L.decode(new TextEncoder().encode('a\r\nb\r\n'))
  assert.deepEqual(crlf, { binary: false, text: 'a\r\nb\r\n', eol: '\r\n', bom: false })
  assert.equal(L.decode(new TextEncoder().encode('a\nb')).eol, '\n')
  const bom = L.decode(new Uint8Array([0xef, 0xbb, 0xbf, 0x68, 0x69]))
  assert.equal(bom.text, 'hi')
  assert.equal(bom.bom, true)
  assert.deepEqual(L.decode(new Uint8Array([0x68, 0, 0x69])), { binary: true })
  assert.deepEqual(L.decode(new Uint8Array([0xff, 0xfe, 0x41])), { binary: true })
  assert.equal(L.decode(new TextEncoder().encode('héllo ✓')).text, 'héllo ✓')
})

test('encode puts back the line ending, the trailing newline and the byte order mark', () => {
  const text = (bytes) => new TextDecoder().decode(bytes)
  assert.equal(text(L.encode('a\nb\n', { eol: '\r\n' })), 'a\r\nb\r\n')
  assert.equal(text(L.encode('a\nb', { eol: '\n' })), 'a\nb')
  assert.deepEqual([...L.encode('x', { bom: true })], [0xef, 0xbb, 0xbf, 0x78])
  // A round trip of a CRLF file leaves it as it was.
  const read = L.decode(new TextEncoder().encode('one\r\ntwo\r\n'))
  assert.equal(text(L.encode(read.text.replace(/\r\n/g, '\n'), read)), 'one\r\ntwo\r\n')
})

test('the line ending a text mostly uses wins', () => {
  assert.equal(L.eolOf('a\r\nb\r\nc\n'), '\r\n')
  assert.equal(L.eolOf('a\nb\nc\r\n'), '\n')
  assert.equal(L.eolOf('no newline'), '\n')
})

test('how a file opens: by its size, and pictures as pictures', () => {
  assert.equal(L.opening({ name: 'a.py', size: 10 }), 'text')
  assert.equal(L.opening({ name: 'a.py', size: L.LARGE + 1 }), 'large')
  assert.equal(L.opening({ name: 'a.py', size: L.LARGEST + 1 }), 'too-large')
  assert.equal(L.opening({ name: 'x.PNG', size: L.LARGE + 1 }), 'image')
  assert.equal(L.imageType('a.svg'), 'image/svg+xml')
  assert.equal(L.imageType('a.txt'), null)
  assert.equal(L.sizeOf(2048), '2.0 KB')
})

test('delta keeps what the two texts share at either end', () => {
  assert.equal(L.delta('same', 'same'), null)
  assert.deepEqual(L.delta('hello world', 'hello brave world'), { from: 6, to: 6, insert: 'brave ' })
  assert.deepEqual(L.delta('abc', ''), { from: 0, to: 3, insert: '' })
  assert.deepEqual(L.delta('aaa', 'aa'), { from: 2, to: 3, insert: '' })
  const before = 'x\ny\nz'
  const change = L.delta(before, 'x\nY\nz')
  assert.equal(before.slice(0, change.from) + change.insert + before.slice(change.to), 'x\nY\nz')
})

// Languages

test('a language is said by the extension or the whole name', () => {
  assert.equal(L.languageOf('/w/a.py'), 'Python')
  assert.equal(L.languageOf('main.RS'), 'Rust')
  assert.equal(L.languageOf('Dockerfile'), 'Dockerfile')
  assert.equal(L.languageOf('Dockerfile.dev'), 'Dockerfile')
  assert.equal(L.languageOf('Makefile'), 'Makefile')
  assert.equal(L.languageOf('notes'), 'Plain Text')
  assert.deepEqual(L.badgeOf('a.ts'), { glyph: 'TS', lane: 5 })
  assert.equal(L.badgeOf('a.png').glyph, 'IMG')
  assert.equal(L.badgeOf('notes').glyph, '')
})

// Tabs

test('a preview tab is replaced by the next file previewed; a pinned one stays', () => {
  let state = { tabs: [], active: null }
  state = L.openTab(state, '/a', {})
  assert.deepEqual(state.tabs, [{ path: '/a', pinned: false }])
  const next = L.openTab(state, '/b', {})
  assert.equal(next.replaced, '/a')
  assert.deepEqual(next.tabs, [{ path: '/b', pinned: false }])
  state = L.openTab(next, '/b', { pin: true })
  assert.deepEqual(state.tabs, [{ path: '/b', pinned: true }])
  state = L.openTab(state, '/c', {})
  assert.deepEqual(state.tabs.map((one) => one.path), ['/b', '/c'])
  state = L.pinTab(state, '/c')
  state = L.openTab({ ...state, active: '/b' }, '/d', { pin: true })
  // Next to the active one.
  assert.deepEqual(state.tabs.map((one) => one.path), ['/b', '/d', '/c'])
  assert.equal(state.active, '/d')
})

test('closing the active tab makes its right neighbour active, else its left', () => {
  const state = { tabs: [{ path: '/a' }, { path: '/b' }, { path: '/c' }], active: '/b' }
  assert.equal(L.closeTab(state, '/b').active, '/c')
  assert.equal(L.closeTab({ ...state, active: '/c' }, '/c').active, '/b')
  assert.equal(L.closeTab({ ...state, active: '/a' }, '/c').active, '/a')
  assert.equal(L.closeTab({ tabs: [{ path: '/a' }], active: '/a' }, '/a').active, null)
  assert.deepEqual(L.closeOthers(state, '/c'), { tabs: [{ path: '/c' }], active: '/c' })
})

test('tabs move, and follow a rename of them or the directory they are in', () => {
  const state = { tabs: [{ path: '/a' }, { path: '/d/b' }, { path: '/d/c' }], active: '/d/b' }
  assert.deepEqual(L.moveTab(state, '/d/c', '/a').tabs.map((one) => one.path), ['/d/c', '/a', '/d/b'])
  assert.deepEqual(L.moveTab(state, '/a', null).tabs.map((one) => one.path), ['/d/b', '/d/c', '/a'])
  const moved = L.renameTabs(state, '/d', '/e')
  assert.deepEqual(moved.tabs.map((one) => one.path), ['/a', '/e/b', '/e/c'])
  assert.equal(moved.active, '/e/b')
})

/** A tab of a strip as the page would hand it: an event target, its box, and the pointer it holds. */
function fakeTab(path, left, strip) {
  const tab = new EventTarget()
  const classes = new Set()
  Object.assign(tab, {
    dataset: { path },
    parentElement: strip,
    held: null,
    classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name), contains: (name) => classes.has(name) },
    getBoundingClientRect: () => ({ left, right: left + 100 }),
    setPointerCapture: (id) => (tab.held = id),
    closest: () => null,
  })
  strip.children.push(tab)
  return tab
}

/** Hands an element a pointer event, as the pointer over `target` at `clientX` would. */
function point(el, type, clientX, { button = 0, target = el } = {}) {
  const event = new Event(type)
  Object.defineProperties(event, { target: { value: target }, clientX: { value: clientX }, button: { value: button }, pointerId: { value: 7 } })
  el.dispatchEvent(event)
}

test('a tab is let go before the first tab whose middle is past the pointer, else at the end', () => {
  const boxes = [
    { path: '/a', left: 0, right: 100 },
    { path: '/b', left: 100, right: 200 },
  ]
  assert.equal(L.dropBefore(boxes, 20), '/a')
  assert.equal(L.dropBefore(boxes, 60), '/b')
  assert.equal(L.dropBefore(boxes, 149), '/b')
  assert.equal(L.dropBefore(boxes, 151), null)
  assert.equal(L.dropBefore([], 0), null)
})

test('a tab is moved by the pointer alone, with no drag and drop event of the browser', () => {
  const strip = { children: [] }
  const [a, b] = ['/a', '/b', '/c'].map((path, at) => fakeTab(path, at * 100, strip))
  let state = { tabs: [{ path: '/a' }, { path: '/b' }, { path: '/c' }], active: '/a' }
  const drops = []
  L.dragTab(a, (before) => {
    drops.push(before)
    state = L.moveTab(state, '/a', before)
  })
  // Onto the right half of the next tab: it goes past it.
  point(a, 'pointerdown', 50)
  assert.equal(a.held, 7)
  point(a, 'pointermove', 170)
  assert.equal(a.classList.contains('dragging'), true)
  point(a, 'pointerup', 170)
  assert.equal(a.classList.contains('dragging'), false)
  assert.deepEqual(drops, ['/c'])
  assert.deepEqual(state.tabs.map((one) => one.path), ['/b', '/a', '/c'])
  // Past the last tab: it goes to the end. Nothing is heard of the pointer once it is let go.
  point(a, 'pointerdown', 50)
  point(a, 'pointermove', 400)
  point(a, 'pointerup', 400)
  point(a, 'pointermove', 10)
  point(a, 'pointerup', 10)
  assert.deepEqual(drops, ['/c', null])
  // A press that hardly moves is a click, one cancelled moves nothing, and neither does another
  // button or a press on the tab's close button.
  point(a, 'pointerdown', 50)
  point(a, 'pointermove', 52)
  point(a, 'pointerup', 52)
  point(a, 'pointerdown', 50)
  point(a, 'pointermove', 270)
  point(a, 'pointercancel', 270)
  assert.equal(a.classList.contains('dragging'), false)
  point(a, 'pointerdown', 50, { button: 1 })
  point(a, 'pointermove', 270)
  point(a, 'pointerup', 270)
  point(a, 'pointerdown', 50, { target: { closest: (selector) => (selector === '.files-tab-close' ? {} : null) } })
  point(a, 'pointermove', 270)
  point(a, 'pointerup', 270)
  assert.deepEqual(drops, ['/c', null])
  assert.equal(b.held, null)
})

test('the panel asks nothing of the drag and drop a desktop web view keeps from the page', async () => {
  const { readFile } = await import('node:fs/promises')
  const source = await readFile(new URL('../../../../src/hmz/web/static/views/envs/files.js', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /draggable|'dragstart'|'dragover'|'drop'/)
})

// The explorer

const entry = (name, kind = 'file') => ({ name, kind, size: 0, mtime: 0 })

test('the tree shows what is in each directory open, directories first', () => {
  const tree = {
    root: '/w',
    open: new Set(['/w/src', '/w/docs']),
    listed: new Map([
      ['/w', L.sorted([entry('z.txt'), entry('src', 'dir'), entry('docs', 'dir'), entry('a.txt')])],
      ['/w/src', [entry('main.py')]],
    ]),
    failed: new Map(),
  }
  const rows = L.treeRows(tree)
  assert.deepEqual(rows.map((one) => [one.path, one.depth, one.open]), [
    ['/w/docs', 0, true],
    ['/w/docs/\0loading', 1, false],
    ['/w/src', 0, true],
    ['/w/src/main.py', 1, false],
    ['/w/a.txt', 0, false],
    ['/w/z.txt', 0, false],
  ])
  tree.failed.set('/w/docs', 'Permission denied')
  assert.equal(L.treeRows(tree)[1].kind, 'error')
})

test('a link listed as a directory opens as one', () => {
  const tree = { root: '/w', open: new Set(['/w/l']), listed: new Map([['/w', [entry('l', 'link')]], ['/w/l', [entry('x')]]]) }
  assert.deepEqual(L.treeRows(tree).map((one) => one.path), ['/w/l', '/w/l/x'])
  tree.listed.delete('/w/l')
  assert.deepEqual(L.treeRows(tree).map((one) => one.path), ['/w/l'])
})

test('a filter keeps the names that hold it and the directories they are in', () => {
  const tree = {
    root: '/w',
    open: new Set(),
    listed: new Map([
      ['/w', [entry('src', 'dir'), entry('readme.md')]],
      ['/w/src', [entry('main.py'), entry('util.py')]],
    ]),
  }
  assert.deepEqual(L.treeRows(tree, 'MAIN').map((one) => one.path), ['/w/src', '/w/src/main.py'])
  assert.deepEqual(L.treeRows(tree, 'nothing'), [])
})

test('sorting is natural, and the arrow keys step over rows that are not entries', () => {
  assert.deepEqual(L.sorted([entry('f10'), entry('f2'), entry('B', 'dir'), entry('a')]).map((one) => one.name), ['B', 'a', 'f2', 'f10'])
  const rows = [{ path: '/a', kind: 'dir' }, { path: '/a/\0loading', kind: 'loading' }, { path: '/b', kind: 'file' }]
  assert.equal(L.step(rows, '/a', 1), '/b')
  assert.equal(L.step(rows, '/b', 1), '/b')
  assert.equal(L.step(rows, '/b', -1), '/a')
  assert.equal(L.step(rows, null, 1), '/a')
  assert.equal(L.step([], null, 1), null)
})

// Search

test('matches are grouped by file, in the order found, and folded files hide theirs', () => {
  const groups = L.grouped([
    { path: 'a.py', line: 1, column: 1, text: 'x' },
    { path: 'b.py', line: 2, column: 1, text: 'y' },
    { path: 'a.py', line: 5, column: 3, text: 'z' },
  ], '/w')
  assert.deepEqual(groups.map((one) => [one.path, one.matches.length]), [['/w/a.py', 2], ['/w/b.py', 1]])
  assert.equal(L.resultRows(groups).length, 5)
  const rows = L.resultRows(groups, new Set(['/w/a.py']))
  assert.deepEqual(rows.map((one) => one.kind), ['file', 'file', 'match'])
  assert.equal(rows[0].folded, true)
})

test('the match on a result line is found again to be picked out', () => {
  assert.deepEqual(L.matchOn('foo bar foo', 'foo', {}, 5), [8, 11])
  assert.deepEqual(L.matchOn('foo bar foo', 'FOO', {}, 1), [0, 3])
  assert.equal(L.matchOn('foo', 'FOO', { caseSensitive: true }), null)
  assert.deepEqual(L.matchOn('a1 b22', 'b\\d+', { regex: true }), [3, 6])
  assert.deepEqual(L.matchOn('a.b', '.', {}), [1, 2])
  assert.equal(L.matchOn('x', '(', { regex: true }), null)
})
