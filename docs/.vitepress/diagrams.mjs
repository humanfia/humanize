// The diagrams' dark twins: every hand-written diagram under public/diagrams is drawn for the
// light page, and this writes `<name>.dark.svg` beside each `<name>.svg`, the same drawing with
// every colour traded for its counterpart on the dark page.
//
//   pnpm diagrams            writes the twins
//   pnpm diagrams --check    fails if one is missing or is not what this writes
//
// A diagram is never drawn twice by hand: edit the light one and run this. The diagrams draw
// with a closed palette, which DARK below maps colour by colour; a colour that is not in it is
// an error here, and so in `pnpm check:pictures`, which holds each twin to this.

import { readdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const DIAGRAMS = fileURLToPath(new URL('../public/diagrams', import.meta.url))

/** The palette, light to dark. Paper and the sheets on it go deep, ink goes pale, the two
 *  greys of a rule and of a quiet word trade places, each accent is its brighter self, and each
 *  pale tint the deep tint of the same hue. */
export const DARK = {
  '#f4f8f9': '#172026', // the paper
  '#ffffff': '#0f161a', // a sheet on it, and what is written on an accent
  '#141a1f': '#e8f0f2', // ink
  '#435058': '#b3c3c8', // a second word
  '#b3c3c8': '#435058', // a rule
  '#5d6a72': '#9aa9b0', // a quiet word, an arrow
  '#0b7080': '#4fd8ea', // cyan
  '#b83a72': '#ff94c2', // pink
  '#5a8f00': '#a5d84a', // green
  '#80590c': '#e3b55a', // gold
  '#d9f1f4': '#12343b', // cyan, as a tint
  '#fbe3ee': '#3b1f2c', // pink, as a tint
  '#e6f2cf': '#27351a', // green, as a tint
  '#f6ecd2': '#3a3017', // gold, as a tint
}

/** A colour said any other way than as one of the palette's: by name, or as a function. */
const OTHERWISE = /\b(?:fill|stroke|stop-color|flood-color|color)\s*[=:]\s*["']?\s*(?!none\b|url\(|currentColor\b|inherit\b|#)([a-zA-Z(][^"';}\s]*)/g

/** The dark twin of a light diagram, and every colour of it that the palette does not know. */
export function darkened(light) {
  const unknown = new Set()
  // `url(#a)` and `href="#a"` name something in the file; every other `#…` is a colour.
  const dark = light.replace(/(url\(\s*|href=["'])?#([0-9a-fA-F]{3,8})\b/g, (said, naming, hex) => {
    if (naming) return said
    const to = DARK[`#${hex.toLowerCase()}`]
    if (!to) unknown.add(`#${hex}`)
    return to ?? said
  })
  for (const found of light.matchAll(OTHERWISE)) unknown.add(found[1])
  return { dark, unknown: [...unknown] }
}

/** Every light diagram's file name. */
export async function diagrams() {
  return (await readdir(DIAGRAMS)).filter((name) => name.endsWith('.svg') && !name.endsWith('.dark.svg')).sort()
}

/** What is wrong with the twins as they stand: nothing, where every one is what this writes. */
export async function stale() {
  const wrong = []
  for (const name of await diagrams()) {
    const { dark, unknown } = darkened(await readFile(join(DIAGRAMS, name), 'utf8'))
    for (const colour of unknown) wrong.push(`public/diagrams/${name}: ${colour} is not a colour of the diagrams' palette (diagrams.mjs)`)
    const twin = name.replace(/\.svg$/, '.dark.svg')
    const written = await readFile(join(DIAGRAMS, twin), 'utf8').catch(() => null)
    if (written === null) wrong.push(`public/diagrams/${twin}: missing; run pnpm diagrams`)
    else if (written !== dark) wrong.push(`public/diagrams/${twin}: not what its light diagram gives; run pnpm diagrams`)
  }
  return wrong
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (process.argv.includes('--check')) {
    const wrong = await stale()
    if (wrong.length) {
      console.error(wrong.join('\n'))
      process.exit(1)
    }
    console.log(`${(await diagrams()).length} diagrams, each with its dark twin`)
  } else {
    const wrong = []
    let written = 0
    for (const name of await diagrams()) {
      const { dark, unknown } = darkened(await readFile(join(DIAGRAMS, name), 'utf8'))
      for (const colour of unknown) wrong.push(`public/diagrams/${name}: ${colour} is not a colour of the diagrams' palette (diagrams.mjs)`)
      if (unknown.length) continue
      await writeFile(join(DIAGRAMS, name.replace(/\.svg$/, '.dark.svg')), dark)
      written++
    }
    if (wrong.length) {
      console.error(wrong.join('\n'))
      process.exit(1)
    }
    console.log(`${written} dark diagrams written`)
  }
}
