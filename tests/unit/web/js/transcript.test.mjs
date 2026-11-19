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

test('a turn read off a trace opens on the prompt as a session, and on its person’s line as a chat', () => {
  const session = { key: 'Ada/1', actions: [{ category: 'turn', start: 1, name: 'turn 1', args: { prompt: 'hello' } }, { category: 'message', start: 2, name: 'message', args: { text: 'hi' } }] }
  const [turn, answer] = saidTraced(session)
  assert.deepEqual([turn.getAttribute('class'), turn.querySelector('.body').textContent], ['said turn', 'hello'])
  assert.equal(answer.getAttribute('class'), 'said text')
  const [mine] = saidTraced({ ...session, chat: true })
  assert.deepEqual([mine.getAttribute('class'), mine.querySelector('.body').textContent], ['said you', 'hello'])
})
