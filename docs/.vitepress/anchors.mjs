// Every `#fragment` in the documentation, checked against the ids the site really built.
//
// VitePress checks that a link's *page* exists and stops there, so a fragment written the way
// GitHub would slugify it - apostrophes stripped rather than turned into `-`, a leading digit
// left bare rather than prefixed with `_` - passes the build and silently drops the reader at
// the top of the page. This is the check that catches that.
//
//   pnpm build && pnpm check:anchors

import { readdir, readFile } from 'node:fs/promises'
import { join, relative } from 'node:path'

const DIST = new URL('./dist/', import.meta.url).pathname
const DOCS = new URL('../', import.meta.url).pathname
const SKIP = new Set(['node_modules', '.vitepress', 'tapes', 'public'])

async function walk(at, ext) {
  const found = []
  for (const entry of await readdir(at, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (SKIP.has(entry.name)) continue
      found.push(...(await walk(join(at, entry.name), ext)))
    } else if (entry.name.endsWith(ext)) {
      found.push(join(at, entry.name))
    }
  }
  return found
}

// One spelling of a route, whichever of the two sides below is asking for it. An index page
// is built as `contributing/index.html` and has to be *linked* as `/contributing/` - VitePress
// resolves the trailing slash and calls the bare form a dead link - so neither of the two
// spellings anybody writes is the `/contributing` they have to meet at. Both the trailing
// `index` and the trailing slash come off here rather than at each call site: the keys of `ids`
// and the lookups against it must agree exactly, and a rule added to one copy and not the other
// is every fragment on an index page reported as `no such page`.
const normalized = (path) => path.replace(/\/index$/, '').replace(/\/$/, '') || '/'

const route = (path, root, ext) =>
  normalized('/' + relative(root, path).replaceAll('\\', '/').slice(0, -ext.length))

const ids = new Map()
for (const page of await walk(DIST, '.html')) {
  const html = await readFile(page, 'utf8')
  ids.set(
    route(page, DIST, '.html'),
    new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1])),
  )
}

const squashed = (said) => said.toLowerCase().replace(/[^a-z0-9]/g, '')
let broken = 0

for (const doc of await walk(DOCS, '.md')) {
  const here = route(doc, DOCS, '.md')
  const text = await readFile(doc, 'utf8')
  for (const [, target] of text.matchAll(/\]\(([^)\s]+)\)/g)) {
    if (target.startsWith('http')) continue
    const [base, fragment] = target.split('#')
    if (!fragment) continue
    const page = normalized(
      base ? '/' + base.replace(/^\//, '').replace(/\.md$/, '') : here,
    )
    const has = ids.get(page)
    const where = relative(DOCS, doc)
    if (!has) {
      console.error(`${where}: ${target} -- no such page`)
      broken += 1
    } else if (!has.has(fragment)) {
      const near = [...has].filter((id) => squashed(id) === squashed(fragment))
      const meant = near.length ? ` -- did you mean #${near[0]}` : ''
      console.error(`${where}: ${target} -- no such heading${meant}`)
      broken += 1
    }
  }
}

if (broken) {
  console.error(`\n${broken} dead fragment(s).`)
  process.exit(1)
}
console.log('every #fragment resolves')
