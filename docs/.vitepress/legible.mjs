// Every word on the Flows and Features pages, and on any other page a scene plays on, can be
// read on a phone: drawn at 11px or more, on a phone and on a tablet, with the animations
// playing and held still, and no page scrolls sideways.
//
// A diagram's labels are drawn at whatever size its camera and its viewBox leave them, so the
// build cannot see one shrink to a smudge. This loads the built site in Chromium, plays every
// scene through on a fake clock (so a 30-second scene takes a fraction of that), steps through
// every moment under reduced motion, and at each frame measures every piece of text that can be
// seen: its font size times every scale between it and the screen.
//
//   pnpm build && pnpm check:legible
//
// The first run wants a browser: `pnpm exec playwright install chromium`.
// `--page flows/rlar --width 390` narrows it down; `--report` prints every frame's offenders
// rather than the worst of each; `--clipped` also lists words cut off at the edge of what
// shows them, and `--overlap` words drawn over one another: a camera pushing in and a scene in
// motion do both on purpose, so neither is a failure, only something to look at.

import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { parseArgs } from 'node:util'

import { chromium } from 'playwright'
import { serve } from 'vitepress'

const DIST = new URL('./dist/', import.meta.url).pathname
const DOCS = new URL('../', import.meta.url).pathname
const BASE = '/humanize/'
const SECTIONS = ['features', 'flows']
const MIN = 11
const STEP = 150 // ms between frames while a scene plays
// While a scene plays, a word that is small for only a moment -- popping in from half its size,
// say -- is motion rather than a label: it fails once it has been too small for this many
// frames in a row, which is 300ms. Held still, every frame counts.
const HOLD = 3
const LONGEST = 90_000 // ms: no scene loops slower than this

const { values: args } = parseArgs({
  options: {
    page: { type: 'string', multiple: true },
    width: { type: 'string', multiple: true },
    motion: { type: 'string', multiple: true },
    report: { type: 'boolean', default: false },
    clipped: { type: 'boolean', default: false },
    overlap: { type: 'boolean', default: false },
    jobs: { type: 'string', default: '6' },
  },
})
// The flows' diagrams are drawn for the width they are given. The feature scenes are drawn for
// a 360-wide phone and scaled to fit, with their words lifted back on a narrower one: so 360
// too, the width where nothing is lifted.
const WIDTHS = {
  // and every other page a scene plays on
  features: [320, 360, 390, 768],
  flows: [320, 390, 768],
}
const widthsOf = (path) => (args.width ? args.width.map(Number) : WIDTHS[path.split('/')[0]] ?? WIDTHS.features)
const MOTIONS = args.motion ?? ['reduce', 'no-preference']

/** The built site under its base, served the way `pnpm preview` serves it, on a free port. */
async function start() {
  const app = await serve({ root: DOCS, port: 0 })
  const server = app.server
  if (!server.listening) await new Promise((resolve) => server.once('listening', resolve))
  return server
}

/** Every page of the Flows and Features sections, and any other page a scene plays on. */
async function pages() {
  const found = []
  for (const file of (await readdir(DIST, { recursive: true })).sort()) {
    if (!file.endsWith('.html') || file === '404.html') continue
    const html = await readFile(join(DIST, file), 'utf8')
    if (html.includes('http-equiv="refresh"')) continue
    const path = file.slice(0, -5).replaceAll('\\', '/')
    if (SECTIONS.includes(path.split('/')[0]) || /class="[^"]*\b(hmz-stage|hmz-flow-player)\b/.test(html)) found.push(path)
  }
  return found.filter((p) => !args.page || args.page.some((want) => p === want || p.startsWith(`${want}/`)))
}

/* ------------------------------------------------------------------------------------------
   In the page: every piece of text that can be seen, and how big it is drawn.
   ------------------------------------------------------------------------------------------ */

function measure({ scope, min, clipped, overlap }) {
  const roots = [...document.querySelectorAll(scope)]
  const out = []
  const boxes = []
  const opacityOf = (el) => {
    let o = 1
    for (let a = el; a && a !== document.documentElement; a = a.parentElement) {
      const s = getComputedStyle(a)
      if (s.display === 'none' || s.visibility === 'hidden') return 0
      o *= Number(s.opacity)
      if (o < 0.01) return 0
    }
    return o
  }
  /** The part of the screen an element can show in: the viewport's width, cut down by every
   *  ancestor that clips what overflows it. */
  const clipOf = (el) => {
    let box = { left: 0, top: -Infinity, right: innerWidth, bottom: Infinity }
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const s = getComputedStyle(a)
      if (s.overflowX === 'visible' && s.overflowY === 'visible') continue
      if (a instanceof SVGElement && !(a instanceof SVGSVGElement)) continue
      const r = a.getBoundingClientRect()
      box = {
        left: Math.max(box.left, r.left),
        top: Math.max(box.top, r.top),
        right: Math.min(box.right, r.right),
        bottom: Math.min(box.bottom, r.bottom),
      }
    }
    return box
  }
  /** How much bigger than its own font size an HTML element is drawn: every CSS transform and
   *  zoom on the way up. */
  const cssScale = (el) => {
    let k = 1
    for (let a = el; a && a !== document.documentElement; a = a.parentElement) {
      const s = getComputedStyle(a)
      if (s.transform && s.transform !== 'none') {
        const m = new DOMMatrix(s.transform)
        k *= Math.hypot(m.c, m.d)
      }
      if (s.zoom && s.zoom !== '1') k *= Number(s.zoom)
    }
    return k
  }
  for (const root of roots) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    const seen = new Set()
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.data.trim()) continue
      const el = node.parentElement
      if (!el || seen.has(el)) continue
      seen.add(el)
      if (el.closest('pre, code, .vp-code-group, script, style, title, desc, .VPBadge, [data-legible="skip"]')) {
        if (!el.closest('svg') && !el.closest('.hmz-panel')) continue
      }
      if (el.closest('title, desc, .sr-only, .visually-hidden')) continue
      const range = document.createRange()
      range.selectNodeContents(node)
      const rect = range.getBoundingClientRect()
      if (rect.width < 1 || rect.height < 1) continue
      const o = opacityOf(el)
      if (o < 0.4) continue
      const clip = clipOf(el)
      const cx = (rect.left + rect.right) / 2
      const cy = (rect.top + rect.bottom) / 2
      if (cx < clip.left || cx > clip.right || cy < clip.top || cy > clip.bottom) continue
      const font = parseFloat(getComputedStyle(el).fontSize)
      let px
      if (el instanceof SVGElement) {
        const m = el.getScreenCTM()
        if (!m) continue
        px = font * Math.hypot(m.c, m.d)
      } else px = font * cssScale(el)
      const text = node.data.trim().replace(/\s+/g, ' ').slice(0, 40)
      const where = el.closest('[class]')?.getAttribute('class')?.split(' ')[0] ?? el.tagName
      const out_of = rect.left < clip.left - 1 || rect.right > clip.right + 1
      if (overlap && o > 0.6) boxes.push({ el, rect, text })
      if (px < min - 0.05) out.push({ kind: 'small', text, px: Math.round(px * 10) / 10, where })
      if (clipped && out_of) out.push({ kind: 'offscreen', text, px: Math.round(px * 10) / 10, where })
    }
  }
  // Two words drawn over each other, which only `--overlap` looks for: a scene in motion
  // crosses its own words on purpose, so this is for looking at, not for failing on.
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i]
      const b = boxes[j]
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue
      const w = Math.min(a.rect.right, b.rect.right) - Math.max(a.rect.left, b.rect.left)
      const h = Math.min(a.rect.bottom, b.rect.bottom) - Math.max(a.rect.top, b.rect.top)
      if (w <= 0 || h <= 0) continue
      const least = Math.min(a.rect.width * a.rect.height, b.rect.width * b.rect.height)
      if (w * h > 0.2 * least) out.push({ kind: 'overlap', text: `${a.text} / ${b.text}`, px: 0, where: 'text' })
    }
  }
  const wide = document.documentElement.scrollWidth - document.documentElement.clientWidth
  if (wide > 1) out.push({ kind: 'scrolls', text: `page is ${wide}px wider than the screen`, px: 0, where: 'page' })
  return out
}

/* ------------------------------------------------------------------------------------------
   Driving a page.
   ------------------------------------------------------------------------------------------ */

const SCENES = '.hmz-flow-player, .hmz-stage'

async function check(browser, origin, path, width, motion) {
  const context = await browser.newContext({
    viewport: { width, height: 844 },
    reducedMotion: motion,
    colorScheme: 'light',
    deviceScaleFactor: 1,
  })
  const page = await context.newPage()
  await page.clock.install()
  const found = []
  const add = (frame, list) => {
    for (const item of list) found.push({ path, width, motion, frame, ...item })
  }
  // A scene that throws draws nothing, which would pass: a script error is a failure too.
  page.on('pageerror', (error) => add('page', [{ kind: 'error', text: String(error.message).slice(0, 120), px: 0, where: 'script' }]))
  try {
    await page.goto(`${origin}${BASE}${path}`, { waitUntil: 'load' })
    await page.evaluate(() => document.fonts.ready)
    await page.clock.runFor(1500)
    // The whole page on the Flows and Features pages; elsewhere only its scenes.
    if (SECTIONS.includes(path.split('/')[0])) add('page', await page.evaluate(measure, { scope: '.VPContent', min: MIN, clipped: args.clipped, overlap: args.overlap }))

    const count = await page.locator(SCENES).count()
    for (let i = 0; i < count; i += 1) {
      const scene = page.locator(SCENES).nth(i)
      const player = await scene.evaluate((el) => el.classList.contains('hmz-flow-player'))
      await scene.scrollIntoViewIfNeeded()
      await page.clock.runFor(600)
      const name = `${player ? 'flow' : 'stage'}#${i}`
      await scene.evaluate((el, i) => el.setAttribute('data-legible-scene', String(i)), i)
      const scope = `[data-legible-scene="${i}"]`
      const look = async (frame) => add(`${name} ${frame}`, await page.evaluate(measure, { scope, min: MIN, clipped: args.clipped, overlap: args.overlap }))
      if (motion === 'reduce') {
        await look('still')
        // A run too wide to read whole is drawn full size in a frame that scrolls: along it.
        const along = await scene.evaluate((el) => {
          const s = el.querySelector('.scroller')
          return s ? Math.ceil(s.scrollWidth / s.clientWidth) : 0
        })
        for (let k = 1; k < along; k += 1) {
          await scene.evaluate((el, k) => {
            const s = el.querySelector('.scroller')
            s.scrollLeft = k * s.clientWidth
          }, k)
          await page.clock.runFor(100)
          await look(`still, scrolled ${k}`)
        }
        if (player) {
          // Step through every moment, until the steps come round to the first one again.
          let last = -1
          for (let k = 1; k <= 60; k += 1) {
            await scene.getByRole('button', { name: 'the moment after' }).click()
            await page.clock.runFor(300)
            const at = await position(scene, true)
            if (at < last) break
            last = at
            await look(`step ${k}`)
          }
        } else {
          const chapters = scene.locator('.chapters button')
          const n = await chapters.count()
          for (let k = 0; k < n; k += 1) {
            await chapters.nth(k).click()
            await page.clock.runFor(300)
            await look(`chapter ${k + 1}`)
          }
        }
      } else {
        // Play it through once, from the top, looking at every frame.
        if (player) await scene.getByRole('button', { name: 'from the start' }).click()
        else await scene.locator('.chapters button').first().click()
        let last = -1
        let wrapped = false
        let runs = new Map()
        for (let ms = 0; ms < LONGEST && !wrapped; ms += STEP) {
          await page.clock.runFor(STEP)
          const now = await page.evaluate(measure, { scope, min: MIN, clipped: args.clipped, overlap: args.overlap })
          const next = new Map()
          for (const item of now) {
            const key = `${item.kind}|${item.where}|${item.text}`
            const run = (runs.get(key) ?? 0) + 1
            next.set(key, run)
            if (run >= HOLD) add(`${name} ${(ms / 1000).toFixed(1)}s`, [item])
          }
          runs = next
          const at = await position(scene, player)
          if (at === null) break
          if (at < last - 0.5) wrapped = true
          last = at
        }
      }
    }
  } finally {
    await context.close()
  }
  return found
}

/** How far through its loop a scene is, as a number that falls when it starts again. */
async function position(scene, player) {
  return scene.evaluate((el, player) => {
    if (player) return Number(el.querySelector('.scrub')?.value ?? 0) / 100
    const on = [...el.querySelectorAll('.chapters li')].findIndex((li) => li.classList.contains('on'))
    if (on < 0) return null
    const fill = el.querySelectorAll('.chapters .fill')[on]
    const m = fill ? new DOMMatrix(getComputedStyle(fill).transform) : null
    return on + (m ? m.a : 0)
  }, player)
}

async function main() {
  const list = await pages()
  const server = await start()
  const origin = `http://localhost:${server.address().port}`
  const browser = await chromium.launch()
  const jobs = []
  for (const path of list) for (const width of widthsOf(path)) for (const motion of MOTIONS) jobs.push({ path, width, motion })
  const found = []
  let next = 0
  const worker = async () => {
    while (next < jobs.length) {
      const { path, width, motion } = jobs[next++]
      // One page that will not load or click is that page's failure, not the end of the run.
      const got = await check(browser, origin, path, width, motion).catch((error) => [
        { path, width, motion, frame: 'page', kind: 'error', text: String(error.message).split('\n')[0].slice(0, 120), px: 0, where: 'check' },
      ])
      found.push(...got)
      process.stdout.write(got.length ? '!' : '.')
    }
  }
  try {
    await Promise.all(Array.from({ length: Number(args.jobs) }, worker))
  } finally {
    process.stdout.write('\n')
    await browser.close()
    server.close()
  }

  if (args.report) {
    for (const f of found) console.log(`${f.path} @${f.width} ${f.motion} [${f.frame}] ${f.kind} ${f.px}px ${f.where}: ${f.text}`)
  }
  // The worst case of each offender, once.
  const worst = new Map()
  for (const f of found) {
    const key = `${f.path}|${f.width}|${f.motion}|${f.kind}|${f.where}|${f.text}`
    const had = worst.get(key)
    if (!had || f.px < had.px) worst.set(key, { ...f, frames: (had?.frames ?? 0) + 1 })
    else had.frames += 1
  }
  const rows = [...worst.values()].sort((a, b) => a.path.localeCompare(b.path) || a.width - b.width || a.px - b.px)
  for (const f of rows) {
    console.log(`${f.path} @${f.width} ${f.motion} ${f.kind} ${f.px}px in .${f.where} "${f.text}" (${f.frames} frames, e.g. ${f.frame})`)
  }
  console.log(`${jobs.length} page loads, ${rows.length} problems`)
  process.exitCode = rows.length ? 1 : 0
}

await main()
