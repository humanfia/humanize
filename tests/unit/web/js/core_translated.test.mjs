// What the page's shared parts say in Simplified and in Traditional Chinese: an effort by the
// page's own word while a harness and a model keep their vendor's name (Section 3.4.4.11 and
// 3.4.4.14 of protocol/web.md), a notification's title, a folder that is gone, a nous that
// balances, and why a daemon is not kept. A table made as a module loads is made in the language
// the document names then, so each module is loaded once per language.

import assert from 'node:assert/strict'
import { test } from 'node:test'

const root = { lang: '', dataset: {} }
Object.assign(globalThis, { document: { documentElement: root } })

const STATIC = '../../../../src/hmz/web/static/'

/** A module of the page loaded anew with the page written in a language. */
async function loaded(name, language) {
  root.lang = language
  return import(`${STATIC}${name}?${language}`)
}

/** Does something with the page written in a language, then puts it back in English. */
async function written(language, act) {
  root.lang = language
  try {
    return await act()
  } finally {
    root.lang = ''
  }
}

test('an effort is said in the page’s language, a harness and a model as their vendors write them', async () => {
  const hans = await loaded('names.js', 'zh-Hans')
  const hant = await loaded('names.js', 'zh-Hant')
  await written('zh-Hans', () => {
    assert.deepEqual(['ultra', 'max', 'xhigh', 'extra-high', 'high', 'medium', 'low', 'minimal', 'none', 'off', 'as configured'].map(hans.effortName), ['极限', '最高', '超高', '超高', '高', '中', '低', '最低', '无', '关闭', '按配置'])
    assert.equal(hans.effortName(''), '默认')
    assert.equal(hans.effortName('auto'), '默认')
    assert.equal(hans.effortName('swarmmax'), '最高 蜂群')
    // A product's name, and a rung the table does not hold, as written.
    assert.equal(hans.effortName('ultracode'), 'Ultracode')
    assert.equal(hans.effortName('turbo'), 'turbo')
    assert.equal(hans.harnessName('claude'), 'Claude Code')
    assert.equal(hans.modelName('claude-fable-5-2'), 'Fable 5.2')
    assert.equal(hans.modelName('gpt-6.2-sol'), 'GPT-6.2 Sol')
    assert.equal(hans.modelName('auto'), 'Auto')
    assert.equal(hans.modelName('as configured'), '按配置')
    assert.equal(hans.verseName('official'), '官方')
    assert.equal(hans.verseName('acme'), 'acme')
  })
  await written('zh-Hant', () => {
    assert.deepEqual(['xhigh', 'medium', 'none', 'off', 'as configured'].map(hant.effortName), ['超高', '中', '無', '關閉', '依設定'])
    assert.equal(hant.effortName(''), '預設')
    assert.equal(hant.harnessName('codex'), 'Codex')
    assert.equal(hant.modelName('claude-haiku-4-5'), 'Haiku 4.5')
  })
})

test('a notification is titled by its kind in the page’s language, over what the daemon wrote', async () => {
  const notice = { kind: 'asked', daemon: 'local', epic: 'e1', flow: 'goal', text: 'Which **way**?', key: 'local:1' }
  const hans = await loaded('notified.js', 'zh-Hans')
  await written('zh-Hans', () => {
    assert.deepEqual(hans.shownAs(notice), { title: '提问 · 本机', body: 'goal · Which way?', address: '#/epics/e1', tag: 'local:1' })
    assert.equal(hans.shownAs({ ...notice, kind: 'done', daemon: 'atlas' }).title, '已完成 · atlas')
    // A kind the page has no word for is said as the daemon said it.
    assert.equal(hans.shownAs({ ...notice, kind: 'odd' }).title, 'odd · 本机')
  })
  const hant = await loaded('notified.js', 'zh-Hant')
  await written('zh-Hant', () => {
    assert.equal(hant.shownAs({ ...notice, kind: 'failed' }).title, '失敗 · 本機')
    assert.equal(hant.shownAs({ ...notice, kind: 'listening' }).title, '等待中 · 本機')
  })
})

test('a nous that balances is said in the page’s language around the names it was given', async () => {
  const { nodeSaid } = await import(`${STATIC}nous.js`)
  const node = { balance: 'round-robin', among: [{ nous: 'a', weight: 2 }, { nous: 'b', weight: 1 }], spread: 3 }
  assert.equal(nodeSaid(node), 'round-robin: a ×2, b, 3 at most')
  assert.equal(await written('zh-Hans', () => nodeSaid(node)), 'round-robin：a ×2, b，最多 3')
  assert.equal(await written('zh-Hant', () => nodeSaid({ ...node, spread: 0 })), 'round-robin: a ×2, b')
})

test('why a daemon is not kept, and why an answer was not taken, is said in the page’s language', async () => {
  const { parsePairing: named } = await import(`${STATIC}rpc/registry.js`)
  assert.throws(() => named('nonsense'), { message: 'That is not a pairing code.' })
  await written('zh-Hans', () => assert.throws(() => named('nonsense'), { message: '这不是配对码。' }))
  await written('zh-Hant', () => assert.throws(() => named('nonsense'), { message: '這不是配對碼。' }))
  const { errorsOf } = await import(`${STATIC}faces/logic.js`)
  assert.deepEqual(errorsOf(null), [{ path: [], message: 'The answer was not taken.' }])
  // What the flow refused with is the flow's, as written.
  assert.deepEqual(await written('zh-Hans', () => errorsOf([{ path: ['a'], message: 'Too long.' }])), [{ path: ['a'], message: 'Too long.' }])
})
