// The Windows installer's pictures, from src-tauri/windows/*.svg beside them, each drawn into the
// 24-bit BMP NSIS takes: sidebar.bmp for the welcome and finish pages, header.bmp for the rest.
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { Resvg } from '@resvg/resvg-js'

const dir = fileURLToPath(new URL('../src-tauri/windows/', import.meta.url))

/** A BMP of `width` x `height` RGBA pixels: rows bottom up, blue first, each padded to 4 bytes. */
function bmp(width, height, rgba) {
  const row = Math.ceil((width * 3) / 4) * 4
  const out = Buffer.alloc(54 + row * height)
  out.write('BM', 0)
  out.writeUInt32LE(out.length, 2)
  out.writeUInt32LE(54, 10)
  out.writeUInt32LE(40, 14)
  out.writeInt32LE(width, 18)
  out.writeInt32LE(height, 22)
  out.writeUInt16LE(1, 26)
  out.writeUInt16LE(24, 28)
  out.writeUInt32LE(row * height, 34)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const from = (y * width + x) * 4
      const to = 54 + (height - 1 - y) * row + x * 3
      out[to] = rgba[from + 2]
      out[to + 1] = rgba[from + 1]
      out[to + 2] = rgba[from]
    }
  }
  return out
}

for (const name of ['sidebar', 'header']) {
  const drawn = new Resvg(readFileSync(`${dir}${name}.svg`, 'utf8')).render()
  writeFileSync(`${dir}${name}.bmp`, bmp(drawn.width, drawn.height, drawn.pixels))
}
