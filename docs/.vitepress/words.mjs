// The home page's words keep to their rules: the banner is the repository's description, word
// for word; a tab or a button is one word; nothing states a count, and nothing joins two
// fragments with a comma or a semicolon. A program reads those last two as: no digit and no
// number written out, and no comma or semicolon at all.
//
//   pnpm check:words
//
// The words are in theme/home/copy.ts, but the page's title and description, which are the
// frontmatter of index.md. It reads the sources, so it needs no build. It fails on: a banner
// that is not the description pyproject.toml gives the repository (the full stop aside, which
// the page sets in its accent), or a title that does not end with it; a tab, a button or a word
// of the loop's drawing that is more than one word; and any string of copy.ts, or the title or
// description, with a digit, a number word (NUMBER), a comma or a semicolon in it.
//
// It sees copy.ts and the frontmatter, not the names the page's templates print as they are;
// copy.ts lists those.

import { readFile } from 'node:fs/promises'

const DOCS = new URL('../', import.meta.url)
const read = (path) => readFile(new URL(path, DOCS), 'utf8')

// copy.ts is plain data: without its one piece of TypeScript it is a module as it stands.
const source = await read('.vitepress/theme/home/copy.ts')
const { BANNER, WORDS, LOOP, SCENES } = await import(`data:text/javascript,${encodeURIComponent(source.replace(/\bas const\b/g, ''))}`)

const bare = (text) => text.replace(/\.$/, '')
const front = (page, key) => new RegExp(`^${key}: "([^"\\n]*)"$`, 'm').exec(page)?.[1]

const description = /^description = "([^"\n]*)"$/m.exec(await read('../pyproject.toml'))?.[1]
const index = await read('index.md')
const title = front(index, 'title')

// A count in words: the list the words were written against, when the model wrote them.
const NUMBER =
  /\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty|dozens?|hundreds?|thousands?|millions?|single|double|triple|both|several|multiple|many)\b/i

const wrong = []

if (!description) wrong.push('pyproject.toml: no description to hold the banner to')
else {
  if (bare(BANNER) !== bare(description)) wrong.push(`BANNER: "${BANNER}" is not the repository's description, "${description}"`)
  if (!title?.endsWith(bare(description))) wrong.push(`index.md: the title "${title}" does not end with the repository's description`)
}

// What stands on a tab or a button, and in the drawing of the loop: one word each. The row of
// tabs' name and the pictures' descriptions are read out, not shown, and are phrases.
const { tabs: _row, ...buttons } = WORDS
const { alt: _drawing, ...loop } = LOOP
const single = { ...Object.fromEntries(Object.entries(buttons).map(([key, word]) => [`WORDS.${key}`, word])) }
for (const [key, word] of Object.entries(loop)) single[`LOOP.${key}`] = word
for (const scene of SCENES) single[`SCENES ${scene.key}: tab`] = scene.tab
for (const [where, word] of Object.entries(single)) {
  if (!/^\p{L}+$/u.test(word)) wrong.push(`${where}: "${word}" is not one word`)
}

// Every string there is, whatever it is for.
const strings = { BANNER, 'index.md title': title ?? '', 'index.md description': front(index, 'description') ?? '' }
for (const [key, word] of Object.entries(WORDS)) strings[`WORDS.${key}`] = word
for (const [key, word] of Object.entries(LOOP)) strings[`LOOP.${key}`] = word
for (const scene of SCENES) for (const [key, word] of Object.entries(scene)) strings[`SCENES ${scene.key}: ${key}`] = word
for (const [where, text] of Object.entries(strings)) {
  if (typeof text !== 'string' || !text) wrong.push(`${where}: not a string, or empty`)
  else if (/\d/.test(text)) wrong.push(`${where}: "${text}" has a digit in it`)
  else if (NUMBER.test(text)) wrong.push(`${where}: "${text}" has a number in it, "${NUMBER.exec(text)[0]}"`)
  else if (/[,;]/.test(text)) wrong.push(`${where}: "${text}" has a comma or a semicolon in it`)
}

if (wrong.length) {
  console.error(wrong.join('\n'))
  console.error(`\n${wrong.length} word rule${wrong.length === 1 ? '' : 's'} broken`)
  process.exit(1)
}
console.log(`${Object.keys(strings).length} strings, the banner the repository's description`)
