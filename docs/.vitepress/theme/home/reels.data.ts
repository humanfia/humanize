// What the stage has to know of each reel before it is loaded: how large it is and how long it
// runs. Read from the files themselves when the site is built, so a scene that is shot again
// never leaves a number here behind.
import { readFileSync } from 'node:fs'
import { basename } from 'node:path'
import { defineLoader } from 'vitepress'

export interface Reel {
  width: number
  height: number
  /** How long one loop of it is, in seconds; 0 for a picture that does not move. */
  seconds: number
}

declare const data: Record<string, Reel>
export { data }

export default defineLoader({
  watch: ['../../../public/shots/home-*.svg'],
  load(files): Record<string, Reel> {
    const reels: Record<string, Reel> = {}
    for (const file of files) {
      const name = basename(file, '.svg')
      // The dark twin of a picture is the same size and plays in the same time.
      if (name.endsWith('.dark')) continue
      const head = readFileSync(file, 'utf8')
      const box = /viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(head)
      const runs = /animation:\w+ ([\d.]+)s/.exec(head)
      if (box) reels[name] = { width: Number(box[1]), height: Number(box[2]), seconds: runs ? Number(runs[1]) : 0 }
    }
    return reels
  },
})
