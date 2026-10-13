// The disk image's backgrounds, from src-tauri/dmg/background.svg beside them, each drawn at 1x
// and 2x and joined into one TIFF, which Finder shows sharp on any display:
// - background.tiff, the whole sheet, with the plate on opening an app signed ad hoc;
// - background-signed.tiff, the sheet above the plate, for an app signed with a Developer ID.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { Resvg } from '@resvg/resvg-js'

const dir = new URL('../src-tauri/dmg/', import.meta.url).pathname
const sheet = readFileSync(join(dir, 'background.svg'), 'utf8')
const signed = sheet
  .replace(/<g id="unsigned">[\s\S]*?\n {2}<\/g>\n/, '')
  .replace('viewBox="0 0 720 584" width="720" height="584"', 'viewBox="0 0 720 456" width="720" height="456"')
if (signed.includes('id="unsigned"') || !signed.includes('height="456"')) {
  throw new Error('background.svg no longer has the plate or the size this cuts')
}

const work = mkdtempSync(join(tmpdir(), 'dmg-background-'))
try {
  for (const [name, svg] of [['background', sheet], ['background-signed', signed]]) {
    const drawn = [1, 2].map((scale) => {
      const png = join(work, `${name}-${scale}x.png`)
      const resvg = new Resvg(svg, { fitTo: { mode: 'zoom', value: scale }, font: { loadSystemFonts: true } })
      writeFileSync(png, resvg.render().asPng())
      // Points, not pixels: 72 dpi at 1x and 144 at 2x, so both are the window's size.
      execFileSync('sips', ['-s', 'dpiWidth', `${72 * scale}`, '-s', 'dpiHeight', `${72 * scale}`, png], { stdio: 'ignore' })
      return png
    })
    execFileSync('tiffutil', ['-cathidpicheck', ...drawn, '-out', join(dir, `${name}.tiff`)], { stdio: 'inherit' })
  }
} finally {
  rmSync(work, { recursive: true, force: true })
}
