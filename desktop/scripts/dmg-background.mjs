// The disk image's background, src-tauri/dmg/background.tiff, from background.svg beside it:
// drawn at 1x and 2x and joined into one TIFF, which Finder shows sharp on any display.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { Resvg } from '@resvg/resvg-js'

const dir = new URL('../src-tauri/dmg/', import.meta.url).pathname
const svg = readFileSync(join(dir, 'background.svg'))
const work = mkdtempSync(join(tmpdir(), 'dmg-background-'))
try {
  const drawn = [1, 2].map((scale) => {
    const png = join(work, `background-${scale}x.png`)
    const resvg = new Resvg(svg, { fitTo: { mode: 'zoom', value: scale }, font: { loadSystemFonts: true } })
    writeFileSync(png, resvg.render().asPng())
    // Points, not pixels: 72 dpi at 1x and 144 at 2x, so both are the window's size.
    execFileSync('sips', ['-s', 'dpiWidth', `${72 * scale}`, '-s', 'dpiHeight', `${72 * scale}`, png], { stdio: 'ignore' })
    return png
  })
  execFileSync('tiffutil', ['-cathidpicheck', ...drawn, '-out', join(dir, 'background.tiff')], { stdio: 'inherit' })
} finally {
  rmSync(work, { recursive: true, force: true })
}
