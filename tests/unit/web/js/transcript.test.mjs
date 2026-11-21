import assert from 'node:assert/strict'
import { test } from 'node:test'

import { page } from './page.mjs'

const { body, el } = page()
// What a menu asks of the thing that held the focus as it opened.
globalThis.HTMLElement = body.constructor

const { line, saidTraced, sayer, walked } = await import('../../../../src/hmz/web/static/transcript.js')

/** A thread of three lines in the page, and what presses a key on one of them or on the thread. */
function thread() {
  const lines = ['first', 'second', 'third'].map((said) => line('text', said))
  const made = walked(el('div', { class: 'thread' }, ...lines))
  body.replaceChildren(made)
  const key = (target, key, more = {}) => {
    const event = Object.assign(new Event('keydown', { cancelable: true }), { key, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, ...more })
    Object.defineProperty(event, 'target', { value: target })
    made.dispatchEvent(event)
    return event.defaultPrevented
  }
  return { made, lines, key }
}

test('a thread is one stop of Tab, and its lines are none', () => {
  const { made, lines } = thread()
  assert.equal(made.tabIndex, 0)
  assert.ok(lines.every((one) => one.tabIndex === undefined))
})

test('the arrows go from a thread the keys came to onto its newest line, then from line to line', () => {
  const { made, lines, key } = thread()
  made.focus()
  made.dispatchEvent(new Event('focus'))
  assert.equal(key(made, 'ArrowUp'), true)
  assert.equal(document.activeElement, lines[2])
  assert.equal(key(lines[2], 'ArrowUp'), true)
  assert.equal(document.activeElement, lines[1])
  assert.equal(key(lines[1], 'ArrowDown'), true)
  assert.equal(document.activeElement, lines[2])
  // Past either end they are the browser's again, as they are with a key held beside them.
  assert.equal(key(lines[2], 'ArrowDown'), false)
  assert.equal(key(lines[0], 'ArrowUp'), false)
  assert.equal(key(lines[1], 'ArrowUp', { shiftKey: true }), false)
  assert.equal(document.activeElement, lines[2])
})

test('a thread the pointer pressed is scrolled by the arrows still', () => {
  const { made, key } = thread()
  made.focus()
  made.dispatchEvent(new Event('focus'))
  made.dispatchEvent(new Event('pointerdown'))
  assert.equal(key(made, 'ArrowUp'), false)
  assert.equal(document.activeElement, made)
})

test('Alt and Enter on a line open its menu, with the focus in it', () => {
  const { lines, key } = thread()
  lines[1].focus()
  assert.equal(key(lines[1], 'Enter', { altKey: true }), true)
  const menu = body.querySelector('[role=menu]')
  assert.deepEqual(menu.querySelectorAll('[role=menuitem]').map((one) => one.textContent), ['Copy', 'Copy thread'])
  assert.ok(menu.contains(document.activeElement))
  // Enter alone is left to whatever else takes it.
  assert.equal(key(lines[1], 'Enter'), false)
})

test('what an agent stops to ask and the flow then puts to its person is one question, said once', () => {
  const says = sayer('Ada/1', { chat: true })
  const [asks] = says({ type: 'event', kind: 'asks', session: 'Ada/1', text: 'Which one first?' })
  assert.deepEqual(says({ type: 'asked', question: 'q1', key: 'Ada/1', role: 'human', text: 'Which one first? ', options: ['a', 'b'] }), [])
  // The line says which question it is, for its answers to be put under it.
  assert.equal(asks.dataset.question, 'q1')
  // Asked again, or of something its agent never said, it is a line of its own.
  const [again] = says({ type: 'asked', question: 'q2', key: 'Ada/1', role: 'human', text: 'Which one first?' })
  assert.equal(again.dataset.question, 'q2')
  assert.equal(again.querySelector('.who').textContent, 'human asks')
  // A person's log has what they were asked, whatever an agent said of it.
  const theirs = sayer('person:human')
  theirs({ type: 'event', kind: 'asks', session: 'Ada/1', text: 'Which one first?' })
  assert.equal(theirs({ type: 'asked', question: 'q1', key: 'Ada/1', role: 'human', text: 'Which one first?' }).length, 1)
})

test('a turn of a session begins and ends naming whose it was, and a chat’s names nobody', () => {
  const begins = { type: 'event', kind: 'begins', session: 'Ada/1', agent: 'Ada', at: 100 }
  const ends = { type: 'event', kind: 'ends', session: 'Ada/1', agent: 'Ada', at: 112 }
  const session = sayer('Ada/1')
  assert.deepEqual(session(begins).map((one) => [one.getAttribute('class'), one.querySelector('.body').textContent]), [['said begins', 'Ada/1 is working']])
  assert.deepEqual(session(ends).map((one) => [one.getAttribute('class'), one.querySelector('.body').textContent]), [['said ends', 'Worked for 12s · Ada/1']])
  // A chat's, and an Ai-chan conversation's: nothing as it begins, and how long it worked as it ends.
  for (const chat of [sayer('Ada/1', { chat: true }), sayer('Ada/1', { chat: true, folded: true })]) {
    assert.deepEqual(chat(begins), [])
    const [line, ...more] = chat(ends)
    assert.deepEqual([line.getAttribute('class'), line.querySelector('.body').textContent, more.length], ['said ends', 'Worked for 12s', 0])
  }
  // One whose start was not seen says so, and still names nobody.
  assert.equal(sayer('Ada/1', { chat: true })(ends)[0].querySelector('.body').textContent, 'Worked for ?')
})

test('a turn read off a trace opens on the prompt as a session, and on its person’s line as a chat', () => {
  const session = { key: 'Ada/1', actions: [{ category: 'turn', start: 1, name: 'turn 1', args: { prompt: 'hello' } }, { category: 'message', start: 2, name: 'message', args: { text: 'hi' } }] }
  const [turn, answer] = saidTraced(session)
  assert.deepEqual([turn.getAttribute('class'), turn.querySelector('.body').textContent], ['said turn', 'hello'])
  assert.equal(answer.getAttribute('class'), 'said text')
  const [mine] = saidTraced({ ...session, chat: true })
  assert.deepEqual([mine.getAttribute('class'), mine.querySelector('.body').textContent], ['said you', 'hello'])
})

test('a trace read again names each line by what it is drawn from, so that only what is new is made', async () => {
  const { tracedLines } = await import('../../../../src/hmz/web/static/transcript.js')
  const { merged } = await import('../../../../src/hmz/web/static/logs.js')
  const turn = { category: 'turn', start: 1, seconds: 2, name: 'turn', args: { prompt: 'hello' } }
  const answer = { category: 'message', start: 2, name: 'message', args: { text: 'hi' } }
  const more = { category: 'message', start: 3, name: 'message', args: { text: 'and more' } }
  const was = tracedLines({ key: 'claude:s1', label: 'Ada/1', chat: true, actions: [turn, answer] })
  const next = tracedLines({ key: 'claude:s1', label: 'Ada/1', chat: true, actions: [turn, answer, more] })
  // Added to, every line it had is the line it was; the same lines are drawn as before.
  assert.deepEqual(merged(was.map((one) => one.key), next.map((one) => one.key)), { from: [0, 1, -1], dropped: [] })
  assert.deepEqual(next.map((one) => one.make().textContent), saidTraced({ key: 'claude:s1', label: 'Ada/1', chat: true, actions: [turn, answer, more] }).map((one) => one.textContent))
  // A line whose words changed is another line, and no other is.
  const changed = tracedLines({ key: 'claude:s1', label: 'Ada/1', chat: true, actions: [turn, { ...answer, args: { text: 'hi there' } }, more] })
  assert.deepEqual(merged(next.map((one) => one.key), changed.map((one) => one.key)), { from: [0, -1, 2], dropped: [1] })
})
