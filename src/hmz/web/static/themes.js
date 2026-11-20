// Themes, as an editor keeps them: those Humanize comes with and any made in this browser, each
// a light side and a dark side under one name -- the colours a side changes and a picture for
// any of the page's large planes, still or drawn moving. One theme is chosen, whole, and which
// of its sides the page is drawn in is chosen apart: Light, Dark, or Auto, its light where the
// system is light and its dark where it is dark. A theme made here is written out whole as a
// `.hmztheme` file, which is read back in here or in any other browser.
//
// What a side changes is kept beside the choice, for theme.js to paint before the page is
// drawn -- the sides of the theme chosen as well, where Humanize comes with it; its pictures,
// too large for that, are kept in the browser's database and painted after.

import { t } from './i18n.js'
import { OWN, PAIRS } from './presets.js'
import { keep, kept } from './shell.js'
import { migrated } from './themed.js'

export { OWN }

/** The colours a side sets, by what they are of, each by its token in style.css. */
export const COLOURS = [
  [t('Backgrounds'), [['paper', t('Page')], ['side', t('Sidebar')], ['surface', t('Surface')], ['raised', t('Raised')]]],
  [t('Text'), [['ink', t('Text')], ['ink-2', t('Secondary')], ['ink-3', t('Muted')], ['on-ink', t('Inverse')], ['on-fill', t('On colour')], ['link', t('Link')]]],
  [t('Controls'), [['control', t('Button')], ['control-ink', t('Button text')], ['primary', t('Primary')], ['on-primary', t('Primary text')], ['field', t('Field')], ['edge', t('Edge')]]],
  [t('Lines'), [['line', t('Line')], ['line-strong', t('Strong line')], ['hover', t('Hover')], ['scrim', t('Scrim')]]],
  [
    t('Accents'),
    [['green', t('Brand')], ['cyan', t('Accent')], ['cyan-ink', t('Accent text')], ['pink', t('Highlight')], ['pink-ink', t('Highlight text')], ['lavender', t('Tertiary')], ['gold', t('Budget')], ['done', t('Success')], ['fail', t('Danger')]],
  ],
  [t('Graph'), [1, 2, 3, 4, 5, 6].map((n) => [`lane-${n}`, t('Lane {n}', { n })])],
]

/** Every colour's token. */
const TOKENS = new Set(COLOURS.flatMap(([, tokens]) => tokens.map(([token]) => token)))

/** The large planes a picture can be set behind, each by the name its properties carry. */
export const AREAS = [['page', t('Page')], ['sidebar', t('Sidebar')], ['panel', t('Panel')], ['dialog', t('Dialog')]]

/** How a picture fills its plane. */
export const FITS = { cover: t('Cover'), contain: t('Fit'), tile: t('Tile') }

/** What a picture may be: what a browser draws as an image, an SVG's animation included. */
const PICTURE = /^data:image\/(png|jpeg|gif|webp|avif|svg\+xml)(;[^,]*)?,/

/** The sides made here: two of each theme, a light and a dark, joined by the theme's key as `pair`. */
function made() {
  try {
    return JSON.parse(kept('hmz-themes', '[]') || '[]')
  } catch {
    return []
  }
}

/** Every theme: those Humanize comes with, then those made here, each by its key and its name. */
export function themes() {
  const mine = new Map()
  for (const one of made()) if (!mine.has(one.pair)) mine.set(one.pair, { key: one.pair, name: one.name, mine: true })
  return [...PAIRS, ...mine.values()]
}

/** A theme's light and dark, in that order. */
export function sides(key) {
  return [...OWN, ...made()].filter((one) => one.pair === key).sort((a, b) => (a.base === 'light' ? -1 : 1) - (b.base === 'light' ? -1 : 1))
}

/** One side, by its id. */
export function side(id) {
  return [...OWN, ...made()].find((one) => one.id === id) || null
}

/** Which theme is chosen, by its key: Humanize's own where none is. */
export function chosen() {
  const key = kept('hmz-pair', null)
  return key && sides(key).length === 2 ? key : 'humanize'
}

/** Chooses a theme, both its sides at once. */
export function choose(key) {
  keep('hmz-pair', key === 'humanize' ? null : key)
  paint()
}

/** Which side is drawn: `light`, `dark`, or `auto`, the one the system asks for, where none is chosen. */
export function mode() {
  const said = kept('hmz-mode', null)
  return said === 'light' || said === 'dark' ? said : 'auto'
}

/** Chooses which side is drawn: `light`, `dark` or `auto`. */
export function prefer(said) {
  keep('hmz-mode', said === 'light' || said === 'dark' ? said : null)
  paint()
}

/** The side of a theme, the one chosen where none is given, that is drawn now. */
export function shown(key = chosen()) {
  const dark = mode() === 'auto' ? matchMedia('(prefers-color-scheme: dark)').matches : mode() === 'dark'
  return sides(key)[dark ? 1 : 0]
}

/**
 * Keeps the sides of the theme chosen, where Humanize comes with it, beside those made here,
 * for theme.js, which cannot read this file before the page is drawn, to paint them.
 */
function hand() {
  const key = chosen()
  const said = JSON.stringify(OWN.filter((one) => one.pair === key && Object.keys(one.colors).length))
  if (kept('hmz-painted', '[]') !== said) keep('hmz-painted', said)
}

/** Keeps a side made here, new or changed. */
export function save(one) {
  const all = made()
  const at = all.findIndex((other) => other.id === one.id)
  if (at < 0) all.push(one)
  else all[at] = one
  keep('hmz-themes', JSON.stringify(all))
}

/** A new id, for a theme (`p`) or a side (`t`) made here. */
function fresh(kind) {
  return `${kind}${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

/** Gives a theme made here a name: both its sides have it. */
export function rename(key, name) {
  for (const one of made()) if (one.pair === key) save({ ...one, name })
}

/** Forgets a theme made here, both its sides and their pictures; chosen, Humanize's own is shown instead. */
export async function remove(key) {
  const gone = sides(key)
  keep('hmz-themes', JSON.stringify(made().filter((one) => one.pair !== key)))
  if (kept('hmz-pair', null) === key) keep('hmz-pair', null)
  await Promise.all(gone.flatMap((one) => AREAS.map(([area]) => picture(one.id, area, null))))
  paint()
}

/** A new theme, of the light and the dark given: their colours and pictures copied. Says its two sides. */
export async function create(from, name) {
  const key = fresh('p')
  const said = unique(name)
  const two = []
  for (const it of from) {
    const one = { id: fresh('t'), name: said, base: it.base, pair: key, colors: { ...it.colors }, images: {} }
    for (const [area, set] of Object.entries(it.images || {})) {
      const data = await picture(it.id, area)
      if (data) {
        await picture(one.id, area, data)
        one.images[area] = { ...set }
      }
    }
    save(one)
    two.push(one)
  }
  return two
}

/** A name no theme has: the one given, or it numbered. */
function unique(name) {
  const taken = new Set(themes().map((one) => one.name))
  let said = name
  for (let n = 2; taken.has(said); n++) said = `${name} ${n}`
  return said
}

/**
 * Paints the side given -- one being edited -- or the one shown of the theme chosen: its
 * colours at once, as theme.js does, and its pictures once read, each the latest asked for alone.
 */
let painting = 0
export async function paint(given) {
  hand()
  const mine = ++painting
  const one = window.hmzPaint(given)
  const root = document.documentElement
  const set = {}
  await moved
  for (const [area, how] of Object.entries(one.images || {})) {
    const data = await picture(one.id, area).catch(() => null)
    if (!data) continue
    set[area] = { data: still.matches ? await held(data) : data, fit: how.fit }
  }
  if (mine !== painting) return
  for (const [area] of AREAS) {
    const it = set[area]
    if (!it) continue
    root.style.setProperty(`--${area}-image`, `url("${it.data}")`)
    root.style.setProperty(`--${area}-size`, it.fit === 'tile' ? 'auto' : it.fit || 'cover')
    root.style.setProperty(`--${area}-repeat`, it.fit === 'tile' ? 'repeat' : 'no-repeat')
  }
}

/** Where motion is asked to be reduced, a picture is shown as it is first drawn, and held. */
const still = matchMedia('(prefers-reduced-motion: reduce)')
still.addEventListener('change', () => paint())
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => paint())
window.addEventListener('storage', (event) => ['hmz-pair', 'hmz-mode', 'hmz-themes'].includes(event.key) && paint())

const stills = new Map()

/** A picture's first frame, as a PNG; or the picture as it is, where it cannot be drawn. */
function held(data) {
  if (!stills.has(data)) {
    stills.set(
      data,
      new Promise((resolve) => {
        const image = new Image()
        image.onload = () => {
          try {
            const canvas = document.createElement('canvas')
            canvas.width = image.naturalWidth || 1600
            canvas.height = image.naturalHeight || 1000
            canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height)
            resolve(canvas.toDataURL('image/png'))
          } catch {
            resolve(data)
          }
        }
        image.onerror = () => resolve(data)
        image.src = data
      }),
    )
  }
  return stills.get(data)
}

/** The browser's database of pictures, opened once it is first needed. */
let base = null
function pictures(mode, act) {
  base ||= new Promise((resolve, reject) => {
    const asked = indexedDB.open('hmz', 1)
    asked.onupgradeneeded = () => asked.result.createObjectStore('pictures')
    asked.onsuccess = () => resolve(asked.result)
    asked.onerror = () => reject(asked.error)
  })
  return base.then(
    (db) =>
      new Promise((resolve, reject) => {
        const doing = db.transaction('pictures', mode)
        const asked = act(doing.objectStore('pictures'))
        doing.oncomplete = () => resolve(asked.result)
        doing.onerror = () => reject(doing.error)
      }),
  )
}

/** Reads a side's picture for an area, as a data URL; or, given one, keeps it there, or with null forgets it. */
export function picture(id, area, data) {
  const key = `${id}/${area}`
  if (data === undefined) return pictures('readonly', (store) => store.get(key)).then((got) => got || null)
  return pictures('readwrite', (store) => (data ? store.put(data, key) : store.delete(key)))
}

/** Reads a file the user gave as a data URL, refusing what is not a picture. */
export function readPicture(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => (PICTURE.test(reader.result) ? resolve(reader.result) : reject(new Error(t('{name} is not a picture', { name: file.name }))))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

/** Whether a browser draws what is said as a colour. */
export function isColour(said) {
  return typeof said === 'string' && said.trim() !== '' && CSS.supports('color', said.trim())
}

/** What a side sets, with its pictures, as a `.hmztheme` file holds it. */
async function look(one) {
  const images = {}
  for (const [area, how] of Object.entries(one.images || {})) {
    const data = await picture(one.id, area)
    if (data) images[area] = { fit: how.fit || 'cover', data }
  }
  return { colors: { ...one.colors }, images }
}

/** Saves a theme, by its key, whole as a `.hmztheme` file, as the browser saves a download. */
export async function exported(key) {
  const [light, dark] = sides(key)
  const said = { hmztheme: 1, name: light.name, light: await look(light), dark: await look(dark) }
  const blob = new Blob([JSON.stringify(said, null, 2)], { type: 'application/json' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${said.name.replace(/[^\p{L}\p{N}._ -]+/gu, '').trim() || 'theme'}.hmztheme`
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(link.href), 60000)
}

/**
 * Makes a theme of a `.hmztheme` file's text, keeping what it says that a theme can hold; a
 * file that holds one side alone, as an earlier Humanize wrote, makes a theme whose other side
 * is Humanize's own. Says the theme's two sides.
 */
export async function imported(text) {
  let said
  try {
    said = JSON.parse(text)
  } catch {
    throw new Error(t('This is not a theme file'))
  }
  const both = said && [said.light, said.dark].every((it) => it && typeof it === 'object')
  if (!said || said.hmztheme !== 1 || typeof said.name !== 'string' || !(both || ['light', 'dark'].includes(said.base))) throw new Error(t('This is not a theme file'))
  const part = (base) => (both ? said[base] : said.base === base ? said : {})
  const from = ['light', 'dark'].map((base) => {
    const colors = {}
    for (const [token, value] of Object.entries(part(base).colors || {})) if (TOKENS.has(token) && isColour(value)) colors[token] = value.trim()
    return { base, colors }
  })
  const two = await create(from, said.name.trim().slice(0, 60) || t('Imported'))
  for (const one of two) {
    for (const [area] of AREAS) {
      const image = part(one.base).images?.[area]
      if (!image || typeof image.data !== 'string' || !PICTURE.test(image.data)) continue
      await picture(one.id, area, image.data)
      one.images[area] = { fit: image.fit in FITS ? image.fit : 'cover' }
    }
    save(one)
  }
  return two
}

/**
 * What an earlier Humanize kept here, kept as this one does (themed.js): done once, as the page
 * is read, before anything is painted with it. The pictures it copies are waited for by `paint`.
 */
const was = migrated(
  { pair: kept('hmz-pair', null), theme: kept('hmz-theme', null), light: kept('hmz-theme-light', null), dark: kept('hmz-theme-dark', null), themes: made() },
  OWN,
  { fresh, name: t('Custom') },
)
if (was) {
  keep('hmz-themes', JSON.stringify(was.themes))
  keep('hmz-pair', was.pair)
  if (was.mode && kept('hmz-mode', null) === null) keep('hmz-mode', was.mode)
  for (const name of ['hmz-theme', 'hmz-theme-light', 'hmz-theme-dark']) keep(name, null)
}
const moved = Promise.all(
  (was?.copies || []).flatMap(([from, to]) =>
    AREAS.map(async ([area]) => {
      const data = await picture(from, area)
      if (data) await picture(to, area, data)
    }),
  ),
).catch(() => {})
