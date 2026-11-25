// The page's languages: how a text is said in the one the page is written in (i18n.js), which
// one that is (lang.js), and whether the catalogs hold every text the page says.
//
// The catalogs are checked against the page's own source: a translation that drops a `{name}`,
// a text in two fragments, a call that hides its text from this scan, a text one of the Chinese
// catalogs lacks, an entry no call says and a translation left as its English each fail here.
// With `STRICT` false the last three are only reported, which is how a text is written before
// its translations are.

import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'

/** Whether a text the catalogs do not cover fails, or is only reported: every area is translated, so it fails. */
const STRICT = true

const STATIC = new URL('../../../../src/hmz/web/static/', import.meta.url)
const AREAS = ['core', 'sidebar', 'chat', 'ask', 'settings', 'envs', 'themes']
const TRANSLATED = ['zh-Hans', 'zh-Hant']

/**
 * What a Chinese catalog may say exactly as English does: the names the page keeps in Latin
 * script, and a text that is nothing but what is put in it.
 */
const SAME = new Set(['Humanize', 'Ai-chan', 'Exomyth', 'EasyTier', 'OK'])

/**
 * The words of the product that have a Chinese word of their own (the glossary of
 * ARCHITECTURE.md), which a Chinese text therefore never says in Latin script.
 * A command's own spelling, as `/flow`, is lower case and is not one of them.
 */
const GLOSSED = /(?<![A-Za-z/-])(?:Daemon|Nous|Harness|Epic|Flow|Flowverse|Agent|Worktree|Runtime|Workspace|Environment|Env)s?(?![A-Za-z-])/

const root = { lang: '', dataset: {} }
const store = new Map()
Object.assign(globalThis, {
  document: { documentElement: root },
  localStorage: { getItem: (name) => store.get(name) ?? null, setItem: (name, value) => store.set(name, String(value)), removeItem: (name) => store.delete(name) },
})

const { CATALOGS, LANGUAGES, choose, chosen, lang, locale, pieces, t } = await import('../../../../src/hmz/web/static/i18n.js')

/** Does something with the page written in a language, then puts it back in English. */
function written(language, act) {
  root.lang = language
  try {
    return act()
  } finally {
    root.lang = ''
  }
}

/** Does something with entries put in the catalogs, then takes them out again. */
function holding(entries, act) {
  for (const [language, table] of Object.entries(entries)) Object.assign(CATALOGS[language], table)
  try {
    return act()
  } finally {
    for (const [language, table] of Object.entries(entries)) for (const key of Object.keys(table)) delete CATALOGS[language][key]
  }
}

test('the page is written in English where the document names none of its languages', () => {
  assert.equal(lang(), 'en')
  assert.equal(locale(), 'en')
  for (const said of ['fr', 'zh', 'zh-CN', 'constructor']) assert.equal(written(said, lang), 'en')
  for (const said of ['en', 'zh-Hans', 'zh-Hant']) assert.equal(written(said, lang), said)
  // A date is written by the browser's own tag of the language, where lang.js found one.
  root.dataset.locale = 'en-GB'
  assert.equal(locale(), 'en-GB')
  delete root.dataset.locale
})

test('in English a text is what is written at the call, with what is given put at its names', () => {
  assert.equal(t('Nothing the catalogs hold'), 'Nothing the catalogs hold')
  assert.equal(t('New chat in {name}', { name: 'atlas' }), 'New chat in atlas')
  assert.equal(t('{a} of {b}, {a} again', { a: 1, b: 2 }), '1 of 2, 1 again')
  // A name given nothing stays as written, and a text is never looked up as a name of Object's.
  assert.equal(t('From {name}'), 'From {name}')
  assert.equal(t('From {name}', {}), 'From {name}')
  assert.equal(t('toString'), 'toString')
  assert.equal(t('{constructor}', {}), '{constructor}')
})

test('what tells two English homographs apart is not said', () => {
  assert.equal(t('Open@@verb'), 'Open')
  assert.equal(t('None@@effort'), 'None')
  holding({ 'zh-Hans': { 'Open@@verb': '打开', 'Open@@state': '已打开' } }, () => {
    assert.equal(written('zh-Hans', () => t('Open@@verb')), '打开')
    assert.equal(written('zh-Hans', () => t('Open@@state')), '已打开')
    assert.equal(written('zh-Hant', () => t('Open@@state')), 'Open')
  })
})

test('a text is said in the language of the page, and in English where that language has none', () => {
  assert.equal(written('zh-Hans', () => t('Cancel')), '取消')
  assert.equal(written('zh-Hant', () => t('Copied')), '已複製')
  assert.equal(written('zh-Hans', () => t('{n}m ago', { n: 5 })), '5 分钟前')
  assert.equal(written('zh-Hans', () => t('Nothing the catalogs hold, {name}', { name: 'x' })), 'Nothing the catalogs hold, x')
  // Traditional Chinese never falls back on Simplified: English is said.
  holding({ 'zh-Hans': { 'Only in one': '只有一个' } }, () => {
    assert.equal(written('zh-Hans', () => t('Only in one')), '只有一个')
    assert.equal(written('zh-Hant', () => t('Only in one')), 'Only in one')
  })
})

test('a text that differs by number is picked by `n`, by the rules of the language it is said in', () => {
  // A text no catalog holds: what is put in for it here is all there is of it, and is taken out again.
  const key = '{n} lamps have a newer wick'
  const forms = { one: '{n} lamp has a newer wick', other: '{n} lamps have a newer wick' }
  holding({ en: { [key]: forms } }, () => {
    assert.equal(t(key, { n: 1 }), '1 lamp has a newer wick')
    assert.equal(t(key, { n: 2 }), '2 lamps have a newer wick')
    assert.equal(t(key, { n: 0 }), '0 lamps have a newer wick')
    // A language without the text says the English one, by English's rules.
    assert.equal(written('zh-Hans', () => t(key, { n: 1 })), '1 lamp has a newer wick')
    holding({ 'zh-Hans': { [key]: '{n} 盏灯有新灯芯' }, 'zh-Hant': { [key]: { other: '{n} 盞燈有新燈芯' } } }, () => {
      assert.equal(written('zh-Hans', () => t(key, { n: 1 })), '1 盏灯有新灯芯')
      assert.equal(written('zh-Hant', () => t(key, { n: 1 })), '1 盞燈有新燈芯')
    })
  })
})

test('a sentence that holds an element is given in pieces, in the order the language puts them', () => {
  const node = { tagName: 'B' }
  assert.deepEqual(pieces('From {name}', { name: node }), ['From ', node])
  assert.deepEqual(pieces('{name} said so', { name: node }), [node, ' said so'])
  assert.deepEqual(pieces('Nothing in it'), ['Nothing in it'])
  holding({ 'zh-Hans': { 'Copy {what} from {name}': '从 {name} 复制 {what}' } }, () => {
    assert.deepEqual(written('zh-Hans', () => pieces('Copy {what} from {name}', { name: node, what: 'it' })), ['从 ', node, ' 复制 ', 'it'])
  })
})

test('the choice is kept in this browser, and none kept is the system’s', () => {
  assert.deepEqual(LANGUAGES, [['', 'System'], ['en', 'English'], ['zh-Hans', '简体中文'], ['zh-Hant', '繁體中文']])
  assert.equal(chosen(), '')
  choose('zh-Hant')
  assert.equal(store.get('hmz-language'), 'zh-Hant')
  assert.equal(chosen(), 'zh-Hant')
  choose('')
  assert.equal(store.has('hmz-language'), false)
  store.set('hmz-language', 'tlh')
  assert.equal(chosen(), '')
  store.clear()
  // A browser that keeps nothing follows the system, and choosing there throws nothing.
  const { getItem, setItem } = localStorage
  localStorage.getItem = localStorage.setItem = () => {
    throw new Error('denied')
  }
  assert.equal(chosen(), '')
  choose('en')
  Object.assign(localStorage, { getItem, setItem })
})

/** What lang.js makes of a browser: what it asks for, and what it keeps. */
function resolved(languages, kept) {
  const document = { documentElement: { dataset: {} } }
  const window = {}
  const localStorage = {
    getItem: () => {
      if (kept instanceof Error) throw kept
      return kept ?? null
    },
  }
  runInNewContext(readFileSync(new URL('lang.js', STATIC), 'utf8'), { window, document, localStorage, navigator: { languages, language: languages[0] } })
  const said = { ...window.hmzLanguage() }
  assert.equal(document.documentElement.lang, said.language)
  assert.equal(document.documentElement.dataset.locale, said.locale)
  return said
}

test('with none chosen the page follows what the browser asks for', () => {
  for (const tag of ['zh-TW', 'zh-HK', 'zh-MO', 'zh-Hant', 'zh-Hant-TW', 'zh-Hant-CN', 'ZH-tw']) assert.deepEqual(resolved([tag]), { chosen: '', language: 'zh-Hant', locale: tag }, tag)
  for (const tag of ['zh', 'zh-CN', 'zh-SG', 'zh-Hans', 'zh-Hans-TW', 'zh-Hans-HK']) assert.deepEqual(resolved([tag]), { chosen: '', language: 'zh-Hans', locale: tag }, tag)
  for (const tag of ['en', 'en-US', 'en-GB']) assert.deepEqual(resolved([tag]), { chosen: '', language: 'en', locale: tag }, tag)
  for (const tag of ['fr', 'ja-JP', 'zhx', 'enx']) assert.deepEqual(resolved([tag]), { chosen: '', language: 'en', locale: 'en' }, tag)
  // The first it has a language for decides.
  assert.deepEqual(resolved(['fr', 'zh-TW', 'en-US']), { chosen: '', language: 'zh-Hant', locale: 'zh-TW' })
  assert.deepEqual(resolved(['en-GB', 'zh-CN']), { chosen: '', language: 'en', locale: 'en-GB' })
  assert.deepEqual(resolved([]), { chosen: '', language: 'en', locale: 'en' })
})

test('a language chosen is the page’s, whatever the browser asks for', () => {
  assert.deepEqual(resolved(['en-US'], 'zh-Hans'), { chosen: 'zh-Hans', language: 'zh-Hans', locale: 'zh-Hans' })
  assert.deepEqual(resolved(['zh-CN', 'en-GB'], 'en'), { chosen: 'en', language: 'en', locale: 'en-GB' })
  assert.deepEqual(resolved(['zh-CN', 'zh-HK'], 'zh-Hant'), { chosen: 'zh-Hant', language: 'zh-Hant', locale: 'zh-HK' })
  // One it does not have, or a storage that cannot be read, is none chosen.
  assert.deepEqual(resolved(['zh-TW'], 'tlh'), { chosen: '', language: 'zh-Hant', locale: 'zh-TW' })
  assert.deepEqual(resolved(['zh-CN'], new Error('denied')), { chosen: '', language: 'zh-Hans', locale: 'zh-CN' })
})

test('the page sets its language before any of it is drawn', () => {
  const page = readFileSync(new URL('index.html', STATIC), 'utf8')
  const scripts = [...page.matchAll(/<script[^>]*src="([^"]+)"/g)].map(([, src]) => src)
  assert.ok(scripts.includes('/lang.js'))
  assert.ok(scripts.indexOf('/lang.js') < scripts.indexOf('/app.js'))
  // A classic script, which runs where it stands, as the theme's does: a module would wait for the page.
  assert.match(page, /<script src="\/lang\.js"><\/script>/)
})

// ---------------------------------------------------------------------------------------------
// The catalogs against the page's own source.

/** Every script of the page but the libraries it carries and the catalogs themselves. */
function sources(dir = STATIC, under = '') {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const name = under + entry.name
    if (entry.isDirectory()) return name === 'vendor' || name === 'i18n' ? [] : sources(new URL(`${entry.name}/`, dir), `${name}/`)
    return name.endsWith('.js') && name !== 'i18n.js' && name !== 'lang.js' ? [name] : []
  })
}

/**
 * Every `t(…)` and `pieces(…)` of the scripts that import i18n.js: the text each is called with,
 * and each that hides its text.
 */
function called() {
  const keys = new Map()
  const hidden = []
  for (const file of sources()) {
    const text = readFileSync(new URL(file, STATIC), 'utf8')
    const imported = /^import \{([^}]*)\} from '[./]+\/i18n\.js'$/m.exec(text)
    if (!imported) {
      // Imported some other way -- over several lines, or whole -- its calls would go unseen.
      if (/from '[./]+\/i18n\.js'/.test(text)) hidden.push(`${file}: imports i18n.js other than as \`import { t } from '…/i18n.js'\` on one line`)
      continue
    }
    // Under its own name, or this scan would not know its calls.
    if (/\bas\b/.test(imported[1])) hidden.push(`${file}: imports under another name`)
    for (const found of text.matchAll(/(?<![\w.$])(?:t|pieces)\(\s*/g)) {
      const rest = text.slice(found.index + found[0].length)
      const literal = /^'((?:[^'\\\n]|\\.)*)'\s*([,)])/.exec(rest)
      const line = text.slice(0, found.index).split('\n').length
      if (!literal) hidden.push(`${file}:${line}`)
      else {
        const key = new Function(`return '${literal[1]}'`)()
        keys.set(key, [...(keys.get(key) || []), `${file}:${line}`])
      }
    }
  }
  return { keys, hidden }
}

/** The `{names}` of a text, in order of their spelling. */
const names = (text) => [...String(text).matchAll(/\{(\w+)\}/g)].map(([, name]) => name).sort()

/** Every text a catalog entry says: one, or one per plural form. */
const forms = (value) => (typeof value === 'string' ? [value] : Object.values(value))

const fragments = {}
for (const language of ['en', ...TRANSLATED]) {
  fragments[language] = {}
  for (const area of AREAS) fragments[language][area] = (await import(new URL(`i18n/${language}/${area}.js`, STATIC))).default
}

/** Fails where `STRICT`, and otherwise only says what it found. */
function covered(context, what, found) {
  if (!found.length) return
  const said = `${what}: ${found.length}\n  ${found.slice(0, 40).join('\n  ')}${found.length > 40 ? `\n  … and ${found.length - 40} more` : ''}`
  if (STRICT) assert.fail(said)
  context.diagnostic(`(reported, not failed: STRICT is false) ${said}`)
}

test('every call names its text as one single-quoted literal, which is what the catalogs are checked by', () => {
  assert.deepEqual(called().hidden, [])
})

test('each language has a fragment of every area, and a catalog is its fragments together', () => {
  for (const language of ['en', ...TRANSLATED]) {
    assert.deepEqual(readdirSync(new URL(`i18n/${language}/`, STATIC)).sort(), AREAS.map((area) => `${area}.js`).sort(), language)
    assert.deepEqual(CATALOGS[language], Object.assign({}, ...AREAS.map((area) => fragments[language][area])), language)
  }
  assert.deepEqual(readdirSync(new URL('i18n/', STATIC)).sort(), ['en', 'en.js', 'zh-Hans', 'zh-Hans.js', 'zh-Hant', 'zh-Hant.js'])
})

test('no text is in two fragments of a language', () => {
  for (const [language, areas] of Object.entries(fragments)) {
    const held = new Map()
    for (const [area, table] of Object.entries(areas)) {
      for (const key of Object.keys(table)) {
        assert.equal(held.get(key), undefined, `${language}: ${JSON.stringify(key)} is in ${held.get(key)} and in ${area}; a text two areas say belongs to core`)
        held.set(key, area)
      }
    }
  }
})

test('an English entry is the forms of a text that differs by number, and nothing else', () => {
  for (const [key, value] of Object.entries(CATALOGS.en)) {
    assert.equal(typeof value, 'object', `en: ${JSON.stringify(key)} is its own English and needs no entry`)
    assert.deepEqual(Object.keys(value).sort(), ['one', 'other'], key)
    assert.ok(names(key).includes('n'), `en: ${JSON.stringify(key)} is picked by {n}`)
    for (const form of forms(value)) assert.deepEqual(names(form), names(key), key)
  }
})

test('a translation keeps the names of its text, and is a text or its plural forms', () => {
  for (const language of TRANSLATED) {
    for (const [key, value] of Object.entries(CATALOGS[language])) {
      const where = `${language}: ${JSON.stringify(key)}`
      assert.ok(typeof value === 'string' || (value && typeof value.other === 'string'), where)
      for (const form of forms(value)) {
        assert.equal(typeof form, 'string', where)
        assert.notEqual(form.trim(), '', where)
        assert.deepEqual(names(form), names(key), where)
        assert.doesNotMatch(form, /@@/, where)
      }
    }
  }
})

test('every text the page says is in both Chinese catalogs', (context) => {
  const { keys } = called()
  for (const language of TRANSLATED) {
    covered(context, `${language} lacks`, [...keys].filter(([key]) => !Object.hasOwn(CATALOGS[language], key)).map(([key, at]) => `${JSON.stringify(key)} (${at[0]})`))
  }
})

test('every text that differs by number in English has its forms', (context) => {
  // Not found by the scan: named here by whoever writes the call, in i18n/en/<area>.js.
  const { keys } = called()
  covered(context, 'en holds forms of a text no call says', Object.keys(CATALOGS.en).filter((key) => !keys.has(key)).map((key) => JSON.stringify(key)))
})

test('no catalog holds a text the page no longer says', (context) => {
  const { keys } = called()
  for (const language of TRANSLATED) {
    covered(context, `${language} holds what no call says`, Object.keys(CATALOGS[language]).filter((key) => !keys.has(key)).map((key) => JSON.stringify(key)))
  }
})

test('a translation is not its English left as it was, but for the names kept in Latin script', (context) => {
  for (const language of TRANSLATED) {
    covered(context, `${language} says as English does`, Object.entries(CATALOGS[language]).filter(([key, value]) => forms(value).includes(key.replace(/@@.*$/s, '')) && !SAME.has(key) && /[A-Za-z]{2}/.test(key.replace(/\{\w+\}/g, ''))).map(([key]) => JSON.stringify(key)))
  }
})

test('a community node that is up is said to be online, not connected as a daemon reached is', () => {
  // `up` alone is the state of this page's link to a daemon; a node listed is only online.
  assert.deepEqual([CATALOGS['zh-Hans']['up@@node'], CATALOGS['zh-Hant']['up@@node']], ['在线', '上線'])
  for (const language of TRANSLATED) assert.notEqual(CATALOGS[language]['up@@node'], CATALOGS[language].up, language)
  assert.equal(t('up@@node'), 'up')
})

test('a Chinese text says the product’s words by the glossary, never in Latin script', () => {
  for (const language of TRANSLATED) {
    const found = Object.entries(CATALOGS[language]).filter(([, value]) => forms(value).some((form) => GLOSSED.test(form))).map(([key]) => JSON.stringify(key))
    assert.deepEqual(found, [], language)
  }
})
