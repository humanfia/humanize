// Every word on the Flows and Features pages, and on any other page a scene plays on, can be
// read on a phone: drawn at 11px or more, on a phone and on a tablet, with the animations
// playing and held still, and no page scrolls sideways.
//
// A diagram's labels are drawn at whatever size its camera and its viewBox leave them, so the
// build cannot see one shrink to a smudge. This loads the built site in Chromium and, at each
// moment it looks at, measures every piece of text that can be seen: its font size times every
// scale between it and the screen.
//
// It never waits on a clock, so it says the same thing however busy the machine is. The page's
// clock is stopped and moves only when this moves it; a playing scene is not played but held
// still at one moment of its timeline after another (each scene lists itself for that: see
// `theme/motion/probe.ts`), every few hundredths of a second from its start to its end; and
// CSS animations, which the browser runs on a clock of its own, are held still the same way.
// Under reduced motion it steps through every moment with the scene's own buttons.
//
//   pnpm build && pnpm check:legible
//
// The first run wants a browser: `pnpm exec playwright install chromium`.
// `--page flows/rlar --width 390` narrows it down; `--report` prints every moment's offenders
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
const HEIGHT = 844 // px: a phone's screen
// A moving scene is looked at every STEP seconds of its own timeline.
const STEP = 0.05
// While a scene plays, a word that is small for only a moment -- popping in from half its size,
// say -- is motion rather than a label: it fails once it has been too small for this long of
// the scene's timeline, or at all where the scene comes to rest. Held still, every moment
// counts.
const HOLD = 0.3
// The page's clock, stopped here.
const EPOCH = Date.parse('2026-01-01T00:00:00Z')

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

function measure({ scope, skip, min, clipped, overlap }) {
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
      if (skip && el.closest(skip)) continue
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

/** Every CSS animation paused `t` ms in, and every CSS transition at its end: the browser runs
 *  both on a clock of its own, which the page's stopped one does not stop. */
function hold(t) {
  // Style now, so every transition the last change started is there to finish.
  document.documentElement.getBoundingClientRect()
  for (const a of document.getAnimations()) {
    if (a instanceof CSSTransition) a.finish()
    else {
      a.pause()
      a.currentTime = t
    }
  }
}

/** How long the page's CSS animations that move words take to come round, outside `skip`. */
function cycle(skip) {
  let longest = 0
  for (const a of document.getAnimations()) {
    const target = a.effect?.target
    if (a instanceof CSSTransition || !target || a.effect.pseudoElement || target.closest(skip) || !target.textContent?.trim()) continue
    const { delay, duration } = a.effect.getComputedTiming()
    longest = Math.max(longest, (delay || 0) + (Number(duration) || 0))
  }
  return longest
}

/** Once the browser has drawn a frame: by then every ResizeObserver it owed is told. The stopped
 *  clock holds back `requestAnimationFrame`, not this. */
function drawn() {
  return new Promise((resolve) => {
    const seen = new ResizeObserver(() => {
      seen.disconnect()
      resolve()
    })
    seen.observe(document.documentElement)
  })
}

/** The scene `el` as it lists itself in `window.__hmzScenes`. */
function probe(el) {
  return (window.__hmzScenes ?? []).find((one) => one.root() === el)
}

/** Whether the page has started: the app mounted, and every scene built and listed (under
 *  reduced motion a flow's diagram has no timeline to list). */
function ready(moving) {
  if (!document.querySelector('#app')?.__vue_app__) return false
  for (const el of document.querySelectorAll('.hmz-stage, .hmz-flow-player')) {
    if (!moving && el.classList.contains('hmz-flow-player')) continue
    if (!(window.__legible.probe(el)?.duration() > 0)) return false
  }
  return true
}

/** Look at each of `times`: a scene's timeline held there (seconds), or, with no scene, the
 *  page's CSS animations (also seconds). */
async function sweep({ scene, times, look }) {
  const it = scene === undefined ? null : window.__legible.probe(document.querySelector(`[data-legible-scene="${scene}"]`))
  const out = []
  for (const t of times) {
    if (it) await it.seek(t)
    window.__legible.hold(it ? 0 : t * 1000)
    out.push(window.__legible.measure(look))
  }
  return out
}

// What the page gets before any of its own scripts run.
const PAGE = `window.__legible = { measure: ${measure}, hold: ${hold}, cycle: ${cycle}, drawn: ${drawn}, probe: ${probe}, ready: ${ready}, sweep: ${sweep} }`

/* ------------------------------------------------------------------------------------------
   Driving a page.
   ------------------------------------------------------------------------------------------ */

const SCENES = '.hmz-flow-player, .hmz-stage'

/** Let the page catch up with what it was just asked to do: a frame drawn, so every observer
 *  is told, and every font in, then the animation frames those asked for, on the stopped clock. */
async function settle(page) {
  for (let k = 0; k < 3; k += 1) {
    await page.evaluate(async () => {
      await window.__legible.drawn()
      await document.fonts.ready
    })
    await page.clock.runFor(100)
  }
}

/** Wait for the page to start, however long a busy machine takes to get it there. A page looked
 *  at before is only the server's markup. */
async function started(page, motion) {
  for (let k = 0; k < 200; k += 1) {
    if (await page.evaluate((moving) => window.__legible.ready(moving), motion !== 'reduce')) return settle(page)
    await settle(page)
  }
  throw new Error('the page never started: its app did not mount, or a scene did not list itself in window.__hmzScenes')
}

/** Times from 0 to `end` every STEP, and `extra` among them, in order. */
function grid(end, extra = []) {
  const n = Math.floor(end / STEP + 1e-9)
  const all = [...Array.from({ length: n + 1 }, (_, k) => Math.round(k * STEP * 1000) / 1000), ...extra.filter((t) => t >= 0 && t <= end)]
  return [...new Set(all)].sort((a, b) => a - b)
}

/** What fails in a run of moments looked at in order: anything still too small HOLD seconds
 *  after it first was, at every moment, or at a moment in `rest`. */
function judge(times, samples, rest, name) {
  const failed = []
  let since = new Map()
  times.forEach((t, k) => {
    const next = new Map()
    for (const item of samples[k]) {
      const key = `${item.kind}|${item.where}|${item.text}`
      const first = since.get(key) ?? t
      next.set(key, first)
      const still = rest.has(t)
      const always = first === times[0] && k === times.length - 1
      if (still || always || t - first >= HOLD - 1e-9) failed.push({ frame: `${name} ${t.toFixed(2)}s${still ? ' at rest' : ''}`, ...item })
    }
    since = next
  })
  return failed
}

async function check(browser, origin, path, width, motion) {
  const context = await browser.newContext({
    viewport: { width, height: HEIGHT },
    reducedMotion: motion,
    colorScheme: 'light',
    deviceScaleFactor: 1,
  })
  await context.addInitScript(PAGE)
  const page = await context.newPage()
  // Installed, the page's clock still runs at the wall clock's pace: stopped, it moves only
  // when this moves it, so what the page has done by each look is the same every run.
  await page.clock.install({ time: EPOCH })
  await page.clock.pauseAt(EPOCH + 1000)
  const found = []
  const add = (frame, list) => {
    for (const item of list) found.push({ path, width, motion, frame, ...item })
  }
  const opts = { min: MIN, clipped: args.clipped, overlap: args.overlap }
  // A scene that throws draws nothing, which would pass: a script error is a failure too.
  page.on('pageerror', (error) => add('page', [{ kind: 'error', text: String(error.message).slice(0, 120), px: 0, where: 'script' }]))
  try {
    await page.goto(`${origin}${BASE}${path}`, { waitUntil: 'load' })
    await started(page, motion)
    // The whole page on the Flows and Features pages, but its scenes, which are looked at one by
    // one below; elsewhere only its scenes.
    if (SECTIONS.includes(path.split('/')[0])) {
      // Down the page a screen at a time, so every entrance plays -- the cards of a grid rising
      // into place as they are scrolled to, say -- and then every one is over.
      if (motion !== 'reduce') {
        const tall = await page.evaluate(() => document.documentElement.scrollHeight)
        for (let y = HEIGHT; y < tall; y += HEIGHT) {
          await page.evaluate((y) => window.scrollTo(0, y), y)
          await settle(page)
        }
        await page.clock.runFor(3000)
      }
      const look = { scope: '.VPContent', skip: SCENES, ...opts }
      const end = motion === 'reduce' ? 0 : await page.evaluate((skip) => window.__legible.cycle(skip), SCENES)
      const times = grid(end / 1000)
      const samples = await page.evaluate((a) => window.__legible.sweep(a), { times, look })
      for (const { frame, ...item } of judge(times, samples, new Set(), 'page')) add(frame, [item])
    }

    const count = await page.locator(SCENES).count()
    for (let i = 0; i < count; i += 1) {
      const scene = page.locator(SCENES).nth(i)
      const player = await scene.evaluate((el) => el.classList.contains('hmz-flow-player'))
      await scene.scrollIntoViewIfNeeded()
      await settle(page)
      const name = `${player ? 'flow' : 'stage'}#${i}`
      await scene.evaluate((el, i) => el.setAttribute('data-legible-scene', String(i)), i)
      const look = { scope: `[data-legible-scene="${i}"]`, ...opts }
      const still = async (frame) => {
        const [now] = await page.evaluate((a) => window.__legible.sweep(a), { times: [0], look })
        add(`${name} ${frame}`, now)
      }
      if (motion === 'reduce') {
        await still('still')
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
          await settle(page)
          await still(`still, scrolled ${k}`)
        }
        if (player) {
          // Step through every moment, until the steps come round to the first one again.
          let last = -1
          for (let k = 1; k <= 60; k += 1) {
            await scene.getByRole('button', { name: 'the moment after' }).click()
            await settle(page)
            const at = await scene.evaluate((el) => Number(el.querySelector('.scrub')?.value ?? 0))
            if (at < last) break
            last = at
            await still(`step ${k}`)
          }
        } else {
          const chapters = scene.locator('.chapters button')
          const n = await chapters.count()
          for (let k = 0; k < n; k += 1) {
            await chapters.nth(k).click()
            await settle(page)
            await still(`chapter ${k + 1}`)
          }
        }
      } else {
        // Its timeline, from the start to the end, held still at every STEP and wherever it
        // comes to rest.
        const plan = await scene.evaluate((el) => {
          const it = window.__legible.probe(el)
          return it ? { duration: it.duration(), settled: it.settled() } : null
        })
        if (!plan || !(plan.duration > 0)) {
          add(name, [{ kind: 'error', text: 'the scene does not list itself in window.__hmzScenes', px: 0, where: 'probe' }])
          continue
        }
        // To the millisecond, and never past the end, which a duration like 14.3999… would round past.
        const rest = plan.settled.map((t) => Math.min(Math.round(Math.max(t, 0) * 1000) / 1000, plan.duration))
        const times = grid(plan.duration, rest)
        const samples = await page.evaluate((a) => window.__legible.sweep(a), { scene: i, times, look })
        for (const { frame, ...item } of judge(times, samples, new Set(rest), name)) add(frame, [item])
      }
    }
  } finally {
    await context.close()
  }
  return found
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
