// The pictures keep to their rules: every picture in the documentation is an SVG file -- static,
// or animated inside the file -- and there is no video, no recorded cast and no bitmap of an
// interface anywhere on the site.
//
//   pnpm check:pictures
//
// It reads the sources, so it needs no build. It fails on: a page that shows anything but an SVG
// under public/ (or a file that is not there); a `<video>`, a script or a component in a page; a
// picture under public/shots or public/diagrams that is not an SVG, carries a script or reaches
// outside itself, weighs more than half a megabyte, or that no page shows.

import { readdir, readFile, stat } from 'node:fs/promises'
import { join, relative } from 'node:path'

const DOCS = new URL('../', import.meta.url).pathname
const PUBLIC = join(DOCS, 'public')
const SKIP = new Set(['node_modules', '.vitepress', 'public'])
const HEAVIEST = 500 * 1024
const MOVING = /\.(mp4|webm|mov|gif|apng|cast|m4v|ogv)\b/i

async function walk(dir, keep) {
  const found = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (dir === DOCS && SKIP.has(entry.name)) continue
      found.push(...(await walk(join(dir, entry.name), keep)))
    } else if (keep(entry.name)) found.push(join(dir, entry.name))
  }
  return found
}

const wrong = []
const shown = new Set()

for (const page of await walk(DOCS, (name) => name.endsWith('.md'))) {
  const at = relative(DOCS, page)
  // What a page says in a code block is an example, not a picture.
  const text = (await readFile(page, 'utf8'))
    .replace(/^[ \t]*(```+|~~~+)[^\n]*\n[\s\S]*?^[ \t]*\1[ \t]*$/gm, '')
    .replace(/`[^`\n]+`/g, '')
  if (/<video|<audio|<source|<iframe|<object|<embed/i.test(text)) wrong.push(`${at}: plays or embeds something`)
  // The home page is one component, which it imports itself; every other page is plain Markdown.
  if (at !== 'index.md' && /<script/i.test(text)) wrong.push(`${at}: has a <script>; pages are plain Markdown`)
  if (MOVING.test(text)) wrong.push(`${at}: names a video, a GIF or a cast`)
  const sources = [
    ...[...text.matchAll(/!\[(?:[^\][]|\[[^\]]*\])*\]\(([^)\s]+)/g)].map((m) => m[1]),
    ...[...text.matchAll(/<img[^>]*\ssrc="([^"]+)"/gi)].map((m) => m[1]),
  ]
  for (const src of sources) {
    if (!src.startsWith('/')) wrong.push(`${at}: ${src} is not a file of this site`)
    else if (!src.endsWith('.svg')) wrong.push(`${at}: ${src} is not an SVG`)
    else if (!(await stat(join(PUBLIC, src)).catch(() => null))) wrong.push(`${at}: ${src} does not exist`)
    else shown.add(src)
  }
}

// The home page is a component, and shows its pictures through `withBase('/shots/…')`.
for (const part of await walk(join(DOCS, '.vitepress', 'theme'), (name) => /\.(vue|ts)$/.test(name))) {
  const text = await readFile(part, 'utf8')
  if (/<video|<audio/i.test(text) || MOVING.test(text)) wrong.push(`${relative(DOCS, part)}: plays a video, a GIF or a cast`)
  for (const m of text.matchAll(/['"`](\/(?:shots|diagrams)\/[^'"`]+\.svg)['"`]/g)) shown.add(m[1])
}

for (const file of await walk(PUBLIC, () => true)) {
  const src = `/${relative(PUBLIC, file)}`
  if (MOVING.test(src)) wrong.push(`public${src}: a video, a GIF or a cast`)
  if (!/^\/(shots|diagrams)\//.test(src)) continue
  if (!src.endsWith('.svg')) {
    wrong.push(`public${src}: not an SVG`)
    continue
  }
  const text = await readFile(file, 'utf8')
  if (/<script/i.test(text)) wrong.push(`public${src}: carries a script`)
  if (/(?:href|src)\s*=\s*["'](?:https?:)?\/\//i.test(text) || /@import/.test(text)) wrong.push(`public${src}: reaches outside itself`)
  if (Buffer.byteLength(text) > HEAVIEST) wrong.push(`public${src}: over ${HEAVIEST / 1024} kB`)
  if (!shown.has(src)) wrong.push(`public${src}: no page shows it`)
}

if (wrong.length) {
  console.error(wrong.join('\n'))
  console.error(`\n${wrong.length} picture rule${wrong.length === 1 ? '' : 's'} broken`)
  process.exit(1)
}
console.log(`${shown.size} pictures, every one an SVG`)
