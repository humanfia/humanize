// No page scrolls sideways on a phone: the built site, every page, in a window 390px wide.
//
//   pnpm build && pnpm check:phone
//
// The first run wants a browser: `pnpm exec playwright install chromium`. `--page user/chat`
// looks at one page.

import { readdir, readFile } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { parseArgs } from 'node:util'

import { chromium } from 'playwright'
import { serve } from 'vitepress'

const DIST = new URL('./dist/', import.meta.url).pathname
const DOCS = new URL('../', import.meta.url).pathname
const BASE = '/humanize/'
const WIDTH = 390
const PORT = 4179

const { values } = parseArgs({ options: { page: { type: 'string' } } })

async function pages(dir) {
  const found = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (entry.name !== 'assets') found.push(...(await pages(join(dir, entry.name))))
    } else if (entry.name.endsWith('.html') && entry.name !== '404.html') found.push(join(dir, entry.name))
  }
  return found
}

await serve({ root: DOCS, port: PORT })
const browser = await chromium.launch()
const wide = []
try {
  const context = await browser.newContext({ viewport: { width: WIDTH, height: 844 }, isMobile: true, hasTouch: true })
  const all = (await pages(DIST))
    .map((file) => relative(DIST, file).replace(/(^|\/)index\.html$/, '$1').replace(/\.html$/, ''))
    .filter((path) => !values.page || path === values.page)
  const page = await context.newPage()
  for (const path of all.sort()) {
    // A page that moved is a redirect file, which has nothing to scroll and leaves at once.
    const file = join(DIST, path === '' || path.endsWith('/') ? `${path}index.html` : `${path}.html`)
    if ((await readFile(file, 'utf8')).includes('http-equiv="refresh"')) continue
    const answer = await page.goto(`http://localhost:${PORT}${BASE}${path}`, { waitUntil: 'load' })
    if (!answer?.ok()) continue
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    if (over > 1) wide.push(`${path || '(home)'}: ${over}px wider than the screen`)
  }
  console.log(`${all.length} pages at ${WIDTH}px`)
} finally {
  await browser.close()
}
if (wide.length) {
  console.error(wide.join('\n'))
  process.exit(1)
}
// The server this started is still listening, so the check ends itself.
process.exit(0)
