// What the sidebar's list and Search say where the page is written in Chinese: their tables
// are made as their modules load, so the language is set before any of them is read.

import assert from 'node:assert/strict'
import { test } from 'node:test'

globalThis.document = { documentElement: { lang: 'zh-Hant', dataset: {} } }

const { CHAT_SAID, epicSaid, rowSaid, rowTitle, shortcut, wording } = await import('../../../../src/hmz/web/static/sidebar-rows.js')
const { GROUPS, NO_FOLDER, SHOWS, SORTS, arranged } = await import('../../../../src/hmz/web/static/sidebar-view.js')
const { TABS, heading, hints, nothing, paged } = await import('../../../../src/hmz/web/static/search-model.js')
const { DELETING, NO_WORKTREE } = await import('../../../../src/hmz/web/static/chats.js')
const { t } = await import('../../../../src/hmz/web/static/i18n.js')

test('a row says how it stands in the page’s language, and a mark it has no word for as it is', () => {
  assert.deepEqual(CHAT_SAID, { working: '執行中', asking: '等待輸入', failed: '失敗' })
  assert.equal(epicSaid('budget'), '預算用盡')
  assert.equal(epicSaid('done'), '已完成')
  assert.equal(epicSaid('odd'), 'Odd')
  assert.equal(epicSaid(''), '')
  assert.equal(rowSaid('running', true), '執行中')
  assert.equal(rowSaid('stopped', true), '')
  // Pointed at, an epic's mark is the word a badge says, and what was asked stays as it was typed.
  assert.equal(rowTitle({ task: 'fix' }, { chat: false, how: 'done', flow: 'ralph', began: 'today' }), 'fix\nralph · 已完成 · today')
  assert.equal(rowTitle({ task: 'fix' }, { chat: false, how: 'odd', flow: 'ralph', began: 'today' }), 'fix\nralph · odd · today')
})

test('a row’s menu is worded in the page’s language, and the keys of a shortcut are not', () => {
  assert.equal(wording(true).like, '新增類似聊天')
  assert.equal(wording(false).like, '新增類似的史詩')
  for (const said of [...Object.values(wording(true)), ...Object.values(wording(false))]) assert.match(said, /[一-鿿]/)
  assert.deepEqual(shortcut('search', false), ['Ctrl', 'K'])
})

test('what `Group and sort` offers and the groups it makes are named in the page’s language, and kept by the same keys', () => {
  assert.deepEqual(GROUPS, [['folder', '資料夾'], ['date', '日期'], ['none', '不分組']])
  assert.deepEqual(SORTS, [['updated', '上次更新'], ['created', '建立時間']])
  assert.deepEqual(SHOWS, [['chats', '聊天'], ['epics', '史詩']])
  assert.equal(NO_FOLDER, '無資料夾')
  const view = { group: 'date', sort: 'updated', chats: true, epics: true }
  const now = Date.parse('2026-05-02T12:00:00')
  const runs = [
    { name: 'a', kind: 'chat', began: '2026-05-02T09:00:00', workspace: '/w' },
    { name: 'b', kind: 'chat', began: '2026-05-01T09:00:00', workspace: '/w' },
    { name: 'c', kind: 'chat', began: '2026-01-01T09:00:00', workspace: '' },
  ]
  const groups = arranged({ runs, view, pinned: new Set(['c']), now })
  assert.deepEqual(groups.map((one) => [one.key, one.label]), [[':pinned', '已置頂'], [':date:today', '今天'], [':date:yesterday', '昨天'], [':folders', '資料夾']])
  assert.deepEqual(arranged({ runs: [], view: { ...view, group: 'folder' }, now }).map((one) => [one.key, one.label]), [[':nowhere', '無資料夾']])
  assert.equal(arranged({ runs, view: { ...view, group: 'none' }, now })[0].label, '全部')
})

test('Search names its tabs, its keys’ doings and its headings in the page’s language, and a key as it is written on it', () => {
  assert.deepEqual(TABS, [['', '全部'], ['chat', '聊天'], ['flow', '史詩']])
  assert.deepEqual(hints(true).map(([does]) => does), ['關閉', '切換類型', '篩選', '動作', '移動', '開啟'])
  assert.deepEqual(hints(true)[3][1], ['Option', 'Enter'])
  assert.equal(heading({ q: 'x' }), '結果')
  assert.equal(heading({}), '最近')
  assert.equal(paged({ total: 120, offset: 50, runs: Array(50).fill({}) }), '第 51–100 項，共 120 項')
  assert.equal(paged({ total: 0, offset: 0, runs: [] }), '')
  const [title, text, does] = nothing({ kind: 'chat' })
  assert.equal(title, '還沒有聊天。')
  assert.match(text, /^[^ ]/)
  assert.deepEqual(does, ['chat'])
})

test('what is said before a chat is deleted, and why it has no worktree, say a worktree by the glossary', () => {
  assert.match(DELETING, /工作樹/)
  assert.match(DELETING, /無法復原/)
  assert.equal(NO_WORKTREE.none, '工作樹需要一個資料夾')
})

test('a count is said with no plural form of its own, and the texts English tells apart by number are held', () => {
  assert.equal(t('{n} flows have a newer release', { n: 1 }), '1 個流程有新版本')
  assert.equal(t('{n} sessions', { n: 2 }), '2 個工作階段')
  document.documentElement.lang = 'en'
  assert.equal(t('{n} flows have a newer release', { n: 1 }), '1 flow has a newer release')
  assert.equal(t('{n} flows have a newer release', { n: 3 }), '3 flows have a newer release')
  assert.equal(t('{n} sessions', { n: 1 }), '1 session')
  assert.equal(t('{n} sessions', { n: 0 }), '0 sessions')
  assert.equal(t('None@@group'), 'None')
  document.documentElement.lang = 'zh-Hans'
  assert.equal(t('None@@group'), '不分组')
  assert.equal(t('This folder is no longer on this machine: {path}', { path: '/w' }), '此文件夹已不在这台机器上：/w')
})
