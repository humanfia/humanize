// Themes, as an editor keeps them: those humanize comes with, a light and a dark of each pair,
// and any made in this browser on Light or Dark, alone or as a pair of its own -- a name, the
// colours it changes and a picture for any of the page's large planes, still or drawn moving --
// chosen outright or under Auto, which follows the system with the theme picked for its light
// and the one for its dark, a pair at once or any two. A theme, or a pair with both its themes,
// is written out whole as a `.hmztheme` file, which is read back in here or in any other browser.
//
// What a theme changes is kept beside the choice, for theme.js to paint before the page is
// drawn -- those humanize comes with as well, while they are chosen or paired; its pictures,
// too large for that, are kept in the browser's database and painted after.

import { OWN, PAIRS } from './presets.js'
import { keep, kept } from './shell.js'

export { OWN, PAIRS }

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

/** A theme as a menu or a list names it: its name, and whether it is light or dark. */
export function label(one) {
  return `${one.name} · ${one.base === 'dark' ? 'Dark' : 'Light'}`
}

/** Every theme: those humanize comes with, then those made here. */
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

/** Every pair: those humanize comes with, then those made here, each by its key and its name. */
export function pairs() {
  const mine = new Map()
  for (const one of made()) if (one.pair && !mine.has(one.pair)) mine.set(one.pair, { key: one.pair, name: one.name, mine: true })
  return [...PAIRS, ...[...mine.values()].filter((one) => members(one.key).length === 2)]
}

/** A pair's light and dark, in that order. */
export function members(key) {
  return themes()
    .filter((one) => one.pair === key)
    .sort((a, b) => (a.base === 'light' ? -1 : 1) - (b.base === 'light' ? -1 : 1))
}

/** The pair Auto shows, where its light and its dark are one pair's two. */
export function pairing() {
  const { light, dark } = paired()
  const [one, other] = [theme(light), theme(dark)]
  return one.pair && one.pair === other.pair && one.base === 'light' && other.base === 'dark' ? one.pair : null
}

/** Shows a pair under Auto: its light where the system is light, its dark where it is dark. */
export function usePair(key) {
  const [light, dark] = members(key)
  keep('hmz-theme-light', light.id === 'light' ? null : light.id)
  keep('hmz-theme-dark', dark.id === 'dark' ? null : dark.id)
  choose('auto')
}

/**
 * Keeps those humanize comes with that are chosen or paired beside the themes made here, for
 * theme.js, which cannot read this file before the page is drawn, to paint them.
 */
function hand() {
  const { light, dark } = paired()
  const used = new Set([chosen(), light, dark])
  const said = JSON.stringify(OWN.filter((one) => used.has(one.id) && Object.keys(one.colors).length))
  if (kept('hmz-painted', '[]') !== said) keep('hmz-painted', said)
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

/** A new id, for a theme or a pair made here. */
function fresh(kind) {
  return `${kind}${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

/** Gives a pair made here a name: both its themes have it. */
export function rename(key, name) {
  for (const one of made()) if (one.pair === key) save({ ...one, name })
}

/** Forgets a pair made here: both its themes. */
export async function removePair(key) {
  for (const one of members(key)) await remove(one.id)
}

/** A new pair, of the light and the dark given: their colours and pictures copied. */
export async function createPair(light, dark, name) {
  const key = fresh('p')
  const said = unique(name)
  return [await create(light, said, key), await create(dark, said, key)]
}

/** A new theme, on the one given or on the base named: its colours and pictures copied, in a pair where one is given. */
export async function create(from, name, pair = null) {
  const one = { id: fresh('t'), name: pair ? name : unique(name), base: from.base, colors: { ...from.colors }, images: {} }
  if (pair) one.pair = pair
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
  hand()
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

/** What a theme sets, with its pictures, as a `.hmztheme` file holds it. */
async function look(one) {
  const images = {}
  for (const [area, how] of Object.entries(one.images || {})) {
    const data = await picture(one.id, area)
    if (data) images[area] = { fit: how.fit || 'cover', data }
  }
  return { colors: { ...one.colors }, images }
}

/** A theme written out whole -- or, given a pair's key, the pair with both its themes. */
export async function written(it) {
  if (typeof it !== 'string') return { hmztheme: 1, name: it.name, base: it.base, ...(await look(it)) }
  const [light, dark] = members(it)
  return { hmztheme: 1, name: light.name, light: await look(light), dark: await look(dark) }
}

/** Saves a theme, or a pair by its key, as a `.hmztheme` file, as the browser saves a download. */
export async function exported(it) {
  const said = await written(it)
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
 * Makes a theme of a `.hmztheme` file's text -- or, where it holds a light and a dark, a pair
 * of both -- keeping what it says that a theme can hold. Says the themes made.
 */
export async function imported(text) {
  let said
  try {
    said = JSON.parse(text)
  } catch {
    throw new Error('This is not a theme file')
  }
  const both = said && typeof said.light === 'object' && typeof said.dark === 'object' && said.light && said.dark
  if (!said || said.hmztheme !== 1 || typeof said.name !== 'string' || !(both || ['light', 'dark'].includes(said.base))) throw new Error('This is not a theme file')
  const name = said.name.trim().slice(0, 60) || 'Imported'
  const key = both ? fresh('p') : null
  const named = both ? unique(name) : name
  const made = []
  for (const [base, it] of both ? [['light', said.light], ['dark', said.dark]] : [[said.base, said]]) {
    const colors = {}
    for (const [token, value] of Object.entries(it.colors || {})) if (TOKENS.has(token) && isColour(value)) colors[token] = value.trim()
    const one = await create({ id: '', base, colors, images: {} }, named, key)
    for (const [area] of AREAS) {
      const image = it.images?.[area]
      if (!image || typeof image.data !== 'string' || !PICTURE.test(image.data)) continue
      await picture(one.id, area, image.data)
      one.images[area] = { fit: image.fit in FITS ? image.fit : 'cover' }
    }
    save(one)
    made.push(one)
  }
  return made
}
