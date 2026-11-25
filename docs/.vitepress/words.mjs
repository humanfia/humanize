// The home page's words keep to their rules: the banner is the repository's description, word
// for word, and the page's title ends with it; a tab or a button is one word; and no string is
// empty.
//
//   pnpm check:words
//
// The words are in theme/home/copy.ts, but the page's title and description, which are the
// frontmatter of index.md. It reads the sources, so it needs no build. It fails on: a banner
// that is not the description pyproject.toml gives the repository (the full stop aside), or a
// title that does not end with it; a tab or a button that is more than one word; and any string
// of copy.ts, or the title or description, that is missing or empty.
//
// It sees copy.ts and the frontmatter, not the names the page's templates print as they are;
// copy.ts lists those.

import { readFile } from 'node:fs/promises'

const DOCS = new URL('../', import.meta.url)
const read = (path) => readFile(new URL(path, DOCS), 'utf8')

// copy.ts is plain data: without its one piece of TypeScript it is a module as it stands.
const source = await read('.vitepress/theme/home/copy.ts')
const { BANNER, WORDS, SCALE, INFRA, PILLARS, SCENES } = await import(`data:text/javascript,${encodeURIComponent(source.replace(/\bas const\b/g, ''))}`)

const bare = (text) => text.replace(/\.$/, '')
const front = (page, key) => new RegExp(`^${key}: "([^"\\n]*)"$`, 'm').exec(page)?.[1]

const description = /^description = "([^"\n]*)"$/m.exec(await read('../pyproject.toml'))?.[1]
const index = await read('index.md')
const title = front(index, 'title')

const wrong = []

if (!description) wrong.push('pyproject.toml: no description to hold the banner to')
else {
  if (bare(BANNER) !== bare(description)) wrong.push(`BANNER: "${BANNER}" is not the repository's description, "${description}"`)
  if (!title?.endsWith(bare(description))) wrong.push(`index.md: the title "${title}" does not end with the repository's description`)
}

// What stands on a tab or a button: one word each. The row of tabs' name and the pictures'
// descriptions are read out, not shown, and are phrases.
const { tabs: _row, ...buttons } = WORDS
const single = { ...Object.fromEntries(Object.entries(buttons).map(([key, word]) => [`WORDS.${key}`, word])), 'INFRA.more': INFRA.more }
for (const scene of SCENES) single[`SCENES ${scene.key}: tab`] = scene.tab
for (const [where, word] of Object.entries(single)) {
  if (!/^\p{L}+$/u.test(word)) wrong.push(`${where}: "${word}" is not one word`)
}

// Every string there is, whatever it is for.
const strings = { BANNER, 'index.md title': title ?? '', 'index.md description': front(index, 'description') ?? '' }
for (const [key, word] of Object.entries(WORDS)) strings[`WORDS.${key}`] = word
for (const [key, word] of Object.entries(SCALE)) strings[`SCALE.${key}`] = word
for (const [key, word] of Object.entries(INFRA)) strings[`INFRA.${key}`] = word
for (const pillar of PILLARS) for (const [key, word] of Object.entries(pillar)) strings[`PILLARS ${pillar.label}: ${key}`] = word
for (const scene of SCENES) for (const [key, word] of Object.entries(scene)) strings[`SCENES ${scene.key}: ${key}`] = word
for (const [where, text] of Object.entries(strings)) {
  if (typeof text !== 'string' || !text.trim()) wrong.push(`${where}: not a string, or empty`)
}

if (wrong.length) {
  console.error(wrong.join('\n'))
  console.error(`\n${wrong.length} word rule${wrong.length === 1 ? '' : 's'} broken`)
  process.exit(1)
}
console.log(`${Object.keys(strings).length} strings, the banner the repository's description`)
