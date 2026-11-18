import assert from 'node:assert/strict'
import { after, test } from 'node:test'

// As much of a page as mounting a face touches: elements that hold what they are given.
class Node extends EventTarget {
  constructor(tag) {
    super()
    Object.assign(this, { tag, attributes: {}, dataset: {}, style: {}, kids: [], hidden: false, textContent: '' })
  }
  setAttribute(name, value) {
    this.attributes[name] = value
  }
  removeAttribute(name) {
    delete this.attributes[name]
  }
  append(...kids) {
    this.kids.push(...kids)
  }
  remove() {}
}
Object.assign(globalThis, {
  Node,
  document: {
    createElement: (tag) => new Node(tag),
    createTextNode: (text) => new Node(text),
    querySelector: () => null,
    head: new Node('head'),
    documentElement: new Node('html'),
  },
  getComputedStyle: () => ({ length: 0, getPropertyValue: () => '' }),
  matchMedia: () => new EventTarget(),
  MutationObserver: class {
    observe() {}
  },
})

const { dropFace, mountFace, showFace } = await import('../../../../src/hmz/web/static/faces/host.js')

const options = { fetchFace: async () => ({ html: '<p>face</p>', title: 'Review' }), submit: async () => ({}) }
const asked = (run, question) => ({ question, run, role: 'human', session: 'human/1', text: 'Merge?', face: { hash: 'ab12', title: 'Review' } })
const context = [{ kind: 'markdown', text: 'Tests pass.' }]
/** Every face a test mounted, let go of as the tests end: a frame waits five seconds to load. */
const mounted = []
after(() => {
  for (const [session, scope] of mounted) dropFace(session, scope)
})

test('a session keeps one frame across its asks, and another epic’s of the same name has its own', () => {
  mounted.push(['human/1', { where: '/w', run: 1 }], ['human/1', { where: '/w', run: 2 }])
  const first = mountFace(asked(1, 'q1'), { ...options, where: '/w' })
  assert.equal(mountFace(asked(1, 'q2'), { ...options, where: '/w' }), first)
  // The next epic of the same flow names its session the same, and asks with the same face.
  const next = mountFace(asked(2, 'q1'), { ...options, where: '/w' })
  assert.notEqual(next, first)
  assert.equal(next.attributes['data-session'], 'human/1')
  assert.equal(mountFace(asked(1, 'q3'), { ...options, where: '/w' }), first)
})

test('what a session is shown reaches the face of that host’s epic alone', () => {
  mounted.push(['human/1', { where: '/shown', run: 3 }])
  mountFace(asked(3, 'q1'), { ...options, where: '/shown' })
  // A host is named by its workspace alone, or by its workspace and slot: the same host.
  assert.equal(showFace('human/1', context, { where: { workspace: '/shown', slot: '' }, run: 3 }), true)
  assert.equal(showFace('human/1', context, { where: { workspace: '/shown', slot: '' }, run: 4 }), false)
  assert.equal(showFace('human/1', context, { where: { workspace: '/other', slot: '' }, run: 3 }), false)
  assert.equal(showFace('human/1', context, { where: { workspace: '/shown', slot: 'chat:ab' }, run: 3 }), false)
})
