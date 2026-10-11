// Themes, as an editor keeps them: humanize's own Light and Dark, and any made in this browser on
// one of them -- a name, the colours it changes and a picture for any of the page's large
// planes, still or drawn moving -- chosen outright or under Auto, which follows the system with
// the theme picked for its light and the one for its dark. Each is written out whole as a
// `.hmztheme` file, which is read back in here or in any other browser.
//
// What a theme changes is kept beside the choice, for theme.js to paint before the page is
// drawn; its pictures, too large for that, are kept in the browser's database and painted after.

import { keep, kept } from './shell.js'

/** The colours a theme sets, by what they are of, each by its token in style.css. */
export const COLOURS = [
  ['Backgrounds', [['paper', 'Page'], ['side', 'Sidebar'], ['surface', 'Surface'], ['raised', 'Raised']]],
  ['Text', [['ink', 'Text'], ['ink-2', 'Secondary'], ['ink-3', 'Muted'], ['on-ink', 'Inverse'], ['on-fill', 'On colour'], ['link', 'Link']]],
  ['Controls', [['control', 'Button'], ['control-ink', 'Button text'], ['primary', 'Primary'], ['on-primary', 'Primary text'], ['field', 'Field'], ['edge', 'Edge']]],
  ['Lines', [['line', 'Line'], ['line-strong', 'Strong line'], ['hover', 'Hover'], ['scrim', 'Scrim']]],
  ['Accents', [['green', 'Brand'], ['cyan', 'Accent'], ['cyan-ink', 'Accent text'], ['pink', 'Highlight'], ['pink-ink', 'Highlight text'], ['lavender', 'Tertiary'], ['gold', 'Budget'], ['done', 'Success'], ['fail', 'Danger']]],
  ['Graph', [1, 2, 3, 4, 5, 6].map((n) => [`lane-${n}`, `Lane ${n}`])],
]

/** Every colour's token. */
const TOKENS = new Set(COLOURS.flatMap(([, tokens]) => tokens.map(([token]) => token)))

/** The large planes a picture can be set behind, each by the name its properties carry. */
export const AREAS = [['page', 'Page'], ['sidebar', 'Sidebar'], ['panel', 'Panel'], ['dialog', 'Dialog']]

/** How a picture fills its plane. */
export const FITS = { cover: 'Cover', contain: 'Fit', tile: 'Tile' }

/** What a picture may be: what a browser draws as an image, an SVG's animation included. */
const PICTURE = /^data:image\/(png|jpeg|gif|webp|avif|svg\+xml)(;[^,]*)?,/

/** humanize's own, which are never changed. */
export const OWN = [
  { id: 'light', name: 'Light', base: 'light', colors: {}, images: {} },
  { id: 'dark', name: 'Dark', base: 'dark', colors: {}, images: {} },
]

/** Every theme: humanize's own, then those made here. */
export function themes() {
  return [...OWN, ...made()]
}

function made() {
  try {
    return JSON.parse(kept('hmz-themes', '[]') || '[]')
  } catch {
    return []
  }
}

/** One theme, by its id. */
export function theme(id) {
  return themes().find((one) => one.id === id) || null
}

/** Which is chosen: a theme's id, or `auto`. */
export function chosen() {
  return kept('hmz-theme', null) || 'auto'
}

/** The theme Auto shows for the system's light and the one for its dark. */
export function paired() {
  const sure = (id, otherwise) => (theme(id) ? id : otherwise)
  return { light: sure(kept('hmz-theme-light', null), 'light'), dark: sure(kept('hmz-theme-dark', null), 'dark') }
}

export function choose(id) {
  keep('hmz-theme', id === 'auto' ? null : id)
  paint()
}

/** Picks the theme Auto shows for the system's `light` or its `dark`. */
export function pair(scheme, id) {
  keep(`hmz-theme-${scheme}`, id === scheme ? null : id)
  paint()
}

/** Keeps a theme made here, new or changed. */
export function save(one) {
  const all = made()
  const at = all.findIndex((other) => other.id === one.id)
  if (at < 0) all.push(one)
  else all[at] = one
  keep('hmz-themes', JSON.stringify(all))
}

/** Forgets a theme made here and its pictures; whatever showed it shows humanize's own instead. */
export async function remove(id) {
  keep('hmz-themes', JSON.stringify(made().filter((one) => one.id !== id)))
  if (chosen() === id) keep('hmz-theme', null)
  for (const scheme of ['light', 'dark']) if (kept(`hmz-theme-${scheme}`, null) === id) keep(`hmz-theme-${scheme}`, null)
  await Promise.all(AREAS.map(([area]) => picture(id, area, null)))
  paint()
}

/** A new theme, on the one given or on the base named: its colours and pictures copied. */
export async function create(from, name) {
  const one = { id: `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`, name: unique(name), base: from.base, colors: { ...from.colors }, images: {} }
  for (const [area, set] of Object.entries(from.images || {})) {
    const data = await picture(from.id, area)
    if (data) {
      await picture(one.id, area, data)
      one.images[area] = { ...set }
    }
  }
  save(one)
  return one
}

/** A name no theme has: the one given, or it numbered. */
function unique(name) {
  const taken = new Set(themes().map((one) => one.name))
  let said = name
  for (let n = 2; taken.has(said); n++) said = `${name} ${n}`
  return said
}

/**
 * Paints the theme given -- one being edited -- or the one chosen: its colours at once, as
 * theme.js does, and its pictures once read, each the latest asked for alone.
 */
let painting = 0
export async function paint(shown) {
  const mine = ++painting
  const one = window.hmzPaint(shown)
  const root = document.documentElement
  const set = {}
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
window.addEventListener('storage', (event) => event.key?.startsWith('hmz-theme') && paint())

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

/** Reads a theme's picture for an area, as a data URL; or, given one, keeps it there, or with null forgets it. */
export function picture(id, area, data) {
  const key = `${id}/${area}`
  if (data === undefined) return pictures('readonly', (store) => store.get(key)).then((got) => got || null)
  return pictures('readwrite', (store) => (data ? store.put(data, key) : store.delete(key)))
}

/** Reads a file the user gave as a data URL, refusing what is not a picture. */
export function readPicture(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => (PICTURE.test(reader.result) ? resolve(reader.result) : reject(new Error(`${file.name} is not a picture`)))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

/** Whether a browser draws what is said as a colour. */
export function isColour(said) {
  return typeof said === 'string' && said.trim() !== '' && CSS.supports('color', said.trim())
}

/** A theme written out whole, as a `.hmztheme` file holds it. */
export async function written(one) {
  const images = {}
  for (const [area, how] of Object.entries(one.images || {})) {
    const data = await picture(one.id, area)
    if (data) images[area] = { fit: how.fit || 'cover', data }
  }
  return { hmztheme: 1, name: one.name, base: one.base, colors: { ...one.colors }, images }
}

/** Saves a theme as a `.hmztheme` file, as the browser saves a download. */
export async function exported(one) {
  const blob = new Blob([JSON.stringify(await written(one), null, 2)], { type: 'application/json' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${one.name.replace(/[^\p{L}\p{N}._ -]+/gu, '').trim() || 'theme'}.hmztheme`
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(link.href), 60000)
}

/** Makes a theme of a `.hmztheme` file's text, keeping what it says that a theme can hold. */
export async function imported(text) {
  let said
  try {
    said = JSON.parse(text)
  } catch {
    throw new Error('This is not a theme file')
  }
  if (!said || said.hmztheme !== 1 || typeof said.name !== 'string' || !['light', 'dark'].includes(said.base)) throw new Error('This is not a theme file')
  const colors = {}
  for (const [token, value] of Object.entries(said.colors || {})) if (TOKENS.has(token) && isColour(value)) colors[token] = value.trim()
  const one = await create({ id: '', base: said.base, colors, images: {} }, said.name.trim().slice(0, 60) || 'Imported')
  for (const [area] of AREAS) {
    const it = said.images?.[area]
    if (!it || typeof it.data !== 'string' || !PICTURE.test(it.data)) continue
    await picture(one.id, area, it.data)
    one.images[area] = { fit: it.fit in FITS ? it.fit : 'cover' }
  }
  save(one)
  return one
}
