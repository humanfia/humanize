import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { test } from 'node:test'

const STATIC = new URL('../../../../src/hmz/web/static/', import.meta.url)
const read = (path) => readFileSync(new URL(path, STATIC), 'utf8')

/** Every script of the page that is its own, by its path under `static`. */
const scripts = () =>
  readdirSync(STATIC, { recursive: true })
    .map(String)
    .filter((path) => path.endsWith('.js') && !/^(vendor|i18n)\//.test(path))

test('General is said to hold what it holds: the display and reporting, and neither Ai-chan nor side questions', () => {
  const about = /^\s*general: \{.*?about: (?:t\()?'([^']*)'/m.exec(read('views/settings.js'))?.[1]
  assert.equal(about, 'Display and reporting')
})

test('Settings has two groups, App and Daemon, and no page of a workspace', () => {
  const view = read('views/settings.js')
  const groups = [...view.matchAll(/^\s*\['(\w+)', t\('(\w+)'\)\],$/gm)].map((found) => found.slice(1))
  assert.deepEqual(groups, [
    ['app', 'App'],
    ['daemon', 'Daemon'],
  ])
  const pages = [...view.matchAll(/^\s*'?([\w-]+)'?: \{ group: '(\w+)'/gm)].map((found) => found.slice(1))
  assert.deepEqual(pages, [
    ['themes', 'app'],
    ['daemons', 'app'],
    ['notifications', 'app'],
    ['language', 'app'],
    ['general', 'daemon'],
    ['accounts', 'daemon'],
    ['nous', 'daemon'],
    ['runtimes', 'daemon'],
    ['backup', 'daemon'],
    ['usage', 'daemon'],
  ])
  // Neither a daemon nor a workspace is picked in it: no control of it is a choice of one.
  assert.doesNotMatch(view, /h\('select'/)
  assert.doesNotMatch(view, /query\.get\(/)
})

test('Usage is two pages, one drawing: the daemon’s in Settings and a folder’s in its own settings', () => {
  const usage = (view) => [...read(view).matchAll(/^\s*usage: \{.*?label: t\('Usage'\).*?import\('([^']+)'\)/gm)].map((found) => found[1])
  assert.deepEqual(usage('views/settings.js'), ['./settings/usage.js'])
  assert.deepEqual(usage('views/workspace.js'), ['./settings/usage.js'])
})

test('a workspace’s settings hold Setup, Usage and Archived chats, and pick neither a folder nor a daemon', () => {
  const view = read('views/workspace.js')
  const pages = [...view.matchAll(/^\s*(\w+): \{ (folder: true, )?label: t\('([^']+)'\)/gm)].map((found) => [found[1], Boolean(found[2]), found[3]])
  assert.deepEqual(pages, [
    ['setup', true, 'Setup'],
    ['usage', true, 'Usage'],
    // The one page `No folder` has too.
    ['archived', false, 'Archived chats'],
  ])
  assert.doesNotMatch(view, /h\('select'|known\(|toDaemon|onto\(/)
})

test('the daemon shown is chosen at the foot of the sidebar and under Daemons, and nowhere else', () => {
  const calling = (pattern) => scripts().filter((path) => pattern.test(read(path))).sort()
  // What switches the page to another daemon: the sidebar's menu, and Daemons by `onto`.
  assert.deepEqual(calling(/\btoDaemon\(/), ['api.js', 'sidebar.js'])
  assert.deepEqual(calling(/\bonto\(/), ['app.js', 'views/settings/daemons.js'])
  // Who lists the daemons kept: those two, and Batch apply, which copies to them and shows none.
  assert.deepEqual(calling(/\bknown\(\)/), ['api.js', 'sidebar.js', 'views/settings.js', 'views/settings/daemons.js'])
  // No view reads a daemon out of its own query: one named there is the whole page's (api.js).
  assert.deepEqual(calling(/query\.get\('daemon'\)/), [])
  assert.deepEqual(calling(/\?daemon=/), [])
})

test('a new epic and a new chat name no daemon and offer none', () => {
  for (const view of ['views/new.js', 'views/newchat.js', 'chips/environment.js', 'composer.js', 'views/search.js', 'views/flows.js', 'views/envs.js']) {
    const text = read(view)
    assert.doesNotMatch(text, /toDaemon|known\(\)|daemonChip|t\('Daemon'\)|t\('Connected to'\)/, view)
  }
})
