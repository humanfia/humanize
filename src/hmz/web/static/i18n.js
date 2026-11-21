// What the page says, in the language it is written in: English, Simplified Chinese or
// Traditional Chinese, as lang.js set on the document before anything was drawn. The English
// text is itself what a string is looked up by, so English is what is written at the call and
// what anything without a translation falls back to. The catalogs are loaded with the page,
// all three: a string is translated as it is drawn, with nothing to wait for. A language is
// changed by keeping the choice and opening the page again (Settings > App > Language), which
// is why a table made as a module loads may call `t` at once.

import en from './i18n/en.js'
import zhHans from './i18n/zh-Hans.js'
import zhHant from './i18n/zh-Hant.js'

/** Every language the page is written in, and its catalog: what each English text is in it. */
export const CATALOGS = { en, 'zh-Hans': zhHans, 'zh-Hant': zhHant }

/** What Language offers: the choice kept, and what it is called -- a language in its own words, never translated. */
export const LANGUAGES = [
  ['', 'System'],
  ['en', 'English'],
  ['zh-Hans', '简体中文'],
  ['zh-Hant', '繁體中文'],
]

/** Where the choice is kept in this browser: absent, the system's language is followed. */
const KEPT = 'hmz-language'

/** The language the page is written in: what the document says, or English where it says none of them. */
export function lang() {
  const said = globalThis.document?.documentElement?.lang
  return Object.hasOwn(CATALOGS, said) ? said : 'en'
}

/** The tag a date or a number is written by: the browser's own of the page's language, where lang.js found one. */
export function locale() {
  return globalThis.document?.documentElement?.dataset?.locale || lang()
}

const rules = {}

/** A text in the page's language with its `{names}` still in it, or in English where the language has none. */
function said(key, vars) {
  const at = lang()
  const from = Object.hasOwn(CATALOGS[at], key) ? at : 'en'
  // What tells two English homographs apart, after `@@`, is no part of what is said.
  let found = Object.hasOwn(CATALOGS[from], key) ? CATALOGS[from][key] : key.replace(/@@.*$/s, '')
  // One text per plural form of the language it is in, picked by `n`.
  if (typeof found === 'object') found = found[(rules[from] ||= new Intl.PluralRules(from)).select(Number(vars?.n))] ?? found.other
  return found
}

/** A text cut at its `{names}`, each replaced by what is given for it; one given nothing stays as written. */
function filled(text, vars = {}) {
  return text.split(/\{(\w+)\}/).map((bit, at) => (at % 2 && Object.hasOwn(vars, bit) ? vars[bit] : at % 2 ? `{${bit}}` : bit))
}

/**
 * A text the page says, in the language it is written in.
 *
 * @param {string} key The English text, written as a single-quoted literal, `{names}` where
 *   something is put in; `@@note` after it where the same English is two different texts.
 * @param {Record<string, unknown>} [vars] What is put at each name; `n` is the number a plural is picked by.
 */
export function t(key, vars) {
  return filled(said(key, vars), vars).join('')
}

/**
 * The same, as the pieces of a sentence that holds an element: strings, and each thing given
 * as it was given, in the order the language puts them. Given to `h()` or `fill()` as kids.
 */
export function pieces(key, vars) {
  return filled(said(key, vars), vars).filter((bit) => bit !== '')
}

/** The choice this browser keeps: one of `LANGUAGES`, `''` for the system's. */
export function chosen() {
  try {
    const kept = localStorage.getItem(KEPT)
    return LANGUAGES.some(([code]) => code === kept) ? kept : ''
  } catch {
    return ''
  }
}

/** Keeps a choice; the page is written in it once it is opened again. */
export function choose(code) {
  try {
    if (code) localStorage.setItem(KEPT, code)
    else localStorage.removeItem(KEPT)
  } catch {
    // A browser that keeps nothing follows the system.
  }
}

// Chosen in another tab, it is this tab's language too: it opens again in it.
globalThis.addEventListener?.('storage', (event) => {
  if (event.key === KEPT) location.reload()
})
